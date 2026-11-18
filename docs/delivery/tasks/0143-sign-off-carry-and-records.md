---
task_id: 0143-sign-off-carry-and-records
title: Close's catch-up carries a build sign-off when nothing it covers changed, and a lead's ruling gets an id a verdict can cite
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S10", "S15", "S16", "S17", "S23"]
review_point: R9
sign_off: brief
paths: ["ccp/lifecycle.py", "ccp/verify.py", "ccp/cli.py", "contracts/verification.schema.json", "contracts/observability_event.schema.json", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/cli/02-delivery.md", "templates/prompts/verify.md", "plugin/agents/delivery-verifier.md", "plugin/agents/delivery-runner.md", "tests/test_behind_tip_catch_up.py", "tests/test_verify_as_written.py", "tests/test_lead_ruling.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0143-sign-off-carry-and-records
## Intent

With several runners, an unrelated merge to the integration branch before close no longer costs a
task with a build sign-off a merge round, a re-verify and a fresh operator signature on unchanged
text: close's own catch-up carries the sign-off to the caught-up head when nothing it covers changed,
and says so in the record. And a ruling the lead gives a runner by message gets an id, so a verifier
can record a check `as_written: false` against it instead of folding the hold into its evidence.

## Context (not checked)

- §16.5's catch-up rule lets close catch a verified head up to a moved tip itself only when "no build
  sign-off is due on the task (§3.5)"; `_catch_up` (`"def _catch_up"` in `ccp/lifecycle.py`) refuses with "build
  sign-off: … covers the verified head only". §3.5 says a build sign-off "covers the head that merges",
  and close refuses one recorded for another head (`sign_off_gaps`, "build sign-off is stale").
- Seen on task 0124: the tip moved by an unrelated task's merge, so the task took a merge round, a
  re-verify and a new operator sign-off of text that had not changed.
- Close checks sign-offs against the verified head before it tries a catch-up (`sign_off_gaps(...)` then
  `_catch_up(...)` in `close`), so a carried sign-off is always one recorded for the verified head.
- The catch-up already requires that the tip's new commits change no file the task's own diff or
  declared paths change, a `parallel.shared` path aside. Signed text sits in files the task's own diff
  changes; a union merge in a shared path could still change such a file, hence the stricter condition below.
- A ruling the lead gives a runner as a message has no id. §15.4 accepts, as the `ruling` of an
  `as_written: false` check (task 0107), only spec question ids (`sm-…`) or gate ids (`<task_id>-<n>`),
  checked by `_ruling_refusal` in `ccp/verify.py`. In task 0128 the verifier recorded a pass with the hold
  in its evidence instead.
- The verification record's `catch_up` object is closed (`additionalProperties: false` in
  `contracts/verification.schema.json`), so a new field bumps the record's version (§15.4).
- These change § rules (§3.5, §10.5, §15.4, §16.5, §17.5), carried below for signing. The §23.2 event row
  and the CLI row only describe this task's own feature (§31.1).

## Scope

- **In:**
  - `ccp/lifecycle.py` `_catch_up`: a due build sign-off (declared, or from the verdict's
    `spec_beyond_intent`) no longer refuses the catch-up by itself. With one due, the catch-up also
    refuses (naming `build sign-off`) when the tip's new commits change any file the task's own diff
    changes, a `parallel.shared` path included. When it catches up with one due, the record's `catch_up`
    gets `sign_off_carried`, the head the build sign-off covers (the verified head), and the `verify`
    `set` event's payload carries it too.
  - `ccp/lifecycle.py` `sign_off_gaps`: a build sign-off recorded for the verified head holds for the head
    to merge when the verification record's `catch_up.to` is that head and `catch_up.sign_off_carried` is
    the signed head; a re-run of close after the merge judges the same way.
  - `contracts/verification.schema.json`: `catch_up.sign_off_carried` (optional, a sha); the record's
    version (`RECORD_VERSION` in `ccp/verify.py`) goes up by one.
  - `ccp tasks ruling <task_id> --words "…" [--check <dod_check_id>]` (new, `ccp/cli.py` and
    `ccp/lifecycle.py`): the lead records a ruling as a `ruling` `recorded` ledger event (actor the design
    seat; payload `id`, `n`, `check`, `words`), id `<task_id>-r<n>`, `n` counting from 1 per task. It prints
    the id. An unknown task exits 2; empty words exit 2.
  - `ccp/verify.py` `_ruling_refusal`: a `<task_id>-r<n>` token names a ruling that exists when the ledger
    holds its `ruling` `recorded` event; an unknown one is refused, as an unknown gate is.
  - `contracts/observability_event.schema.json`: event type `ruling`. §31.1: `docs/spec/04-observability.md`
    §23.2's event table gets a row, `ruling` | `recorded` | `id`, `n`, `check?`, `words` (§17.5).
  - §31.1: `docs/cli/02-delivery.md` lists `ccp tasks ruling`.
  - `templates/prompts/verify.md` and `plugin/agents/delivery-verifier.md`: a ruling may be named by a lead
    ruling id; `plugin/agents/delivery-runner.md`: a ruling the lead gives by message is recorded by the lead
    with `ccp tasks ruling`, and the runner passes its id on with the ruling.
  - `tests/test_behind_tip_catch_up.py`: the test that expects a due build sign-off to refuse the
    catch-up changes; `tests/test_lead_ruling.py` (new) holds the ruling tests.
  - `docs/spec/01-model.md` §3.5. CURRENT (at `921507e`): "It is signed after verify, and the sign-off covers the head that merges." PROPOSED:
    > It is signed after verify, and the sign-off covers the head that merges, or the verified head when close's own catch-up carried it to the head that merges (§16.5 rule 4).
  - `docs/spec/01-model.md` §3.5. CURRENT (at `921507e`): "or whose `build` sign-off covers another head than the one it merges (stale: the operator signs the new head) (§10.5)." PROPOSED:
    > or whose `build` sign-off covers another head than the one it merges and close's own catch-up did not carry it there (stale: the operator signs the new head) (§10.5).
  - `docs/spec/02-delivery.md` §10.5 step 1. CURRENT (at `921507e`): "or whose `build` sign-off covers another head than the one it merges, or whose" PROPOSED:
    > or whose `build` sign-off covers another head than the one it merges and close's own catch-up did not carry it there (§16.5 rule 4), or whose
  - `docs/spec/02-delivery.md` §16.5 rule 4. CURRENT (at `921507e`): "and no build sign-off is due on the task (§3.5), close merges the tip into the verified head itself," PROPOSED:
    > and any build sign-off due on the task (§3.5) is recorded for the verified head, with the tip's new commits changing no file the task's own diff changes, a `parallel.shared` path included, close merges the tip into the verified head itself,
  - `docs/spec/02-delivery.md` §16.5 rule 4. CURRENT (at `921507e`): "recording the catch-up in the verification record." PROPOSED:
    > recording the catch-up in the verification record, with `sign_off_carried`, the head the build sign-off covers, when it carried one.
  - `docs/spec/02-delivery.md` §15.4. CURRENT (at `921507e`): "ruling, naming spec question ids or gate ids that all exist" PROPOSED:
    > ruling, naming spec question ids, gate ids or lead ruling ids (`<task_id>-r<n>`, §17.5) that all exist
  - `docs/spec/02-delivery.md` §15.4. CURRENT (at `921507e`): "and `ruling`, the spec question or gate ids that let it, in the ruling form above." PROPOSED:
    > and `ruling`, the spec question, gate or lead ruling ids that let it, in the ruling form above.
  - `docs/spec/02-delivery.md` §17.5, a new paragraph at its end. CURRENT: none. PROPOSED:
    > A ruling the lead gives a runner by message, outside a spec question, is recorded with `ccp tasks ruling <task_id> --words "…" [--check <dod_check_id>]`: a `ruling` `recorded` event in the ledger (§23.2) with the check and the words, its id `<task_id>-r<n>`, `n` counting from 1 per task. A verdict may cite that id wherever it cites a ruling (§15.4); the runner passes it on with the ruling.
  - Each PROPOSED passage goes in on lines of its own, unwrapped, the line holding its first word part
    of the diff, so `ccp verify spec-text` finds it.
- **Out:**
  - Carrying a brief sign-off, or a build sign-off across a merge round the implementer makes.
  - A ruling recorded by any seat but the lead.

## dod_checks

- id: `carry-01`
  story: As a runner, an unrelated merge does not cost a signed task a new sign-off.
  setup: `tests/test_behind_tip_catch_up.py`'s fixture with several runners; a task that declares `sign_off: build`, verified at head H with its build sign-off recorded for H; then a commit on the integration tip changing only a file the task's diff and declared paths do not touch.
  steps:
    1. Run `ccp tasks close <task> --pr <n>`.
  expect: exit 0; the merge is the catch-up head; the verification record's `catch_up.sign_off_carried` is H; no new sign-off was recorded.
  dry run: n/a.
- id: `carry-02`
  story: As the operator, a sign-off is not carried over a change to a file it covers.
  setup: the fixture of carry-01, but the tip's new commit appends lines to a `parallel.shared` path that the task's own diff also changes.
  steps:
    1. Run `ccp tasks close <task> --pr <n>`.
  expect: exit 1, nothing merged; the refusal names `behind_tip` and `build sign-off`.
  dry run: n/a.
- id: `carry-03`
  story: As a runner, a re-run of close after the carried merge holds.
  setup: the state after carry-01 with close stopped after the merge and before the reconcile (the fixture's reconcile push made to fail once).
  steps:
    1. Run `ccp tasks close <task> --pr <n>` again.
  expect: exit 0; no `build sign-off is stale` line; the task is done.
  dry run: n/a.
- id: `rule-01`
  story: As a verifier, I cite the lead's ruling by its id.
  setup: a scratch queue with a task's open verify run.
  steps:
    1. Run `ccp tasks ruling <task> --words "hold the count at the merge base" --check cmd-01`.
    2. Run `ccp verify record` on a verdict whose check `cmd-01` is `as_written: false` with `held_instead` and `ruling` the printed id; then on one citing `<task>-r9`.
  expect: step 1 prints `<task>-r1` and the ledger holds a `ruling` `recorded` event; the first record is accepted, the second refused naming `<task>-r9` as no ruling the queue holds.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Run `ccp verify spec-text 0143-sign-off-carry-and-records`, and compare each edit with the PROPOSED text above.
  expect: exit 0, each matches word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- `ccp/lifecycle.py` `_catch_up`: `signed_due` is `"build" in due_stages(q, meta)[0]` (declared, or from the verdict's
  `spec_beyond_intent`); the two early refusals are gone. With one due, the overlap check gains a second test
  after the existing one: any tip file in the task's own diff (a `parallel.shared` path included) raises
  `_NoCatchUp("build sign-off: ...")`, so close refuses `behind_tip` naming `build sign-off`. The catch-up and the
  `verify` `set` event carry `sign_off_carried` = the verified head.
- `sign_off_gaps` takes a build sign-off for another head as holding when `verify.sign_off_carried(q, tid, signed,
  head)`: the approve record's `catch_up` has `from` = the signed head, `to` = the head to merge and
  `sign_off_carried` = the signed head. It requires `from` as well as `sign_off_carried`, the narrowest reading of
  "the head the build sign-off covers": a record naming a different `from` carries nothing.
- `RECORD_VERSION` 5; `catch_up.sign_off_carried` (a sha, optional) in the schema; the example record's
  `schema_version` is 5; `tests/test_verify.py` `KEYS_AT` gets the version-5 list (a module the version bump breaks,
  so in scope).
- `ccp tasks ruling`: `lifecycle.ruling`, `queue.rulings` (the ledger's `ruling` `recorded` events of a task).
  `--check` is stored as given, not checked against the task's `dod_checks` (the task gives no such rule). The
  JSON body carries `id` at its top level as well as inside `ruling`. Actor `design-seat`.
- `scripts/observability/lib.py` (not in the task's `paths`): `ruling` joins `TOOLKIT_EVENT_TYPES` and
  `REQUIRED_PAYLOAD` (`id`, `n`, `words`); without it `emit` refuses the event as an invalid type.
- `verify._ruling_refusal`: `<task_id>-r<n>` tokens, judged against the ledger; the same function serves `rests_on`
  and `as_written`'s `ruling`, so a lead ruling id is also a ruling form for a check not run, as §15.4's ruling
  form is one form for both. A ruling id of another task is as good as a gate id of another task.
- SPEC: each PROPOSED passage is on a line of its own, the sentence around it re-broken at the passage's edges;
  `ccp verify spec-text` exits 0.

## Verification notes
