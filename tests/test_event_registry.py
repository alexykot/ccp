"""The ledger's event types and ops are written once, in `scripts/observability/lib.py`; this is the one test that
holds `contracts/observability_event.schema.json` to them: the schema's type enum is the types ccp writes plus the
read-only legacy ones, its op enum is the ops, and every required payload names a type and an op that exist."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp.queue import lib

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "contracts/observability_event.schema.json").read_text())
TYPES = SCHEMA["properties"]["type"]["enum"]
OPS = SCHEMA["properties"]["op"]["enum"]


class EventRegistry(unittest.TestCase):
    def test_the_schema_types_are_the_writer_types_and_the_legacy_ones(self):
        self.assertEqual(len(TYPES), len(set(TYPES)), "a type is listed twice in the schema")
        self.assertEqual(set(TYPES), {*lib.EVENT_TYPES, *lib.LEGACY_EVENT_TYPES})
        self.assertFalse(set(lib.EVENT_TYPES) & set(lib.LEGACY_EVENT_TYPES), "a legacy type is also a writer type")

    def test_the_schema_ops_are_the_registry_ops(self):
        self.assertEqual(len(OPS), len(set(OPS)), "an op is listed twice in the schema")
        self.assertEqual(set(OPS), set(lib.EVENT_OPS))

    def test_every_required_payload_names_a_known_type_and_op(self):
        for (typ, op), keys in lib.REQUIRED_PAYLOAD.items():
            self.assertIn(typ, lib.EVENT_TYPES, f"required payload {typ}/{op}: not a writer type")
            self.assertIn(op, lib.EVENT_OPS, f"required payload {typ}/{op}: not a known op")
            self.assertTrue(keys and all(isinstance(k, str) and k for k in keys), f"{typ}/{op}: its keys")


if __name__ == "__main__":
    unittest.main()
