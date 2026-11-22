---
task_id: 0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight
title: The architect's friction trigger counts distinct tasks with a worker note, leaves out override notes, and scales with tasks in flight
status: done
kind: feature
depends_on: []
spec_refs: ["S19"]
review_refs: ["ar-20261121T111633Z-4e26#F01"]
review_point: R22
paths: ["ccp/architect.py", "ccp/quality.py", "ccp/board.py", "ccp/board_page.html", "contracts/plane_config.schema.json", "docs/spec/03-quality.md", "docs/design/board.md", "docs/design/architect.md", "tests/test_architect_default_on.py", "tests/test_architect.py", "tests/test_board_quality.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-22
---

# Task: 0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight

## Intent

An architect pass made due by friction comes after about as much work as one made due by the
cadence, not after about one merge. The friction trigger counts the distinct tasks that a worker
wrote a friction note for since the last pass, so one issue restated by three seats counts once. The
notes the plane writes itself when the runner overrides a gate (`--allow-overdue`,
`--allow-unreviewed-fix`) no longer count, so overriding a due pass no longer makes the next pass
due. The threshold is a constant times the tasks the product runs at once, as the cadence is (task
0211). The board shows the tasks and noted tasks since the last pass against the numbers the
triggers actually use.

## Context (not checked)

Measured at `76f41dd` unless a line says otherwise.

- **Provenance.** Architect pass `ar-20261121T111633Z-4e26`, F01 (`rule-cost`), record in
  `docs/delivery/reviews/`. The operator answered its question on 2026-11-21 with "F01 - (c)":
  both (a), leave out the gate's own override notes and count distinct tasks with a worker note
  rather than lines, and (b), scale the threshold with `parallel.max_in_flight`. §19.6 states the
  behaviour and leaves the number to code (house rule E10). That ruling is recorded in the review
  record; the passage below is still signed in this brief (§31).
- **The trigger today counts lines.** `ccp/architect.py` `"def due_info"`: `n_notes = len(notes)` and `if adopted and n_notes >= a["notes_due"]:` (`git grep -n 'n_notes' -- ccp/architect.py` at `76f41dd`: 4 lines: the count, the comparison, the reason, the `notes_since_last` key).
- `"def notes"` in `ccp/health.py` filters by time only, never by source. Before the first pass a note with no task is already left out (`git grep -n 'a note with no task does not count' -- ccp/architect.py` at `76f41dd`: 1 line); after a pass it counts.
- **Who writes notes, by source** (`git grep -n 'add_note(' -- ccp` at `76f41dd`: 5 lines, one the definition): `ccp/report.py` records each line of a worker report's *Friction* section with source `worker`; `ccp health note` (`ccp/health.py`) uses the default source `worker`; `ccp/cli.py` writes `allow-overdue` on `ccp tasks next --allow-overdue`; `ccp/prompt.py` writes `allow-unreviewed-fix` (§15.2). Only `worker` notes are a worker's.
- **The threshold.** `notes_due` defaults to 3 (`git grep -n '"notes_due": 3' -- ccp/config.py` at `76f41dd`: 1 line); it is a deprecated plane.json constant (§29.3), which `contracts/plane_config.schema.json` describes as "Constant, 3 (SPEC §29.3): Or this many friction notes since the last pass" (`git grep -n 'this many friction notes' -- contracts` at `76f41dd`: 1 line).
- `"def _cadence"` in `ccp/architect.py` computes the cadence as `every_n_tasks` times the slots: `parallel.settings(cfg)["max_in_flight"]` when `parallel.enabled(cfg)`, else one.
- This repo's plane.json sets `parallel.max_in_flight` 3 and no `notes_due` (`python3 -c "import json;d=json.load(open('docs/delivery/plane.json'));print(d['parallel'], d['architect'].get('notes_due'))"` at `76f41dd`: `{'max_in_flight': 3, 'schedule': 'clashes'} None`), so after this task the trigger needs 9 noted tasks here, against a 12-merge cadence (`CCP_DEV=1 ./bin/ccp --root . architect due` at `76f41dd`: `cadence_tasks` 12).
- **What the queue shows** (data workers cannot reach; measured by the lead on 2026-11-21 with the `python3 -c` script below, run in this repo's queue directory over `health/notes.jsonl` and `architect.json`; each window runs from one pass's `started_at` to the next). Lines, `allow-overdue` lines, distinct tasks with a `worker` note, lines with no task:
  - after `ar-20261120T234012Z-27eb` (`python3 -c` script below): 26, 4, 7, 0;
  - after `ar-20261121T020523Z-1d5f` (`python3 -c` script below): 79, 22, 16, 4;
  - after `ar-20261121T111633Z-4e26` (`python3 -c` script below): 17, 3, 4, 0;
  - after `ar-20261121T132817Z-d5e5` (`python3 -c` script below): 56, 18, 11, 3;
  - after `ar-20261121T174754Z-7df5` (`python3 -c` script below): 64, 15, 11, 3.

  Every window passed today's threshold within its first task or two; with the new count and threshold (`python3 -c` script below, distinct worker-noted tasks against 9), three of the five windows would have called a friction pass.

  ```
  python3 -c "import json;ns=[json.loads(l) for l in open('health/notes.jsonl') if l.strip()];a=json.load(open('architect.json'));r=sorted((v['started_at'],k) for k,v in a['reviews'].items() if k.startswith('ar-') and v.get('started_at'));[print(k,len(w),sum(n.get('source')=='allow-overdue' for n in w),len({n['task_id'] for n in w if n.get('source')=='worker' and n.get('task_id')}),sum(not n.get('task_id') for n in w)) for i,(s,k) in enumerate(r) for w in [[n for n in ns if s<n['at']<=(r[i+1][0] if i+1<len(r) else '9')]]]"
  ```
- **The board shows stale denominators.** `QUEUE_ROOT=<empty temp dir> CCP_DEV=1 ./bin/ccp --root . board status` at `76f41dd` prints `architect last pass none, 73/4 tasks and 0/3 notes since; pass due: 73 task(s) done since none`: the tasks figure is against `every_n_tasks`, not the cadence (0211's implementation notes left the board out of its paths), and the notes figure against `notes_due`.
- `ccp/board.py` `"def _quality_lines"` and `ccp/board_page.html` (the architect tile, the two meters, and the friction tile's `F.notes_due`) read `settings.every_n_tasks`, `settings.notes_due` and `notes_since_last` (`git grep -n 'notes_since_last\|notes_due' -- ccp/board.py ccp/board_page.html ccp/quality.py` at `76f41dd`: 8 lines).
- **Tests this changes** (`git grep -n 'friction note(s)\|notes_due' -- tests` at `76f41dd`; it also finds `tests/test_plane_json_constants.py` and `tests/test_rules.py`, which list `notes_due` as a constant and do not change): `tests/test_architect.py` `"def test_acceptance_2_notes_reach_the_prompt"` (three notes on one task make a pass due), `tests/test_architect_default_on.py` `"def test_new_work_still_triggers"` and `"def test_after_a_pass_the_notes_of_any_task_count"` (after a pass, notes with no task count; this task reverses that), `tests/test_board_quality.py` (the friction block's `notes_due`).
- The test fixtures set `parallel.max_in_flight` 1 (`git grep -n '"max_in_flight": 1' -- tests/helpers.py` at `76f41dd`: 1 line), so the threshold there stays 3 (`git grep -n '"notes_due": 3' -- ccp/config.py`).
- `python3 -B -m unittest tests.test_architect_default_on tests.test_architect tests.test_board_quality` at `76f41dd`: 101 tests, OK.
- `docs/design/architect.md`'s acceptance walk-through 2 ("Three `ccp health note` lines make `ccp architect due` exit 0") becomes false with this task (`git grep -n 'Three .ccp health note. lines' -- docs/design/architect.md` at `76f41dd`: 1 line).
- Folded in by area: the board's tasks-figure stale denominator is 0211's follow-up, not part of F01; it adds no rule and no SPEC text.
- No other pending task edits §19.6 item 3 or `due_info`'s friction code (`git grep -ln 'Friction notes' -- docs/delivery/tasks`
  at `76f41dd`: three files, this task and two `done`). Of the tasks that shared a file when this brief was
  first written, 0254 (`ccp/architect.py`'s pass worktree), 0262 (`ccp/board.py`'s docstring), 0259 and
  0267 (other sections of `docs/spec/03-quality.md`) have merged, changing none of the code or text this
  brief quotes (`git log --oneline 8020446..76f41dd -- ccp/architect.py ccp/board.py` at `76f41dd`: 2 commits, 0254's
  and 0262's; `git diff 8020446 76f41dd -- ccp/quality.py ccp/board_page.html` at `76f41dd`: empty). 0191, still
  pending, changes other sections of `docs/spec/03-quality.md` and another key of the schema, so it is no clash.

### Rulings for the build (the lead's)

- **What counts.** A note counts when its `source` is `worker` and it names a task; the trigger
  counts the distinct `task_id`s of such notes since the last pass's start. Before the first pass,
  only tasks from the adoption point count, as today. A note with no task never counts, before or
  after the first pass. `allow-overdue` and `allow-unreviewed-fix` notes, and any source other than
  `worker`, never count. Every note still reaches the next pass's prompt as a lead, unchanged.
- **The threshold.** `notes_due` times the same slot count the cadence uses: factor the slot count
  out of `"def _cadence"` into one helper both read. `notes_due` keeps its default, its schema entry
  and its constant status.
- **What `due_info` reports.** `notes_since_last` is replaced by `noted_tasks_since_last` (the
  count above), and `notes_tasks` (the threshold) is added beside `cadence_tasks`. The reason reads
  `{n} task(s) with a friction note since {label}`.
- **The board.** `ccp/quality.py`'s architect block carries `cadence_tasks`, `notes_tasks` and
  `noted_tasks_since_last` in place of `notes_since_last`. The text line reads
  `architect last pass {id}, {done}/{cadence_tasks} tasks and {noted}/{notes_tasks} noted tasks since; …`.
  The HTML architect tile and the two meters use the same figures. The friction block's
  `notes_due` key and argument go: its tile shows the lines since the last pass with no denominator,
  since the trigger no longer counts lines.

## Scope

- **In:** `ccp/architect.py` (`"def due_info"`, `"def _cadence"`, the module docstring's friction
  line), `ccp/quality.py`, `ccp/board.py` (`"def _quality_lines"`), `ccp/board_page.html`,
  `contracts/plane_config.schema.json` (the `notes_due` description: "Constant, 3 (SPEC §29.3): Or
  friction notes from this many tasks, times parallel.max_in_flight, since the last pass. …", the
  rest unchanged), `docs/design/board.md` (the architect paragraph's `every_n_tasks`, `notes_due`), `docs/design/architect.md` (acceptance walk-through 2: worker notes on 3 distinct tasks, `ccp health note --task`, with one slot),
  `tests/test_architect_default_on.py`, `tests/test_architect.py`, `tests/test_board_quality.py`.
- **Tests:**
  - with slots 1, worker notes on 3 distinct tasks make the reason; 9 notes on 2 tasks do not;
  - with `max_in_flight` 3, worker notes on 8 tasks make no reason and on 9 tasks do;
  - after a pass, `allow-overdue` and `allow-unreviewed-fix` notes on 3 more tasks, and worker notes
    with no task, make no reason;
  - `due_info` carries `notes_tasks` and `noted_tasks_since_last`, and no `notes_since_last`;
  - the board's text line and quality block read the cadence and noted-task figures;
  - the three existing tests named in Context changed to these rules.
- **Out:** the cadence, the 14-day trigger, drift and budgets; `notes_due`'s value; what reaches the
  pass's prompt; how notes are recorded (`ccp health note`, `report.py`, the override writers);
  §19.6's `--allow-overdue` paragraph.

- **Signed before the claim (`sign_off: brief`, §31):** `docs/spec/03-quality.md` §19.6, item 3,
  replaced whole.

    CURRENT (`docs/spec/03-quality.md` at `76f41dd`, §19.6 item 3):
    > 3. **Friction notes.** 3 notes have arrived since the last pass's start. Any
    >    worker (implementer, reviewer, verifier) may report friction in the *Friction* section of its
    >    report, and the runner records each line with `ccp health note`: a fact changed in many places, a
    >    test that pinned wording, a document read that did not help, a rule that forced extra work. The
    >    notes go to the next pass as leads.

    PROPOSED:
    > 3. **Friction notes.** Enough distinct tasks have a worker's friction note since the last pass's
    >    start: a fixed number (a constant in code) times the product's `parallel.max_in_flight` (1 when
    >    tasks run one at a time, §16.2), as for the cadence. A task counts once however many notes its
    >    seats wrote. A note with no task does not count, nor does one the plane records for an override
    >    (`--allow-overdue`, below; `--allow-unreviewed-fix`, §15.2). Any
    >    worker (implementer, reviewer, verifier) may report friction in the *Friction* section of its
    >    report, and the runner records each line with `ccp health note`: a fact changed in many places, a
    >    test that pinned wording, a document read that did not help, a rule that forced extra work. All
    >    the notes go to the next pass as leads.

  It retires the sentence "3 notes have arrived since the last pass's start." and the reading that
  every note line counts. No other SPEC text changes: §19.6's `--allow-overdue` paragraph ("the
  override is recorded as a friction note with source `allow-overdue`") and §15.2's
  `allow-unreviewed-fix` note stay true (`git grep -n -i 'friction note' -- docs/spec` at `76f41dd`:
  6 lines: item 3, the adoption paragraph, the override paragraph, §15.2 and two board lists in
  `docs/spec/04-observability.md`; only item 3 states a count).

## dod_checks

- id: `fr-01`
  story: As a lead, a friction pass comes after enough noted tasks, not after one task's notes.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_architect_default_on tests.test_architect tests.test_board_quality 2>&1 | tail -60`.
  expect: The run ends `OK`, and the Scope's tests are listed `ok`: 3 noted tasks with one slot due and 9 notes on 2 tasks not; 8 tasks with three slots not due and 9 due; override notes and notes with no task never counted; `notes_tasks` and `noted_tasks_since_last` in `due_info` and no `notes_since_last`; the board line and quality block.
  dry run (`76f41dd`): 101 tests, `OK`; the new tests do not exist yet.

- id: `fr-02`
  story: As a plane developer, the tests bite on each of the three rules.
  setup: A checkout of the PR head; then three copies (`git worktree add --detach <tmp> HEAD`), never the branch's own worktree. Copy A counts note lines again (the distinct-task set replaced by the note count); copy B counts every source (the `worker` filter removed); copy C uses `notes_due` alone as the threshold (the slot factor removed).
  steps:
    1. In each copy, run `python3 -B -m unittest -q tests.test_architect_default_on tests.test_architect; echo "exit $?"`.
  expect: Each of the three runs prints at least one failure and ends with a non-zero exit.
  dry run: n/a — the rules and their tests are new.

- id: `fr-03`
  story: As a lead, `ccp architect due` names how many noted tasks the friction trigger waits for.
  setup: A checkout of the PR head; `QUEUE_ROOT` an empty temp directory.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp --root . architect due | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['cadence_tasks'], d['notes_tasks'], d['noted_tasks_since_last'], 'notes_since_last' in d)"`.
  expect: It prints `12 9 0 False` (this repo's `every_n_tasks` 4 and `notes_due` 3, each times its `max_in_flight` 3).
  dry run (`76f41dd`): the script raised `KeyError: 'notes_tasks'`; `cadence_tasks` was 12.

- id: `fr-04`
  story: As the operator reading the board, the tasks and noted tasks are shown against the numbers the triggers use.
  setup: A checkout of the PR head; `QUEUE_ROOT` an empty temp directory.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp --root . board status 2>&1 | grep '^architect last pass'`.
  expect: One line, starting `architect last pass none, ` and holding `/12 tasks and 0/9 noted tasks since;`.
  dry run (`76f41dd`): `architect last pass none, 73/4 tasks and 0/3 notes since; pass due: 73 task(s) done since none`.

- id: `fr-05`
  story: As the operator, §19.6 item 3 reads as I signed it.
  setup: A checkout of the PR head; the brief sign-off recorded; `QUEUE_ROOT` a temp queue.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp --root . verify spec-text 0270`.
  expect: Exit 0, the PROPOSED passage found in `docs/spec/03-quality.md`.
  dry run (simulated: this task file committed, then the PROPOSED passage applied to `docs/spec/03-quality.md` and committed, in a scratch worktree off `76f41dd`, `--base` the commit holding the task file): exit 0, the passage found in `docs/spec/03-quality.md`.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: A checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: The gate exits 0 and the branch list prints nothing.
  dry run: n/a.

## Implementation notes

- `ccp/architect.py`: `_slots(cfg)` is the slot count both `_cadence` and the new `_notes_tasks` read.
  `noted_tasks(notes, counts)` is the pure rule (source `worker`, a task named, `counts` keeps the tasks
  the trigger counts: from the adoption point before the first pass, any task after it). `due_info`
  reports `notes_tasks` beside `cadence_tasks` and `noted_tasks_since_last` in place of
  `notes_since_last`; the reason reads `{n} task(s) with a friction note since {label}`. The pass's
  prompt still reads every note (`health.notes` in the prompt builder, unchanged).
- A note with no `source` field does not count (only `worker` counts, as the ruling says); every
  record in this repo's queue carries one (`add_note` has always written it).
- `ccp/quality.py`: the architect block carries `cadence_tasks`, `notes_tasks` and
  `noted_tasks_since_last`; `settings` is unchanged. The friction block loses `notes_due` and
  `friction()` its argument. `ccp/board.py` and `ccp/board_page.html` read the new figures; the
  friction tile shows the lines since the last pass with no denominator.
- The page's JavaScript has no test that runs it (the suite runs no JS engine); the Python side of
  each figure it reads is tested through `board.json`.
- `tests/test_architect_default_on.py`'s `test_after_a_pass_the_notes_of_any_task_count` keeps its
  name: after a pass a task before the adoption point still counts, and the test now also shows a note
  with no task does not.

## Verification notes
- 2026-11-22 — verifier, PR #341 head `80d189c` (close's catch-up of the approved `a03379d`, gate run st-20261122T132455Z-3fbefb) (squash `26e14d9`): APPROVE. Passed: fr-01, fr-02, fr-03, fr-04, fr-05, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0270-the-friction-trigger-counts-noted-tasks-and-scales-with-tasks-in-flight.json.

