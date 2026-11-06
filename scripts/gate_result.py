#!/usr/bin/env python3
"""gate_result.py LOG SECONDS — the gate-result JSON (contracts/suite_result.schema.json) from a
unittest run's output, for scripts/gate.sh."""
import json, re, sys
text = open(sys.argv[1], errors="replace").read()
ran = re.search(r"^Ran (\d+) tests? in", text, re.M)
summary = re.findall(r"^(?:OK|FAILED)\b.*$", text, re.M)
skipped = re.search(r"\bskipped=(\d+)", summary[-1]) if summary else None
def fid(name, paren):
    # 3.11+: "FAIL: test_x (pkg.mod.Class.test_x)"; older: "(pkg.mod.Class)"; setUpClass: "(pkg.mod.Class)"
    return paren if paren.endswith("." + name) else f"{paren}.{name}"
fails = [fid(n, p) for n, p in re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]+)\)", text, re.M)]
print(json.dumps({"tests": int(ran.group(1)) if ran else 0,
                  "skipped": int(skipped.group(1)) if skipped else 0,
                  "failed": len(fails), "failures": [{"id": f} for f in fails],
                  "seconds": int(sys.argv[2])}))
