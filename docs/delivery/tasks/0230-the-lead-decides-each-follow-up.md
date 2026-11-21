---
task_id: 0230-the-lead-decides-each-follow-up
title: The lead records each follow-up's outcome, and ccp tasks follow-ups lists them
status: pending
kind: feature
depends_on: []
spec_refs: ["S13"]
adr_refs: ["0044 D2", "0044 D4"]
review_point: R15
paths: ["ccp/followups.py", "ccp/refs.py", "ccp/tasklog.py", "ccp/cli.py", "ccp/CLAUDE.md", "docs/cli/02-delivery.md", "docs/adr/0044-a-follow-up-is-tracked-not-left-in.md", "tests/test_followups.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0230-the-lead-decides-each-follow-up

## Intent

ADR-0044 has workers state follow-ups in their reports (0223) and the lead decide each. This task
builds the lead's side on run records that carry `follow_ups`: `ccp tasks follow-up <run_id>#<n>`
records what became of one (a task, a plane proposal, or dropped with a reason), and `ccp tasks
follow-ups [--open] [--json]` lists them across tasks. The undecided list it computes is the one
source the review-point check (0231) and the orientation line (0232) read.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0044 D2 and the list of D4; D4's orientation line is 0232. Shaped by
  `sh-20261120T235613Z-4fce`; its task graph runs this beside the report section (0223), on fixture run
  records with the agreed shape `follow_ups: [{"id", "text", "outcome"}]`.
- **No § text here.** The rule that the lead decides each follow-up is 0223's §13.4 text; this task
  adds the commands and their `docs/cli` rows only (§31.1). 0223 depends on this task, so the SPEC
  never names a command that is not built.
- **Where ids live.** `ccp/refs.py` holds every id pattern (`ccp/CLAUDE.md`); the follow-up id
  `<run_id>#<n>` joins the run id pattern there (the shape's single sources).
- **A task at the tip.** D2's `--task` names a task in the task log at `origin/<integration>`; no
  helper reads the task log at a ref today (the shape's hot spots), so `tasklog` gains
  `task_ids_at(cfg, rev)`.
- **Proposals.** `ccp/plane.py` `proposals(q)` reads `plane/proposals.jsonl`.
- **Who runs it.** Only the lead: the same actor check `ccp tasks sign-off` uses.

## Scope

- **In:** `ccp/followups.py` (new), `ccp/refs.py`, `ccp/tasklog.py`, `ccp/cli.py`, `ccp/CLAUDE.md`,
  `docs/cli/02-delivery.md`, `docs/adr/0044-a-follow-up-is-tracked-not-left-in.md`,
  `tests/test_followups.py` (new).
- **`ccp/followups.py`**: `undecided(runs) -> list` on plain run records, `decide(q, cfg, fid, kind,
  ref_or_reason, by)`, and `listing(runs, open_only)`; `ccp/CLAUDE.md` lists the module under the
  runtime queue.
- **`ccp tasks follow-up <run_id>#<n> (--task <id> | --proposal <id> | --drop "<reason>")`**, needs
  `QUEUE_ROOT`, writes `outcome: {"kind", "ref" or "reason", "at", "by"}` on the run record. It
  refuses (exit 2, nothing written): an id resolving to no follow-up; `--task` naming no task at
  `origin/<integration>`; `--proposal` naming no row of `plane/proposals.jsonl`; an empty `--drop`
  reason; a caller other than the lead. Run again, it replaces the outcome.
- **`ccp tasks follow-ups [--open] [--json]`**: one line per follow-up,
  `<id> <task_id> <outcome or open>: <text>`, then `<n> open`. Exit 0.
- ADR-0044 D2 recorded `built`; D4 stays `not_built` until its orientation line lands.
- **Tests** in `tests/test_followups.py` (new): `undecided` and `listing` on plain records; each
  refusal; a decision replaced by a second; the JSON listing.

## dod_checks

- id: `fd-01`
  story: As a lead, I record what became of each follow-up and list the open ones.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_followups 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `fd-02`
  story: As a plane developer, the lead-only refusal bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `ccp tasks follow-up` skips its actor check.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_followups`.
  expect: at least one failure.
  dry run: n/a — the module is new.

- id: `fd-03`
  story: As a lead, the list runs on a real queue.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . tasks follow-ups --open --json; echo rc=$?`.
  expect: prints a JSON list (empty) and `rc=0`.
  dry run (`8aefa59`): `rc=2`, argparse refusing `follow-ups`.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
