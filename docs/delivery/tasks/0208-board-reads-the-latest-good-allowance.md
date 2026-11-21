---
task_id: 0208-board-reads-the-latest-good-allowance
title: The board reads the latest good allowance reading for the weekly tile and the checkpoint blocker
status: pending
kind: feature
depends_on: []
spec_refs: ["S25", "S28"]
review_point: R14
paths: ["ccp/board.py", "ccp/board_page.html", "tests/test_board.py", "tests/test_board_layout.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0208-board-reads-the-latest-good-allowance

## Intent

Since task 0197, a failed usage read is recorded as a row with no figures, and every rule judges the
latest good reading instead. The board still reads the raw last row. While a failed read is last,
its weekly tile shows `?%`, and its "allowance at the checkpoint" blocker disappears, even though
the claim still refuses at the checkpoint. After this task, the board judges what the claim judges:
the tile shows the latest good figure and says how old it is, and the blocker stands while the
latest good reading is past the checkpoint and its window has not reset.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/board.py` `_blockers` and `status_text` both read
  `seven = (a.get("latest") or {}).get("seven_day")`, with `a = b["now"]["allowance"]`
  (`git grep -n 'a.get("latest") or {}' ccp/board.py` at `58cf1d0`: two lines).
- `ccp/board_page.html` `render` reads `last = a.latest || {}` for the tile's figure, meter and reset
  (`git grep -n 'last = a.latest' ccp/board_page.html` at `58cf1d0`: one line).
- `now.allowance` is `usage.status(cfg, q, sample=False)`, which already returns `latest_good`
  and `in_force` beside `latest` (task 0197). `usage.weekly_over(cfg, q, row, t)` is the claim's own
  judge: the first weekly window of a good sample at or past its checkpoint while its reset is
  still ahead.
- A failed row has no `seven_day` (`usage._record` writes the unknown sample), so `latest` after a
  failed read gives `None`, the tile `?` and no blocker.
- §28.3 says the board shows "the allowance against its checkpoint", which stays true, so the SPEC
  needs no change (`grep -n 'against its checkpoint' docs/spec/04-observability.md` at `58cf1d0`:
  one line).
- Found in task 0197's review.

## Scope

- **In:** `ccp/board.py`, `ccp/board_page.html`, `tests/test_board.py`, `tests/test_board_layout.py`.
- **`board.py`:** where `now.allowance` is built, it also gets `weekly_over`: `{window, pct,
  checkpoint}`, built from the `(window, cp)` result of `usage.weekly_over(cfg, q,
  usage.latest_good(q), <now>)`, or `None` when that is None.
  - `_blockers` adds "allowance at the checkpoint: <pct>% of <checkpoint>%" (and the lapsed-decision
    text, as today) when `weekly_over` is set, and only then.
  - `status_text` takes the weekly figure from `latest_good`. When `in_force` is false and a
    `latest_good` exists, it appends `(last good reading <its at>)`.
- **`board_page.html`:** the weekly tile reads `a.latest_good || {}` for its figure, meter and reset.
  When `a.in_force === false` and `a.latest_good` exists, its `d` line adds
  ` · last good reading <ago(at)>`. `usage unread` (no allowance command) shows as today.
- **Tests:**
  - `tests/test_board.py`: samples holding a good row at 95% (weekly reset a day ahead, checkpoint
    90) followed by a failed row. The board's blockers include "allowance at the checkpoint: 95% of
    90%", and `status_text` shows `allowance weekly 95%` and the last good reading. With the good
    row's reset in the past, there is no blocker.
  - `tests/test_board_layout.py` (runs where `node` is installed): with the same allowance block, the
    rendered tile shows `95%` and `last good reading`.
- **Out:** the forecast's allowance projection, and `ccp allowance status`.

## dod_checks

- id: `bd-01`
  story: As the operator, the board keeps the checkpoint blocker while a failed read is the last row.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_board 2>&1 | grep -i 'good\|allowance'`.
  expect: the Scope's `tests/test_board.py` tests are listed `ok`.
  dry run (`58cf1d0`): the module runs 30 tests, OK; the new tests do not exist yet.

- id: `bd-02`
  story: As the operator, the weekly tile shows the latest good figure and its age.
  setup: a checkout of the PR head, on a machine with `node`.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_board_layout 2>&1 | tail -12`.
  expect: exit 0, with the tile test listed `ok`, not `skipped`.
  dry run (`58cf1d0`): the module passes; the tile test does not exist yet.

- id: `bd-03`
  story: As a plane developer, the blocker test bites, and no raw-row read is left.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `_blockers` reads `a.get("latest")` again.
  steps:
    1. On the head, run `git grep -n 'a.get("latest") or {}' ccp/board.py; git grep -n 'last = a.latest ||' ccp/board_page.html`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_board`.
  expect: step 1 prints nothing; step 2 fails, naming the blocker test.
  dry run (`58cf1d0`): step 1 prints three lines.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `board._allowance` builds `now.allowance`: `usage.status(cfg, q, sample=False)` plus `weekly_over`
  (`{window, pct, checkpoint}` from `usage.weekly_over(cfg, q, usage.latest_good(q), usage.now())`, or
  None). `_blockers` adds the checkpoint blocker from `weekly_over` alone; `status_text` takes the weekly
  figure from `latest_good` and appends `(last good reading <at>)` when `in_force` is false.
- The page's `last = a.latest` became `good = a.latest_good || {}`. The Health tab's Allowance card shared
  that variable, so its weekly, 5-hour and "read <ago>" figures now come from the latest good reading
  too, matching the tile. The tile's `last good reading` suffix is left off when `usage_read` is false,
  so `usage unread` shows as before.
- Like the blocker before it, `weekly_over` on the board is not gated on `usage_read` (the claim's
  `checkpoint_stop` is): without an allowance command no samples are written, so the two agree in practice.
- `tests/test_allowance_lapse.py` and `tests/test_board_layout.py`'s throwing-card test built
  `now.allowance` by hand with `latest` only; they now carry `latest_good` (and `weekly_over` for the
  lapsed-decision blocker).
- Fix round 1 (review MINOR-1, NIT-1, NIT-2): the tile test also checks the meter (`width:95%`) and that
  the `d` line says `resets …`, not `reset unknown`, so both stay on the good reading; its ages match
  `2.\d h ago`, so a slow render cannot turn them to `2.1 h`. `_allowance` passes `usage.status`'s own
  `latest_good` to `weekly_over` instead of reading the samples log again: the same row, so the blocker
  and the tile judge one reading.

## Verification notes
