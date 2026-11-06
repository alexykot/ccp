# Roadmap

Where CCP (Claude Control Plane) is heading, and what is done. The SPEC (`SPEC.md`) is normative; this file is
the plan. Update it in the same PR as the work it describes.

## Principle

**The plane owns formats, lifecycles and mechanisms. A project supplies content, conventions
(config) and environment (hooks).**

- The plane never parses product text. A product declares a fact in config, or reports it as JSON.
- An action the plane needs from the product is a **hook** with a defined context, timeout and
  failure behaviour, never an instruction in prompt prose.
- Plane formats (task files, ADRs, house rules) are canonical and documented. Projects adapt to them.
- **One home per fact:**
  - knowledge and outcomes live in git: task intent, terminal status, verification notes, ADRs and
    their decision states;
  - live operational state lives in the plane's store;
  - the store indexes git read-only, as a rebuildable projection.

## Done

| Change | What |
|---|---|
| Grok hosting removed | The plane runs one hosting, the Claude agent team |
| Operator naming | The human role is "operator" everywhere; products rewrote their old values and the plane no longer reads them |
| Shared resolvers | `ccp/refs.py` parses every id and reference; patterns configurable (`ids`) |
| Canonical task format | SPEC §5, `contracts/task_file.schema.json`. File statuses are `pending`/`done`/`dropped`, plus declared `paths:` |
| Spec maintainer | The team lead answers spec questions; the headless resume path is gone |
| Local configuration | Per-product bindings are local (`projects/`, gitignored) until the store holds them |
| ADR tool | SPEC §6, `contracts/adr.schema.json`, `ccp adr new / status / decide / supersede / check / index / list / migrate --markers`: a declared frontmatter schema, `### D1. Title` decisions with a build state each (`not_built / built / live / retired`), decision-level links whose reverse is checked both ways, statuses with allowed transitions, an in-force check; the header converter is retired |
| Worktrees and environments | SPEC §12.2: `ccp wt create / remove / list / up / down / urls / gc` for every worktree kind, recorded in queue state; `env` hooks (setup, teardown, up, down, and urls returning a dynamic list of named URLs); `merge.command`; `auth_check.probes`; the adapter layer removed |
| Estimation and allowance | SPEC §25.4, §26.3, `contracts/allowance.schema.json`: the allowance command reports any number of named usage windows, each with a weekly stop or a session park (`telemetry.windows`); the estimator reads families, path suffixes and SPEC locations from `ids` and `estimate.*` |
| Doc checks per language | SPEC §21.5: a language-neutral core plus language packs (`package_docs.language`, Python first), product commands in `docs.checks`, opt-in rules (citations, no ids in code, history attribute, no overlapping checks) |
| Runner rules | SPEC §15.6 and the runner brief: settled-head review, merge pinned to the approved head, merge the integration tip in (never rebase), re-verify after an integration merge, minors before merge |
| The CLI is `ccp` | ADR-0036 D3, task 0029: the command, package, `CCP_*` variables, `ccp.*` telemetry keys and the `dev.ccp` launchd prefix; the plugin and marketplace ids are `ccp` (`ccp@ccp`, `ccp:<agent>`, ADR-0036 D4); the `cpl` shim and the old `CPL_*` and `cpl.*` names are no longer read |
| Gate-result contract | SPEC §14.1, `contracts/suite_result.schema.json`: a gate may write its counts to `$CCP_SUITE_RESULT`; output parsing defaults to unittest only; generic `ran`/`cached` counters; lane roles in `suite.roles` |

## The reshape

Each phase lands as one to three PRs (SPEC change, code, tests), with an independent review and a
release. Readers stay backward compatible, so managed products keep working between phases.

All reshape phases have landed.

## After the reshape

- **Self-hosting:** the plane's own development is managed by the plane, with tasks, ADRs and
  house rules. It is the reference example of a managed project.
  - **Stage 1, records only (bootstrapped):** `docs/PROJECT.md`, `docs/delivery/` (`plane.json`,
    task log, review points, writing rules, standing DoD), `docs/adr/`, `docs/ENGINEERING.md`,
    `scripts/gate.sh` and `scripts/leak-check.sh`, the telemetry anchor in `.claude/settings.json`
    (the plugin anchor lives in the gitignored `.claude/settings.local.json` until publication), and a test that runs the plane's checks on itself. `examples/` is
    removed. Sessions still implement in worktrees by hand; the work is recorded in the plane's
    own task log.
  - **Stage 2, runner-driven (later, its own design):** a lead and runner teammates claim the
    plane's tasks through `ccp`. The release must happen strictly between tasks, because the
    `ccp` doing the work is the run checkout that a merge moves.
- **The plane's decision record:** the operator's rulings so far become the plane's own ADRs,
  accepted and implemented, with no private detail.
- **SPEC restructure:**
  - normative rules only;
  - implementation notes move to `docs/design/`;
  - history moves out;
  - amendment layers are folded into current rules;
  - neutral examples throughout.
- **Merge handling (pluggable strategy):** the plane owns how a PR reaches the integration branch
  (main, by default).
  - **Builds on what exists:**
    - task PRs already squash-merge by default, through the `merge.command` step (§15.5);
    - `ccp tasks close` already deletes the task's worktrees and its branch, locally and on the
      remote, when a worktree directory is configured.
  - **New: a strategy interface,** since projects differ. One strategy ships now, the operator's
    preferred one: each PR is **squashed onto the integration tip** as one commit, so main stays a
    clean, linear sequence. Every merged PR's branch is deleted, locally, on the remote and in
    worktrees, whatever opened the PR and whether or not a worktree directory is set.
  - **New: `ccp repo check | apply`.** It reads and sets what the hosting service exposes through
    its API: allowed merge methods, delete-branch-on-merge, linear history on the protected
    branch. A setting the API can't change is reported, not assumed.
  - **Depends on the strategy:** the runner's rule "bring the integration tip into a PR by merging,
    never rebasing" (§15.6) is safe only because PRs squash-merge, so the branch's own history
    never reaches main. A rebase-merge or merge-commit strategy would need its own rule there.
- **Store:** a `Store` interface over today's file-backed queue first, then a hosted multi-user,
  multi-project backend that also serves the dashboard.
- **Publishing:**
  - a leak check;
  - a squashed history in a new public repository;
  - SPEC §31 approvals become the operator's review approval on the PR;
  - done before publication: the plugin and marketplace ids and the agent namespace are `ccp`
    (`ccp@ccp`, `ccp:<agent>`), and the `cpl` shim and the old `CPL_*` and `cpl.*` names are gone
    (ADR-0036 D3, D4); each product's lead updates its `.claude/settings.json` and bindings.
