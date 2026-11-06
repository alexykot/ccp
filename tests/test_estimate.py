"""SPEC §26.3: task estimation, phase A. Features and the task hash, the reference class and its
fallbacks, quantiles, row versioning and the re-estimate triggers, the backfill's no-leakage rule,
actuals at close (never blocking it), the accuracy maths and the board (escaped)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import board, config, estimate
from tests.helpers import TASK, Product
from tests.test_board_drill import HASH_STUB, Fixture
from tests.test_board_quality import HOSTILE
from tests.test_toolkit import ToolkitFixture, git

BODY = """---
task_id: {tid}
title: A task
status: {status}
kind: {kind}
depends_on: [{deps}]
spec_refs: ["S1", "S2"]
adr_refs: ["ADR-0031", "0007"]
rule_refs: ["E8"]
created: 2026-10-01
updated: 2026-10-01
---

# Task: {tid}

## Intent

Change `src/app/store.py` and `src/app/record.py`; add `ops/new_tool.py`. See `https://x/y` and `-flag`.

## Scope

- **In:** `docs/delivery/WORKERS.md`

## dod_checks

- id: `code-01`
  story: It works.
  steps:
    1. run it, then a mutation of the guard
  expect: exit 0

- id: `code-02`
  story: It still works.
  expect: exit 0

- id: `docs-01`
  expect: one match

## Implementation notes

{notes}

## Verification notes

*Append-only.*
"""


def body(tid="0005-sf-store", status="pending", kind="feature", deps="", notes="*Append-only, newest last.*"):
    return BODY.format(tid=tid, status=status, kind=kind, deps=deps, notes=notes)


def entry(tid, merged, wall, kind="feature", fam=None, areas=(), adrs=(), tokens=None, phases=None, fix=0, start=None,
          **feat):
    """A history entry as `estimate.history` returns it, with its features already read."""
    f = {"kind": kind, "family": fam if fam is not None else estimate.family(tid), "areas": list(areas), "adrs": list(adrs),
         "cited_lines": 100, "dod_checks": 3, "text_chars": 2000, "deps": 0, **feat}
    return {"task_id": tid, "merged_at": float(merged), "start": float(start if start is not None else merged - wall),
            "excluded": False, "rev": None, "features": f,
            "task": {"task_id": tid, "_text": body(tid), "depends_on": [], "status": "done"},
            "actual": {"wall_s": wall, "phases": phases or {"implement": wall / 2, "review": wall / 4, "fix": 0, "verify": wall / 4},
                       "tokens": tokens, "cost_usd": tokens / 1e6 if tokens else None,
                       "rounds": {"review": 1, "fix": fix, "verify": 1},
                       "merged_at": estimate.iso_ep(float(merged)), "start_at": estimate.iso_ep(float(merged - wall))}}


class Features(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.p.write("src/app/store.py", "a\n" * 10)
        self.p.write("src/app/record.py", "b\n" * 5)
        self.p.write("docs/delivery/WORKERS.md", "w\n" * 3)
        (self.p.root / "ops").mkdir()

    def tearDown(self):
        self.p.cleanup()

    def t(self, text):
        return {"_text": text, **_fm(text)}

    def test_features_count_what_the_task_cites_and_checks(self):
        f = estimate.features(self.p.cfg, self.t(body()))
        self.assertEqual((f["kind"], f["family"]), ("feature", "sf"))
        self.assertEqual((f["cited_paths"], f["cited_lines"]), (3, 18))  # the new ops/ file does not exist yet
        self.assertEqual(f["areas"], ["docs/delivery", "ops", "src/app"])
        self.assertEqual((f["adr_refs"], f["adrs"], f["spec_refs"], f["rule_refs"]), (2, [7, 31], 2, 1))
        self.assertEqual((f["dod_checks"], f["dod_kinds"], f["dod_mutation"], f["dod_story"]), (3, {"code": 2, "docs": 1}, 1, 2))
        self.assertEqual(f["deps"], 0)
        for v in f.values():  # numbers, ids and short labels only
            self.assertIsInstance(v, (int, str, list, dict))

    def test_notes_and_status_change_neither_the_hash_nor_the_features(self):
        a = body()
        b = body(status="done", notes="- 2026-10-02 - built it, see `src/app/other.py`\n" * 40)
        self.assertEqual(estimate.task_hash(a), estimate.task_hash(b))
        self.assertEqual(estimate.features(self.p.cfg, self.t(a)), estimate.features(self.p.cfg, self.t(b)))
        self.assertNotEqual(estimate.task_hash(a), estimate.task_hash(a.replace("Change `src", "Rework `src")))

    def test_lines_are_read_at_a_commit_for_the_backfill(self):
        r = self.p.root
        subprocess.run(["git", "init", "-q", str(r)], check=True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t"}
        subprocess.run(["git", "-C", str(r), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(r), "commit", "-qm", "one"], check=True, env=env)
        first = subprocess.run(["git", "-C", str(r), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.p.write("src/app/store.py", "a\n" * 500)
        self.p.write("ops/new_tool.py", "c\n" * 7)
        subprocess.run(["git", "-C", str(r), "commit", "-qam", "two"], check=True, env=env)
        then = estimate.features(self.p.cfg, self.t(body()), rev=first)
        self.assertEqual((then["cited_paths"], then["cited_lines"]), (3, 18))
        now = estimate.features(self.p.cfg, self.t(body()))
        self.assertEqual((now["cited_paths"], now["cited_lines"]), (4, 515))


def _fm(text):
    from ccp import tasklog
    return tasklog.frontmatter(text)


class Baseline(unittest.TestCase):
    def test_quantiles_interpolate(self):
        self.assertEqual(estimate.quantile([100, 200, 300, 400, 500, 600], 0.5), 350)
        self.assertEqual(estimate.quantile([100, 200, 300, 400, 500, 600], 0.9), 550)
        self.assertEqual(estimate.quantile([7], 0.9), 7)
        self.assertIsNone(estimate.quantile([], 0.5))

    def test_the_class_is_the_related_tasks_then_the_kind_then_all(self):
        target = {"kind": "feature", "family": "sf", "areas": ["src/app"], "adrs": [31], "cited_lines": 100, "dod_checks": 3,
                  "text_chars": 2000, "deps": 0}
        pool = [entry(f"00{10 + i}-sf-x", 1000 + i, 600 + i) for i in range(4)] \
            + [entry(f"00{20 + i}-docs-y", 2000 + i, 9000, kind="feature") for i in range(4)] \
            + [entry(f"00{30 + i}-ops-z", 3000 + i, 50, kind="refactor") for i in range(4)]
        b = estimate.baseline(target, pool, 6)
        self.assertEqual(b["tier"], "similar")
        self.assertEqual(sorted(b["reference_tasks"]), [f"00{10 + i}-sf-x" for i in range(4)])
        b = estimate.baseline(target, pool[2:], 6)  # two sf tasks left: too few, so the kind
        self.assertEqual(b["tier"], "kind")
        self.assertTrue(all(t.endswith(("-sf-x", "-docs-y")) for t in b["reference_tasks"]))
        b = estimate.baseline({**target, "family": "new", "areas": [], "adrs": [], "kind": "spike"}, pool[8:9], 6)
        self.assertEqual((b["tier"], b["reference_tasks"]), ("all", ["0030-ops-z"]))
        self.assertIsNone(estimate.baseline(target, [], 6))

    def test_recent_tasks_weigh_more_and_numbers_come_from_the_class(self):
        target = {"kind": "feature", "family": "sf", "areas": [], "adrs": [], "cited_lines": 100, "dod_checks": 3,
                  "text_chars": 2000, "deps": 0}
        pool = [entry(f"{i:04d}-sf-x", 1000 + i, 100 * (i + 1), tokens=(i + 1) * 1_000_000 if i >= 4 else None,
                      fix=1 if i % 2 else 0) for i in range(10)]
        b = estimate.baseline(target, pool, 5)
        self.assertEqual(b["reference_tasks"], [f"{i:04d}-sf-x" for i in (9, 8, 7, 6, 5)])  # identical features: newest first
        self.assertEqual(b["total"], {"p50_s": 800, "p90_s": 960})
        self.assertEqual(b["phases"]["implement"], {"p50_s": 400, "p90_s": 480})
        self.assertEqual(b["reference_tasks_tokens"], [f"{i:04d}-sf-x" for i in (9, 8, 7, 6, 5)])
        self.assertEqual(b["tokens"], {"p50": 8_000_000, "p90": 9_600_000})
        self.assertEqual(b["rounds"]["fix_risk"], 0.6)
        self.assertEqual(b["novelty"]["family"], 10)


class Records(unittest.TestCase):
    """Rows, versions and the re-estimate triggers, with `history` stubbed: no git needed."""

    def setUp(self):
        self.p = Product()
        self.p.write("docs/delivery/tasks/0005-sf-store.md", body(deps='"0004-sf-dep"'))
        self.p.write("docs/delivery/tasks/0004-sf-dep.md", body("0004-sf-dep"))
        self.p.write("docs/delivery/tasks/0003-sf-old.md", body("0003-sf-old", status="done"))
        self.q = Path(tempfile.mkdtemp())
        self.hist = [entry(f"000{i}-sf-h", 1000 + i, 600) for i in range(3)]
        self.stub = mock.patch.object(estimate, "history", lambda cfg, q, tasks=None: [dict(h) for h in self.hist])
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.p.cleanup()
        shutil.rmtree(self.q, ignore_errors=True)

    def run_(self, ids=None, **kw):
        return estimate.estimate_tasks(self.p.cfg, self.q, ids, **kw)

    def test_a_row_is_written_once_and_again_only_when_the_task_or_its_deps_change(self):
        r = self.run_(["0005"])
        self.assertEqual((r["tasks"][0]["action"], r["tasks"][0]["reason"]), ("written", "no baseline yet"))
        rows = estimate.rows(self.q, "0005-sf-store")
        self.assertEqual([(x["source"], x["version"]) for x in rows], [("baseline", 1)])
        row = rows[0]
        self.assertEqual(row["total"], {"p50_s": 600, "p90_s": 600})
        self.assertEqual(row["inputs"]["method"]["name"], "reference-class")
        self.assertEqual(row["inputs"]["deps_done"], [])
        self.assertEqual(self.run_(["0005"])["tasks"][0]["action"], "unchanged")
        # a note or a status change: no new row
        f = self.p.root / "docs/delivery/tasks/0005-sf-store.md"
        f.write_text(f.read_text().replace("*Append-only, newest last.*", "- started").replace("status: pending", "status: in_progress"))
        self.assertEqual(self.run_(["0005"])["tasks"][0]["action"], "unchanged")
        f.write_text(f.read_text().replace("Change `src", "Rework `src"))
        r = self.run_(["0005"])["tasks"][0]
        self.assertEqual((r["action"], r["reason"]), ("written", "the task changed"))
        dep = self.p.root / "docs/delivery/tasks/0004-sf-dep.md"
        dep.write_text(dep.read_text().replace("status: pending", "status: done"))
        r = self.run_(["0005"])["tasks"][0]
        self.assertEqual((r["action"], r["reason"]), ("written", "a dependency merged since: 0004-sf-dep"))
        self.assertEqual([x["version"] for x in estimate.rows(self.q, "0005-sf-store")], [1, 2, 3])
        self.assertEqual(self.run_(["0005"], force=True)["tasks"][0]["reason"], "forced")

    def test_all_covers_open_tasks_dry_run_writes_nothing_and_done_tasks_are_skipped(self):
        r = self.run_(None, dry_run=True)
        self.assertEqual(sorted(x["task_id"] for x in r["tasks"]), ["0004-sf-dep", "0005-sf-store"])
        self.assertEqual({x["action"] for x in r["tasks"]}, {"would write"})
        self.assertFalse((self.q / "estimates").exists())
        self.assertEqual(self.run_(["0003"])["tasks"][0]["action"], "skipped")
        self.assertEqual(self.run_(None)["written"], 2)
        self.assertEqual(self.run_(None)["written"], 0)

    def test_no_history_writes_nothing(self):
        self.hist = []
        r = self.run_(["0005"])["tasks"][0]
        self.assertEqual(r["action"], "skipped")
        self.assertFalse(estimate.rows(self.q, "0005-sf-store"))

    def test_the_cli_needs_baseline_and_shows_rows(self):
        from tests.test_toolkit import ToolkitFixture  # noqa: F401  (the cli import path)
        from ccp import cli
        import io
        from contextlib import redirect_stderr, redirect_stdout
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            def go(*a):
                o, e = io.StringIO(), io.StringIO()
                with redirect_stdout(o), redirect_stderr(e):
                    c = cli.main(["--root", str(self.p.root), *a])
                return c, o.getvalue(), e.getvalue()
            # Without --baseline it is the estimator seat (phase B; tests/test_estimator.py)
            self.assertEqual(go("tasks", "estimate", "0005", "--all", "--baseline")[0], 2)
            c, out, _ = go("tasks", "estimate", "0005", "--baseline")
            self.assertEqual(c, 0, out)
            c, out, _ = go("tasks", "estimate", "show", "0005")
            self.assertIn("baseline  v1", out)
            c, out, _ = go("estimate", "accuracy", "--json")
            self.assertEqual(json.loads(out)["actuals"], 0)


class Backfill(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.q = Path(tempfile.mkdtemp())
        # 0001..0006 merged one after another; 0004 ran long, from before 0003 merged
        self.hist = [entry("0001-sf-a", 1000, 100), entry("0002-sf-b", 2000, 200), entry("0003-sf-c", 3000, 300),
                     entry("0004-sf-d", 4000, 1500, start=2500), entry("0005-sf-e", 5000, 500, tokens=5_000_000),
                     entry("0006-sf-f", 6000, 600, tokens=6_000_000)]
        self.stub = mock.patch.object(estimate, "history", lambda cfg, q, tasks=None: [dict(h) for h in self.hist])
        self.stub.start()

    def tearDown(self):
        self.stub.stop()
        self.p.cleanup()
        shutil.rmtree(self.q, ignore_errors=True)

    def test_each_task_is_estimated_only_from_tasks_merged_before_it_started(self):
        r = estimate.backfill(self.p.cfg, self.q)
        self.assertEqual((r["tasks"], r["baselines"], r["actuals"], r["no_pool"]), (6, 5, 6, 1))
        merged = {h["task_id"]: h["merged_at"] for h in self.hist}
        start = {h["task_id"]: h["start"] for h in self.hist}
        for tid in merged:
            rs = estimate.rows(self.q, tid)
            b = estimate.latest(rs, "baseline")
            if tid == "0001-sf-a":
                self.assertIsNone(b)
                continue
            self.assertTrue(b["backfill"])
            self.assertEqual(b["as_of"], estimate.iso_ep(start[tid]))
            refs = b["inputs"]["reference_tasks"] + b["inputs"]["reference_tasks_tokens"]
            self.assertTrue(refs)
            for ref in refs:
                self.assertLess(merged[ref], start[tid], (tid, ref))
            self.assertNotIn(tid, refs)
            self.assertEqual(estimate.latest(rs, "actual")["wall_s"], self.hist[int(tid[:4]) - 1]["actual"]["wall_s"])
        self.assertEqual(estimate.latest(estimate.rows(self.q, "0004-sf-d"), "baseline")["inputs"]["reference_tasks"],
                         ["0002-sf-b", "0001-sf-a"])  # 0003 merged after 0004 started
        self.assertEqual(estimate.latest(estimate.rows(self.q, "0006-sf-f"), "baseline")["inputs"]["reference_tasks_tokens"],
                         ["0005-sf-e"])
        again = estimate.backfill(self.p.cfg, self.q)
        self.assertEqual((again["baselines"], again["actuals"], again["kept"]), (0, 0, 5))
        self.assertEqual(again["accuracy"], r["accuracy"])

    def test_dry_run_writes_nothing_but_reports_accuracy(self):
        r = estimate.backfill(self.p.cfg, self.q, dry_run=True)
        self.assertFalse((self.q / "estimates").exists())
        self.assertEqual(r["accuracy"]["actuals"], 6)
        self.assertEqual(r["accuracy"]["sources"]["baseline"]["wall"]["n"], 5)

    def test_reference_since_leaves_older_tasks_out(self):
        for h in self.hist[:3]:
            h["excluded"] = True
        estimate.backfill(self.p.cfg, self.q)
        for tid in ("0005-sf-e", "0006-sf-f"):
            refs = estimate.latest(estimate.rows(self.q, tid), "baseline")["inputs"]["reference_tasks"]
            self.assertFalse(set(refs) & {"0001-sf-a", "0002-sf-b", "0003-sf-c"}, refs)

    def test_a_live_row_written_after_the_start_does_not_suppress_the_backfill(self):
        # 0003 started at 2700 s and merged at 3000 s: an `--all` row at 2820 s came in flight
        estimate._append(self.q, {"at": "1970-01-01T00:47:00Z", "as_of": "1970-01-01T00:47:00Z", "task_id": "0003-sf-c",
                                  "source": "baseline", "version": 1, "total": {"p50_s": 1, "p90_s": 2}})
        estimate.backfill(self.p.cfg, self.q)
        rs = estimate.rows(self.q, "0003-sf-c")
        self.assertEqual(sorted(bool(r.get("backfill")) for r in rs if r["source"] == "baseline"), [False, True])
        self.assertTrue(estimate._pair(rs, "baseline")[0]["backfill"])  # the in-flight row is not scored

    def test_a_live_estimate_before_the_merge_is_not_backfilled_over(self):
        estimate._append(self.q, {"at": "1970-01-01T00:20:00Z", "as_of": "1970-01-01T00:20:00Z", "task_id": "0003-sf-c",
                                  "source": "baseline", "version": 1, "total": {"p50_s": 1, "p90_s": 2}})
        estimate.backfill(self.p.cfg, self.q)
        rs = estimate.rows(self.q, "0003-sf-c")
        self.assertEqual([r["source"] for r in rs if r["source"] == "baseline"], ["baseline"])


class Actuals(unittest.TestCase):
    def test_span_phases_are_clipped_to_the_wall_window(self):
        row = {"merged_at": "2026-10-20T12:00:00Z", "wall_s": 100, "implementing_s": 30, "reviewing_s": 50,
               "verifying_s": 1_157_107, "merge_sha": "abc1234"}
        a = estimate.actual_from(Path(tempfile.mkdtemp()), "0086-x", row, None)
        self.assertEqual(a["phases"], {"implement": 30, "review": 50, "fix": None, "verify": 20})
        self.assertEqual((a["wall_s"], a["start_at"], a["phases_from"]), (100, "2026-10-20T11:58:20Z", "spans"))

    def test_run_phases_are_the_union_of_their_runs_inside_the_drill_window(self):
        d = {"wall_s": 1000, "start_at": "2026-10-20T10:00:00Z", "end_at": "2026-10-20T10:16:40Z", "runs": [
            {"phase": "implement", "start_at": "2026-10-20T09:50:00Z", "end_at": "2026-10-20T10:05:00Z"},
            {"phase": "implement", "start_at": "2026-10-20T10:04:00Z", "end_at": "2026-10-20T10:06:00Z"},
            {"phase": "review", "start_at": "2026-10-20T10:10:00Z", "end_at": "2026-10-20T11:00:00Z"}]}
        a = estimate.actual_from(Path(tempfile.mkdtemp()), "0001-x", {"merged_at": "2026-10-20T10:16:40Z", "wall_s": 999}, d)
        self.assertEqual(a["phases"], {"implement": 360, "review": 400, "fix": 0, "verify": 0})
        self.assertEqual((a["wall_s"], a["start_at"]), (1000, "2026-10-20T10:00:00Z"))


class Accuracy(unittest.TestCase):
    def rows_(self, wall, p50, p90, merged="2026-10-20T12:00:00Z", **extra):
        return [{"source": "actual", "at": merged, "merged_at": merged, "wall_s": wall, "tokens": extra.get("tokens"),
                 "cost_usd": None},
                {"source": "baseline", "at": "2026-10-20T09:00:00Z", "as_of": "2026-10-20T09:00:00Z", "version": 1,
                 "total": {"p50_s": p50, "p90_s": p90}, "tokens": extra.get("band"),
                 "inputs": {"features": {"kind": extra.get("kind", "feature"), "family": "sf"}}}]

    def test_shares_ratio_and_bias(self):
        by = {"a": self.rows_(50, 100, 200), "b": self.rows_(150, 100, 200), "c": self.rows_(300, 100, 200),
              "d": self.rows_(100, 100, 200, tokens=10, band={"p50": 20, "p90": 30}),
              "e": [{"source": "actual", "merged_at": "x", "wall_s": 1}]}
        a = estimate.accuracy(by)
        w = a["sources"]["baseline"]["wall"]
        self.assertEqual((a["actuals"], w["n"], w["le_p50"], w["le_p90"], w["share_p50"], w["share_p90"]), (5, 4, 2, 3, 0.5, 0.75))
        self.assertEqual(w["median_ratio"], 1.25)  # 0.5, 1.5, 3, 1
        self.assertEqual(a["sources"]["baseline"]["tokens"]["n"], 1)
        self.assertEqual(a["sources"]["agent"]["wall"], {"n": 0})
        self.assertEqual(a["bias"]["baseline"]["kind"]["feature"]["n"], 4)

    def test_an_estimate_made_after_the_start_is_not_scored(self):
        rs = self.rows_(150, 100, 200)
        rs[0]["start_at"] = "2026-10-20T08:30:00Z"  # the --all row at 09:00 came while the task was in flight
        self.assertIsNone(estimate._pair(rs, "baseline"))
        rs.append({"source": "baseline", "as_of": "2026-10-20T08:30:00Z", "version": 2, "backfill": True,
                   "total": {"p50_s": 10, "p90_s": 20}})
        self.assertEqual(estimate._pair(rs, "baseline")[0]["version"], 2)

    def test_the_estimate_scored_is_the_latest_before_the_merge_live_before_backfill(self):
        rs = self.rows_(150, 100, 200)
        rs.append({"source": "baseline", "as_of": "2026-10-20T13:00:00Z", "version": 2, "total": {"p50_s": 1000, "p90_s": 2000}})
        rs.append({"source": "baseline", "as_of": "2026-10-20T08:00:00Z", "version": 3, "backfill": True,
                   "total": {"p50_s": 10, "p90_s": 20}})
        est, _ = estimate._pair(rs, "baseline")
        self.assertEqual(est["version"], 1)  # after the merge: ignored; the backfill: only without a live one
        self.assertEqual(estimate._pair([r for r in rs if r.get("version") != 1], "baseline")[0]["version"], 3)


class Close(ToolkitFixture, unittest.TestCase):
    def test_close_appends_the_actual_row_once(self):
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        rs = estimate.rows(self.q, "0002-second")
        self.assertEqual([r["source"] for r in rs], ["actual"])
        a = rs[0]
        self.assertIsNotNone(a["wall_s"])
        self.assertEqual(set(a["phases"]), set(estimate.PHASES))
        self.assertEqual(a["phases_from"], "runs")
        self.assertIn("BLOCKER", a["findings"])
        code, *_ = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0)
        self.assertEqual(len(estimate.rows(self.q, "0002-second")), 1)

    def test_a_failing_estimate_never_blocks_the_close(self):
        self._to_approved_pr()
        with mock.patch.object(estimate, "record_actuals", side_effect=RuntimeError("boom")):
            code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("estimate actuals not recorded (RuntimeError: boom)" in w for w in body["warnings"]))
        self.assertEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["status"], "done")


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Page(Fixture, unittest.TestCase):
    def view(self, tid):
        h = HOSTILE
        est = {"source": "baseline" + h, "at": "2026-10-20T09:00:00Z" + h, "version": 1, "tier": "similar" + h,
               "refs": ["0001-first" + h], "backfill": True, "total": {"p50_s": 600, "p90_s": 1200},
               "tokens": {"p50": 1e6, "p90": 2e6}, "cost_usd": {"p50": 1.5, "p90": 3},
               "phases": {"implement": {"p50_s": 300, "p90_s": 600}, "review": None}, "rounds": {"review_p50": 1}}
        acc = {"actuals": 3, "sources": {"baseline": {"wall": {"n": 3, "share_p50": 0.5, "share_p90": 0.9, "median_ratio": "1.1" + h},
                                                      "tokens": {"n": 0}}, "agent": {}},
               "bias": {"baseline": {"kind" + h: {"feature" + h: {"n": 2, "share_p50": 0.5, "share_p90": 1, "median_ratio": 1}}}}}
        return {"tasks": {tid: {"baseline": est, "agent": None, "baseline_scored": est,
                                "actual": {"wall_s": 1500, "phases": {"implement": 700}, "phases_from": "spans" + h,
                                           "tokens": 2e6, "cost_usd": 2.5}}}, "accuracy": acc}

    def render(self, b, tail):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: '#tab=quality', pathname: '/b', search: ''};\n"
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + tail + "\nprocess.stdout.write(JSON.stringify(out.join('')));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_the_build_carries_estimates_and_the_page_renders_them_as_text(self):
        self.seed()
        b = self.build()[0]
        self.assertEqual(b["estimates"]["tasks"], {})
        self.assertEqual(b["estimates"]["accuracy"]["actuals"], 0)
        b["estimates"] = self.view("0002-second")
        html = self.render(b, "\nout.push(estDrill('0002-second')); out.push(estCell('0002-second'));")
        for t in ("<h2>Estimation</h2>", "Estimate against actual", "10m–20m", "over P90", "50% / 90%", "Advisory"):
            self.assertIn(t, html, t)
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)
        self.assertNotIn(HOSTILE, html)
        self.assertIn("&lt;!--&lt;script&gt;", html)

    def test_a_broken_estimates_block_shows_its_banner_and_the_page_renders(self):
        self.seed()
        b = self.build()[0]
        b["estimates"] = {"accuracy": {"sources": "x", "bias": 3}, "tasks": {"0002-second": {"baseline": {"total": 5}}}}
        html = self.render(b, "")
        self.assertIn("Wall time per task", html)
        b["estimates"] = {"_error": "boom" + HOSTILE}
        html = self.render(b, "")
        self.assertIn("Estimates failed to load", html)
        self.assertNotIn("<script", html)
        html = self.render(b, "\nout.push(String(estDrill('__proto__')) + '|' + estCell('constructor'));")
        self.assertIn('|<span class="muted">–</span>', html)


class Config(unittest.TestCase):
    def test_the_estimate_block_is_checked(self):
        for bad, msg in (({"k": 3}, "estimate.k"), ({"reference_since": "last week"}, "estimate.reference_since"),
                         ({"other": 1}, "unknown key")):
            p = Product({"estimate": bad})
            try:
                with self.assertRaises(config.ConfigError) as cm:
                    p.cfg
                self.assertIn(msg, str(cm.exception))
            finally:
                p.cleanup()
        p = Product({"estimate": {"reference_since": "2026-10-21", "k": 8}})
        try:
            self.assertEqual(p.cfg.estimate, {"reference_since": "2026-10-21", "k": 8, "auto": False,
                                              "spec_paths": ["docs/SPEC.md", "SPEC.md", "docs/spec/*.md", "spec/*.md"],
                                              "path_suffixes": None,
                                              "calibration": {"half_life": 40, "min_pairs": 8, "k": None}})
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
