---
task_id: 0273-verify-refuses-early-what-record-would-refuse
title: ccp prompt verify refuses a not_built citation and a waiver that verify record would refuse, and the per-check facts move to the judge
status: pending
kind: feature
depends_on: []
spec_refs: ["S6", "S15"]
review_refs: ["ar-20261121T223646Z-f0a7#F07", "ar-20261121T223646Z-f0a7#F08"]
review_point: R23
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/runs.py", "ccp/lifecycle.py", "ccp/report.py", "docs/spec/01-model.md", "docs/cli/02-delivery.md", "tests/test_prompt_verify_early.py", "tests/test_text_at_subroot.py", "tests/test_marked_checks_record.py", "tests/test_marked_checks_loop.py"]
adopt: "none"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0273-verify-refuses-early-what-record-would-refuse

## Intent

A verifier never does a whole verification only to have `ccp verify record` refuse the approve for
a reason known before it started. `ccp prompt verify` refuses to open a verify when the head still
records a decision the task cites as `not_built` (under `adr.strict`), so the runner sends the task
back to flip it before a verifier starts. `--waived` accepts exactly the waivers `verify record`
accepts: an operator gate approves running a step, never skipping it, at both points. A marked check
recorded `ran: false` on a genuine waiving ruling is accepted whoever produced the record, as
ADR-0045 D3 says. The per-check facts a verify run keeps are computed in the judge's module, so the
run store imports nothing from it. A product whose root sits below its git toplevel reads task and
ADR files at a commit correctly, and a test holds it.

## Context (not checked)

Measured at `8020446` unless a line says otherwise. Provenance: architect pass
`ar-20261121T223646Z-f0a7`, F07 and F08 (record in `docs/delivery/reviews/`), and three items of the
lead's follow-up log, folded here because they sit in the same judge: after 0237, `--waived` and the
`produced_by: operator` refusal; after 0234, the sub-root test. The §6.7 change is the operator's to
sign (the triage's second question).

- **F07, the late refusal.** `git grep -n 'adr_errors\|in_force_at' -- ccp` at `8020446`: 5 lines,
  all in `ccp/adr.py` (the definition) and `ccp/verify.py` (`"def adr_errors"` and its one call inside
  `"def record"`). `ccp/prompt.py` never calls `adr.in_force_at`. For 0230 that cost a ruling round, a
  second review and a second verify (the queue's run records of 0230, read by the architect; data only
  the queue holds).
- **0237, `--waived`.** `"def marked_gate"` in `ccp/prompt.py` accepts a `--waived` ruling id when
  `verify._ruling_refusal` is None. `"def _waiver_texts"` in `ccp/verify.py`, which `record` uses,
  also requires the text to name at least one id that is not a gate of class `operator` ("An
  operator gate approves running a step, never skipping it"). So `--waived CHECK=<operator gate id>`
  opens a verify whose approve `record` then refuses.
- **0237, `produced_by: operator`.** `"def marked_errors"` refuses a `ran: false` marked check when
  `c.get("produced_by") == "operator" or rests not in rulings`. ADR-0045 D3 refuses "`ran: false`
  resting on free-text operator evidence", and §15.4 says the same ("that is `ran: false` on free-text
  operator evidence"); a `rests_on` that is a waiving ruling is not free text. The lead ruled
  (follow-up log) that such a check is accepted: the refusal keys on `rests_on`, not on `produced_by`.
- **F08.** `"def check_facts"` in `ccp/runs.py` imports `carried_from` and `heads_match` from
  `ccp.verify` inside the function, and `"def unreviewed_fix"` imports `heads_match` the same way
  (`grep -n 'from ccp.verify import' ccp/runs.py` at `8020446`: 2 lines). `heads_match` is a plain sha
  comparison, called from three other modules: `git grep -c 'verify.heads_match\|from ccp.verify import heads_match' -- ccp/lifecycle.py ccp/prompt.py ccp/report.py` at `8020446`: 4, 3 and 1 lines;
  `git grep -n 'check_facts' -- ccp` at `8020446`: its definition and three lines in `ccp/verify.py`
  (two docstrings, one call in `"def _note_run"`). `tests/test_marked_checks_record.py` calls `runs.check_facts` (`git grep -c 'runs.check_facts' -- tests/test_marked_checks_record.py` at `8020446`: 5).
- **0234, sub-root.** `"def text_at"` in `ccp/tasklog.py` runs `git -C <root> show <rev>:./<rel>`, so a
  root below the git toplevel resolves; `"def drop"` in `ccp/lifecycle.py` and `adr.in_force_at` read
  through it. `git grep -ln 'text_at' -- tests` at `8020446`: no test module, so nothing holds the
  sub-root case.
- **Other tasks on these files** change other logic: 0260 and 0269 (`ccp/prompt.py`'s tools and
  verify's parser), 0263, 0264, 0266 (`ccp/verify.py`'s schema, signed blocks, PR fetch). PR #297
  (R22, merged) edited §6.7's Failures bullet, not the paragraph quoted below.
- **Existing drift, not this task's to settle.** §15.4 accepts a ruling naming gate ids "every gate
  closed and approved", with no limit on the gate's class. The rule that an operator gate approves
  running a step, never skipping it, exists only in `"def _waiver_texts"` (0237's fix round). This
  task adds no rule: `--waived` refuses what `verify record` already refuses, through one function.
  Whether §15.4 states the class limit is the operator's question in this triage's record.

### Rulings for the build (the lead's)

- **The in-force refusal.** In `ccp prompt verify` (phase `verify` only), after the marked-check gate,
  `adr.in_force_at(cfg, meta, head)` runs on the `--head` given; any line refuses (exit 1, nothing
  opened, no run, no event), printing the lines (each already names its `ccp adr decide`) and that the
  runner sends the task back to flip them in its PR. Nothing without `adr.strict`, as today.
  `verify record`'s refusal stays as the backstop (E20).
- **One waiver judge.** `ccp/verify.py` gets `waiver_refusal(queue, text) -> str | None`, the reason a
  text does not waive a marked check (None when it does): `_ruling_refusal`, then the operator-gate
  rule. `_waiver_texts` and `prompt.marked_gate` both call it; `marked_gate` stops calling
  `_ruling_refusal` itself.
- **`produced_by: operator`.** `marked_errors` refuses a `ran: false` marked check whose `rests_on` is
  neither a carried verdict it may carry nor in `rulings`, whatever `produced_by` says; a check
  `produced_by: operator` with free text is still refused, by the same condition. The message keeps
  "free-text operator evidence is never its evidence".
- **F08.** `check_facts` moves to `ccp/verify.py` beside `marked_errors`, unchanged; callers and
  tests use `verify.check_facts`. `heads_match` moves to `ccp/runs.py`, unchanged; `ccp/verify.py`
  imports it from there, and `ccp/lifecycle.py`, `ccp/prompt.py` and `ccp/report.py` call
  `runs.heads_match`. `ccp/runs.py` then imports nothing from `ccp.verify`.
- **The sub-root test.** A new `tests/test_text_at_subroot.py` builds a git repo whose product root is
  a subdirectory and checks that `text_at` reads a task file at a commit, that `ccp tasks drop` reads
  the tip's copy, and that `adr.in_force_at` reads the ADR at the head.

## Scope

- **In:** `ccp/prompt.py` (`"def marked_gate"`, the in-force gate where the verify gates run),
  `ccp/verify.py` (`"def waiver_refusal"` (new), `"def _waiver_texts"`, `"def marked_errors"`,
  `check_facts` moved in, `heads_match` moved out), `ccp/runs.py` (`check_facts` out, `heads_match`
  in), `ccp/lifecycle.py`, `ccp/report.py` and `ccp/prompt.py` (the `heads_match` call sites), `tests/test_prompt_verify_early.py`
  (new), `tests/test_text_at_subroot.py` (new), `tests/test_marked_checks_record.py`,
  `tests/test_marked_checks_loop.py`, `docs/cli/02-delivery.md` (the `ccp prompt` row: a verify is
  also refused under `adr.strict` while a decision the task cites is `not_built` at the head, and a
  `--waived` ruling whose only ids are operator gates is refused).
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/01-model.md` §6.7, its last
  paragraph, replaced whole. The `produced_by` change needs no SPEC text: §15.4's "`ran: false` on free-text operator evidence"
  already says what the code will do (`git grep -n 'free-text operator evidence' -- docs/spec` at
  `8020446`: 1 line). The `--waived` change adds no SPEC text either: it makes `ccp prompt verify`
  refuse what `ccp verify record` already refuses, a code rule §15.4 does not state (see Context,
  existing drift).

    CURRENT (`docs/spec/01-model.md` at `8020446`, §6.7, last paragraph):
    > The in-force check also runs before a task's verdict, on its PR head: under `adr.strict`, `ccp verify
    > record` refuses an approve of a head on which a decision the task cites is recorded `not_built`
    > (§15.4), so the task flips it in its own PR rather than at close.

    PROPOSED:
    > The in-force check also runs before a task's verdict, on its PR head: under `adr.strict`, `ccp prompt
    > verify` refuses to open a verify of a head on which a decision the task cites is recorded `not_built`
    > (exit 1, nothing opened), and `ccp verify record` refuses an approve of such a head (§15.4), so the
    > task flips it in its own PR before a verifier starts rather than at close.
- **Out:** the in-force check in `ccp adr check` and `ccp tasks check`; the implementer's pre-gate;
  `verify record`'s other refusals; `ccp verify merge-ok`.

## dod_checks

- id: `code-01`
  story: As a runner, `ccp prompt verify` refuses a head that still records a cited decision `not_built`, before a verifier spends a round on it.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prompt_verify_early`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_prompt_verify_early --mutant-file <file>`, the file's mutant removing the in-force gate's call from `ccp/prompt.py`.
  expect: step 1 exits 0 and lists, each `ok`, a test where a temp product under `adr.strict` whose task cites a decision its head records `not_built` gets exit 1 from `ccp prompt verify`, the output naming `ccp adr decide`, no verify run opened; and one where the same task with the decision `built` opens the verify. Step 2 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-02`
  story: As a runner, `--waived` refuses an operator gate id, as `verify record` would.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prompt_verify_early`.
  expect: exits 0 and lists, `ok`, a test where `ccp prompt verify --waived <check>=<id of a closed, approved operator gate>` exits non-zero naming the operator gate, and `--waived <check>=<a lead ruling id>` opens the verify.
  dry run: n/a — the module is new.
- id: `code-03`
  story: As a verifier, a marked check I record `ran: false` on a genuine waiving ruling is accepted whoever produced the record; free-text operator evidence is still refused.
  setup: A checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_marked_checks_record 2>&1 | tail -3`.
    2. Run `python3 -B -m unittest -v tests.test_prompt_verify_early`.
  expect: step 1 ends `OK`; step 2 lists, `ok`, a test where `verify.marked_errors` on a `ran: false`, `produced_by: operator` check whose `rests_on` names a recorded lead ruling returns no line, and one where the same check with free-text `rests_on` returns one line containing `free-text operator evidence`.
  dry run (`8020446`): step 1 ended `OK`; step 2 n/a — the module is new.
- id: `code-04`
  story: As a plane developer, the run store imports nothing from the judge.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'ccp.verify\|from ccp import.*verify' -- ccp/runs.py`.
    2. Run `git grep -n 'def check_facts' -- ccp`.
  expect: step 1 prints nothing (exit 1); step 2 prints one line, in `ccp/verify.py`.
  dry run (`8020446`): step 1 printed 2 lines (`ccp/runs.py:396`, `ccp/runs.py:439`); step 2 printed `ccp/runs.py:390`.
- id: `test-01`
  story: As a product whose root sits below its git toplevel, task and ADR files read at a commit come from the right path.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_text_at_subroot`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_text_at_subroot --mutant 'ccp/tasklog.py:f"{rev}:./{rel}"=>f"{rev}:{rel}"'`.
  expect: step 1 exits 0 and lists, `ok`, tests for `text_at`, `ccp tasks drop` and `adr.in_force_at` with the product root a subdirectory of the git repo. Step 2 prints the mutant `killed`.
  dry run (`8020446`): step 1 n/a — the module is new; the mutant's old text is in `ccp/tasklog.py` once (`grep -c 'f"{rev}:./{rel}"' ccp/tasklog.py`: 1).
- id: `spec-01`
  story: As the operator, §6.7 says what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0273`.
  expect: exit 0, the PROPOSED passage found in `docs/spec/01-model.md`.
  dry run (simulated at `8020446`: this task file committed, then the passage applied to `docs/spec/01-model.md`, each CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0273 --base HEAD~2`): `"ok": true`, one passage(s) found, none missing.

## Implementation notes

## Verification notes
