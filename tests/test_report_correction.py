"""A worker corrects a report it already recorded (SPEC §13.4): `ccp report` takes the corrected one while
no later run of the task has opened, checks it like a first report, keeps the earlier one beside it as
superseded and replaces the run's figures; once a later run opened, the report stays as it is."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from ccp import runs
from tests.helpers import done_report
from tests.review_flow import ReviewFlow
from tests.test_report_fields import HEAD, implement_report
from tests.test_toolkit import ToolkitFixture

A = "a" * 40
REVIEW = "0002-second/review"
IMPLEMENT = "0002-second/implement"


def review_report(beyond: str, severity: str = "BLOCKER=0 MAJOR=1 MINOR=0 NIT=0") -> str:
    return (f"Outcome: done\nSeverity: {severity}\n## Spec beyond intent\n{beyond}\n"
            "## Friction\n- the review brief named a stale path\n")


class Correction(ReviewFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        for where in ("ccp.runs.iso", "ccp.report.iso"):
            patch = mock.patch(where, side_effect=lambda: next(clock))
            patch.start()
            self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def run_rec(self, run_id: str) -> dict:
        return json.loads(runs.path(self.q, run_id).read_text())

    def open_phase(self, phase: str, *args: str) -> str:
        code, body, out, err = self.ccp("prompt", phase, "0002", *args)
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def reported_review(self) -> None:
        self.open_phase("review", "--pr", "7", "--head", A)
        code, _, out, err = self.report(REVIEW, review_report("- §13.4 gains a rule the brief does not ask for"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec(REVIEW)["spec_beyond_intent"], 1)

    def reported_implement(self, *lines: str) -> None:
        self.open_phase("implement", "--base", "abc1234")
        text = done_report("implement", "PR: #7", f"Head: {HEAD}", "Suite: 412 tests, 88.5 s", *lines,
                           friction=("- the same fact sits in three files", "- a test pinned an error's wording"))
        code, _, out, err = self.report(IMPLEMENT, text)
        self.assertEqual(code, 0, out + err)

    def notes(self) -> list[dict]:
        p = self.q / "health/notes.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def metrics(self) -> list[str]:
        p = self.q / "health/metrics.jsonl"
        return p.read_text().splitlines() if p.is_file() else []

    def test_a_corrected_review_replaces_the_stale_count_and_keeps_the_earlier_report(self):
        self.reported_review()
        stored = runs.report_path(self.q, REVIEW)
        first_text, first = stored.read_text(), self.run_rec(REVIEW)
        code, body, out, err = self.report(REVIEW, review_report("none", "BLOCKER=0 MAJOR=0 MINOR=1 NIT=0"))
        self.assertEqual(code, 0, out + err)
        rec = self.run_rec(REVIEW)
        self.assertEqual(rec["spec_beyond_intent"], 0)
        self.assertEqual(rec["severity"], {"BLOCKER": 0, "MAJOR": 0, "MINOR": 1, "NIT": 0})
        self.assertEqual(rec["reported_at"], first["reported_at"])  # the run closed when it first reported
        kept = stored.with_name(f"{stored.stem}.superseded-1.md")
        self.assertEqual(kept.read_text(), first_text)
        self.assertIn("none", stored.read_text())
        self.assertEqual(len(rec["corrections"]), 1)
        self.assertEqual(rec["corrections"][0]["superseded"], str(kept))
        self.assertTrue(rec["corrections"][0]["at"])
        self.assertEqual(body["corrections"], rec["corrections"])
        reported = [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("run", "reported")
                    and e["payload"]["run_id"] == REVIEW]
        self.assertEqual(len(reported), 2)
        self.assertNotIn("corrected", reported[0])
        self.assertIs(reported[1]["corrected"], True)
        recorded = [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("review", "recorded")]
        self.assertEqual([(p["run_id"], p["verdict"]) for p in recorded], [(REVIEW, "changes"), (REVIEW, "clean")])
        self.assertEqual(recorded[1]["severity"]["MINOR"], 1)

    def test_a_second_correction_keeps_both_earlier_reports(self):
        self.reported_review()
        stored = runs.report_path(self.q, REVIEW)
        self.report(REVIEW, review_report("none"))
        second_text = stored.read_text()
        code, _, out, err = self.report(REVIEW, review_report("none", "BLOCKER=0 MAJOR=0 MINOR=0 NIT=1"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(stored.with_name(f"{stored.stem}.superseded-2.md").read_text(), second_text)
        self.assertEqual([c["superseded"] for c in self.run_rec(REVIEW)["corrections"]],
                         [str(stored.with_name(f"{stored.stem}.superseded-{k}.md")) for k in (1, 2)])

    def test_a_report_a_later_run_followed_is_not_corrected(self):
        self.reported_review()
        stored = runs.report_path(self.q, REVIEW)
        fix = self.open_phase("fix", "--pr", "7", "--head", A)
        before_text, before = stored.read_text(), runs.path(self.q, REVIEW).read_text()
        code, _, out, err = self.report(REVIEW, review_report("none"))
        self.assertEqual(code, 1, out + err)
        self.assertIn(fix, err)
        self.assertEqual(stored.read_text(), before_text)
        self.assertEqual(runs.path(self.q, REVIEW).read_text(), before)
        self.assertFalse(stored.with_name(f"{stored.stem}.superseded-1.md").exists())

    def test_a_correction_records_friction_and_suite_numbers_once(self):
        self.reported_implement()
        notes, metrics = self.notes(), self.metrics()
        self.assertEqual(len([n for n in notes if n["task_id"] == "0002-second"]), 2)
        code, body, out, err = self.report(IMPLEMENT, "\n".join([
            "Outcome: blocked", "Suite: 412 tests, 88.5 s", "## Friction", "- the same fact sits in three files",
            "- a test pinned an error's wording", ""]))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.notes(), notes)
        self.assertEqual(self.metrics(), metrics)
        rec = self.run_rec(IMPLEMENT)
        self.assertEqual(rec["outcome"], "blocked")
        self.assertEqual(rec["friction_count"], 2)
        for gone in ("pr", "head"):  # the corrected report states none: nothing is left from the earlier one
            self.assertNotIn(gone, rec)
        self.assertEqual(body["outcome"], "blocked")

    def test_a_done_correction_files_no_suite_numbers_again(self):
        self.reported_implement()
        metrics = self.metrics()
        self.assertTrue(metrics)
        code, _, out, err = self.report(IMPLEMENT, done_report("implement", "PR: #8", f"Head: {HEAD}",
                                                               "Suite: 415 tests, 90 s"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.metrics(), metrics)
        rec = self.run_rec(IMPLEMENT)
        self.assertEqual((rec["pr"], rec["suite_tests"], rec["friction_count"]), ("8", 415, 0))

    def test_a_correction_is_checked_like_a_first_report(self):
        self.reported_implement()
        stored = runs.report_path(self.q, IMPLEMENT)
        before_text, before = stored.read_text(), runs.path(self.q, IMPLEMENT).read_text()
        events = len(self.events())
        code, _, out, err = self.report(IMPLEMENT, implement_report(outcome="blocked"), token=False)
        self.assertEqual(code, 2, out + err)
        self.assertIn(self.run_rec(IMPLEMENT)["prompt_token"], err)
        code, _, out, err = self.report(IMPLEMENT, "Outcome: done\n## Friction\nnone\n")
        self.assertEqual(code, 1, out + err)
        self.assertIn("no `Head: <sha>` line", err)
        self.assertEqual(stored.read_text(), before_text)
        self.assertEqual(runs.path(self.q, IMPLEMENT).read_text(), before)
        self.assertEqual(len(self.events()), events)
        self.assertEqual(list(stored.parent.glob("*.superseded-*")), [])

    def test_a_report_corrected_in_place_goes_through_with_nothing_kept(self):
        self.reported_implement()
        stored = runs.report_path(self.q, IMPLEMENT)
        token = self.run_rec(IMPLEMENT)["prompt_token"]
        stored.write_text(f"Outcome: blocked\nPrompt: {token}\n## Friction\nnone\n")
        code, body, out, err = self.ccp("report", IMPLEMENT, str(stored))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec(IMPLEMENT)["outcome"], "blocked")
        self.assertEqual([c["superseded"] for c in self.run_rec(IMPLEMENT)["corrections"]], [None])
        self.assertTrue(any(str(stored) in w for w in body["warnings"]))
        self.assertEqual(list(stored.parent.glob("*.superseded-*")), [])

    def test_a_verify_correction_keeps_the_recorded_verdict(self):
        self.open_phase("review", "--pr", "7", "--head", A)
        self.assertEqual(self.report(REVIEW, review_report("none", "BLOCKER=0 MAJOR=0 MINOR=0 NIT=0"))[0], 0)
        run_id = self.open_phase("verify", "--pr", "7", "--head", A)
        code, _, out, err = self.verdict(A)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(run_id, f"Outcome: done\nVerdict: approve\nHead: {A}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(run_id, f"Outcome: done\nVerdict: reject\nHead: {A}\n## Friction\nnone\n")
        self.assertEqual(code, 1, out + err)  # the verdict still matches `ccp verify record`'s
        self.assertIn("reject", err)
        code, _, out, err = self.report(run_id, "Outcome: blocked\nSuite: 9 tests, 2 s\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        rec = self.run_rec(run_id)
        self.assertEqual((rec["outcome"], rec["verdict"], rec["head"], rec["suite_tests"]), ("blocked", "approve", A, 9))

    def test_an_abandoned_run_is_still_refused(self):
        self.open_phase("review", "--pr", "7", "--head", A)
        self.open_phase("review", "--pr", "7", "--head", A, "--supersede")
        code, _, _, err = self.report(REVIEW, review_report("none"))
        self.assertEqual(code, 1)
        self.assertIn("already abandoned", err)


class OpenedAfter(unittest.TestCase):
    """`runs.opened_after`: the first run of the task opened after the given one."""

    def setUp(self):
        import tempfile  # noqa: PLC0415
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name)

    def put(self, run_id: str, opened_at: str) -> dict:
        task, phase, n = runs.parse_id(run_id)
        rec = {"run_id": run_id, "task_id": task, "phase": phase, "round": n, "opened_at": opened_at}
        runs.save(self.q, rec)
        return rec

    def test_only_a_run_of_the_same_task_opened_later_or_in_the_same_second_counts(self):
        rec = self.put("0002-second/review", "2026-10-22T10:01:00Z")
        self.put("0002-second/implement", "2026-10-22T10:00:00Z")
        self.put("0003-third/fix", "2026-10-22T10:05:00Z")
        self.assertIsNone(runs.opened_after(self.q, rec))
        self.put("0002-second/verify", "2026-10-22T10:01:00Z")
        self.assertEqual(runs.opened_after(self.q, rec)["run_id"], "0002-second/verify")
        self.put("0002-second/fix", "2026-10-22T10:00:59Z")
        self.put("0002-second/merge", "2026-10-22T10:00:30Z")
        self.assertEqual(runs.opened_after(self.q, rec)["run_id"], "0002-second/verify")


if __name__ == "__main__":
    unittest.main()
