"""A check only the operator's machine can run, in the verdict (SPEC §15.4, §15.6 rule 3, §15.8; ADR-0045 D3): an
approve holds it to a passed run at the head under an approved operator step, a verdict it may carry, or a ruling
that waives it, never free text, and `ccp verify record`, `merge-ok` and `check` refuse alike, reading the marked
checks from the task file at the head. Each verify run keeps its verdict's per-check facts for a later carry."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, prhost, runs, verify
from tests.helpers import Product, binding
from tests.test_verify import approve, now_iso

TID = "0002-second"
CID = "mac-01"
STEP = f"{TID}-1"
RULING = f"{TID}-2"  # a gate that is not of class operator: a ruling
H, OLD, OLDER = "1" * 40, "2" * 40, "3" * 40
MARKED = f"""- id: `{CID}`
  story: As the operator, it runs on my machine.
  setup: a checkout of the head.
  runs_on: operator-machine
  steps:
    1. run it
  expect: exit 0

## Implementation notes"""


def row(sid: str, head: str, lane: str = CID, task: str = TID, state: str = "passed") -> dict:
    """A suite run as `suite.fold` gives it."""
    return {"suite_id": sid, "lane": lane, "task_id": task, "head": head, "state": state}


def ran(sid: str | None = "st-h", step: str | None = STEP, seat: str = "runner", passed: bool = True) -> dict:
    """The marked check as the verifier records the runner's run of it."""
    c = {"dod_check_id": CID, "pass": passed, "evidence": "the runner's run at the head", "produced_by": seat}
    return {**c, **({"operator_step": step} if step else {}), **({"suite_id": sid} if sid else {})}


def resting(on: str, seat: str | None = "verifier") -> dict:
    """The marked check recorded not run, resting on `on`: the verifier names itself for a carried verdict."""
    return {"dod_check_id": CID, "ran": False, "pass": None, "rests_on": on, "evidence": "not run here",
            **({"produced_by": seat} if seat else {})}


def verdict(*checks: dict, head: str = H) -> dict:
    return approve(TID, head_sha=head, checked_at=now_iso(),
                   checks=[{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"},
                           *checks])


def approved_at(head: str, *facts: dict, run_id: str = f"{TID}/verify") -> dict:
    """A verify run that recorded an approve at `head`, with the per-check facts it kept."""
    return {"run_id": run_id, "phase": "verify", "verdict": "approve", "head": head, "checks": list(facts)}


PASS_AT_OLD = {"id": CID, "ran": True, "pass": True, "produced_by": "runner", "operator_step": STEP, "suite_id": "st-old"}


class MarkedErrors(unittest.TestCase):
    """`verify.marked_errors` on plain values."""

    SUITES = [row("st-h", H), row("st-old", OLD), row("st-older", OLDER)]

    def errors(self, *checks: dict, marked: tuple = (CID,), suites: list | None = None, verifies: tuple = (),
               steps: frozenset = frozenset({STEP}), rulings: frozenset = frozenset()) -> list[str]:
        return verify.marked_errors(verdict(*checks), list(marked), self.SUITES if suites is None else suites,
                                    list(verifies), set(steps), set(rulings))

    def test_a_passed_run_at_the_head_under_an_approved_step_is_accepted(self):
        self.assertEqual(self.errors(ran()), [])
        self.assertEqual(self.errors(ran(seat="operator")), [])

    def test_a_marked_check_missing_from_the_record_is_refused_naming_it(self):
        errs = self.errors()
        self.assertEqual(len(errs), 1, errs)
        self.assertIn(CID, errs[0])
        self.assertIn("missing", errs[0])

    def test_a_run_naming_no_approved_operator_step_is_refused_whoever_produced_it(self):
        for seat in ("operator", "verifier", "runner"):
            errs = self.errors(ran(step=None, seat=seat))
            self.assertEqual(len(errs), 1, (seat, errs))
            self.assertIn("operator_step", errs[0])
        self.assertTrue(self.errors(ran(), steps=frozenset()))  # named, but not an approved gate of the task

    def test_a_run_naming_no_passed_run_of_its_lane_at_the_head_is_refused(self):
        for check, suites in ((ran(sid=None), None), (ran(sid="st-none"), None), (ran(sid="st-old"), None),
                              (ran(), [row("st-h", H, state="failed")]), (ran(), [row("st-h", H, lane="gate")]),
                              (ran(), [row("st-h", H, task="0001-first")]), (ran(), [row("st-h", "")])):
            errs = self.errors(check, suites=suites)
            self.assertEqual(len(errs), 1, (check, suites, errs))
            self.assertIn("suite", errs[0])

    def test_ran_false_on_free_text_operator_evidence_is_refused(self):
        errs = self.errors(resting("The operator's live run, pasted into the task notes", seat="operator"))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn(CID, errs[0])
        self.assertIn("free-text", errs[0])

    def test_free_text_is_still_accepted_for_an_unmarked_check(self):
        self.assertEqual(self.errors(resting("The operator's live run", seat="operator"), marked=()), [])

    def test_a_marked_check_waived_by_a_ruling_is_accepted(self):
        self.assertEqual(self.errors(resting(RULING, seat=None), rulings=frozenset({RULING})), [])

    def test_operator_evidence_is_never_a_waiver_even_naming_a_ruling(self):
        errs = self.errors(resting(RULING, seat="operator"), rulings=frozenset({RULING}))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("never a ruling", errs[0])

    def test_a_checks_suite_id_is_an_id(self):
        self.assertEqual(verify.record_errors(verdict(ran())), [])
        self.assertTrue(verify.record_errors(verdict(ran(sid="the runner's run, pasted"))))

    def test_a_failed_marked_check_is_left_to_the_approve_rule(self):
        self.assertEqual(self.errors(ran(passed=False)), [])

    def test_a_carry_from_a_qualifying_verdict_needs_no_run_at_the_new_head(self):
        self.assertEqual(self.errors(resting(f"approve at {OLD}"), suites=[row("st-old", OLD)],
                                     verifies=(approved_at(OLD, PASS_AT_OLD),)), [])

    def test_a_carry_from_a_qualifying_carry_is_accepted(self):
        carried = {"id": CID, "ran": False, "pass": None, "produced_by": "runner", "operator_step": STEP,
                   "suite_id": "st-older"}
        self.assertEqual(self.errors(resting(f"approve at {OLD[:12]}"), suites=[row("st-older", OLDER)],
                                     verifies=(approved_at(OLD, carried),)), [])

    def test_a_carry_from_a_free_text_verdict_is_refused(self):
        free = {"id": CID, "ran": False, "pass": None, "produced_by": "operator"}
        errs = self.errors(resting(f"approve at {OLD}"), verifies=(approved_at(OLD, free),))
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("may not carry", errs[0])

    def test_a_carry_the_run_at_old_kept_no_qualifying_facts_for_is_refused(self):
        other_head = {**PASS_AT_OLD, "suite_id": "st-h"}  # its run was at another head than <old>
        for verifies in ((), (approved_at(OLDER, PASS_AT_OLD),), ({**approved_at(OLD), "checks": None},),
                         (approved_at(OLD, {**PASS_AT_OLD, "id": "cmd-01"}),),
                         ({**approved_at(OLD, PASS_AT_OLD), "verdict": "reject"},),
                         (approved_at(OLD, {**PASS_AT_OLD, "operator_step": None}),),
                         (approved_at(OLD, {**PASS_AT_OLD, "pass": False}),),
                         (approved_at(OLD, other_head),)):
            errs = self.errors(resting(f"approve at {OLD}"), verifies=verifies)
            self.assertEqual(len(errs), 1, (verifies, errs))
            self.assertIn("may not carry", errs[0])


class CheckFacts(unittest.TestCase):
    """`runs.check_facts`: ids and booleans of each check, a carry keeping the pass it carries."""

    def test_a_run_check_keeps_its_step_and_suite_run(self):
        facts = runs.check_facts([ran(), {"dod_check_id": "cmd-01", "pass": True, "evidence": "x"}], [])
        self.assertEqual(facts, [{"id": CID, "ran": True, "pass": True, "produced_by": "runner", "operator_step": STEP,
                                  "suite_id": "st-h"},
                                 {"id": "cmd-01", "ran": True, "pass": True}])

    def test_a_carry_keeps_the_pass_it_carries(self):
        facts = runs.check_facts([resting(f"approve at {OLD[:12]}")], [approved_at(OLD, PASS_AT_OLD)])
        self.assertEqual(facts, [{"id": CID, "ran": False, "pass": None, "produced_by": "verifier",
                                  "operator_step": STEP, "suite_id": "st-old"}])

    def test_a_check_not_run_on_anything_else_keeps_neither(self):
        free = {**resting("the operator's word", seat="operator"), "operator_step": STEP, "suite_id": "st-h"}
        self.assertEqual(runs.check_facts([free], []), [{"id": CID, "ran": False, "pass": None,
                                                          "produced_by": "operator"}])
        nothing = runs.check_facts([resting(f"approve at {OLD}")], [approved_at(OLD, {"id": CID, "ran": False})])
        self.assertNotIn("suite_id", nothing[0])


def git(root: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


class RecordAndMerge(unittest.TestCase):
    """`ccp verify record`, `judge` and `merge-ok` on a product checkout whose task file marks the check."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text(binding())
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()
        self.task = self.p.task(TID)
        self.task.write_text(self.task.read_text().replace("## Implementation notes", MARKED, 1))
        root = self.p.root
        git(root, "init", "-q", "-b", "main")
        git(root, "add", ".")
        git(root, "commit", "-q", "-m", "base")
        git(root, "checkout", "-q", "-b", "feat")
        (root / "feature.txt").write_text("the task's change\n")
        git(root, "add", "feature.txt")
        git(root, "commit", "-q", "-m", "task change")
        self.old = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-q", "main")
        (root / "other.txt").write_text("the tip moved\n")
        git(root, "add", "other.txt")
        git(root, "commit", "-q", "-m", "tip change")
        git(root, "checkout", "-q", "feat")
        git(root, "merge", "-q", "--no-edit", "main")  # the head moved only by an integration merge
        self.head = git(root, "rev-parse", "HEAD")
        gate = self.q / "escalations" / TID / "1.json"
        gate.parent.mkdir(parents=True)
        gate.write_text(json.dumps({"task_id": TID, "escalation_id": STEP, "class": "operator", "status": "closed",
                                    "decision": "approved"}))

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def suite_run(self, sid: str, head: str) -> None:
        with (self.q / "runs" / "_suites.jsonl").open("a") as fh:
            fh.write(json.dumps({"op": "started", "suite_id": sid, "at": "2026-10-22T10:00:00Z", "lane": CID,
                                 "task_id": TID, "head": head}) + "\n")
            fh.write(json.dumps({"op": "ended", "suite_id": sid, "at": "2026-10-22T10:01:00Z", "exit_code": 0}) + "\n")

    def put_run(self, name: str, at: str, **fields: object) -> None:
        phase = name.split("-")[0]
        path = self.q / "runs" / TID / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"run_id": f"{TID}/{name}", "task_id": TID, "phase": phase, "opened_at": at,
                                    **fields}))

    def run_rec(self, name: str) -> dict:
        return json.loads((self.q / "runs" / TID / f"{name}.json").read_text())

    def earlier_approve(self) -> None:
        """The task's first verify run approved `old`, with the marked check's passed run there."""
        (self.q / "runs").mkdir(exist_ok=True)
        self.suite_run("st-old", self.old)
        self.put_run("verify", "2026-10-22T10:00:00Z", verdict="approve", head=self.old, reported_at="2026-10-22T10:05:00Z",
                 outcome="done", checks=runs.check_facts([ran(sid="st-old")], []))

    def record(self, *checks: dict) -> tuple[int, str]:
        src = self.q / "in.json"
        src.write_text(json.dumps(verdict(*checks, head=self.head)))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "record", str(src)])
        return code, out.getvalue() + err.getvalue()

    def test_an_approve_with_a_passed_run_at_the_head_is_recorded_and_its_run_keeps_the_facts(self):
        (self.q / "runs").mkdir(exist_ok=True)
        self.suite_run("st-h", self.head)
        self.put_run("verify", "2026-10-22T10:00:00Z")
        code, out = self.record(ran())
        self.assertEqual(code, 0, out)
        kept = {f["id"]: f for f in self.run_rec("verify")["checks"]}
        self.assertEqual(kept[CID], {"id": CID, "ran": True, "pass": True, "produced_by": "runner",
                                     "operator_step": STEP, "suite_id": "st-h"})

    def test_record_refuses_free_text_and_a_missing_marked_check(self):
        code, out = self.record(resting("The operator's live run", seat="operator"))
        self.assertEqual(code, 1, out)
        self.assertIn("free-text", out)
        code, out = self.record()
        self.assertEqual(code, 1, out)
        self.assertIn("missing", out)
        self.assertFalse((self.q / "verification" / f"{TID}.json").exists())

    def test_the_tasks_operator_gate_cited_as_a_waiver_is_refused(self):
        for check in (resting(f"The operator's live run, pasted into the task notes, under gate {STEP}", seat="operator"),
                      resting(STEP), resting(f"run under {STEP}", seat=None)):
            code, out = self.record(check)
            self.assertEqual(code, 1, (check, out))
            self.assertIn(CID, out)
        self.assertFalse((self.q / "verification" / f"{TID}.json").exists())

    def test_a_waiver_by_a_gate_that_is_not_an_operator_gate_is_recorded(self):
        gate = self.q / "escalations" / TID / "2.json"
        gate.write_text(json.dumps({"task_id": TID, "escalation_id": RULING, "class": "other", "status": "closed",
                                    "decision": "approved"}))
        (self.q / "runs").mkdir(exist_ok=True)
        self.put_run("verify", "2026-10-22T10:00:00Z")
        code, out = self.record(resting(f"waived under {RULING}, beside {STEP}"))
        self.assertEqual(code, 0, out)

    def test_a_carry_after_an_integration_merge_is_recorded_with_no_run_at_the_new_head(self):
        self.earlier_approve()
        self.put_run("verify-2", "2026-10-22T11:00:00Z")
        code, out = self.record(resting(f"approve at {self.old}"))
        self.assertEqual(code, 0, out)
        kept = {f["id"]: f for f in self.run_rec("verify-2")["checks"]}
        self.assertEqual((kept[CID]["operator_step"], kept[CID]["suite_id"]), (STEP, "st-old"))

    def test_a_carry_after_a_resolution_review_that_does_not_list_it_is_recorded(self):
        self.earlier_approve()
        self.put_run("merge", "2026-10-22T10:30:00Z", reported_at="2026-10-22T10:40:00Z", outcome="done")
        self.put_run("review", "2026-10-22T10:50:00Z", reported_at="2026-10-22T10:55:00Z", outcome="done",
                 mode="resolution", resolution="contained", head=self.head, affected_checks=["cmd-01"])
        self.put_run("verify-2", "2026-10-22T11:00:00Z")
        code, out = self.record(resting(f"approve at {self.old}"))
        self.assertEqual(code, 0, out)

    def test_judge_and_merge_ok_read_the_marked_checks_from_the_task_file_at_the_head(self):
        self.task.write_text(self.task.read_text().replace("  runs_on: operator-machine\n", ""))  # the checkout's copy
        rec = verdict(head=self.head)  # no marked check in it
        reasons = verify.judge(self.p.cfg, self.q, rec, TID, self.head)[0]
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn(CID, reasons[0])
        rec_path = self.q / "verification" / f"{TID}.json"
        rec_path.parent.mkdir()
        rec_path.write_text(json.dumps(rec))
        facts = prhost.PrFacts(number=7, state="open", head=self.head)
        with mock.patch.object(prhost, "view", return_value=facts):
            reasons, _ = verify.merge_ok(self.p.cfg, self.q, "7", TID)
        self.assertTrue(any(CID in r for r in reasons), reasons)
        git(self.p.root, "commit", "-q", "-am", "unmark")  # a head whose task file marks nothing
        unmarked = git(self.p.root, "rev-parse", "HEAD")
        self.task.write_text(self.task.read_text().replace("## Implementation notes", MARKED, 1))
        self.assertEqual(verify.judge(self.p.cfg, self.q, verdict(head=unmarked), TID, unmarked)[0], [])

    def test_a_head_this_checkout_does_not_hold_is_refused_when_its_copy_marks_a_check(self):
        reasons = verify.judge(self.p.cfg, self.q, verdict(head=H), TID, H)[0]
        self.assertEqual(len(reasons), 1, reasons)
        self.assertIn("git fetch", reasons[0])


if __name__ == "__main__":
    unittest.main()
