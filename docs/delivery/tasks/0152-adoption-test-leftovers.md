---
task_id: 0152-adoption-test-leftovers
title: Migrate reads a backticked Refs table, a backfilled adoption keeps its real date, a test notice names what it is about, and orphans pass over the lead's own task-log and SPEC commits
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S4", "S3", "S10", "S27"]
review_point: R10
sign_off: brief
paths: ["ccp/taskmigrate.py", "ccp/init.py", "ccp/health.py", "ccp/notify.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/01-model.md", "docs/cli/02-delivery.md", "docs/cli/05-operations.md", "contracts/observability_event.schema.json", "tests/test_tasks_migrate.py", "tests/test_init.py", "tests/test_health.py", "tests/test_notify.py", "tests/test_orphans.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0152-adoption-test-leftovers
## Intent

Four leftovers from adopting a product are closed. `ccp tasks migrate` converts an earlier-generation
task file whose Meta and Refs tables write their field names and values in backticks, under a Refs
heading with a note after it, and names the row it could not read when it fails. A product whose queue
predates the adoption event gets one dated at its real adoption, not at the first `ccp init` rerun after
a plane release. A test notice says which task, gate or question it is about. `ccp tasks orphans` stops
listing the lead's own commits that change only the task log and the SPEC.

## Context (not checked)

- **Migrate (proposal `9a66`).** `convert` in `ccp/taskmigrate.py` reads `table(text, "Refs")`, whose
  heading pattern is `^##[ \t]+Refs[ \t]*$`, so `## Refs (required for verifier packet)` is no Refs table;
  it takes only rows keyed `spec` (`if k == "spec"`), and `spec_refs` reads only `§N`, `§N.M` or `SN`. The
  product in the proposal wrote, under that heading, a two-column `| Field | Value |` table whose row is
  `` | `spec_refs` | `docs/SPEC.md#<anchor>`, `docs/SPEC.md#<anchor>` | ``: a backticked key, and
  values that are backticked `path#anchor` links to unnumbered SPEC headings. Its Meta table has the
  same shape with keys `task_id`, `status`, `depends_on` (a JSON-style list, `["<id>"]`) and `created`.
  `table` already strips the backticks round a key (`_cell`), so `status` and `created` are read;
  `depends_on` is not (`row.get("depends on", "")`), so its dependencies would be dropped silently. That
  product's current task files keep `spec_refs` as such `path#anchor` strings, and `ccp tasks check`
  accepts them (it requires a cited SPEC section, not a numbered one). Ruled: a `path#anchor` value whose
  path names a SPEC file (`task_log.spec_paths`, `tasklog._names_spec`) is kept as written; a value with
  `§N` or `SN` is read as today. The fixture is built from that description, with made-up names.
- **Adoption event (proposal `bfdf`, premise mostly false at `85d388b`).** `record_adoption` in
  `ccp/init.py` records nothing on a rerun once the ledger holds a `plane`/`adopted` event (`"if not
  written and health.adopted_at(q) is not None"`), and `tests/test_init.py`
  `test_writing_the_binding_records_one_event_and_a_rerun_none` pins it. The event in the proposal was the
  first ever in that queue: the product was adopted before task 0139 added the event, so the first rerun
  after the release backfilled one (`binding: kept`), dated at the rerun. That backfill date is the real
  defect: every product adopted before the event gets its adoption point at whenever init is next run.
  The binding file is written at adoption and rewritten only by `ccp init --force` (which records an event
  of its own), so its last change is the adoption's time.
- **Test notice (proposal `3187`).** `ccp notify fire decision` with no `--task` and no `--id` is accepted
  and records a pending notice whose body is the project and trigger only (`cmd_fire` in `ccp/notify.py`
  checks the sandbox, the trigger and one-line values, nothing else). Every step that fires a notice passes
  a task or an id (`git grep -n "notify.fire(" -- ccp` at `85d388b`: 3 sites, each with `task_id=`). Ruled:
  the test notice needs `--task` or `--id`, whatever the trigger.
- **Orphans (proposal `4265`).** `uncovered` in `ccp/health.py` passes over a commit that "changes nothing
  outside the task log" (`task_log_paths`: the task files, `INDEX.yaml`, the reconcile log). The lead's
  spec-maintainer rulings change the SPEC too, and a squash merge replaces their `spec(<question_id>):`
  subject with the PR's title, so neither the subject nor the paths pass them. Read in the proposal's
  product: its non-task commits since adoption each touched only `docs/delivery/` task files and
  `INDEX.yaml` and its SPEC directory. Ruled: recognised by paths, not by subject: a commit whose every
  path is in the task log or names a SPEC file (`task_log.spec_paths`) is covered. A commit that also
  changes anything else is still listed. This changes a § rule, carried below for signing.

## Scope

- **In:**
  - `ccp/taskmigrate.py`: `table` matches a `## <heading>` followed by anything after a space (`## Refs
    (required for verifier packet)`). The Refs rows read are keyed `spec` or `spec_refs` (any case). A
    value is split into its backticked items when it has any, else on commas; each `§N`, `§N.M` or `SN`
    is read as today, and an item `<path>#<anchor>` whose path names a SPEC file is kept as written. The
    Meta row `depends_on` is read as `Depends on` is, a `["<id>", …]` value as its ids. A file it cannot
    convert for want of a SPEC section names the Refs heading it read (or none) and each row's key with
    its value. The module docstring describes the second table shape.
  - `ccp/init.py` `record_adoption`: a backfilled event (binding kept, no event in the ledger yet) gets a
    payload `since`, the binding file's last modification time in UTC (`YYYY-MM-DDTHH:MM:SSZ`).
    `ccp/health.py` `adopted_at`: the latest event's `since` when it has one, else its `at`.
    `contracts/observability_event.schema.json`'s description and `docs/spec/04-observability.md`'s
    `plane`/`adopted` payload row name `since?` (§31.1).
  - `ccp/notify.py` `cmd_fire`: with neither `--task` nor `--id` it refuses (exit 2), recording nothing,
    after the sandbox check.
  - `ccp/health.py` `uncovered`: a commit whose every path is in the task log or names a SPEC file
    (`tasklog._names_spec` over `task_log.spec_paths`) is covered.
  - `docs/spec/02-delivery.md` §10.7. CURRENT (at `85d388b`): "4. it changes nothing outside the task log (its task files, `INDEX.yaml`, the reconcile log)." PROPOSED:
    > 4. it changes nothing outside the task log (its task files, `INDEX.yaml`, the reconcile log) and the SPEC files (`task_log.spec_paths`): the lead's own task-log commits and spec rulings, however they were merged.
  - `docs/spec/01-model.md` §4.5. CURRENT (at `85d388b`, over two lines): "when the queue's ledger holds no such event yet (a queue from before the event, re-adopted); a rerun on an adopted product records nothing." PROPOSED:
    > when the queue's ledger holds no such event yet (a queue from before the event, re-adopted), with `since`, the binding file's last change, as the adoption point `ccp health` reads in place of the event's time; a rerun on an adopted product records nothing.
  - `docs/spec/01-model.md` §3.6. CURRENT (at `85d388b`): "- **Test notice.** In a sandbox only (§29.3), `ccp notify fire <trigger>` fires a notice as a step would: the `pending` record, the command channel, the rendered notice." PROPOSED:
    > - **Test notice.** In a sandbox only (§29.3), `ccp notify fire <trigger>` fires a notice as a step would: the `pending` record, the command channel, the rendered notice. It needs `--task` or `--id`, as every step that fires one gives; without either it refuses (exit 2) and records nothing.
  - Each PROPOSED passage replaces its CURRENT text on a line of its own, unwrapped, so `ccp verify
    spec-text` finds it. `docs/cli/01-model.md` and `docs/cli/05-operations.md` (the `ccp notify fire`
    rows) and `docs/cli/02-delivery.md` (the `ccp tasks orphans` row) follow in one clause each.
  - Tests: `tests/test_tasks_migrate.py`, `tests/test_init.py`, `tests/test_health.py`,
    `tests/test_notify.py`, `tests/test_orphans.py`.
- **Out:**
  - Correcting an adoption event already backfilled at a rerun's time (`ccp health --since` covers that
    queue).
  - Recognising a ruling by its `spec(<id>):` subject or a trailer.
  - Other earlier-generation table shapes than the two described.

## dod_checks

- id: `mig-01`
  story: As a lead adopting a product of that generation, its old task files convert.
  setup: a scratch product (`tests/helpers.py`) with two old task files: `0001-a` done, and `0002-b` done whose `## Meta` table has backticked rows `task_id`, `status` `done`, `depends_on` `["0001-a"]`, `created` `2026-01-02`, and whose `## Refs (required for verifier packet)` table has the row `` | `spec_refs` | `docs/SPEC.md#first-part`, `docs/SPEC.md#second-part` | ``; the product has `docs/SPEC.md`.
  steps:
    1. Run `ccp tasks migrate`, then `ccp tasks check`.
  expect: `0002-b` is converted with `spec_refs` `["docs/SPEC.md#first-part", "docs/SPEC.md#second-part"]` and `depends_on` `["0001-a"]`; `ccp tasks check` exits 0.
  dry run: n/a — at `85d388b` it reports "no SPEC section in its Refs table" for `0002-b`.
- id: `mig-02`
  story: As a lead, a file that still cannot convert says which row.
  setup: the product of mig-01 with a third file whose Refs row is `` | `spec_refs` | `docs/OTHER.md#x` | ``.
  steps:
    1. Run `ccp tasks migrate --dry-run`.
  expect: the third file's line names the `Refs` heading and the row `spec_refs` with its value `docs/OTHER.md#x`; the file is unchanged.
  dry run: n/a.
- id: `ini-01`
  story: As a product adopted before the adoption event, my adoption point is my adoption, not my next rerun.
  setup: a scratch product adopted with `ccp init`, its ledger then emptied of `plane`/`adopted` events, and its binding file's modification time set to `2026-01-05T10:00:00Z`.
  steps:
    1. Run `ccp init --project-id <id>` again, then again, then `ccp health --json`.
  expect: one `plane`/`adopted` event, payload `binding` `kept` and `since` `2026-01-05T10:00:00Z`; health's `adopted_at` is `2026-01-05T10:00:00Z`.
  dry run: n/a.
- id: `ntf-01`
  story: As an operator, a test notice always says what it is about.
  setup: a sandbox (`ccp sandbox create`).
  steps:
    1. Run `ccp notify fire decision` there, then `ccp notify pending`.
    2. Run `ccp notify fire decision --id Q1`, then `ccp notify pending`.
  expect: step 1 exits 2 naming `--task` and `--id`, and pending lists nothing; step 2 exits 0 and pending lists one `decision` notice with id `Q1`.
  dry run: n/a — at `85d388b` step 1 exits 0 and records a notice.
- id: `orp-01`
  story: As a lead, my own task-log and SPEC commits are not orphans, but a mixed one is.
  setup: a scratch product whose integration branch has, after a ref R, a squash commit changing a task file and `docs/spec/x.md`, and one changing `docs/spec/x.md` and `src/app.py`.
  steps:
    1. Run `ccp tasks orphans --since R --json`.
  expect: exit 1; `uncovered` lists only the second commit.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, `ccp verify spec-text 0152`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 — Built at `c5f6079`; the measured premise (`git grep -n "notify.fire(" -- ccp`: 3 sites, each
  with `task_id=`) holds there.
  - Migrate: `heading` finds `## <name>` with or without a note after a space; `table(..., raw=True)` keeps
    the Refs values only trimmed, so `spec_refs` can split a value into its backticked items (else on commas).
    A `<path>#<anchor>` item is kept when `tasklog._names_spec` names its path; anything else is read for
    `§N`/`SN` as before. `depends_on` is read when `Depends on` is absent, and a `[...]` value is unwrapped
    first. A file with no SPEC section gets `(<heading line>: <key> = <raw value>; …)` or
    `(no Refs heading)` after the old reason, so the reason still starts as before.
  - Adoption: `record_adoption` takes the binding path; a backfilled (kept) event carries `since`, the
    binding file's mtime in UTC. `adopted_at` returns the latest event's `since` when it parses, else its
    `at`; the latest event is still chosen by `at`.
  - Test notice: the refusal sits after the sandbox and `upgrade` checks, before the queue is resolved.
  - Orphans: `in_log` also passes a path `tasklog._names_spec` names under `task_log.spec_paths`.

## Verification notes
