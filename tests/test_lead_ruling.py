"""SPEC §17.5, §15.4: a ruling the lead gives a runner by message is recorded with `ccp tasks ruling` as a
`ruling` `recorded` event in the ledger, id `<task_id>-r<n>`, and a verdict cites that id as the ruling of a
check it holds `as_written: false`."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, queue, verify
from tests.helpers import approve_verdict as approve, held_otherwise, Product, LEAD_ENV


class LeadRuling(unittest.TestCase):

    def setUp(self):
        self.p = Product()
        self.p.task("0001-a")
        self.p.task("0002-b")
        self.p.index()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), **LEAD_ENV})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def events(self) -> list[dict]:
        p = self.q / "observability" / "events.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def ruling(self, task: str = "0001-a", words: str = "hold the count at the merge base", *more: str):
        return self.ccp("tasks", "ruling", task, "--words", words, *more)

    def record(self, ruling: str, task: str = "0001-a"):
        src = self.q / "in.json"
        src.write_text(json.dumps(approve(task, checks=[held_otherwise(ruling=ruling)])))
        return self.ccp("verify", "record", str(src))

    def test_a_ruling_gets_the_next_id_of_its_task_and_one_event(self):
        code, out, err = self.ruling("0001-a", "hold the count at the merge base", "--check", "cmd-01")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["id"], "0001-a-r1")
        code, out, err = self.ruling("0001-a", "and the second thing")
        self.assertEqual((code, json.loads(out)["id"]), (0, "0001-a-r2"))
        code, out, err = self.ruling("0002-b", "another task counts from 1")
        self.assertEqual((code, json.loads(out)["id"]), (0, "0002-b-r1"))
        events = [e for e in self.events() if e["type"] == "ruling"]
        self.assertEqual([(e["op"], e["task_id"], e["actor"]) for e in events],
                         [("recorded", "0001-a", "design-seat"), ("recorded", "0001-a", "design-seat"),
                          ("recorded", "0002-b", "design-seat")])
        self.assertEqual(events[0]["payload"], {"id": "0001-a-r1", "n": 1, "check": "cmd-01",
                                                "words": "hold the count at the merge base"})
        self.assertEqual(events[1]["payload"], {"id": "0001-a-r2", "n": 2, "words": "and the second thing"})
        self.assertEqual([r["id"] for r in queue.rulings(self.q, "0001-a")], ["0001-a-r1", "0001-a-r2"])

    def test_an_unknown_task_and_empty_words_exit_2_and_record_nothing(self):
        code, _, err = self.ruling("0099-none")
        self.assertEqual(code, 2, err)
        for words in ("", "   "):
            code, _, err = self.ruling("0001-a", words)
            self.assertEqual(code, 2, err)
            self.assertIn("--words", err)
        code, _, err = self.ruling("0001-a", "words", "--check", " ")
        self.assertEqual(code, 2, err)
        self.assertEqual([e for e in self.events() if e["type"] == "ruling"], [])

    def test_a_verdict_cites_the_ruling_id_and_a_ruling_never_recorded_is_refused(self):
        self.ruling("0001-a", "hold the count at the merge base", "--check", "cmd-01")
        code, out, err = self.record("0001-a-r1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "verification/0001-a.json").read_text())["checks"][0]["ruling"],
                         "0001-a-r1")
        (self.q / "verification/0001-a.json").unlink()
        code, out, err = self.record("0001-a-r9")
        self.assertEqual(code, 1, out + err)
        self.assertIn("0001-a-r9", err)
        self.assertIn("is not a ruling the queue holds", err)
        self.assertIn("no lead ruling 0001-a-r9 is recorded", err)
        self.assertFalse((self.q / "verification/0001-a.json").exists())

    def test_a_ruling_of_another_task_does_not_stand_for_this_task_s_id(self):
        self.ruling("0002-b")
        code, out, err = self.record("0001-a-r1")  # 0001-a has recorded none
        self.assertEqual(code, 1, out + err)
        self.assertIn("no lead ruling 0001-a-r1 is recorded", err)
        code, out, err = self.record("0002-b-r1")  # any task's ruling id is one the queue holds, as a gate id is
        self.assertEqual(code, 0, out + err)

    def test_a_lead_ruling_id_is_one_of_the_forms_a_check_not_run_rests_on(self):
        self.ruling()
        check = {"dod_check_id": "cmd-02", "ran": False, "pass": None, "rests_on": "0001-a-r1",
                 "evidence": "the lead ruled it"}
        self.assertEqual(verify.rests_on_errors(self.p.root, self.q, {"checks": [check]}), [])
        check["rests_on"] = "0001-a-r2"
        errs = verify.rests_on_errors(self.p.root, self.q, {"checks": [check]})
        self.assertEqual(len(errs), 1)
        self.assertIn("no lead ruling 0001-a-r2 is recorded", errs[0])

    def test_a_ruling_beside_a_known_gate_or_prose_is_judged_id_by_id(self):
        self.ruling()
        self.assertIsNone(verify._ruling_refusal(self.q, "the lead ruled in 0001-a-r1, thus"))
        why = verify._ruling_refusal(self.q, "0001-a-r1 and 0001-a-r2")
        self.assertIn("0001-a-r2", why or "")
        self.assertNotIn("0001-a-r1 ", why or "")


if __name__ == "__main__":
    unittest.main()
