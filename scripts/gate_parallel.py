#!/usr/bin/env python3
"""gate_parallel.py — the plane's test modules, each in its own process, for scripts/gate.sh.

Runs every `tests/test_*.py` module as `python3 -m unittest tests.<module>` from the repo root,
GATE_WORKERS at a time (default: the CPU count), the largest files first so the slowest modules do
not start last. Given module names (`tests.test_x`) as arguments, it runs only those, the same way
(the part lane, SPEC §14.7); a name that is no `tests/test_*.py` module exits 2 naming it, running
nothing. The modules in SERIAL run afterwards, one at a time, with nothing else running.
Each module's output is printed whole when it ends, then one line:

  gate module tests.test_x: ok, 12.34 s, 45 tests
  gate module tests.test_x: FAILED (exit 1), 12.34 s, 45 tests
  gate module tests.test_x: cached, 12.34 s, 45 tests

which scripts/gate_result.py reads for the result file's `modules`, `ran` and `cached`.

The test cache (SPEC §15.3, plane.json `verify.accept_cache`). Before a module runs, its key is looked
up: the SHA-256 of the module file's content, its name, the interpreter's version and the inputs every
module shares. The shared inputs are `git ls-files -s` of every tracked path, with uncommitted edits
(tracked files changed in the working tree, and untracked files git does not ignore) folded in by
their content, except the test modules: a test module imports no other (E4), so each is an input of
its own key alone. An untracked directory git lists whole (a nested repository) is folded in file by file, its
own `.git` left out. A key whose recorded result passed, no older than plane.json
`verify.accept_cache.max_age_days` (no limit when unset), is a hit: the module is reported `cached`,
with the seconds and tests of the run that recorded it, and is not run. A miss runs; once every
module has ended and no `state/*` branch is left (the check gate.sh fails on), each that passed
records `{key, passed, tests, seconds, at}`: a module that leaked a branch, or ran beside one that
did, is never served from the cache. The keys are computed over the whole suite whatever modules
run, so a module's entry is the same in a run of some modules and in a run of all. Computing the key
writes nothing to the repository: not its index, objects or stash list.

The cache directory is GATE_CACHE_DIR, default `~/.cache/ccp-gate/<repo id>` (the repo id from its
root commit, so every worktree and clone of the repo shares it); it must be outside the repository.
The cold option, GATE_COLD=1 (any value but empty or 0), reads and writes no cache: every module
runs and the run counts nothing cached. A checkout git cannot read, or an untracked file that cannot
be read, runs with no cache, saying so (the file named).

Exits 1 when any module failed or errored (a non-zero exit), 2 on a bad GATE_WORKERS, an unknown
module name or a cache directory inside the repository; failing on a leftover `state/*` branch is gate.sh's, after it.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Modules (dotted, `tests.test_x`) that share state with another (a fixed path, a port, the real HOME)
# and must run alone.
SERIAL: list[str] = []
RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
KEY_VERSION = "ccp-gate-cache 1"
_print = threading.Lock()


def workers() -> int:
    raw = os.environ.get("GATE_WORKERS", "").strip()
    if not raw:
        return os.cpu_count() or 1
    if not raw.isdigit() or int(raw) < 1:
        raise ValueError(f"GATE_WORKERS must be an integer >= 1, not {raw!r}")
    return int(raw)


def modules() -> list[str]:
    files = sorted((ROOT / "tests").glob("test_*.py"), key=lambda p: (-p.stat().st_size, p.name))
    return [f"tests.{p.stem}" for p in files]


def selected(suite: list[str], wanted: list[str]) -> list[str]:
    """The suite's modules to run, in its order: all of them when `wanted` is empty, else those it names.
    ValueError naming each name that is no module of the suite."""
    unknown = [w for w in dict.fromkeys(wanted) if w not in suite]
    if unknown:
        raise ValueError(f"no tests/test_*.py module named {', '.join(unknown)}")
    return [m for m in suite if m in wanted] if wanted else list(suite)


def cold() -> bool:
    return os.environ.get("GATE_COLD", "").strip() not in ("", "0")


def _git(*args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(ROOT), *args], stdin=subprocess.DEVNULL, capture_output=True)
    if p.returncode != 0:
        raise OSError(f"git {args[0]} exited {p.returncode}")
    return p.stdout


def cache_dir() -> Path:
    """GATE_CACHE_DIR, else ~/.cache/ccp-gate/<repo id>; ValueError when it lies inside the repository."""
    raw = os.environ.get("GATE_CACHE_DIR", "").strip()
    if raw:
        d = Path(raw).expanduser().resolve()
    else:
        roots = sorted(_git("rev-list", "--max-parents=0", "HEAD").decode().split())
        rid = hashlib.sha256(" ".join(roots).encode()).hexdigest()[:16] if roots else "no-commit"
        d = (Path.home() / ".cache" / "ccp-gate" / rid).resolve()
    if d == ROOT or ROOT in d.parents:
        raise ValueError(f"GATE_CACHE_DIR must be outside the repository, not {d}")
    return d


def _blob(path: Path) -> tuple[str, str] | None:
    """A working-tree file as git would stage it, unfiltered: its mode and blob id; None when it is gone.
    An unchanged file gives its index entry's own values, so the key does not hang on stat data. A file
    that cannot be read raises OSError, which names it."""
    try:
        if path.is_symlink():
            mode, data = "120000", os.readlink(path).encode(errors="surrogateescape")
        else:
            mode, data = ("100755" if path.stat().st_mode & 0o111 else "100644"), path.read_bytes()
    except FileNotFoundError:
        return None
    return mode, hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _files_under(rel: str) -> list[str]:
    """An untracked directory git lists whole (a nested repository, `rel` ending in `/`): every file
    under it, relative to the repository, its `.git` left out; a symbolic link is a file, never followed."""
    out = []
    for d, dirs, files in os.walk(ROOT / rel):
        links = [x for x in dirs if os.path.islink(os.path.join(d, x))]
        dirs[:] = [x for x in dirs if x != ".git" and x not in links]
        out += [os.path.relpath(os.path.join(d, f), ROOT) for f in files + links if f != ".git"]
    return out


def shared_inputs(leaves: set[str]) -> str:
    """The digest of what every module may read: the index's entry for every tracked path, with the
    working tree's edits to tracked paths and its untracked, unignored files folded in by content.
    Paths in `leaves` (every test module of the suite) are left out. Read-only: nothing is written to git,
    its index or its objects."""
    entries: dict[str, list[str]] = {}
    for raw in _git("ls-files", "-s", "-z").split(b"\0"):
        if raw:
            meta, rel = raw.decode(errors="surrogateescape").split("\t", 1)
            entries.setdefault(rel, []).append(meta)
    def fold(flag: str, *extra: str) -> None:
        for raw in set(_git("ls-files", flag, *extra, "-z").split(b"\0")) - {b""}:
            listed = raw.decode(errors="surrogateescape")
            for rel in _files_under(listed) if flag == "-o" and listed.endswith("/") else [listed]:
                blob = _blob(ROOT / rel)
                entries[rel] = [f"{blob[0]} {blob[1]} {'u' if flag == '-o' else 0}"] if blob else ["deleted"]
    fold("-m")
    fold("-o", "--exclude-standard")
    h = hashlib.sha256()
    for rel in sorted(entries):
        if rel not in leaves:
            for meta in entries[rel]:
                h.update(f"{meta}\t{rel}\0".encode(errors="surrogateescape"))
    return h.hexdigest()


def module_key(name: str, shared: str) -> str:
    own = hashlib.sha256((ROOT / "tests" / f"{name.split('.', 1)[1]}.py").read_bytes()).hexdigest()
    return hashlib.sha256(f"{KEY_VERSION}\n{sys.version}\n{name}\n{own}\n{shared}".encode()).hexdigest()


def max_age_days() -> int | None:
    """plane.json `verify.accept_cache.max_age_days`, as ccp loads it: an entry older than it is no hit
    (None: no limit, also when the configuration does not load). The load's warnings are not printed."""
    sys.path.insert(0, str(ROOT))
    try:
        from ccp import config  # noqa: PLC0415
        with contextlib.redirect_stderr(io.StringIO()):
            cfg = config.load(ROOT)
        age = ((cfg.verify or {}).get("accept_cache") or {}).get("max_age_days")
    except Exception:  # noqa: BLE001  (no plane.json, invalid JSON, a ConfigError: no limit, as before)
        return None
    return age if isinstance(age, int) and not isinstance(age, bool) and age >= 1 else None


class Cache:
    def __init__(self, directory: Path, max_age: int | None):
        self.dir, self.max_age = directory, max_age

    def lookup(self, key: str) -> dict | None:
        try:
            e = json.loads((self.dir / f"{key}.json").read_text())
            at = datetime.strptime(e["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if not (isinstance(e, dict) and e.get("key") == key and e.get("passed") is True
                and isinstance(e.get("tests"), int) and isinstance(e.get("seconds"), (int, float))):
            return None
        if self.max_age is not None and datetime.now(timezone.utc) - at > timedelta(days=self.max_age):
            return None
        return e

    def record(self, key: str, tests: int, seconds: float) -> None:
        entry = {"key": key, "passed": True, "tests": tests, "seconds": round(seconds, 2),
                 "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".entry-")
            with os.fdopen(fd, "w") as f:
                json.dump(entry, f)
            os.replace(tmp, self.dir / f"{key}.json")
        except OSError as e:
            with _print:
                print(f"gate: could not record a cache entry ({e.__class__.__name__}); the module still passed",
                      file=sys.stderr)


def module_tests(output: str) -> int:
    """A module's tests: the sum of every `Ran N tests` line in its output, as gate_result.py sums the
    whole log's, so the modules' counts add up to the total."""
    return sum(int(n) for n in RAN_RE.findall(output))


def branches_left() -> bool:
    """Whether a `state/*` branch is left (gate.sh's check, E2), or git cannot say: either way no pass
    is recorded."""
    try:
        return bool(_git("branch", "--list", "state/*").strip())
    except OSError:
        return True


def run_one(name: str) -> tuple[str, int, float, int]:
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "unittest", name], cwd=ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    secs = time.monotonic() - t0
    tests = module_tests(p.stdout)
    state = "ok" if p.returncode == 0 else f"FAILED (exit {p.returncode})"
    with _print:
        sys.stdout.write(p.stdout if p.stdout.endswith("\n") or not p.stdout else p.stdout + "\n")
        sys.stdout.write(f"gate module {name}: {state}, {secs:.2f} s, {tests} tests\n")
        sys.stdout.flush()
    return name, p.returncode, secs, tests


def main(argv: list[str]) -> int:
    try:
        n = workers()
        suite = modules()
        run = selected(suite, argv)
    except ValueError as e:
        print(f"gate: {e}", file=sys.stderr)
        return 2
    t0 = time.monotonic()
    cache: Cache | None = None
    keys: dict[str, str] = {}
    if cold():
        print("gate: cold (GATE_COLD): no test cache read or written")
    else:
        try:
            cache = Cache(cache_dir(), max_age_days())
            leaves = {f"tests/{m.split('.', 1)[1]}.py" for m in suite}
            common = shared_inputs(leaves)
            keys = {m: module_key(m, common) for m in run}
        except ValueError as e:
            print(f"gate: {e}", file=sys.stderr)
            return 2
        except OSError as e:
            print(f"gate: no test cache this run: {e}", file=sys.stderr)
            cache, keys = None, {}
    hits: list[str] = []
    for m in run:
        e = cache.lookup(keys[m]) if cache is not None else None
        if e is not None:
            hits.append(m)
            print(f"gate module {m}: cached, {float(e['seconds']):.2f} s, {e['tests']} tests")
    sys.stdout.flush()
    todo = [m for m in run if m not in hits]
    alone = [m for m in todo if m in SERIAL]
    together = [m for m in todo if m not in alone]
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(run_one, together))
    results += [run_one(m) for m in alone]
    failed = [name for name, rc, _s, _t in results if rc != 0]
    if cache is not None and any(rc == 0 for _n, rc, _s, _t in results):
        if branches_left():  # a module that leaked a branch passed its run but not the gate: record nothing
            print("gate: a state/* branch is left, so no module's pass is recorded in the test cache", file=sys.stderr)
        else:
            for name, rc, secs, t in results:
                if rc == 0:
                    cache.record(keys[name], t, secs)
    tests = sum(t for *_x, t in results)
    print(f"gate: {len(run)} modules, ran {len(results)}, cached {len(hits)}, {tests} tests, {n} workers, "
          f"{time.monotonic() - t0:.1f} s" + (f"; FAILED: {', '.join(sorted(failed))}" if failed else "; all passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
