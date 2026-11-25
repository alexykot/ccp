---
task_id: 0333-every-docs-cli-part-takes-one-table-shape-e25-reads-every-line-and-the-cli-reference-tests-run-on-their-own-docs
title: Every docs/cli part lists its commands in one table shape, Command | Who | SPEC, with no fenced block, no exit-code prose and no command listed twice, and E25's check reads every line; the command-reference checker tests build their own docs; §24.6 and §27.1 name the knobs the code reads
status: pending
kind: feature
depends_on: []
spec_refs: ["S24", "S27"]
rule_refs: ["E25", "E4"]
review_refs: ["ar-20261124T234643Z-3c95#F04", "ar-20261124T234643Z-3c95#F06"]
review_point: R35
paths: ["docs/cli/01-model.md", "docs/cli/02-delivery.md", "docs/cli/03-quality.md", "docs/cli/04-observability.md", "docs/cli/05-operations.md", "tests/test_cli_reference.py", "docs/spec/04-observability.md", "docs/ENGINEERING.md", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0332-one-fence-aware-markdown-section-helper-and-ccp-spec-show-prints-a-cited-section"]
sign_off: brief
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0333-every-docs-cli-part-takes-one-table-shape-e25-reads-every-line-and-the-cli-reference-tests-run-on-their-own-docs

## Intent

A reader of the command reference finds every command the same way: each docs/cli part is one or more tables of
`Command | Who | SPEC`, a command is listed once, and no line restates the SPEC's exit codes. House rule E25 says so,
and its check reads every line of docs/cli, in any case, so a fenced block, a long prose line or an exit code outside a
row is found as a row's is. The command-reference checker's own tests take a small docs directory and parser they
build, so rewording a real row breaks only the test that holds the real docs to the parser. And the SPEC names the
knob behind the usage advice's default window and the small-task line, as the code reads them.

## Context (not checked)

Findings F04 and F06 of architect pass `ar-20261124T234643Z-3c95` (`docs/delivery/reviews/ar-20261124T234643Z-3c95.md`),
and the follow-ups of 0330 that the lead passed to this pass: the docs/cli clauses no § states, §24.6 and §27.1
disagreeing on the usage advice's window, the `health.small_task_lines` knob no § names, and E25's check missing
exit-code prose outside rows and the rows that do not start with `` `ccp``. The architect proposed E25's amendment; this
triage accepted it and this task lands it, text and check together. This task changes 0330's ruling that each file
keeps its existing columns.

Measured at `1a575497`:

- The triage commit after `1a575497` (`docs/ENGINEERING.md`: E5, E19 and E26 rewrapped, words unchanged;
  `docs/delivery/plane.json`: `E4`'s alias grep at `^\s*`) leaves every figure below as measured.
- **F04.** `git grep -hP '^\|\s*Command\s*\|' -- docs/cli | grep -cvxF '| Command | Who | SPEC |'`: 3 headers
  (`01-model`: Command | What it does | SPEC; `03-quality`: … | Cost | SPEC; `04-observability`: Command | What it
  does), and `05-operations` has no table. `git grep -nP '^\s*(\x60{3}|~{3})' -- docs/cli | wc -l`: 8 fence lines (4
  blocks, all in `05-operations`). `git grep -niP '\bexits? (code )?[0-9]|\bexit code' -- docs/cli | wc -l`: 2 (the
  Pull requests preface in `02-delivery`, the closing paragraph of `03-quality`). `git grep -n 'ccp auth check' -- docs/cli | wc -l`:
  2 (`02-delivery`, `05-operations`). `CCP_DEV=1 ./bin/ccp docs check --only E25`: clean, its cmd reading only
  `` | `ccp `` rows and a lowercase `exit`.
- **F06.** `grep -c 'copy_with(' tests/test_cli_reference.py`: 8 (the helper and 7 tests that copy the real docs and
  replace a real row's text).
- **The § texts.** `"def advice_start"` (`ccp/usage.py`) reads `--since`, else `usage.advice.window_hours` back, else
  every request; §24.6 says "every request, or those from `--since`", and §27.1 says the code's reading.
  `"def small_tasks"` (`ccp/health.py`) reads `health.small_task_lines` (`HEALTH_DEFAULTS`, `ccp/config.py`); §27.1
  says "strictly fewer than 100 lines". `git grep -n 'small_task_lines\|window_hours' -- docs/spec`: only §27.1's
  `window_hours`.
- **Ruled.**
  - Every docs/cli part lists its commands in tables headed `| Command | Who | SPEC |`, as `02-delivery` does: Who is
    the seat or seats, and the SPEC cell is the § with at most one clause of purpose in parentheses. The What it does
    column's seat goes to Who and its purpose to the SPEC cell; `03-quality`'s Cost column goes; `04-observability`
    gains the SPEC cell from the § its heading or row names. `05-operations`' four fenced blocks become rows under
    their headings, the `scripts/` lines included.
  - `ccp auth check` is listed once, in `05-operations` (`| runner, lead | §30.1, §10.5 |`); its `02-delivery` row goes.
  - The Pull requests preface's exit-code sentence and `03-quality`'s closing exit-code paragraph go; §10.6 holds the
    contract.
  - The clauses 0330 kept because no § states them (what `--starter-rules`, `tasks next --json`, `tasks follow-up`,
    `otel status`, `pr open`, `pr view --json` and `tasks estimate show` take or print, `ACTOR=design-seat` on the
    lead's commands) stay as each row's one clause of purpose or call syntax; this task adds no § for them.
  - `tests/test_cli_reference.py`: `"def problems_of"` takes the parser to read as an argument, defaulting to `ccp`'s.
    The seven checker tests (the flag, command and span cases) build a small `argparse` parser and a docs directory
    of a few rows in a temporary directory, and assert the same problems; `copy_with` goes.
    `test_the_docs_hold_the_parsers_commands_and_flags_and_no_others` stays the one test that reads the real docs/cli.
  - **E25** (`docs/ENGINEERING.md`): its four lines are replaced by these five (the triage freed the line):

    > - **E25** The parser is the one source of the command surface. Call syntax is written by hand in one place (docs/cli),
    >   in one table shape (Command | Who | SPEC), held to the parser by a test: a row gives the syntax, who calls it, at most
    >   one clause of purpose and the §; no line of docs/cli states the SPEC's rules or exit codes; no module docstring in
    >   ccp/ carries a usage table.
    >   check: command — architect.checks `E25` (no docs/cli line over 300 bytes, no fenced block, no exit code in any case); plus the gate — tests.test_cli_reference (E1)

    and `docs/delivery/plane.json` `architect.checks` `E25`'s cmd becomes:

    ```
    ! awk 'length > 300 {print FILENAME ": " substr($0, 1, 60); n++} END {exit n == 0}' docs/cli/*.md && ! git grep -nP '^\s*(\x60{3}|~{3})' -- docs/cli && ! git grep -niP '\bexits? (code )?[0-9]|\bexit code' -- docs/cli
    ```
- No other test expectation changes.

## Scope

- **In:** `docs/cli/01-model.md`, `docs/cli/02-delivery.md`, `docs/cli/03-quality.md`, `docs/cli/04-observability.md`,
  `docs/cli/05-operations.md`; `tests/test_cli_reference.py`; `docs/ENGINEERING.md` (E25, the text above);
  `docs/delivery/plane.json` (`architect.checks` `E25`); the SPEC, signed:

  CURRENT (`docs/spec/04-observability.md` at `1a575497`), §24.6, the first paragraph's last sentence:
  > The advice reads every request, or those from `--since` when given, and each line names its start.

  PROPOSED:
  > The advice reads the requests from `--since` when given, else those of the last `usage.advice.window_hours` hours (every request when that is 0), and each line names its start.

  CURRENT (`docs/spec/04-observability.md` at `1a575497`), §27.1, the Small tasks bullet:
  > - **Small tasks:** the share of the tasks merged in the window whose diff (lines added plus deleted, summed over all of a task's merges in the window) is strictly fewer than 100 lines, with the count and the line, so the task-log owner sees follow-ups drifting into one task each (bundle them by area, the writing-tasks skill); `small_tasks` in `--json`.

  PROPOSED:
  > - **Small tasks:** the share of the tasks merged in the window whose diff (lines added plus deleted, summed over all of a task's merges in the window) is strictly fewer than `health.small_task_lines` lines, with the count and the line, so the task-log owner sees follow-ups drifting into one task each (bundle them by area, the writing-tasks skill); `small_tasks` in `--json`.

  Retired: "every request, or those from `--since` when given" (§24.6, false when `window_hours` is set) and "100"
  (§27.1, a default's value, which lives in code under E10).
- **Out:** `docs/cli.md`; the commands' behaviour; a § for the clauses named above; the parser.

## dod_checks

- id: `doc-01`
  story: As a reader of the command reference, every part lists its commands in the same table shape, with no fenced block.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -hP '^\|\s*Command\s*\|' -- docs/cli | grep -cvxF '| Command | Who | SPEC |'`.
    2. Run `git grep -nP '^\s*(\x60{3}|~{3})' -- docs/cli`.
  expect: step 1 prints `0`; step 2 prints nothing (exit 1).
  dry run (`1a575497`): step 1 printed `3`; step 2 printed 8 lines.
- id: `doc-02`
  story: As a plane developer, no docs/cli line restates an exit code in any case, and E25's check reads every line.
  setup: A checkout of the PR head (any seat), with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `git grep -niP '\bexits? (code )?[0-9]|\bexit code' -- docs/cli`.
    2. Run `python3 -B -c 'import json; c = [x["cmd"] for x in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if x["id"] == "E25"][0]; print(c.count("-niP"), c.count("/^"))'`.
    3. Run `CCP_DEV=1 ./bin/ccp docs check --only E25; echo "exit $?"`.
  expect: step 1 prints nothing (exit 1); step 2 prints `1 0`; step 3's last line is `exit 0`.
  dry run (`1a575497`): step 1 printed 2 lines; step 2 printed `0 1`; step 3 printed `docs: clean: E25 only`, `exit 0`.
- id: `doc-03`
  story: As a reader, a command is listed once.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n 'ccp auth check' -- docs/cli`.
  expect: prints exactly one line, in `docs/cli/05-operations.md`.
  dry run (`1a575497`): printed 2 lines (`docs/cli/02-delivery.md:52`, `docs/cli/05-operations.md:9`).
- id: `code-01`
  story: As a plane developer, rewording a docs/cli row breaks no checker test, and the checker tests still pass.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `grep -c 'copy_with(' tests/test_cli_reference.py`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_cli_reference`.
  expect: step 1 prints `0`; step 2 exits 0.
  dry run (`1a575497`): step 1 printed `8`; step 2 exit 0.
- id: `spec-01`
  story: As the operator, §24.6 and §27.1 say what I signed.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0333`.
  expect: exit 0, every PROPOSED passage found.
  dry run (`1a575497`, with this brief): exit 1, the PROPOSED passages missing (`not found in the SPEC`).

## Implementation notes

- Every docs/cli part's tables are headed `| Command | Who | SPEC |`. The old What it does column split into Who (its
  seat) and the SPEC cell's one clause in parentheses; `03-quality`'s Cost column and closing exit-code paragraph went;
  `04-observability` gained a SPEC cell, the § its row named, else the § that states the command (`board task` §28.3,
  `board install|uninstall|timer` §28.2, `otel install|uninstall|status` §24.1, §24.2, `allowance continue` §25.3,
  `tasks estimate --all` §26.3, `tasks estimate show` §26.2, `estimate accuracy` §26.3). `05-operations`' four fenced
  blocks became tables under their headings, the `scripts/` lines included; the `plane check` block's "not listed"
  line (a §31.3 rule) went. Who cells the SPEC names no caller for are inferred from §29.2 and §31.5 (the plane
  session runs the release, triages and closes proposals as built), ADR-0041 (the lead declines or takes a step) and
  E21 (workers build a sandbox in a dod_check).
- A command is listed once: `ccp auth check` only in `05-operations`, as ruled; and, on the same reading of the
  title, `ccp tasks index` only in `01-model` (§5.7, its § part), `ccp health note` only in `03-quality` (§19.6) and
  `ccp health record` only in `04-observability` (§27.1), and `ccp notify fire` only in `01-model`, where each was
  listed twice. `ccp tasks check --lease` (`02-delivery`) and `ccp tasks check` (`03-quality`) stay: two call forms.
- The Pull requests preface keeps its first sentence; its exit-code sentence went.
- `04-observability`'s closing paragraph on the observability scripts stays as 0331 left it: the ruling names no change
  to it.
- `tests/test_cli_reference.py`: `problems_of(docs, parser=None)`; the seven checker tests run on `small_parser()` and
  `SMALL_DOCS` (two parts) written to a temporary directory by `Checker.docs_with`, which asserts the text it replaces
  is there; one more test holds the small docs clean against the small parser, so each case's exact problem list
  stands for the change alone.
- E25's text and `architect.checks` `E25` are the ruled ones; `docs/ENGINEERING.md` is at 150 lines.
- Fix round 1 (review NITs): four SPEC cells cut to one clause of purpose (`adr supersede` keeps the retiring, which
  §6.6 states with the links; `otel` keeps the `status` clause the ruling names; `usage --by-model` keeps its default
  inside the one clause; `plane check` drops what `--archive` does, which §31.3 states); `adr check` and `init` get back
  the subject the move into the SPEC cell lost; the second blank line before `__main__` in `tests/test_cli_reference.py`
  is back.

## Verification notes
