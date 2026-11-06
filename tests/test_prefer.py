"""SPEC §10.4: the lead's preference list for the runner's next tasks (`ccp tasks prefer`, work.json
`next_tasks`): set, show, clear, refusals, `next` taking the first ready one, the claim removing only
its own entry, a legacy `next_task`, the board."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture

KEYS = ("next_tasks", "next_task", "next_task_by", "next_task_at", "next_task_reason")


class Prefer(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        t = lambda tid, status="pending", deps="": TASK.format(tid=tid, title=tid[5:].title(), status=status,  # noqa: E731
                                                               deps=deps, ver="*Append-only.*")
        self.write("docs/delivery/tasks/0003-third.md", t("0003-third", deps='"0002-second"'))
        self.write("docs/delivery/tasks/0004-fourth.md", t("0004-fourth"))
        self.write("docs/delivery/tasks/0005-gone.md", t("0005-gone", status="dropped"))
        self.write("docs/delivery/tasks/0006-other.md", t("0006-other"))
        self.set_work(scope=["0002-second", "0003-third", "0004-fourth", "0005-gone"])
        self.lead = mock.patch.dict(os.environ, {"ACTOR": "design-seat"})

    def set_work(self, **kw):
        (self.q / "work.json").write_text(json.dumps({"status": "running", **kw}))

    def work(self) -> dict:
        return json.loads((self.q / "work.json").read_text())

    def prefer(self, *args):
        with self.lead:
            return self.ccp("tasks", "prefer", *args, root=self.main)

    def test_prefer_sets_shows_and_clears(self):
        code, body, out, err = self.prefer("0004", "--reason", "unblocks the demo")
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertEqual((w["next_tasks"], w["next_task_by"], w["next_task_reason"]),
                         (["0004-fourth"], "design-seat", "unblocks the demo"))
        self.assertTrue(w["next_task_at"])
        self.assertEqual(w["scope"][0], "0002-second")  # other keys kept
        code, body, _, _ = self.prefer()
        self.assertEqual((code, body["next_tasks"]["tasks"], body["next_tasks"]["by"]), (0, ["0004-fourth"], "design-seat"))
        code, body, _, _ = self.prefer("--clear")
        self.assertEqual((code, body["cleared"]["tasks"]), (0, ["0004-fourth"]))
        self.assertFalse(any(k in self.work() for k in KEYS))
        self.assertIsNone(self.prefer()[1]["next_tasks"])
        evs = [e for e in self.events() if e["type"] == "prefer"]
        self.assertEqual([(e["op"], e["task_id"], e["actor"]) for e in evs],
                         [("set", "0004-fourth", "design-seat"), ("clear", "0004-fourth", "design-seat")])
        self.assertEqual((evs[1]["payload"]["was"], evs[1]["payload"]["tasks"]), ("0004-fourth", ["0004-fourth"]))

    def test_prefer_refuses_unknown_done_dropped_and_out_of_scope(self):
        for tid, want in (("0099", "no task 0099"), ("0001", "0001-first is done"), ("0005", "0005-gone is dropped"),
                          ("0006", "team.sh runner scope --add 0006-other")):
            code, _, _, err = self.prefer(tid)
            self.assertEqual(code, 2, tid)
            self.assertIn(want, err)
        self.assertNotIn("next_tasks", self.work())
        self.assertFalse([e for e in self.events() if e["type"] == "prefer"])

    def test_one_bad_entry_refuses_the_whole_list_and_a_new_list_replaces_the_old(self):
        self.assertEqual(self.prefer("0004", "0002")[0], 0)
        for args, want in ((("0002", "0099"), "no task 0099"), (("0002", "0006"), "team.sh runner scope --add 0006-other"),
                           (("0002", "0004", "0002"), "0002-second is named twice")):
            code, _, _, err = self.prefer(*args)
            self.assertEqual(code, 2, args)
            self.assertIn(want, err)
            self.assertEqual(self.work()["next_tasks"], ["0004-fourth", "0002-second"])  # nothing written
        self.assertEqual(self.prefer("0003", "0004")[0], 0)
        self.assertEqual(self.work()["next_tasks"], ["0003-third", "0004-fourth"])
        evs = [e for e in self.events() if e["type"] == "prefer"]
        self.assertEqual(evs[-1]["payload"]["tasks"], ["0003-third", "0004-fourth"])

    def test_next_takes_the_first_ready_entry_and_claims_walk_the_list(self):
        code, _, _, err = self.prefer("0003", "0004", "0002", "--reason", "the order")
        self.assertEqual(code, 0)
        self.assertIn("preferred 0003-third is waiting on 0002-second", err)
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0004-fourth"), out)
        self.assertIn("the lead's preference (2 of 3, design-seat, ", out)
        self.assertIn("preferred 0003-third is waiting on 0002-second: skipped for now, keeping its place", err)
        code, body, out, err = self.ccp("tasks", "next", "--explain", root=self.main)
        self.assertEqual(code, 0, out + err)
        rows = err[err.index("--explain:"):]
        self.assertLess(rows.index("0004-fourth"), rows.index("0002-second"))
        self.assertIn("0002-second  Second  — the lead's preference (3 of 3, ", err)
        code, _, out, err = self.ccp("tasks", "claim", "0004", root=self.main)
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertEqual((w["next_tasks"], w["next_task_reason"]), (["0003-third", "0002-second"], "the order"))
        last = [e for e in self.events() if e["type"] == "prefer"][-1]
        self.assertEqual(last["payload"], {"was": "0004-fourth", "reason": "claimed", "left": ["0003-third", "0002-second"]})

    def test_held_and_dead_entries_are_passed_over_and_the_last_claim_empties_the_list(self):
        self.assertEqual(self.prefer("0004", "0003", "0002")[0], 0)
        self.set_work(**{**self.work(), "next_tasks": ["0005-gone", "0004-fourth", "0003-third", "0002-second"],
                         "held": {"0004-fourth": {"by": "design-seat"}}})
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertTrue(out.startswith("0002-second"), out)  # 0005 dropped, 0004 held, 0003 waits on 0002
        self.assertIn("the lead's preference (4 of 4, ", out)
        for note in ("preferred 0005-gone is dropped: ignored", "preferred 0004-fourth is held: passed over",
                     "preferred 0003-third is waiting on 0002-second: skipped for now"):
            self.assertIn(note, err)
        from ccp import selection  # noqa: PLC0415
        from ccp.config import load as load_cfg  # noqa: PLC0415
        states = {s["task_id"]: s["state"] for s in selection.pick(load_cfg(self.main), self.q)["preferred"]}
        self.assertEqual(states["0004-fourth"], "held")
        self.set_work(**{**self.work(), "next_tasks": ["0002-second"], "held": {}})
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(any(k in self.work() for k in KEYS), self.work())

    def test_a_claim_keeps_entries_the_lead_set_after_the_claim_read(self):
        from ccp import lifecycle  # noqa: PLC0415
        self.assertEqual(self.prefer("0002", "0004")[0], 0)
        real = lifecycle.save_work

        def racing(q, updates, *a, **kw):  # the lead resets the list between the claim's read and its write
            if kw.get("edit") is not None:
                w = json.loads((self.q / "work.json").read_text())
                (self.q / "work.json").write_text(json.dumps({**w, "next_tasks": ["0004-fourth", "0002-second", "0003-third"]}))
            return real(q, updates, *a, **kw)

        with mock.patch.object(lifecycle, "save_work", racing):
            code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.work()["next_tasks"], ["0004-fourth", "0003-third"])
        self.assertEqual([e for e in self.events() if e["type"] == "prefer"][-1]["payload"]["left"], ["0004-fourth", "0003-third"])
        n = len([e for e in self.events() if e["type"] == "prefer"])

        def dropped(q, updates, *a, **kw):  # the lead's new list leaves the claimed task out: no clear is logged
            w = json.loads((self.q / "work.json").read_text())
            (self.q / "work.json").write_text(json.dumps({**w, "next_tasks": ["0004-fourth"]}))
            return real(q, updates, *a, **kw)

        self.set_work(**{**self.work(), "next_tasks": ["0002-second", "0004-fourth"]})
        with mock.patch.object(lifecycle, "save_work", dropped):
            self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        self.assertEqual(len([e for e in self.events() if e["type"] == "prefer"]), n)
        self.assertEqual(self.work()["next_tasks"], ["0004-fourth"])

    def test_next_takes_the_preference_ahead_of_the_review_points_refactors(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {}}))
        self.write("docs/delivery/tasks/0007-tidy.md", TASK.format(tid="0007-tidy", title="Tidy", status="pending", deps="",
                                                                   ver="*Append-only.*").replace('spec_refs: ["S1"]', 'spec_refs: []\nkind: refactor\nrule_refs: ["E1"]'))
        (self.q / "architect.json").write_text(json.dumps({"reviews": {}, "last": {"done_count": 99, "at": "2099-01-01T00:00:00Z"}}))
        self.set_work(scope=["0007-tidy", "0002-second", "0004-fourth"], review_point="R8", review_point_refactors=["0007-tidy"])
        self.assertEqual(self.prefer("0004", "--reason", "the demo")[0], 0)
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0004-fourth"), out)
        self.assertIn("why:       the lead's preference (design-seat, ", out)
        self.assertIn("the demo", out)
        self.prefer("--clear")
        self.assertTrue(self.ccp("tasks", "next", root=self.main)[2].startswith("0007-tidy"))

    def test_a_preference_not_ready_yet_falls_through_with_a_note(self):
        code, body, _, err = self.prefer("0003")
        self.assertEqual(code, 0)
        self.assertIn("preferred 0003-third is waiting on 0002-second", err)
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0002-second"), out)
        self.assertIn("preferred 0003-third is waiting on 0002-second", err)
        self.assertNotIn("lead's preference", out)
        self.set_work(scope=["0002-second"], next_task="0003-third")  # a legacy next_task; scope narrowed since: ignored
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertTrue(out.startswith("0002-second"), out)
        self.assertIn("preferred 0003-third is out of scope: ignored", err)

    def test_claim_of_the_preferred_task_clears_it_and_another_claim_keeps_it(self):
        self.assertEqual(self.prefer("0004")[0], 0)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.work()["next_tasks"], ["0004-fourth"])
        self.assertEqual(self.work()["task_id"], "0002-second")
        self.set_work(scope=["0002-second"], next_task="0002-second", next_task_by="design-seat",  # a legacy next_task
                      next_task_at="2026-10-21T16:00:00Z", next_task_reason="x")
        code, _, out, err = self.ccp("tasks", "claim", "0002")  # resumed: same holder
        self.assertEqual(code, 0, out + err)
        w = self.work()
        self.assertFalse(any(k in w for k in KEYS), w)
        self.assertEqual(w["task_id"], "0002-second")
        last = [e for e in self.events() if e["type"] == "prefer"][-1]
        self.assertEqual((last["op"], last["payload"]), ("clear", {"was": "0002-second", "reason": "claimed", "left": []}))

    def test_board_shows_the_preference(self):
        self.prefer("0004", "0002", "--reason", "the demo")
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        b = json.loads(Path(body["board"]).read_text())
        self.assertEqual((b["now"]["next_tasks"]["tasks"], b["now"]["next_tasks"]["reason"]),
                         (["0004-fourth", "0002-second"], "the demo"))
        self.assertIn("next: 0004-fourth, 0002-second (design-seat, the demo)", self.ccp("board", "status", root=self.main)[2])
        self.assertIn("n.next_tasks", Path(body["page"]).read_text())
        self.prefer("--clear")
        self.ccp("board", "build", root=self.main)
        self.assertNotIn("next:", self.ccp("board", "status", root=self.main)[2])


if __name__ == "__main__":
    unittest.main()
