"""`ccp tasks check` warns, before the gate, about an ADR decision a task not yet done cites that the
checkout still records `not_built` (SPEC §6.7, §15.4): a warning, never a refusal, and only for the task
whose branch, `task/<id>`, is checked out."""
from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import adr, cli, tasklog
from tests.helpers import TASK, Product

ADR_BODY = "# ADR-0001 — T\n\n## Decision\n\n### D1. First\n\nOne.\n\n### D2. Second\n\nTwo.\n"


def on_branch(p: Product, branch: str) -> None:
    """Make the scratch product a git checkout whose HEAD is `branch`."""
    subprocess.run(["git", "init", "-q", "-b", branch, str(p.root)], check=True, capture_output=True)


class UnbuiltDecisionWarning(unittest.TestCase):
    strict = True

    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr", "strict": self.strict}})
        self.addCleanup(self.p.cleanup)
        on_branch(self.p, "task/0001-a")

    def adr(self, d1: str) -> None:
        self.p.write("docs/adr/0001-a.md", adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted",
                                                      "date": "2026-01-01", "decisions": [f"D1 {d1}", "D2 built"]})
                     + ADR_BODY)

    def task(self, tid: str, refs: list[str], status: str = "pending") -> None:
        ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
        text = TASK.format(tid=tid, title="A task", status=status, deps="", ver=ver)
        text = text.replace('spec_refs: ["S1"]\n',
                            'spec_refs: ["S1"]\nadr_refs: [' + ", ".join(f'"{r}"' for r in refs) + "]\n")
        self.p.write(f"docs/delivery/tasks/{tid}.md", text)

    def check(self) -> tuple[int, list[str]]:
        self.p.index()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        return code, [x for x in (out.getvalue() + err.getvalue()).splitlines() if "not_built" in x]

    def test_a_pending_task_citing_a_not_built_decision_is_warned_once_and_check_passes(self):
        self.adr("not_built")
        self.task("0001-a", ["0001 D1"])
        code, lines = self.check()
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("warning:", lines[0])
        self.assertIn("0001-a", lines[0])
        self.assertIn("0001 D1", lines[0])
        self.assertIn("adr decide 1 D1 built", lines[0])

    def test_no_warning_once_the_decision_is_built(self):
        self.adr("built")
        self.task("0001-a", ["0001 D1"])
        code, lines = self.check()
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines, [])

    def test_only_the_not_built_decision_is_named(self):
        self.adr("not_built")
        self.task("0001-a", ["ADR-0001 D2", "ADR-0001 D1"])
        warns = [w for w in tasklog.warnings(self.p.cfg) if "not_built" in w]
        self.assertEqual(len(warns), 1, warns)
        self.assertIn("ADR-0001 D1", warns[0])
        self.assertNotIn("D2", warns[0])

    def test_a_decision_recorded_but_not_in_the_body_is_not_warned(self):
        self.p.write("docs/adr/0001-a.md", adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted",
                                                      "date": "2026-01-01", "decisions": ["D1 built", "D9 not_built"]})
                     + ADR_BODY)
        self.task("0001-a", ["0001 D9"])
        self.assertEqual([w for w in tasklog.warnings(self.p.cfg) if "not_built" in w], [])
        self.assertEqual(adr.unbuilt_cited(self.p.cfg, tasklog.load(self.p.cfg)), [])

    def test_a_done_or_dropped_task_is_not_warned_here(self):
        self.adr("not_built")
        self.task("0001-a", ["0001 D1"], status="dropped")
        self.assertEqual(adr.unbuilt_cited(self.p.cfg, tasklog.load(self.p.cfg)), [])

    def test_a_pending_task_is_not_warned_on_the_integration_branch(self):
        subprocess.run(["git", "-C", str(self.p.root), "symbolic-ref", "HEAD", "refs/heads/main"], check=True)
        self.adr("not_built")
        self.task("0001-a", ["0001 D1"])
        code, lines = self.check()
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines, [])

    def test_on_a_task_branch_another_pending_task_is_not_warned(self):
        self.adr("not_built")
        self.task("0001-a", ["0001 D1"])
        self.task("0002-b", ["0001 D1"])
        code, lines = self.check()
        self.assertEqual(code, 0, lines)
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("0001-a", lines[0])
        self.assertNotIn("0002-b", lines[0])

    def test_without_the_adr_block_nothing_is_read(self):
        p = Product()
        self.addCleanup(p.cleanup)
        on_branch(p, "task/0001-a")
        p.write("docs/adr/0001-a.md", adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted",
                                                "date": "2026-01-01", "decisions": ["D1 not_built"]}) + ADR_BODY)
        text = TASK.format(tid="0001-a", title="A task", status="pending", deps="", ver="*Append-only.*")
        p.write("docs/delivery/tasks/0001-a.md", text.replace('spec_refs: ["S1"]\n',
                                                              'spec_refs: ["S1"]\nadr_refs: ["0001 D1"]\n'))
        self.assertEqual([w for w in tasklog.warnings(p.cfg) if "not_built" in w], [])


class UnbuiltDecisionWarningNotStrict(UnbuiltDecisionWarning):
    strict = False


if __name__ == "__main__":
    unittest.main()
