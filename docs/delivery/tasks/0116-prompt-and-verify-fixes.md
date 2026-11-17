---
task_id: 0116-prompt-and-verify-fixes
title: Unbuilt ADR decisions are caught before the gate, staged lanes take no command, the verify prompt names every record field, and carried checks are named
status: done
kind: feature
depends_on: ["0115-wait-on-a-suite-run"]
spec_refs: ["S5", "S14", "S15"]
review_point: R7
sign_off: brief
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
- The staged-lane refusal changes a § rule (§14.2), so it is quoted below and signed before the claim (§3.5). The other three describe the accepted proposals' own behaviour (§31.1).

## Scope

- **In:**
  - `templates/prompts/implement.md` "Before the PR": run `ccp adr decide <n> <Dn> built` in the PR for each `adr_refs` decision the task builds. `ccp tasks check` warns, on the task's branch, about an `adr_refs` decision the task cites that is still `not_built` there (warning, so products stay conforming).
  - `ccp suite run`: a command after `--` on a lane that has stages is refused (exit 2), naming the lane; `templates/prompts/_common.md` says a staged lane takes no command (worker guidance, not a § rule).
  - `docs/spec/02-delivery.md` §14.2. CURRENT (at `7094dfe`): "An argv lane runs as one stage named after the lane, with no `plane-docs` stage; a command after `--` is no stage." PROPOSED:
    > An argv lane runs as one stage named after the lane, with no `plane-docs` stage; a command after `--` is no stage, and `ccp suite run` refuses one (exit 2, nothing recorded) on a lane plane.json gives stages, naming the lane, so a staged gate cannot be replaced by a command.
  - `templates/prompts/verify.md`: `project_id: "{{project_id}}"`, `findings` as a list of strings, and the verification example's absolute path in the plane checkout.
  - The reconcile line: checks carried from an earlier approval are named as `Carried from <sha>: <ids>`.
- **Out:**
  - Refusing at `tasks check`.
  - Any § rule change other than the §14.2 sentence above.

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
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §14.2 edit with the PROPOSED text above.
  expect: it matches word for word, and no other § rule changes.
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

- 2026-11-17 — implementer. `ccp tasks check` warns (`adr.unbuilt_cited`, called from `tasklog.warnings`) about each
  `adr_refs` decision a task not done or dropped cites that the checkout's ADRs record `not_built`, naming the task
  file, the ref as written, the ADR decision and the `ccp adr decide <n> D<n> built` that flips it; a warning under
  `adr.strict` too, nothing without the `adr` block. It reads the checkout it runs in, so on a task branch it names
  that task, and on the integration branch every pending task that cites an unbuilt decision. `ccp suite run`
  refuses a command after `--` on a lane plane.json gives stages (exit 2, naming the lane, before anything is
  recorded; `resolve_stages`); an argv lane still takes one, and an unreadable plane.json still runs it (§14.5).
  The verify prompt names `project_id: "<id>"`, `findings` as a list of strings, and the example as an absolute
  path in the plane checkout (`verification_example`, from `queue.PLANE`). The close line names checks whose
  `rests_on` is exactly `approve at <sha>` as `Carried from <sha>: <ids>` (the sha as written, one clause per sha,
  `verify.carried_from`), drops `Passed: none` when only carried checks remain, and keeps other unrun checks under
  `Not run by the verifier`. Beyond the declared paths: `ccp/adr.py`, `ccp/verify.py`, `ccp/prompt.py`.
- 2026-11-17 — implementer, fix round 1 (review MINOR 1, narrowed as the Scope says). The unbuilt-decision
  warning fires only for the task whose branch is checked out: `adr.unbuilt_cited` reads HEAD
  (`git symbolic-ref`) and warns only when it is `task/<id>`, for that task alone. A planned task citing a
  not-yet-built decision no longer warns on the integration branch, nor on another task's branch; a checkout
  that is not a git repo, or a detached HEAD, warns about nothing. cmd-01's scratch product now runs on
  `task/0001-a`. This supersedes the earlier note's "on the integration branch every pending task".

## Verification notes
- 2026-11-17 — verifier, PR #127 head `204cea4` (squash `0e305a6`): APPROVE. Passed: cmd-01, cmd-02, cmd-03, cmd-04, check-01, suite-01. Gate: `ccp suite run --lane gate -- scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0116-prompt-and-verify-fixes.json.

