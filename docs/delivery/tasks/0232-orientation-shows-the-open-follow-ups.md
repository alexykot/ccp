---
task_id: 0232-orientation-shows-the-open-follow-ups
title: The lead's orientation shows how many follow-ups are open, and the command that lists them
status: pending
kind: feature
depends_on: ["0223-a-follow-up-is-tracked-not-left-in-notes", "0229-orientation-extras-from-one-ccp-call", "0230-the-lead-decides-each-follow-up"]
spec_refs: ["S9"]
adr_refs: ["0044 D4"]
review_point: R15
paths: ["ccp/cli.py", "ccp/followups.py", "docs/spec/01-model.md", "docs/adr/0044-a-follow-up-is-tracked-not-left-in.md", "tests/test_orientation_follow_ups.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0232-orientation-shows-the-open-follow-ups

## Intent

ADR-0044 has the lead decide each follow-up before its review point closes; a lead who does not
know some are open cannot. After this task, when any are open, the lead's session start shows one
line after the pending notices: how many are open and `ccp tasks follow-ups --open`, the command that
lists them. It is not a notice and fires nothing on the operator's channel.

## Context (not checked)

Measured at `31a7d7b`.

- Builds ADR-0044 D4's orientation line, accepted by the operator on 2026-11-20; D4's list is 0230.
- **Shaped** by `sh-20261120T235613Z-4fce`, F08: the hook gets everything it appends from one call,
  `ccp orientation --tail` (0229), so this line is one more part of that text, built in `ccp` and
  unit-tested on plain values, not a third subprocess in the hook.
- **The count** is `len(followups.undecided(runs))` (0230). Without `QUEUE_ROOT` the line is left out.
- §9.3's pending-notices bullet is the only orientation text after the orientation itself
  (`grep -c 'After the orientation, the hook' docs/spec/01-model.md` at `31a7d7b`: 1).

## Scope

- **In:** `ccp/cli.py`, `ccp/followups.py`, `docs/spec/01-model.md`,
  `docs/adr/0044-a-follow-up-is-tracked-not-left-in.md`, `tests/test_orientation_follow_ups.py` (new).
- `orientation_tail` (0229) takes the open count and, when it is above zero, ends with the line
  `<n> follow-up(s) open: \`ccp tasks follow-ups --open\``; none when zero or without a queue.
- ADR-0044 D4 recorded `built`.
- **Tests** in `tests/test_orientation_follow_ups.py` (new): no line at zero; the line at two, after
  the notices; no line without a queue.

### SPEC changes (signed in the brief, §31)

**a. §9.3, what follows the orientation.**

CURRENT (`docs/spec/01-model.md` at `31a7d7b`):
> - After the orientation, the hook and `ccp orientation` list the product's pending notices (`ccp notify pending`, §3.6): each one's subject, reason and the call that records it sent, within the hook's cap.

PROPOSED: (new lines after it)
> - Then, while any worker follow-up has no outcome (§13.4), one line gives how many and `ccp tasks follow-ups --open`. It is not a notice.

- **Out:** a §3.6 notice trigger, the runner's relay (0223), the list command (0230).

## dod_checks

- id: `of-01`
  story: As a lead, my session start tells me follow-ups are waiting for me.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_orientation_follow_ups 2>&1 | tail -6`.
  expect: exit 0, the Scope's three tests listed `ok`.
  dry run: n/a — the module is new.

- id: `of-02`
  story: As a plane developer, the line's zero rule bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `orientation_tail` prints the line at zero.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_orientation_follow_ups`.
  expect: at least one failure.
  dry run: n/a — the module is new.

- id: `of-03`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0232 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`31a7d7b`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `orientation_tail` (0229) is `ccp/notify.py`'s, which the task's `paths` do not list: it takes
  `open_follow_ups` (default 0) and, above zero, ends with the line, after the notices and the allowance
  warning. `followups.open_count(q)` counts `undecided` over the queue's run records; `cli._orientation_tail`
  passes it, left at 0 when the records do not read. Without a queue `--tail` prints nothing, as before.
- The Scope's `follow-up(s)` is read as a plural: `1 follow-up open`, `2 follow-ups open`.
- The hook (`plugin/hooks/orientation.sh`) needs no code change: it appends whatever `--tail` prints.
- Fix round 1 (review MINOR and NITs): `orientation --tail`'s help text in `ccp/cli.py` and its row in
  `docs/cli/01-model.md` now name the open follow-ups' count; the hook's header comment names the line; the
  tests pin only the count and the command on the last line, not the noun or its plural form.

## Verification notes
