# The architect seat: design notes

Non-normative notes behind SPEC §19–§20: how the seat is built, the choices made where the rules
left room, and walk-throughs. The SPEC states the rules; nothing here overrides it.

## How it is built

- **One review kit.** `scripts/observability/architecture_review.py` defines a `Kind` (state file,
  lock, id prefix, event type, categories, triage command) and the lock, report and triage
  validation, rendering and triage hand-off every kind shares. The architect (`ccp/architect.py`)
  is its one kind.
- **Shared helpers.** The driver reuses the headless-call helpers (lock, quota detection, Claude
  JSON parsing, binding readers) from `scripts/observability/spec_maintainer.py`. The durable `done`
  count is `load_durable_statuses` over the product's task log.
- **The skill loads by slash command.** The reviewer prompt starts with `/architect` so Claude Code
  loads the skill, and tells the model to read the skill file
  if it did not load.
- **Uncommitted edits in the tree.** The working tree may hold another session's uncommitted edits
  (an implementer working in the main checkout); the prompt then tells the reviewer to read
  committed versions (`git show HEAD:<path>`).
- **Managed copies (before the plugin).** A sync used to put a skill's managed-copy header after its
  YAML frontmatter, because Claude Code reads the frontmatter first; `--check` found the header
  anywhere near the top. The plugin now ships the skills.
- **Stub for tests:** `DA_CLAUDE_BIN` replaces `claude`.
  The loop was dry-run with the stub: due → run → reported → triage → triaged → the actions; the
  failure path (no JSON gives `failed`, raw output kept) and the board rebuild with the new events.

## The retired review kinds

The architecture review and the docs audit, and their aliases `scripts/architecture-review.sh` and
`ccp docs audit`, are retired (SPEC §19.12, ADR-0034 D5). Nothing writes their records any more,
but an older queue may still hold them, and the board and `ccp health` read it as before:
`architecture-review.json` and `docs-audit.json` (a `running` docs-audit record still shows as a
headless seat), `reviews/ar-*` and `reviews/da-*`, and the `architecture_review` and `docs_audit`
event types in the ledger. A binding's `architecture_review` block is read by
nothing; a `docs_audit` block in `plane.json` is refused as an unknown key. A sync still removes
a product's leftover managed copies of the two older skills, and `--check` reports them as
`retired`.

## Choices made where the rules left room

- **A merge is a task reaching `done`.** Each pass records the done set at its start; "since none"
  counts every done task. `grace_tasks` blocks once that many merges have followed the moment a pass
  became due; `triage_grace_tasks` once that many have followed the report ("at least").
- **A closed scope blocks at once.** When `next` would name no task, a due pass blocks immediately
  (exit 4, not 3), which is how the review-point trigger is enforced: a closed scope has no further
  merges for a grace to count.
- **When a trigger fired.** Cadence's moment is computed; the others' is the done count when `ccp`
  first saw them, kept in `architect.json` (`seen`).
- **Failed passes.** A started pass that failed restarts the grace rather than re-blocking at the
  done count it failed at. After two failed passes in a row `next` stops blocking on it, so a
  systematic failure (a broken prompt or skill) does not burn a full pass per merge.
- **Detached passes.** `ccp architect run --detach` lets a pass outlive the runner's shell call.
- **Shape records.** An `adr_refs` entry cites an ADR when it opens with its number (`"0031 D1"`,
  `"ADR-0031"`) or names its `adr/NNNN…` file; frontmatter lists keep a quoted item's commas.
- **Refactors.** "Merged since the last refactor" follows `git log -G` over the task files becoming
  `done`.
- **Budgets are diagnostics.** They were kept out of the verifier's gate so one file growing never
  fails an unrelated task; `ccp budgets check --base` was added later so a change is still judged on
  the files it grew. Every binding value is type-checked; `metrics` (with `suite_seconds` and
  `suite_tests` built in) and `shape_only_dirs` are binding keys beyond the basic example.
- **Health timing.** For `ccp health`, a merge is a merge commit or a `(#N)` squash on HEAD's
  first-parent history whose subject starts with the task's `NNNN` or that merged `task/NNNN-…`.
  A task starts at its first prompt audit, lease, phase or `progress/<task>.json` event; each phase
  ends when the next is launched, and verifying at the verifier's `checked_at`. Only a phase end with
  no recorded time falls back to its report file's modification time, and the row says so
  (`times`), since a copied or restored queue moves those.
- **Report and triage contracts.** A finding's category must belong to the run's lenses, and
  `rule-cost` also needs fix `decide`. The triage file gains `rule_changes` (`applied`, `rejected`
  or `needs_operator`, with a reason).
- **Event ops.** Event type `architect` uses the ops and payloads of the retired review kinds'
  event types.
- **Refactor reach.** `ccp/tasklog.py` has `scope_deps` (the transitive dependencies of the scope's
  open tasks), `refactor_reach` (the refactors outside the scope `next` may return, each with the
  scope task that needs it) and `waiting_refactors` (pending refactors the scope neither names nor
  reaches). `team.sh runner prompt` stays a plain preview and adds none.

## Switching the seat on for a product with history

A product whose tasks are already done would get `architect pass due: N task(s) done since none` at
its first `next`. Switch on in this order:

1. Release the plane first: a `ccp` without the seat refuses the `architect` key, and every `ccp`
   command, the verifier's gate included, would exit 2.
2. Make sure the product's sessions load the plugin's `architect` skill and the current runner and
   worker briefs.
3. Write the house rules (`rules_doc`, from `templates/docs-project/ENGINEERING.md`). Set
   `shape_from_task` to the next unwritten task number, so no task already written fails the
   shaping check. Dry-run `ccp tasks check` and `ccp docs check`: the `architect.checks` commands
   gate every verification.
4. In the same change that adds the block, start the first pass, before any runner sees the block:
   `QUEUE_ROOT=<queue> ccp architect run --force --detach`. A running pass does not block `next`.
5. Rotate the runner, so it works from the brief with the exit-4 step. Then triage the first report
   within `triage_grace_tasks` merges.

## Acceptance walk-throughs

1. **A pass is enforced.** On a stub product with 4 merged tasks and no pass, `ccp tasks next` names
   a task. After one more merge, it exits 4 with "architect pass due: 5 task(s) done since none".
   After `ccp architect run` (stubbed with `DA_CLAUDE_BIN`), `next` names a task again. Once 2 more
   merges pass with the report untriaged, it exits 4 with "awaits triage".
2. **Friction triggers a pass.** Three `ccp health note` lines make `ccp architect due` exit 0 with
   a reason that names the notes. The next architect prompt contains all three.
3. **Shaping is checked.** With `shape_adrs` on, a new pending task citing an ADR with no `sh-`
   record fails `ccp tasks check`. It passes once a record names that ADR, or once the task carries
   `shaping: waived — …`.
4. **Refactor capacity.** With 4 feature tasks merged since the last refactor and one ready
   refactor, `ccp tasks next --scope <features only>` returns the refactor when the scope reaches it
   (under `refactor_in_scope: true`, or under `"deps"` when a scope task depends on it).
5. **Rules are bounded.** A `rules_doc` over `rules_max_lines`, or a rule with no `check:`, fails
   `ccp docs check`.
6. **`rule-cost` reaches the operator.** A stub report with a `rule-cost` finding that has
   `needs_decision: false` fails validation. Triage of a valid one produces a `needs_operator`
   entry.
7. **The runner brief** handles exit 4; `tests/test_team_hosting.py` checks the brief's text for the
   step.
