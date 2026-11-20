---
task_id: 0190-the-plane-takes-its-own-upgrade-steps
title: The plane's own plane.json takes the ADR-0043 upgrade steps before their grace ends
status: pending
kind: feature
depends_on: ["0181-models-block-and-role-defaults", "0182-language-is-a-required-key", "0183-gate-lane-is-required", "0185-architect-on-by-default", "0186-account-facts-on-the-machine", "0187-short-plane-json", "0192-plane-json-constants-and-defaults"]
spec_refs: ["S8", "S19", "S29"]
review_point: R12
paths: ["docs/delivery/plane.json", ".claude/settings.json"]
adopt: none
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0190-the-plane-takes-its-own-upgrade-steps

## Intent

The plane manages itself, so it is the first product to take the steps ADR-0043 asks of every product
with history, before 0191 turns the grace's warnings into refusals: its plane.json names its language,
records its architect adoption point, gives its implementer models in the `models` block, and drops
every key that is now removed, merged or a constant. Its own commands then load with no deprecation
warning.

## Context (not checked)

- ADR-0043 D9's migration (the required steps for a product with history), accepted 2026-11-19.
- Depends on the tasks that introduce each step: 0182 (`language`), 0183 (the gate lane: the plane
  already has one, `scripts/gate.sh`), 0185 (the adoption point), 0181 (`models`), 0186 (the account
  keys: the plane's plane.json sets none), 0187 (removed and merged keys) and 0192 (constant keys).
- Today, at `e9ff0fc`, `docs/delivery/plane.json` holds `package_docs.language: python`,
  `workers.implementer_model {small: sonnet, refactor: sonnet}`, `task_log.dir`, `worktrees.dir`,
  `package_docs.doc_name`, `docs.workers: 4`, `estimate.auto: true`, `review_points.file`, and no
  `architect` block (`cat docs/delivery/plane.json` at `e9ff0fc`).
- Decided here:
  - `language: python`; `package_docs.language` deleted.
  - `architect: {"shape_from_task": "<NNNN>"}` where `<NNNN>` is the next task number when this task
    is built (the highest task file number plus one, at the build's base). The house rules are
    `docs/ENGINEERING.md`, the default. The seat then enforces from that task on; nothing before it
    is judged by the kind rules (the R12 refactors cite `spec_refs`, as the task check needs with the
    seat off).
  - `models: {"implementer_small": "sonnet", "implementer_refactor": "sonnet"}`; `workers` deleted.
  - Every key `ccp --root . upgrade status` then lists as removed, merged or a constant is deleted,
    accepting the constant (the plane files no proposal to keep one); each step taken is recorded in
    `upgrade.taken` with this task's PR.
  - `.claude/settings.json` gains `"model": "opus"`, the lead's model (0181).
  - The plane's binding lives outside the repo (§8.3): its removed keys (0188) are the operator's to
    delete on the machine, and the machine file's account keys (0186) likewise. The PR body says so.
    No file outside the repo is written.

## Scope

- **In:**
  - `docs/delivery/plane.json`, `.claude/settings.json`: as decided.
- **Out:**
  - The plane's binding and the machine file (the operator's). Code.

## dod_checks

- id: `pl-01`
  story: As the operator, the plane's plane.json takes the required steps.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -c "import json; d=json.load(open('docs/delivery/plane.json')); print(d.get('language'), 'language' in d.get('package_docs', {}), bool(d.get('architect', {}).get('shape_from_task')), d.get('models'), 'workers' in d)"`.
  expect: prints `python False True {'implementer_small': 'sonnet', 'implementer_refactor': 'sonnet'} False`.
  dry run (`e9ff0fc`): printed `None True False None True`.
- id: `pl-02`
  story: As the operator, the plane has no upgrade step left to take but the binding's.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp --root . upgrade status` and list each step whose `check` is `not taken` and whose `adopt` names `plane.json`.
    2. Run `ccp --root . tasks check` and read its stderr.
  expect: step 1 lists no step from 0181, 0182, 0183, 0185, 0187 or 0192; step 2 exits 0 with no `deprecated`, `unknown key` or `moves to` warning about `docs/delivery/plane.json`.
  dry run: n/a — those steps come with their tasks.
- id: `pl-03`
  story: As the operator, the architect seat is on and adopted, and not due at once.
  setup: a checkout of the PR head, with `QUEUE_ROOT` set to the plane's queue (read only).
  steps:
    1. Run `ccp --root . architect due`.
  expect: prints `"enabled": true` and `"due": false`.
  dry run (`e9ff0fc`): printed `"enabled": false` with `"reason": "no architect block in docs/delivery/plane.json"`.
- id: `suite-01`
  story: As a plane developer, the plane's own checks still pass under its new configuration.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp docs check` and `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.
- Lead's rulings on this task (questions sm-20261120T134838Z-ddcd), verbatim:
  - r1 (suite-01): "E1: change E1's check line in docs/ENGINEERING.md to 'check: pass — the verifier's gate runs the suite on every task (§15); an architect.checks entry would run the gate inside itself'; fix the stale docs.checks mentions for E3, E16 and E18 to architect.checks; docs/ENGINEERING.md is added to 0190's scope; no SPEC text changes; claude_md_dirs and moving the command rules to architect.checks with E2 and E12 are accepted as part of adopting."
  - r2 (pl-03): "Notes and drift counting from the queue's start is a defect against ADR-0043 D7 and §19.11; task 0196 (PR #222) makes only the cadence count before a product's first pass; 0190 waits for 0196, so pl-03 holds as written once 0196 is merged. Adoption point: apply the task's own rule at the build's final base, highest task number plus one; with 0195 and 0196 on main that is 0197; rebase onto main after 0196 merges and set it then."

## Implementation notes

*Append-only, newest last.*

- `docs/delivery/plane.json`: `architect.shape_from_task` is `"0196"` (the base had 0194 as its highest task file; the catch-up merge brought 0195, so the next number is 0196),
  `models` holds `implementer_small` and `implementer_refactor` as `sonnet`, and `package_docs.doc_name` and
  `docs.workers` are deleted (the constants apply). At the base the file already had no `package_docs.language`,
  `workers`, `task_log`, `worktrees` or `review_points` keys (0181, 0182, 0187 and 0192 had removed them), so
  `ccp upgrade status` listed only `doc_name` and `docs.workers` as constants to delete. `estimate.auto` is not
  listed, so it stays.
- `upgrade.taken` records 0181, 0182, 0183, 0185, 0187 and 0192 with this task's PR.
- `.claude/settings.json` gains `"model": "opus"`.
- Added beyond the task's text, because the suite fails without them (the task did not see them):
  - `package_docs.claude_md_dirs` lists `ccp`, `ccp/doclang`, `contracts`, `scripts`, `scripts/observability` and `tests`:
    with `doc_name` deleted the constant `.claude.md` applies, and these directories carry `CLAUDE.md`; listing them
    keeps the files and renames nothing.
  - With the seat adopted, `ccp docs check` holds `docs/ENGINEERING.md`'s command rules to `architect.checks`
    entries. `docs.checks` (`leak-check`, `merge-helper`, `config-reader`, `language-pack`) moved there as E3, E14,
    E16 and E18 (the `docs` block is gone: its `workers` is deleted too); E12 runs
    `tests.test_plane_config_defaults`; E2 tests that no `state/*` branch is left.
- Open: E1 ("the full suite passes", `ccp suite run --lane gate`) has no `architect.checks` entry, so `ccp docs check`
  and the gate's `test_the_docs_are_clean` fail on it: the gate runs the docs check, so a command running the gate
  would recurse. See the implement report.
- Open: `ccp architect due` prints `"due": true` here, not `"due": false`. With no pass yet, the friction-note
  and health-drift triggers (§19.6) count every note and task since the queue began, not from the adoption
  point; only the cadence trigger is counted from it. See the implement report.
- Ruling round 1 (rulings r1 and r2 above, recorded verbatim in Context):
  - r1: `docs/ENGINEERING.md` is in scope. E1's check line is now `check: pass`, with the reason that the
    verifier's gate runs the suite and an `architect.checks` entry would run the gate inside itself; the
    intro and E3, E16 and E18 name `architect.checks` instead of `docs.checks`. The `architect.checks`
    entries for E2, E12, E3, E14, E16 and E18, and `claude_md_dirs`, stay. This closes the first "Open" note
    above.
  - r2: `architect.shape_from_task` stays `"0196"`: at this merge, task 0196 (PR #222) is neither merged nor
    on `origin/main`, whose highest task is 0195. The ruling sets `"0197"` once 0196 is on main (merge
    `origin/main`, never rebase, then change that one value). Until task 0196 merges, `ccp architect due`
    prints `"due": true` (the second "Open" note above): that is expected, and not worked around.
- Fix round 1 (task 0196 is merged, `origin/main` merged in):
  - `architect.shape_from_task` is now `"0197"` (the highest task on `origin/main` is 0196), and the
    `upgrade.taken` text for 0185 names `0197` in the same commit (review MINOR 2).
  - Review MINOR 1, recorded and not changed: dropping `package_docs.doc_name` stops `scripts/git-hooks/CLAUDE.md`
    being judged by `ccp docs check`, because the constant `.claude.md` applies and the directory is not in
    `claude_md_dirs`. Listing it there fails the size check: `source()` in `ccp/pkgdocs.py` excludes only
    `doc_name`, so a listed `CLAUDE.md` counts its own `.md` lines as source (and it loosens the size check
    for the six listed directories). A code follow-up is the lead's call; no code changed here.
  - Review NIT 3: `docs/ENGINEERING.md` E3, E16 and E18 name their `architect.checks` entries by rule id
    (`E3`, `E16`, `E18`).
  - Review NIT 4: `docs/ENGINEERING.md` E12 now says the check is the schema-defaults test the `architect.checks`
    `E12` entry runs (`python3 -B -m unittest -q tests.test_plane_config_defaults`), which the gate also runs.

## Verification notes
