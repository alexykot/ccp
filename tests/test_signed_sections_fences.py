"""SPEC §3.5, §15.2: a task file's sections end only at real headings. A `## ` line inside a fenced block is
quoted text: it neither ends the Scope, so a signed passage after it is one `ccp verify spec-text` looks for, nor
opens a `Rule changes` section; a `PROPOSED:` inside a fence or a code span carries no passage; and a dod_check
whose steps quote a `## ` line keeps the checks after it."""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, tasklog
from tests.helpers import GIT_ENV, TASK, Product
from tests.git_helpers import git

FENCE = "```"
PASSAGE = "A signed sentence the build must add."
BLOCK = f"CURRENT (`docs/spec/x.md` at `abc1234`): none.\nPROPOSED:\n> {PASSAGE}"


def task_text(scope: str, checks: str | None = None, tid: str = "0001-fenced") -> str:
    """A pending task whose Scope is `scope` and, when given, whose dod_checks section is `checks`."""
    text = TASK.format(tid=tid, title="A task", status="pending", deps="", ver="*Append-only.*")
    text = text.replace("- **In:** it\n", scope + "\n", 1)
    if checks is not None:
        head = text.index("## dod_checks\n") + len("## dod_checks\n")
        text = text[:head] + "\n" + checks + "\n" + text[text.index("## Implementation notes"):]
    return text


def line_of(text: str, needle: str) -> int:
    return text.split("\n").index(needle) + 1


def fenced(*lines: str) -> str:
    return "\n".join([FENCE, *lines, FENCE])


class SignedSections(unittest.TestCase):
    def test_a_scope_holding_a_fenced_heading_line_keeps_the_passage_after_it(self):
        text = task_text(f"- an example:\n\n{fenced('## Not a heading')}\n\n{BLOCK}")
        self.assertEqual(tasklog.signed_blocks(text), [(line_of(text, f"> {PASSAGE}") - 1, PASSAGE, "docs/spec/x.md")])

    def test_a_fenced_rule_changes_line_in_dod_checks_opens_no_signed_section(self):
        checks = "- id: `cmd-01`\n  steps:\n" + fenced("## Rule changes", "PROPOSED:", "> fenced passage")
        self.assertEqual(tasklog.signed_blocks(task_text("- **In:** it", checks)), [])

    def test_a_passage_after_a_fenced_rule_changes_line_outside_the_signed_sections_is_not_read(self):
        checks = "- id: `cmd-01`\n  steps:\n" + fenced("## Rule changes") + f"\n\n{BLOCK}"
        self.assertEqual(tasklog.signed_blocks(task_text("- **In:** it", checks)), [])

    def test_a_proposed_in_a_fence_or_a_code_span_carries_no_passage(self):
        text = task_text(f"{fenced('PROPOSED:', '> fenced passage')}\n- the `PROPOSED:`\n> spanned passage")
        self.assertEqual(tasklog.signed_blocks(text), [])

    def test_a_fenced_scope_heading_is_not_the_scope(self):
        text = task_text(BLOCK).replace("- background\n", fenced("## Scope", "PROPOSED:", "> fenced passage") + "\n", 1)
        self.assertEqual([p for _, p, _ in tasklog.signed_blocks(text)], [PASSAGE])

    def test_a_rule_changes_section_holding_a_fenced_heading_line_keeps_the_passage_after_it(self):
        text = task_text("- **In:** it").replace(
            "## Implementation notes", f"## Rule changes\n\n{fenced('## Example')}\n\n{BLOCK}\n\n## Implementation notes", 1)
        self.assertEqual([p for _, p, _ in tasklog.signed_blocks(text)], [PASSAGE])

    def test_dod_checks_quoting_a_fenced_heading_line_keep_every_check_after_it(self):
        checks = ("- id: `cmd-01`\n  steps:\n" + fenced("## Example") + "\n  expect: exit 0\n\n"
                  "- id: `cmd-02`\n  steps:\n    1. run\n  expect: exit 0\n")
        self.assertEqual([c.id for c in tasklog.checks(task_text("- **In:** it", checks))], ["cmd-01", "cmd-02"])


class SpecTextAfterAFence(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("QUEUE_ROOT", None)
        self.text = task_text(f"- an example:\n\n{fenced('## Not a heading')}\n\n{BLOCK}")
        self.file = self.p.task("0001-fenced", body=self.text)
        self.p.write("docs/spec/x.md", "# Spec\n\n## 1. Rules\n\nAn older rule.\n")
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", ".")
        git(self.p.root, "commit", "-q", "-m", "init")
        git(self.p.root, "checkout", "-q", "-b", "task/0001-fenced")
        spec = self.p.root / "docs/spec/x.md"
        spec.write_text(spec.read_text() + "\nOther text the build wrote instead.\n")
        git(self.p.root, "commit", "-q", "-am", "change the spec")

    def test_spec_text_fails_a_build_that_leaves_out_the_passage_signed_after_the_fence(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "spec-text", "0001-fenced", "--base", "main"])
        self.assertEqual(code, 1, err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["missing"],
                         [f"{self.p.cfg.rel(self.file)}:{line_of(self.text, f'> {PASSAGE}') - 1}"])


if __name__ == "__main__":
    unittest.main()
