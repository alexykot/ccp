---
task_id: 0166-catch-up-before-review
title: The implementer catches up with the tip before review, and ccp prompt review refuses a head whose merge of the tip would conflict
status: pending
kind: feature
depends_on: ["0162-git-merge-helper"]
spec_refs: ["S13", "S15", "S16"]
adr_refs: ["0042 D3"]
review_point: R11
paths: ["ccp/prompt.py", "templates/prompts/implement.md", "templates/prompts/fix.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-runner.md", "docs/spec/02-delivery.md", "tests/test_review_tip_gate.py", "tests/test_prompt_pr_body.py", "tests/test_run_abandon.py"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0166-catch-up-before-review
## Intent

Most textual conflicts between tasks running together are resolved by the implementer before review,
at the cost of one merge and one test run, instead of after a full review and verify. An implement or
fix round ends by merging the integration tip into its branch, resolving any conflict and running its
tests on the merged code, then pushes the head it reports. `ccp prompt review` refuses a head that is
behind the tip only when merging the tip into it would conflict, so a reviewer never judges a head
whose conflict is still to come, while a head behind by a clean merge goes to review and a moving tip
does not send the implementer back again and again.

## Context (not checked)

- ADR-0042 D3, accepted 2026-11-19; shape `sh-20261119T072530Z-663f` F01 and F02.
- **F01, confirmed at `b9e58ce`: review refuses nothing for being behind.** `"def tip_gate"` in
  `ccp/prompt.py` returns at once for any phase but `verify` (`if phase != "verify": return []`), and §15.2
  holds no behind-tip refusal for review. So this task adds a new refusal at review; it relaxes nothing.
  Dry run at `b9e58ce` (the `tests.test_parallel_merging` fixture): a pushed task head that adds
  `feature.txt`, then a tip commit adding `feature.txt` with other content;
  `ccp prompt review 0002 --pr 7 --head <head>` exits 0 with no warnings, and `ccp prompt verify` on the same head exits 4 (`behind_tip`).
- **The implement prompt already merges the tip before the PR, but not last.** `templates/prompts/implement.md`
  at `b9e58ce` says "Before you open the PR, bring the branch up to origin/{{integration}} by merging it
  in" in its second paragraph, before the build, and says nothing of conflicts or of running the suite after
  the merge. `templates/prompts/fix.md` merges the tip first ("Fetch first; if origin/{{integration}}
  moved, merge it into the branch"), before the fix. D3 makes the merge the last step, with the tests run on
  the merged code. Neither §13.2 nor the implementer's brief mentions a catch-up today.
- Depends on 0162: its merge probe, `gitmerge.probe(root, ours, theirs)` in `ccp/gitmerge.py` (the tree and the conflicted files of merging one commit into another,
  with `git merge-tree`, which writes nothing) is what this gate calls. This task runs no merge analysis of its own:
  0162's `docs.checks` entry `merge-helper` fails on any of the three git subcommand names in `ccp/` outside
  `ccp/gitmerge.py`, so `ccp/prompt.py`'s code and docstring name none of them.
- `lifecycle.behind_tip` (fetches the tip, and the head when missing; raises `Unjudged`) is reused as is to
  decide whether the head is behind at all; the probe runs only when it is.
- Decided here:
  - The refusal's condition: the head is behind (`behind_tip` non-empty) and the probe's conflicted files
    include at least one outside the task log and `merge.behind_tip_ignore` (`lifecycle._tip_pathspec`'s set).
    A conflict only in those does not refuse: close's reconcile owns the task log.
  - Exit 4, nothing opened, as at verify. The message names up to 5 conflicted files and the round:
    `ccp prompt merge <id> --pr <n> --head <sha7>`.
  - A tip or head that cannot be fetched is a warning on the run (`behind_tip not checked: …`), and the review
    opens, as at verify. Review tests that pass a made-up `--head` now get that warning:
    `tests/test_prompt_pr_body.py` `test_a_body_naming_its_task_renders_the_prompt` asserts no warnings and
    changes to assert none but that one. `tests/test_run_abandon.py` `test_a_stopped_round_is_superseded_by_the_next`
    (lines 60-61 at `b9e58ce`) calls `ccp prompt review` with `--head` of 40 `a`s and asserts no warning in stderr
    or the body; it changes to assert no warning but the `behind_tip not checked` one.
  - The catch-up in the implement and fix prompts comes right before the round's full-lane run, so that run
    is on the merged code; the tip moving during the run starts no second catch-up. Conflicts resolved are
    listed in the report, file by file, as the merge prompt asks today.
- `plugin/agents/delivery-runner.md`'s Review step gets one sentence naming the new refusal and §15.2, per the
  shape's proposed E13 (name the command and the §, not the conditions). Task 0167 edits the same file's
  merge rules (F06), another section.
- The two SPEC passages below change §13.2's round kinds and §15.2's review rule: `sign_off: brief`.

## Scope

- **In:**
  - `ccp/prompt.py` `tip_gate`: also runs for `review`. Under the condition above it raises `QueueError(…, 4)`
    before anything is opened, naming the conflicted files (at most 5, then a count) and `ccp prompt merge`. A
    head behind by a clean merge, or not behind, opens the review. `Unjudged` returns the warning, as for verify.
    The merge probe is 0162's `gitmerge.probe`. The module docstring's review paragraph says the same in one sentence.
  - `templates/prompts/implement.md`: the second paragraph's "Before you open the PR, bring the branch up …"
    sentence moves into the "Before the PR" paragraph as its first step: fetch, `git merge origin/{{integration}}`
    into the branch (never rebase), resolve any conflict so both sides keep what they meant, list each in the
    report file by file, then run the checks that paragraph lists on the merged code.
  - `templates/prompts/fix.md`: "Fetch first; if origin/{{integration}} moved, merge it …" moves to the
    "Before you push" paragraph as its first step, worded as in `implement.md`.
  - `plugin/agents/delivery-implementer.md`: one bullet: the last step before you push the head you report from
    an implement or fix round is the catch-up merge (SPEC §13.2); never a rebase.
  - `plugin/agents/delivery-runner.md`, its Review step: one sentence: `ccp prompt review` also refuses (exit 4) a head
    whose merge of the tip would conflict (SPEC §15.2); `ccp prompt merge` first, then review the new head.
  - `docs/spec/02-delivery.md` §13.2: CURRENT (at `b9e58ce`): "needs such a report), `merge` and `ruling`, each with its own template and run name:" PROPOSED:
    > needs such a report), `merge` and `ruling`, each with its own template and run name. An `implement` or `fix` round's last step before it pushes the head it reports is a catch-up: it merges the integration tip into the task branch (§15.6 rule 2: never a rebase), resolves any conflict, listing each in its report, and runs its suite (§14) on the merged code. The other two:
  - `docs/spec/02-delivery.md` §15.2: CURRENT (at `b9e58ce`): "the task id; the runner repairs the body first. A commit landing while a review runs makes its head stale." PROPOSED:
    > the task id; the runner repairs the body first. It refuses (exit 4, nothing opened) a head behind the integration tip (`behind_tip`, §16.5 rule 4) only when merging the tip into it would conflict in a file outside the task log and `merge.behind_tip_ignore`, judged with `git merge-tree`, which writes nothing; the refusal names the conflicted files, and `ccp prompt merge` has the implementer resolve them. A head behind by a clean merge is reviewed, and a later catch-up handles it (§15.6 rule 3, §16.5 rule 4). A tip or head that cannot be fetched to judge is a warning on the run, and the review opens. A commit landing while a review runs makes its head stale.
  - `tests/test_review_tip_gate.py` (new): the checks below. `tests/test_prompt_pr_body.py` and
    `tests/test_run_abandon.py`: as in Context.
  - ADR-0042 D3: this task marks it built (`ccp adr decide 42 D3 built`).
- **Out:**
  - The resolution review mode and verify rerunning affected checks (task 0168), close's catch-up (task 0167),
    counting conflict catch-ups (task 0169).
  - Any change to verify's `behind_tip` refusal or to `merge.behind_tip_ignore`.

## dod_checks

- id: `rev-01`
  story: As a runner, a review of a head whose merge of the tip would conflict is refused before a reviewer starts.
  setup: the `tests.test_parallel_merging` fixture shape: task 0002 claimed, its branch head adds `feature.txt` and is pushed; then a tip commit on `main` adds `feature.txt` with other content.
  steps:
    1. Run `ccp prompt review 0002 --pr 7 --head <the pushed head>`.
  expect: exit 4; stderr names `feature.txt` and `ccp prompt merge 0002-second`; no review run and no review prompt file exist for 0002.
  dry run (`b9e58ce`): exit 0, no warnings, a review run opened (Context).
- id: `rev-02`
  story: As a runner, a head behind the tip by a clean merge, or by a conflict only in the task log, still goes to review.
  setup: the fixture of `rev-01`, but the tip commit changes `other.py` only; a second fixture where the tip commit and the head both edit the same line of 0002's own task file and nothing else conflicts.
  steps:
    1. In each, run `ccp prompt review 0002 --pr 7 --head <the pushed head>`.
  expect: both exit 0 and open a review run; neither run's warnings name `behind_tip`.
  dry run (`b9e58ce`): the first exits 0 (review checks nothing).
- id: `rev-03`
  story: As a runner, a head that cannot be fetched opens the review with a warning.
  setup: the `tests.test_toolkit` fixture, task 0002 claimed, no such commit as `abc1234`.
  steps:
    1. Run `ccp prompt review 0002 --pr 7 --head abc1234`.
  expect: exit 0; the body's `warnings` holds one line starting `behind_tip not checked`.
  dry run (`b9e58ce`): exit 0 with no `warnings` key.
- id: `tpl-01`
  story: As an implementer, my implement and fix prompts end with the catch-up, before the suite.
  setup: the `tests.test_toolkit` fixture at the PR head, 0002 claimed; for the fix round, a review run of 0002 that reported a MAJOR.
  steps:
    1. Run `ccp prompt implement 0002` and read the rendered prompt file.
    2. Run `ccp prompt fix 0002 --pr 7 --head abc1234` and read the rendered prompt file.
  expect: in the implement prompt the first `git merge origin/main` comes after `is binding` and before the first `ccp suite run --lane`; in the fix prompt it comes after `Fix what these found` and before the first `ccp suite run --lane`.
  dry run (`b9e58ce`): implement prompt offsets `git merge origin/main` 409, `is binding` 563, `ccp suite run --lane` 2278 (the merge comes first); in `templates/prompts/fix.md` the merge sentence is in the second paragraph, before `Fix what these found`.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0166-catch-up-before-review --base origin/main`.
  expect: exit 0, both passages found in `docs/spec/02-delivery.md`.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-19 (implementer): `ccp/prompt.py` `tip_gate` now runs for `review` and `verify`. For review, a head behind
  (`lifecycle.behind_tip`) is judged with `gitmerge.probe(head, origin/<integ>)`; the conflicted files outside the
  task log (`lifecycle.task_log_paths`) and `merge.behind_tip_ignore` refuse (exit 4), up to 5 named then "and N more",
  with `ccp prompt merge`. The ignore match is the path itself or anything under it (the same reading as the
  pathspec `behind_tip` uses). Verify's refusal is unchanged except that its text shares the `ccp prompt merge` sentence.
- Open choices, narrowest reading: (1) a probe that fails to run (git older than 2.38) is a `behind_tip not checked`
  warning and the review opens, like a fetch that fails; (2) the review's fetch warning carries no "close checks it"
  suffix, since close judges only a verify's head; (3) a head behind only by task-log or `behind_tip_ignore` commits is
  not behind at all (`behind_tip` is empty), so the probe never runs for it: the conflict-only-in-the-log fixtures
  therefore carry a second tip change outside the log, or the head would not be judged.
- `tests/test_worker_efficiency.py` `test_workers_merge_the_integration_branch_in_never_rebase` pinned the fix
  prompt's old wording ("merge it into the branch"); it now pins the catch-up wording ("by merging it in",
  "never by rebasing"). `tests/test_run_abandon.py` `test_a_running_round_is_superseded_with_a_warning` counted
  every warning; it now counts the ones other than `behind_tip not checked`.
- ADR-0042 D3 marked built.

## Verification notes
