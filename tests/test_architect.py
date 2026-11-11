"""ccp architect (SPEC §19): triggers, enforcement at `ccp tasks next`, the run and its triage, end to end
against a stub `claude` (DA_CLAUDE_BIN). Acceptance checks docs/design/architect.md #1, #2 and #6 are named below."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from tests.helpers import Product

STUB = """#!/usr/bin/env bash
# Stub claude: answer with the report in $DA_STUB_REPORT, as `claude -p --output-format json` would.
python3 - "$@" <<'PY'
import json, os, re, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
open(os.environ["DA_STUB_REPORT"] + ".argv", "w").write(json.dumps(sys.argv[1:]))
open(os.environ["DA_STUB_REPORT"] + ".otel", "w").write(os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""))
rid = re.search(r"review_id=(\\S+)", prompt).group(1)
rep = json.loads(open(os.environ["DA_STUB_REPORT"]).read())
rep["review_id"] = rid
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "Done.\\n```json\\n" + json.dumps(rep) + "\\n```", "session_id": "stub"}))
PY
"""

FINDING = {"id": "F01", "title": "Two registries for one concept", "category": "duplication", "severity": "medium",
           "confidence": "high", "what": "Arms are listed twice.", "evidence": ["app/a.py:1 — ARMS", "app/b.py:1 — ARMS"],
           "fix": "merge", "proposal": "Keep app/a.py's list.", "touches": ["code"]}
RULE_COST = {**FINDING, "id": "F02", "title": "Legacy ids kept alive", "category": "rule-cost",
             "fix": "decide", "needs_decision": True, "proposal": "Ask whether old rows may be rewritten."}


def git(root: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                   capture_output=True)


class Harness(unittest.TestCase):
    """A committed product with the architect skill, a team-lead runtime queue and a stub claude."""

    ARCHITECT: dict = {}
    TASKS = 8

    def setUp(self):
        self.p = Product({"architect": self.ARCHITECT})
        self.p.write(".claude/skills/architect/SKILL.md", "---\nname: architect\n---\n# Architect\n")
        self.p.write("docs/delivery/REVIEW-TRIAGE.md", "# triage\n")
        for i in range(1, self.TASKS + 1):
            self.p.task(f"{i:04d}-t{i}")
        self.p.index()
        git(self.p.root, "init", "-q")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text(
            f"project_id: demo\nhosting: claude-team\nproduct_root: {self.p.root}\n"
            "spec_maintainer:\n  kind: team-lead\n  alias: demo-design\n  protocol_doc: docs/delivery/SPEC-MAINTAINER.md\n")
        stub = self.q / "claude-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.report = self.q / "stub-report.json"
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "PROJECT_YAML": str(self.q / "project.yaml"),
                                                "DA_CLAUDE_BIN": str(stub), "DA_STUB_REPORT": str(self.report),
                                                "ACTOR": "task-runner"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli.main(["--root", str(self.p.root), *args])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
                err.write(str(e.code))
        return code, out.getvalue(), err.getvalue()

    def dpj(self, *args):
        code, out, err = self.ccp(*args)
        return code, json.loads(out), err

    def merge(self, n: int, kind: str | None = None):
        """Mark task n done, as a reconcile after its merge would, and commit."""
        tid = f"{n:04d}-t{n}"
        f = self.p.task(tid, "done")
        if kind:
            f.write_text(f.read_text().replace("status: done", f"status: done\nkind: {kind}"))
        self.p.index()
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", f"Reconcile {tid}")

    def stub_report(self, findings, **extra):
        self.report.write_text(json.dumps({"schema_version": 1, "project_id": "demo", "head": "x",
                                           "summary": "A look.", "findings": findings, **extra}))

    def state(self):
        return json.loads((self.q / "architect.json").read_text())


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
            "schema_version": 1, "review_id": rid, "project_id": "demo", "record": f"docs/delivery/reviews/{rid}.md",
            "commit_sha": None, "tasks_created": [], "answered_by": "spec_maintainer",
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
            "holder": "task-runner", "pid": 1, "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
        for i, t in enumerate(texts):
            code, _, err = self.ccp("health", "note", "--text", t, "--task", "0001-t1", "--by", "implementer")
            self.assertEqual(code, 0, err)
        code, info, _ = self.dpj("architect", "due")
        self.assertEqual((code, info["due"]), (0, True))
        self.assertIn("3 friction note(s) since none", info["reason"])
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
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "record": f"docs/delivery/reviews/{rid}.md",
                "commit_sha": None, "tasks_created": [], "answered_by": "spec_maintainer"}
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
        self.assertIn("rule_changes[0]: names no check", " ".join(res["errors"]))
        self.stub_report([], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry.", "check": "command"}])
        code, res, _ = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported")  # no findings, but a rule change to triage
        rid = res["review_id"]
        self.assertIn("| E9 | add | command |", (self.q / "reviews" / f"{rid}.md").read_text())
        tp = self.q / "reviews" / f"{rid}.triage.json"
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "record": "r.md", "tasks_created": [],
                "answered_by": "spec_maintainer", "dispositions": []}
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
        base = {"schema_version": 1, "review_id": rid, "project_id": "demo", "record": "r.md", "tasks_created": [],
                "answered_by": "spec_maintainer", "dispositions": [], "rule_changes": [change]}
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
            "schema_version": 1, "review_id": rid, "project_id": "demo",
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


class NoHostingLine(Harness):
    """A binding without the old `hosting` line is a Claude team like any other."""

    def test_a_binding_without_hosting_blocks_on_an_overdue_pass(self):
        text = (self.q / "project.yaml").read_text().replace("hosting: claude-team\n", "")
        (self.q / "project.yaml").write_text(text)
        for n in range(1, 6):
            self.merge(n)
        code, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 4, out + err)
        self.assertIn("architect pass due", out)


if __name__ == "__main__":
    unittest.main()
