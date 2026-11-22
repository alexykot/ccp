---
task_id: 0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log
title: ccp owns the headless-launch helpers and the open-question rule, and the spec-question script's blocked and task-id checks read the task log and id shape through ccp
status: pending
kind: feature
depends_on: []
spec_refs: ["S17", "S24"]
review_refs: ["ar-20261122T055103Z-11aa#F01", "ar-20261122T055103Z-11aa#F02"]
rule_refs: ["E7", "E8", "E23"]
review_point: R25
paths: ["ccp/headless.py", "ccp/queue.py", "ccp/architect.py", "ccp/estimator.py", "ccp/seats.py", "ccp/submit.py", "ccp/CLAUDE.md", "scripts/observability/spec_maintainer.py", "scripts/observability/team.py", "scripts/observability/CLAUDE.md", "scripts/spec-maintainer-ask.sh", "docs/ENGINEERING.md", "docs/delivery/plane.json", "tests/test_headless.py", "tests/test_usage.py", "tests/test_estimator.py", "tests/test_spec_maintainer_blocked.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0282-ccp-owns-the-headless-launch-helpers-and-blocked-reads-the-task-log

## Intent

The one place that strips the API keys from a plane-launched `claude -p` (house rule E8), reads its
JSON and detects a quota stop is a `ccp` module, and so is the rule for which spec questions are open.
`ccp` no longer imports the spec-question script to reach them. That script's `blocked` (the §17.7
skip-ahead) lists every task-log descendant of a blocked task through the product's binding, whether
or not `DURABLE_DOCS` is set, and its task-id check uses the product's id shape from `ccp/refs.py`.

## Context (not checked)

From architect pass `ar-20261122T055103Z-11aa`, F01 (`incoherence`) and F02 (`duplication`); the record
is in `docs/delivery/reviews/`. Also the worker follow-up
`0264-one-parser-for-signed-blocks-and-task-id-patterns/implement#1` (`ccp/CLAUDE.md` could say that
`tasklog.py` holds the signed-block reader), since this task edits `ccp/CLAUDE.md` anyway.

Measured at `072d9f9`.

- **What ccp borrows.** `git grep -nP 'import spec_maintainer|\bsm\.(STRIP_KEYS|headless_env|parse_claude_json|detect_quota|lock_is_stale|open_questions)\b|\barchitect\.sm\b' -- ccp` at `072d9f9`: 16 lines in `ccp/architect.py` (the import and 5 uses),
  `ccp/estimator.py` (7 lines: `return architect.sm, architect.ar` and 6 uses), `ccp/seats.py` (1, `architect.sm.lock_is_stale`) and `ccp/submit.py`
  (the import and `sm.open_questions`). `lock_is_stale` is lib's, re-exported by `spec_maintainer.py`
  (`"lock_is_stale,  # noqa: F401  (re-exported"`).
- **No caller inside the script.** `git grep -c 'headless_env\|parse_claude_json\|detect_quota' -- scripts/observability/spec_maintainer.py` at `072d9f9`: 3, the three `def` lines.
  `open_questions` is called by `cmd_blocked` in the script and twice in `scripts/observability/team.py`.
- **The open-question rule.** `"def open_questions"` keeps a question whose `status` is `open` or
  `escalated`. `ccp/board.py`'s `_open_questions` keeps only `open` (its own reader of `questions/`).
  The board is Out: changing which questions it shows is a board behaviour change no finding asks for.
- **blocked.** `"def descendants"` reads `depends_on` from the queue's `tasks/*.json` and, only when the
  `DURABLE_DOCS` variable is set, from `INDEX.yaml` or the task files' frontmatter, each with its own
  regex, and computes its own closure. A probe at `072d9f9` (`env -u DURABLE_DOCS python3 -B -c '…sm.descendants(<empty queue>, ["0001-a"])'`):
  returned `{'0001-a'}`, so a task-log descendant of a blocked task is not listed. `ccp/graph.py`'s
  `closure` gives what a node depends on; the dependents are the closure over the reversed map.
- **The task-id regex.** `"TASK_ID_RE = re.compile"` in the script has no width: a probe at `072d9f9`
  (`python3 -B -c '…sm.TASK_ID_RE.match("00001-x")'`) matched `1-x` and `00001-x`. `ccp/refs.py`'s
  `Ids.task_id_re` carries the product's width (`ids.task.width`). The proposed E23 command,
  `git grep -nE '\\d[+{][^"]*-\[a-z0-9\]' -- ccp scripts ':(exclude)ccp/refs.py'` at `072d9f9`: 1 line, the script's `TASK_ID_RE`.
- **Tests that reach the moved names.** `git grep -n 'headless_env' -- tests` at `072d9f9`: 2 lines,
  `tests/test_usage.py` (`class HeadlessEnv`, through `import spec_maintainer as sm`) and `tests/test_estimator.py`
  (`architect.sm.headless_env`). `git grep -n 'detect_quota\|parse_claude_json\|open_questions\|descendants\|check_task_ids' -- tests` at `072d9f9`: no lines.
  `tests/test_team_hosting.py` runs `spec-maintainer-ask.sh blocked` only for its no-binding refusal, which stays.
- **No SPEC change.** `git grep -n 'DURABLE_DOCS\|spec_maintainer.py\|headless_env' -- docs/spec SPEC.md` at `072d9f9`: no lines.
  §17.7 already says the blocked tasks are "the tasks in its `blocks`, plus their `depends_on` descendants",
  and §24.3 says what a headless session's environment carries, not where the code lives.
- **E7 is not amended here.** Its amendment ("`ccp` imports nothing from scripts/") is a question for the
  operator in this triage, and needs the move of `lib.py` and `architecture_review.py` that the roadmap's
  F17 entry keeps deferred. `ccp/architect.py`, `ccp/queue.py` and `ccp/health.py` keep their `sys.path`
  entries for `lib` and `architecture_review`.
- **Other tasks.** 0277 (R24) changes `QID_RE` in `scripts/observability/spec_maintainer.py` and 0278 (R24, signed) changes
  `ccp/submit.py`'s coverage logic; this task changes other functions of both files. No clash.

### Rulings for the build (the lead's)

- `ccp/headless.py` (new) holds `STRIP_KEYS`, `headless_env`, `parse_claude_json` and `detect_quota`, moved
  unchanged in behaviour; no copy or re-export stays in `spec_maintainer.py`.
- `open_questions(queue_root)` moves to `ccp/queue.py`, unchanged in what it returns; `ccp/submit.py`,
  `scripts/observability/team.py` and the script's `cmd_blocked` call it.
- `ccp/architect.py`, `ccp/estimator.py` and `ccp/seats.py` take `lock_is_stale` from `lib`, as
  `ccp/architect.py` already takes `fmt_dt` and `parse_dt`.
- `descendants` takes the task log through the binding: the product root the script already resolves
  (`"def product_root"`), `ccp.config.load` and `ccp.tasklog.load`. It unions each task's `depends_on`
  with the queue's `tasks/*.json` ones, and returns the seeds plus every task whose dependency closure
  (`ccp.graph.closure`) holds a seed. With no product root, or a plane.json that cannot be read, it reads
  the queue's tasks only, as now without `DURABLE_DOCS`. It reads `DURABLE_DOCS` no more; the
  `blocked` line of `scripts/spec-maintainer-ask.sh`'s usage text drops it.
- `check_task_ids` matches each id with `refs.ids(cfg).task_id_re` of that config, and with the
  default `Ids` when no config can be read. Its refusal text names the shape at that width.
- House rule E23 becomes, in `docs/ENGINEERING.md` (the text the architect proposed):
  "One parser per reference form: an ADR-decision link (`<ADR id>[ Dn]`, as `adr_refs`, `requires` and
  `retired by` write it) and a task-id reference are parsed by ccp/refs.py; no other module in ccp or
  scripts holds a regex for either." with `check: command — architect.checks `E23``, and
  `docs/delivery/plane.json` gets the entry
  `{"id": "E23", "cmd": "! git grep -nE '\\\\d[+{][^\"]*-\\[a-z0-9\\]' -- ccp scripts ':(exclude)ccp/refs.py'"}`.
  The rules doc stays within its 150-line budget (`rules_max_lines`).

## Scope

- **In:** `ccp/headless.py` (new), `ccp/queue.py`, `ccp/architect.py`, `ccp/estimator.py`, `ccp/seats.py`,
  `ccp/submit.py`, `ccp/CLAUDE.md` (the new module, and `tasklog.py` holding the signed-block reader),
  `scripts/observability/spec_maintainer.py`, `scripts/observability/team.py`,
  `scripts/observability/CLAUDE.md`, `scripts/spec-maintainer-ask.sh` (usage text), `docs/ENGINEERING.md`
  (E23), `docs/delivery/plane.json` (`architect.checks` `E23`), `tests/test_headless.py` (new; `HeadlessEnv`
  moves there from `tests/test_usage.py`), `tests/test_usage.py`, `tests/test_estimator.py`,
  `tests/test_spec_maintainer_blocked.py` (new).
- **Out:** the move of `lib.py` and `architecture_review.py` and the E7 amendment (the roadmap's F17);
  `ccp/board.py`'s question reader; the SPEC.

## dod_checks

- id: `code-01`
  story: As a plane developer, ccp reaches the headless-launch helpers and the open-question rule without importing the spec-question script.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nP 'import spec_maintainer|\bsm\.(STRIP_KEYS|headless_env|parse_claude_json|detect_quota|lock_is_stale|open_questions)\b|\barchitect\.sm\b' -- ccp`.
    2. Run `git grep -nP 'def (headless_env|parse_claude_json|detect_quota|open_questions)\b|^STRIP_KEYS\b' -- ccp scripts`.
  expect: step 1 prints nothing; step 2 prints exactly five lines: `STRIP_KEYS`, `def headless_env`, `def parse_claude_json` and `def detect_quota` in `ccp/headless.py`, and `def open_questions` in `ccp/queue.py`.
  dry run (`072d9f9`): step 1 printed 16 lines (the measured borrowings); step 2 printed 5 lines, all in `scripts/observability/spec_maintainer.py`.
- id: `cmd-01`
  story: As a headless seat's launcher, the child environment still has no API key and carries the project and seat.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_headless tests.test_estimator tests.test_usage 2>&1 | tail -1`.
  expect: prints `OK`.
  dry run: n/a — `tests.test_headless` is new.
- id: `cmd-02`
  story: As a runner skipping ahead past a spec question, blocked lists the task-log descendants of a blocked task without DURABLE_DOCS.
  setup: A checkout of the PR head.
  steps:
    1. Run `env -u DURABLE_DOCS python3 -B -m unittest -v tests.test_spec_maintainer_blocked 2>&1 | grep -e descendant -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_spec_maintainer_blocked --mutant-file <file>`, the file's mutant making `descendants` skip the task log.
  expect: step 1 prints, each `ok`, a test where a product whose task log has `0003-c` depending on `0002-b` and `0002-b` on `0001-a`, with a queue question blocking `0001-a` and no `tasks/*.json`, makes `spec-maintainer-ask.sh blocked` list `0001-a`, `0002-b` and `0003-c`; and one where a product with no readable plane.json lists the blocked task alone; then `OK`. Step 2 prints the mutant `killed`.
  dry run: n/a — the test module is new.
- id: `cmd-03`
  story: As a runner raising a question, an id at the wrong width is refused before anything is written.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_spec_maintainer_blocked 2>&1 | grep -e width -e '^OK'`.
  expect: prints, `ok`, a test where `spec-maintainer-ask.sh raise --task-id 00001-x …` in a product at the default width exits 2 naming `00001-x`, with no file under the queue's `questions/`; then `OK`.
  dry run: n/a — the test module is new.
- id: `rule-01`
  story: As the architect, E23's command covers scripts and passes.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -c "import json;print([c['id'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E23'])"`.
    2. Run `git grep -nE '\\d[+{][^"]*-\[a-z0-9\]' -- ccp scripts ':(exclude)ccp/refs.py'; echo "exit=$?"`.
  expect: step 1 prints `['E23']`; step 2 prints only `exit=1`.
  dry run (`072d9f9`): step 1 printed `[]`; step 2 printed the `TASK_ID_RE` line of `scripts/observability/spec_maintainer.py` and `exit=0`.

## Implementation notes

- `ccp/headless.py` holds `STRIP_KEYS`, `headless_env`, `parse_claude_json` and `detect_quota` (with the quota,
  ISO and epoch patterns only `detect_quota` reads), moved unchanged; it takes `fmt_dt` and `parse_dt` from lib
  through `from ccp.queue import lib`, as `ccp/seats.py` already does, so it adds no `sys.path` edit.
- `open_questions(q)` is in `ccp/queue.py`; `ccp/submit.py`, `scripts/observability/team.py` (both status ops)
  and the script's `cmd_blocked` import it. `ccp/architect.py` takes `lock_is_stale` from lib with `fmt_dt`;
  `ccp/estimator.py` and `ccp/seats.py` call `lib.lock_is_stale` (lib through `ccp.queue`, as seats already
  took it). The estimator's `_sm()` became `_ar()`, the review kit alone.
- `spec_maintainer.py` keeps the `lock_is_stale` re-export: `scripts/observability/architecture_review.py`
  (outside this task's paths) reads `sm.lock_is_stale`. The re-export's comment names that reader.
- `descendants` and `check_task_ids` read the product's config through a new `product_config(root)`
  (the binding's product root, `ccp.config.load`; None with no root or an unreadable plane.json).
  `descendants` unions the queue's `tasks/*.json` with `tasklog.load` and returns the seeds plus every task
  whose `graph.closure` holds one. `check_task_ids` refuses with `refs.ids(cfg).task_id_re` and names the
  shape as `N` repeated to the width, `-slug`; its task-existence check is unchanged.
- Usage text: the `DURABLE_DOCS` env line (it named only `blocked`) is gone; the `blocked` line says the
  descendants come from the task log and the queue's tasks.
- Docs that named `spec_maintainer.headless_env` or `STRIP_KEYS` in the script now name `ccp/headless.py`:
  `docs/design/allowance.md`, `docs/design/telemetry.md`, `docs/design/threat-model.md` and the estimator's
  module docstring (outside `paths`, but they would be wrong after the move).
- `tests/test_usage.py`'s `HeadlessEnv` moved to `tests/test_headless.py`; its half that checked the OTLP fold
  reading `ccp.seat` stays in `tests/test_usage.py` as `SeatAttribute`, since it needs that module's own
  `logs` and `kv` builders. `tests/test_estimator.py` calls `headless.headless_env`.

## Verification notes
