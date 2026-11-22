"""`ccp mutate` with several `--test` ids (SPEC §20.6): the tests run in order until one fails, that run decides
the mutant, and its row names the test and the failing tests its output names."""
from __future__ import annotations

import json
import re
import shlex
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from ccp import config, mutate, runs
from tests.toolkit_fixture import ToolkitFixture, git

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef unused(a):\n    return a * 2\n"
ONE = """import unittest

from calc import add


class OneTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 1), 2)
"""
TWO = """import unittest

from calc import add, sub


class TwoTest(unittest.TestCase):
    def test_add_zero(self):
        self.assertEqual(add(2, 0), 2)

    def test_sub(self):
        self.assertEqual(sub(3, 1), 2)
"""
COMMAND = f"{shlex.quote(sys.executable)} -B -m unittest -q {{test}}"
FIRST, SECOND = "test_one", "test_two"
SUB_MUTANT = "calc.py:a - b=>a + b"  # only the second module's test_sub fails
UNUSED_MUTANT = "calc.py:a * 2=>a * 3"  # no test reaches it


class SeveralTests(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "language": "python", "mutate": {"command": COMMAND}}

    @classmethod
    def _build_repos(cls, t: Path) -> None:
        super()._build_repos(t)
        main = t / "product"
        for rel, text in (("calc.py", CALC), (f"{FIRST}.py", ONE), (f"{SECOND}.py", TWO)):
            (main / rel).write_text(text)
        git(main, "add", "calc.py", f"{FIRST}.py", f"{SECOND}.py")
        git(main, "commit", "-q", "-m", "calc")
        git(main, "push", "-q", "origin", "main")

    def setUp(self):
        super().setUp()
        self.run_id = runs.open_run(self.q, config.load(self.main), "0002-second", "verify", prompt_ref=None,
                                    note=None, supersede=False)["run_id"]
        head = git(self.main, "rev-parse", "origin/main")
        code, body, _, err = self.ccp("wt", "create", "--kind", "mut", "--task", "0002", "--sha", head, root=self.main)
        self.assertEqual(code, 0, err)
        self.mut = Path(body["path"])

    def mutate(self, *mutants: str, tests: tuple[str, ...] = (FIRST, SECOND)):
        args = ["mutate", "--run", self.run_id]
        for t in tests:
            args += ["--test", t]
        for m in mutants:
            args += ["--mutant", m]
        return self.ccp(*args, root=self.mut)

    def rows(self) -> list[dict]:
        return runs.load(self.q, self.run_id).get("mutation", [])

    def log(self) -> str:
        return mutate.log_path(self.q, self.run_id).read_text()

    def test_a_mutant_only_the_second_test_fails_is_killed_by_the_second(self):
        code, body, _, err = self.mutate(SUB_MUTANT)
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["outcome"], r["test"]) for r in self.rows()], [("killed", SECOND)])
        self.assertEqual([b["test"] for b in body["baseline"]], [FIRST, SECOND])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_mutant_every_test_passes_survives_named_by_the_last(self):
        code, _, _, err = self.mutate(UNUSED_MUTANT)
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["outcome"], r["test"]) for r in self.rows()], [("survived", SECOND)])

    def test_the_first_test_that_fails_decides_and_the_rest_do_not_run(self):
        code, _, _, err = self.mutate("calc.py:a + b=>a - b")  # both modules fail; the first decides
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["outcome"], r["test"]) for r in self.rows()], [("killed", FIRST)])
        self.assertIn(f"{FIRST} mutant 1 ", self.log())
        self.assertNotIn(f"{SECOND} mutant 1 ", self.log())

    def test_a_second_test_that_fails_unmutated_stops_the_call_naming_it(self):
        (self.mut / f"{SECOND}.py").write_text(TWO.replace("sub(3, 1), 2", "sub(3, 1), 5"))
        code, _, _, err = self.mutate(SUB_MUTANT)
        self.assertEqual(code, 1, err)
        self.assertIn(SECOND, err)
        self.assertEqual(self.rows(), [])
        self.assertNotIn("mutant 1 ", self.log())

    def test_each_killed_row_names_its_own_failing_tests_and_a_survived_row_none(self):
        code, _, _, err = self.mutate("calc.py:a + b=>a - b", SUB_MUTANT, UNUSED_MUTANT)
        self.assertEqual(code, 1, err)
        first, second, survived = self.rows()
        self.assertEqual(len(first["failed"]), 1, first)
        self.assertTrue(first["failed"][0].startswith(f"test_add ({FIRST}.OneTest"), first["failed"])
        self.assertEqual(len(second["failed"]), 1, second)
        self.assertTrue(second["failed"][0].startswith(f"test_sub ({SECOND}.TwoTest"), second["failed"])
        self.assertEqual((survived["outcome"], survived["failed"]), ("survived", []))

    def test_the_product_s_section_pattern_replaces_the_pack_s(self):
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        p.write_text(json.dumps({**body, "suite": {**body.get("suite", {}), "summary": {"section_re": "^NEVER: "}}}))
        code, _, _, err = self.mutate(SUB_MUTANT)
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["outcome"], r["failed"]) for r in self.rows()], [("killed", [])])

    def test_a_no_op_mutant_among_others_refuses_the_call_before_any_test_runs(self):
        code, _, _, err = self.mutate(SUB_MUTANT, "calc.py:a * 2=>a * 2")
        self.assertEqual(code, 2, err)
        self.assertIn("changes nothing", err)
        self.assertEqual(self.rows(), [])
        self.assertFalse(mutate.log_path(self.q, self.run_id).exists())


class FailedIds(unittest.TestCase):
    """The failing tests a run's output names, read from the log from the run's own offset."""

    def setUp(self):
        d = Path(tempfile.mkdtemp(prefix="ccp-mutate-failed-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.log = d / "mutate.log"

    def test_each_matching_line_after_the_offset_its_match_stripped_in_order_at_most_twenty(self):
        before = "FAIL: earlier_run (m.T.earlier_run)\n"
        self.log.write_text(before + "".join(f"noise {i}\nFAIL:  t{i} (m.T.t{i}) \n" for i in range(25)))
        got = mutate._failed(self.log, len(before), [re.compile(r"^(?:FAIL|ERROR): ")])
        self.assertEqual(got, [f"t{i} (m.T.t{i})" for i in range(mutate.MAX_FAILED)])
        self.assertEqual(mutate._failed(self.log, 0, []), [])


if __name__ == "__main__":
    unittest.main()
