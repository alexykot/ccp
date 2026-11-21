---
task_id: 0222-a-product-without-github-uses-the-local-pr-host
title: A product names its PR host in plane.json, and the local adapter serves one with only a git origin
status: pending
kind: feature
depends_on: ["0221-workers-reach-the-pr-host-through-ccp-pr", "0226-one-pr-host-module-github-only"]
spec_refs: ["S4", "S8", "S15"]
adr_refs: ["0040 D3", "0040 D5"]
review_point: R15
paths: ["ccp/prhost.py", "ccp/config.py", "ccp/init.py", "contracts/plane_config.schema.json", "contracts/pr_record.schema.json", "docs/spec/01-model.md", "docs/adr/0040-the-pr-host-is-an-adapter.md", "README.md", "tests/test_prhost_local.py", "tests/test_init_permissions.py"]
adopt: "plane.json pr_host.adapter: local, for a product whose origin is not on GitHub"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0222-a-product-without-github-uses-the-local-pr-host

## Intent

After 0220 and 0221 every PR-host call goes through one interface, but GitHub is still its only
adapter, so a product whose origin is a bare repository, or a server the plane has no adapter for,
adopts and then fails at its first PR. After this task a product names its adapter in plane.json as
`pr_host.adapter`: `github`, the default, keeps today's behaviour; `local` keeps the PR record in the
product's queue and merges with git alone, so the whole loop runs with nothing but an origin the
plane can push to. `ccp init` warns only when the origin does not suit the adapter named, and the
permission list allows `gh pr` only under the GitHub adapter.

## Context (not checked)

Measured at `1b734dd`.

- Builds ADR-0040 D3 (the local adapter) and D5 (a product selects its adapter). D4 (GitLab and
  Gitea) is a later decision and stays `not_built`. Depends on 0221, which completes the interface
  (`ccp pr edit` included) that the local adapter must serve.
- **The init warning.** `ccp/init.py` `def github_warning` warns when the origin is missing or not on
  GitHub, naming `GITHUB_ONLY` (`git grep -n 'GITHUB_ONLY' -- ccp/init.py` at `1b734dd`: two lines,
  the tuple and its use). §4.5 says review, merge and close need a GitHub origin "until the PR host
  adapter of ADR-0040 exists".
- **The permission list.** `ccp/init.py` `def permissions` appends `_rule("gh pr")` unconditionally
  (`git grep -n '_rule("gh pr")' -- ccp/init.py` at `1b734dd`: one line), and §4.5 lists `gh pr`.
- **plane.json.** `contracts/plane_config.schema.json` has no `pr_host` key
  (`grep -c pr_host contracts/plane_config.schema.json` at `1b734dd`: 0); §8.1's block table lists
  `merge` with `worktrees`, `env` and `auth_check`.
- **Close's merge worktree.** `lifecycle._merge_path` gives the task's `merge-<nnnn>` worktree (§10.5),
  which close already uses for its reconcile; the local merge runs there.
- **The squash subject** is the one §10.7's first rule reads to tie a merge to its task:
  `Task <NNNN>: <title> (#<n>)`.
- **Shaped** by `sh-20261120T235116Z-eb9f`. Two of its decisions are the operator's and this brief is
  written on the recommended answers; it is revised and signed again if an answer differs:
  - F02: the local record keeps the PR's title and body, and serves `edit`, so the §15.2 body gate
    works under either adapter (recommended: yes);
  - F06: where the adapter key lives (recommended: `pr_host.adapter`, as ADR-0040 D5 decided, with
    `merge.command` still overriding the merge, and ADR-0029 D1's merge-strategy interface superseded
    by ADR-0040 so the merge has no third knob).
  F04 (the test fixture's fake `gh` replaced by this adapter) is task 0227.
- §15.5 after 0220 names the interface's operations generically; this task adds no §15.5 text, so it
  does not quote 0220's PROPOSED text as CURRENT.

## Scope

- **In:** `ccp/prhost.py`, `ccp/config.py`, `ccp/init.py`, `contracts/plane_config.schema.json`,
  `contracts/pr_record.schema.json` (new), `docs/spec/01-model.md`,
  `docs/adr/0040-the-pr-host-is-an-adapter.md`, `README.md`, `tests/test_prhost_local.py` (new),
  `tests/test_init_permissions.py`.
- **`pr_host.adapter`** in plane.json: `github` (default) or `local`; any other value is refused by
  plane.json validation, naming the two. `prhost.adapter(cfg)` returns the one named. `merge.command`
  still overrides the merge under either.
- **The local adapter.** Its record is `QUEUE_ROOT/prs/<n>.json` (`contracts/pr_record.schema.json`):
  `number`, `branch`, `base`, `title`, `body`, `head` (last seen), `state` (`OPEN`, `MERGED`,
  `CLOSED`), `opened_at`, `merged_at`, `merge_commit`. Numbers are given by the plane, one more than
  the highest held, under `prs/.lock`.
  - **open** refuses a branch not on `origin`, or one with an open record already (naming its
    number), and writes the record;
  - **view** fetches and reads `head` from `origin/<branch>`, updating the record;
  - **diff** is `git diff origin/<base>...<head>`;
  - **edit** replaces the body;
  - **merge** refuses unless the record is open and `origin/<branch>` is the given head; in close's
    merge worktree, detached at `origin/<base>`, it runs `git merge --squash <head>`, commits with
    the subject `Task <NNNN>: <title> (#<n>)` (the task's title from its file) and pushes to
    `<base>`; a push refused because the tip moved is an error naming the rerun of close, with
    nothing recorded merged;
  - **confirm** returns the merge commit when it is on `origin/<base>`, recording `MERGED`.
- **`ccp init`.** Under `github` its warning is as today. Under `local` it warns only when the product
  has no origin, naming the commands that need one. `ccp init --permissions` allows `gh pr` only
  under `github`.
- **README:** the prerequisites and the "PR hosts other than GitHub" limitation say that a product
  without GitHub sets `pr_host.adapter: local`, and that its PRs are then visible only in the queue.
- ADR-0040: D3 and D5 recorded `built`.
- **Tests** in `tests/test_prhost_local.py` (new), on a temp product with a bare origin and a temp
  queue: open, view, diff, edit, merge and confirm of one task branch, the squash commit's subject
  and the record's `MERGED` state; merge refusing a head that is not the branch's; open refusing a
  second record for one branch. In `tests/test_init_permissions.py`: `gh pr` allowed under `github`,
  absent under `local`.

### SPEC changes (signed in the brief, §31)

**a. §4.5, the init warning.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> adopts it all the same: review, merge and close need a GitHub origin until the PR host adapter of
> ADR-0040 exists.

PROPOSED:
> adopts it all the same: under plane.json `pr_host.adapter` `github` (the default), review, merge
> and close need a GitHub origin. Under `local` it warns only when the product has no origin: the
> local adapter keeps each PR's record in the queue (`prs/<n>.json`) and merges by a squash commit,
> subject `Task <NNNN>: <title> (#<n>)`, pushed from close's merge worktree (ADR-0040 D3).

**b. §4.5, the permission list.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
>     absolute path, each of the three also behind the binding's `QUEUE_ROOT=`; git by verb; `gh pr`;
>     and the gate lane's commands;

PROPOSED:
>     absolute path, each of the three also behind the binding's `QUEUE_ROOT=`; git by verb; `gh pr`
>     only under the GitHub adapter (`pr_host.adapter`); and the gate lane's commands;

**c. §8.1, the block table.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> | `worktrees`, `env`, `merge`, `auth_check` | worktree links and environment hooks (`ccp wt`), the merge step (`merge.command`) and the paths that do not make a head behind the tip (`merge.behind_tip_ignore`), credential probes (`auth_check.probes`) | §12, §15, §16, §30 |

PROPOSED:
> | `worktrees`, `env`, `merge`, `auth_check` | worktree links and environment hooks (`ccp wt`), the merge step (`merge.command`) and the paths that do not make a head behind the tip (`merge.behind_tip_ignore`), credential probes (`auth_check.probes`) | §12, §15, §16, §30 |
> | `pr_host` | the PR host's adapter (`adapter`: `github`, the default, or `local`, ADR-0040 D5) | §4.5, §15.5 |

- **Out:** GitLab and Gitea adapters (ADR-0040 D4), repository settings (ADR-0029 D3), a web view of
  local PRs, and moving an adopted product's open PRs between adapters.

## dod_checks

- id: `lh-01`
  story: As a lead of a product without GitHub, a task's PR opens, merges and is confirmed with git alone.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_prhost_local 2>&1 | tail -15`.
  expect: exit 0, with the Scope's local-adapter tests listed `ok`.
  dry run: n/a — the module is new.

- id: `lh-02`
  story: As a plane developer, the head pin of the local merge bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    local merge no longer compares `origin/<branch>` with the given head.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_prhost_local`.
  expect: at least one failure (the merge of a head that is not the branch's).
  dry run: n/a — the module is new.

- id: `lh-03`
  story: As an operator, the permission list follows the adapter.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_init_permissions 2>&1 | tail -3`.
  expect: exit 0, `OK`, the Scope's two permission tests among them.
  dry run (`1b734dd`): `OK`; the new tests do not exist yet.

- id: `lh-04`
  story: As a product, an unknown adapter is refused before anything runs.
  setup: a checkout of the PR head; a copy of it (`git worktree add --detach <tmp> HEAD`) whose
    `docs/delivery/plane.json` gains `"pr_host": {"adapter": "forge"}`; QUEUE_ROOT a fresh temp directory.
  steps:
    1. Run `<tmp>/bin/ccp --root <tmp> tasks list >/dev/null; echo rc=$?`.
  expect: stderr names `pr_host.adapter` and the values `github` and `local`, and the exit is not 0.
  dry run (`1b734dd`): `rc=0`, with a warning that the unknown key `pr_host` is ignored.

- id: `lh-05`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0222 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`1b734dd`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
