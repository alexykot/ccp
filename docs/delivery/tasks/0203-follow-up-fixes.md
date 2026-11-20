---
task_id: 0203-follow-up-fixes
title: Follow-up fixes - a claim clears the wait, beyond needs a reason, constants shown in words, a finite retry
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S16", "S25", "S29"]
review_point: R14
paths: ["ccp/lifecycle.py", "ccp/report.py", "ccp/upgrade.py", "ccp/usage.py", "scripts/observability/lib.py", "tests/test_wait_detail.py", "tests/test_resolution_review.py", "tests/test_short_binding.py", "tests/test_plane_json_constants.py", "tests/test_usage_reader_rules.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0203-follow-up-fixes

## Intent

Four small defects left by the R10 to R12 tasks, each found in a review or a plane proposal and each
in a different module. After this task:
- a claimed task never shows a wait it no longer has;
- a resolution review that says `beyond` has to say why;
- `ccp upgrade status` names a constant in words, as the load warning does;
- an allowance command that prints an infinite `retry_after_s` can no longer write a non-JSON value
  into the samples.

## Context (not checked)

Measured at `58cf1d0`. One finding per bullet, each with its own dod_check.

1. **The claim leaves the wait's details.** `ccp/lifecycle.py` `claim` updates work.json with
   `"waiting_on": None` through `save_work`, which merges, so `waiting_on_detail`,
   `waiting_on_since`, `planned_resume_at` and `quota_class` survive from the wait before the claim
   (`git grep -n '"runtime_status": "running", "waiting_on": None' ccp/lifecycle.py` at `58cf1d0`: one
   line). `WAIT_KEYS` already names all five. From a plane proposal on task 0150's follow-ups. The
   board's head-of-line comment it also named reads correctly now, so it needs no change.
2. **A bare `beyond` is accepted.** `ccp/report.py` `resolution_lines` matches
   `(contained|beyond)\b(.*)$` and accepts `Resolution: beyond` with nothing after it
   (`git grep -n 'contained|beyond' ccp/report.py` at `58cf1d0`: one line), while §13.4 asks for
   `Resolution: beyond <why>`. The proposal also said the resolution gate fetches before it refuses.
   That is fixed already: `prompt.resolution_gate` refuses on the runs first and fetches only when
   the head is not in the object store (`git grep -n 'fetch' ccp/prompt.py` at `58cf1d0`: the fetch
   comes after the three run refusals).
3. **`ccp upgrade status` prints a constant with `repr`.** `ccp/upgrade.py` `key_change` and
   `binding_change` format `{found['constant']!r}` (`git grep -n "constant'\]!r" ccp/upgrade.py` at
   `58cf1d0`: three lines). Probe at `58cf1d0`: a temp product setting `docs.workers` to two gets
   this change from `ccp upgrade status`: "delete `docs.workers`: it is a constant, None, and yours is 2". The binding's
   `runner.rotate_at_context_tokens` constant is `None` too (`lib.binding_constants`). Task 0195
   added `Outcome.shown` for the load warning; `config.constant_override` prints
   `out.shown or repr(out.value)`.
4. **An infinite `retry_after_s` reaches the samples.** `ccp/usage.py` `_run` takes
   `_num_or_none(data.get("retry_after_s"))` and keeps it when not negative. `json.loads` reads `Infinity`
   as `float('inf')`, which passes, and `_record` writes it with `json.dumps`, which emits the
   non-JSON token `Infinity` (`git grep -n 'retry >= 0' ccp/usage.py` at `58cf1d0`: one line).
   Found in task 0197's review.

No finding changes SPEC text: §13.4 already asks for `beyond <why>`, and no SPEC sentence describes
the rest (`grep -n 'waiting_on_detail\|retry_after_s' docs/spec/*.md` at `58cf1d0`: no line names a
claim or a finite check).

A plane proposal also found that health's integration merges can count merges already on the
integration branch once the task branch is rebased onto a newer tip (`report.round_merges` lists
`<base>..<tip>`). The fix redefines the recorded `integration_merges` of §11.1, so it waits for a
signed task and is not here. The proposal's `--since` point is fixed already: `health` passes its
window to `conflict_catch_ups` (`git grep -n 'conflict_catch_ups(q, window)' ccp/health.py` at
`58cf1d0`: one line).

## Scope

- **In:** `ccp/lifecycle.py`, `ccp/report.py`, `ccp/upgrade.py`, `ccp/usage.py`,
  `scripts/observability/lib.py`, `tests/test_wait_detail.py`,
  `tests/test_resolution_review.py`, `tests/test_short_binding.py`,
  `tests/test_plane_json_constants.py`, `tests/test_usage_reader_rules.py`.
- **Claim:** the work.json update sets every key of `WAIT_KEYS` to `None`, not only `waiting_on`.
  The task's own state already starts with `waiting_on: None`; a resumed claim clears the same
  keys in work.json. A test in `tests/test_wait_detail.py`: a wait set with `--detail`, then a
  claim, leaves no `waiting_on_detail`, `waiting_on_since`, `planned_resume_at` or `quota_class`
  in work.json.
- **Beyond:** `Resolution: beyond` must be followed by at least one word character after
  punctuation and markup are stripped. Otherwise the error is "`Resolution: beyond` needs its
  reason: `Resolution: beyond <why>`". Tests in `tests/test_resolution_review.py`: a bare `beyond`,
  `beyond.` and `beyond —` are refused; `beyond the merge rewrote a helper` is accepted.
- **Constants in words:** `key_change` and `binding_change` print `outcome.shown or
  repr(outcome.value)`: `config.KEY_OUTCOMES[key]` for plane.json, `lib.binding_constants()[key]`
  for the binding. `binding_constants` gives `runner.rotate_at_context_tokens` `shown="off"`. Tests:
  `tests/test_plane_json_constants.py` (`docs.workers: 2` gives "it is a constant, as many as there
  are checks, and yours is 2") and `tests/test_short_binding.py` (a binding setting
  `rotate_at_context_tokens: 100000` gives "it is a constant, off, and yours is 100000").
- **Finite retry:** `_run` keeps `retry_after_s` only when `math.isfinite(retry) and retry >= 0`. A
  test in `tests/test_usage_reader_rules.py`: a command printing `{"retry_after_s": Infinity}` and
  exiting 1 records a failed row with no `retry_after_s`, and the samples file parses with a strict
  reader (`json.loads(line, parse_constant=…)` that raises on `Infinity` and `NaN`).
- **Out:** the board comment (already correct), the resolution gate's fetch order and health's
  `--since` (both already fixed), and health's integration merges (a §11.1 change, for a signed task).

## dod_checks

- id: `fx-01`
  story: As a lead reading the board, a claimed task shows no wait it no longer has.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_wait_detail 2>&1 | tail -12`.
  expect: exit 0, with the **Claim** test of the Scope listed `ok`.
  dry run (`58cf1d0`): 4 tests, OK; the new test does not exist yet.

- id: `fx-02`
  story: As a runner, a resolution review that says `beyond` says why.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_resolution_review 2>&1 | grep -i beyond`.
  expect: the **Beyond** tests of the Scope are listed `ok`: the bare forms refused, the reasoned one accepted.
  dry run (`58cf1d0`): the module runs 25 tests, OK.

- id: `fx-04`
  story: As a lead, `ccp upgrade status` names a constant in words.
  setup: a checkout of the PR head; a temp git repo whose `docs/delivery/plane.json` is
    `{"project_id": "demo", "language": "none", "docs": {"workers": 2}, "suite": {"lanes": {"gate":
    ["true"]}}, "architect": false}`; `CCP_BINDINGS_DIR` set to an empty temp dir.
  steps:
    1. Run `ccp --root <temp> upgrade status | grep 'docs.workers'`.
  expect: the change reads "delete `docs.workers`: it is a constant, as many as there are checks, and
    yours is 2; or file a plane proposal to keep the key", and no line says "constant, None".
  dry run (`58cf1d0`): "delete `docs.workers`: it is a constant, None, and yours is 2; or file a plane
    proposal to keep the key".

- id: `fx-05`
  story: As the plane, an infinite retry never reaches the samples.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_usage_reader_rules tests.test_short_binding tests.test_plane_json_constants 2>&1 | tail -30`.
  expect: exit 0, with the finite-retry test and the two constant-wording tests (the Scope's **Finite retry** and **Constants in words**)
    listed `ok`.
  dry run (`58cf1d0`): 15, 22 and 30 tests, OK.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
