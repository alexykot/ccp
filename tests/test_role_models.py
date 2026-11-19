"""SPEC §2.4: each role's default model is one table (`models.ROLES`, `models.FULL_IDS`); the headless
launchers read it, and each plugin agent definition's model id and effort equal its role's row."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from ccp import estimator, models, tasklog

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"
DEFINED = ("runner", "implementer", "reviewer", "verifier")
sys.path.insert(0, str(PLUGIN.parent / "scripts" / "observability"))
import architecture_review  # noqa: E402


class TheRoleTable(unittest.TestCase):
    def test_each_definition_holds_its_roles_row(self):
        for role in DEFINED:
            fm = tasklog.frontmatter((PLUGIN / "agents" / f"delivery-{role}.md").read_text())
            model, effort = models.default(role)
            self.assertEqual((fm["model"], fm["effort"]), (model, effort), f"delivery-{role}.md: the {role} row")

    def test_every_row_names_a_pinned_alias(self):
        for role, (alias, effort) in models.ROLES.items():
            self.assertIn(alias, models.FULL_IDS, role)
            self.assertIn(effort, ("low", "medium", "high", "xhigh", "max"), role)

    def test_the_headless_flags_are_the_rows(self):
        self.assertEqual(models.headless_flags("architect"), ["--model", "claude-opus-5-5", "--effort", "high"])
        self.assertEqual(models.headless_flags("estimator"), ["--model", "claude-sonnet-5-5", "--effort", "medium"])

    def test_the_launchers_take_their_flags_from_the_table(self):
        self.assertEqual(estimator.HEADLESS_MODEL, models.headless_flags("estimator"))
        self.assertEqual(architecture_review.HEADLESS_MODEL, models.headless_flags("architect"))

    def test_a_role_without_a_row_is_refused(self):
        with self.assertRaises(KeyError):
            models.headless_flags("lead")


if __name__ == "__main__":
    unittest.main()
