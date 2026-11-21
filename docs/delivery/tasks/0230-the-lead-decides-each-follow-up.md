---
task_id: 0230-the-lead-decides-each-follow-up
title: The lead records each follow-up's outcome, and ccp tasks follow-ups lists them
status: pending
kind: feature
depends_on: ["0234-one-check-parser-and-one-file-at-rev-reader"]
spec_refs: ["S13"]
adr_refs: ["0044 D2"]
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
- **A task at the tip.** D2's `--task` names a task in the task log at `origin/<integration>`.
  `tasklog.statuses_at(cfg, ref, ids)` already reads named task files at a ref
  (`grep -c 'def statuses_at' ccp/tasklog.py` at `8aefa59`: 1), and 0234 adds `tasklog.text_at`, the
  one file-at-rev reader (listed in `depends_on`); this task builds `tasklog.task_ids_at(cfg, rev)` (the
  task ids present at `rev`, for a `NNNN` given to `--task`) on `git ls-tree` and checks the full id
  with `statuses_at`, never a reader of its own.
- **Proposals.** `ccp/plane.py` `proposals(q)` reads `plane/proposals.jsonl`.
- **Who runs it.** Only the lead: the same actor check `ccp tasks sign-off` uses.
- **Lead ruling, spec question `sm-20261121T194256Z-d51f`** (lead, commit `4b10fa2`), as the runner
  passed it:

  > Drop "0044 D4" from this task's adr_refs, leaving ["0044 D2"]. 0230 builds only D4's list; 0232,
  > which also cites D4, builds its orientation line and records D4 built. Make that one-line frontmatter
  > edit on the task branch (PR #285), note this ruling (question id sm-20261121T194256Z-d51f) in the task
  > file's `Context (not checked)` section, change nothing else, and also merge origin/main into the task
  > branch (a plain push) if it is behind the tip. Do not touch ADR 0044's decisions.

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
- **`tasklog.task_ids_at(cfg, rev) -> list[str]`**: the task ids whose files exist at `rev`; a `--task`
  given as `NNNN` resolves through it, then `statuses_at` confirms it.
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

- `ccp/followups.py` holds `undecided`, `listing`, the listing `line`, `resolve_task` (a full id, or a
  number exactly one task at the rev has) and `decide`. An outcome is `{"kind": "task"|"proposal"|"drop",
  "ref"|"reason", "at", "by"}`; a second decision replaces the first, and the command prints the one it
  replaced. Each decision records a `run` `decided` event (ids only: run, follow-up, kind and, for a task
  or proposal, its id; never the drop reason), both type and op already in the ledger's registry.
- **The lead-only check.** `ccp tasks sign-off` has no refusal of its own: it records its event as
  `queue.actor("design-seat")`. `follow-up` uses the same resolution and refuses (exit 2) when it gives
  any other actor, so `ACTOR` naming another known seat (`task-runner`, `task-verifier`, ...) is refused
  and an unset `ACTOR` reads as the lead, as for sign-off.
- **The id.** The run id pattern lives in `ccp/runs.py` (`RUN_ID_RE`, built on its `PHASES`), not in
  `ccp/refs.py`; `runs.py` is outside this task's paths. `refs.py` gains the follow-up id's shape
  (`FOLLOW_UP_ID`, `follow_up_id`, `parse_follow_up_id`), with the run part read by `runs.parse_id`.
- `--task` reads `origin/<integration>` as it is, unfetched; a task committed but not pushed is refused.
- A `--drop` reason that looks like a secret is refused too (house rule E5: text on a queue record).
- `ccp tasks follow-ups` needs `QUEUE_ROOT`, as every queue reader does.
- Fix round 1 (review MINOR-1, MINOR-2, NIT-1): the command reference row now says the command is refused
  when `ACTOR` names another seat (an unset or unknown `ACTOR` reads as the lead, as for sign-off) and lists
  the secret-like `--drop` reason among the refusals. Two tests were added: a task file at the tip with no
  status is refused (the `statuses_at` confirmation of `--task`), and an id given with surrounding whitespace
  resolves. The code is unchanged.
- Ruling round 1 (`sm-20261121T194256Z-d51f`): `adr_refs` drops `0044 D4`, leaving `["0044 D2"]`. This task
  builds only D4's list; 0232 builds D4's orientation line and records D4 built. ADR 0044's decisions are
  unchanged (D2 built, D4 not_built). No code, test or doc change; `origin/main` was already merged.

## Verification notes
