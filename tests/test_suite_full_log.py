"""A recorded `ccp suite run --full` keeps a log (SPEC §14.2, §14.4): what it copies through, both streams, goes to
the log summary mode would name too, the terminal gets the command's output and nothing else, and the `ended` row
records the log's path; a log that cannot be opened is a warning, and the run streams with none."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.helpers import Product, repo_git as git
from tests.suite_fixture import PY, ccp_proc

ALPHA_BETA = "import sys; print('alpha'); sys.stdout.flush(); print('beta', file=sys.stderr)"


class FullLog(unittest.TestCase):
    def setUp(self):
        self.p = Product({"language": "python"})
        self.addCleanup(self.p.cleanup)
        qdir = tempfile.TemporaryDirectory()
        self.addCleanup(qdir.cleanup)
        self.q = Path(qdir.name)
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")

    def ccp(self, *args: str):
        return ccp_proc(self.p.root, *args, env={"QUEUE_ROOT": str(self.q)})

    def ended(self) -> list[dict]:
        p = self.q / "runs" / "_suites.jsonl"
        return [r for r in (json.loads(x) for x in p.read_text().splitlines()) if r["op"] == "ended"]

    def test_a_recorded_full_run_prints_only_the_output_and_logs_both_streams(self):
        r = self.ccp("suite", "run", "--full", "--lane", "part", "--", PY, "-c", ALPHA_BETA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((r.stdout, r.stderr), (b"alpha\n", b"beta\n"))  # no line of ccp's added
        [row] = self.ended()
        log = Path(row["log"])
        self.assertEqual(log.parent, self.q / "runs" / "_suite-logs")
        self.assertEqual(sorted(log.read_text().splitlines()), ["alpha", "beta"])
        listed = self.ccp("suite", "list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(json.loads(listed.stdout)["suites"][-1]["log"], str(log))

    def test_a_full_run_whose_log_cannot_be_opened_warns_and_streams_with_none(self):
        blocker = self.p.write("not-a-dir", "")
        r = self.ccp("suite", "run", "--full", "--lane", "part", "--log", str(blocker / "x.log"), "--", PY, "-c",
                     ALPHA_BETA)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, b"alpha\n")
        self.assertIn(b"beta\n", r.stderr)
        self.assertIn(b"no log file", r.stderr)
        self.assertIsNone(self.ended()[0]["log"])


if __name__ == "__main__":
    unittest.main()
