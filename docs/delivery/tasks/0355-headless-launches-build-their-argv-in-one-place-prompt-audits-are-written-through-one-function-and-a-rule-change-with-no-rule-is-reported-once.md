---
task_id: 0355-headless-launches-build-their-argv-in-one-place-prompt-audits-are-written-through-one-function-and-a-rule-change-with-no-rule-is-reported-once
title: The architect and estimator seats build their claude -p argv through one headless function that owns the key strip and the seat's binary override; every prompt audit is written through one ccp function its four callers share; an architect report's rule change with no rule is reported once
status: done
kind: feature
depends_on: []
spec_refs: ["S19", "S23", "S24"]
rule_refs: ["E8", "E12"]
review_refs: ["ar-20261125T202431Z-1a86#F05"]
review_point: R39
paths: ["ccp/headless.py", "ccp/promptaudit.py", "ccp/architect.py", "ccp/estimator.py", "ccp/prompt.py", "ccp/architecture_review.py", "ccp/CLAUDE.md", "scripts/observability/team.py", "tests/test_headless.py", "tests/test_promptaudit.py", "tests/test_architect_triage_schema.py", "tests/test_team_hosting.py"]
clashes_with: ["0191-the-grace-release-ends", "0351-the-runner-s-scope-slot-and-readiness-decisions-move-into-a-ccp-module-tested-on-plain-values", "0353-prompt-tests-pin-rendered-values-ccp-prompt-render-prints-a-template-and-the-lanes-line-names-the-module-form"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0355-headless-launches-build-their-argv-in-one-place-prompt-audits-are-written-through-one-function-and-a-rule-change-with-no-rule-is-reported-once

## Intent

A maintainer changing how a headless seat starts `claude -p`, or what a prompt audit records, changes one function,
not each seat's copy. An operator reading a refused architect report sees each fault once.

## Context (not checked)

Finding F05 of architect pass `ar-20261125T202431Z-1a86` (`docs/delivery/reviews/ar-20261125T202431Z-1a86.md`), and
a follow-up of R38 the lead passed to that pass: 0350's reviewer saw `ar.validate_report` report a rule change
that has no `rule` twice.

0191 (on hold; it removes the moved keys' fallback reads, and its `paths` hold all of `tests/`) leaves a constant's non-default value applying, so `prompts.keep_body` is read as now; whichever lands second rebases.

Measured at `becb6417`:

- `git grep -n 'for k in headless.STRIP_KEYS' -- ccp` at `becb6417`: 2 lines, `ccp/architect.py` (the launch in
  `"def _run_one"`, `envvar("CCP_ARCHITECT_CLAUDE_BIN") or "claude"`) and `ccp/estimator.py` (`"def argv_for"`,
  `envvar("CCP_ESTIMATOR_CLAUDE_BIN") or "claude"`). Both build `["env", "-u", <key>…, <binary>, "-p", <prompt>, …]`.
- `git grep -ln 'write-prompt-audit' -- 'ccp/*.py' scripts/observability/team.py` at `becb6417`: `ccp/architect.py`,
  `ccp/estimator.py`, `ccp/prompt.py` (`"def audit"`) and `scripts/observability/team.py` (three calls, with its own
  `"def keep_body"`). Each builds the script's argv, adds `--keep-body` when `prompts.keep_body` is set, and takes
  the last stdout line as the prompt ref; the failure messages are `write-prompt-audit failed: …` (architect,
  estimator, team.py) and `write-prompt-audit: …` (`ccp prompt`).
- `"rc = r.get(\"rule_changes\")"` (`ccp/architecture_review.py` `validate_report`) reports
  `rule_changes[i]: rule None is not a rule id` for a change with no `rule`, beside the contract's own
  missing-`rule` error.

**Ruled.**

- `ccp/headless.py` gains `claude_argv(override_var: str, prompt: str, flags: list[str]) -> list[str]`:
  `["env", "-u", <each STRIP_KEYS key>, envvar(override_var) or "claude", "-p", prompt, *flags]`. `ccp/architect.py`
  and `estimator.argv_for` (its signature unchanged) call it; the two override variables and the two fence lines in `tests/__init__.py` stay
  (each seat's tests stub its own). New test `tests.test_headless.ClaudeArgv.test_the_keys_are_stripped_and_the_seat_s_override_is_the_binary`.
- `ccp/promptaudit.py` (new) holds `write(q, cfg, *, task_id, phase, argv, prompt=None, prompt_file=None,
  **fields) -> str`: it runs `scripts/observability/write-prompt-audit.sh` with `QUEUE_ROOT=q`, the prompt on stdin
  (`--prompt-file -`) or the named file, each field as its `--<field-with-dashes>` option (`actor`, `project_id`,
  `worktree`, `git_head`, `notes`, `session_id`, `durable_task_path`, `spec_refs`), and `--keep-body` when `cfg` is
  not None and its `prompts.keep_body` is set; it returns the last stdout line, and on a non-zero exit raises
  `QueueError("write-prompt-audit failed: <stderr>", 1)`. `ccp/prompt.py`'s `audit`, `ccp/architect.py`,
  `ccp/estimator.py` and `team.py`'s three calls use it; `team.py`'s `keep_body` goes, replaced by
  `product_config(root)`, which returns the product's loaded config, or None
  when there is no product root, no plane.json, or a load that fails, and which the three calls pass to `write`. `ccp prompt`'s message becomes `write-prompt-audit failed: …`; the
  architect and estimator keep raising `RuntimeError` with the same message; `team.py` keeps its `die`. New module
  `tests/test_promptaudit.py` (new) runs `write` against a scratch queue: the ref returned, `--keep-body` only with
  the setting, and the failure.
- `validate_report` checks a rule change's id only when `rule` is a string, as the triage check does; the contract
  reports a missing one. New test
  `tests.test_architect_triage_schema.ReportContract.test_a_rule_change_with_no_rule_is_reported_once`.
- `tests.test_team_hosting.TestKeepBodyImport` (`"def test_repeated_calls_leave_the_import_path_as_the_first_left_it"`)
  calls `team.keep_body` and asserts `["--keep-body"]`: it stays in `tests/test_team_hosting.py` and calls
  `team.product_config` instead, asserting its `prompts["keep_body"]` is true; its import-path assertions are
  unchanged.
- `ccp/CLAUDE.md` names `promptaudit.py`. No other test expectation changes.
- No SPEC change: §23.8 names `write-prompt-audit.sh` as the writer, which stays; `git grep -n 'argv_for\|STRIP_KEYS' -- docs/spec`
  at `becb6417` prints nothing.

## Scope

- **In:** `ccp/headless.py`; `ccp/promptaudit.py` (new); `ccp/architect.py`; `ccp/estimator.py`; `ccp/prompt.py`
  (`audit` only); `ccp/architecture_review.py` (`validate_report` only); `ccp/CLAUDE.md`;
  `scripts/observability/team.py` (the three audit calls and `keep_body` only); `tests/test_headless.py`;
  `tests/test_promptaudit.py` (new); `tests/test_architect_triage_schema.py`; `tests/test_team_hosting.py`
  (`TestKeepBodyImport` only).
- **Out:** `prompts.keep_body` itself and `prune_audits` (the operator's question on `ar-20261125T202431Z-1a86`
  F04); `scripts/observability/write-prompt-audit.sh`; the runner's decisions in `team.py` (0351).

## dod_checks

- id: `code-01`
  story: As a maintainer, one function builds a headless seat's claude argv.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -n 'for k in headless.STRIP_KEYS' -- ccp`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_headless.ClaudeArgv.test_the_keys_are_stripped_and_the_seat_s_override_is_the_binary tests.test_headless tests.test_estimator tests.test_models_block tests.test_architect`.
  expect: step 1 prints nothing (git grep's exit 1); step 2 exits 0.
  dry run (`becb6417`): step 1 printed 2 lines; step 2 exit 1 (`AttributeError: module 'tests.test_headless' has no attribute 'ClaudeArgv'`).
- id: `code-02`
  story: As a maintainer, every prompt audit is written through one ccp function.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `git grep -ln 'write-prompt-audit' -- 'ccp/*.py' scripts/observability/team.py`.
    2. Run `git grep -nw 'def keep_body' -- scripts/observability/team.py`.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_promptaudit tests.test_prompt_audit tests.test_team_hosting`.
  expect: step 1 prints only `ccp/promptaudit.py`; step 2 prints nothing (git grep's exit 1); step 3 exits 0.
  dry run (`becb6417`): step 1 printed `ccp/architect.py`, `ccp/estimator.py`, `ccp/prompt.py` and `scripts/observability/team.py`; step 2 printed 1 line; step 3 exit 1 (`tests.test_promptaudit` does not exist).
- id: `code-03`
  story: As an operator, a refused architect report names a rule change's missing rule once.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_architect_triage_schema.ReportContract.test_a_rule_change_with_no_rule_is_reported_once tests.test_architect_triage_schema`.
  expect: exit 0.
  dry run (`becb6417`): exit 1 (`AttributeError: type object 'ReportContract' has no attribute 'test_a_rule_change_with_no_rule_is_reported_once'`).

## Implementation notes

- `headless.claude_argv` builds the argv for the architect (`_run_one`) and `estimator.argv_for`; both seats' override variables and fence lines are unchanged. `ccp/architect.py` lost its now-unused `envvar` import and its `PLANE`/`OBS` constants (the audit call was their only use); `ccp/prompt.py` lost its unused `subprocess` import and `OBS`; `scripts/observability/team.py` lost its unused `subprocess` and `os` imports.
- `promptaudit.write` raises `ValueError` when given both or neither of `prompt` and `prompt_file` (the task leaves it open: the narrowest rule). A field given as None is not passed to the writer, so `ccp prompt` passes `worktree or None` and `note or None`, keeping its old skip of an empty value. The failure message is the writer's stderr only: `ccp prompt` no longer falls back to stdout, and the estimator's message is no longer cut to 300 characters.
- `team.py` gains `write_audit(root, **kw)`, a small wrapper over `promptaudit.write` that passes `product_config(root)`, `actor=LEAD` and the project id and turns a `QueueError` into `die`, so the three calls do not each repeat the try. The task names only `product_config`; the wrapper holds no new rule.
- `TestKeepBodyImport` also asserts `product_config` is None with no product root and with a plane.json that fails to load (the two branches the task's text names).
- `validate_report`'s rule-change check now matches `validate_triage`'s: it runs only when `rule` is a string.

## Verification notes
- 2026-11-25 — verifier, PR #433 head `296a77d` (squash `e2d9243`): APPROVE. Passed: code-01, code-02, code-03. Gate: `scripts/gate.sh` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0355-headless-launches-build-their-argv-in-one-place-prompt-audits-are-written-through-one-function-and-a-rule-change-with-no-rule-is-reported-once.json.

