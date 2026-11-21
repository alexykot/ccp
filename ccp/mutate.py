"""`ccp mutate` (SPEC §20.6): does the named test check what it claims? It applies one mutant at a
time in the seat's worktree, runs the product's one-test command, and records the mutant killed only
when that test fails, and `unbuilt` when the run says the code did not build or import.

`--test` is one test id, passed whole as `{test}`, so it may name a single test method. A mutant is
`<file>:<old>=><new>` (the text `old`, found exactly once in the file, relative to the worktree's
root, becomes `new`) or the path of a patch `git apply` takes. A `--mutant-file` holds the same
substitution without shell quoting, for a mutant that spans lines: the file's path on its first line,
then a line `=== old`, the old text, a line `=== new` and the new text, each text exactly what lies
between its marker line and the next (or the file's end); a part missing refuses the call. A `--revert` mutant puts back the
merge base's version (HEAD's merge base with the integration branch) of a file, or of every change
from it that a range of the worktree file's lines overlaps or borders, the changes being the hunks
`git diff -U0` shows between the two; in a shallow worktree (§12.1) the merge base is the one its
record holds, and with none the call is refused. The `--mutant`s come first, then the `--mutant-file`s,
then the `--revert`s, each in the order given.

`--together` makes them one mutant: its parts are applied in order under one snapshot of all their files, and a
part that does not apply restores the tree and refuses the call. Parts on different files are each checked against
the unmutated tree. Its files are the union of its parts' files in order of first touch, and its digest is a digest of
the parts' digests.

Every mutant is checked before anything runs. Then the named test runs once unmutated: a test that
fails already proves nothing, so the command stops there. Each mutant (a `--together` one whole) is
applied alone, the test runs (plane.json `mutate.command` with `{test}` filled in shell-quoted, in the
worktree's root, in its own process group, killed after `mutate.timeout_seconds`, which counts as the
test failing), and every file the mutant touched is written back byte for byte (a file or directory it made is
removed), and checked, before the next. A mutated Python file loses its compiled `__pycache__` entries
before its test runs, so bytecode compiled from another source (an unchecked hash-based `.pyc`, or one
whose recorded mtime and size happen to match) never runs in its place; a restored one loses them
again, and every test run has `PYTHONDONTWRITEBYTECODE=1`: a same-size mutant restored within the
second leaves no bytecode that a later run would take for the source. A mutant whose run exits 0
survived; one whose run exits non-zero with an output line plane.json `mutate.unbuilt_re` matches is
`unbuilt` (the code did not build or import, which proves nothing about the test); any other is killed.
A SIGTERM at any point of the call kills the running test, restores the files and exits 143.

It runs only from a recorded `impl`, `mut`, `rev` or `ver` worktree of the run's task, and only for a run that is
still open. Each mutant adds a row to the run record's `mutation` list, never the mutant's text or the test's output,
which goes to a log next to the run's record; the call ends with one `run`/`recorded` event. Exit 0 when every mutant
was killed, 1 when one survived or was unbuilt or the unmutated test failed, 2 for a usage or configuration problem.
"""
from __future__ import annotations

import hashlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager
from glob import escape as glob_escape
from pathlib import Path
from typing import Any, Iterator

from ccp import doclang, runs
from ccp.config import Config, fill
from ccp.queue import QueueError, emit, git, iso

SEP = "=>"
OUTPUT_AT = "_output_at"  # `_test`'s offset in the log where the run's own output starts; never recorded
OLD_MARK, NEW_MARK = b"=== old", b"=== new"  # a --mutant-file's part separators, each a line of its own
WORKTREE_KINDS = ("impl", "mut", "rev", "ver")  # the seats' worktrees a call may run in (§20.6)
RANGE_RE = re.compile(r"([1-9][0-9]*)(?:-([1-9][0-9]*))?")
HUNK_RE = re.compile(rb"^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@", re.M)  # a `git diff` hunk header


def _inside(root: Path, p: Path) -> bool:
    return p == root or root in p.parents


def parse(root: Path, spec: str, cwd: Path, count: bool = True) -> dict[str, Any]:
    """One `--mutant`: a substitution when it holds `=>`, else a patch file. Checked against the
    unmutated tree; nothing is written. Without `count`, a substitution's old text is left for `together`
    to find."""
    if SEP in spec:
        target, _, new = spec.partition(SEP)
        rel, colon, old = target.partition(":")
        if not colon or not rel or not old:
            raise QueueError(f"mutant {spec!r}: a substitution is <file>:<old>=><new>, with a file and the old text", 2)
        return _substitution(root, f"mutant {spec!r}", rel, old.encode(), new.encode(), count)
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


def _substitution(root: Path, label: str, rel: str, old: bytes, new: bytes, count: bool = True) -> dict[str, Any]:
    """A text mutant: `old`, found exactly once in the worktree file `rel`, becomes `new`. Checked against
    the unmutated tree (the count only with `count`); nothing is written."""
    if Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise QueueError(f"{label}: {rel} must be a path relative to the worktree's root", 2)
    path = root / rel
    if not path.is_file() or not _inside(root, path.resolve()):
        raise QueueError(f"{label}: {rel} is not a file in the worktree", 2)
    if count:
        _once(label, rel, path.read_bytes(), old, False)
    digest = hashlib.sha256(b"\0".join((rel.encode(), old, new))).hexdigest()[:12]
    return {"kind": "text", "files": [rel], "old": old, "new": new, "digest": digest, "label": label}


def _once(label: str, rel: str, text: bytes, old: bytes, after: bool) -> None:
    """Refuse (exit 2) unless `old` is in `text` exactly once; `after`: `text` is what earlier parts left."""
    n = text.count(old)
    if n != 1:
        where = f"{rel} as the earlier parts on it leave it" if after else rel
        raise QueueError(f"{label}: the old text is in {where} {n} times; a mutant names one place", 2)


def parse_file(root: Path, spec: str, cwd: Path, count: bool = True) -> dict[str, Any]:
    """One `--mutant-file`: the target file's path on the first line, then a line `=== old`, the old text,
    a line `=== new` and the new text (§20.6). Each text is exactly the bytes between its marker line and
    the next marker line or the file's end, so a mutant spanning lines needs no shell quoting. A part
    missing (the path, either marker, or the old text) refuses the call (exit 2). Checked against the
    unmutated tree (the old text's count only with `count`); nothing is written."""
    label = f"mutant file {spec!r}"
    f = Path(spec) if Path(spec).is_absolute() else cwd / spec
    if not f.is_file():
        raise QueueError(f"{label} is not a file", 2)
    lines = f.read_bytes().splitlines(keepends=True)
    rel = lines[0].rstrip(b"\r\n").decode(errors="replace").strip() if lines else ""
    if not rel or rel.encode() in (OLD_MARK, NEW_MARK):
        raise QueueError(f"{label}: its first line names no file; it holds the file's path, then `=== old`, the old "
                         "text, `=== new` and the new text", 2)
    marks = [ln.rstrip(b"\r\n") for ln in lines]
    if OLD_MARK not in marks[1:]:
        raise QueueError(f"{label}: no line `=== old` before the old text", 2)
    i = marks.index(OLD_MARK, 1)
    if NEW_MARK not in marks[i + 1:]:
        raise QueueError(f"{label}: no line `=== new` after the old text", 2)
    j = marks.index(NEW_MARK, i + 1)
    if NEW_MARK in marks[1:i]:
        raise QueueError(f"{label}: `=== new` comes before `=== old`", 2)
    old, new = b"".join(lines[i + 1:j]), b"".join(lines[j + 1:])
    if not old:
        raise QueueError(f"{label}: the old text between `=== old` and `=== new` is empty", 2)
    return _substitution(root, label, rel, old, new, count)


def _key(rel: str) -> str:
    """One spelling per file for `--together`'s checks: `./calc.py` and `calc.py` are one file."""
    return Path(os.path.normpath(rel)).as_posix()


def together(parts: list[dict[str, Any]], texts: dict[str, bytes]) -> dict[str, Any]:
    """`--together`: the parsed parts (at least two, in order) as one mutant. `texts` holds the unmutated
    bytes of every file a substitution names, keyed by `_key`. Files are told apart by `_key`, so two
    spellings of one file are one file. Substitutions on one file are checked in order, each old text
    exactly once in what the earlier ones leave (a lone one: in the unmutated file); a file any other part
    shares with another refuses the call (exit 2). Nothing is written."""
    if len(parts) < 2:
        raise QueueError(f"--together makes the mutants given one; it needs at least two, and {len(parts)} was "
                         "given", 2)
    on: dict[str, list[int]] = {}
    for i, p in enumerate(parts):
        for rel in p["files"]:
            on.setdefault(_key(rel), []).append(i)
    for rel, idx in on.items():
        kinds = [parts[i]["kind"] for i in idx]
        if len(idx) > 1 and any(k != "text" for k in kinds):
            raise QueueError(f"--together: {rel} is touched by parts {', '.join(str(i + 1) for i in idx)} "
                             f"({', '.join(kinds)}); only substitutions may share a file", 2)
        if kinds[0] != "text":
            continue
        text = texts[rel]
        for k, i in enumerate(idx):
            _once(parts[i]["label"], rel, text, parts[i]["old"], k > 0)
            text = text.replace(parts[i]["old"], parts[i]["new"], 1)
    digest = hashlib.sha256("\0".join(p["digest"] for p in parts).encode()).hexdigest()[:12]
    return {"kind": "together", "parts": [p["kind"] for p in parts], "files": list(on), "digest": digest,
            "members": parts}


def _relpath(root: Path, spec: str, rel: str) -> Path:
    if not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
        raise QueueError(f"revert {spec!r}: {rel!r} must be a path relative to the worktree's root", 2)
    path = root / rel
    if not _inside(root, path.resolve()):
        raise QueueError(f"revert {spec!r}: {rel} is outside the worktree", 2)
    return path


def _base_blob(root: Path, base: str, rel: str, spec: str) -> bytes | None:
    """The file's bytes at the merge base; None when it is not there."""
    kind = git(root, "cat-file", "-t", f"{base}:{rel}")
    if kind.returncode != 0:
        return None
    if kind.stdout.strip() != "blob":
        raise QueueError(f"revert {spec!r}: {rel} is a {kind.stdout.strip()} at the merge base, not a file", 2)
    r = subprocess.run(["git", "-C", str(root), "cat-file", "blob", f"{base}:{rel}"], capture_output=True)
    if r.returncode != 0:
        raise QueueError(f"revert {spec!r}: cannot read {rel} at the merge base", 2)
    return r.stdout


def _lines(text: bytes) -> list[bytes]:
    """The lines git counts: split after each newline only, each keeping its own."""
    parts = text.split(b"\n")
    out = [p + b"\n" for p in parts[:-1]]
    return out + [parts[-1]] if parts[-1] else out


def _hunks(was: bytes, now: bytes, cwd: Path | None = None) -> list[tuple[int, int, int, int]]:
    """The hunks `git diff -U0` shows from `was` to `now`, as 0-based half-open line spans
    `(i1, i2, j1, j2)`: `was[i1:i2]` became `now[j1:j2]`. An empty span sits after that many lines
    of its side, as git's `-s,0` header says. Run in `cwd` (the worktree), so the product's own diff
    settings place them as its `git diff` does."""
    with tempfile.TemporaryDirectory(prefix="ccp-mutate-") as d:
        a, b = Path(d) / "base", Path(d) / "worktree"
        a.write_bytes(was)
        b.write_bytes(now)
        r = subprocess.run(["git", "diff", "--no-index", "--no-ext-diff", "--no-textconv", "--no-color", "--text",
                            "-U0", str(a), str(b)], cwd=str(cwd) if cwd else d, capture_output=True)
    if r.returncode not in (0, 1):
        raise QueueError("git diff could not compare the file with the merge base: "
                         + r.stderr.decode(errors="replace").strip(), 2)
    out = []
    for m in HUNK_RE.finditer(r.stdout):
        s1, n1, s2, n2 = int(m[1]), int(m[2] or b"1"), int(m[3]), int(m[4] or b"1")
        i1, j1 = (s1 - 1 if n1 else s1), (s2 - 1 if n2 else s2)
        out.append((i1, i1 + n1, j1, j1 + n2))
    return out


def _revert_lines(now: bytes, was: bytes, first: int, last: int, cwd: Path | None = None) -> bytes:
    """`now` with every change from `was` put back whose lines in `now` overlap lines first..last
    (1-based, inclusive), a deletion inside the range or next to it included. The changes are the
    hunks `git diff -U0` shows (`_hunks`)."""
    a, b = _lines(was), _lines(now)
    out: list[bytes] = []
    at = 0
    for i1, i2, j1, j2 in _hunks(was, now, cwd):
        hit = first - 1 <= j1 <= last if j1 == j2 else j1 < last and j2 > first - 1
        out.extend(b[at:j1])
        out.extend(a[i1:i2] if hit else b[j1:j2])
        at = j2
    out.extend(b[at:])
    return b"".join(out)


def parse_revert(root: Path, spec: str, base: str) -> dict[str, Any]:
    """One `--revert PATH[:N[-M]]`: the merge base's version of the file, or of the changes the line
    range touches, as a mutant. Checked against the unmutated tree; nothing is written."""
    rel, colon, rng = spec.rpartition(":")
    m = RANGE_RE.fullmatch(rng) if colon else None
    if m is None:
        rel, rng = spec, ""
    path = _relpath(root, spec, rel)
    if path.is_dir():
        raise QueueError(f"revert {spec!r}: {rel} is a directory; a revert names a file", 2)
    now = path.read_bytes() if path.is_file() else None
    was = _base_blob(root, base, rel, spec)
    if m is None:
        if now is None and was is None:
            raise QueueError(f"revert {spec!r}: {rel} is neither in the worktree nor at the merge base", 2)
        content = was
    else:
        first, last = int(m.group(1)), int(m.group(2) or m.group(1))
        if now is None:
            raise QueueError(f"revert {spec!r}: {rel} is not a file in the worktree; a line range needs one", 2)
        n = len(_lines(now))
        if last < first or last > n:
            raise QueueError(f"revert {spec!r}: lines {first}-{last} are not a range of {rel}'s {n} lines", 2)
        content = _revert_lines(now, was or b"", first, last, root)
    if content == now:
        what = f"lines {rng} of {rel} touch no change" if rng else f"{rel} does not differ"
        raise QueueError(f"revert {spec!r}: {what} from the merge base; the revert changes nothing", 2)
    digest = hashlib.sha256(b"\0".join((b"revert", rel.encode(), rng.encode(),
                                         b"-" if content is None else content))).hexdigest()[:12]
    return {"kind": "revert", "files": [rel], "content": content, "digest": digest}


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


def _drop_bytecode(root: Path, rel: str) -> None:
    """A Python file's compiled entries in its `__pycache__` (`<stem>.<tag>[.opt-N].pyc`), dropped after a
    mutant is applied and again after it is restored. Python trusts one whose recorded source mtime (in whole
    seconds) and size still match, and an unchecked hash-based one whatever the source, so either would
    otherwise run in place of the source: the original's before the mutant, the mutant's after it."""
    if not rel.endswith(".py"):
        return
    p = root / rel
    cache = p.parent / "__pycache__"
    if not cache.is_dir():
        return
    for f in cache.glob(f"{glob_escape(p.stem)}.*.pyc"):
        try:
            f.unlink()
        except OSError:
            pass


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
        _drop_bytecode(root, rel)
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
    if m["kind"] == "together":
        for k, part in enumerate(m["members"], 1):
            try:
                _apply(root, part)
            except QueueError as e:
                raise QueueError(f"part {k} of the --together mutant did not apply: {e}", 2) from e
        return
    if m["kind"] == "revert":
        p = root / m["files"][0]
        if m["content"] is None:
            p.unlink()
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(m["content"])
        return
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
        start = f.tell()
        p = subprocess.Popen(["/bin/sh", "-c", line], cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=f,
                             stderr=subprocess.STDOUT, start_new_session=True,
                             env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})  # no bytecode outlives a mutant
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
    return {"exit_code": code, "seconds": round(time.monotonic() - t0, 2), "timed_out": timed_out, OUTPUT_AT: start}


def _unbuilt_patterns(mu: dict[str, Any]) -> list[re.Pattern[str]]:
    """plane.json `mutate.unbuilt_re`, compiled: a pattern, a list of them, or none (null)."""
    pats = mu.get("unbuilt_re")
    return [re.compile(x) for x in ([pats] if isinstance(pats, str) else pats or [])]


def _says_unbuilt(log: Path, start: int, pats: list[re.Pattern[str]]) -> bool:
    """Whether a line of one run's output (the log from `start`) matches an `unbuilt_re` pattern."""
    if not pats:
        return False
    with log.open("rb") as f:
        f.seek(start)
        text = f.read().decode(errors="replace")
    return any(p.search(ln) for ln in text.splitlines() for p in pats)


def _worktree(cfg: Config, q: Path, task_id: str) -> dict[str, Any]:
    from ccp import wt  # noqa: PLC0415

    root = cfg.root.resolve()
    for st in wt.records(q):
        try:
            if Path(str(st.get("path"))).resolve() != root:
                continue
        except (OSError, ValueError):
            continue
        if st.get("kind") not in WORKTREE_KINDS:
            raise QueueError(f"{root} is the {st.get('kind')} worktree {st['name']}, not an impl, mut, rev or ver "
                             f"one: run from your own worktree, or make a mutation copy with "
                             f"`ccp wt create --kind mut --task {task_id} --sha <head>` and run there", 2)
        if st.get("task_id") != task_id:
            raise QueueError(f"worktree {st['name']} is task {st.get('task_id')}'s, not {task_id}'s", 2)
        return st
    raise QueueError(f"{root} is not a recorded impl, mut, rev or ver worktree: run from your own worktree, or "
                     f"make a mutation copy with `ccp wt create --kind mut --task {task_id} --sha <head>` and run "
                     f"there", 2)


def log_path(q: Path, run_id: str) -> Path:
    p = runs.path(q, run_id)
    return p.with_name(f"{p.stem}-mutate.log")


def run(cfg: Config, q: Path, run_id: str, test: str, mutants: list[str], cwd: Path | None = None,
        reverts: list[str] | None = None, mutant_files: list[str] | None = None,
        together: bool = False) -> tuple[dict[str, Any], int]:
    with _on_sigterm() as stop:
        return _run(cfg, q, run_id, test, mutants, reverts or [], cwd, stop, mutant_files or [], together)


def _run(cfg: Config, q: Path, run_id: str, test: str, mutants: list[str], reverts: list[str],
         cwd: Path | None, stop: _Stop, mutant_files: list[str] | None = None,
         as_one: bool = False) -> tuple[dict[str, Any], int]:
    mutant_files = mutant_files or []
    mu = cfg.mutate or {}
    if not mu.get("command"):
        runner = doclang.for_tests(cfg).test_command
        shape = f"a per-test runner (`{runner} {{test}}`)" if runner else "a command that runs one test"
        raise QueueError("plane.json names no mutate.command: the product has no command that runs one test "
                         f"(§20.6). Set mutate.command to a shell template that runs the test named by {{test}}: {shape}, "
                         "or, where each test is a whole script, `sh {test}` with --test the script's path", 2)
    if not test.strip():
        raise QueueError("--test names the test a mutant is judged by", 2)
    if not mutants and not reverts and not mutant_files:
        raise QueueError("give at least one --mutant <file>:<old>=><new> or patch file, --mutant-file <path>, "
                         "or --revert <path>[:<lines>]", 2)
    runs.parse_id(run_id)
    rec = runs.load(q, run_id)
    if runs.state(rec) not in runs.OPEN:
        raise QueueError(f"run {run_id} is {runs.state(rec)}: mutants are recorded only on an open run", 2)
    task_id = rec["task_id"]
    st = _worktree(cfg, q, task_id)
    root = cfg.root.resolve()
    parsed = [parse(root, m, cwd or Path.cwd(), not as_one) for m in mutants]
    parsed += [parse_file(root, m, cwd or Path.cwd(), not as_one) for m in mutant_files]
    base = None
    if reverts:
        from ccp import wt  # noqa: PLC0415

        if st.get("shallow"):  # §12.1: a depth-1 clone has no history; `wt create` recorded its merge base
            base = st.get("merge_base")
            if not base:
                raise QueueError(f"the shallow worktree {st['name']} has no merge base recorded, so --revert has "
                                 "nothing to put back: run it in a full worktree (`ccp wt create` without --shallow)", 2)
        else:
            head = git(root, "rev-parse", "HEAD").stdout.strip()
            base = wt.merge_base(cfg, q, head)
        parsed += [parse_revert(root, r, base) for r in reverts]
    if as_one:
        texts = {_key(p["files"][0]): (root / p["files"][0]).read_bytes() for p in parsed if p["kind"] == "text"}
        parsed = [together(parsed, texts)]
    line = fill(mu["command"], {"test": shlex.quote(test)})
    timeout = int(mu["timeout_seconds"])
    unbuilt = _unbuilt_patterns(mu)
    log = log_path(q, run_id)
    out: dict[str, Any] = {"ok": True, "run_id": run_id, "worktree": st["name"], "test": test, "log": str(log)}
    if base:
        out["merge_base"] = base
    stop.check("before the unmutated run; nothing was run, applied or recorded")
    unmutated = _test(line, root, timeout, log, f"{test} unmutated", stop)
    unmutated.pop(OUTPUT_AT)
    out["baseline"] = unmutated
    stop.check("in the unmutated run; nothing was applied or recorded")
    if unmutated["exit_code"] != 0:
        raise QueueError(f"the test {test} fails with no mutant (exit {unmutated['exit_code']}), so it cannot tell a "
                         f"mutant; nothing was applied or recorded. Its output: {log}", 1)
    rows: list[dict[str, Any]] = []
    for n, m in enumerate(parsed, 1):
        stop.check(f"before mutant {n} of {len(parsed)}; {len(rows)} mutant(s) recorded")
        snap = _snapshot(root, m["files"])
        res: dict[str, Any] | None = None
        try:
            _apply(root, m)
            for rel in m["files"]:  # a stale compiled entry would run in place of the mutated source
                _drop_bytecode(root, rel)
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
        at = res.pop(OUTPUT_AT)
        outcome = "survived" if res["exit_code"] == 0 else "unbuilt" if _says_unbuilt(log, at, unbuilt) else "killed"
        parts = {"parts": m["parts"]} if "parts" in m else {}  # a --together mutant's parts' kinds
        row = {"at": iso(), "test": test, "mutant": n, "kind": m["kind"], **parts, "files": m["files"],
               "digest": m["digest"], "outcome": outcome, **res}
        rec = runs.load(q, run_id)
        rec.setdefault("mutation", []).append({**row, "worktree": st["name"]})
        runs.save(q, rec)
        rows.append(row)
    stop.check(f"after the last mutant; {len(rows)} mutant(s) recorded")
    counts = {k: sum(r["outcome"] == k for r in rows) for k in ("killed", "unbuilt", "survived")}
    killed = counts["killed"]
    out.update(mutants=rows, **counts)
    emit(q, cfg, task_id, "run", "recorded", {"run_id": run_id, "mutants": len(rows), **counts})
    stop.check(f"after the last mutant; {len(rows)} mutant(s) and the run/recorded event recorded")
    return out, 0 if killed == len(rows) else 1


__all__ = ["log_path", "parse", "parse_file", "parse_revert", "run", "together"]
