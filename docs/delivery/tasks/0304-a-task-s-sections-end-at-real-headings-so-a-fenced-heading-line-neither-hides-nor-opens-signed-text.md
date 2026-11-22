---
task_id: 0304-a-task-s-sections-end-at-real-headings-so-a-fenced-heading-line-neither-hides-nor-opens-signed-text
title: A task file's sections end only at real headings, so a fenced `## ` line neither hides a signed passage from ccp verify spec-text nor opens a signed section
status: pending
kind: feature
depends_on: ["0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes"]
spec_refs: ["S3", "S15"]
rule_refs: ["E22"]
review_point: R28
clashes_with: ["0191-the-grace-release-ends", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured"]
paths: ["ccp/tasklog.py", "tests/test_signed_sections_fences.py", "tests/test_signed_blocks_check.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0304-a-task-s-sections-end-at-real-headings-so-a-fenced-heading-line-neither-hides-nor-opens-signed-text

## Intent

The operator's signed text is always checked. A brief whose Scope holds a fenced block with a line that
starts `## ` (an example of a task file, a quoted heading) keeps its Scope to the next real heading, so a
properly quoted `PROPOSED:` after the fence is a passage `ccp verify spec-text` looks for, and a build
that leaves it out of the SPEC fails the check. A fenced `## Rule changes` line is quoted text, so it
opens no signed section, and a `PROPOSED:` inside a fence is never read as signed text. `ccp tasks
check`'s unreadable-`PROPOSED:` warning reads the same sections, marker for marker.

## Context (not checked)

From the lead's notes on architect pass `ar-20261122T162238Z-9098` (the record is in `docs/delivery/reviews/`),
items (a) and (d). Measured at `0f44fb3` (origin/main, after 0285 merged) unless a line says otherwise.

- **The hole.** `ccp/tasklog.py` `"def _section_at"` finds a section's end with
  `re.search(r"^## ", text[m.end():], re.M)` on the raw text, and `"def _signed_sections"` finds
  `Rule changes` headings with `_RULE_CHANGES_RE.finditer(text)` on the raw text. `"def signed_blocks"` (what
  `ccp verify spec-text` reads, through `verify.signed_passages`) takes its sections from them. A probe at
  `0f44fb3` (`python3 -B -c` calling `tasklog.signed_blocks` on a task text whose Scope holds a three-backtick
  fence around the line `## Not a heading`, then a `CURRENT` line with its (`docs/spec/x.md` at `abc1234`)
  locator, a quoted line, `PROPOSED:` and the quoted line `> new text here`) printed `[]`; the same text with
  the fenced line changed to `no heading` printed `[(14, 'new text here', 'docs/spec/x.md')]`. So signed text after such a fence escapes
  spec-text entirely: spec-text then judges the task as carrying fewer passages, or exits 2 as carrying none.
- **The false section.** The same probe on a task whose `## dod_checks` holds a fence around the lines
  `## Rule changes`, `PROPOSED:` and `> fenced passage` printed `[(12, 'fenced passage', None)]`: a quoted
  example becomes a passage the build must add to the SPEC.
- **0285 (done, PR #354, squash `0bb5470`)** aligned `"def unreadable_proposed"` with `signed_blocks` by
  reading the sections from the raw text too (its `cmd-04`). Its two new tests in
  `tests/test_signed_blocks_check.py` both fence the line `## Rule changes`, so the first
  (`test_a_scope_holding_a_fenced_heading_line_then_an_inline_proposed_warns_on_its_line`) passed at 0285's base
  for the wrong reason: the fenced line opens a section of its own, whatever the Scope's end. The second
  (`test_an_inline_proposed_under_a_fenced_rule_changes_line_warns_as_spec_text_reads_it`) pins the false
  section above. This task turns both round.
- **Who else reads `_section_at`.** Every section reader of the task log (`_section`, the dod_checks split, the notes sections). `python3 -B -c` over `docs/delivery/tasks/*.md` at `0f44fb3`, comparing the `^## ` line offsets of each file's raw text with those of its text with `FENCE_RE` blanked: 0 files differ. So no task file in the log reads differently after the change.
- **No SPEC change.** §3.5 and §15.2 read "the task's Scope, or a section of the task whose heading begins `Rule changes`"; a line inside a fenced block is no heading. `git grep -n 'heading begins' -- docs/spec` at `0f44fb3`: 2 lines (`docs/spec/01-model.md` 1, `docs/spec/02-delivery.md` 1), none naming fences. The SPEC already says a fenced block is not read for placeholders (§5, `docs/spec/01-model.md`) and rules (§20.1).
- **Other tasks.** 0301 (claimed) adds a `ccp tasks check` warning in `ccp/tasklog.py`, and 0293 (claimed) edits
  it for seat ids; 0191 (pending) lists test globs. Different logic; recorded as clashes since the files meet.

### Rulings for the build (the lead's)

- `"def _section_at"` matches its heading, and the next `^## ` line, in `FENCE_RE.sub(_blank, text)` (same
  length and line breaks, so offsets hold) and returns the body sliced from the raw text.
- `"def _signed_sections"` finds `Rule changes` headings and their ends in that blanked text, and returns raw
  bodies.
- `"def signed_blocks"` reads a `PROPOSED:` marker only where it is outside a fence and a code span (the text
  with both blanked, as `unreadable_proposed` does), and takes the passage, the quotes and the block's file
  from the raw lines, as now.
- `"def unreadable_proposed"` keeps 0285's shape (raw sections from `_signed_sections`, markers read in the
  blanked text); it now reads the same sections and markers as `signed_blocks` by construction.
- In `tests/test_signed_blocks_check.py`, 0285's first test fences `## Not a heading` instead of
  `## Rule changes`; its second becomes
  `test_an_inline_proposed_under_a_fenced_rule_changes_line_does_not_warn`, asserting no warning. No other
  test expectation changes.

## Scope

- **In:** `ccp/tasklog.py` (`_section_at`, `_signed_sections`, `signed_blocks`, `unreadable_proposed`),
  `tests/test_signed_sections_fences.py` (new), `tests/test_signed_blocks_check.py` (0285's two tests).
- No SPEC change (measured in Context).
- **Out:** `FENCE_RE` and `CODE_SPAN_RE` themselves; ADR and SPEC heading readers (`ccp/adr.py`, the
  citations rule); `verify.signed_passages`' shape; 0285's task file.

## dod_checks

- id: `code-01`
  story: As the operator, a signed passage after a fenced `## ` line in the Scope is one spec-text checks.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_signed_sections_fences`.
    2. Run `grep -e fenced_heading -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_signed_sections_fences --revert ccp/tasklog.py`.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `fenced_heading` in which `tasklog.signed_blocks` of a Scope holding a fenced `## Not a heading` line followed by a quoted `PROPOSED:` block returns that passage with its line and the file its locator names; then `OK`. Step 3 prints the mutant `killed`.
  dry run (`0f44fb3`): n/a — the module is new; Context's probe printed `[]` for that text today.
- id: `cmd-01`
  story: As the operator, a build that leaves out a passage signed after such a fence fails ccp verify spec-text.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_signed_sections_fences`.
    2. Run `grep -e spec_text -e '^OK' <the log step 1 names>`.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `spec_text` in which `ccp verify spec-text` (through `ccp.cli.main`, in a fixture repo) of a task whose Scope holds a fenced `## ` line and then one quoted `PROPOSED:` passage, on a branch that adds other text to the SPEC, exits 1 and its `missing` names that passage; then `OK`.
  dry run (`0f44fb3`): n/a — the module is new; at `0f44fb3` such a task carries no passage, so spec-text exits 2.
- id: `code-02`
  story: As a task writer, a fenced `## Rule changes` line or a fenced PROPOSED block is quoted text, never signed text.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_signed_sections_fences tests.test_signed_blocks_check`.
    2. Run `grep -e fenced_rule_changes -e '^OK' <the log step 1 names>`.
  expect: step 1 exits 0; step 2 lists, each `ok`, a test in `tests.test_signed_sections_fences` whose name holds `fenced_rule_changes` in which `signed_blocks` of a task whose `## dod_checks` holds a fence around `## Rule changes`, `PROPOSED:` and a `> ` line returns `[]`, and `test_an_inline_proposed_under_a_fenced_rule_changes_line_does_not_warn` in `tests.test_signed_blocks_check`; then `OK`.
  dry run (`0f44fb3`): n/a — the tests are new; Context's probe printed `[(12, 'fenced passage', None)]` for that text today.
- id: `code-03`
  story: As a task writer, a dod_check whose steps quote a `## ` line in a fence keeps every check after it.
  setup: A checkout of the PR head, in your own worktree, with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_signed_sections_fences`.
    2. Run `grep -e dod_checks -e '^OK' <the log step 1 names>`.
  expect: step 1 exits 0; step 2 lists, `ok`, a test whose name holds `dod_checks` in which `tasklog.checks` of a task whose first check's steps hold a fence (at the line's start) around `## Example`, with a second check after it, returns both check ids; then `OK`.
  dry run (`0f44fb3`): n/a — the module is new; a probe (`python3 -B -c` calling `tasklog.checks` on that text) printed `['cmd-01']`.

## Implementation notes

## Verification notes
