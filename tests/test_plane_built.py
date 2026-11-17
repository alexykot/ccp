"""SPEC §29.3, ADR-0041 D4: `ccp plane built` closes an accepted proposal as built by a merged plane task
and copies that task's `adopt` step into its record, which `ccp plane list` shows."""
from __future__ import annotations

import json
import unittest

from ccp.queue import lib
from tests.test_upgrade import UpgradeFixture


class Built(UpgradeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane_task("0001-cache", "done", "Cache", "plane.json verify.accept_cache")
        self.plane_task("0002-bare", "done", "No key")
        self.plane_task("0003-open", "pending", "Not merged", "plane.json x")
        self.commit("plane")
        self.proposal("pp-p", "accepted")

    def listed(self) -> dict:
        code, body, err = self.ccp("plane", "list")
        self.assertEqual(code, 0, err)
        return {r["id"]: r for r in body["proposals"]}

    def rows(self) -> list[dict]:
        return [json.loads(x) for x in (self.q / "plane" / "proposals.jsonl").read_text().splitlines()]

    def events(self) -> list[dict]:
        p = self.q / "observability" / "events.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def test_an_accepted_proposal_is_closed_as_built_with_the_tasks_step(self):
        code, body, err = self.ccp("plane", "built", "pp-p", "--task", "0001-cache")
        self.assertEqual(code, 0, err)
        p = self.listed()["pp-p"]
        self.assertEqual((p["status"], p["built_task"], p["adopt"]),
                         ("built", "0001-cache", "plane.json verify.accept_cache"))
        self.assertEqual([(e["type"], e["op"], e["payload"]["built_task"]) for e in self.events()],
                         [("plane", "built", "0001-cache")])

    def test_a_task_with_no_adopt_key_gives_none(self):
        self.assertEqual(self.ccp("plane", "built", "pp-p", "--task", "0002-bare")[0], 0)
        self.assertEqual(self.listed()["pp-p"]["adopt"], "none")

    def test_a_task_that_is_not_merged_is_refused_and_the_proposal_is_unchanged(self):
        before = self.rows()
        for task in ("NOPE", "0003-open"):
            code, body, err = self.ccp("plane", "built", "pp-p", "--task", task)
            self.assertEqual((code, body), (2, None), task)
            self.assertIn(task, err)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.listed()["pp-p"]["status"], "accepted")
        self.assertEqual(self.events(), [])

    def test_only_an_accepted_proposal_is_closed(self):
        self.proposal("pp-open")
        self.proposal("pp-declined", "declined")
        for pid in ("pp-open", "pp-declined"):
            self.assertEqual(self.ccp("plane", "built", pid, "--task", "0001-cache")[0], 3, pid)
        self.assertEqual(self.ccp("plane", "built", "pp-none", "--task", "0001-cache")[0], 2)
        self.assertEqual(self.ccp("plane", "built", "pp-p", "--task", "0001-cache")[0], 0)
        self.assertEqual(self.ccp("plane", "built", "pp-p", "--task", "0001-cache")[0], 3)

    def test_the_built_event_is_a_known_one(self):
        ev = {"at": "2026-11-17T00:00:00Z", "project_id": "demo", "task_id": "", "actor": "plane-session",
              "type": "plane", "op": "built", "payload": {"proposal_id": "pp-p", "built_task": "0001-cache"}}
        self.assertEqual(lib.validate_event(ev), [])
        self.assertTrue(lib.validate_event({**ev, "payload": {"proposal_id": "pp-p"}}))


if __name__ == "__main__":
    unittest.main()
