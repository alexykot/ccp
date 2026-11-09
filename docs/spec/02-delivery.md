# Part II — Delivery

How a task goes from the task log to a merge: its lifecycle, the runs and worktrees it uses, the
workers and their prompts, the test runs, review, verification and merge, several runners at once,
spec questions and gates, and keeping the runner going. Rules only; reasons are in the ADRs,
implementation notes in `docs/design/team.md` and `docs/design/toolkit.md`, call syntax in
`docs/cli/02-delivery.md`.

## 10. Task lifecycle

### 10.1 States and waits

A task's file status is `pending`, `done` or `dropped` (§5). Its runtime state lives in the queue
(`tasks/<id>.json`, `work.json`):

```
pending → leased → implementing → implemented → reviewing → reviewed → fixing → reviewing …
        → submitted → verifying → (approve) merging → done
                                 (reject)  fixing / implementing
       ↘ blocked (a runtime wait, below)
       ↘ failed  (unrecoverable)
```

`ccp prompt` moves a task to `implementing`, `fixing`, `reviewing` or `verifying`; `ccp tasks
phase <id> <phase>` moves it for a step with no run of its own (an operator step, waiting to
merge). `MID_FLIGHT` is every phase from `leased` to `merging`.

**Runtime waits** (`waiting_on`): `null` | `runner` | `steerer` | `spec_maintainer` | `quota` |
`reauth` | `operator_decision` | `operator_step` | `design_seat`. `spec_maintainer`: an open spec
question lists the task (§17.3). `operator_decision`: something waits on the operator.
`operator_step`: a step only the operator's machine can run (§15.8). `design_seat`: an open gate
(§17.9). `steerer` is read for older queues. Only these names are read; a queue holding values from
before the operator rename is rewritten by its product before upgrading. A wait is set and cleared
only through its single writer (`ccp tasks wait|resume`, which call `set-waiting-on.sh`).

### 10.2 The runner's lifecycle

1. **Start.** The operator asks the lead to run a scope (task ids or a review point). The lead
   checks it is ready (its tasks exist, `ccp tasks check` is clean, its standing approvals, §17.9,
   are written) and runs `team.sh runner spawn --scope … [--review-point …] [--count N]`. It writes
   the prompt audit (`phase: runner-spawn`, task id `_runner`), emits `runner`/`spawn`, records
   `status: running`, `scope`, `review_point` and the runner slots in `work.json`, and prints the
   exact Agent call (name, agent type `delivery-runner`, a fixed spawn prompt naming the project,
   the scope, the queue root and the slot). The spawn prompt holds nothing else. Under
   `refactor_in_scope: "deps"`, a spawn that starts a new review point puts every waiting refactor
   at the top of the scope it records, names them in the prompt and the printed action, and lists
   them as `refactors_added` in the `runner`/`spawn` payload and as `review_point_refactors` in
   `work.json`; a respawn of the same review point puts back the ones still pending and adds no
   others (§20).
2. **Run.** The runner loops: `ccp tasks next` (§10.3) → `ccp tasks claim` (§10.5) → `ccp prompt`
   and the worker (implement, then the PR in the same worker) → review → fix and review again while
   needed → verify (§15) → `ccp tasks close` (merge pinned to the verified head, §10.5) → the operator step,
   if the task has one and it is approved (§15.8, §17.9) → reconcile → next. Each step is a `ccp` command (§10.6). Implementers never merge; the runner merges. When
   the harness denies any of the runner's agents an action, no agent of the runner's performs it:
   the runner opens a gate and tells the lead (§17.9).
3. **Stop.** The runner stops when (a) the scope has no ready task and none in flight; (b) every
   ready task waits on the lead or the operator; or (c) the allowance checkpoint is reached (§25).
   It reports to the lead in one message: what finished, what is waiting and why, and the next
   step. At a review point, (a) is the hard stop; the review pack is the lead's to prepare with the
   operator. With several runners the last runner to finish reports the stop.
4. **Rotate.** When its context gets heavy, or its slot's `tasks_done` reaches
   `runner.rotate_after_tasks` (default 4), the runner finishes the current phase, writes
   `work.json` and asks the lead to rotate it. The lead records it (`team.sh runner rotate
   [--slot]`), shuts it down, and only once it is gone spawns a fresh runner with the same prompt.
   The harness may give the fresh one a suffixed name; the lead binds the name the Agent result
   gives (`team.sh runner bind --name <it> [--as <slot>]`) and stops the old one if it is still
   there. Until that bind no teammate is kept working (§18.2). Workers' prompts, the hook and the
   lead's own actions address the bound name. Shutdown is a `shutdown_request` message first; a
   runner that does not acknowledge it is stopped with `TaskStop(<the bound name>)`. A rotation is
   refused only while that slot's own task has a worker run open.
5. **Restart.** If the lead session is resumed, the runners are gone. When `work.json` `status` is
   `running`, the lead respawns every slot. A runner resumes from the queue: a task mid-flight is
   picked up at its recorded phase, and its worker is re-launched with the task's branch and notes.

Only the lead spawns, rotates, re-scopes or stops a runner (`team.sh runner stop [--slot]
[--drain]`); the operator does it by asking the lead. `team.sh runner status` is the lead's view:
`work.json`, every slot with its bound name, task and phase, open gates and open questions.

**Changing the scope.** `team.sh runner scope --add <ids> [--remove <ids>]` (lead only): every id
an existing task id; it updates `work.json` `scope`, emits `runner`/`scope` (`name`, `scope`,
`added`, `removed`, `prompt_ref`), writes a prompt audit (task id `_runner`, `phase: runner-scope`)
and prints the message for the lead to send each runner. It refuses with no runner running, when
the scope would be empty (use `stop`), and when removing a task in `in_flight`. The runner reads
the scope from `work.json` before each `ccp tasks next`.

### 10.3 Choosing the next task

`ccp tasks next [--scope IDS] [--explain]` returns the lowest-numbered `pending` task whose
`depends_on` are all `done`. `--scope` (task ids or `NNNN`) restricts the candidates (their
dependencies may lie outside it); while `work.json` `status` is `running`, the scope defaults to
`work.json`'s. The order:

1. **The lead's preference list** (`work.json` `next_tasks`, §10.4): its first entry that is
   ready and in the scope (or one the scope reaches, §20), its `why:` line giving its place ("2 of
   3"). An entry waiting on a dependency is skipped and keeps its place; one done, dropped, unknown
   or out of scope is ignored with a note on stderr.
2. **The review point's refactors** (`review_point_refactors`, §20).
3. **The plane's own order** (`ccp/selection.py` `ranked`, shared with the board).

A held task (§10.4) is passed over, a held refactor and a held preference alike, and stderr says so;
`--explain` prints the whole ranked queue with the pick and the holds marked. The runner always
takes `next`'s pick and turns a lead's "take X next" back to the lead as `ccp tasks prefer X`. With
several runners `next` also applies §16.3 (head of line, exit 7).

### 10.4 The lead's preference, holds, release and drop

These are durable lead state in `work.json`, not messages, which can arrive after a claim.

- **Preference.** `ccp tasks prefer <id> [<id>…] [--reason "…"]` writes `next_tasks` (the full
  ids, in order) with `next_task_by`, `next_task_at` and `next_task_reason`, and a `prefer` `set`
  event. A new list replaces the old. One refused entry (unknown, not pending, outside `work.json`'s
  scope, named twice) writes nothing (exit 2); an entry still waiting on a dependency is accepted
  with a warning. `--clear` empties it; no arguments prints it. Claiming a listed task removes only
  that entry in the same `work.json` write (a `prefer` `clear` event with the entries left); when
  the last goes, the four keys go. A `work.json` with a single `next_task` reads as a one-entry list.
  The ready entries lead `ranked`'s order, and the forecast's replay takes each once it is ready.
- **Hold.** `ccp tasks hold <id> [--reason "…"]` writes `held[<id>] = {by, at, reason}` and a
  `hold` `set` event; it refuses (exit 2) a task the log lacks and one not pending. `--clear <id>`
  lifts it (`hold` `clear`); no arguments lists the holds.
- **Release** (lead or runner). `ccp tasks release <id> --reason "…"` undoes a claim taken too early: a task leased
  (or blocked) in the queue with no run at all (nor, from before run records, a prompt audit) goes
  back to `pending`. Its wait is cleared through `set-waiting-on.sh`, its phase moves to `pending`
  (the `queue/pending/` marker), then a `lease` `clear` event with `released: true` and the reason;
  `lease_since`, `claimed_at` and `implementation_started_at` are cleared, and it leaves `work.json`
  as `ccp tasks sync` does (out of `in_flight`, the next task in flight becomes current, none left
  makes `runtime_status` `idle`). The worktree and branch are kept, and a later claim resumes in
  them. It refuses (exit 3) a task with no lease, in another status, or with a run; no `--reason`
  is exit 2. A hold stays; a preference entry the claim removed is not restored. A task's time
  starts at its first claim after its last release.
- **Drop** (lead or runner). `ccp tasks drop <id> --reason "…"`, for a task its file on the integration tip marks
  `dropped` whose PR did not merge, whatever its phase: it abandons its open runs (`task dropped`),
  clears its wait and lease, sets the queue status `dropped`, takes it out of `work.json` and prints
  `idle_runners`. Its worktree and branch are kept.
- **Sync.** `ccp tasks sync` makes the queue follow the log for tasks done or dropped there; it
  skips a task still leased in a mid-flight phase (close or drop settles it) and never takes a
  lease from a live runner.

### 10.5 Claim and close

**`ccp tasks claim <id> [--holder <slot>]`** runs the product's auth probes first
(`auth_check.probes`, §30) and exits 8 when one fails: no task is taken, and the runner raises a `reauth` gate to the lead (probes: `[{id, cmd}]`, `auth_check.timeout_seconds`, default 60).
Then it takes the lease, writes `work.json` (`task_id`, `phase`,
`runtime_status`, `in_flight`) and `tasks/<id>.json` from the task file, makes the task's implement
worktree (`ccp wt create --kind impl`, §12), samples the allowance (§25) and writes a heartbeat. A
`draining` or `stopped` `work.json` refuses a new task. A legacy `in_progress` or `blocked` file
status reads as `pending`. With several runners, §16.3 and §16.4 apply.

**`ccp tasks close <id> --pr N [--summary "…"]`** is one resumable step:

1. `ccp verify merge-ok` and the merge pinned to the verified head (§15.5). It refuses before
   merging when the runner worktree has changes or a rebase in progress; with several runners it
   refuses a head behind the tip (§16.5 rule 4).
2. **Reconcile:** the task file's status and Verification notes line (from the verifier's record),
   dated by the clock; `review_point` stamped when the task has none; `ccp tasks index` and
   `check`; the product's `reconcile.log` entry and `reconcile.hooks` (§8; a hook must be
   idempotent, a re-run runs it again); a commit by path and a push, retried once after a fresh
   pull. There is no `--no-push`.
3. The adapter's legacy `post_close` (§12.4), then every recorded worktree of the task and its
   branch removed (§12.1).
4. `lease/clear`, `work.json`, the slot's `tasks_done`, and the task's runs abandoned (§11.1).

After the merge, any failure prints the recovery steps; a re-run sees the merge (approved at the head
that merged) and only reconciles; a task already reconciled only has its queue state finished.

### 10.6 Principles of the toolkit, and exit codes

- **Every step that changes delivery state is a `ccp` command, and the command records its own
  telemetry** (ADR-0018). A seat cannot skip the telemetry without skipping the work. Every command
  runs with `QUEUE_ROOT` set, writes its own events (§23) and rebuilds the board (§28).
- **No seat writes its own automation**: a missing generic tool is a `ccp plane propose`; a need only this product has is product work (§31.4). Scripts no
  one reviews drift.
- **Worker prompts are rendered by `ccp`** from plane templates plus a product fragment (§13.2).
- **Token, model and effort figures come from the harness** (§24), never from an agent's account.
- **Numbers are diagnostics, never targets**: no board figure is a DoD item or a worker goal.
- The runner brief (`plugin/agents/delivery-runner.md`) names these commands at each step and describes no step in prose.
  `scripts/queue/*.sh` and `scripts/observability/*.sh` stay as thin wrappers over `ccp`.

**Exit codes** of `ccp` commands, run in the product checkout (`--root DIR`, else `$CCP_ROOT`, else
the git toplevel): 0 ok; 1 check failures or a failed run; 2 usage or configuration; 3 nothing
ready, not due, or busy; 4 refused by a review rule (§15.2) or a refused gate (§17.9); 5 the
allowance checkpoint (§25); 6 the session park (§25); 7 no slot for this runner now (§16.3);
8 an auth probe failed (§10.5); 75 an exclusive test lane is held (§16.6).

## 11. Runs and process locks

### 11.1 Runs

A **run** is one launch of one worker for one phase of one task: the unit time and tokens are
reported in.

- **Id:** `<task_id>/<phase>[-<n>]`, phase `implement`, `pr`, `review`, `fix`, `verify` or `merge`,
  the same name as its report file `progress/<task_id>/<phase>[-<n>].md`. Runs outside a task:
  `_runner/spawn-<n>`, `_architect/<review_id>`, `_triage/<review_id>`.
- **Record:** `QUEUE_ROOT/runs/<task_id>/<phase>[-<n>].json` (`contracts/run.schema.json`):
  `run_id`, `task_id`, `phase`, `round`, `seat`, `agent_type`, `expected_model`,
  `expected_effort`, `prompt_ref`, `opened_at`, `opened_by` (the runner slot), `agent_id`,
  `session_id`, `worktree`, `started_at`, `stopped_at`, `reported_at`, `abandoned_at`,
  `abandoned_reason`, `abandoned_by`, `outcome`, `suite_tests`, `suite_seconds`, `severity`
  (BLOCKER, MAJOR, MINOR, NIT counts), `friction_count`, `usage` (§24), `observed_models`,
  `observed_efforts`.
- **Binding.** `ccp prompt` opens the run as `pending`. The harness's `SubagentStart` hook calls
  `ccp agent start`, which binds the oldest pending run of that `agent_type` (whatever the session)
  to the agent (`agent_id`, `agent_type`, `session_id`); `SubagentStop` calls `ccp agent stop`. So
  `ccp prompt` refuses a second pending run of an agent type that already has one unbound (exit 3;
  with several runners, wait a few seconds and ask again); `--supersede` lifts that, but never
  abandons another slot's pending run opened in the last 120 s. A resumed agent is not bound again;
  an agent of another type is skipped; a start with no pending run lands in `runs/_unbound.jsonl`,
  as do hook errors, and the hook always exits 0. Headless runs bind directly.
- **Abandoning.** A run ends when its worker's `ccp report` closes it, or when it is abandoned
  (`abandoned_at`, `abandoned_reason`, `abandoned_by`, a `run` `abandoned` event) because a later
  round of its task and phase opens (`superseded by <new run_id>`; `ccp prompt` warns when the old
  round was `running`, and a report from it is refused), its task is closed (`task closed`), or its
  task is done or dropped in its file (`ccp tasks sync`: `task closed`, `task dropped`).
  `ccp runs gc [--dry-run]` applies the same rules to older records; a second run changes nothing.
  `abandoned_at` is never reverted. The board's Now panel and Seats table never list a run of a done
  or dropped task; an abandoned run shows only in the task's drill-down.

### 11.2 Process locks

The plane's process locks (the architect, estimator and review locks) share one rule. A
lock file records `pid`, `host`, `since` and `ttl_seconds`. It is **stale** when its `pid` is dead on
this host, even inside the TTL, or, for a lock from another host (whose pid cannot be checked), once
`now > since + ttl_seconds`. A stale lock may be broken by any process that wants it. Take is atomic
(create-if-absent); release removes the file only when holder and pid match.

## 12. Worktrees and environments

### 12.1 Worktrees

`ccp wt create --kind KIND --task ID [--sha SHA] [--name N] [--seat S] [--tag T]` makes a git
worktree under plane.json `worktrees.dir` (relative to the main checkout), named
`<kind>-<nnnn>[-<n>]`. Kinds: `impl` (the implementer's, on `task/<id>` from
`origin/<integration>`; `ccp tasks claim` makes it), `rev` and `ver` (detached at the head they
judge), `mut` (a mutation copy) and `mac` (a machine check), all detached at `--sha`.
`worktrees.links` are linked in from the main checkout and named in the repository's
`info/exclude`. Each worktree is recorded in `QUEUE_ROOT/worktrees/<name>.json`
(`contracts/worktree.schema.json`): kind, task, seat, tag, path, branch, sha, state and URLs.

- `ccp wt list [--task ID]` shows the records and any unrecorded worktree; `ccp wt remove NAME`
  removes one.
- `ccp tasks close` removes every worktree of the task, and its branch. `ccp tasks drop` and
  `release` keep them: an implementer may still be working there, and a later claim resumes in them.
- `ccp wt gc` prunes git's worktree list, forgets records whose worktree is gone, and removes the
  worktrees of tasks done or dropped in the queue and leased by no one.
- A worktree made before records (`impl-`, `rev-`, `ver-` with the task's number) is removed by
  close, or adopted by `create`. `create` reuses an existing worktree only at the `--sha` asked for;
  at another head it refuses (exit 3). A default name taken meanwhile moves to the next `-<n>`.
- Workers make theirs with `ccp wt create`, never `git worktree add`.

**The lead and the runners.** The lead keeps the product's main checkout and pulls it when a merge is
reported. Each runner merges, reconciles and runs operator steps from its own **runner worktree**
(binding `runner.worktree`; with several runners `<runner.worktree>-<slot>`, made by
`ccp tasks worktree --runner <slot>` when missing), detached at `origin/<integration_branch>` (the
main checkout holds the branch). It fetches and re-detaches before each task and pushes reconcile
commits with `git push origin HEAD:<integration_branch>`. Each implementer works in its task's
`impl` worktree.

### 12.2 Environment hooks

plane.json `env` holds shell command templates or null: `setup` when a worktree is made, `teardown`
when it is removed, `up` and `down` to start and stop what it serves, `urls` to say where it serves.

- A hook runs in the worktree, in its own process group, killed whole after `env.timeout_seconds`
  (default 600). Its output goes to `QUEUE_ROOT/worktrees/<name>.<hook>.log`, and it returns when its
  shell exits, so `up` must start services in the background and exit.
- The fields `{task_id} {nnnn} {kind} {seat} {tag} {worktree} {main_checkout} {name}` are filled in
  (the path fields `{worktree}`, `{main_checkout}` and `{name}` shell-quoted; any other brace is
  literal) and are also in the environment as `CCP_WT_<FIELD>`, raw (`"$CCP_WT_WORKTREE"`).
- A failed `setup` removes the half-made worktree and `create` exits non-zero. A failed `teardown`
  or `down` is a warning (the worktree is removed regardless). A failed `up` leaves the worktree
  `down` and `ccp wt up` exits non-zero. When a worktree's path is gone, `teardown` and `down` are
  skipped with a warning.

### 12.3 Up, down and URLs

`ccp wt up NAME` runs `env.up` (with no hook it only marks the worktree up), then `env.urls`;
`ccp wt down NAME` runs `env.down`; removing an up worktree runs `down` first. `env.urls` prints a
JSON list of `{name, url}`, as many as the product serves (none, one or many; names unique; a URL
has a scheme). `ccp wt urls NAME` runs it and records the list; `up` records it too (a bad list is a
warning there, an error from `urls`). The verify prompt tells the verifier to bring its worktree up
and use those URLs for checks that need the running product, browser checks included.

### 12.4 Legacy keys

`adapter.worktree_dir` and `adapter.worktree_links` read as `worktrees.dir` and `worktrees.links`
(setting both is an error). `adapter.post_close` commands (`{task_id}`, `{nnnn}`, run in the main
checkout) still run once at close, before the worktrees are removed. The binding's `adapter` and
`adapter_config_path` are ignored. A product with no `env` block behaves as before.

## 13. Workers and prompts

### 13.1 Workers

The runner's workers are subagents of fixed agent types (§2): the implementer, the reviewer and the
verifier. The implementer writes the change and, **in the same worker** (resumed by name), opens the
PR with `/mk-pr`; a cold `/mk-pr` is forbidden. The review is a clean separate worker, never the
implementer's session. Every worker runs the PATH `claude`, never `--bare`. Workers never merge,
never edit a task's checks and never create a task: a follow-up a worker finds goes to the lead.
Each worker reports through `ccp report` and a `SendMessage` to its runner (§13.4).

### 13.2 Prompt assembly

`ccp prompt <phase> <id> [--round n] [--note "…" | --note-file PATH]` builds every implementer,
reviewer, fixer and verifier prompt from four parts, in order, writes the prompt audit, opens the run
(§11.1) and prints the prompt path, the report path and the exact Agent call (agent type, no
`model`):

1. **The plane template** `templates/prompts/<phase>.md` (with `templates/prompts/_common.md`): the rules that hold
   in every product, among them working only in one's own worktree, foreground commands only, never
   merging, the review and verify standards (adversarial; reject only on BLOCKER or MAJOR; prove an
   absence pattern on a known positive; mutation-test a test that could pass vacuously, in a
   mutation copy made with `ccp wt create --kind mut`), the report contract, every test command
   through `ccp suite run` with the phase's lane (§14), the refactor DoD for a `kind: refactor` task
   (§20), and for the reviewer and verifier `ccp report` before removing their own checkout.
2. **The product fragment**: the file plane.json `prompts.fragment` names, holding the product's
   own rules (for example scratch resources, suite limits, paths that must not be written). It is
   product-owned and reviewed like product code.
3. **The task:** id, task file path, cited SPEC and ADR sections, the house rules (`rules_doc`), the
   PR and head for review and verify, the verifier's fixed packet, and the bound name of the runner
   that holds the task (its `lease_holder` slot's `bound_name`), so each worker messages its own
   runner.
4. **The note:** at most 4000 characters of runner text for this run, from `--note` or
   `--note-file` (UTF-8, stripped), recorded in the prompt audit. A note that looks like a secret is
   refused. A recurring note is a candidate for the template or the fragment, which `ccp board`
   shows.

`ccp prompt` needs a claimed task, checks for a pending run before writing anything, and refuses a
template naming anything it does not set. `ccp prompt verify <id>` renders the same text on every
run apart from paths.

### 13.3 Worker environment

When plane.json names `prompts.worker_env` (§8), `ccp prompt` also writes the run's environment
beside the prompt (`<phase>[-n]-env.sh`, plain `export NAME='value'` lines rendered from its
templates, values shell-quoted), and the prompt tells the worker to start each command with
`. <that file> && `: a worker's shell calls share no environment. A value that looks like a secret is
refused.

### 13.4 Reports

A worker submits its report with `ccp report <run_id> FILE`, which checks its shape, stores it at the
run's report path (`progress/<task_id>/<phase>[-<n>].md`), closes the run, and records the suite
metrics and every friction line. Report lines:

- `Outcome: done|blocked|failed` always;
- `PR:` and `Head:` for implement and fix;
- `Severity: BLOCKER=… MAJOR=… MINOR=… NIT=…` for review (a review with a BLOCKER or MAJOR is
  recorded as `changes`, otherwise `clean`);
- `Verdict:` and `Head:` for verify, matching the verdict `ccp verify record` noted;
- `Suite:` when the full suite ran, or `Suite: from <suite_id>`, or none (filled from the run's
  record, §14.4);
- `## Friction` as `- ` (or `* `) lines, or `none`;
- for implement and fix, `## Tests for new behaviour` (§13.5).

`ccp verify record` notes the verdict on the task's open verify run and emits `verify/recorded`; the
verifier's `ccp report` closes the run.

### 13.5 Worker efficiency

None of these changes what is checked; they change what each request carries and how soon a failure
shows.

- **Tool allowlist.** Every delivery agent definition names its tools (`tools`, `disallowedTools`),
  with no `Skill`; `SendMessage` stays reachable through `ToolSearch`.
- **Cache lifetime.** `experimental.cacheTtl: 1h` in every delivery definition; `ccp usage` shows
  the 1-hour cache writes (`W-1H`) per run and seat.
- **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's
  `architect.checks` commands (rendered from plane.json) and the test modules depending on the
  changed paths, through `ccp suite run --lane part`, by the product's own discovery command when its
  rules name one. It never stands in for the full suite, which runs on the final code and must be
  green.
- **Exploration hygiene.** What the task cites is read in full; a listing, search or log likely past
  about 200 lines goes to a scratch file and is read in slices; independent reads go as parallel tool
  calls in one turn.
- **The self-check.** Before the full suite, the implementer and fixer list each branch, field,
  refusal or behaviour their commits add or change with the test that fails without it, write the
  missing tests, and report the list under `## Tests for new behaviour`; the reviewer checks those
  lists against the diff (a later round, the fix reports' lists against the fix commits) and rates a
  gap as it would a missing test.
- **One statement of each rule.** The worker definitions do not repeat the `ccp suite run` rule, and
  the verifier's definition defers to its prompt's test-cache rule. The review and verify briefs run
  `ccp report` from their own checkout before removing it (or from anywhere with `--root`).

## 14. Test runs

### 14.1 The rule and the lanes

Implementer, fixer, reviewer and verifier workers run **every** test command (the full suite, the
gate, a subset of modules, every rerun) through
`ccp suite run --run <run_id> --lane <lane> -- <command>`, outermost, around any wrapper the product's rules give, never inside a script. The
plane reads three lane **roles**: `full` (the implementer's and fixer's full suite), `gate` (the
verifier's formal gate, whose script picks its own lanes) and `part` (a subset, such as the
reviewer's modules or a mutation check). plane.json `suite.roles` names the product's lane for each
(default: the role's own name; a role left out keeps it; two roles may not share a lane); the prompts,
the report's auto-fill and the health series use these names. `--lane` is a short label; without `-- <command>` it runs the argv plane.json `suite.lanes` gives that lane, from the checkout's root. A run
with no `--lane` is recorded without a lane (filed as part); for an exclusive lane's lock and its
usual duration it counts as the `full` role's lane. `ccp report` warns, never refuses, when a report
has a `Suite:` line but no suite run is recorded for its run.

### 14.2 The command

- It runs the command in the foreground with stdin inherited and exits with its exit code (128 + N
  when signal N ended it).
- **Summary mode** is the default when stdin is not a terminal (`--summary` forces it). The
  command's stdout and stderr both go to one log file, in the order written: `--log PATH`, else next
  to the run's record (`QUEUE_ROOT/runs/<task>/<phase>[-n]-suite-<suite_id>.log`), else
  `QUEUE_ROOT/runs/_suite-logs/<suite_id>.log` for an unbound run, else a temp file. `ccp` prints a
  start line naming the log and, when the command ends, a summary:
  - on a failure (a non-zero exit, or a failure counted), the failing tests' sections in full
    (`section_re`; unittest's `FAIL:` and `ERROR:` blocks), then the log's last `tail_lines` (40)
    lines not inside a shown section. They share `max_chars` (40,000): the sections first, less a
    reserve for the tail (a quarter of the cap at most); the tail is cut from its front, so the log's
    last lines and its final error always show. A log no longer than `tail_lines` is shown whole; an
    empty one says "the command printed nothing";
  - always, every line `suite.summary.show_re` matches (at most 20), such as a gate's red step
    (`exit 1: scripts/lint.sh`), never dropped to fit the cap;
  - always, last: the suite id, passed or FAILED (or interrupted, with the signal), the exit code,
    lane, seconds, tests, failures, skips, and the units ran and cached when given; then the log's
    path. A gate that wrote a result file with failures gets one line naming the failing ids (at most
    20).

  A log that cannot be opened is a warning, and the run streams as `--full` does.
- **`--full`** is the default with a terminal on stdin: the output is copied through unchanged as it
  arrives; when stdout and stderr are the same file the command gets one pipe for both.
- When the options do not parse, the command still runs, unrecorded, with a warning.
- When the command exits, `ccp` exits within a couple of seconds, even if a background child holds
  its output open. SIGINT and SIGTERM sent to `ccp` reach the command's whole process group; such a
  run is recorded as interrupted. No background or detached mode exists.
- **Environment:** the caller's, unchanged, plus `CCP_SUITE_ID` and `CCP_SUITE_RESULT`. `bin/ccp`
  sets no variable. A `QUEUE_ROOT` that `ccp` found from the binding stays `ccp`'s own. A `ccp suite
  run` inside it becomes its command, records nothing and writes no log.
- The run it belongs to is `--run`, else `--task` (and `--phase`)'s latest open run, else the one
  running worker run whose worktree holds the current directory; otherwise it is recorded unbound.

### 14.3 Counts: the gate-result contract and the output

- **The gate-result contract** (ADR-0014). A command may write a JSON result to `CCP_SUITE_RESULT`
  (`contracts/suite_result.schema.json`): `tests` (tests that ran), `ran` and `cached` (units run
  and served from the product's cache, in the product's unit), `cached_tests` (the tests behind the
  cached units), `skipped`, `failed`, `failures` (`[{id, message?}]`), `seconds` and `extra`; at
  least one of `tests`, `ran`, `cached`. When written and valid it is the run's record: the output's
  counts are not used, a counter it leaves out is absent (null), and `failed` defaults to the number
  of `failures`. It is read without following a symlink, at most 1 MB, and removed once read. Only
  counters are recorded; failure ids are shown in the summary and never recorded; `seconds` (the
  record keeps `ccp`'s wall time), `message` and `extra` are ignored. An invalid result gets its own
  summary line and a `result_problem` label, and the output's counts stand. `counts_from` says which
  (`result` or `output`).
- **Without a result file** the counts are read from the output: each line matched against
  `suite.count_re` (default `^Ran (\d+) tests? in `), the matches summed; `suite.summary`'s
  `failed_re`, `skipped_re`, `ran_re`, `cached_re` and `cached_tests_re` (a pattern or a list, first
  group a number, summed) give the rest. The defaults read Python unittest only (`OK (skipped=N)`,
  `FAILED (failures=N, errors=N, skipped=N)`); `ran_re`, `cached_re` and `cached_tests_re`
  match nothing until a product sets them. Their older names `modules_ran_re` and `modules_cached_re`
  are read; given both, the new name wins and `ccp tasks check` warns. `section_re`, `show_re`
  (default none), `tail_lines` and `max_chars` shape the summary.
- **An all-cached run:** with no test count found and the run saying 0 units ran and some cached,
  the test count is 0, not none; `cached_tests` is recorded beside it, and the summary ends
  `; N tests behind the cached results`.

### 14.4 Records and citing them

`QUEUE_ROOT/runs/_suites.jsonl`, append-only: a `started` and an `ended` row per run sharing a
`suite_id`, and a `suite/recorded` event at the end. Numbers, ids and short labels only: the lane,
the output mode (`output`), the command's basename and argument count; the `ended` row adds `tests`,
`failed`, `skipped`, `ran`, `cached`, `cached_tests` (null when not found), `counts_from` and summary
mode's `log` path. Never the command's arguments, never its output; the event carries the numbers,
not the path. A row naming `modules_ran` and `modules_cached` reads as `ran` and `cached`.

- **Reports cite them.** `Suite: from <suite_id>`, the preferred form, takes the tests, seconds and
  units ran and cached of that run, which must be recorded against the report's run and have ended
  with a test count. A report with no `Suite:` line takes them from its run's latest ended `full` or
  `gate` run with a count (`suite_filled: auto`), only when it passed; when it failed nothing is
  filled and `ccp report` warns, naming the run. A hand-written `Suite:` line stays valid and wins on
  the run record; a line in neither form is kept, records no numbers, and draws a warning. Health's
  suite series come from the suite records (§27); the line feeds them only for a run with no record.
  Counts on the line read `ran <r>, cached <c>` (the older `<r> modules ran, <c> cached` is read).
- **Verdicts cite them.** A `gate.runs` entry in `ccp verify record` may carry `suite_id`: its
  `exit_code`, `tests_run`, `tests_skipped`, `seconds`, `ran` and `cached` are filled from that run
  where the entry leaves them out, and `command` names it when absent. The suite run must be bound to
  the task's latest verify run. A differing `exit_code`, an unknown, unfinished or unbound run,
  another phase's, or an earlier verify round's is refused. `cold` stays the verifier's to give.
- **Logs are pruned.** A recording `ccp suite run` removes summary-mode logs
  (`runs/<task>/*-suite-st-*.log`, `runs/_suite-logs/st-*.log`) older than `suite.log_keep_days`
  (default 14): no other file, no symlink, nothing outside `runs/`, at most 5,000 looked at, a failure
  ignored.
- **Totals.** A `started` row with no end is `open` while the run may still be going and `killed`
  once its run has stopped, reported or been abandoned since, or after 30 minutes (its time runs to
  that stop or report when known). Totals count killed runs (`suite_killed`). `ccp suite list [--task
  ID]` prints rows and totals; `ccp usage` gives each run its `suite` totals and `ccp usage --task`
  the task's per phase; each board task row carries `suite_s`, `suite_runs`, `suite_killed` and
  `suite_phases`. A damaged suites file empties these totals and never breaks the board or `ccp
  usage`.

### 14.5 Recording never blocks the tests

When a command is given after `--`, it runs and its exit code is returned even when `QUEUE_ROOT` is
not set, there is no git checkout, `plane.json` is unreadable, an option is wrong (a bad `--lane`
label or `--phase`, an unknown flag) or a write fails. `ccp` prints one `ccp suite:` warning and
records nothing more. Only with no command to run does it exit 2.

## 15. Review, verification and merge

### 15.1 Standing DoD and the formal gate

The standing DoD (`dod/standing.yaml`) is harness-owned; a task supplies parameters and its
`dod_checks` only. Phases: unit and lint → the PR from the implementer's worker
(`mk_pr_via_implementer_resume`) and a clean separate review → formal-submit (a local checklist,
not the gate) → verifier approve → merge (`implementer_merge`, carried out by the runner once
`ccp verify merge-ok` exits 0). **Done** is all of them; post-merge smoke and production promotion are
outside it.

The `unit_lint` gate is **the verifier's own run** of the product's unit and lint commands on the PR
head, with `ccp tasks check` and `ccp docs check` where the product has `docs/delivery/plane.json`,
each through `ccp suite run` (§14). The verifier records each command, its exit code, tests run and
skipped, and seconds in its record's `gate` (`contracts/verification.schema.json`). A result the
verifier did not run is not a pass, with the one exception of §15.3. The gate needs no CI.

### 15.2 Review

- **Review starts on a settled head.** The runner opens a review (`ccp prompt review --head`) only
  once the task's open spec questions are answered and their rulings are on the PR. A commit landing
  while a review runs makes its head stale.
- **A fix round is reviewed again before it is verified.** `ccp prompt verify` refuses (exit 4,
  nothing opened) when the task's latest fix run that was not abandoned opened no later than its
  latest review run that reported `done`, or when `--head` is not the head that review judged (its
  run's `head`; a short sha matches). A head that differs from the reviewed one only by merging the
  integration branch, its own diff against its merge base unchanged (the same patch id), needs no new
  review; integration changes inside the PR's own hunks or their context lines change the patch id,
  and a head with no change of its own, or one that cannot be fetched, is reviewed again. A task with
  no runs passes. Only on the lead's or the operator's word, 
  `--allow-unreviewed-fix --reason "<their words>"` opens it anyway: the run records `allow_unreviewed_fix` (`reason`, `was`), a friction note
  with source `allow-unreviewed-fix` goes to `health/notes.jsonl`, and a `note`/`set` event to the
  ledger. `ccp verify record` refuses an approve under the same condition (judged at the record's
  `head_sha`) unless the task's open verify run carries that override; a reject is never held back.

### 15.3 A product's test cache

Where plane.json sets `verify.accept_cache` (`{"max_age_days": <n>, "cold_tasks": [<task-id
globs>], "review": <bool>}`):

- a test unit that the verifier's own gate run at the head reports as a hit in the product's
  content-keyed test cache (its recorded inputs identical to a pass under the same key) counts as
  run, and as passed. An entry older than `max_age_days` is no hit. Any other result the verifier did
  not run is still not a pass;
- the gate runs warm unless a `dod_check` asks for a cold run. A task whose id matches a
  `cold_tasks` glob, or whose frontmatter says `gate: cold`, has a cold gate (the product's cold
  option, nothing cached); `ccp tasks check` refuses another `gate` value;
- the gate run records `ran` and `cached` from its `ccp suite run` (the result file, else the
  product's `suite.summary` patterns; `modules_ran`/`modules_cached` read the same) and `cold: true`
  for a cold run. `ccp verify record` refuses an approve with no gate run giving both counts, and on a
  cold-gate task one whose counted run is not cold with nothing cached. The verify report's `Suite:`
  line ends `ran <r>, cached <c>`, and `ccp report` refuses a verify report without them;
- a suite run with cached units, from any worker, is a warm run, filed under `suite_seconds_warm`,
  never `suite_seconds` (§27);
- with `"review": true` (`verify.accept_cache.review`, off by default) the reviewer runs the modules the PR touches and those importing what it
  changed through the same cache, under the same rule; order-checking runs (any-order, reverse-order)
  and mutation runs stay uncached; the reviewer reports how many units ran and how many were cached.
  The verifier still runs its own gate.

`ccp prompt verify` renders the exception only for such a product, and `ccp prompt review` the
reviewer's only with `review: true`; without the setting each prompt is unchanged.

### 15.4 The verdict record

The verifier writes `verification/<task_id>.json` only through `ccp verify record <file>`, which
refuses, writing nothing, a record that fails the contract (a verdict other than `approve` or
`reject`, an extra key, a finding that is not a string, a check with no evidence), a `checked_at`
later than the write, a check marked not run that has a `pass` or names no `rests_on`, and an
`approve` that `merge-ok` would refuse (a failed check it ran, no `head_sha`, or no `gate` whose runs
all exited 0). A valid example is `contracts/verification.example.json`. `checked_at` is the clock
time the verdict was reached; `record` stamps it when absent. A check the verifier did not run itself
is `ran: false`, `pass: null`, and `rests_on` names whose claim it rests on: neither a pass nor a
fail. A product with `ci: github-actions` in its binding may cite a green CI run at the same head
(`gate.ci_run`) beside its own runs, never in place of them; `ccp verify record` refuses a
`gate.ci_run` otherwise.

### 15.5 Merge

The runner merges a PR only when `ccp verify merge-ok <pr> --task <task_id>` exits 0, and then pinned
to that head: plane.json `merge.command`, a template naming `{pr}`, `{head_sha}` (required) and
`{task_id}`; null means `gh pr merge {pr} --squash --match-head-commit {head_sha}`, with the PR's full
head `merge-ok` prints (`match_head_commit`). Close confirms the PR merged through `gh` (the merge
commit is the one `gh pr view` names; a merge `gh` accepts without merging, such as a merge queue,
stops it). `merge-ok` reads the PR with `gh` and refuses unless the PR is open, its head is the
record's `head_sha`, the record passes `ccp verify`'s rules and is `approve` with no failed check, it
carries the verifier's `gate` with every run at exit 0, its `task_id` names the record it is in, and
it was written no earlier than its `checked_at`. A refusal for a PR already merged says whether the
approval was recorded before or after the merge. `merge-ok` lists `unrun_checks`, `gate_runs` and
`match_head_commit`. A PR that is not a task's (a reconcile, a SPEC or ADR PR, a docs-only PR) is
approved in `verification/pr-<n>.json`, whose verdict's `task_id` is exactly `pr-<n>`. `ccp verify
check <task_id> --head <sha>` serves a merge step that has no `gh`.

### 15.6 Merge and verify rules

They hold for every PR the runner merges, a task's or not (ADR-0011).

1. **Merge only on an approval at the head** (§15.5). A verdict at another head, one written after
   the merge, or one relayed in a message is not an approval; a push after the verdict needs a new
   verdict.
2. **Merge only from the integration tip.** Under several runners `ccp tasks close` refuses a
   verified head that lacks code merged since (`behind_tip`; task-log-only commits do not count,
   §16.5 rule 4). The task branch takes the integration branch by a merge, never a rebase (a rebase
   needs a force-push). With one runner `close` does not run this check.
3. **Re-verify after an integration merge.** When the head moved only by merging the integration
   branch and the PR's own change is unchanged (same patch id), no new review is needed (§15.2). The
   verdict must still be at the new head: the runner opens `ccp prompt verify --head <new> --note
   "head moved by an integration merge; prior approve at <old>"`; the verifier runs the gate at the
   new head through `ccp suite run` (bound to this run), records each `dod_check` it does not rerun
   as `ran: false`, `pass: null`, `rests_on: "approve at <old>"`, and puts in `findings` the command
   showing the PR's own files are unchanged (for example `git diff <old> <new> -- <the PR's files>`
   printing nothing). A merge with a conflict, or one whose own change moved, is reviewed and verified
   in full.
4. **Minors before merge; reasons and the rest in the verifier's record.** A minor finding that
   could cost a later cycle is fixed before the merge. A second verify round with no fix round
   between says why in its `findings` (from the runner's `--note`); minor findings not fixed before
   the merge are listed there too. `ccp tasks close` writes the Verification notes line from that
   record; nobody edits a task's notes by hand.
5. **One seat runs an approved spend step** (a live step that spends allowance or money): the one
   the approval (gate or standing approval, §17.9)
   names; another seat that sees it pending asks that seat.
6. **Who writes the task file** is the §5 table: Implementation notes by the runner from the
   implementer's output, Verification notes by the verifier's record through `ccp tasks close`,
   `dropped` by the task-log owner (the lead).
7. **Code from outside the runner** reaches the integration branch through the task log: a task
   file, then implement, review, verify and gate. The lead's own commits to the integration branch
   keep `ccp docs check` green; a house rule whose check command does not exist yet goes in as
   `check: pass` until the task that builds it lands.

### 15.7 Optional CI and store tests

A product may copy `templates/github/workflows/formal-unit-lint.yml` to
`.github/workflows/formal-unit-lint.yml`. It runs `scripts/gate.sh`, `scripts/unit.sh` or `python3 -m unittest discover`, then `scripts/lint.sh`, calls no agent and reads no secrets; its result is
evidence only (§15.4). Store tests must not silently skip: in the verifier's run a skipped store test
counts in `tests_skipped` and is not a pass. The template's defaults are neutral: it ships no
database service, `STORE_TEST_PATTERN` is empty and `EXPECT_STORE_TESTS` is `0`. A product with store
tests adds its service, names the tests expected in `STORE_TEST_PATTERN` and sets
`EXPECT_STORE_TESTS=1`; then a skipped test matching the pattern fails the job, and so does a run in
which no matching test ran. A service password is an image default for an ephemeral database, never
a product credential. (Today's template still carries a database default; task 0014 makes it
neutral.)

### 15.8 Queue rules beside the gate

- **Steps only the operator's machine can run.** A step needing the live store or the operator's
  machine (a live upgrade, creating a database role) that the workers cannot take is parked with
  `waiting_on=operator_step` (`set-waiting-on.sh set <task_id> operator_step --detail "<step>"`).
  The task may merge code-only, the step listed as a follow-up. A parked step, and any check needing
  that machine, runs in a worktree of its own at the PR head (`ccp wt create --kind mac`), never in
  the main checkout.
- **The seat that rules does not produce its evidence.** The lead never runs a task's checks; with
  the no-combined-seats rule (§2), the verifier is the only producer of a verdict's evidence.
- **Shaping waivers.** The task-log owner never writes a shape of its own (§19.5). A task citing an
  ADR with no shaping record waits for the architect's shape unless its frontmatter carries `shaping: waived — <reason>`.
- **Triage of a committed file.** A triage file written by hand is applied with `ccp architect triage --apply <id>`: it validates the file, finalises `architect.json` (a `triage_sent` report
  becomes `triaged`) and rebuilds `docs/delivery/INDEX.yaml`, with no `claude -p` call.

## 16. Parallel runners

### 16.1 Intent

Tasks in unrelated parts of a codebase need not wait for each other (ADR-0012). The lead spawns up to
`max_in_flight` runner teammates sharing one queue-wide scope, each holding **one** task with its own
worktrees, workers and merge worktree; a teammate's Agent call blocks until its worker ends, so one
runner runs one worker at a time. Correctness never rests on declared paths: a task merges only from
a head that contains the current integration tip (task-log bookkeeping aside), verified there, and
git resolves the rest with no merge lock. Two merges that conflict: the later fails, and its
implementer resolves it. A merge landing between another task's catch-up and its merge is a small
window, accepted. Declared paths only decide what to start together. Off (`max_in_flight: 1`) is the
single-runner behaviour, exactly.

### 16.2 The knob

```json
"parallel": { "max_in_flight": 2, "exclusive": ["db/schema.sql"], "session_ceiling_pct": 60 },
"suite": { "exclusive_lanes": ["gate", "full"] }
```

No `parallel` block, or `max_in_flight: 1`: one task at a time. `max_in_flight` is 1 to 4;
`exclusive` lists paths and globs (`**` spans directories) whose concurrent edits git cannot merge
safely (a schema or migration file); `session_ceiling_pct` defaults to 60. Config loading validates
both blocks; unknown keys are refused. Lowering `parallel.max_in_flight` is completed by `stop --slot` for the
extra slots.

### 16.3 Which tasks may start together

**A task's paths:** its declared `paths:` frontmatter (§5); without it, the backticked tokens in its
Scope section's **In:** item (until `**Out:**`) that are paths (holding a `/`, ending in a file
extension, or naming a file or directory in the main checkout). A trailing `/` names a directory; a
bare file name meets any path ending in it. `parallel: false` always runs alone; `parallel: true`
(it changes no file, such as an operator step or a watch) runs beside anything.

**The active set** is `work.json` `in_flight`: every runner's claimed tasks not yet closed or
released, including one waiting on someone.

**The claim rules.** `ccp tasks claim C` (new, not a resume) beside a non-empty active set A is
allowed only when all hold; otherwise it refuses with exit 7, naming the rule and the task:

1. A has fewer than `max_in_flight` tasks.
2. No task in A or C says `parallel: false`; each has at least one path or says `parallel: true`.
3. No path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or
   bare name of one matching the other).
4. No path of C or of a task in A meets an `exclusive` entry.
5. The account's session-window usage, sampled at this claim, is below `session_ceiling_pct` (the
   gating session window, §25). A sample whose weekly figure is known but has no session figure
   means the account has no session limit: the rule passes. A sample with neither (no
   `allowance_cmd`, a failed read) refuses.

A claim into an empty active set is judged as single-runner; a resume is never refused by these
rules. A claim by a runner that already holds a task not closed or released refuses (exit 7).

**`ccp tasks next`** ranks as before (§10.3), then: if the first ready task not in A could not be
claimed beside A, it returns none (head of line: no task waits forever behind smaller ones);
otherwise it returns that task. Returning none because of A (full, head of line, the ceiling), it
exits 7 with `slots_full: true` and the in-flight tasks to resume; exit 3 still means nothing is
ready. `ccp tasks check` warns when a task not yet done has neither a path nor `parallel: true` while
`max_in_flight` is above 1: it will only ever run alone.

### 16.4 Queue state

- **Runners.** `work.json` `runners` maps each runner's **slot** (`runner-1` … `runner-N`; one
  runner: `runner.name`) to `bound_name`, `spawned_at`, `tasks_done`, `bind_pending`, `rotated_at`
  and `worktree`. The slot is stable across rotations; the bound name is not. The hook and `ccp
  prompt` map a teammate name to its slot through `bound_name`. `status`, `scope`, `review_point`,
  the preference list and holds stay queue-wide. With one runner and no `runners` map, `work.json`
  reads as single-runner (`runner`, `runner_tasks_done`).
- **Leases.** `tasks/<id>.json` `lease_holder` is the slot holding it, so a rotated runner resumes its
  slot's task. `ccp tasks claim <id> --holder <slot>` takes it; with more than one runner, `--holder`
  is required. A claim of a task another runner holds refuses (exit 3). The lease check and write hold
  the task file's lock.
- **Only the slot holding a task's lease opens its rounds.** `ccp prompt <phase> <id> --holder <slot>`
  names the caller; another slot is refused (exit 3), and with more than one runner `--holder` is
  required (exit 2). A new round never abandons a running round of that phase opened by another slot,
  unless the holder passes `--supersede` (exit 3 otherwise). With one runner the lease holder is the
  caller and nothing changes. `--holder` takes the slot or its teammate name (`bound_name`). With
  `--supersede`, a pending run of the same agent type for another task is also abandoned, once it is
  older than the 120-second grace.
- `in_flight` is every runner's tasks; each task's phase lives in `tasks/<id>.json`. `task_id`,
  `phase` and `lease` in `work.json` mean "the task a runner acted on last"; no decision rests on them
  alone.
- Every read-modify-write of `work.json` takes its lock (`file_lock`) and computes what it writes
  from the file as read under the lock (`save_work(edit=…)`): claim, release, close,
  `set-waiting-on.sh`'s writer and `team.py`'s. A wait, gate or question on one task never repoints
  `work.json` `task_id` (`set-waiting-on.sh` acts as with `--task-only`).

### 16.5 How the runners work

**The lead:** `team.sh runner spawn --count N` (N at most `max_in_flight`; default 1) records N slots
and prints one spawn per slot, each naming its slot; with slots recorded it adds slots up to N and
respawns none that are live. Claim rule 1 is the real bound: a runner beyond `max_in_flight` finds no
task and idles. `bind --as <slot>`, `rotate --slot`, `stop --slot [--drain]` act on one
runner; `stop [--drain]` with no slot on all. Gate decisions, question answers, a lead's `release` and the session wake (`--fire`, per parked task) name the bound name of the
task's holder.

**Each runner** (when `max_in_flight` is above 1):

1. **Its own worktree** (§12.1); `ccp tasks close` runs from there, so two closes never share a
   working tree.
2. **One task**, claimed with `--holder <its slot>`. Exit 7 from `next` means "nothing for you now":
   it idles until another runner's `idle_runners` message (rule 7) or the lead wakes it. A claim that
   exits 3 "held by <slot>" lost a race: it asks `next` again. A runner with no task while `next`
   exits 3 and others hold tasks idles without a report.
3. **Workers as before**: `ccp prompt`, then the Agent call, which blocks until the worker ends.
4. **Bring the head up to the tip before merging.** `ccp tasks close` fetches
   `origin/<integration>` and the verified head (`match_head_commit`) and refuses (exit 1, nothing
   merged, naming `behind_tip`) when the tip has a commit the head lacks that changes anything outside
   the task log (`git log <head>..origin/<integration> -- . ':!<tasks dir>' ':!<INDEX.yaml>'
   ':!<reconcile.log path>'` is not empty). Another task's reconcile alone does not hold a task back.
   A re-run after a failed reconcile (the PR already merged) skips the check. The task's implementer
   merges `origin/<integration>` into the task branch (a plain push; PRs squash-merge) and resolves
   any conflict; the task is verified again on the new head (§15.6 rule 3). A merge the hosting
   service refuses for a conflict is the same case.
5. **The reconcile retries on a moved tip.** When the push after a reconcile is rejected, or its
   rebase conflicts, `close` aborts the rebase, fetches, detaches at the fresh `origin/<integration>`
   and rebuilds: a task file already `done` there leaves nothing to do; otherwise it redoes the task
   file, the log entry, the reconcile hooks and the index, commits and pushes, up to 5 times. The
   legacy `post_close` runs once, after the push that lands.
6. **The session park parks every task in flight** (§25, exit 6), whoever holds it; the lead's wake
   resumes every runner.
7. **A freed slot wakes the idle.** After `ccp tasks close` or `release`, which name the runners
   holding no task (`idle_runners`), the runner sends each one message: "a slot is free: `ccp tasks
   next`".

### 16.6 Exclusive test lanes

plane.json `suite.exclusive_lanes` names the `ccp suite run` lanes that run one at a time in a queue
(a run with no `--lane` counts as `full`). A run of an exclusive lane takes
`QUEUE_ROOT/locks/suite-exclusive.lock` first. Held, `ccp suite run` exits 75 at once, saying who
holds it, since when, and the holder's usual duration; the worker does other work and retries.
`--wait SECONDS` waits up to that bound instead (the wait plus the run stay under the worker shell's
600 s limit), recorded as `wait_s` apart from the run's time. A lock whose holder process is gone is
taken over with a warning. Busy exits are recorded on the run (`lane_busy`).

### 16.7 Records, forecast, usage and the board

- **Actuals:** each closed task records `peak_in_flight` (the most tasks in flight during its window)
  and `undeclared_paths` (files its PR changed that its declared paths did not name). Calibration may
  split by `peak_in_flight` once enough tasks exist; until then it is recorded, not used.
- **Forecast** (§26): `max_in_flight` slots; a task starts at the earliest free slot after its
  dependencies; one without paths and without `parallel: true`, or touching an exclusive path, takes
  every slot; gaps between tasks are drawn only from closes with `peak_in_flight` 1. One slot is the
  single-runner model, exactly.
- **Usage:** the runner seat covers every slot's worktree and every bound name a `runner` event
  recorded (§24).
- **Board:** the Now card lists every in-flight task with its phase and time there; the Seats table
  has a row per runner (§28).

## 17. Spec questions, escalation and gate decisions

### 17.1 Escalation classes

Every worker question is classified `implementation` or `spec` (`spec` when unsure); `/review`
decisions use the same split. An **implementation** question is answered by the runner (no source
edits by it) and the worker resumes. A **spec** question goes to the spec maintainer, which is the
team lead (ADR-0005), through the question channel (§17.3). Nothing emails: whatever needs the operator is raised in the lead's session (§17.10). None of
this relaxes the rules on keys and wallets (§30), quota (§18.4), operator gates (§3.2) or the ledger
and observability (§23).

### 17.2 Who decides

| Kind of issue | Who decides |
| --- | --- |
| Implementation choice (library, structure, naming, test approach, anything the spec leaves to the builder) | The runner or its implementer. No question |
| Spec ambiguity or gap | Spec maintainer |
| Task brief contradicts SPEC or PROJECT | Spec maintainer |
| SPEC versus PROJECT tension | Spec maintainer |
| A task's `dod_checks` or cited SPEC inconsistent with each other | Spec maintainer |

The runner raises spec questions, including ones its implementer, reviewer or verifier classifies as
`spec`. Only the spec maintainer may return `needs_operator`; seats never contact the operator about
spec questions. The operator gates (§3) are not spec questions and keep their route (§17.9). No
binding is needed for the lead to be the maintainer; an older binding's `spec_maintainer` block is
accepted (`kind: team-lead` only; a `claude-session` block is reported as removed; only its
`protocol_doc` is read). The lead's protocol is the
plugin's `spec-maintainer` skill, or the product's `docs/delivery/SPEC-MAINTAINER.md` where one is
installed.

### 17.3 The question channel

**Question file.** `scripts/spec-maintainer-ask.sh raise` writes one file per question at
`QUEUE_ROOT/questions/<question_id>.json` (`contracts/question.schema.json`), `question_id`
`sm-<UTC yyyymmddThhmmssZ>-<4 hex>`: `task_id`, `project_id`, `question_id`, `class` (`spec`),
`text`, `inconsistency`, `spec_refs`, `tried`, `blocks` (the task ids that cannot proceed; at least
`task_id`), `raised_by`, `route` (`spec_maintainer`), `status` (`open`, `answered`, `escalated`),
`dispatch`, `lead_messaged_at`, `answer_ref`, `asked_at`, `updated_at`. `--task-id` and every
`--blocks` entry must be a task id (an existing task when the log is reachable); anything else is
refused before any write. Older files carrying `route: steerer` or a removed `dispatch` value
(`queued_lock`, `quota_parked`) are read as open questions for the lead.

**Raise.**

1. Write the question file.
2. Set `waiting_on=spec_maintainer` on each task in `blocks` (`set-waiting-on.sh`,
   `--detail <question_id>`).
3. Emit `question`/`raised`.
4. Print the one message the runner sends the lead: the question id, the task, the blocked tasks and
   the paths of the question and answer files.

The lead rules in its own session and writes the answer file; the runner skips ahead meanwhile
(§17.7) and, on the lead's reply, runs `spec-maintainer-ask.sh process <question_id>`, which applies
the answer (§17.5). A raised question is marked `dispatch: in_call`. Before an answer exists, `process` reports
`waiting_on_lead` and sends the lead message once to a question that
has no `lead_messaged_at` (one raised by the steerer route, a headless call that died, or a lock or
quota queue), moving its tasks' old `steerer` or `quota` wait to `spec_maintainer`; otherwise it says
to skip ahead. The same hand-off serves review triage (§19): the triage command prints a
`send_message_to_lead` action with the fixed triage prompt, the lead writes the triage file in its
own session, and the triage command is run again to apply it.

### 17.4 Authority of the spec maintainer

- **May edit and commit:** `docs/PROJECT.md`, `docs/SPEC.md` (or `spec/`), and the context section of
  durable task files.
- **Chooses the route itself:** rule and commit, or escalate with `needs_operator`; no second reviewer.
- **Every `resolved` ruling lands in git**, `commit_sha` required. A ruling that needs no SPEC or
  PROJECT wording is recorded in the context section of each blocked task file.
- **Commit rule:** only the files it changed, by explicit path (`git commit -- <paths>`), on the
  integration branch, pushed; message `spec(<question_id>): <one-line ruling>`. If it cannot commit
  or push, it returns `needs_operator` and says why.
- As the task-log owner the lead creates tasks and amends their intent, `dod_checks`, ids and
  dependencies, never once a task is claimed without superseding it (§5).

### 17.5 Verdicts and the answer file

The lead writes `QUEUE_ROOT/questions/<question_id>.answer.json`
(`contracts/question_answer.schema.json`):

```json
{
  "schema_version": 1,
  "question_id": "sm-20260925T083400Z-a1b2",
  "project_id": "example-product",
  "verdict": "resolved",
  "ruling": "A retry limit of three applies to every import.",
  "reasoning": "SPEC Imports states the limit; the task brief predates that edit.",
  "commit_sha": "3e1f0c2",
  "files_changed": ["docs/SPEC.md", "docs/delivery/tasks/0004-import-retries.md"],
  "question_for_operator": null,
  "guidance": null,
  "answered_by": "spec_maintainer",
  "session_id": "<the lead's session id>",
  "answered_at": "2026-09-25T08:36:10Z",
  "supersedes": null
}
```

| Verdict | Required fields | What `process` does for the runner |
| --- | --- | --- |
| `resolved` | `ruling`, `reasoning`, `commit_sha`, `files_changed` | Clears `waiting_on` on the blocked tasks (`spec_resolved`) and prints the actions: a durable note on each blocked task, pull the worktrees, pass the ruling and sha into the next implementer prompt |
| `needs_operator` | `reasoning`, `question_for_operator` | Moves the blocked tasks to `waiting_on=operator_decision` (§17.6) and prints `wait_for_lead` |
| `not_a_spec_question` | `reasoning`, optional `guidance` | Clears `waiting_on`; the runner decides it as an implementation choice and notes the decision |

`answered_by` is `spec_maintainer`, or `operator_via_maintainer` after the operator rules. A
rewritten answer keeps the previous verdict object under `supersedes`.

### 17.6 needs_operator

The lead asks the operator in its own session. When the operator rules, the lead records it exactly
as a `resolved` ruling: commits the change and rewrites the answer file with `verdict: resolved`,
`answered_by: operator_via_maintainer`, the `commit_sha`, and the previous `needs_operator` object
under `supersedes`. It then tells the runner, which runs `process` again (`question`/`resolved_by_operator`,
waits cleared).

### 17.7 Skip-ahead

While a question is open, **only** the tasks in its `blocks`, plus their `depends_on` descendants,
wait (`spec-maintainer-ask.sh blocked` lists them); every other task continues. A question never
parks the whole project; descendants not yet started stay unclaimable without a `waiting_on`. The
gate's "no open spec escalation" applies to a task only while an open question lists it in `blocks`.

### 17.8 Events, waits and the board

| type | op | payload (required keys) |
| --- | --- | --- |
| `question` | `raised` | `question_id`, `raised_by`, `blocks`, `route`, `spec_refs` |
| `question` | `answered` | `question_id`, `verdict`, `answered_by`, `commit_sha?` |
| `question` | `escalated` | `question_id`, `blocks`, `email_sent` (bool; historical) |
| `question` | `resolved_by_operator` | `question_id`, `commit_sha` |

`spec_maintainer` (`set`, `clear`, `rebound`) rows and `claude` events with `phase: spec-maintainer`
in older ledgers are read past; nothing writes them. `waiting_on` is `spec_maintainer` while a
question is open and `operator_decision` once escalated, `detail` naming the `question_id`; both are
blocker kinds.

### 17.9 Gate decisions

**Authority.** The operator delegates to the lead (the design seat) the approval of anything the
runner needs to proceed: merges, live-store operator steps, spend within the project's allowance
rules, and every other operator gate a runner can hit (§3). Whether a gate also needs the operator is
the lead's judgement. The runner never approves its own gates and never asks the operator directly.
The lead must still bring a gate to the operator when:

- it would contradict a decision the operator recorded (PROJECT, SPEC, the plan, an ADR, a task, or a
  commit attributed to them), standing rules such as the allowance checkpoint included;
- it needs the operator's hands: SSO or reauth, putting a credential into `.env`, payments, anything
  requiring a login only they have;
- it is production promotion, or an irreversible destructive operation without a verified backup (a
  live-store step with a fresh, verified backup rehearsed on a restore is not irreversible).

**Record.** A gate is an escalation file (`escalations/<task_id>/<n>.json`, id `<task_id>-<n>`,
`contracts/escalation.schema.json`) with `to: design_seat` and a `class` (`operator`, `spend`,
`merge`, `credential`, `security`, `reauth`, `other`). All writes go through `scripts/team.sh gate`:

| Command | Seat | Effect |
|---|---|---|
| `gate open --task-id … --class … --brief … [--ask …]` | runner | file `open`; `waiting_on=design_seat` (detail = id); `gate`/`opened`; prints the message for the lead |
| `gate open … --standing <ref>` | runner | file `closed`, `approved`, `decided_by: standing`, `authority: <ref>`; no wait |
| `gate decide <id> --decision approved\|refused --resolution … --authority … [--by …]` | lead | file `closed` with `decision`, `decided_by` (`design_seat`, or `operator_via_design_seat` after `ask-operator`), `authority`, `decided_at`; `gate`/`decided`; clears the wait |
| `gate ask-operator <id>` | lead | file `waiting_operator`; `waiting_on=operator_decision`; `gate`/`escalated` |
| `gate status <id>` | runner | exit 0 approved, 3 open or waiting on the operator, 4 refused |

The runner acts only when `gate status` exits 0. The mailbox notifies; it does not record.

**Standing approvals.** A review point in the product's plan may list pre-approved gates (operator
steps with backup and rehearsal, a spend envelope). The runner treats them as closed (`--standing <ref>`) without asking. The lead writes them with the operator when it defines the review point.

**Harness limits.** The harness treats a message from another agent as not coming from the user, and
an approval relayed by another agent as untrusted. Nothing here works around that: the authority
rests on the operator's written grant; the runner's operator commands are pre-approved in the
product's `.claude/settings.json`; where the harness still blocks an action, the runner reports it to
the lead, who takes it to the operator.

### 17.10 Route to the operator

Nothing emails. Whatever needs the operator is raised in the lead's session: the runner's question or
gate reaches the lead through the mailbox, and the lead asks the operator or decides it (§17.9). The
operator may open a runner directly; what they say there counts as coming from them but does not move
authority: the runner still records gates through escalation files.

## 18. Liveness, operating window and quota

### 18.1 Operating window

The plane runs around the clock, all days (ADR-0032). There are no quiet hours: while unfinished
durable tasks remain and allowance is available, work continues. On a wait (`operator_decision`,
`reauth`, `quota`, …) the normal routes apply (§17); the operator unblocks when they can.

### 18.2 The `TeammateIdle` hook

The lead gets the runners' idle and failure notices. The `TeammateIdle` hook
(`templates/claude-hooks/runner-idle.sh`, installed by the plugin) keeps a runner working:

- It acts only on a bound runner (`work.json` `runners` bound names, else `runner`, else
  `runner.name`), only while `work.json` says `status: running`. It fires inside a runner's subagents
  too, with the runner's `teammate_name`; it acts only when there is no `agent_id`, or `agent_type` is
  `runner.agent_type`.
- Every input's non-secret fields (a whitelist: event, teammate and team name, agent id and type,
  session id, cwd, permission mode, and the list of keys) are appended to
  `observability/runner-idle-inputs.jsonl` (trimmed past 256 KiB); its block counter per slot is in
  `observability/runner-idle.json`. With no `work.json` it exits before logging.
- It exits 2 ("scope not finished: <task_id> is ready") when the task the runner holds is ready (not
  waiting on anyone), or, when it holds none, when a task in scope is ready (a legacy `in_progress` file status, whatever its dependencies; or
  `pending`, or a legacy `blocked` read as pending, with its dependencies done) and not held by
  its runtime `waiting_on`, an open question's `blocks`, or an undecided gate. `work.json`'s own
  `waiting_on` is not a scope-wide stop.
- It lets the runner go idle when its slot's rotation is due, after `runner.idle_block_limit`
  consecutive blocks on the same ready set (default 3), and while a task is parked on a session window
  (`waiting_on: quota`, `quota_class: session`) with its `planned_resume_at` still ahead. A park past
  its `planned_resume_at` has expired and holds nothing back.

### 18.3 Seat liveness

Every seat is event-only under the Claude team: never time-stale. `design-seat`, `task-runner` and
`task-verifier` are seat ids; the toolkit writes heartbeats (`observability/seats/<seat_id>.json`,
`seat`/`heartbeat` events, `heartbeat.sh`), and `ccp tasks claim` and `close` write them. There is no
stale rule for seats and no `stale_seat` blocker, and no `verify_stale` blocker: the verifier is the
runner's subagent and reports by message and file (§15).

### 18.4 Quota

- A quota wait is `waiting_on=quota`: not a failure, never a stall to stop.
- **The session park and wake.** At a usage window's park threshold (§25; the built-in five-hour
  window parks at `telemetry.session_park_pct`, default 95), `ccp tasks claim` and `ccp prompt` park
  every task in flight until the window's actual reset plus a margin and exit 6; the lead keeps a
  one-shot wake armed at that reset (`ccp allowance session-wake`), armed before the limit while the
  lead can still act. The weekly checkpoints stop for the operator (§25).
- **A credit quota park** (`quota_class` other than `session`) has no wake of its own: the lead
  re-checks every task parked on quota at its next session start and resumes those whose quota has
  recovered.
- The twelve-hour runaway backstop is retired (ADR-0032).

### 18.5 Not covered, and permission prompts

Laptop sleep, the lead's exit and a host restart are not covered: nothing inside the session survives
them. Recovery is the operator resuming the lead, which respawns the runners (§10.2 step 5).
Teammate permission prompts appear in the lead's session and block while the operator is away, so
before a run the runner's commands (tests, `ccp`, `gh`, git by path, the product's operator commands)
are pre-approved in the product's settings.
