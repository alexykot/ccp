---
task_id: 0202-forecast-and-health-report-task-supply
title: The forecast and health name the accepted decisions that no task cites yet
status: pending
kind: feature
depends_on: []
clashes_with: ["0204-spec-descriptions-catch-up"]
spec_refs: ["S26", "S27"]
review_point: R14
paths: ["ccp/adr.py", "ccp/forecast.py", "ccp/health.py", "docs/spec/04-observability.md", "tests/test_task_supply.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0202-forecast-and-health-report-task-supply

## Intent

The forecast replays only the tasks that exist, and health measures only the tasks that ran. Neither
tells the lead that decisions have been accepted but nobody has written their tasks, which is how
runners come to starve. After this task, `ccp forecast` and `ccp health` name the accepted ADR
decisions that no task cites yet, so the lead sees that the backlog forecast leaves out work already
decided. Both only read: nothing new is recorded.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/forecast.py` `text` prints "Review point …" and "Open backlog" only, built from the task log's
  open tasks (`git grep -n '"Open backlog"' ccp/forecast.py` at `58cf1d0`: one line). Nothing in
  `forecast.py` or `health.py` reads ADR decisions (`git grep -n 'decision_states\|not_built' ccp/forecast.py ccp/health.py`
  at `58cf1d0`: no line). `cmd_forecast` prints `forecast.run`'s dict as `--json`, and `health.main`
  builds its own output, so `ccp/cli.py` needs no change.
- `ccp/adr.py` already reads each ADR's status and decision states: `load(cfg)` and
  `decision_states(m)`, where a state is one of `not_built`, `built`, `live` or `retired`. A task
  cites a decision through `adr_refs` (`"0040 D1"`), and `tasklog.adr_number` parses the ADR's
  number.
- An example of the gap: ADR-0040 is `accepted`, with D1 to D6 all `not_built`, and no task cites it
  (`git grep -n 'adr_refs:.*0040' -- docs/delivery/tasks/` at `58cf1d0`: no line).
- The other half of the proposal, runner slots idle with nothing ready, needs a new ledger event
  with a new writer, which adds a row to §23.7's writers table. It waits for a signed task.
- The SPEC text below describes only what this task builds (§31.1). It adds one bullet each to
  §26.4 and §27.1.
- Task 0204 also edits §27.1 (its Window bullet), hence the clash.

## Scope

- **In:** `ccp/adr.py`, `ccp/forecast.py`, `ccp/health.py`, `docs/spec/04-observability.md`,
  `tests/test_task_supply.py` (new).
- **Untasked decisions.** `adr.untasked(cfg, tasks) -> list[{"adr", "decisions"}]`:
  - it reads every ADR whose status is `accepted` or `in-progress`, and each of its decisions whose
    state is `not_built`;
  - it keeps those that no task cites, a `dropped` task excepted. A ref with a decision
    (`"0040 D2"`) cites that decision; a ref naming only the ADR (`"ADR-0040"`, `"0040"`) cites
    all of them;
  - it returns them by ADR number, each ADR with its decision ids in order. Without an `adr` block it
    returns `[]`.
- **`ccp health`** gains `task_supply` in `--json`, `{"untasked_decisions": [...]}`, and one text
  line: `Task supply: <n> accepted decision(s) not tasked (ADR-0040 D1-D6, …)`. The ADR list shows
  at most 5 ADRs, then `…`. The line is left out when the list is empty.
- **`ccp forecast`** gains `untasked_decisions` in `--json` (the same list), and after the backlog
  block the text line `Not yet tasked: <n> accepted decision(s) in <m> ADR(s); the backlog above
  leaves them out`. The line is left out when the list is empty.
- **SPEC (§31.1), in `docs/spec/04-observability.md`:**
  - §26.4's **Output** bullet gains: "It also lists the decisions of accepted ADRs that no task cites
    (`untasked_decisions`), which the backlog leaves out."
  - §27.1 gains a bullet placed just before "**Diagnostic only.**": "- **Task supply:** the
    `not_built` decisions of `accepted` and `in-progress` ADRs that no task cites (a dropped task does
    not count); `task_supply` in `--json`."
- **Tests** in `tests/test_task_supply.py` (new), on temp products:
  - `untasked`: a decision cited by a pending task, one cited only by a dropped task, a ref naming
    only the ADR, a `built` decision, and a `proposed` ADR, each counted or not as the Scope says;
  - the health text line and `--json` key, and the forecast line, appear with a non-empty list and
    are absent with an empty one.
- **Out:** idle runner slots (a new event and writer, for a signed task), the board (a later task may
  show the same figures), and drafting the tasks themselves.

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
    2. Run `ccp --root . forecast --backlog --json | python3 -c "import json,sys; print(len(json.load(sys.stdin)['untasked_decisions']))"`.
  expect: both exit 0. When step 2 prints a number above 0, step 1 has a `Not yet tasked:` line
    after the backlog block; when it prints 0, step 1 has no such line.
  dry run (`58cf1d0`): step 1 exits 0, with an "Open backlog" block and no such line; step 2 fails,
    the key being absent.

- id: `ts-03`
  story: As a plane developer, the measure is tested and the tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `adr.untasked` keeps decisions cited by dropped tasks out of its result.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_task_supply 2>&1 | tail -20`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_task_supply`.
  expect: step 1 exits 0 with the Scope's tests listed `ok`; step 2 has at least one failure.
  dry run: n/a — the module is new.

- id: `ts-04`
  story: As the SPEC reader, both lists are described.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n 'untasked_decisions\|Task supply\|Diagnostic only' docs/spec/04-observability.md`.
  expect: the §26.4 sentence and the §27.1 bullet, each exactly as PROPOSED, the bullet's last line
    just before the "Diagnostic only" bullet.
  dry run (`58cf1d0`): prints only the "Diagnostic only" line.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `adr.untasked(cfg, tasks)` in `ccp/adr.py`: the decision ids are the bare ids `decision_states` gives (`"1"`,
  `"2a"`), `adr` is the id string (`ADR-0040`). A decision cited as `D2` is the ADR's `2`.
- `ccp health`: `task_supply` is set in `collect`'s `files` block (so `--json` has it; the forecast's
  `health.collect(files=False)` does not), `null` if the ADR read fails. The text line comes from
  `health.supply_text`, printed after the budget lines; it is not in `summary_text` (the architect's view).
  Choices the task left open: consecutive plain numbers join as a range (`D1-D6`, also `D1-D2`), ranges
  and lone ids within one ADR are joined with `,` and no space (`D1,D3-D4`), and ADRs with `, `.
- `ccp forecast`: `untasked_decisions` is added in `forecast.run`, not `collect`, so the board's forecast
  is unchanged. The text line shows for the whole text and `--backlog`, not for `--point`.

Fix round 1 (review of PR #240):
- The forecast's `note` path (no open task, or none with an estimate) now prints the `Not yet tasked:` line
  after the note when the list is non-empty and the view is not `--point`: that is the starvation case the
  line is for. It replaces the earlier choice above to leave the line out there.
- Tests added: the `--point` view, both `note` cases and the `note` case with every decision cited for the
  forecast; a `D2a`-style decision id in the health line. The text tests now assert the count and the ADR
  list, not the whole prose line.

## Verification notes
