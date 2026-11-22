"""SPEC §2.4: every role has a default model, and plane.json `models` overrides any of them. `models.model_for`
reads the product's model for a role (the implementer's per task); a worker's Agent call (`ccp prompt`), the
runner's spawn, the headless seats' flags, the seat checks and the lead's `ccp init` setting all follow it. A key
that is no role, or a value that is no alias, is refused naming it."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import architect, config, estimator, models, seats
from tests.helpers import Product
from tests.architect_fixture import Harness as ArchitectHarness
from tests.board_seats_fixture import Base as SeatsBase
from tests.init_fixture import InitCase
from tests.team_hosting_fixture import TeamCase
from tests.toolkit_fixture import ToolkitFixture

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())
ROLES = ("lead", "runner", "implementer", "implementer_small", "implementer_refactor", "reviewer", "verifier",
         "architect", "estimator")
SONNET_ID, OPUS_ID = models.FULL_IDS["sonnet"], models.FULL_IDS["opus"]


def resolved(cfg: config.Config) -> dict[str, str]:
    return {role: models.model_for(cfg, role) for role in ROLES}


class Loaded(unittest.TestCase):
    def product(self, block: object = None, **more: object) -> Product:
        p = Product({**({"models": block} if block is not None else {}), **more})
        self.addCleanup(p.cleanup)
        return p

    def test_every_role_has_its_default_with_no_configuration(self):
        self.assertEqual(list(resolved(self.product().cfg).values()),
                         ["opus", "sonnet", "opus", "sonnet", "sonnet", "opus", "sonnet", "opus", "sonnet"])

    def test_the_block_is_the_role_table_and_nothing_else(self):
        self.assertEqual(tuple(config.MODELS_DEFAULTS), ROLES)
        self.assertEqual(config.MODELS_DEFAULTS, {r: models.ROLES[r][0] for r in ROLES})
        self.assertEqual(self.product().cfg.models, config.MODELS_DEFAULTS)

    def test_one_block_overrides_a_role_and_leaves_the_rest(self):
        cfg = self.product({"reviewer": "sonnet"}).cfg
        self.assertEqual(models.model_for(cfg, "reviewer"), "sonnet")
        self.assertEqual({r: v for r, v in resolved(cfg).items() if r != "reviewer"},
                         {r: v for r, v in resolved(self.product().cfg).items() if r != "reviewer"})
        self.assertEqual(cfg.models_given, ("reviewer",))

    def test_every_alias_the_agent_call_accepts_loads_for_every_role(self):
        for alias in ("sonnet", "opus", "haiku", "fable"):
            with self.subTest(alias=alias):
                cfg = self.product({r: alias for r in ROLES}).cfg
                self.assertEqual(set(resolved(cfg).values()), {alias})

    def test_a_key_that_is_no_role_is_refused_naming_it(self):
        with self.assertRaises(config.ConfigError) as cm:
            self.product({"reviwer": "sonnet"}).cfg
        self.assertIn("models.reviwer", str(cm.exception))

    def test_a_value_that_is_no_alias_is_refused_naming_its_key(self):
        for bad in ("claude-opus-5-5", "inherit", "Opus", "", None, 5, ["opus"]):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError) as cm:
                self.product({"reviewer": bad}).cfg
            self.assertIn("models.reviewer", str(cm.exception))

    def test_a_block_that_is_no_object_is_refused(self):
        for bad in ("sonnet", ["reviewer"], 1):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError) as cm:
                self.product(bad).cfg
            self.assertIn("`models` must be an object", str(cm.exception))

    def test_a_key_that_is_no_role_and_a_bad_value_are_each_named(self):
        with self.assertRaises(config.ConfigError) as cm:
            self.product({"reviwer": "sonnet", "verifier": "gpt"}).cfg
        self.assertIn("models.reviwer", str(cm.exception))
        self.assertIn("models.verifier", str(cm.exception))

    def test_the_schema_lists_the_roles_with_the_aliases_as_their_values(self):
        props = SCHEMA["properties"]["models"]["properties"]
        self.assertEqual(tuple(props), ROLES)
        for role, prop in props.items():
            self.assertEqual(prop["enum"], list(models.ALIASES), role)
        self.assertEqual(list(models.ALIASES), list(config.WORKER_MODEL_ALIASES))

    def test_the_schema_marks_the_old_knob_deprecated(self):
        prop = SCHEMA["properties"]["workers"]["properties"]["implementer_model"]
        self.assertTrue(prop["deprecated"])
        self.assertIn("models.implementer_small", prop["description"])


class ImplementerPerTask(unittest.TestCase):
    def cfg(self, block: object = None, workers: object = None) -> config.Config:
        p = Product({**({"models": block} if block else {}), **({"workers": workers} if workers else {})})
        self.addCleanup(p.cleanup)
        return p.cfg

    def pick(self, cfg: config.Config, kind: str = "feature", estimate_s: float | None = None) -> str:
        return models.model_for(cfg, "implementer", {"kind": kind}, estimate_s)

    def test_a_task_goes_by_its_kind_and_estimate(self):
        cfg = self.cfg()
        self.assertEqual(self.pick(cfg, estimate_s=20 * 60), "sonnet")
        self.assertEqual(self.pick(cfg, estimate_s=90 * 60), "opus")
        self.assertEqual(self.pick(cfg, estimate_s=None), "opus")
        self.assertEqual(self.pick(cfg, kind="refactor", estimate_s=None), "sonnet")

    def test_the_small_bound_is_inclusive_and_the_products(self):
        cfg = self.cfg(workers={"small_estimate_minutes": 60})
        self.assertEqual(self.pick(cfg, estimate_s=3600), "sonnet")
        self.assertEqual(self.pick(cfg, estimate_s=3601), "opus")

    def test_the_refactor_choice_wins_when_both_apply(self):
        cfg = self.cfg({"implementer_small": "haiku", "implementer_refactor": "fable"})
        self.assertEqual(self.pick(cfg, kind="refactor", estimate_s=60), "fable")
        self.assertEqual(self.pick(cfg, estimate_s=60), "haiku")

    def test_the_implementers_own_model_serves_the_rest_and_a_call_without_a_task(self):
        cfg = self.cfg({"implementer": "haiku"})
        self.assertEqual(self.pick(cfg, estimate_s=7200), "haiku")
        self.assertEqual(models.model_for(cfg, "implementer"), "haiku")
        self.assertEqual(models.model_for(cfg, "implementer_small"), "sonnet")

    def test_a_role_other_than_the_implementer_ignores_the_task(self):
        cfg = self.cfg({"reviewer": "haiku"})
        self.assertEqual(models.model_for(cfg, "reviewer", {"kind": "refactor"}, 60), "haiku")

    def test_the_old_knob_applies_where_models_does_not_set_the_arm(self):
        cfg = self.cfg({"implementer_refactor": "haiku"},
                       {"implementer_model": {"small": "fable", "refactor": "opus"}})
        self.assertEqual(self.pick(cfg, estimate_s=60), "fable")
        self.assertEqual(self.pick(cfg, kind="refactor"), "haiku")  # models sets it: the old arm gives way
        self.assertEqual(models.model_for(cfg, "implementer_small"), "fable")
        self.assertEqual(self.pick(cfg, estimate_s=7200), "opus")  # neither arm applies

    def test_an_old_knob_with_one_arm_leaves_the_other_to_its_default(self):
        cfg = self.cfg(workers={"implementer_model": {"small": "opus"}})
        self.assertEqual(self.pick(cfg, estimate_s=60), "opus")
        self.assertEqual(self.pick(cfg, kind="refactor"), "sonnet")


class Pinned(unittest.TestCase):
    def test_the_definitions_model_stands_when_it_is_the_aliass_family(self):
        self.assertEqual(models.pin("opus", OPUS_ID), OPUS_ID)
        self.assertEqual(models.pin("sonnet", OPUS_ID), "sonnet")
        self.assertEqual(models.pin("haiku", SONNET_ID), "haiku")
        self.assertIsNone(models.pin("opus", None))

    def test_the_headless_flags_follow_the_product_and_pass_an_unpinned_alias_as_it_is(self):
        p = Product({"models": {"architect": "sonnet", "estimator": "haiku"}})
        self.addCleanup(p.cleanup)
        self.assertEqual(models.headless_flags("architect", p.cfg), ["--model", SONNET_ID, "--effort", "high"])
        self.assertEqual(models.headless_flags("estimator", p.cfg), ["--model", "haiku", "--effort", "medium"])
        self.assertEqual(models.headless_flags("architect"), ["--model", OPUS_ID, "--effort", "high"])

    def test_the_estimator_and_the_architect_take_their_models_from_the_product(self):
        p = Product({"models": {"architect": "sonnet", "estimator": "opus"}})
        self.addCleanup(p.cleanup)
        argv = estimator.argv_for("PROMPT", p.cfg)
        self.assertEqual(argv[argv.index("--model") + 1], OPUS_ID)
        self.assertEqual(estimator.pins(p.cfg)["model"], OPUS_ID)
        self.assertEqual(estimator.pins()["model"], SONNET_ID)
        self.assertEqual(architect.ar.headless_flags(p.cfg), ["--model", SONNET_ID, "--effort", "high"])
        self.assertEqual(seats.headless_pins(p.cfg)["model"], SONNET_ID)
        self.assertEqual(seats.headless_pins()["model"], OPUS_ID)


class WorkersCarryAnAliasOnlyWhenTheModelDiffers(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "models": {"reviewer": "sonnet", "verifier": "opus"}}

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")

    def prompt(self, phase: str, *extra: str) -> dict:
        code, body, out, err = self.ccp("prompt", phase, "0002", *extra, "--supersede")
        self.assertEqual(code, 0, out + err)
        return body

    def estimate(self, minutes: float) -> None:
        est = self.q / "estimates" / "0002-second.jsonl"
        est.parent.mkdir(exist_ok=True)
        est.write_text(json.dumps({"at": "2026-11-01T00:00:00Z", "source": "baseline", "version": 1,
                                   "total": {"p50_s": minutes * 60, "p90_s": minutes * 120}}) + "\n")

    def test_a_reviewer_the_product_moved_to_sonnet_carries_the_alias_and_is_expected_on_it(self):
        body = self.prompt("review", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(body["agent_call"]["model"], "sonnet")
        self.assertEqual(body["expected_model"], "sonnet")

    def test_a_verifier_the_product_moved_to_opus_carries_the_alias(self):
        body = self.prompt("verify", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(body["agent_call"]["model"], "opus")
        self.assertEqual(body["expected_model"], "opus")

    def test_a_small_task_carries_the_small_alias_in_every_implementer_round(self):
        self.estimate(20)
        for phase, extra in (("implement", ("--base", "abc1234")), ("merge", ("--pr", "7", "--head", "abc1234")),
                             ("ruling", ("--pr", "7", "--head", "abc1234", "--note", "go on"))):
            with self.subTest(phase=phase):
                body = self.prompt(phase, *extra)
                self.assertEqual((body["agent_call"].get("model"), body["expected_model"]), ("sonnet", "sonnet"))

    def test_a_large_task_carries_none_and_is_expected_on_the_definitions_model(self):
        self.estimate(90)
        for phase, extra in (("implement", ("--base", "abc1234")), ("merge", ("--pr", "7", "--head", "abc1234"))):
            with self.subTest(phase=phase):
                body = self.prompt(phase, *extra)
                self.assertNotIn("model", body["agent_call"])
                self.assertEqual(body["expected_model"], OPUS_ID)

    def test_a_product_that_keeps_the_default_reviewer_passes_none(self):
        self.write_plane({})
        body = self.prompt("review", "--pr", "7", "--head", "a" * 40)
        self.assertNotIn("model", body["agent_call"])
        self.assertEqual(body["expected_model"], OPUS_ID)

    def write_plane(self, models_block: dict) -> None:
        plane = {**self.PLANE_JSON, "models": models_block}
        for root in (self.main, self.runner):
            (root / "docs/delivery/plane.json").write_text(json.dumps(plane))

    def test_an_implementer_the_product_moved_to_sonnet_carries_it_for_a_large_task(self):
        self.write_plane({"implementer": "sonnet"})
        self.estimate(90)
        body = self.prompt("implement", "--base", "abc1234")
        self.assertEqual((body["agent_call"]["model"], body["expected_model"]), ("sonnet", "sonnet"))

    def test_an_unestimated_task_warns_that_the_small_choice_cannot_apply_unless_it_makes_no_difference(self):
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertIn("cannot apply", err)
        self.write_plane({"implementer_small": "opus"})  # the small choice is the implementer's: nothing to apply
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("cannot apply", err)

    def test_the_old_knob_still_applies_and_the_warning_names_the_move(self):
        self.write_plane({})
        plane = {**self.PLANE_JSON, "models": {}, "workers": {"implementer_model": {"small": "haiku"}}}
        for root in (self.main, self.runner):
            (root / "docs/delivery/plane.json").write_text(json.dumps(plane))
        self.estimate(20)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["agent_call"]["model"], "haiku")
        self.assertIn("workers.implementer_model", err)
        self.assertIn("models.implementer_small", err)


class ArchitectPass(ArchitectHarness):
    def test_the_pass_runs_on_the_products_architect_model(self):
        plane = json.loads((self.p.root / "docs/delivery/plane.json").read_text())
        self.p.write("docs/delivery/plane.json", json.dumps({**plane, "models": {"architect": "sonnet"}}))
        self.stub_report([])
        self.assertEqual(self.dpj("architect", "run", "--force")[0], 0)
        argv = json.loads(Path(str(self.report) + ".argv").read_text())
        self.assertIn(f"--model {SONNET_ID} --effort high", " ".join(argv))


class SeatsExpectTheRolesModel(SeatsBase, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "models": {"runner": "opus", "reviewer": "sonnet"}}

    def test_the_runner_row_expects_the_products_runner_model(self):
        row = self.rows(self.build())["runner"]
        self.assertEqual(row["expected"]["model"], "opus")

    def test_a_run_row_expects_the_model_its_prompt_pinned(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["agent_call"]["model"], "sonnet")
        row = self.rows(self.build())["reviewer 0002-second/review"]
        self.assertEqual(row["expected"]["model"], "sonnet")


class RunnerSpawn(TeamCase):
    def setUp(self):
        super().setUp()
        for tid in ("0001-a", "0002-b"):
            self.prod.task(tid)
        self.prod.index()

    def spawn(self) -> dict:
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        return res["actions"][-1]

    def test_the_default_runner_passes_no_model(self):
        self.assertNotIn("model", self.spawn())

    def test_a_runner_the_product_moved_to_opus_carries_the_alias(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "models": {"runner": "opus"}}))
        self.assertEqual(self.spawn()["model"], "opus")

    def test_a_runner_with_a_definition_of_the_products_own_keeps_that_definitions_model(self):
        self.prod.write(".claude/agents/delivery-runner.md", "---\nname: delivery-runner\nmodel: opus\neffort: max\n---\n")
        self.assertNotIn("model", self.spawn())

    def test_a_runner_moved_to_its_own_default_passes_none(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "models": {"runner": "sonnet"}}))
        self.assertNotIn("model", self.spawn())


class LeadSetting(InitCase):
    @property
    def settings_path(self):
        return self.repo / ".claude" / "settings.json"

    def settings(self):
        return json.loads(self.settings_path.read_text())

    def adopt(self, *args):
        code, res = self.init("--project-id", "demo", *args)
        self.assertEqual(code, 0, res)
        return res

    def test_a_new_product_gets_the_leads_model_and_the_result_says_added(self):
        res = self.adopt()
        self.assertEqual(self.settings()["model"], "opus")
        self.assertEqual(res["settings"]["model"], "added")

    def test_a_model_the_product_set_is_kept_on_every_run(self):
        self.settings_path.parent.mkdir()
        self.settings_path.write_text(json.dumps({"model": "sonnet"}))
        for args in ((), ("--force",)):
            res = self.adopt(*args)
            self.assertEqual(self.settings()["model"], "sonnet", args)
            self.assertEqual(res["settings"]["model"], "kept", args)

    def test_a_kept_plane_json_names_the_leads_model(self):
        self.adopt()
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "demo", "models": {"lead": "fable"}}))
        self.settings_path.unlink()
        self.adopt()
        self.assertEqual(self.settings()["model"], "fable")


if __name__ == "__main__":
    unittest.main()
