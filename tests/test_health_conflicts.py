"""SPEC §11.1, §27.1: `ccp report` records each done change round's integration merges and whether they
conflicted, and `ccp health` counts the conflicted ones before and after review, with the cost of the rounds that
held them. The git history is real (a task branch, an integration tip that moves, hand-made merge commits); the
health tests write run records and telemetry rows straight into a fenced queue."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ccp import gitmerge, health, runs
from tests import test_review_gate
from tests.test_toolkit import GIT_ENV, ToolkitFixture, git


def sh(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env={**os.environ, **GIT_ENV})


class RoundReport(ToolkitFixture, unittest.TestCase):
    run_phase = test_review_gate.ReviewGate.run_phase
    review = test_review_gate.ReviewGate.review

    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution, and the review order reads it
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")
        m = self.main
        self.write("shared.txt", "one\ntwo\nthree\n")
        self.write("other.txt", "alpha\n")
        git(m, "add", "shared.txt", "other.txt")
        git(m, "commit", "-q", "-m", "base")
        git(m, "push", "-q", "origin", "main")

    def record(self, run_id: str) -> dict:
        return runs.load(self.q, run_id)

    def branch(self) -> str:
        """The task branch's head H1: one change to a line of shared.txt, forked before the tip moves."""
        m = self.main
        git(m, "checkout", "-q", "-b", "feat")
        self.write("shared.txt", "one\ntask change\nthree\n")
        git(m, "commit", "-q", "-am", "task change")
        h1 = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return h1

    def implement(self, head: str) -> str:
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", git(self.main, "rev-parse", "origin/main"))
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(body["run_id"], f"Outcome: done\nPR: #7\nHead: {head}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def move_tip(self, conflict: bool) -> str:
        """The tip moves and the task branch merges it: with `conflict` both changed one line and the merge
        commit holds a hand resolution, else the merge was clean. The merge commit."""
        m = self.main
        if conflict:
            self.write("shared.txt", "one\ntip change\nthree\n")
        else:
            self.write("other.txt", self.main.joinpath("other.txt").read_text() + "beta\n")
        git(m, "commit", "-q", "-am", "tip change")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "feat")
        merged = sh(m, "merge", "-q", "--no-edit", "origin/main")
        self.assertEqual(merged.returncode, 1 if conflict else 0, merged.stdout + merged.stderr)
        if conflict:
            self.write("shared.txt", "one\ntask change and tip change\nthree\n")
            git(m, "add", "shared.txt")
            git(m, "commit", "-q", "--no-edit")
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return head

    def test_a_merge_round_records_its_conflict_and_a_clean_one_does_not(self):
        h1 = self.branch()
        first = self.implement(h1)
        self.review(h1)
        h2 = self.move_tip(conflict=True)
        merge = self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        h3 = self.move_tip(conflict=False)
        second = self.run_phase("merge", h2, f"PR: #7\nHead: {h3}")
        got = self.record(merge)
        self.assertEqual(got["integration_merges"], [{"sha": h2, "conflicted": True, "files": 1}])
        self.assertIs(got["before_review"], False)
        self.assertEqual(self.record(second)["integration_merges"], [{"sha": h3, "conflicted": False, "files": 0}])
        self.assertEqual(self.record(first)["integration_merges"], [])  # no merge in origin/main..H1
        self.assertIs(self.record(first)["before_review"], True)

    def test_a_head_not_in_the_object_store_records_no_merges_and_the_report_stands(self):
        h1 = self.branch()
        self.implement(h1)
        self.review(h1)
        fix = self.run_phase("fix", h1, "PR: #7\nHead: " + "deadbeef" * 5)
        got = self.record(fix)
        self.assertNotIn("integration_merges", got)
        self.assertEqual(got["outcome"], "done")

    def test_a_probe_git_could_not_run_records_no_merges_and_the_report_stands(self):
        h1 = self.branch()
        self.implement(h1)
        h2 = self.move_tip(conflict=False)
        failed = gitmerge.Probe("", failed=True, returncode=129)
        with mock.patch("ccp.gitmerge.probe", return_value=failed):
            merge = self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        self.assertNotIn("integration_merges", self.record(merge))

    def test_a_merge_of_something_else_is_not_an_integration_merge(self):
        m = self.main
        h1 = self.branch()
        git(m, "checkout", "-q", "-b", "side", h1)
        self.write("side.txt", "side\n")
        git(m, "add", "side.txt")
        git(m, "commit", "-q", "-m", "side work")
        git(m, "checkout", "-q", "feat")
        self.assertEqual(sh(m, "merge", "-q", "--no-ff", "--no-edit", "side").returncode, 0)
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        self.assertEqual(self.record(self.implement(head))["integration_merges"], [])

    def test_a_round_measures_from_the_previous_rounds_head(self):
        h1 = self.branch()
        self.implement(h1)
        self.review(h1)
        h2 = self.move_tip(conflict=True)
        first = self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        fix = self.run_phase("fix", h2, f"PR: #7\nHead: {h2}")  # nothing new since the merge round's head
        self.assertEqual(len(self.record(first)["integration_merges"]), 1)
        self.assertEqual(self.record(fix)["integration_merges"], [])
        self.assertIs(self.record(fix)["before_review"], False)

    def test_a_correction_measures_again_and_a_blocked_report_records_nothing(self):
        h1 = self.branch()
        self.implement(h1)
        self.review(h1)
        h2 = self.move_tip(conflict=True)
        merge = self.run_phase("merge", h1, f"PR: #7\nHead: {h2}")
        self.assertEqual(len(self.record(merge)["integration_merges"]), 1)
        tok = self.record(merge)["prompt_token"]
        code, _, out, err = self.report(merge, f"Outcome: done\nPR: #7\nHead: {'deadbeef' * 5}\nPrompt: {tok}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("integration_merges", self.record(merge))
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", h2)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(body["run_id"], "Outcome: blocked\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        self.assertTrue({"integration_merges", "before_review"}.isdisjoint(self.record(body["run_id"])))


class Counts(ToolkitFixture, unittest.TestCase):
    ADOPTED = "2026-11-05T00:00:00Z"

    def setUp(self):
        super().setUp()
        self.agents = 0
        self.rows: list[dict] = []
        self.spans: list[dict] = []
        events = self.q / "observability" / "events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(json.dumps({"at": self.ADOPTED, "project_id": "demo", "task_id": "", "actor": "operator",
                                      "type": "plane", "op": "adopted", "payload": {"plane": "abc", "binding": "kept"}}) + "\n")

    def run_record(self, run_id: str, opened: str, reported: str | None, tokens: int = 0, **extra) -> str:
        """A run record with its report time and the tokens telemetry attributes to it (one request)."""
        tid, name = run_id.split("/")
        phase = name.split("-")[0]
        self.agents += 1
        rec = {"run_id": run_id, "task_id": tid, "phase": phase, "opened_at": f"2026-11-10T{opened}Z",
               "started_at": None, "reported_at": f"2026-11-10T{reported}Z" if reported else None, "outcome": "done",
               "agent_id": f"a{self.agents}", **extra}
        p = self.q / "runs" / tid / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec))
        if tokens:
            rid = f"req-{self.agents}"
            self.rows.append({"request_id": rid, "at": "2026-11-10T10:00:00Z", "model": "claude-opus-5-5", "effort": "high",
                              "input_tokens": tokens // 2, "output_tokens": tokens - tokens // 2, "cache_read_tokens": 0,
                              "cache_creation_tokens": 0, "cost_usd": 0.01})
            self.spans.append({"request_id": rid, "agent_id": rec["agent_id"]})
        return run_id

    def telemetry(self):
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        (b / "usage-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows))
        (b / "usage-spans.jsonl").write_text("".join(json.dumps(s) + "\n" for s in self.spans))

    def catch_ups(self, *args: str) -> dict:
        self.telemetry()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            code, body, out, err = self.ccp("health", "--json", *args, root=self.main)
        self.assertEqual(code, 0, out + err)
        return body["conflict_catch_ups"]

    def hit(self, conflicted: bool = True) -> list[dict]:
        return [{"sha": "a" * 40, "conflicted": conflicted, "files": 1 if conflicted else 0}]

    def fill(self):
        """An implement round before review (one conflicted merge, 600 s, 1000 tokens); a merge round after it
        (one, 300 s, 400 tokens) and its resolution review (120 s, 200 tokens); a fix round with a clean merge
        (500 tokens); a change round with no record (700 tokens)."""
        t = "0002-second"
        self.run_record(f"{t}/implement", "10:00:00", "10:10:00", 1000, integration_merges=self.hit(), before_review=True)
        self.run_record(f"{t}/review", "10:20:00", "10:30:00", 90, mode=None)
        self.run_record(f"{t}/merge", "11:00:00", "11:05:00", 400, integration_merges=self.hit(), before_review=False)
        self.run_record(f"{t}/review-2", "11:06:00", "11:08:00", 200, mode="resolution")
        self.run_record(f"{t}/fix", "12:00:00", "12:05:00", 500, integration_merges=self.hit(False), before_review=False)
        self.run_record("0003-third/implement", "09:00:00", "09:30:00", 700)

    def test_conflicts_before_and_after_review_with_their_cost(self):
        self.fill()
        c = self.catch_ups()
        self.assertEqual(c["before_review"], {"count": 1, "rounds": 1, "wall_s": 600, "tokens": 1000})
        self.assertEqual(c["after_review"], {"count": 1, "rounds": 1, "resolution_reviews": 1, "wall_s": 420, "tokens": 600})
        self.assertEqual((c["clean_merges"], c["unmeasured"]), (1, 1))

    def test_a_round_reported_before_the_window_is_left_out_and_the_text_has_the_line(self):
        self.fill()
        self.run_record("0004-fourth/merge", "08:00:00", "08:10:00", 50, integration_merges=self.hit(), before_review=False)
        old = self.q / "runs" / "0004-fourth" / "merge.json"
        rec = json.loads(old.read_text())
        rec.update(opened_at="2026-11-01T08:00:00Z", reported_at="2026-11-01T08:10:00Z")
        old.write_text(json.dumps(rec))
        c = self.catch_ups()
        self.assertEqual((c["after_review"]["count"], c["after_review"]["rounds"]), (1, 1))
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            code, _, out, err = self.ccp("health", root=self.main)
        self.assertEqual(code, 0, err)
        [line] = [ln for ln in out.splitlines() if "onflict catch-ups" in ln]
        self.assertIn("1 before review", line)
        self.assertIn("1 after review", line)
        self.assertEqual(health.conflict_text(None), None)

    def test_each_resolution_review_counts_with_the_merge_round_it_followed(self):
        t = "0002-second"
        self.run_record(f"{t}/review", "10:20:00", "10:30:00")
        self.run_record(f"{t}/merge", "11:00:00", "11:05:00", 10, integration_merges=self.hit(), before_review=False)
        self.run_record(f"{t}/review-2", "11:06:00", "11:07:00", 1, mode="resolution")
        self.run_record(f"{t}/merge-2", "11:10:00", "11:15:00", 20, integration_merges=self.hit(), before_review=False)
        self.run_record(f"{t}/review-3", "11:16:00", "11:18:00", 2, mode="resolution")
        self.run_record(f"{t}/fix", "11:30:00", "11:35:00", 5, integration_merges=self.hit(False), before_review=False)
        self.run_record(f"{t}/review-4", "11:36:00", "11:38:00", 4, mode="resolution")  # follows a round with no conflict
        c = self.catch_ups()["after_review"]
        self.assertEqual((c["count"], c["rounds"], c["resolution_reviews"]), (2, 2, 2))
        self.assertEqual((c["wall_s"], c["tokens"]), (300 + 300 + 60 + 120, 33))

    def test_rounds_that_did_not_finish_or_were_abandoned_are_not_counted(self):
        t = "0002-second"
        self.run_record(f"{t}/implement", "10:00:00", "10:10:00", 0, integration_merges=self.hit(), before_review=True,
                        outcome="blocked")
        self.run_record(f"{t}/fix", "11:00:00", None, 0, abandoned_at="2026-11-10T11:30:00Z")
        self.run_record(f"{t}/merge", "12:00:00", None, 0)
        c = self.catch_ups()
        self.assertEqual(c["before_review"]["count"] + c["after_review"]["count"] + c["clean_merges"] + c["unmeasured"], 0)

    def test_no_runs_is_all_zero(self):
        c = self.catch_ups()
        self.assertEqual(c["before_review"], {"count": 0, "rounds": 0, "wall_s": 0, "tokens": 0})
        self.assertEqual(c["after_review"], {"count": 0, "rounds": 0, "resolution_reviews": 0, "wall_s": 0, "tokens": 0})
        self.assertEqual((c["clean_merges"], c["unmeasured"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
