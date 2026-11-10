"""The seat that rules never produces the evidence it rules on (SPEC §2.3, §15.4): each check of a
verify record names the seat that produced its evidence, and `ccp verify` refuses evidence from a
ruling seat unless it is an operator step the operator approved."""
from __future__ import annotations

import io
import json
import os
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
