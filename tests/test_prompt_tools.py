"""`ccp prompt` (SPEC §13.2, §13.5, §20.6): the worker prompts name the tools the workers run, `ccp mutate`
from the worker's own worktree and `ccp suite affected` for the pre-gate's test modules."""
from __future__ import annotations

import unittest
from pathlib import Path

from ccp import prompt as prompt_mod
from tests.test_toolkit import PLANE, ToolkitFixture

A = "a" * 40
CHANGE_ROUNDS = (("implement", ("--base", "abc1234"), "origin/main"),
                 ("fix", ("--pr", "7", "--head", A), A),
                 ("merge", ("--pr", "7", "--head", A), A),
                 ("ruling", ("--pr", "7", "--head", A, "--note", "the field is optional"), A))


class PromptsNameTheTools(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        (self.q / "progress/0002-second").mkdir(parents=True)
        (self.q / "progress/0002-second/review-report.md").write_text("Outcome: done\n")  # a fix's findings

    def render(self, phase: str, *args: str) -> tuple[str, str]:
        code, body, out, err = self.ccp("prompt", phase, "0002", *args, "--supersede")
        self.assertEqual(code, 0, f"{phase}: {out}{err}")
        return body["run_id"], Path(body["prompt_path"]).read_text()

    def test_the_verifier_reverts_from_its_own_worktree(self):
        run_id, text = self.render("verify", "--pr", "7", "--head", A)
        self.assertIn(f"mutate --run {run_id} --test <test id> --revert <path>[:<lines>]", text)
        self.assertIn(str(self.main / ".rt" / "ver-0002"), text)
        self.assertNotIn("wt create --kind mut", text)

    def test_the_change_rounds_name_mutate_and_suite_affected(self):
        for phase, args, since in CHANGE_ROUNDS:
            run_id, text = self.render(phase, *args)
            self.assertIn(f"mutate --run {run_id} --test <test id>", text, phase)
            self.assertIn(f"suite affected --since {since}`", text, phase)
            self.assertNotIn("dependent-modules", text, phase)

    def test_every_worker_prompt_gives_long_commands_the_full_timeout_and_names_suite_wait(self):
        for phase, args, _since in (("verify", ("--pr", "7", "--head", A), A), ("review", ("--pr", "7", "--head", A), A),
                                    *CHANGE_ROUNDS):
            _run_id, text = self.render(phase, *args)
            self.assertIn("timeout: 600000", text, phase)
            self.assertIn("suite wait <suite_id>", text, phase)

    def test_no_template_sends_a_worker_to_a_mutation_worktree_or_a_discovery_command(self):
        for phase in ("implement", "fix", "ruling", "merge", "verify"):
            text = (PLANE / "templates/prompts" / f"{phase}.md").read_text()
            for gone in ("dependent-modules command", "mut worktree", "--kind mut"):
                self.assertNotIn(gone, text, (phase, gone))
        self.assertEqual(prompt_mod.TEMPLATES, PLANE / "templates/prompts")


if __name__ == "__main__":
    unittest.main()
