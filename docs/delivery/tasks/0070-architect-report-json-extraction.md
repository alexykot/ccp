---
task_id: 0070-architect-report-json-extraction
title: The architect's report is found even when a finding quotes an unbalanced brace
status: pending
kind: bug
depends_on: []
spec_refs: ["S19"]
review_point: R4
paths: ["scripts/observability/architecture_review.py", "tests/test_architect*.py", "tests/test_architecture_review*.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0070-architect-report-json-extraction

## Intent

An architect pass whose report quotes code or text with an unbalanced `{` or `}` inside a JSON string
is read as the report it is, so the pass completes (§19.7) instead of failing as "missing summary;
missing findings".

## Context (not checked)

- `last_json_object` (scripts/observability/architecture_review.py) looks for a fenced JSON object,
  then scans bare text backwards counting `{` and `}` without reading strings. A finding whose
  evidence quotes `'X = {'` throws the count off, and it returns the last parsable inner object (the
  last finding), which fails validation. A managed product's architect passes failed this way three
  times in a row; the saved `failed.txt` starts mid-JSON only because it keeps the last 20,000
  characters.
- Accepted plane proposal (triaged 2026-11-12).

## Scope

- **In:** find the report with a string-aware parse: for each `{` in the final message, from the
  first, try `json.JSONDecoder().raw_decode` and keep the outermost (longest) dict, preferring the
  last such top-level object; keep the fenced-block path first. Every caller of `last_json_object`
  (architect pass, shape, triage, docs audit leftovers) gets the fix. Tests: an unfenced report whose
  finding quotes an unbalanced `{`, one with an unbalanced `}`, prose before and after the object, a
  fenced report, and two top-level objects (the last wins).
- **Out:** the 20,000-character cap on `failed.txt` (it only affects the saved copy).

## dod_checks

- id: `check-01`
  story: As a lead, an architect report quoting an unbalanced brace is accepted.
  setup: a final message `Report:\n` followed by a pretty-printed report whose second finding's
    evidence is `x.py:274 — 'EVENT_KINDS = {'`.
  steps:
    1. Call `last_json_object` on it.
  expect: the returned dict has `summary` and `findings`, with both findings.
  dry run: on the merge base it returns the second finding (`id`, `evidence` keys only).
- id: `check-02`
  story: As a lead, the other report shapes still parse.
  setup: a fenced report; a report with an unbalanced `}` in a string; two top-level objects in one
    message.
  steps:
    1. Call `last_json_object` on each.
  expect: the full report each time, and the last of two objects.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
