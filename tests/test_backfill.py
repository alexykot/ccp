"""`ccp tasks backfill-review-points` (SPEC §22): review points rebuilt from the queue's runner
history and the product log, written to the working tree only, never over a value."""
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

from ccp import backfill, cli
from tests.helpers import Product

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def ev(at: str, typ: str, op: str, payload: dict, task_id: str = "") -> dict:
    return {"at": at, "project_id": "demo", "task_id": task_id, "actor": "design-seat", "type": typ, "op": op,
            "payload": payload}


def spawn(at: str, rp: str, scope: list[str]) -> dict:
    return ev(at, "runner", "spawn", {"name": "runner", "scope": scope, "review_point": rp})


def claim(at: str, tid: str) -> dict:
    return ev(at, "lease", "set", {"holder": "runner"}, tid)


def done(at: str, tid: str) -> dict:
    return ev(at, "phase", "transition", {"from": "verifying", "to": "done"}, tid)


class Backfill(unittest.TestCase):
    def setUp(self):
        self.p = Product({"reconcile": {"log": {"path": "docs/LOG.md",
                                                "entry": "**{date} (runner, {review_point}):** `{nnnn}` done: {summary} PR #{pr}."}}})
        self.p.write("docs/LOG.md", "# Log\n")
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "observability").mkdir()
        (self.q / "tasks").mkdir()
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def events(self, *evs: dict) -> None:
        (self.q / "observability" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))

    def run_cli(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "backfill-review-points", *args])
        return code, out.getvalue(), err.getvalue()

    def plan(self) -> dict[str, dict]:
        return {r["task_id"]: r for r in backfill.plan(self.p.cfg, self.q)["tasks"]}

    def test_scope_then_time_then_unset(self):
        for tid in ("0001-early", "0002-scoped", "0003-unscoped", "0004-gap", "0005-late-scope"):
            self.p.task(tid, status="done")
        self.p.task("0006-open")
        self.events(claim("2026-10-01T00:00:00Z", "0001-early"),
                    spawn("2026-10-02T00:00:00Z", "R2", ["0002-scoped"]),
                    claim("2026-10-02T01:00:00Z", "0002-scoped"), done("2026-10-02T02:00:00Z", "0002-scoped"),
                    claim("2026-10-02T03:00:00Z", "0003-unscoped"),
                    ev("2026-10-03T00:00:00Z", "runner", "stop", {"name": "runner", "reason": "r"}),
                    claim("2026-10-03T01:00:00Z", "0004-gap"),
                    claim("2026-10-03T02:00:00Z", "0005-late-scope"),
                    spawn("2026-10-04T00:00:00Z", "R3", ["0005-late-scope"]),
                    done("2026-10-04T01:00:00Z", "0005-late-scope"))
        got = self.plan()
        self.assertNotIn("0006-open", got)
        self.assertEqual(got["0001-early"]["review_point"], None)
        self.assertIn("before the first", got["0001-early"]["why"])
        self.assertEqual((got["0002-scoped"]["review_point"], got["0002-scoped"]["how"], got["0002-scoped"]["scope_hit"]),
                         ("R2", "scope", "at spawn"))
        self.assertEqual((got["0003-unscoped"]["review_point"], got["0003-unscoped"]["how"]), ("R2", "time"))
        self.assertEqual(got["0004-gap"]["review_point"], None)
        self.assertEqual((got["0005-late-scope"]["review_point"], got["0005-late-scope"]["how"]), ("R3", "scope"))

    def test_scope_changes_count_and_the_queue_file_gives_a_claim(self):
        self.p.task("0001-added", status="done")
        self.p.task("0002-queue-file", status="done")
        self.events(spawn("2026-10-02T00:00:00Z", "R4", []),
                    ev("2026-10-02T00:30:00Z", "runner", "scope", {"name": "runner", "scope": ["0001-added"],
                                                                  "added": ["0001-added"], "removed": []}),
                    claim("2026-10-02T01:00:00Z", "0001-added"),
                    spawn("2026-10-05T00:00:00Z", "R5", ["0002-queue-file"]))
        (self.q / "tasks" / "0002-queue-file.json").write_text(json.dumps({"implementation_started_at": "2026-10-05T01:00:00Z"}))
        got = self.plan()
        self.assertEqual((got["0001-added"]["review_point"], got["0001-added"]["scope_hit"]), ("R4", "added later"))
        self.assertEqual((got["0002-queue-file"]["review_point"], got["0002-queue-file"]["claim_from"]),
                         ("R5", "tasks/0002-queue-file.json implementation_started_at"))

    def test_the_product_log_wins_and_the_ledger_disagreement_is_shown(self):
        self.p.task("0001-logged", status="done")
        self.p.write("docs/LOG.md", "# Log\n\n**2026-10-03 (runner, R6):** `0001` done: it works. PR #4.\n")
        self.events(spawn("2026-10-02T00:00:00Z", "R5", ["0001-logged"]), claim("2026-10-02T01:00:00Z", "0001-logged"))
        r = self.plan()["0001-logged"]
        self.assertEqual((r["review_point"], r["how"], r["ledger_says"]), ("R6", "log", "R5"))

    def test_dry_run_writes_nothing_and_a_point_off_the_pattern_is_skipped(self):
        f = self.p.task("0001-a", status="done")
        self.p.task("0002-b", status="done")
        before = f.read_bytes()
        self.events(spawn("2026-10-02T00:00:00Z", "R2", ["0001-a"]), claim("2026-10-02T01:00:00Z", "0001-a"),
                    spawn("2026-10-03T00:00:00Z", "PM", ["0002-b"]), claim("2026-10-03T01:00:00Z", "0002-b"))
        code, out, err = self.run_cli("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("0001-a -> R2", out)
        self.assertIn("scope: spawn 2026-10-02T00:00:00Z, scope at spawn", out)
        self.assertIn("0002-b -> PM", out)
        self.assertIn("not stamped: review point 'PM' does not match", out)
        self.assertIn("PM 1, R2 1", out)
        self.assertEqual(f.read_bytes(), before)

    def test_writes_only_where_absent_keeps_crlf_and_bytes_and_commits_nothing(self):
        lf = self.p.task("0001-lf", status="done")
        crlf = self.p.task("0002-crlf", status="done")
        crlf.write_bytes(crlf.read_bytes().replace(b"\n", b"\r\n"))
        kept = self.p.task("0003-kept", status="done")
        kept.write_text(kept.read_text().replace("updated: 2026-09-30\n", "updated: 2026-09-30\nreview_point: R1\n"))
        for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(self.p.root), *c], check=True, capture_output=True)
        head = subprocess.run(["git", "-C", str(self.p.root), "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        before = {p: p.read_bytes() for p in (lf, crlf, kept)}
        self.events(spawn("2026-10-02T00:00:00Z", "R2", ["0001-lf", "0002-crlf", "0003-kept"]),
                    *(claim(f"2026-10-02T0{i}:00:00Z", t) for i, t in enumerate(("0001-lf", "0002-crlf", "0003-kept"), 1)))
        code, out, err = self.run_cli()
        self.assertEqual(code, 0, err)
        self.assertIn("Written (working tree only, nothing committed): 2 files", out)
        self.assertEqual(lf.read_bytes(), before[lf].replace(b"updated: 2026-09-30\n---\n",
                                                             b"updated: 2026-09-30\nreview_point: R2\n---\n"))
        self.assertEqual(crlf.read_bytes(), before[crlf].replace(b"updated: 2026-09-30\r\n---\r\n",
                                                                 b"updated: 2026-09-30\r\nreview_point: R2\r\n---\r\n"))
        self.assertEqual(kept.read_bytes(), before[kept])
        self.assertEqual(subprocess.run(["git", "-C", str(self.p.root), "rev-parse", "HEAD"], capture_output=True,
                                        text=True).stdout, head)
        code, out, _ = self.run_cli("--dry-run")
        self.assertIn("Already set: 3", out)

    def test_refuses_a_target_with_uncommitted_changes(self):
        f = self.p.task("0001-a", status="done")
        for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(self.p.root), *c], check=True, capture_output=True)
        f.write_text(f.read_text() + "\nhand edit\n")
        self.events(spawn("2026-10-02T00:00:00Z", "R2", ["0001-a"]), claim("2026-10-02T01:00:00Z", "0001-a"))
        code, _, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("uncommitted changes", err)
        self.assertNotIn("review_point", f.read_text())


if __name__ == "__main__":
    unittest.main()
