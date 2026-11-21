---
task_id: 0229-orientation-extras-from-one-ccp-call
title: The orientation hook gets everything it appends from one ccp call
status: pending
kind: refactor
depends_on: []
review_refs: ["sh-20261120T235613Z-4fce#F08"]
rule_refs: ["E15", "E16"]
review_point: R15
paths: ["plugin/hooks/orientation.sh", "ccp/cli.py", "ccp/notify.py", "docs/cli/01-model.md", "tests/test_orientation_tail.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0229-orientation-extras-from-one-ccp-call

## Intent

The SessionStart orientation hook runs two `ccp` subprocesses in series after the orientation text
(the pending notices, then the allowance warning), each with a 3-second timeout under the hook's
10-second limit, and renders them in Python embedded in bash that only subprocess tests reach.
ADR-0044 adds a third line (open follow-ups). After this task the hook makes one call,
`ccp orientation --tail`, which returns the rendered text of everything appended after the
orientation, built in `ccp` and unit-tested there. What a session sees is unchanged.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0044 (`sh-20261120T235613Z-4fce`), F08.
- **The two calls.** `plugin/hooks/orientation.sh` runs `ccp notify pending` and `ccp allowance status`
  (`grep -c 'timeout=3' plugin/hooks/orientation.sh` at `8aefa59`: two lines), and renders the
  "Pending notices" section with its 2400-character cap and the allowance warning inline.
- `ccp orientation` already prints the hook's output by running the script.

## Scope

- **In:** `plugin/hooks/orientation.sh`, `ccp/cli.py`, `ccp/notify.py`, `docs/cli/01-model.md`,
  `tests/test_orientation_tail.py` (new).
- **`ccp orientation --tail`** prints the text the hook appends today: the pending-notices section (its
  heading, one line per notice, the cap and the "more" line) and the allowance warning, built from
  `notify.pending` and the allowance status by a function on plain values (`orientation_tail(rows,
  warning) -> str`).
- `docs/cli/01-model.md` gains a `ccp orientation --tail` row (the text the hook appends after the
  orientation: pending notices and the allowance warning; writes nothing; §9.3).
- **The hook** makes that one call, with one 3-second timeout, and appends its stdout; a failed or slow
  call appends nothing, as today.
- **Tests** in `tests/test_orientation_tail.py` (new): `orientation_tail` with no notice and no warning
  is empty; with notices it gives the heading and one line each; past the cap it ends with the "more"
  line; the warning is appended.

## dod_checks

- id: `ot-01`
  story: As a plane developer, what orientation appends is unit-tested in ccp.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_orientation_tail 2>&1 | tail -10`.
  expect: exit 0, the Scope's four tests listed `ok`.
  dry run: n/a — the module is new.

- id: `ot-02`
  story: As a lead, the hook makes one ccp call.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c 'timeout=3' plugin/hooks/orientation.sh`.
  expect: prints 1.
  dry run (`8aefa59`): prints 2.

- id: `ot-04`
  story: As a plane developer, the tail tests bite.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `orientation_tail` drops the "more" line past the cap.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_orientation_tail`.
  expect: at least one failure (the cap test).
  dry run: n/a — the module is new.

- id: `ot-03`
  story: As a lead, the session's orientation reads as before.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_orientation_hook tests.test_orientation_command tests.test_notify_upgrade 2>&1 | tail -3`.
  expect: exit 0, `OK`.
  dry run (`8aefa59`): `OK`.

## Implementation notes

- `notify.orientation_tail(rows, warning) -> str` (in `ccp/notify.py`) holds the text the hook used to build
  inline: the "Pending notices" heading, one line per notice (reason cut at 500), the 2400-character body cap
  with the "more" line, then the warning cut at 600. The text is byte-for-byte what the hook appended, leading
  blank lines included, so the hook's 9500-character cut of the orientation is unchanged.
- `ccp orientation --tail` (`cli._orientation_tail`) reads `notify.pending` and `usage.status` (no sample, so it
  writes nothing) and prints that text. A part it cannot read is left out; with no `QUEUE_ROOT` it prints nothing
  and exits 1, as the two old calls each gave nothing there. The hook appends stdout only on exit 0.
- The hook makes the one call with one 3-second timeout (`grep -c 'timeout=3'` prints 1).
- Existing tests whose stand-in `ccp` answered `notify pending` / `allowance status`
  (`tests/test_notify_upgrade.py` `OrientationHookNotices`, `tests/test_machine_account.py`
  `SessionStartCheck`) now answer `orientation --tail` with the text `notify.orientation_tail` builds from the same
  rows and warning; their expectations are unchanged.
- `tests/test_orientation_tail.py` has the four Scope tests plus a cut-reason test and three `--tail` command tests
  (warning from the allowance status, a fired notice, no queue).

## Verification notes
