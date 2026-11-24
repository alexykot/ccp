"""`ccp tasks dry-run`: a task's dod_check commands run at the integration tip, and with `--write` their
dry-run records written into the task file from what they printed (SPEC §21.1, §5.5).

The task file is read in the checkout the command runs in; the commands run, each through `bash -c`, in a
temporary worktree detached at `origin/<integration_branch>`, removed afterwards, or with `--here` in that
checkout at its HEAD, so a worker runs its own claimed task's check as the dry run does. The check grammar is
tasklog's (house rule E22); what to run, the record and the printout are worked out on plain values here (E15).
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ccp import queue, rules, tasklog, wt
from ccp.config import Config

STEP_TIMEOUT_S = 300  # each step's time limit; its process group is killed on timeout
FIRST_LINE_CAP = 160  # characters of a step's first output line kept in the printout and the record
NOT_RUN = "not run"   # a step that is not one backticked command and nothing else, holds a placeholder, or a marked check's
PLACEHOLDER_RE = re.compile(r"<[A-Za-z][^<>\n]*>")  # §21.1: a step's command holding one is not run
HERE_INDENT = "      "  # §21.1 `--here`: each line of a step's whole output, under its line
REFUSED = 3           # §10.6: a task that is done, dropped or claimed has no dry run
USAGE = 2             # §21.1: `--here` with `--write`, or a `--check` id the task does not have


@dataclass(frozen=True)
class Ran:
    """One step's run: its number, its command, its exit code (None: timed out), its output's line count, its
    first line and its whole output's lines."""
    step: str
    command: str
    code: int | None
    lines: int
    first: str
    output: tuple[str, ...] = ()


def refusal(tid: str, status: object, claimed: bool, here: bool = False) -> str | None:
    """§21.1: why a task has no dry run, or None. A done or dropped task's checks are walked; a claimed task's
    file is edited only in its PR (§10.5), so only a run `--here`, which writes nothing, takes one."""
    if status in tasklog.TERMINAL:
        return f"{tid} is {status}: a dry run is for a task not yet done or dropped (SPEC §21.1)"
    if claimed and not here:
        return (f"{tid} is claimed: its file is edited only in its PR (SPEC §10.5); its worker runs a check in its "
                "own checkout with --here")
    return None


def usage_problem(write: bool, here: bool) -> str | None:
    """§21.1: a flag pair the command refuses (exit 2), or None: `--here` writes nothing, so not with `--write`."""
    if write and here:
        return "--here writes nothing, so it takes no --write: a dry-run record is written from the tip (SPEC §21.1)"
    return None


def only(tid: str, checks: list[tuple[str, list[tuple[str, str | None]]]],
         check: str | None) -> tuple[list[tuple[str, list[tuple[str, str | None]]]], str | None]:
    """§21.1 `--check`: the one check named, or every check when none is named; with an id the task does not
    have, no check and why, naming the ids it has."""
    if check is None:
        return checks, None
    picked = [c for c in checks if c[0] == check]
    if picked:
        return picked, None
    ids = ", ".join(cid for cid, _ in checks) or "none"
    return [], f"{tid} has no dod_check {check} (its checks: {ids})"


def claimed(st: dict[str, object]) -> bool:
    """§10.5: the queue holds a live lease on the task (`lease_holder` set, its queue status neither done
    nor dropped)."""
    return bool(st.get("lease_holder")) and st.get("status") not in tasklog.TERMINAL


def outcome(step: str, command: str, code: int | None, output: str) -> Ran:
    """A step's run, from its exit code and its whole output."""
    lines = output.splitlines()
    first = lines[0] if lines else ""
    if len(first) > FIRST_LINE_CAP:
        first = first[:FIRST_LINE_CAP] + "…"
    return Ran(step, command, code, len(lines), first, tuple(lines))


def _span(s: str) -> str:
    """`s` as one code span, fenced by more backticks than any run in it."""
    run = longest = 0
    for c in s:
        run = run + 1 if c == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = " " if s.startswith("`") or s.endswith("`") else ""
    return f"{fence}{pad}{s}{pad}{fence}"


def said(r: Ran) -> str:
    """What one step's run printed, in a few words."""
    how = f"timed out after {STEP_TIMEOUT_S} s" if r.code is None else f"exited {r.code}"
    if not r.lines:
        return f"step {r.step} {how}, no output"
    first = f"first: {_span(r.first)}" if r.first.strip() else "first line blank"
    return f"step {r.step} {how}, {r.lines} line{'s' if r.lines != 1 else ''}, {first}"


def record(ran: list[Ran]) -> str:
    """A check's dry-run record (what follows ``dry run (`<sha>`): ``) from the runs of its steps."""
    return "; ".join(said(r) for r in ran) + "."


def plan(text: str) -> list[tuple[str, list[tuple[str, str | None]]]]:
    """Each dod_check of a task file's text, by id, with its numbered steps: the command a step holds, or
    None for a step that is not one backticked command and nothing else."""
    return [(c.id, tasklog.check_steps(c.block)) for c in tasklog.checks(text)]


def placeholder(cmd: str) -> str | None:
    """§21.1: the first placeholder a step's command holds (as `<your run>`), or None."""
    m = PLACEHOLDER_RE.search(cmd)
    return m.group(0) if m else None


def runnable(steps: list[tuple[str, str | None]]) -> list[tuple[str, str]]:
    """§21.1: the steps a dry run runs, by number and command: each one backticked command holding no placeholder."""
    return [(n, cmd) for n, cmd in steps if cmd is not None and placeholder(cmd) is None]


def marked(text: str) -> set[str]:
    """§5.5: the ids of the checks marked `runs_on: operator-machine`, which a dry run does not run: the workers
    cannot take them, and their dry-run line stays as it is."""
    return {c.id for c in tasklog.checks(text) if c.on_operator_machine}


def printout(tid: str, sha: str, ref: str, checks: list[tuple[str, list[tuple[str, str | None]]]],
             runs: dict[str, list[Ran]], skip: set[str] | frozenset[str] = frozenset(),
             whole: bool = False) -> list[str]:
    """The lines `ccp tasks dry-run` prints: per check, each step run (its command, exit code, line count and
    first line, then with `whole` (`--here`) each line of its output) and each other step as not run, naming the
    placeholder a command holds; a check in `skip` (marked, §5.5) as not run, whole."""
    out = [f"tasks dry-run {tid} at {sha} ({ref})"]
    for cid, steps in checks:
        out.append(f"  {cid}:")
        if cid in skip:
            out.append(f"    {NOT_RUN}: runs on the operator's machine "
                       f"(`{tasklog.RUNS_ON_KEY}: {tasklog.RUNS_ON_OPERATOR}`, SPEC §5.5)")
            continue
        done = {r.step: r for r in runs.get(cid, [])}
        if not steps:
            out.append(f"    no numbered step: {NOT_RUN}")
        for n, cmd in steps:
            ph = None if cmd is None else placeholder(cmd)
            if ph is not None:
                out.append(f"    step {n}: {NOT_RUN} (holds the placeholder {_span(ph)})")
            elif cmd is not None and n in done:
                out.append(f"    {said(done[n])} ({_span(cmd)})")
                if whole:
                    out.extend(HERE_INDENT + ln for ln in done[n].output)
            else:
                out.append(f"    step {n}: {NOT_RUN} (not one backticked command and nothing else)")
    return out


def run_step(cmd: str, cwd: Path, timeout: int = STEP_TIMEOUT_S) -> tuple[int | None, str]:
    """(exit code, stdout and stderr) of `bash -c cmd` in `cwd`; (None, …) after `timeout` seconds, when the
    command's whole process group is killed."""
    p = subprocess.Popen(["bash", "-c", cmd], cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, env=rules.product_env(), start_new_session=True)
    try:
        raw, _ = p.communicate(timeout=timeout)
        code: int | None = p.returncode
    except subprocess.TimeoutExpired:
        _kill(p.pid)
        raw, _ = p.communicate()
        code = None
    except BaseException:
        _kill(p.pid)
        p.wait()
        raise
    return code, (raw or b"").decode(errors="replace")


def _kill(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def dry_run(cfg: Config, task: str, write: bool, check: str | None = None, here: bool = False) -> int:
    """§21.1 `ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]`: print each check's runs (only
    `check`'s when given); with `write`, set each check's record from them in the task file. With `here`, the
    steps run in this checkout at its HEAD and nothing is written. Exit 2 for `here` with `write` or a check the
    task does not have, 3 for a done, dropped or (without `here`) claimed task; a QueueError for no queue, an
    unknown task or no integration tip."""
    bad = usage_problem(write, here)
    if bad:
        print(f"ccp tasks dry-run: {bad}", file=sys.stderr)
        return USAGE
    q = queue.root()
    meta = queue.task_meta(cfg, task)
    tid = str(meta["task_id"])
    why = refusal(tid, tasklog.canonical_status(meta.get("status")), claimed(queue.load_task_state(q, tid)), here)
    if why:
        print(f"ccp tasks dry-run: {why}", file=sys.stderr)
        return REFUSED
    path: Path = meta["_file"]
    text = path.read_text()
    checks, missing = only(tid, plan(text), check)
    if missing:
        print(f"ccp tasks dry-run: {missing}", file=sys.stderr)
        return USAGE
    skip = marked(text)
    if here:
        return _here(cfg, tid, checks, skip)
    sha = wt.tip(cfg, q)
    ref = f"origin/{queue.integration_branch(q)}"
    main = wt.main_checkout(cfg)
    tmp = Path(tempfile.mkdtemp(prefix="ccp-dry-run-"))
    tree = tmp / "tree"
    runs: dict[str, list[Ran]] = {}
    try:
        wt.add_unrecorded(cfg, main, tree, sha)  # §12.1: with the worktrees.links paths, as in any plane worktree
        for cid, steps in checks:
            for n, cmd in [] if cid in skip else runnable(steps):
                runs.setdefault(cid, []).append(outcome(n, cmd, *run_step(cmd, tree)))
    finally:
        wt.remove_unrecorded(main, tree)
        shutil.rmtree(tmp, ignore_errors=True)
        queue.git(main, "worktree", "prune")  # a tree `worktree remove` could not drop is unregistered once deleted
    short = sha[:7]
    for line in printout(tid, short, ref, checks, runs, skip):
        print(line)
    if write:
        records = {cid: record(ran) for cid, ran in runs.items()}
        now = path.read_text()  # the file as it is now: an edit made while the steps ran is kept
        new = tasklog.with_dry_runs(now, short, records)
        if new != now:
            path.write_text(new)
        print(f"wrote {len(records)} dry-run record(s) to {cfg.rel(path)}")
    return 0


def _here(cfg: Config, tid: str, checks: list[tuple[str, list[tuple[str, str | None]]]], skip: set[str]) -> int:
    """§21.1 `--here`: the steps run in the checkout the command runs in, at its HEAD, and each one's whole output
    is printed; nothing is written."""
    sha = queue.git(cfg.root, "rev-parse", "HEAD", check=True).stdout.strip()  # before a step can move it
    runs = {cid: [outcome(n, cmd, *run_step(cmd, cfg.root)) for n, cmd in runnable(steps)]
            for cid, steps in checks if cid not in skip}
    for line in printout(tid, sha[:7], "HEAD, here", checks, runs, skip, whole=True):
        print(line)
    return 0
