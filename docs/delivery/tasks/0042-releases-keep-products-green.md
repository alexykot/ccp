---
task_id: 0042-releases-keep-products-green
title: A plane release keeps conforming products green
status: pending
kind: feature
depends_on: []
spec_refs: ["S29"]
review_point: R3
paths: ["scripts/sync-product-docs.sh", "scripts/run-checkout.sh", "docs/spec/05-operations.md", "tests/test_release.py", ".github/", "tests/test_sync*.py"]
created: 2026-11-09
updated: 2026-11-10
---

# Task: 0042-releases-keep-products-green

## Intent

When a plane release is installed, `ccp` checks each bound product's integration branch against the new rules and tells the lead what is now stale. A plane change that would make a conforming product fail ships its own fix-up (a migrate or regenerate command) and says so in the release notes.

## Context (not checked)

- Raised in triage of a managed product's tool proposals; the rules touched are §29.
- A release that renames a generator or tightens a check turns a product's integration branch red with no product commit; the first to notice is a verifier mid-task.

## Scope

- **In:** `sync-product-docs.sh` (or `run-checkout.sh update`) runs `ccp docs check`, `ccp adr check` and `ccp tasks check` per bound product read-only and prints what fails; §29 adds the rule that a breaking plane change ships a migrate command; the PR template asks whether the change breaks conforming products.
- **Out:** fixing a product's repo from the plane.

## dod_checks

- id: `check-01`
  story: As a lead, a release tells me what went stale.
  setup: a scratch product that passes the old checks and fails a tightened one.
  steps:
    1. Run the install step.
  expect: it names the product and the failing check, and writes nothing to the product.
  dry run: n/a — the behaviour does not exist yet.
- id: `check-02`
  story: As a lead, a green product stays quiet.
  setup: a conforming product.
  steps:
    1. Run the install step.
  expect: it reports the product as clean.
  dry run: n/a — the behaviour does not exist yet.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): the check lives in `scripts/run-checkout.sh update` (so `release.sh` runs it),
  after the fast-forward and the receiver restart. It reads the bindings in `CCP_BINDINGS_DIR` (default
  the run checkout's `projects/`) and runs the run checkout's new `bin/ccp` (`docs check`, `tasks check`,
  and `adr check` only when the product's `plane.json` has an `adr` block, since without one it exits 2)
  on each binding's `integration_branch` (default `main`): `origin/<branch>` as the product last fetched
  it, else the local branch, checked out in a `git clone --shared` in a temp dir. The product is only
  read (no fetch, no worktree, no index refresh). A product prints `clean` or `STALE` with the failing
  checks and the first 20 lines of each one's output; a binding with no repository or no such branch
  prints `not checked`. A stale product never fails the update. `sync-product-docs.sh` is unchanged.
- SPEC §29.3 gains two bullets (the migrate-command rule as Scope states it, and the release check). The
  task carried no CURRENT -> PROPOSED text, so the wording is the implementer's; flagged in the report.
- `.github/pull_request_template.md` (new) asks whether the change breaks conforming products. The release
  steps in `CLAUDE.md` and the `release.sh` header name the new check. Tests: `tests/test_sync_on_release.py`.
- `.github` joins `package_docs.exempt_dirs` in `docs/delivery/plane.json`: it holds GitHub's config, not
  source, so it carries no `CLAUDE.md` (the self-hosting docs check failed on it otherwise).
- 2026-11-10 (implementer, fix round 1): a binding whose integration branch has no
  `docs/delivery/plane.json` (a product that has not adopted `ccp`) now prints `not checked` and is
  skipped, rather than reported STALE on every release for a product that was never green. A failing
  check's output is cut to 20 lines with `sed -n` instead of `head`, which closed the pipe early and,
  under `pipefail`, killed the update when a check printed more than the pipe buffer, leaving the
  remaining products unchecked. The SPEC §29.3 bullets name the not-adopted case and the migrate-command
  bullet is reworded (same meaning). Tests: `test_a_product_that_has_not_adopted_ccp_is_not_checked`,
  `test_a_check_that_prints_a_lot_neither_kills_the_update_nor_floods_it`.

## Verification notes

*Append-only.*
