"""A `--mutant-file` (SPEC §20.6) whose old text matches nothing only because it ends with the line break before
`=== new` is refused with a message naming that line break; any other zero match keeps the plain refusal."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from ccp import mutate
from ccp.queue import QueueError

RULED = ("mutant file 'm.txt': the old text is in calc.py 0 times: it ends with the line break before === new, and "
         "without it it is in calc.py 1 times; end the old text at a line end")


class LineBreak(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ccp-mutant-line-break-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "calc.py").write_text("x = 1\ny = 2\n")

    def mfile(self, old: str, name: str = "m.txt") -> str:
        (self.root / name).write_text(f"calc.py\n=== old\n{old}\n=== new\nz = 3\n")
        return name

    def refusal(self, old: str) -> str:
        self.mfile(old)
        with self.assertRaises(QueueError) as cm:
            mutate.parse_file(self.root, "m.txt", self.root)
        self.assertEqual(cm.exception.code, 2)
        return str(cm.exception)

    def test_an_old_text_ending_mid_line_is_refused_naming_the_line_break(self):
        self.assertEqual(self.refusal("x = "), RULED)

    def test_with_crlf_line_ends_the_same_refusal_names_the_line_break(self):
        (self.root / "calc.py").write_bytes(b"x = 1\r\ny = 2\r\n")
        (self.root / "m.txt").write_bytes(b"calc.py\r\n=== old\r\nx = \r\n=== new\r\nz = 3\r\n")
        with self.assertRaises(QueueError) as cm:
            mutate.parse_file(self.root, "m.txt", self.root)
        self.assertEqual(str(cm.exception), RULED)

    def test_a_whole_line_old_text_that_matches_nothing_keeps_the_plain_refusal(self):
        msg = self.refusal("w = 9")
        self.assertIn("0 times; a mutant names one place", msg)
        self.assertNotIn("line break", msg)

    def test_a_together_part_from_a_mutant_file_gets_the_same_refusal(self):
        parts = [mutate.parse_file(self.root, self.mfile(old, f"m{i}.txt"), self.root, False)
                 for i, old in enumerate(("x = ", "y = 2"))]
        with self.assertRaises(QueueError) as cm:
            mutate.together(parts, {"calc.py": (self.root / "calc.py").read_bytes()})
        self.assertIn("ends with the line break before", str(cm.exception))

    def test_a_mutant_substitution_keeps_the_plain_refusal(self):
        with self.assertRaises(QueueError) as cm:
            mutate.parse(self.root, "calc.py:x = \n=>z", self.root)
        self.assertIn("0 times; a mutant names one place", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
