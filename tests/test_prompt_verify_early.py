"""`ccp prompt verify` refuses up front what `ccp verify record` would refuse after the verifier's round (SPEC §6.7,
§15.4; ADR-0045 D3): under `adr.strict`, a head that records a decision the task cites as `not_built`; and a
`--waived` ruling whose only ids are operator gates. And the judge of a marked check `ran: false` keys on what it
rests on, not on who produced the record."""
from __future__ import annotations

import json
import unittest

from ccp import adr, verify
from tests.helpers import as_lead
from tests.report_helpers import approve_verdict, MARKED_BLOCK, MARKED_CHECK_ID as CHECK, MARKED_TASK_ID as TASK
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

OPERATOR_GATE = f"{TASK}-1"


def adr_text(d1: str) -> str:
    """ADR-0001 with its D1 in the state `d1`."""
    return adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted", "date": "2026-01-01",
                     "decisions": [f"D1 {d1}"]}) + "# ADR-0001 — T\n\n## Decision\n\n### D1. First\n\nOne.\n"


class EarlyRefusal(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "adr": {"dir": "docs/adr", "strict": True}}

    def setUp(self):
        super().setUp()
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def head(self, d1: str = "built", cites: bool = True) -> str:
        """The task branch's head: ADR-0001 with D1 in the state `d1`, and the task file citing it when `cites`."""
        m = self.main
        git(m, "checkout", "-q", "-b", "feat")
        self.write("docs/adr/0001-a.md", adr_text(d1))
        if cites:
            task = m / f"docs/delivery/tasks/{TASK}.md"
            task.write_text(task.read_text().replace('spec_refs: ["S1"]\n', 'spec_refs: ["S1"]\nadr_refs: ["ADR-0001 D1"]\n', 1))
        git(m, "add", "-A")
        git(m, "commit", "-q", "-m", "the task's change")
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return head

    def verify(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)

    def opened(self) -> bool:
        return any(p.name.startswith("verify") for p in (self.q / "runs" / TASK).glob("*.json"))

    def assert_refused(self, got: tuple, *names: str) -> None:
        code, _, out, err = got
        self.assertEqual(code, 1, out + err)
        for name in names:
            self.assertIn(name, err)
        self.assertFalse(self.opened(), "nothing opened")

    # ------------------------------------------------------------------ the in-force check (§6.7)

    def test_a_head_that_records_a_cited_decision_not_built_is_refused_before_a_verifier_starts(self):
        head = self.head("not_built")
        before = self.ops()
        self.assert_refused(self.verify(head), "ADR-0001 D1", "`ccp adr decide 1 D1 built`")
        self.assertEqual(self.ops(), before, "no event")

    def test_the_same_task_with_the_decision_built_opens_the_verify(self):
        code, body, out, err = self.verify(self.head("built"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], f"{TASK}/verify")

    def test_a_review_of_that_head_is_not_held_back(self):
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", self.head("not_built"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], f"{TASK}/review")

    def test_a_head_the_checkout_lacks_is_refused_with_nothing_to_flip(self):
        task = self.runner / f"docs/delivery/tasks/{TASK}.md"
        task.write_text(task.read_text().replace('spec_refs: ["S1"]\n', 'spec_refs: ["S1"]\nadr_refs: ["ADR-0001 D1"]\n', 1))
        got = self.verify("0123456789abcdef0123456789abcdef01234567")
        self.assert_refused(got, "not in this checkout", "Fetch the head")
        self.assertNotIn("ccp prompt fix", got[3])

    def test_a_decision_the_task_does_not_cite_is_not_judged(self):
        code, _, out, err = self.verify(self.head("not_built", cites=False))
        self.assertEqual(code, 0, out + err)

    # ------------------------------------------------------------------ the waiver (§15.4, ADR-0045 D3)

    def mark(self) -> None:
        """The claimed task gets the check `CHECK`, marked `runs_on: operator-machine`, and an approved operator
        gate."""
        task = self.runner / f"docs/delivery/tasks/{TASK}.md"
        task.write_text(task.read_text().replace("## Implementation notes", MARKED_BLOCK, 1))
        gate = self.q / "escalations" / TASK / "1.json"
        gate.parent.mkdir(parents=True)
        gate.write_text(json.dumps({"task_id": TASK, "escalation_id": OPERATOR_GATE, "class": "operator",
                                    "status": "closed", "decision": "approved"}))

    def test_a_waiver_naming_only_an_operator_gate_is_refused(self):
        self.mark()
        head = self.head()
        self.assert_refused(self.verify(head, "--waived", f"{CHECK}={OPERATOR_GATE}"), CHECK, OPERATOR_GATE)

    def test_a_waiver_naming_a_lead_ruling_opens_the_verify(self):
        self.mark()
        head = self.head()
        with as_lead():
            code, _, out, err = self.ccp("tasks", "ruling", "0002", "--words", "the live check is waived this round")
        self.assertEqual(code, 0, out + err)
        ruling = json.loads(out)["id"]
        code, body, out, err = self.verify(head, "--waived", f"{CHECK}={ruling}")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], f"{TASK}/verify")


class WaivedWhoeverProducedIt(unittest.TestCase):
    """`verify.marked_errors` on plain values: a marked check `ran: false` is judged on its `rests_on`."""

    RULING = f"{TASK}-r1"

    def errors(self, rests_on: str) -> list[str]:
        check = {"dod_check_id": CHECK, "ran": False, "pass": None, "rests_on": rests_on, "evidence": "not run here",
                 "produced_by": "operator"}
        rec = approve_verdict(TASK, checks=[check])
        return verify.marked_errors(rec, [CHECK], [], [], set(), {self.RULING})

    def test_operator_produced_resting_on_a_recorded_lead_ruling_is_accepted(self):
        self.assertEqual(self.errors(self.RULING), [])

    def test_operator_produced_free_text_is_refused(self):
        errs = self.errors("The operator's live run, pasted into the task notes")
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("free-text operator evidence", errs[0])


if __name__ == "__main__":
    unittest.main()
