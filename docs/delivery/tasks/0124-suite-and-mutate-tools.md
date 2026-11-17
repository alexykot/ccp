---
task_id: 0124-suite-and-mutate-tools
title: suite wait exits 0 or 1 for a finished run, suite run takes --cold, worker_env renders dry, and mutate takes a mutant file
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S14"]
review_point: R8
sign_off: brief
paths: ["ccp/suite.py", "ccp/mutate.py", "ccp/prompt.py", "ccp/cli.py", "scripts/gate.sh", "templates/prompts/_common.md", "templates/prompts/verify.md", "docs/spec/02-delivery.md", "tests/test_suite*.py", "tests/test_mutate.py", "tests/test_prompt_env.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0124-suite-and-mutate-tools
## Intent

Workers wait on a long run without a loop that never ends, ask any cached gate for a cold run the
same way in every product, see what `worker_env` gives a worktree before a run, and prove a test
bites with a mutant that spans lines.

## Context (not checked)

- `ccp suite wait` exits with a finished run's own exit code, so a run whose command exited 3 reads
  as "still running" (the same code); a script polling on the code loops. The lead ruled the fix on the
  task that built the command; its fix round ran before the ruling reached it.
- A cold run of the plane's cached gate is asked for with a gate-specific variable (`GATE_COLD=1`).
- `--mutant file:old=>new` needs shell-quoted text for a multi-line mutant, which seats got wrong
  by hand (a product's friction notes, five seats in three tasks).
- §31.1 for `--cold`, the dry render and `--mutant-file`: each is this task's own feature.

## Scope

- **In:**
  - `docs/spec/02-delivery.md` §14.2. CURRENT (at `b4de6ad`): "and exits with the run's exit code." PROPOSED:
    > and exits 0 when the run passed and 1 when it failed (§10.6), the summary showing the run's own exit code.
  - `docs/spec/02-delivery.md` §14.2. CURRENT (at `b4de6ad`): "a printed summary means the run ended, whatever the code." PROPOSED:
    > exit 3 means only that the run is still going.
  - `ccp suite run --cold`: sets `CCP_SUITE_COLD=1` for the lane's stages and records `cold: true`;
    `scripts/gate.sh` reads it as it reads `GATE_COLD`; the verify prompt asks for the cold run this way.
  - `ccp prompt env <worktree>` (new): prints the `worker_env` lines the worktree's workers would get,
    rendered from its record, opening no run.
  - `ccp mutate --mutant-file PATH`: the file holds `file`, then the old text and the new text,
    separated by lines `=== old` and `=== new`; refused (exit 2) when a part is missing.
  - `templates/prompts/_common.md`: the polling sentence matches §14.2.
- **Out:**
  - A product's own gate's cache.

## dod_checks

- id: `cmd-01`
  story: As a worker, a finished run whose command exited 3 ends my wait.
  setup: a scratch product with a lane whose command is `sh -c 'exit 3'`, run once.
  steps:
    1. Run `ccp suite wait <its id>`.
  expect: exit 1; the summary shows exit code 3.
  dry run: n/a.
- id: `cmd-02`
  story: As a verifier, I ask any gate for a cold run the same way.
  setup: a scratch product with a gate lane whose stage prints `$CCP_SUITE_COLD`.
  steps:
    1. Run `ccp suite run --lane gate --cold`.
  expect: the log shows `1`; the run's record holds `cold: true`.
  dry run: n/a.
- id: `cmd-03`
  story: As a product writer, I see what worker_env gives a worktree.
  setup: a scratch product whose `prompts.worker_env` uses `{{nnnn}}` and `{{seat}}`, with a recorded `rev` worktree.
  steps:
    1. Run `ccp prompt env <that worktree>`.
  expect: prints the rendered lines with that worktree's values; no run or prompt audit is recorded.
  dry run: n/a.
- id: `cmd-04`
  story: As a seat, a multi-line mutant needs no shell quoting.
  setup: a scratch repo with a two-line function and a test that catches a change to it; a mutant file replacing both lines.
  steps:
    1. Run `ccp mutate --mutant-file <file> -- <test command>`.
  expect: the test fails on the mutant and the file is restored; a file without `=== new` exits 2.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the two §14.2 edits with the PROPOSED text above.
  expect: they match word for word, other §14 edits only describe the new options, and no other § rule changes.
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

- 2026-11-17 (implementer): built as scoped.
  - `ccp suite wait` exits 0 for a passed run and 1 for any other finished run (an interrupted one
    too); the summary keeps the run's own code. Only a run still going exits 3. The two §14.2 edits
    are the PROPOSED text word for word; `_common.md` says the same.
  - `ccp suite run --cold` adds `CCP_SUITE_COLD=1` to what the run starts: a lane's stages, a command
    after `--`, and a nested run's command. The `ended` row and its event record `cold: true` unless
    the run's own count shows units cached (then `false`: the count wins over the ask). `scripts/gate.sh`
    turns a `CCP_SUITE_COLD` other than empty or 0 into `GATE_COLD=1`. The verify template names
    `ccp suite run --lane <gate role's lane> --cold` (new template value `gate_lane`).
  - `ccp prompt env <worktree>` takes the worktree's path or its recorded name and prints the
    `export` lines `ccp prompt` would write, from the worktree record (task, nnnn, kind, seat, path).
    `run_id` and `phase` come from the open run bound to that worktree, else stay `<run_id>` and
    `<phase>`. It writes nothing, opens no run, writes no audit and starts no board rebuild. A
    worktree with no record, or a value that looks like a secret, exits 2; a product with no
    `worker_env` prints nothing (exit 0, a note on stderr).
  - `ccp mutate --mutant-file PATH`: first line the target path, then `=== old`, the old text,
    `=== new`, the new text. Each text is the exact bytes between its marker line and the next (or
    EOF). A missing path, marker or old text exits 2. Mutant files are numbered after `--mutant` and
    before `--revert`. The dod_check `cmd-04` writes the step as `ccp mutate --mutant-file <file> --
    <test command>`; `ccp mutate` takes its test as `--test <id>` run through plane.json
    `mutate.command` and has no `--` form, so the option was built on the existing call.
  - SPEC: the two signed §14.2 edits. Descriptions of the new options (§31.1) in §13.3
    (`prompt env`), §14.2 and §14.6 (`--cold`), and §20.6 in `docs/spec/03-quality.md`
    (`--mutant-file`). That file is outside the task's `paths`, but §20.6 is where `ccp mutate` is
    specified. The CLI reference (`docs/cli/02-delivery.md`, `docs/cli/03-quality.md`) lists the
    new options.
  - Tests the change necessarily touches: `tests/test_gate_parallel.py`'s fixture drops an
    inherited `CCP_SUITE_COLD`, as it drops `GATE_COLD`, and `tests/test_suite.py`'s `ccp_proc`
    does the same. Otherwise the plane's own gate, run with `--cold`, would run its cache tests
    cold.

## Verification notes
