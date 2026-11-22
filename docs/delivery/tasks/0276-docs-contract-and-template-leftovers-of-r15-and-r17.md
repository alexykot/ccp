---
task_id: 0276-docs-contract-and-template-leftovers-of-r15-and-r17
title: Close the docs, contract and template follow-ups of R15 and R17 - the triage contract's writer, stale queue rules, call syntax in docstrings, a template line cap check and three shared template sentences, and the reviewer brief passes the PR head to the base worktree
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S19", "S20"]
rule_refs: ["E13", "E25"]
review_point: R24
paths: ["contracts/architecture_review_triage.schema.json", "scripts/queue/README.md", "ccp/backfill.py", "ccp/prompt.py", "ccp/report.py", "ccp/submit.py", "ccp/suite.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "templates/prompts/_common.md", "templates/prompts/_gate.md", "plugin/agents/delivery-reviewer.md", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/ruling.md", "tests/test_cli_reference.py", "tests/test_worker_efficiency.py", "tests/test_prompt_tools.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0276-docs-contract-and-template-leftovers-of-r15-and-r17

## Intent

The docs and templates that the R15 and R17 tasks left behind say what the plane does now. The
architecture-review triage contract names the team lead as its only writer. The queue README keeps no
rule that the plane dropped. No `ccp/` module docstring opens with call syntax. A template line over
600 characters fails an architect check. The "keep your context lean" sentence and the refactor
sentence that the four change rounds share are each written once, in `_common.md`, and the
self-check sentence (the report's list of behaviours and their tests) is written once, in `_gate.md`.
The reviewer brief names the same `ccp wt create --kind base --sha <PR head>` form as SPEC §12.1 and the
verifier brief.

## Context (not checked)

Measured at `934e959` (after 0260 and 0274 merged). The lines that name `a80cee0` were first measured there and re-measured at `934e959` with the same result, except the `implementation_started_at` count, corrected below.

Follow-ups covered (the lead's worker follow-up log): `0253-one-wait-reason-table/review#1`,
`0253-one-wait-reason-table/fix#1`, `0253-one-wait-reason-table/verify#1`,
`0232-orientation-shows-the-open-follow-ups/implement#1`,
`0232-orientation-shows-the-open-follow-ups/review#1`,
`0258-the-plane-writes-the-pre-merge-phases/implement#2`,
`0262-module-docstrings-and-house-rule-checks/review-2#1`,
`0257-one-gate-block-and-one-sentence-per-line/implement#2`,
`0257-one-gate-block-and-one-sentence-per-line/review#2`,
`0257-one-gate-block-and-one-sentence-per-line/review#1`,
`0260-review-tools-and-the-tests-for-new-behaviour-section/review#1`, `…/fix#1` and `…/verify#1` (the
reviewer brief's `--sha`), `0260-review-tools-and-the-tests-for-new-behaviour-section/implement#1`,
`…/review#2` and `…/fix#2` (one self-check sentence).
0257's implement#1 (a note in §13.2 naming `_gate.md`) is not covered here but in 0278: SPEC.md says the SPEC "states rules only", and `git grep -n -i 'non-normative' -- docs/spec`
at `a80cee0` finds no non-normative note form. Naming the file means editing the first item of
§13.2's list, which is rule text.

- **The triage contract.** `git grep -n 'steerer or team lead' -- contracts/architecture_review_triage.schema.json` at `a80cee0`: 1 line (line 5, the top-level `description`).
  §19.8 gives triage to "the task-log owner, the team lead": `git grep -n 'task-log owner, the team lead' -- docs/spec/03-quality.md` at `a80cee0`: 1 line.
  The schema's `steerer` enum value stays as a read alias, as 0253 decided.
- **Orientation (0232), already done.** `git grep -n 'follow-ups are open' -- plugin/hooks/orientation.sh` at `a80cee0`: 1 line (line 8, the header comment).
  0232's own squash `0455523` added it. Nothing is left to change; doc-01 keeps it true.
- **The queue README.** `git grep -n -e implementation_started_at -e 'Seats stay idle' -- scripts/queue/README.md`
  at `a80cee0`: 2 lines, both in `## Rules`. Nothing in `ccp` sets `implementation_started_at` in a
  queue file. `git grep -n '"implementation_started_at"' -- ccp` at `a80cee0` and `934e959` finds 3 lines: `ccp tasks release`
  clears it (`ccp/lifecycle.py`), `ccp/tasklog.py` refuses it in frontmatter, and `ccp/backfill.py` reads it
  from an older task state as a fallback. The observability
  fold derives it from the ledger (`scripts/observability/lib.py`), and `scripts/observability/README.md`'s
  `wall_hours` row already says it does not reset. Seats do not poll for work: the runner works its
  scope and idles (§16).
- **Docstrings (E25).** The first lines of five module docstrings open with a backticked span that
  holds call syntax: a `<placeholder>`, a `[flag]`, a `|` alternation or an upper-case metavariable.
  Measured with `python3 -c "import ast,re,pathlib; pat=re.compile(r'^\s*\x60ccp [^\x60]*(?:[<\[|]|\b[A-Z][A-Z_]+\b)'); [print(p) for p in sorted([*pathlib.Path('ccp').glob('*.py'),*pathlib.Path('ccp/doclang').glob('*.py')]) if pat.match(((ast.get_docstring(ast.parse(p.read_text()),clean=False) or '').splitlines() or [''])[0])]"` at `a80cee0`: 5 files, `ccp/backfill.py`, `ccp/prompt.py`, `ccp/report.py`, `ccp/submit.py` and `ccp/suite.py`. A bare command name such as `` `ccp init` `` is not call syntax.
  `tests/test_cli_reference.py`'s `USAGE_LINE` (`^\s*ccp [a-z]`) misses them because they start with a
  backtick.
- **The line cap (E13).** E13's `check:` line is `pass` only. Running
  `sh -c "test -z \"\$(awk 'length > 600' templates/prompts/*.md)\""` at `a80cee0` exits 0, so every
  template already holds the cap.
- **Two shared sentences (E13).** `git grep -c -i 'keep your context lean' -- templates/prompts` at
  `a80cee0`: one line each in `fix.md`, `implement.md`, `merge.md` and `ruling.md` (three start
  "Beyond that, keep", merge's starts "Keep").
  `git grep -c 'no test expectation changes except where the task names it, and SPEC does not change' -- templates/prompts`
  at `a80cee0`: the same four files. `fix.md`, `merge.md` and `ruling.md` carry the identical
  `{{#refactor}}` sentence, and `implement.md` carries it split over two lines with a third line
  ("If the work turns out …"). The review and verify refactor sentences say something else
  (a BLOCKER; prove the DoD) and stay. `tests/test_worker_efficiency.py`
  (`test_implement_and_fix_keep_context_lean_but_read_citations_in_full`) asserts that the rendered
  implement and fix prompts carry the context sentence, which they still do after the move.
- **The reviewer brief's base worktree (0260 review#1, fix#1, verify#1).** Measured at `934e959`
  (origin/main, after 0260 merged). `git grep -n 'sha <base>' -- plugin/agents/delivery-reviewer.md`: 1 line
  (`:45`), followed by "`<base>` being what `git merge-base origin/<integration> <PR head>` prints". The
  verifier brief passes the head, and so does §15.1:
  `git grep -n 'sha <PR head>' -- plugin/agents/delivery-verifier.md docs/spec/02-delivery.md` at `934e959`: 2 lines (`delivery-verifier.md:91`, `02-delivery.md:908`). §12.1 says the command makes the worktree "detached
  at the merge base of HEAD and `origin/<integration>`" itself (`git grep -n 'detached' -- docs/spec/02-delivery.md`
  at `934e959`: the `--kind base` bullet). Both forms land on one commit; the reviewer's own `git merge-base`
  step is one the command already takes (E13). `tests/test_prompt_tools.py`
  (`"def test_the_reviewer_reads_and_runs_code_at_the_merge_base_in_a_base_worktree"`) asserts the brief holds
  `git merge-base origin/<integration>`, so that test changes.
- **The self-check sentence (0260 implement#1, review#2, fix#2).** Measured at `934e959`. Each change round
  restates the report's list in its own words:
  `git grep -n 'with the test that' -- templates/prompts/fix.md templates/prompts/merge.md templates/prompts/ruling.md` at `934e959`: 3 lines (`fix.md:20`, `merge.md:20` "with the test that covers it", `ruling.md:21`), and
  `git grep -c 'dod_check ids' -- templates/prompts`: 3 files (`_gate.md`, `fix.md`, `ruling.md`, 1 each). `_gate.md` holds
  implement's version inside its `{{#gate_pr}}` block: "Put that list in your report, as its last part asks,
  so the reviewer can check it." and "That map lives in the report only: never put dod_check ids or the map
  in test names or docstrings." `"GATES"` in `ccp/prompt.py` renders `_gate.md` for implement, fix, merge and
  ruling. The report's last part already gives the section's heading and format for all four
  (`report.SECTIONS`, the `tests` entry, which accepts a `none` line with why). `merge.md:11` (list each
  conflict resolved, file by file) is a different instruction and stays. No test pins the three lines:
  `git grep -n -e 'as the implementer did' -e 'test that covers it' -e 'Put that list in your report' -e 'That map lives' -- tests`
  at `934e959`: no match. `git grep -n -i 'self-check' -- docs/spec` at `934e959`: 1 line, §13.5's bullet, which
  names no template wording and stays true.
- **Order and other tasks.** 0274 (R23) changes `plugin/agents/*.md` and the writing-tasks skill
  only, and its Scope leaves the templates out: no clash. 0260 (R19) and 0275 (R23) edit other
  sentences of the same templates (the affected-modules line and the Tests-for-new-behaviour
  section; the stale-Context block). 0260 merged at `934e959` and its follow-ups are taken here.
  0274 (done) edited `plugin/agents/delivery-reviewer.md`, other bullets. That is different logic, so there is no clash, only a possible
  text merge. 0263 adds an example for the triage contract and does not change its `description`.
  0278 changes the body of `ccp/submit.py`'s docstring. This task changes only its first line.
  0266 (R21) rewords `ccp/prompt.py`'s module docstring (the PR host), and 0272 (R23) adds an E27 entry
  to `architect.checks` and E27's `check:` line to `docs/ENGINEERING.md`. Those are text merges with
  this task's docstring first line, E13 entry and E13 `check:` line, not clashes.

### Rulings for the build (the lead's)

- **The contract.** In the top-level `description`, "(spec maintainer, steerer or team lead)" becomes
  "(the team lead)". Nothing else in the file changes.
- **The queue README.** Remove the two `## Rules` bullets that start
  "`implementation_started_at` is set **once**" and "Seats stay idle". Add nothing in their place.
- **Docstrings.** Each of the five first lines keeps the command's bare name in its backticks and drops
  the rest of the call syntax: `` `ccp tasks backfill-review-points` ``, `` `ccp prompt` ``,
  `` `ccp report` ``, `` `ccp tasks submit` ``, `` `ccp suite` ``. The rest of each line stays.
  `tests/test_cli_reference.py` gets a test, `test_no_module_docstring_opens_with_call_syntax`. It
  reads the first docstring line of the modules the existing usage-line test reads, with the pattern
  measured above, and expects no match.
- **The line cap.** `docs/delivery/plane.json` `architect.checks` gets
  `{"id": "E13", "cmd": "test -z \"$(awk 'length > 600' templates/prompts/*.md)\""}`. E13's rule text
  is unchanged. Only its `check:` line in `docs/ENGINEERING.md` changes, to:
  "check: pass, plus command — architect.checks `E13`: `awk 'length > 600' templates/prompts/*.md` prints nothing, a proxy for one sentence per line, not a rule of its own; the
  architect compares plugin/agents and templates/prompts with the § rules they cite, ccp/report.py's
  sections, and looks for inline sample records and sentences repeated across templates".
- **The shared sentences.** `templates/prompts/_common.md` gets a `{{#change_round}}…{{/change_round}}`
  block of two `- ` bullets, placed right after the "Stage by path" bullet:
  `- Keep your context lean: send a listing, search or log that may run past about 200 lines to a scratch file outside the repo and read the slices you need, and issue independent reads as parallel tool calls in one turn.` and
  "{{#refactor}}- This is a `kind: refactor` task (SPEC §20.4): behaviour is unchanged, no test
  expectation changes except where the task names it, and SPEC does not change.\n{{/refactor}}".
  `ccp/prompt.py` sets `"change_round": phase in runs.CHANGE_PHASES` in the values. The lean sentence
  and the `{{#refactor}}` block are removed from `fix.md`, `merge.md` and `ruling.md`. `implement.md`
  loses the lean sentence, and its `{{#refactor}}` block keeps only "The suite and the product's
  scenario checks pass too." and "If the work turns out to need a behaviour or stored-data change,
  stop and report it.". `tests/test_worker_efficiency.py` gets a test: for a refactor task, each of the
  implement, fix, merge and ruling prompts renders "Keep your context lean" once and the refactor
  sentence once, and the review and verify prompts render neither.

- **The reviewer brief.** In `plugin/agents/delivery-reviewer.md`, the bullet "Line numbers the task file
  cites may be stale" keeps its first two sentences. Its third becomes: "To read or run code there, use
  `ccp wt create --kind base --task <task_id> --sha <PR head> -- <command>`, which takes the merge base of
  the head and `origin/<integration>` itself (SPEC §12.1)." The "Never use a hand-made checkout, …" sentence
  stays. `tests/test_prompt_tools.py`'s
  `test_the_reviewer_reads_and_runs_code_at_the_merge_base_in_a_base_worktree` asserts
  `--sha <PR head> -- <command>` in the brief and `git merge-base` not in it.
- **The self-check sentence.** In `templates/prompts/_gate.md`:
  - The `{{#gate_pr}}` block loses the two sentences "Put that list in your report, …" and "That map lives
    in the report only: …".
  - Its "First, check your tests against your diff" line drops the clause ", with the test that fails
    without it" and ends "… list each branch, field, refusal or behaviour the diff adds or changes, and write
    the test for any that has none."
  - The block ends with `{{/gate_pr}}` at the end of the "To show a test fails without your change, …" line.
    The next line, which every phase rendering `_gate.md` renders, is:
    `List each branch, field, refusal or behaviour this round's commits add or change, with the test that fails without it, in your report, as its last part asks, so the reviewer can check it; the list lives in the report only, never as dod_check ids or a map in test names or docstrings.`
    The line after it starts "Fail fast first", which no longer carries a `{{/gate_pr}}` tag at its start.
  The "List each … in your report …" line of `fix.md`, `merge.md` and `ruling.md` (quoted in Context) is
  removed from each. `tests/test_worker_efficiency.py`'s new test (below) also checks
  that the implement, fix, merge and ruling prompts each render `dod_check ids` once.

## Scope

- **In:** `contracts/architecture_review_triage.schema.json` (the description),
  `scripts/queue/README.md` (two Rules bullets), `ccp/backfill.py`, `ccp/prompt.py`, `ccp/report.py`,
  `ccp/submit.py`, `ccp/suite.py` (the first docstring line; `ccp/prompt.py` also the `change_round`
  value), `docs/delivery/plane.json` (`architect.checks`), `docs/ENGINEERING.md` (E13's `check:`
  line), `templates/prompts/_common.md`, `templates/prompts/implement.md`, `templates/prompts/fix.md`,
  `templates/prompts/merge.md`, `templates/prompts/ruling.md` (also the self-check lines),
  `templates/prompts/_gate.md` (the self-check sentence), `plugin/agents/delivery-reviewer.md` (the base
  worktree's `--sha`), `tests/test_cli_reference.py`, `tests/test_worker_efficiency.py`,
  `tests/test_prompt_tools.py` (the reviewer-brief test).
- No SPEC change. Each concept the task touches, searched in `docs/spec` at `a80cee0`:
  `git grep -n -i 'context lean' -- docs/spec` finds nothing (§13.5 describes reading in slices with
  no template wording). `git grep -n '_common.md' -- docs/spec` finds 1 line, §13.2 item 1, and it
  stays true. `git grep -n -i 'usage table' -- docs/spec` finds nothing. `git grep -n 'implementation_started_at' -- docs/spec`
  finds 3 lines, one each in `02-delivery.md`, `03-quality.md` and `04-observability.md`, none about the README's rule.
- **Out:** the `steerer` enum alias; `plugin/hooks/orientation.sh` (already right); the review and
  verify refactor sentences; §13.2's text (0278); `plugin/agents/*.md` other than the reviewer brief's one
  sentence; `merge.md`'s conflict-list line.

## dod_checks

- id: `doc-01`
  story: As a plane developer, the triage contract and the queue README name only what the plane does, and orientation's header names the follow-ups line.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'steerer or team lead' -- contracts/architecture_review_triage.schema.json`.
    2. Run `git grep -n -e implementation_started_at -e 'Seats stay idle' -- scripts/queue/README.md`.
    3. Run `git grep -n 'follow-ups are open' -- plugin/hooks/orientation.sh` (a guard: it already passes at the base, and keeps 0232's follow-ups closed).
  expect: steps 1 and 2 print nothing (exit 1); step 3 prints exactly one line, `plugin/hooks/orientation.sh:8`.
  dry run (`a80cee0`): step 1 printed 1 line (`:5`); step 2 printed 2 lines (`:54`, `:56`); step 3 printed `plugin/hooks/orientation.sh:8`.
- id: `code-01`
  story: As a plane developer, no ccp module docstring opens with call syntax, and a test holds it.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_cli_reference 2>&1 | grep -e 'opens_with_call_syntax' -e '^OK' -e FAILED`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_cli_reference --mutant-file <file>`, the file's mutant putting `` `ccp suite run|wait|list|affected` `` back at the start of `ccp/suite.py`'s first docstring line.
  expect: step 1 prints `test_no_module_docstring_opens_with_call_syntax … ok` and `OK`; step 2 prints the mutant `killed`.
  dry run: n/a — the test is new.
- id: `cmd-01`
  story: As the architect, a template line over 600 characters fails a command check.
  setup: A checkout of the PR head.
  steps (one shell, from the checkout's root):
    1. Run `cmd=$(python3 -c "import json; print(next(c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id'] == 'E13'))"); echo "$cmd"`.
    2. Run `sh -c "$cmd"; echo $?`.
    3. Run `d=$(mktemp -d); mkdir -p $d/templates/prompts; python3 -c "print('x'*601)" > $d/templates/prompts/x.md; (cd $d && sh -c "$cmd"); echo $?`.
    4. Run `git grep -n 'architect.checks .E13.' -- docs/ENGINEERING.md`.
  expect: step 1 prints a command holding `awk 'length > 600' templates/prompts/*.md`; step 2 prints `0`; step 3 prints `1`; step 4 prints one line, in E13's `check:` line.
  dry run (`a80cee0`): step 1 failed (`StopIteration`: no E13 entry); with `cmd` set by hand to the ruled command, step 2 printed `0` and step 3 printed `1`; step 4 printed nothing.
- id: `doc-02`
  story: As a plane developer, the context and refactor sentences of the change rounds are written once.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -c -i 'keep your context lean' -- templates/prompts`.
    2. Run `git grep -c 'no test expectation changes except where the task names it, and SPEC does not change' -- templates/prompts`.
    3. Run `git grep -c 'dod_check ids' -- templates/prompts`, then `git grep -n 'with the test that' -- templates/prompts/fix.md templates/prompts/merge.md templates/prompts/ruling.md`.
  expect: steps 1 and 2 each print exactly one line, `templates/prompts/_common.md:1`; step 3's first command prints exactly one line, `templates/prompts/_gate.md:1`, and its second prints nothing (exit 1).
  dry run (`a80cee0`): steps 1 and 2 each printed 4 lines (`fix.md`, `implement.md`, `merge.md`, `ruling.md`, 1 each). Step 3 (`934e959`): the first command printed 3 lines (`_gate.md`, `fix.md`, `ruling.md`, 1 each), the second 3 lines (`fix.md:20`, `merge.md:20`, `ruling.md:21`).
- id: `cmd-02`
  story: As a worker in a change round, my prompt still carries both sentences, once; a reviewer's and a verifier's carry neither.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_worker_efficiency 2>&1 | tail -3`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_worker_efficiency --mutant 'ccp/prompt.py:"change_round": phase in runs.CHANGE_PHASES=>"change_round": phase in runs.PHASES'`.
  expect: step 1 ends `OK` and the run lists, `ok`, a test where a refactor task's implement, fix, merge and ruling prompts each render `Keep your context lean` once, `no test expectation changes except where the task names it` once and `dod_check ids` once, and its review and verify prompts render none of the three; step 2 prints the mutant `killed`.
  dry run (`a80cee0`): step 1 ended `OK` (the new test n/a — it is new).

- id: `doc-03`
  story: As a reviewer, my brief runs code at the merge base the way the verifier's brief and SPEC §12.1 do, passing the PR head.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for step 3.
  steps:
    1. Run `git grep -n -e 'sha <base>' -e 'git merge-base' -e 'sha <PR head>' -- plugin/agents/delivery-reviewer.md`.
    2. Run `python3 -B -m unittest -v tests.test_prompt_tools 2>&1 | grep -e merge_base_in_a_base_worktree -e '^OK' -e FAILED`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_prompt_tools.PromptsNameTheTools.test_the_reviewer_reads_and_runs_code_at_the_merge_base_in_a_base_worktree --revert plugin/agents/delivery-reviewer.md`.
  expect: step 1 prints exactly one line, the one holding `--sha <PR head> -- <command>`; step 2 prints the test `… ok` and `OK`; step 3 prints the mutant `killed`.
  dry run (`934e959`): step 1 printed 2 lines (`:45` `sha <base>`, `:46` `git merge-base`); steps 2 and 3 n/a — the test's new assertions are the build's.

## Implementation notes

- Every measured premise in Context re-ran at `b5f2273` with the figures the task states.
- `_gate.md`: the `{{#gate_pr}}` block now opens at the end of the line before it (after "…{{/gate_merge}}.")
  instead of at the start of the "For each `adr_refs`" line, so that closing it at the end of the "To show a test
  fails…" line, as ruled, leaves no blank line in the fix, merge and ruling prompts. The rendered implement
  prompt is unchanged apart from the ruled sentences.
- `fix.md`, `merge.md` and `ruling.md` keep the blank line before `{{gate}}` that the removed `{{#refactor}}`
  block used to leave, so their rendered layout is as before.
- `tests/test_worker_efficiency.py`: besides the new `RefactorRounds` test (through `ccp prompt`, so the
  `change_round` value in `ccp/prompt.py` is what it checks), two existing tests pinned the sentences the ruling
  moves or rewords: `test_implement_and_fix_keep_context_lean_but_read_citations_in_full` rendered only the phase
  template and now renders it with `_common.md` (helper `with_common`), and
  `test_the_implementer_lists_each_new_behaviour_and_the_reviewer_checks_it` asserts the ruled wording (the
  shortened "First, check your tests" clause, and the shared report-only sentence in every change round).
- `tests/test_cli_reference.py`: the module glob the usage-line test read is now `module_docstrings()`, which
  the new call-syntax test reads too.

## Verification notes
