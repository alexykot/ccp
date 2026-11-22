---
task_id: 0266-github-knowledge-stays-in-the-pr-host-module
title: A PR's head is fetched through the PR-host module, init grants no gh pr, and close's messages name the PR host
status: pending
kind: feature
depends_on: []
clashes_with: ["0254-close-and-architect-share-the-unrecorded-worktree-helper", "0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events"]
spec_refs: ["S4", "S15", "S18"]
adr_refs: ["0040 D5"]
review_refs: ["ar-20261121T174754Z-7df5#F02", "ar-20261121T174754Z-7df5#F03"]
rule_refs: ["E19"]
review_point: R21
paths: ["ccp/prhost.py", "ccp/lifecycle.py", "ccp/prompt.py", "ccp/verify.py", "ccp/init.py", "docs/delivery/plane.json", "docs/spec/01-model.md", "docs/adr/0040-the-pr-host-is-an-adapter.md", "README.md", "tests/test_prhost_fetch.py", "tests/test_init.py", "tests/test_init_permissions.py", "tests/test_tasks_close.py", "tests/test_verify.py"]
adopt: ".claude/settings.json permissions.allow: remove `Bash(gh pr:*)` where `ccp init --permissions` put it"
sign_off: brief
created: 2026-11-21
updated: 2026-11-21
---

# Task: 0266-github-knowledge-stays-in-the-pr-host-module

## Intent

Only the PR-host module knows how a forge lays out a PR's refs: a step that needs a PR's head
commit asks the module, which fetches the adapter's own ref and then the task branch, so the local
adapter never tries a GitHub ref that cannot exist. The runner's and workers' permission block grants
no forge CLI, since every worker step reaches the host through `ccp pr`, and init's GitHub warning
names the commands that really need GitHub. Close's and merge-ok's messages name the PR host and its
adapter, never `gh`, so an operator on the local adapter is not told about a tool it does not use.

## Context (not checked)

From architect pass `ar-20261121T174754Z-7df5`, findings F02 and F03 (the record is in
`docs/delivery/reviews/`), and two follow-ups of 0222 from the lead's log. Measured at `afb8ce6` (the figures below match `31357f0`, where the dry runs ran).

- **F02, three copies of a GitHub fetch.** `git grep -n 'refs/pull' -- ccp plugin templates scripts`
  at `31357f0`: 3 lines, one loop each in `ccp/lifecycle.py` `"def behind_tip"`, `ccp/prompt.py`
  `"def resolution_gate"` and `ccp/verify.py` `"def _judge_fix"`: `for ref in
  ([f"refs/pull/{pr}/head"] if pr else []) + [f"task/{tid}"]:` then `git fetch -q origin <ref>` until
  `git cat-file -e <sha>^{commit}` holds. Under the local adapter (0222) `refs/pull/…` never exists.
  Ruling: `ccp/prhost.py` gains `def fetch_commit(cfg, root, sha, pr, branch) -> bool`: True at once
  when `sha` is a commit in `root`; else it fetches from `origin`, in order, the adapter's own refs
  for `pr` (a method on each adapter: GitHub `refs/pull/<pr>/head`; Local none, its PR's head is on
  its branch) and then `branch`, stopping when `sha` is there; False when it never is. `pr` None or
  empty skips the adapter's refs. The three sites call it with the branch they use today
  (`task/<id>`) and keep their own error on False. House rule E19's text names the ref layout (the
  triage applied it); its `architect.checks` entry gains the third grep here.
- **F03, a grant no step uses** (a rule-cost finding; the operator's question in the review record).
  `git grep -nE '\bgh\b' -- plugin templates` at `31357f0`: nothing. `git grep -n 'gh pr' -- ccp/init.py`
  at `31357f0`: 3 lines (the `GITHUB_ONLY` warning entry, the `"def permissions"` docstring and its
  `allow.append(_rule("gh pr"))` under the GitHub adapter). Close and merge-ok call `gh` from inside
  `ccp` (`ccp/prhost.py` `GitHub`), which the Bash allowlist does not gate. The threat model names a
  seat holding `gh pr` as a way around the pinned merge. Ruling (the operator's to sign, the triage's
  recommendation): the permission block grants no `gh` entry under any adapter, and `GITHUB_ONLY`'s
  third entry becomes "`ccp pr` (open, view, diff, edit, merge)". The README's permission paragraph
  (`git grep -n 'gh pr' -- README.md` at `31357f0`: 1 line) loses its `gh pr` clause.
- **0222 follow-up, close's messages.**
  `git grep -nwP 'gh' -- ccp/lifecycle.py ccp/verify.py ccp/prompt.py` at `31357f0`: 6 lines (three close messages in `ccp/lifecycle.py`, merge-ok's unavailable message
  and the usage docstring in `ccp/verify.py`, and `ccp/prompt.py`'s module docstring). Ruling: each
  message names the host as `the PR host (<adapter>)`, `<adapter>` being plane.json `pr_host.adapter`
  as `cfg` holds it: `the PR host (<adapter>) did not merge PR <n>: …`, `the PR host (<adapter>)
  merged PR <n> without error, but it is <STATE> (a merge queue or auto-merge?): …`, `PR <n> is merged
  but the PR host (<adapter>) names no merge commit`, and merge-ok's `…: merge-ok reads the PR from the
  PR host (<adapter>)`. The two docstrings say "the PR host".
- **Tests this breaks** (measured by `git grep -n` at `31357f0` for each changed string):
  `tests/test_init.py` (`"gh pr"` among the GitHub warning's commands), `tests/test_init_permissions.py`
  (`Bash(gh pr:*)` three times), `tests/test_tasks_close.py` (`exited 0 but the PR is OPEN`),
  `tests/test_verify.py` (`merge-ok reads the PR with gh`).
- **Not here:** the threat model's "a seat holding `gh pr` or `git push`" sentences stay true as
  written; the local PR record's state words and ledger events are 0268's (a clash: both change
  `ccp/prhost.py`).

## Scope

- **In:**
  - `ccp/prhost.py` (`fetch_commit` and each adapter's head refs), `ccp/lifecycle.py`
    (`behind_tip`, close's merge messages), `ccp/prompt.py` (`resolution_gate`, the docstring),
    `ccp/verify.py` (`_judge_fix`, merge-ok's message, the docstring).
  - `ccp/init.py` (`permissions`, `GITHUB_ONLY`), `README.md` (the permission paragraph).
  - `docs/delivery/plane.json` (`architect.checks` `E19` gains `&& ! git grep -n 'refs/pull' -- ccp ':(exclude)ccp/prhost.py'`).
  - `tests/test_prhost_fetch.py` (new), and the four test modules named in Context.
- **SPEC, signed before the claim (`sign_off: brief`):** `docs/spec/01-model.md` §4.5, the
  permission list's allowlist bullet, replaced.

    CURRENT (`docs/spec/01-model.md` at `31357f0`), §4.5, The permission list, first sub-bullet:
    > an allowlist: `ccp` by name (§4.3), and the plane's `team.sh` and `spec-maintainer-ask.sh` by absolute path, each of the three also behind the binding's `QUEUE_ROOT=`; git by verb; `gh pr` only under the GitHub adapter (`pr_host.adapter`); and the gate lane's commands;

    PROPOSED:
    > an allowlist: `ccp` by name (§4.3), and the plane's `team.sh` and `spec-maintainer-ask.sh` by absolute path, each of the three also behind the binding's `QUEUE_ROOT=`; git by verb; and the gate lane's commands. It grants no forge CLI under any adapter: the workers reach the PR host through `ccp pr` (§15.5);
- **ADR-0040, amended on the same sign-off:** its Consequences' third bullet, and a line in its
  `notes` naming this task and the operator's sign-off.

    CURRENT (`docs/adr/0040-the-pr-host-is-an-adapter.md` at `31357f0`), Consequences, third bullet:
    > §10.5 and §15.5 name the interface's operations instead of `gh`; `ccp init --permissions` allows `ccp pr` and, for the GitHub adapter, keeps `gh pr`.

    PROPOSED:
    > §10.5 and §15.5 name the interface's operations instead of `gh`; `ccp init --permissions` allows `ccp pr` and grants no forge CLI under any adapter.
- **Out:** the threat model; `merge.command` (an operator's own override may still call `gh`);
  the local PR record (0268).

## dod_checks

- id: `pr-01`
  story: As a plane developer, no module but the PR host names a forge's PR ref, and E19's command check says so.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'refs/pull' -- ccp ':(exclude)ccp/prhost.py'`.
    2. Run `python3 -B -c "import json; print({c['id']: c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks']}['E19'])" | grep -c refs/pull`.
    3. Run `sh -c "$(python3 -B -c "import json; print({c['id']: c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks']}['E19'])")"; echo "exit $?"`.
  expect: step 1 prints nothing (exit 1); step 2 prints `1`; step 3 prints `exit 0`.
  dry run (`31357f0`): step 1 printed 3 lines (`ccp/lifecycle.py:1445`, `ccp/prompt.py:542`, `ccp/verify.py:751`); step 2 printed `0`; step 3 printed `exit 0`.
- id: `pr-02`
  story: As a runner on either adapter, a head that is not in my checkout is fetched from the PR's own ref or the task branch, and the three steps that need it behave as before.
  setup: A checkout of the PR head; then a separate copy of it where `fetch_commit` skips `branch`.
  steps:
    1. On the head, run `python3 -B -m unittest -v tests.test_prhost_fetch 2>&1 | tail -8`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_prhost_fetch`.
    3. On the head, run `python3 -B -m unittest -q tests.test_behind_tip_catch_up tests.test_resolution_review tests.test_review_skip_clean`.
  expect: step 1 exits 0, listing as `ok` tests on a fenced bare origin that: under the GitHub adapter a commit only on `refs/pull/7/head` is fetched; under the local adapter a commit only on `task/<id>` is fetched and no `refs/pull` fetch is run; a commit on neither gives False. Step 2 exits non-zero. Step 3 exits 0.
  dry run (`31357f0`): steps 1 and 2 n/a — the module is new; step 3 exited 0 (`OK`).
- id: `pr-03`
  story: As an operator, the permission block grants no gh, and init's GitHub warning names the commands that need GitHub.
  setup: A checkout of the PR head; then a separate copy of it where `permissions` appends `_rule("gh pr")` again under the GitHub adapter.
  steps:
    1. Run `git grep -n 'gh pr' -- ccp/init.py README.md`.
    2. On the head, run `python3 -B -m unittest -q tests.test_init_permissions tests.test_init`.
    3. In the copy, run `python3 -B -m unittest -q tests.test_init_permissions`.
  expect: step 1 prints nothing (exit 1); step 2 exits 0; step 3 exits non-zero.
  dry run (`31357f0`): step 1 printed 4 lines (`ccp/init.py:150`, `:602`, `:610`, `README.md:275`); step 2 exited 0 (`OK`); step 3 n/a until the head exists.
- id: `pr-04`
  story: As an operator on the local adapter, close and merge-ok name the PR host they used, never gh.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nwP 'gh' -- ccp/lifecycle.py ccp/verify.py ccp/prompt.py`.
    2. Run `python3 -B -m unittest -q tests.test_tasks_close tests.test_verify`.
    3. Run `git grep -c 'PR host (local)' -- tests/test_tasks_close.py`.
  expect: step 1 prints nothing (exit 1); step 2 exits 0; step 3 prints `tests/test_tasks_close.py:` and a count of at least 1.
  dry run (`31357f0`): step 1 printed 6 lines; step 2 exited 0 (`OK`); step 3 printed nothing (exit 1).
- id: `spec-01`
  story: As the operator, §4.5 and ADR-0040 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0266`.
  expect: exit 0, both PROPOSED passages found (the first in `docs/spec/01-model.md`, the second in `docs/adr/0040-the-pr-host-is-an-adapter.md`).
  dry run (simulated: this task file and both passages applied, committed in a scratch worktree off `31357f0`, `--base` the commit holding the task file): `"ok": true`, exit 0; the first passage found in `docs/spec/01-model.md`, the second in `docs/adr/0040-the-pr-host-is-an-adapter.md`.

## Implementation notes

- `ccp/prhost.py`: `fetch_commit(cfg, root, sha, pr, branch)` as ruled; each adapter has a static
  `head_refs(pr)` (GitHub `refs/pull/<pr>/head`, Local none). `adapter_name(cfg)` reads plane.json
  `pr_host.adapter` once, for `adapter()` and for `label(cfg)`, which renders `the PR host (<adapter>)`
  for close's and merge-ok's messages.
- `behind_tip`, `resolution_gate` and `_judge_fix` call `fetch_commit` with `task/<id>` and keep their
  own error on False; `_judge_fix` still rev-parses for the full sha.
- `permissions` grants no `gh` entry; `GITHUB_ONLY`'s third entry is "`ccp pr` (open, view, diff, edit,
  merge)". The README clause is removed; nothing added in its place.
- Measured at `3ea3a7aa`: `git grep -nwP 'gh' -- ccp/lifecycle.py ccp/verify.py ccp/prompt.py` printed
  5 lines, not 6: `ccp/verify.py`'s usage docstring no longer names `gh`. The other premises matched.
- `tests/test_prhost_only.py` still lists `ccp/init.py` among the modules allowed to name the forge CLI
  (its `DENY` keeps `gh repo delete`); left as it is (not in Scope).

## Verification notes
