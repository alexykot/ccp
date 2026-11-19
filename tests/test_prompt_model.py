"""SPEC §2.4: the implementer's model per task. `ccp prompt implement` prints it in the Agent call (`model`) for
a small task (its estimate at most `workers.small_estimate_minutes`) or a `refactor` one, as the plane's default
(Sonnet) or plane.json `models` gives it, and the run expects it; for any other task the call carries no `model`.
The deprecated `workers.implementer_model` still picks an arm `models` leaves to its default, taking only the
aliases the Agent call's `model` accepts; a small choice that a task's missing estimate keeps from applying is a
warning."""
from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli, config, models
from tests.helpers import Product
from tests.test_toolkit import ToolkitFixture

SONNET = "sonnet"
NO_ESTIMATE = "cannot apply"
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

    def test_an_unestimated_refactor_gets_its_arm_without_a_warning(self):
        self.shape(None, kind="refactor")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual((code, body["agent_call"].get("model")), (0, SONNET))
        self.assertNotIn(NO_ESTIMATE, err)

    def test_an_unestimated_feature_warns_that_the_small_arm_cannot_apply(self):
        self.shape(None)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertIn(NO_ESTIMATE, err)
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], models.default("implementer")[0])  # the definition's

    def test_an_estimated_task_draws_no_warning_whichever_side_of_the_bound(self):
        for minutes in (20, 90):
            with self.subTest(minutes=minutes):
                self.shape(minutes)
                code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
                self.assertEqual(code, 0, out + err)
                self.assertNotIn(NO_ESTIMATE, err)

    def test_a_large_feature_carries_no_model(self):
        self.shape(90)
        body = self.implement()
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], models.default("implementer")[0])  # the definition's

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

    def test_a_rework_round_takes_the_implementers_model_for_the_task(self):
        self.shape(20)
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["agent_call"].get("model"), body["expected_model"]), (SONNET, SONNET))

    def test_a_rework_round_of_an_unestimated_task_draws_no_warning(self):
        self.shape(None)
        code, body, out, err = self.ccp("prompt", "merge", "0002", "--pr", "7", "--head", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(NO_ESTIMATE, err)


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


class Defaults(ToolkitFixture, unittest.TestCase):
    def estimate(self, seconds: float) -> None:
        (self.q / "estimates").mkdir()
        (self.q / "estimates" / "0002-second.jsonl").write_text(json.dumps(
            {"at": "2026-11-01T00:00:00Z", "source": "baseline", "version": 1, "total": {"p50_s": seconds, "p90_s": 2 * seconds}}) + "\n")

    def test_a_small_task_carries_the_small_model_with_nothing_configured(self):
        self.ccp("tasks", "claim", "0002")
        self.estimate(60)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["agent_call"].get("model"), body["expected_model"]), (SONNET, SONNET))
        self.assertNotIn("workers.implementer_model", err)

    def test_a_large_task_carries_no_model(self):
        self.ccp("tasks", "claim", "0002")
        self.estimate(7200)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], models.default("implementer")[0])
        self.assertNotIn(NO_ESTIMATE, err)

    def test_an_unestimated_task_warns_that_the_small_choice_cannot_apply(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertIn(NO_ESTIMATE, err)
        self.assertNotIn("model", body["agent_call"])


class Knob(unittest.TestCase):
    def load(self, workers: object) -> config.Config:
        p = Product({"workers": workers})
        self.addCleanup(p.cleanup)
        return p.cfg

    def test_the_defaults_leave_it_off(self):
        self.assertEqual(self.load({}).workers, {"implementer_model": None, "small_estimate_minutes": 30})

    def test_each_alias_the_agent_call_accepts_loads(self):
        for alias in ("sonnet", "opus", "haiku", "fable"):
            with self.subTest(alias=alias):
                arms = {"small": alias, "refactor": alias}
                self.assertEqual(self.load({"implementer_model": arms}).workers["implementer_model"], arms)

    def test_bad_values_are_refused(self):
        for bad in ({"implementer_model": {"small": "claude-sonnet-5-5"}},
                    {"implementer_model": {"refactor": "claude-opus-5-5"}}, {"implementer_model": {"small": "inherit"}},
                    {"implementer_model": {"small": "Sonnet"}}, {"implementer_model": {"small": ""}},
                    {"implementer_model": {"small": None}}, {"implementer_model": "sonnet"},
                    {"small_estimate_minutes": 0}, {"small_estimate_minutes": True}):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError):
                self.load(bad)

    def test_a_full_id_is_refused_naming_the_knob_and_the_aliases(self):
        p = Product({"workers": {"implementer_model": {"small": "claude-sonnet-5-5"}}})
        self.addCleanup(p.cleanup)
        p.task("0001-a")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(p.root), "tasks", "check"])
        self.assertEqual(code, 2, out.getvalue() + err.getvalue())
        self.assertIn("workers.implementer_model", err.getvalue())
        for alias in ("sonnet", "opus", "haiku", "fable"):
            self.assertIn(alias, err.getvalue().replace("claude-sonnet-5-5", ""))

    def test_the_schema_names_the_knobs(self):
        schema = json.loads((config.Path(__file__).resolve().parents[1] / "contracts" / "plane_config.schema.json")
                            .read_text())
        w = schema["properties"]["workers"]["properties"]
        self.assertEqual(set(w), set(config.WORKERS_DEFAULTS))
        self.assertEqual(set(w["implementer_model"]["properties"]), set(config.WORKER_MODEL_ARMS))
        for arm in config.WORKER_MODEL_ARMS:
            self.assertEqual(w["implementer_model"]["properties"][arm]["enum"], list(config.WORKER_MODEL_ALIASES))


if __name__ == "__main__":
    unittest.main()
