"""ccp architect (SPEC §19): triggers, enforcement at `ccp tasks next`, the run and its triage, end to end
against a stub `claude` (CCP_ARCHITECT_CLAUDE_BIN). Acceptance checks docs/design/architect.md #1, #2 and #6 are named below."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import architect, config
from ccp.queue import lib
from tests.git_helpers import git
from tests.architect_fixture import FINDING, Harness


RULE_COST = {**FINDING, "id": "F02", "title": "Legacy ids kept alive", "category": "rule-cost",
             "fix": "decide", "needs_decision": True, "proposal": "Ask whether old rows may be rewritten."}


class PassIsEnforced(Harness):
    def test_acceptance_1_pass_then_triage_block(self):
        for n in range(1, 5):
            self.merge(n)
        code, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0005-t5"))
        self.assertIn("architect pass due (4 task(s) done since none)", err)  # a notice, within grace
        self.merge(5)
        code, out, _ = self.ccp("tasks", "next")
        self.assertEqual(code, 4)
        self.assertIn("architect pass due: 5 task(s) done since none", out)
        self.assertIn("ccp architect run --detach", out)
        self.stub_report([FINDING])
        code, res, _ = self.dpj("architect", "run")
        self.assertEqual((code, res["outcome"]), (0, "reported"), res)
        rid = res["review_id"]
        # §24: the headless session's telemetry names the project and the seat; its session id is recorded.
        self.assertEqual(Path(str(self.report) + ".otel").read_text(), "ccp.project_id=demo,ccp.seat=architect-pass")
        hu = [json.loads(x) for x in (self.q / "board/headless-usage.jsonl").read_text().splitlines()]
        self.assertEqual((hu[-1]["kind"], hu[-1]["session_id"]), ("architect-pass", "stub"))
        self.assertTrue(rid.startswith("ar-"))
        code, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("0006-t6"))
        self.assertIn(f"report {rid} awaits triage", err)
        self.merge(6)
        self.merge(7)
        code, out, _ = self.ccp("tasks", "next")
        self.assertEqual(code, 4)
        self.assertIn(f"architect report {rid} awaits triage", out)
        code, res, _ = self.dpj("tasks", "next", "--json")
        self.assertEqual((code, res["architect"]["kind"]), (4, "triage"))
        # Triage hands off to the lead; the lead's triage file is applied.
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual((code, res["outcome"], res["actions"][0]["action"]), (0, "sent_async", "send_message_to_lead"))
        self.assertIn("SPEC §19.8", res["actions"][0]["message"])
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "schema_version": 1, "review_id": rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
            "record": f"docs/delivery/reviews/{rid}.md", "commit_sha": None, "tasks_created": [],
            "answered_by": "spec_maintainer",
            "dispositions": [{"finding": "F01", "disposition": "reject", "reason": "intentional"}]}))
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual((code, res["outcome"]), (0, "triaged"), res)
        code, out, _ = self.ccp("tasks", "next")
        self.assertEqual((code, out[:7]), (0, "0008-t8"))

    def test_allow_overdue_overrides_once_and_records_a_note(self):
        for n in range(1, 6):
            self.merge(n)
        code, out, err = self.ccp("tasks", "next", "--allow-overdue", "lead says: after 0006")
        self.assertEqual(code, 0, out + err)
        self.assertIn("overridden once", err)
        note = json.loads((self.q / "health" / "notes.jsonl").read_text().splitlines()[-1])
        self.assertEqual((note["source"], note["task_id"]), ("allow-overdue", "0006-t6"))
        self.assertIn("lead says: after 0006", note["text"])
        self.assertEqual(self.ccp("tasks", "next")[0], 4)  # once: the next call blocks again

    def test_running_pass_does_not_block_and_a_dead_one_is_reaped(self):
        for n in range(1, 6):
            self.merge(n)
        st = {"schema_version": 1, "seen": {}, "reviews": {"ar-20261014T000000Z-abcd": {
            "status": "running", "mode": "pass", "done": [], "started_at": "2026-10-14T00:00:00Z"}}}
        (self.q / "architect.lock").write_text(json.dumps({
            "holder": lib.RUNNER, "pid": 1, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ttl_seconds": 3600, "review_id": "ar-20261014T000000Z-abcd"}))
        (self.q / "architect.json").write_text(json.dumps(st))
        self.assertEqual(self.ccp("tasks", "next")[0], 0)  # running: work goes on beside it
        (self.q / "architect.lock").unlink()
        self.assertEqual(self.ccp("tasks", "next")[0], 4)  # its process is gone: failed, due again
        self.assertEqual(self.state()["reviews"]["ar-20261014T000000Z-abcd"]["status"], "failed")

    def test_failed_pass_restarts_the_grace(self):
        for n in range(1, 6):
            self.merge(n)
        self.report.write_text("not json")
        code, res, _ = self.dpj("architect", "run")
        self.assertEqual((code, res["outcome"]), (1, "failed"))
        code, _, err = self.ccp("tasks", "next")
        self.assertEqual(code, 0)  # it was started; grace counts from there
        self.assertIn("the last pass ar-", err)
        self.merge(6)
        code, out, _ = self.ccp("tasks", "next")
        self.assertEqual(code, 4)
        self.assertIn("failed: no JSON report in the final message", out)  # the runner sees why

    def test_a_failed_pass_never_reblocks_at_the_same_count(self):
        for n in range(1, 9):
            self.merge(n)  # nothing left to merge: a due pass blocks at once
        self.assertEqual(self.ccp("tasks", "next")[0], 4)
        self.report.write_text("not json")
        self.dpj("architect", "run")
        code, _, err = self.ccp("tasks", "next")
        self.assertEqual(code, 3)  # failed at this very count: nothing re-blocks until a task merges
        self.assertIn("architect pass due", err)
        self.assertIn("failed.txt", err)

    def test_two_failed_passes_in_a_row_stop_blocking(self):
        for n in range(1, 6):
            self.merge(n)
        self.report.write_text("not json")
        self.dpj("architect", "run")
        self.merge(6)
        self.assertEqual(self.ccp("tasks", "next")[0], 4)  # one failure: re-blocks after a merge
        self.dpj("architect", "run")
        self.merge(7)
        code, out, err = self.ccp("tasks", "next")
        self.assertEqual((code, out[:7]), (0, "0008-t8"))  # two in a row: the pass goes to the owner
        self.assertIn("the last 2 passes failed", err)
        self.assertIn("Not blocking: take it to the task-log owner (the lead)", err)
        self.stub_report([])
        self.assertEqual(self.dpj("architect", "run", "--force")[1]["outcome"], "no_findings")
        self.assertEqual(self.dpj("architect", "due")[1]["failed_in_a_row"], 0)  # a good pass resets it

    def test_passes_started_in_the_same_second_do_not_crash_due(self):
        """Two passes with the same (or no) started_at sorted on their status too: None < str raised TypeError."""
        st = {"schema_version": 1, "seen": {}, "reviews": {
            "ar-20261028T000000Z-aaaa": {"mode": "pass", "status": None},
            "ar-20261028T000000Z-bbbb": {"mode": "pass", "status": "failed"}}}
        (self.q / "architect.json").write_text(json.dumps(st))
        body = self.dpj("architect", "due")[1]  # a crash prints no JSON
        self.assertEqual((body["due"], body["failed_in_a_row"]), (False, 1))

    def test_reviewers_repro_detached_pass_that_fails(self):
        """The `not json` stub with --detach: run says started, the pass fails a moment later, and the
        runner sees why at the next block instead of looping on full passes."""
        for n in range(1, 6):
            self.merge(n)
        self.report.write_text("not json")
        code, res, _ = self.dpj("architect", "run", "--detach")
        self.assertEqual((code, res["outcome"]), (0, "started"), res)
        rid = res["review_id"]
        for _ in range(100):
            if self.state()["reviews"][rid]["status"] == "failed":
                break
            time.sleep(0.1)
        self.assertEqual(self.state()["reviews"][rid]["status"], "failed")
        code, _, err = self.ccp("tasks", "next")
        self.assertEqual(code, 0)  # same done count: no block
        self.assertIn(f"the last pass {rid} failed: no JSON report in the final message", err)
        self.merge(6)
        code, out, _ = self.ccp("tasks", "next")
        self.assertEqual(code, 4)  # one more merge re-arms it
        self.assertIn(f"the last pass {rid} failed", out)
        self.assertIn(f"reviews/{rid}.failed.txt: \"", out)

    def test_review_point_close_needs_its_closing_pass(self):
        self.merge(1)
        self.merge(2)
        code, out, _ = self.ccp("tasks", "next", "--scope", "0001,0002")
        self.assertEqual(code, 4)
        self.assertIn("review point closes", out)
        self.assertIn("ccp architect run --detach --scope 0001,0002", out)
        self.stub_report([])
        self.assertEqual(self.dpj("architect", "run", "--scope", "0001,0002")[1]["outcome"], "no_findings")
        self.assertEqual(self.ccp("tasks", "next", "--scope", "0001,0002")[0], 3)  # closed: nothing ready

    def test_nothing_ready_and_a_due_pass_exits_4(self):
        for n in range(1, 9):
            self.merge(n)
        self.assertEqual(self.ccp("tasks", "next")[0], 4)

    def test_next_needs_queue_root_with_an_architect_block(self):
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
            code, _, err = self.ccp("tasks", "next")
        self.assertEqual(code, 2)
        self.assertIn("set QUEUE_ROOT", err)

    def test_detached_run_returns_while_the_pass_goes_on(self):
        self.stub_report([FINDING])
        code, res, _ = self.dpj("architect", "run", "--force", "--detach")
        self.assertEqual((code, res["outcome"]), (0, "started"), res)
        rid = res["review_id"]
        for _ in range(100):
            if self.state()["reviews"][rid]["status"] == "reported":
                break
            time.sleep(0.1)
        self.assertEqual(self.state()["reviews"][rid]["status"], "reported")
        self.assertTrue((self.q / "reviews" / f"{rid}.md").is_file())


class FrictionTriggersAPass(Harness):
    def test_acceptance_2_notes_reach_the_prompt(self):
        texts = ["one fact edited in 13 files", "a test pinned the help wording", "RUNBOOK read for nothing"]
        for i, t in enumerate(texts, start=1):
            code, _, err = self.ccp("health", "note", "--text", t, "--task", f"{i:04d}-t{i}", "--by", "implementer")
            self.assertEqual(code, 0, err)
        code, info, _ = self.dpj("architect", "due")
        self.assertEqual((code, info["due"]), (0, True))
        self.assertIn("3 task(s) with a friction note since none", info["reason"])
        self.stub_report([])
        self.dpj("architect", "run")
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        body = argv[argv.index("-p") + 1]  # the prompt the headless call got
        for t in texts:
            self.assertIn(t, body)
        self.assertIn("/architect mode=pass lenses=structure,docs,tests,process", body)
        self.assertIn("--model claude-opus-5-5 --effort high", " ".join(argv))
        code, info, _ = self.dpj("architect", "due")
        self.assertEqual(code, 3)  # the notes were seen by that pass

    def test_the_small_tasks_line_reaches_the_prompt(self):
        for n, lines in ((1, 20), (2, 400)):
            self.p.write(f"app/{n}.py", "x\n" * lines)
            git(self.p.root, "add", "-A")
            git(self.p.root, "commit", "-qm", f"Task {n:04d}: change {n} (#{n})")
        self.stub_report([])
        self.assertEqual(self.dpj("architect", "run", "--force")[0], 0)
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        body = argv[argv.index("-p") + 1]  # the prompt the headless call got
        small = [ln for ln in body.splitlines() if ln.startswith("Small tasks")]
        self.assertEqual(len(small), 1, body)
        self.assertIn("1 of 2", small[0])

    def test_note_with_a_secret_is_refused(self):
        code, _, err = self.ccp("health", "note", "--text", "key sk-ant-api03-" + "x" * 40)
        self.assertEqual(code, 2, err)


class RuleCostReachesTheOperator(Harness):
    def test_acceptance_6_rule_cost_needs_a_decision_and_goes_to_the_operator(self):
        self.stub_report([{**RULE_COST, "needs_decision": False}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["outcome"]), (1, "failed"))
        self.assertIn("a rule-cost finding needs a decision", " ".join(res["errors"]))
        self.stub_report([RULE_COST])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported", res)
        rid = res["review_id"]
        tp = self.q / "reviews" / f"{rid}.triage.json"
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
                "record": f"docs/delivery/reviews/{rid}.md", "commit_sha": None, "tasks_created": [],
                "answered_by": "spec_maintainer"}
        tp.write_text(json.dumps({**base, "dispositions": [{"finding": "F02", "disposition": "reject", "reason": "fine"}]}))
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual((code, res["outcome"]), (1, "invalid_triage"))
        self.assertIn("F02 is a rule-cost finding: its disposition is needs_operator", " ".join(res["errors"]))
        tp.write_text(json.dumps({**base, "question_for_operator": "May old rows be rewritten? (a) yes (b) no. I recommend (a).",
                                  "dispositions": [{"finding": "F02", "disposition": "needs_operator", "reason": "a rule"}]}))
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual((code, res["outcome"], res["dispositions"]), (0, "triaged", {"needs_operator": 1}))
        self.assertEqual(res["actions"][0]["action"], "lead_asks_operator")  # team lead asks in its session (§17.10)


class RuleChangesAndShape(Harness):
    def test_rule_changes_are_validated_and_disposed(self):
        self.stub_report([], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry for arms."}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "failed")
        self.assertIn("rule_changes[0]: missing check", " ".join(res["errors"]))
        self.stub_report([], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry.", "check": "command"}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported")  # no findings, but a rule change to triage
        rid = res["review_id"]
        self.assertIn("| E9 | add | command |", (self.q / "reviews" / f"{rid}.md").read_text())
        tp = self.q / "reviews" / f"{rid}.triage.json"
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
                "record": "r.md", "tasks_created": [], "answered_by": "spec_maintainer", "dispositions": []}
        tp.write_text(json.dumps({**base, "commit_sha": None}))
        self.assertEqual(self.dpj("architect", "triage", rid)[1]["outcome"], "invalid_triage")
        tp.write_text(json.dumps({**base, "commit_sha": None, "rule_changes": [
            {"rule": "E9", "action": "add", "disposition": "applied", "reason": "agreed"}]}))
        self.assertIn("rule changes applied without commit_sha", " ".join(self.dpj("architect", "triage", rid)[1]["errors"]))
        tp.write_text(json.dumps({**base, "commit_sha": "abc1234", "rule_changes": [
            {"rule": "E9", "action": "add", "disposition": "applied", "reason": "agreed"}]}))
        self.assertEqual(self.dpj("architect", "triage", rid)[1]["outcome"], "triaged")

    def test_pending_rule_change_finalises_and_backfill_records_the_sha(self):
        self.assertEqual(self.dpj("architect", "status")[1]["backfills"], [])
        self.stub_report([], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry.", "check": "command"}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported", res)
        rid = res["review_id"]
        tp = self.q / "reviews" / f"{rid}.triage.json"
        change = {"rule": "E9", "action": "add", "disposition": "applied", "reason": "agreed"}
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
                "record": "r.md", "tasks_created": [], "answered_by": "spec_maintainer", "dispositions": [],
                "rule_changes": [change]}
        tp.write_text(json.dumps({**base, "commit_sha": "pending"}))
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual(res["outcome"], "invalid_triage")
        self.assertIn("pending_change", " ".join(res["errors"]))
        note = "Add E9 to the house rules."
        tp.write_text(json.dumps({**base, "commit_sha": "pending", "pending_change": note}))
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertEqual((code, res["outcome"]), (0, "triaged"), res)
        self.assertEqual(res["actions"][0]["action"], "backfill")
        code, status, _ = self.dpj("architect", "status")
        self.assertEqual(status["backfills"], [{"review_id": rid, "commit_sha": "pending", "pending_change": note}])
        code, res, _ = self.dpj("architect", "triage", "--backfill", rid, "deadbeef")
        self.assertNotEqual(code, 0)
        self.assertEqual(res["outcome"], "unknown_commit")
        sha = subprocess.run(["git", "-C", str(self.p.root), "rev-parse", "HEAD"],
                             check=True, capture_output=True, text=True).stdout.strip()
        code, res, _ = self.dpj("architect", "triage", "--backfill", rid, sha)
        self.assertEqual((code, res["outcome"], res["commit_sha"]), (0, "backfilled", sha), res)
        self.assertEqual(self.dpj("architect", "status")[1]["backfills"], [])
        code, res, _ = self.dpj("architect", "triage", "--backfill", rid, sha[:7])
        self.assertEqual((code, res["outcome"]), (0, "already"))

    def test_apply_finalises_a_hand_committed_triage_and_rebuilds_the_index(self):
        """A triage file committed while architect.json stayed triage_sent."""
        self.stub_report([FINDING], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry.",
                                                   "check": "command"}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported", res)
        rid = res["review_id"]
        code, res, _ = self.dpj("architect", "triage", "--apply", rid)
        self.assertEqual(res["outcome"], "no_triage_file")
        self.assertNotEqual(code, 0)
        st = self.state()
        st["reviews"][rid]["status"] = "triage_sent"
        (self.q / "architect.json").write_text(json.dumps(st))
        sha = "607370975dcdd1883c5e8bf8a9dbaf38c32f111a"
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "schema_version": 1, "review_id": rid, "project_id": "demo", "triaged_at": "2026-11-01T10:00:00Z",
            "record": f"docs/delivery/reviews/{rid}.md", "commit_sha": sha,
            "tasks_created": ["0162-build-lists-accepted-adrs"], "answered_by": "spec_maintainer",
            "dispositions": [{"finding": "F01", "disposition": "task", "reason": "grouped with the BUILD rows",
                              "target": "0162-build-lists-accepted-adrs"}],
            "rule_changes": [{"rule": "E9", "action": "add", "disposition": "applied", "reason": "agreed"}],
        }))
        index = self.p.root / "docs/delivery/INDEX.yaml"
        index.unlink()
        code, res, _ = self.dpj("architect", "triage", "--apply", rid)
        self.assertEqual((code, res["outcome"], res["index"]), (0, "applied", "docs/delivery/INDEX.yaml"), res)
        self.assertEqual(self.state()["reviews"][rid]["status"], "triaged")
        self.assertEqual(self.state()["reviews"][rid]["commit_sha"], sha)
        self.assertIn("Generated by `ccp tasks index`", index.read_text())
        code, res, _ = self.dpj("architect", "triage", "--apply", rid)
        self.assertEqual((code, res["outcome"]), (0, "already_triaged"))

    def test_shape_run_names_the_adr_and_never_resets_the_cadence(self):
        self.p.write("docs/adr/0031-detach.md", "# ADR-0031\n")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "adr")
        self.stub_report([{**FINDING, "category": "duplication"}])
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "31")
        self.assertEqual(res["outcome"], "failed")  # a shape carries its `shape` object
        self.stub_report([FINDING], shape={"hot_spots": ["app/a.py"], "preparatory_refactors": [], "single_sources": [],
                                           "task_graph": []})
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "31")
        self.assertEqual((code, res["outcome"]), (0, "reported"), res)
        rid = res["review_id"]
        self.assertTrue(rid.startswith("sh-"))
        md = (self.q / "reviews" / f"{rid}.md").read_text()
        self.assertIn("ADR: ADR-0031", md)
        self.assertIn("### Hot spots\n\n- app/a.py", md)
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        body = argv[argv.index("-p") + 1]  # the prompt the headless call got
        self.assertIn("ADR to shape: ADR-0031 (docs/adr/0031-detach.md)", body)
        self.assertNotIn("last", self.state())
        code, res, _ = self.dpj("architect", "triage", rid)
        self.assertIn(f"docs/delivery/reviews/{rid}.md with the line `ADR: ADR-0031`", res["actions"][0]["message"])

    def test_due_lists_the_adrs_awaiting_a_shape(self):
        pj = self.p.root / "docs/delivery/plane.json"
        pj.write_text(json.dumps({"project_id": "demo", "architect": {"shape_adrs": True, "shape_from_task": "0008"}}))
        f = self.p.root / "docs/delivery/tasks/0008-t8.md"
        f.write_text(f.read_text().replace('spec_refs: ["S1"]', 'spec_refs: ["S1"]\nadr_refs: ["0031 D1"]'))
        self.assertEqual(self.dpj("architect", "due")[1]["shape_due"], ["ADR-0031"])
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "ADR: ADR-0031\n")
        self.assertEqual(self.dpj("architect", "due")[1]["shape_due"], [])

    def test_the_audit_keeps_the_prompt_text_only_when_the_product_opts_in(self):
        """§23.8: off by default, the audit holds the prompt's hash and length, and the argv entry
        that is the prompt reads `<prompt>`; `prompts.keep_body` keeps the text."""
        self.stub_report([])
        self.assertEqual(self.dpj("architect", "run", "--force")[0], 0)
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        prompt = argv[argv.index("-p") + 1]
        audit = json.loads(sorted((self.q / "prompts" / "architect").glob("*_architect-pass.json"))[-1].read_text())
        self.assertNotIn("prompt_body", audit)
        self.assertEqual(audit["prompt_sha256"], hashlib.sha256(prompt.encode()).hexdigest())
        self.assertEqual(audit["prompt_chars"], len(prompt))
        self.assertEqual(audit["argv"][audit["argv"].index("-p") + 1], "<prompt>")
        self.assertNotIn(prompt, json.dumps(audit))
        pj = self.p.root / "docs/delivery/plane.json"
        pj.write_text(json.dumps({**json.loads(pj.read_text()), "prompts": {"keep_body": True}}))
        self.assertEqual(self.dpj("architect", "run", "--force")[0], 0)
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        audit = json.loads(sorted((self.q / "prompts" / "architect").glob("*_architect-pass.json"))[-1].read_text())
        self.assertEqual(audit["prompt_body"], argv[argv.index("-p") + 1])
        self.assertEqual(audit["argv"][audit["argv"].index("-p") + 1], audit["prompt_body"])

    def test_a_finding_outside_the_lenses_is_refused(self):
        self.stub_report([{**FINDING, "category": "test-cost"}])
        code, res, _ = self.dpj("architect", "run", "--force", "--lens", "structure")
        self.assertIn("category 'test-cost'", " ".join(res["errors"]))


SHAPE = {"hot_spots": [], "preparatory_refactors": [], "single_sources": [], "task_graph": []}


class ThePassRunsInItsOwnWorktree(Harness):
    """§19.7, §12.1: the headless call runs in `arch-<review id>` under the worktree directory, at `head`."""

    def stub(self, name: str) -> str:
        return Path(f"{self.report}.{name}").read_text()

    def own(self, rid: str) -> Path:
        return (self.p.root / config.WORKTREES_DIR / f"arch-{rid}").resolve()

    def plane(self, **blocks):
        pj = self.p.root / "docs/delivery/plane.json"
        cur = json.loads(pj.read_text())
        for k, v in blocks.items():
            cur[k] = {**(cur.get(k) or {}), **v}
        pj.write_text(json.dumps(cur))

    def registered(self) -> str:
        return subprocess.run(["git", "-C", str(self.p.root), "worktree", "list", "--porcelain"],
                              capture_output=True, text=True).stdout

    def test_the_headless_call_runs_in_its_own_worktree_at_head_and_it_is_removed(self):
        self.stub_report([FINDING])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["outcome"]), (0, "reported"), res)
        rid = res["review_id"]
        self.assertEqual(self.stub("cwd"), str(self.own(rid)))
        self.assertEqual(self.stub("head"), res["head"])
        self.assertEqual(self.state()["reviews"][rid]["worktree"], str(self.own(rid)))
        self.assertFalse(self.own(rid).exists())  # removed once the pass reported
        self.assertNotIn(f"arch-{rid}", self.registered())

    def test_a_failed_pass_removes_its_worktree(self):
        self.report.write_text("not json")
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["outcome"]), (1, "failed"), res)
        rid = res["review_id"]
        self.assertEqual(self.stub("cwd"), str(self.own(rid)))
        self.assertFalse(self.own(rid).exists())
        self.assertNotIn(f"arch-{rid}", self.registered())

    def test_worktree_links_are_links_in_the_pass_worktree(self):
        self.plane(worktrees={"links": ["deps"]})
        self.p.write("deps/lib.txt", "a dependency\n")  # untracked: only the link brings it in
        self.stub_report([])
        with mock.patch.dict(os.environ, {"CCP_ARCHITECT_STUB_LINK": "deps"}):
            code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(code, 0, res)
        self.assertEqual(self.stub("cwd"), str(self.own(res["review_id"])))
        self.assertEqual(self.stub("link"), "True")

    def test_without_a_worktrees_dir_the_pass_runs_in_the_product_root(self):
        self.plane(worktrees={"dir": None})
        self.stub_report([])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(code, 0, res)
        self.assertEqual(self.stub("cwd"), str(self.p.root.resolve()))
        self.assertNotIn("worktree", self.state()["reviews"][res["review_id"]])

    def test_a_dead_pass_worktree_is_removed_by_the_write_path_only(self):
        rid = "ar-20261014T000000Z-abcd"
        own = self.own(rid)
        git(self.p.root, "worktree", "add", "-q", "--detach", str(own), "HEAD")
        (self.q / "architect.json").write_text(json.dumps({"schema_version": 1, "seen": {}, "reviews": {rid: {
            "status": "running", "mode": "pass", "done": [], "started_at": "2026-10-14T00:00:00Z",
            "worktree": str(own), "main": str(self.p.root)}}}))
        self.assertEqual(architect.load(self.q, reap=False)["reviews"][rid]["status"], "running")
        self.assertTrue(own.is_dir())  # a read never removes anything
        self.assertEqual(architect.load(self.q)["reviews"][rid]["status"], "failed")
        self.assertFalse(own.exists())
        self.assertNotIn(f"arch-{rid}", self.registered())

    def test_private_paths_are_denied_by_their_absolute_paths_too(self):
        self.plane(architect={"private_dirs": ["secret"]})
        self.stub_report([])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(code, 0, res)
        argv = json.loads(self.stub("argv"))
        deny = argv[argv.index("--disallowedTools") + 1].split(",")
        own, root = str(self.own(res["review_id"])), str(self.p.root.resolve())
        for rule in ("Read(./secret)", "Read(./secret/**)", f"Read(/{own}/secret)", f"Read(/{own}/secret/**)",
                     f"Read(/{root}/secret)", f"Read(/{root}/secret/**)"):
            self.assertIn(rule, deny)
        self.assertTrue(f"Read(/{own}/secret)".startswith("Read(//"))

    def test_a_commit_in_the_product_root_during_the_pass_changes_nothing_it_reads(self):
        self.p.write("app/watched.txt", "one\n")
        git(self.p.root, "add", "app/watched.txt")
        git(self.p.root, "commit", "-qm", "watched")
        started, go = Path(f"{self.report}.started"), Path(f"{self.report}.go")

        def move_the_checkout():
            for _ in range(400):
                if started.exists():
                    break
                time.sleep(0.05)
            self.p.write("app/watched.txt", "two\n")
            git(self.p.root, "add", "app/watched.txt")
            git(self.p.root, "commit", "-qm", "moved")
            go.write_text("")

        mover = threading.Thread(target=move_the_checkout)
        mover.start()
        self.stub_report([])
        with mock.patch.dict(os.environ, {"CCP_ARCHITECT_STUB_WATCH": "app/watched.txt"}):
            code, res, _ = self.dpj("architect", "run", "--force")
        mover.join()
        self.assertEqual(code, 0, res)
        self.assertEqual(json.loads(self.stub("reads")), ["one\n", "one\n"])

    def test_a_worktree_that_cannot_be_made_fails_the_pass(self):
        self.p.write(config.WORKTREES_DIR, "a file where the worktree directory goes\n")
        self.stub_report([])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["outcome"]), (1, "failed"), res)
        self.assertIn("git worktree add", self.state()["reviews"][res["review_id"]]["error"])
        self.assertFalse(Path(f"{self.report}.argv").exists())  # nothing launched

    def test_a_dirty_caller_checkout_names_the_head_the_pass_reads(self):
        f = self.p.root / "docs/delivery/REVIEW-TRIAGE.md"
        f.write_text(f.read_text() + "uncommitted\n")
        self.stub_report([])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["dirty"]), (0, True), res)
        argv = json.loads(self.stub("argv"))
        body = argv[argv.index("-p") + 1]
        self.assertIn(f"`{res['head'][:7]}`", body)
        self.assertNotIn("git show HEAD:", body)

    def test_a_dirty_product_root_without_a_worktrees_dir_keeps_the_committed_state_line(self):
        self.plane(worktrees={"dir": None})
        f = self.p.root / "docs/delivery/REVIEW-TRIAGE.md"
        f.write_text(f.read_text() + "uncommitted\n")
        self.stub_report([])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual((code, res["dirty"]), (0, True), res)
        argv = json.loads(self.stub("argv"))
        body = argv[argv.index("-p") + 1]
        self.assertIn("git show HEAD:", body)
        self.assertNotIn("you are reading", body)


class OneCallShapesEveryAdrDue(Harness):
    """§19.5: `--adr` takes several ids, comma-separated, or `due`; one call shapes each in turn."""

    def setUp(self):
        super().setUp()
        pj = self.p.root / "docs/delivery/plane.json"
        pj.write_text(json.dumps({**json.loads(pj.read_text()),
                                  "architect": {"shape_adrs": True, "shape_from_task": "0008"}}))
        f = self.p.root / "docs/delivery/tasks/0008-t8.md"
        f.write_text(f.read_text().replace('spec_refs: ["S1"]', 'spec_refs: ["S1"]\nadr_refs: ["0032 D1", "0031 D1"]'))
        self.stub_report([FINDING], shape=SHAPE)

    def adrs(self, rids):
        return [self.state()["reviews"][r]["adr"] for r in rids]

    def test_adr_due_shapes_every_adr_due_in_order_and_exits_3_with_none_due(self):
        self.assertEqual(self.dpj("architect", "due")[1]["shape_due"], ["ADR-0031", "ADR-0032"])
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "due")
        self.assertEqual(code, 0, res)
        rids = [r["review_id"] for r in res["runs"]]
        self.assertEqual([r["outcome"] for r in res["runs"]], ["reported", "reported"])
        self.assertTrue(all(r.startswith("sh-") for r in rids) and len(set(rids)) == 2)
        self.assertEqual(self.adrs(rids), ["ADR-0031", "ADR-0032"])
        for n in (31, 32):
            self.p.write(f"docs/delivery/reviews/sh-20261014T000000Z-00{n}.md", f"ADR: ADR-00{n}\n")
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "due")
        self.assertEqual((code, res["outcome"]), (3, "not_due"), res)

    def test_adr_comma_list_shapes_each_in_the_order_given(self):
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "31,32")
        self.assertEqual(code, 0, res)
        self.assertEqual(self.adrs([r["review_id"] for r in res["runs"]]), ["ADR-0031", "ADR-0032"])
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "32,31")
        self.assertEqual(code, 0, res)
        self.assertEqual(self.adrs([r["review_id"] for r in res["runs"]]), ["ADR-0032", "ADR-0031"])

    def test_several_adrs_need_one_review_id_each(self):
        code, out, err = self.ccp("architect", "run", "--mode", "shape", "--adr", "31,32", "--review-id",
                                  "sh-20261014T000000Z-0001")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("--review-id needs one id per ADR", err)
        self.assertFalse((self.q / "architect.json").exists() and self.state()["reviews"])

    def test_a_failed_shape_among_several_exits_1(self):
        self.report.write_text("not json")
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "31,32")
        self.assertEqual((code, [r["outcome"] for r in res["runs"]]), (1, ["failed", "failed"]), res)

    def test_adr_due_detached_runs_every_shape_in_one_process(self):
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "due", "--detach")
        self.assertEqual((code, res["outcome"]), (0, "started"), res)
        rids = res["review_ids"]
        self.assertEqual(len(set(rids)), 2)
        for _ in range(200):
            if all((self.state()["reviews"].get(r) or {}).get("status") == "reported" for r in rids):
                break
            time.sleep(0.1)
        self.assertEqual(self.adrs(rids), ["ADR-0031", "ADR-0032"])
        self.assertEqual([self.state()["reviews"][r]["status"] for r in rids], ["reported", "reported"])

    def test_adr_due_detached_with_one_adr_due_still_prints_review_ids(self):
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-0032.md", "ADR: ADR-0032\n")
        self.assertEqual(self.dpj("architect", "due")[1]["shape_due"], ["ADR-0031"])
        code, res, _ = self.dpj("architect", "run", "--mode", "shape", "--adr", "due", "--detach")
        self.assertEqual((code, res["outcome"]), (0, "started"), res)
        self.assertEqual(res["review_ids"], [res["review_id"]])
        for _ in range(200):
            if (self.state()["reviews"].get(res["review_id"]) or {}).get("status") == "reported":
                break
            time.sleep(0.1)
        self.assertEqual(self.adrs(res["review_ids"]), ["ADR-0031"])


class AdrPlan(unittest.TestCase):
    """`--adr`'s reading on plain values (§19.5)."""

    def test_ids_are_canonical_in_the_order_given(self):
        self.assertEqual(architect.adr_plan("32, 31", "shape", lambda: []), ["ADR-0032", "ADR-0031"])
        self.assertEqual(architect.adr_plan("31", "pass", lambda: []), ["ADR-0031"])  # one id: as before
        self.assertEqual(architect.adr_plan(None, "shape", lambda: ["ADR-0001"]), [])

    def test_due_reads_the_due_list(self):
        self.assertEqual(architect.adr_plan("due", "shape", lambda: ["ADR-0031", "ADR-0032"]),
                         ["ADR-0031", "ADR-0032"])

    def test_due_or_several_ids_need_shape_mode(self):
        for arg in ("due", "31,32"):
            with self.assertRaises(SystemExit):
                architect.adr_plan(arg, "pass", lambda: ["ADR-0031"])
        with self.assertRaises(SystemExit):
            architect.adr_plan("31,due", "shape", lambda: ["ADR-0031"])

    def test_deny_rules_add_each_absolute_root(self):
        self.assertEqual(architect.deny_rules(["s"], ["/w", "/w", "/r"]),
                         ["Read(./s)", "Read(./s/**)", "Read(//w/s)", "Read(//w/s/**)", "Read(//r/s)", "Read(//r/s/**)"])


class NoHostingLine(Harness):
    """A binding without the old `hosting` line is a Claude team like any other."""

    def test_a_binding_without_hosting_blocks_on_an_overdue_pass(self):
        self.assertNotIn("hosting", (self.q / "project.yaml").read_text())
        for n in range(1, 6):
            self.merge(n)
        code, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 4, out + err)
        self.assertIn("architect pass due", out)


class TheReportIsFoundInTheFinalMessage(unittest.TestCase):
    """The architect's JSON report is read from its final message, whatever its strings quote."""

    @staticmethod
    def report(evidence: str) -> dict:
        return {"summary": "Two findings.", "findings": [
            {"id": "F1", "evidence": "a.py:3 — plain"},
            {"id": "F2", "evidence": evidence}]}

    @staticmethod
    def parse(text: str):
        from ccp.architect import ar  # noqa: PLC0415
        return ar.last_json_object(text)

    def test_an_unfenced_report_quoting_an_unbalanced_open_brace_is_read_whole(self):
        r = self.report("a.py:10 — 'MAP = {'")
        got = self.parse("Report:\n" + json.dumps(r, indent=2, ensure_ascii=False))
        self.assertEqual(got, r)
        self.assertEqual(len(got["findings"]), 2)

    def test_an_unfenced_report_quoting_an_unbalanced_close_brace_is_read_whole(self):
        r = self.report("a.py:12 — 'end = }'")
        self.assertEqual(self.parse("Report:\n" + json.dumps(r, indent=2, ensure_ascii=False)), r)

    def test_prose_before_and_after_the_report_is_skipped(self):
        r = self.report("a.py:10 — 'MAP = {'")
        text = ("Looked at {x} and the rest.\n" + json.dumps(r, indent=2, ensure_ascii=False)
                + "\nThat is all; no {more} to say.")
        self.assertEqual(self.parse(text), r)

    def test_a_fenced_report_is_read(self):
        r = self.report("a.py:10 — 'MAP = {'")
        text = "Before {x}.\n```json\n" + json.dumps(r, indent=2, ensure_ascii=False) + "\n```\nAfter."
        self.assertEqual(self.parse(text), r)

    def test_of_two_top_level_objects_the_last_wins(self):
        first, second = self.report("a.py:1 — '{'"), self.report("b.py:2 — '}'")
        text = (json.dumps(first, ensure_ascii=False) + "\nOn reflection:\n"
                + json.dumps(second, indent=2, ensure_ascii=False))
        self.assertEqual(self.parse(text), second)

    def test_a_message_without_an_object_has_no_report(self):
        self.assertIsNone(self.parse("No report {here}, sorry."))
        self.assertIsNone(self.parse(""))


if __name__ == "__main__":
    unittest.main()
