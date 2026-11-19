"""Text beyond a task's intent (SPEC §3.5): the verdict's `spec_beyond_intent` makes a build sign-off due on a
task that declares none, `ccp tasks close` holds the merge until the lead records it, and the reviewer's and
the verifier's reports must say what they found (an empty list, or `none`, when nothing)."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, lifecycle, prompt, report, verify
from tests.helpers import Product
from tests.test_toolkit import PLANE, ToolkitFixture
from tests.test_verify import approve

PASSAGE = "docs/spec/01-model.md §3.5: a new rule that close also waits on the lead's word"
SECOND = "contracts/x.schema.json: a new required key"


class CloseHolds(ToolkitFixture, unittest.TestCase):
    """A task with no `sign_off:` and a verdict that lists text beyond its intent."""

    def verdict(self, head: str, beyond: list[str]) -> None:
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head, spec_beyond_intent=beyond)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict-beyond.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)

    def sign(self, *extra: str):
        return self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed the new rule", *extra)

    def signed(self) -> list[dict]:
        return [e for e in self.events() if (e["type"], e["op"]) == ("sign_off", "recorded")]

    def test_close_refuses_naming_the_passage_until_the_build_sign_off_is_recorded(self):
        head = self._to_approved_pr()
        self.verdict(head, [PASSAGE, SECOND])
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("no build sign-off", err)
        self.assertIn(PASSAGE, err)
        self.assertIn(SECOND, err)
        self.assertIn("ccp tasks sign-off 0002-second --stage build", err)
        self.assertFalse((self.ghstate / "merge-called").exists())
        code, body, out, err = self.sign()  # no --stage: build is the one stage due
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["sign_off"]["stage"], body["sign_off"]["head"]), ("build", head))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)

    def test_an_empty_list_needs_no_sign_off(self):
        head = self._to_approved_pr()
        self.verdict(head, [])
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)
        self.assertEqual(self.signed(), [])

    def test_the_latest_verdict_wins_a_reverify_with_none_clears_the_due_sign_off(self):
        head = self._to_approved_pr()
        self.verdict(head, [PASSAGE])
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn(PASSAGE, err)
        self.verdict(head, [])  # the fix round took the passage out; the re-verify lists none
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)
        self.assertEqual(self.signed(), [])

    def test_a_sign_off_is_refused_while_none_is_due(self):
        head = self._to_approved_pr()
        self.verdict(head, [])
        code, _, _, err = self.sign()
        self.assertEqual(code, 2)
        self.assertIn("lists no spec_beyond_intent", err)
        self.verdict(head, [PASSAGE])
        code, _, _, err = self.sign("--stage", "brief")
        self.assertEqual(code, 2)
        self.assertIn("no brief sign-off due", err)
        self.assertEqual(self.signed(), [])

    def test_a_build_sign_off_at_another_head_is_stale_and_names_the_passage(self):
        head = self._to_approved_pr()
        self.verdict(head, [PASSAGE])
        code, _, out, err = self.sign("--head", "1234567")
        self.assertEqual(code, 0, out + err)
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        self.assertIn(PASSAGE, err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_a_review_keeps_only_the_count_of_its_passages_on_its_run(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.report("0002-second/review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 "
                                           f"NIT=0\n## Spec beyond intent\n- {PASSAGE}\n## Friction\nnone\n")
        self.assertEqual((code, body.get("spec_beyond_intent")), (0, 1), out + err)
        run = json.loads((self.q / "runs/0002-second/review.json").read_text())
        self.assertEqual(run["spec_beyond_intent"], 1)
        self.assertNotIn(PASSAGE, json.dumps(run))

    def test_a_verdict_listing_text_beyond_intent_no_longer_refuses_the_catch_up_by_itself(self):
        head = self._to_approved_pr()
        self.verdict(head, [PASSAGE])
        meta = {"task_id": "0002-second", "paths": ["feature.txt"]}
        self.write("docs/delivery/plane.json", json.dumps({k: v for k, v in self.PLANE_JSON.items() if k != "suite"}))
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            with self.assertRaises(lifecycle._NoCatchUp) as cm:
                lifecycle._catch_up(config.load(self.main), self.q, meta, "0002-second", "7", head,
                                    {"head_sha": head}, "main", {})
        # The refusal is the next condition (the product has no gate lane), not the sign-off the verdict made due.
        self.assertIn("no gate lane", str(cm.exception))
        self.assertNotIn("sign-off", str(cm.exception))


class Verdict(unittest.TestCase):
    """`ccp verify record` and the reader: a task's verdict says what it found beyond the task's intent."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def record(self, body: dict):
        src = self.q / "in.json"
        src.write_text(json.dumps(body))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "record", str(src)])
        return code, out.getvalue(), err.getvalue()

    def test_a_task_verdict_without_the_list_is_refused_and_nothing_is_written(self):
        body = approve()
        body.pop("spec_beyond_intent", None)
        for verdict in ("approve", "reject"):
            code, _, err = self.record({**body, "verdict": verdict})
            self.assertEqual(code, 1, err)
            self.assertIn("spec_beyond_intent: missing", err)
            self.assertFalse((self.q / "verification/0001-a.json").exists())

    def test_a_list_that_is_not_of_passages_is_refused(self):
        for bad in ("none", [""], [3]):
            code, _, err = self.record(approve(spec_beyond_intent=bad))
            self.assertEqual(code, 1, (bad, err))
            self.assertIn("spec_beyond_intent", err)

    def test_the_list_is_kept_and_read_back(self):
        code, out, err = self.record(approve(spec_beyond_intent=[PASSAGE]))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "verification/0001-a.json").read_text())["spec_beyond_intent"], [PASSAGE])
        self.assertEqual(verify.beyond_intent(self.q, "0001-a"), [PASSAGE])

    def test_a_pr_verdict_may_leave_it_out(self):
        body = approve("pr-12")
        body.pop("spec_beyond_intent", None)
        code, out, err = self.record(body)
        self.assertEqual(code, 0, out + err)

    def test_passages_add_build_to_the_declared_stages_once(self):
        self.record(approve(spec_beyond_intent=[PASSAGE]))
        for declared, want in ((None, ["build"]), ("brief", ["brief", "build"]), ("build", ["build"]),
                               (["brief", "build"], ["brief", "build"])):
            meta = {"task_id": "0001-a", **({"sign_off": declared} if declared else {})}
            self.assertEqual(lifecycle.due_stages(self.q, meta), (want, [PASSAGE]), declared)
        self.record(approve(spec_beyond_intent=[]))  # the latest verdict wins
        self.assertEqual(lifecycle.due_stages(self.q, {"task_id": "0001-a", "sign_off": "brief"}), (["brief"], []))

    def test_a_record_without_the_field_or_with_none_lists_nothing(self):
        d = self.q / "verification"
        d.mkdir()
        (d / "0001-a.json").write_text(json.dumps({"task_id": "0001-a", "schema_version": 2}))
        self.assertEqual(verify.beyond_intent(self.q, "0001-a"), [])
        self.assertEqual(verify.beyond_intent(self.q, "0009-none"), [])


class ReviewReport(unittest.TestCase):
    """A done review report carries a `## Spec beyond intent` section; the run keeps only its count."""

    HEAD = "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"

    def test_a_done_review_without_the_section_is_refused(self):
        _, errs = report.parse("review", self.HEAD + "## Friction\nnone\n")
        self.assertTrue(any("## Spec beyond intent" in e for e in errs), errs)

    def test_the_section_is_counted(self):
        for section, n in (("none", 0), (f"- {PASSAGE}\n- {SECOND}", 2)):
            got, errs = report.parse("review", self.HEAD + f"## Spec beyond intent\n{section}\n## Friction\nnone\n")
            self.assertEqual((errs, got.get("spec_beyond_intent"), got.get("friction")), ([], n, []))

    def test_a_blocked_review_and_other_phases_need_no_section(self):
        _, errs = report.parse("review", "Outcome: blocked\n## Friction\nnone\n")
        self.assertEqual(errs, [])
        _, errs = report.parse("verify", f"Outcome: done\nVerdict: approve\nHead: {'a' * 40}\n## Friction\nnone\n")
        self.assertEqual(errs, [])


class Briefs(unittest.TestCase):
    """The review and verify prompts and briefs ask for what `ccp report` and `ccp verify record` check."""

    def test_the_reviewer_is_asked_for_the_section_and_the_verifier_for_the_list(self):
        for path, needle in (("templates/prompts/review.md", "## Spec beyond intent"),
                             ("plugin/agents/delivery-reviewer.md", "## Spec beyond intent"),
                             ("templates/prompts/verify.md", "spec_beyond_intent"),
                             ("plugin/agents/delivery-verifier.md", "spec_beyond_intent")):
            self.assertIn(needle, (PLANE / path).read_text(), path)

    def test_the_review_report_lines_name_the_section(self):
        self.assertIn("## Spec beyond intent", prompt.REPORT_LINES["review"])
        self.assertNotIn("Spec beyond intent", prompt.REPORT_LINES["verify"] + prompt.REPORT_LINES["implement"])


if __name__ == "__main__":
    unittest.main()
