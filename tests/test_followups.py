"""SPEC §13.4, ADR-0044 D2 and D4: the lead records what became of each worker follow-up on its run record
(`ccp tasks follow-up`), and `ccp tasks follow-ups` lists them across tasks, the undecided ones counted."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ccp import config, followups, refs, runs, tasklog
from ccp.queue import lib
from tests.helpers import as_lead
from tests.toolkit_fixture import ToolkitFixture, git


def record(run_id: str, *texts: str, outcomes: dict[int, dict] | None = None) -> dict:
    """A reported run record carrying `texts` as its follow-ups, numbered from 1; `outcomes` by number."""
    task_id, _, _ = runs.parse_id(run_id)
    return {"run_id": run_id, "task_id": task_id, "phase": run_id.split("/")[1].split("-")[0],
            "follow_ups": [{"id": refs.follow_up_id(run_id, n), "text": t, "outcome": (outcomes or {}).get(n)}
                           for n, t in enumerate(texts, 1)]}


DROPPED = {"kind": "drop", "reason": "not worth it", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD}


class OnPlainRecords(unittest.TestCase):

    def test_undecided_holds_each_follow_up_without_an_outcome_in_order(self):
        recs = [record("0001-a/implement", "gap one", "gap two", outcomes={1: DROPPED}),
                {"run_id": "0001-a/review", "task_id": "0001-a"},  # no follow_ups at all
                {"run_id": "0002-b/review", "task_id": "0002-b", "follow_ups": "not a list"},
                record("0002-b/verify", "gap three")]
        got = followups.undecided(recs)
        self.assertEqual([(r["id"], r["task_id"], r["run_id"], r["text"]) for r in got],
                         [("0001-a/implement#2", "0001-a", "0001-a/implement", "gap two"),
                          ("0002-b/verify#1", "0002-b", "0002-b/verify", "gap three")])
        self.assertTrue(all(r["outcome"] is None for r in got))

    def test_an_entry_without_an_id_or_with_an_empty_outcome_reads_as_listed(self):
        rec = {"run_id": "0001-a/fix", "task_id": "0001-a",
               "follow_ups": ["text only", {"text": "no id"}, {"id": "0001-a/fix#3", "text": "t", "outcome": {}}]}
        self.assertEqual([r["id"] for r in followups.undecided([rec])], ["0001-a/fix#3"])

    def test_listing_gives_every_follow_up_or_only_the_open_ones(self):
        recs = [record("0001-a/implement", "gap one", "gap two", outcomes={1: DROPPED})]
        self.assertEqual([(r["id"], r["outcome"]) for r in followups.listing(recs, False)],
                         [("0001-a/implement#1", DROPPED), ("0001-a/implement#2", None)])
        self.assertEqual([r["id"] for r in followups.listing(recs, True)], ["0001-a/implement#2"])

    def test_a_line_names_the_id_the_task_the_outcome_or_open_and_the_text(self):
        rows = followups.listing([record("0001-a/implement", "gap one", "gap two", "gap three", outcomes={
            1: DROPPED, 2: {"kind": "task", "ref": "0009-z", "at": "t", "by": lib.LEAD}})], False)
        self.assertEqual([followups.line(r) for r in rows],
                         ["0001-a/implement#1 0001-a drop: gap one", "0001-a/implement#2 0001-a task:0009-z: gap two",
                          "0001-a/implement#3 0001-a open: gap three"])

    def test_a_task_resolves_by_its_full_id_or_its_only_number(self):
        present = ["0001-first", "0002-second"]
        self.assertEqual(followups.resolve_task("0002-second", present, refs.DEFAULT), "0002-second")
        self.assertEqual(followups.resolve_task("0002", present, refs.DEFAULT), "0002-second")
        self.assertIsNone(followups.resolve_task("0003", present, refs.DEFAULT))
        self.assertIsNone(followups.resolve_task("0002-other", present, refs.DEFAULT))

    def test_a_follow_up_id_parses_back_to_its_run_and_number(self):
        fid = refs.follow_up_id("0001-a/review-2", 3)
        self.assertEqual(refs.parse_follow_up_id(fid), ("0001-a/review-2", 3))
        for bad in ("0001-a/review", "0001-a/review#0", "0001-a/review#x", "#1", ""):
            self.assertIsNone(refs.parse_follow_up_id(bad), bad)


class TheCommands(ToolkitFixture, unittest.TestCase):
    """`ccp tasks follow-up` and `follow-ups` against a git product and a queue, run as the lead."""

    RUN = "0002-second/review"

    def setUp(self):
        super().setUp()
        self.lead = as_lead()
        self.lead.start()
        runs.save(self.q, record(self.RUN, "a test gap out of scope", "a step for a later task"))

    def tearDown(self):
        self.lead.stop()
        super().tearDown()

    def follow_ups_on_record(self) -> list[dict]:
        return runs.load(self.q, self.RUN)["follow_ups"]

    def decide(self, n: int, *how: str):
        return self.ccp("tasks", "follow-up", refs.follow_up_id(self.RUN, n), *how)

    def assert_refused(self, result, *flag: str):
        code, _, _, err = result
        self.assertEqual(code, 2, err)
        for f in flag:
            self.assertIn(f, err)
        self.assertEqual([fu["outcome"] for fu in self.follow_ups_on_record()], [None, None])
        self.assertNotIn(("run", "decided"), self.ops())

    def test_a_task_outcome_is_written_on_the_run_with_its_event(self):
        code, body, _, err = self.decide(1, "--task", "0001")
        self.assertEqual(code, 0, err)
        outcome = self.follow_ups_on_record()[0]["outcome"]
        self.assertEqual((outcome["kind"], outcome["ref"], outcome["by"]), ("task", "0001-first", lib.LEAD))
        self.assertTrue(outcome["at"])
        self.assertIsNone(self.follow_ups_on_record()[1]["outcome"])
        self.assertEqual(body["outcome"], outcome)
        ev = [e for e in self.events() if (e["type"], e["op"]) == ("run", "decided")]
        self.assertEqual([(e["task_id"], e["actor"], e["payload"]) for e in ev],
                         [("0002-second", lib.LEAD, {"run_id": self.RUN, "follow_up": f"{self.RUN}#1",
                                                            "kind": "task", "ref": "0001-first"})])

    def test_a_second_decision_replaces_the_first(self):
        self.assertEqual(self.decide(1, "--task", "0002-second")[0], 0)
        code, body, _, err = self.decide(1, "--drop", "the later task already covers it")
        self.assertEqual(code, 0, err)
        outcome = self.follow_ups_on_record()[0]["outcome"]
        self.assertEqual((outcome["kind"], outcome["reason"]), ("drop", "the later task already covers it"))
        self.assertNotIn("ref", outcome)
        self.assertEqual(body["replaced"]["ref"], "0002-second")

    def test_a_proposal_outcome_names_a_row_of_the_proposals(self):
        code, made, _, err = self.ccp("plane", "propose", "--need", "a step", "--generic", "any product")
        self.assertEqual(code, 0, err)
        code, _, _, err = self.decide(2, "--proposal", made["id"])
        self.assertEqual(code, 0, err)
        self.assertEqual(self.follow_ups_on_record()[1]["outcome"]["ref"], made["id"])

    def test_a_caller_other_than_the_lead_is_refused(self):
        with mock.patch.dict(os.environ, {"ACTOR": lib.RUNNER}):
            self.assert_refused(self.decide(1, "--drop", "not worth it"))

    def test_an_id_that_resolves_to_no_follow_up_is_refused(self):
        self.assert_refused(self.decide(3, "--drop", "not worth it"))
        self.assert_refused(self.ccp("tasks", "follow-up", "0002-second/verify#1", "--drop", "x"))
        self.assert_refused(self.ccp("tasks", "follow-up", self.RUN, "--drop", "x"))
        self.assert_refused(self.ccp("tasks", "follow-up", "not-a-run#1", "--drop", "x"))

    def test_a_task_not_in_the_log_at_the_integration_tip_is_refused(self):
        self.assert_refused(self.decide(1, "--task", "0009-none"), "--task")
        self.write("docs/delivery/tasks/0003-third.md", (self.main / "docs/delivery/tasks/0002-second.md")
                   .read_text().replace("0002-second", "0003-third"))
        git(self.main, "add", "docs/delivery/tasks/0003-third.md")
        git(self.main, "commit", "-q", "-m", "a task not pushed")
        self.assert_refused(self.ccp("tasks", "follow-up", f"{self.RUN}#1", "--task", "0003", root=self.main), "--task")
        git(self.main, "push", "-q", "origin", "main")
        code, _, _, err = self.ccp("tasks", "follow-up", f"{self.RUN}#1", "--task", "0003", root=self.main)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.follow_ups_on_record()[0]["outcome"]["ref"], "0003-third")

    def test_a_task_file_at_the_tip_with_no_status_is_refused(self):
        self.write("docs/delivery/tasks/0004-broken.md", "No frontmatter, so no status.\n")
        git(self.main, "add", "docs/delivery/tasks/0004-broken.md")
        git(self.main, "commit", "-q", "-m", "a task file without a status")
        git(self.main, "push", "-q", "origin", "main")
        self.assertIn("0004-broken", tasklog.task_ids_at(config.load(self.main), "origin/main"))
        self.assert_refused(self.ccp("tasks", "follow-up", f"{self.RUN}#1", "--task", "0004", root=self.main),
                            "--task")

    def test_an_id_given_with_surrounding_whitespace_resolves(self):
        code, body, _, err = self.ccp("tasks", "follow-up", f"  {self.RUN}#2 ", "--drop", "not worth it")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["id"], f"{self.RUN}#2")
        self.assertEqual(self.follow_ups_on_record()[1]["outcome"]["reason"], "not worth it")

    def test_the_task_ids_at_a_rev_are_its_task_files_only(self):
        self.write("docs/delivery/tasks/README.md", "Not a task.\n")
        git(self.main, "add", "docs/delivery/tasks/README.md")
        git(self.main, "commit", "-q", "-m", "a file that is not a task")
        cfg = config.load(self.main)
        self.assertEqual(tasklog.task_ids_at(cfg, "HEAD"), ["0001-first", "0002-second"])
        self.assertEqual(tasklog.task_ids_at(cfg, "no-such-rev"), [])

    def test_a_proposal_not_on_record_is_refused(self):
        self.assert_refused(self.decide(1, "--proposal", "pp-none"), "--proposal")

    def test_an_empty_or_secret_like_drop_reason_is_refused(self):
        for reason in ("", "   "):
            self.assert_refused(self.decide(1, "--drop", reason), "--drop")
        self.assert_refused(self.decide(1, "--drop", "ghp_" + "a" * 36), "--drop")

    def test_the_listing_prints_a_line_each_then_the_open_count_and_json_with_open(self):
        self.assertEqual(self.decide(1, "--drop", "not worth it")[0], 0)
        runs.save(self.q, record("0001-first/verify", "one more gap", "and another"))
        code, _, out, err = self.ccp("tasks", "follow-ups")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual([x.split(":")[0].split() for x in lines[:-1]],
                         [["0001-first/verify#1", "0001-first", "open"], ["0001-first/verify#2", "0001-first", "open"],
                          [f"{self.RUN}#1", "0002-second", "drop"], [f"{self.RUN}#2", "0002-second", "open"]])
        self.assertEqual(lines[-1], "3 open")
        code, _, out, err = self.ccp("tasks", "follow-ups", "--open", "--json")
        self.assertEqual(code, 0, err)
        got = json.loads(out)
        self.assertEqual([(r["id"], r["task_id"], r["text"], r["outcome"]) for r in got],
                         [("0001-first/verify#1", "0001-first", "one more gap", None),
                          ("0001-first/verify#2", "0001-first", "and another", None),
                          (f"{self.RUN}#2", "0002-second", "a step for a later task", None)])
        code, _, out, err = self.ccp("tasks", "follow-ups", "--json")
        self.assertEqual([r["outcome"]["kind"] if r["outcome"] else None for r in json.loads(out)],
                         [None, None, "drop", None])


if __name__ == "__main__":
    unittest.main()
