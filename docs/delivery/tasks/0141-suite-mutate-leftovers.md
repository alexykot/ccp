---
task_id: 0141-suite-mutate-leftovers
title: A product whose tests are whole scripts gets a recorded mutation check, and a hand-made mutant never needs a restore in a seat's own worktree
status: done
kind: feature
depends_on: []
spec_refs: ["S20", "S14"]
review_point: R9
paths: ["ccp/mutate.py", "templates/prompts/_common.md", "templates/prompts/verify.md", "plugin/agents/delivery-implementer.md", "plugin/agents/delivery-reviewer.md", "plugin/agents/delivery-verifier.md", "contracts/plane_config.schema.json", "docs/spec/03-quality.md", "docs/cli/03-quality.md", "scripts/CLAUDE.md", "tests/test_mutate.py", "tests/test_prompt*.py"]
adopt: "plane.json mutate.command: a product with no per-test runner, whose tests are whole scripts, sets it to run one script, `sh {test}`"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0141-suite-mutate-leftovers
## Intent

A product whose tests are whole scripts (shell or any other single-file test) proves its tests bite
with a recorded `ccp mutate` run, as any other product does; and where a product still declares no
`mutate.command`, a seat that breaks code by hand does it in a throwaway mutation worktree, so it never
has to restore a committed file in its own worktree, which the permission system may deny.

## Context (not checked)

- `ccp mutate` refuses (exit 2) when plane.json `mutate.command` is null, the default:
  `"plane.json names no mutate.command"` in `ccp/mutate.py`. The refusal says nothing about what to set.
- A product whose tests are whole scripts already can declare one: `mutate.command` is a shell template
  naming `{test}`, filled in shell-quoted (§20.6), so `sh {test}` with `--test tests/<script>.sh` runs one
  script. Nothing tells a product this: the SPEC's only example is a unittest method id
  (`git grep -n 'mutate.command' -- docs/spec/03-quality.md` at `921507e`: the one §20.6 bullet).
- Seen in an adopting product: with no `mutate.command`, the implementer overwrote a source file with
  its base content by hand, and the permission system denied the restore (a `git checkout` of its own
  committed paths), which blocked the task.
- The verify template's fallback today: "Where the product declares no `mutate.command`, break the code
  by hand in your own worktree, run the test through `ccp suite run` with `--lane {{part_lane}}`, and put
  the file back" (`templates/prompts/verify.md`). The implementer and reviewer definitions say to use
  `ccp mutate` "where the product declares `mutate.command`" and give no fallback.
- §20.6 already names a mutation worktree (`ccp wt create --kind mut`, §12.1) as a place `ccp mutate`
  runs; `ccp wt remove NAME` removes one.
- Follow-up from 0124: `scripts/CLAUDE.md` names `GATE_COLD=1` as the plane gate's cold option but not
  `CCP_SUITE_COLD`, which `scripts/gate.sh` reads too (`case "${CCP_SUITE_COLD:-}"`).
- The rest of that follow-up (`--cold` recording `cold: true` with no cached count, and `ccp verify record`
  filling `cold`) changes signed §14.2 and §14.6 text and is task 0146.
- §31.1: the §20.6 sentence below describes what the existing `mutate.command` already allows; no rule
  changes.

## Scope

- **In:**
  - `ccp/mutate.py`: the refusal with no `mutate.command` adds what to set, naming both forms: a per-test
    runner (`python3 -m unittest {test}`) and a whole-script test (`sh {test}`, `--test` the script's path).
  - §31.1: `docs/spec/03-quality.md` §20.6, after the bullet **The product's command.**, one sentence: a
    product whose tests are whole scripts sets `mutate.command` to `sh {test}` (or the interpreter its
    scripts need) and names the script as `--test`.
  - `contracts/plane_config.schema.json`: the `mutate.command` description gives the same example.
  - `docs/cli/03-quality.md`: the `ccp mutate` row says the same in one clause.
  - `templates/prompts/_common.md` (the line on recorded test runs) and `templates/prompts/verify.md` (the
    fallback quoted in Context): where the product declares no `mutate.command`, the seat makes a
    mutation worktree at the head it judges (`ccp wt create --kind mut --task <id> --sha <head>`), breaks
    the code there by hand, runs the test there through `ccp suite run --run <run_id> --lane <part lane> --
    <command>`, and removes the worktree with `ccp wt remove <name>`; never a hand edit and restore in
    its own worktree.
  - `plugin/agents/delivery-implementer.md`, `delivery-reviewer.md`, `delivery-verifier.md`: the same
    fallback, one sentence each, beside their existing `ccp mutate` sentence.
  - `scripts/CLAUDE.md`: the gate's cold option is `GATE_COLD=1`, which `ccp suite run --cold` sets through
    `CCP_SUITE_COLD`.
  - Tests that pin the template text the change rewrites, if any (`tests/test_prompt*.py`).
- **Out:**
  - Running `ccp mutate` without a `mutate.command` (an option that takes the command per call).
  - `--cold`'s record and `ccp verify record`'s `cold` (task 0146).

## dod_checks

- id: `mut-01`
  story: As a seat in a product whose tests are whole scripts, my mutation check is recorded.
  setup: a scratch product (`tests/helpers.py`) with plane.json `mutate.command` `sh {test}`, a source file `lib.sh` holding a function, a test script `tests/t.sh` that exits 1 when that function's output changes, and an open implement run with its recorded `impl` worktree.
  steps:
    1. Run `ccp mutate --run <run_id> --test tests/t.sh --mutant 'lib.sh:<old>=><new>'` in the worktree.
  expect: exit 0; the run record's `mutation` list holds one row, `killed`, for test `tests/t.sh`; `lib.sh` is byte for byte as before.
  dry run: n/a.
- id: `mut-02`
  story: As a seat in a product with no mutate.command, I am told what to set.
  setup: a scratch product with no `mutate` block and an open implement run.
  steps:
    1. Run `ccp mutate --run <run_id> --test x --mutant 'a.py:1=>2'`.
  expect: exit 2; stderr names `mutate.command`, `{test}` and the whole-script form `sh {test}`.
  dry run: n/a.
- id: `prompt-01`
  story: As a verifier in a product with no mutate.command, I break code in a mutation worktree, not my own.
  setup: a scratch product with no `mutate.command` and a task ready for verify.
  steps:
    1. Render the verify prompt (`ccp prompt verify <task> --pr <n> --head <sha>`), and read `plugin/agents/delivery-implementer.md`, `delivery-reviewer.md` and `delivery-verifier.md`.
  expect: the prompt and each definition name `ccp wt create --kind mut` and `ccp wt remove` for that case; neither the prompt nor `templates/prompts/verify.md` holds the words "put the file back".
  dry run: n/a.
- id: `doc-01`
  story: As a plane developer, the scripts doc names the cold signal.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n CCP_SUITE_COLD -- scripts/CLAUDE.md`.
  expect: at least one line.
  dry run (`921507e`): no line (exit 1), as expected before the change.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): premises re-measured at `8376cdd`: §20.6 holds one `mutate.command`
  bullet, the refusal named nothing to set, the verify fallback said "put the file back", and
  `scripts/CLAUDE.md` named `GATE_COLD=1` but not `CCP_SUITE_COLD`. The refusal now names
  `{test}`, a per-test runner and `sh {test}`. The §20.6 sentence is appended to the end of the
  **The product's command.** bullet. The fallback in `_common.md`, `verify.md` and the three agent
  definitions sends the seat to a `mut` worktree (`wt create --kind mut --task <id> --sha <head>`),
  the test through `ccp suite run` on the part lane, and `wt remove <name>`. `_common.md` gives
  `--sha <head>` (the committed head the seat tests or judges); `verify.md` fills in the PR head.
  `tests/test_prompt_tools.py`: two tests that said no prompt names `--kind mut` now say none does
  outside that fallback clause; the new whole-script tests are in `tests/test_mutate.py`.

## Verification notes
- 2026-11-18 — verifier, PR #157 head `edb6d63` (squash `68cc5d7`): APPROVE. Passed: mut-01, mut-02, prompt-01, doc-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0141-suite-mutate-leftovers.json.

