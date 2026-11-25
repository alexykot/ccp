"""House rule E22, SPEC §7.2, §26.3: one fence-aware finder of a Markdown section under a heading, and the one
resolver of a SPEC ref that `ccp spec show` prints and the estimator quotes. A `#` line inside a fenced block
neither starts nor ends a section, in every reader."""
from __future__ import annotations

import contextlib
import io
import unittest

from ccp import adr, estimator, mdsection, report, spec, taskmigrate, tasklog
from tests.helpers import Product

FENCE = "```"
PREFIX = "S"
SPEC_TEXT = ("# Spec\n\n## 13. Workers\n\nintro\n\n### 13.1 One\n\nbody one\n\n### 13.2 Two\n\nbody two\n\n"
             "## 14. Next\n\nnext\n")


class Sections(unittest.TestCase):
    def test_a_heading_inside_a_fence_neither_starts_nor_ends_a_section(self):
        text = (f"# T\n\n{FENCE}\n## Target\nquoted\n{FENCE}\n\n## Target\n\nreal body\n\n{FENCE}\n## Other\n{FENCE}\n"
                "tail\n\n## After\n\nafter\n")
        block = mdsection.heading_block(text, "Target")
        self.assertTrue(block.startswith("## Target\n\nreal body"), block)
        self.assertIn("tail", block)
        self.assertNotIn("quoted", block)
        self.assertNotIn("after", block)
        self.assertIsNone(mdsection.heading_block(f"{FENCE}\n## Target\n{FENCE}\n", "Target"))

    def test_a_section_ends_at_a_heading_of_its_level_or_higher_only(self):
        text = "## A\n\na\n\n### A.1\n\nsub\n\n# Top\n\ntop\n"
        self.assertEqual(mdsection.heading_block(text, "A"), "## A\n\na\n\n### A.1\n\nsub\n\n")
        self.assertIsNone(mdsection.heading_block(text, "A$", level=3))
        self.assertEqual(mdsection.heading_block(text, r"A\.1", level=3), "### A.1\n\nsub\n\n")

    def test_a_ref_matches_a_heading_with_or_without_the_prefix(self):
        plain, prefixed = [SPEC_TEXT], [SPEC_TEXT.replace("## 13.", "## S13.").replace("### 13.", "### S13.")]
        for texts in (plain, prefixed):
            for ref in ("S13", "13", "§13"):
                block = spec.resolve(texts, ref, PREFIX)
                self.assertIn("body two", block)
                self.assertNotIn("next", block)
            one = spec.resolve(texts, "S13.1", PREFIX)
            self.assertIn("body one", one)
            self.assertNotIn("body two", one)
            self.assertIsNone(spec.resolve(texts, "S1", PREFIX))  # 13 is not 1 followed by `.`, a blank or the end
            self.assertIsNone(spec.resolve(texts, "S99", PREFIX))

    def test_the_first_spec_file_carrying_the_ref_wins(self):
        self.assertIn("mine", spec.resolve(["# a\n", "## 7 Seven\n\nmine\n", "## 7 Seven\n\ntheirs\n"], "S7", PREFIX))


class Callers(unittest.TestCase):
    def test_report_follow_ups_read_past_a_fenced_heading(self):
        quoted = f"{FENCE}\n## Follow-ups\n\n- quoted\n{FENCE}\n"
        text = f"Outcome: done\n\n{quoted}\n## Follow-ups\n\n- first\n- second\n\n## Friction\n\nnone\n"
        self.assertEqual(report.follow_ups(text), (["first", "second"], None))
        self.assertEqual(report.follow_ups(quoted), ([], None))

    def test_report_friction_reads_past_a_fenced_heading(self):
        text = f"{FENCE}\n## Friction\n\n- quoted\n{FENCE}\n\n## Friction\n\n- one\n- two\n\n## Follow-ups\n\nnone\n"
        self.assertEqual(report.friction(text), ["one", "two"])

    def test_an_adr_decision_block_reads_past_a_fenced_heading(self):
        text = (f"# ADR\n\n## Decision\n\n{FENCE}\n### D1. Quoted\n{FENCE}\n\n### D1. First\n\nbody one\n\n"
                f"{FENCE}\n## Not a heading\n{FENCE}\n\nstill one\n\n### D2. Second\n\nbody two\n")
        block = adr.decision_block(text, "1")
        self.assertTrue(block.startswith("### D1. First"), block)
        self.assertIn("still one", block)
        self.assertNotIn("body two", block)

    def test_the_estimator_quotes_a_spec_section_cited_with_the_prefix(self):
        p = Product({"spec_paths": ["docs/SPEC.md"]})
        self.addCleanup(p.cleanup)
        p.write("docs/SPEC.md", SPEC_TEXT)
        out = estimator.spec_excerpts(p.cfg, ["S13", "S14", "S99"])
        self.assertIn("body two", out)
        self.assertIn("next", out)
        self.assertIn("### S99: no SPEC heading found", out)

    def test_a_task_files_section_ends_at_a_heading_of_level_two_or_higher_outside_a_fence(self):
        text = f"## Scope\n\nin\n\n{FENCE}\n# quoted\n{FENCE}\n\n### sub\n\nkept\n\n# Top\n\nout\n"
        self.assertEqual(tasklog.section(text, tasklog.SEC_SCOPE), f"\n\nin\n\n{FENCE}\n# quoted\n{FENCE}\n\n### sub\n\nkept\n\n")

    def test_a_task_migration_table_reads_past_a_fenced_heading(self):
        text = f"## Meta\n\n| k | v |\n|---|---|\n| a | 1 |\n\n{FENCE}\n## x\n{FENCE}\n\n| b | 2 |\n\n## Refs\n\n| c | 3 |\n"
        self.assertEqual(taskmigrate.table(text, "meta"), [("a", "1"), ("b", "2")])
        self.assertIsNone(taskmigrate.heading(f"{FENCE}\n## Meta\n{FENCE}\n", "Meta"))


class Show(unittest.TestCase):
    def show(self, refs: list[str]) -> tuple[int, str, str]:
        p = Product({"spec_paths": ["docs/SPEC.md"]})
        self.addCleanup(p.cleanup)
        p.write("docs/SPEC.md", SPEC_TEXT)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = spec.show(p.cfg, refs)
        return code, out.getvalue(), err.getvalue()

    def test_each_ref_prints_its_section_in_the_order_given(self):
        code, out, err = self.show(["S14", "13.1"])
        self.assertEqual((code, err), (0, ""))
        self.assertLess(out.index("## 14."), out.index("### 13.1"))
        self.assertNotIn("body two", out)

    def test_an_unresolved_ref_is_named_on_stderr_and_exits_1(self):
        code, out, err = self.show(["S99", "S14"])
        self.assertEqual(code, 1)
        self.assertIn("`S99`", err)
        self.assertIn("## 14.", out)


if __name__ == "__main__":
    unittest.main()
