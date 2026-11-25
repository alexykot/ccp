"""`ccp mutate`'s refusals (SPEC §20.6) on plain values: the arguments, the mutants and the worktree, each refused
(exit 2) before any test runs, read from plain bytes and a temp directory of plain files."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ccp import mutate, wt
from ccp.queue import QueueError

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
TASK = "0002-second"


class PlainFiles(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ccp-mutate-refusals-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "calc.py").write_text(CALC)

    def refused(self, fn, *a) -> str:
        with self.assertRaises(QueueError) as cm:
            fn(*a)
        self.assertEqual(cm.exception.code, 2)
        return str(cm.exception)

    def mfile(self, old: str, new: str, name: str = "m.txt") -> str:
        (self.root / name).write_text(f"calc.py\n=== old\n{old}=== new\n{new}")
        return name


class Arguments(PlainFiles):
    def test_no_test_a_blank_test_or_no_mutant_is_refused(self):
        for tests in ([], [" "], ["test_calc", ""]):
            self.assertIn("--test", self.refused(mutate._usage, tests, ["calc.py:a=>b"], [], []))
        self.assertIn("--mutant", self.refused(mutate._usage, ["test_calc"], [], [], []))
        mutate._usage(["test_calc", "test_other"], [], ["calc.py"], [])  # a revert alone is a mutant


class TextMutants(PlainFiles):
    def test_a_substitution_whose_new_text_is_its_old_text_changes_nothing(self):
        msg = self.refused(mutate.parse, self.root, "calc.py:a + b=>a + b", self.root)
        self.assertIn("changes nothing", msg)
        # unchecked counts (a --together part) are refused the same way, at the first such part
        self.assertIn("changes nothing", self.refused(mutate.parse, self.root, "calc.py:sub=>sub", self.root, False))

    def test_a_mutant_file_whose_new_text_is_its_old_text_changes_nothing(self):
        name = self.mfile("    return a + b\n", "    return a + b\n")
        self.assertIn("changes nothing", self.refused(mutate.parse_file, self.root, name, self.root))
        differs = mutate.parse_file(self.root, self.mfile("    return a + b\n", "    return a + b \n"), self.root)
        self.assertEqual(differs["kind"], "text")  # one byte apart is a mutant

    def test_old_text_absent_or_ambiguous(self):
        self.assertIn("0 times", self.refused(mutate.parse, self.root, "calc.py:a / b=>a - b", self.root))
        self.assertIn("2 times", self.refused(mutate.parse, self.root, "calc.py:def =>fed ", self.root))
        self.assertIn("2 times", self.refused(mutate._once, "m", "calc.py", CALC.encode(), b"return", False))
        mutate._once("m", "calc.py", CALC.encode(), b"a + b", False)  # once: no refusal

    def test_an_ambiguous_old_text_names_the_lines_it_is_on(self):
        self.assertIn("2 times, at lines 2 and 6;", self.refused(mutate._once, "m", "calc.py", CALC.encode(),
                                                                  b"return", False))
        three = (CALC + "\n\ndef mul(a, b):\n    return a * b\n").encode()
        self.assertIn("3 times, at lines 2, 6 and 10;", self.refused(mutate._once, "m", "calc.py", three, b"return",
                                                                      False))
        self.assertIn("2 times, at lines 1 and 5;", self.refused(mutate.parse, self.root, "calc.py:def =>fed ",
                                                                 self.root))
        # the lines of the text as checked: what the earlier parts leave
        msg = self.refused(mutate.together, [mutate.parse(self.root, s, self.root, False) for s in
                                             ("calc.py:def add(a, b):\n=>", "calc.py:return=>yield")],
                           {"calc.py": CALC.encode()})
        self.assertIn("leave it 2 times, at lines 1 and 5;", msg)
        self.assertNotIn("at line", self.refused(mutate._once, "m", "calc.py", CALC.encode(), b"a / b", False))

    def test_a_mutant_that_is_no_file_or_leaves_the_worktree(self):
        for spec in ("no-such.patch", "../calc.py:a + b=>a - b", "missing.py:a=>b", "/etc/hosts:a=>b",
                     "calc.py=>x", "calc.py:=>x"):
            self.refused(mutate.parse, self.root, spec, self.root)

    def test_a_mutant_file_whose_old_text_or_target_is_not_there(self):
        for text in ("calc.py\n=== old\nreturn a / b\n=== new\nx\n", "missing.py\n=== old\na + b\n=== new\nx\n",
                     "../calc.py\n=== old\na + b\n=== new\nx\n", "/etc/hosts\n=== old\na + b\n=== new\nx\n"):
            (self.root / "m.txt").write_text(text)
            self.refused(mutate.parse_file, self.root, "m.txt", self.root)

    def test_a_mutant_file_with_a_part_missing(self):
        for text in ("calc.py\n=== old\n    return a + b\n", "calc.py\n=== new\nx\n", "\n=== old\na\n=== new\nb\n",
                     "=== old\n    return a + b\n=== new\nx\n",  # no file, the marker first
                     "calc.py\n=== new\nx\n=== old\n    return a + b\n",  # the markers swapped
                     "calc.py\n=== old\n=== new\nx\n", ""):
            (self.root / "m.txt").write_text(text)
            self.refused(mutate.parse_file, self.root, "m.txt", self.root)
        self.assertIn("not a file", self.refused(mutate.parse_file, self.root, "no-such.txt", self.root))


class Together(PlainFiles):
    def parts(self, *specs: str) -> list[dict]:
        return [mutate.parse(self.root, s, self.root, False) for s in specs]

    def test_one_part_a_patch_sharing_a_file_or_an_old_text_an_earlier_part_removed(self):
        texts = {"calc.py": CALC.encode()}
        self.assertIn("at least two", self.refused(mutate.together, self.parts("calc.py:a + b=>a - b"), texts))
        patch = {"kind": "patch", "files": ["calc.py"], "digest": "0" * 12}
        self.assertIn("only substitutions", self.refused(mutate.together, [patch, *self.parts("calc.py:sub=>add")],
                                                         texts))
        msg = self.refused(mutate.together, self.parts("calc.py:a + b=>a * b", "calc.py:a + b=>a - b"), texts)
        self.assertIn("as the earlier parts on it leave it 0 times", msg)


class Worktree(unittest.TestCase):
    def setUp(self):
        t = Path(tempfile.mkdtemp(prefix="ccp-mutate-wt-")).resolve()
        self.addCleanup(shutil.rmtree, t, True)
        self.q, self.here = t / "queue", t / "here"
        self.here.mkdir()
        self.cfg = SimpleNamespace(root=self.here)

    def record(self, kind: str, task: str = TASK) -> None:
        wt.save(self.q, {"name": f"{kind}-0002", "kind": kind, "task_id": task, "path": str(self.here)})

    def test_an_unrecorded_or_other_kind_of_worktree_is_refused(self):
        with self.assertRaises(QueueError) as cm:
            mutate._worktree(self.cfg, self.q, TASK)
        self.assertEqual(cm.exception.code, 2)
        self.record("mac")
        with self.assertRaises(QueueError) as cm:
            mutate._worktree(self.cfg, self.q, TASK)
        self.assertIn("mac", str(cm.exception))

    def test_each_seat_s_worktree_of_the_task_is_taken_and_another_task_s_is_refused(self):
        for kind in mutate.WORKTREE_KINDS:
            self.record(kind)
            self.assertEqual(mutate._worktree(self.cfg, self.q, TASK)["kind"], kind)
            wt.state_path(self.q, f"{kind}-0002").unlink()
        self.record("rev", task="0001-first")
        with self.assertRaises(QueueError) as cm:
            mutate._worktree(self.cfg, self.q, TASK)
        self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
