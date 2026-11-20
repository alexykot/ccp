---
task_id: 0204-spec-descriptions-catch-up
title: SPEC descriptions catch up with built behaviour
status: pending
kind: feature
depends_on: []
clashes_with: ["0202-forecast-and-health-report-task-supply"]
spec_refs: ["S13", "S19", "S23", "S25", "S27", "S31"]
review_point: R14
paths: ["docs/spec/02-delivery.md", "docs/spec/03-quality.md", "docs/spec/04-observability.md"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0204-spec-descriptions-catch-up

## Intent

Five SPEC passages describe behaviour that later tasks changed, so a reader who trusts them gets
the wrong answer. After this task, each one says what the code does, and nothing else changes: no
code, no rule. Every change is a description of built behaviour (§31.1).

## Context (not checked)

Measured at `58cf1d0`. Each item cites the code it describes. The verifier checks each PROPOSED
text against that code, not against this brief.

1. **§27.1's Window bullet** (plane proposals on task 0155) says the usage advice reads the whole
   queue. `ccp/health.py`'s docstring and `usage.advice_start` read it from `--since`, else
   `usage.advice.window_hours` back, and every request only when that key is zero
   (`git grep -n 'window_hours' ccp/health.py ccp/usage.py` at `58cf1d0`: the docstrings and
   `advice_start`). Health also says the rotation slots due now "judge each slot since its own spawn".
2. **§13.2's resolution-review refusals** (plane proposal on task 0168) list four refusals.
   `ccp/prompt.py` `resolution_gate` has six: it also refuses when the latest review that reported
   `done` is a resolution review judged `beyond`, and when the head cannot be read or fetched
   (`git grep -n 'raise QueueError' ccp/prompt.py` at `58cf1d0`, in `resolution_gate`: seven raises,
   one for a phase other than review, which the SPEC states apart).
3. **§23's `run`/`recorded` row** names `killed` and `survived` but not `unbuilt`. `ccp/mutate.py`
   emits `{"run_id", "mutants", **counts}` with `counts` over `killed`, `unbuilt` and `survived`
   (`git grep -n '"killed", "unbuilt", "survived"' ccp/mutate.py` at `58cf1d0`: one line).
4. **§19.6's "which needs `shape_from_task`"** (plane proposal on task 0192). Task 0192 relaxed it.
   `config._architect` turns `shape_adrs` on whenever the product has an `adr` block, and
   `tasklog._check_shaping` checks only tasks from the adoption point on, none when there is no
   adoption point (`git grep -n 'shape_adrs' ccp/config.py` at `58cf1d0`: the default set from
   `adr_on`).
5. **§25.3's `ccp allowance status` bullet** (plane proposal on task 0197). Task 0197 added the
   shared reader's fields. `usage.status` returns `latest_good`, `in_force`, `backoff_until` and
   `unread_since` beside `latest`. Probe at `58cf1d0`: `ccp allowance status` on a temp queue
   printed the keys `backoff_until`, `checkpoint`, `counter_resets`, `decision_lapsed_at`,
   `decisions`, `in_force`, `latest`, `latest_good`, `ok`, `project_checkpoint`, `unread_since`,
   `usage_read`, `warning` and `window`. The field is `unread_since`, not `unread`.

The proposal on task 0155 also named §25.1's board-build sentence. Task 0197 already fixed it
(`grep -c "and \`ccp board build\`" docs/spec/04-observability.md` at `58cf1d0`: 0). Its other
item, §15.2's `ccp verify spec-text` exit-2 sentence, moves to task 0209, which rewrites that
paragraph.

## Scope

- **In:** `docs/spec/02-delivery.md`, `docs/spec/03-quality.md`, `docs/spec/04-observability.md`.
  Text only, §31.1. Each CURRENT is verbatim at `58cf1d0`.
1. **§27.1, Window** (`docs/spec/04-observability.md`).
   CURRENT: "are left out (the usage advice, `ccp usage`'s, and the rotation slots due now still read
   the whole queue), and the report gives".
   PROPOSED: "are left out (the usage advice, `ccp usage`'s, reads the requests since `--since`, else
   `usage.advice.window_hours` back, every request when that is 0; the rotation slots due now judge
   each slot since its own spawn), and the report gives".
2. **§13.2, resolution review** (`docs/spec/02-delivery.md`).
   CURRENT: "It is refused (exit 2, nothing opened) when the task has no review that reported `done`,
   when a round since the latest such review is not a merge round, when the head is not a merge
   commit, or when the head's remerge diff is empty."
   PROPOSED: "It is refused (exit 2, nothing opened) when the task has no review that reported `done`,
   when the latest such review is a resolution review that judged the resolution `beyond` (a full
   review is due, §15.2), when a round since the latest such review is not a merge round, when the
   head can be neither read nor fetched from origin, when the head is not a merge commit, or when the
   head's remerge diff is empty."
3. **§23, event table** (`docs/spec/04-observability.md`).
   CURRENT: "| `run` | `recorded` | `run_id`, `mutants`, `killed`, `survived` (one `ccp mutate` call,
   §20.6) |".
   PROPOSED: "| `run` | `recorded` | `run_id`, `mutants`, `killed`, `unbuilt`, `survived` (one
   `ccp mutate` call, §20.6) |".
4. **§19.6, Shape is due** (`docs/spec/03-quality.md`).
   CURRENT: "With `architect.shape_adrs` on (which needs `shape_from_task`), `ccp tasks check` fails
   such a task unless its frontmatter says `shaping: waived — <reason>` (§15). Only `pending` tasks
   from `shape_from_task` on are checked, so older tasks never fail."
   PROPOSED: "With `architect.shape_adrs` on (by default whenever the product has an `adr` block,
   §19.11), `ccp tasks check` fails such a task unless its frontmatter says `shaping: waived —
   <reason>` (§15). Only `pending` tasks from `shape_from_task` on are checked, so older tasks never
   fail, and a product with no adoption point checks none."
5. **§25.3, `ccp allowance status`** (`docs/spec/04-observability.md`).
   CURRENT: "`ccp allowance status` shows the latest sample, the checkpoint in force, the counter
   resets detected and the window's decisions, each lapsed one with its reset's time (`lapsed_at`);"
   PROPOSED: "`ccp allowance status` shows the latest sample (a failed one included), the latest good
   one (`latest_good`) and whether it is in force (`in_force`, §25.1), the shared reader's state
   (`backoff_until`, when it may next run the command, and `unread_since`, when the current run of
   failed reads began), the checkpoint in force, the counter resets detected and the window's
   decisions, each lapsed one with its reset's time (`lapsed_at`);"
- **Out:** any code; §15.2's spec-text sentence (task 0209); §25.1 (already true).

## dod_checks

- id: `sd-01`
  story: As the SPEC reader, the old false wording is gone.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c 'still read the whole' docs/spec/04-observability.md`.
    2. Run `grep -c 'which needs' docs/spec/03-quality.md`.
    3. Run `grep -c 'killed., .survived. (one' docs/spec/04-observability.md`.
  expect: each step prints 0.
  dry run (`58cf1d0`): 1, 1 and 1.

- id: `sd-02`
  story: As the SPEC reader, each passage reads as PROPOSED.
  setup: a checkout of the PR head; the five PROPOSED texts of the Scope.
  steps:
    1. For each PROPOSED text, search the named SPEC file for it, whitespace-normalised (for example
       `python3 -c "import re,sys; t=re.sub(r'\s+',' ',open(sys.argv[1]).read()); print(re.sub(r'\s+',' ',sys.argv[2]) in t)" <file> "<text>"`).
  expect: `True` for all five.
  dry run (`58cf1d0`): `False` for all five.

- id: `sd-03`
  story: As the plane, each new description is true of the code.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_resolution_review tests.test_mutate tests.test_health`.
    2. Run `git grep -n 'has no review that reported done\|judged it beyond the conflict hunks\|is newer than the last review\|could not be read here or fetched from origin\|is not a merge commit\|no conflict was resolved' ccp/prompt.py`.
    3. Run `git grep -n '"latest_good": good_last, "in_force"\|"backoff_until":\|"unread_since":' ccp/usage.py`.
    4. Run `git grep -n 'if adr_on and not' ccp/config.py`.
  expect: step 1 exits 0. Step 2's output includes six `raise QueueError` lines in
    `resolution_gate` (any docstring line aside), one per refusal PROPOSED item 2 names, in that
    order: no review that reported done, judged beyond, a newer round, a head neither read nor
    fetched, not a merge commit, no conflict resolved. Step 3's output includes the keys PROPOSED
    item 5 names (`latest_good`, `in_force`, `backoff_until`, `unread_since`) in `status` and
    `reader_state`. Step 4 prints the line in `_architect` that turns `shape_adrs` on when the
    product has an `adr` block, PROPOSED item 4's default.
  dry run (`58cf1d0`): step 1, 25, 60 and 31 tests, OK; steps 2 to 4 print as expected.

- id: `sd-04`
  story: As the plane, the change is SPEC text only.
  setup: a checkout of the PR head.
  steps:
    1. Run `git diff --stat origin/main...HEAD -- . ':!docs/spec' ':!docs/delivery'`.
  expect: prints nothing.
  dry run: n/a.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
