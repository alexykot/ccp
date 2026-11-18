---
task_id: 0135-queue-legacy-archive
title: ccp plane check names every queue entry the plane does not write, and --archive moves them to QUEUE_ROOT/_legacy/<date>/
status: pending
kind: feature
depends_on: []
spec_refs: ["S31", "S29", "S4"]
review_point: R9
paths: ["ccp/queue.py", "ccp/plane.py", "ccp/cli.py", "ccp/init.py", "docs/spec/05-operations.md", "docs/cli/05-operations.md", "tests/test_plane_check.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0135-queue-legacy-archive
## Intent

A product re-adopted on a queue an earlier plane generation used learns, from `ccp init` and
`ccp plane check`, every file in that queue the current plane does not write, and moves them all out of
the way with one command that never deletes anything, after which `ccp plane check` is green.

## Context (not checked)

- A re-adopted product reuses its queue root through the kept binding. Files an earlier generation
  wrote stay there: queue scripts the plane no longer ships, and loose files at the queue root (old
  task briefs, run scripts, backups, an old `work.json` copy). Seats may not edit the queue by hand, so
  today the only way out is an operator's by-hand archive.
- What `ccp plane check` reads today: `queue.script_drift` (`"def script_drift"` in `ccp/queue.py`),
  which walks `QUEUE_ROOT/scripts/` only and names each file `unknown`, `drifted` or `retired`
  (`RETIRED_SCRIPTS`); a file at the queue root, or in any other directory, is named by nothing. Probe
  (`ccp sandbox create`, then a `run-task.sh` at the queue root and an extra `scripts/queue/claim.sh`,
  then `ccp plane check` at `921507e`): it lists the script only and says nothing of `run-task.sh`.
- The plane has no list of what it keeps at the queue root; this task makes one. The top-level
  names the code joins to a queue path, measured by
  `git grep -hoP '\b(q|queue|root|queue_root)\s*/\s*"[^"/]+"' -- ccp scripts/observability` at
  `921507e` (less the product-root names the same search finds: `.claude`, `.gitignore`, `CLAUDE.md`,
  `README.md`, `docs`): `architect.json`, `auth`, `board`, `escalations`, `estimates`, `health`,
  `locks`, `observability`, `plane`, `progress`, `prompts`, `queue` (the state markers,
  `"def set_marker"`), `questions`, `reviews`, `runs`, `scripts`, `tasks`, `verification`, `work.json`,
  `worktrees`; and two an older layout left that the code still reads as fallbacks, so they stay owned
  while it does: `project.yaml` (the retired queue copy of the binding, §8.3) and `durable`
  (`"def load_durable_statuses"`). Beside them, the lock files `work.json.lock` and `architect.lock`
  (`git grep -n 'work.json.lock\|architect.lock' -- ccp scripts/observability`). The implementer
  re-runs the searches at its base, over all of `scripts/` and `plugin/` as well (they add at least `review/`, from `scripts/formal-submit.template.sh`, and `product-docs-check.json`, from `scripts/sync-product-docs.sh`), and adds any name missing here; a name it cannot place is a scope
  question.
- **No plane code runs a copy in `QUEUE_ROOT/scripts/`:** the seats run the plane's own scripts by
  absolute path (`ccp init --permissions`, §4.5). `git grep -n '/ "scripts"' -- ccp scripts/observability plugin`
  at `921507e`: every hit joins `PLANE` but one, `script_drift`'s own `q / "scripts"`. So a drifted copy is not replaced with the
  plane's: it is archived like an unknown one. A byte-identical copy stays, as today (it is no
  finding); the binding's own auth-check script (`auth_check.script`, §30) stays too.
- Footprint leftovers in the product repository (managed copies of agents, skills and hooks) are
  already reported by `scripts/sync-product-docs.sh --check` (§9.5) and removed by a sync, and they are
  tracked product files, which the queue's archive must not take. They are out of scope.
- "A release declares what it retires" is not needed as a new rule: an ownership list makes every
  entry not on it a finding, whatever release dropped it. `RETIRED_SCRIPTS` keeps its role (a clearer
  message for a known script).
- §31.1: the SPEC text below only describes this task's own feature.

## Scope

- **In:**
  - `ccp/queue.py`: `QUEUE_OWNED`, the top-level names of Context (plus `_legacy`, the archive itself),
    each with a comment naming the SPEC section that describes it; `queue_leftovers(q)` returns each
    top-level entry not in it as `unknown: <name>` (a directory once, with a trailing `/`), after
    `script_drift`'s findings.
  - `ccp/plane.py` `check`: prints `scripts` as today and a new `root` list from `queue_leftovers`;
    exit 1 when either is non-empty.
  - `ccp plane check --archive` (new flag, `ccp/cli.py`): moves every entry `check` lists (the root
    entries, and the `unknown`, `drifted` and `retired` scripts) to
    `QUEUE_ROOT/_legacy/<YYYY-MM-DD>/<its path relative to QUEUE_ROOT>`, the date in UTC; never deletes
    a file. An entry whose target already exists is left in place and listed under `not_moved` with the
    reason. Its JSON adds `archived` (each path moved, with its target) and `not_moved`. It then runs the
    check again and exits as the check does.
  - `ccp/init.py`: when the queue it keeps already holds entries `plane check` would list, the result's
    `warnings` names their count and the command `ccp plane check --archive`; it moves nothing.
  - §31.1: `docs/spec/05-operations.md` §31.3, one bullet under **Checks** describing the root listing
    and `--archive`; `docs/cli/05-operations.md`, a row for `ccp plane check [--archive]`.
- **Out:**
  - The board's and `ccp tasks claim`'s warnings (they stay on `scripts/`).
  - Anything in the product repository.
  - Deleting anything, or moving a byte-identical script copy.

## dod_checks

- id: `cmd-01`
  story: As a lead re-adopting a product, I see every leftover in my queue.
  setup: a sandbox from `ccp sandbox create S`, its `env` lines exported; in its queue, a file `run-task.sh` and a directory `old-briefs/` with one file at the root, `scripts/queue/claim.sh` with any content, and `scripts/gate.sh` holding the plane's `scripts/gate.sh` plus one extra line.
  steps:
    1. Run `ccp plane check` in the sandbox's product root.
  expect: exit 1; `root` lists exactly `unknown: run-task.sh` and `unknown: old-briefs/`; `scripts` lists the drifted `scripts/gate.sh` and the unknown `scripts/queue/claim.sh`; no plane-owned entry (`board`, `work.json` and the rest) is listed.
  dry run (`921507e`): exit 1, `scripts` listed the two scripts; `run-task.sh` was not named (the gap this task closes).
- id: `cmd-02`
  story: As a lead, one command archives them and nothing is lost.
  setup: the sandbox of cmd-01.
  steps:
    1. Run `ccp plane check --archive`.
    2. Run `ccp plane check`.
  expect: step 1 lists the four entries under `archived`, each now under `QUEUE_ROOT/_legacy/<today, UTC>/` at its old relative path with its content unchanged, and exits 0; step 2 exits 0 with both lists empty.
  dry run: n/a — `--archive` is added by this task.
- id: `cmd-03`
  story: As an operator, an archive never overwrites an earlier one.
  setup: the sandbox of cmd-02, then a new `run-task.sh` at the queue root.
  steps:
    1. Run `ccp plane check --archive` again the same day.
  expect: `run-task.sh` is under `not_moved` with a reason naming the existing target; both files still exist; exit 1.
  dry run: n/a.
- id: `cmd-04`
  story: As a lead re-adopting, init tells me about the leftovers.
  setup: a sandbox from `ccp sandbox create S` whose queue holds a `run-task.sh` at its root.
  steps:
    1. In `S/product`, run `CCP_BINDINGS_DIR=S/bindings ccp init` (the sandbox's own bindings directory, so the installation's is never touched).
  expect: exit 0; `warnings` names one leftover and `ccp plane check --archive`; `run-task.sh` is still at the queue root.
  dry run: n/a.
- id: `cmd-05`
  story: As a product with an auth-check script and a clean copy, I am not told to move them.
  setup: a sandbox whose binding names `auth_check.script: scripts/auth-check.sh`, that file in its queue, and a byte-identical copy of the plane's `scripts/gate.sh` in the queue's `scripts/`.
  steps:
    1. Run `ccp plane check --archive`.
  expect: exit 0; nothing is listed or archived; both files are where they were.
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

- 2026-11-18 (implementer): `ccp/queue.py` gains `QUEUE_OWNED` (each name with its SPEC section),
  `leftover_entries`/`queue_leftovers` and `script_findings` (the structured form `script_drift` now
  formats; its messages are unchanged). `ccp plane check` adds `root`; `--archive` (`plane.archive`)
  moves the scripts it lists, then the root entries, to `_legacy/<UTC date>/<relative path>` with
  `os.rename`; `archived` and `not_moved` rows are `{path, target[, reason]}`, relative to QUEUE_ROOT,
  a directory's ending in `/`. `ccp init` warns with the count. Tests: `tests/test_plane_check.py`.
- Names added to the Context's list after re-running its searches over `scripts/`, `plugin/` and the
  constants the code joins: `review`, `product-docs-check.json` (as the Context says), `estimator` and
  `estimator.lock` (`ccp/estimator.py` `DIR`, `LOCK`), `architect.json.lock` (the architect state
  file's own lock, `architecture_review.state_lock`), and `docs-audit.json`, `docs-audit.lock` (still
  read as old records by `seats._headless`, §19.12).
- Choices beyond the text: a root entry named `*.tmp` is not listed (an atomic write's temporary file,
  as `script_drift` already skips); the binding's `auth_check.script` is not listed at the root either;
  `--archive` writes no ledger event (no event type exists for it); an entry that cannot be moved
  (an `OSError`) is listed under `not_moved` with the error, like an existing target.

## Verification notes
