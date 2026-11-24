---
task_id: 0330-docs-cli-rows-give-call-syntax-not-spec-rules-the-reviewer-brief-leaves-the-prompt-s-rule-to-it-and-the-scripts-doc-follows-e7
title: The docs/cli rows give call syntax, who calls it, one clause of purpose and the §, not the SPEC's rules or exit codes, and E25 checks it; the reviewer brief leaves the Spec-beyond-intent instruction to the review prompt; the scripts package doc follows E7
status: done
kind: refactor
depends_on: []
rule_refs: ["E25", "E13", "E7", "E26"]
review_refs: ["ar-20261124T205520Z-4ce8#F03", "ar-20261124T205520Z-4ce8#F04", "ar-20261124T205520Z-4ce8#F05"]
review_point: R34
paths: ["docs/cli/01-model.md", "docs/cli/02-delivery.md", "docs/cli/03-quality.md", "docs/cli/04-observability.md", "docs/ENGINEERING.md", "docs/delivery/plane.json", "plugin/agents/delivery-reviewer.md", "tests/test_sign_off_beyond_intent.py", "scripts/CLAUDE.md"]
clashes_with: ["0191-the-grace-release-ends", "0329-tests-edit-plane-json-through-one-helper-name-the-plane-root-once-and-take-git-from-its-own-module"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0330-docs-cli-rows-give-call-syntax-not-spec-rules-the-reviewer-brief-leaves-the-prompt-s-rule-to-it-and-the-scripts-doc-follows-e7

## Intent

A feature that changes a command's behaviour edits the SPEC, not also the command reference: each docs/cli row gives
the call syntax, who calls it, at most one clause of purpose and the §, and house rule E25 says so with a command check
that names a row over its length in bytes or an exit code in docs/cli. The reviewer reads the Spec-beyond-intent instruction
once, in its rendered prompt, not again in its brief. And `scripts/CLAUDE.md` describes the directory as it is, a
plane-development program included, naming E7 instead of restating it.

## Context (not checked)

Findings F03, F04 and F05 of architect pass `ar-20261124T205520Z-4ce8`
(`docs/delivery/reviews/ar-20261124T205520Z-4ce8.md`); that triage applied F05's E7 amendment and accepted F03's E25
amendment, which this task lands (text and check together).

Measured at `db68df5b`:

- **F03.** ``awk '/^\| `ccp/ && length > 300' docs/cli/*.md | wc -l``: 16 rows (`ccp init`, `notify fire`, `notify
  upgrade`; `tasks next`, `tasks submit`, `tasks follow-up`, `ccp prompt`, `suite run`, `suite affected`; `tasks
  check`, `tasks dry-run`, `docs check`, `ccp mutate`; `ccp usage`, `usage --by-model`, `ccp health`), the longest 1,319
  bytes (awk's `length`). `git grep -nP '\bexits? (code )?[0-9]|\bexit code' -- docs/cli | wc -l`: 13 lines. `git grep -ln
  'docs/cli' -- tests`: only `tests/test_cli_reference.py`, which holds the flags to the parser. `CCP_DEV=1 ./bin/ccp
  docs check --only E25` printed `ccp docs check runs no check E25`, exit 2.
- **F04.** `git grep -c 'beyond intent' -- plugin/agents/delivery-reviewer.md`: 2 (its bullet "Judge the normative text
  the PR adds or changes …", which `templates/prompts/review.md` gives too). `tests/test_sign_off_beyond_intent.py`
  (`"def test_the_reviewer_is_asked_for_the_section_and_the_verifier_for_the_list"`) pins `## Spec beyond intent` in
  the reviewer brief. The evidence rule the briefs also state stays: §13.1 puts the four generic rules in the worker
  definitions (a Known intentional note says so).
- **F05.** `grep -c 'shell entry points\|not into a new script' scripts/CLAUDE.md`: 2 (the title and the last line,
  which restates E7, against E26).
- **Ruled.**
  - Each file keeps its existing columns: no Who column is added, `docs/cli/03-quality.md` keeps Cost, and
    `docs/cli/05-operations.md` gets no § column. E25 governs a row's length and content only, so "who calls it" is
    said within the row's own text where a file has no Who column.
  - Each docs/cli row keeps its call syntax and flags (held to the parser by `tests.test_cli_reference`), who calls
    it, at most one clause of purpose and its §; every other clause (a refusal, an exit code, an output format, a
    condition) goes. Before cutting a clause, find it in the § the row cites; a clause no § states stays, shortened,
    and is named under the report's follow-ups. The prefaces of `docs/cli.md` and the part files stay.
  - **E25** (`docs/ENGINEERING.md`, its four lines replaced by these four, so the doc stays within its 150-line cap):

    > - **E25** The parser is the one source of the command surface. Call syntax is written by hand in one place (docs/cli),
    >   held to the parser by a test: a row gives the syntax, who calls it, at most one clause of purpose and the §, never
    >   the SPEC's rules or exit codes; no module docstring in ccp/ carries a usage table.
    >   check: command — architect.checks `E25` (no docs/cli command row over 300 bytes, none naming an exit code); plus the gate — tests.test_cli_reference (E1)

    and `docs/delivery/plane.json` `architect.checks` gains, after `E24`, the entry `{"id": "E25", "cmd": …}` whose
    cmd is:

    ```
    ! awk '/^\| `ccp/ && length > 300 {print FILENAME ": " substr($0, 1, 60); n++} END {exit n == 0}' docs/cli/*.md && ! git grep -nP '\bexits? (code )?[0-9]|\bexit code' -- docs/cli
    ```

    (at `db68df5b` it prints the 16 rows and exits 1; in a repo whose one docs/cli row is short it exits 0).
  - `plugin/agents/delivery-reviewer.md`: the bullet "Judge the normative text the PR adds or changes …" goes whole;
    nothing replaces it. `tests/test_sign_off_beyond_intent.py` stops pinning the reviewer brief (its other three pins
    stay).
  - `scripts/CLAUDE.md`: the title becomes `# scripts — the plane's entry points and its development programs`, and
    the last line becomes `Scripts follow E7.`

## Scope

- **In:** `docs/cli/01-model.md`, `docs/cli/02-delivery.md`, `docs/cli/03-quality.md`, `docs/cli/04-observability.md`
  (their rows); `docs/ENGINEERING.md` (E25, the text above); `docs/delivery/plane.json` (`architect.checks` `E25`);
  `plugin/agents/delivery-reviewer.md`; `tests/test_sign_off_beyond_intent.py` (the reviewer brief's pin, named
  above); `scripts/CLAUDE.md`.
- **Out:** the SPEC; `docs/cli.md` and the part files' prefaces; `docs/cli/05-operations.md` (no row over the limit,
  no exit code); the implementer's and verifier's briefs; `templates/prompts/`.

## dod_checks

- id: `code-01`
  story: As a plane developer, E25's check passes: no docs/cli row is over 300 bytes or names an exit code, and E25 names its command check.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp docs check --only E25; echo "exit $?"`.
    2. Run `grep -c 'architect.checks .E25' docs/ENGINEERING.md`.
  expect: step 1's last line is `exit 0`; step 2 prints `1`.
  dry run (`db68df5b`): step 1 printed `ccp docs check: --only E25: ccp docs check runs no check E25 (…)`, `exit 2`; step 2 printed `0`, exit 1.
- id: `doc-01`
  story: As a reviewer, my brief does not restate the Spec-beyond-intent instruction my prompt gives.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -c 'beyond intent' -- plugin/agents/delivery-reviewer.md`.
  expect: prints nothing (exit 1).
  dry run (`db68df5b`): printed `plugin/agents/delivery-reviewer.md:2`.
- id: `doc-02`
  story: As a plane developer, the scripts package doc describes the directory as it is and names E7 without restating it.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `grep -c 'shell entry points\|not into a new script' scripts/CLAUDE.md`.
  expect: prints `0`.
  dry run (`db68df5b`): printed `2`.

## Implementation notes

- Premises re-measured at 49fc0406 before building: 16 docs/cli rows over 300 bytes, 13 exit-code lines, 2 `beyond intent` hits in the reviewer brief, 2 `scripts/CLAUDE.md` hits: unchanged.
- docs/cli: 19 rows rewritten (the 16 long ones, plus the exit-code rows `tasks migrate`, `tasks prefer`, `tasks hold`, `tasks sign-off`, `tasks ruling`, `tasks checks`, `team.sh runner spawn --dry-run`, and `ccp board status`'s "exits non-zero"). Who is said inside the row's own text where a file has no Who column, and only in the rows rewritten.
- `ccp prompt` is four rows, not one: its syntax alone is about 280 bytes, so the one row cannot hold the 300-byte limit with its who and §. Row 1 has the flags every phase takes; `--allow-unreviewed-fix`, `--mode resolution` and `--waived` each sit on a row naming the one phase that takes them. `tests.test_cli_reference` credits flags per command, so it passes as before.
- Clauses kept because no § states them, shortened: `ccp init`'s `--starter-rules` is a no-op (the flag must stay in the syntax; only the parser's help says it), `ACTOR=design-seat` for the lead's writing commands (`tasks prefer`, `hold`, `sign-off`, `ruling`, `follow-up`), `tasks next --json` carries `passed_over`, `tasks follow-up` run again replaces the outcome.
- Left as they were, outside the rows: the "Exit 1 on a PR-host error ... 2 on a usage error" line under `## Pull requests` in `02-delivery.md` (capital E, so E25's grep does not match it) and the closing `Exit codes for these commands follow §10's contract` paragraph of `03-quality.md`.
- E25 in `docs/ENGINEERING.md` and `architect.checks` `E25` in `docs/delivery/plane.json` as the task gives them; `docs/ENGINEERING.md` stays at 150 lines.
- The reviewer brief's Spec-beyond-intent bullet is gone; `templates/prompts/review.md` still carries the instruction. `tests/test_sign_off_beyond_intent.py` no longer pins the reviewer brief for it.
- `scripts/CLAUDE.md`: title and last line as given.

## Verification notes

### Fix round 1

- Brought every remaining docs/cli row to the ruled shape (syntax, who, at most one clause of purpose, the §), not only the 19 the E25 command flags: refusals, conditions, output formats and "needs `QUEUE_ROOT`" went from the rows of 01-model, 02-delivery, 03-quality and 04-observability, each found in the § the row cites first (§4.5 and §3.6 for `init` and `notify`, §16.5 for `idle_runners` and `vacant_slots`, §10.7 for `tasks orphans`, §21.1 and §22.2 for `--closed-points`, §15.5 for `pr`). Who is now in each row's own text where the file has no Who column; the 03-quality Cost cells are untouched.
- `ccp health`'s row keeps the adoption-point window for the measurements and suite series only, and names the usage advice apart (§27.1). `ccp usage --by-model` keeps "default `implementer`". `ccp init` and `--rules-doc` name the operator (README step 2, §4.5); `tasks dry-run` names the lead, and any worker for `--here` (§21.1). The `ccp docs check` row names `--only` as taking an `architect.checks` or `docs.checks` entry (§21.2).
- Clauses no § states, left out and named under the report's follow-ups: `health.small_task_lines`, `advice_since`, `usage --by-model`'s per-model measures and attribution rule, `tasks check --stale`'s "no other flag", `ccp usage`'s window.

### Fix round 2

- The `ccp init` row now says "(the operator)", as round 1's notes claimed (README step 2, §4.5).
- Clauses no cited § states stay in their rows, shortened, instead of being cut: `ccp otel status` ("reports the counts and checks the user settings"), `ccp pr open` ("prints its number"), `ccp pr view` ("`--json` gives one object"), `ccp tasks estimate show` ("latest of each source"). They are named under the report's follow-ups as SPEC gaps.
- The `ccp forecast` row cites §26.5 as well as §26.4, where the allowance projection is.
- 2026-11-24 — verifier, PR #402 head `eb24982` (squash `f62d016`): APPROVE. Passed: code-01, doc-01, doc-02. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0330-docs-cli-rows-give-call-syntax-not-spec-rules-the-reviewer-brief-leaves-the-prompt-s-rule-to-it-and-the-scripts-doc-follows-e7.json.

