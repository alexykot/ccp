"""tasklog's one dod_check parser (`checks`) and its one reader of a file at a commit (`text_at`)."""
from __future__ import annotations

import subprocess
import unittest

from ccp import tasklog
from tests.helpers import Product

THREE = """# Task: x

## Scope

- In: `a.py`.

## dod_checks

- id: `cg-01`
  story: As a developer, the first holds.
  runs_on: part
  steps:
    1. Run `echo one`.
  expect: exit 0.
  dry run (`abc1234`): step 1 exited 0.

- id: `cg-02`
  story: As a developer, the second holds.
  steps:
    1. Run `echo two`.
       expect: not a key of the check.
  expect: prints two.

- id: `doc-03`
  expect: the text reads.

Text after the checks, outside any of them.

## Implementation notes

- id: `cg-09`
  expect: this is not a check.
"""


class Checks(unittest.TestCase):
    def test_a_task_with_three_checks_gives_each_its_id_block_and_key_lines(self):
        got = tasklog.checks(THREE)
        self.assertEqual([c.id for c in got], ["cg-01", "cg-02", "doc-03"])
        self.assertEqual(got[0].fields, {"story": "As a developer, the first holds.", "runs_on": "part",
                                         "steps": "", "expect": "exit 0.", "dry run": "step 1 exited 0."})
        self.assertEqual(got[1].fields, {"story": "As a developer, the second holds.", "steps": "",
                                         "expect": "prints two."})
        self.assertEqual(got[2].fields, {"expect": "the text reads."})
        self.assertIn("echo one", got[0].block)
        self.assertNotIn("cg-02", got[0].block)
        self.assertNotIn("- id:", got[0].block)
        self.assertEqual(THREE[got[1].start:got[1].end], got[1].block)
        self.assertNotIn("cg-09", "".join(c.id for c in got))

    def test_a_comment_after_an_id_is_allowed_and_a_malformed_id_line_is_no_check(self):
        text = ("## dod_checks\n\n- id: `cg-01`   # the first\n  expect: ok.\n\n"
                "- id: `CG-02`\n  expect: upper case is no kind.\n\n- id: cg-03\n  expect: no backticks.\n")
        got = tasklog.checks(text)
        self.assertEqual([c.id for c in got], ["cg-01"])
        self.assertEqual(got[0].fields["expect"], "ok.")
        self.assertIn("CG-02", got[0].block)

    def test_a_task_with_no_dod_checks_section_has_no_checks(self):
        self.assertEqual(tasklog.checks("## Scope\n\n- id: `cg-01`\n  expect: ok.\n"), [])
        self.assertEqual(tasklog.checks(""), [])


class TextAt(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self.git("init", "-q")
        self.p.write("notes/a.md", "kept at the first commit\n")
        self.git("add", "notes/a.md")
        self.git("commit", "-qm", "first")

    def git(self, *a: str) -> None:
        subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                       check=True, capture_output=True)

    def test_a_file_at_a_commit_is_its_text_there_not_the_checkouts(self):
        self.p.write("notes/a.md", "second commit\n")
        self.git("commit", "-qam", "second")
        self.p.write("notes/a.md", "staged\n")
        self.git("add", "notes/a.md")
        self.p.write("notes/a.md", "edited after the commit\n")
        cfg = self.p.cfg
        self.assertEqual(tasklog.text_at(cfg, "HEAD", "notes/a.md"), "second commit\n")
        self.assertEqual(tasklog.text_at(cfg, "HEAD~1", "notes/a.md"), "kept at the first commit\n")
        self.assertEqual(tasklog.text_at(cfg, "", "notes/a.md"), "staged\n")

    def test_a_file_missing_at_the_rev_is_none_though_the_checkout_has_it(self):
        self.p.write("notes/b.md", "only in the checkout\n")
        self.assertIsNone(tasklog.text_at(self.p.cfg, "HEAD", "notes/b.md"))

    def test_a_rev_that_does_not_resolve_is_none(self):
        self.assertIsNone(tasklog.text_at(self.p.cfg, "no-such-rev", "notes/a.md"))


if __name__ == "__main__":
    unittest.main()
