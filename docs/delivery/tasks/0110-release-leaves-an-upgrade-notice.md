---
task_id: 0110-release-leaves-an-upgrade-notice
title: A release leaves each bound product an upgrade notice its lead gets at its next session start
status: pending
kind: feature
depends_on: ["0109-upgrade-notes-and-status"]
spec_refs: ["S3", "S29"]
adr_refs: ["0041 D3"]
review_point: R7
sign_off: brief
paths: ["scripts/run-checkout.sh", "scripts/release.sh", "ccp/notify.py", "ccp/upgrade.py", "ccp/cli.py", "docs/spec/01-model.md", "docs/spec/05-operations.md", "tests/test_notify*.py", "tests/test_upgrade*.py", "tests/test_run_checkout*.py"]
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0110-release-leaves-an-upgrade-notice
## Intent

After a release, each bound product's lead learns at its next session start what arrived and what
to adopt, through the plane's notify path, without anyone relaying it by hand.

## Context (not checked)

- ADR-0041 D3. The notice goes through the notify path of ADR-0039: the plane renders and records, the lead dispatches.
- `release.sh` already checks each bound product after a release (§29.3) through `scripts/run-checkout.sh`.
- The notice is recorded in the product's queue, which is plane runtime; the release still writes nothing to a product's repository.

## Scope

- **In:**
  - `docs/spec/01-model.md` §3.6, the trigger table. CURRENT (at `7094dfe`): none; a new row after `allowance_checkpoint`. PROPOSED:
    > | `upgrade` | `scripts/run-checkout.sh update`, for each bound product with an `adopt` step it has not taken among the tasks the release brought (§29.3) | the release's commit; the steps |
  - `docs/spec/05-operations.md` §29.3. CURRENT (at `7094dfe`): "It prints each product as clean or stale, with the checks that failed and their output, writes nothing to a product, and does not fail the release." PROPOSED:
    > It prints each product as clean or stale, with the checks that failed and their output, and records in each product's queue an `upgrade` notice (§3.6) listing the `adopt` steps of the release's tasks that the product has not taken (`ccp upgrade status`), or none when there are none. It writes nothing to a product's repository and does not fail the release.
  - `scripts/run-checkout.sh`: after the checks, `ccp notify` records the `upgrade` notice per product (with that product's queue root from its binding).
  - `ccp/notify.py`: the `upgrade` trigger and its rendering; orientation lists it among pending notices.
- **Out:**
  - Sending the notice anywhere: the lead dispatches it (ADR-0039).

## dod_checks

- id: `cmd-01`
  story: As a product's lead, a release leaves me a notice.
  setup: a scratch run checkout with one binding to a scratch product whose plane.json lacks a key that a task merged in the release names as its `adopt` step; a second binding whose product has taken it.
  steps:
    1. Run `scripts/run-checkout.sh update` with the new commit.
    2. Run `ccp notify pending` in each product's queue.
  expect: (1) prints both products' check results as before. (2) the first queue has one pending `upgrade` notice naming the step and the release commit; the second has none.
  dry run: n/a.
- id: `cmd-02`
  story: As a lead, orientation shows the notice.
  setup: the first product of `cmd-01`.
  steps:
    1. Run `ccp orientation` in it.
  expect: the output lists the pending `upgrade` notice with its step.
  dry run: n/a.
- id: `cmd-03`
  story: As a product owner, the release still writes nothing to my repository.
  setup: the scratch products of `cmd-01`.
  steps:
    1. Run `git status --porcelain` in each product after the update.
  expect: prints nothing for either.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §3.6 and §29.3 edits with the PROPOSED text above.
  expect: they match word for word, and no other § rule changes.
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

- 2026-11-17 (implementer): `ccp notify upgrade [--since COMMIT]` (ccp/notify.py `record_upgrade`)
  records the notice: the steps `ccp upgrade status` lists (not taken, or check by hand) whose task
  `ccp upgrade notes --since` lists, as one `notify` `pending` event with `id` = the plane checkout's
  HEAD (the release commit, full sha) and `reason` = `<task>: <adopt step>; …` (capped at the one-line
  limit, the rest counted with a pointer to `ccp upgrade status`). No steps: nothing recorded. It never
  runs `notify.command` (`RECORD_ONLY`; `send` and `fire` refuse it): the lead dispatches it. Actor:
  `$ACTOR` when it names one, else `plane-session`.
- `scripts/run-checkout.sh update` notes HEAD before the merge and, after each checked product's
  checks, runs the new `ccp notify upgrade --since <that commit>` with `--root <product_root>`,
  QUEUE_ROOT from the binding's `queue_root`, PROJECT_YAML and CCP_BINDINGS_DIR set to the binding.
  It skips the call when the update brought no commit; a missing queue or a failed call is one
  `run-checkout: upgrade notice for <id> not recorded: …` line, never a failed update. Products not
  checked (no repository, no branch, not adopted) get no notice. The steps are read in the product's
  checkout (as `ccp upgrade status` run there reads them), not the integration branch's temp clone.
- Orientation had no list of pending notices at the base. `plugin/hooks/orientation.sh` (outside the
  task's `paths`) now appends the product's `ccp notify pending` rows (subject, reason, the `sent`
  call), within the hook's cap, using the `ccp` beside the plugin, else `ccp` on PATH. `ccp
  orientation` prints the hook's text, so it shows them too. §9.3 carries no rule for it yet.

## Verification notes
