---
task_id: 0323-the-package-docs-name-lib-py-s-roles-the-architect-writes-its-queue-files-atomically-and-queue-goes
title: The observability package doc names lib.py as the one binding reader and the seat table, ccp's conventions name the atomic write as it is, the architect writes its report and failure text into the queue atomically, and the tracked queue directory goes
status: pending
kind: refactor
depends_on: []
review_refs: ["ar-20261124T034246Z-e089#F08", "ar-20261124T034246Z-e089#F09", "ar-20261124T034246Z-e089#F12"]
review_point: R33
paths: ["scripts/observability/CLAUDE.md", "ccp/CLAUDE.md", "ccp/architect.py", "queue/README.md"]
clashes_with: []
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0323-the-package-docs-name-lib-py-s-roles-the-architect-writes-its-queue-files-atomically-and-queue-goes

## Intent

A developer reading the package docs finds where a product's binding is parsed and where the seats' actor ids are
named: `scripts/observability/CLAUDE.md` says `lib.py` holds both, which house rules E17 and E27 rely on. `ccp`'s
conventions state the queue-write route as the code has it since 0312, `lib.write_atomic` (and `queue.write_json`,
which calls it) under `file_lock`, and the architect's report and failure text in the queue go through it too, so no
reader meets a half-written file. The tracked top-level `queue/` directory, which holds only a README about a
directory that lives elsewhere, goes.

## Context (not checked)

Findings F08, F09 and F12 of architect pass `ar-20261124T034246Z-e089`
(`docs/delivery/reviews/ar-20261124T034246Z-e089.md`).

Measured at `9691fd9c` (origin/main after 0317's reconcile):

- **F08.** `scripts/observability/CLAUDE.md`'s first paragraph lists the ledger, the work.json lock, the one atomic
  write and the read-only values; `grep -c 'read_binding\|SEAT_IDS\|machine' scripts/observability/CLAUDE.md`: 0.
  `scripts/observability/lib.py` holds the seat table (`"LEAD = "design-seat""`, `RUNNER`, `VERIFIER`,
  `"SEAT_IDS = (RUNNER, VERIFIER, LEAD)"`), the binding reader (`"def read_binding"`, `binding_path`,
  `product_binding`, `binding_data`) and the machine file (`"MACHINE_FILE = "machine.json""`, `read_machine`). E17
  (amended by this triage) names lib.py; E27 says "in the seat table".
- **F09.** `ccp/CLAUDE.md`, *Conventions*: "Writes to the queue go through `queue.py`'s helpers (atomic replace,
  `file_lock`)". `git grep -l write_atomic -- ccp` at `9691fd9c`: 7 files call `lib.write_atomic` directly (0312);
  `"def write_json"` in `ccp/queue.py` only calls `lib.write_json`. `git grep -n '\.write_text(' -- ccp/architect.py`
  at `9691fd9c`: 2 lines, the pass's `reviews/<rid>.failed.txt` and `reviews/<rid>.md`, both in the queue.
  Ruled: the line becomes "Writes to the queue are atomic: `lib.write_atomic`, or `queue.write_json`, which calls it,
  under `file_lock` where two writers can meet; events go through `queue.emit`." (the sentence on events is kept as
  it is now, joined). Both `write_text` calls in `ccp/architect.py` become `lib.write_atomic` calls with the same
  text; `architect.py` already imports from `lib`.
- **F12.** `git ls-files queue` at `9691fd9c`: `queue/README.md` only. `git grep -nE 'queue/README' -- ccp scripts tests
  README.md docs/spec` at `9691fd9c`: no line. SPEC §23.7 and `README.md` already say where the queue lives.

## Scope

- **In:** `scripts/observability/CLAUDE.md` (its first paragraph); `ccp/CLAUDE.md` (the queue-write convention);
  `ccp/architect.py` (the two queue writes); `queue/README.md` (removed).
- **Out:** `lib.py` itself; E17's and E27's text (E17 is amended by the triage); the move of `lib.py` into `ccp`
  (deferred, `docs/ROADMAP.md`).

## dod_checks

- id: `doc-01`
  story: As a developer, the observability doc names lib.py's binding reader and seat table.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'read_binding' scripts/observability/CLAUDE.md`.
    2. Run `grep -c 'SEAT_IDS' scripts/observability/CLAUDE.md`.
  expect: each prints `1` or more.
  dry run (`9691fd9c`): each printed `0`.
- id: `doc-02`
  story: As a developer, ccp's conventions name the atomic write the code uses.
  setup: As `doc-01`.
  steps:
    1. Run ``grep -c "queue.py\`'s helpers" ccp/CLAUDE.md``.
    2. Run `grep -c 'lib.write_atomic' ccp/CLAUDE.md`.
  expect: step 1 prints `0`; step 2 prints `1`.
  dry run (`9691fd9c`): step 1 printed `1`; step 2 printed `0`.
- id: `code-01`
  story: As a reader of the queue, the architect's report and failure text are written atomically.
  setup: As `doc-01`.
  steps:
    1. Run `git grep -n '\.write_text(' -- ccp/architect.py`.
    2. Run `git grep -c 'write_atomic(' -- ccp/architect.py`.
  expect: step 1 prints nothing (exit 1); step 2 prints `ccp/architect.py:2` or more.
  dry run (`9691fd9c`): step 1 printed 2 lines (`failed.txt`, `.md`); step 2 printed nothing (exit 1).
- id: `doc-03`
  story: As a developer, the repo has no tracked directory for a queue that lives elsewhere.
  setup: As `doc-01`.
  steps:
    1. Run `git ls-files queue`.
  expect: prints nothing.
  dry run (`9691fd9c`): printed `queue/README.md`.

## Implementation notes

## Verification notes
