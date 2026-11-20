"""SPEC §29.3, §3.6: a release (`run-checkout.sh update`) records in each bound product's queue an
`upgrade` notice of the `adopt` steps the release brought that the product has not taken, none for a
product that took them, and writes nothing to a product's repository."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_sync_on_release import GIT_ENV, PLANE, SCRIPT, git, run

TASK = """---
task_id: {tid}
title: A knob
status: {status}
adopt: "plane.json verify.accept_cache"
depends_on: []
spec_refs: ["S1"]
created: 2026-09-30
updated: 2026-09-30
---

# Task: {tid}

## Intent

Something true for the user.

## Context (not verified)

- background

## Scope

- **In:** it

## dod_checks

- id: `cmd-01`
  story: As an operator, I run it.
  steps:
    1. run
  expect: exit 0

## Implementation notes

*Append-only, newest last.*

## Verification notes

{ver}
"""
TID = "0001-a-knob"
# The run checkout's own code: present, untracked (as a clean checkout's ignored files would be), so
# its `ccp` reads the scratch plane's task log as the plane's.
CODE = ("ccp", "bin", "contracts", "plugin", "scripts/observability")


class ReleaseLeavesAnUpgradeNotice(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name).resolve()
        self.origin, self.seed, self.run_dir = self.d / "origin.git", self.d / "seed", self.d / "run"
        run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)])
        run(["git", "clone", "-q", str(self.origin), str(self.seed)])
        git(self.seed, "checkout", "-q", "-b", "main")
        (self.seed / "docs/delivery").mkdir(parents=True)
        (self.seed / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "plane"}))
        self.plane_task("pending", "the task is in flight")
        run(["git", "clone", "-q", str(self.origin), str(self.run_dir)])
        for rel in CODE:
            shutil.copytree(PLANE / rel, self.run_dir / rel, ignore=shutil.ignore_patterns("__pycache__"))
        (self.run_dir / "projects").mkdir()
        self.env = {"CCP_RUN_CHECKOUT": str(self.run_dir), "CCP_BIN_LINK": str(self.d / "link/ccp"),
                    "CCP_BINDINGS_DIR": str(self.run_dir / "projects")}

    def tearDown(self):
        self._tmp.cleanup()

    def plane_task(self, status: str, msg: str) -> str:
        ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
        (self.seed / f"docs/delivery/tasks/{TID}.md").parent.mkdir(parents=True, exist_ok=True)
        (self.seed / f"docs/delivery/tasks/{TID}.md").write_text(TASK.format(tid=TID, status=status, ver=ver))
        git(self.seed, "add", "docs")
        git(self.seed, "commit", "-qm", msg)
        git(self.seed, "push", "-q", "origin", "main")
        return git(self.seed, "rev-parse", "HEAD")

    def product(self, name: str, plane_json: dict) -> tuple[Path, Path]:
        """A committed, conforming product, bound with a queue of its own."""
        root, q = self.d / name, self.d / "queues" / name
        (root / "docs/delivery/tasks").mkdir(parents=True)
        (root / "docs/delivery/tasks/.gitkeep").write_text("")
        (root / "docs/delivery/plane.json").write_text(json.dumps({"project_id": name, **plane_json}))
        git(root, "init", "-q", "-b", "main")
        r = run([str(PLANE / "bin/ccp"), "--root", str(root), "tasks", "index"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        git(root, "add", "docs")
        git(root, "commit", "-qm", "conforming")
        q.mkdir(parents=True)
        (self.run_dir / "projects" / f"{name}.yaml").write_text(
            f"project_id: {name}\nintegration_branch: main\nproduct_root: {root}\nqueue_root: {q}\n")
        return root, q

    def ccp(self, root: Path, q: Path, *args: str) -> subprocess.CompletedProcess:
        return run([str(PLANE / "bin/ccp"), "--root", str(root), *args], env={"QUEUE_ROOT": str(q)})

    def pending(self, root: Path, q: Path) -> list[dict]:
        r = self.ccp(root, q, "notify", "pending")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["pending"]

    def test_the_product_that_has_not_taken_the_step_gets_one_notice_and_the_other_none(self):
        behind, q1 = self.product("behind", {})
        ahead, q2 = self.product("ahead", {"verify": {"accept_cache": {"max_age_days": 7}}})
        release = self.plane_task("done", "the task merged")
        r = run([SCRIPT, "update"], env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("run-checkout: product behind (main ", r.stdout)
        self.assertIn("run-checkout: product ahead (main ", r.stdout)
        self.assertNotIn("not recorded", r.stdout)
        [n] = self.pending(behind, q1)
        self.assertEqual((n["trigger"], n["id"]), ("upgrade", release))
        self.assertIn(f"{TID}: plane.json verify.accept_cache", n["reason"])
        self.assertEqual(self.pending(ahead, q2), [])
        # The lead finds it in the orientation the release's `ccp` gives.
        o = run([str(self.run_dir / "bin/ccp"), "--root", str(behind), "orientation"], env={"QUEUE_ROOT": str(q1)})
        self.assertEqual(o.returncode, 0, o.stderr)
        self.assertIn(f"upgrade: {release}", o.stdout)
        self.assertIn("plane.json verify.accept_cache", o.stdout)
        # Nothing is written to either product's repository.
        for root in (behind, ahead):
            self.assertEqual(git(root, "status", "--porcelain"), "")

    def test_an_update_that_brings_nothing_records_nothing(self):
        behind, q1 = self.product("behind", {})
        self.plane_task("done", "the task merged")
        self.assertEqual(run([SCRIPT, "update"], env=self.env).returncode, 0)
        self.assertEqual(len(self.pending(behind, q1)), 1)
        r = run([SCRIPT, "update"], env=self.env)  # already at origin/main
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("upgrade notice", r.stdout)
        events = (q1 / "observability/events.jsonl").read_text().splitlines()
        self.assertEqual(sum('"notify"' in e for e in events), 1)

    def test_a_binding_with_no_queue_is_reported_and_the_update_still_succeeds(self):
        root, _q = self.product("noqueue", {})
        b = self.run_dir / "projects/noqueue.yaml"
        b.write_text(b.read_text().replace(f"queue_root: {self.d / 'queues/noqueue'}", "queue_root: /nonexistent/q"))
        self.plane_task("done", "the task merged")
        r = run([SCRIPT, "update"], env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("upgrade notice for noqueue not recorded", r.stdout)
        self.assertIn("run-checkout: product noqueue (main ", r.stdout)
        self.assertEqual(git(root, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
