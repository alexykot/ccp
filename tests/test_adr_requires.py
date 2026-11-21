"""SPEC §6.2, §6.4: an ADR's `requires` key, read into the decision index, and accepting an ADR waiting
for the other ADRs whose decisions it rests on."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import adr, cli, refs
from tests.helpers import Product

BODY = "# T\n\n## Decision\n\n### D1. First\n\nOne.\n\n### D2. Second\n\nTwo.\n"


class Requires(unittest.TestCase):
    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr"}})
        self.addCleanup(self.p.cleanup)

    def write_adr(self, n: int, status: str, **kw):
        fields = {"id": refs.DEFAULT.adr_id(n), "title": "T", "status": status, "date": "2026-01-01", **kw}
        return self.p.write(f"docs/adr/{n:04d}-a.md", adr.emit(fields) + BODY)

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def meta(self, f):
        return adr.parse(adr.split(f.read_text())[0])

    def test_both_forms_are_read_into_the_index(self):
        self.write_adr(1, "accepted")
        self.write_adr(2, "proposed", requires=["D1 ADR-0001 D2", "D2 D1", "D2 0001 D1"])
        index = adr.DecisionIndex.build(adr.load(self.p.cfg)[0])
        self.assertEqual(index.requires(2, "1"), [(1, "2")])
        self.assertEqual(index.requires(2, "2"), [(2, "1"), (1, "1")])
        self.assertEqual(index.required(2), [("1", (1, "2")), ("2", (2, "1")), ("2", (1, "1"))])
        self.assertEqual(index.requires(1, "1"), [])

    def test_an_entry_of_neither_form_is_left_out(self):
        for s in ("ADR-0001 D2", "D1 ADR-0001", "D1", "1 D2", "D1 D2 D3", "D1 ADR-0001 D2 D3", ""):
            self.assertIsNone(adr.parse_requires(s, 2), s)
        self.assertEqual(adr.parse_requires("D2a ADR-0007 D1b", 2), ("2a", (7, "1b")))
        index = adr.DecisionIndex.build([{"_number": 2, "requires": ["D1 ADR-0001", "D1 D2"]}])
        self.assertEqual(index.requires(2, "1"), [(2, "2")])

    def test_the_key_is_declared_and_needs_no_reverse_link(self):
        self.write_adr(1, "accepted")
        self.write_adr(2, "accepted", requires=["D1 ADR-0001 D2"])
        _, errs, warns = adr.analyse(self.p.cfg)
        self.assertEqual(errs, [])
        self.assertFalse([w for w in warns if "requires" in w or "ADR-0002" in w or "0002-a.md" in w], warns)

    def test_accepting_waits_for_a_proposed_prerequisite_and_names_it(self):
        self.write_adr(1, "proposed")
        f = self.write_adr(2, "proposed", requires=["D2 ADR-0001 D1"])
        before = f.read_bytes()
        code, _, err = self.ccp("adr", "status", "2", "accepted")
        self.assertEqual(code, 2)
        self.assertIn("ADR-0001 D1", err)
        self.assertIn("docs/adr/0001-a.md", err)
        self.assertEqual(f.read_bytes(), before)
        self.assertEqual(self.ccp("adr", "status", "1", "accepted")[0], 0)
        code, out, err = self.ccp("adr", "status", "2", "accepted")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.meta(f)["status"], "accepted")

    def test_a_prerequisite_in_its_own_adr_never_holds_its_acceptance(self):
        f = self.write_adr(1, "proposed", requires=["D2 D1", "D1 ADR-0001 D2"])
        code, _, err = self.ccp("adr", "status", "1", "accepted")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.meta(f)["status"], "accepted")

    def test_other_moves_and_settled_prerequisites_do_not_wait(self):
        self.write_adr(1, "proposed")
        self.write_adr(3, "accepted")
        f = self.write_adr(2, "proposed", requires=["D1 ADR-0001 D1"])
        self.assertEqual(self.ccp("adr", "status", "2", "withdrawn")[0], 0)   # only accepting waits
        g = self.write_adr(4, "proposed", requires=["D1 ADR-0003 D1", "D2 ADR-0099 D1", "D1 ADR-0002 D1"])
        code, _, err = self.ccp("adr", "status", "4", "accepted")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.meta(f)["status"], self.meta(g)["status"]), ("withdrawn", "accepted"))


if __name__ == "__main__":
    unittest.main()
