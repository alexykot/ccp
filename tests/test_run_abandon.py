"""SPEC §11.1: a run that will never report is abandoned — superseded by a later round of its task's
phase, or when its task is closed or dropped — and `ccp runs gc` applies the same rules to old records."""
from __future__ import annotations

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import board, config, drill, plane, prompt, runs, seats
from ccp.queue import QueueError, lib
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

HEAD = "a" * 40


def at(s: float) -> str:
    return datetime.fromtimestamp(1_790_000_000 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Abandon(ToolkitFixture, unittest.TestCase):
    def run_rec(self, run_id: str) -> dict:
        return json.loads(runs.path(self.q, run_id).read_text())

    def start(self, agent: str, agent_type: str = "delivery-reviewer"):
        self.ccp("agent", "start", stdin=json.dumps({"agent_id": agent, "agent_type": agent_type, "session_id": "s1"}))

    def stop(self, agent: str, agent_type: str = "delivery-reviewer"):
        self.ccp("agent", "stop", stdin=json.dumps({"agent_id": agent, "agent_type": agent_type}))

    def review(self, *extra: str):
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", self.PR, "--head", HEAD, *extra)
        self.assertEqual(code, 0, out + err)
        return body, err

    def abandoned(self) -> list[dict]:
        return [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("run", "abandoned")]

    def write_run(self, run_id: str, **fields) -> None:
        task, phase, n = runs.parse_id(run_id)
        rec = {"schema_version": 1, "run_id": run_id, "task_id": task, "phase": phase, "round": n,
               "seat": runs.SEAT[phase], "agent_type": runs.AGENT_TYPE[phase], "opened_at": at(n * 10),
               "agent_id": None, "started_at": None, "stopped_at": None, "reported_at": None, "outcome": None, **fields}
        runs.save(self.q, rec)

    # ------------------------------------------------------------- superseded by a new round

    def test_a_stopped_round_is_superseded_by_the_next(self):
        self._push_task_work()
        self.review()
        self.start("r1")
        self.stop("r1")
        body, err = self.review()
        self.assertEqual(body["run_id"], "0002-second/review-2")
        old = self.run_rec("0002-second/review")
        self.assertEqual(runs.state(old), "abandoned")
        self.assertEqual((old["abandoned_reason"], old["abandoned_by"]), ("superseded by 0002-second/review-2", lib.RUNNER))
        self.assertTrue(old["abandoned_at"])
        self.assertEqual(self.abandoned(), [{"run_id": "0002-second/review", "reason": "superseded by 0002-second/review-2"}])
        self.assertEqual([ln for ln in err.splitlines() if "warning" in ln and "behind_tip not checked" not in ln], [])
        self.assertEqual([w for w in body.get("warnings", []) if not w.startswith("behind_tip not checked")], [])

    def test_a_pending_round_is_superseded_with_supersede(self):
        self._push_task_work()
        self.review()
        self.review("--supersede")
        old = self.run_rec("0002-second/review")
        self.assertEqual(old["abandoned_reason"], "superseded by 0002-second/review-2")
        self.assertEqual(len(self.abandoned()), 1)

    def test_a_running_round_is_superseded_with_a_warning(self):
        self._push_task_work()
        self.review()
        self.start("r1")
        body, err = self.review()
        self.assertEqual(runs.state(self.run_rec("0002-second/review")), "abandoned")
        self.assertIn("0002-second/review was still running", err)
        self.assertEqual(len([w for w in body["warnings"] if not w.startswith("behind_tip not checked")]), 1)
        code, _, _, err = self.report("0002-second/review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                                            "## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 1)
        self.assertIn("already abandoned", err)

    def test_another_phase_and_a_reported_round_are_left(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.start("i1", "delivery-implementer")
        self.stop("i1", "delivery-implementer")
        self.review()
        self.report("0002-second/review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.review()
        self.assertEqual(runs.state(self.run_rec("0002-second/implement")), "stopped")
        rev = self.run_rec("0002-second/review")
        self.assertEqual(runs.state(rev), "reported")
        self.assertNotIn("abandoned_at", rev)
        self.assertEqual(self.abandoned(), [])

    # ------------------------------------------------------------- task closed or dropped

    def test_close_abandons_the_tasks_leftover_runs(self):
        head = self._to_approved_pr()
        self.ccp("prompt", "review", "0002", "--pr", self.PR, "--head", head)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "built.")
        self.assertEqual(code, 0, out + err)
        # the verify run recorded its verdict but its worker never ran `ccp report`
        self.assertEqual(body["abandoned_runs"], ["0002-second/review", "0002-second/verify"])
        self.assertEqual(self.run_rec("0002-second/review")["abandoned_reason"], "task closed")
        self.assertEqual(self.run_rec("0002-second/verify")["verdict"], "approve")
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "built.")
        self.assertEqual((code, body["abandoned_runs"]), (0, []), out + err)  # a re-run finds none left

    def test_sync_abandons_a_dropped_tasks_runs(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        st.update(lease_holder=None, status="pending")
        (self.q / "tasks/0002-second.json").write_text(json.dumps(st))
        f = self.runner / "docs/delivery/tasks/0002-second.md"
        f.write_text(f.read_text().replace("status: pending", "status: dropped", 1))
        code, body, out, err = self.ccp("tasks", "sync", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertIn("abandoned run 0002-second/implement (task dropped)", body["changed"][0]["changed"])
        self.assertEqual(runs.state(self.run_rec("0002-second/implement")), "pending")
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.run_rec("0002-second/implement")["abandoned_reason"], "task dropped")

    # ------------------------------------------------------------- ccp runs gc

    def seed_old_records(self):
        self.write_run("0001-first/review", agent_id="a", started_at=at(11), stopped_at=at(12))     # done task
        self.write_run("0002-second/review", agent_id="b", started_at=at(11), stopped_at=at(12))    # superseded
        self.write_run("0002-second/review-2", agent_id="c", started_at=at(21), stopped_at=at(22), reported_at=at(23))
        self.write_run("0002-second/verify", agent_id="d", started_at=at(11))                         # live

    def test_gc_dry_run_then_real_then_nothing(self):
        self.seed_old_records()
        code, body, out, err = self.ccp("runs", "gc", "--dry-run")
        self.assertEqual(code, 0, out + err)
        want = [{"run_id": "0001-first/review", "state": "stopped", "reason": "task closed"},
                {"run_id": "0002-second/review", "state": "stopped", "reason": "superseded by 0002-second/review-2"}]
        self.assertEqual(sorted(body["abandoned"], key=lambda x: x["run_id"]), want)
        self.assertEqual(self.abandoned(), [])
        self.assertEqual(runs.state(self.run_rec("0002-second/review")), "stopped")
        code, body, out, err = self.ccp("runs", "gc")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(sorted(body["abandoned"], key=lambda x: x["run_id"]), want)
        self.assertEqual(len(self.abandoned()), 2)
        self.assertEqual(runs.state(self.run_rec("0002-second/verify")), "running")
        self.assertEqual(runs.state(self.run_rec("0002-second/review-2")), "reported")
        code, body, _, _ = self.ccp("runs", "gc")
        self.assertEqual((code, body["abandoned"]), (0, []))

    def test_an_expired_round_is_abandoned_by_the_next_prompt_and_its_opener_told(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        old = self.run_rec("0002-second/implement")
        old["opened_at"] = ago(runs.PENDING_EXPIRY_S + 60)
        runs.save(self.q, old)
        self.write_run("0001-first/implement", opened_at=ago(0))  # a fresh pending run still refuses this prompt
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 3, out + err)
        old = self.run_rec("0002-second/implement")
        self.assertEqual(old["abandoned_reason"], runs.EXPIRED_REASON)
        self.assertTrue(old["expired_told_at"])
        self.assertEqual(len([ln for ln in err.splitlines() if "0002-second/implement," in ln]), 1)
        self.write_run("0001-first/implement", opened_at=ago(0), agent_id="i0", started_at=ago(0))
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual((code, body["run_id"]), (0, "0002-second/implement-2"), out + err)
        self.assertEqual([ln for ln in err.splitlines() if "0002-second/implement," in ln], [])  # told once

    def test_the_board_lists_no_run_of_a_done_task(self):
        self.write_run("0001-first/review", agent_id="a", started_at=at(11), stopped_at=at(12))
        self.write_run("0002-second/verify", agent_id="d", started_at=at(11))
        cfg = config.load(self.main)
        self.assertEqual([r["run_id"] for r in runs.open_on_live_tasks(self.q, cfg)], ["0002-second/verify"])
        b = board.build(cfg, self.q)
        self.assertEqual([r["run_id"] for r in b["now"]["open_runs"]], ["0002-second/verify"])
        rows = [r["seat"] for r in seats.collect(cfg, self.q, {"runs": [], "seats": {}, "timeline": {}}, {})["rows"]]
        self.assertIn("verifier 0002-second/verify", rows)
        self.assertFalse([s for s in rows if "0001-first" in s])


def ago(s: float) -> str:
    return datetime.fromtimestamp(time.time() - s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class PendingExpiry(unittest.TestCase):
    """§11.1: a pending run whose agent never started within the bound has expired."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)
        self.cfg = SimpleNamespace(project_id="demo")
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        env.start()
        self.addCleanup(env.stop)

    def write_run(self, run_id: str, age: float, by: str | None = "runner-1", **fields) -> None:
        task, phase, n = runs.parse_id(run_id)
        runs.save(self.q, {"schema_version": 1, "run_id": run_id, "task_id": task, "phase": phase, "round": n,
                           "seat": runs.SEAT[phase], "agent_type": runs.AGENT_TYPE[phase], "opened_at": ago(age),
                           "opened_by": by, "agent_id": None, "started_at": None, "stopped_at": None,
                           "reported_at": None, "outcome": None, **fields})

    def rec(self, run_id: str) -> dict:
        return runs.load(self.q, run_id)

    def abandoned_events(self) -> list[dict]:
        rows = [json.loads(ln) for ln in (self.q / "observability" / "events.jsonl").read_text().splitlines() if ln]
        return [e["payload"] for e in rows if (e["type"], e["op"]) == ("run", "abandoned")]

    def test_a_pending_run_past_the_bound_no_longer_blocks_its_agent_type(self):
        old = runs.PENDING_EXPIRY_S + 60
        self.write_run("0001-first/implement", old)
        self.write_run("0003-third/review", old)  # another agent type's: left to its own next prompt
        pending = runs.check_pending(self.q, self.cfg, runs.AGENT_TYPE["implement"], False, "runner-2")
        self.assertEqual(pending, [])
        self.assertEqual(self.rec("0001-first/implement")["abandoned_reason"], runs.EXPIRED_REASON)
        self.assertEqual(runs.state(self.rec("0003-third/review")), "pending")
        self.assertEqual(self.abandoned_events(), [{"run_id": "0001-first/implement", "reason": runs.EXPIRED_REASON}])

    def test_a_fresh_pending_run_still_refuses(self):
        self.write_run("0001-first/implement", runs.PENDING_EXPIRY_S - 60)
        self.write_run("0002-second/implement", runs.PENDING_EXPIRY_S + 60, opened_at="not a time")
        with self.assertRaises(QueueError) as e:
            runs.check_pending(self.q, self.cfg, runs.AGENT_TYPE["implement"], False, "runner-2")
        self.assertEqual(e.exception.code, 3)
        self.assertEqual([runs.state(self.rec(r)) for r in ("0001-first/implement", "0002-second/implement")],
                         ["pending", "pending"])
        self.write_run("0001-first/implement", runs.SUPERSEDE_GRACE_S - 30)  # the grace still holds for a fresh one
        with self.assertRaises(QueueError) as e:
            runs.check_pending(self.q, self.cfg, runs.AGENT_TYPE["implement"], True, "runner-2")
        self.assertEqual(e.exception.code, 3)

    def test_gc_abandons_an_expired_pending_run(self):
        old = runs.PENDING_EXPIRY_S + 60
        self.write_run("0001-first/implement", old)
        self.write_run("0002-second/implement", runs.PENDING_EXPIRY_S - 60)
        self.write_run("0003-third/review", old, agent_id="a", started_at=ago(old - 5))  # running: never expires
        self.assertEqual(runs.gc(self.cfg, dry_run=True)["abandoned"],
                         [{"run_id": "0001-first/implement", "state": "pending", "reason": runs.EXPIRED_REASON}])
        self.assertEqual(runs.state(self.rec("0001-first/implement")), "pending")
        self.assertEqual(len(runs.gc(self.cfg)["abandoned"]), 1)
        self.assertEqual(self.rec("0001-first/implement")["abandoned_reason"], runs.EXPIRED_REASON)
        self.assertEqual([runs.state(self.rec(r)) for r in ("0002-second/implement", "0003-third/review")],
                         ["pending", "running"])
        self.assertEqual(runs.gc(self.cfg)["abandoned"], [])

    def start(self, agent: str) -> dict:
        return plane.agent_hook(self.cfg, "start", json.dumps({"agent_id": agent, "session_id": "s1",
                                                               "agent_type": runs.AGENT_TYPE["implement"]}))

    def test_agent_start_binds_no_expired_run(self):
        self.write_run("0001-first/implement", runs.PENDING_EXPIRY_S + 60)  # the oldest, but expired
        self.write_run("0002-second/implement", 30)
        self.assertEqual(self.start("i1")["bound"], "0002-second/implement")
        self.assertEqual(self.rec("0001-first/implement")["abandoned_reason"], runs.EXPIRED_REASON)
        self.write_run("0003-third/implement", runs.PENDING_EXPIRY_S + 60)
        self.assertIsNone(self.start("i2")["bound"])
        self.assertEqual(runs.state(self.rec("0003-third/implement")), "abandoned")
        unbound = [json.loads(ln) for ln in (self.q / "runs" / "_unbound.jsonl").read_text().splitlines()]
        self.assertEqual([u["agent_id"] for u in unbound], ["i2"])

    def told(self, slot: str) -> list[str]:
        err = io.StringIO()
        with redirect_stderr(err):
            prompt.tell_expired(self.q, slot)
        return err.getvalue().splitlines()

    def test_the_opener_is_told_once_on_its_next_prompt(self):
        old = runs.PENDING_EXPIRY_S + 60
        self.write_run("0001-first/implement", old)
        self.write_run("0002-second/implement", old, by="runner-2")
        runs.check_pending(self.q, self.cfg, runs.AGENT_TYPE["implement"], False, "runner-2")
        mine = self.told("runner-1")
        self.assertEqual(len(mine), 1)
        self.assertIn("0001-first/implement,", mine[0])
        self.assertTrue(self.rec("0001-first/implement")["expired_told_at"])
        self.assertNotIn("expired_told_at", self.rec("0002-second/implement"))
        self.assertEqual(self.told("runner-1"), [])
        self.assertEqual(len(self.told("runner-2")), 1)
        self.assertEqual(self.told("runner-2"), [])


class Drill(unittest.TestCase):
    def test_an_abandoned_run_shows_its_reason_and_ends_at_its_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            d = q / "runs" / "0002-second"
            d.mkdir(parents=True)
            base = {"schema_version": 1, "task_id": "0002-second", "phase": "review", "seat": "reviewer",
                    "agent_type": "delivery-reviewer"}
            (d / "review.json").write_text(json.dumps({**base, "run_id": "0002-second/review", "round": 1,
                "opened_at": at(0), "agent_id": "a", "started_at": at(10), "stopped_at": at(300),
                "abandoned_at": at(5000), "abandoned_reason": "superseded by 0002-second/review-2"}))
            (d / "review-2.json").write_text(json.dumps({**base, "run_id": "0002-second/review-2", "round": 2,
                "opened_at": at(400), "agent_id": "b", "started_at": at(410), "stopped_at": at(900),
                "reported_at": at(890), "outcome": "done"}))
            (d / "fix.json").write_text(json.dumps({**base, "run_id": "0002-second/fix", "phase": "fix", "round": 1,
                "seat": "implementer", "opened_at": at(950), "abandoned_at": at(960), "abandoned_reason": "task dropped"}))
            out = drill.collect(q, [{"task_id": "0002-second", "merged_at": at(6000)}], {"runs": [], "timeline": {}},
                                now=1_790_000_000 + 7000)["0002-second"]
        got = {r["run_id"]: r for r in out["runs"]}
        rev = got["0002-second/review"]
        self.assertEqual((rev["state"], rev["abandoned_reason"]), ("abandoned", "superseded by 0002-second/review-2"))
        self.assertEqual(rev["end_at"][:19], at(300)[:19])  # its stop, not the later abandonment
        self.assertIsNone(got["0002-second/review-2"]["abandoned_reason"])
        self.assertIn("abandoned: superseded by 0002-second/review-2", drill.text(out))


if __name__ == "__main__":
    unittest.main()
