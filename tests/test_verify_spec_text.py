"""`ccp verify spec-text` (SPEC §15.2, §3.5): the passages a task carries for the operator's sign-off, each a
`PROPOSED:` marker followed by `> ` blockquote lines in its Scope, are looked for, whitespace-normalised, in
the lines the branch adds to the product's SPEC files; and the review and verify prompts of a task that
declares a `brief` sign-off ask for it."""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, verify
from tests.helpers import Product
from tests.test_toolkit import GIT_ENV, ToolkitFixture, git

PASSAGE = ("A task whose brief sign-off is due and not recorded is passed over the same way, and stderr names "
           "the missing sign-off, so the runner takes the next task it can claim.")

SCOPE = """## Scope

- **In:**
  - `docs/spec/x.md` §1. CURRENT (at `abc1234`): none; a new sentence. PROPOSED:
    > A task whose brief sign-off is due and not recorded is passed over the same way, and stderr names the
    > missing sign-off, so the runner takes the next task it can claim.
  - the code, which reads each `PROPOSED:` block in the Scope.
- **Out:** nothing else.
"""

TASK = """---
task_id: 0001-signed
title: Signed text
status: pending
depends_on: []
spec_refs: ["S1"]
sign_off: brief
created: 2026-09-30
updated: 2026-09-30
---

# Task: 0001-signed

## Intent

Something true for the user.

## Context (not checked)

- background, with PROPOSED: outside the Scope
  > a quote outside the Scope is no signed passage

{scope}
## dod_checks

- id: `cmd-01`
  story: As an operator, I run it.
  steps:
    1. run
  expect: exit 0

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
"""


class SpecText(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("QUEUE_ROOT", None)
        self.p.task("0001-signed", body=TASK.format(scope=SCOPE))
        self.p.write("docs/spec/x.md", "# Spec\n\n## 1. Rules\n\nAn older rule.\n")
        self.p.write("notes.md", "# Notes\n")
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", ".")
        git(self.p.root, "commit", "-q", "-m", "init")
        git(self.p.root, "checkout", "-q", "-b", "task/0001-signed")

    def change(self, rel: str, add: str) -> None:
        path = self.p.root / rel
        path.write_text(path.read_text() + add)
        git(self.p.root, "commit", "-q", "-am", f"change {rel}")

    def run_cmd(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "spec-text", *args])
        body = out.getvalue()
        return code, (json.loads(body) if body.strip().startswith("{") else None), err.getvalue()

    def test_the_signed_passage_added_with_other_wrapping_passes(self):
        self.change("docs/spec/x.md", "\nA task whose brief sign-off is due and not recorded is passed over the\n"
                                      "same way,   and stderr names the missing sign-off, so the runner takes\n"
                                      "  the next task it can claim. And a sentence the PR adds after it.\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["missing"], [])
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_a_passage_split_across_two_hunks_is_not_found(self):
        scope = SCOPE.replace(SCOPE[SCOPE.index("    > A task"):SCOPE.index("  - the code")], "    > Alpha one. Beta two.\n")
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "the passage")
        git(self.p.root, "checkout", "-q", "main")
        self.change("docs/spec/x.md", "\nGamma.\n")  # on the base: unchanged on the branch
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")
        x = self.p.root / "docs/spec/x.md"
        x.write_text(x.read_text().replace("Gamma.\n", "Alpha one.\nGamma.\nBeta two.\n"))
        git(self.p.root, "commit", "-q", "-am", "two halves")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn("Alpha one. Beta two.", err)

    def test_an_added_line_beginning_plus_plus_is_content(self):
        self.change("docs/spec/x.md", "\n++ counter\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_a_changed_word_fails_naming_the_passage(self):
        self.change("docs/spec/x.md", "\n" + PASSAGE.replace("next task", "first task") + "\n")
        code, body, err = self.run_cmd("0001", "--base", "main")
        self.assertEqual(code, 1)
        lines = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text().splitlines()
        at = f"docs/delivery/tasks/0001-signed.md:{lines.index(SCOPE.splitlines()[3]) + 1}"  # the PROPOSED: line
        self.assertEqual(body["missing"], [at])
        self.assertIn(at, err)
        self.assertIn(PASSAGE, err)

    def test_a_task_with_no_proposed_block_exits_2(self):
        scope = "## Scope\n\n- **In:** the code, which reads each `PROPOSED:` block. PROPOSED: \"inline, unquoted\"\n"
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "no block")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 2)
        self.assertIn("no PROPOSED: block", err)

    def test_only_lines_the_branch_adds_to_a_spec_file_count(self):
        self.change("notes.md", "\n" + PASSAGE + "\n")  # not under task_log.spec_paths
        self.assertEqual(self.run_cmd("0001-signed", "--base", "main")[0], 1)
        git(self.p.root, "checkout", "-q", "main")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")  # on the base: the branch adds nothing
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")
        self.assertEqual(self.run_cmd("0001-signed", "--base", "main")[0], 1)

    def test_each_passage_is_judged_and_only_the_missing_one_named(self):
        second = ("\n  - `docs/spec/x.md` §1. CURRENT: \"An older rule.\" PROPOSED:\n"
                  "    > An older rule, now with a knob.\n")
        self.p.task("0001-signed", body=TASK.format(scope=SCOPE.replace("\n- **Out:**", second + "- **Out:**")))
        git(self.p.root, "commit", "-q", "-am", "two passages")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1)
        self.assertEqual(len(body["passages"]), 2)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn("An older rule, now with a knob.", err)
        self.assertNotIn(PASSAGE, err)

    def test_the_base_defaults_to_the_integration_branch_on_the_remote(self):
        origin = self.p.root.parent / (self.p.root.name + "-origin.git")
        git(self.p.root.parent, "init", "-q", "--bare", "-b", "main", str(origin))
        self.addCleanup(lambda: __import__("shutil").rmtree(origin, ignore_errors=True))
        git(self.p.root, "remote", "add", "origin", str(origin))
        git(self.p.root, "push", "-q", "origin", "main")
        git(self.p.root, "fetch", "-q", "origin")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed")
        self.assertEqual((code, body["base"]), (0, "origin/main"), err)

    def test_a_base_that_does_not_resolve_or_an_unknown_task_exits_2(self):
        code, _, err = self.run_cmd("0001-signed", "--base", "no-such-ref")
        self.assertEqual(code, 2)
        self.assertIn("no-such-ref", err)
        self.assertEqual(self.run_cmd("0099-none", "--base", "main")[0], 2)

    def test_the_passages_are_read_from_the_scope_only(self):
        text = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text()
        self.assertEqual([p for _, p in verify.signed_passages(text)], [PASSAGE])


class Prompts(ToolkitFixture, unittest.TestCase):
    """The review and verify prompts ask for the check only on a task that declares a `brief` sign-off."""

    def prompts(self) -> tuple[str, str]:
        self.ccp("tasks", "claim", "0002")
        for phase in ("review", "verify"):
            code, _, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", "a" * 40)
            self.assertEqual(code, 0, out + err)
        d = self.q / "prompts/0002-second"
        return (d / "review-prompt.md").read_text(), (d / "verify-prompt.md").read_text()

    def test_a_brief_task_s_review_and_verify_prompts_run_the_check(self):
        p = self.main / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("depends_on:", "sign_off: brief\ndepends_on:", 1))
        git(self.main, "commit", "-q", "-am", "0002 needs a brief sign-off")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, out, err = self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed")
        self.assertEqual(code, 0, out + err)
        for text in self.prompts():
            self.assertIn("verify spec-text 0002-second --base origin/main", text)

    def test_other_tasks_prompts_do_not(self):
        for text in self.prompts():
            self.assertNotIn("spec-text", text)


if __name__ == "__main__":
    unittest.main()
