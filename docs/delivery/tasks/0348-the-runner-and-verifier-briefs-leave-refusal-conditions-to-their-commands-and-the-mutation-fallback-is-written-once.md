---
task_id: 0348-the-runner-and-verifier-briefs-leave-refusal-conditions-to-their-commands-and-the-mutation-fallback-is-written-once
title: The runner brief leaves the review-skip conditions and the second behind_tip refusal to the commands and the SPEC; the verifier definition leaves verify record's refusals and §15.6 rule 3 to them; the hand-mutation fallback is written once, in _common.md; the review prompt drops its pre-rule line; the verify prompt carries the two sentences 0343 cut
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S15"]
rule_refs: ["E13"]
review_refs: ["ar-20261125T184522Z-c248#F03", "ar-20261125T184522Z-c248#F04", "ar-20261125T184522Z-c248#F05", "ar-20261125T184522Z-c248#F12"]
review_point: R38
paths: ["plugin/agents/delivery-runner.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-implementer.md", "templates/prompts/verify.md", "templates/prompts/review.md", "tests/test_prompt_tools.py"]
clashes_with: ["0191-the-grace-release-ends"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0348-the-runner-and-verifier-briefs-leave-refusal-conditions-to-their-commands-and-the-mutation-fallback-is-written-once

## Intent

A runner and a verifier load briefs that say what to do on each outcome and leave the conditions behind a refusal to
the command's message and the § it cites, so a change to a rule edits one place. A worker's prompt gives the
hand-mutation fallback once. A reviewer is not told how to judge reports that no longer exist. A verifier is told
again to say whether its verdict relies on a check it did not run, and to cite a ruling the runner passed it by
message.

## Context (not checked)

Findings F03, F04, F05 and F12 of architect pass `ar-20261125T184522Z-c248`
(`docs/delivery/reviews/ar-20261125T184522Z-c248.md`), under house rule E13, and one follow-up of 0343 the lead
passed to that pass: 0343 cut two verifier sentences no template gives (say in `findings` whether the verdict relies
on a `ran: false` check; cite the id of a ruling the lead gave the runner by message).

Measured at `05cb00e2`:

- **F03.** `grep -c -e 'skip_review' -e 'verify.provers' plugin/agents/delivery-runner.md`: 3, all in step 7
  (**Review.**), which restates `ccp prompt verify`'s and `ccp verify record`'s review-skip conditions;
  `grep -c 'behind_tip_ignore' plugin/agents/delivery-runner.md`: 2, the refusal written in step 8 (**Verify.**,
  "with one runner too") and again in *Several runners*, item 4 (**Merge only from the tip.**).
- **F04.** `git grep -c 'wt create --kind mut' -- plugin/agents templates/prompts`: 5 files, 1 each
  (`templates/prompts/_common.md`, `templates/prompts/verify.md`, and the implementer, reviewer and verifier
  definitions). `_common.md`'s copy is in no section tag, so the verify prompt renders it beside `verify.md`'s.
  §13.1's fourth rule names `ccp suite run --run` or `ccp mutate`, never the fallback; the Known intentional note
  on §13.1's four rules covers the evidence rule, not this sentence.
- **F05.** `grep -c -e 'adr.strict' -e 'rests_on' plugin/agents/delivery-verifier.md`: 2, the first two bullets. The
  first restates `ccp verify record`'s refusals; the second restates §15.6 rule 3. Correction to the report: the
  second is the clean integration merge, which `verify.md` does not render (its `resolved_verify` part is the
  conflicted merge after a resolution review), so the bullet becomes a pointer to §15.6 rule 3, not a cut.
- **F12.** `grep -c 'A report from before this rule' templates/prompts/review.md`: 1. `ccp report` requires the
  `## Tests for new behaviour` list (`ccp/report.py`, `TESTS_HEAD`), and no task is in flight in this queue.
- **0343.** `grep -c -e 'whether your verdict relies on' -e 'by message' templates/prompts/verify.md`: 0.
- `tests/test_prompt_tools.py`
  (`PromptsNameTheTools.test_with_no_mutate_command_a_seat_breaks_code_in_a_mutation_worktree_it_removes`) pins
  `verify.md`'s copy (`--sha {A}` and `suite run --run {run_id}` with `--lane part` in the verify prompt) and the
  three definitions' copies (`ccp wt create --kind mut`, `ccp wt remove <name>`).

**Ruled.**

- **F03, step 7.** "`ccp prompt verify <task_id> --pr <n> --head <new sha>`: it opens the verify when the fix needs
  no new review (a clean review's MINOR and NIT fix under `verify.skip_review_after_clean`, or a fix
  `verify.skip_review` or a review prover proves), and refuses (exit 4), naming why, when it needs one:" becomes
  "`ccp prompt verify <task_id> --pr <n> --head <new sha>`: it opens the verify when the fix needs no new review
  (SPEC §15.2) and refuses (exit 4), naming why, when it needs one:". The sentence from "`ccp` enforces it:" to "(a
  verify reject since sends it back to review)." is cut whole; "Only on the lead's or the operator's word: …" stays.
- **F03, item 4.** In *Several runners*, item 4, the sentence "`ccp prompt verify` refuses (exit 4, `behind_tip`,
  nothing opened) a head that lacks a tip commit changing more than the task log and the product's
  `merge.behind_tip_ignore` paths: the head is stale, so merge the tip in and verify the new head." is cut; step 8's
  copy, which says it holds with one runner too, stays. The rest of the brief stays: its other exit-code lines name
  the action each code calls for.
- **F04.** The fallback stays in `_common.md` alone. `verify.md`'s sentence beginning "Where the product declares no
  `mutate.command`" is cut (the bullet before it ends with the `--revert` sentence). In each of the three
  definitions, the evidence bullet ends at its `(SPEC §14.1, §20.6).`; the sentences after it, from "Where the
  product declares no `mutate.command`" to "in your own worktree." (the reviewer's: "in your own checkout."), are
  cut. `test_with_no_mutate_command_a_seat_breaks_code_in_a_mutation_worktree_it_removes` drops its two
  verify-only assertions and its loop over the definitions; its loops over the rendered verify and implement
  prompts' fallbacks stay.
- **F05.** The verifier definition's first bullet becomes "- On a PR that is not a task's, `task_id` is exactly
  `pr-<n>`." Its second becomes "- A head that moved only by an integration merge (the runner's note says so) is
  not a reject case: SPEC §15.6 rule 3 says what you run, record and show in `findings` (`ccp spec show 15.6`)."
- **F12.** `review.md`'s line "A report from before this rule has no list; judge its tests from the diff alone." is
  cut.
- **0343.** `verify.md` gains, after its line beginning "Each check's evidence follows SPEC §15.4": "Say in
  `findings` whether your verdict relies on a check you record `ran: false`." and "A ruling the lead gave the runner
  by message has an id when the runner passes it to you: cite that id in the check's `ruling`."
- No other test expectation changes; no SPEC text changes (`git grep -n 'skip_review_after_clean\|behind_tip_ignore'
  docs/spec` at `05cb00e2` finds the rules in §15.2, §15.6 and §16.5, which stay).

## Scope

- **In:** `plugin/agents/delivery-runner.md` (step 7 and *Several runners* item 4); `plugin/agents/delivery-verifier.md`
  (the first two bullets and the evidence bullet); `plugin/agents/delivery-reviewer.md` and
  `plugin/agents/delivery-implementer.md` (the evidence bullet); `templates/prompts/verify.md`;
  `templates/prompts/review.md`; `tests/test_prompt_tools.py`.
- **Out:** `templates/prompts/_common.md` (its fallback is the one kept); the runner brief's other steps; the SPEC.

## dod_checks

- id: `doc-01`
  story: As a runner, my brief names the command and the § for a review skip and gives the behind_tip refusal once.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c -e 'skip_review' -e 'verify.provers' plugin/agents/delivery-runner.md`.
    2. Run `grep -c 'behind_tip_ignore' plugin/agents/delivery-runner.md`.
  expect: step 1 prints `0` (grep's exit 1, no match); step 2 prints `1`.
  dry run (`05cb00e2`): step 1 printed `3`; step 2 printed `2`.
- id: `doc-02`
  story: As a worker, my prompt gives the hand-mutation fallback once and my definition leaves it to the prompt.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -c 'wt create --kind mut' -- plugin/agents templates/prompts`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_tools.PromptsNameTheTools.test_with_no_mutate_command_a_seat_breaks_code_in_a_mutation_worktree_it_removes tests.test_prompt_tools`.
  expect: step 1 prints exactly one line, `templates/prompts/_common.md:1`; step 2 exits 0.
  dry run (`05cb00e2`): step 1 printed five lines (`plugin/agents/delivery-implementer.md:1`, `plugin/agents/delivery-reviewer.md:1`, `plugin/agents/delivery-verifier.md:1`, `templates/prompts/_common.md:1`, `templates/prompts/verify.md:1`); step 2 exit 0.
- id: `doc-03`
  story: As a verifier, my definition leaves verify record's refusals and §15.6 rule 3 to the command and the SPEC.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c -e 'adr.strict' -e 'rests_on' plugin/agents/delivery-verifier.md`.
    2. Run `grep -c '15.6 rule 3' plugin/agents/delivery-verifier.md`.
  expect: step 1 prints `0` (grep's exit 1, no match); step 2 prints `1`.
  dry run (`05cb00e2`): step 1 printed `2`; step 2 printed `1`.
- id: `doc-04`
  story: As a reviewer, my prompt carries no line for reports from before the tests list.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'A report from before this rule' templates/prompts/review.md`.
  expect: prints `0` (grep's exit 1, no match).
  dry run (`05cb00e2`): printed `1`.
- id: `doc-05`
  story: As a verifier, my prompt tells me to say whether my verdict relies on a check not run and to cite a ruling passed by message.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -n 'whether your verdict relies on' templates/prompts/verify.md`.
    2. Run `grep -n 'by message' templates/prompts/verify.md`.
  expect: each step prints at least one line and exits 0.
  dry run (`05cb00e2`): steps 1 and 2 printed nothing (exit 1 each).

## Implementation notes

- Edits as ruled: runner step 7 and *Several runners* item 4; verifier first two bullets and evidence bullet; reviewer and
  implementer evidence bullets; `verify.md` fallback sentence cut, its preceding bullet now ends with `;` where the
  fallback's `;` ended the item; `review.md` pre-rule line cut; `verify.md` gains the two 0343 sentences.
- `tests/test_prompt_tools.py`: the two verify-only assertions and the definitions loop dropped as ruled; a new test pins the
  two restored `verify.md` sentences.
- Two other test modules the cuts necessarily break are updated in the same PR: `tests/test_worker_efficiency.py`
  (its `assertIn("before this rule has no list", review)` is now `assertNotIn`) and `tests/test_suite.py`
  (`test_the_mutation_runs_name_the_part_roles_lane` looked for `--lane subset` in `verify.md`'s fallback item; it now takes
  the item holding "is a recorded one", where `_common.md` carries the fallback and its `--lane {{part_lane}}`).

## Verification notes
