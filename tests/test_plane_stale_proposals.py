"""SPEC §31.4: an open plane proposal untouched for seven days (since its creation or its last
`--again`, whichever is later) is flagged in `ccp plane list` and on the board."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.test_toolkit import ToolkitFixture


def days_ago(d: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%SZ")


class StaleProposals(ToolkitFixture, unittest.TestCase):
    def row(self, **r) -> None:
        p = self.q / "plane" / "proposals.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(r) + "\n")

    def proposed(self, pid: str, at: str) -> None:
        self.row(op="proposed", id=pid, at=at, by="implementer", task_id=None, need=f"need {pid}",
                 generic="any product", workaround=None, frequency="per-task")

    def fresh(self) -> str:
        code, body, out, err = self.ccp("plane", "propose", "--need", "a command that frees a task's resources",
                                        "--generic", "every product with per-task resources needs them freed")
        self.assertEqual(code, 0, out + err)
        return body["id"]

    def listed(self, *flags: str) -> dict:
        code, body, out, err = self.ccp("plane", "list", *flags)
        self.assertEqual(code, 0, out + err)
        return body

    def board(self) -> dict:
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text())

    def test_an_eight_day_old_proposal_is_flagged_in_the_list_and_on_the_board_and_a_new_one_is_not(self):
        self.proposed("pp-old", days_ago(8))
        new = self.fresh()
        for flags in ((), ("--open",)):
            body = self.listed(*flags)
            self.assertEqual({r["id"]: r["stale"] for r in body["proposals"]}, {"pp-old": True, new: False}, flags)
            self.assertEqual(body["stale"], ["pp-old"], flags)
        b = self.board()
        self.assertEqual({p["id"]: p["stale"] for p in b["health"]["proposals_open"]}, {"pp-old": True, new: False})

    def test_a_recent_again_restarts_the_age(self):
        self.proposed("pp-old", days_ago(10))
        self.row(op="again", id="pp-old", at=days_ago(9), by="implementer", task_id=None)
        self.proposed("pp-repeated", days_ago(10))
        self.row(op="again", id="pp-repeated", at=days_ago(2), by="implementer", task_id=None)
        body = self.listed()
        self.assertEqual({r["id"]: r["stale"] for r in body["proposals"]}, {"pp-old": True, "pp-repeated": False})
        self.assertEqual(body["stale"], ["pp-old"])

    def test_a_triaged_proposal_is_never_flagged(self):
        self.proposed("pp-done", days_ago(30))
        self.row(op="triaged", id="pp-done", at=days_ago(1), by="plane-session", decision="declined",
                 merged_into=None, reason="product work")
        body = self.listed()
        self.assertEqual([(r["id"], r["stale"]) for r in body["proposals"]], [("pp-done", False)])
        self.assertEqual(body["stale"], [])
        self.assertEqual(self.board()["health"]["proposals_open"], [])

    def test_a_proposal_six_days_old_or_with_an_unreadable_time_is_not_flagged(self):
        self.proposed("pp-six", days_ago(6))
        self.proposed("pp-garbled", "not a time")
        body = self.listed()
        self.assertEqual({r["id"]: r["stale"] for r in body["proposals"]}, {"pp-six": False, "pp-garbled": False})


if __name__ == "__main__":
    unittest.main()
