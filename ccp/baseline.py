"""Failures already on the integration branch (SPEC §21.2): a failing `ccp docs check` or `ccp tasks check`
runs the same command at the branch's merge base with `origin/<integration>`, and a failure the base shows
too, outside what the branch changes, is reported as pre-existing instead of failing the command. The
verifier's gate is those two commands (§21.8), so it judges the same way.

The decision (`split`, `comparable`, `names`) is on plain values; `judge` gathers its inputs from git and
from the run at the base (`run_at_base`), which is the running `ccp` with a temporary detached worktree of
the base as its root, writing its failures to the file `BASE_RUN` names.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

from ccp.config import Config
from ccp.envvars import envvar, for_child
from ccp.rules import OUTPUT_CAP, CheckRun

BASE_RUN = "CCP_BASE_RUN"  # set for the run at the base: the command writes its failures, as JSON, to this file
CHECKER_DIRS = ("bin/", "ccp/")  # the plane's own `ccp`, in a repository that holds it
HEADING = "pre-existing on {integ} at {sha7}, not this change's: report it under Friction"

# A path is named when it stands whole: at the line start or after whitespace, a colon or a backtick (a
# command line also after a quote, a parenthesis or `=`), optionally as `./<path>`, and not run on into a
# longer path (`a.md.bak`, `a.md/x`).
_LINE_START = r"(?:^|(?<=[\s:`]))"
_CMD_START = r"(?:^|(?<=[\s:`'\"()=]))"
_END = r"(?![\w/-]|\.\w)"


@dataclass(frozen=True)
class Failure:
    """One failure line as the command prints it. A command check's (`architect.checks`, `docs.checks`)
    also carries its key (`check <id>`, `docs check <id>`), its command and its whole kept output."""
    line: str
    check: str | None = None
    cmd: str = ""
    output: str = ""
    timed_out: bool = False


@dataclass
class Judged:
    """What the command prints: the failures that fail it, and the pre-existing ones under `heading`."""
    failing: list[str]
    preexisting: list[str] = field(default_factory=list)
    heading: str = ""


def rule_failures(lines: Iterable[str]) -> list[Failure]:
    return [Failure(line) for line in lines]


def check_failures(kind: str, runs: Iterable[CheckRun]) -> list[Failure]:
    """The failing runs of one kind of check command (`check` or `docs check`), as `<kind> <failure line>`."""
    return [Failure(f"{kind} {r.failure}", f"{kind} {r.id}", r.cmd, r.output, r.code is None)
            for r in runs if r.failure]


# ---------------------------------------------------------------- the decision, on plain values

def names(text: str, path: str, command: bool = False) -> bool:
    """Whether `text` (a failure line, or with `command` a check's command line) names `path` whole."""
    start = _CMD_START if command else _LINE_START
    return re.search(rf"{start}(?:\./)?{re.escape(path)}{_END}", text, re.M) is not None


def comparable(base: str | None, head: str | None) -> bool:
    """Whether there is a merge base to compare with: one exists, and it is not `HEAD` itself (the
    integration tip, whose failures are all its own)."""
    return bool(base) and bool(head) and base != head


def checker_changed(changed: Iterable[str], holds_ccp: bool) -> bool:
    """Whether the branch changes the repository's own `ccp`, in a repository that holds it."""
    return holds_ccp and any(p.startswith(CHECKER_DIRS) for p in changed)


def _normalised(text: str, roots: Iterable[tuple[str, str]]) -> str:
    for old, new in roots:
        if old:
            text = text.replace(old, new)
    return text


def _preexisting(f: Failure, base_rules: set[str], base_checks: dict[str, Failure], changed: list[str],
                 roots: list[tuple[str, str]]) -> bool:
    if f.check is None:
        return f.line in base_rules and not any(names(f.line, p) for p in changed)
    b = base_checks.get(f.check)
    if b is None or f.timed_out or b.timed_out or not f.output.strip():
        return False
    if len(f.output) >= OUTPUT_CAP or len(b.output) >= OUTPUT_CAP or any(names(f.cmd, p, True) for p in changed):
        return False
    seen = set(_normalised(b.output, roots).splitlines())
    return all(line in seen for line in f.output.splitlines())


def split(head: list[Failure], base: list[Failure] | None, changed: list[str], holds_ccp: bool = False,
          roots: Iterable[tuple[str, str]] = ()) -> tuple[list[str], list[str]]:
    """(the failing lines, the pre-existing lines) of `head`'s failures, each list in `head`'s order.

    `base` is the failures of the same command at the merge base (None: no base run, so every failure
    counts); `changed` the paths the branch changes since the base; `holds_ccp` whether the repository
    holds the `ccp` package; `roots` the (base worktree root, product root) pairs that normalise the
    base's check output. A rule line is pre-existing when the base prints it too and it names no changed
    path. A command check is pre-existing only when it fails at the base too, neither side timed out or
    reached the kept-output cap, its command names no changed path, its output at `HEAD` is not empty,
    and every line of it is a line of the base's output. A branch that changes the checker leaves every
    failure counting."""
    if base is None or checker_changed(changed, holds_ccp):
        return [f.line for f in head], []
    base_rules = {f.line for f in base if f.check is None}
    base_checks = {f.check: f for f in base if f.check is not None}
    pairs = list(roots)
    failing: list[str] = []
    pre: list[str] = []
    for f in head:
        (pre if _preexisting(f, base_rules, base_checks, changed, pairs) else failing).append(f.line)
    return failing, pre


# ---------------------------------------------------------------- the run at the base

def emit(failures: list[Failure]) -> bool:
    """In the run at a base (`BASE_RUN` set): write `failures` to the file it names and return True;
    elsewhere False, writing nothing."""
    out = envvar(BASE_RUN)
    if not out:
        return False
    Path(out).write_text(json.dumps([asdict(f) for f in failures]))
    return True


def _read(path: Path) -> list[Failure] | None:
    try:
        rows = json.loads(path.read_text())
        return [Failure(**r) for r in rows]
    except (OSError, ValueError, TypeError):
        return None


def integration_branch() -> str:
    """The binding's integration branch when QUEUE_ROOT is set, else `main`."""
    from ccp import queue  # noqa: PLC0415
    q = os.environ.get("QUEUE_ROOT")
    if q:
        try:
            return queue.integration_branch(Path(q))
        except (OSError, ValueError):
            pass
    return "main"


def run_at_base(cfg: Config, sha: str, argv: list[str]) -> tuple[list[Failure] | None, list[tuple[str, str]]]:
    """The failures `ccp <argv>` reports at `sha`, run by this `ccp` in a temporary detached worktree
    outside the product root, removed afterwards whatever happens, with QUEUE_ROOT unset and
    `CCP_BINDINGS_DIR` the bindings directory this run resolved; and the (worktree root, product root)
    pairs that normalise its output. None when the worktree cannot be made or the run reports nothing
    readable."""
    from ccp import queue, wt  # noqa: PLC0415
    main = wt.main_checkout(cfg)
    tmp = Path(tempfile.mkdtemp(prefix="ccp-base-run-"))
    tree, out = tmp / "tree", tmp / "failures.json"
    roots = [(str(tree.resolve()), str(cfg.root.resolve())), (str(tree), str(cfg.root))]
    try:
        try:
            wt.add_unrecorded(cfg, main, tree, sha)
        except queue.QueueError:
            return None, roots
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "CCP_ROOT")}
        env.update(for_child({BASE_RUN: str(out), "CCP_BINDINGS_DIR": str(queue.lib.bindings_dir()),
                              "CCP_NO_BINDING_QUEUE": "1"}))
        r = subprocess.run([sys.executable, str(queue.CCP_BIN), "--root", str(tree), *argv], cwd=tree, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True)
        return (_read(out) if r.returncode in (0, 1) else None), roots
    finally:
        wt.remove_unrecorded(main, tree)
        shutil.rmtree(tmp, ignore_errors=True)


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def changed_paths(root: Path, base: str) -> list[str] | None:
    """The paths the commits since `base` change, as the failure lines print them: NUL-separated and
    unquoted (`core.quotepath` off), so a path with non-ASCII characters is named whole. None when git
    fails."""
    r = subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=off", "diff", "--name-only", "-z",
                        f"{base}...HEAD"], capture_output=True, encoding="utf-8", errors="surrogateescape")
    return [p for p in r.stdout.split("\0") if p] if r.returncode == 0 else None


def judge(cfg: Config, failures: list[Failure], argv: list[str]) -> Judged:
    """`failures`, the command's at `HEAD`, judged against the same command at the merge base of `HEAD` and
    `origin/<integration>` as the checkout has it (nothing fetched). With no failures, no base, a base
    equal to `HEAD`, a branch that changes the checker, or no run at the base: every failure counts."""
    if not failures:
        return Judged([])
    lines = [f.line for f in failures]
    integ = integration_branch()
    head = _git(cfg.root, "rev-parse", "HEAD")
    base = _git(cfg.root, "merge-base", "HEAD", f"origin/{integ}")
    if not comparable(base, head):
        return Judged(lines)
    changed = changed_paths(cfg.root, str(base))
    if changed is None:
        return Judged(lines)
    holds_ccp = (cfg.root / "ccp" / "__init__.py").is_file()
    if checker_changed(changed, holds_ccp):
        return Judged(lines)
    found, roots = run_at_base(cfg, str(base), argv)
    failing, pre = split(failures, found, changed, holds_ccp, roots)
    return Judged(failing, pre, HEADING.format(integ=integ, sha7=str(base)[:7]) if pre else "")
