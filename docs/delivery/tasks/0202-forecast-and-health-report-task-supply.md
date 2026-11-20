---
task_id: 0202-forecast-and-health-report-task-supply
title: The forecast and health report task supply - accepted decisions not yet tasked, and slots idle with nothing ready
status: pending
kind: feature
depends_on: []
spec_refs: ["S6", "S16", "S23", "S26", "S27"]
review_point: R14
paths: ["ccp/adr.py", "ccp/forecast.py", "ccp/health.py", "ccp/cli.py", "docs/spec/04-observability.md", "tests/test_task_supply.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0202-forecast-and-health-report-task-supply

## Intent

The forecast replays only the tasks that exist, and health measures only the tasks that ran. Neither
tells the lead when the runners are about to starve: decisions are accepted but nobody has written
their tasks, or runner slots sit free because nothing is ready. After this task:
- `ccp forecast` and `ccp health` name the accepted ADR decisions that no task cites yet, so the lead
  sees that the backlog forecast leaves out work already decided;
- `ccp health` reports how long runner slots sat free while `ccp tasks next` had nothing ready, from a
  ledger event that `next` records.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/forecast.py` `text` prints "Review point …" and "Open backlog" only, built from the task log's
  open tasks (`git grep -n '"Open backlog"' ccp/forecast.py` at `58cf1d0`: one line). Nothing in
  `forecast.py` or `health.py` reads ADR decisions (`git grep -n 'decision_states\|not_built' ccp/forecast.py ccp/health.py`
  at `58cf1d0`: no line).
- `ccp/adr.py` already reads each ADR's status and decision states: `load(cfg)` and
  `decision_states(m)`, where a state is one of `not_built`, `built`, `live` or `retired`. A task
  cites a decision through `adr_refs` (`"0040 D1"`), and `tasklog.adr_number` parses the ADR's
  number.
- An example of the gap: ADR-0040 is `accepted`, with D1 to D6 all `not_built`, and no task cites it
  (`git grep -n 'adr_refs:.*0040' -- docs/delivery/tasks/` at `58cf1d0`: no line).
- `ccp tasks next` prints "nothing ready" and exits 3, and records nothing
  (`git grep -n 'nothing ready' ccp/cli.py` at `58cf1d0`: the print in `cmd_tasks_next`, no `emit` near it). A
  claim records `lease`/`set` with its `holder`, and the lead's `runner`/`stop` ends a runner. So the
  start of an idle stretch is the one fact the ledger is missing.
- `parallel.active_tasks(cfg, q, work)` lists the tasks held now, and `parallel.max_in_flight` is the
  slot count (§16).
- The SPEC text below describes only what this task builds (§31.1). It adds one event op to §23's
  table and one bullet each to §26.4 and §27.1.

## Scope

- **In:** `ccp/adr.py`, `ccp/forecast.py`, `ccp/health.py`, `ccp/cli.py`,
  `docs/spec/04-observability.md`, `tests/test_task_supply.py` (new).
- **Untasked decisions.** `adr.untasked(cfg, tasks) -> list[{"adr", "decisions"}]`:
  - it reads every ADR whose status is `accepted` or `in-progress`, and each of its decisions whose
    state is `not_built`;
  - it keeps those that no task cites, a `dropped` task excepted. A ref with a decision
    (`"0040 D2"`) cites that decision; a ref naming only the ADR (`"ADR-0040"`, `"0040"`) cites
    all of them;
  - it returns them by ADR number, each ADR with its decision ids in order. Without an `adr` block it
    returns `[]`.
- **Starved slots.** When `ccp tasks next` exits 3 ("nothing ready") with `QUEUE_ROOT` set, it emits
  `runner`/`starved` `{in_flight, slots}`: the tasks held now and `parallel.max_in_flight` (1 when
  parallel work is off). It emits nothing when `in_flight >= slots`, and nothing when the ledger's
  latest `runner`/`starved` event came after the latest `lease`/`set` (an idle stretch already open).
  - `health.starved(q, start)` reads the ledger. A stretch opens at a `runner`/`starved` event and
    ends at the first later `lease`/`set`, `runner`/`stop` or `runner`/`spawn`, or at now. Its
    idle slot-hours are its hours times (`slots` − `in_flight`) as recorded at its start. It returns
    `{"stretches", "hours", "slot_hours"}` over the stretches that end at or after `start` (the
    health window), clipped to it.
- **`ccp health`** gains `task_supply` in `--json`, `{"untasked_decisions": [...], "starved": {...}}`,
  and one text line: `Task supply: <n> accepted decision(s) not tasked (ADR-0040 D1-D6, …); slots
  idle with nothing ready: <h> slot-hour(s) in <k> stretch(es)`. The ADR list shows at most 5 ADRs,
  then `…`.
- **`ccp forecast`** gains `untasked_decisions` in `--json` (the same list), and after the backlog
  block the text line `Not yet tasked: <n> accepted decision(s) in <m> ADR(s); the backlog above
  leaves them out`. Nothing is printed when the list is empty.
- **SPEC (§31.1), in `docs/spec/04-observability.md`:**
  - §23's event table gains the row: "| `runner` | `starved` | `in_flight`, `slots` (`ccp tasks
    next` found nothing ready with a slot free, §27.1) |".
  - §26.4's **Output** bullet gains: "It also lists the decisions of accepted ADRs that no task cites
    (`untasked_decisions`), which the backlog leaves out."
  - §27.1 gains a last bullet: "- **Task supply:** the `not_built` decisions of `accepted` and
    `in-progress` ADRs that no task cites (a dropped task does not count), and the stretches when
    runner slots sat free with nothing ready: from `ccp tasks next`'s `runner`/`starved` event to the
    next claim, `runner`/`stop` or `runner`/`spawn`, in slot-hours; `task_supply` in `--json`."
- **Tests** in `tests/test_task_supply.py` (new), on temp products and temp queues:
  - `untasked`: a decision cited by a pending task, one cited only by a dropped task, a ref naming
    only the ADR, a `built` decision, and a `proposed` ADR, each counted or not as the Scope says;
  - `next` exiting 3 with one of two slots held emits one `starved` event, and a second exit 3
    before any claim emits none;
  - `starved` sums a stretch closed by a claim and one still open, in slot-hours;
  - the health text line and `--json` key, and the forecast line, appear with a non-empty list and
    are absent with an empty one.
- **Out:** the board (a later task may show the same figures), and drafting the tasks themselves.

## dod_checks

- id: `ts-01`
  story: As a lead, I see the accepted decisions that no task cites yet.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp --root . health --json | python3 -c "import json,sys; d=json.load(sys.stdin)['task_supply']; print([u['adr'] for u in d['untasked_decisions']])"`.
    2. Run `git grep -n 'adr_refs:.*0040' -- docs/delivery/tasks/`.
  expect: step 1 exits 0. When step 2 prints nothing, step 1's list includes `ADR-0040`; when step 2
    prints a line, the list leaves `ADR-0040` out.
  dry run (`58cf1d0`): `ccp --root . health --json` exits 0 with no `task_supply` key; step 2 prints
    nothing.

- id: `ts-02`
  story: As a lead, the forecast says what the backlog leaves out.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp --root . forecast --backlog`.
  expect: the output has a `Not yet tasked:` line after the backlog block, naming a count of at least
    1.
  dry run (`58cf1d0`): exit 0, an "Open backlog: 6 remaining" block and no such line.

- id: `ts-03`
  story: As a plane developer, the supply measures are tested and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `adr.untasked` keeps decisions cited by dropped tasks out of its result.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_task_supply 2>&1 | tail -20`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_task_supply`.
  expect: step 1 exits 0 with the Scope's tests listed `ok`; step 2 has at least one failure.
  dry run: n/a — the module is new.

- id: `ts-04`
  story: As the SPEC reader, the event and both measures are described.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n 'starved\|untasked_decisions\|Task supply' docs/spec/04-observability.md`.
  expect: the §23 row, the §26.4 sentence and the §27.1 bullet, each exactly as PROPOSED.
  dry run (`58cf1d0`): prints nothing.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
