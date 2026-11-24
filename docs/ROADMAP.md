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
- **Deferred from architect pass `ar-20261120T234012Z-27eb`** (record in `docs/delivery/reviews/`):
  - F10: replace the tests' sentence assertions (hundreds of them, across most modules) with the
    token each guards, and derive the template flags' defaults from the templates. Too large for one
    task; house rule E4 keeps new tests clean meanwhile.
  - F17: move `scripts/observability/lib.py` and `architecture_review.py` into the `ccp` package, so
    `ccp` imports nothing from `scripts/`. The move also amends E7 ("`ccp` imports nothing from scripts/", with a
    command check; operator, 2026-11-22). Architect pass
    `ar-20261122T055103Z-11aa` (F01) found the first trigger fired; task 0282 (R25) moves the headless
    helpers and the open-question rule out of `spec_maintainer.py`. Tasked once 0296, which edits lib.py and
    its importers, is done (0272, 0277, 0282, 0283 and 0293 are; `ar-20261122T100027Z-dd31`).
    It also corrects the text on the observability scripts' direction (`ar-20261122T162238Z-9098` F03, deferred
    here by the operator, 2026-11-23): §10.6, §23.4, `docs/cli/04-observability.md` and E7 call
    `scripts/observability/*.sh` wrappers over `ccp`, but `emit-event.sh` and `heartbeat.sh` write the ledger
    themselves through `lib.py`, and `ccp` calls `heartbeat.sh` and `set-waiting-on.sh` as single writers that
    share `lib.py` with it. F17 states the direction it lands on in those four places.
    Architect pass `ar-20261124T034246Z-e089` (F04) found the trigger met and untasked; its triage, at the
    five-task cap, sets a new one: tasked once 0323 (the package docs on lib.py and the queue-write route) and 0324
    (the test helpers that import lib) are done.
  - `ar-20261124T034246Z-e089` F06, deferred at that triage's five-task cap: `ccp architect triage` validates a
    triage against `contracts/architecture_review_triage.schema.json` through `ccp/schema.py`, and a test compares
    `DISPOSITIONS` and `RULE_DISPOSITIONS` with the schema's enums. Tasked with the next architect pass's fixes.
  - Found applying E17 at that triage: `ccp/otel.py` (three `bindings_dir() / f"{pid}.yaml"` reads) and
    `scripts/sync-product-docs.sh` read a binding by path and ignore `PROJECT_YAML`. Routing them through lib's
    resolver changes which file is read when it is set, so it is a feature, not a refactor; tasked with the next
    architect pass's fixes.
- **Deferred from architect pass `ar-20261121T020523Z-1d5f`** (record in `docs/delivery/reviews/`):
  - F12: the plane's own `pregate` lane: taken up by task 0285 (R25), after architect pass
    `ar-20261122T055103Z-11aa` (F07) found it still undeclared.
- **Deferred from architect pass `ar-20261121T132817Z-d5e5`** (record in `docs/delivery/reviews/`):
  - F06: taken up by task 0271 (R23), after architect pass `ar-20261121T223646Z-f0a7` (F06) found
    `tests.test_mutate` still the second slowest module after 0255.
- **Deferred from architect pass `ar-20261121T174754Z-7df5`** (record in `docs/delivery/reviews/`):
  - F01: a change to `ccp/cli.py` or `ccp/config.py` names more than a quarter of the test modules as
    affected, so `ccp suite affected` says to run the full lane. Re-measured after R19's 0261 runs a
    declared part lane in parallel: if a cli or config task's part run still takes longer than the
    gate lane, the lead chooses between each command module registering its own parser and handler
    (cli.py only dispatches) and a language-pack rule for a declared hub module. Other widely read files
    bring the part-lane pre-gate near a full gate too: `ccp suite affected` at `ad9b4f84` names 44 of
    226 test modules for `ccp/tasklog.py`, 99 for `docs/delivery/plane.json`, 127 for 0301's change.
    Config files are taken up by task 0319 (architect pass `ar-20261123T230912Z-197a` F01, a signed §14.7
    brief): the pack stops matching tests by the name of a path `suite.affected_map` matches. The cli and config hub
    modules stay here.
  - F10: the six retirement-guard test modules. Re-measured after R17's 0255 makes `ToolkitFixture`
    cheap; a guard with no reader left is cut then, by one refactor task.
- **Deferred from architect pass `ar-20261122T055103Z-11aa`** (record in `docs/delivery/reviews/`):
  - F08: a render-only `ccp prompt` (no audit, no run), so a template refactor proves "rendered prompt
    unchanged" with one command at base and head. Tasked if the seats of R24's 0276, the next template
    refactor, note the same scratch render-and-compare work. 0317's seats noted it (`ar-20261124T034246Z-e089` F04);
    its triage, at the five-task cap, sets a new trigger: the next task that refactors a prompt template builds it,
    as its first check.
- **Deferred from architect pass `ar-20261122T162238Z-9098`** (record in `docs/delivery/reviews/`):
  - F03: the observability scripts called wrappers over `ccp`; with F17 above (operator, 2026-11-23).
  - F09 and F11: `tests/helpers.py` is imported by most test modules, so an edit to it makes the part lane
    nearly the whole suite, and tests keep private git runners (the shared one strips its output) beside it.
    Split `tests/helpers.py` by concern and give it one git runner with a raw-output option, by one refactor
    task, once the R26 tasks that edit shared test fixtures (0293, 0302) are done: taken up by task 0324 (R33,
    `ar-20261124T034246Z-e089` F04). The language pack selecting only a
    changed name's importers is not taken: a test reaches a changed helper through another helper of the
    same module, so it would miss tests.
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
