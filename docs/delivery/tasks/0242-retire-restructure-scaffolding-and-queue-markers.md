---
task_id: 0242-retire-restructure-scaffolding-and-queue-markers
title: Retire the SPEC restructure's scaffolding and the queue state markers, and fix stale package and design docs
status: pending
kind: feature
depends_on: []
spec_refs: ["S10", "S31"]
review_refs: ["ar-20261120T234012Z-27eb#F08", "ar-20261120T234012Z-27eb#F09", "ar-20261120T234012Z-27eb#F18", "ar-20261120T234012Z-27eb#F19"]
review_point: R16
paths: ["docs/spec/RULINGS.md", "docs/spec/map/", "docs/spec/MAP.md", "SPEC.md", "scripts/spec_map_check.py", "scripts/CLAUDE.md", "tests/test_spec_map_check.py", "docs/design/", "ccp/queue.py", "ccp/lifecycle.py", "scripts/queue/README.md", "docs/spec/02-delivery.md", "ccp/CLAUDE.md", "ccp/doclang/CLAUDE.md", "tests/test_board.py", "tests/test_release.py", "tests/test_tasks_release_keep_branch.py", "tests/test_toolkit.py", "tests/test_queue_markers_gone.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0242-retire-restructure-scaffolding-and-queue-markers

## Intent

Three kinds of leftover stop costing readers and writers. The completed SPEC restructure's map, its
rulings trail and the checker for them leave the normative SPEC directory, since Git and ADR-0034 keep
them. The per-task `queue/<state>/` marker files, which every transition writes and nothing reads
except the code keeping them in step, are no longer written, and an old queue's `queue/` directory
becomes a leftover `ccp plane check --archive` moves aside. And the package and design docs stop
naming modules wrongly, citing a config place the plane no longer uses, or heading sections with
pre-restructure numbers and dated step labels.

## Context (not checked)

From architect pass `ar-20261120T234012Z-27eb`, findings F08, F09, F18 and F19, triaged by the lead
on 2026-11-21. Finding F07 (the pre-ccp contracts and `formal-submit.template.sh`) is out of this
task: it waits on an operator question about the `/mk-pr` and formal-submit phases in §13.1/§15.1.
Measured at `8aefa59`.

- **F08, the restructure scaffolding.** `git log --oneline -- docs/spec/map docs/spec/RULINGS.md scripts/spec_map_check.py`
  at `8aefa59`: two commits, the initial commit and task 0012. Nothing runs the checker:
  `git grep -n spec_map_check -- scripts/gate.sh scripts/gate_parallel.py ccp plugin` at `8aefa59`
  prints nothing. Its `refs` subcommand goes with it; no gate or docs check calls it. References to
  update: `SPEC.md`'s "The restructure" bullet, `docs/spec/MAP.md` (keep its Outline, drop "The map,
  old → new" and the RULINGS paragraph), `docs/design/README.md` (the sentence saying MAP.md maps old
  sections), `scripts/CLAUDE.md`. ADR-0034's sentence naming `docs/spec/RULINGS.md` stays as written:
  an ADR records its time, and Git keeps the file.
- **F09, the markers.** `ccp/queue.py` `"def set_marker"` keeps `queue/<state>/<task_id>` "for the
  plane's queue scripts"; `scripts/queue/` holds only README.md. `git grep -n 'set_marker\|_markers(' -- ccp` at `8aefa59`, less the ADR tool's unrelated `migrate_markers` lines: 10 lines, writers in
  `ccp/lifecycle.py` at claim, phase, release and close, and the reader `"def _markers"` used only by
  sync's plan and its own re-sync. Ruling: stop writing them, drop `_markers` and its line in the
  sync plan, and remove `"queue"` from `QUEUE_OWNED` in `ccp/queue.py`, so an old queue's `queue/`
  directory is a leftover the archive moves to `_legacy/` (§31.3). `scripts/queue/README.md`'s
  layout drops the `queue/…` line. Tests that assert on markers:
  `git grep -nE 'queue/(pending|leased|done)' -- tests` at `8aefa59`: 7 lines in
  `tests/test_board.py`, `tests/test_release.py`, `tests/test_tasks_release_keep_branch.py` and
  `tests/test_toolkit.py`.
- **F18, package docs.** `ccp/CLAUDE.md`'s layout names no `init.py` or `envvars.py` (a loop over
  `ccp/*.py` grepping each backticked name in it, at `8aefa59`: those two missing, beside
  `__init__.py` and `__main__.py`, which need no entry). `ccp/doclang/CLAUDE.md` says the
  `language-pack` check in plane.json's `docs.checks` keeps the rule; the plane's plane.json has no
  `docs` block and the rule runs from `architect.checks` `E18`. (E18's own "once the pack owns the
  patterns" is dropped by this triage's rule change, not here.)
- **F19, design notes.** `git grep -nE '^#+ +[0-9]+\.[0-9]+ ' -- docs/design` at `8aefa59`: 6 headings
  carrying old § numbers (allowance.md, board.md, observability.md, telemetry.md x3), most with a
  dated step or spike label. `git grep -nE 'default [0-9]+|defaults? to [0-9]' -- docs/design` at `8aefa59`: 7 lines restating default values, which E10 places in code and the schema. Retitle each
  heading by topic; replace each restated default with a pointer to the schema or the constant.

## Scope

- **In:**
  - `docs/spec/RULINGS.md` (removed), `docs/spec/map/` (removed), `scripts/spec_map_check.py`
    (removed), `tests/test_spec_map_check.py` (removed); `docs/spec/MAP.md`, `SPEC.md`,
    `docs/design/README.md`, `scripts/CLAUDE.md`.
  - `ccp/queue.py` (`set_marker` removed, `QUEUE_OWNED`), `ccp/lifecycle.py` (`_markers` and its
    callers), `scripts/queue/README.md`; the four test modules above; `tests/test_queue_markers_gone.py` (new).
  - `ccp/CLAUDE.md`, `ccp/doclang/CLAUDE.md`; `docs/design/allowance.md`, `docs/design/board.md`,
    `docs/design/observability.md`, `docs/design/telemetry.md`, `docs/design/architect.md`.
  - SPEC, signed before the claim (`sign_off: brief`):
  - `docs/spec/02-delivery.md` §10.4: CURRENT (at `8aefa59`): "Its wait is cleared through `set-waiting-on.sh`, its phase moves to `pending` (the `queue/pending/` marker), then a `lease` `clear` event with `released: true` and the reason;" PROPOSED:
    > Its wait is cleared through `set-waiting-on.sh`, its phase moves to `pending`, then a `lease` `clear` event with `released: true` and the reason;
  - `docs/spec/02-delivery.md` §10.6: CURRENT (at `8aefa59`): "`scripts/queue/*.sh` and `scripts/observability/*.sh` stay as thin wrappers over `ccp`." PROPOSED:
    > `scripts/observability/*.sh` stay as thin wrappers over `ccp`.
- **Out:**
  - F07: `contracts/progress|review|result|architecture_review.schema.json`, `scripts/formal-submit.template.sh`, §13.1 and §15.1 (an operator question).
  - ADR-0034's text.

## dod_checks

- id: `ret-01`
  story: As a SPEC reader, the restructure's map, rulings trail and checker are gone and nothing points at them.
  setup: a checkout of the PR head.
  steps:
    1. Run `ls docs/spec/RULINGS.md docs/spec/map scripts/spec_map_check.py tests/test_spec_map_check.py 2>&1 | grep -c 'No such file'`.
    2. Run `git grep -nE 'spec/map|RULINGS\.md|spec_map_check' -- ':!docs/delivery/tasks' ':!docs/delivery/reviews' ':!docs/adr'`.
  expect: step 1 prints `4`; step 2 prints nothing.
  dry run (`8aefa59`): step 1 printed `0`; step 2 printed 32 lines, in `SPEC.md`, `docs/spec/MAP.md`, `docs/spec/map/`, `scripts/CLAUDE.md`, `scripts/spec_map_check.py` and `tests/test_spec_map_check.py`.
- id: `ret-02`
  story: As an operator, the queue no longer carries per-task marker files, and an old `queue/` directory is archived as a leftover.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'set_marker\|_markers(' -- ccp ':(exclude)ccp/adr.py' ':(exclude)ccp/cli.py'`.
    2. Run `python3 -B -c "from ccp import queue; print('queue' in queue.QUEUE_OWNED)"`.
  expect: step 1 prints nothing; step 2 prints `False`.
  dry run (`8aefa59`): step 1 printed 10 lines; step 2 printed `True`.
- id: `ret-03`
  story: As a plane developer, a claim, a release and a close in a fenced product create no `queue/` directory, and the test bites.
  setup: a checkout of the PR head; then a separate copy where `ccp/lifecycle.py`'s release touches `queue/pending/<id>` again.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_queue_markers_gone tests.test_release tests.test_tasks_release_keep_branch tests.test_toolkit tests.test_board`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_queue_markers_gone`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run: n/a — `tests/test_queue_markers_gone.py` is new.
- id: `ret-04`
  story: As a reader of the package docs, they name every module and the place the language rule runs from.
  setup: a checkout of the PR head.
  steps:
    1. Run `for f in ccp/*.py; do b=$(basename $f); grep -q "\`$b\`" ccp/CLAUDE.md || echo $b; done`.
    2. Run `grep -c 'docs.checks' ccp/doclang/CLAUDE.md`.
  expect: step 1 prints only `__init__.py` and `__main__.py`; step 2 prints `0`.
  dry run (`8aefa59`): step 1 printed `__init__.py`, `__main__.py`, `envvars.py`, `init.py`; step 2 printed `1`.
- id: `ret-05`
  story: As a reader of the design notes, headings name topics and defaults point at their source.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nE '^#+ +[0-9]+\.[0-9]+ ' -- docs/design`.
    2. Run `git grep -nE 'default [0-9]+|defaults? to [0-9]' -- docs/design`.
  expect: both print nothing.
  dry run (`8aefa59`): step 1 printed 6 lines; step 2 printed 7 lines.

## Implementation notes

## Verification notes
