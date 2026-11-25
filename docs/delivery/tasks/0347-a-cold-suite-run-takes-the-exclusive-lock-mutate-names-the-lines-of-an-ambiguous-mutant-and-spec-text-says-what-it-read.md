---
task_id: 0347-a-cold-suite-run-takes-the-exclusive-lock-mutate-names-the-lines-of-an-ambiguous-mutant-and-spec-text-says-what-it-read
title: A suite run given --cold takes the exclusive lane's lock whatever its tree or cache probe says, with its signed §16.6 sentence; ccp mutate's refusal of an old text found more than once names the lines it is on; verify spec-text's help, not-found line and a base with no merge base say what it read
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15", "S16", "S20"]
review_refs: ["ar-20261125T184522Z-c248#F11"]
review_point: R38
paths: ["ccp/suite.py", "ccp/mutate.py", "ccp/verify.py", "ccp/cli.py", "docs/spec/02-delivery.md", "tests/test_parallel_lanes.py", "tests/test_suite_cache_probe.py", "tests/test_mutate_refusals.py", "tests/test_verify_spec_text.py"]
clashes_with: ["0191-the-grace-release-ends", "0350-the-architect-stub-is-ccp-named-and-fenced-the-report-is-checked-once-by-its-contract-and-the-envvars-and-adr-docs-say-what-is-there"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0347-a-cold-suite-run-takes-the-exclusive-lock-mutate-names-the-lines-of-an-ambiguous-mutant-and-spec-text-says-what-it-read

## Intent

A worker who asks for a cold run of an exclusive lane waits for the lock like any full-cost run, instead of skipping
it on a cache answer the run will not use. A worker whose mutant's old text is in the file more than once is told
the lines it is on, so the next try names one place without reading the file again. An implementer running
`ccp verify spec-text` reads in its help, its not-found line and its refusal of an unrelated base what it compared.

## Context (not checked)

The operator's ruling on question 2 of architect pass `ar-20261125T094654Z-c8a0` (0341's follow-up: does `--cold`
disable both exclusive-lane lock skips?), answered on 2026-11-25 through the lead:

> Always lock (Recommended)

That is option (a), whose words were: "`--cold` disables both skips: a signed §16.6 sentence, tasked at the next
triage ("A run given `--cold` takes the lock as any other.")". The operator approved that sentence as written; it
is this task's one PROPOSED passage, and the lead records the brief sign-off with these words.

Also finding F11 of architect pass `ar-20261125T184522Z-c248` (`docs/delivery/reviews/ar-20261125T184522Z-c248.md`):
three friction notes in one window came from placing a mutant (0341's old text not unique, 0345's multi-line JSON,
0342's `--revert` range). The line-anchored mutant form it also proposes changes §20.6's signed grammar and is
deferred in `docs/ROADMAP.md`; this task takes the refusal's line numbers, which need no SPEC change. And three
follow-ups of 0346 the lead passed to that pass: `verify spec-text --head`'s help still says the default is `HEAD`,
the not-found line reads "in the text working tree changes since …", and no test covers a base with no merge base.

Measured at `05cb00e2`:

- **--cold.** `"def _green_from"` (`ccp/suite.py`) returns the green run unless `_cold_task`; the probe runs under
  `"if probe and not _cold_task(cfg, started):"`. Neither reads `a.cold`, which only sets `cold_env`
  (`"cold_env = for_child({COLD_VAR: \"1\"}) if getattr(a, \"cold\", False) else {}"`). `git grep -n -- '--cold'
  docs/spec` at `05cb00e2`: §14.2 (lines 735, 741), §14.4 (852) and §15.2 (1070); none names the lock.
- **mutate.** `"def _once"` (`ccp/mutate.py`) raises `f"{label}: the old text is in {where} {n} times; a mutant names
  one place"`. `tests.test_mutate_refusals.TextMutants.test_old_text_absent_or_ambiguous` and
  `tests.test_mutate_refusals.Together.test_one_part_a_patch_sharing_a_file_or_an_old_text_an_earlier_part_removed`
  pin `"0 times"`, `"2 times"` and `"as the earlier parts on it leave it 0 times"`, which the ruled message keeps.
  `git grep -n 'a mutant names one place' docs/spec docs/cli` at `05cb00e2`: nothing, so no SPEC text changes.
- **spec-text.** `"p.add_argument(\"--head\", help=\"the commit whose SPEC change is checked (default: HEAD)\")"`
  (`ccp/cli.py`); the not-found line in `"def main"` (`ccp/verify.py`) prints `in the text {body['head']} changes since
  {body['base']}`, which with no `--head` reads "in the text working tree changes since origin/main"; with no `--head`
  and a base sharing no merge base with `HEAD`, `spec_hunks` returns None and the error is `git diff from the merge
  base of <base> and HEAD failed: is <base> a ref in <root>?`, untested. §15.2's "a base the diff cannot be read
  against" (exit 2) already covers it.

**Ruled.**

- **--cold.** A run given `--cold` neither skips the lock on a green tree nor runs the lane's cache probe: `_green_from`
  is not consulted and the probe is not run when `a.cold` is set, as for a run bound to a cold-gate task. Its
  `started` row has no `lane_skipped`. New tests
  `tests.test_parallel_lanes.Lanes.test_a_cold_run_takes_the_lock_whatever_its_tree` (a passing run of the tree is
  recorded, the lane is held, the same run given `--cold --wait 0` exits `suite.BUSY_EXIT`) and
  `tests.test_suite_cache_probe.CacheProbe.test_a_cold_run_takes_the_lock_whatever_the_probe_says` (a probe that
  exits 0, the lane held, a run given `--cold --wait 0` exits `suite.BUSY_EXIT` and `probed()` is empty).
- **mutate.** When `old` is in the text two or more times, `_once`'s message adds the line of each occurrence (the
  1-based line its first byte is on, in the text as checked: the file, or what the earlier parts leave), after the
  count: `the old text is in calc.py 2 times, at lines 2 and 6; a mutant names one place` (`at lines 2, 6 and 9`
  for three). A count of 0 is unchanged. New test
  `tests.test_mutate_refusals.TextMutants.test_an_ambiguous_old_text_names_the_lines_it_is_on` (`CALC`'s `return`
  is on lines 2 and 6).
- **spec-text.** The `--head` help becomes "the commit whose SPEC change is checked (default: the working tree,
  against its merge base with the base)". With no `--head`, the not-found line reads `… in the text the working tree
  changes since its merge base with <base>: …`; with `--head`, as now. New tests
  `tests.test_verify_spec_text.SpecText.test_with_no_head_the_not_found_line_names_the_working_tree` and
  `tests.test_verify_spec_text.SpecText.test_with_no_head_a_base_with_no_merge_base_exits_2` (an orphan branch as the
  base: exit 2, the base named on stderr).
- No other test expectation changes.

## Scope

- **In:** `ccp/suite.py` (the green-tree and probe conditions); `ccp/mutate.py` (`_once`); `ccp/verify.py` (`main`'s
  not-found line); `ccp/cli.py` (the `--head` help); `tests/test_parallel_lanes.py`; `tests/test_suite_cache_probe.py`;
  `tests/test_mutate_refusals.py`; `tests/test_verify_spec_text.py`; the SPEC, signed:

  CURRENT (`docs/spec/02-delivery.md` at `05cb00e2`), §16.6:
  > Any other exit, a timeout, or a probe that cannot start leaves the run taking the lock as before, and a run bound to a task whose gate is cold takes the lock whatever the probe says. The verifier still runs its gate (§15.3).

  PROPOSED:
  > Any other exit, a timeout, or a probe that cannot start leaves the run
  > taking the lock as before, and a run bound to a task whose gate is cold takes the lock whatever the
  > probe says. A run given `--cold` takes the lock as any other. The verifier still runs its gate (§15.3).

  Nothing retired: the sentence is added.
- **Out:** the line-anchored mutant form (`docs/ROADMAP.md`); `docs/cli/` (no call syntax changes); the cache probe's
  other rules.

## dod_checks

- id: `spec-01`
  story: As the operator, §16.6 says what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0347`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`05cb00e2`, with this brief): exit 1, the PROPOSED passage not found.
- id: `code-01`
  story: As a worker, a cold run of an exclusive lane waits for the lock whatever its tree or the probe says.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_parallel_lanes.Lanes.test_a_cold_run_takes_the_lock_whatever_its_tree tests.test_suite_cache_probe.CacheProbe.test_a_cold_run_takes_the_lock_whatever_the_probe_says tests.test_parallel_lanes tests.test_suite_cache_probe`.
  expect: exit 0.
  dry run (`05cb00e2`): exit 1 (`AttributeError: type object 'Lanes' has no attribute 'test_a_cold_run_takes_the_lock_whatever_its_tree'`).
- id: `code-02`
  story: As a worker, a refused mutant tells me the lines its old text is on.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mutate_refusals.TextMutants.test_an_ambiguous_old_text_names_the_lines_it_is_on tests.test_mutate_refusals`.
  expect: exit 0.
  dry run (`05cb00e2`): exit 1 (`AttributeError: type object 'TextMutants' has no attribute 'test_an_ambiguous_old_text_names_the_lines_it_is_on'`).
- id: `code-03`
  story: As an implementer, spec-text says it read the working tree and refuses a base with no shared history.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_verify_spec_text.SpecText.test_with_no_head_the_not_found_line_names_the_working_tree tests.test_verify_spec_text.SpecText.test_with_no_head_a_base_with_no_merge_base_exits_2 tests.test_verify_spec_text`.
    2. Run `CCP_DEV=1 ./bin/ccp verify spec-text --help | grep -c 'default: HEAD'`.
  expect: step 1 exits 0; step 2 prints `0` (grep's exit 1, no match).
  dry run (`05cb00e2`): step 1 exit 1 (`AttributeError: type object 'SpecText' has no attribute 'test_with_no_head_the_not_found_line_names_the_working_tree'`); step 2 printed `1`.

## Implementation notes

## Verification notes
