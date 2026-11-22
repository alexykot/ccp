"""A `--mutant-file` (SPEC §20.6) whose old text matches nothing only because it ends with the line break before
`=== new` is refused with a message naming that line break; any other zero match keeps the plain refusal."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from ccp import mutate
from ccp.queue import QueueError


class LineBreak(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ccp-mutant-line-break-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "calc.py").write_text("x = 1\ny = 2\n")

    def refusal(self, old: str) -> str:
        (self.root / "m.txt").write_text(f"calc.py\n=== old\n{old}\n=== new\nz = 3\n")
        with self.assertRaises(QueueError) as cm:
            mutate.parse_file(self.root, "m.txt", self.root)
        self.assertEqual(cm.exception.code, 2)
        return str(cm.exception)

    def test_an_old_text_ending_mid_line_is_refused_naming_the_line_break(self):
        msg = self.refusal("x = ")
        self.assertIn("ends with the line break before", msg)
        self.assertIn("1 times", msg)

    def test_a_whole_line_old_text_that_matches_nothing_keeps_the_plain_refusal(self):
        msg = self.refusal("w = 9")
        self.assertIn("0 times; a mutant names one place", msg)
        self.assertNotIn("line break", msg)


if __name__ == "__main__":
    unittest.main()
