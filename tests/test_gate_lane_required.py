"""A product must name a gate lane (SPEC §8.1, §14.1): without one `ccp tasks claim` and `ccp tasks next`
refuse with exit 2, naming it, once the grace release has ended, and warn and carry on during it (§29.3);
`ccp init` lists it among the required keys still unset, and `ccp upgrade status` lists its step."""
from __future__ import annotations

import dataclasses
import json
import unittest
from unittest import mock

from ccp import config
from tests.helpers import Product
from tests.init_fixture import InitCase
from tests.toolkit_fixture import ToolkitFixture
from tests.upgrade_fixture import UpgradeFixture

NO_SUITE = {k: v for k, v in ToolkitFixture.PLANE_JSON.items() if k != "suite"}
TASK = "0002-second"


def after_grace():
    return mock.patch.object(config, "REQUIRED_KEYS_GRACE", False)


class Missing(unittest.TestCase):
    """config.gate_lane_missing: the lane the gate role names, with a command that is not the placeholder."""

    def cfg(self, plane: dict) -> config.Config:
        p = Product(plane, bare=True)
        self.addCleanup(p.cleanup)
        return p.cfg

    def with_lanes(self, lanes: dict, roles: dict | None = None) -> config.Config:
        cfg = self.cfg({})  # the loader refuses an empty or placeholder lane itself; the rule is judged here too
        return dataclasses.replace(cfg, suite={**cfg.suite, "lanes": lanes, **({"roles": roles} if roles else {})})

    def test_no_suite_block_is_missing_naming_the_lane_and_the_key(self):
        why = config.gate_lane_missing(self.cfg({}))
        self.assertIn("no gate lane", why)
        self.assertIn("suite.lanes", why)
        self.assertIn("'gate'", why)

    def test_a_lanes_block_without_the_gate_lane_is_missing(self):
        self.assertIsNotNone(config.gate_lane_missing(self.cfg({"suite": {"lanes": {"full": ["true"]}}})))

    def test_an_argv_or_staged_gate_lane_is_a_gate_lane(self):
        self.assertIsNone(config.gate_lane_missing(self.cfg({"suite": {"lanes": {"gate": ["make", "test"]}}})))
        staged = {"suite": {"lanes": {"gate": [{"name": "unit", "cmd": "make test"}]}}}
        self.assertIsNone(config.gate_lane_missing(self.cfg(staged)))

    def test_the_gate_role_names_the_lane(self):
        renamed = self.cfg({"suite": {"roles": {"gate": "ci"}, "lanes": {"ci": ["make", "test"]}}})
        self.assertIsNone(config.gate_lane_missing(renamed))
        why = config.gate_lane_missing(self.cfg({"suite": {"roles": {"gate": "ci"}, "lanes": {"gate": ["true"]}}}))
        self.assertIn("'ci'", why)

    def test_empty_blank_and_placeholder_lanes_are_missing(self):
        for lanes in ({"gate": []}, {"gate": ["  "]}, {"gate": [config.LANE_PLACEHOLDER]},
                      {"gate": ["sh", "-c", f"{config.LANE_PLACEHOLDER} && true"]},
                      {"gate": [{"name": "unit", "cmd": f"run {config.LANE_PLACEHOLDER}"}]},
                      {"gate": [{"name": "unit", "cmd": " "}]}):
            self.assertIn("no gate lane", config.gate_lane_missing(self.with_lanes(lanes)) or "", lanes)


class ClaimAndNext(ToolkitFixture):
    """`tasks next` and `tasks claim` in a product, from the runner's worktree."""

    def setUp(self):
        super().setUp()
        config._GATE_WARNED.clear()

    def next_(self):
        config._GATE_WARNED.clear()
        return self.ccp("tasks", "next")

    def claim(self):
        config._GATE_WARNED.clear()
        return self.ccp("tasks", "claim", TASK)

    def taken(self) -> bool:
        return (self.q / "tasks" / f"{TASK}.json").is_file() or ("task", "claim") in self.ops()

    def assert_refused(self) -> None:
        with after_grace():
            code, _, out, err = self.next_()
            self.assertEqual(code, 2, out + err)
            self.assertIn("no gate lane", err)
            self.assertIn("suite.lanes", err)
            self.assertNotIn(TASK, out)
            code, _, out, err = self.claim()
            self.assertEqual(code, 2, out + err)
            self.assertIn("no gate lane", err)
        self.assertFalse(self.taken())

    def assert_passes(self) -> None:
        with after_grace():
            code, _, out, err = self.next_()
            self.assertEqual(code, 0, out + err)
            self.assertIn(TASK, out)
            self.assertNotIn("gate lane", err)
            code, _, out, err = self.claim()
            self.assertEqual(code, 0, out + err)
            self.assertNotIn("gate lane", err)
        self.assertTrue(self.taken())


class NoSuiteBlock(ClaimAndNext, unittest.TestCase):
    PLANE_JSON = NO_SUITE

    def test_after_the_grace_release_next_and_claim_refuse_naming_it_and_take_nothing(self):
        self.assert_refused()

    def test_during_the_grace_release_next_and_claim_warn_and_carry_on(self):
        self.assertTrue(config.REQUIRED_KEYS_GRACE)
        code, _, out, err = self.next_()
        self.assertEqual(code, 0, out + err)
        self.assertIn(TASK, out)
        self.assertIn("warning: no gate lane", err)
        self.assertIn("suite.lanes", err)
        self.assertIn("required: plane.json suite.lanes.gate", err)
        code, _, out, err = self.claim()
        self.assertEqual(code, 0, out + err)
        self.assertIn("warning: no gate lane", err)
        self.assertTrue(self.taken())

    def test_the_warning_is_given_once_per_product_and_process(self):
        self.assertIn("no gate lane", self.next_()[3])
        self.assertNotIn("no gate lane", self.ccp("tasks", "next")[3])


class LaneShapes(ClaimAndNext, unittest.TestCase):
    """The fixture's plane.json names a gate lane; a shape the loader refuses is handed in as a loaded one."""

    def lanes(self, lanes: dict):
        real = config.load

        def load(root):
            cfg = real(root)
            return dataclasses.replace(cfg, suite={**cfg.suite, "lanes": lanes})
        return mock.patch.object(config, "load", load)

    def test_with_a_gate_lane_next_and_claim_pass(self):
        self.assert_passes()

    def test_an_empty_gate_lane_is_refused(self):
        with self.lanes({"gate": []}):
            self.assert_refused()

    def test_a_gate_lane_holding_the_placeholder_is_refused(self):
        with self.lanes({"gate": [config.LANE_PLACEHOLDER]}):
            self.assert_refused()

    def test_a_staged_gate_lane_holding_the_placeholder_is_refused(self):
        with self.lanes({"gate": [{"name": "unit", "cmd": f"run {config.LANE_PLACEHOLDER}"}]}):
            self.assert_refused()


class Init(InitCase):
    def test_without_gate_init_lists_the_gate_lane_as_required_and_unset(self):
        code, res = self.init("--project-id", "demo", "--language", "none")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["required_unset"], ["suite.lanes.gate"])
        r = self.ccp("init", "--project-id", "demo")
        self.assertIn("`suite.lanes.gate` is unset", r.stderr)

    def test_with_gate_it_is_not_listed(self):
        code, res = self.init("--project-id", "demo", "--language", "none", "--gate", "make test")
        self.assertEqual(code, 0, res)
        self.assertNotIn("required_unset", res)
        r = self.ccp("init", "--project-id", "demo")
        self.assertNotIn("suite.lanes.gate", r.stderr)


class Upgrade(UpgradeFixture, unittest.TestCase):
    STEP = "required: plane.json suite.lanes.gate"

    def setUp(self):
        super().setUp()
        self.plane_task("0001-gate", "done", "Gate", self.STEP)
        self.commit("plane")

    def lists(self, **plane) -> tuple[list[dict], list[dict]]:
        self.product_json(language="none", **plane)
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return ([s for s in body["steps"] if s["task"] == "0001-gate"],
                [s for s in body["detected"] if s["task"] == "0001-gate"])

    def test_a_product_with_no_gate_lane_has_the_required_step_to_take(self):
        steps, detected = self.lists()
        self.assertEqual(len(steps), 1)
        self.assertTrue(steps[0]["required"])
        self.assertIn("suite.lanes.gate", steps[0]["change"])
        self.assertEqual(detected, [])
        steps, _ = self.lists(suite={"lanes": {"full": ["true"]}})
        self.assertEqual(len(steps), 1)

    def test_a_product_with_a_gate_lane_has_taken_it_whatever_the_role_names(self):
        self.assertEqual(self.lists(suite={"lanes": {"gate": ["make", "test"]}}), ([], [mock.ANY]))
        renamed = {"roles": {"gate": "ci"}, "lanes": {"ci": ["make", "test"]}}
        self.assertEqual(self.lists(suite=renamed), ([], [mock.ANY]))

    def test_a_gate_key_naming_another_roles_lane_is_not_taken(self):
        steps, _ = self.lists(suite={"roles": {"gate": "ci"}, "lanes": {"gate": ["make", "test"]}})
        self.assertEqual(len(steps), 1)


if __name__ == "__main__":
    unittest.main()
