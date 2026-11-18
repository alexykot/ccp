"""`ccp prompt` (SPEC §13.2, §13.5, §20.6): the worker prompts name the tools the workers run, `ccp mutate`
from the worker's own worktree and `ccp suite affected` for the pre-gate's test modules."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from ccp import prompt as prompt_mod
from tests.test_toolkit import PLANE, ToolkitFixture

A = "a" * 40
CHANGE_ROUNDS = (("implement", ("--base", "abc1234"), "origin/main"),
                 ("fix", ("--pr", "7", "--head", A), A),
                 ("merge", ("--pr", "7", "--head", A), A),
                 ("ruling", ("--pr", "7", "--head", A, "--note", "the field is optional"), A))


# The one place a prompt names a mutation worktree: where the product declares no `mutate.command`,
# up to the clause's end (`;` or a sentence's `.`).
FALLBACK = re.compile(r"Where the product declares no `mutate\.command`.*?(?:;|\.(?=\s|$))")


def outside_the_fallback(text: str) -> str:
    return FALLBACK.sub("", text)


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
        self.assertNotIn("wt create --kind mut", outside_the_fallback(text))

    def test_with_no_mutate_command_a_seat_breaks_code_in_a_mutation_worktree_it_removes(self):
        run_id, text = self.render("verify", "--pr", "7", "--head", A)
        fallbacks = FALLBACK.findall(text)
        self.assertTrue(fallbacks)
        for f in fallbacks:
            self.assertIn("wt create --kind mut --task 0002-second --sha ", f)
            self.assertIn("wt remove <name>", f)
        self.assertIn(f"wt create --kind mut --task 0002-second --sha {A}`", text)
        self.assertIn(f"suite run --run {run_id} --lane part -- <command>`", text)
        _impl_run, text_impl = self.render("implement", "--base", "abc1234")  # every seat, through the common rules
        fallbacks = FALLBACK.findall(text_impl)
        self.assertTrue(fallbacks)
        for f in fallbacks:
            for named in ("wt create --kind mut --task 0002-second --sha <head>`", "wt remove <name>`", "`--lane part`"):
                self.assertIn(named, f)
        self.assertNotIn("put the file back", text)
        self.assertNotIn("put the file back", (PLANE / "templates/prompts/verify.md").read_text())
        for a in ("implementer", "reviewer", "verifier"):
            brief = (PLANE / f"plugin/agents/delivery-{a}.md").read_text()
            for named in ("ccp wt create --kind mut", "ccp wt remove <name>"):
                self.assertIn(named, brief, (a, named))

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

    def test_the_implementer_sends_rule_text_the_task_does_not_carry_to_a_proposal(self):
        _run_id, text = self.render("implement", "--base", "abc1234")
        self.assertIn("plane propose`), not the PR", text)
        self.assertIn("only text without which the code cannot be correct goes to the lead, as a spec question", text)

    def test_the_verify_prompt_names_the_record_s_project_id_its_findings_list_and_an_example_that_exists(self):
        _run_id, text = self.render("verify", "--pr", "7", "--head", A)
        self.assertIn('`project_id: "demo"`', text)
        self.assertIn("`findings`, a list of strings", text)
        example = PLANE / "contracts" / "verification.example.json"
        self.assertTrue(example.is_absolute() and example.is_file())
        self.assertIn(f"a valid example is {example})", text)

    def test_the_implementer_flips_the_decisions_it_builds_and_every_worker_hears_a_staged_lane_takes_no_command(self):
        _run_id, text = self.render("implement", "--base", "abc1234")
        self.assertIn("adr decide <n> <Dn> built", text)
        for phase, args in (("verify", ("--pr", "7", "--head", A)), ("implement", ("--base", "abc1234"))):
            _run_id, text = self.render(phase, *args)
            self.assertIn("gives stages takes no command", text, phase)

    def test_no_template_sends_a_worker_to_a_mutation_worktree_or_a_discovery_command(self):
        for phase in ("implement", "fix", "ruling", "merge", "verify", "_common"):
            text = outside_the_fallback((PLANE / "templates/prompts" / f"{phase}.md").read_text())
            for gone in ("dependent-modules command", "mut worktree", "--kind mut"):
                self.assertNotIn(gone, text, (phase, gone))
        self.assertEqual(prompt_mod.TEMPLATES, PLANE / "templates/prompts")


if __name__ == "__main__":
    unittest.main()
