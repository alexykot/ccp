---
task_id: 0276-docs-contract-and-template-leftovers-of-r15-and-r17
title: Close the docs, contract and template follow-ups of R15 and R17 - the triage contract's writer, stale queue rules, call syntax in docstrings, a template line cap check and two shared template sentences
status: pending
kind: feature
depends_on: []
spec_refs: ["S13", "S19", "S20"]
rule_refs: ["E13", "E25"]
review_point: R24
paths: ["contracts/architecture_review_triage.schema.json", "scripts/queue/README.md", "ccp/backfill.py", "ccp/prompt.py", "ccp/report.py", "ccp/submit.py", "ccp/suite.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "templates/prompts/_common.md", "templates/prompts/implement.md", "templates/prompts/fix.md", "templates/prompts/merge.md", "templates/prompts/ruling.md", "tests/test_cli_reference.py", "tests/test_worker_efficiency.py"]
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
sentence that the four change rounds share are each written once, in `_common.md`.

## Context (not checked)

Measured at `a80cee0` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log): `0253-one-wait-reason-table/review#1`,
`0253-one-wait-reason-table/fix#1`, `0253-one-wait-reason-table/verify#1`,
`0232-orientation-shows-the-open-follow-ups/implement#1`,
`0232-orientation-shows-the-open-follow-ups/review#1`,
`0258-the-plane-writes-the-pre-merge-phases/implement#2`,
`0262-module-docstrings-and-house-rule-checks/review-2#1`,
`0257-one-gate-block-and-one-sentence-per-line/implement#2`,
`0257-one-gate-block-and-one-sentence-per-line/review#2`,
`0257-one-gate-block-and-one-sentence-per-line/review#1`.
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
  queue file. `git grep -n '"implementation_started_at"' -- ccp` at `a80cee0` finds 2 lines: `ccp tasks release`
  clears it (`ccp/lifecycle.py`) and `ccp/tasklog.py` refuses it in frontmatter. The observability
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
- **Order and other tasks.** 0274 (R23) changes `plugin/agents/*.md` and the writing-tasks skill
  only, and its Scope leaves the templates out: no clash. 0260 (R19) and 0275 (R23) edit other
  sentences of the same templates (the affected-modules line and the Tests-for-new-behaviour
  section; the stale-Context block). That is different logic, so there is no clash, only a possible
  text merge. 0263 adds an example for the triage contract and does not change its `description`.
  0278 changes the body of `ccp/submit.py`'s docstring. This task changes only its first line.

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
  `{"id": "E13", "cmd": "test -z \"$(awk 'length > 600' templates/prompts/*.md)\""}`. E13's `check:`
  line in `docs/ENGINEERING.md` becomes:
  "check: pass, plus command — architect.checks `E13`: `awk 'length > 600' templates/prompts/*.md` prints nothing; the
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

## Scope

- **In:** `contracts/architecture_review_triage.schema.json` (the description),
  `scripts/queue/README.md` (two Rules bullets), `ccp/backfill.py`, `ccp/prompt.py`, `ccp/report.py`,
  `ccp/submit.py`, `ccp/suite.py` (the first docstring line; `ccp/prompt.py` also the `change_round`
  value), `docs/delivery/plane.json` (`architect.checks`), `docs/ENGINEERING.md` (E13's `check:`
  line), `templates/prompts/_common.md`, `templates/prompts/implement.md`, `templates/prompts/fix.md`,
  `templates/prompts/merge.md`, `templates/prompts/ruling.md`, `tests/test_cli_reference.py`,
  `tests/test_worker_efficiency.py`.
- No SPEC change. Each concept the task touches, searched in `docs/spec` at `a80cee0`:
  `git grep -n -i 'context lean' -- docs/spec` finds nothing (§13.5 describes reading in slices with
  no template wording). `git grep -n '_common.md' -- docs/spec` finds 1 line, §13.2 item 1, and it
  stays true. `git grep -n -i 'usage table' -- docs/spec` finds nothing. `git grep -n 'implementation_started_at' -- docs/spec`
  finds 3 lines, one each in `02-delivery.md`, `03-quality.md` and `04-observability.md`, none about the README's rule.
- **Out:** the `steerer` enum alias; `plugin/hooks/orientation.sh` (already right); the review and
  verify refactor sentences; §13.2's text (0278); `plugin/agents/*.md` (0274).

## dod_checks

- id: `doc-01`
  story: As a plane developer, the triage contract and the queue README name only what the plane does, and orientation's header names the follow-ups line.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'steerer or team lead' -- contracts/architecture_review_triage.schema.json`.
    2. Run `git grep -n -e implementation_started_at -e 'Seats stay idle' -- scripts/queue/README.md`.
    3. Run `git grep -n 'follow-ups are open' -- plugin/hooks/orientation.sh`.
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
  steps:
    1. Run `python3 -c "import json; print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id'] == 'E13'])"`.
    2. Run that command from the checkout's root with `sh -c '<the command>'; echo $?`.
    3. Run `d=$(mktemp -d); mkdir -p $d/templates/prompts; python3 -c "print('x'*601)" > $d/templates/prompts/x.md; (cd $d && sh -c '<the command>'); echo $?`.
    4. Run `git grep -n 'architect.checks .E13.' -- docs/ENGINEERING.md`.
  expect: step 1 prints a one-item list holding `awk 'length > 600' templates/prompts/*.md`; step 2 prints `0`; step 3 prints `1`; step 4 prints one line, in E13's `check:` line.
  dry run (`a80cee0`): step 1 printed `[]`; the command run by hand printed `0` in the checkout and `1` in the temp dir; step 4 printed nothing.
- id: `doc-02`
  story: As a plane developer, the context and refactor sentences of the change rounds are written once.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -c -i 'keep your context lean' -- templates/prompts`.
    2. Run `git grep -c 'no test expectation changes except where the task names it, and SPEC does not change' -- templates/prompts`.
  expect: each step prints exactly one line, `templates/prompts/_common.md:1`.
  dry run (`a80cee0`): each step printed 4 lines (`fix.md`, `implement.md`, `merge.md`, `ruling.md`, 1 each).
- id: `cmd-02`
  story: As a worker in a change round, my prompt still carries both sentences, once; a reviewer's and a verifier's carry neither.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_worker_efficiency 2>&1 | tail -3`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_worker_efficiency --mutant 'ccp/prompt.py:"change_round": phase in runs.CHANGE_PHASES=>"change_round": phase in runs.PHASES'`.
  expect: step 1 ends `OK` and the run lists, `ok`, a test where a refactor task's implement, fix, merge and ruling prompts each render `Keep your context lean` once and `no test expectation changes except where the task names it` once, and its review and verify prompts render neither; step 2 prints the mutant `killed`.
  dry run (`a80cee0`): step 1 ended `OK` (the new test n/a — it is new).

## Implementation notes

## Verification notes
