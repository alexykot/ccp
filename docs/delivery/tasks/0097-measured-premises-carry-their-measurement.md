---
task_id: 0097-measured-premises-carry-their-measurement
title: A brief's measured premises name the command and commit they came from, and the implementer re-checks them
status: done
kind: chore
depends_on: []
spec_refs: ["S5", "S13"]
review_point: R5
paths: ["plugin/skills/writing-tasks/", "plugin/agents/delivery-implementer.md", "templates/prompts/", "ccp/tasklog.py", "tests/test_tasklog*.py", "tests/test_plugin.py"]
created: 2026-11-12
updated: 2026-11-13
---

# Task: 0097-measured-premises-carry-their-measurement

## Intent

A count, size, list of sites or "X already/never happens" claim in a task brief names the command
that measured it and the commit it ran at, and the implementer re-runs it at its base before
building, so a premise that moved between writing and claim costs a scope question, not a wasted
round (§5, §13).

## Context (not checked)

- Accepted plane proposal. A managed product's friction notes showed briefs whose factual premises
  were wrong at claim, each costing a probe, a scope question or an extra round. The plane's own
  tasks had the same: three this week rested on a false premise.
- §31.1: skill and brief guidance plus an optional warning describing its own feature; no merge
  gate.
- Ruling (spec question sm-20261113T081609Z-5cf3, commit 839ce6e), verbatim: "Yes: add one
  sentence to the §5.5 table's Context row, beside the Scope path warning, describing the new
  warning (a count, size, site list or 'never'/'already' claim in Context with no command and commit
  beside it is warned about by ccp tasks check, not refused). It's §31.1, the task's own feature.
  Editing docs/spec/01-model.md outside the declared paths is accepted; list it in the PR body.
  Record this ruling in 0097's Context with a ruling round, then review."

## Scope

- **In:**
  - The writing-tasks skill: any count, size, site list or "already/never happens" claim in a brief
    names, in Context, the command that measured it and the commit it was run at.
  - The implementer brief and implement prompt: the first step re-runs those commands at the base,
    and if a figure changed materially, stops with a scope question before building.
  - `ccp tasks check` warns (not fails) on a pending task whose Context states a number with no
    backticked command on the same line.
- **Out:** checking that the command's output matches.

## dod_checks

- id: `check-01`
  story: As a task writer, an unmeasured number is flagged.
  setup: a scratch product with a pending task whose Context says "only 2 call sites exist" and
    another saying "`git grep -c foo` at abc1234: 2 call sites".
  steps:
    1. Run `ccp tasks check`.
  expect: a warning names the first task's line; none for the second; the check still passes.
  dry run: on the merge base no warning is given.
- id: `check-02`
  story: As an implementer, I re-check premises first.
  setup: a checkout of the PR head.
  steps:
    1. Read the implementer brief, the implement prompt and the writing-tasks skill.
  expect: each states the rule as above.
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

- 2026-11-13 (implement): `ccp tasks check` warns, never fails, about a task not yet done or dropped
  whose Context has a line stating a number with no backticked command on it, named `path:line`
  (`tasklog.unmeasured_numbers`, called from `tasklog.warnings`). Narrowest rule taken where the
  brief left it open: a number is a run of digits that is not part of an id or a ref (after a
  letter, `§`, `-`, `.`, `/`, `:` or `#`), not zero-padded, not a list marker and not in a date
  written with its month's name; fenced blocks and code spans are not read for numbers; a command is
  a code span of two words or more, so a lone backticked path does not clear the line.
- The rule is stated in the writing-tasks skill (Writing the brief), the implementer brief and the
  implement prompt template; `tests/test_plugin.py` pins each by its tokens.
- No SPEC text: the task gives none, so the warning is not yet described in SPEC §5.5's Context
  row (flagged to the runner).
- 2026-11-13 (implementer, ruling round 1): per the lead's ruling sm-20261113T081609Z-5cf3, SPEC
  §5.5's Context row now carries one sentence: a count, size, site list or "already"/"never" claim
  names, on its line, its command and commit, and `ccp tasks check` warns, without refusing, about a
  Context line of a task not yet done that states a number with no backticked command. The warning's
  half is worded as built (a number with no command on its line), not as the ruling's shorthand
  (which reads as if the check also saw the commit and the "already"/"never" claims): the check
  detects neither, and the Scope asked for neither. `docs/spec/01-model.md` is outside the declared
  paths, accepted by the ruling. No code or test changed. Merged `origin/main` (839ce6e) first.
- 2026-11-13 (implementer, fix round 1): review MAJOR 1: two single-word code spans on one line
  matched the old command regex as one span (it ran across the backticks), so a line citing two
  paths next to a count was not warned about. A line is now cleared only when one of its code spans
  (`CODE_SPAN_RE`, each span on its own) holds two words or more; the cross-backtick
  `COMMAND_SPAN_RE` is gone. Review NIT 1: the warning no longer skips a task whose id does not
  parse as a number; `unmeasured_numbers` runs before that skip and keeps its own done/dropped skip.

## Verification notes

- 2026-11-13 — verifier, PR #96 head `f3976f2` (squash `056eda7`): APPROVE. Passed: check-01, check-02, check-03. Gate: `python3 -m unittest discover -s tests -t .` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0097-measured-premises-carry-their-measurement.json.
