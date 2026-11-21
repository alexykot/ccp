"""A contract schema is written one key to a line, so two changes to different parts of one schema merge
without a conflict on the whole file."""
from __future__ import annotations

import unittest
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


class ContractLayout(unittest.TestCase):
    def test_no_schema_is_one_line(self):
        schemas = sorted(CONTRACTS.glob("*.schema.json"))
        self.assertTrue(schemas)
        flat = [p.name for p in schemas if len(p.read_text().splitlines()) <= 1]
        self.assertEqual(flat, [], "pretty-print these with json.dumps(indent=2) and a trailing newline")


if __name__ == "__main__":
    unittest.main()
