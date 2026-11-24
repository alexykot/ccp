"""SPEC §5, §10, §26: every reader of a task file's sections finds a heading only outside a fenced block. Close
writes its merge record under the real Verification notes heading, the estimator's task text (what `task_hash`
hashes) leaves out only the real notes sections, and a line that starts with a three-backtick code span is prose,
no fence opener (a backtick fence's info string holds no backtick)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccp import estimate, lifecycle, tasklog
from tests.helpers import TASK

FENCE = "```"
VERIFY = f"## {tasklog.SEC_VERIFY}"
IMPL = f"## {tasklog.SEC_IMPL}"


class SectionReadersFences(unittest.TestCase):
    def test_close_writes_its_note_under_the_real_verification_notes_heading(self):
        fenced = f"{FENCE}\n{VERIFY}\n{FENCE}\n"
        text = (f"---\ntask_id: 0001-x\nstatus: pending\nupdated: 2026-01-01\n---\n\n## Scope\n\n{fenced}\n"
                f"Scope tail.\n\n{VERIFY}\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "0001-x.md"
            p.write_text(text)
            lifecycle._task_file_done(p, "- NOTE", "2026-02-02")
            out = p.read_text()
        self.assertEqual(out.count("- NOTE"), 1)
        self.assertIn("- NOTE", out.rsplit(VERIFY, 1)[1])
        self.assertIn(f"## Scope\n\n{fenced}\nScope tail.\n\n{VERIFY}\n", out)

    def test_close_ends_the_verification_notes_at_the_next_unfenced_heading(self):
        notes = f"{VERIFY}\n\nFirst note.\n\n{FENCE}\n## X\n{FENCE}\n"
        text = f"---\ntask_id: 0001-x\nstatus: pending\nupdated: 2026-01-01\n---\n\n{notes}\n## Later\n\nlater\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "0001-x.md"
            p.write_text(text)
            lifecycle._task_file_done(p, "- NOTE", "2026-02-02")
            out = p.read_text()
        self.assertTrue(out.endswith(f"\n{notes}- NOTE\n\n## Later\n\nlater\n"), out)

    def test_the_estimators_text_keeps_a_fenced_notes_heading_and_drops_the_real_notes(self):
        kept = f"## Scope\n\n{FENCE}\n{IMPL}\n{FENCE}\n\nScope tail.\n\n## dod_checks\n\n- id: x\n\n"
        self.assertEqual(estimate.strip_notes(f"{kept}{IMPL}\n\nIMPL\n\n{VERIFY}\n\nVER\n"), kept)
        task = TASK.format(tid="0001-x", title="A task", status="pending", deps="", ver="*Append-only.*")
        task = task.replace("- **In:** it\n", f"- **In:** it\n\n{FENCE}\n{IMPL}\n{FENCE}\n", 1)
        real = task.rindex(IMPL) + len(IMPL)  # the real heading, after the fenced one
        noted = task[:real] + "\n\n- built it" + task[real:]
        self.assertEqual(estimate.task_hash(noted), estimate.task_hash(task))
        self.assertNotEqual(estimate.task_hash(task.replace(f"{FENCE}\n{IMPL}\n{FENCE}", f"{FENCE}\n## Other\n{FENCE}")),
                            estimate.task_hash(task))

    def test_the_estimators_text_ends_a_real_notes_section_at_the_next_unfenced_heading(self):
        kept = "## Scope\n\ns\n\n"
        rest = "## dod_checks\n\nd\n"
        notes = f"{IMPL}\n\n{FENCE}\n## X\n{FENCE}\nTAIL\n\n"
        self.assertEqual(estimate.strip_notes(kept + notes + rest), kept + rest)

    def test_a_backtick_fences_info_string_holds_no_backtick(self):
        span = (f"## Scope\n\n{FENCE}x{FENCE} is a span.\n\n## dod_checks\n\nc\n\n{IMPL}\n\n{FENCE}\nn\n{FENCE}\n")
        self.assertEqual(tasklog.section(span, "dod_checks"), "\n\nc\n\n")
        tilde = "## Scope\n\n~~~ a`b\n## dod_checks\n~~~\n"
        self.assertIsNone(tasklog.section(tilde, "dod_checks"))
        info = f"## Scope\n\n{FENCE}py\n## dod_checks\n{FENCE}\n"
        self.assertIsNone(tasklog.section(info, "dod_checks"))

    def test_every_reader_finds_a_heading_line_ending_in_cr(self):
        task = TASK.format(tid="0001-x", title="A task", status="pending", deps="", ver="*Append-only.*")
        real = task.rindex(IMPL) + len(IMPL)
        crlf = (task[:real] + "\n\n- built it" + task[real:]).replace("\n", "\r\n")
        self.assertEqual(tasklog.section(crlf, tasklog.SEC_CHECKS),
                         tasklog.section(task, tasklog.SEC_CHECKS).replace("\n", "\r\n"))
        stripped = estimate.strip_notes(crlf)
        self.assertNotIn(IMPL, stripped)
        self.assertNotIn("- built it", stripped)
        self.assertIn(f"## {tasklog.SEC_CHECKS}", stripped)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "0001-x.md"
            p.write_bytes(crlf.encode())
            lifecycle._task_file_done(p, "- NOTE", "2026-02-02")
            out = p.read_bytes().decode()
        self.assertIn("- NOTE", out.rsplit(VERIFY, 1)[1])


if __name__ == "__main__":
    unittest.main()
