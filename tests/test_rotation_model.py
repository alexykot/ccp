"""SPEC §2.4, §24.4: the runner seat runs on, and is measured on, the model its agent definition
declares. The lead's spawn of the runner passes no `model` (a call's model would override the
definition), and a `claude -p` session run from a runner's checkout is not the runner seat's."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from ccp import otel, usage
from tests.test_team_hosting import TeamCase
from tests.test_usage import req

PLANE = Path(__file__).resolve().parents[1]


def declared_model() -> str:
    text = (PLANE / "plugin/agents/delivery-runner.md").read_text()
    return re.search(r"^model:\s*(\S+)", text.split("\n---", 1)[0], re.M).group(1)


class RunnerSeatModel(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.q = Path(self._d.name) / "queue"
        root = Path(self._d.name) / "prod"
        (root / ".rt/runner").mkdir(parents=True)
        (self.q / "board").mkdir(parents=True)
        (self.q / "project.yaml").write_text(f"project_id: demo\nproduct_root: {root}\nrunner:\n  name: runner\n"
                                             f"  worktree: {root}/.rt/runner\n")
        self.root = root

    def tearDown(self):
        self._d.cleanup()

    def write(self, name, rows):
        with (self.q / "board" / name).open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def test_the_runner_seats_requests_are_on_its_declared_model(self):
        model, other = declared_model(), "claude-other-9-9"
        self.assertNotEqual(model, other)
        rows = [req("t1", 1, model=model, out=40),                                     # the runner teammate
                req("h1", 2, model=other, source="sdk", session__id="hs-1", cwd=f"{self.root}/.rt/runner", out=7),
                req("m1", 3, model=model, source="repl_main_thread", session__id="rs-1",  # a session in its checkout
                    cwd=f"{self.root}/.rt/runner", out=5)]
        self.write("usage-requests.jsonl", [{k.replace("__", "_"): v for k, v in r.items() if k != "t"}
                                            | {"at": otel._iso(r["t"])} for r in rows])
        self.write("usage-spans.jsonl", [{"request_id": "t1", "agent_id": "runner@session-abc"},
                                         {"request_id": "h1"}, {"request_id": "m1"}])
        r = usage.fold(self.q)
        self.assertEqual(r["seats"]["runner"]["observed_models"], [model])
        self.assertEqual(r["seats"]["runner"]["output_tokens"], 45)
        self.assertEqual(r["seats"][usage.UNTAGGED]["observed_models"], [other])
        self.assertEqual([x["model"] for x in r["recent"]["seats"]["runner"]], [model, model])


class RunnerSpawnModel(TeamCase):
    def spawns(self, *argv):
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b", *argv)
        self.assertEqual(code, 0, err)
        return [a for a in res["actions"] if a["action"] == "spawn_teammate"]

    def test_the_spawn_leaves_the_model_to_the_runners_definition(self):
        acts = self.spawns()
        self.assertEqual(len(acts), 1)
        self.assertTrue(acts[0]["subagent_type"].endswith("delivery-runner"), acts[0])
        self.assertNotIn("model", acts[0])

    def test_several_runners_spawn_without_a_model_too(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        acts = self.spawns("--count", "2")
        self.assertEqual(len(acts), 2)
        for a in acts:
            self.assertNotIn("model", a)

    def test_the_definition_pins_a_full_model_id(self):
        self.assertRegex(declared_model(), r"^claude-[a-z]+-\d")


if __name__ == "__main__":
    unittest.main()
