---
task_id: 0235-one-approval-judge-for-merge-ok-and-verify-check
title: merge-ok and ccp verify check judge a record with one function, and verify check refuses a verdict with no head
status: pending
kind: feature
depends_on: ["0226-one-pr-host-module-github-only"]
spec_refs: ["S15"]
review_refs: ["sh-20261121T000350Z-5ef1#F06"]
review_point: R15
paths: ["ccp/verify.py", "tests/test_verify.py", "tests/test_verify_judge.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0235-one-approval-judge-for-merge-ok-and-verify-check

## Intent

§15.5 offers two merge-time judges of a verification record: `ccp verify merge-ok` and, for a merge
step that does not read the PR host, `ccp verify check`. They build their refusals separately, and
`verify check` is the weaker: it applies the producer rule but not the approve rule, and passes an
approve with no `head_sha`, which `merge-ok` and `ccp verify record` both refuse (§15.4). After this
task both call one function that judges a record against a head (approve, head, gate, producers), so
`verify check` refuses what `merge-ok` refuses and ADR-0045's marked-check refusal (0237) lands once.

## Context (not checked)

Measured at `8aefa59`.

- From the shape of ADR-0045 (`sh-20261121T000350Z-5ef1`), F06, and the new house rule E20.
- **The judges.** `def refusal` (`ccp verify check`) runs `record_errors` and `producer_errors` and
  returns early when the record has no `head_sha`; `def merge_ok` adds `approve_errors`.
- **The test that pins the gap.** `tests/test_verify.py`
  `test_a_missing_head_sha_passes_check_and_a_different_one_is_refused`
  (`grep -c 'def test_a_missing_head_sha_passes_check' tests/test_verify.py` at `8aefa59`: 1) expects
  exit 0 for a verdict with no head; this task changes that expectation to a refusal.
- **Depends on 0226**, which gives `ccp/prhost.py` the `PrFacts` value and splits `merge_ok` into the
  read and a decision on plain values (`merge_ok_reasons(facts, rec, …)`); the judge is built on that
  split, so it never reads the PR host itself.
- **No SPEC change.** §15.4 already says `record` refuses "an `approve` that `merge-ok` would refuse
  (… no `head_sha` …)" (`grep -c 'no .head_sha., or no .gate.' docs/spec/02-delivery.md` at `8aefa59`:
  1), and §15.5 names `verify check` as a merge step's judge; the change brings `verify check` to the
  rule already written. A feature, since one refusal is new.

## Scope

- **In:** `ccp/verify.py`, `tests/test_verify.py`, `tests/test_verify_judge.py` (new).
- **`judge(queue, rec, head, facts: PrFacts | None) -> list[str]`** on plain values: the approve
  rule, the head (the record's `head_sha` or a recorded catch-up head), the gate and the producers,
  and, when `facts` is given, the PR's own facts (`merge_ok_reasons`' checks on state and head).
  `merge_ok_reasons` becomes `judge` with the facts `merge_ok` read; `refusal` (`ccp verify check`,
  which reads no PR host) calls it with `facts=None` in place of its own chain; `write_record`'s
  approve checks call it where they overlap.
- `ccp verify check` refuses a record with no `head_sha`, naming it.
- **Tests** in `tests/test_verify_judge.py` (new): `judge` on plain records and `PrFacts` values
  (approved at the head; no head; another head; a failed gate run; a producer refusal; a closed PR);
  `verify check` and `merge-ok` giving the same refusal for each record refusal. The `tests/test_verify.py` test above expects the refusal.
- **Out:** the marked-check refusal (0237), `verify check`'s future (the operator's decision under
  ADR-0040's shape).

## dod_checks

- id: `jd-01`
  story: As a runner, both merge-time judges refuse the same records.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_verify_judge 2>&1 | tail -12`.
  expect: exit 0, the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `jd-02`
  story: As a runner, `verify check` no longer passes a verdict with no head.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_verify 2>&1 | tail -3`.
  expect: exit 0, `OK`, with the missing-head test expecting exit 1.
  dry run (`8aefa59`): `OK`, the test expecting exit 0.

- id: `jd-03`
  story: As a plane developer, the shared judge's head rule bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `judge` skips the head comparison.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_verify_judge tests.test_verify`.
  expect: at least two failures (one from each module).
  dry run: n/a — the function is new.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `judge(cfg, queue, rec, rid, head, facts=None, recorded=None, pr=None)` returns `(reasons, body)`, the
  shape `merge_ok_reasons` had (it is that function, renamed and given the facts and the recorded time as
  optional), not the bare list of the Scope's sketch: `merge-ok` prints the body (`catch_up`, `gate_runs`,
  `match_head_commit`). It takes `cfg` (the project's id, the gate lane `catch_up_refusal` reads) and `rid`
  (the task id the record must name) besides the Scope's `queue`, `rec`, `head`, `facts`.
- With `facts=None` the PR's state is not judged; with `recorded=None` the `checked_at` against recorded-time
  rule is not (it needs `recorded_at`, a read of the queue's git state, which `check` never did).
- `refusal` (`ccp verify check`) takes `cfg` now and returns the judge's reasons joined by `; `. Its head
  message is `merge-ok`'s (`is not the approved head ... (the head differs from head_sha)`), keeping the
  word the existing check tests pin. A `check` now also refuses a wrong project, a wrong task id, an approve
  with a failed check or no gate, and takes a head `close` caught up through `catch_up`: what `merge-ok` did.
- `write_record` keeps calling `approve_errors` itself: that is the one place `judge` and `record` overlap
  (`record` has no head to judge against and holds producers to `require=True`).
- `tests/test_verify.py`: the missing-head test is renamed and expects exit 1 naming `head_sha`; the
  `MergeGate.verdict` helper carries a gate, since `check` now holds an approve to one.

## Verification notes
