"""SPEC §4: a task's runtime state lives in the queue, and `contracts/task.schema.json` is its contract.
What `ccp tasks claim` writes validates against it, and the state keeps no copy of the task's checks: the
task file at the head is where they are read."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp.schema import schema_errors
from tests.test_toolkit import ToolkitFixture

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "task.schema.json"


class TaskStateContract(ToolkitFixture, unittest.TestCase):
    def claimed(self) -> dict:
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        return json.loads((self.q / "tasks/0002-second.json").read_text())

    def test_a_claimed_state_validates_against_the_contract(self):
        self.assertEqual(schema_errors(self.claimed(), json.loads(SCHEMA.read_text())), [])

    def test_a_claimed_state_has_no_copy_of_the_checks(self):
        self.assertNotIn("dod_checks", self.claimed())


if __name__ == "__main__":
    unittest.main()
