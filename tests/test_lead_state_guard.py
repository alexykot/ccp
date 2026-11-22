"""SPEC §10.4: the lead's preference and holds are recorded only by the lead. `ccp tasks prefer` and `ccp tasks hold`
refuse, through the lead's guard, every caller whose `ACTOR` does not name the lead (unset included); listing them
needs no `ACTOR`, and the hints that tell a reader to run either name the lead's `ACTOR`."""
from __future__ import annotations

import json
import unittest

from ccp.queue import lib
from tests.helpers import as_actor, as_lead
from tests.toolkit_fixture import ToolkitFixture

TID = "0002-second"
WORK = {"status": "running"}


class LeadState(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.set_work(WORK)

    def set_work(self, w: dict) -> None:
        (self.q / "work.json").write_text(json.dumps(w))

    def work_text(self) -> str:
        return (self.q / "work.json").read_text()

    def assert_refused(self, *args: str) -> None:
        """`ccp tasks <args>` as the runner and with `ACTOR` unset: each exits 2 naming the lead, and work.json and the
        ledger are as they were."""
        before, events = self.work_text(), len(self.events())
        for value in (lib.RUNNER, None):
            with as_actor(value):
                code, _, out, err = self.ccp("tasks", *args, root=self.main)
            self.assertEqual(code, 2, f"{value}: {out}{err}")
            self.assertIn("only the lead records", err, value)
            self.assertIn(f"ACTOR={lib.LEAD}", err, value)
            self.assertEqual(self.work_text(), before, value)
            self.assertEqual(len(self.events()), events, value)

    def test_prefer_refuses_the_runner_and_an_unset_actor(self):
        self.assert_refused("prefer", "0002", "--reason", "first")
        with as_lead():
            self.assertEqual(self.ccp("tasks", "prefer", "0002", root=self.main)[0], 0)
        self.assert_refused("prefer", "--clear")
        self.assertEqual(json.loads(self.work_text())["next_tasks"], [TID])

    def test_hold_refuses_the_runner_and_an_unset_actor(self):
        self.assert_refused("hold", "0002", "--reason", "later")
        with as_lead():
            self.assertEqual(self.ccp("tasks", "hold", "0002", root=self.main)[0], 0)
        self.assert_refused("hold", "--clear", "0002")
        self.assertIn(TID, json.loads(self.work_text())["held"])

    def test_the_lead_records_both_as_the_lead(self):
        with as_lead():
            self.assertEqual(self.ccp("tasks", "prefer", "0002", root=self.main)[0], 0)
            self.assertEqual(self.ccp("tasks", "hold", "0002", "--reason", "later", root=self.main)[0], 0)
        w = json.loads(self.work_text())
        self.assertEqual((w["next_task_by"], w["held"][TID]["by"]), (lib.LEAD, lib.LEAD))
        self.assertEqual([(e["type"], e["actor"]) for e in self.events() if e["type"] in ("prefer", "hold")],
                         [("prefer", lib.LEAD), ("hold", lib.LEAD)])

    def test_listing_preference_and_holds_needs_no_actor(self):
        with as_lead():
            self.ccp("tasks", "prefer", "0002", root=self.main)
            self.ccp("tasks", "hold", "0002", "--reason", "later", root=self.main)
        with as_actor(None):
            code, body, out, err = self.ccp("tasks", "prefer", root=self.main)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(body["next_tasks"]["tasks"], [TID])
            code, body, out, err = self.ccp("tasks", "hold", root=self.main)
            self.assertEqual(code, 0, out + err)
            self.assertEqual([h["task_id"] for h in body["held"]], [TID])

    def test_next_passing_over_a_held_task_hints_the_lead_s_clear(self):
        with as_lead():
            self.assertEqual(self.ccp("tasks", "hold", "0002", "--reason", "later", root=self.main)[0], 0)
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 3, out + err)
        self.assertIn(f"passed over {TID}: held", err)
        self.assertIn(f"ACTOR={lib.LEAD} ccp tasks hold --clear {TID}", err)

    def test_a_held_preferred_task_hints_the_lead_s_clear(self):
        self.set_work({**WORK, "next_tasks": [TID]})
        with as_lead():
            self.assertEqual(self.ccp("tasks", "hold", "0002", root=self.main)[0], 0)
        _, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertIn(f"preferred {TID} is held: passed over (`ACTOR={lib.LEAD} ccp tasks hold --clear {TID}`)", err)

    def test_an_ignored_preference_hints_the_lead_s_prefer(self):
        self.set_work({**WORK, "next_tasks": ["0001-first"]})  # done: ignored
        _, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertIn(f"preferred 0001-first is done: ignored (`ACTOR={lib.LEAD} ccp tasks prefer` a new list", err)

    def test_claiming_a_held_task_hints_the_lead_s_clear(self):
        with as_lead():
            self.assertEqual(self.ccp("tasks", "hold", "0002", root=self.main)[0], 0)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"claimed anyway; `ACTOR={lib.LEAD} ccp tasks hold --clear {TID}`", err)


if __name__ == "__main__":
    unittest.main()
