---
task_id: 0258-the-plane-writes-the-pre-merge-phases
title: The plane writes the pre-merge phases the standing DoD describes, and its contracts match what it writes
status: pending
kind: feature
depends_on: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0242-retire-restructure-scaffolding-and-queue-markers"]
clashes_with: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0219-integration-merges-leave-out-the-tip", "0223-a-follow-up-is-tracked-not-left-in-notes", "0238-the-runner-runs-marked-checks-before-verify", "0257-one-gate-block-and-one-sentence-per-line"]
spec_refs: ["S10", "S13", "S15"]
review_refs: ["ar-20261120T234012Z-27eb#F07"]
review_point: R18
paths: ["ccp/report.py", "ccp/prompt.py", "ccp/lifecycle.py", "ccp/cli.py", "ccp/queue.py", "ccp/submit.py", "contracts/progress.schema.json", "contracts/review.schema.json", "contracts/result.schema.json", "contracts/architecture_review.schema.json", "contracts/CLAUDE.md", "dod/standing.yaml", "scripts/formal-submit.template.sh", "scripts/CLAUDE.md", "scripts/queue/README.md", "docs/spec/02-delivery.md", "docs/spec/05-operations.md", "docs/cli/02-delivery.md", "docs/design/observability.md", "tests/test_review_record.py", "tests/test_formal_submit.py", "tests/test_phase_contracts.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0258-the-plane-writes-the-pre-merge-phases

## Intent

The pre-merge phases that SPEC §13.1, §15.1 and `dod/standing.yaml` describe are what the plane does
and records, not prose about a retired pipeline. The PR comes from the implementer's own worker, a
clean review leaves a review record, formal-submit is a `ccp` command that `ccp prompt verify` runs
first, and a task moves through `implemented`, `reviewed` and `submitted` as §10.1 draws it. Every
contract under `contracts/` describes a record the plane writes or reads, in the shape it writes it.

## Context (not checked)

- **The ruling.** Architect pass `ar-20261120T234012Z-27eb`, finding F07, asked whether to drop the
  `/mk-pr` and formal-submit phases or keep them. The operator, 2026-11-21, in the lead session:
  "(b)", that is, keep the phases as described and keep the script. Recorded in
  `docs/delivery/reviews/ar-20261120T234012Z-27eb.md`.
- **What the code does today** (measured at `b2b9846`):
  - Phases: `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`
    (`PHASE_STATUS` in `ccp/prompt.py`). Nothing moves a task to `implemented`, `reviewed` or
    `submitted`: `git grep -nE '"(implemented|reviewed|submitted)"' -- ccp` at `b2b9846` gives 8 lines,
    and the only one naming a queue phase is `MID_FLIGHT` in `ccp/queue.py`.
  - The PR: the implement prompt has the implementer open it in its own worker; no prompt, agent or
    module names `/mk-pr` (`git grep -n -e mk-pr -e mk_pr -- templates plugin ccp` at `b2b9846`: 0 lines).
    Each run record holds `pr`, `head`, `session_id` and `agent_id`.
  - The review verdict: `ccp report` (`"def submit"` in `ccp/report.py`) already computes `clean` or
    `changes` for a review run and emits `review`/`recorded`; it writes no review record.
  - Contracts: nothing in `ccp`, `scripts`, `plugin` or `tests` names the progress, review, result or
    architecture-review schemas
    (`git grep -lw -e progress.schema -e review.schema -e result.schema -e architecture_review.schema -- ccp scripts plugin tests` at `b2b9846`: 0 files).
    `progress.schema.json` requires `project_id` and `status` and allows only
    `at`, `actor`, `message` on an event, while `"def progress_event"` in `ccp/queue.py` writes
    `task_id`, `events` (`at`, `from`, `to`, `note`) and `updated_at`.
  - The script: `scripts/formal-submit.template.sh` reads `pr_url` from the task's queue file and
    `mk_pr_session_id` from `review/<task_id>.json`, neither of which the plane writes, and writes
    nothing itself. `git grep -n formal-submit -- . ':!docs/delivery'` at `b2b9846`: 7 lines in 4 files
    (the SPEC, `scripts/CLAUDE.md`, the script, `scripts/queue/README.md`).
- **Rulings for the build** (the lead's):
  - **Phases.** `ccp report` moves the task to `implemented` when an implement or rework run (fix,
    merge, ruling: `runs.REWORK_PHASES`) reports `done` with a head, and to `reviewed` when a review
    run reports `done` with the verdict `clean`. A correction (§13.4) moves nothing again. Formal-submit
    moves it to `submitted`. Each move goes through `queue.phase_move`, so it has its event and progress
    row like every other.
  - **The review record.** On a review run reported `done` and `clean`, `ccp report` writes
    `review/<task_id>.json` (one per task, replaced by each clean review) with: `task_id`, `project_id`,
    `pr` (the PR number), `head` (the head reviewed), `mk_pr_run_id` and `mk_pr_session_id` (the
    implement or rework run that first reported this PR, and its session), `review_run_id` and
    `review_session_id`, `safe_fixes_applied` (the run ids of the rework rounds reported after the PR
    opened and before this review), `decisions` (each spec question the task raised: `class` `spec`, its
    `question_ref`), `review_artifact_path` (the stored review report) and `reviewed_at`. Ids, numbers,
    paths and times only (E5). `contracts/review.schema.json` is rewritten to exactly these keys, `pr`
    replacing `pr_url`.
  - **Formal-submit** is `ccp tasks submit <id>` (needs QUEUE_ROOT), in a new module `ccp/submit.py`,
    and `ccp prompt verify` calls the same function before it opens a verify run. It checks, in this
    order, the standing DoD's `formal_submit` items: `pr_exists` (the task's queue record names a PR);
    `mk_pr_via_implementer_resume` (an implement or rework run of the task reported that PR);
    `review_artifact_present` (a review record exists and its review covers the PR head, judged by the
    rules `ccp prompt verify` already applies, `runs.unreviewed_fix` and the review skips);
    `unit_lint` (the run whose head is the PR head recorded at least one ended `ccp suite run` with a
    zero exit code); `no_open_spec_escalation` (no open spec question or escalation lists the task). Any
    failure refuses with exit 4, naming each failed item, and moves nothing; a pass moves the task to
    `submitted`. It writes no other record and runs no test. If the suite rows do not record an exit
    code, stop with a scope question rather than choose another proof.
  - **The script** is kept (the ruling) and becomes a wrapper: `scripts/formal-submit.template.sh
    <task_id>` runs `ccp tasks submit <task_id>` and exits with its code (E7: scripts only wrap `ccp`).
  - **Contracts.** `progress.schema.json` is rewritten to what `progress_event` writes: `task_id`,
    `events` (items `at`, `from` (string or null), `to`, `note`), `updated_at`, with `from` and `to`
    the §10.1 phase names. `result.schema.json` and `architecture_review.schema.json` describe no record
    the plane writes or reads and no phase the ruling keeps: they are removed (E9). A new test compares
    each kept phase contract's keys with what the code writes, without a schema library (the plane has
    none).
  - **`dod/standing.yaml`**: the `same_session_mk_pr_review` and `formal_submit` phases get `notes:`
    naming the review record and `ccp tasks submit`; the `mk_pr_via_implementer_resume` comment drops
    "/mk-pr" for "a PR another session opened fails formal-submit". No item is added or removed.
- **SPEC.** The changes below only describe this task's feature, the phases the operator ruled kept
  (§31.1): no sign-off. The two false statements, §13.1's "with `/mk-pr`" and §30.2's "same-session
  `/mk-pr`" (`git grep -n -e /mk-pr -- docs/spec` at `b2b9846`: 2 lines), are corrected the same way.
  `docs/cli/02-delivery.md` gains `ccp tasks submit` (E25).

## Scope

- **In:**
  - `ccp/submit.py` (new): the formal-submit check; `ccp/cli.py` (`ccp tasks submit`);
    `ccp/prompt.py` (`ccp prompt verify` runs it first); `ccp/report.py` (the phase moves and the
    review record); `ccp/queue.py` and `ccp/lifecycle.py` only where a phase list needs the new moves.
  - `contracts/progress.schema.json`, `contracts/review.schema.json` (rewritten);
    `contracts/result.schema.json` (removed), `contracts/architecture_review.schema.json` (removed);
    `contracts/CLAUDE.md`.
  - `dod/standing.yaml` (notes and one comment); `scripts/formal-submit.template.sh` (a wrapper);
    `scripts/CLAUDE.md`, `scripts/queue/README.md`, `docs/design/observability.md` (their lines on
    these records); `docs/cli/02-delivery.md`.
  - `tests/test_review_record.py` (new), `tests/test_formal_submit.py` (new),
    `tests/test_phase_contracts.py` (new).
  - SPEC, §31.1 (describes this task's feature; no sign-off):
  - `docs/spec/02-delivery.md` §10.1, one sentence replaced:

    CURRENT (`docs/spec/02-delivery.md` at `b2b9846`):
    > `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`; `ccp tasks
    > phase <id> <phase>` moves it for a step with no run of its own (an operator step, waiting to
    > merge).

    PROPOSED:
    > `ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`; `ccp report`
    > moves it to `implemented` when an implement or rework round reports done with a head, and to
    > `reviewed` when a review reports clean; formal-submit moves it to `submitted` (§15.1); `ccp tasks
    > phase <id> <phase>` moves it for a step with no run of its own (an operator step, waiting to
    > merge).
  - `docs/spec/02-delivery.md` §13.1, one sentence replaced:

    CURRENT (`docs/spec/02-delivery.md` at `b2b9846`):
    > The implementer writes the change and, **in the same worker** (resumed by name), opens the
    > PR with `/mk-pr`; a cold `/mk-pr` is forbidden.

    PROPOSED:
    > The implementer writes the change and, **in the same worker** (resumed by name), opens the
    > PR (`mk_pr_via_implementer_resume`, §15.1); a PR opened by any other session fails formal-submit.
  - `docs/spec/02-delivery.md` §15.1, a paragraph added after the one that ends "post-merge smoke and
    production promotion are outside it.":

    CURRENT (`docs/spec/02-delivery.md` at `b2b9846`): none, a new paragraph.

    PROPOSED:
    > The plane records two of these phases. When a review reports clean, `ccp report` writes the
    > task's review record, `review/<task_id>.json` (`contracts/review.schema.json`): the PR, the head
    > reviewed, the run and session that opened the PR, the review's run and session, the rework rounds
    > since the PR opened, the spec questions the task raised, the review report's path and the time.
    > Formal-submit is `ccp tasks submit <id>`, which `ccp prompt verify` runs before it opens a verify
    > run: it refuses (exit 4, naming each failed item, moving nothing) unless the task has a PR, an
    > implement or rework run of the task reported that PR, the review record's review covers the PR
    > head (§15.2), the run at that head recorded a passed `ccp suite run`, and no spec question or
    > escalation listing the task is open; a pass moves the task to `submitted`. It writes no other
    > record and runs no test.
  - `docs/spec/05-operations.md` §30.2, the first row of the wallets table:

    CURRENT (`docs/spec/05-operations.md` at `b2b9846`):
    > | **Prepaid Claude allowance** (CLI login / subscription quota) | Implementer `claude -p`, same-session `/mk-pr`, a clean `/review`, fix loops | **Development only** |

    PROPOSED:
    > | **Prepaid Claude allowance** (CLI login / subscription quota) | The runner's workers: the implementer and the PR it opens, the clean review, fix loops, the verifier | **Development only** |
- **Out:** the verifier's own gate (unchanged, §15.1's `unit_lint`); the PR-host calls (0220-0222);
  a schema validator library and the other live contracts (deferred F08 of
  `ar-20261121T020523Z-1d5f`); the prompt templates (formal-submit needs no worker step).

## dod_checks

- id: `fs-01`
  story: As the runner, a clean review leaves a review record and moves the task to `reviewed`, and a reported implement round moves it to `implemented`; the tests bite.
  setup: a checkout of the PR head; then a separate copy of it with the review-record write in `ccp/report.py` removed.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_review_record 2>&1 | tail -10`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_review_record`.
  expect: step 1 exits 0, listing as `ok` tests for: an implement run reported done with a head moves the task to `implemented`; a review reported clean writes `review/<task_id>.json` with the implementer run's `mk_pr_session_id` and moves the task to `reviewed`; a review with a MAJOR finding writes no record; a correction moves nothing. Step 2 exits non-zero.
  dry run: n/a — the module is new.
- id: `fs-02`
  story: As the runner, `ccp prompt verify` runs formal-submit first, and each formal-submit item refuses on its own.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_formal_submit 2>&1 | tail -12`.
    2. Run `./bin/ccp tasks submit --help`.
  expect: step 1 exits 0, listing as `ok` one test per refused item (no PR; a PR no implement or rework run reported; no review record covering the head; no passed suite run at the head; an open spec question), each asserting exit 4, the item's name in the message and the phase unchanged; one where every item passes and the task moves to `submitted`; and one where `ccp prompt verify` refuses with the same message and opens no run. Step 2 exits 0 and shows the task id argument.
  dry run: n/a — the command is new.
- id: `fs-03`
  story: As a plane developer, every phase contract describes what the code writes, and the two contracts nothing writes are gone.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_phase_contracts 2>&1 | tail -6`.
    2. Run `git ls-files contracts/result.schema.json contracts/architecture_review.schema.json`.
    3. Run `git grep -n mk_pr_session_id -- contracts ccp scripts`.
  expect: step 1 exits 0, with tests listed `ok` comparing the keys `queue.progress_event` writes, and the review record's keys, with `contracts/progress.schema.json` and `contracts/review.schema.json`; step 2 prints nothing; step 3 prints lines in `contracts/review.schema.json` and in `ccp/` only, none in `scripts/`.
  dry run (`b2b9846`): step 1 n/a (the module is new); step 2 printed 2 paths; step 3 printed 1 line in `contracts/review.schema.json` and 2 in `scripts/formal-submit.template.sh`.
- id: `fs-04`
  story: As a product that kept the formal-submit script, it now runs the plane's own check.
  setup: a checkout of the PR head; a scratch QUEUE_ROOT with no task in it.
  steps:
    1. Run `git grep -c "ccp tasks submit" -- scripts/formal-submit.template.sh`.
    2. Run `QUEUE_ROOT=$(mktemp -d) bash scripts/formal-submit.template.sh 0001-none; echo "exit $?"`.
  expect: step 1 prints `scripts/formal-submit.template.sh:` with a count of at least 1; step 2 prints `ccp`'s refusal for an unknown task and an exit code other than 0.
  dry run (`b2b9846`): step 1 printed nothing (exit 1); step 2 printed "formal-submit: missing task file …" and `exit 1`.
- id: `fs-05`
  story: As the operator, the SPEC describes the kept phases as the plane runs them.
  setup: a checkout of the PR head.
  steps:
    1. Run `./bin/ccp verify spec-text 0258`.
    2. Run `git grep -n -e '/mk-pr' -- docs/spec`.
  expect: step 1 exits 0 with the four PROPOSED passages found (three in `docs/spec/02-delivery.md`, one in `docs/spec/05-operations.md`); step 2 prints nothing.
  dry run (`b2b9846`): step 1 n/a (the passages land with the task); step 2 printed 2 lines (§13.1, §30.2).

## Implementation notes

## Verification notes
