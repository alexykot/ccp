"""ccp health (SPEC §27): task merges from git, spans from the queue, the trend, and note/record."""
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

from ccp import cli, health
from tests.helpers import Product

T0 = 1_760_000_000  # 2025-10-09T08:53:20Z


def git(root, *a, env=None):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True, env={**os.environ, **(env or {})}).stdout


def commit(root, msg, at, *extra):
    stamp = f"@{at} +0000"
    git(root, "commit", "-qm", msg, *extra, env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})


class Merges(unittest.TestCase):
    def setUp(self):
        self.p = Product({"architect": {"areas": {"code": ["app/**"], "docs": ["docs/**", "**/*.md"]}}})
        for i in range(1, 6):
            self.p.task(f"{i:04d}-t{i}")
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        commit(self.p.root, "init", T0)
        # 0001: a squash merge; 0002: a merge commit of its task branch; 0003: a later squash of 0001's follow-up
        self.p.write("app/a.py", "a\n" * 10)
        git(self.p.root, "add", "-A")
        commit(self.p.root, "Task 0001: the first thing (#1)", T0 + 3600)
        git(self.p.root, "checkout", "-q", "-b", "task/0002-t2")
        self.p.write("app/b.py", "b\n" * 4)
        self.p.write("docs/b.md", "b\n")
        git(self.p.root, "add", "-A")
        commit(self.p.root, "work on 0002", T0 + 7000)
        git(self.p.root, "checkout", "-q", "main")
        stamp = f"@{T0 + 7200} +0000"
        git(self.p.root, "merge", "-q", "--no-ff", "-m", "Merge pull request #2 from me/task/0002-t2", "task/0002-t2",
            env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
        for msg, at in (("spec: 0003 — a ruling", T0 + 8000), ("ADR-0004 (Proposed): a design (#3)", T0 + 9000),
                        ("0003: spike passed (#4)", T0 + 10800)):
            self.p.write(f"notes/{at}.txt", "x\n")
            git(self.p.root, "add", "-A")
            commit(self.p.root, msg, at)

    def tearDown(self):
        self.p.cleanup()

    def test_merges_name_tasks(self):
        ms = health.merges(self.p.cfg)
        self.assertEqual([(m["task_id"], m["at"]) for m in ms],
                         [("0001-t1", T0 + 3600), ("0002-t2", T0 + 7200), ("0003-t3", T0 + 10800)])

    def test_files_and_areas(self):
        rows = {r["task_id"]: r for r in health.collect(self.p.cfg, None)["tasks"]}
        self.assertEqual((rows["0001-t1"]["files"], rows["0001-t1"]["lines"], rows["0001-t1"]["areas"]),
                         (1, 10, {"code": 10}))
        self.assertEqual(rows["0002-t2"]["areas"], {"code": 4, "docs": 1})
        self.assertIsNone(rows["0002-t2"].get("wall_s"))  # no queue, no wall time

    def test_queue_spans_rounds_and_prompts(self):
        with tempfile.TemporaryDirectory() as qd:
            q = Path(qd)
            d = q / "progress" / "0003-t3"
            d.mkdir(parents=True)
            for name, at in (("implement-report.md", T0 + 9000), ("review-report.md", T0 + 9300),
                             ("fix-report.md", T0 + 9600), ("verify-report.md", T0 + 10200),
                             ("verify-2-report.md", T0 + 10500)):
                (d / name).write_text("r\n")
                os.utime(d / name, (at, at))
            pd = q / "prompts" / "0003-t3"
            pd.mkdir(parents=True)
            (pd / "20251009T094000Z_implement.json").write_text(json.dumps({"prompt_body": "x" * 300}))
            (q / "observability").mkdir()
            (q / "observability" / "events.jsonl").write_text(json.dumps(
                {"at": "2025-10-09T09:30:00Z", "task_id": "0003-t3", "type": "lease", "op": "set"}) + "\n")
            r = {x["task_id"]: x for x in health.collect(self.p.cfg, q)["tasks"]}["0003-t3"]
        start = T0 + 2200  # the lease event, before the first audit
        self.assertEqual(r["wall_s"], T0 + 10800 - start)
        self.assertEqual((r["implementing_s"], r["reviewing_s"], r["verifying_s"]), (9000 - 2200, 600, 900))
        self.assertEqual((r["fix_rounds"], r["review_rounds"], r["verify_rounds"]), (1, 1, 2))
        self.assertEqual((r["prompts"], r["prompt_chars"], r["implement_prompt_chars"]), (1, 300, 300))
        self.assertEqual(r["times"], "recorded, some file mtimes")  # no review/verify launch was recorded

    def test_recorded_times_win_over_file_mtimes(self):
        """A copied or restored queue rewrites file mtimes; the times the queue recorded do not move."""
        with tempfile.TemporaryDirectory() as qd:
            q = Path(qd)
            d = q / "progress" / "0003-t3"
            d.mkdir(parents=True)
            for name in ("implement-report.md", "review-report.md", "verify-report.md"):
                (d / name).write_text("r\n")  # mtime: now, i.e. a copy made today
            (q / "progress" / "0003-t3.json").write_text(json.dumps({"events": [
                {"at": "2025-10-09T09:20:00Z", "from": "pending", "to": "implementing"}]}))
            pd = q / "prompts" / "0003-t3"
            pd.mkdir(parents=True)
            for stamp, phase in (("20251009T093000Z", "implement"), ("20251009T100000Z", "review"),
                                 ("20251009T101500Z", "fix-review"), ("20251009T102000Z", "verify")):
                (pd / f"{stamp}_{phase}.json").write_text("{}")
            (q / "verification").mkdir()
            (q / "verification" / "0003-t3.json").write_text(json.dumps({"checked_at": "2025-10-09T11:30:00+01:00"}))
            r = {x["task_id"]: x for x in health.collect(self.p.cfg, q)["tasks"]}["0003-t3"]
        self.assertEqual(r["times"], "recorded")
        self.assertEqual(r["wall_s"], T0 + 10800 - (T0 + 1600))  # from the 09:20 claim to the merge
        self.assertEqual((r["implementing_s"], r["reviewing_s"], r["verifying_s"]), (2400, 1200, 600))
        self.assertEqual((r["review_rounds"], r["fix_rounds"], r["verify_rounds"]), (1, 1, 1))

    def test_cli_since_and_json(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
            self.assertEqual(cli.main(["--root", str(self.p.root), "health", "--since", "2025-10-09", "--json"]), 0)
        self.assertEqual(len(json.loads(out.getvalue())["tasks"]), 3)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(["--root", str(self.p.root), "health", "--since", "soon"]), 2)


class Trend(unittest.TestCase):
    def rows(self, walls):
        return [{"wall_s": w} for w in walls]

    def test_drift_needs_fifteen_timed_tasks(self):
        t = health.trend(self.rows([3600] * 14), 1.5)
        self.assertIsNone(t["drift_ratio"])
        self.assertFalse(t["drift"])

    def test_drift_ratio(self):
        t = health.trend(self.rows([3600] * 10 + [7200] * 5), 1.5)
        self.assertEqual((t["drift_ratio"], t["drift"]), (2.0, True))
        t = health.trend(self.rows([3600] * 10 + [5000] * 5 + [None]), 1.5)
        self.assertEqual((t["drift_ratio"], t["drift"]), (1.39, False))


class NoteAndRecord(unittest.TestCase):
    def setUp(self):
        self.p = Product({"architect": {"metrics": ["eval_seconds"]}})
        self._q = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": self._q.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "health", *args])
        return code, out.getvalue(), err.getvalue()

    def test_record_builtin_and_named_metrics(self):
        code, _, err = self.ccp("record", "--task", "0001-a", "--metric", "suite_seconds=212", "--metric", "suite_tests=1389",
                               "--metric", "eval_seconds=3.5")
        self.assertEqual(code, 0, err)
        recs = [json.loads(l) for l in (Path(self._q.name) / "health" / "metrics.jsonl").read_text().splitlines()]
        self.assertEqual([(r["metric"], r["value"]) for r in recs],
                         [("suite_seconds_unverified", 212), ("suite_tests_unverified", 1389), ("eval_seconds", 3.5)])  # §27: typed by hand
        self.assertEqual(self.ccp("record", "--task", "0001-a", "--metric", "lines=3")[0], 2)
        self.assertEqual(self.ccp("record", "--task", "0001-a", "--metric", "suite_seconds=fast")[0], 2)

    def test_note_and_notes_since(self):
        self.assertEqual(self.ccp("note", "--text", "a doc that did not help", "--task", "0001-a", "--by", "verifier")[0], 0)
        q = Path(self._q.name)
        n = health.notes(q)
        self.assertEqual((len(n), n[0]["by"], n[0]["task_id"]), (1, "verifier", "0001-a"))
        self.assertEqual(health.notes(q, "2999-01-01T00:00:00Z"), [])
        self.assertEqual(self.ccp("note")[0], 2)

    def test_note_needs_queue_root(self):
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
            with self.assertRaises(SystemExit):
                self.ccp("note", "--text", "x")


if __name__ == "__main__":
    unittest.main()
