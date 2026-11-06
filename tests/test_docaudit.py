"""ccp docs audit (SPEC §21.7), end to end against a stub `claude` (DA_CLAUDE_BIN)."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from tests.helpers import Product

STUB = """#!/usr/bin/env bash
# Stub claude: answer with the report held in $DA_STUB_REPORT, as `claude -p --output-format json` would.
python3 - "$@" <<'PY'
import json, os, re, sys
prompt = sys.argv[sys.argv.index("-p") + 1]
open(os.environ["DA_STUB_REPORT"] + ".argv", "w").write(json.dumps(sys.argv[1:]))
rid = re.search(r"review_id=(\\S+)", prompt).group(1)
rep = json.loads(open(os.environ["DA_STUB_REPORT"]).read())
rep["review_id"] = rid
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "Done.\\n```json\\n" + json.dumps(rep) + "\\n```", "session_id": "stub"}))
PY
"""

FINDING = {"id": "D01", "title": "Doc names a removed flag", "category": "doc-wrong", "severity": "medium",
           "confidence": "high", "what": "The doc says --x exists.",
           "evidence": ["app/main.py:1 — no --x", "app/CLAUDE.md:3 — 'use --x'"],
           "fix": "cut", "proposal": "Drop the --x sentence.", "touches": ["docs"]}


class Harness(unittest.TestCase):
    """A committed product with package docs, a runtime queue and a stub claude."""

    def setUp(self):
        self.p = Product({"package_docs": {"claude_md_dirs": ["app"]}})
        self.p.write("app/CLAUDE.md", "# app\n\nThe app.\n")
        self.p.write("app/main.py", '"""Main."""\n' + "x = 1\n" * 20)
        self.p.write(".claude/skills/docs-audit/SKILL.md", "---\nname: docs-audit\n---\n# Docs audit\n")
        self.p.task("0001-a")
        self.p.index()
        g = ["git", "-C", str(self.p.root)]
        subprocess.run([*g, "init", "-q"], check=True)
        subprocess.run([*g, "add", "-A"], check=True)
        subprocess.run([*g, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"], check=True)
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text(
            f"project_id: demo\nadapter: local-repo\nintegration_branch: master\nqueue_root: {self.q}\n"
            f"durable_docs_path: docs/delivery/\nproduct_root: {self.p.root}\n")
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
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = cli.main(["--root", str(self.p.root), "docs", "audit", *args])
        return code, json.loads(buf.getvalue())

    def stub_report(self, findings):
        self.report.write_text(json.dumps({"schema_version": 1, "project_id": "demo", "head": "x",
                                           "summary": "One directory.", "findings": findings}))


class DocsAuditTest(Harness):
    def test_due_run_reported_then_blocked(self):
        code, info = self.ccp("due")
        self.assertEqual((code, info["due"]), (0, True))
        self.stub_report([FINDING])
        code, res = self.ccp("run")
        self.assertEqual((code, res["outcome"], res["findings"]), (0, "reported", 1))
        rid = res["review_id"]
        self.assertTrue(rid.startswith("da-"))
        self.assertTrue((self.q / "reviews" / f"{rid}.md").read_text().startswith(f"# Docs audit {rid}"))
        self.assertEqual(res["actions"][0]["cmd"], f"ccp docs audit triage {rid}")
        code, info = self.ccp("due")
        self.assertEqual(code, 3)
        self.assertIn("awaits triage", info["reason"])
        events = [json.loads(l) for l in (self.q / "observability" / "events.jsonl").read_text().splitlines()]
        self.assertTrue(all(e["type"] == "docs_audit" for e in events))
        self.assertFalse((self.q / "architecture-review.json").exists())

    def test_auditor_pins_model_and_effort(self):
        self.stub_report([])
        self.ccp("run")
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        self.assertIn("--model claude-opus-5-5 --effort high", " ".join(argv))

    def test_no_findings_then_not_due_until_head_moves(self):
        self.stub_report([])
        code, res = self.ccp("run")
        self.assertEqual(res["outcome"], "no_findings")
        code, info = self.ccp("due")
        self.assertEqual((code, info["reason"]), (3, "nothing committed since the last audit"))

    def test_invalid_report_fails_and_keeps_output(self):
        self.stub_report([{**FINDING, "category": "holdover"}])
        code, res = self.ccp("run")
        self.assertEqual((code, res["outcome"]), (1, "failed"))
        self.assertIn("category 'holdover'", " ".join(res["errors"]))
        self.assertTrue((self.q / "reviews" / f"{res['review_id']}.failed.txt").exists())

    def test_triage_applies_owner_file(self):
        self.stub_report([FINDING])
        rid = self.ccp("run")[1]["review_id"]
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "schema_version": 1, "review_id": rid, "project_id": "demo", "record": f"docs/delivery/reviews/{rid}.md",
            "commit_sha": "abc1234", "tasks_created": ["0002-doc-fixes"], "answered_by": "steerer",
            "dispositions": [{"finding": "D01", "disposition": "task", "target": "0002-doc-fixes", "reason": "real"}]}))
        code, res = self.ccp("triage", rid)
        self.assertEqual((code, res["outcome"]), (0, "triaged"))
        self.assertEqual(res["actions"][0]["action"], "register_tasks")
        self.assertEqual(json.loads((self.q / "docs-audit.json").read_text())["reviews"][rid]["status"], "triaged")

    def test_disabled_without_package_docs(self):
        (self.p.root / "docs/delivery/plane.json").write_text('{"project_id": "demo"}')
        code, info = self.ccp("due")
        self.assertEqual(code, 3)
        self.assertIn("no package_docs", info["reason"])


if __name__ == "__main__":
    unittest.main()


class ArchitectureReviewStillWorks(Harness):
    """The Kind refactor must leave the §19 driver's run + triage unchanged."""

    def test_ar_run_and_triage(self):
        from ccp import docaudit  # noqa: F401  (puts scripts/observability on sys.path)
        import architecture_review as ar
        self.p.write(".claude/skills/architecture-review/SKILL.md", "---\nname: architecture-review\n---\n")
        self.stub_report([{**FINDING, "id": "F01", "category": "holdover", "fix": "remove"}])
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"AR_CLAUDE_BIN": os.environ["DA_CLAUDE_BIN"]}), redirect_stdout(buf):
            code = ar.main(["run", "--force"])
        res = json.loads(buf.getvalue())
        self.assertEqual((code, res["outcome"]), (0, "reported"), res)
        rid = res["review_id"]
        self.assertTrue(rid.startswith("ar-"))
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        self.assertIn("--model claude-opus-5-5 --effort high", " ".join(argv))
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "schema_version": 1, "review_id": rid, "record": "r.md", "commit_sha": None, "answered_by": "steerer",
            "dispositions": [{"finding": "F01", "disposition": "reject", "reason": "intentional"}]}))
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(ar.main(["triage", rid]), 0)
        self.assertEqual(json.loads(buf.getvalue())["outcome"], "triaged")
        self.assertEqual(json.loads((self.q / "architecture-review.json").read_text())["reviews"][rid]["status"], "triaged")
        self.assertFalse((self.q / "docs-audit.json").exists())
