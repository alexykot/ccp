"""`ccp mutate` (SPEC §20.6): a mutant is killed only when the named test fails, and the worktree is
restored after each."""
from __future__ import annotations

import json
import shlex
import sys
import unittest
from pathlib import Path

from ccp import config, runs
from tests.test_toolkit import PLANE, ToolkitFixture, git

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef unused(a):\n    return a * 2\n"
TESTS = """import unittest

from calc import add, sub


class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 1), 2)

    def test_sub(self):
        self.assertEqual(sub(3, 1), 2)
"""
ADD = "test_calc.CalcTest.test_add"
COMMAND = f"{shlex.quote(sys.executable)} -B -m unittest -q {{test}}"


class MutateFixture(ToolkitFixture):
    def setUp(self):
        super().setUp()
        self.write("docs/delivery/plane.json", json.dumps({**self.PLANE_JSON, "mutate": {"command": COMMAND}}))
        self.write("calc.py", CALC)
        self.write("test_calc.py", TESTS)
        git(self.main, "add", "docs/delivery/plane.json", "calc.py", "test_calc.py")
        git(self.main, "commit", "-q", "-m", "calc")
        git(self.main, "push", "-q", "origin", "main")
        self.run_id = runs.open_run(self.q, config.load(self.main), "0002-second", "verify", prompt_ref=None,
                                    note=None, supersede=False)["run_id"]
        self.mut = self.make_wt("mut")

    def make_wt(self, kind: str, task: str = "0002") -> Path:
        head = git(self.main, "rev-parse", "origin/main")
        code, body, _, err = self.ccp("wt", "create", "--kind", kind, "--task", task, "--sha", head, root=self.main)
        self.assertEqual(code, 0, err)
        return Path(body["path"])

    def mutate(self, *mutants: str, test: str = ADD, root: Path | None = None, run: str | None = None):
        args = ["mutate", "--run", run or self.run_id, "--test", test]
        for m in mutants:
            args += ["--mutant", m]
        return self.ccp(*args, root=root or self.mut)

    def rows(self) -> list[dict]:
        return runs.load(self.q, self.run_id).get("mutation", [])

    def set_mutate(self, **knobs) -> None:
        """The mutation worktree's own plane.json (ccp reads the checkout it runs in)."""
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        body["mutate"] = {**body["mutate"], **knobs}
        p.write_text(json.dumps(body))


class Outcomes(MutateFixture, unittest.TestCase):
    def test_a_mutant_the_test_catches_is_killed_and_the_file_restored(self):
        code, body, _, err = self.mutate("calc.py:a + b=>a - b")
        self.assertEqual(code, 0, err)
        self.assertEqual((body["killed"], body["survived"]), (1, 0))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        row = self.rows()[0]
        self.assertEqual((row["outcome"], row["test"], row["mutant"], row["kind"], row["files"]),
                         ("killed", ADD, 1, "text", ["calc.py"]))
        self.assertNotEqual(row["exit_code"], 0)
        ev = [e for e in self.events() if (e["type"], e["op"]) == ("run", "recorded")]
        self.assertEqual([(e["payload"]["run_id"], e["payload"]["killed"], e["payload"]["survived"]) for e in ev],
                         [(self.run_id, 1, 0)])
        self.assertIn("FAIL: test_add", Path(body["log"]).read_text())

    def test_a_mutant_the_test_does_not_reach_survives(self):
        code, body, _, err = self.mutate("calc.py:a * 2=>a * 3")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.rows()[0]["outcome"], "survived")
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_mutant_that_breaks_only_another_test_survives(self):
        code, _, _, err = self.mutate("calc.py:return a - b=>return a + b")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.rows()[0]["outcome"], "survived")
        code, _, _, err = self.mutate("calc.py:return a - b=>return a + b", test="test_calc.CalcTest.test_sub")
        self.assertEqual((code, self.rows()[1]["outcome"]), (0, "killed"), err)

    def test_each_mutant_runs_alone_on_the_restored_tree(self):
        code, body, _, err = self.mutate("calc.py:a * 2=>a * 3", "calc.py:a + b=>a - b", "calc.py:a * 2=>a * 4")
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["outcome"]) for r in self.rows()],
                         [(1, "survived"), (2, "killed"), (3, "survived")])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_patch_is_a_mutant(self):
        (self.mut / "calc.py").write_text(CALC.replace("a + b", "a + b + 1"))
        patch = Path(self._tmp.name) / "m.patch"
        patch.write_text(git(self.mut, "diff") + "\n")
        git(self.mut, "checkout", "--", "calc.py")
        code, body, _, err = self.mutate(str(patch))
        self.assertEqual(code, 0, err)
        self.assertEqual((self.rows()[0]["kind"], self.rows()[0]["files"], self.rows()[0]["outcome"]),
                         ("patch", ["calc.py"], "killed"))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_patch_that_adds_a_file_is_undone(self):
        (self.mut / "calc.py").write_text(CALC.replace("a + b", "helper(a, b)") + "from extra import helper\n")
        (self.mut / "extra.py").write_text("def helper(a, b):\n    return a + b\n")
        git(self.mut, "add", "-N", "extra.py")
        patch = Path(self._tmp.name) / "m.patch"
        patch.write_text(git(self.mut, "diff") + "\n")
        git(self.mut, "reset", "-q", "extra.py")
        (self.mut / "extra.py").unlink()
        git(self.mut, "checkout", "--", "calc.py")
        code, body, _, err = self.mutate(str(patch))
        self.assertEqual((code, self.rows()[0]["outcome"]), (1, "survived"), err)
        self.assertEqual(sorted(self.rows()[0]["files"]), ["calc.py", "extra.py"])
        self.assertFalse((self.mut / "extra.py").exists())
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_hang_is_killed_at_the_timeout(self):
        self.set_mutate(timeout_seconds=2)
        code, _, _, err = self.mutate("calc.py:return a + b=>while True: pass")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.rows()[0]["outcome"], self.rows()[0]["timed_out"]), ("killed", True))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_the_record_carries_no_mutant_text(self):
        self.mutate("calc.py:a + b=>a - b")
        raw = runs.path(self.q, self.run_id).read_text()
        self.assertNotIn("a - b", raw)
        self.assertEqual(len(self.rows()[0]["digest"]), 12)

    def test_a_sigterm_restores_the_files(self):
        self.set_mutate(command="grep -q KILLME calc.py && kill -TERM $PPID && sleep 5; " + COMMAND)
        code, _, _, err = self.mutate("calc.py:a + b=>a + b  # KILLME")
        self.assertEqual(code, 143, err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertEqual(self.rows(), [])


class Refusals(MutateFixture, unittest.TestCase):
    def refused(self, code_want: int, *mutants: str, **kw) -> str:
        code, _, _, err = self.mutate(*mutants, **kw)
        self.assertEqual(code, code_want, err)
        self.assertEqual(self.rows(), [])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        return err

    def test_outside_a_mutation_worktree(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("ver"))
        self.refused(2, "calc.py:a + b=>a - b", root=self.main)

    def test_a_mutation_worktree_of_another_task(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("mut", task="0001"))

    def test_old_text_absent_or_ambiguous(self):
        self.refused(2, "calc.py:a / b=>a - b")
        self.refused(2, "calc.py:def =>fed ")
        self.refused(2, "calc.py:a + b=>a - b", "calc.py:nope=>x")  # one bad mutant: none runs

    def test_a_mutant_that_is_no_file_or_leaves_the_worktree(self):
        self.refused(2, "no-such.patch")
        self.refused(2, "../calc.py:a + b=>a - b")
        self.refused(2, "missing.py:a=>b")
        self.refused(2, "/etc/hosts:a=>b")
        self.refused(2, "calc.py=>x")
        self.refused(2, "calc.py:=>x")

    def test_no_test_named(self):
        self.refused(2, "calc.py:a + b=>a - b", test=" ")

    def test_a_closed_run(self):
        rec = runs.load(self.q, self.run_id)
        rec["reported_at"] = "2026-11-10T00:00:00Z"
        runs.save(self.q, rec)
        self.refused(2, "calc.py:a + b=>a - b")

    def test_no_command(self):
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        del body["mutate"]
        p.write_text(json.dumps(body))
        self.refused(2, "calc.py:a + b=>a - b")

    def test_a_test_that_fails_unmutated(self):
        (self.mut / "test_calc.py").write_text(TESTS.replace("add(1, 1), 2", "add(1, 1), 3"))
        self.refused(1, "calc.py:a + b=>a - b")


class PatchPaths(unittest.TestCase):
    def test_numstat_names_plain_and_renamed_paths(self):
        from ccp import mutate
        out = "1\t1\tcalc.py\x000\t0\t\x00old.py\x00new.py\x00-\t-\tbin.dat\x00"
        self.assertEqual(mutate._numstat_paths(out), ["calc.py", "old.py", "new.py", "bin.dat"])


class MutateConfig(unittest.TestCase):
    def test_the_block_is_checked(self):
        from tests.helpers import Product
        for bad in ({"command": "run-one-test"}, {"command": ""}, {"timeout_seconds": 0}, {"other": 1}):
            p = Product({"mutate": bad})
            try:
                with self.assertRaises(config.ConfigError, msg=bad):
                    p.cfg
            finally:
                p.cleanup()
        p = Product({"mutate": {"command": "t {test}"}})
        try:
            self.assertEqual(p.cfg.mutate, {"command": "t {test}", "timeout_seconds": 600})
        finally:
            p.cleanup()

    def test_the_schema_lists_the_block(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["mutate"]["properties"]), set(config.MUTATE_DEFAULTS))


if __name__ == "__main__":
    unittest.main()
