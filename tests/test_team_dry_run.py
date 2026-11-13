"""SPEC §16.5: `team.sh runner spawn --dry-run` runs the spawn's refusals, prints its actions and
the readiness checks, and writes nothing to the queue."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.test_team_hosting import TeamCase


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
        yaml = (self.q / "project.yaml").read_text()
        (self.q / "project.yaml").write_text(yaml.replace("  name: runner\n", "  name: runner\n  worktree: rwt\n"))
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["ready"], self.check(res, "runner_worktree")["ok"]), (True, True))
        self.assertFalse((self.prod.root / "rwt").exists())
        self.prod.write("rwt/stray.txt", "x")
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
