"""A product with no `parallel` block runs up to `config.PARALLEL_DEFAULTS["max_in_flight"]` tasks at once under
the `clashes` schedule: `ccp tasks claim` lets two tasks whose paths meet both in, a recorded clash keeps them
apart, and the team script and the idle hook read the same slot count as `ccp`. The two knobs set back give the
old behaviour."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from unittest import mock

from ccp import config, parallel
from tests.parallel_claims_fixture import ParallelFixture, task
from tests.team_hosting_fixture import HOOK, PLANE, TeamCase


class NoParallelBlock(ParallelFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        plane = json.loads((self.main / "docs/delivery/plane.json").read_text())
        plane.pop("parallel")  # the subject: a product that says nothing about parallel work
        self.write("docs/delivery/plane.json", json.dumps(plane))

    def test_the_defaults_are_three_slots_scheduled_by_clashes(self):
        got = parallel.settings(config.load(self.main))
        self.assertEqual((got["max_in_flight"], got["schedule"]), (3, "clashes"))
        self.assertTrue(parallel.enabled(config.load(self.main)))

    def test_two_tasks_whose_paths_meet_both_claim_and_the_slots_are_three(self):
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.claim("0004")  # 0002 and 0004 both hold `src/app/pool.py`
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.claim("0003")[0], 0)
        self.assertEqual(self.work()["in_flight"], ["0002-second", "0004-fourth", "0003-third"])
        code, _, out, err = self.claim("0007")  # parallel: true, so only the slots keep it out
        self.assertEqual(code, 7, out + err)
        self.assertIn("rule 1", err)

    def test_a_recorded_clash_keeps_two_tasks_apart(self):
        self.write("docs/delivery/tasks/0004-fourth.md",
                   task("0004-fourth", "`src/app/pool.py`", extra='clashes_with: ["0002-second"]\n'))
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 7, out + err)
        self.assertIn("clashes with in-flight 0002-second (clashes_with, rule 3)", err)

    def test_one_slot_or_the_paths_schedule_gives_the_old_behaviour(self):
        self.plane(max_in_flight=1)
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, _ = self.next()  # one runner: the task in flight, to resume, not a second one
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("0002-second"), out)
        self.ccp("tasks", "release", "0002", "--reason", "t", root=self.main)
        self.plane(schedule="paths")  # no max_in_flight: the default's three slots, paths decide
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 7, out + err)
        self.assertIn("`src/app/pool.py` meets in-flight 0002-second", err)


class ReadersAgree(TeamCase):
    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))

    def team_module(self):
        with mock.patch.object(sys, "path", list(sys.path)):
            spec = importlib.util.spec_from_file_location("team_by_default", PLANE / "scripts/observability/team.py")
            team = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(team)
            return team

    def test_the_team_script_reads_ccps_slot_count(self):
        team = self.team_module()
        want = parallel.settings(config.load(self.prod.root))["max_in_flight"]
        self.assertEqual(want, config.PARALLEL_DEFAULTS["max_in_flight"])
        self.assertEqual(team.max_in_flight(self.q), want)
        self.assertTrue(team.parallel_on(self.q))

    def test_the_idle_hook_treats_the_product_as_parallel(self):
        for tid, path in (("0001-a", "a.py"), ("0002-b", "b.py")):
            self.prod.task(tid)
            f = self.prod.root / f"docs/delivery/tasks/{tid}.md"
            f.write_text(f.read_text().replace("- **In:** it", f"- **In:** `{path}`"))
        self.prod.index()
        (self.q / "work.json").write_text(json.dumps({
            "status": "running", "scope": ["0001-a", "0002-b"], "in_flight": [],
            "runners": {"runner-2": {"bound_name": "runner-2-x"}}}))
        r = subprocess.run(["bash", HOOK, "--queue-root", self.q, "--ccp", PLANE / "bin" / "ccp"], capture_output=True,
                           text=True, env=self.env, input=json.dumps({
                               "hook_event_name": "TeammateIdle", "teammate_name": "runner-2-x",
                               "cwd": str(self.prod.root)}))
        self.assertEqual(r.returncode, 2, r.stderr)  # a slot with a task to claim: `next` was asked
        self.assertIn("ccp tasks claim 0001-a --holder runner-2", r.stderr)


if __name__ == "__main__":
    unittest.main()
