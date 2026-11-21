"""`adr.DecisionIndex` on plain ADR dicts: each decision's recorded state, the `retired by` walk and
the two predicates."""
from __future__ import annotations

import unittest

from ccp import adr, refs


def meta(number: int, *recorded: str, body: tuple[str, ...] = ("1", "2", "3", "4")) -> dict:
    return {"_number": number, "decisions": list(recorded), "_decisions": [{"id": i} for i in body]}


class StateTests(unittest.TestCase):
    def setUp(self):
        self.ix = adr.DecisionIndex.build([meta(5, "D1 not_built", "D2 built", "D3 live", "D4 retired by ADR-0006 D1 — gone")])

    def test_each_recorded_state_is_read(self):
        self.assertEqual([self.ix.state(5, i)["state"] for i in "1234"], ["not_built", "built", "live", "retired"])
        self.assertEqual(self.ix.state(5, "4"), {"id": "4", "state": "retired", "by": "ADR-0006 D1", "note": "gone"})

    def test_a_decision_with_no_recorded_state_has_none(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 built")])
        self.assertIsNone(ix.state(5, "2"))
        self.assertIsNone(ix.state(9, "1"))
        self.assertEqual([d["state"] for d in ix.decisions(5)], ["built", None, None, None])

    def test_both_predicates_on_a_decision_with_no_recorded_state(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 built")])
        self.assertFalse(ix.is_built(5, "2"))
        self.assertFalse(ix.blocks_done(5, "2"))

    def test_the_predicates_read_the_recorded_state(self):
        self.assertEqual([self.ix.is_built(5, i) for i in "1234"], [False, True, True, False])
        self.assertEqual([self.ix.blocks_done(5, i) for i in "1234"], [True, False, False, False])

    def test_an_adr_dict_without_a_decisions_key_records_nothing(self):
        ix = adr.DecisionIndex.build([{"_number": 1, "_decisions": [{"id": "1"}]}])
        self.assertEqual(ix.decisions(1)[0]["state"], None)


class BuiltCountTests(unittest.TestCase):
    def test_built_and_live_count_over_the_decisions_not_retired(self):
        self.assertEqual(adr.built(meta(5, "D1 built", "D2 live", "D3 not_built", "D4 retired")), (2, 3))

    def test_a_body_decision_with_no_recorded_state_counts_as_not_built(self):
        self.assertEqual(adr.built(meta(5, "D1 built")), (1, 4))

    def test_an_adr_recording_no_state_has_no_count(self):
        self.assertIsNone(adr.built(meta(5)))

    def test_all_retired_is_a_count_over_none(self):
        self.assertEqual(adr.built(meta(5, "D1 retired", "D2 retired", body=("1", "2"))), (0, 0))


class ResolveTests(unittest.TestCase):
    def test_a_decision_nothing_retires_resolves_to_itself(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 built", "D2 retired")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(5, "1", False))
        self.assertEqual(ix.resolve(5, "2"), adr.Resolved(5, "2", False))
        self.assertEqual(ix.resolve(5, "9"), adr.Resolved(5, "9", False))

    def test_one_link_is_followed(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by ADR-0006 D2"), meta(6, "D2 built")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(6, "2", False))

    def test_two_links_are_followed_to_the_end(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by ADR-0006 D2"), meta(6, "D2 retired by 7 D3"),
                                      meta(7, "D3 built")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(7, "3", False))

    def test_a_loop_is_returned_as_one(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by ADR-0006 D1"), meta(6, "D1 retired by ADR-0005 D1")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(5, "1", True))
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by ADR-0005 D1")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(5, "1", True))

    def test_a_link_to_a_whole_adr_ends_there(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by ADR-0006")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(6, None, False))

    def test_a_retired_by_that_is_not_a_link_ends_at_the_decision(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by the queue rework")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(5, "1", False))

    def test_only_a_retired_state_is_followed(self):
        ix = adr.DecisionIndex.build([meta(5, "D1 built by ADR-0006 D2"), meta(6, "D2 built")])
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(5, "1", False))

    def test_the_prefix_is_the_products(self):
        ids = refs.Ids(adr_prefix="DEC-")
        ix = adr.DecisionIndex.build([meta(5, "D1 retired by DEC-0006 D2"), meta(6, "D2 built")], ids)
        self.assertEqual(ix.resolve(5, "1"), adr.Resolved(6, "2", False))


if __name__ == "__main__":
    unittest.main()
