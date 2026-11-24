---
task_id: 0313-close-and-the-estimator-find-task-sections-outside-fences-and-a-backtick-fence-s-info-string-holds-no-backtick
title: Close's notes edit and the estimator's task text find section headings outside fenced blocks, a backtick fence's info string holds no backtick, and the placeholder check reads the unquoted text through the shared helper
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S10", "S26"]
rule_refs: ["E22"]
review_point: R31
paths: ["ccp/tasklog.py", "ccp/lifecycle.py", "ccp/estimate.py", "tests/test_section_readers_fences.py"]
clashes_with: []
adopt: "none"
created: 2026-11-23
updated: 2026-11-23
---

# Task: 0313-close-and-the-estimator-find-task-sections-outside-fences-and-a-backtick-fence-s-info-string-holds-no-backtick

## Intent

Every reader of a task file's sections agrees on where a section starts and ends. `ccp tasks close` writes its
merge record under the task's real `## Verification notes` heading, never inside a fenced example in the Scope,
and the estimator's task text (what `task_hash` hashes) keeps a fenced `## Implementation notes` line and the
text after it, so only the real notes sections are left out. A line that starts with a three-backtick code span
(```` ```x``` is a span ````) is prose, not a fence opener, so it no longer hides the task's later headings from
every section reader. And the placeholder check reads the unquoted text through the same helper the signed-text
readers use.

## Context (not checked)

Covers these follow-ups (`ccp --root . tasks follow-ups --open`), and the lead's notes on them:

- `0304-…/review#1` and `0304-…/verify#1`: `lifecycle._task_file_done` and `estimate.strip_notes` should find section
  headings outside fenced blocks, as `tasklog._section_at` now does.
- `0304-…/review#2` and `0304-…/verify#2`: `FENCE_RE` should refuse an opener whose info string holds a backtick
  (CommonMark: "If the info string comes after a backtick fence, it may not contain any backtick characters").
- `0304-…/implement#1`: `_check_placeholders` could use `_unquoted`.

Measured at `b09de675` (origin/main) unless a line says otherwise. Each probe runs from the checkout root.

- **Close.** `ccp/lifecycle.py` `"def _task_file_done"` finds `re.search(rf"^## {re.escape(tasklog.SEC_VERIFY)}[ \t]*(?=\r?$)", text, re.M)`
  and the next `^## ` in the raw text. The probe of `code-01` (a Scope fence around `## Verification notes`, the real
  heading last) printed `False 1` at `b09de675`: the one note went inside the Scope, before the real heading.
- **The estimator's text.** `ccp/estimate.py` `"def strip_notes"` finds each `NOTES` heading and its end in the raw text.
  The probe of `code-02` printed `False True False` at `b09de675`: the Scope's text after the fence was cut and the real
  Implementation notes kept.
- **The fence opener.** `ccp/tasklog.py` `FENCE_RE`'s opener is followed by `[^\n]*`, any info string. The probe of
  `code-03` printed `[False, False]` at `b09de675`: the span line opened a fence that a later real fence closed, hiding
  `## dod_checks`.
- **The placeholder check.** `"def _check_placeholders"` computes `CODE_SPAN_RE.sub(_blank, FENCE_RE.sub(_blank, t["_text"]))`,
  which is `_unquoted(t["_text"])` by definition (`"def _unquoted"` returns `CODE_SPAN_RE.sub(_blank, _unfenced(text))`).
  `git grep -n 'CODE_SPAN_RE.sub(_blank, FENCE_RE.sub' -- ccp` at `b09de675`: 1 line.
- **No stored hash moves.** `task_hash` hashes `strip_notes`' output, so a task file whose headings read differently
  would be re-estimated. The probe of `data-01` (each task file's `^## ` offsets in its raw text against those in its
  text with fences blanked) printed `[]` at `b09de675`. With this task's `FENCE_RE`, a probe at `b09de675` blanking each file
  under `docs/delivery/tasks/` and `docs/delivery/reviews/` with the old and the new pattern found no file that differs
  (`python3 -B` over both globs, comparing `FENCE_RE.sub(_blank, s)` for each pattern: `[]` for both directories).
- **A bound product's log too.** The same probe, extended to compare `strip_notes`' output today with the ruled
  `strip_notes` (headings found in the text blanked with the new `FENCE_RE`), ran read-only over this checkout's task log
  and over the task log of each product bound on the plane's machine, at `b09de675`:
  `python3 -B <probe> <product root>` printed 0 blanking differences and 0 `strip_notes` differences in every log, so no stored
  `task_hash` moves in any of them.
- **Line endings.** `FENCE_RE`'s closer is `[ \t]*$`, so in a CRLF file no fence closes and nothing is blanked: such a
  file reads as raw text, as close reads it today. `python3 -B -c 'from ccp import tasklog as t; print(bool(t.FENCE_RE.search("a\r\n\x60\x60\x60\r\n## X\r\n\x60\x60\x60\r\n")))'`
  at `b09de675`: `False`. Close's CRLF handling stays as it is; CRLF fences are out of this task.
- **No SPEC change.** §5's notes sections and §26's "the task file without its notes" (`docs/spec/04-observability.md`)
  name sections; a fenced line is no heading, as 0304 measured. `git grep -nE 'info string|backtick fence' -- docs/spec`
  at `b09de675`: no line.
- **Clashes.** A script over the pending tasks' `paths` at `b09de675` found: 0191 and 0305 (`ccp/lifecycle.py`: the
  grace release; `_own_commit` and close's merge-outcome refusals), 0309 (`ccp/tasklog.py`: `runs_bare`). None changes
  `_task_file_done`, `strip_notes`, `FENCE_RE` or a section reader
  (`git grep -nE '_task_file_done|strip_notes|task_hash|FENCE_RE|_unfenced|_section|_check_placeholders' -- <those task files>`
  at `b09de675`: no line). So `clashes_with` is empty.

### Rulings for the build (the lead's)

- **One shared helper, public.** In `ccp/tasklog.py`, `_unfenced` becomes `unfence` and `_section_end` becomes
  `section_end` (a local `unfenced` variable would shadow the name `unfenced`), with every caller in `tasklog.py` and the
  `HEADING_RE` comment renamed with them. No other change to them.
- **Close.** `_task_file_done` searches its heading pattern (as now, `(?=\r?$)` kept) in `tasklog.unfence(text)` and ends
  the section at `tasklog.section_end(<that text>, m.end())`; it slices and writes the raw text as now.
- **The estimator.** `strip_notes`, for each name in `NOTES`, searches its heading in `tasklog.unfence(text)` of the text
  as it stands at that step and cuts from the heading to `tasklog.section_end`, as now.
- **The fence.** `FENCE_RE`'s `[^\n]*` after the opener becomes `(?:(?<=~)[^\n]*|[^`\n]*)`: after a tilde fence any info
  string, after a backtick fence one with no backtick. The comment above it says so. `docrules.FENCE_RE` (the docs check's
  line reader) is not changed.
- **The placeholders.** `_check_placeholders` reads `_unquoted(t["_text"])`.
- **The tests**, in `tests/test_section_readers_fences.py` (new):
  - `test_close_writes_its_note_under_the_real_verification_notes_heading` (`code-01`'s file: one note, after the last
    heading, the fence as written);
  - `test_the_estimators_text_keeps_a_fenced_notes_heading_and_drops_the_real_notes` (`code-02`'s text, and the
    `task_hash` of a file with a fenced notes line equal before and after a note is added under the real heading);
  - `test_a_backtick_fences_info_string_holds_no_backtick` (`code-03`'s two texts, and a three-backtick `py` fence still
    hiding its `## ` line).

## Scope

- **In:** `ccp/tasklog.py` (`FENCE_RE`, `unfence` and `section_end` renamed from `_unfenced` and `_section_end`, their
  callers, `_check_placeholders`), `ccp/lifecycle.py` (`_task_file_done`), `ccp/estimate.py` (`strip_notes`),
  `tests/test_section_readers_fences.py` (new).
- No SPEC change (measured in Context).
- **Out:** `CODE_SPAN_RE`; `docrules.FENCE_RE`; CRLF fences; the ADR and SPEC heading readers.

## dod_checks

- id: `code-01`
  story: As the lead, close writes its merge record under the task's real Verification notes heading, not inside a fenced example.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), at its root.
  steps:
    1. Run `python3 -B -c 'import pathlib,tempfile; from ccp import lifecycle; F="\x60"*3; p=pathlib.Path(tempfile.mkdtemp())/"0001-x.md"; p.write_text(f"---\ntask_id: 0001-x\nstatus: pending\nupdated: 2026-01-01\n---\n\n## Scope\n\n{F}\n## Verification notes\n{F}\n\nScope tail.\n\n## Verification notes\n"); lifecycle._task_file_done(p,"- NOTE","2026-02-02"); t=p.read_text(); print("- NOTE" in t.rsplit("## Verification notes",1)[1], t.count("- NOTE"))'`.
  expect: prints `True 1`.
  dry run (`b09de675`): printed `False 1`.
- id: `code-02`
  story: As the estimator, a task's text keeps a fenced notes line and what follows it, and leaves out only the real notes.
  setup: A checkout of the PR head, in your own worktree, at its root.
  steps:
    1. Run `python3 -B -c 'from ccp import estimate; F="\x60"*3; s=estimate.strip_notes(f"## Scope\n\n{F}\n## Implementation notes\n{F}\n\nScope tail.\n\n## dod_checks\n\n- id: x\n\n## Implementation notes\n\nIMPL\n\n## Verification notes\n\nVER\n"); print("Scope tail." in s, "IMPL" in s, "VER" in s)'`.
  expect: prints `True False False`.
  dry run (`b09de675`): printed `False True False`.
- id: `code-03`
  story: As a task writer, a line starting with a three-backtick code span hides no heading, and a tilde fence still quotes its lines.
  setup: A checkout of the PR head, in your own worktree, at its root.
  steps:
    1. Run `python3 -B -c 'from ccp import tasklog as t; F="\x60"*3; print([t._section(s,"dod_checks") is not None for s in (f"## Scope\n\n{F}x{F} is a span.\n\n## dod_checks\n\nc\n\n## Implementation notes\n\n{F}\nn\n{F}\n", f"## Scope\n\n~~~ a\x60b\n## dod_checks\n~~~\n")])'`.
  expect: prints `[True, False]`.
  dry run (`b09de675`): printed `[False, False]`.
- id: `code-04`
  story: As a plane developer, the placeholder check reads the unquoted text through the one helper, with its tests unchanged.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `git grep -n 'CODE_SPAN_RE.sub(_blank, FENCE_RE.sub' -- ccp`.
    2. Run `git diff origin/main...HEAD -- tests/test_task_placeholders.py`.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_task_placeholders tests.test_signed_sections_fences tests.test_signed_blocks_check`.
  expect: step 1 prints nothing (exit 1); step 2 prints nothing; step 3 exits 0.
  dry run (`b09de675`): step 1 printed 1 line (`ccp/tasklog.py`, in `_check_placeholders`); step 2 printed nothing; step 3 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 36 tests`.
- id: `test-01`
  story: As a plane developer, the new tests hold close, the estimator's text and the fence opener, and they bite.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_section_readers_fences`.
    2. Run `grep -e real_verification_notes_heading -e drops_the_real_notes -e holds_no_backtick -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_section_readers_fences --revert ccp/lifecycle.py --revert ccp/estimate.py`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_section_readers_fences --mutant-file <file>`, the file's mutant putting `FENCE_RE`'s `[^\n]*` after the opener back.
  expect: step 1 exits 0; step 2 lists `test_close_writes_its_note_under_the_real_verification_notes_heading`, `test_the_estimators_text_keeps_a_fenced_notes_heading_and_drops_the_real_notes` and `test_a_backtick_fences_info_string_holds_no_backtick`, each `ok`, then `OK`; step 3 prints both mutants `killed`; step 4 prints the mutant `killed`.
  dry run: n/a — the module is new and `--revert` needs the branch.
- id: `data-01`
  story: As the estimator, no task file in the log reads differently, so no stored task_hash moves.
  setup: A checkout of the PR head, in your own worktree, at its root.
  steps:
    1. Run `python3 -B -c 'import glob; from ccp import tasklog as t; print([f for f in sorted(glob.glob("docs/delivery/tasks/*.md")) if [m.start() for m in t.HEADING_RE.finditer(open(f).read())] != [m.start() for m in t.HEADING_RE.finditer(t.unfence(open(f).read()))]])'`.
  expect: prints `[]`.
  dry run (`b09de675`, with `t.FENCE_RE.sub(t._blank, …)` in place of `t.unfence(…)`, which is new): printed `[]`.

## Implementation notes

- 2026-11-24: built as the lead's rulings give it. `tasklog._unfenced` and `_section_end` are now `unfence` and
  `section_end`, with every caller in `tasklog.py`, the `HEADING_RE` comment and two docstrings renamed. `FENCE_RE`'s
  info string is `(?:(?<=~)[^\n]*|[^`\n]*)`, the comment above it saying so. `_task_file_done` and `strip_notes`
  find their headings in `tasklog.unfence(text)` and end the section at `tasklog.section_end`; both slice the raw
  text. `_check_placeholders` reads `_unquoted(t["_text"])`. Re-measured at `7b8aab9c`: every Context probe gave the
  figure the task states, and `task_hash` before and after the change differs for no file in this log or in the two
  bound products' logs (read-only). Mutants: reverting `lifecycle.py` or `estimate.py`, putting `[^\n]*` back, making
  the tilde branch refuse a backtick, and refusing a backtick fence's info string are each killed by
  `tests.test_section_readers_fences`.

## Verification notes
