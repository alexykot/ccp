"""ADR-0034 D5: the older architecture-review and docs-audit aliases are retired (SPEC §19.12).
`ccp docs audit` is no longer a command, and a queue that still holds the aliases' state files,
reports and events builds its board and its health as before."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ccp import cli
from tests.test_toolkit import ToolkitFixture

AR_ID = "ar-20261001T120000Z-abcd"
DA_ID = "da-20261002T120000Z-beef"
REPORT = {"schema_version": 1, "review_id": AR_ID, "project_id": "demo", "head": "a" * 40, "base": None,
          "summary": "One holdover.",
          "findings": [{"id": "F01", "title": "Old table", "category": "holdover", "severity": "medium",
                        "confidence": "high", "what": "A table a later decision replaced.",
                        "evidence": ["x.py:1"], "fix": "remove", "proposal": "Drop it."}]}


def _event(at: str, typ: str, op: str, payload: dict) -> dict:
    return {"at": at, "project_id": "demo", "task_id": "", "actor": "task-runner", "type": typ, "op": op,
            "payload": payload}


class OlderAliasRecords(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        q = self.q
        (q / "architecture-review.json").write_text(json.dumps({
            "schema_version": 1,
            "last": {"review_id": AR_ID, "at": "2026-10-01T12:30:00Z", "head": "a" * 40, "done_count": 1},
            "reviews": {AR_ID: {"status": "triaged", "head": "a" * 40, "base": None, "done_count": 1,
                                "started_at": "2026-10-01T12:00:00Z", "updated_at": "2026-10-01T13:00:00Z",
                                "findings": 1, "commit_sha": None, "record": "docs/delivery/reviews/x.md"}}}))
        (q / "docs-audit.json").write_text(json.dumps({
            "schema_version": 1,
            "reviews": {DA_ID: {"status": "running", "head": "b" * 40, "started_at": "2026-10-02T12:00:00Z"}}}))
        reviews = q / "reviews"
        reviews.mkdir()
        (reviews / f"{AR_ID}.json").write_text(json.dumps(REPORT))
        (reviews / f"{AR_ID}.md").write_text("# Architecture review\n")
        (reviews / f"{AR_ID}.triage.json").write_text(json.dumps({
            "schema_version": 1, "review_id": AR_ID, "record": "r.md", "commit_sha": None, "answered_by": "steerer",
            "dispositions": [{"finding": "F01", "disposition": "reject", "reason": "intentional"}]}))
        obs = q / "observability"
        obs.mkdir(exist_ok=True)
        events = [
            _event("2026-10-01T12:00:00Z", "architecture_review", "transition",
                   {"review_id": AR_ID, "from": "none", "to": "running"}),
            _event("2026-10-01T12:30:00Z", "architecture_review", "transition",
                   {"review_id": AR_ID, "from": "running", "to": "reported"}),
            _event("2026-10-01T13:00:00Z", "architecture_review", "transition",
                   {"review_id": AR_ID, "from": "reported", "to": "triaged"}),
            _event("2026-10-02T12:00:00Z", "docs_audit", "transition",
                   {"review_id": DA_ID, "from": "none", "to": "running"}),
        ]
        with (obs / "events.jsonl").open("a") as fh:
            fh.write("".join(json.dumps(e) + "\n" for e in events))

    def test_the_board_and_health_build_from_an_older_queue(self):
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(Path(body["board"]).is_file())
        code, _, out, err = self.ccp("health", "--json")
        self.assertEqual(code, 0, out + err)
        json.loads(out)

    def test_docs_audit_is_no_longer_a_command(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as ctx:
            cli.main(["--root", str(self.runner), "docs", "audit", "due"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
