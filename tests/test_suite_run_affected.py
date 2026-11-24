"""`ccp suite run --affected [--since <ref>]` (SPEC §14.7): it works out the test modules as `ccp suite affected`
does and runs what that command's stderr line names, recorded as any run; with nothing touched it runs and records
nothing; with modules and nothing to run them, or with `--lane`, a command after `--`, or `--since` alone, it exits 2
with nothing run (those flag rules are judged on the parsed flags)."""
from __future__ import annotations

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from ccp import suite
from tests.git_helpers import git
from tests.helpers import Product
from tests.suite_fixture import PY, ccp_proc

# A part-lane argv that writes the module names it was given, and counts one test
RECORD = "import json, sys; open('part-args.json', 'w').write(json.dumps(sys.argv[1:])); print('Ran 1 test in 0.0s')"
GATE = "open('gate-ran', 'w').write('x'); print('Ran 5 tests in 0.0s')"
FILLERS = [f"tests/test_filler{i}.py" for i in range(1, 7)]
ONE_TEST = "import unittest\nfrom pkg import {m}\n\n\nclass T(unittest.TestCase):\n    def test_it(self):\n        pass\n"


class AffectedProduct:
    """A git Python product: tests/test_a.py imports pkg/a.py, tests/test_b.py imports pkg/b.py, six filler test
    modules import nothing; its queue is a temp directory."""

    LANES: dict = {"gate": [PY, "-c", GATE], "part": [PY, "-c", RECORD]}

    def setUp(self, cfg: dict | None = None):
        self.p = Product(cfg or {"language": "python", "suite": {"lanes": self.LANES}})
        self.addCleanup(self.p.cleanup)
        qdir = tempfile.TemporaryDirectory()
        self.addCleanup(qdir.cleanup)
        self.q = Path(qdir.name)
        for rel, text in {
            ".gitignore": "part-args.json\ngate-ran\n",
            "pkg/__init__.py": "",
            "pkg/a.py": "X = 1\n",
            "pkg/b.py": "Y = 2\n",
            "tests/__init__.py": "",
            "tests/test_a.py": ONE_TEST.format(m="a"),
            "tests/test_b.py": ONE_TEST.format(m="b"),
            **{rel: "import unittest\n" for rel in FILLERS},
        }.items():
            self.p.write(rel, text)
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")

    def ccp(self, *args: str):
        return ccp_proc(self.p.root, *args, env={"QUEUE_ROOT": str(self.q)})

    def rows(self, op: str) -> list[dict]:
        p = self.q / "runs" / "_suites.jsonl"
        return [r for r in (json.loads(x) for x in p.read_text().splitlines()) if r["op"] == op] if p.is_file() else []

    def part_args(self) -> list[str] | None:
        p = self.p.root / "part-args.json"
        return json.loads(p.read_text()) if p.is_file() else None


class RunAffected(AffectedProduct, unittest.TestCase):

    def test_affected_runs_the_part_lane_with_exactly_the_modules_suite_affected_lists_and_records_one_run(self):
        self.p.write("pkg/a.py", "X = 3\n")
        self.p.write("pkg/b.py", "Y = 3\n")
        listed = self.ccp("suite", "affected")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        mods = listed.stdout.decode().split()
        self.assertEqual(mods, ["tests.test_a", "tests.test_b"])
        r = self.ccp("suite", "run", "--affected", "--summary")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.part_args(), mods)
        started, ended = self.rows("started"), self.rows("ended")
        self.assertEqual([(s["lane"], s["argc"]) for s in started], [("part", 2 + len(mods))])
        self.assertEqual([(e["suite_id"], e["tests"], e["exit_code"]) for e in ended],
                         [(started[0]["suite_id"], 1, 0)])

    def test_affected_runs_from_the_product_root_and_takes_log_from_the_callers_directory(self):
        self.p.write("pkg/a.py", "X = 3\n")
        r = ccp_proc(self.p.root / "pkg", "suite", "run", "--affected", "--summary", "--log", "mine.log",
                     env={"QUEUE_ROOT": str(self.q)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.part_args(), ["tests.test_a"])  # written in the root, where the modules are named from
        self.assertEqual(self.rows("ended")[0]["log"], str((self.p.root / "pkg" / "mine.log").resolve()))

    def test_affected_since_reads_the_change_as_suite_affected_does(self):
        self.p.write("pkg/a.py", "X = 3\n")
        git(self.p.root, "commit", "-qam", "change a")
        r = self.ccp("suite", "run", "--affected", "--summary", "--since", "HEAD~1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.part_args(), ["tests.test_a"])
        r = self.ccp("suite", "run", "--affected", "--since", "-x")  # a ref, never an option
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"'-x'", r.stderr)
        self.assertEqual(len(self.rows("started")), 1)

    def test_affected_with_nothing_touched_records_nothing_and_exits_0(self):
        r = self.ccp("suite", "run", "--affected", "--summary")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"ccp suite run --affected: no test module touched", r.stderr)
        self.assertEqual((self.rows("started"), self.part_args()), ([], None))

    def test_affected_with_a_lane_exits_2_with_nothing_run(self):
        self.p.write("pkg/a.py", "X = 3\n")
        r = self.ccp("suite", "run", "--summary", "--affected", "--lane", "part")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.rows("started"), [])
        self.assertIsNone(self.part_args())


class AffectedUsage(unittest.TestCase):
    """`--affected` and `--since` against the other flags, on the parsed values (`suite.affected_usage`)."""

    @staticmethod
    def ns(**flags) -> argparse.Namespace:
        return argparse.Namespace(**{"affected": False, "since": None, "lane": None, **flags})

    def test_since_without_affected_is_refused_by_name(self):
        self.assertIn("--since", suite.affected_usage(self.ns(since="HEAD"), ["true"]))
        self.assertIn("--since", suite.affected_usage(self.ns(since="HEAD", lane="part"), None))

    def test_affected_with_a_lane_is_refused_by_name(self):
        self.assertIn("--lane", suite.affected_usage(self.ns(affected=True, lane="part"), None))

    def test_affected_with_a_command_is_refused_by_name(self):
        self.assertIn("`--`", suite.affected_usage(self.ns(affected=True), ["true"]))

    def test_affected_alone_and_neither_flag_pass(self):
        self.assertIsNone(suite.affected_usage(self.ns(affected=True), None))
        self.assertIsNone(suite.affected_usage(self.ns(affected=True, since="HEAD"), None))
        self.assertIsNone(suite.affected_usage(self.ns(lane="part"), ["true"]))


class RunAffectedWithTheLanguagesCommand(AffectedProduct, unittest.TestCase):
    """The same product declaring no part lane: the language's command runs the modules, or the full lane past
    a quarter of the suite."""

    LANES = {"gate": [PY, "-c", GATE]}

    def test_affected_runs_the_languages_command_with_the_modules(self):
        self.p.write("pkg/a.py", "X = 3\n")
        r = self.ccp("suite", "run", "--affected", "--summary")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        started = self.rows("started")
        self.assertEqual([(s["lane"], s["cmd"], s["argc"]) for s in started], [("part", "python3", 3)])
        self.assertEqual(self.rows("ended")[0]["tests"], 1)

    def test_affected_past_a_quarter_of_the_suite_runs_the_full_lane(self):
        for rel in (*FILLERS[:2], "pkg/a.py"):  # 3 of 8 test modules
            self.p.write(rel, "import unittest\nX = 4\n")
        r = self.ccp("suite", "run", "--affected", "--summary")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([s["lane"] for s in self.rows("started")], ["gate"])  # the full role's lane here
        self.assertTrue((self.p.root / "gate-ran").exists())


class RunAffectedWithNothingToRunThem(AffectedProduct, unittest.TestCase):
    def setUp(self):
        super().setUp({"language": "none", "suite": {"lanes": {"gate": ["true"]}, "affected_map": {"pkg/*": ["t.one"]}}})

    def test_affected_modules_with_no_part_lane_and_no_language_command_exit_2(self):
        self.p.write("pkg/a.py", "X = 3\n")
        r = self.ccp("suite", "run", "--affected", "--summary")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"nothing runs them", r.stderr)
        self.assertEqual(self.rows("started"), [])


if __name__ == "__main__":
    unittest.main()
