---
task_id: 0157-spec-text-sections-and-head
title: ccp verify spec-text reads signed passages from a Rule changes section too, and checks a past commit with --head
status: done
kind: feature
depends_on: []
spec_refs: ["S15", "S3"]
review_point: R10
paths: ["ccp/verify.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_verify_spec_text.py"]
adopt: "none"
sign_off: brief
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0157-spec-text-sections-and-head
## Intent

A reviewer or verifier runs `ccp verify spec-text` on a task whose signed CURRENT → PROPOSED text sits
in a section of its own headed `Rule changes` (as some products write it) and gets the same check a
task with the text in its Scope gets, instead of exit 2 and a check done by hand; and anyone can ask
whether a past commit's SPEC change carries a task's signed words, with `--head <ref>`, without
checking that commit out.

## Context (not checked)

- `signed_passages` in `ccp/verify.py` reads only the `## Scope` section (`tasklog._section_at(text,
  tasklog.SEC_SCOPE)`). A task with its PROPOSED blocks under `## Rule changes (signed at tasking)`
  gets exit 2, "carries no PROPOSED: block … in its Scope".
- Done tasks in this repo with that heading, `git grep -l '^## Rule changes' -- docs/delivery/tasks` at `85d388b`: 2 files, 0144 and 0145.
- 0144's section only points at its Scope, where its block is. 0145 carries its PROPOSED blocks only
  there: `ccp verify spec-text 0145-adoption-rule-fixes --base da38de1^ --head da38de1` at `85d388b`
  exits 2 (no PROPOSED block in its Scope). Products that adopted the plane write the same heading.
- `--head` already parses on `ccp verify` (it is `check`'s PR head) and `spec-text` ignores it today:
  `spec_hunks` diffs `<base>...HEAD` and reads each SPEC file with `git show HEAD:<file>`.
- Where a task should carry signed text stays as §3.5 says (its Scope); this task only lets the check
  read the other section a task may use. A section whose heading begins `Rule changes` is the one read
  besides Scope; no other section is.
- §15.2 states that the passages are those "the task's Scope carries" and that the diff is
  `git diff <base>...HEAD`, so both changes alter rule text: `sign_off: brief`, the passages below.

## Scope

- **In:**
  - `ccp/verify.py` `signed_passages`: reads the `## Scope` section and every `## ` section whose
    heading begins `Rule changes` (any text after it, such as `(signed at tasking)`), in file order;
    a passage found in more than one place is listed once, at its first line. The exit-2 message names
    both places.
  - `ccp/verify.py` `spec_hunks` and `spec_text`, and `ccp/cli.py`: `ccp verify spec-text` takes
    `--head REF` (default `HEAD`). The diff is `git diff <base>...<head>` and each SPEC file is read as
    it is at `<head>`. A `--head` that names no commit exits 2, naming it. The body gains `head`. The task
    file is read from the checkout, as today. The `--head` help says it serves `check` and `spec-text`.
    The usage line in `ccp/cli.py`'s module docstring gains `[--head REF]`.
  - `docs/spec/02-delivery.md` §15.2, three passages:
    1. CURRENT (at `85d388b`): "`ccp verify spec-text <task_id> [--base REF]` reads each passage" PROPOSED:
       > `ccp verify spec-text <task_id> [--base REF] [--head REF]` reads each passage
    2. CURRENT (at `85d388b`): "the task's Scope carries for the operator's sign-off (§3.5: a `PROPOSED:` marker followed by `> `" PROPOSED:
       > the task's Scope, or a section of the task whose heading begins `Rule changes`, carries for the operator's sign-off (§3.5: a `PROPOSED:` marker followed by `> `
    3. CURRENT (at `85d388b`): "(`git diff <base>...HEAD`; the base defaults to `origin/<integration branch>`," PROPOSED:
       > (`git diff <base>...<head>`, each SPEC file read as it is at `<head>`, which defaults to `HEAD`; the base defaults to `origin/<integration branch>`,
  - `docs/cli/02-delivery.md`: the `ccp verify spec-text` row gains `[--head <ref>]`.
  - `ccp/verify.py` module docstring: the `spec-text` paragraph says the same.
  - `tests/test_verify_spec_text.py`: the checks below.
- **Out:**
  - Reading the task file as it was at `--head`.
  - Any change to where §3.5 says a task carries its signed text, or to `ccp tasks check`.

## dod_checks

- id: `sec-01`
  story: As a verifier, a task whose signed text sits under a Rule changes heading is checked like one with it in its Scope.
  setup: a fenced scratch product whose task carries one PROPOSED block under `## Rule changes (signed at tasking)` and none in its Scope, and a branch commit adding that passage to a SPEC file.
  steps:
    1. Run `ccp verify spec-text <task> --base <the commit before the branch>`.
  expect: exit 0; the body lists one passage, its `line` the line of that block in the task file, `found_in` naming the SPEC file.
  dry run: n/a — at `85d388b` the same layout exits 2 (task 0145, Context).
- id: `sec-02`
  story: As a verifier, a passage carried in both places is judged once.
  setup: the product of sec-01, its task carrying the same PROPOSED block in its Scope too, and a second block only under Rule changes that the branch does not add.
  steps:
    1. Run `ccp verify spec-text <task> --base <the commit before the branch>`.
  expect: exit 1; the body lists two passages, the shared one once; `missing` names only the second block's line.
  dry run: n/a.
- id: `head-01`
  story: As a lead, I check a past commit's SPEC change against the signed words.
  setup: a fenced scratch product with a task carrying one PROPOSED block in its Scope; commit A adds that passage to a SPEC file, then commit B rewrites the passage to other words; HEAD is B.
  steps:
    1. Run `ccp verify spec-text <task> --base <A^> --head <A>`.
    2. Run `ccp verify spec-text <task> --base <A^>`.
    3. Run `ccp verify spec-text <task> --base <A^> --head no-such-ref`.
  expect: step 1 exits 0 and its body's `head` is the given ref; step 2 exits 1 naming the passage; step 3 exits 2 and stderr names `no-such-ref`.
  dry run: n/a.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0157-spec-text-sections-and-head --base origin/main`.
  expect: exit 0, all three passages found in `docs/spec/02-delivery.md`.
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

- 2026-11-18 (implementer): `signed_passages` reads the Scope (`tasklog._section_at`, aliases included) and
  every section whose heading matches `^## Rule changes\b` (so `Rule changes (signed at tasking)` and
  `Rule changes, signed` are read, `Rule changesets` and `Proposed rule changes` are not), sorted by offset;
  a passage is deduplicated on its normalised text, which also folds a passage repeated within one section.
  `--head` stays one argparse option shared with `check` (default None there); `spec_text` treats a missing
  one as `HEAD`, checks it with `git rev-parse --verify --quiet <head>^{commit}` before the diff (exit 2,
  the error names the head and not the base), and every body that names the base also names the head. The
  not-found stderr line now reads "not found in the SPEC text <head> changes since <base>". The SPEC's
  exit-2 sentence in §15.2 still names only "no `PROPOSED:` block"; the bad-head exit 2, like the existing
  bad-base one, is in the code and module docstring only, as the task carried no passage for it.

## Verification notes
- 2026-11-18 — verifier, PR #176 head `dd5ab11` (squash `838efa2`): APPROVE. Passed: sec-01, sec-02, head-01, spec-01, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0157-spec-text-sections-and-head.json.

