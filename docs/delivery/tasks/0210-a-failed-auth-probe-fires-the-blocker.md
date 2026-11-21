---
task_id: 0210-a-failed-auth-probe-fires-the-blocker
title: A claim refused by a failed auth probe fires the blocker notice
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S10", "S30"]
review_point: R15
paths: ["ccp/lifecycle.py", "ccp/notify.py", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/05-operations.md", "plugin/agents/delivery-runner.md", "tests/test_notify.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0210-a-failed-auth-probe-fires-the-blocker

## Intent

When a credential expires, `ccp tasks claim` refuses with exit 8 and takes no task, and the runner
raises a `reauth` gate to the lead. The operator is the only one who can fix it, yet nothing tells
the operator: a gate fires no notice, and the `blocker` notice fires only when someone sets a
`reauth` wait on a task, which a refused claim never holds. After this task, the claim that a failed
probe refuses fires the `blocker` notice itself, so the operator hears of an expired login the first
time it stops the work.

## Context (not checked)

Measured at `1b734dd`.

- Provenance: an accepted plane proposal (triage item T3).
- **The refusal raises with no notice.** `ccp/lifecycle.py` `claim`: on a failed probe it raises
  `QueueError(f"auth probe(s) failed: {failed}. Set waiting_on reauth and raise it to the lead ...",
  EXIT_AUTH)` (`git grep -n 'EXIT_AUTH)' -- ccp/lifecycle.py` at `1b734dd`: one line), with no
  `notify.fire` before it. The step that does fire on a refused claim is the weekly checkpoint, just
  below: `notify.fire(cfg, q, "allowance_checkpoint", task_id=tid, reason=exc.reason)`, whose
  warning is appended to the refusal (`git grep -n 'notify.fire(' -- ccp` at `1b734dd`: three
  calls, the checkpoint, `wait` and the review-point close).
- **What fires `blocker` today.** `lifecycle.wait` fires it when a wait is set with a reason in
  `notify.BLOCKER_WAITS` (`reauth`, `operator_step`). `team.sh gate open` sets no wait and fires
  nothing (`grep -n 'notify' scripts/observability/team.py` at `1b734dd`: one call, the
  `ask-operator` decision). The runner's definition, its **Auth** step, tells it to raise a gate of
  class `reauth` (`grep -n 'class .reauth.' plugin/agents/delivery-runner.md` at `1b734dd`: one
  line). So the operator hears nothing unless the lead sends a notice by hand.
- **No task is held.** The claim refuses before the lease, so there is no task wait to set. The
  notice names the task the runner tried to claim, as the checkpoint's does.
- **Repeats.** §3.6 already says a refused claim sends again on each call. A runner retrying a claim
  while the login is still expired fires once per retry; the runner's definition says to wait for
  the lead's word, not to retry in a loop.
- `tests/test_notify.py` holds the checkpoint's notice tests
  (`grep -n 'def test_a_claim' tests/test_notify.py` at `1b734dd`: three tests) and its `ChannelFixture`
  records each notice the product's command receives.
- No R14 task edits `ccp/lifecycle.py` `claim` or the passages below: 0203 edits `claim`'s work.json
  update (`"waiting_on": None`), a different statement.

## Scope

- **In:** `ccp/lifecycle.py`, `ccp/notify.py` (module docstring only), `docs/spec/01-model.md`,
  `docs/spec/02-delivery.md`, `docs/spec/05-operations.md`, `plugin/agents/delivery-runner.md`,
  `tests/test_notify.py`.
- **The claim.** On a failed probe, `claim` calls `notify.fire(cfg, q, "blocker", task_id=tid,
  reason="reauth")` before it raises exit 8. A `notify:` warning the fire returns is appended to the
  refusal's message, as the checkpoint's is. The exit-8 message no longer says to set `waiting_on
  reauth` (no task is held): it says the operator was notified and to raise a `reauth` gate to the
  lead (SPEC §30), for example `auth probe(s) failed: <ids>. The operator was notified (blocker);
  raise a reauth gate to the lead (SPEC §30); ccp auth check shows each`. Exit 8 and
  `auth/status.json` are otherwise unchanged. A resumed claim runs no probe and fires nothing, as
  today.
- **The runner's definition**, step 4 **Auth**: the claim has already fired the operator's `blocker`
  notice; the runner still raises the `reauth` gate to the lead, passes on any `notify:` warning,
  sets no `reauth` wait (it holds no task) and waits for the lead's word before claiming again.
- `ccp/notify.py`'s module docstring names the refused claim among the `blocker` triggers.
- **Tests** in `tests/test_notify.py`, on `ChannelFixture`:
  - a claim refused by a failing probe exits 8 and the product's command receives one `blocker` line
    naming the task, with reason `reauth`; the refusal's message says the operator was notified and
    names the `reauth` gate, and does not say `waiting_on`;
  - with probes that pass, the claim fires no notice;
  - a failing notify command adds its `notify:` warning to the exit-8 refusal.

### SPEC changes (signed in the brief, §31)

**a. §3.6, the trigger table's `blocker` row.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> | `blocker` | `ccp tasks wait <id> reauth` or `operator_step`: a wait only the operator clears | the task; the wait's reason |

PROPOSED:
> | `blocker` | `ccp tasks wait <id> reauth` or `operator_step`: a wait only the operator clears; `ccp tasks claim` refused by a failed auth probe (exit 8, §30.1) | the task; the wait's reason, `reauth` for the refused claim |

**b. §10.5, the claim's probes.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> **`ccp tasks claim <id> [--holder <slot>]`** runs the product's auth probes first
> (`auth_check.probes`, §30) and exits 8 when one fails: no task is taken, and the runner raises a `reauth` gate to the lead (probes: `[{id, cmd}]`, each given 60 seconds).

PROPOSED:
> **`ccp tasks claim <id> [--holder <slot>]`** runs the product's auth probes first
> (`auth_check.probes`, §30) and exits 8 when one fails: no task is taken, the claim fires the `blocker` notice (§3.6), and the runner raises a `reauth` gate to the lead (probes: `[{id, cmd}]`, each given 60 seconds).

**c. §30.1, the second bullet.**

CURRENT (`docs/spec/05-operations.md` at `8aefa59`):
> - `ccp tasks claim` runs the probes before each new task and refuses with exit 8 when one fails: no
>   task is taken, and the runner raises it to the lead as a `reauth` gate. `ccp auth check` runs them on
>   demand.

PROPOSED:
> - `ccp tasks claim` runs the probes before each new task and refuses with exit 8 when one fails: no
>   task is taken, the claim fires the operator's `blocker` notice with the reason `reauth` (§3.6), and
>   the runner raises it to the lead as a `reauth` gate. `ccp auth check` runs them on demand.

- **Out:** the probes themselves, `ccp auth check`, the gate classes, and any limit on how often a
  repeated refusal notifies.

## dod_checks

- id: `au-01`
  story: As the operator, I hear of an expired login the first time it stops a claim.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_notify 2>&1 | tail -40`.
  expect: exit 0, with the three Scope tests listed `ok`, among them a test whose name holds
    `auth` and asserts one `blocker` line with reason `reauth` and the refusal's new wording.
  dry run (`1b734dd`): `python3 -B -m unittest -q tests.test_notify` runs 30 tests, OK; no auth test exists yet.

- id: `au-02`
  story: As a plane developer, the notice test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    new `notify.fire(..., "blocker", ...)` call in `claim` is deleted.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_notify`.
  expect: at least one failure, naming the auth-probe notice test.
  dry run: n/a — the test is new.

- id: `au-03`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0210 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found (nothing changed yet).

- id: `au-04`
  story: As a runner, my definition says the notice has already gone.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -A6 '\*\*Auth' plugin/agents/delivery-runner.md | grep -c blocker`.
  expect: prints 1 or more (the Auth step names the `blocker` notice).
  dry run (`8aefa59`): prints 0.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `ccp/lifecycle.py` `claim`: on a failed probe it calls `notify.fire(cfg, q, "blocker", task_id=tid,
  reason="reauth")` and then raises exit 8. The message now reads `auth probe(s) failed: <ids>. The
  operator was notified (blocker); raise a reauth gate to the lead (SPEC §30); ccp auth check shows
  each`, with the fire's first `notify:` warning appended after a `. ` as the checkpoint does. The probes,
  `auth/status.json`, exit 8 and the resumed claim (no probe, no notice) are unchanged.
- `ccp/notify.py`: the module docstring names the refused claim among the `blocker` triggers.
- `plugin/agents/delivery-runner.md` step 4 **Auth**: the notice has already gone; raise the `reauth`
  gate, pass on a `notify:` warning, set no wait, wait for the lead's word before claiming again.
- SPEC §3.6, §10.5 and §30.1 carry the signed text (a, b, c).
- Three tests in `tests/test_notify.py` (`Channel`, on `ChannelFixture`): the refused claim's one
  `blocker` line with reason `reauth` and the new wording, no notice when the probes pass, and a
  failing notify command's warning on the refusal.

## Verification notes
