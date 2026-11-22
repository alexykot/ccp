---
task_id: 0269-verify-actions-own-their-flags-and-prompts-link-cited-findings
title: ccp verify refuses a flag its action does not take, and a worker prompt names the record of each finding a task cites
status: done
kind: feature
depends_on: []
clashes_with: ["0262-module-docstrings-and-house-rule-checks", "0266-github-knowledge-stays-in-the-pr-host-module"]
spec_refs: ["S13", "S15", "S19"]
review_refs: ["ar-20261121T174754Z-7df5#F08", "ar-20261121T174754Z-7df5#F11"]
rule_refs: ["E25", "E13"]
review_point: R21
paths: ["ccp/cli.py", "ccp/verify.py", "ccp/prompt.py", "docs/cli/02-delivery.md", "tests/test_verify_parser.py", "tests/test_verify_later.py", "tests/test_prompt_review_refs.py"]
adopt: "none"
created: 2026-11-21
updated: 2026-11-22
---

# Task: 0269-verify-actions-own-their-flags-and-prompts-link-cited-findings

## Intent

Each `ccp verify` action takes only its own arguments: a flag another action reads is refused by the
parser, with the usage of the action that was called, instead of being dropped silently. A worker
reading a prompt for a task that cites review findings sees, beside each finding id, the review
record that holds its evidence, so it reads the finding before judging the task.

## Context (not checked)

From architect pass `ar-20261121T174754Z-7df5`, findings F08 and F11 (the record is in
`docs/delivery/reviews/`). Two small findings on what a worker types and reads, bundled into one task.
Measured at `afb8ce6` (the figures below match `31357f0`, where the dry runs ran).

- **F08, one flat parser for six actions.** `ccp/cli.py`'s `verify` parser:
  `p.add_argument("action", choices=("record", "merge-ok", "check", "spec-text", "later", "deferred"))`,
  `target` with `nargs="?"`, then `--task`, `--check`, `--pass`/`--fail`, `--evidence`,
  `--produced-by`, `--operator-step`, `--json`, `--head`, `--base` for all. `ccp/verify.py`
  `"def main"` re-checks the target per action by hand. `CCP_DEV=1 ./bin/ccp verify record /dev/null --check x --pass`
  at `31357f0`: parses, then stops on QUEUE_ROOT; the flags are never refused. `ccp pr` (0220) uses
  subparsers. Ruling: `ccp verify` gets one subparser per action, each with the arguments
  `docs/cli/02-delivery.md`'s six rows give it (`record FILE`; `merge-ok PR [--task]`;
  `check TASK --head SHA`; `spec-text TASK [--base] [--head]`;
  `later TASK --check ID --pass|--fail --evidence TEXT --produced-by SEAT [--operator-step ID]`;
  `deferred [--task] [--json]`), with the help texts it has today. `main()`'s hand checks of the
  target go. The board-refresh entry `("verify", "record")` in `ccp/cli.py` `REFRESHES` keeps
  matching (`a.cmd` or the dest the subparsers use). `--pass`/`--fail` stay one required group on
  `later`.
- **F11, bare finding ids.** `ccp/prompt.py` builds `refs` as `", ".join(cited)` over `spec_refs`,
  `adr_refs`, `rule_refs` and `review_refs`
  (`grep -c '"refs": ", ".join(cited)' ccp/prompt.py` at `31357f0`: 1 line). The implement, review and verify templates render `{{refs}}`. A review ref
  (`<review_id>#F<nn>`) names a finding whose evidence is in `<reviews_dir>/<review_id>.md`
  (`cfg.reviews_dir`, `task_log.reviews_dir`). 0234's reviewer looked for the shape findings in the
  queue and judged without them (its friction note). Ruling: each review ref renders as
  `<review_id>#F<nn> (<cfg.rel(cfg.reviews_dir)>/<review_id>.md)`; the other refs render as today.
  No template changes.
- **Tests this breaks:** `tests/test_verify_later.py` (`"def test_deferred_refuses_a_task_given_as_a_positional"`
  expects `--task` in the refusal; argparse's own refusal replaces it, exit 2 kept).
  `git grep -n '"refs"' -- tests` at `31357f0`: 2 lines, both estimate records (`tests/test_estimate.py`,
  `tests/test_estimator.py`); no test pins the rendered refs.
- **No SPEC change:** `git grep -n 'refs}}' -- docs/spec` at `31357f0`: nothing names the
  prompt's refs value; §15.4's and §15.5's syntax is `docs/cli`'s, unchanged.

## Scope

- **In:**
  - `ccp/cli.py` (the `verify` subparsers), `ccp/verify.py` (`main`), `docs/cli/02-delivery.md`
    (only if a row's wording must follow the parser).
  - `ccp/prompt.py` (the `refs` value).
  - `tests/test_verify_parser.py` (new), `tests/test_verify_later.py`, `tests/test_prompt_review_refs.py` (new).
- **Out:** other flat action parsers; the templates; resolving review refs in `ccp tasks check`.

## dod_checks

- id: `cli-01`
  story: As a verifier, a flag that belongs to another verify action is refused, not dropped.
  setup: A checkout of the PR head, QUEUE_ROOT unset.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify record /dev/null --check x --pass 2>&1 | grep -c 'unrecognized arguments'`.
    2. Run `CCP_DEV=1 ./bin/ccp verify deferred 0001 2>&1 | grep -c 'unrecognized arguments'`.
  expect: steps 1 and 2 each print `1`.
  dry run (`31357f0`): step 1 printed `0` (it stopped on QUEUE_ROOT); step 2 printed `0` (it printed `give the task with --task`).
- id: `cli-02`
  story: As a plane developer, each verify action's arguments are its own, the CLI reference still matches the parser, and the actions behave as before.
  setup: A checkout of the PR head; then a separate copy of it where the `later` subparser also takes `--json`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_verify_parser tests.test_cli_reference tests.test_verify tests.test_verify_later tests.test_verify_spec_text`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_verify_parser`.
  expect: step 1 exits 0, `tests/test_verify_parser.py` holding a test per action that a flag only another action takes exits 2, the `later` case passing `--json` (a `deferred` flag); step 2 exits non-zero.
  dry run (`31357f0`): step 1 without `tests.test_verify_parser` (new) exited 0 (`OK`); step 2 n/a.
- id: `pr-01`
  story: As a reviewer of a task that cites a review finding, my prompt names the record that holds the finding's evidence.
  setup: A checkout of the PR head; then a separate copy of it where `refs` joins the bare ids again.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_prompt_review_refs 2>&1 | tail -6`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_prompt_review_refs`.
  expect: step 1 exits 0, listing as `ok` a test where a fenced product's task with `review_refs: ["ar-20261001T120000Z-0f3c#F02"]` and `spec_refs: ["S10"]` renders, in its implement prompt, `ar-20261001T120000Z-0f3c#F02 (docs/delivery/reviews/ar-20261001T120000Z-0f3c.md)` and `S10` with nothing after it; step 2 exits non-zero.
  dry run: n/a — the module is new.

## Implementation notes

- `ccp verify` is one subparser per action (`dest="action"`, so `REFRESHES`' `("verify", "record")` still
  matches), each with the arguments its `docs/cli/02-delivery.md` row gives: the row's unbracketed flags are
  `required=True` (`check --head`; `later --check`, `--evidence`, `--produced-by`, and `--pass`/`--fail` as one
  required group), and `merge-ok`'s PR takes `ccp pr`'s `_pr_number` type. The doc rows needed no change.
- The action parsers are `_OwnArgs` (`ccp/cli.py`): an argument the action does not take is refused by the
  action's own parser, so the refusal shows that action's usage, not the whole command's (argparse's default
  leaves extras to the top-level parser, which prints `usage: ccp …`).
- `verify.main()` loses its hand checks of the target, and `_later_main` its missing-flag check (dead once the
  parser requires them). The blank `--head` refusal on `check` stays: a `--head ""` still parses.
- `ccp/prompt.py` `cited_refs(cfg, meta)` builds `refs`: each `review_refs` entry is followed by
  `(<cfg.rel(cfg.reviews_dir)>/<the part before #>.md)`; the other refs as before.
- `tests/test_verify_later.py`: the three parser-refusal tests now expect argparse's `SystemExit(2)` (exit 2 kept,
  nothing on stdout) instead of a returned 2 with the hand-written text.

## Verification notes
- 2026-11-22 — verifier, PR #320 head `3d14dcc` (squash `1bdd7a5`): APPROVE. Passed: cli-01, cli-02, pr-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0269-verify-actions-own-their-flags-and-prompts-link-cited-findings.json.

