"""The full lane in the worker prompts (SPEC §14.1, §13.2): a lane plane.json `suite.lanes` declares is run as
`--lane <lane>` with nothing after `--`, so a fix or merge round runs the product's own full suite; a lane it
does not declare still takes the command after `--`."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, prompt as prompt_mod
from tests import test_review_gate
from tests.test_toolkit import ToolkitFixture

A, B = "a" * 40, "b" * 40
DECLARED = "`--lane full` with nothing after `--`"


class DeclaredFullLane(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "suite": {"lanes": {"full": ["scripts/gate.sh"]}}}
    run_phase = test_review_gate.ReviewGate.run_phase

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
            code, _, out, err = self.report(body["run_id"], f"Outcome: done\nPR: #7\nHead: {to}\n## Friction\nnone\n")
            self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        for phase, text in texts.items():
            self.assertIn(DECLARED, text, phase)
            self.assertIn("suite run --lane full`", text, phase)  # the round's full test suite names the lane
            self.assertNotIn("--lane full -- ", text, phase)

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
        self.assertIn("`--lane formal` with nothing after `--`: the formal gate", prompt_mod.suite_lanes(c, "verify"))
        self.assertIn("`--lane whole` with nothing after `--`: the product's full suite",
                      prompt_mod.suite_lanes(c, "implement"))
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
        self.assertIn("`--lane full` for the product's full suite", text)
        self.assertNotIn(DECLARED, text)


if __name__ == "__main__":
    unittest.main()
