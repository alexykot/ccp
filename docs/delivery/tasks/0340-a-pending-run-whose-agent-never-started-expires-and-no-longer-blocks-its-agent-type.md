---
task_id: 0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type
title: A pending run whose agent never started expires after 10 minutes, so it no longer blocks every runner's launches of its agent type; the next prompt and runs gc abandon it, and the slot that opened it is told
status: done
kind: feature
depends_on: []
spec_refs: ["S11", "S16"]
review_point: R36
paths: ["ccp/runs.py", "ccp/prompt.py", "tests/test_run_abandon.py", "docs/spec/02-delivery.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0339-a-suite-run-s-liveness-is-judged-by-its-process-and-a-killed-run-s-processes-are-ended", "0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type

## Intent

A worker launch that never happened no longer stalls a product's runners. A run `ccp prompt` opened whose agent has
not started within 10 minutes has expired: the next `ccp prompt` of its agent type, by any runner, abandons it and
goes on instead of refusing, the harness's start hook never binds it, and `ccp runs gc` abandons it too. The runner
slot that opened it is told, once, on its next `ccp prompt`.

## Context (not checked)

An accepted plane proposal, generic as stated here. With several runners, one runner's `ccp prompt` opened a run
whose agent never started (the launch failed or was never made). Every runner's next launch of that agent type was
then refused as "still pending"; the runner brief forbids superseding another runner's run, and `ccp runs gc` left it,
since its task was neither done nor re-opened. The lead accepted the design on 2026-11-24: such a run expires after a
bound, `ccp runs gc` abandons it, and its runner is told on its next call.

Measured at `554fe3a`:

- `"def check_pending"` in `ccp/runs.py` refuses (exit 3) while any run of the agent type is `pending`, unless
  `--supersede`; even then, another slot's pending run opened in the last `SUPERSEDE_GRACE_S` (120 s) is refused.
  Age plays no other part.
- `"def gc_plan"` abandons an open run only when a later round of its task and phase exists or its task is done or
  dropped.
- `"def bind"` binds the oldest pending run of the agent type, whatever its age.
- In a scratch product, a second `ccp prompt implement` while the first round is pending (its `opened_at` set to
  2026-01-01) exits 3 and the old run keeps no `abandoned_reason`; `ccp runs gc --dry-run` lists nothing (the dry
  runs of cmd-01 and cmd-02).

**Ruled.**

- **The bound.** `PENDING_EXPIRY_S = 600` in `ccp/runs.py`, a constant: a launch binds within seconds, and 10
  minutes is five times the 120 s supersede grace. A run is expired when its state is `pending` and its `opened_at`
  is more than `PENDING_EXPIRY_S` ago; an `opened_at` that does not parse never expires. The bound is not tied to its
  task's head (the proposal's "or once its task's head moves" is not built: the age alone ends every such stall).
- **The next prompt.** `check_pending` first abandons every expired pending run of the agent type, with the reason
  `expired: its agent never started within 10 minutes`, then judges the rest as today; so an expired run neither
  refuses nor needs `--supersede`, and the 120 s grace still holds for a fresh one.
- **Binding.** `bind` skips an expired pending run and abandons it with the same reason; a start with no other
  pending run lands in `runs/_unbound.jsonl` as today.
- **gc.** `gc_plan` gives an expired pending run the same reason, after the two existing rules.
- **Telling the opener.** An expired run's record gains `expired_told_at` once its opener has been told. `ccp prompt`,
  for any phase, warns once for each expired run opened by its caller's slot (`opened_by`) with no `expired_told_at`,
  `ccp prompt: <run_id>, which you opened at <opened_at>, expired: its agent never started within 10 minutes; it is
  abandoned (SPEC §11.1)`, and sets `expired_told_at`. When the caller is the opener and its own prompt abandoned
  the run, that prompt is the one that tells it.
- **Tests.** `tests/test_run_abandon.py` gains class `PendingExpiry(unittest.TestCase)`:
  `test_a_pending_run_past_the_bound_no_longer_blocks_its_agent_type`, `test_a_fresh_pending_run_still_refuses`,
  `test_gc_abandons_an_expired_pending_run`, `test_agent_start_binds_no_expired_run` and
  `test_the_opener_is_told_once_on_its_next_prompt`. No other test expectation changes.

## Scope

- **In:** `ccp/runs.py` (the constant, `check_pending`, `bind`, `gc_plan`, the told marker), `ccp/prompt.py` (the
  warning), `tests/test_run_abandon.py` (class `PendingExpiry`); the SPEC, describing this task's own feature
  (§31.1, the accepted proposal): one sentence added to §11.1 *Binding* and one clause added to §11.1 *Abandoning*.
  No other § sentence changes.

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §11.1 *Binding*, the sentence the new one follows, unchanged (the new sentence goes right after it and retires none):
  > `ccp prompt` refuses a second pending run of an agent type that already has one unbound (exit 3;
  >   with several runners, wait a few seconds and ask again); `--supersede` lifts that, but never
  >   abandons another slot's pending run opened in the last 120 s.

  PROPOSED:
  > A pending run whose agent has not started within 10 minutes of its opening has expired: the next `ccp prompt` of its agent type, by any slot, abandons it (`expired: its agent never started within 10 minutes`) instead of refusing, `ccp agent start` binds no expired run, and the slot that opened it is told once, on its next `ccp prompt`.

  CURRENT (`docs/spec/02-delivery.md` at `3539c23`), §11.1 *Abandoning*, the sentence:
  > `ccp runs gc [--dry-run]` applies the same rules to older records; a second run changes nothing.

  PROPOSED:
  > `ccp runs gc [--dry-run]` applies the same rules to older records, an expired pending run (*Binding*) included; a second run changes nothing.
- **Out:** expiry on a moved task head; a setting for the bound; expiring a `running` or `stopped` run; any change
  to `--supersede` or the 120 s grace; telling the opener on commands other than `ccp prompt`.

## dod_checks

- id: `cmd-01`
  story: As a runner, a pending run whose agent never started no longer blocks my next launch of that agent type, and I am told.
  setup: A checkout of the PR head (any seat); the step builds its scratch product with one task, a local origin and a claim, opens a round, and sets its opening back to 2026-01-01.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["language"] = "none"; c["suite"] = {"lanes": {"gate": ["true"]}}; json.dump(c, open(p, "w"))' "$P" && printf -- '---\ntask_id: 0001-first\ntitle: Do the first thing\nstatus: pending\ndepends_on: []\nspec_refs: ["S1"]\nparallel: true\ncreated: 2026-11-25\nupdated: 2026-11-25\n---\n\n## Intent\n\nA.\n\n## Context (not checked)\n\nB.\n\n## Scope\n\n- **In:** c.\n- **Out:** d.\n\n## dod_checks\n\n- id: \140cmd-01\140\n  story: As a user, I see it.\n  setup: none.\n  steps:\n    1. Look.\n  expect: it is there.\n\n## Implementation notes\n\n## Verification notes\n' > "$P/docs/delivery/tasks/0001-first.md" && export QUEUE_ROOT="$D/queue" CCP_DEV=1 && unset PROJECT_YAML && ./bin/ccp --root "$P" tasks index >/dev/null 2>&1; git -C "$P" add -A && git -C "$P" -c user.name=t -c user.email=t@example.invalid commit -qm task && git init -q --bare "$D/origin.git" && git -C "$P" remote add origin "$D/origin.git" && git -C "$P" push -q origin HEAD:main && ./bin/ccp --root "$P" tasks claim 0001 >/dev/null 2>&1 && ./bin/ccp --root "$P" prompt implement 0001 >/dev/null 2>&1 && python3 -c 'import json, sys; p = sys.argv[1] + "/queue/runs/0001-first/implement.json"; r = json.load(open(p)); r["opened_at"] = "2026-01-01T00:00:00Z"; json.dump(r, open(p, "w"))' "$D" && ./bin/ccp --root "$P" prompt implement 0001 >/dev/null 2>"$D/err"; echo "exit $?"; python3 -c 'import json, sys; print(json.load(open(sys.argv[1] + "/queue/runs/0001-first/implement.json")).get("abandoned_reason"))' "$D"; grep -c '0001-first/implement, which you opened at .* expired' "$D/err"`.
  expect: exactly three lines: `exit 0`, `expired: its agent never started within 10 minutes`, `1`.
  dry run (`3539c23`): printed `exit 3`, `None`, `0`.
- id: `cmd-02`
  story: As the lead, ccp runs gc abandons a pending run whose agent never started.
  setup: A checkout of the PR head (any seat); the step builds the same scratch product and expired pending round as cmd-01.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["language"] = "none"; c["suite"] = {"lanes": {"gate": ["true"]}}; json.dump(c, open(p, "w"))' "$P" && printf -- '---\ntask_id: 0001-first\ntitle: Do the first thing\nstatus: pending\ndepends_on: []\nspec_refs: ["S1"]\nparallel: true\ncreated: 2026-11-25\nupdated: 2026-11-25\n---\n\n## Intent\n\nA.\n\n## Context (not checked)\n\nB.\n\n## Scope\n\n- **In:** c.\n- **Out:** d.\n\n## dod_checks\n\n- id: \140cmd-01\140\n  story: As a user, I see it.\n  setup: none.\n  steps:\n    1. Look.\n  expect: it is there.\n\n## Implementation notes\n\n## Verification notes\n' > "$P/docs/delivery/tasks/0001-first.md" && export QUEUE_ROOT="$D/queue" CCP_DEV=1 && unset PROJECT_YAML && ./bin/ccp --root "$P" tasks index >/dev/null 2>&1; git -C "$P" add -A && git -C "$P" -c user.name=t -c user.email=t@example.invalid commit -qm task && git init -q --bare "$D/origin.git" && git -C "$P" remote add origin "$D/origin.git" && git -C "$P" push -q origin HEAD:main && ./bin/ccp --root "$P" tasks claim 0001 >/dev/null 2>&1 && ./bin/ccp --root "$P" prompt implement 0001 >/dev/null 2>&1 && python3 -c 'import json, sys; p = sys.argv[1] + "/queue/runs/0001-first/implement.json"; r = json.load(open(p)); r["opened_at"] = "2026-01-01T00:00:00Z"; json.dump(r, open(p, "w"))' "$D" && ./bin/ccp --root "$P" runs gc --dry-run 2>/dev/null | python3 -c 'import json, sys; print([(r["run_id"], r["reason"]) for r in json.load(sys.stdin)["abandoned"]])'`.
  expect: prints `[('0001-first/implement', 'expired: its agent never started within 10 minutes')]`.
  dry run (`3539c23`): printed `[]`.
- id: `code-01`
  story: As a plane developer, the tests hold the expiry, the unchanged refusal of a fresh pending run, binding, gc and telling the opener.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_run_abandon.PendingExpiry.test_a_pending_run_past_the_bound_no_longer_blocks_its_agent_type tests.test_run_abandon.PendingExpiry.test_a_fresh_pending_run_still_refuses tests.test_run_abandon.PendingExpiry.test_gc_abandons_an_expired_pending_run tests.test_run_abandon.PendingExpiry.test_agent_start_binds_no_expired_run tests.test_run_abandon.PendingExpiry.test_the_opener_is_told_once_on_its_next_prompt`.
  expect: exit 0.
  dry run (`3539c23`): exit 1, the run FAILED (`PendingExpiry` does not exist yet).
- id: `spec-01`
  story: As the operator, §11.1 describes the expiry of a pending run.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0340`.
  expect: exit 0, both PROPOSED passages found.
  dry run (`3539c23`, with this brief): exit 1, both passages `not found in the SPEC`.

## Implementation notes

- `ccp/runs.py`: `PENDING_EXPIRY_S = 600` and `EXPIRED_REASON` (its minutes derived from the constant); `expired(rec,
  now)` is the plain-value judgement (pending, `opened_at` parses, older than the bound), with `opened_ts` shared with
  the supersede grace's age. One helper, `unexpired_pending`, abandons each expired pending run of an agent type and
  returns the rest; `check_pending` (now taking `cfg`, to abandon) and `bind` both call it. `gc_plan` gives an
  expired pending run `EXPIRED_REASON` after its two existing rules. `expired_untold(q, by)` and `mark_told` read and
  set `expired_told_at`.
- `ccp/prompt.py`: `tell_expired` prints the warning on stderr, once per run, and sets the marker. `build` calls it in
  a `finally` around `check_pending`, so a prompt that abandons its own slot's expired run tells it even when it then
  refuses on a fresh pending run.
- Narrowest reading: an opener is told of a run abandoned as expired (by a prompt of its agent type, `ccp agent
  start` or `ccp runs gc`). An expired run still pending, of an agent type nobody has prompted since, is not abandoned
  by a prompt of another type, so it is told once something abandons it.
- Tests: `PendingExpiry` (plain values on a temp queue, the five named tests) and one end-to-end wiring test in
  `Abandon`, `test_an_expired_round_is_abandoned_by_the_next_prompt_and_its_opener_told` (the build wiring, the
  refused prompt that still tells, and told once).

## Verification notes
- 2026-11-25 — verifier, PR #416 head `d57cc34` (squash `1abbb84`): APPROVE. Passed: cmd-01, cmd-02, code-01, spec-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0340-a-pending-run-whose-agent-never-started-expires-and-no-longer-blocks-its-agent-type.json.

