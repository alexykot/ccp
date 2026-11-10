"""Verdicts a product requires on every implementer report (SPEC §13.4, plane.json `report.required_fields`):
`ccp report` checks them, the run keeps them, the implement and fix prompts list them and the review prompt
shows them."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import config, report
from tests.test_toolkit import PLANE, ToolkitFixture

MIGRATION = {"name": "migration", "values": ["required", "not required"]}
HEAD = "a" * 40


def implement_report(*lines: str, outcome: str = "done") -> str:
    return "\n".join([f"Outcome: {outcome}", "PR: #7", f"Head: {HEAD}", *lines, "## Friction", "none", ""])


class Declared(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "report": {"required_fields": [MIGRATION]}}

    def implement(self) -> dict:
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        return body

    def test_a_report_without_the_verdict_is_refused_naming_it_and_its_values(self):
        self.implement()
        code, _, _, err = self.report("0002-second/implement", implement_report())
        self.assertEqual(code, 1)
        for want in ("migration", "`required`", "`not required`"):
            self.assertIn(want, err)
        self.assertFalse((self.q / "progress/0002-second/implement-report.md").exists())
        self.assertIsNone(json.loads((self.q / "runs/0002-second/implement.json").read_text())["reported_at"])

    def test_a_value_outside_the_declared_ones_is_refused(self):
        self.implement()
        for said in ("maybe", "requiredness"):
            code, _, _, err = self.report("0002-second/implement", implement_report(f"Migration: {said}"))
            self.assertEqual(code, 1, said)
            self.assertIn(f"says `{said}`", err)
            self.assertIn("`not required`", err)

    def test_the_verdict_is_recorded_on_the_run_and_in_the_output(self):
        self.implement()
        code, body, out, err = self.report("0002-second/implement",
                                           implement_report("- **Migration:** not required (no schema change)"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["fields"], {"migration": "not required"})
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(run["fields"], {"migration": "not required"})

    def test_a_report_that_is_not_done_need_not_state_it(self):
        self.implement()
        code, _, out, err = self.report("0002-second/implement", "Outcome: blocked\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    def test_a_review_report_need_not_state_it(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        code, _, out, err = self.report("0002-second/review",
                                        "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    def test_the_implement_prompt_lists_the_field_and_its_values(self):
        text = Path(self.implement()["prompt_path"]).read_text()
        self.assertIn("`migration: required|not required`", text)

    def test_the_review_prompt_shows_the_latest_implementer_verdict(self):
        self.implement()
        self.report("0002-second/implement", implement_report("Migration: required"))
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("`migration: required`", text)
        self.assertIn("0002-second/implement", text)
        self.assertEqual(body["report_fields"], {"run_id": "0002-second/implement", "fields": {"migration": "required"}})
        self.report("0002-second/review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0\n## Friction\nnone\n")
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertIn("`migration: required|not required`", Path(body["prompt_path"]).read_text())
        code, _, _, err = self.report("0002-second/fix", implement_report())
        self.assertEqual(code, 1)
        self.assertIn("migration", err)
        code, _, out, err = self.report("0002-second/fix", implement_report("Migration: not required"))
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("`migration: not required`", text)
        self.assertNotIn("`migration: required`", text)
        self.assertEqual(body["report_fields"]["run_id"], "0002-second/fix")

    def test_a_report_from_before_the_declaration_shows_the_verdict_as_not_stated(self):
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(ToolkitFixture.PLANE_JSON))
        self.implement()
        code, _, out, err = self.report("0002-second/implement", implement_report())
        self.assertEqual(code, 0, out + err)
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(self.PLANE_JSON))
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertIn("`migration: not stated`", Path(body["prompt_path"]).read_text())

    def test_the_review_prompt_shows_nothing_before_an_implementer_report(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("report.required_fields", Path(body["prompt_path"]).read_text())
        self.assertNotIn("report_fields", body)


class Parse(unittest.TestCase):
    def test_the_longest_declared_value_that_fits_wins(self):
        deploy = [{"name": "Deploy step", "values": ["yes", "yes after the migration"]}]
        self.assertEqual(report.fields("deploy step: yes after the migration, then restart\n", deploy),
                         ({"Deploy step": "yes after the migration"}, []))
        self.assertEqual(report.fields("Deploy step: `yes`.\n", deploy), ({"Deploy step": "yes"}, []))


class Undeclared(ToolkitFixture, unittest.TestCase):
    def test_without_a_declaration_nothing_is_asked_or_shown(self):
        self.ccp("tasks", "claim", "0002")
        body = self.ccp("prompt", "implement", "0002", "--base", "abc1234")[1]
        self.assertNotIn("report.required_fields", Path(body["prompt_path"]).read_text())
        code, out_body, out, err = self.report("0002-second/implement", implement_report())
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("fields", out_body)
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("report.required_fields", Path(body["prompt_path"]).read_text())


class ConfigBlock(ToolkitFixture, unittest.TestCase):
    def load(self, report) -> config.Config:
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "report": report}))
        return config.load(self.main)

    def test_the_block_is_read_and_defaults_to_none(self):
        self.assertEqual(self.load({"required_fields": [MIGRATION]}).report["required_fields"], [MIGRATION])
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))
        self.assertEqual(config.load(self.main).report, {"required_fields": []})

    def test_a_malformed_declaration_is_refused(self):
        for bad in ({"required_fields": "migration"}, {"other": []},
                    {"required_fields": [{"name": "migration"}]},
                    {"required_fields": [{**MIGRATION, "extra": 1}]},
                    {"required_fields": [{"name": "1st", "values": ["a"]}]},
                    {"required_fields": [{"name": "migration ", "values": ["a"]}]},
                    {"required_fields": [{"name": "Outcome", "values": ["a"]}]},
                    {"required_fields": [MIGRATION, {"name": "Migration", "values": ["a"]}]},
                    {"required_fields": [{"name": "migration", "values": []}]},
                    {"required_fields": [{"name": "migration", "values": ["a", "A"]}]},
                    {"required_fields": [{"name": "migration", "values": ["a\nb"]}]},
                    {"required_fields": [{"name": "migration", "values": [" a"]}]}):
            with self.assertRaises(config.ConfigError, msg=bad):
                self.load(bad)

    def test_the_schema_lists_the_block(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["report"]["properties"]), set(config.REPORT_DEFAULTS))


if __name__ == "__main__":
    unittest.main()
