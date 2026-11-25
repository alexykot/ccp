"""SPEC §19.8: `ccp architect triage` holds a triage to its contract (`contracts/architecture_review_triage.schema.json`)
through the plane's one schema checker, and the code's disposition lists are the contract's enums."""
from __future__ import annotations

import json
import unittest

from ccp import architect, architecture_review, refs
from tests.architect_fixture import Harness
from tests.helpers import PLANE_ROOT

CONTRACTS = PLANE_ROOT / "contracts"


def contract(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


class TriageSchema(unittest.TestCase):
    def test_a_triage_missing_a_key_the_contract_requires_is_refused_naming_it(self):
        triage = contract("architecture_review_triage.example.json")
        self.assertEqual(architecture_review.validate_triage(triage, triage["review_id"]), [])
        for key in contract("architecture_review_triage.schema.json")["required"]:
            with self.subTest(key=key):
                rest = {k: v for k, v in triage.items() if k != key}
                errs = architecture_review.validate_triage(rest, triage["review_id"])
                self.assertTrue(any(f"missing {key}" in e for e in errs), errs)
        rest = {k: v for k, v in triage.items() if k != "triaged_at"}
        self.assertIn("triage: missing triaged_at", architecture_review.validate_triage(rest, triage["review_id"]))

    def test_the_disposition_lists_equal_the_contract_enums(self):
        props = contract("architecture_review_triage.schema.json")["properties"]
        self.assertEqual(set(architecture_review.DISPOSITIONS),
                         set(props["dispositions"]["items"]["properties"]["disposition"]["enum"]))
        self.assertEqual(set(architect.RULE_DISPOSITIONS),
                         set(props["rule_changes"]["items"]["properties"]["disposition"]["enum"]))


class TriageIdShapes(unittest.TestCase):
    """SPEC §7.1: a task id's width and a rule id's pattern are the product's, so the contract's own patterns (the
    defaults) refuse neither; every other contract error still does."""

    IDS = refs.Ids(task_width=5, rule_pattern="HR-[0-9]+")

    def triage(self, **over):
        triage = contract("architecture_review_triage.example.json")
        triage.update({"tasks_created": ["00012-a-task"], "rule_changes": [
            {"rule": "HR-3", "action": "add", "disposition": "applied", "reason": "agreed"}], **over})
        return triage

    def errs(self, triage, ids=IDS):
        return architecture_review.validate_triage(triage, triage["review_id"], ids)

    def test_a_triage_in_the_products_task_width_and_rule_pattern_passes(self):
        self.assertEqual(self.errs(self.triage()), [])

    def test_the_default_shapes_are_refused_for_a_product_with_its_own(self):
        errs = self.errs(self.triage(tasks_created=["0012-a-task"]))
        self.assertTrue(any("tasks_created[0]" in e for e in errs), errs)
        triage = self.triage()
        triage["rule_changes"][0]["rule"] = "E3"
        errs = self.errs(triage)
        self.assertTrue(any("rule_changes[0].rule" in e for e in errs), errs)

    def test_the_products_shapes_are_refused_under_the_defaults(self):
        errs = self.errs(self.triage(), refs.DEFAULT)
        self.assertTrue(any("tasks_created[0]" in e for e in errs), errs)
        self.assertTrue(any("rule_changes[0].rule" in e for e in errs), errs)

    def test_every_other_contract_error_still_refuses(self):
        triage = self.triage()
        triage["rule_changes"][0]["disposition"] = "bogus"
        triage["tasks_created"].append(7)
        errs = self.errs(triage)
        self.assertTrue(any("rule_changes[0].disposition" in e for e in errs), errs)
        self.assertTrue(any("tasks_created[1]" in e and "is not string" in e for e in errs), errs)


class TriageByAProductsRuleIds(Harness):
    """`ccp architect triage` hands the product's ids to the validation, through both the file-present and `--apply` paths."""

    PLANE_EXTRA = {"ids": {"rule": {"pattern": "HR-[0-9]+"}}}

    def setUp(self):
        super().setUp()
        self.stub_report([], rule_changes=[{"rule": "HR-9", "action": "add", "text": "One registry.",
                                            "check": "command"}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported", res)
        self.rid = res["review_id"]
        self.triage_file = self.q / "reviews" / f"{self.rid}.triage.json"
        self.triage_file.write_text(json.dumps({
            "schema_version": 1, "review_id": self.rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
            "record": "r.md", "tasks_created": [], "answered_by": "spec_maintainer", "dispositions": [],
            "commit_sha": "abc1234", "rule_changes": [
                {"rule": "HR-9", "action": "add", "disposition": "applied", "reason": "agreed"}]}))

    def test_triage_accepts_the_products_rule_id(self):
        code, res, _ = self.dpj("architect", "triage", self.rid)
        self.assertEqual((code, res["outcome"]), (0, "triaged"), res)

    def test_apply_accepts_the_products_rule_id(self):
        st = self.state()
        st["reviews"][self.rid]["status"] = "triage_sent"
        (self.q / "architect.json").write_text(json.dumps(st))
        code, res, _ = self.dpj("architect", "triage", "--apply", self.rid)
        self.assertEqual((code, res["outcome"]), (0, "applied"), res)


if __name__ == "__main__":
    unittest.main()
