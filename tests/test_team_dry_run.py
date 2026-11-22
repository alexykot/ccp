"""SPEC §16.5: `team.sh runner spawn --dry-run` runs the spawn's refusals, prints its actions and
the readiness checks, and writes nothing to the queue."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ccp import config
from tests.helpers import REVIEW_REGISTER as REGISTER, tagged_task as _tagged
from tests.team_hosting_fixture import TeamCase


def snapshot(q: Path) -> dict[str, str]:
    """Every file under the queue, by its content hash."""
    return {str(p.relative_to(q)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(q.rglob("*")) if p.is_file()}


class TestSpawnDryRun(TeamCase):
    def setUp(self):
        super().setUp()
        for tid in ("0001-a", "0002-b"):
            self.prod.task(tid)
        self.prod.index()

    def check(self, res, name):
        return next(c for c in res["checks"] if c["check"] == name)

    def test_a_dry_run_prints_the_spawn_and_writes_nothing(self):
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertEqual((res["dry_run"], res["ready"]), (True, True))
        self.assertNotIn("failed", res)
        self.assertEqual(res["stale"], [])  # §16.5: no scope task was measured before a change to its paths
        act = res["actions"][-1]
        self.assertEqual((act["action"], act["name"], act["subagent_type"]), ("spawn_teammate", "runner", "ccp:delivery-runner"))
        self.assertNotIn("prompt_ref", res)
        # the prompt is the one the real spawn passes
        code, real, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual(act["prompt"], real["actions"][-1]["prompt"])

    def test_a_scope_task_missing_from_the_log_is_not_ready(self):
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a,0009-z")
        self.assertEqual(code, 1, err)
        self.assertFalse(res["ready"])
        self.assertEqual(res["failed"], ["scope_tasks_exist"])
        self.assertIn("scope_tasks_exist", err)
        self.assertFalse(self.check(res, "scope_tasks_exist")["ok"])
        self.assertIn("0009-z", self.check(res, "scope_tasks_exist")["detail"])
        self.assertTrue(self.check(res, "tasks_check")["ok"])

    def test_a_scope_entry_by_number_names_its_task(self):
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.check(res, "scope_tasks_exist")["ok"])

    def test_a_failing_tasks_check_is_not_ready(self):
        self.prod.task("0003-c", deps=["0099-nowhere"])
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 1, err)
        self.assertEqual((res["ready"], self.check(res, "tasks_check")["ok"]), (False, False))
        self.assertEqual(res["failed"], ["tasks_check"])
        self.assertIn("tasks_check", err)

    def test_no_task_log_is_not_ready(self):
        (self.prod.root / "docs/delivery/plane.json").unlink()
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 1, err)
        self.assertEqual((res["ready"], self.check(res, "task_log")["ok"]), (False, False))
        self.assertEqual(res["failed"], ["task_log"])

    def test_a_live_runner_shows_the_stop_it_would_need_and_is_left_alone(self):
        self.assertEqual(self.team("runner", "spawn", "--scope", "0001-a")[0], 0)
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertEqual(res["would_stop"], "runner")
        self.assertEqual([a["action"] for a in res["actions"]], ["shutdown_teammate", "spawn_teammate"])

    def test_the_spawns_refusals_still_refuse(self):
        before = snapshot(self.q)
        code, _res, err = self.team("runner", "spawn", "--dry-run")
        self.assertEqual(code, 2)
        self.assertIn("--scope required", err)
        self.prod.write("docs/delivery/plane.json", "{not json")
        code, _res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 2)
        self.assertIn("cannot read the product's task log", err)
        self.assertEqual(snapshot(self.q), before)

    def test_dry_run_goes_with_spawn_only(self):
        self.assertEqual(self.team("runner", "spawn", "--scope", "0001-a")[0], 0)
        before = snapshot(self.q)
        for op in ("stop", "rotate", "bind", "prompt"):
            code, _res, err = self.team("runner", op, "--dry-run", "--scope", "0001-a", "--name", "x")
            self.assertEqual(code, 2, op)
            self.assertIn("--dry-run", err)
        self.assertEqual(snapshot(self.q), before)

    def test_the_runner_worktree_is_checked_and_not_made(self):
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["ready"], self.check(res, "runner_worktree")["ok"]), (True, True))
        self.assertFalse((self.prod.root / config.WORKTREES_DIR).exists())
        self.prod.write(f"{config.WORKTREES_DIR}/runner/stray.txt", "x")
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 1, err)
        self.assertEqual((res["ready"], self.check(res, "runner_worktree")["ok"]), (False, False))
        self.assertEqual(res["failed"], ["runner_worktree"])

    def test_several_slots_print_a_spawn_each_and_record_none(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        for tid in ("0001-a", "0002-b"):  # a task needs a path to run beside another
            text = (self.prod.root / f"docs/delivery/tasks/{tid}.md").read_text()
            self.prod.write(f"docs/delivery/tasks/{tid}.md",
                            text.replace("created:", f'paths: ["src/{tid}/"]\ncreated:', 1))
        self.prod.index()
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--count", "2", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertEqual(res["slots"], ["runner-1", "runner-2"])
        self.assertEqual([(a["action"], a["name"]) for a in res["actions"]],
                         [("spawn_teammate", "runner-1"), ("spawn_teammate", "runner-2")])
        self.assertNotIn("runner_worktree", [c["check"] for c in res["checks"]])
        code, real, err = self.team("runner", "spawn", "--count", "2", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual([a["prompt"] for a in res["actions"]], [a["prompt"] for a in real["actions"]])


class TestSpawnNeedsTheIntegrationRef(TeamCase):
    """SPEC §12.1: a spawn that would make a runner worktree, or tell a slot's runner to make one, refuses
    when origin/<integration> does not resolve: dry run or real, before anything is made or written."""
    with_origin = False  # each test sets its origin up: with the integration branch pushed or not

    def setUp(self):
        super().setUp()
        for tid in ("0001-a", "0002-b"):
            self.prod.task(tid)
        self.prod.index()

    def slots(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        (self.q / "work.json").write_text(json.dumps({
            "project_id": "demo", "status": "running", "scope": ["0001-a", "0002-b"],
            "runners": {"runner-1": {"bound_name": "runner-1", "tasks_done": 0, "rotated_at": "2026-11-16T00:00:00Z"},
                        "runner-2": {"bound_name": "runner-2", "tasks_done": 0}}}))

    def made(self):
        runtime = self.prod.root / config.WORKTREES_DIR  # the derived runner worktree is `runner` under it (§8.3)
        return [p.name for p in runtime.iterdir()] if runtime.is_dir() else []

    def test_one_runner_refuses_dry_run_and_real(self):
        self.origin(push=False)
        before = snapshot(self.q)
        for dry in (["--dry-run"], []):
            code, _res, err = self.team("runner", "spawn", *dry, "--scope", "0001-a")
            self.assertEqual(code, 3, err)
            self.assertIn("origin/main", err)
            self.assertEqual(snapshot(self.q), before)
            self.assertEqual(self.made(), [])

    def test_the_binding_names_the_integration_branch(self):
        self.origin()
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text() + "integration_branch: develop\n")
        code, _res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 3, err)
        self.assertIn("origin/develop", err)

    def test_an_existing_runner_worktree_needs_no_ref(self):
        self.origin(push=False)
        from tests.toolkit_fixture import git
        git(self.prod.root, "worktree", "add", "-q", "--detach", str(self.prod.root / config.WORKTREES_DIR / "runner"), "HEAD")
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.check(res, "runner_worktree")["ok"])

    def test_a_ref_pushed_but_not_yet_fetched_is_fetched_before_the_check(self):
        from tests.toolkit_fixture import git
        self.origin()
        git(self.prod.root, "update-ref", "-d", "refs/remotes/origin/main")  # pushed from elsewhere, never fetched
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertTrue(self.check(res, "runner_worktree")["ok"])
        git(self.prod.root, "update-ref", "-d", "refs/remotes/origin/main")
        code, _res, err = self.team("runner", "spawn", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.made(), ["runner"])
        self.assertEqual(git(self.prod.root / config.WORKTREES_DIR / "runner", "rev-parse", "HEAD"),
                         git(self.prod.root, "rev-parse", "main"))

    def check(self, res, name):
        return next(c for c in res["checks"] if c["check"] == name)

    def test_a_slot_respawn_refuses_without_the_ref_and_writes_nothing(self):
        self.origin(push=False)
        self.slots()
        before = snapshot(self.q)
        for dry in (["--dry-run"], []):
            code, _res, err = self.team("runner", "spawn", "--slot", "runner-1", "--review-point", "R1", *dry)
            self.assertEqual(code, 3, err)
            self.assertIn("origin/main", err)
            self.assertEqual(snapshot(self.q), before)
            self.assertEqual(self.made(), [])

    def test_a_slot_respawn_dry_run_prints_that_slots_spawn_only(self):
        self.origin()
        self.slots()
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--slot", "runner-1", "--review-point", "R1", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertEqual((res["dry_run"], res["slots"], res["scope"]), (True, ["runner-1"], ["0001-a", "0002-b"]))
        self.assertEqual([(a["action"], a["name"]) for a in res["actions"]], [("spawn_teammate", "runner-1")])
        self.assertEqual(self.made(), [])
        code, real, err = self.team("runner", "spawn", "--slot", "runner-1", "--review-point", "R1")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["actions"][0]["prompt"], real["actions"][0]["prompt"])
        self.assertEqual(self.made(), [])  # the slot's runner makes its own worktree (`ccp tasks worktree`)


class TestReviewPointDryRun(TeamCase):
    """SPEC §16.5, §22: `--review-point` in a dry run: the point's open tagged tasks are the scope, its
    refusals still refuse, and nothing is written."""

    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.prod, "0001-a", "done", "R8")
        _tagged(self.prod, "0002-b", "pending", "R8")
        _tagged(self.prod, "0003-c", "pending")
        self.prod.index()

    def test_the_points_open_tasks_are_the_scope_and_nothing_is_written(self):
        before = snapshot(self.q)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--review-point", "R8")
        self.assertEqual(code, 0, err)
        self.assertEqual(snapshot(self.q), before)
        self.assertEqual((res["dry_run"], res["ready"], res["scope"]), (True, True, ["0002-b"]))
        code, real, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["actions"][-1]["prompt"], real["actions"][-1]["prompt"])

    def test_a_point_outside_the_register_refuses_and_writes_nothing(self):
        before = snapshot(self.q)
        code, _res, err = self.team("runner", "spawn", "--dry-run", "--review-point", "R9")
        self.assertEqual(code, 2)
        self.assertIn("R9", err)
        self.assertEqual(snapshot(self.q), before)
