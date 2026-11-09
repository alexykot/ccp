---
task_id: 0012-retire-the-old-snapshot
title: Retire now.json, STATUS.md and their scripts
status: pending
kind: feature
depends_on: ["0008-spec-switch-to-parts"]
spec_refs: ["S23", "S28"]
adr_refs: ["0034 D7"]
review_point: R1
paths: ["scripts/observability/rebuild-now.sh", "scripts/observability/status.sh", "scripts/observability/lib.py", "scripts/observability/README.md", "scripts/queue/README.md", "contracts/observability_now.schema.json", "ccp/", "plugin/", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0012-retire-the-old-snapshot

## Intent

The board is the status: nothing writes or reads `observability/now.json` or `STATUS.md`, and `rebuild-now.sh` and `status.sh` are gone. Whatever still reads the snapshot reads the board instead.

## Context (not checked)

- §23.4 states the target rule; ADR-0034 D7 records the ruling.
- Before deleting, find every reader (hooks, team.py, health, tests) and move it to the board or the ledger.
- Old `now.json` files left in queues are ignored.
- Ruling `sm-20261109T225130Z-6af9` (spec maintainer, 2026-11-09): in this task's PR, (1) §17.8 deletes
  the sentence from "`now.json` has a top-level `questions` array…" through "…its `spec_maintainer`
  field is always `null` (deprecated)."; (2) `docs/spec/map/04-observability.md` keeps the §20.1.3
  row's history and changes only its last cell to say `now.json` and `STATUS.md` are retired (task
  0012); (3) §11.2 drops "docs-audit lock" from its list of process locks, a leftover of task 0010.
  The §31 approval for (1) and (3) is the operator's recorded rulings in `docs/spec/RULINGS.md` (the
  §20.1.3 row for task 0012, the §26.13 row for task 0010).

## Scope

- **In:** the two scripts, the snapshot writer, readers of the snapshot, schema status (deprecated), READMEs, tests.
- **Out:** the board; the ledger.

## dod_checks

- id: `code-01`
  story: As a plane developer, nothing writes or reads the old snapshot.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -E 'now\.json|STATUS\.md|rebuild-now|status\.sh' -- ccp scripts plugin`.
  expect: no match apart from a comment noting the retirement.
  dry run (`216cda1`): matches in scripts/observability (lib.py, rebuild-now.sh, status.sh, set-waiting-on.sh, prune-prompts.sh, README) and scripts/queue/README.md.
- id: `board-01`
  story: As an operator, the board shows what the snapshot showed.
  setup: a temporary queue with a waiting task, an open question and a gate.
  steps:
    1. Run `ccp board status`.
  expect: it lists all three and exits non-zero.
  dry run: n/a — the test this task adds builds the queue.

## Implementation notes

*Append-only, newest last.*

- 2026-11-09 (implementer): `scripts/observability/rebuild-now.sh` and `status.sh` are deleted. `lib.py`
  loses the snapshot writer and its CLI (`build_now`, `render_status_md`, `print_human`, `write_snapshot`,
  `cmd_rebuild`, `has_blockers`, `cmd_status`, `main`) and the helpers and constants only it used
  (`hours_between`, `round_hours`, `pid_alive`, the question, task, work, auth, running and seat-file
  loaders, `SCHEMA_VERSION`, `BLOCKER_KINDS`, `WAIT_BLOCKER_KINDS`). The event fold that
  `spec_maintainer.py` uses (`apply_event`, `accrue`, `new_task_state`) stays. No code in `ccp/` or
  `plugin/` read the snapshot, so no reader moved; the board already lists waits, gates and questions.
  `contracts/observability_now.schema.json` is marked deprecated. The READMEs and package docs, plus
  `docs/cli/04-observability.md`, `docs/design/board.md`, `docs/design/observability.md` and
  `queue/README.md`, now name the board as the status; the one remaining match for code-01 is the
  retirement note in `scripts/observability/README.md`. The backstop and stale-blocker tests check
  the board and `ccp board status` instead of the snapshot; `tests/test_snapshot_retired.py` is new.
  SPEC §17.8 (`docs/spec/02-delivery.md`) still describes `now.json`'s `questions` array: left for a
  SPEC edit.
- 2026-11-09 (implementer, round 2): `origin/main` (tasks 0010 and 0011) merged in; the
  `scripts/CLAUDE.md` and `scripts/observability/CLAUDE.md` conflicts keep both tasks' changes, and
  `lib.py` keeps task 0010's retirement comments. Ruling `sm-20261109T225130Z-6af9` applied: §17.8
  loses the `now.json` sentence, §11.2 loses the docs-audit lock, and the §20.1.3 map row's last cell
  says the snapshot is retired. The observability README describes the fold's wait-by-reason split
  instead of the snapshot's `wait_hours_by_reason`. Left for a ruling: §23.3 still names
  `wait_hours_by_reason`, and nothing now outputs the §23.3 timers; §18.3 says old snapshots holding
  `stale_seat` or `verify_stale` "stay readable", though nothing reads a snapshot any more.

## Verification notes

*Append-only.*
