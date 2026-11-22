"""SPEC §3.5, §15.2: `ccp tasks check` warns on a task not yet done or dropped whose Scope, or a section whose
heading begins `Rule changes`, holds a `PROPOSED:` line with no `> ` blockquote under it, the shape `ccp verify
spec-text` carries no passage from; a `PROPOSED:` in a code span or a fenced block is quoted, not read."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli, tasklog
from tests.helpers import TASK, Product

INLINE = '- `docs/spec/x.md` §1: CURRENT: "older words". PROPOSED: "newer words".'
QUOTED = "- `docs/spec/x.md` §1. PROPOSED:\n  > newer words, with `a token` in them\n  > `only a span`"


def task_text(tid: str, scope: str, status: str = "pending", after: str = "") -> str:
    ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
    body = TASK.format(tid=tid, title="A task", status=status, deps="", ver=ver)
    body = body.replace("- **In:** it\n", scope + "\n", 1)
    return body.replace("## Implementation notes", after + "## Implementation notes", 1) if after else body


def line_of(text: str, needle: str) -> int:
    return text.split("\n").index(needle) + 1


class UnreadableProposed(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def task(self, tid: str, scope: str, status: str = "pending", after: str = "") -> str:
        text = task_text(tid, scope, status, after)
        self.p.write(f"docs/delivery/tasks/{tid}.md", text)
        return text

    def warns(self) -> list[str]:
        return [w for w in tasklog.warnings(self.p.cfg) if "PROPOSED:" in w]

    def test_an_inline_proposed_in_scope_warns_naming_the_file_and_line(self):
        text = self.task("0001-inline", INLINE)
        warned = self.warns()
        self.assertEqual(len(warned), 1, warned)
        self.assertTrue(warned[0].startswith(f"docs/delivery/tasks/0001-inline.md:{line_of(text, INLINE)}: "), warned)

    def test_a_proposed_followed_by_blockquote_lines_does_not_warn(self):
        self.task("0001-quoted", QUOTED)
        self.task("0002-flush", "PROPOSED:\n> newer words")
        self.assertEqual(self.warns(), [])

    def test_a_proposed_in_a_rule_changes_section_warns_the_same(self):
        rule = 'The §2 sentence. PROPOSED: "newer words".'
        text = self.task("0001-rules", "- **In:** it", after=f"## Rule changes (signed)\n\n{rule}\n\n")
        self.task("0002-rules-quoted", "- **In:** it", after="## Rule changes\n\nPROPOSED:\n> newer words\n\n")
        warned = self.warns()
        self.assertEqual(len(warned), 1, warned)
        self.assertTrue(warned[0].startswith(f"docs/delivery/tasks/0001-rules.md:{line_of(text, rule)}: "), warned)

    def test_a_proposed_in_a_code_span_or_a_fenced_block_does_not_warn(self):
        self.task("0001-span", "- it reads each `PROPOSED:` line of the Scope")
        self.task("0002-fence", "- the shape:\n\n  ```\n  PROPOSED: \"newer words\"\n  ```\n")
        self.assertEqual(self.warns(), [])

    def test_a_proposed_outside_the_scope_and_rule_changes_does_not_warn(self):
        self.task("0001-elsewhere", "- **In:** it", after='## Notes\n\nPROPOSED: "newer words".\n\n')
        self.assertEqual(self.warns(), [])

    def test_a_done_or_dropped_task_does_not_warn(self):
        self.task("0001-done", INLINE, status="done")
        self.task("0002-dropped", INLINE, status="dropped")
        self.assertEqual(self.warns(), [])

    def test_tasks_check_warns_and_exits_0(self):
        self.task("0001-inline", INLINE)
        self.p.index()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        printed = out.getvalue() + err.getvalue()
        self.assertEqual(code, 0, printed)
        self.assertEqual(len([x for x in printed.splitlines() if "0001-inline.md:" in x and "PROPOSED:" in x]), 1,
                         printed)


if __name__ == "__main__":
    unittest.main()
