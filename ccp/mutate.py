"""`ccp mutate` (SPEC §20.6): does the named test check what it claims? It applies one mutant at a
time in a mutation worktree, runs the product's one-test command, and records the mutant killed only
when that test fails.

  ccp mutate --run RUN_ID --test ID --mutant M [--mutant M …]

A mutant is `<file>:<old>=><new>` (the text `old`, found exactly once in the file, relative to the
worktree's root, becomes `new`) or the path of a patch `git apply` takes. Every mutant is checked
before anything runs. Then the named test runs once unmutated: a test that fails already proves
nothing, so the command stops there. Each mutant is applied alone, the test runs (plane.json
`mutate.command` with `{test}` filled in shell-quoted, in the worktree's root, in its own process group,
killed after `mutate.timeout_seconds`, which counts as the test failing), and every file the mutant
touched is written back byte for byte (a file or directory it made is removed), and checked, before
the next. A SIGTERM at any point of the call kills the running test, restores the files and exits 143.

It runs only from a recorded `mut` worktree (`ccp wt create --kind mut`) of the run's task, and only
for a run that is still open. Each mutant adds a row to the run record's `mutation` list: the test id,
the mutant's number, kind, files and a digest, killed or survived, the exit code and seconds; never
the mutant's text, old or new, or the test's output, which goes to a log next to the run's record. The call ends
with one `run`/`recorded` event. Exit 0 when every mutant was killed, 1 when one survived or the
unmutated test failed, 2 for a usage or configuration problem.
"""
from __future__ import annotations

import hashlib
import os
import shlex
import shutil
import signal
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from ccp import runs
from ccp.config import Config, fill
from ccp.queue import QueueError, emit, git, iso

SEP = "=>"


def _inside(root: Path, p: Path) -> bool:
    return p == root or root in p.parents


def parse(root: Path, spec: str, cwd: Path) -> dict[str, Any]:
    """One `--mutant`: a substitution when it holds `=>`, else a patch file. Checked against the
    unmutated tree; nothing is written."""
    if SEP in spec:
        target, _, new = spec.partition(SEP)
        rel, colon, old = target.partition(":")
        if not colon or not rel or not old:
            raise QueueError(f"mutant {spec!r}: a substitution is <file>:<old>=><new>, with a file and the old text", 2)
        if Path(rel).is_absolute() or ".." in Path(rel).parts:
            raise QueueError(f"mutant {spec!r}: {rel} must be a path relative to the worktree's root", 2)
        path = root / rel
        if not path.is_file() or not _inside(root, path.resolve()):
            raise QueueError(f"mutant {spec!r}: {rel} is not a file in the worktree", 2)
        text = path.read_bytes()
        n = text.count(old.encode())
        if n != 1:
            raise QueueError(f"mutant {spec!r}: the old text is in {rel} {n} times; a mutant names one place", 2)
        digest = hashlib.sha256(b"\0".join((rel.encode(), old.encode(), new.encode()))).hexdigest()[:12]
        return {"kind": "text", "files": [rel], "old": old.encode(), "new": new.encode(), "digest": digest}
    patch = Path(spec) if Path(spec).is_absolute() else cwd / spec
    if not patch.is_file():
        raise QueueError(f"mutant {spec!r} is neither <file>:<old>=><new> nor a patch file", 2)
    patch = patch.resolve()
    r = git(root, "apply", "--check", str(patch))
    if r.returncode != 0:
        raise QueueError(f"mutant {spec!r}: the patch does not apply to the worktree: {r.stderr.strip()}", 2)
    r = git(root, "apply", "--numstat", "-z", str(patch))
    files = _numstat_paths(r.stdout)
    if not files:
        raise QueueError(f"mutant {spec!r}: the patch changes no file", 2)
    for rel in files:
        if not _inside(root, (root / rel).resolve()):
            raise QueueError(f"mutant {spec!r}: {rel} is outside the worktree", 2)
    return {"kind": "patch", "files": files, "patch": patch,
            "digest": hashlib.sha256(patch.read_bytes()).hexdigest()[:12]}


def _numstat_paths(out: str) -> list[str]:
    """The paths `git apply --numstat -z` names: `<a>\\t<d>\\t<path>\\0`, or for a rename
    `<a>\\t<d>\\t\\0<old>\\0<new>\\0`."""
    parts, files, i = out.split("\0"), [], 0
    while i < len(parts):
        head = parts[i]
        if not head:
            i += 1
            continue
        path = head.split("\t", 2)[2] if head.count("\t") >= 2 else ""
        if path:
            files.append(path)
            i += 1
        else:
            files.extend(p for p in parts[i + 1:i + 3] if p)
            i += 3
    return list(dict.fromkeys(files))


Snapshot = tuple[dict[str, "tuple[bytes, int] | None"], list[str]]


def _snapshot(root: Path, files: list[str]) -> Snapshot:
    """Each touched file's bytes and mode (None: absent), and the outermost directories a touched
    file's path needs that do not exist yet (a patch that adds a file there makes them)."""
    snap: dict[str, tuple[bytes, int] | None] = {}
    made: list[str] = []
    for rel in files:
        p = root / rel
        snap[rel] = (p.read_bytes(), p.stat().st_mode) if p.is_file() else None
        top = None
        for d in Path(rel).parents:
            if d == Path(".") or (root / d).exists() or (root / d).is_symlink():
                break
            top = d.as_posix()
        if top is not None and top not in made:
            made.append(top)
    return snap, made


def _restore(root: Path, snapshot: Snapshot) -> list[str]:
    """Write every touched file back as it was (remove one the mutant made, and every directory it
    made, whatever the test left in it); the paths not restored."""
    snap, made = snapshot
    left = []
    for rel, was in snap.items():
        p = root / rel
        try:
            if was is None:
                if p.exists() or p.is_symlink():
                    p.unlink()
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(was[0])
                os.chmod(p, was[1] & 0o7777)
        except OSError:
            pass
        now = (p.read_bytes() if p.is_file() else None) if not p.is_dir() else b""
        if now != (was[0] if was else None):
            left.append(rel)
    for rel in made:
        d = root / rel
        try:
            if d.is_symlink() or d.is_file():
                d.unlink()
            elif d.is_dir():
                shutil.rmtree(d)
        except OSError:
            pass
        if d.exists() or d.is_symlink():
            left.append(f"{rel}/")
    return left


def _apply(root: Path, m: dict[str, Any]) -> None:
    if m["kind"] == "text":
        p = root / m["files"][0]
        p.write_bytes(p.read_bytes().replace(m["old"], m["new"], 1))
        return
    r = git(root, "apply", str(m["patch"]))
    if r.returncode != 0:
        raise QueueError(f"the patch {m['patch']} did not apply: {r.stderr.strip()}", 1)


def _kill(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        pass


class _Stop:
    """A SIGTERM during the call. The handler only notes it and kills the running test's process
    group, so it never cuts a restore or a record write short; the call checks `hit` between steps
    and ends with exit 143."""

    def __init__(self) -> None:
        self.hit = False
        self.child: subprocess.Popen | None = None

    def handle(self, _sig: int, _frame: Any) -> None:
        self.hit = True
        if self.child is not None and self.child.returncode is None:
            _kill(self.child)

    def check(self, where: str) -> None:
        if self.hit:
            raise QueueError(f"terminated {where}", 128 + signal.SIGTERM)


@contextmanager
def _on_sigterm() -> Iterator[_Stop]:
    """Route a SIGTERM to a `_Stop` for the call (main thread only: elsewhere none is installed)."""
    stop = _Stop()
    if threading.current_thread() is not threading.main_thread():
        yield stop
        return
    old = signal.signal(signal.SIGTERM, stop.handle)
    try:
        yield stop
    finally:
        signal.signal(signal.SIGTERM, old)


def _test(line: str, cwd: Path, timeout: int, log: Path, label: str, stop: _Stop) -> dict[str, Any]:
    """Run the one-test command in its own process group, its output appended to `log`; a SIGTERM
    kills the group (`stop`)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    timed_out = False
    with log.open("ab") as f:
        f.write(f"\n--- {iso()} {label}\n".encode())
        f.flush()
        p = subprocess.Popen(["/bin/sh", "-c", line], cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=f,
                             stderr=subprocess.STDOUT, start_new_session=True)
        stop.child = p
        if stop.hit:
            _kill(p)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill(p)
            code = p.wait()
        except BaseException:
            _kill(p)
            p.wait()
            raise
        finally:
            stop.child = None
    return {"exit_code": code, "seconds": round(time.monotonic() - t0, 2), "timed_out": timed_out}


def _worktree(cfg: Config, q: Path, task_id: str) -> dict[str, Any]:
    from ccp import wt  # noqa: PLC0415

    root = cfg.root.resolve()
    for st in wt.records(q):
        try:
            if Path(str(st.get("path"))).resolve() != root:
                continue
        except (OSError, ValueError):
            continue
        if st.get("kind") != "mut":
            raise QueueError(f"{root} is the {st.get('kind')} worktree {st['name']}, not a mutation worktree: make "
                             f"one with `ccp wt create --kind mut --task {task_id} --sha <head>` and run there", 2)
        if st.get("task_id") != task_id:
            raise QueueError(f"mutation worktree {st['name']} is task {st.get('task_id')}'s, not {task_id}'s", 2)
        return st
    raise QueueError(f"{root} is not a recorded mutation worktree: make one with "
                     f"`ccp wt create --kind mut --task {task_id} --sha <head>` and run there", 2)


def log_path(q: Path, run_id: str) -> Path:
    p = runs.path(q, run_id)
    return p.with_name(f"{p.stem}-mutate.log")


def run(cfg: Config, q: Path, run_id: str, test: str, mutants: list[str], cwd: Path | None = None) -> tuple[dict[str, Any], int]:
    with _on_sigterm() as stop:
        return _run(cfg, q, run_id, test, mutants, cwd, stop)


def _run(cfg: Config, q: Path, run_id: str, test: str, mutants: list[str], cwd: Path | None,
         stop: _Stop) -> tuple[dict[str, Any], int]:
    mu = cfg.mutate or {}
    if not mu.get("command"):
        raise QueueError("plane.json names no mutate.command: the product has no command that runs one test (§20.6)", 2)
    if not test.strip():
        raise QueueError("--test names the test a mutant is judged by", 2)
    if not mutants:
        raise QueueError("give at least one --mutant <file>:<old>=><new> or a patch file", 2)
    runs.parse_id(run_id)
    rec = runs.load(q, run_id)
    if runs.state(rec) not in runs.OPEN:
        raise QueueError(f"run {run_id} is {runs.state(rec)}: mutants are recorded only on an open run", 2)
    task_id = rec["task_id"]
    st = _worktree(cfg, q, task_id)
    root = cfg.root.resolve()
    parsed = [parse(root, m, cwd or Path.cwd()) for m in mutants]
    line = fill(mu["command"], {"test": shlex.quote(test)})
    timeout = int(mu["timeout_seconds"])
    log = log_path(q, run_id)
    out: dict[str, Any] = {"ok": True, "run_id": run_id, "worktree": st["name"], "test": test, "log": str(log)}
    stop.check("before the unmutated run; nothing was run, applied or recorded")
    base = _test(line, root, timeout, log, f"{test} unmutated", stop)
    out["baseline"] = base
    stop.check("in the unmutated run; nothing was applied or recorded")
    if base["exit_code"] != 0:
        raise QueueError(f"the test {test} fails with no mutant (exit {base['exit_code']}), so it cannot tell a "
                         f"mutant; nothing was applied or recorded. Its output: {log}", 1)
    rows: list[dict[str, Any]] = []
    for n, m in enumerate(parsed, 1):
        stop.check(f"before mutant {n} of {len(parsed)}; {len(rows)} mutant(s) recorded")
        snap = _snapshot(root, m["files"])
        res: dict[str, Any] | None = None
        try:
            _apply(root, m)
            if not stop.hit:
                res = _test(line, root, timeout, log, f"{test} mutant {n} ({m['digest']})", stop)
        except QueueError:
            if not stop.hit:
                raise
        finally:
            left = _restore(root, snap)
        stop.check(f"at mutant {n} of {len(parsed)}; "
                   + (f"{', '.join(left)} could not be restored" if left else "its files are restored")
                   + f"; {len(rows)} mutant(s) recorded")
        if left:
            raise QueueError(f"mutant {n}: {', '.join(left)} could not be restored in {root}", 1)
        assert res is not None
        row = {"at": iso(), "test": test, "mutant": n, "kind": m["kind"], "files": m["files"],
               "digest": m["digest"], "outcome": "survived" if res["exit_code"] == 0 else "killed", **res}
        rec = runs.load(q, run_id)
        rec.setdefault("mutation", []).append({**row, "worktree": st["name"]})
        runs.save(q, rec)
        rows.append(row)
    stop.check(f"after the last mutant; {len(rows)} mutant(s) recorded")
    killed = sum(r["outcome"] == "killed" for r in rows)
    out.update(mutants=rows, killed=killed, survived=len(rows) - killed)
    emit(q, cfg, task_id, "run", "recorded", {"run_id": run_id, "mutants": len(rows), "killed": killed,
                                              "survived": len(rows) - killed})
    stop.check(f"after the last mutant; {len(rows)} mutant(s) and the run/recorded event recorded")
    return out, 0 if killed == len(rows) else 1


__all__ = ["log_path", "parse", "run"]
