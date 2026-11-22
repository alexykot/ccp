---
task_id: 0258-the-plane-writes-the-pre-merge-phases
title: The plane writes the pre-merge phases the standing DoD describes, and its phase contracts match what it writes
status: pending
kind: feature
depends_on: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0242-retire-restructure-scaffolding-and-queue-markers"]
clashes_with: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0219-integration-merges-leave-out-the-tip", "0223-a-follow-up-is-tracked-not-left-in-notes", "0227-the-test-fixture-uses-the-local-pr-host", "0238-the-runner-runs-marked-checks-before-verify", "0257-one-gate-block-and-one-sentence-per-line"]
spec_refs: ["S10", "S13", "S15"]
review_refs: ["ar-20261120T234012Z-27eb#F07"]
review_point: R18
paths: ["ccp/report.py", "ccp/submit.py", "ccp/cli.py", "ccp/queue.py", "ccp/CLAUDE.md", "contracts/progress.schema.json", "contracts/review.schema.json", "contracts/CLAUDE.md", "dod/standing.yaml", "plugin/agents/delivery-runner.md", "scripts/formal-submit.template.sh", "scripts/CLAUDE.md", "scripts/queue/README.md", "docs/spec/02-delivery.md", "docs/spec/05-operations.md", "docs/cli/02-delivery.md", "docs/design/observability.md", "tests/test_review_record.py", "tests/test_formal_submit.py", "tests/test_phase_contracts.py", "tests/test_release.py", "tests/test_session_park.py", "tests/test_tasks_release_keep_branch.py", "tests/test_toolkit.py", "tests/test_health.py", "tests/test_board.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0258-the-plane-writes-the-pre-merge-phases

## Intent

The pre-merge phases that SPEC §13.1, §15.1 and `dod/standing.yaml` describe are what the plane does
and records, not prose about a retired pipeline. A clean review leaves a review record; formal-submit,
the local checklist between review and verify, is a `ccp` command the runner runs before it launches
the verifier; and a task moves through `implemented`, `reviewed` and `submitted` as §10.1 draws it.
The progress and review contracts describe the records the plane writes, in the shape it writes them.

## Context (not checked)

- **The ruling.** Architect pass `ar-20261120T234012Z-27eb`, finding F07, asked whether to drop the
  `/mk-pr` and formal-submit phases (a), keep them (b), or remove only the unread contracts (c). The
  operator, 2026-11-21, in the lead session: "(b)". Recorded in
  `docs/delivery/reviews/ar-20261120T234012Z-27eb.md`.
- **No § rule is added.** Every SPEC edit below describes the phases the ruling keeps, as §13.1, §15.1
  and the standing DoD already state them (§31.1). `ccp prompt verify` keeps its refusals as they are,
  and formal-submit stays "a local checklist, not the gate".
- **What the code does today** (measured at `58e9220`):
  - Phases: `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`
    (`PHASE_STATUS` in `ccp/prompt.py`). Nothing moves a task to `implemented`, `reviewed` or
    `submitted`: `git grep -nE '"(implemented|reviewed|submitted)"' -- ccp` at `58e9220` gives 8 lines,
    and the only one naming a queue phase is `MID_FLIGHT` in `ccp/queue.py`.
  - The PR: the implement prompt has the implementer open it in its own worker; nothing names `/mk-pr`
    (`git grep -n -e mk-pr -e mk_pr -- templates plugin ccp` at `58e9220`: 0 lines). Each run record
    holds `pr`, `head`, `session_id` and `agent_id`.
  - The review verdict: `"def submit"` in `ccp/report.py` already computes `clean` or `changes` for a
    review run and emits `review`/`recorded`; it writes no review record.
  - Contracts: nothing in `ccp`, `scripts`, `plugin` or `tests` names the progress, review, result or
    architecture-review schemas
    (`git grep -lw -e progress.schema -e review.schema -e result.schema -e architecture_review.schema -- ccp scripts plugin tests` at `58e9220`: 0 files).
    `progress.schema.json` requires `project_id` and `status` and allows only `at`, `actor`, `message`
    on an event, while `"def progress_event"` in `ccp/queue.py` writes `task_id`, `events` (`at`,
    `from`, `to`, `note`) and `updated_at`. The plane has a schema checker: `"def schema_errors"` in
    `ccp/verify.py`.
  - The script: `scripts/formal-submit.template.sh` reads `pr_url` from the task's queue file and
    `mk_pr_session_id` from `review/<task_id>.json`, neither of which the plane writes, and writes
    nothing itself. `git grep -n formal-submit -- . ':!docs/delivery'` at `58e9220`: 7 lines in 4 files
    (the SPEC, `scripts/CLAUDE.md`, the script, `scripts/queue/README.md`).
  - Test modules that set or assert a runtime phase, which the new moves can touch
    (`git grep -lE '"(implementing|reviewing|fixing)"' -- tests` at `58e9220`: 14 files); the ones that
    assert a phase after a report are listed in `paths`. Any other module the new moves break is in
    scope (§13.1).
- **Rulings for the build** (the lead's):
  - **Phases.** `ccp report` moves the task to `implemented` when an implement run (phase `implement`)
    reports `done` with a head, and to `reviewed` when a review run reports `done` with the verdict
    `clean`. Rework rounds move nothing new. A correction (§13.4) moves nothing again. `ccp tasks
    submit` moves the task to `submitted`. Each move goes through `queue.phase_move`, so it has its
    event and progress row like every other.
  - **The review record.** On a review run reported `done` and `clean`, `ccp report` writes
    `review/<task_id>.json` (one per task, replaced by each clean review) with: `task_id`, `project_id`,
    `pr` (the PR number), `head` (the head reviewed), `mk_pr_run_id` and `mk_pr_session_id` (the
    implement or rework run that first reported this PR, and its session), `review_run_id` and
    `review_session_id`, `safe_fixes_applied` (the run ids of the rework rounds reported after the PR
    opened and before this review), `decisions` (each spec question the task raised: `class` `spec`, its
    `question_ref`), `review_artifact_path` (the stored review report) and `reviewed_at`. Ids, numbers,
    paths and times only (E5). `contracts/review.schema.json` is rewritten to exactly these keys, `pr`
    replacing `pr_url`. The `mk_pr_*` fields record the standing DoD's `mk_pr_via_implementer_resume`,
    which stays in its `same_session_mk_pr_review` phase; formal-submit does not check it.
  - **Formal-submit** is `ccp tasks submit <id>` (needs QUEUE_ROOT), in a new module `ccp/submit.py`,
    run by the runner after the last review and before `ccp prompt verify`. It checks the standing DoD's
    `formal_submit` items: `pr_exists` (the task's queue record names a PR); `review_artifact_present`
    (a review record exists and its review covers the PR head, judged by the rules `ccp prompt verify`
    already applies: `runs.unreviewed_fix` and the review skips); `no_open_spec_escalation` (no open
    spec question or escalation lists the task). Any of these failing exits 4, naming each failed item,
    and moves nothing; all passing moves the task to `submitted`. `unit_lint` keeps its §15.1 meaning,
    the verifier's own run: submit only reports, in its output, whether the run at the PR head recorded
    a passed `ccp suite run`, and never refuses on it. It writes no other record and runs no test.
    `ccp prompt verify` is unchanged: it neither runs submit nor refuses a task that is not `submitted`.
  - **The runner's definition** (`plugin/agents/delivery-runner.md`) gains the step: after the review
    that clears the head, `ccp tasks submit <task_id>`; on exit 4, the named items are handled like the
    matching refusals of `ccp prompt verify`. A change to the runner's contract: its release is followed
    by a runner rotation (§29.3).
  - **The script** is kept (the ruling) and becomes a wrapper: `scripts/formal-submit.template.sh
    <task_id>` runs `ccp tasks submit <task_id>` and exits with its code (E7: scripts only wrap `ccp`).
  - **Contracts.** `progress.schema.json` is rewritten to what `progress_event` writes: `task_id`,
    `events` (items `at`, `from` (string or null), `to`, `note`), `updated_at`, with `from` and `to`
    the §10.1 phase names. `result.schema.json` and `architecture_review.schema.json` stay as they are:
    the operator chose (b) over (c), and their fate waits for the schema-validation work deferred as F08
    of `ar-20261121T020523Z-1d5f`. A new test validates a written progress file and a written review
    record against their schemas with `verify.schema_errors`.
  - **`dod/standing.yaml`**: the `same_session_mk_pr_review` and `formal_submit` phases get `notes:`
    naming the review record and `ccp tasks submit`; the `mk_pr_via_implementer_resume` comment drops
    "cold /mk-pr forbidden" for "the PR comes from the implementer's own worker". No item is added,
    moved or removed.
- **Tasks in flight when this ships.** A task mid-flight when 0258 is released has no review record, so
  `ccp tasks submit` refuses it (`review_artifact_present`) and it costs one extra review before
  verify; accepted.
- **SPEC.** The edits below only describe the kept phases (§31.1): no sign-off. §13.1's "with `/mk-pr`"
  and §30.2's "same-session `/mk-pr`" were already false (`git grep -n -e /mk-pr -- docs/spec` at
  `58e9220`: 2 lines) and are corrected the same way. `docs/cli/02-delivery.md` gains `ccp tasks submit`
  (E25).

## Scope

- **In:**
  - `ccp/submit.py` (new): the formal-submit checklist; `ccp/cli.py` (`ccp tasks submit`);
    `ccp/report.py` (the phase moves and the review record); `ccp/queue.py` only where a phase list
    needs the new moves; `ccp/CLAUDE.md` (the module list).
  - `contracts/progress.schema.json`, `contracts/review.schema.json` (rewritten); `contracts/CLAUDE.md`.
  - `dod/standing.yaml` (notes and one comment); `plugin/agents/delivery-runner.md` (the submit step);
    `scripts/formal-submit.template.sh` (a wrapper); `scripts/CLAUDE.md`, `scripts/queue/README.md`,
    `docs/design/observability.md` (their lines on these records); `docs/cli/02-delivery.md`.
  - `tests/test_review_record.py` (new), `tests/test_formal_submit.py` (new),
    `tests/test_phase_contracts.py` (new); the existing modules in `paths` whose fixtures assert a phase
    after a report.
  - SPEC, §31.1 (describes the kept phases; no sign-off):
  - `docs/spec/02-delivery.md` §10.1, one sentence replaced:

    CURRENT (`docs/spec/02-delivery.md` at `58e9220`):
    > `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`; `ccp tasks
    > phase <id> <phase>` moves it for a step with no run of its own (an operator step, waiting to
    > merge).

    PROPOSED:
    > `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`; `ccp report`
    > moves it to `implemented` when an implement round reports done with a head, and to `reviewed`
    > when a review reports clean; `ccp tasks submit` moves it to `submitted` (§15.1); `ccp tasks
    > phase <id> <phase>` moves it for a step with no run of its own (an operator step, waiting to
    > merge).
  - `docs/spec/02-delivery.md` §13.1, one sentence replaced:

    CURRENT (`docs/spec/02-delivery.md` at `58e9220`):
    > The implementer writes the change and, **in the same worker** (resumed by name), opens the
    > PR with `/mk-pr`; a cold `/mk-pr` is forbidden.

    PROPOSED:
    > The implementer writes the change and, **in the same worker** (resumed by name), opens the
    > PR (`mk_pr_via_implementer_resume`, §15.1); a PR from any other session is forbidden.
  - `docs/spec/02-delivery.md` §15.1, a paragraph added after the one that ends "post-merge smoke and
    production promotion are outside it.":

    CURRENT (`docs/spec/02-delivery.md` at `58e9220`): none, a new paragraph.

    PROPOSED:
    > The plane records two of these phases. When a review reports clean, `ccp report` writes the
    > task's review record, `review/<task_id>.json` (`contracts/review.schema.json`): the PR, the head
    > reviewed, the run and session that opened the PR, the review's run and session, the rework rounds
    > since the PR opened, the spec questions the task raised, the review report's path and the time.
    > Formal-submit is `ccp tasks submit <id>`, which the runner runs before `ccp prompt verify`: it
    > exits 4, naming each failed item and moving nothing, unless the task has a PR, the review record's
    > review covers the PR head (§15.2), and no spec question or escalation listing the task is open; a
    > pass moves the task to `submitted`. It also reports whether the run at the PR head recorded a
    > passed `ccp suite run`, which it does not judge: `unit_lint` is the verifier's own run.
  - `docs/spec/05-operations.md` §30.2, the first row of the wallets table:

    CURRENT (`docs/spec/05-operations.md` at `58e9220`):
    > | **Prepaid Claude allowance** (CLI login / subscription quota) | Implementer `claude -p`, same-session `/mk-pr`, a clean `/review`, fix loops | **Development only** |

    PROPOSED:
    > | **Prepaid Claude allowance** (CLI login / subscription quota) | The runner's workers: the implementer and the PR it opens, the clean review, fix loops, the verifier | **Development only** |
- **Out:** `ccp prompt verify` (unchanged: no new refusal); the verifier's gate (§15.1's `unit_lint`);
  the PR-host calls (0220-0222); `result.schema.json` and `architecture_review.schema.json` (F08 of
  `ar-20261121T020523Z-1d5f`); the prompt templates.

## dod_checks

- id: `fs-01`
  story: As the runner, a clean review leaves a review record and moves the task to `reviewed`, and a reported implement round moves it to `implemented`; the tests bite.
  setup: a checkout of the PR head; then a separate copy of it with the review-record write in `ccp/report.py` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_review_record 2>&1 | tail -10`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_review_record`.
  expect: step 1 exits 0, listing as `ok` tests for: an implement run reported done with a head moves the task to `implemented`; a fix run reported done leaves its phase as it was; a review reported clean writes `review/<task_id>.json` with the implementer run's `mk_pr_session_id` and moves the task to `reviewed`; a review with a MAJOR finding writes no record; a correction moves nothing. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `fs-02`
  story: As the runner, `ccp tasks submit` checks the formal-submit items before I launch the verifier, and `ccp prompt verify` is unchanged.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_formal_submit 2>&1 | tail -12`.
    2. Run `./bin/ccp tasks submit --help`.
  expect: step 1 exits 0, listing as `ok` one test per refused item (no PR; no review record covering the head; an open spec question), each asserting exit 4, the item's name in the message and the phase unchanged; one where those pass with no passed suite run at the head, asserting exit 0, the task `submitted` and the missing suite run reported; and one asserting `ccp prompt verify` opens a verify run for a task that was never submitted. Step 2 exits 0 and shows the task id argument.
  dry run: n/a — the command is new.
- id: `fs-03`
  story: As a plane developer, the progress and review contracts validate the records the code writes.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_phase_contracts 2>&1 | tail -6`.
    2. Run `git grep -n mk_pr_session_id -- contracts ccp scripts`.
  expect: step 1 exits 0, with tests listed `ok` that validate a progress file written by `queue.progress_event` against `contracts/progress.schema.json`, and a review record written by `ccp report` against `contracts/review.schema.json`, each with `verify.schema_errors` returning none; step 2 prints lines in `contracts/review.schema.json` and in `ccp/` only, none in `scripts/`.
  dry run (`58e9220`): step 1 n/a (the module is new); step 2 printed 1 line in `contracts/review.schema.json` and 2 in `scripts/formal-submit.template.sh`.
- id: `fs-04`
  story: As a product that kept the formal-submit script, it now runs the plane's own check.
  setup: a checkout of the PR head; a scratch QUEUE_ROOT with no task in it.
  steps:
    1. Run `git grep -c "ccp tasks submit" -- scripts/formal-submit.template.sh`.
    2. Run `PATH=$PWD/bin:$PATH QUEUE_ROOT=$(mktemp -d) bash scripts/formal-submit.template.sh 0001-none; echo "exit $?"`.
  expect: step 1 prints `scripts/formal-submit.template.sh:` with a count of at least 1; step 2 prints the checkout's `ccp` refusal `no task 0001-none in docs/delivery/tasks` and `exit 2`.
  dry run (`58e9220`): step 1 printed nothing (exit 1); step 2 printed "formal-submit: missing task file …" and `exit 1`.
- id: `fs-05`
  story: As the operator, the SPEC describes the kept phases as the plane runs them.
  setup: a checkout of the PR head.
  steps:
    1. Run `./bin/ccp verify spec-text 0258`.
    2. Run `git grep -n -e '/mk-pr' -- docs/spec`.
  expect: step 1 exits 0 with the four PROPOSED passages found (three in `docs/spec/02-delivery.md`, one in `docs/spec/05-operations.md`); step 2 prints nothing.
  dry run (`58e9220`): step 1 n/a (the passages land with the task); step 2 printed 2 lines (§13.1, §30.2).

## Implementation notes

- 2026-11-22 (implementer): `ccp report` moves a first report's task through `report.phase_after` (an implement
  done with a head: `implemented`; a review done and clean: `reviewed`) and, on a clean review, writes
  `review/<task_id>.json` (`report.review_record`, built on plain values from the task's runs and its raised
  questions); the `review recorded` event names the record (`record`). A correction moves nothing; a review
  corrected to clean writes the record again.
- `ccp tasks submit` (`ccp/submit.py`) takes the PR and the head from the task's latest done implement or rework
  round (nothing writes `pr` on the task's queue file before close; its `pr` is read as a fallback). Choices the
  ruling left open, sent to the runner: `review_artifact_present` also needs the record's review to be the task's
  latest done review, and that review clean, so an older clean record never passes over a later MAJOR review;
  `no_open_spec_escalation` counts open spec questions whose `task_id` or `blocks` name the task and open
  escalations of class `spec`; the `unit_lint` report looks for a passed suite run on the full or gate lane of
  the round that reported the head.
- `contracts/progress.schema.json`: `from` and `to` are strings, not an enum, because `ccp tasks phase` accepts any
  phase name (the runner's `operator`), and readers accept every value a live queue holds (E9).
- `ccp prompt verify` is unchanged.

## Verification notes
