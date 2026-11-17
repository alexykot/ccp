---
task_id: 0129-health-and-config-leftovers
title: Small fixes left by R7 in health's sign-off waits, the lead's compaction knob, the verifier definition and the parallel gate's counts
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S27"]
review_point: R8
paths: ["ccp/health.py", "ccp/config.py", "plugin/agents/delivery-verifier.md", "scripts/gate_parallel.py", "tests/test_health_signoff.py", "tests/test_init_session_settings.py", "tests/test_gate_parallel.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0129-health-and-config-leftovers
## Intent

`ccp health`'s sign-off waits read cleanly, a mistyped compaction window is caught instead of
silently replaced, the verifier's definition points where its prompt does, and the parallel gate's
per-module counts agree with its total.

## Context (not checked)

- Health's `sign_off_wait` prints minutes unrounded and lists waits of zero seconds.
- `config.lead_auto_compact_window` reads a value that is not a positive whole number as the default,
  silently.
- `plugin/agents/delivery-verifier.md` gives the example verification record by a relative path;
  the verify prompt gives it by the plane's absolute path.
- `scripts/gate_parallel.py` takes each module's first `Ran N tests` line for the module's count
  while the total sums every such line.
- No SPEC change: `git grep -n -E 'sign_off_wait|Ran N tests' -- docs/spec/` at `b4de6ad` finds no
  rule on these outputs; §4.5 already says the knob is a positive whole number.

## Scope

- **In:**
  - `ccp/health.py`: sign-off waits print whole minutes; a wait under one minute is left out.
  - `ccp/config.py`: a `lead.auto_compact_window` that is not a positive whole number warns on stderr,
    naming the key and the value, and reads as the default.
  - `plugin/agents/delivery-verifier.md`: the example record is "the path the verify prompt gives".
  - `scripts/gate_parallel.py`: a module's count is the sum of its `Ran N tests` lines.
- **Out:**
  - Changing the knob's default.

## dod_checks

- id: `health-01`
  story: As an operator, sign-off waits read in whole minutes.
  setup: a scratch queue with brief sign-off waits of 0 s, 30 s and 754 s.
  steps:
    1. Run `ccp health --json`.
  expect: `sign_off_wait` lists one wait, of 13 minutes (754 s rounded to the nearest minute).
  dry run: n/a.
- id: `cfg-01`
  story: As an operator, a mistyped window is named.
  setup: a scratch product whose binding sets `lead.auto_compact_window: 35O000` (a letter O).
  steps:
    1. Run `ccp init` there with no `.claude/settings.json`.
  expect: stderr names `lead.auto_compact_window` and `35O000`; the written `autoCompactWindow` is 350000.
  dry run: n/a.
- id: `agent-01`
  story: As a verifier, my definition agrees with my prompt.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'verification.example.json' -- plugin/agents/delivery-verifier.md`.
  expect: no line gives the bare relative path `contracts/verification.example.json`.
  dry run: n/a.
- id: `gate-01`
  story: As a gate, per-module counts add up.
  setup: a fake module output holding two `Ran N tests` lines, `Ran 3 tests` and `Ran 4 tests`.
  steps:
    1. Run the unit test that feeds it to `gate_parallel.py`'s parser.
  expect: the module's count is 7 and equals its share of the total.
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

- 2026-11-17 (implementer): `sign_off_wait` keeps `wait_s`, `median_s` and `longest_s` in seconds and adds
  `wait_min`, `median_min` and `longest_min`, whole minutes rounded half up (`health._minutes`); the text
  line prints the minutes. A wait under 60 s (raw) is left out of a point's tasks, its median and its
  longest, and a point left with none is not listed.
- `config.lead_auto_compact_window` warns on stderr (`warning: the binding's lead.auto_compact_window is
  '<v>', …`) only when the key is set and is not a positive whole number; absent (or empty, which the
  binding reader drops) stays silent. It is read whenever `ccp init` keeps a binding, so the warning shows
  even when the product's own settings keep their `autoCompactWindow`.
- `gate_parallel.module_tests` sums a module's `Ran N tests` lines; `run_one` uses it, so a module's count is
  its share of `gate_result.py`'s total.
- The verifier's definition names the example as the plane's `verification.example.json` at the path the
  verify prompt gives (`{{verification_example}}`, absolute).

## Verification notes
- 2026-11-17 — verifier, PR #134 head `b6c85f9` (squash `bd86b9b`): APPROVE. Passed: health-01, cfg-01, agent-01, gate-01, suite-01. Gate: `scripts/gate.sh (ccp suite run --lane gate)` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0129-health-and-config-leftovers.json.

