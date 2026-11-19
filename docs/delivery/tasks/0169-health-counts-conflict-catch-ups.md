---
task_id: 0169-health-counts-conflict-catch-ups
title: ccp report records each round's integration merges and whether they conflicted, and ccp health reports conflict catch-ups before and after review
status: pending
kind: feature
depends_on: ["0166-catch-up-before-review", "0168-resolution-review"]
spec_refs: ["S27", "S11", "S13"]
adr_refs: ["0042 D5"]
review_point: R11
paths: ["ccp/report.py", "ccp/health.py", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/04-observability.md", "tests/test_health_conflicts.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0169-health-counts-conflict-catch-ups
## Intent

The operator and the task-log owner can see, per product, what running overlapping tasks together
costs in conflicts. `ccp health` reports how many integration merges conflicted before review (the
implementer's own catch-up) and after it (a merge round, then a resolution review), with the wall time
and tokens of the rounds that held them. That figure is the evidence for changing ADR-0042 D1's
default. It comes from a field the plane computes when each round reports, not from report prose.

## Context (not checked)

- ADR-0042 D5 (accepted 2026-11-19); shape `sh-20261119T072530Z-663f`, single source "conflict
  catch-ups". Today:
  - merge-round reports list conflicts in prose only (`templates/prompts/merge.md`), and E6 forbids
    parsing prose;
  - a catch-up inside an implement or fix round (task 0166-catch-up-before-review) records nothing.
- `ccp --root . health --json` at `b9e58ce` prints these top-level keys: `adopted_at`,
  `before_adoption`, `budget_failures`, `gate_time`, `notes`, `queue`, `rotation`, `sign_off_wait`,
  `small_tasks`, `suite`, `suite_modules`, `tasks`, `trend`, `usage_advice`, `usage_advice_since`. There
  is no `conflict_catch_ups`.
- **Where the merges are found.** The field is computed at `ccp report`, for a done implement, fix,
  merge or ruling report with a `Head:`.
  - The round's range is `<the task's previous done change round's reported head>..<head>`. For the
    first such round it is `origin/<integration>..<head>`.
  - An integration merge is a merge commit in that range whose second parent is an ancestor of
    `origin/<integration>` (`git merge-base --is-ancestor`).
  - Whether it conflicted is the merge probe of 0162-git-merge-helper (`ccp/gitmerge.py`), run on its first and
    second parents. E14 forbids any other module to run `merge-tree`.
- **Fail-safe.** No product checkout, a head not in the object store, or a failed probe records
  nothing: the run has no `integration_merges` key, and health counts it as unmeasured. The report is
  never refused for it.
- **Before or after review.** A round opened before the task's first review run that reported `done`
  is before review; any later round is after.
  - After review, the cost of a conflict catch-up is its merge round plus the resolution review that
    followed it (task 0168's `mode: resolution`).
  - Before review, the merge sits inside a larger implement or fix round. Its figures are that whole
    round's, so the report calls them the rounds' totals.
- **The figures.**
  - Wall time is each run's `started_at` (else `opened_at`) to `reported_at`.
  - Tokens are the sum of `usage.TOKENS` over that run in `usage.fold`'s runs, as `ccp board` sums
    them.
  - The window is health's own (§27.1): runs reported in it.
- **SPEC is §31.1.** ADR-0042 names §27 among the rules it changes. This task's SPEC text only
  describes its own new, diagnostic measure (§27.1 says nothing there is a target) and the run field
  that feeds it (§11.1). No existing sentence changes meaning. So this task carries no `sign_off`.

## Scope

- **In:**
  - `ccp/report.py`, at submit, for a done implement, fix, merge or ruling report with a head:
    - it computes the round's integration merges as Context says and stores them on the run as
      `integration_merges`: a list of `{"sha": <merge sha>, "conflicted": <bool>, "files": <count of
      conflicted files>}`, in commit order;
    - an empty list means none were found; the key is absent when it could not be measured;
    - it also stores `before_review: <bool>`;
    - ids and counts only, never file names or content.
  - `ccp/health.py`: `conflict_catch_ups` in `--json`, with one line in the text output:
    - `before_review` and `after_review`, each `{"count": <conflicted merges>, "rounds": <runs holding
      them>, "wall_s": <sum>, "tokens": <sum>}`;
    - `after_review` adds the resolution review runs that followed each such merge round (its wall
      time and tokens, and `resolution_reviews`, their count);
    - `clean_merges`, the count of integration merges that did not conflict;
    - `unmeasured`, the count of change rounds in the window without the key.
    It reads runs reported in health's window.
  - `docs/spec/02-delivery.md` §11.1, the run record's field list: it gains `integration_merges` and
    `before_review`, with one sentence on how `ccp report` computes them. §31.1: this task's own
    feature.
  - `docs/spec/04-observability.md` §27.1: a new bullet **Conflict catch-ups**, describing
    `conflict_catch_ups` as above. §31.1: this task's own feature.
  - `docs/cli/04-observability.md`: the `ccp health` row names `conflict_catch_ups`.
  - `tests/test_health_conflicts.py` (new): the checks below, on fenced temp products, origins and
    queues.
- **Out:**
  - Close's own catch-ups. They never conflict (a union of `parallel.shared` lines is recorded on the
    verification record as `merge_tree: union`).
  - Changing D1's default, which is a later decision.
  - The board.
  - Any telemetry field.

## dod_checks

- id: `run-01`
  story: As the plane, each round's report records its integration merges and whether they conflicted.
  setup: a fenced product with an origin and a queue: task 0002 claimed, its implement round reported at H1; then a merge round whose head H2 is a merge of `origin/main` that conflicted in one file and was resolved; a second merge round whose head H3 merges a later tip cleanly.
  steps:
    1. Submit the merge round's done report at H2 through `ccp report`.
    2. Submit the second merge round's done report at H3.
    3. Submit a done fix report whose `Head:` names a sha that is not in the product's object store.
  expect: step 1's run has `integration_merges` with one entry, `conflicted: true`, `files: 1`, and `before_review` false when a done review precedes it; step 2's run has one entry with `conflicted: false`; step 3 exits 0 and its run has no `integration_merges` key.
  dry run: n/a — `ccp report` records no such field at `b9e58ce`.
- id: `hl-01`
  story: As the operator, health shows conflict catch-ups before and after review, with their cost.
  setup: a fenced queue whose run records carry `integration_merges`. An implement run (before review, one conflicted merge, 600 s, usage summing 1000 tokens). A merge round after review (one conflicted merge, 300 s, 400 tokens) followed by a resolution review run (120 s, 200 tokens). A fix round with one clean merge. A change round without the key.
  steps:
    1. Run `ccp health --json`.
  expect: `conflict_catch_ups.before_review` is `{"count": 1, "rounds": 1, "wall_s": 600, "tokens": 1000}`; `after_review` has count 1, rounds 1, `resolution_reviews` 1, `wall_s` 420 and `tokens` 600; `clean_merges` is 1; `unmeasured` is 1.
  dry run (`b9e58ce`): `ccp --root . health --json` has no `conflict_catch_ups` key (top-level keys listed in Context).
- id: `hl-02`
  story: As the operator, runs before health's window are left out, and the text output shows the line.
  setup: the queue of hl-01, plus a merge round with a conflicted merge reported before the queue's `plane`/`adopted` event.
  steps:
    1. Run `ccp health --json`, then `ccp health`.
  expect: the JSON counts equal hl-01's (the earlier round is left out); the text output has one line naming conflict catch-ups with `1 before review` and `1 after review`.
  dry run: n/a — the measure does not exist at `b9e58ce`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
