---
task_id: 0220-one-pr-host-interface-with-the-github-adapter
title: The PR-host interface is ccp pr, and the SPEC names its operations instead of gh
status: pending
kind: feature
depends_on: ["0226-one-pr-host-module-github-only"]
spec_refs: ["S10", "S15"]
adr_refs: ["0040 D1", "0040 D2"]
review_point: R15
paths: ["ccp/prhost.py", "ccp/cli.py", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "docs/adr/0040-the-pr-host-is-an-adapter.md", "tests/test_prhost_cli.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0220-one-pr-host-interface-with-the-github-adapter

## Intent

Once its refactor lands, the plane's own code reaches GitHub through one module. This task makes that module the
PR-host interface of ADR-0040 for everyone: `ccp pr open|view|diff|edit|merge` give workers and the
runner the same operations whatever the host, and §15.5 names those operations rather than `gh`
commands. On a GitHub product nothing behaves differently.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0040 D1 (one interface) and D2 (the GitHub adapter behind it; its code moved in 0226,
  a refactor, which cites no ADR). D3 and D5 are 0222, D6 is 0221, D4 (GitLab, Gitea) is a later
  decision and is not tasked.
- **Shaped** by `sh-20261120T235116Z-eb9f`. F02 asks the operator whether `view` also returns the
  merge time, the branch and the body, and whether `edit` (the PR body) is a sixth operation, as the
  §15.2 body gate and the runner's body repair need. This brief is written on the recommended answer
  (both yes); if the operator answers otherwise, the brief is revised and signed again. F07's SPEC
  half is here: §15.5 stops restating the GitHub argv (house rule E10).
- F03 (retiring `ccp verify check`) is the operator's to decide; this task leaves the command and
  only stops saying "no `gh`".
- §15.5 names `gh` four times (`grep -n '`gh' docs/spec/02-delivery.md` at `8aefa59`: five lines,
  four in §15.5, one in §18.5, which 0221 changes).

## Scope

- **In:** `ccp/prhost.py`, `ccp/cli.py`, `docs/spec/02-delivery.md`, `docs/cli/02-delivery.md`,
  `docs/adr/0040-the-pr-host-is-an-adapter.md`, `tests/test_prhost_cli.py` (new).
- **The interface** in `ccp/prhost.py` gains `open(cfg, branch, base, title, body) -> int`,
  `diff(cfg, pr) -> str` and `edit(cfg, pr, body)` beside 0226's `view`, `merge` and `confirm`; the
  GitHub adapter serves them with `gh pr create`, `gh pr diff` and `gh pr edit --body-file`.
- **`ccp pr open --branch <b> --title <t> --body-file <f>` | `view <pr> [--json]` | `diff <pr>` |
  `edit <pr> --body-file <f>` | `merge <pr> --head <sha> --task <id>`**: thin commands over the
  interface; each takes the PR number, never the current branch's PR. Exit 0 on success, 1 on a host
  error naming it, 2 on a usage error. `view --json` prints `PrFacts`.
- `docs/cli/02-delivery.md` gains the rows, and its `ccp verify check` row reads "a merge step that
  does not read the PR host" (it says "a merge step without `gh`"); ADR-0040 D1 and D2 recorded
  `built`. If the operator accepts F02's sixth operation, the lead amends ADR-0040 D1 (`ccp adr`)
  before this task is claimed.
- **Tests** in `tests/test_prhost_cli.py` (new), a stub `gh` on `CCP_GH_BIN` logging its argv: each
  command's argv and output, a missing binary exiting 1, `view 7 --json` printing the facts.

### SPEC changes (signed in the brief, §31)

**a. §15.5, the merge paragraph.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> `{task_id}`; null means `gh pr merge {pr} --squash --match-head-commit {head_sha}`, with the PR's full
> head `merge-ok` prints (`match_head_commit`). Close confirms the PR merged through `gh` (the merge
> commit is the one `gh pr view` names; a merge `gh` accepts without merging, such as a merge queue,
> stops it). `merge-ok` reads the PR with `gh` and refuses unless the PR is open, its head is the

PROPOSED:
> `{task_id}`; null means the PR host's merge, pinned to the PR's full head `merge-ok` prints
> (`match_head_commit`). Close confirms the merge through the PR host (the merge commit is the one the
> host names; a merge the host accepts without merging, such as a merge queue, stops it). The plane
> reaches the PR host only through one interface (open, view, diff, edit, merge, confirm; ADR-0040),
> which workers and the runner use as `ccp pr open|view|diff|edit|merge`, each given the PR number
> except open, never a forge's CLI. `merge-ok`
> reads the PR through the host and refuses unless the PR is open, its head is the

**b. §15.5, its last sentence.**

CURRENT (`docs/spec/02-delivery.md` at `8aefa59`):
> approved in `verification/pr-<n>.json`, whose verdict's `task_id` is exactly `pr-<n>`. `ccp verify
> check <task_id> --head <sha>` serves a merge step that has no `gh`.

PROPOSED:
> approved in `verification/pr-<n>.json`, whose verdict's `task_id` is exactly `pr-<n>`. `ccp verify
> check <task_id> --head <sha>` serves a merge step that does not read the PR host.

- **Out:** the prompts and agents (0221), the local adapter and `pr_host` selection (0222), the test
  fixture's fake `gh` (0227), retiring `ccp verify check` (the operator's decision), and ADR-0029
  D3's repository settings.

## dod_checks

- id: `ph-01`
  story: As a worker, `ccp pr` gives me the PR whatever the host.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prhost_cli 2>&1 | tail -15`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `ph-02`
  story: As a runner, `ccp pr` refuses a call without a PR number.
  setup: a checkout of the PR head; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `bin/ccp --root . pr view; echo rc=$?`.
  expect: prints a usage error naming the PR number and `rc=2`.
  dry run (`8aefa59`): `rc=2`, argparse refusing `pr` as a command.

- id: `ph-03`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0220 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
