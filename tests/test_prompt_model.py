"""SPEC §2.4: plane.json `workers.implementer_model` picks the implementer's model per task. `ccp prompt
implement` prints it in the Agent call (`model`) for a `small` task (its estimate at most
`workers.small_estimate_minutes`) or a `refactor` one, and the run expects it; with the knob unset, or for a
task neither arm matches, the call carries no `model`."""
from __future__ import annotations

import json
import re
import unittest

from ccp import config
from tests.helpers import Product
from tests.test_toolkit import ToolkitFixture

SONNET = "claude-sonnet-5-5"
KNOB = {"implementer_model": {"small": SONNET, "refactor": SONNET}}


class PickedModel(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "workers": KNOB}

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        self.task = self.runner / "docs/delivery/tasks/0002-second.md"

    def shape(self, minutes: float | None, kind: str = "feature", source: str = "baseline") -> None:
        """Task 0002 as a task of `kind` whose latest `source` estimate is `minutes` (none: no estimate)."""
        text = re.sub(r"^kind: .*\n", "", self.task.read_text(), flags=re.M)
        self.task.write_text(text.replace("\nstatus:", f"\nkind: {kind}\nstatus:", 1))
        est = self.q / "estimates" / "0002-second.jsonl"
        est.parent.mkdir(exist_ok=True)
        est.unlink(missing_ok=True)
        if minutes is not None:
            est.write_text(json.dumps({"at": "2026-11-01T00:00:00Z", "as_of": "2026-11-01T00:00:00Z",
                                       "task_id": "0002-second", "source": source, "version": 1,
                                       "total": {"p50_s": minutes * 60, "p90_s": minutes * 120}}) + "\n")

    def implement(self) -> dict:
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        return body

    def run_rec(self, body: dict) -> dict:
        return json.loads((self.q / "runs" / f"{body['run_id']}.json").read_text())

    def test_a_small_task_gets_the_small_model(self):
        self.shape(20)
        body = self.implement()
        self.assertEqual(body["agent_call"]["model"], SONNET)
        self.assertEqual((body["expected_model"], self.run_rec(body)["expected_model"]), (SONNET, SONNET))

    def test_a_refactor_gets_the_refactor_model_whatever_its_estimate(self):
        self.shape(90, kind="refactor")
        self.assertEqual(self.implement()["agent_call"]["model"], SONNET)

    def test_a_large_feature_carries_no_model(self):
        self.shape(90)
        body = self.implement()
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], "claude-opus-5-5")  # the definition's

    def test_the_bound_is_inclusive_and_an_unestimated_task_is_not_small(self):
        self.shape(30)
        self.assertEqual(self.implement()["agent_call"].get("model"), SONNET)
        self.shape(31)
        self.assertNotIn("model", self.implement()["agent_call"])
        self.shape(None)
        self.assertNotIn("model", self.implement()["agent_call"])

    def test_the_agent_estimate_comes_before_the_baseline(self):
        self.shape(90)
        with (self.q / "estimates" / "0002-second.jsonl").open("a") as fh:
            fh.write(json.dumps({"at": "2026-11-02T00:00:00Z", "source": "agent", "version": 1,
                                 "total": {"p50_s": 600, "p90_s": 1200}}) + "\n")
        self.assertEqual(self.implement()["agent_call"].get("model"), SONNET)

    def test_a_rework_round_keeps_the_definitions_model(self):
        self.shape(20)
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], "claude-opus-5-5")


class SmallBound(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "workers": {"implementer_model": {"small": SONNET},
                                                           "small_estimate_minutes": 60}}

    def test_the_bound_is_the_knobs_and_a_refactor_without_its_arm_goes_by_size(self):
        self.ccp("tasks", "claim", "0002")
        task = self.runner / "docs/delivery/tasks/0002-second.md"
        task.write_text(task.read_text().replace("\nstatus:", "\nkind: refactor\nstatus:", 1))
        (self.q / "estimates").mkdir()
        (self.q / "estimates" / "0002-second.jsonl").write_text(json.dumps(
            {"at": "2026-11-01T00:00:00Z", "source": "baseline", "version": 1, "total": {"p50_s": 3000, "p90_s": 6000}}) + "\n")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["agent_call"].get("model"), SONNET)


class NoKnob(ToolkitFixture, unittest.TestCase):
    def test_a_small_task_carries_no_model(self):
        self.ccp("tasks", "claim", "0002")
        (self.q / "estimates").mkdir()
        (self.q / "estimates" / "0002-second.jsonl").write_text(json.dumps(
            {"at": "2026-11-01T00:00:00Z", "source": "baseline", "version": 1, "total": {"p50_s": 60, "p90_s": 120}}) + "\n")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], "claude-opus-5-5")


class Knob(unittest.TestCase):
    def load(self, workers: object) -> config.Config:
        p = Product({"workers": workers})
        self.addCleanup(p.cleanup)
        return p.cfg

    def test_defaults_are_off(self):
        self.assertEqual(self.load({}).workers, {"implementer_model": None, "small_estimate_minutes": 30})

    def test_bad_values_are_refused(self):
        for bad in ({"implementer_model": {"large": SONNET}}, {"implementer_model": {"small": "sonnet"}},
                    {"implementer_model": {"small": ""}}, {"implementer_model": "claude-sonnet-5-5"},
                    {"small_estimate_minutes": 0}, {"small_estimate_minutes": True}, {"model": SONNET}):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError):
                self.load(bad)

    def test_the_schema_names_the_knobs(self):
        schema = json.loads((config.Path(__file__).resolve().parents[1] / "contracts" / "plane_config.schema.json")
                            .read_text())
        w = schema["properties"]["workers"]["properties"]
        self.assertEqual(set(w), set(config.WORKERS_DEFAULTS))
        self.assertEqual(set(w["implementer_model"]["properties"]), set(config.WORKER_MODEL_ARMS))


if __name__ == "__main__":
    unittest.main()
