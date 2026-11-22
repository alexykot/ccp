---
task_id: 0305-a-task-s-merge-is-read-one-way-and-close-s-merge-outcome-refusals-are-judged-on-plain-values
title: Health, the plan and close read a task's merge only in the §10.7 form, from one pattern in ccp/refs.py, and close's three refusals on the PR host's merge outcome are judged by plain functions
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S27"]
rule_refs: ["E23", "E15"]
review_refs: ["ar-20261122T162238Z-9098#F01", "ar-20261122T162238Z-9098#F08"]
review_point: R28
clashes_with: ["0191-the-grace-release-ends", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0297-a-sign-off-wait-ends-on-the-lead-s-sign-off-and-briefs-name-the-lead-s-actor", "0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured", "0308-module-docstrings-and-queue-docs-stop-restating-the-spec"]
paths: ["ccp/refs.py", "ccp/health.py", "ccp/lifecycle.py", "docs/delivery/plane.json", "tests/test_refs.py", "tests/test_health.py", "tests/test_tasks_close.py", "tests/test_close_merge_outcome.py"]
adopt: "a product whose task merges predate §10.7's `Task <NNNN>: ` subject loses those merges' rows from ccp health and calibration; old calibration rows age out and nothing is migrated"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0305-a-task-s-merge-is-read-one-way-and-close-s-merge-outcome-refusals-are-judged-on-plain-values

## Intent

A lead's PR that only edits a task's file never counts as that task's merge. `ccp health`, the plan and
board rows, `ccp tasks orphans` and close's lease check all read a task's merge as §10.7 rule 1 defines
it (a merge of a `task/<NNNN>-…` branch, or a subject starting `Task <NNNN>: `), from one pattern in
`ccp/refs.py`, so a pending task shows no merge sha or PR, and a merged task's row counts its own merge
and its own lines. Close's refusals on what the PR host did with the merge (refused it, has not finished
it, merged it with no merge commit) are each tested on plain values, and the module that drives a whole
close keeps one of them for the wiring.

## Context (not checked)

From architect pass `ar-20261122T162238Z-9098`, F01 (`incoherence`) and F08 (`test-cost`); the record is in
`docs/delivery/reviews/`. Measured at `0f44fb3` (origin/main) unless a line says otherwise.

- **Two rules.** `ccp/refs.py` `"def task_merge_subject_re"` is
  `rf"^(?:task\s+)?(\d{{{self.task_width}}})(?!\d)"` with `re.I`; `ccp/health.py` `"def _written_task_re"` is
  `rf"^Task (\d{{{width}}}): "`. `"def merges"` uses the first unless `written=True`; `"def uncovered"`
  (orphans) passes `written=True`, and `ccp/lifecycle.py` `"def _own_commit"` calls `health._written_task_re`.
  `ccp/plan.py` `"def task_rows"` reads `health.merges(cfg, tasks)` for its `pr` and `merge_sha` fallbacks.
- **What the loose rule counts.** A probe at `0f44fb3` (`python3 -B -c` comparing `health.merges(cfg)` with `health.merges(cfg, written=True)` on this repo): 291 merges against 289; the two extra are `4d5755b` ("Task 0297 takes 0275's follow-up on implement.md (#349)", a task-file edit; 0297 is pending) and `14ba2a4` ("Task 0069 supersedes 0067: … (#57)", a second merge for 0069). `env -u QUEUE_ROOT CCP_DEV=1 ./bin/ccp health show --json` at `0f44fb3` gives 0297 `merge_sha` `4d5755b` and 0069 `merges` 2.
- **The drift reading was not inflated by it.** The architect pass that found F01 ran on the drift trigger
  (1.52 against 1.5). 0297's row has no wall time (no lease), so `"def trend"`, which reads only rows with an
  `active_s`, leaves it out; the review record shows the arithmetic.
- **Tests that pin the loose form:** `tests/test_refs.py`
  (`test_a_merge_subject_and_a_task_branch_name_the_task_number`: `"0042 sf store (#7)"` and `"TASK  0042-sf"`
  read as 0042; `test_merge_subject_and_branch_patterns_read_the_width`: `"task 00042 x"`), and
  `tests/test_health.py`'s fixture, whose `"0003: spike passed (#4)"` is 0003's merge.
  `git grep -nE '"(task )?[0-9]{4}[ :-][^"]*\(#[0-9]+\)' -- tests` at `0f44fb3`: 4 lines, that fixture line, the
  `tests/test_refs.py` line above, and two in `tests/test_orphans.py`, which already expects those commits listed
  as uncovered.
- **Close's host outcome.** `ccp/lifecycle.py`, in close after `prhost.merge`: `if not r.ok: … raise
  QueueError(f"{prhost.label(cfg)} did not merge PR {pr}: {r.message}{hint}", 1)`, then after `prhost.confirm`,
  `if facts.state != "merged": raise …`, then `if not merge: raise QueueError(f"PR {pr} is merged but … names no
  merge commit", 1)`. `tests/test_tasks_close.py` tests each through `self._to_approved_pr()` and a whole
  `ccp tasks close` with `prhost` mocked (`test_a_merge_the_host_has_not_completed_names_the_hosts_own_state_word`,
  `test_a_merge_the_host_refuses_names_the_host`, `test_a_merged_pr_without_a_merge_commit_names_the_host`), and
  `CloseReadsAMalformedRunnerCount` runs two whole closes for a count `tests/test_rotation.py`'s
  `test_a_tasks_done_that_is_no_number_reads_as_zero_with_a_warning` and
  `test_one_runners_tasks_done_that_is_no_number_reads_as_zero_too` hold on plain values.
- **Older merge subjects.** A product whose early task merges carry a subject without the `Task ` prefix (`NNNN: title (#n)`, before §10.7's form) has them read by today's loose pattern and not by §10.7's: `git log --first-parent --format=%s <integration>` on one bound product, counted with the loose pattern and not the written one, gives about 40 such merges. The lead's ruling: accept the drop. Those rows leave health and calibration; nothing is migrated, and old calibration rows age out (the `adopt` line says so).
- **No SPEC change.** §10.7 rule 1 already defines a task's merge; §27.1's source is "the merges that name a task" (`git grep -n 'merges that name a task' -- docs/spec` at `0f44fb3`: 1 line, `docs/spec/04-observability.md`). The refusal texts do not change.
- **Other tasks.** 0293 and 0301 (claimed) and 0191 (pending) change other code in `ccp/lifecycle.py`, 0297
  (pending) `sign_off_wait` in `ccp/health.py`, 0293 E27's command in `docs/delivery/plane.json`, and 0308 (pending)
  `lifecycle.py`'s module docstring and E24's figure. Different logic; recorded as clashes since the files meet.

### Rulings for the build (the lead's)

- `ccp/refs.py`: `task_merge_subject_re` is `rf"^Task (\d{{{self.task_width}}}): "`, case-sensitive, its docstring naming §10.7 rule 1. `ccp/health.py`'s `_written_task_re` and `merges`' `written` parameter go; `merges`, `uncovered` and `lifecycle._own_commit` use `ids.task_merge_subject_re`. `ccp/plan.py` does not change.
- `docs/delivery/plane.json` `architect.checks` `E23`'s command gains
  `&& ! git grep -nF 'rf"^Task ' -- ccp scripts ':(exclude)ccp/refs.py'` (house rule E23, amended by the triage).
- `tests/test_refs.py`: `"Task 0042: sf store"` reads 0042; `"0042 sf store (#7)"`, `"TASK  0042-sf"` and
  `"Task 0042 takes a follow-up (#9)"` read none; the width test uses `"Task 00042: x"` (00042) and
  `"Task 0042: x"` (none). `tests/test_health.py`'s fixture subject becomes `"Task 0003: spike passed (#4)"`, and
  it gains a later commit `"Task 0003 takes a follow-up (#5)"` that `test_merges_name_tasks` does not list.
- `ccp/lifecycle.py` gains two plain functions, each returning the refusal text or None:
  `def merge_refused(label: str, pr: str, tid: str, head: str, caught: bool, result: prhost.MergeResult) -> str | None`
  (the `not r.ok` text with its conflict and catch-up hints) and
  `def not_merged(label: str, pr: str, tid: str, facts: prhost.PrFacts, merged_now: bool) -> str | None`
  (the state text, only when `merged_now`, then the no-merge-commit text under the line
  `if not facts.merge_commit:`, the only line of the module holding that text). Close raises `QueueError(text, 1)`
  on each, at the points it raises today.
- `tests/test_close_merge_outcome.py` (new) tests both on plain `MergeResult` and `PrFacts` values: the three
  refusals, the conflict hint, and None for a merged PR with a merge commit. `tests/test_tasks_close.py` keeps
  `test_a_merge_the_host_refuses_names_the_host` and drops the other two host tests and
  `CloseReadsAMalformedRunnerCount`.

## Scope

- **In:** `ccp/refs.py` (`task_merge_subject_re`), `ccp/health.py` (`_written_task_re`, `merges`, `uncovered`),
  `ccp/lifecycle.py` (`_own_commit`, close's host-outcome refusals), `docs/delivery/plane.json` (`architect.checks`
  `E23`), `tests/test_refs.py`, `tests/test_health.py`, `tests/test_tasks_close.py`,
  `tests/test_close_merge_outcome.py` (new).
- No SPEC change (measured in Context).
- **Out:** `ccp/plan.py` (it reads `health.merges`); `task_branch_re`; the reconcile subject (`reconcile_re`);
  the refusal texts; `tests/test_orphans.py`.

## dod_checks

- id: `cmd-01`
  story: As the lead, a task-file edit PR is no task's merge in health or the plan.
  setup: A checkout of the PR head (any seat), `QUEUE_ROOT` unset.
  steps:
    1. Run `env -u QUEUE_ROOT CCP_DEV=1 ./bin/ccp health show --json | python3 -c 'import json,sys; print(sorted(r["merge_sha"] for r in json.load(sys.stdin)["tasks"] if r["merge_sha"] in ("4d5755b", "14ba2a4")))'`.
  expect: prints `[]`.
  dry run (`0f44fb3`): printed `['4d5755b']` (0297's row; 0069's row shows its last merge, `39f7944`, with `merges` 2, `14ba2a4` folded into it).
- id: `code-01`
  story: As a plane developer, the one merge pattern reads only the written form.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_refs tests.test_health`.
    2. Run `grep -e merge_subject -e merges_name_tasks -e '^OK' <the log step 1 names>`.
    3. Write a mutant file: first line `ccp/refs.py`, then `=== old`, the line `return re.compile(rf"^Task (\d{{{self.task_width}}}): ")`, then `=== new`, the line `return re.compile(rf"^(?:task\s+)?(\d{{{self.task_width}}})(?!\d)", re.I)`. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_refs --test tests.test_health --mutant-file <file>`.
  expect: step 1 exits 0; step 2 lists `test_a_merge_subject_and_a_task_branch_name_the_task_number`, `test_merge_subject_and_branch_patterns_read_the_width` and `test_merges_name_tasks`, each `ok`, then `OK`; step 3 prints the mutant `killed`.
  dry run (`0f44fb3`): step 1 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part, 7.9 s; 54 tests`; the three tests pass today on the loose form, so the mutant (today's pattern) is what they must reject after the change.
- id: `cfg-01`
  story: As the architect, no module but ccp/refs.py holds a task-merge pattern, and E23's check says so.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nF 'rf"^Task ' -- ccp scripts; git grep -n -e '_written_task_re' -e 'written=True' -- ccp scripts`.
    2. Run `python3 -c 'import json; print([c["cmd"] for c in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if c["id"] == "E23"][0])' | grep -cF "git grep -nF 'rf\"^Task '"`.
  expect: step 1 prints exactly one line, in `ccp/refs.py`; step 2 prints `1`.
  dry run (`0f44fb3`): step 1 printed 5 lines (`ccp/health.py` 4: the pattern, `def _written_task_re`, `merges`' switch, `uncovered`'s call; `ccp/lifecycle.py` 1); step 2 printed `0`.
- id: `code-02`
  story: As a plane developer, close's host-outcome refusals are tested on plain values and the whole-close copies go.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_close_merge_outcome tests.test_tasks_close`.
    2. Run `grep -c ' ok$' <the log step 1 names>; grep -e '^OK' <the log step 1 names>`.
    3. Run `git grep -n -e 'def test_a_merge_the_host_has_not_completed' -e 'def test_a_merged_pr_without_a_merge_commit' -e 'class CloseReadsAMalformedRunnerCount' -e 'def test_a_merge_the_host_refuses_names_the_host' -- tests/test_tasks_close.py`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_close_merge_outcome --mutant 'ccp/lifecycle.py:if not facts.merge_commit:=>if False:'`.
  expect: step 1 exits 0; step 2's `OK` line is printed and `tests.test_close_merge_outcome` holds at least four tests (the three refusals and the None); step 3 prints exactly one line, `test_a_merge_the_host_refuses_names_the_host`; step 4 prints the mutant `killed`.
  dry run (`0f44fb3`): step 3 printed 4 lines (the three host tests and the class); steps 1, 2 and 4: n/a — the module and `not_merged` are new.

## Implementation notes

## Verification notes
