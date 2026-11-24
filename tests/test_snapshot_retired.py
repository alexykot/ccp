"""SPEC §23.4, ADR-0034 D7: the board is the status. `ccp board status` lists the waits, gates and questions
the retired snapshot used to show."""
from __future__ import annotations

import json
import unittest

from tests.toolkit_fixture import ToolkitFixture


class SnapshotRetired(ToolkitFixture, unittest.TestCase):
    def test_board_status_lists_a_wait_a_gate_and_a_question_and_exits_non_zero(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "x")
        g = self.q / "escalations/0002-second/1.json"
        g.parent.mkdir(parents=True)
        g.write_text(json.dumps({"escalation_id": "0002-second-1", "task_id": "0002-second", "status": "open",
                                 "class": "operator", "brief": "run it by hand"}))
        (self.q / "questions").mkdir()
        (self.q / "questions/sm-1.json").write_text(json.dumps(
            {"question_id": "sm-1", "task_id": "0002-second", "status": "open"}))
        code, _, out, _ = self.ccp("board", "status")
        self.assertEqual(code, 1, out)
        self.assertIn("waiting: 0002-second on design_seat", out)
        self.assertIn("gate 0002-second-1 (operator) open", out)
        self.assertIn("question sm-1 open", out)


if __name__ == "__main__":
    unittest.main()
