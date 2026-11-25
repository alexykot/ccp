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
| Doc checks per language | SPEC §21.5: a language-neutral core plus language packs (the top-level `language`, Python first), product commands in `docs.checks`, opt-in rules (citations, no ids in code, history attribute, no overlapping checks) |
| Runner rules | SPEC §15.6 and the runner brief: settled-head review, merge pinned to the approved head, merge the integration tip in (never rebase), re-verify after an integration merge, minors before merge |
| The CLI is `ccp` | ADR-0036 D3, task 0029: the command, package, `CCP_*` variables, `ccp.*` telemetry keys and the `dev.ccp` launchd prefix; the plugin and marketplace ids are `ccp` (`ccp@ccp`, `ccp:<agent>`, ADR-0036 D4); the `cpl` shim and the old `CPL_*` and `cpl.*` names are no longer read |
| Gate-result contract | SPEC §14.1, `contracts/suite_result.schema.json`: a gate may write its counts to `$CCP_SUITE_RESULT`; output parsing defaults to unittest only; generic `ran`/`cached` counters; lane roles in `suite.roles` |

## The reshape

Each phase lands as one to three PRs (SPEC change, code, tests), with an independent review and a
release. Readers stay backward compatible, so managed products keep working between phases.

All reshape phases have landed.

## After the reshape

- **Tasked in R15:** ADR-0044 (a follow-up is tracked, not left in notes; tasks 0223, 0230-0232),
  ADR-0045 (checks only the operator's machine can run; 0224, 0237, 0238) and ADR-0046 (decisions may
  depend on other ADRs' decisions; 0225, 0251, 0252).
- **Deferred from architect passes** (each review record in `docs/delivery/reviews/` holds the finding's trail):
  - `ar-20261120T234012Z-27eb` F10: replace the tests' sentence assertions (hundreds of them, across most modules)
    with the token each guards, and derive the template flags' defaults from the templates. Too large for one task;
    house rule E4 keeps new tests clean meanwhile.
  - `ar-20261121T174754Z-7df5` F01: a change to `ccp/cli.py` or `ccp/config.py` names more than a quarter of the test
    modules as affected, so `ccp suite affected` says to run the full lane. Trigger: a cli or config task's part run
    taking longer than the gate lane; then the lead chooses between each command module registering its own parser
    and handler (cli.py only dispatches) and a language-pack rule for a declared hub module.
  - `ar-20261122T055103Z-11aa` F08: a render-only `ccp prompt` (no audit, no run), so a template refactor proves
    "rendered prompt unchanged" with one command at base and head. Trigger: the next task that refactors a prompt
    template builds it, as its first check.
  - `ar-20261122T162238Z-9098` F09 and F11: left after 0324 and 0329, the fixture-class git runners and inline git
    calls. The language pack selecting only a changed name's importers is not taken: a test reaches a changed helper
    through another helper of the same module, so it would miss tests.
  - `ar-20261124T234643Z-3c95` F09: `ccp tasks backfill-review-points` (tasks closed before close stamped a review
    point) has no stated end. The operator chose (a) on 2026-11-25: `ccp tasks migrate` is retired by task 0342; keep
    `backfill-review-points`. Trigger: every bound product's `--dry-run` stamps nothing; then a task retires it.
  - `ar-20261125T094654Z-c8a0` F09, with 0340's follow-ups on the double-abandon race and `tell_expired`'s place: an
    expired run is found by its `abandoned_reason` text, which embeds `PENDING_EXPIRY_S`. Trigger: a task that changes
    the bound or makes it a knob records the expiry as its own field and matches on that (§11.1 then states the rule
    without the figure), or a double abandon is seen in a ledger.
  - Follow-ups the lead passed to `ar-20261125T094654Z-c8a0`, each with its trigger:
    - `ccp tasks check`'s Scope-path warning reads paths inside a quoted CURRENT or PROPOSED passage (0336). Raised
      once, a warning only, and leaving quotes out narrows §5.6's stated rule. Trigger: a second brief draws it.
    - `kind_forbids` forbids `adr_refs` for a configured kind whose own `refs_any` leaves it out (0338). Trigger: a
      bound product configures a kind with its own `refs_any`; then §5.4 rules whether a kind forbids what it omits.
    - `ccp report`'s follow-ups near-miss warning reads a fenced heading (0332). Trigger: the next task that touches
      the report's follow-ups reading moves both patterns to `ccp/mdsection.py` (E22).
    - `ccp/suite.py`'s `_alive` mixes process I/O with its judgement (0339, E15). Trigger: the next task that changes
      the liveness judgement splits it first.
    - `PLANE_PROJECT_YAML`, read beside `PROJECT_YAML` by the queue and project-id resolvers and named by no § (0331).
      Trigger: no binding script or product environment sets it; then a task drops it from both.
  - T102 at triage `ar-20261124T205520Z-4ce8`: init's starter `citations` rule covers `docs/*.md`, so a product
    doc that names its own stages `S1`, `S2` reads as SPEC citations. A product fixes it with
    `package_docs.rules.citations.ignore` (§21.6). Trigger: a second product hits it; then the starter globs leave
    out the planning doc, or the rule gains a per-file exclude.
- **Considered and declined:** continuing past the weekly allowance into paid extra usage (the plane
  runs on the prepaid allowance only, ADR-0026), and a separate task-drafting seat (the lead drafts
  tasks, with a writer subagent when several land at once).

- **Self-hosting:** the plane's own development is managed by the plane, with tasks, ADRs and
  house rules. It is the reference example of a managed project.
  - **Stage 1, records only (bootstrapped):** `docs/PROJECT.md`, `docs/delivery/` (`plane.json`,
    task log, review points, writing rules, standing DoD), `docs/adr/`, `docs/ENGINEERING.md`,
    `scripts/gate.sh` and `scripts/leak-check.sh`, the telemetry anchor in `.claude/settings.json`
    (the plugin anchor lives in the gitignored `.claude/settings.local.json` until publication), and a test that runs the plane's checks on itself. `examples/` is
    removed.
  - **Stage 2, runner-driven (running):** a lead and runner teammates claim the plane's tasks
    through `ccp` (plane.json `parallel.max_in_flight`). A merge to main is a release (ADR-0024),
    made at any time (ADR-0031 D4): tasks in flight carry on, their workers run the head they change,
    and only the runners' and the lead's own `ccp` calls move to the new release.
- **Done:** the plane's decision record (the operator's rulings are the plane's own ADRs, ADR-0031
  D3) and the SPEC restructure (review point R1).
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
  - **Later: a batching merge queue.** Today each PR merges alone, pinned to its verified head,
    and every merge sends the other runners to catch up and re-run the gate. A queue would run the
    gate once per batch on the merged stack and bisect failures. It needs its own strategy, and a
    rule for what a verdict binds to when the landed commit is a batch: §15.5 stops close when the
    host accepts a merge without merging. Trigger: merge catch-ups, not the number of runners,
    become the throughput limit.
- **Seat isolation (later).** Every seat runs as the operator's OS user, with the operator's
  credentials (`docs/design/threat-model.md`). Options by cost: Claude Code's command sandbox,
  per-product scoped forge tokens, a container per worker, a separate OS user or VM per product.
  In-process teammates share the lead's process, so isolation per seat beyond the command sandbox
  means headless worker processes. Trigger: other models behind the harness, many more runners, or
  several operators' products on one host. It follows the threat model.
- **Store:** a `Store` interface over today's file-backed queue first, then a hosted multi-user,
  multi-project backend that also serves the dashboard.
- **Publishing:**
  - a leak check;
  - a squashed history in a new public repository;
  - SPEC §31 approvals become the operator's review approval on the PR;
  - done before publication: the plugin and marketplace ids and the agent namespace are `ccp`
    (`ccp@ccp`, `ccp:<agent>`), and the `cpl` shim and the old `CPL_*` and `cpl.*` names are gone
    (ADR-0036 D3, D4); each product's lead updates its `.claude/settings.json` and bindings.
