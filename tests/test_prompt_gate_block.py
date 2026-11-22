"""The before-push block (SPEC §13.2, §13.5): written once, in `templates/prompts/_gate.md`, and rendered into
the phases that push, with each phase's differences set as section flags by `ccp/prompt.py`."""
from __future__ import annotations

import re
import unittest

from ccp import prompt, runs

PUSHING = runs.CHANGE_PHASES


def values(**over) -> dict:
    """Every name the templates use, set to a placeholder, every section off, with the given overrides."""
    names: set[str] = set()
    sections: set[str] = set()
    for f in prompt.TEMPLATES.glob("*.md"):
        t = f.read_text()
        names |= set(prompt.VAR_RE.findall(t))
        sections |= {m[1] for m in re.findall(r"\{\{([#^/])(\w+)\}\}", t)}
    v: dict = {n: f"<{n}>" for n in names} | {n: "" for n in sections}
    v.update(integration="main", head="<head>")
    v.update(over)
    return v


class GateBlock(unittest.TestCase):
    def test_every_phase_that_pushes_has_its_flags_and_no_other_phase_does(self):
        self.assertEqual(set(prompt.GATE_FLAGS), set(runs.CHANGE_PHASES))

    def test_each_phase_that_pushes_gets_the_block_once_and_no_other_phase_does(self):
        for phase in PUSHING:
            self.assertEqual(prompt.render_phase(phase, values()).count("Fail fast first"), 1, phase)
        for phase in ("review", "verify"):
            self.assertNotIn("Fail fast first", prompt.render_phase(phase, values()), phase)

    def test_the_catch_up_is_the_implement_and_fix_rounds_own(self):
        for phase in PUSHING:
            text = prompt.render_phase(phase, values())
            self.assertEqual("do not merge again if the tip moves" in text, phase in ("implement", "fix"), phase)

    def test_the_affected_run_starts_from_the_integration_tip_in_every_phase(self):
        for phase in PUSHING:
            text = prompt.render_phase(phase, values())
            self.assertIn("suite affected --since origin/main`", text, phase)
            self.assertNotIn("--since <head>", text, phase)
            self.assertEqual("adr decide" in text, phase == "implement", phase)

    def test_only_the_merge_round_hands_a_tip_failure_to_the_report(self):
        for phase in PUSHING:
            text = prompt.render_phase(phase, values())
            self.assertEqual("a failure the tip brought in" in text, phase == "merge", phase)
            self.assertEqual("must be green" in text, phase != "merge", phase)

    def test_the_budget_check_runs_before_the_pre_gate_only_in_implement(self):
        for phase in PUSHING:
            text = prompt.render_phase(phase, values(budgets=True))
            before = text[:text.index("run a quick pre-gate")]
            self.assertEqual("budgets check" in before.split("Fail fast first")[1], phase == "implement", phase)


if __name__ == "__main__":
    unittest.main()
