"""The seat that rules never produces the evidence it rules on (SPEC §2.3, §15.4): each check of a
verify record names the seat that produced its evidence, and `ccp verify` refuses evidence from a
ruling seat unless it is an operator step the operator approved."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from tests.helpers import Product
from tests.test_verify import HEAD_A, ROOT, approve, now_iso

TASK = "0001-a"


def check(seat: str | None, **fields: object) -> dict:
    c = {"dod_check_id": "data-01", "pass": True, "evidence": "the migration's output at the head", **fields}
    if seat is not None:
        c["produced_by"] = seat
    return c


class Producer(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.pr = {"number": 7, "state": "OPEN", "headRefOid": HEAD_A, "mergedAt": None}
        gh = self.q / "fake-gh"
        gh.write_text("#!/bin/sh\ncat \"$(dirname \"$0\")/pr.json\"\n")
        gh.chmod(0o755)
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "CCP_GH_BIN": str(gh)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def record(self, *checks: dict, **fields: object) -> tuple[int, str, str]:
        src = self.q / "in.json"
        src.write_text(json.dumps(approve(TASK, checks=list(checks), **fields)))
        return self.ccp("verify", "record", str(src))

    def written(self) -> Path:
        return self.q / "verification" / f"{TASK}.json"

    def gate(self, n: int, task: str = TASK, **fields: object) -> str:
        """An escalation file as `team.sh gate` writes it (§17.9), approved unless `fields` say otherwise."""
        g = {"task_id": task, "project_id": "demo", "escalation_id": f"{task}-{n}", "class": "operator",
             "to": "design_seat", "brief": "live step", "status": "closed", "decision": "approved",
             "decided_by": "design_seat", "created_at": now_iso(), **fields}
        d = self.q / "escalations" / task
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{n}.json").write_text(json.dumps(g))
        return f"{task}-{n}"

    def question(self, qid: str, verdict: str | None) -> str:
        """A spec question file (§17.4) and, with `verdict`, its answer file as the lead writes it (§17.5)."""
        d = self.q / "questions"
        d.mkdir(exist_ok=True)
        (d / f"{qid}.json").write_text(json.dumps({"question_id": qid, "project_id": "demo", "status": "open"}))
        if verdict is not None:
            (d / f"{qid}.answer.json").write_text(json.dumps({"schema_version": 1, "question_id": qid,
                                                             "project_id": "demo", "verdict": verdict}))
        return qid

    def test_evidence_produced_by_a_ruling_seat_is_refused_naming_the_check_and_the_seat(self):
        for seat in ("lead", "runner"):
            for verdict in ("approve", "reject"):
                code, _, err = self.record(check("verifier", dod_check_id="cmd-01"), check(seat), verdict=verdict)
                self.assertEqual(code, 1, (seat, verdict))
                self.assertIn("nothing written", err)
                self.assertIn("checks[1] (data-01)", err)
                self.assertIn(f"produced by the {seat}", err)
                self.assertNotIn("checks[0]", err)
                self.assertFalse(self.written().exists())

    def test_a_check_must_name_its_producer(self):
        code, _, err = self.record(check(None))
        self.assertEqual(code, 1)
        self.assertIn("checks[0] (data-01)", err)
        self.assertIn("produced_by", err)
        self.assertFalse(self.written().exists())
        code, _, err = self.record(check("auditor"))
        self.assertEqual(code, 1)
        self.assertIn("record.checks[0].produced_by", err)

    def test_only_a_check_a_ruling_closed_may_name_no_producer(self):
        self.gate(1)
        waived = {"ran": False, "pass": None, "rests_on": "the lead's ruling, gate 0001-a-1"}
        code, _, err = self.record(check(None, **waived))
        self.assertEqual(code, 0, err)
        self.assertNotIn("produced_by", json.loads(self.written().read_text())["checks"][0])
        self.written().unlink()
        for fields in ({"ran": True}, {"ran": False, "pass": None}):
            code, _, err = self.record(check(None, **fields))
            self.assertEqual(code, 1, fields)
            self.assertIn("checks[0] (data-01)", err)
            self.assertIn("names no produced_by", err)
            self.assertFalse(self.written().exists())
        code, _, err = self.record(check("lead", **waived))
        self.assertEqual(code, 1)
        self.assertIn("produced by the lead", err)

    def test_a_check_a_ruling_closed_names_a_ruling_the_queue_holds(self):
        question = self.question("sm-20261111T120000Z-ab12", "resolved")
        ruled = {"ran": False, "pass": None}
        for rests_on in (self.gate(1), f"the lead's answer to {question}", self.gate(3, task="0002-b")):
            code, _, err = self.record(check(None, rests_on=rests_on, **ruled))
            self.assertEqual(code, 0, (rests_on, err))
            self.written().unlink()
        for rests_on, needle in (("the lead said so in chat", "names no ruling id"),
                                 (f"{TASK}-9", f"{TASK}-9"),
                                 ("sm-20261111T120000Z-ffff", "sm-20261111T120000Z-ffff"),
                                 (f"{TASK}-1 and {TASK}-9", f"{TASK}-9"),
                                 (f"{question} and sm-20261111T120000Z-ffff", "sm-20261111T120000Z-ffff"),
                                 (self.gate(4, status="open", decision=None), f"gate {TASK}-4 is not closed"),
                                 (self.gate(5, decision="refused"), f"gate {TASK}-5 is not closed")):
            code, _, err = self.record(check(None, rests_on=rests_on, **ruled))
            self.assertEqual(code, 1, rests_on)
            self.assertIn("checks[0] (data-01): rests_on", err)
            self.assertIn(needle, err)
            self.assertNotIn("names no produced_by", err)
            self.assertFalse(self.written().exists())

    def test_a_spec_question_is_a_ruling_only_once_answered_resolved(self):
        unrun = {"ran": False, "pass": None}
        resolved = self.question("sm-20261111T120000Z-0001", "resolved")
        code, _, err = self.record(check(None, rests_on=f"the lead's answer to {resolved}", **unrun))
        self.assertEqual(code, 0, err)
        self.written().unlink()
        for qid, verdict in (("sm-20261111T120000Z-0002", None), ("sm-20261111T120000Z-0003", "needs_operator"),
                             ("sm-20261111T120000Z-0004", "not_a_spec_question")):
            self.question(qid, verdict)
            for seat in (None, "implementer"):
                for rests_on in (qid, f"{resolved} and {qid}"):
                    code, _, err = self.record(check(seat, rests_on=rests_on, **unrun))
                    self.assertEqual(code, 1, (qid, seat, rests_on))
                    self.assertIn("checks[0] (data-01): rests_on", err)
                    self.assertIn(f"spec question {qid} has no answer at verdict resolved", err)
                    self.assertFalse(self.written().exists())

    def test_an_answer_without_its_question_file_is_no_ruling(self):
        qid = self.question("sm-20261111T120000Z-0005", "resolved")
        (self.q / "questions" / f"{qid}.json").unlink()
        for seat in (None, "implementer"):
            code, _, err = self.record(check(seat, rests_on=f"the lead's answer to {qid}", ran=False, **{"pass": None}))
            self.assertEqual(code, 1, seat)
            self.assertIn("checks[0] (data-01): rests_on", err)
            self.assertIn(f"no gate or spec question {qid} is in the queue", err)
            self.assertFalse(self.written().exists())

    def test_a_cited_gate_file_names_the_gate_it_is_filed_as_and_its_task(self):
        unrun = {"ran": False, "pass": None}
        for fields in ({"escalation_id": f"{TASK}-2"}, {"task_id": "0002-b"}, {"escalation_id": None}):
            gate = self.gate(1, **fields)
            for seat in (None, "implementer"):
                code, _, err = self.record(check(seat, rests_on=f"the lead's ruling, gate {gate}", **unrun))
                self.assertEqual(code, 1, (fields, seat))
                self.assertIn("checks[0] (data-01): rests_on", err)
                self.assertIn(f"gate {gate} (its file names task", err)
                self.assertFalse(self.written().exists())
        self.gate(1)
        code, _, err = self.record(check(None, rests_on=f"the lead's ruling, gate {TASK}-1", **unrun))
        self.assertEqual(code, 0, err)
        # Another task's gate, filed as itself, is a ruling too: the check is the file's integrity only.
        other = self.gate(1, task="0002-b")
        code, _, err = self.record(check(None, rests_on=f"the lead's ruling, gate {other}", **unrun))
        self.assertEqual(code, 0, err)

    def test_the_example_checks_the_verifier_is_shown_are_valid(self):
        for doc in ("templates/prompts/verify.md", "plugin/agents/delivery-verifier.md"):
            shown = [json.loads(m) for m in re.findall(r'`(\{"dod_check_id".*?\})`', (ROOT / doc).read_text())]
            self.assertEqual([c.get("ran", True) for c in shown], [True, False], doc)
            for c in shown:
                code, _, err = self.record(c)
                self.assertEqual(code, 0, (doc, c, err))
                self.written().unlink()

    def test_a_date_beside_a_ruling_reads_as_an_unknown_gate_id_and_is_refused(self):
        # Decided: refuse. A date is shaped like a gate id (`<digits>-<slug>-<digits>`), and the ruling
        # form allows no unknown id beside a known one, so the verifier writes the date another way.
        gate = self.gate(1)
        for rests_on in (f"the lead's ruling, gate {gate}, 2026-11-12", f"gate {gate} (decided 2026-11-12)"):
            code, _, err = self.record(check(None, rests_on=rests_on, ran=False, **{"pass": None}))
            self.assertEqual(code, 1, rests_on)
            self.assertIn("2026-11-12", err)
            self.assertFalse(self.written().exists())
        code, _, err = self.record(check(None, rests_on=f"the lead's ruling, gate {gate}, 12 November 2026",
                                         ran=False, **{"pass": None}))
        self.assertEqual(code, 0, err)

    def test_a_ruling_id_inside_a_longer_token_is_not_one(self):
        gate = self.gate(1)
        question = self.question("sm-20261111T120000Z-ab12", "resolved")
        for rests_on in (f"x{gate}", f"gate-{gate}", f"{gate}x", f"{gate}-", f"x{question}", f"{question}9"):
            code, _, err = self.record(check(None, rests_on=rests_on, ran=False, **{"pass": None}))
            self.assertEqual(code, 1, rests_on)
            self.assertIn("names no ruling id", err)
            self.assertFalse(self.written().exists())

    def commit(self) -> str:
        """A commit in the product checkout, as a carried verdict's old head."""
        def git(*a: str) -> str:
            return subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("add", "-A")
        git("commit", "-qm", "init")
        return git("rev-parse", "HEAD")

    def test_a_check_not_run_rests_on_a_ruling_a_carried_verdict_or_the_operators_evidence(self):
        sha = self.commit()
        unrun = {"ran": False, "pass": None}
        for seat, rests_on in (("implementer", self.gate(1)), ("verifier", f"approve at {sha}"),
                               ("reviewer", f"approve at {sha[:12]}"), (None, f"approve at {sha}"),
                               ("operator", "the operator's paste, 15:49"), ("operator", f"approve at {'c' * 40}")):
            code, _, err = self.record(check(seat, rests_on=rests_on, **unrun))
            self.assertEqual(code, 0, (seat, rests_on, err))
            self.written().unlink()
        code, _, err = self.record(check("verifier", rests_on="a check it ran rests on nothing"))
        self.assertEqual(code, 0, err)

    def test_a_check_not_run_on_anything_else_is_refused_naming_it(self):
        sha = self.commit()
        unrun = {"ran": False, "pass": None}
        for seat, rests_on, needle in (
                ("verifier", "the operator's paste, 15:49", "names no ruling id"),
                ("implementer", "the lead said so", "names no ruling id"),
                ("verifier", f"approve at {'c' * 40}", f"{'c' * 40} does not resolve to a commit"),
                ("verifier", f"approve at {sha}, see the notes", "names no ruling id"),
                ("verifier", f"approved at {sha}", "names no ruling id"),
                ("implementer", f"{TASK}-9", f"{TASK}-9")):
            code, _, err = self.record(check("verifier", dod_check_id="cmd-01"),
                                       check(seat, rests_on=rests_on, **unrun))
            self.assertEqual(code, 1, (seat, rests_on))
            self.assertIn("checks[1] (data-01): rests_on", err)
            self.assertNotIn("checks[0]", err)
            self.assertIn(needle, err)
            self.assertFalse(self.written().exists())

    def test_check_and_merge_ok_read_a_record_whose_ruling_names_no_id(self):
        rec = approve(TASK, checked_at=now_iso(),
                      checks=[check(None, ran=False, rests_on="the lead said so", **{"pass": None})])
        (self.q / "pr.json").write_text(json.dumps(self.pr))
        self.written().parent.mkdir(exist_ok=True)
        self.written().write_text(json.dumps(rec))
        code, _, err = self.ccp("verify", "check", TASK, "--head", HEAD_A)
        self.assertEqual(code, 0, err)
        code, _, err = self.ccp("verify", "merge-ok", "7", "--task", TASK)
        self.assertEqual(code, 0, err)

    def test_seats_that_do_not_rule_may_produce_evidence(self):
        schema = json.loads((ROOT / "contracts/verification.schema.json").read_text())
        seats = schema["properties"]["checks"]["items"]["properties"]["produced_by"]["enum"]
        for seat in sorted(set(seats) - {"lead", "runner"}):
            code, _, err = self.record(check(seat))
            self.assertEqual(code, 0, (seat, err))

    def test_an_approved_operator_step_counts(self):
        step = self.gate(1)
        standing = self.gate(2, decided_by="standing", authority="docs/plan.md#r2")
        for seat in ("runner", "lead", "operator"):
            for gate in (step, standing):
                code, out, err = self.record(check(seat, operator_step=gate))
                self.assertEqual(code, 0, (seat, gate, err))
                written = json.loads(self.written().read_text())
                self.assertEqual((written["checks"][0]["produced_by"], written["checks"][0]["operator_step"]),
                                 (seat, gate))

    def test_an_operator_step_that_is_not_an_approved_operator_gate_of_the_task_is_refused(self):
        cases = (
            (self.gate(1, status="open", decision=None), "is not approved"),
            (self.gate(2, status="waiting_operator", decision=None), "is not approved"),
            (self.gate(3, decision="refused"), "is not approved"),
            (self.gate(4, **{"class": "spend"}), "not an operator step"),
            (f"{TASK}-9", "no gate file"),
            (self.gate(1, task="0002-b"), "is not a gate of this task"),
            (self.gate(5, task_id="0002-b"), "not this task and step"),
            (self.gate(6, escalation_id=f"{TASK}-1"), "not this task and step"),
            (TASK, "is not a gate of this task"),
            (f"{TASK}-x", "is not a gate of this task"),
        )
        for seat in ("runner", "verifier"):
            for step, needle in cases:
                code, _, err = self.record(check(seat, operator_step=step))
                self.assertEqual(code, 1, (seat, step))
                self.assertIn(needle, err, (seat, step))
                self.assertIn("checks[0] (data-01)", err)
                self.assertFalse(self.written().exists())

    def test_check_and_merge_ok_read_a_record_without_producers_and_refuse_a_ruling_seats_evidence(self):
        legacy = approve(TASK, checked_at=now_iso(),
                         checks=[{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it"}])
        ruled = approve(TASK, checked_at=now_iso(), checks=[check("lead")])
        stepped = approve(TASK, checked_at=now_iso(), checks=[check("runner", operator_step=self.gate(1))])
        (self.q / "pr.json").write_text(json.dumps(self.pr))
        self.written().parent.mkdir(exist_ok=True)
        for rec, ok in ((legacy, True), (stepped, True), (ruled, False)):
            self.written().write_text(json.dumps(rec))
            code, _, err = self.ccp("verify", "check", TASK, "--head", HEAD_A)
            self.assertEqual(code, 0 if ok else 1, err)
            code, out, err = self.ccp("verify", "merge-ok", "7", "--task", TASK)
            self.assertEqual(code, 0 if ok else 1, err)
            if not ok:
                self.assertIn("produced by the lead", err)
                self.assertIn("checks[0] (data-01)", err)

    def test_the_briefs_name_the_field(self):
        self.assertIn("produced_by", (ROOT / "plugin/agents/delivery-verifier.md").read_text())
        self.assertIn("produced_by", (ROOT / "plugin/agents/delivery-runner.md").read_text())


if __name__ == "__main__":
    unittest.main()
