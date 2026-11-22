"""A check the verifier recorded not run, and that rests on no carried verdict, may be run after its task
closed (SPEC §15.4): `ccp verify later` records its result beside the verdict record, held to the verdict's
producer rule, and `ccp verify deferred` lists each such check of a done task as open, passed or failed."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, verify
from tests.helpers import Product
from tests.test_verify import now_iso

TASK = "0001-a"
RULED, CARRIED, RAN = "live-01", "cmd-01", "cmd-02"


def closed_record(task: str = TASK) -> dict:
    """A verdict record as `ccp verify record` writes it: one check closed by a ruling, one carried from an
    earlier head, one the verifier ran."""
    return {"task_id": task, "verdict": "approve", "head_sha": "a" * 40, "checked_at": now_iso(),
            "checks": [
                {"dod_check_id": RULED, "ran": False, "pass": None, "rests_on": f"{task}-1",
                 "evidence": "needs the merged code deployed"},
                {"dod_check_id": CARRIED, "ran": False, "pass": None, "rests_on": "approve at " + "b" * 40,
                 "evidence": "carried"},
                {"dod_check_id": RAN, "pass": True, "evidence": "ran it", "produced_by": "verifier"}]}


class Later(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.p.task(TASK, status="done")
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()
        self.task_state(TASK, "done")
        self.verdict(closed_record())

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def task_state(self, task: str, status: str) -> None:
        d = self.q / "tasks"
        d.mkdir(exist_ok=True)
        (d / f"{task}.json").write_text(json.dumps({"task_id": task, "status": status}))

    def verdict(self, rec: dict) -> None:
        d = self.q / "verification"
        d.mkdir(exist_ok=True)
        (d / f"{rec['task_id']}.json").write_text(json.dumps(rec))

    def gate(self, n: int, **fields: object) -> str:
        """An operator gate of the task as `team.sh gate` writes it (§17.9), approved unless `fields` say otherwise."""
        g = {"task_id": TASK, "project_id": "demo", "escalation_id": f"{TASK}-{n}", "class": "operator",
             "status": "closed", "decision": "approved", **fields}
        d = self.q / "escalations" / TASK
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{n}.json").write_text(json.dumps(g))
        return f"{TASK}-{n}"

    def later(self, *extra: str, task: str = TASK, check: str = RULED, result: str = "--pass",
              evidence: str = "the step on the live system printed ok", seat: str = "operator") -> tuple[int, str, str]:
        return self.ccp("verify", "later", task, "--check", check, result, "--evidence", evidence,
                        "--produced-by", seat, *extra)

    def rows(self, task: str = TASK) -> list[dict]:
        return verify.later_rows(self.q, task)

    def deferred(self, *extra: str) -> list[dict]:
        code, out, err = self.ccp("verify", "deferred", "--json", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def assert_refused(self, result: tuple[int, str, str], *names: str) -> None:
        code, _, err = result
        self.assertEqual(code, 2, err)
        for name in names:
            self.assertIn(name, err)
        self.assertFalse(verify.later_path(self.q, TASK).exists())

    def test_a_pass_on_a_ruled_check_writes_one_row_and_lists_it_passed(self):
        code, out, err = self.later()
        self.assertEqual(code, 0, err)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual({k: row[k] for k in ("task_id", "dod_check_id", "pass", "produced_by", "operator_step")},
                         {"task_id": TASK, "dod_check_id": RULED, "pass": True, "produced_by": "operator",
                          "operator_step": None})
        self.assertEqual(set(row), {"task_id", "dod_check_id", "pass", "evidence", "produced_by", "operator_step",
                                    "at", "by"})
        self.assertTrue(row["evidence"] and row["at"] and row["by"])
        self.assertEqual(json.loads(out)["dod_check_id"], RULED)
        self.assertEqual(self.deferred(), [{"task_id": TASK, "dod_check_id": RULED, "state": "passed"}])

    def test_the_verdict_record_is_left_as_it_was(self):
        path = self.q / "verification" / f"{TASK}.json"
        before = path.read_text()
        self.assertEqual(self.later()[0], 0)
        self.assertEqual(path.read_text(), before)

    def test_the_task_argument_takes_the_task_number(self):
        self.assertEqual(self.later(task=TASK.split("-")[0])[0], 0)
        self.assertEqual(self.rows()[0]["task_id"], TASK)

    def test_a_check_with_no_result_is_open_and_counted(self):
        self.assertEqual(self.deferred(), [{"task_id": TASK, "dod_check_id": RULED, "state": "open"}])
        code, out, _ = self.ccp("verify", "deferred")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [f"{TASK} {RULED} open", "1 open, 0 failed"])

    def test_a_failed_result_is_listed_failed_and_counted(self):
        self.assertEqual(self.later(result="--fail")[0], 0)
        self.assertIs(self.rows()[0]["pass"], False)
        self.assertEqual(self.deferred()[0]["state"], "failed")
        code, out, _ = self.ccp("verify", "deferred")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [f"{TASK} {RULED} failed", "0 open, 1 failed"])

    def test_a_check_recorded_again_takes_its_latest_result(self):
        self.assertEqual(self.later(result="--fail")[0], 0)
        self.assertEqual(self.later()[0], 0)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.deferred()[0]["state"], "passed")

    def test_deferred_lists_only_done_tasks_and_filters_by_task(self):
        other = "0002-b"
        self.p.task(other, status="done")
        self.task_state(other, "done")
        self.verdict(closed_record(other))
        self.task_state("0003-c", "merging")
        self.verdict(closed_record("0003-c"))
        self.assertEqual([(r["task_id"], r["state"]) for r in self.deferred()], [(TASK, "open"), (other, "open")])
        self.assertEqual([r["task_id"] for r in self.deferred("--task", "0002")], [other])

    def test_deferred_on_an_empty_queue_is_an_empty_list(self):
        (self.q / "verification" / f"{TASK}.json").unlink()
        self.assertEqual(self.deferred(), [])

    def test_a_task_not_done_is_refused(self):
        self.task_state(TASK, "merging")
        self.assert_refused(self.later(), "merging", "not done")

    def test_a_task_with_no_verification_record_is_refused(self):
        (self.q / "verification" / f"{TASK}.json").unlink()
        self.assert_refused(self.later(), "no verification record")

    def test_a_check_the_record_does_not_hold_is_refused(self):
        self.assert_refused(self.later(check="nope-01"), "'nope-01'")

    def test_a_check_verify_ran_is_refused(self):
        self.assert_refused(self.later(check=RAN), f"{RAN!r}", "run at verify")

    def test_a_check_on_a_carried_verdict_is_refused(self):
        self.assert_refused(self.later(check=CARRIED), f"{CARRIED!r}", "carried verdict")

    def test_evidence_that_is_empty_is_refused(self):
        self.assert_refused(self.later(evidence="  "), "--evidence is empty")

    def test_evidence_over_the_limit_is_refused(self):
        self.assertEqual(self.later(evidence="x" * verify.EVIDENCE_MAX)[0], 0)
        verify.later_path(self.q, TASK).unlink()
        self.assert_refused(self.later(evidence="x" * (verify.EVIDENCE_MAX + 1)), str(verify.EVIDENCE_MAX))

    def test_evidence_on_more_than_one_line_is_refused(self):
        self.assert_refused(self.later(evidence="ok\nand more"), "line break")
        self.assert_refused(self.later(evidence="ok\rand more"), "line break")

    def test_evidence_that_looks_like_a_secret_is_refused(self):
        self.assert_refused(self.later(evidence="used ghp_" + "A" * 36), "secret")

    def test_a_seat_the_record_does_not_know_is_refused(self):
        self.assert_refused(self.later(seat="someone"), "'someone'")

    def test_a_ruling_seat_without_an_operator_step_is_refused(self):
        for seat in ("lead", "runner"):
            self.assert_refused(self.later(seat=seat), seat, "--operator-step")

    def test_the_runner_with_an_approved_operator_gate_is_accepted(self):
        step = self.gate(1)
        code, _, err = self.later("--operator-step", step, seat="runner")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.rows()[0]["produced_by"], self.rows()[0]["operator_step"]), ("runner", step))

    def test_an_operator_step_that_is_not_an_approved_operator_gate_is_refused(self):
        cases = {"open": {"status": "open", "decision": None}, "rejected": {"decision": "rejected"},
                 "not operator": {"class": "spec"}}
        for n, (why, fields) in enumerate(cases.items(), start=1):
            step = self.gate(n, **fields)
            self.assert_refused(self.later("--operator-step", step, seat="runner"), step)
        self.assert_refused(self.later("--operator-step", f"{TASK}-9", seat="runner"), f"{TASK}-9")
        self.assert_refused(self.later("--operator-step", "0099-z-1", seat="operator"), "0099-z-1")

    def refused_by_the_parser(self, *args: str) -> str:
        """The parser's refusal of `ccp <args>`: exit 2, nothing on stdout; its stderr."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            cli.main(["--root", str(self.p.root), *args])
        self.assertEqual((cm.exception.code, out.getvalue()), (2, ""), err.getvalue())
        return err.getvalue()

    def test_a_missing_flag_is_refused(self):
        err = self.refused_by_the_parser("verify", "later", TASK, "--check", RULED, "--evidence", "ok",
                                         "--produced-by", "operator")
        self.assertIn("--pass", err)
        self.assertFalse(verify.later_path(self.q, TASK).exists())

    def test_the_other_actions_still_need_their_target(self):
        for action in ("record", "merge-ok", "check", "spec-text", "later"):
            self.refused_by_the_parser("verify", action)

    def test_deferred_refuses_a_task_given_as_a_positional(self):
        err = self.refused_by_the_parser("verify", "deferred", TASK)
        self.assertIn("unrecognized arguments", err)

    def test_later_on_a_task_whose_queue_file_is_not_json_is_refused(self):
        (self.q / "tasks" / f"{TASK}.json").write_text("{not json")
        self.assert_refused(self.later(), f"{TASK}.json")


class LaterRules(unittest.TestCase):
    """The decision on plain values: no queue."""

    def errors(self, status: str | None = "done", rec: object = None, check: str = RULED, evidence: str = "ok",
               seat: str = "operator", step: str | None = None, step_why: str | None = None) -> list[str]:
        return verify.later_errors(status, closed_record() if rec is None else rec, check, evidence, seat, step,
                                   lambda _s: step_why, ("operator", "runner", "lead", "verifier"))

    def test_a_deferred_check_by_the_operator_is_accepted(self):
        self.assertEqual(self.errors(), [])

    def test_every_refusal_is_named_at_once(self):
        errs = self.errors(status=None, check=RAN, evidence="", seat="lead")
        self.assertEqual(len(errs), 4, errs)

    def test_a_named_step_is_judged_whoever_produced_the_evidence(self):
        self.assertEqual(len(self.errors(step="0001-a-1", step_why="not approved")), 1)
        self.assertEqual(self.errors(seat="runner", step="0001-a-1"), [])

    def test_deferred_states_take_each_checks_latest_row(self):
        rows = [{"dod_check_id": RULED, "pass": True}, {"dod_check_id": RULED, "pass": False}]
        self.assertEqual(verify.deferred_states(TASK, closed_record(), rows),
                         [{"task_id": TASK, "dod_check_id": RULED, "state": "failed"}])
        self.assertEqual(verify.deferred_states(TASK, closed_record(), [])[0]["state"], "open")
        self.assertEqual(verify.deferred_states(TASK, None, []), [])


if __name__ == "__main__":
    unittest.main()
