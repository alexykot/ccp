"""`ccp verify spec-text` (SPEC §15.2, §3.5): the passages a task carries for the operator's sign-off, each a
`PROPOSED:` marker followed by `> ` blockquote lines in its Scope or in a section whose heading begins `Rule
changes`, are looked for, whitespace-normalised, in each hunk the branch (or `--head`) makes to the product's SPEC
files, read with its paragraph, where they cover a line the hunk adds, and otherwise in the hunks made to the one file
the passage's own block names, such as a contract; and the review and verify prompts of a task that declares a `brief`
sign-off ask for it."""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, verify
from tests.helpers import Product
from tests.test_toolkit import GIT_ENV, ToolkitFixture, git

PASSAGE = ("A task whose brief sign-off is due and not recorded is passed over the same way, and stderr names "
           "the missing sign-off, so the runner takes the next task it can claim.")

SCOPE = """## Scope

- **In:**
  - `docs/spec/x.md` §1. CURRENT (at `abc1234`): none; a new sentence. PROPOSED:
    > A task whose brief sign-off is due and not recorded is passed over the same way, and stderr names the
    > missing sign-off, so the runner takes the next task it can claim.
  - the code, which reads each `PROPOSED:` block in the Scope.
- **Out:** nothing else.
"""

TASK = """---
task_id: 0001-signed
title: Signed text
status: pending
depends_on: []
spec_refs: ["S1"]
sign_off: brief
created: 2026-09-30
updated: 2026-09-30
---

# Task: 0001-signed

## Intent

Something true for the user.

## Context (not checked)

- background, with PROPOSED: outside the Scope
  > a quote outside the Scope is no signed passage

{scope}
## dod_checks

- id: `cmd-01`
  story: As an operator, I run it.
  steps:
    1. run
  expect: exit 0

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
"""


CONTRACT = '{\n  "description": "An older description.",\n  "type": "object"\n}\n'


def contract_scope(above: str, current: str = "CURRENT:\n> An older description.\n") -> str:
    """A Scope signing PASSAGE, on one line, in a block whose CURRENT is `current` and whose nearest line above
    is `above`."""
    return f"## Scope\n\n- **In:** the code.\n\n{above}\n\n{current}\nPROPOSED:\n> {PASSAGE}\n\n- **Out:** nothing.\n"


class SpecText(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("QUEUE_ROOT", None)
        self.p.task("0001-signed", body=TASK.format(scope=SCOPE))
        self.p.write("docs/spec/x.md", "# Spec\n\n## 1. Rules\n\nAn older rule.\n")
        self.p.write("notes.md", "# Notes\n")
        self.p.write("contracts/x.schema.json", CONTRACT)
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", ".")
        git(self.p.root, "commit", "-q", "-m", "init")
        git(self.p.root, "checkout", "-q", "-b", "task/0001-signed")

    def change(self, rel: str, add: str) -> None:
        path = self.p.root / rel
        path.write_text(path.read_text() + add)
        git(self.p.root, "commit", "-q", "-am", f"change {rel}")

    def run_cmd(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "spec-text", *args])
        body = out.getvalue()
        return code, (json.loads(body) if body.strip().startswith("{") else None), err.getvalue()

    def test_the_signed_passage_added_with_other_wrapping_passes(self):
        self.change("docs/spec/x.md", "\nA task whose brief sign-off is due and not recorded is passed over the\n"
                                      "same way,   and stderr names the missing sign-off, so the runner takes\n"
                                      "  the next task it can claim. And a sentence the PR adds after it.\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["missing"], [])
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_a_passage_split_across_two_hunks_is_not_found(self):
        scope = SCOPE.replace(SCOPE[SCOPE.index("    > A task"):SCOPE.index("  - the code")], "    > Alpha one. Beta two.\n")
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "the passage")
        git(self.p.root, "checkout", "-q", "main")
        self.change("docs/spec/x.md", "\nGamma.\n")  # on the base: unchanged on the branch
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")
        x = self.p.root / "docs/spec/x.md"
        x.write_text(x.read_text().replace("Gamma.\n", "Alpha one.\nGamma.\nBeta two.\n"))
        git(self.p.root, "commit", "-q", "-am", "two halves")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn("Alpha one. Beta two.", err)

    def signs(self, passage: str) -> None:
        """The task signs `passage` alone, committed on the branch."""
        scope = SCOPE.replace(SCOPE[SCOPE.index("    > A task"):SCOPE.index("  - the code")], f"    > {passage}\n")
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "the passage")

    def on_base(self, text: str) -> None:
        """The SPEC file reads `text` on the base, merged into the branch, so the branch changes nothing yet."""
        git(self.p.root, "checkout", "-q", "main")
        (self.p.root / "docs/spec/x.md").write_text(text)
        git(self.p.root, "commit", "-q", "-am", "the base's SPEC")
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")

    def edit(self, old: str, new: str) -> None:
        x = self.p.root / "docs/spec/x.md"
        x.write_text(x.read_text().replace(old, new, 1))
        git(self.p.root, "commit", "-q", "-am", "the edit")

    def test_a_passage_whose_head_sits_on_an_unchanged_line_is_found(self):
        self.signs("Alpha one two three four five.")
        self.on_base("# Spec\n\n## 1. Rules\n\nAlpha one two\nthree four.\n\nAn older rule.\n")
        self.edit("three four.\n", "three four five.\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_a_passage_whose_tail_sits_on_an_unchanged_line_is_found(self):
        self.signs("Alpha one two three four five.")
        self.on_base("# Spec\n\nAlpha one\nthree four five.\n")
        self.edit("Alpha one\n", "Alpha one two\n")
        self.assertEqual(self.run_cmd("0001-signed", "--base", "main")[0], 0)

    def test_a_passage_wholly_in_unchanged_lines_is_not_found(self):
        self.signs("Alpha one two three four.")
        self.on_base("# Spec\n\nAlpha one two\nthree four.\n\nAn older rule.\n")
        self.edit("An older rule.\n", "An older rule, reworded.\n")  # elsewhere: another paragraph
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn("Alpha one two three four.", err)
        self.edit("three four.\n", "three four.\nA sentence the branch adds.\n")  # in its paragraph, after it
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertIn("Alpha one two three four.", err)

    def test_a_passage_across_a_blank_line_is_not_found(self):
        self.signs("Alpha one two. Three four.")
        self.on_base("# Spec\n\nAlpha one two.\n")
        self.change("docs/spec/x.md", "\nThree four.\n")  # the hunk adds the blank line and the second half
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertIn("Alpha one two. Three four.", err)

    def test_a_passage_across_an_unchanged_blank_line_is_not_found(self):
        self.signs("Alpha one two. Three four.")
        self.on_base("# Spec\n\nAlpha one two.\n\n")
        self.change("docs/spec/x.md", "Three four.\n")  # the blank line before it unchanged
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertIn("Alpha one two. Three four.", err)

    def test_an_added_line_beginning_plus_plus_is_content(self):
        self.change("docs/spec/x.md", "\n++ counter\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_a_changed_word_fails_naming_the_passage(self):
        self.change("docs/spec/x.md", "\n" + PASSAGE.replace("next task", "first task") + "\n")
        code, body, err = self.run_cmd("0001", "--base", "main")
        self.assertEqual(code, 1)
        lines = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text().splitlines()
        at = f"docs/delivery/tasks/0001-signed.md:{lines.index(SCOPE.splitlines()[3]) + 1}"  # the PROPOSED: line
        self.assertEqual(body["missing"], [at])
        self.assertIn(at, err)
        self.assertIn(PASSAGE, err)

    def test_a_task_with_no_proposed_block_exits_2(self):
        scope = "## Scope\n\n- **In:** the code, which reads each `PROPOSED:` block. PROPOSED: \"inline, unquoted\"\n"
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "no block")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 2)
        self.assertIn("no PROPOSED: block", err)

    def test_only_lines_the_branch_adds_to_a_spec_file_count(self):
        self.change("notes.md", "\n" + PASSAGE + "\n")  # not under spec_paths
        self.assertEqual(self.run_cmd("0001-signed", "--base", "main")[0], 1)
        git(self.p.root, "checkout", "-q", "main")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")  # on the base: the branch adds nothing
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")
        self.assertEqual(self.run_cmd("0001-signed", "--base", "main")[0], 1)

    def test_each_passage_is_judged_and_only_the_missing_one_named(self):
        second = ("\n  - `docs/spec/x.md` §1. CURRENT: \"An older rule.\" PROPOSED:\n"
                  "    > An older rule, now with a knob.\n")
        self.p.task("0001-signed", body=TASK.format(scope=SCOPE.replace("\n- **Out:**", second + "- **Out:**")))
        git(self.p.root, "commit", "-q", "-am", "two passages")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1)
        self.assertEqual(len(body["passages"]), 2)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn("An older rule, now with a knob.", err)
        self.assertNotIn(PASSAGE, err)

    def test_the_base_defaults_to_the_integration_branch_on_the_remote(self):
        origin = self.p.root.parent / (self.p.root.name + "-origin.git")
        git(self.p.root.parent, "init", "-q", "--bare", "-b", "main", str(origin))
        self.addCleanup(lambda: __import__("shutil").rmtree(origin, ignore_errors=True))
        git(self.p.root, "remote", "add", "origin", str(origin))
        git(self.p.root, "push", "-q", "origin", "main")
        git(self.p.root, "fetch", "-q", "origin")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed")
        self.assertEqual((code, body["base"]), (0, "origin/main"), err)

    def test_a_base_that_does_not_resolve_or_an_unknown_task_exits_2(self):
        code, _, err = self.run_cmd("0001-signed", "--base", "no-such-ref")
        self.assertEqual(code, 2)
        self.assertIn("no-such-ref", err)
        self.assertEqual(self.run_cmd("0099-none", "--base", "main")[0], 2)

    def test_the_passages_are_read_from_the_scope_only(self):
        text = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text()
        self.assertEqual([p for _, p in verify.signed_passages(text)], [PASSAGE])

    def rule_changes(self, scope: str, section: str) -> None:
        """The task carries `scope` as its Scope and `section` after it, committed on the branch."""
        self.p.task("0001-signed", body=TASK.format(scope=scope + "\n" + section))
        git(self.p.root, "commit", "-q", "-am", "the task")

    def line_of(self, needle: str, nth: int = 0) -> str:
        lines = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text().splitlines()
        at = [k for k, line in enumerate(lines) if needle in line][nth]
        return f"docs/delivery/tasks/0001-signed.md:{at + 1}"

    def test_a_passage_under_a_rule_changes_heading_is_checked(self):
        bare = "## Scope\n\n- **In:** the code.\n"
        self.rule_changes(bare, "## Rule changes (signed at tasking)\n\n- §1, the new rule. PROPOSED:\n"
                                f"  > {PASSAGE}\n")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["line"], r["found_in"]) for r in body["passages"]],
                         [(self.line_of("the new rule. PROPOSED:"), ["docs/spec/x.md"])])

    def test_a_passage_in_both_places_is_judged_once(self):
        other = "An older rule, now with a knob."
        self.rule_changes(SCOPE, "## Rule changes\n\n- §1. PROPOSED:\n"
                                 f"  > {PASSAGE}\n- §1, the second. PROPOSED:\n  > {other}\n")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual([r["line"] for r in body["passages"]],
                         [self.line_of(SCOPE.splitlines()[3]), self.line_of("the second. PROPOSED:")])
        self.assertEqual(body["missing"], [self.line_of("the second. PROPOSED:")])
        self.assertIn(other, err)

    def test_a_passage_in_both_places_is_listed_at_its_first_line_in_the_file(self):
        text = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text()
        text = text.replace("## Scope\n", f"## Rule changes, signed\n\nPROPOSED:\n> {PASSAGE}\n\n## Scope\n", 1)
        at = text.splitlines().index("## Rule changes, signed") + 3
        self.assertEqual(verify.signed_passages(text), [(at, PASSAGE)])

    def test_only_a_heading_that_begins_rule_changes_is_read_besides_the_scope(self):
        text = (self.p.root / "docs/delivery/tasks/0001-signed.md").read_text()
        text = text.replace("## dod_checks\n", "## Proposed rule changes\n\nPROPOSED:\n> Not signed here.\n\n"
                                               "## Rule changesets\n\nPROPOSED:\n> Nor here.\n\n## dod_checks\n", 1)
        self.assertEqual([p for _, p in verify.signed_passages(text)], [PASSAGE])

    def test_a_task_with_a_rule_changes_section_and_no_block_names_both_places(self):
        self.rule_changes("## Scope\n\n- **In:** the code.\n", "## Rule changes\n\n- none.\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 2)
        self.assertIn("Scope", err)
        self.assertIn("Rule changes", err)

    def test_head_checks_a_past_commit_s_spec_change(self):
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        a = git(self.p.root, "rev-parse", "HEAD").strip()
        self.edit(PASSAGE, PASSAGE.replace("next task", "first task"))
        code, body, err = self.run_cmd("0001-signed", "--base", f"{a}^", "--head", a)
        self.assertEqual((code, body["head"]), (0, a), err)
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])
        code, body, err = self.run_cmd("0001-signed", "--base", f"{a}^")
        self.assertEqual((code, body["head"]), (1, "HEAD"), err)
        self.assertIn(PASSAGE, err)
        code, body, err = self.run_cmd("0001-signed", "--base", f"{a}^", "--head", "no-such-ref")
        self.assertEqual(code, 2)
        self.assertIn("no-such-ref", err)
        self.assertNotIn(f"{a}^", err)  # the head is refused, not the base

    def test_head_s_diff_is_the_one_read_not_the_checkout_s(self):
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        a = git(self.p.root, "rev-parse", "HEAD").strip()
        self.edit("\n" + PASSAGE + "\n", "")  # HEAD takes the passage out again: its diff adds nothing
        self.assertEqual(self.run_cmd("0001-signed", "--base", f"{a}^")[0], 1)
        code, body, err = self.run_cmd("0001-signed", "--base", f"{a}^", "--head", a)
        self.assertEqual(code, 0, err)

    def scope(self, scope: str) -> None:
        """The task carries `scope` as its Scope, committed on the branch."""
        self.p.task("0001-signed", body=TASK.format(scope=scope))
        git(self.p.root, "commit", "-q", "-am", "the scope")

    def describe(self, rel: str, text: str = PASSAGE) -> None:
        """The branch writes `rel` as the contract with `text` as its description, committed."""
        self.p.write(rel, CONTRACT.replace("An older description.", text))
        git(self.p.root, "add", rel)
        git(self.p.root, "commit", "-q", "-m", f"describe {rel}")

    def test_a_passage_landing_in_the_contract_its_block_names_is_found_there(self):
        for scope in (contract_scope("`contracts/x.schema.json`, the top-level `description`."),
                      contract_scope("The contract's description.",
                                     "CURRENT (`contracts/x.schema.json` at `abc1234`):\n> An older description.\n")):
            with self.subTest(scope=scope):
                git(self.p.root, "reset", "-q", "--hard", "main")
                self.scope(scope)
                self.describe("contracts/x.schema.json")
                code, body, err = self.run_cmd("0001-signed", "--base", "main")
                self.assertEqual(code, 0, err)
                self.assertEqual([r["found_in"] for r in body["passages"]], [["contracts/x.schema.json"]])

    def test_a_passage_landing_in_a_changed_file_its_block_does_not_name_is_not_found(self):
        self.scope(contract_scope("`contracts/x.schema.json`, the top-level `description`."))
        self.describe("contracts/x.schema.json", "A newer description.")
        self.describe("contracts/y.schema.json")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)
        self.assertIn(PASSAGE, err)

    def test_a_named_file_under_tests_is_never_searched(self):
        self.scope(contract_scope("`tests/fixture.json`, its `description`."))
        self.describe("tests/fixture.json")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)

    def test_a_passage_the_diff_adds_only_to_the_task_file_is_not_found(self):
        rel = str(self.p.task("0001-signed", body=TASK.format(scope="")).relative_to(self.p.root))
        self.scope(contract_scope(f"`{rel}`, this task."))  # the branch adds the passage, on one line, to the task file
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)

    def test_a_passage_only_in_unchanged_lines_of_the_named_file_is_not_found(self):
        git(self.p.root, "checkout", "-q", "main")
        self.describe("contracts/x.schema.json")  # on the base
        git(self.p.root, "checkout", "-q", "task/0001-signed")
        git(self.p.root, "merge", "-q", "--no-edit", "main")
        self.scope(contract_scope("`contracts/x.schema.json`, the top-level `description`."))
        x = self.p.root / "contracts/x.schema.json"
        x.write_text(x.read_text().replace('"object"', '"array"'))  # the branch changes the file elsewhere
        git(self.p.root, "commit", "-q", "-am", "another line")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)

    def test_a_path_inside_quoted_current_text_names_nothing(self):
        for current in ("CURRENT:\n> The `contracts/x.schema.json` description: an older description.\n",
                        "CURRENT: \"the `contracts/x.schema.json` description\".\n"):
            with self.subTest(current=current):
                git(self.p.root, "reset", "-q", "--hard", "main")
                self.scope(contract_scope("The contract's description.", current))
                self.describe("contracts/x.schema.json")
                code, body, err = self.run_cmd("0001-signed", "--base", "main")
                self.assertEqual(code, 1, err)
                self.assertEqual(len(body["missing"]), 1)

    def test_a_locator_naming_a_glob_names_nothing(self):
        self.scope(contract_scope("The contracts' descriptions.",
                                  "CURRENT (`contracts/*.json` at `abc1234`):\n> An older description.\n"))
        self.describe("contracts/x.schema.json")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 1, err)
        self.assertEqual(len(body["missing"]), 1)

    def test_a_passage_found_in_the_spec_is_not_looked_for_in_its_named_file(self):
        self.scope(contract_scope("`contracts/x.schema.json`, the top-level `description`."))
        self.describe("contracts/x.schema.json")
        self.change("docs/spec/x.md", "\n" + PASSAGE + "\n")
        code, body, err = self.run_cmd("0001-signed", "--base", "main")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["found_in"] for r in body["passages"]], [["docs/spec/x.md"]])

    def test_the_file_a_block_names(self):
        def names(scope: str) -> list:
            return [f for _, _, f in verify.signed_blocks(TASK.format(scope=scope))]
        self.assertEqual(names(contract_scope("`contracts/x.schema.json`, its `description`.")),
                         ["contracts/x.schema.json"])
        self.assertEqual(names(contract_scope("x", "CURRENT (`contracts/x.schema.json` at `abc1234`):\n> Older.\n")),
                         ["contracts/x.schema.json"])
        self.assertEqual(names(contract_scope("`notes.md`, a file at the root.")), [None])  # no `/`
        self.assertEqual(names(contract_scope("See `contracts/x.schema.json`.")), [None])  # not opening the line
        inline = ("## Scope\n\n`contracts/x.schema.json`, its `description`.\n"
                  "- CURRENT (`contracts/y.schema.json` at `abc1234`): \"older\". PROPOSED:\n> Newer.\n")
        self.assertEqual(names(inline), ["contracts/y.schema.json"])  # the locator, not the line above
        # A second block with no CURRENT of its own takes neither the first's CURRENT nor its file.
        self.assertEqual(names(inline + "\nPROPOSED:\n> A second passage.\n"), ["contracts/y.schema.json", None])
        second = contract_scope("`contracts/x.schema.json`, its `description`.").replace(
            "\n\n- **Out:**", "\nPROPOSED:\n> A second passage.\n\n- **Out:**")
        self.assertEqual(names(second), ["contracts/x.schema.json", None])


class Prompts(ToolkitFixture, unittest.TestCase):
    """The review and verify prompts ask for the check only on a task that declares a `brief` sign-off."""

    def prompts(self) -> tuple[str, str]:
        self.ccp("tasks", "claim", "0002")
        for phase in ("review", "verify"):
            code, _, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", "a" * 40)
            self.assertEqual(code, 0, out + err)
        d = self.q / "prompts/0002-second"
        return (d / "review-prompt.md").read_text(), (d / "verify-prompt.md").read_text()

    def test_a_brief_task_s_review_and_verify_prompts_run_the_check(self):
        p = self.main / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("depends_on:", "sign_off: brief\ndepends_on:", 1))
        git(self.main, "commit", "-q", "-am", "0002 needs a brief sign-off")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, out, err = self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed")
        self.assertEqual(code, 0, out + err)
        for text in self.prompts():
            self.assertIn("verify spec-text 0002-second --base origin/main", text)

    def test_other_tasks_prompts_do_not(self):
        for text in self.prompts():
            self.assertNotIn("spec-text", text)


if __name__ == "__main__":
    unittest.main()
