#!/usr/bin/env python3
"""gate_result.py LOG SECONDS — the gate-result JSON (contracts/suite_result.schema.json) from the gate's
output, for scripts/gate.sh. The counts are summed over every unittest run in the log (one per module
under scripts/gate_parallel.py); each `gate module` line of a module that ran becomes an entry of
`modules` ({name, seconds, tests}), and a module that failed with no failing test named (it crashed)
counts as one failure under its own name. With module lines, `ran` and `cached` count the modules run
and those the gate's test cache served (SPEC §15.3), and `cached_tests` the tests behind the cached
ones, from the runs that recorded them; a cached module is in neither `tests` nor `modules`."""
import json, re, sys
text = open(sys.argv[1], errors="replace").read()
ran = [int(n) for n in re.findall(r"^Ran (\d+) tests? in", text, re.M)]
summary = re.findall(r"^(?:OK|FAILED)\b.*$", text, re.M)
skipped = [int(n) for s in summary for n in re.findall(r"\bskipped=(\d+)", s)]
def fid(name, paren):
    # 3.11+: "FAIL: test_x (pkg.mod.Class.test_x)"; older: "(pkg.mod.Class)"; setUpClass: "(pkg.mod.Class)"
    return paren if paren.endswith("." + name) else f"{paren}.{name}"
FAIL_RE = re.compile(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", re.M)
MOD_RE = re.compile(r"^gate module (\S+): (ok|cached|FAILED[^,]*), (\d+(?:\.\d+)?) s, (\d+) tests?$", re.M)
fails, mods, at, cached, cached_tests = [], [], 0, 0, 0
for m in MOD_RE.finditer(text):  # each module's output comes whole, just before its line
    if m.group(2) == "cached":  # served from the cache: no output of its own, nothing ran
        cached, cached_tests, at = cached + 1, cached_tests + int(m.group(4)), m.end()
        continue
    block = [fid(n, p) for n, p in FAIL_RE.findall(text, at, m.start())]
    # a module that failed to import is named by unittest's loader, not by its own name
    block = [m.group(1) if f.startswith("unittest.loader._FailedTest.") else f for f in block]
    fails += block if block or m.group(2) == "ok" else [m.group(1)]  # crashed with no test named
    mods.append({"name": m.group(1), "seconds": float(m.group(3)), "tests": int(m.group(4))})
    at = m.end()
fails += [fid(n, p) for n, p in FAIL_RE.findall(text, at)]  # a log with no module lines: all of it
out = {"tests": sum(ran), "skipped": sum(skipped), "failed": len(fails), "failures": [{"id": f} for f in fails],
       "seconds": int(sys.argv[2])}
if mods:
    out["modules"] = mods
if mods or cached:
    out.update(ran=len(mods), cached=cached, cached_tests=cached_tests)
print(json.dumps(out))
