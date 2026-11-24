---
task_id: 0317-the-review-prompt-routes-mutation-checks-through-mutate-prompt-tests-pin-tokens-and-checks-pin-tests-by-id
title: The review prompt gives one route for a mutation check (ccp mutate, from the shared part), the prompt-text tests pin one token per instruction and E4's figure drops with them, and the writing-tasks skill has a check pin a test by its id so the run's exit code decides and a removal check miss the text that replaces it
status: pending
kind: feature
depends_on: ["0316-e4-counts-every-long-literal-assert-and-names-its-count-when-over"]
spec_refs: ["S20", "S14"]
rule_refs: ["E4", "E13", "E21"]
review_refs: ["ar-20261123T230912Z-197a#F02", "ar-20261123T230912Z-197a#F04", "ar-20261123T230912Z-197a#F05"]
review_point: R32
paths: ["templates/prompts/review.md", "tests/test_prompt_tools.py", "tests/test_worker_efficiency.py", "tests/test_full_lane_prompt.py", "docs/delivery/plane.json", "plugin/skills/writing-tasks/SKILL.md", "tests/test_suite.py"]
clashes_with: ["0191-the-grace-release-ends", "0307-seats-are-told-how-to-run-one-check-and-the-spec-names-the-language-pack-s-test-command", "0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log", "0314-task-writers-leave-a-line-between-a-revert-check-s-hunks-and-an-implementer-s-questions-go-in-its-report"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0317-the-review-prompt-routes-mutation-checks-through-mutate-prompt-tests-pin-tokens-and-checks-pin-tests-by-id

## Intent

A reviewer reads one route for a mutation check: `ccp mutate`, as the prompts' shared part gives it, and no
longer also `ccp suite run` on the part lane. A template edit stops breaking the prompt-text tests: they pin
the token each instruction turns on (a command, a flag, a key, a §), not its sentence, and E4's figure drops by
what they shed. A task writer is told to pin a named test by giving its id to the recorded run's command, so the
run's exit code decides whether it ran and passed, with no grep of the runner's text for a person to read.

## Context (not checked)

Findings F02 (its second half), F04 and F05 of architect pass `ar-20261123T230912Z-197a`
(`docs/delivery/reviews/ar-20261123T230912Z-197a.md`), and E21 as that triage amended it.

Measured at `bb102371`:

- **Two routes (F04).** `templates/prompts/review.md` says "and any mutation run through `{{ccp}} suite run` with
  `--lane {{part_lane}}{{^review_cache}} --cold{{/review_cache}}`" (the line starting "Run the tests the PR touches")
  and, in the resolution branch, "Run any test you need, and any mutation run, through `{{ccp}} suite run` with
  `--lane {{part_lane}}`.", while `templates/prompts/_common.md` (the line starting "A test run you cite as
  evidence") gives `{{ccp}} mutate --run {{run_id}} --test <test id> --mutant …` wherever the product declares
  `mutate.command` or its pack has a per-test runner, and a mutation worktree otherwise.
  `git grep -n 'mutation run' -- templates/prompts`: 3 lines, all in review.md.
  Ruled: the first line drops its clause ", and any mutation run through … `--cold{{/review_cache}}`", keeping
  "; you need not run the full suite."; the resolution line becomes "Run any test you need through `{{ccp}} suite
  run` with `--lane {{part_lane}}`." The line "Run uncached any check of test order (any-order or reverse-order
  runs) and every mutation run." stays: §15.3 (`docs/spec/02-delivery.md`, "and mutation runs stay uncached") says
  the same. The test is `test_the_review_prompt_routes_mutation_checks_through_mutate_only` in
  `tests/test_prompt_tools.py` (class `PromptsNameTheTools`): the rendered review prompt, in a full review and in a
  resolution review, holds `mutate --run` and no line holding both `mutation` and `suite run`.
  `test_the_mutation_runs_name_the_part_roles_lane` in `tests/test_suite.py` (class `LaneRoles`) reads the review
  prompt's "and any mutation run" line for `--lane subset --cold`, so it breaks with that clause. Ruled: its review half
  goes (the `("review", "and any mutation run", …)` row of its loop); its verify half stays unchanged. The review prompt
  names one mutation route, `ccp mutate`.
- **Prose pins (F02).** The AST count 0316 puts in E4 (every assert call with a string argument of 40 or more
  characters), run as a probe over `tests/test_worker_efficiency.py`, `tests/test_prompt_tools.py` and
  `tests/test_full_lane_prompt.py`: 34. A plain-literal grep, `LC_ALL=C grep -cE 'assert[A-Za-z]*\(f?"[^"]{40,}'` on each:
  18, 10 and 7. Ruled: each such assertion pins the token its instruction turns on (one or several per test);
  no test is dropped, and each still fails when its instruction is cut from the template. E4's figure (the
  literal in its count part) is lowered to the count at this build's head.
- **Pinning a test (F05).** `plugin/skills/writing-tasks/SKILL.md`, the bullet "A check that runs tests runs them
  through `ccp suite run`", says the check "pins a named test by grepping that run's log". The 030x briefs then add a
  second step, `grep … -e '^OK' <the log step 1 names>`, whose result a person reads, and `unittest -v` prints a
  test's docstring on a second line, which broke one such grep (0304's friction). A probe at `bb102371`:
  `python3 -B -m unittest tests.test_suite_run_affected.Nope.test_x`: exit 1 (a named test that does not exist fails
  the run), so naming the ids in the command makes its exit code the answer.
  Ruled: the bullet's clause becomes "and pins a named test by giving its id (`<module>.<class>.<test>`) to that
  command, so the run's exit code says it ran and passed; never a grep of the runner's text, nor a bare test
  runner's output." E21 (`docs/ENGINEERING.md`) says the same since the triage.
- **Removal checks.** Two briefs this week (0296, 0303) had a check that text was removed whose pattern also matched
  the text that replaced it. Ruled: the skill's bullet "An absence check first shows its pattern finding a known
  positive" gains the sentence "A check that text was removed uses a pattern that the text replacing it does not
  match."
- **No SPEC change.** `git grep -n -e 'mutation run' -e grepping -- docs/spec` at `bb102371`: the two lines are §2.4's
  verifier `Edit` note and §15.3's cache line, neither changed. The prompt follows §20.6 as it stands.

## Scope

- **In:** `templates/prompts/review.md` (the two lines above); `tests/test_prompt_tools.py`,
  `tests/test_worker_efficiency.py` and `tests/test_full_lane_prompt.py` (their long-literal assertions as tokens, and
  the new test); `tests/test_suite.py` (the review half of `test_the_mutation_runs_name_the_part_roles_lane`);
  `docs/delivery/plane.json` (E4's figure only); `plugin/skills/writing-tasks/SKILL.md` (the two bullets above).
- No SPEC change (Context, *No SPEC change*).
- **Out:** `templates/prompts/_common.md` (0307 is changing it); the other prompt tests; any other template line.

## dod_checks

- id: `doc-01`
  story: As a reviewer, my prompt names one route for a mutation check.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -c 'mutation run' -- templates/prompts/review.md; git grep -n 'mutation run through' -- templates/prompts`.
  expect: step 1 prints `templates/prompts/review.md:1` (the uncached line), then nothing from the second grep.
  dry run (`bb102371`): printed `templates/prompts/review.md:3`, then the line starting "Run the tests the PR touches".
- id: `code-01`
  story: As a plane developer, a test holds the review prompt's mutation route, and it bites.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_tools.PromptsNameTheTools.test_the_review_prompt_routes_mutation_checks_through_mutate_only`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_prompt_tools.PromptsNameTheTools.test_the_review_prompt_routes_mutation_checks_through_mutate_only --mutant 'templates/prompts/review.md:Run any test you need through=>Run any test you need, and any mutation run, through'`.
  expect: step 1 exits 0; step 2 prints the mutant `killed`.
  dry run: n/a — the test and the new line are the build's.
- id: `code-02`
  story: As a template writer, the prompt-text tests pin tokens, and E4's figure holds the lower count.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `part=$(python3 -B -c "import json;print([p for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4' for p in c['cmd'].split(' && ') if 'long-literal' in p][0])"); bash -c "$part tests/test_worker_efficiency.py tests/test_prompt_tools.py tests/test_full_lane_prompt.py"; echo "exit $?"`.
    2. Run `echo "$part" | grep -oE 'figure = [0-9]+'`, then the same with `$part` taken from `git show $(git merge-base origin/main HEAD):docs/delivery/plane.json` in place of the file.
  expect: step 1 prints `exit 0` and no other line (the three modules hold no counted assertion); step 2's figure at the head is at least 30 below the merge base's.
  dry run: n/a — the count part is 0316's.
- id: `code-03`
  story: As a plane developer, the converted prompt tests still pass and still bite.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_prompt_tools tests.test_worker_efficiency tests.test_full_lane_prompt tests.test_suite.LaneRoles.test_the_mutation_runs_name_the_part_roles_lane`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_prompt_tools --mutant 'templates/prompts/review.md:suite run --affected --since origin/{{integration}}...=>suite run --since origin/{{integration}}...'`.
  expect: step 1 exits 0; step 2 prints the mutant `killed`.
  dry run: n/a — needs an open run; the old text is found once in `templates/prompts/review.md` at `bb102371` (`grep -c 'suite run --affected --since origin/{{integration}}...'`: 1).
- id: `doc-02`
  story: As a task writer, the skill tells me to pin a test by its id, so the run's exit code decides.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -c 'grepping that run' -- plugin/skills/writing-tasks/SKILL.md; tr '\n' ' ' < plugin/skills/writing-tasks/SKILL.md | grep -o "giving its id[^;]*exit code" | head -1; tr '\n' ' ' < plugin/skills/writing-tasks/SKILL.md | grep -c "the text replacing it does not"`.
  expect: the first grep prints nothing (exit 1); the second prints one fragment starting `giving its id` and ending `exit code`; the third prints `1`.
  dry run (`bb102371`): printed `plugin/skills/writing-tasks/SKILL.md:1`, then nothing, then `0`.

## Implementation notes

- `templates/prompts/review.md`: the full review's affected-run line drops its mutation clause, and the resolution
  line reads "Run any test you need through `{{ccp}} suite run` with `--lane {{part_lane}}`."; the uncached line stays.
- New test `test_the_review_prompt_routes_mutation_checks_through_mutate_only`: the full review through `ccp prompt`,
  the resolution review as its template and `_common.md` render together (opening one needs a conflicted merge). It
  looks for lines holding `mutation run` and `suite run`, not `mutation` alone: `_common.md`'s evidence line ("a
  mutation check included, is a recorded one: the `suite run` command above, or … `mutate`") holds `mutation` and
  `suite run` in every rendered prompt, and `_common.md` is out of scope.
- The 35 long-literal assertions of the three prompt-text modules (18, 9 and 8; the Context's 34 was measured before
  later merges) pin a token each, or several; `--lane <part_lane> --cold` in `test_worker_efficiency` now pins
  `--cold` on the affected run, its one remaining place. E4's figure: 483 to 448, the count at this head.
- `tests/test_suite.py`: the review row of `test_the_mutation_runs_name_the_part_roles_lane` goes; the verify row
  stays as it was.
- `plugin/skills/writing-tasks/SKILL.md`: the two bullets, worded as ruled.

## Verification notes
