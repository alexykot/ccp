"""A worker prompt names what the task cites (SPEC §13.2): each review finding beside the record that holds its
evidence (`<review_id>.md` in the reviews directory, §19.2), the other refs as they are written."""
from __future__ import annotations

import unittest
from pathlib import Path

from ccp import config
from ccp import prompt as prompt_mod
from tests.helpers import Product
from tests.toolkit_fixture import ToolkitFixture

RECORD = "ar-20261001T120000Z-0f3c"
FINDING = f"{RECORD}#F02"


def record_path(cfg: config.Config, review_id: str) -> str:
    return f"{cfg.rel(cfg.reviews_dir)}/{review_id}.md"


class CitedRefs(unittest.TestCase):
    """The `refs` value on plain task metadata."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)

    def test_a_review_ref_names_its_record_and_the_other_refs_stay_bare(self):
        cfg = self.p.cfg
        meta = {"spec_refs": ["S10"], "adr_refs": ["0031 D1"], "rule_refs": "E4",
                "review_refs": [FINDING, "sh-20261002T080000Z-1a2b"]}
        self.assertEqual(prompt_mod.cited_refs(cfg, meta).split(", "),
                         ["S10", "0031 D1", "E4", f"{FINDING} ({record_path(cfg, RECORD)})",
                          f"sh-20261002T080000Z-1a2b ({record_path(cfg, 'sh-20261002T080000Z-1a2b')})"])

    def test_the_record_is_in_the_products_own_reviews_directory(self):
        p = Product({"task_log": {"reviews_dir": "findings"}})
        self.addCleanup(p.cleanup)
        cfg = p.cfg
        self.assertNotEqual(cfg.rel(cfg.reviews_dir), self.p.cfg.rel(self.p.cfg.reviews_dir))
        self.assertEqual(prompt_mod.cited_refs(cfg, {"review_refs": [FINDING]}),
                         f"{FINDING} ({record_path(cfg, RECORD)})")

    def test_a_task_citing_nothing_reads_none(self):
        self.assertEqual(prompt_mod.cited_refs(self.p.cfg, {}), "none")


class ImplementPromptRefs(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        task = self.runner / "docs/delivery/tasks/0002-second.md"
        text = task.read_text()
        self.assertIn('spec_refs: ["S1"]\n', text)
        task.write_text(text.replace('spec_refs: ["S1"]\n', f'spec_refs: ["S10"]\nreview_refs: ["{FINDING}"]\n'))
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_the_implement_prompt_names_the_record_of_each_cited_finding(self):
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(f"S10, {FINDING} ({record_path(config.load(self.runner), RECORD)})", text)


if __name__ == "__main__":
    unittest.main()
