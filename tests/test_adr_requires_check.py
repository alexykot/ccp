"""SPEC §6.5, §6.7: `ccp adr check` holds an ADR's `requires` links, a prerequisite retired with a
replacement resolves to it, and `ccp adr supersede` does not cut a `requires` chain."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import adr, cli, refs
from tests.helpers import Product

BODY = "# T\n\n## Decision\n\n### D1. First\n\nOne.\n\n### D2. Second\n\nTwo.\n"


def plain(n: int, *decisions: str, **kw) -> dict:
    """An ADR as `adr.load` returns it, for a decision index: its recorded `decisions` entries."""
    return {"_number": n, "_decisions": [{"id": "1"}, {"id": "2"}], "decisions": list(decisions), **kw}


class Resolution(unittest.TestCase):
    def resolve(self, adrs, n, d):
        return adr.DecisionIndex.build(adrs).resolve(n, d)

    def test_a_decision_not_retired_resolves_to_itself(self):
        self.assertEqual(self.resolve([plain(1, "D1 built")], 1, "1"), adr.Resolved(1, "1"))

    def test_one_link_follows_to_the_replacement(self):
        adrs = [plain(1, "D1 retired by ADR-0002 D2"), plain(2, "D2 built")]
        self.assertEqual(self.resolve(adrs, 1, "1"), adr.Resolved(2, "2"))

    def test_two_links_follow_to_the_end_of_the_chain(self):
        adrs = [plain(1, "D1 retired by ADR-0002 D2"), plain(2, "D2 retired by ADR-0003 D1"), plain(3, "D1 live")]
        self.assertEqual(self.resolve(adrs, 1, "1"), adr.Resolved(3, "1"))

    def test_a_whole_adr_retired_by_ends_the_chain_with_no_replacement(self):
        adrs = [plain(1, "D1 retired by ADR-0002"), plain(2, "D1 built")]
        self.assertEqual(self.resolve(adrs, 1, "1"), adr.Resolved(2, None))

    def test_a_loop_is_marked(self):
        adrs = [plain(1, "D1 retired by ADR-0002 D1"), plain(2, "D1 retired by ADR-0001 D1")]
        self.assertTrue(self.resolve(adrs, 1, "1").loop)


class Check(unittest.TestCase):
    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr"}})
        self.addCleanup(self.p.cleanup)

    def write_adr(self, n: int, status: str = "accepted", **kw):
        fields = {"id": refs.DEFAULT.adr_id(n), "title": "T", "status": status, "date": "2026-01-01", **kw}
        return self.p.write(f"docs/adr/{n:04d}-a.md", adr.emit(fields) + BODY)

    def analyse(self):
        _, errs, warns = adr.analyse(self.p.cfg)
        return errs, warns

    def only(self, found, *words):
        hits = [x for x in found if "requires" in x]
        self.assertEqual(len(hits), 1, found)
        for w in words:
            self.assertIn(w, hits[0])

    def test_links_that_hold_raise_nothing(self):
        self.write_adr(1, decisions=["D1 built", "D2 built"])
        self.write_adr(2, requires=["D1 ADR-0001 D2", "D2 D1"])
        errs, warns = self.analyse()
        self.assertEqual((errs, warns), ([], []))

    def test_an_entry_of_neither_form_fails(self):
        self.write_adr(1)
        self.write_adr(2, requires=["ADR-0001 D1", "D1 D2 D3"])
        errs, _ = self.analyse()
        self.assertEqual(len([e for e in errs if "requires entry" in e]), 2, errs)
        self.assertIn("'ADR-0001 D1'", errs[0])

    def test_a_prose_value_fails_as_malformed(self):
        self.write_adr(1)
        self.write_adr(2, requires="D1 needs the other one")
        self.only(self.analyse()[0], "requires entry")

    def test_its_own_decision_must_exist(self):
        self.write_adr(1)
        self.write_adr(2, requires=["D9 ADR-0001 D1"])
        self.only(self.analyse()[0], "0002-a.md has no decision D9")

    def test_a_target_decision_must_exist(self):
        self.write_adr(1)
        self.write_adr(2, requires=["D1 ADR-0001 D9", "D2 D7"])
        errs = [e for e in self.analyse()[0] if "requires" in e]
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("0001-a.md has no decision D9", errs[0])
        self.assertIn("0002-a.md has no decision D7", errs[1])

    def test_a_target_adr_must_exist(self):
        self.write_adr(2, requires=["D1 ADR-0099 D1"])
        self.only(self.analyse()[0], "names no ADR")

    def test_a_target_in_a_rejected_or_withdrawn_adr_fails(self):
        self.write_adr(1, "rejected")
        self.write_adr(3, "withdrawn")
        self.write_adr(2, requires=["D1 ADR-0001 D1", "D2 ADR-0003 D1"])
        errs = [e for e in self.analyse()[0] if "requires" in e]
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("is rejected", errs[0])
        self.assertIn("is withdrawn", errs[1])

    def test_a_link_inside_a_rejected_or_withdrawn_adr_is_no_failure(self):
        self.write_adr(1, "rejected", requires=["D1 D2"])
        self.write_adr(2, "withdrawn", requires=["D1 ADR-0002 D2"])
        self.assertEqual(self.analyse()[0], [])

    def test_a_proposed_target_is_not_a_failure(self):
        self.write_adr(1, "proposed")
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        self.assertEqual(self.analyse()[0], [])

    def test_a_cycle_across_adrs_fails_naming_its_decisions_in_order(self):
        self.write_adr(1, requires=["D1 ADR-0002 D2"])
        self.write_adr(2, requires=["D2 ADR-0003 D1"])
        self.write_adr(3, requires=["D1 ADR-0001 D1"])
        errs = [e for e in self.analyse()[0] if "cycle" in e]
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("ADR-0001 D1 → ADR-0002 D2 → ADR-0003 D1 → ADR-0001 D1", errs[0])
        self.assertTrue(errs[0].startswith("docs/adr/0001-a.md:"))

    def test_a_cycle_within_one_adr_and_a_self_requirement_fail(self):
        self.write_adr(1, requires=["D1 D2", "D2 D1"])
        self.write_adr(2, requires=["D1 D1"])
        errs = [e for e in self.analyse()[0] if "cycle" in e]
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("ADR-0001 D1 → ADR-0001 D2 → ADR-0001 D1", errs[0])
        self.assertIn("ADR-0002 D1 → ADR-0002 D1", errs[1])

    def test_a_chain_that_is_not_a_cycle_passes(self):
        self.write_adr(1, requires=["D2 D1"])
        self.write_adr(2, requires=["D1 ADR-0001 D2"])
        self.assertEqual(self.analyse()[0], [])

    def test_a_retired_prerequisite_with_a_replacement_resolves_without_a_warning(self):
        self.write_adr(1, decisions=["D1 retired by ADR-0003 D2"])
        self.write_adr(3, decisions=["D2 built"])
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        self.assertEqual(self.analyse(), ([], []))

    def test_a_chain_ending_in_a_decision_retired_with_no_replacement_warns(self):
        self.write_adr(1, decisions=["D1 retired by ADR-0003 D2"])
        self.write_adr(3, decisions=["D2 retired"])
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.only(warns, "ADR-0003 D2", "no replacement", "0002-a.md: D1 requires ADR-0001 D1")

    def test_a_decision_retired_directly_with_no_replacement_warns(self):
        self.write_adr(1, decisions=["D1 retired"])
        self.write_adr(2, requires=["D2 ADR-0001 D1"])
        self.only(self.analyse()[1], "ADR-0001 D1, which is retired with no replacement")

    def test_a_whole_adr_retired_by_is_no_replacement(self):
        self.write_adr(1, decisions=["D1 retired by ADR-0003"])
        self.write_adr(3)
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.only(warns, "whole ADR")

    def test_the_warning_is_a_failure_under_strict(self):
        self.p = Product({"adr": {"dir": "docs/adr", "strict": True}})
        self.addCleanup(self.p.cleanup)
        self.write_adr(1, decisions=["D1 retired by ADR-0003"])
        self.write_adr(3)
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        errs, warns = self.analyse()
        self.only(errs, "whole ADR")
        self.assertEqual([w for w in warns if "requires" in w], [])

    def test_a_retired_by_loop_fails(self):
        self.write_adr(1, decisions=["D1 retired by ADR-0003 D1"])
        self.write_adr(3, decisions=["D1 retired by ADR-0001 D1"])
        self.write_adr(2, requires=["D1 ADR-0001 D1"])
        self.only(self.analyse()[0], "loops back")

    def test_an_adr_with_no_requires_is_unchanged(self):
        self.write_adr(1, decisions=["D1 retired by ADR-0002"])
        self.write_adr(2)
        self.assertEqual(self.analyse(), ([], []))


class Supersede(unittest.TestCase):
    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr"}})
        self.addCleanup(self.p.cleanup)
        self.old = self.write_adr(1, decisions=["D1 built", "D2 built"])
        self.new = self.write_adr(2, decisions=["D1 not_built", "D2 not_built"])
        self.dep = self.write_adr(3, requires=["D1 ADR-0001 D2"])

    def write_adr(self, n: int, status: str = "accepted", **kw):
        fields = {"id": refs.DEFAULT.adr_id(n), "title": "T", "status": status, "date": "2026-01-01", **kw}
        return self.p.write(f"docs/adr/{n:04d}-a.md", adr.emit(fields) + BODY)

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        return [f.read_bytes() for f in (self.old, self.new, self.dep)]

    def test_a_whole_adr_supersede_without_by_refuses_naming_the_requirer(self):
        before = self.snapshot()
        code, _, err = self.ccp("adr", "supersede", "1", "2")
        self.assertEqual(code, 2)
        self.assertIn("ADR-0001 D2 is required by ADR-0003 D1", err)
        self.assertIn("--by", err)
        self.assertEqual(self.snapshot(), before)

    def test_the_same_supersede_with_by_records_the_replacement_decision(self):
        code, _, err = self.ccp("adr", "supersede", "1", "2", "--by", "D2")
        self.assertEqual(code, 0, err)
        index = adr.DecisionIndex.build(adr.load(self.p.cfg)[0])
        self.assertEqual(index.resolve(1, "2"), adr.Resolved(2, "2"))
        self.assertEqual(adr.analyse(self.p.cfg)[1:], ([], []))

    def test_a_partial_supersede_of_the_target_without_by_refuses(self):
        before = self.snapshot()
        code, _, err = self.ccp("adr", "supersede", "1", "2", "--decisions", "D2")
        self.assertEqual(code, 2)
        self.assertIn("ADR-0003 D1", err)
        self.assertEqual(self.snapshot(), before)

    def test_a_partial_supersede_of_another_decision_does_not_refuse(self):
        code, _, err = self.ccp("adr", "supersede", "1", "2", "--decisions", "D1")
        self.assertEqual(code, 0, err)
        self.assertEqual(adr.analyse(self.p.cfg)[1:], ([], []))

    def test_a_decision_already_retired_by_a_decision_is_not_cut(self):
        self.old.write_text(self.old.read_text().replace("D2 built", "D2 retired by ADR-0002 D1"))
        code, _, err = self.ccp("adr", "supersede", "1", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(adr.analyse(self.p.cfg)[1:], ([], []))

    def test_a_requirer_in_the_adr_being_superseded_holds_it_too(self):
        four = self.write_adr(4, decisions=["D1 built", "D2 built"], requires=["D1 D2"])
        before = four.read_bytes()
        code, _, err = self.ccp("adr", "supersede", "4", "2")
        self.assertEqual(code, 2)
        self.assertIn("ADR-0004 D2 is required by ADR-0004 D1", err)
        self.assertEqual(four.read_bytes(), before)
        code, _, err = self.ccp("adr", "supersede", "4", "2", "--by", "D2")
        self.assertEqual(code, 0, err)
        self.assertEqual(adr.analyse(self.p.cfg)[1:], ([], []))

    def test_no_requires_target_supersedes_as_before(self):
        self.dep.write_text(adr.emit({"id": "ADR-0003", "title": "T", "status": "accepted", "date": "2026-01-01"}) + BODY)
        code, _, err = self.ccp("adr", "supersede", "1", "2")
        self.assertEqual(code, 0, err)
        self.assertEqual(adr.analyse(self.p.cfg)[1:], ([], []))


if __name__ == "__main__":
    unittest.main()
