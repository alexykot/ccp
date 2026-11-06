"""ADR decision lookup: every style ADRs write decisions in, and the ADR file finder."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ccp import adr, architect

HEADING = "# ADR-0001 — H\n\n## Decision\n\n### D1. First\n\nbody one\n\n### D2. Second\n\nbody two\n\n## Consequences\n\nc\n"
BULLET = ("# ADR-0002 — B\n\n## Decision\n\n- **D1. First.** body one\n  continued\n- **D2. Second.** body two\n"
          "- **D2a. Variant.** body two-a\n\n## Consequences\n\nc\n")
BOLD = "# ADR-0003 — P\n\n## Decision\n\n**D1 — First**\n\nbody one\n\n**D2 — Second**\n\nbody two\n"
PARA = "# ADR-0004 — Q\n\n## Decision\n\nD1. **First.** body one\n\nD2. **Second.** body two\n"


class DecisionBlock(unittest.TestCase):
    def check(self, text: str) -> None:
        one = adr.decision_block(text, "1")
        self.assertIsNotNone(one)
        self.assertIn("body one", one)
        self.assertNotIn("body two", one)
        self.assertIn("body two", adr.decision_block(text, "2"))
        self.assertIsNone(adr.decision_block(text, "9"))

    def test_heading_style(self):
        self.check(HEADING)
        self.assertNotIn("Consequences", adr.decision_block(HEADING, "2"))

    def test_bullet_style(self):
        self.check(BULLET)
        self.assertIn("continued", adr.decision_block(BULLET, "1"))
        self.assertNotIn("two-a", adr.decision_block(BULLET, "2"))     # D2 is not D2a
        self.assertIn("two-a", adr.decision_block(BULLET, "2a"))

    def test_bold_lead_style(self):
        self.check(BOLD)

    def test_paragraph_style(self):
        self.check(PARA)

    def test_titles_cover_every_style(self):
        self.assertEqual(adr.decision_titles(HEADING), ["D1. First", "D2. Second"])
        self.assertEqual(adr.decision_titles(BULLET)[:2], ["D1. First. body one", "D2. Second. body two"])
        self.assertEqual(len(adr.decision_titles(BOLD)), 2)
        self.assertEqual(len(adr.decision_titles(PARA)), 2)

    def test_a_bracketed_note_after_the_id(self):
        text = "## Decision\n\n- **D5 (F01). Edges.** body five\n- **D6 (F02). Path.** body six\n"
        self.assertIn("body five", adr.decision_block(text, "5"))
        self.assertNotIn("body six", adr.decision_block(text, "5"))

    def test_wrapped_prose_starting_with_an_id_and_bracket_is_not_a_decision(self):
        text = "## Decision\n\n- **D1. A.** see the count (\nD3) and more\n- **D2. B.** two\n"
        self.assertIn("and more", adr.decision_block(text, "1"))
        self.assertIsNone(adr.decision_block(text, "3"))

    def test_titles_list_each_id_once(self):
        text = BULLET + "\n## Implementation notes\n\n- **D1.** notes for one\n"
        self.assertEqual([x.split(".")[0] for x in adr.decision_titles(text)], ["D1", "D2", "D2a"])

    def test_a_comment_in_a_code_fence_does_not_end_the_decision(self):
        text = "## Decision\n\n- **D1. A.** run:\n  ```sh\n# step\n  make it\n  ```\n  after\n- **D2. B.** two\n"
        block = adr.decision_block(text, "1")
        self.assertIn("after", block)
        self.assertNotIn("two", block)

    def test_prose_mentioning_a_decision_is_not_one(self):
        self.assertIsNone(adr.decision_block("# ADR\n\nD1 is built; see D2 later.\n", "1"))


class FindFile(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def cfg(self, adr_dir=None):
        root = self.root
        return SimpleNamespace(root=root, adr={"dir": adr_dir} if adr_dir else None,
                               rel=lambda p: str(Path(p).relative_to(root)))

    def write(self, rel: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# ADR\n")

    def test_the_configured_dir_and_its_archive_win(self):
        self.write("decisions/0007-x.md")
        self.write("decisions/archive/0008-y.md")
        self.write("other/adr/0007-z.md")
        cfg = self.cfg("decisions")
        self.assertEqual(adr.find_file(cfg, 7), self.root / "decisions/0007-x.md")
        self.assertEqual(adr.find_file(cfg, 8), self.root / "decisions/archive/0008-y.md")
        self.assertEqual(architect._adr_path(cfg, "ADR-0007"), "decisions/0007-x.md")

    def test_top_level_beats_the_archive_whatever_the_name(self):
        self.write("docs/adr/archive/0001-old.md")
        self.write("docs/adr/ADR-0001-new.md")
        self.assertEqual(adr.find_file(self.cfg(), 1), self.root / "docs/adr/ADR-0001-new.md")

    def test_falls_back_to_any_adr_dir(self):
        self.write("docs/adr/0003-a.md")
        self.assertEqual(adr.find_file(self.cfg(), 3), self.root / "docs/adr/0003-a.md")
        self.assertIsNone(adr.find_file(self.cfg(), 4))


if __name__ == "__main__":
    unittest.main()
