---
task_id: 0142-signed-text-checks
title: The signed-text check reads each hunk on its own and no content line as a header, next's stdout names unsigned tasks, and a spec path without a slash is exact
status: done
kind: feature
depends_on: []
spec_refs: ["S3", "S15", "S10"]
review_point: R9
paths: ["ccp/verify.py", "ccp/cli.py", "ccp/tasklog.py", "tests/test_verify_spec_text.py", "tests/test_tasklog_spec_signoff.py", "tests/test_sign_off.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-18
---

# Task: 0142-signed-text-checks
## Intent

`ccp verify spec-text`, the check that guards the operator's signed words, gives no false pass when a
passage's pieces sit in separate hunks, and does not lose a file because an added line begins `++ `;
`ccp tasks next` says on stdout that tasks wait on a sign-off when that is why nothing is ready; and a
configured SPEC path without a trailing `/` matches only itself, as the signed §3.5 text says.

## Context (not checked)

- `added_spec_lines` (`"def added_spec_lines"` in `ccp/verify.py`) joins every added line of a file, from
  `git diff --unified=0`, into one text. A signed passage whose two halves were added in two hunks, with
  an unchanged line between them in the file, reads as found: a false pass.
- The same function treats any diff line starting `+++ ` as a file header. An added content line whose
  text starts `++ ` is `+++ …` in the diff, so it resets the current file (to none, or to a wrong path)
  and the lines after it are lost.
- `ccp tasks next` prints, when nothing is ready, "nothing ready: every pending task is blocked on a
  dependency, or all are done" (`"nothing ready"` in `ccp/cli.py`), even when the reason is that every
  ready task waits on its brief sign-off or is held; only stderr names those.
- `_names_spec` (`"def _names_spec"` in `ccp/tasklog.py`) treats every `task_log.spec_paths` entry as a
  directory too (`e + "/"`), so an entry `docs/spec` meets `docs/spec/x.md`. The signed §3.5 text
  (`docs/spec/01-model.md`, task 0128) says: "a path meets an entry it equals or, for an entry ending in
  `/`, lies under, so `docs/spec` without its `/` meets none". `added_spec_lines` uses the same function.
  `tests/test_tasklog_spec_signoff.py`'s `test_an_entry_without_a_slash_names_a_directory_too` pins the
  current behaviour and changes with it.
- A proposal said several signed edits in task 0128 read as not found because passages span a SPEC line
  break, and asked for whitespace to be normalised across lines. That premise is false: the added lines
  are already joined with spaces and normalised (`_norm(" ".join(ls))` in `added_spec_lines`).
- Measured at `921507e`: `git diff 7ff1abd^ 7ff1abd -- docs/spec` against 0128's `signed_passages`: 4 of 12 not found.
- Each of those misses is a passage whose first words sit on an unchanged line before the added one.
  Matching that case needs §15.2's "in the lines the branch adds" to change: that is task 0147, with
  signed text.
- Making `next` pass over a stale or malformed brief sign-off changes §10.3's rule: also task 0147.
- No SPEC change: per-hunk matching and the header parse keep §15.2's "looks for it, whitespace-normalised,
  in the lines the branch adds"; the stdout line is not specified; `_names_spec` is brought into line with
  §3.5 as signed.

## Scope

- **In:**
  - `ccp/verify.py` `added_spec_lines`: per SPEC file, a list of texts, one per hunk (the hunk's added
    lines joined and whitespace-normalised); `spec_text` finds a passage when it lies within one hunk's
    text. File headers (`+++ `, `--- `) are read only between a `diff --git` line and that file's first
    `@@` line; within a hunk every `+` line is content. The module docstring and `spec_text`'s say "each
    hunk's added lines read as one text".
  - `ccp/cli.py` `tasks next`: when nothing is ready and tasks were passed over for a missing brief
    sign-off or a hold, the stdout line says so with their counts, e.g. "nothing ready: 2 wait on a brief
    sign-off, 1 held (stderr names them)"; otherwise it is unchanged. Exit 3 as before.
  - `ccp/tasklog.py` `_names_spec`: a path meets an entry it equals, or, for an entry ending in `/`, lies
    under it; an entry without `/` is exact. Its docstring cites §3.5.
  - `tests/test_tasklog_spec_signoff.py`: `test_an_entry_without_a_slash_names_a_directory_too` is
    replaced by a test of the exact match.
- **Out:**
  - Matching a passage that starts on an unchanged line (task 0147).
  - Stale or malformed sign-offs in `next` (task 0147).

## dod_checks

- id: `spec-01`
  story: As a reviewer, a passage split across hunks is not reported found.
  setup: a fixture repo (`tests/test_verify_spec_text.py`'s) whose task signs the passage "Alpha one. Beta two."; the branch adds "Alpha one." and "Beta two." to `docs/spec/x.md` as two lines with an unchanged line "Gamma." between them.
  steps:
    1. Run `ccp verify spec-text 0001-signed --base <base>`.
  expect: exit 1, naming the passage as not found.
  dry run: n/a.
- id: `spec-02`
  story: As a reviewer, an added line that begins `++ ` does not hide the rest of the file.
  setup: the fixture repo; the branch adds to `docs/spec/x.md` a line `++ counter` and, after it in the same hunk, the signed passage.
  steps:
    1. Run `ccp verify spec-text 0001-signed --base <base>`.
  expect: exit 0, the passage found in `docs/spec/x.md`.
  dry run: n/a.
- id: `spec-03`
  story: As a reviewer, a passage added whole in one hunk is still found.
  setup: the fixture repo; the branch adds the signed passage over three wrapped lines in one hunk of `docs/spec/x.md`.
  steps:
    1. Run `ccp verify spec-text 0001-signed --base <base>`.
  expect: exit 0.
  dry run: n/a.
- id: `next-01`
  story: As a runner, the stdout of an empty next says tasks wait on a sign-off.
  setup: a scratch product whose only pending task declares `sign_off: brief` with none recorded, and a queue.
  steps:
    1. Run `ccp tasks next`.
  expect: exit 3; stdout's line says one task waits on a brief sign-off.
  dry run: n/a.
- id: `path-01`
  story: As a product writer, a spec path without a slash is exact, as §3.5 says.
  setup: a scratch product with `task_log.spec_paths: ["rules"]` and pending tasks with `paths` `["rules"]`, `["rules/one.md"]` and `["rulesets/one.md"]`, none declaring a sign-off or §31.1.
  steps:
    1. Run `ccp tasks check`.
  expect: the unsigned-SPEC-edit warning names only the task with `paths` `["rules"]`.
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

- 2026-11-18 (implement): `verify.added_spec_lines` now returns, per SPEC file, one whitespace-normalised
  text per hunk (empty hunks, a deletion's, dropped); `spec_text` finds a passage when one hunk's text holds
  it. The parse reads `+++ ` only while in a file's header (after `diff --git`, before its first `@@`); with
  `--unified=0` no content line begins `@@`, so every `+` line inside a hunk is content. `tasklog._names_spec`
  is exact for an entry without `/` (§3.5 as signed). `tasks next`'s empty stdout line counts the tasks
  passed over (`selection.pick`'s `unsigned` and `passed_over`): "nothing ready: 1 waits on a brief sign-off
  (stderr names it)", "…: 2 wait on a brief sign-off, 1 held (stderr names them)"; with neither, the old
  line. `--json` is unchanged (`null`, exit 3).
- Premise re-run at `78e8940` (`git diff --unified=0 7ff1abd^ 7ff1abd -- docs/spec` against
  `signed_passages` of 0128's task file at `7ff1abd^`): 4 not found, as stated, of 10 passages, not 12; the
  same 4 per hunk, so per-hunk matching changes no outcome there.

## Verification notes
- 2026-11-18 — verifier, PR #153 head `2021b2a` (squash `4fc06e4`): APPROVE. Passed: spec-01, spec-02, spec-03, next-01, path-01, suite-01. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0142-signed-text-checks.json.

