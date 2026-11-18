---
task_id: 0155-recent-window-for-usage-and-health
title: Cost advice can read a recent window and says which requests it read; init refuses a blank gate; verifiers check ccp by hand with the head's own; suite affected prints a ready command
status: pending
kind: feature
depends_on: []
spec_refs: ["S24", "S27", "S4", "S14", "S15"]
review_point: R10
paths: ["ccp/usage.py", "ccp/health.py", "ccp/cli.py", "ccp/config.py", "contracts/plane_config.schema.json", "ccp/init.py", "ccp/suite.py", "templates/prompts/verify.md", "docs/spec/04-observability.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/cli/04-observability.md", "tests/test_usage_advice.py", "tests/test_usage.py", "tests/test_health.py", "tests/test_init.py", "tests/test_suite_affected.py", "tests/test_prompt*.py"]
adopt: "optional: plane.json usage.advice.window_hours 24, for cost advice from the last day's requests only"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0155-recent-window-for-usage-and-health
## Intent

The cost advice describes how the product runs now, not since telemetry began: once a lead fixes
what the advice named, a product that sets a window stops seeing it within that window, and each
line says which requests it read.
Three adoption follow-ups close with it. `ccp init` refuses a blank gate command instead of writing
one config then refuses. A verifier checking a `ccp` change by hand runs the head's `ccp`. And
`ccp suite affected` hands the worker a command it can run.

## Context (not checked)

- `ccp usage` and `ccp health` compute the cost advice (`cost_advice` in `ccp/usage.py`) from every
  request in `board/usage-requests.jsonl`. `fold` has no time bound (`"def fold"`), and `ccp usage
  --since` is accepted only with `--system` (`ccp usage --help` at `85d388b`: its `--since` takes
  `YYYY-MM-DD` with `--system` only). Seen in an adopting product: a day after it set `subagentPromptCacheTtl` to `1h` and
  `autoCompactWindow`, the advice still named the runner's 5-minute cache writes, the lead's median
  context and the coordination share, while the requests of the day since showed none of them past
  its threshold.
- `ccp health` already starts its window at the adoption point. Its module docstring says "The usage
  advice (`ccp usage`'s) and the rotation slots due now are not windowed." An adoption-point window
  would still be stale in the case above, so the advice gets its own recent window.
- The rotation slots due are not a history. `lifecycle.rotation_due` judges each slot since its own
  spawn (its docstring: "the teammate's latest request since the spawn"), so they need no window. That
  half of the proposal is false and is dropped.
- `ccp init --gate ' '` at `85d388b` (a scratch repo, `ccp init --project-id demo --queue-root <dir>
  --gate ' '`) wrote plane.json with a gate stage whose `cmd` is blank, then crashed with a
  `ConfigError` traceback saying the gate stage needs "a non-empty shell command".
- The verifier's agent definition already says it: "When the product is the control plane itself, check a
  change to `ccp` by hand with your checkout's own `bin/ccp`" (`plugin/agents/delivery-verifier.md`,
  since task 0057). The rendered verify prompt says it only for `verify record`. This task adds the
  general sentence to the prompt, which the verifier reads per run.
- `ccp suite affected` prints module names, one per line (`main_affected` in `ccp/suite.py`). §14.7
  fixes that stdout form, so the command line goes to stderr, after the list.
- §31.1: every SPEC edit below describes this task's own feature or knob, with a neutral default.
  No § rule changes.

## Scope

- **In:**
  - Window. plane.json `usage.advice.window_hours`, an integer >= 0 (default `0`: every request, as
    today; a product sets e.g. `24` for advice from the last day), in `ccp/config.py` (defaults and validation) and `contracts/plane_config.schema.json`.
    `usage.fold` takes `advice_since` (epoch seconds, or None for every request). The cost advice
    (`cost_advice`: the seats' figures, the contexts and the count of worker runs) is computed only
    from requests whose `at` is at or after it. Every other figure `fold` returns is unchanged, and so
    is the design-seat model and effort advice.
  - `ccp usage` (without `--system`): the window starts `window_hours` before now, or at `--since`
    when given. `--since` takes `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`; any other value exits 2. Its help
    becomes "the cost advice's start (default: plane.json usage.advice.window_hours back, every request when
    0); with --system: `YYYY-MM-DD`". The report gains `advice_since` (UTC ISO, or null for every request). Each
    cost advice line ends ` (requests since <advice_since>)`, or ` (every request)` when it is null.
  - `ccp health`: `usage_advice` uses the same window, starting at `--since` when given, else
    `window_hours` back (every request when it is 0). `--json` gains `usage_advice_since`, and each line carries the same suffix.
    The module docstring's sentence on what is not windowed says this instead.
  - `docs/spec/04-observability.md` §24.6 (§31.1): one sentence after its first paragraph: the advice
    reads the requests of the last `usage.advice.window_hours` (default 0: every request), or from
    `--since`, and each line names its start. `docs/spec/01-model.md`: the `usage` row lists
    `window_hours` 0.
  - `docs/cli/04-observability.md`: the `ccp usage` row gains `[--since DATE]` and the window. The
    `ccp health` row names its window: tasks and series from the adoption point, or `--since`; the
    usage advice from `usage.advice.window_hours` back, or `--since`.
  - `ccp/init.py`: a `--gate` value that is blank or only whitespace is refused with exit 2 before
    anything is written: "ccp init: --gate is blank: give the gate lane's command, or leave --gate out".
  - `templates/prompts/verify.md`: one sentence, beside the `wt exec` sentence on `verify record`,
    rendered in every verify prompt (not inside a conditional section). When
    the product's checkout carries its own `bin/ccp` (the product is the control plane), a by-hand
    check of a `ccp` command runs the head's, as `QUEUE_ROOT={{queue_root}} {{ccp}} wt exec
    {{#own_worktree}}{{own_worktree_name}} {{/own_worktree}}-- <args>`. It never runs `ccp` on PATH,
    which runs the released plane.
  - `ccp/suite.py` `main_affected`: with modules found, after the list, one stderr line:
    `ccp suite affected: run them with: ccp suite run --lane <part lane> -- python3 -m unittest <m1> <m2> …`.
    The part lane is `lane_for(cfg, "part")`. The command is named directly for the language
    `package_docs.language` gives (python: `python3 -m unittest`, the only reader today); a language
    with no command named prints no line. stdout is unchanged. §31.1: `docs/spec/02-delivery.md` §14.7 says so in
    one sentence.
  - Tests of the window (`tests/test_usage_advice.py`, `tests/test_usage.py`, `tests/test_health.py`)
    set `window_hours` in their plane.json; tests that pin advice from older fixtures keep passing
    under the default 0. A test that pins the verify template text, if any (`tests/test_prompt*.py`).
- **Out:**
  - The board's advice (`ccp/board.py` calls `fold` without `advice_since`: every request, as now).
  - Saying, in the advice, that a recommended setting is already set.
  - The rotation slots due (Context).

## dod_checks

- id: `adv-01`
  story: As a lead who fixed what the advice named, the advice stops naming it.
  setup: a scratch queue (`tests/helpers.py`) whose `board/usage-requests.jsonl` holds runner requests from three days before now whose cache writes are all 5-minute ones, and runner requests from the last hour whose cache writes are all 1-hour ones; plane.json with `usage.advice.window_hours` 24.
  steps:
    1. Run `ccp usage --json`.
    2. Run `ccp usage --json --since <the date four days before now>`.
    3. Remove the `usage` block from plane.json and run `ccp usage --json`.
  expect: step 1's `advice` holds no line naming 5-minute writes, and its `advice_since` is within a minute of 24 hours before now; step 2's `advice` holds the runner's 5-minute line, ending ` (requests since <that date>T00:00:00Z)`; step 3's `advice_since` is null and its `advice` holds the 5-minute line, ending ` (every request)`.
  dry run: n/a.
- id: `adv-02`
  story: As a lead, health's advice reads the same window, and the docs say so.
  setup: the queue of adv-01, with a product checkout.
  steps:
    1. Run `ccp health --json`, then `ccp health --json --since <the date four days before now>`.
    2. Run `git grep -n window_hours -- docs/cli/04-observability.md`.
  expect: step 1's first `usage_advice` holds no 5-minute line and its second holds it; both carry `usage_advice_since`; step 2 prints at least one line, in the `ccp health` row.
  dry run: n/a.
- id: `init-01`
  story: As a lead adopting, a blank gate is refused before anything is written.
  setup: an empty git repository and an empty queue directory.
  steps:
    1. Run `ccp init --project-id demo --queue-root <queue> --gate ' '`.
  expect: exit 2; stderr holds "--gate is blank" and no traceback; no `docs/delivery/plane.json` and no binding exist.
  dry run (`85d388b`): plane.json written, then a `ConfigError` traceback.
- id: `prompt-01`
  story: As a verifier of a ccp change, I am told to check by hand with the head's ccp.
  setup: a scratch product with a task ready for verify.
  steps:
    1. Render `ccp prompt verify <task> --pr <n> --head <sha>`.
  expect: the prompt holds `wt exec` twice, once in the `verify record` sentence and once in the by-hand sentence, which names `bin/ccp` and "never runs `ccp` on PATH"; the by-hand sentence renders whatever the product, since it sits in no conditional section.
  dry run: n/a.
- id: `aff-01`
  story: As a worker, `suite affected` hands me the command to run.
  setup: a scratch Python product with `pkg/a.py` and `tests/test_a.py` importing it, and no `suite.roles`.
  steps:
    1. Run `ccp suite affected --paths pkg/a.py`.
  expect: stdout is exactly `tests.test_a`; stderr holds `ccp suite run --lane part -- python3 -m unittest tests.test_a`.
  dry run (`85d388b`, this repo, `--paths ccp/upgrade.py`): stdout one module per line, no command line on stderr.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
