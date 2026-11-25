"""SPEC §19.8: `ccp architect triage` holds a triage to its contract (`contracts/architecture_review_triage.schema.json`)
through the plane's one schema checker, and the code's disposition lists are the contract's enums."""
from __future__ import annotations

import json
import unittest

from ccp import architect, architecture_review
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


if __name__ == "__main__":
    unittest.main()
