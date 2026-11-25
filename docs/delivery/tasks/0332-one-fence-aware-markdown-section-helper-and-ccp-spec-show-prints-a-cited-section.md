---
task_id: 0332-one-fence-aware-markdown-section-helper-and-ccp-spec-show-prints-a-cited-section
title: One fence-aware Markdown section helper finds a section under a heading for the task log, the estimator, the ADR reader, the report parser and the task converter, and E22 checks it; ccp spec show prints each cited SPEC section, which the estimator also quotes for a ref written with the prefix, and the worker prompts name it
status: pending
kind: feature
depends_on: []
spec_refs: ["S7", "S26"]
rule_refs: ["E22"]
review_refs: ["ar-20261124T234643Z-3c95#F02", "ar-20261124T234643Z-3c95#F03"]
review_point: R35
paths: ["ccp/mdsection.py", "ccp/tasklog.py", "ccp/estimator.py", "ccp/adr.py", "ccp/report.py", "ccp/taskmigrate.py", "ccp/cli.py", "ccp/spec.py", "tests/test_mdsection.py", "templates/prompts/_common.md", "docs/cli/01-model.md", "docs/spec/01-model.md", "docs/ENGINEERING.md", "docs/delivery/plane.json"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0333-every-docs-cli-part-takes-one-table-shape-e25-reads-every-line-and-the-cli-reference-tests-run-on-their-own-docs"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0332-one-fence-aware-markdown-section-helper-and-ccp-spec-show-prints-a-cited-section

## Intent

A seat checking a clause against the § it cites runs `ccp spec show <ref>` and reads that section, instead of
searching the SPEC files by hand; the worker prompts name the command. The section it prints is the one the estimator
quotes, now also for a ref written with the SPEC prefix (`S13`). Every reader that takes a Markdown section under a
heading (a task file's, a worker report's, a SPEC §, an ADR decision, an earlier generation's task table) finds it
through one fence-aware helper, so a `#` line inside a fenced block never ends a section, and house rule E22 says so
with a command check.

## Context (not checked)

Findings F02 and F03 of architect pass `ar-20261124T234643Z-3c95` (`docs/delivery/reviews/ar-20261124T234643Z-3c95.md`),
and the lead's friction notes from 0330's implementer, reviewer and verifier ("No `ccp` command prints a SPEC section
by its number"). The architect proposed E22's amendment; this triage accepted it and this task lands it, text and check
together.

Measured at `1a575497`:

- The triage commit after `1a575497` (`docs/ENGINEERING.md`: E5, E19 and E26 rewrapped, words unchanged;
  `docs/delivery/plane.json`: `E4`'s alias grep at `^\s*`) leaves every figure below as measured.
- **F03.** `git grep -nE 're\.search\(r?f?"\^(#\{\{?1,|\(#\+\))' -- ccp scripts ':(exclude)ccp/mdsection.py'`: 6 lines in
  5 functions: `"def _heading_block"` (`ccp/estimator.py`, 2), `"def decision_block"` (`ccp/adr.py`, its heading
  path), `"def friction"` and `"def follow_ups"` (`ccp/report.py`), `"def table"` (`ccp/taskmigrate.py`). None reads
  past a fenced block; `"def section_span"` and `"def unfence"` (`ccp/tasklog.py`) do.
- **F02.** `CCP_DEV=1 ./bin/ccp spec show 10.6`: exit 2 (`invalid choice: 'spec'`). `python3 -B -c 'from pathlib import Path; from ccp import config, estimator as e; print(e.spec_excerpts(config.load(Path(".")), ["S13"]))'`
  printed `### S13: no SPEC heading found`: this repo's SPEC headings carry no prefix (`## 13. Workers and prompts`),
  and every task here cites `S<n>`, so the estimator has quoted no SPEC section for them (a change of behaviour once
  fixed, so this is a feature). With `["10.6"]` it printed §10.6's block.
- `git grep -c 'spec show' -- templates/prompts plugin/agents`: nothing.
- **Ruled.**
  - New module `ccp/mdsection.py`: `unfence` moves there from `ccp/tasklog.py`, and it gains
    `"def heading_block(text: str, pattern: str, level: int | None = None) -> str | None"`: the block from the first
    heading outside a fenced block whose text matches `pattern` (at `level`, or any level), up to the next heading
    outside a fenced block of its level or higher. `tasklog.section_span` (a task file's `## ` sections, its aliases
    kept), the estimator, `adr.decision_block`'s heading path, `report.friction`, `report.follow_ups` and
    `taskmigrate.table` call it; `_heading_block` goes. `ccp/docrules.py`'s line reader is out.
  - A SPEC ref resolves through one function in new module `ccp/spec.py`: it drops a leading `§` or `ids.spec.prefix`
    and takes, across the `spec_paths` files in order, the `heading_block` of the first heading whose text starts with
    the number, with or without the prefix, followed by `.`, a space or the line's end. `ccp spec show <ref> [<ref> …]`
    prints each block in the order given (any seat; no `QUEUE_ROOT` needed); a ref no heading carries is named on
    stderr, and the command exits 1 when any ref is unresolved. `estimator.spec_excerpts` calls the same function.
  - `templates/prompts/_common.md` gains one line: a SPEC section the task or a finding cites is read with
    `{{ccp}} spec show <ref>`.
  - `docs/cli/01-model.md` gains the row `ccp spec show <ref> [<ref> …]` (any seat, §7.2).
  - New module `tests/test_mdsection.py`: class `Sections`, `test_a_heading_inside_a_fence_neither_starts_nor_ends_a_section`
    and `test_a_ref_matches_a_heading_with_or_without_the_prefix`; class `Callers`,
    `test_report_follow_ups_read_past_a_fenced_heading`, `test_an_adr_decision_block_reads_past_a_fenced_heading` and
    `test_the_estimator_quotes_a_spec_section_cited_with_the_prefix`.
  - **E22** (`docs/ENGINEERING.md`): its three lines are replaced by these four (the triage freed the line):

    > - **E22** One parser per durable grammar: one fence-aware helper, ccp/mdsection.py, finds a Markdown section under a
    >   heading (a task file's, a report's, a SPEC §, an ADR decision), and one tasklog function splits a task's dod_checks;
    >   no other module ends a section at a `#` heading, matches a task file's `## ` heading or `CHECK_RE`, or re-splits one.
    >   check: command — architect.checks `E22`

    and `docs/delivery/plane.json` `architect.checks` `E22`'s cmd becomes:

    ```
    ! git grep -n CHECK_RE -- ccp ':(exclude)ccp/tasklog.py' && ! git grep -nE 'search\(rf"\^## |tasklog\._section' -- ccp scripts ':(exclude)ccp/tasklog.py' && ! git grep -nE 're\.search\(r?f?"\^(#\{\{?1,|\(#\+\))' -- ccp scripts ':(exclude)ccp/mdsection.py'
    ```
- No other test expectation changes.

## Scope

- **In:** `ccp/mdsection.py` (new), `ccp/spec.py` (new), `ccp/tasklog.py`, `ccp/estimator.py`, `ccp/adr.py`,
  `ccp/report.py`, `ccp/taskmigrate.py`, `ccp/cli.py` (the `spec show` parser); `tests/test_mdsection.py` (new);
  `templates/prompts/_common.md`; `docs/cli/01-model.md` (one row); `docs/ENGINEERING.md` (E22, the text above);
  `docs/delivery/plane.json` (`architect.checks` `E22`); the SPEC, describing this task's own feature (§31.1):

  CURRENT (`docs/spec/01-model.md` at `1a575497`), §7.2, the SPEC refs bullet:
  > - **SPEC refs:** `<prefix><n>` and ranges (`S3–S5`). The citation rule of the doc checks (§21) reads them with `ids.spec.prefix`.

  PROPOSED:
  > - **SPEC refs:** `<prefix><n>` and ranges (`S3–S5`). The citation rule of the doc checks (§21) reads them with `ids.spec.prefix`. `ccp spec show <ref>` prints, and the estimator quotes (§26.3), the block under the first heading outside a fenced block across the `spec_paths` files whose text starts with the ref's number, with or without the prefix, up to the next heading of its level or higher.
  The sentence only describes this task's command and the estimator's quote; it states no rule for citations, and
  §21.6 (the opt-in rules, the `citations` rule among them) is unchanged.
- **Out:** §21.6 and the `citations` rule's reading of a ref; `ccp/docrules.py`'s heading reader; ranges in
  `ccp spec show`; the estimator's excerpt budgets; the other worker briefs.

## dod_checks

- id: `cmd-01`
  story: As a seat checking a clause, I print the § it cites by its number, with or without the prefix.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp spec show 10.6 | head -1`.
    2. Run `CCP_DEV=1 ./bin/ccp spec show S13 | head -1`.
    3. Run `CCP_DEV=1 ./bin/ccp spec show 99.9 >/dev/null 2>&1; echo "exit $?"`.
  expect: step 1 prints `### 10.6 Principles of the toolkit, and exit codes`; step 2 prints `## 13. Workers and prompts`; step 3 prints `exit 1`.
  dry run (`1a575497`): steps 1 and 2 printed nothing (the parser's usage on stderr); step 3 printed `exit 2`.
- id: `code-01`
  story: As a plane developer, a `#` line inside a fenced block never ends a section, in every reader, and the estimator quotes a § cited with the prefix.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_mdsection.Sections.test_a_heading_inside_a_fence_neither_starts_nor_ends_a_section tests.test_mdsection.Sections.test_a_ref_matches_a_heading_with_or_without_the_prefix tests.test_mdsection.Callers.test_report_follow_ups_read_past_a_fenced_heading tests.test_mdsection.Callers.test_an_adr_decision_block_reads_past_a_fenced_heading tests.test_mdsection.Callers.test_the_estimator_quotes_a_spec_section_cited_with_the_prefix`.
  expect: exit 0.
  dry run (`1a575497`): exit 1 (`ModuleNotFoundError: No module named 'tests.test_mdsection'`).
- id: `code-02`
  story: As a plane developer, no module but the helper ends a section at a heading, and E22's check holds it.
  setup: A checkout of the PR head (any seat), with a scratch `QUEUE_ROOT`.
  steps:
    1. Run `git grep -nE 're\.search\(r?f?"\^(#\{\{?1,|\(#\+\))' -- ccp scripts ':(exclude)ccp/mdsection.py'`.
    2. Run `python3 -B -c 'import json; c = [x["cmd"] for x in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if x["id"] == "E22"][0]; print(c.count("mdsection.py"))'`.
    3. Run `CCP_DEV=1 ./bin/ccp docs check --only E22; echo "exit $?"`.
  expect: step 1 prints nothing (exit 1); step 2 prints `1`; step 3's last line is `exit 0`.
  dry run (`1a575497`): step 1 printed 6 lines; step 2 printed `0`; step 3 printed `docs: clean: E22 only`, `exit 0`.
- id: `doc-01`
  story: As a worker, my prompt names the command that prints a cited §.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'spec show' templates/prompts/_common.md`.
  expect: prints `1`.
  dry run (`1a575497`): printed `0`, exit 1.
- id: `spec-01`
  story: As the operator, §7.2 says how a SPEC ref resolves and names the command.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0332`.
  expect: exit 0, the PROPOSED passage found.
  dry run (`1a575497`, with this brief): exit 1, the PROPOSED passage missing (`not found in the SPEC`).

## Implementation notes

## Verification notes
