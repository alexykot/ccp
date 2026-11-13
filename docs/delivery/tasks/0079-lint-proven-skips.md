---
task_id: 0079-lint-proven-skips
title: A product's prover command can skip a step it makes redundant, recorded on the run
status: pending
kind: feature
depends_on: []
spec_refs: ["S14", "S15"]
review_point: R5
paths: ["ccp/verify.py", "ccp/suite.py", "ccp/config.py", "contracts/", "docs/spec/02-delivery.md", "tests/test_review_skip*.py", "tests/test_suite_stages.py"]
created: 2026-11-12
updated: 2026-11-12
---

# Task: 0079-lint-proven-skips

## Intent

A change that a cheap, declared check proves harmless (a comment-only diff, a docs-only diff, a diff confined to declared paths) skips the step it makes redundant (a re-review, or a gate stage such as the suite), and the skip and its proof are recorded on the run (§14, §15).

## Context (not checked)

- Accepted plane proposal. Its triage records the operator's ruling of 11 Nov 2026, "if some gates can be skipped on that, they should be", as the acceptance.
- Generalises `verify.skip_review` (one proof for one skip) into declared provers.
- §31: this task adds or changes a § rule beyond describing its own feature, so its merge waits on the operator's approval of the final text at its merge gate (§31.1).
- Ruling sm-20261113T190943Z-1b85 (lead, 2026-11-13, spec commit `3030421`; the first ruling round), verbatim:
  "Drop the command text. Records carry the prover's name (its id in plane.json), its exit code and
  the run id; the command is looked up in plane.json by name, so the record never holds command text
  (E5, §14.4). That applies to the suite ended row, the verify run's review_skip and any event. Read
  the task's 'name, command and exit' as 'name and exit, with the command identified by name'. The
  edits outside the declared paths (the 01-model table row, the README git floor, the runner brief,
  the prompt label) are accepted; list them in the PR body. Record this ruling in 0079's Context with
  a ruling round, then review. The task stays gated at merge."
- Lead ruling (2026-11-13, after review and verify at `33643b8`, before the gate is decided; the second
  ruling round), verbatim:
  "Reviewer NIT 3 is a real hole, not a nit. A skip rule a task can grant itself by editing plane.json in
  its own diff defeats the point of the gate, so fix it in one round:
  - Provers and `verify.skip_review` are read from the integration branch's plane.json
    (origin/<integration> at the merge base or tip), never from the head under test. A prover the task
    adds or changes in its own diff doesn't apply to that task.
  - Test it: a task that declares a prover in its own diff gets no skip.
  - Say it in SPEC §14.2 (and §15.2 for skip_review).
  - Fix review NIT 2 too: put the run id inside `proven_skips`.
  Write this ruling into the task file's `Context (not checked)` section (second ruling round) and an
  Implementation note. Update the PR body (SPEC text changes and the text they replace). Merge
  origin/main first. Keep the earlier ruling (no command text on records) intact."
- Lead ruling (2026-11-13, after review 2 at `5fb7789`; the third ruling round), verbatim:
  "0079: option (b), in this PR. A skip that the task can grant itself by another route is the same hole.
  - Refuse a skip, at both the gate stage and the review skip, when the task's diff touches any file the
    prover's command names: each token of the integration branch's command that is a path in the repo,
    plus `plane.json` itself. Record the refusal reason (`prover_touched`) with the prover's name.
  - Fix both NITs too: fetch `origin/<integration>` before reading the rules (fall back to no skip if the
    fetch fails), and have verify say plainly when the integration plane.json doesn't load and nothing is
    skipped.
  - Tests: a diff that edits the prover's script gets no skip; one that doesn't still skips.
  - State it in SPEC §14.2 and §15.2."
- Lead ruling (2026-11-13, after review 4 at `b157eae`; the fourth ruling round), verbatim:
  "0079: option (1). Your diagnosis is right, and token-reading can't be made complete.
  - Run every prover, for both the gate-stage skips and `verify.skip_review`'s proof, with its working
    directory set to a clean worktree of origin/<integration>'s tip (fetched first). {from} and {head}
    resolve in the same repo.
  - Remove the token-reading code and its tests, keeping the rules read from the tip's plane.json.
  - Remove the worktree after each run.
  - SPEC §14.2 and §15.2 say provers run from the integration tip's checkout, so nothing a task's diff
    changes can alter their verdict.
  - Test that a task editing the prover's script still gets the integration branch's verdict."
  The runner's note with it: this supersedes ruling round 3's `prover_touched` refusal (the file-token
  reading, the `refused_provers` record field and its schema and SPEC text): remove them, and update the
  SPEC text, schemas and the PR body (each SPEC change and the text it replaces). Keep: the fetch before
  reading rules, the plain message when the integration plane.json does not load or the fetch fails, the
  `-z` diff if still needed, run_id in proven_skips, no command text on records. Use `ccp wt` or git
  worktree for the clean checkout; remove it after each run, also on error or signal.

## Scope

- **In:** plane.json `verify.provers`: a list of `{name, command, skips}` where `skips` names one step (`review` or a gate stage name); when the command exits 0 on the task's or fix round's diff, `ccp` skips that step and records the prover's name, command and exit on the run; `verify.skip_review` keeps working as one such prover; §14.2 and §15.2 state the rule (PROPOSED: "a declared prover that exits 0 on the diff skips the step it names, recorded on the run").
- **Out:** shipping provers for any language.

## dod_checks

- id: `check-01`
  story: As a runner, a docs-only diff skips the suite stage.
  setup: a scratch product with a prover `docs-only` that skips stage `suite` and exits 0 when the diff touches only `docs/`; a task whose diff touches only `docs/`.
  steps:
    1. Run the gate lane for the task.
  expect: the suite stage is skipped and the run records the prover's name and exit.
  dry run: on the merge base `verify.provers` is refused as an unknown key.
- id: `check-02`
  story: As a runner, a failing prover skips nothing.
  setup: as check-01 with a diff touching `src/`.
  steps:
    1. Run the gate lane.
  expect: the suite stage runs.
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

- 2026-11-13 (implementer): plane.json `verify.provers` (`[{name, command, skips}]`, default `[]`) in
  `ccp/config.py` and `contracts/plane_config.schema.json`. `skips` is `review` or a stage that the gate
  role's lane declares. That excludes `plane-docs` and argv lanes. Names are unique labels. Gate
  stages (`ccp/suite.py`): before a stage starts, on a run of the gate role's staged lane that is
  recorded and names its task, its provers run in order with `{task_id}`, `{from}` (merge base with
  `origin/<integration>`) and `{head}` filled in. The first that exits 0 skips the stage. The
  `ended` row records `proven_skips` (`stage, prover, command, exit_code`). The event records the same
  without `command`, since the ledger holds ids and numbers only. A checkout with uncommitted
  changes, or a head with no merge base, runs no prover. A signal while proving stops the run before
  the stage. Review (`ccp/verify.py`): `skip_review` computes the fix diff once and tries
  `verify.skip_review` first, unchanged with its record as before. It then tries each review prover;
  a prover's skip adds `prover`, `command` and `exit_code` to `review_skip`. The refusal names the
  settings in force (`review_proof_label`). SPEC §14.2, §14.4 and §15.2 carry the PROPOSED rule and
  describe the feature. §01 table, README git floor and runner brief name the new key.
- 2026-11-13 (implementer, ruling round 1): applied ruling sm-20261113T190943Z-1b85, recorded in
  Context. No record holds a prover's command text: the suite `ended` row's `proven_skips` entries are
  `{stage, prover, exit_code}`, the same as the `suite/recorded` event's (the event no longer filters a
  `command` out, since there is none), and the verify run's `review_skip` adds `prover` and `exit_code`
  only. The run id was already on both records (the suite run's `started` row and event carry
  `run_id`; `review_skip` sits on the verify run's own record), so no field was added. The
  `suite_result` schema drops `command` from `proven_skips` items; SPEC §14.2, §14.4 and §15.2 say the
  records carry the name and exit, the name looking the command up in plane.json. The tests assert the
  records' exact fields and that the command text appears in neither the suite record nor the ledger
  (nor the verify run's record, for the review prover).
- 2026-11-13 (implementer, ruling round 2): applied the lead's second ruling, recorded in Context. The
  skip rules are read from plane.json on `origin/<integration branch>`, its tip as the checkout last
  fetched it (the ruling allows the merge base or the tip; the tip needs no merge base to find the rules,
  so `ccp` reads them before anything else and a product without them sees no new message or fetch, and
  a rule the integration branch drops stops applying at once). `config.skip_rules_at(root, rev)` loads
  and checks plane.json at a revision (`git show`) and returns its `verify` block; `load` and it share
  `_parse`. Gate stages (`suite.stage_provers`) take their provers from it, never from the checkout's
  plane.json; an integration plane.json that does not load declares none, and the stage log says so.
  Review (`verify.skip_review`) reads `verify.skip_review` and the review provers the same way, before
  its fetch; its refusal reason now carries the settings label (`review_proof_label` takes the `verify`
  block), so `ccp prompt verify` prints it as is. The suite `ended` row's and event's `proven_skips`
  entries gain `run_id` (the suite run's run, null without one; review NIT 2). The command text stays
  off every record (ruling round 1). SPEC §14.2, §14.4 and §15.2 and both schemas say so. Tests: a
  prover, or `verify.skip_review`, that only the head (or the runner's checkout) declares gets no skip;
  the integration branch's prover applies whatever the head declares; an integration plane.json that
  does not load declares none. The prover tests now push their plane.json to origin/main.
- 2026-11-13 (implementer, ruling round 3): applied the lead's third ruling, recorded in Context.
  `config.prover_touched(command, touched, root)` gives the files of the task's diff a prover's command
  names: each shell word of the integration branch's command (split with `shlex`, operators apart, and a
  quoted word's own words too, so `sh -c '<script> …'` counts), made relative to the root and normalised,
  that is a touched path, plus plane.json itself. A file token only: a directory such as `.` names no file,
  or every docs-only prover written with a pathspec would be refused. Gate stages: `task_diff` also
  returns the task's touched files (merge base to HEAD, renames as both paths); a prover that touches one
  is refused before it runs, the next prover still tried, and the `ended` row and its event record
  `refused_provers` (`{stage, prover, reason: "prover_touched", run_id}`, the shape of `proven_skips`).
  Review: `_judge_fix` reads the task's diff (the head's merge base with the integration branch to the
  head, not only the fix diff, as the ruling says "the task's diff") and refuses a review prover, and the
  `verify.skip_review` proof (named `verify.skip_review`; the Scope makes it "one such prover"), the same
  way; the refusal names each with `prover_touched`, and a skip a later prover proves records
  `refused_provers` (`{prover, reason}`) on `review_skip`. NITs: `stage_provers` fetches
  `origin <integration>` and `skip_review` fetches `origin` before reading the rules, and a failed fetch
  reads none (the stage log, or the verify refusal, says so); verify says "nothing is skipped" when the
  integration plane.json does not load. A head that edits plane.json now gets no skip from the
  integration branch's prover, so the round-2 test that the integration's rule applied whatever the head
  declared became the test that such a head is refused. SPEC §14.2, §14.4 (the record list) and §15.2,
  both schemas and the suite and verify docstrings say so.
- 2026-11-13 (implementer, fix round 1, after review 3 at `9315343`): `config.prover_touched` now also
  reads the pieces of each shell word between the shell's metacharacters, `=` and braces, so a script in a
  quoted command substitution (`test -z "$(<script> {from} {head})"`), a backquoted one and
  `--config=<file>` count, and a path written after a variable or a substitution (`$PWD/<script>`,
  `${ROOT}/…`, `$(git rev-parse --show-toplevel)/…`) is read from the root (review 3 MAJOR 1). A path
  outside the root (`../x`) still names nothing. The task's diff that feeds it is read with `git diff -z`
  in `suite.task_diff` and `verify._judge_fix`, so a path with a non-ASCII character is not quoted and
  still matches (MINOR 1). SPEC §14.2 and §15.2 and the plane_config schema say what a token is and that
  only a file the command names literally is covered, not one reached through `cd`/`-C`, a module, a make
  or npm target, a glob, a symlink or a sourced file (MINOR 2). New tests pin that the gate and verify
  fetch `origin/<integration>` before reading the rules: a prover another clone pushes after the runner's
  last fetch applies (MINOR 3). The §14.2 Provers bullet is reflowed (NIT 1).
- 2026-11-13 (implementer, ruling round 4): applied the lead's fourth ruling, recorded in Context; it
  supersedes round 3's refusal. Every prover, a gate stage's, a review prover and `verify.skip_review`'s
  `proof`, now runs with its working directory in a clean, detached git worktree of the
  `origin/<integration branch>` commit the rules were read at (fetched first, then resolved to a sha, so
  the rules and the checkout are the same commit). `suite.clean_checkout(root, sha)` makes it in a temp
  dir with `git worktree add --detach` in the product's repository (so `{from}`, `{head}`, `{reviewed}`
  and the merge-tree `{from}` resolve in it) and removes it on the way out (`git worktree remove
  --force`, the temp dir, `git worktree prune`); in its scope a SIGTERM or SIGHUP left at its default
  handler exits through Python, so the removal runs (SIGINT already does, and the suite's own handler
  takes SIGINT and SIGTERM). It is made once per run, on first use, and removed when the run ends: at the
  end of `ccp suite run` (its `finally`), and when `verify.skip_review` finishes judging. A prover in one
  run therefore shares the checkout with the provers after it (the narrowest reading of "after each
  run"). Git cannot make it: no prover runs, and the stage log or the verify refusal says so.
  `rules.run_command` takes a `cwd` and now kills the command's process group when an exception (a
  signal raised in Python) interrupts it. Removed: `config.prover_touched`, `PROVER_TOUCHED`, the
  `refused_provers` field on the suite `ended` row, its event and `review_skip`, its schema entry, and the
  task's touched-file list (and with it the `-z` diffs, which only fed the token reading). The rules stay
  read from the tip's plane.json; the fetch, the plain messages, `run_id` in `proven_skips` and no command
  text are unchanged. A head that edits plane.json gets the integration branch's verdict again. SPEC
  §14.2, §14.4 and §15.2, both schemas and the suite and verify docstrings say so. Tests: a task whose
  diff edits the prover's script (a gate stage prover, a review prover, the `proof`) gets the integration
  branch's verdict, both ways; the prover's working directory is a clean checkout of the tip that is gone
  after the run, after an error and after a signal.

## Verification notes

*Append-only.*
