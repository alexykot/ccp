"""`ccp tasks dry-run`: a task's dod_check commands run at the integration tip, and with `--write` their
dry-run records written into the task file from what they printed (SPEC §21.1, §5.5).

The task file is read in the checkout the command runs in; the commands run in a temporary worktree
detached at `origin/<integration_branch>`, removed afterwards. The check grammar is tasklog's (house
rule E22); what to run, the record and the printout are worked out on plain values here (E15).
"""
from __future__ import annotations

import os
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
NOT_RUN = "not run"   # a step that is not one backticked command and nothing else
REFUSED = 3           # §10.6: a task that is done, dropped or claimed has no dry run


@dataclass(frozen=True)
class Ran:
    """One step's run: its number, its command, its exit code (None: timed out), its output's line count and
    its first line."""
    step: str
    command: str
    code: int | None
    lines: int
    first: str


def refusal(tid: str, status: object, claimed: bool) -> str | None:
    """§21.1: why a task has no dry run, or None. A done or dropped task's checks are walked; a claimed task's
    file is edited only in its PR (§10.5)."""
    if status in tasklog.TERMINAL:
        return f"{tid} is {status}: a dry run is for a task not yet done or dropped (SPEC §21.1)"
    if claimed:
        return f"{tid} is claimed: its file is edited only in its PR (SPEC §10.5)"
    return None


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
    return Ran(step, command, code, len(lines), first)


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
    """Each dod_check of a task file's text, by id, with its numbered steps: the command a step runs, or
    None for a step that is not one backticked command and nothing else."""
    return [(c.id, tasklog.check_steps(c.block)) for c in tasklog.checks(text)]


def printout(tid: str, sha: str, ref: str, checks: list[tuple[str, list[tuple[str, str | None]]]],
             runs: dict[str, list[Ran]]) -> list[str]:
    """The lines `ccp tasks dry-run` prints: per check, each step run (its command, exit code, line count and
    first line) and each other step as not run."""
    out = [f"tasks dry-run {tid} at {sha} ({ref})"]
    for cid, steps in checks:
        out.append(f"  {cid}:")
        done = {r.step: r for r in runs.get(cid, [])}
        if not steps:
            out.append(f"    no numbered step: {NOT_RUN}")
        for n, cmd in steps:
            out.append(f"    {said(done[n])} ({_span(cmd)})" if cmd is not None and n in done
                       else f"    step {n}: {NOT_RUN} (not one backticked command and nothing else)")
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


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def dry_run(cfg: Config, task: str, write: bool) -> int:
    """§21.1 `ccp tasks dry-run <id> [--write]`: print each check's runs; with `write`, set each check's record
    from them in the task file. Exit 3 for a done, dropped or claimed task; a QueueError for no queue, an
    unknown task or no integration tip."""
    q = queue.root()
    meta = queue.task_meta(cfg, task)
    tid = str(meta["task_id"])
    why = refusal(tid, tasklog.canonical_status(meta.get("status")), claimed(queue.load_task_state(q, tid)))
    if why:
        print(f"ccp tasks dry-run: {why}", file=sys.stderr)
        return REFUSED
    path: Path = meta["_file"]
    text = path.read_text()
    checks = plan(text)
    sha = wt.tip(cfg, q)
    ref = f"origin/{queue.integration_branch(q)}"
    main = wt.main_checkout(cfg)
    tmp = Path(tempfile.mkdtemp(prefix="ccp-dry-run-"))
    tree = tmp / "tree"
    runs: dict[str, list[Ran]] = {}
    try:
        r = _git(main, "worktree", "add", "-q", "--detach", str(tree), sha)
        if r.returncode != 0:
            raise queue.QueueError(f"git worktree add {tree}: {(r.stderr or r.stdout).strip()[:300]}", 1)
        wt._link(cfg, main, tree)  # noqa: SLF001  (§12.1: the worktrees.links paths, as in any plane worktree)
        for cid, steps in checks:
            for n, cmd in steps:
                if cmd is not None:
                    runs.setdefault(cid, []).append(outcome(n, cmd, *run_step(cmd, tree)))
    finally:
        _git(main, "worktree", "remove", "--force", str(tree))
        shutil.rmtree(tmp, ignore_errors=True)
        _git(main, "worktree", "prune")
    short = sha[:7]
    for line in printout(tid, short, ref, checks, runs):
        print(line)
    if write:
        records = {cid: record(ran) for cid, ran in runs.items()}
        now = path.read_text()  # the file as it is now: an edit made while the steps ran is kept
        new = tasklog.with_dry_runs(now, short, records)
        if new != now:
            path.write_text(new)
        print(f"wrote {len(records)} dry-run record(s) to {cfg.rel(path)}")
    return 0
