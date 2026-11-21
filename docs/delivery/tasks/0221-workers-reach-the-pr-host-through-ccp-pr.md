---
task_id: 0221-workers-reach-the-pr-host-through-ccp-pr
title: The worker prompts and the runner's brief reach the PR host through ccp pr, never gh
status: pending
kind: feature
depends_on: ["0220-one-pr-host-interface-with-the-github-adapter", "0240-plane-workers-run-the-head"]
clashes_with: ["0212-full-role-runs-the-gate-lane-and-a-pregate-lane", "0223-a-follow-up-is-tracked-not-left-in-notes", "0228-report-sections-as-one-table", "0233-briefs-point-at-the-evidence-rules"]
spec_refs: ["S13", "S18"]
adr_refs: ["0040 D1", "0040 D6"]
review_point: R15
paths: ["templates/prompts/_common.md", "templates/prompts/implement.md", "templates/prompts/review.md", "templates/prompts/verify.md", "plugin/agents/delivery-runner.md", "ccp/prompt.py", "docs/delivery/plane.json", "docs/ENGINEERING.md", "docs/spec/02-delivery.md", "docs/adr/0040-the-pr-host-is-an-adapter.md", "tests/test_prhost_only.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0221-workers-reach-the-pr-host-through-ccp-pr

## Intent

After 0220 the plane's own code reaches the PR host through one interface, but the worker prompts
and the runner's brief still tell each seat to run `gh pr diff`, `gh pr view` and `gh pr edit`. A
prompt that names a forge's CLI fails on any other host, and the runner's permissions must allow
`gh`. After this task every prompt and the runner's brief use `ccp pr`, so they read the same
whatever the host, and a test keeps a forge's CLI out of everything outside the adapter.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0040 D6 (the forge-independent parts never call the host) and completes D1's "the worker
  prompts call it through `ccp pr`". Depends on 0220, which adds `ccp pr`, and on R16's 0240, which
  renders every `ccp` a worker prompt names as `{{ccp}}` (`ccp wt exec --` for the plane): the prompts
  here write `{{ccp}} pr …`, so the rendered command is the head's `ccp`.
- **Clash with 0223**, which edits `templates/prompts/implement.md`'s one long instruction line too.
- **Where `gh` is named.** `git grep -n 'gh pr' -- templates plugin` at `8aefa59`: five lines, in
  `templates/prompts/_common.md` (the PR-number rule), `templates/prompts/review.md` (`gh pr diff
  {{pr}}`), `templates/prompts/verify.md` (`gh pr diff`, and `gh pr view {{pr}} --json headRefOid` at
  start and end) and `plugin/agents/delivery-runner.md` (`gh pr edit <n> --body-file <file>` to repair
  a PR body). `templates/prompts/implement.md` says "Open a PR to {{integration}} titled …" without
  naming a tool.
- **A PR body edit.** `ccp pr edit` comes with 0220 (the shape's F02, on its recommended answer);
  `prompt.body_gate`'s refusal still names `gh pr edit`, and this task makes it name `ccp pr edit`.
- **Shaped** by `sh-20261120T235116Z-eb9f`: F07's prompt half (prompts name `ccp pr <op> <n>`, which
  always takes the number, so `_common.md`'s rule about `gh`'s default PR goes) and the check of the
  new house rule E19, which this task adds to `architect.checks` once it passes.
- **A runner contract change.** The runner's brief changes, so the release is followed by a runner
  rotation (§29.3, ADR-0040 Consequences).
- §18.5 lists `gh` among the commands pre-approved for the runner.
- The permission list (`ccp init --permissions`, §4.5) keeps `gh pr` for the GitHub adapter; 0222
  makes it follow the adapter.

## Scope

- **In:** `templates/prompts/_common.md`, `templates/prompts/implement.md`,
  `templates/prompts/review.md`, `templates/prompts/verify.md`, `plugin/agents/delivery-runner.md`,
  `ccp/prompt.py`, `docs/delivery/plane.json`, `docs/ENGINEERING.md`, `docs/spec/02-delivery.md`,
  `docs/adr/0040-the-pr-host-is-an-adapter.md`, `tests/test_prhost_only.py` (new).
- **The prompts:** review reads `{{ccp}} pr diff {{pr}}`; verify reads `{{ccp}} pr diff {{pr}}` and checks
  `{{ccp}} pr view {{pr}} --json` (its `head`) at start and end; implement opens its PR with `{{ccp}} pr open
  --branch task/{{task_id}} --title "Task {{nnnn}}: <short title>" --body-file <file>`; `_common.md`'s
  rule about `gh pr edit` and `gh pr view` taking the PR number is removed (`ccp pr` always takes it).
- **The runner's brief** repairs a body with `ccp pr edit <n> --body-file <file>`.
- `body_gate`'s refusal names `ccp pr edit <n> --body-file <file>`.
- `docs/delivery/plane.json` `architect.checks` gains `{"id": "E19", "cmd": …}` with house rule E19's
  two commands, and E19's `check:` line in `docs/ENGINEERING.md` becomes `command`.
- ADR-0040: D6 recorded `built`.
- **`tests/test_prhost_only.py`** (new), the D6 house check:
  - no line of `templates/prompts/*.md` or `plugin/agents/*.md` names `gh pr` or `gh api`;
  - no `ccp/*.py` other than `ccp/prhost.py` and `ccp/init.py` (the permission list and the init
    warning, 0222) holds the string literal `"gh"` or reads `CCP_GH_BIN`;
  - each rendered prompt (implement, review, verify) for a fixture task holds the rendered `ccp`
    command (the prompt's `ccp` value) followed by ` pr ` and `diff`, `view` or `open`.

### SPEC changes (signed in the brief, §31)

**a. §18.5, the pre-approved commands.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> before a run the runner's commands (tests, `ccp`, `gh`, git by path, the product's operator commands)
> are pre-approved in the product's settings.

PROPOSED:
> before a run the runner's commands (tests, `ccp`, git by path, the product's operator commands)
> are pre-approved in the product's settings. The runner and the workers reach the PR host only
> through `ccp pr` (ADR-0040 D1), never a forge's CLI.

- **Out:** the permission list and `pr_host.adapter` (0222), the local adapter (0222), and the
  README's prerequisites, which change with 0222.

## dod_checks

- id: `pc-01`
  story: As a plane developer, nothing outside the adapter names a forge's CLI.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prhost_only 2>&1 | tail -10`.
  expect: exit 0, with the Scope's three tests listed `ok`.
  dry run: n/a — the module is new.

- id: `pc-02`
  story: As a plane developer, the house check bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    `templates/prompts/review.md` reads `gh pr diff {{pr}}` again.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_prhost_only`.
  expect: at least one failure, naming `templates/prompts/review.md`.
  dry run: n/a — the module is new.

- id: `pc-03`
  story: As a worker, my prompt names `ccp pr`, not `gh`.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'gh pr' -- templates/prompts plugin/agents`.
  expect: prints nothing.
  dry run (`1b734dd`): five lines (`_common.md`, `review.md`, `verify.md` twice, `delivery-runner.md`).

- id: `pc-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0221 --base origin/main`.
  expect: exit 0, the passage found.
  dry run (`1b734dd`): exit 1, the passage not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- Premise re-run at `58546f7`: `git grep -n 'gh pr' -- templates plugin` gives the same five lines;
  `ccp/*.py` holds the literal `"gh"` and `CCP_GH_BIN` only in `ccp/prhost.py`.
- The prompts name `{{ccp}} pr diff|view|open`; the implementer's `pr open` carries
  `QUEUE_ROOT={{queue_root}}`, which `ccp pr open` needs. Verify reads `{{ccp}} pr view {{pr}} --json`
  and its `head` field in place of `headRefOid`. `_common.md`'s PR-number rule is removed.
- `architect.checks` `E19` keeps one entry and runs both commands, joined with `&&`; E19's `check:`
  line names both.
- `tests/test_prhost_only.py` scans `ccp/**/*.py` (subpackages included) for a string constant equal
  to `gh` or naming `CCP_GH_BIN`, by AST, so a docstring naming the override counts too; the prompt and
  brief scan matches `gh pr` or `gh api` as a command, not inside a longer word.
- `tests/test_resolution_review.py` pins the review prompt's diff command as the rendered `ccp` value's
  `pr diff 7`, and `tests/test_prompt_pr_body.py` pins the body gate's repair as `ccp pr edit 7`.

## Verification notes
