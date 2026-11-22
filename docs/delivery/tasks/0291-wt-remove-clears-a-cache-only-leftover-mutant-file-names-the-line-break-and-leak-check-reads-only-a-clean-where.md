---
task_id: 0291-wt-remove-clears-a-cache-only-leftover-mutant-file-names-the-line-break-and-leak-check-reads-only-a-clean-where
title: ccp wt remove clears a leftover directory that holds only the language's caches, a mutant file's zero-match refusal names its trailing line break, and leak-check reads ccp where only when it exits 0
status: pending
kind: feature
depends_on: []
spec_refs: ["S12", "S20"]
rule_refs: ["E3", "E18"]
review_point: R25
paths: ["ccp/wt.py", "ccp/mutate.py", "scripts/leak-check.sh", "tests/test_wt_leftover.py", "tests/test_mutant_file_line_break.py", "tests/test_leak_check.py"]
clashes_with: ["0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0291-wt-remove-clears-a-cache-only-leftover-mutant-file-names-the-line-break-and-leak-check-reads-only-a-clean-where

## Intent

Three tool frictions workers met are gone. `ccp wt remove` no longer leaves an empty worktree
directory behind when a bytecode cache appears in it while git removes it. A `--mutant-file` whose old
text ends mid-line, and so matches nothing because the file's format takes the line break before
`=== new` as part of it, is refused with a message that says so. `scripts/leak-check.sh` reads
`ccp where` only when it exits 0, as its header says.

## Context (not checked)

Measured at `329ff75` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log):
`0280-the-base-run-reads-the-denylist-the-head-run-reads-and-tests-make-no-base-run/review#1`, `…/fix#1` and
`…/verify#1` (leak-check's `ccp where` step), `…` there being
`0280-the-base-run-reads-the-denylist-the-head-run-reads-and-tests-make-no-base-run`. And two frictions from the
workers' health notes (`<queue>/health/notes.jsonl`, data only the queue holds), named by the lead:

- **The leftover worktree directory.** A reviewer's report (0276's review, queue data): `ccp wt remove rev-0276`
  dropped the git worktree and its record, then failed with "Directory not empty", because a
  `ccp/__pycache__/report.cpython-315.pyc` appeared during the removal (the reviewer had just run `ccp report`
  from inside it). The directory, empty but for that cache, stayed. In `"def remove"` (`ccp/wt.py`) the removal
  is `"def _rm_tree"`, which for a git worktree runs `git worktree remove --force` and returns git's failure, which
  `remove` turns into the warning `worktree <path>: <text>`. `"def remove_task"`'s fallback removals call
  `_rm_tree` too. The language pack names its cache directories already: `ccp/doclang/python.py`'s
  `file_skip_dirs=("__pycache__",)` (`git grep -n 'file_skip_dirs' -- ccp` at `329ff75`: 3 lines), and E18 keeps a
  language's facts in its pack, so `wt` names no cache directory itself.
- **The mutant file's zero-match refusal.** Five worker notes from 0234, 0237, 0261, 0272 and 0276 (queue data) describe the same refusal: a `--mutant-file` whose old text was part of a line was refused "the old text is in <file> 0 times", read as a wrong path or text. The format takes each text "exactly what lies between its marker line and the next" (§20.6), so the old text ends with the line break before `=== new`. Probe at `329ff75`: `mutate.parse_file` on a file `calc.py` holding `x = 1\ny = 2\n`, with a mutant file whose old text is the line `x = ` (then `=== new`), raised "mutant file 'm.txt': the old text is in calc.py 0 times; a mutant names one place" (`python3 -B -c "from pathlib import Path; from ccp import mutate; mutate.parse_file(Path('<dir>'), 'm.txt', Path('<dir>'))"`). `"def _once"` builds that text for `--mutant`, `--mutant-file` and `--together` alike.
- **Leak-check's step 3.** `scripts/leak-check.sh`'s header says "A missing ccp, a non-zero exit or output that does not parse falls through quietly", but its code runs `(ccp --root "$PWD" where 2>/dev/null || true) | python3 -c …`, so it parses what a failing `ccp` printed. Probe at `329ff75`, in a scratch repo with a stub `ccp` on PATH that prints a JSON `binding` naming a directory with a denylist and then exits 1: the script printed "leak-check: denylist found (bindings dir)" and failed on the planted word (exit 1). `ccp where` always exits 0 today, so no real run differs yet; `ccp/baseline.py`'s `head_bindings_dir` (0280) already falls back on a non-zero exit.
- **No SPEC change.** `git grep -n 'wt remove' -- docs/spec` at `329ff75`: 3 lines, none on a failed removal (§12.1: "`ccp wt remove NAME` removes one"). `git grep -n '0 times' -- docs/spec` at `329ff75`: 0 lines; §20.6 states the mutant file's format, which does not change. `git grep -n 'leak-check' -- docs/spec` at `329ff75`: 0 lines.
- **Other tasks on these files.** 0271 (R23) and 0285 (R25) change `ccp/mutate.py`'s interface and defaults, not
  `_once`'s message; 0290 changes `tests/test_leak_check.py`'s plane-root line. No clash on the logic; the
  shared files are recorded as clashes so they do not run together.

### Rulings for the build (the lead's)

- **The leftover.** `_rm_tree` takes the language pack's cache directories (its callers pass
  `doclang.get(config.language_name(cfg)).file_skip_dirs`). When `git worktree remove --force` fails, it prunes
  git's worktree list, and when `git worktree list --porcelain` then names the path no more, the path still
  exists, and every file under it lies inside a directory with one of those names (an empty tree qualifies),
  it deletes the path and reports success. Otherwise it returns git's failure as now. A path git still lists,
  or one holding any other file, is never deleted.
- **The message.** For a `--mutant-file` substitution whose old text is in the file 0 times, ends with a line break, and is found without it, the refusal reads: `{label}: the old text is in {rel} 0 times: it ends with the line break before === new, and without it it is in {rel} {n} times; end the old text at a line end`. Every other count keeps today's message. `--mutant` refusals are unchanged.
- **Leak-check.** Step 3 runs `ccp --root "$PWD" where` on its own and pipes its output to the parser only when it
  exits 0; a non-zero exit leaves `dir` empty. The header is unchanged.
- **Tests.** `tests/test_wt_leftover.py` (new): a recorded worktree that git no longer lists, its directory
  holding only `pkg/__pycache__/m.pyc`, is gone after `ccp wt remove` with no warning; the same with a
  `notes.txt` beside it stays, with the `worktree <path>:` warning. `tests/test_mutant_file_line_break.py` (new):
  the probe above gets the new message; a whole-line old text that matches nothing keeps the old one.
  `tests/test_leak_check.py`: the stub that prints a binding and exits 1 leaves "nothing checked", exit 0.

## Scope

- **In:** `ccp/wt.py` (`_rm_tree` and its callers), `ccp/mutate.py` (the zero-match message for a mutant file),
  `scripts/leak-check.sh` (step 3), `tests/test_wt_leftover.py` (new), `tests/test_mutant_file_line_break.py` (new),
  `tests/test_leak_check.py`.
- No SPEC change (measured in Context).
- **Out:** the mutant file's format; `ccp where`'s exit codes; `head_bindings_dir`; `remove_unrecorded`.

## dod_checks

- id: `code-01`
  story: As a reviewer who ran ccp inside my worktree, `ccp wt remove` leaves no directory behind when only a bytecode cache was left in it.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_wt_leftover 2>&1 | tail -1`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_wt_leftover --mutant-file <file>`, the file's mutant making `_rm_tree` return git's failure without the leftover check.
    3. Run the same with a second mutant file, whose mutant makes the leftover check accept any file.
  expect: step 1 prints `OK`, the module holding the two tests of the ruling; steps 2 and 3 each print the mutant `killed`.
  dry run: n/a — the module is new.
- id: `code-02`
  story: As a worker writing a mutant file, a mutant that ends mid-line is refused with a message naming the line break.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutant_file_line_break 2>&1 | tail -1`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutant_file_line_break --mutant-file <file>`, the file's mutant removing the line-break clause from the refusal.
  expect: step 1 prints `OK`, the module holding a test whose refusal contains `ends with the line break before` and `1 times`, and one whose whole-line old text that matches nothing is refused with `0 times; a mutant names one place`; step 2 prints the mutant `killed`.
  dry run (`329ff75`): the probe in Context printed the old message, with no line-break clause; the module is new.
- id: `cmd-01`
  story: As the leak check, a `ccp where` that fails is not read, as my header says.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_leak_check 2>&1 | tail -1`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_leak_check --mutant-file <file>`, the file's mutant putting `|| true` back into step 3's `ccp where` call so its output is parsed whatever the exit.
  expect: step 1 prints `OK`, the module holding a test where a stub `ccp` that prints a binding beside a denylist and exits 1 leaves `nothing checked`, exit 0; step 2 prints the mutant `killed`.
  dry run (`329ff75`): step 1 printed `OK` (the new test n/a — it is new); the scratch probe in Context found the denylist and exited 1.

## Implementation notes

## Verification notes
