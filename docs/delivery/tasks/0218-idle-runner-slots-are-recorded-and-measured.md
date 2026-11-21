---
task_id: 0218-idle-runner-slots-are-recorded-and-measured
title: A runner slot left with nothing ready is recorded, and health reports the slot-hours idle
status: pending
kind: feature
depends_on: ["0202-forecast-and-health-report-task-supply"]
clashes_with: ["0243-one-source-for-syntax-events-and-config"]
spec_refs: ["S10", "S23", "S27"]
review_point: R15
paths: ["ccp/cli.py", "ccp/health.py", "scripts/observability/lib.py", "contracts/observability_event.schema.json", "plugin/agents/delivery-runner.md", "docs/spec/04-observability.md", "docs/cli/02-delivery.md", "tests/test_task_supply.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0218-idle-runner-slots-are-recorded-and-measured

## Intent

A runner that asks for its next task and gets "nothing ready" stops, and so does its slot. That time
is lost to the plan, not to the work, and nothing records it: health measures only the tasks that
ran. After this task, `ccp tasks next --holder <slot>` records a `runner`/`starved` event when it
finds nothing ready, the slot's next claim, stop or spawn ends the stretch, and `ccp health` reports
how many slot-hours went idle with nothing ready, beside the untasked decisions task 0202 reports.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: the second half of an accepted plane proposal (triage item T10), moved out of R14's
  task 0202 because it adds a ledger event and a writer (`grep -n 'idle runner slots' docs/delivery/tasks/0202-*.md`
  at `1b734dd`: one line, its **Out:** item).
- **`next` exits 3 on two paths.** `ccp/cli.py` `cmd_tasks_next`: `return 0 if t else 3` after the
  `--json` print, and `return 3` after the plain "nothing ready" line
  (`git grep -n 'return 0 if t else 3' -- ccp/cli.py` at `1b734dd`: one line; the plain return is the
  next `return 3` below it). Neither writes anything. Exit 7 (slots full) and exit 4 (architect) are
  other paths and record nothing here.
- **`next` has no slot.** Its parser takes `--scope`, `--json`, `--allow-overdue` and `--explain`
  (`git grep -n 'add_parser("next"' -A10 -- ccp/cli.py` at `1b734dd`). `ccp tasks claim` takes
  `--holder` with default `runner` (`git grep -n '"--holder", default="runner"' -- ccp/cli.py` at
  `1b734dd`: two lines, claim and rotation-due). The idle hook and the board also call `next`
  (`plugin/hooks/runner-idle.sh`, `parallel.next_choice`), so only a call naming its slot records.
- **The events that end a stretch.** `lease`/`set` carries `holder` (`ccp/lifecycle.py`,
  `emit(q, cfg, tid, "lease", "set", {"holder": holder}, ...)`). `runner`/`spawn` and `runner`/`stop`
  carry `slot` when the lead names slots, and none for the single runner
  (`grep -n '"runner", "stop"\|"runner", "spawn"' scripts/observability/team.py` at `1b734dd`: five
  lines).
- **The ledger's validation.** `scripts/observability/lib.py` lists the ops and each event's required
  payload keys (`("runner", "stop"): ("name", "reason")`), and
  `contracts/observability_event.schema.json` enumerates the ops; `starved` is in neither
  (at `1b734dd`,
  `grep -c starved scripts/observability/lib.py contracts/observability_event.schema.json`: 0 and 0). §23.2's event table has no `runner` row at all; §23.7 names the lead as the
  writer of the `runner` events.
- **Clash with R16's 0243**, which edits the same `ccp tasks next` row in `docs/cli/02-delivery.md`
  (it adds `--allow-overdue`), the event registry in `scripts/observability/lib.py` (a legacy-types
  tuple), and adds `tests/test_event_registry.py`, which will check this task's new op.
- **Depends on 0202**, which adds `task_supply` to `ccp health`, its text line, and the §27.1 bullet
  placed before "**Diagnostic only.**", and creates `tests/test_task_supply.py`. This task adds to
  each. The CURRENT below quotes the "**Diagnostic only.**" bullet, which 0202 leaves as it is.

## Scope

- **In:** `ccp/cli.py`, `ccp/health.py`, `scripts/observability/lib.py`,
  `contracts/observability_event.schema.json`, `plugin/agents/delivery-runner.md`,
  `docs/spec/04-observability.md`, `docs/cli/02-delivery.md`, `tests/test_task_supply.py`.
- **`ccp tasks next --holder <slot>`.** An optional argument, no default. With it and `QUEUE_ROOT`
  set, an exit 3, on the plain path and the `--json` path alike, appends a project-level event
  `runner`/`starved`, payload `{"slot": <slot>, "scope": <the scope's ids>, "in_flight": <the count of
  tasks the slot holds>}`, actor the caller's. Without `--holder` nothing is written. A write that
  fails is a `warning:` on stderr and never changes the exit code.
- **The duplicate guard.** Before writing, `next` reads the ledger for the slot's latest event among:
  `runner`/`starved` with that `slot`; `lease`/`set` with that `holder`; `runner`/`stop` or
  `runner`/`spawn` whose `slot` is it or which carries no `slot`. When that latest event is a
  `runner`/`starved`, nothing is written: the stretch is already open.
- **The ledger's rules.** `lib.py` adds the op `starved` and `("runner", "starved"): ("slot", "scope",
  "in_flight")`; the schema's `op` enum gains `starved`, and its `type` description names the event.
- **`health.starved(q, window)`.** Each stretch runs from a `runner`/`starved` event to the slot's next
  closing event (the same three kinds as the guard), or to now when none has come; the part inside
  the window counts. It returns `{"slot_hours", "stretches", "open"}` (`open`: the slots whose stretch
  is still running). `ccp health` puts it in `task_supply` as `idle_slots`, and prints
  `Idle slots: <h> slot-hour(s) with nothing ready (<n> stretch(es))` after the task-supply line,
  left out when `stretches` is 0.
- **The runner's definition** passes `--holder <your slot>` to every `ccp tasks next` it runs (the
  single runner `--holder runner`); `docs/cli/02-delivery.md`'s `ccp tasks next` row gains
  `[--holder <slot>]`.
- **Tests** in `tests/test_task_supply.py`:
  - `next --holder runner-1 --json` exiting 3 writes one `runner`/`starved`; a second call writes none;
    after a `lease`/`set` for `runner-1`, a third call writes one again;
  - the plain path writes it too; a call without `--holder` writes none;
  - `health.starved` over a starved event closed by a `runner`/`stop` two hours later gives
    `slot_hours` 2.0 and `stretches` 1; one with no closing event is in `open`;
  - the `Idle slots:` line appears with a stretch and not without.

### SPEC changes (signed in the brief, §31)

**a. §23.2, the event table.**

CURRENT (`docs/spec/04-observability.md` at `8aefa59`):
> | `lease` | `set`, `clear` | `holder`, `expires_at?` |

PROPOSED:
> | `lease` | `set`, `clear` | `holder`, `expires_at?` |
> | `runner` | `starved` (the lead's `runner` ops: §23.7) | `slot`, `scope`, `in_flight` (`ccp tasks next --holder <slot>` found nothing ready, exit 3; once per stretch, which the slot's next `lease`/`set`, or a `runner`/`stop` or `runner`/`spawn` for the slot or for every slot, ends, §27.1) |

**b. §23.7, the writers table.**

CURRENT (`docs/spec/04-observability.md` at `8aefa59`):
> | `events.jsonl` | the runner (task events); the lead (`question`/`answered`, `gate`/`decided`, `runner`/`spawn`, `bound`, `scope`, `rotate`, `stop`) |

PROPOSED:
> | `events.jsonl` | the runner (task events, and `runner`/`starved` through `ccp tasks next --holder`); the lead (`question`/`answered`, `gate`/`decided`, `runner`/`spawn`, `bound`, `scope`, `rotate`, `stop`) |

**c. §27.1, a bullet before Diagnostic only.**

CURRENT (`docs/spec/04-observability.md` at `8aefa59`):
> - **Diagnostic only.** Nothing here is a target for a worker or part of a DoD.

PROPOSED:
> - **Idle slots:** the slot-hours in the window that runner slots spent with nothing ready, from each
>   `runner`/`starved` event to the slot's next `lease`/`set`, `runner`/`stop` or `runner`/`spawn` (or
>   now), with the stretches counted and those still open named; `task_supply.idle_slots` in `--json`.
> - **Diagnostic only.** Nothing here is a target for a worker or part of a DoD.

- **Out:** the board, the forecast, a notice on a starved slot, and exit 7 (slots full), which is a
  wait for work in flight rather than a lack of ready work.

## dod_checks

- id: `st-01`
  story: As a lead, a slot left with nothing ready leaves one record per stretch.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_task_supply 2>&1 | tail -25`.
  expect: exit 0, with the Scope's four tests listed `ok`, beside 0202's.
  dry run: n/a — the module is 0202's and these tests are new.

- id: `st-02`
  story: As a plane developer, the duplicate guard is tested and the test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    guard always writes.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_task_supply`.
  expect: at least one failure (the second call writing a second event).
  dry run: n/a — the tests are new.

- id: `st-03`
  story: As a runner, `next` with my slot records the stretch on a real queue.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . tasks next --scope 0001 --holder runner --allow-overdue "dod check"; echo rc=$?`.
    2. Run `grep -c '"starved"' "$QUEUE_ROOT/observability/events.jsonl"`.
  expect: step 1 prints `rc=3` (0001 is done; `--allow-overdue` keeps a due architect pass from
    answering first); step 2 prints 1.
  dry run (`1b734dd`): without `--holder`, step 1 prints "nothing ready in scope" and `rc=3`; with it,
    argparse refuses `--holder` (exit 2).

- id: `st-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0218 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
