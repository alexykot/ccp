---
task_id: 0099-worker-prompts-arrive-whole
title: A worker proves it received its whole rendered prompt, and a verifier knows when to record with the head's own ccp
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S15"]
review_point: R6
paths: ["ccp/prompt.py", "ccp/report.py", "ccp/verify.py", "templates/prompts/", "plugin/agents/delivery-runner.md", "plugin/agents/delivery-verifier.md", "docs/spec/02-delivery.md", "tests/test_prompt*.py", "tests/test_report*.py", "tests/test_verify.py"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0099-worker-prompts-arrive-whole

## Intent

A worker's prompt is the one `ccp prompt` rendered, whole, and `ccp report` can tell when it was not.
The rendered prompt ends with a marker line that carries a token, the worker's report repeats the
token, and `ccp report` refuses a report whose token is missing or is not that run's. A verifier that
verifies a change to the verification record's own contract is told to record with the task head's
`ccp`, and `ccp verify record` says so when the verdict carries keys its contract does not know.

## Context (not checked)

- Two accepted plane proposals (operator, 2026-11-16: all approved).
- Runners retyped worker prompts into the Agent call, and the tail was cut at least twice in one week.
  The worker got a prompt that was not the rendered one, and nothing noticed. The runner now passes a
  pointer to the rendered file ("Your full instructions are in <path>. Read that file in full first
  and follow it exactly."), but nothing checks it.
- A task that adds a required field to the verification record, or raises its schema version, was
  verified by a `ccp` on PATH that predates the change. The record then failed or lost the field.
  §15.4 already reads a newer record with an older reader; what is missing is telling the verifier
  which `ccp` writes it.

## Scope

- **In:**
  - `ccp prompt <phase>` ends every rendered prompt with one line, `Prompt end: <token>`. The token is
    the run id's last 8 characters, or a short hash of the run id and the prompt text, whichever the
    implementer finds simpler to check. Each template's report section tells the worker to copy it
    into the report as `Prompt: <token>`.
  - `ccp report <run_id> FILE` refuses (exit 2, nothing written) a report with no `Prompt:` line, or
    one whose token is not the run's, naming the expected token and saying the prompt the worker read
    was probably cut. A run opened before this change (no token recorded) is not refused.
  - The runner brief's worker step says: pass the pointer to the rendered prompt file, never the text
    retyped. It also says what to do on this refusal: re-prompt the worker with the pointer
    (`--supersede` when the run never started).
  - `templates/prompts/verify.md` and the verifier agent say: when the task changes the verification
    record's contract (`contracts/verification.schema.json` or the record's version in the task's own
    diff), record with the head's own `ccp`, run as `ccp wt exec <your worktree> -- python3 -m ccp
    verify record …`, or whatever form `ccp wt exec` takes.
  - `ccp verify record` refuses a key its contract does not know, as now, and its error then adds one
    line: if the task's head carries a newer record contract, record with the head's own `ccp`.
  - SPEC §13.2 and §13.4 (the marker and the `Prompt:` line) and §15.4 (the verifier's `ccp`),
    written as text describing this task's feature (§31.1).
- **Out:**
  - The runner opening the Agent call itself. The runner still makes the call; the token makes a cut
    prompt visible.
  - A token in the verdict record. The verify run's report carries it, as every other report does.

## dod_checks

- id: `check-01`
  story: As a runner, a worker report from a cut prompt is refused.
  setup: a throwaway product with a task and an open implement run made by `ccp prompt implement`.
  steps:
    1. Read the prompt file's last line.
    2. Submit a done report with no `Prompt:` line, then one with another token, then one with the
       right token.
  expect: the last line is `Prompt end: <token>`. The first two reports are refused (exit 2) naming the
    expected token, with no report file written and the run still open. The third is accepted.
  dry run: n/a.
- id: `check-02`
  story: As a runner, a run opened before the change is not refused.
  setup: as check-01, with the run's record carrying no token (as one written by the previous `ccp`).
  steps:
    1. Submit a done report with no `Prompt:` line.
  expect: accepted.
  dry run: n/a.
- id: `check-03`
  story: As a verifier, I know when to record with the head's `ccp`.
  setup: a checkout of the PR head.
  steps:
    1. Render `ccp prompt verify` for a task, and read the verifier agent file.
    2. Run `ccp verify record` on a verdict carrying a key its contract does not know.
  expect: (1) both say to record with the head's own `ccp` when the task changes the record's
    contract, and name the command. (2) The refusal names the key and adds the line about the head's
    own `ccp`.
  dry run: n/a.
- id: `check-04`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
