---
task_id: 0353-prompt-tests-pin-rendered-values-ccp-prompt-render-prints-a-template-and-the-lanes-line-names-the-module-form
title: The prompt tests stop asserting removed sentences are absent and find an instruction by the value it renders, not a sentence around it; ccp prompt render prints a phase's prompt with placeholder values, writing nothing, so a template change is compared by two renders (§31.1); the Lanes line names the language pack's test-module form
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S14", "S21"]
rule_refs: ["E4", "E18"]
review_refs: ["ar-20261125T202431Z-1a86#F01", "ar-20261125T202431Z-1a86#F02", "ar-20261125T202431Z-1a86#F06", "ar-20261122T055103Z-11aa#F08"]
review_point: R39
paths: ["ccp/prompt.py", "ccp/cli.py", "ccp/doclang/__init__.py", "ccp/doclang/python.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_suite.py", "tests/test_full_lane_prompt.py", "tests/render_helpers.py", "tests/test_prompt_render.py"]
clashes_with: ["0191-the-grace-release-ends", "0354-mutate-names-each-failing-test-s-kind-and-caps-its-line-list-and-the-cold-run-tests-assert-what-they-mean", "0355-headless-launches-build-their-argv-in-one-place-prompt-audits-are-written-through-one-function-and-a-rule-change-with-no-rule-is-reported-once"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0353-prompt-tests-pin-rendered-values-ccp-prompt-render-prints-a-template-and-the-lanes-line-names-the-module-form

## Intent

A maintainer who rewords or removes a prompt sentence breaks no test that only remembered the old words, and proves
the rest of the prompt unchanged by comparing `ccp prompt render` at the base and at the head. A worker reading the
Lanes line sees how its language names a test module (`tests.test_x` for Python), so its first subset run is not
refused.

## Context (not checked)

Findings F01, F02 and F06 of architect pass `ar-20261125T202431Z-1a86`
(`docs/delivery/reviews/ar-20261125T202431Z-1a86.md`). F02 is the roadmap's deferral of `ar-20261122T055103Z-11aa`
F08, whose trigger ("the next task that refactors a prompt template builds it") never fired:
`git log --oneline a8ad7319..becb6417 -- templates/prompts | wc -l` at `becb6417`: 15 commits changed a template since
that triage, none built it. F06's other half (`ccp mutate` naming a module's test ids) is deferred in
`docs/ROADMAP.md`. House rule E4 as amended by triage `ar-20261125T202431Z-1a86`: "a test finds a rendered
instruction by the value it renders, never by a sentence around it" and no test "asserts that a retired name or a
removed sentence is absent".

Measured at `becb6417`:

- **Tombstones.** `git grep -nF -e 'Remove it when you are done' -e 'git worktree add --detach' -e 'depend on the paths' -e 'a cheap failure shows in seconds' -e 'before this rule has no list' -e 'Rebase onto' -e 'put the file back' -e 'plane propose`), not the PR' -e 'dependent-modules' -- tests/test_worker_efficiency.py tests/test_prompt_tools.py | wc -l`
  at `becb6417`: 13 lines, each an `assertNotIn` of a sentence a template no longer has.
- **Sentence locators.** `tests/test_prompt_tools.py`'s `FALLBACK` regex finds the mutation-worktree fallback by its
  opening words; `tests/test_suite.py`'s `"def rule_item"` finds a list item by a marker phrase, used by
  `tests.test_suite.ReportCrossCheck.test_every_worker_prompt_names_the_recorded_route_for_evidence`
  (`"cite as evidence"`) and `tests.test_suite.LaneRoles.test_the_mutation_runs_name_the_part_roles_lane`
  (`"is a recorded one"`). `tests.test_prompt_tools.PromptsNameTheTools.test_the_verify_prompt_asks_for_the_ran_false_reliance_and_the_ruling_id`
  (0348) asserts three verify-prompt sentences whole.
- **Render.** `git grep -n 'render-only\|--render\b\|--no-audit' -- ccp docs/cli | wc -l` at `becb6417`: 0.
  `tests/render_helpers.py`'s `"def phase_values"` already builds every template name as a `<name>` placeholder;
  `"def render_phase"` (`ccp/prompt.py`) joins a phase's template with `_gate.md`, and `"def build"` appends
  `_common.md`.
- **Lanes line.** `"def suite_lanes"` (`ccp/prompt.py`) renders a declared part argv as
  `` `<ccp> suite run --lane <lane> -- <argv> <module> …` (module names, not test ids) ``; the Python pack's
  `"TEST_COMMAND ="` comment says it runs modules "by dotted name". `tests/test_full_lane_prompt.py`'s `PART_ARGV`
  pins that line.

**Ruled.**

- **Tombstones.** The 13 lines go: `tests/test_worker_efficiency.py`'s `assertNotIn` of "Remove it when you are
  done", "git worktree add --detach", "depend on the paths" (2), "a cheap failure shows in seconds" (2), "before this
  rule has no list" and "Rebase onto"; `tests/test_prompt_tools.py`'s of "put the file back" (2), "dependent-modules"
  and "plane propose`), not the PR", and the "dependent-modules command" entry of
  `test_no_template_sends_a_worker_to_a_mutation_worktree_or_a_discovery_command`'s loop. The other assertions of
  those tests stay.
- **Locators.** `FALLBACK` and `outside_the_fallback` go. The fallback is found by the command it renders: each
  render names `wt create --kind mut` once (`text.count(...) == 1`), and the line that holds it holds
  `--task 0002-second --sha `, `wt remove <name>` and `` `--lane part` ``; across `templates/prompts/*.md`,
  `--kind mut` is on one line of `_common.md` only. `rule_item` goes: the evidence test finds the line holding
  `mutate --run 0002-second/<phase> --test <test id>` and asserts `QUEUE_ROOT=<q> ` on it (its "a bare test runner"
  assertion goes); the lane-role test finds the line holding `wt create --kind mut` and asserts `` `--lane subset` ``
  on it. The 0348 test asserts one line of the verify render holds both `` `findings` `` and `` `ran: false` ``, and
  one holds both `` `ruling` `` and `message`.
- **Render.** `ccp prompt render <phase> [--on <name>]…` (a new `phase` choice beside `env`, its phase in the `task`
  positional, `--on` repeatable) prints to stdout what `build` writes before the end line: `render_phase(phase, v)`
  then `_common.md`, joined as `build` joins them (one shared function), with `v` from `prompt.placeholder_values(on)`
  (new): every name the templates use as a value is `<name>`, every name they use as a section is `""` unless `--on`
  names it, then `<name>`. It needs no task, claim, `QUEUE_ROOT` or binding, writes nothing (no prompt file, audit,
  run, event or board refresh) and exits 0; an unknown phase, or an `--on` naming no template section, exits 2.
  `tests/render_helpers.py`'s `phase_values` starts from `prompt.placeholder_values()` and keeps its overrides. New
  module `tests/test_prompt_render.py` (new). `docs/cli/02-delivery.md` gains its row.
- **Lanes line.** `ccp/doclang`'s `Pack` gains `module_example` (default `""`; Python `tests.test_x`). A declared part
  argv renders `` `<ccp> suite run --lane <lane> -- <argv> <module> …` (test modules, such as `tests.test_x`, not
  test ids) `` with an example, and `(test modules, not test ids)` without. New test
  `tests.test_full_lane_prompt.DeclaredPartLane.test_the_part_argv_names_the_packs_module_form`; `PART_ARGV` follows.
- No other test expectation changes.

## Scope

- **In:** `ccp/prompt.py`; `ccp/cli.py` (the `prompt` parser and `cmd_prompt`); `ccp/doclang/__init__.py`;
  `ccp/doclang/python.py`; `docs/cli/02-delivery.md`; `tests/test_prompt_tools.py`; `tests/test_worker_efficiency.py`;
  `tests/test_suite.py`; `tests/test_full_lane_prompt.py`; `tests/render_helpers.py`; `tests/test_prompt_render.py`
  (new); the SPEC, a description of this task's own feature (§31.1), no sign-off:

  CURRENT (`docs/spec/02-delivery.md` at `becb6417`), §13.2:
  > `ccp prompt` needs a claimed task, checks for a pending run before writing anything, and refuses a template naming anything it does not set. `ccp prompt verify <id>` renders the same text on every run apart from the fields it fills in (such as paths, the run id and round, the head, the runner's note) and the end token, which differs on every run (below).

  PROPOSED:
  > `ccp prompt` needs a claimed task, checks for a pending run before writing anything, and refuses a
  > template naming anything it does not set. `ccp prompt verify <id>` renders the same text on every
  > run apart from the fields it fills in (such as paths, the run id and round, the head, the runner's
  > note) and the end token, which differs on every run (below). `ccp prompt render <phase> [--on <name>]…`
  > prints a phase's prompt as `ccp prompt` joins its parts, every value a `<name>` placeholder and every
  > section off unless `--on` names it, so two checkouts' renders show what a template change changed; it
  > needs no task, claim or queue and writes nothing.

  Nothing retired: the sentence is added.
- **Out:** `templates/prompts/` (no template text changes); the sentence assertions of other test modules (the
  roadmap's `ar-20261120T234012Z-27eb` F10); `ccp mutate`'s refusal naming test ids (`docs/ROADMAP.md`).

## dod_checks

- id: `test-01`
  story: As a maintainer, no prompt test asserts that a removed sentence is absent.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nF -e 'Remove it when you are done' -e 'git worktree add --detach' -e 'depend on the paths' -e 'a cheap failure shows in seconds' -e 'before this rule has no list' -e 'Rebase onto' -e 'put the file back' -e 'plane propose`), not the PR' -e 'dependent-modules' -- tests/test_worker_efficiency.py tests/test_prompt_tools.py`.
  expect: prints nothing (git grep's exit 1).
  dry run (`becb6417`, run by hand: the pattern's backtick keeps `tasks dry-run` from running it): printed 13 lines.
- id: `test-02`
  story: As a maintainer, the prompt tests find an instruction by its rendered value and still pass.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -nF -e 'FALLBACK' -e 'def rule_item' -e 'whether your verdict relies on' -e 'A ruling the lead gave the runner' -- tests`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_tools tests.test_worker_efficiency tests.test_suite.ReportCrossCheck tests.test_suite.LaneRoles`.
  expect: step 1 prints nothing (git grep's exit 1); step 2 exits 0.
  dry run (`becb6417`): step 1 printed 7 lines; step 2 exit 0.
- id: `cmd-01`
  story: As a maintainer changing a template, I print a phase's prompt with placeholders and nothing is written.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp prompt render implement | grep -F 'mutate --run <run_id> --test <test id>'`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_render tests.test_cli_reference`.
  expect: step 1 prints one line (grep's exit 0); step 2 exits 0.
  dry run (`becb6417`): step 1 printed nothing (exit 1; ccp's `invalid choice: 'render'`); step 2 exit 1 (`tests.test_prompt_render` does not exist).
- id: `code-01`
  story: As a worker, the Lanes line shows how my language names a test module.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_full_lane_prompt.DeclaredPartLane.test_the_part_argv_names_the_packs_module_form tests.test_full_lane_prompt`.
  expect: exit 0.
  dry run (`becb6417`): exit 1 (`AttributeError: type object 'DeclaredPartLane' has no attribute 'test_the_part_argv_names_the_packs_module_form'`).
- id: `spec-01`
  story: As a reader of §13.2, it says how to print a prompt without opening a run.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0353`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`becb6417`, with this brief): exit 1, the PROPOSED passage not found.

## Implementation notes

## Verification notes
