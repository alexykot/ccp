"""Worker efficiency (SPEC §13.5, 2026-10-22): the worker agents' tool allowlist and 1-hour cache
lifetime (§2.5), the fail-fast pre-gate and exploration hygiene in the implement and fix briefs
(§15.2), one statement of each rule, the report-before-remove order in review and verify, the
reviewer's use of the product's test cache (§15.3), and the cache-write split in usage (§24)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from ccp import otel, prompt, runs, usage
from tests.test_toolkit import PLANE, git
from tests.test_verify_cache import CacheFixture

AGENTS = PLANE / "plugin" / "agents"
TEMPLATES = PLANE / "templates" / "prompts"
WORKER_TOOLS = {
    "implementer": "Bash, Read, Edit, Write, Grep, Glob, SendMessage, ToolSearch",
    "reviewer": "Bash, Read, Write, Grep, Glob, SendMessage, ToolSearch",
    "verifier": "Bash, Read, Edit, Write, Grep, Glob, SendMessage, ToolSearch",
}
REVIEW_RULE = "This product's test-cache rule (plane.json `verify.accept_cache.review`)"


def fm(name: str) -> dict:
    return runs.agent_frontmatter((AGENTS / f"delivery-{name}.md").read_text())


class Definitions(unittest.TestCase):
    def test_workers_name_their_tools(self):
        for a, tools in WORKER_TOOLS.items():
            self.assertEqual(fm(a)["tools"], tools, a)
            named = {t.strip() for t in tools.split(",")}
            # SendMessage is deferred: ToolSearch loads it (§2.5 "How subagents report")
            self.assertTrue({"Bash", "Read", "SendMessage", "ToolSearch"} <= named, a)
            self.assertFalse(named & {"Agent", "Skill", "Artifact", "WebFetch", "WebSearch"}, a)
        self.assertNotIn("Edit", fm("reviewer")["tools"])  # read only; Write is for its report

    def test_the_runner_keeps_its_tools(self):
        self.assertEqual(fm("runner")["tools"], "Agent, Bash, Read, Edit, Write")

    def test_every_delivery_agent_asks_for_the_1h_cache(self):
        for a in ("runner", *WORKER_TOOLS):
            self.assertEqual(fm(a)["experimental"], {"cacheTtl": "1h"}, a)
            text = (AGENTS / f"delivery-{a}.md").read_text()
            self.assertNotRegex(text.split("\n---\n", 1)[0], r"(?m)^cacheTtl:", a)  # nested, never top level

    def test_a_nested_key_never_shadows_a_top_level_one(self):
        text = "---\nname: x\nmodel: claude-a\nexperimental:\n  model: claude-b\n  cacheTtl: 1h\neffort: high\n---\nbody\n"
        self.assertEqual(runs.agent_frontmatter(text),
                         {"name": "x", "model": "claude-a", "experimental": {"model": "claude-b", "cacheTtl": "1h"},
                          "effort": "high"})
        self.assertEqual(runs.agent_frontmatter("no frontmatter"), {})

    def test_the_suite_rule_is_stated_once_in_the_prompt(self):
        for a in WORKER_TOOLS:  # a definition names the command only in its evidence bullet (§13.1)
            text = (AGENTS / f"delivery-{a}.md").read_text()
            bullet = next(b for b in re.split(r"(?m)^(?=- )", text) if "cite as evidence" in b)
            self.assertEqual(text.count("ccp suite run"), bullet.count("ccp suite run"), a)
            self.assertNotIn("Run every test command", text, a)
        self.assertEqual((TEMPLATES / "_common.md").read_text().count("Run every test command through `ccp`"), 1)

    def test_the_verifier_defers_to_its_prompt_on_the_cache(self):
        text = (AGENTS / "delivery-verifier.md").read_text()
        self.assertIn("A result you did not run is not a pass, except as your prompt's test-cache rule allows", text)
        self.assertNotIn("modules_cached", text)  # the template, not the definition, says what to record


def values(**over) -> dict:
    """Every name the templates use, set to a placeholder, with the given overrides."""
    names = set()
    for f in TEMPLATES.glob("*.md"):
        t = f.read_text()
        names |= set(prompt.VAR_RE.findall(t)) | {m[1] for m in re.findall(r"\{\{([#^/])(\w+)\}\}", t)}
    v = {n: f"<{n}>" for n in names}
    v.update(refactor=False, prior_reports="", note="", worker_env="", rules_doc="", fragment="", main_checkout="/m",
             accept_cache=False, review_cache=False, cold_gate=False, architect_checks="", cache_max_age_days="",
             budgets=False)
    v.update(over)
    return v


def render(phase: str, **over) -> str:
    return prompt.render((TEMPLATES / f"{phase}.md").read_text(), values(**over))


class Templates(unittest.TestCase):
    def test_review_without_the_reviewer_setting_is_unchanged(self):
        base = render("review")
        self.assertNotIn("cache", base)
        # the verifier's rule alone leaves the review brief byte for byte as it is without any rule
        self.assertEqual(render("review", accept_cache=True, cache_max_age_days=3), base)

    def test_review_with_it_runs_touched_modules_through_the_cache(self):
        base = render("review")
        text = render("review", accept_cache=True, review_cache=True, cache_max_age_days=3)
        self.assertIn(REVIEW_RULE, text)
        self.assertIn("no more than 3 days old) counts as run, and as passed", text)
        self.assertIn("Run uncached any check of test order (any-order or reverse-order runs) and every mutation run",
                      text)
        self.assertIn("how many units ran and how many were cached (`ran <r>, cached <c>`).", text)
        start = text.index(" " + REVIEW_RULE)
        end = text.index("cached <c>`).", start) + len("cached <c>`).")
        self.assertEqual(text[:start] + text[end:], base)  # one sentence added, nothing else moved

    def test_review_and_verify_report_before_removing_their_checkout(self):
        for phase in ("review", "verify"):
            text = render(phase, own_worktree="/m/.rt/rev-0002", worktree_links="")
            self.assertNotIn("Remove it when you are done", text, phase)
            self.assertIn("Remove it last, after `ccp report` has accepted your report, with", text)
            self.assertIn("(run `report` from inside it first", text)
            self.assertIn("wt create --kind", text)
            self.assertNotIn("git worktree add --detach", text)
            self.assertIn("add `--root /m` before `report`", text, phase)

    def test_implement_and_fix_fail_fast_and_keep_the_full_suite(self):
        for phase in ("implement", "fix"):
            text = render(phase, architect_checks="`python -m unittest tests.test_a`")
            self.assertIn("run a quick pre-gate through `ccp suite run --lane part`: the product's house-rule checks "
                          "(`python -m unittest tests.test_a`) and the test modules that depend on the paths you changed",
                          text, phase)
            self.assertIn("The pre-gate never stands in for the full suite", text, phase)
            plain = render(phase)
            self.assertNotIn("house-rule checks", plain, phase)
            self.assertIn("run a quick pre-gate through `ccp suite run --lane part`: the test modules that depend", plain)

    def test_implement_and_fix_keep_context_lean_but_read_citations_in_full(self):
        self.assertIn("Read what the task cites in full.", render("implement"))
        self.assertIn("Read what the findings cite in full.", render("fix"))
        for phase in ("implement", "fix"):
            text = render(phase)
            self.assertIn("may run past about 200 lines to a scratch file outside the repo", text, phase)
            self.assertIn("issue independent reads as parallel tool calls in one turn", text, phase)


    def test_the_implementer_lists_each_new_behaviour_and_the_reviewer_checks_it(self):
        """SPEC §13.2: the self-check before the PR."""
        text = render("implement")
        self.assertIn("list each branch, field, refusal or behaviour the diff adds or changes, with the test that "
                      "fails without it, and write the test for any that has none", text)
        self.assertIn("`## Tests for new behaviour`", text)
        self.assertLess(text.index("Tests for new behaviour"), text.index("Fail fast first"))  # before the full suite
        self.assertIn("under `## Tests for new behaviour` in your report", render("fix"))
        # The map is the report's, never test names or docstrings
        self.assertIn("never put dod_check ids or the map in test names or docstrings", text)
        self.assertIn("no dod_check ids or map in test names or docstrings", render("fix"))

        review = render("review")
        self.assertIn("check those lists against the diff (in a later round, the fix reports' lists", review)
        self.assertIn("A report from before this rule has no list", review)

    def test_with_budgets_the_implement_fix_and_verify_briefs_run_the_budget_check(self):
        """§20.2: only on the files the change grew, in each phase's gate."""
        cmd = "budgets check --base origin/main"
        for phase in ("implement", "fix", "verify"):
            self.assertIn(cmd, render(phase, budgets=True, integration="main"), phase)
            self.assertNotIn("budgets check", render(phase, integration="main"), phase)
        text = render("implement", budgets=True, integration="main")
        self.assertLess(text.index(cmd), text.index("run a quick pre-gate through"))  # before the pre-gate
        self.assertIn("its warnings are not failures", render("verify", budgets=True, integration="main"))
        self.assertNotIn("budgets check", render("review", budgets=True, integration="main"))

class Rendered(CacheFixture, unittest.TestCase):
    """Through `ccp prompt`: the settings come from plane.json."""

    def review_prompt(self) -> str:
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        return (self.q / "prompts/0002-second/review-prompt.md").read_text()

    def test_review_prompt_off_by_default_and_on_with_review_true(self):
        self.assertNotIn(REVIEW_RULE, self.review_prompt())

    def test_review_true_renders_the_rule(self):
        self.plane({"max_age_days": 3, "review": True})
        self.assertIn(REVIEW_RULE, self.review_prompt())

    def test_architect_checks_are_named_in_the_implement_prompt(self):
        body = {**self.PLANE_JSON, "architect": {"checks": [{"id": "E1", "cmd": "python3 -m unittest -q tests.test_x"}]}}
        self.write("docs/delivery/plane.json", json.dumps(body))
        git(self.main, "commit", "-qam", "checks")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = (self.q / "prompts/0002-second/implement-prompt.md").read_text()
        self.assertIn("house-rule checks (`python3 -m unittest -q tests.test_x`)", text)


class CacheSplit(unittest.TestCase):
    def test_the_receiver_keeps_the_cache_write_split(self):
        a = {"event.name": "api_request", "cache_creation_tokens": 30, "cache_creation_5m_tokens": "10",
             "cache_creation_1h_tokens": 20, "request_id": "r1"}
        row = otel._row(a, otel.REQUEST_FIELDS)
        self.assertEqual((row["cache_creation_5m_tokens"], row["cache_creation_1h_tokens"]), (10, 20))

    def test_usage_sums_it_apart_from_the_totals(self):
        acc = usage._blank()
        usage._add(acc, {"cache_creation_tokens": 30, "cache_creation_5m_tokens": 10, "cache_creation_1h_tokens": 20})
        usage._add(acc, {"cache_creation_tokens": 5})  # a row from before the split was kept
        out = usage._out(acc)
        self.assertEqual((out["cache_creation_tokens"], out["cache_creation_5m_tokens"], out["cache_creation_1h_tokens"]),
                         (35, 10, 20))
        self.assertNotIn("cache_creation_1h_tokens", usage.TOKENS)  # a part of cache_creation_tokens, never added twice


    def test_workers_merge_the_integration_branch_in_never_rebase(self):
        """A rebase needs a force-push, which Claude Code's auto mode denies."""
        self.assertIn("by merging it in (`git merge origin/", render("implement"))
        self.assertIn("never by rebasing", render("implement"))
        self.assertIn("merge it into the branch (`git merge origin/", render("fix"))
        self.assertNotIn("Rebase onto", render("implement"))


if __name__ == "__main__":
    unittest.main()
