"""SPEC §2.4: each role's default model is one table (`models.ROLES`, `models.FULL_IDS`); the headless
launchers read it, and each plugin agent definition's model id and effort equal its role's row."""
from __future__ import annotations

import unittest

from ccp import architecture_review, estimator, models, tasklog
from tests.helpers import PLANE_ROOT

PLUGIN = PLANE_ROOT / "plugin"
DEFINED = ("runner", "implementer", "reviewer", "verifier")


class TheRoleTable(unittest.TestCase):
    def test_each_definition_holds_its_roles_row(self):
        for role in DEFINED:
            fm = tasklog.frontmatter((PLUGIN / "agents" / f"delivery-{role}.md").read_text())
            model, effort = models.default(role)
            self.assertEqual((fm["model"], fm["effort"]), (model, effort), f"delivery-{role}.md: the {role} row")

    def test_every_row_names_a_pinned_alias(self):
        for role, (alias, effort) in models.ROLES.items():
            self.assertIn(alias, models.FULL_IDS, role)
            self.assertIn(effort, ("low", "medium", "high", "xhigh", "max", None), role)  # None: the operator sets it

    def test_the_headless_flags_are_the_rows(self):
        self.assertEqual(models.headless_flags("architect"), ["--model", "claude-opus-5-5", "--effort", "high"])
        self.assertEqual(models.headless_flags("estimator"), ["--model", "claude-sonnet-5-5", "--effort", "medium"])

    def test_the_launchers_take_their_flags_from_the_table(self):
        self.assertEqual(estimator.HEADLESS_MODEL, models.headless_flags("estimator"))
        self.assertEqual(architecture_review.HEADLESS_MODEL, models.headless_flags("architect"))

    def test_a_role_without_a_row_or_an_effort_is_refused(self):
        for role in ("nobody", "lead"):
            with self.assertRaises(KeyError, msg=role):
                models.headless_flags(role)

    def test_the_reviewer_runs_on_opus_and_the_small_arms_on_sonnet(self):
        self.assertEqual(models.default("reviewer")[0], "claude-opus-5-5")
        self.assertEqual([models.ROLES[r][0] for r in ("implementer_small", "implementer_refactor", "lead")],
                         ["sonnet", "sonnet", "opus"])


if __name__ == "__main__":
    unittest.main()
