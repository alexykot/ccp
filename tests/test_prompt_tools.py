"""`ccp prompt` (SPEC §13.2, §13.5, §20.6): the worker prompts name the tools the workers run, `ccp mutate`
from the worker's own worktree and `ccp suite run --affected` since the merge base with the integration tip for
the test modules a change touches, in every change round's pre-gate and the reviewer's part-lane run."""
from __future__ import annotations

import unittest
from pathlib import Path

from ccp import config
from ccp import prompt as prompt_mod
from tests.helpers import PLANE_ROOT
from tests.render_helpers import phase_values
from tests.toolkit_fixture import ToolkitFixture

A = "a" * 40
CHANGE_ROUNDS = (("implement", ("--base", "abc1234")),
                 ("fix", ("--pr", "7", "--head", A)),
                 ("merge", ("--pr", "7", "--head", A)),
                 ("ruling", ("--pr", "7", "--head", A, "--note", "the field is optional")))


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
        self.assertIn(f"mutate --run {run_id} --test", text)
        self.assertIn("<test id> --revert <path>[:<lines>]", text)
        self.assertIn(str(self.main / config.WORKTREES_DIR / "ver-0002"), text)
        self.assertEqual(text.count("wt create --kind mut"), 1)  # the one fallback line of the shared part

    def test_every_worker_prompt_names_how_to_run_one_check(self):
        for phase, args in (("implement", ("--base", "abc1234")), ("review", ("--pr", "7", "--head", A)),
                            ("verify", ("--pr", "7", "--head", A))):
            _run_id, text = self.render(phase, *args)
            self.assertIn("tasks dry-run 0002-second --check", text, phase)
            self.assertIn("--check <check id> --here", text, phase)
            self.assertIn("docs check --only", text, phase)

    def test_the_verifier_is_told_the_flag_that_runs_the_prs_own_hooks(self):
        _run_id, text = self.render("verify", "--pr", "7", "--head", A)
        self.assertIn("`--own-hooks`", text)
        self.assertIn("add `--own-hooks`", (PLANE_ROOT / "templates/prompts/verify.md").read_text())

    def test_with_no_mutate_command_a_seat_breaks_code_in_a_mutation_worktree_it_removes(self):
        _run_id, text = self.render("verify", "--pr", "7", "--head", A)
        self.assertEqual(text.count("wt create --kind mut"), 1)
        line = next(ln for ln in text.splitlines() if "wt create --kind mut" in ln)
        for named in ("--task 0002-second --sha ", "wt remove <name>", "`--lane part`"):
            self.assertIn(named, line)
        _impl_run, text_impl = self.render("implement", "--base", "abc1234")  # every seat, through the common rules
        self.assertEqual(text_impl.count("wt create --kind mut"), 1)
        line = next(ln for ln in text_impl.splitlines() if "wt create --kind mut" in ln)
        for named in ("wt create --kind mut --task 0002-second --sha <head>`", "wt remove <name>`", "`--lane part`"):
            self.assertIn(named, line)

    def test_the_verify_prompt_asks_for_the_ran_false_reliance_and_the_ruling_id(self):
        _run_id, text = self.render("verify", "--pr", "7", "--head", A)
        lines = text.splitlines()
        self.assertTrue(any("`findings`" in ln and "`ran: false`" in ln for ln in lines))
        self.assertTrue(any("`ruling`" in ln and "message" in ln for ln in lines))

    def test_the_change_rounds_name_mutate_and_suite_run_affected(self):
        for phase, args in CHANGE_ROUNDS:
            run_id, text = self.render(phase, *args)
            self.assertIn(f"mutate --run {run_id} --test <test id>", text, phase)
            self.assertIn("--affected --since origin/main...`", text, phase)

    def test_fix_ruling_and_merge_affected_since_the_tip(self):
        """After their catch-up merge, the round's own change is its diff from its merge base with the integration
        tip; its starting head would also name every file the tip brought in."""
        for phase, args in CHANGE_ROUNDS[1:]:
            _run_id, text = self.render(phase, *args)
            self.assertIn("--affected --since origin/main...`", text, phase)
            self.assertNotIn(f"--since {A}", text, phase)
            self.assertNotIn(f"--since {A[:7]}", text, phase)

    def test_the_review_prompt_names_suite_run_affected_since_the_merge_base_with_the_tip(self):
        _run_id, text = self.render("review", "--pr", "7", "--head", A)
        self.assertIn("--affected --since origin/main...", text)
        self.assertNotIn(f"--since {A[:7]}", text)

    def test_the_review_prompt_routes_mutation_checks_through_mutate_only(self):
        """§20.6: a reviewer's mutation check runs through `ccp mutate`, as the shared part gives it, never through
        the part lane's `suite run`: in a full review, and in a resolution review (its template and the shared part,
        as `ccp prompt` joins them: opening one needs a conflicted merge). No line of the review template's own
        render, in either review and with or without the review cache, names a mutation and `suite run` together
        (the shared part's evidence line does, and gives `mutate` beside it)."""
        full = self.render("review", "--pr", "7", "--head", A)
        v = phase_values(resolution=True)
        resolution = (v["run_id"], prompt_mod.render_phase("review", v)
                      + prompt_mod.render((prompt_mod.TEMPLATES / "_common.md").read_text(), v))
        for run_id, text in (full, resolution):
            self.assertIn(f"mutate --run {run_id}", text)
        for res in (False, True):
            for cache in (False, True):
                own = prompt_mod.render_phase("review", phase_values(resolution=res, review_cache=cache))
                both = [ln for ln in own.splitlines() if "mutation" in ln and "suite run" in ln]
                self.assertEqual(both, [], (res, cache))

    def test_the_reviewer_reads_and_runs_code_at_the_merge_base_in_a_base_worktree(self):
        brief = (PLANE_ROOT / "plugin/agents/delivery-reviewer.md").read_text()
        self.assertIn("wt create --kind base --task <task_id>", brief)
        self.assertIn("--sha <PR head> -- <command>", brief)
        self.assertNotIn("git merge-base", brief)

    def test_every_worker_prompt_gives_long_commands_the_full_timeout_and_names_suite_wait(self):
        for phase, args in (("verify", ("--pr", "7", "--head", A)), ("review", ("--pr", "7", "--head", A)), *CHANGE_ROUNDS):
            _run_id, text = self.render(phase, *args)
            self.assertIn("timeout: 600000", text, phase)
            self.assertIn("suite wait <suite_id>", text, phase)

    def test_the_implementer_sends_rule_text_the_task_does_not_carry_to_a_follow_up(self):
        _run_id, text = self.render("implement", "--base", "abc1234")
        self.assertIn("`## Follow-ups`, not the PR", text)
        self.assertIn("as a spec question", text)

    def test_the_verify_prompt_names_the_record_s_project_id_its_findings_list_and_an_example_that_exists(self):
        _run_id, text = self.render("verify", "--pr", "7", "--head", A)
        self.assertIn('`project_id: "demo"`', text)
        self.assertIn("`findings`, a list of strings", text)
        example = PLANE_ROOT / "contracts" / "verification.example.json"
        self.assertTrue(example.is_absolute() and example.is_file())
        self.assertIn(f"a valid example is {example})", text)

    def test_the_implementer_flips_the_decisions_it_builds_and_every_worker_hears_a_staged_lane_takes_no_command(self):
        _run_id, text = self.render("implement", "--base", "abc1234")
        self.assertIn("adr decide <n> <Dn> built", text)
        for phase, args in (("verify", ("--pr", "7", "--head", A)), ("implement", ("--base", "abc1234"))):
            _run_id, text = self.render(phase, *args)
            self.assertIn("refuses one on a lane with stages", text, phase)

    def test_no_template_sends_a_worker_to_a_mutation_worktree_or_a_discovery_command(self):
        """The mutation-worktree fallback is on one line of the shared part, `_common.md`, and of no other template."""
        holding = [(f.name, ln) for f in sorted((PLANE_ROOT / "templates/prompts").glob("*.md"))
                   for ln in f.read_text().splitlines() if "--kind mut" in ln]
        self.assertEqual([name for name, _ln in holding], ["_common.md"])
        for phase in ("implement", "fix", "ruling", "merge", "verify", "_common", "_gate"):
            text = (PLANE_ROOT / "templates/prompts" / f"{phase}.md").read_text()
            self.assertNotIn("mut worktree", text, phase)
        self.assertEqual(prompt_mod.TEMPLATES, PLANE_ROOT / "templates/prompts")


class PromptsNameTheHouseRules(ToolkitFixture, unittest.TestCase):
    """The architect seat is on without a block (§19.11): its default `rules_doc` is named in a prompt only
    once the file exists."""
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "architect": {}}

    def render(self) -> str:
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        return Path(body["prompt_path"]).read_text()

    def test_a_worker_is_sent_to_the_house_rules_only_when_the_file_exists(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Read the house rules", self.render())
        (self.runner / "docs/ENGINEERING.md").write_text("# Rules\n")
        self.assertIn("house rules, docs/ENGINEERING.md", self.render())


if __name__ == "__main__":
    unittest.main()
