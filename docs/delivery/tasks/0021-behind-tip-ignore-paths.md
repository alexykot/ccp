---
task_id: 0021-behind-tip-ignore-paths
title: Declared paths do not make a head behind the tip; verify refuses a stale head
status: done
kind: feature
depends_on: []
spec_refs: ["S15", "S16"]
adr_refs: ["0035 D1", "0035 D2"]
review_point: R2
paths: ["ccp/lifecycle.py", "ccp/prompt.py", "ccp/config.py", "contracts/plane_config.schema.json", "docs/spec/02-delivery.md", "tests/"]
created: 2026-11-06
updated: 2026-11-10
---

# Task: 0021-behind-tip-ignore-paths

## Intent

A product setting (empty by default) lists paths whose commits on the integration branch do not count as behind the tip at close; `ccp prompt verify` refuses a head that lacks the tip beyond those paths.

## Context (not checked)

- Today only the task log, INDEX and the reconcile log are skipped, so a history-only or doc-only commit forces a merge and a re-verify.
- Ruling (operator, 2026-11-10, on PR #17): "(1) The verify refusal applies with one runner too: ADR-0035 D2 states no runner-count condition, and a single runner's PR also falls behind the tip, for example after the previous task's reconcile commit. The close-time check keeps its current condition; changing it is out of scope. (2) The setting is `merge.behind_tip_ignore` (a list of paths, empty by default), not `parallel.*`, because the verify refusal is no longer parallel-only and both D1 and D2 are about the head against the tip. If close reads it under `parallel`, read it from `merge` there too; there is no other user of the old name yet. (3) Yes: edit SPEC section 16.1, the section 16.2 example and `plugin/agents/delivery-runner.md` step 4 in this PR, so the runner merges the tip into the head before asking for verify. Section 31: these describe the task's own feature from ADR-0035 D1/D2, which the operator accepted, so the operator's 2026-11-10 ruling covers them. Quote it and the old text. No merge gate."

## Scope

- **In:** the setting, the behind-tip check at close and at verify launch, SPEC §15.6 and §16.5 wording, tests.
- **Out:** which paths a product lists.

## dod_checks

- id: `tip-01`
  story: As a runner, a doc-only commit on the tip does not cost a re-verify.
  setup: a temporary repo whose tip gained only a commit under a declared path.
  steps:
    1. Close the verified task.
  expect: close accepts the verified head.
  dry run: n/a — built by the task's test.
- id: `tip-02`
  story: As a runner, I cannot launch a verifier on a stale head.
  setup: a temporary repo whose tip gained a commit outside the declared paths.
  steps:
    1. Run `ccp prompt verify <task>`.
  expect: exit non-zero: merge the tip in first.
  dry run: n/a — built by the task's test.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): The setting is plane.json `parallel.behind_tip_ignore` (paths relative to the
  product root, a directory covering everything under it; empty by default; validated in `ccp/config.py`
  and the schema). `lifecycle.behind_tip` is the one check, shared by `ccp tasks close` and
  `ccp prompt verify`; it adds the declared paths to the task-log exclusions of the `git log` pathspec.
  Close keeps its behaviour on an unreadable tip (refuse) or head (warn). `ccp prompt verify` runs the
  check only with several runners, as close does, refusing exit 4 with nothing opened; a tip or head it
  cannot fetch is a warning in its output, and close still checks. SPEC §15.6 rule 2 and §16.5 rule 4
  carry the rule, worded from ADR-0035 D1 and D2.
- 2026-11-10 (implementer, round 2, on the ruling in Context): the setting is now plane.json
  `merge.behind_tip_ignore` (in `MERGE_DEFAULTS` and the schema's `merge` block; `parallel.behind_tip_ignore`
  is refused as an unknown key). `ccp prompt verify` runs the check with one runner too; close keeps its
  several-runners condition, so the unfetchable-tip warning says "close checks it" only with several
  runners. SPEC §15.6 rule 2, §16.1, §16.2 (example and text) and §16.5 rule 4 say so; the §8.1 block
  table in `docs/spec/01-model.md` names the key. `plugin/agents/delivery-runner.md` step 4 has the runner
  merge the tip in before asking for a verify, and step 8 says what the refusal means for a single runner,
  who skips the Several runners section.

## Verification notes

- 2026-11-10 — verifier, PR #17 head `d20b184` (squash `0a0b6f7`): APPROVE. Passed: tip-01, tip-02. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0021-behind-tip-ignore-paths.json.
