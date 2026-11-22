"""The suite-run tests' product and `ccp` runner, and the test module they run. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.helpers import with_test_methods
from tests.toolkit_fixture import ToolkitFixture


PLANE = Path(__file__).resolve().parents[1]
CCP = str(PLANE / "bin" / "ccp")
PY = sys.executable


def ccp_proc(cwd: Path, *args: str, env: dict | None = None, stdin: bytes | None = None,
             unset: tuple[str, ...] = ()) -> subprocess.CompletedProcess[bytes]:
    e = {**os.environ, **(env or {})}
    e.pop("CCP_SUITE_ID", None) if "CCP_SUITE_ID" not in (env or {}) else None
    e.pop("CCP_SUITE_COLD", None) if "CCP_SUITE_COLD" not in (env or {}) else None  # a cold outer run's
    for k in unset:
        e.pop(k, None)
    return subprocess.run([CCP, *args], cwd=cwd, env=e, input=stdin, capture_output=True, timeout=60)


# A product whose gate prints its own cache tally (`<name>: N modules ran, N cached; …the cached
# modules' last runs: N tests…`) and writes no result file keeps its counts with these knobs.
TALLY_SUMMARY = {
    "ran_re": r"^\S+: (\d+) modules? ran, \d+ cached",
    "cached_re": r"^\S+: \d+ modules? ran, (\d+) cached",
    "cached_tests_re": r"^\S+: \d+ modules? ran, .*\bcached modules' last runs: (\d+) tests?\b",
    "show_re": [r"^\S+: \d+ modules? ran, \d+ cached", r"^\S+: failed: ", r"^exit [1-9]\d*: "],
}


class SuiteFixture(ToolkitFixture):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "language": "python"}  # the tests below print unittest's output

    def tally(self, summary: dict | None = None) -> None:
        """Configure the product's tally regexes (the pre-contract defaults) in its plane.json."""
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg.setdefault("suite", {})["summary"] = summary or TALLY_SUMMARY
        p.write_text(json.dumps(cfg))

    def rows(self) -> list[dict]:
        p = self.q / "runs" / "_suites.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def run_suite(self, *args: str, **kw) -> subprocess.CompletedProcess[bytes]:
        return ccp_proc(self.runner, "suite", "run", *args, **kw)

    def implementing(self) -> None:
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)


FAILING_MODULE = with_test_methods("""\
import unittest
class T(unittest.TestCase):
    def t_ok(self):
        for i in range(300):
            print(f"noise line {i}")
    def t_bad(self):
        self.assertEqual(1, 2, "one is not two")
    def t_err(self):
        raise RuntimeError("boom")
    @unittest.skip("later")
    def t_skip(self):
        pass
""")


def _start_log(stdout: bytes) -> Path:
    first = stdout.decode().splitlines()[0]
    m = re.search(r"the output goes to (\S+); a summary follows", first)
    assert m, first
    return Path(m.group(1))
