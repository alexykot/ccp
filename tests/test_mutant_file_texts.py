"""A `--mutant-file`'s texts (SPEC §20.6): each is what lies between its marker line and the next, less the one line
break that ends it, read and applied on plain files in a temp directory."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from ccp import mutate
from ccp.queue import QueueError

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n"
TWO_LINES_OLD = "def add(a, b):\n    return a + b"
TWO_LINES_NEW = "def add(a, b):\n    return b - a"


class MutantFileTexts(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ccp-mutant-file-texts-")).resolve()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.calc = self.root / "calc.py"
        self.calc.write_text(CALC)

    def mfile(self, body: str, name: str = "m.txt") -> str:
        (self.root / name).write_bytes(body.encode())
        return name

    def applied(self, name: str) -> bytes:
        """The target file as the mutant in `name` leaves it."""
        mutate._apply(self.root, mutate.parse_file(self.root, name, self.root))
        return self.calc.read_bytes()

    def test_an_old_text_ending_mid_line_is_found_and_substituted(self):
        self.calc.write_text("x = 1\ny = 2\n")
        self.assertEqual(self.applied(self.mfile("calc.py\n=== old\nx = \n=== new\nz = \n")), b"z = 1\ny = 2\n")
        self.calc.write_text("total = a + b  # the sum\n")
        self.assertEqual(self.applied(self.mfile("calc.py\n=== old\na + b\n=== new\na - b\n")),
                         b"total = a - b  # the sum\n")  # a trailing comment stays where it was

    def test_a_whole_line_mutant_written_as_before_gives_the_same_file(self):
        for old, new in (("    return a + b\n", "    return a - b\n"), (TWO_LINES_OLD + "\n", TWO_LINES_NEW + "\n")):
            self.calc.write_text(CALC)
            self.assertEqual(self.applied(self.mfile(f"calc.py\n=== old\n{old}=== new\n{new}")),
                             CALC.replace(old, new).encode(), old)

    def test_a_whole_line_deletion_written_as_before_leaves_an_empty_line(self):
        self.calc.write_text("x = 1\ny = 2\n")
        self.assertEqual(self.applied(self.mfile("calc.py\n=== old\nx = 1\n=== new\n")), b"\ny = 2\n")

    def test_an_empty_line_before_the_next_marker_keeps_the_old_text_s_line_break(self):
        self.calc.write_text("x = 1\ny = 2\n")
        m = mutate.parse_file(self.root, self.mfile("calc.py\n=== old\nx = 1\n\n=== new\n"), self.root)
        self.assertEqual((m["old"], m["new"]), (b"x = 1\n", b""))
        self.assertEqual(self.applied("m.txt"), b"y = 2\n")
        self.calc.write_text("x = 1\ny = 2\n")
        self.assertEqual(self.applied(self.mfile("calc.py\n=== old\nx = 1\n\n=== new\nw = 0\n\n")), b"w = 0\ny = 2\n")

    def test_an_old_text_that_starts_another_line_is_ambiguous_until_it_keeps_its_line_break(self):
        self.calc.write_text("x = 1\nx = 10\n")
        with self.assertRaises(QueueError) as cm:
            mutate.parse_file(self.root, self.mfile("calc.py\n=== old\nx = 1\n=== new\nx = 2\n"), self.root)
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("2 times", str(cm.exception))
        self.assertEqual(self.applied(self.mfile("calc.py\n=== old\nx = 1\n\n=== new\nx = 2\n\n")), b"x = 2\nx = 10\n")

    def test_crlf_files_behave_the_same(self):
        self.calc.write_bytes(b"x = 1\r\ny = 2\r\n")
        self.assertEqual(self.applied(self.mfile("calc.py\r\n=== old\r\nx = \r\n=== new\r\nz = \r\n")),
                         b"z = 1\r\ny = 2\r\n")
        self.calc.write_bytes(b"x = 1\r\ny = 2\r\n")
        self.assertEqual(self.applied(self.mfile("calc.py\r\n=== old\r\nx = 1\r\n=== new\r\nw = 0\r\n")),
                         b"w = 0\r\ny = 2\r\n")
        self.calc.write_bytes(b"x = 1\r\ny = 2\r\n")
        self.assertEqual(self.applied(self.mfile("calc.py\r\n=== old\r\nx = 1\r\n\r\n=== new\r\n")), b"y = 2\r\n")

    def test_each_text_is_what_lies_between_its_markers_less_its_last_line_break(self):
        name = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}\n=== new\n{TWO_LINES_NEW}\n")
        m = mutate.parse_file(self.root, name, self.root)
        self.assertEqual((m["old"], m["new"], m["files"]), (TWO_LINES_OLD.encode(), TWO_LINES_NEW.encode(), ["calc.py"]))
        same = mutate.parse(self.root, f"calc.py:{TWO_LINES_OLD}=>{TWO_LINES_NEW}", self.root)
        self.assertEqual(m["digest"], same["digest"])  # the same substitution as the inline form
        unended = mutate.parse_file(self.root, self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}\n=== new\nx"), self.root)
        self.assertEqual(unended["new"], b"x")  # a text the file's end cuts off loses nothing
        gone = mutate.parse_file(self.root, self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}\n=== new\n"), self.root)
        self.assertEqual(gone["new"], b"")  # an empty new text deletes the old


if __name__ == "__main__":
    unittest.main()
