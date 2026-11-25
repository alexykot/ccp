"""`ccp prompt render <phase> [--on <name>]…` (SPEC §13.2): a phase's prompt as `ccp prompt` joins its parts, every
value a `<name>` placeholder and every section off unless `--on` names it, from no task, claim or run, with
nothing written."""
from __future__ import annotations

import unittest
from unittest import mock

from ccp import prompt as prompt_mod, runs
from tests.render_helpers import phase_values
from tests.toolkit_fixture import ToolkitFixture


class PromptRender(ToolkitFixture, unittest.TestCase):
    def queue_files(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.q)): p.read_bytes() for p in sorted(self.q.rglob("*")) if p.is_file()}

    def test_it_prints_the_phase_prompt_with_a_placeholder_for_every_value_and_writes_nothing(self):
        before = self.queue_files()
        with mock.patch("ccp.board.refresh") as refresh:
            code, _, out, err = self.ccp("prompt", "render", "implement")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.queue_files(), before)  # no prompt file, audit, run or event
        refresh.assert_not_called()
        self.assertIn("mutate --run <run_id> --test <test id>", out)
        self.assertIn("<ccp> suite run", out)
        self.assertNotIn("{{", out)
        self.assertNotIn("Prompt end:", out)  # the end line is a run's own

    def test_it_needs_no_task_or_claim_and_every_phase_renders(self):
        for phase in runs.PHASES:
            code, _, out, err = self.ccp("prompt", "render", phase)
            self.assertEqual(code, 0, f"{phase}: {err}")
            self.assertTrue(out.endswith("\n"), phase)
            self.assertIn("<run_id>", out, phase)

    def test_it_joins_the_phase_template_and_the_shared_part_as_ccp_prompt_does(self):
        _code, _, out, _err = self.ccp("prompt", "render", "verify")
        shared = prompt_mod.render((prompt_mod.TEMPLATES / "_common.md").read_text(), prompt_mod.placeholder_values())
        self.assertEqual(out, prompt_mod.phase_text("verify", prompt_mod.placeholder_values()))
        self.assertIn(shared.rstrip(), out)
        self.assertTrue(out.index(shared.rstrip()) > len(out) // 3)  # the phase's own text comes first

    def test_a_section_is_off_unless_on_names_it_and_then_its_name_is_a_placeholder(self):
        _code, _, off, _err = self.ccp("prompt", "render", "implement")
        _code, _, on, _err = self.ccp("prompt", "render", "implement", "--on", "refactor", "--on", "change_round")
        self.assertNotEqual(off, on)
        self.assertGreater(len(on), len(off))
        for name in ("refactor", "change_round"):
            self.assertEqual(prompt_mod.placeholder_values([name])[name], f"<{name}>")
            self.assertEqual(prompt_mod.placeholder_values()[name], "")

    def test_an_unknown_phase_or_an_on_naming_no_section_exits_2_and_writes_nothing(self):
        before = self.queue_files()
        for args in (("nope",), ("implement", "--on", "no_such_section"), ("implement", "--on", "run_id")):
            code, _, out, err = self.ccp("prompt", "render", *args)
            self.assertEqual((code, out), (2, ""), args)
            self.assertIn("ccp prompt:", err, args)
        self.assertEqual(self.queue_files(), before)

    def test_the_test_helper_starts_from_the_placeholders_with_every_section_on(self):
        v = phase_values()
        self.assertEqual((v["run_id"], v["change_round"]), ("<run_id>", "<change_round>"))
        self.assertEqual(phase_values(run_id="r1", change_round=False)["run_id"], "r1")
        self.assertIs(phase_values(change_round=False)["change_round"], False)
        self.assertEqual(v["main_checkout"], "/m")  # its own overrides stay


if __name__ == "__main__":
    unittest.main()
