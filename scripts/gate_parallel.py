#!/usr/bin/env python3
"""gate_parallel.py — the plane's test modules, each in its own process, for scripts/gate.sh.

Runs every `tests/test_*.py` module as `python3 -m unittest tests.<module>` from the repo root,
GATE_WORKERS at a time (default: the CPU count), the largest files first so the slowest modules do
not start last. The modules in SERIAL run afterwards, one at a time, with nothing else running.
Each module's output is printed whole when it ends, then one line:

  gate module tests.test_x: ok, 12.34 s, 45 tests
  gate module tests.test_x: FAILED (exit 1), 12.34 s, 45 tests

which scripts/gate_result.py reads for the result file's `modules`. Exits 1 when any module failed
or errored (a non-zero exit), 2 on a bad GATE_WORKERS; the `state/*` check is gate.sh's, after it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Modules (dotted, `tests.test_x`) that share state with another (a fixed path, a port, the real HOME)
# and must run alone.
SERIAL: list[str] = []
RAN_RE = re.compile(r"^Ran (\d+) tests? in ", re.M)
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


def run_one(name: str) -> tuple[str, int, float, int]:
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, "-m", "unittest", name], cwd=ROOT, stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    secs = time.monotonic() - t0
    ran = RAN_RE.search(p.stdout)
    tests = int(ran.group(1)) if ran else 0
    state = "ok" if p.returncode == 0 else f"FAILED (exit {p.returncode})"
    with _print:
        sys.stdout.write(p.stdout if p.stdout.endswith("\n") or not p.stdout else p.stdout + "\n")
        sys.stdout.write(f"gate module {name}: {state}, {secs:.2f} s, {tests} tests\n")
        sys.stdout.flush()
    return name, p.returncode, secs, tests


def main() -> int:
    try:
        n = workers()
    except ValueError as e:
        print(f"gate: {e}", file=sys.stderr)
        return 2
    t0 = time.monotonic()
    names = modules()
    alone = [m for m in names if m in SERIAL]
    together = [m for m in names if m not in alone]
    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(run_one, together))
    results += [run_one(m) for m in alone]
    failed = [name for name, rc, _s, _t in results if rc != 0]
    tests = sum(t for *_x, t in results)
    print(f"gate: {len(results)} modules, {tests} tests, {n} workers, {time.monotonic() - t0:.1f} s"
          + (f"; FAILED: {', '.join(sorted(failed))}" if failed else "; all passed"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
