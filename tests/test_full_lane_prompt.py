"""The full lane in the worker prompts (SPEC §14.1, §13.2): a lane plane.json `suite.lanes` declares is run as
`--lane <lane>` with nothing after `--`, so a fix or merge round runs the product's own full suite; a lane it
does not declare still takes the command after `--`. A product declaring a gate lane and no full lane runs the gate
lane for the full role; a declared `pregate` lane replaces the house-rule checks in the fail-fast pre-gate (§13.5)."""
from __future__ import annotations

import dataclasses
import json
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, prompt as prompt_mod
from tests.report_helpers import done_report
from tests.review_flow import ReviewFlow
from tests.toolkit_fixture import ToolkitFixture

A, B = "a" * 40, "b" * 40
DECLARED = "`--lane full` with nothing after `--`"


class DeclaredFullLane(ReviewFlow, ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {"full": ["scripts/gate.sh"]}}}

    def setUp(self):
        super().setUp()
        # runs open a minute apart: `opened_at` has one-second resolution, and the gates order by it
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_the_fix_and_merge_rounds_run_the_declared_full_lane_with_no_command(self):
        self.run_phase("review", A, "Severity: BLOCKER=1 MAJOR=0 MINOR=0 NIT=0")
        texts = {}
        for phase, head, to in (("fix", A, B), ("merge", B, A)):
            code, body, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", head)
            self.assertEqual(code, 0, f"{phase}: {out}{err}")
            texts[phase] = Path(body["prompt_path"]).read_text()
            code, _, out, err = self.report(body["run_id"], done_report(phase, "PR: #7", f"Head: {to}"))
            self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        for phase, text in texts.items():
            self.assertIn(DECLARED, text, phase)
            self.assertIn("suite run --lane full`", text, phase)  # the round's full test suite names the lane
            self.assertNotIn("--lane full -- ", text, phase)

    def test_a_ruling_round_runs_the_declared_full_lane_too(self):
        code, body, out, err = self.ccp("prompt", "ruling", "0002", "--pr", "7", "--head", A, "--note", "the field is optional")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(DECLARED, text)
        self.assertIn("suite run --lane full`", text)
        self.assertNotIn("--lane full -- ", text)

    def test_every_change_round_and_the_reviewer_hear_the_declared_lane(self):
        c = config.load(self.runner)
        for phase in ("implement", "ruling", "review"):
            self.assertIn(DECLARED, prompt_mod.suite_lanes(c, phase), phase)
        self.assertIn("`--lane gate` for the formal gate", prompt_mod.suite_lanes(c, "verify"))  # not declared here
        self.assertIn("`--lane part` for a subset", prompt_mod.suite_lanes(c, "implement"))


class StagedAndRenamedLanes(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON,
                  "suite": {"lanes": {"formal": [{"name": "unit", "cmd": "true"}], "whole": ["scripts/all.sh"]},
                            "roles": {"gate": "formal", "full": "whole"}}}

    def test_a_staged_or_renamed_lane_is_written_by_its_own_name_with_no_command(self):
        c = config.load(self.runner)
        verify, implement = prompt_mod.suite_lanes(c, "verify"), prompt_mod.suite_lanes(c, "implement")
        self.assertIn("`--lane formal` with nothing after `--`", verify)
        self.assertIn("`--`: the formal gate", verify)
        self.assertIn("`--lane whole` with nothing after `--`", implement)
        self.assertIn("`--`: the product's full suite", implement)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertIn("suite run --lane whole`", Path(body["prompt_path"]).read_text())


class UndeclaredFullLane(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {}}}

    def test_an_undeclared_full_lane_still_takes_the_command(self):
        self.assertEqual(json.loads((self.runner / "docs/delivery/plane.json").read_text())["suite"]["lanes"], {})
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("--lane <lane> -- <command>`", text)
        self.assertIn("`--lane full` for the product's", text)
        self.assertNotIn(DECLARED, text)


PART_ARGV = "suite run --lane part -- scripts/gate.sh <module> …` (module names, not test ids)"
PART_EMPTY = "`--lane part` with nothing after `--`"


class DeclaredPartLane(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {"part": ["scripts/gate.sh"]}}}

    def test_a_declared_part_argv_takes_the_module_names_after_it(self):
        c = config.load(self.runner)
        for phase in ("implement", "fix", "merge", "ruling", "review", "verify"):
            lanes = prompt_mod.suite_lanes(c, phase)
            self.assertIn(f"`{prompt_mod.ccp_command(c)} {PART_ARGV}", lanes, phase)
            self.assertIn(f", or `{prompt_mod.ccp_command(c)} suite run --affected` (it picks", lanes, phase)
            self.assertNotIn(PART_EMPTY, lanes, phase)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(PART_ARGV, text)
        self.assertIn("for one the Lanes line above gives", text)

    def test_a_part_lane_declared_as_an_argv_is_given_as_whole_commands(self):
        """§14.7: each option is a command the worker can run as written, never `--lane` and `--affected` in one."""
        c = config.load(self.runner)
        for phase in ("implement", "fix", "merge", "ruling", "review", "verify"):
            lanes = prompt_mod.suite_lanes(c, phase)
            self.assertIn("suite run --lane part -- scripts/gate.sh <module> …", lanes, phase)
            self.assertIn("(it picks the lane itself)", lanes, phase)
            self.assertNotIn("`--lane part` with", lanes, phase)

    def test_a_staged_part_lane_still_runs_with_nothing_after_it(self):
        staged = {"lanes": {"part": [{"name": "unit", "cmd": "true"}]}}
        lanes = prompt_mod.suite_lanes(dataclasses.replace(config.load(self.runner), suite=staged), "implement")
        self.assertIn(PART_EMPTY, lanes)
        self.assertNotIn("<modules>", lanes)

    def test_a_staged_part_lane_names_suite_run_affected_through_the_workers_ccp(self):
        stages = [{"name": "unit", "cmd": "true"}]
        staged = {"lanes": {"part": stages, "gate": stages}}
        c = dataclasses.replace(config.load(self.runner), suite=staged)
        affected = f"{prompt_mod.ccp_command(c)} suite run --affected"
        for phase in ("implement", "review"):
            self.assertIn(affected, prompt_mod.suite_lanes(c, phase), phase)
        # the staged gate lane gets no such tail: the verify line names it once, for the part lane
        self.assertEqual(prompt_mod.suite_lanes(c, "verify").count(affected), 1)
        # nor does an undeclared part lane, which takes the command after `--`
        bare = dataclasses.replace(c, suite={"lanes": {}})
        self.assertNotIn("suite run --affected", prompt_mod.suite_lanes(bare, "implement"))


class GateOnlyLanes(ReviewFlow, ToolkitFixture, unittest.TestCase):
    """A product with one test command declares it once, as the gate lane: the full role runs that lane."""
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {"gate": ["scripts/gate.sh"]}}}

    def test_the_full_role_resolves_to_the_declared_gate_lane(self):
        c = config.load(self.runner)
        self.assertEqual(config.lane_for(c, "full"), "gate")
        self.assertEqual(config.lane_for(c, "gate"), "gate")
        self.assertEqual(config.lane_for(c, "part"), "part")

    def test_the_implement_and_fix_briefs_run_the_gate_lane_as_the_full_suite(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        texts = {"implement": Path(body["prompt_path"]).read_text()}
        code, _, out, err = self.report(body["run_id"], done_report("implement", "PR: #7", f"Head: {A}"))
        self.assertEqual(code, 0, out + err)
        self.run_phase("review", A, "Severity: BLOCKER=1 MAJOR=0 MINOR=0 NIT=0")
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        texts["fix"] = Path(body["prompt_path"]).read_text()
        for phase, text in texts.items():
            self.assertIn("`--lane gate` with nothing after `--`", text, phase)
            self.assertIn("`--`: the product's full suite", text, phase)
            self.assertIn("suite run --lane gate`", text, phase)
            self.assertNotIn("--lane full", text, phase)


class RenamedGateOnlyLanes(ToolkitFixture, unittest.TestCase):
    """The fallback reads the gate role's lane by the name `suite.roles` gives it."""
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON,
                  "suite": {"lanes": {"formal": ["scripts/gate.sh"]}, "roles": {"gate": "formal"}}}

    def test_the_full_role_resolves_to_the_renamed_gate_lane(self):
        c = config.load(self.runner)
        self.assertEqual(config.lane_for(c, "full"), "formal")
        self.assertEqual(config.lane_for(c, "gate"), "formal")


class FullAndGateLanes(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {"gate": ["scripts/gate.sh"], "full": ["scripts/all.sh"]}}}

    def test_a_declared_full_lane_stays_the_full_role(self):
        c = config.load(self.runner)
        self.assertEqual(config.lane_for(c, "full"), "full")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(DECLARED, text)
        self.assertIn("suite run --lane full`", text)


CHECKS = [{"id": "E1", "cmd": "scripts/house-one.sh"}, {"id": "E2", "cmd": "scripts/house-two.sh"}]


class _PregateBriefs(ReviewFlow, ToolkitFixture):
    """The four change rounds' briefs, rendered in turn for one task."""

    def briefs(self) -> dict[str, str]:
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        texts = {"implement": Path(body["prompt_path"]).read_text()}
        code, _, out, err = self.report(body["run_id"], done_report("implement", "PR: #7", f"Head: {A}"))
        self.assertEqual(code, 0, out + err)
        self.run_phase("review", A, "Severity: BLOCKER=1 MAJOR=0 MINOR=0 NIT=0")
        steps = (("fix", A, B, ()), ("merge", B, A, ()), ("ruling", A, B, ("--note", "the field is optional")))
        for phase, head, to, extra in steps:
            code, body, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", head, *extra)
            self.assertEqual(code, 0, f"{phase}: {out}{err}")
            texts[phase] = Path(body["prompt_path"]).read_text()
            code, _, out, err = self.report(body["run_id"], done_report(phase, "PR: #7", f"Head: {to}"))
            self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        return texts


class DeclaredPregateLane(_PregateBriefs, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "architect": {"checks": CHECKS},
                  "suite": {"lanes": {"gate": ["scripts/gate.sh"], "pregate": ["scripts/pregate.sh"]}}}

    def test_the_pregate_lane_replaces_the_house_rule_checks_in_every_change_brief(self):
        texts = self.briefs()
        self.assertEqual(sorted(texts), ["fix", "implement", "merge", "ruling"])
        for phase, text in texts.items():
            self.assertIn("--lane pregate`, as plane.json gives it", text, phase)
            self.assertIn("suite run --affected --since ", text, phase)
            for c in CHECKS:
                self.assertNotIn(c["cmd"], text, phase)
            self.assertNotIn("house-rule checks (", text, phase)


class NoPregateLane(_PregateBriefs, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "architect": {"checks": CHECKS},
                  "suite": {"lanes": {"gate": ["scripts/gate.sh"]}}}

    def test_without_the_lane_the_briefs_render_the_house_rule_checks(self):
        texts = self.briefs()
        for phase, text in texts.items():
            self.assertIn("checks (`scripts/house-one.sh`, `", text, phase)
            self.assertIn("`scripts/house-two.sh`) and `", text, phase)
            self.assertNotIn("--lane pregate", text, phase)
            self.assertNotIn("pre-gate lane", text, phase)


if __name__ == "__main__":
    unittest.main()
