---
task_id: 0116-prompt-and-verify-fixes
title: Unbuilt ADR decisions are caught before the gate, staged lanes take no command, the verify prompt names every record field, and carried checks are named
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S14", "S15"]
review_point: R7
paths: ["ccp/suite.py", "ccp/tasklog.py", "ccp/lifecycle.py", "templates/prompts/implement.md", "templates/prompts/verify.md", "templates/prompts/_common.md", "docs/spec/02-delivery.md", "tests/test_suite_stages.py", "tests/test_tasklog*.py", "tests/test_prompt*.py", "tests/test_tasks_close*.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0116-prompt-and-verify-fixes
## Intent

Four late failures move earlier or stop happening: an implementer learns before the gate that an
ADR decision it builds is still `not_built`; a staged lane can no longer record a gate that ran
nothing; a verifier's prompt names every field `ccp verify record` needs; and a task log names the
checks a later verify round carried from an earlier approval.

## Context (not checked)

- From four accepted product proposals; each costs a fix round or misleads a reader today.
- `ccp verify record` refuses an `adr_refs` decision left `not_built`, but only after the full gate.
- `ccp suite run --lane gate -- <cmd>` on a lane with stages replaces the stages with `<cmd>`, so `-- true` records a passed gate that ran nothing (stage resolution in `ccp/suite.py`, `"def resolve_stages"`).
- The verify prompt omits `project_id` and the list form of `findings`, and gives the verification example by a relative path workers cannot reach.
- The reconcile's verification line (`ccp/lifecycle.py`, the sentence beginning "Not run by the verifier") reads "Passed: none" when the checks were carried from an earlier approval.
- All four describe the accepted proposals' own behaviour (§31.1); no rule changes.

## Scope

- **In:**
  - `templates/prompts/implement.md` "Before the PR": run `ccp adr decide <n> <Dn> built` in the PR for each `adr_refs` decision the task builds. `ccp tasks check` warns, on the task's branch, about an `adr_refs` decision the task cites that is still `not_built` there (warning, so products stay conforming).
  - `ccp suite run`: a command after `--` on a lane that has stages is refused (exit 2), naming the lane; `templates/prompts/_common.md` says a staged lane takes no command.
  - `templates/prompts/verify.md`: `project_id: "{{project_id}}"`, `findings` as a list of strings, and the verification example's absolute path in the plane checkout.
  - The reconcile line: checks carried from an earlier approval are named as `Carried from <sha>: <ids>`.
- **Out:**
  - Refusing at `tasks check`.

## dod_checks

- id: `cmd-01`
  story: As an implementer, I am warned before the gate about an unbuilt decision.
  setup: a scratch product with an ADR whose D1 is `not_built` and a pending task citing `adr_refs: ["0001 D1"]`; then the same with D1 `built`.
  steps:
    1. Run `ccp tasks check` in each state.
  expect: exit 0 both times; one warning naming the task and `0001 D1` in the first, none in the second.
  dry run: n/a.
- id: `cmd-02`
  story: As a verifier, a staged gate cannot be replaced by a command.
  setup: a scratch product whose `gate` lane has two stages.
  steps:
    1. Run `ccp suite run --lane gate -- true`.
    2. Run `ccp suite run --lane gate`.
  expect: (1) exit 2 naming the lane, and no suite run recorded. (2) runs both stages.
  dry run: n/a.
- id: `cmd-03`
  story: As a verifier, my prompt names every field the record needs.
  setup: a checkout of the PR head.
  steps:
    1. Render a verify prompt with `ccp prompt verify` for a scratch task.
  expect: it names `project_id` with the project's id, `findings` as a list of strings, and an absolute path to `contracts/verification.example.json` that exists.
  dry run: n/a.
- id: `cmd-04`
  story: As a reader of the task log, carried checks are named.
  setup: a scratch task approved at sha A with checks `c-01`, `c-02`, then re-verified at B carrying both.
  steps:
    1. Close it and read the verification line written to the task file.
  expect: the line names `Carried from A: c-01, c-02`, and does not say "Passed: none".
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
