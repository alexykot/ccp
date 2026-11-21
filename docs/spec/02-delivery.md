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
   the scope, the queue root and the slot). The spawn prompt holds nothing else. Unless a product
   still sets `refactor_in_scope` to `true` or `false` (§20.4, §29.3), a spawn that starts a new
   review point puts every waiting refactor
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
4. **Rotate.** When its slot's `tasks_done` reaches 4, or the
   runner seat's request context reaches its limit (off unless a binding still sets one, §29.3), rotation is
   due:
   `ccp tasks claim` refuses the slot a new task until the lead rotates it, and from the rotation until the lead binds the fresh runner (`team.sh runner bind`), so the runner being rotated out takes no new task.
   The runner finishes
   the current phase, writes `work.json` and asks the lead to rotate it, as it also may sooner when
   its context gets heavy. The lead records it (`team.sh runner rotate
   [--slot]`), shuts it down, and only once it is gone spawns a fresh runner with the same prompt.
   The harness may give the fresh one a suffixed name; the lead binds the name the Agent result
   gives (`team.sh runner bind --name <it> [--as <slot>]`) and stops the old one if it is still
   there.
   From the rotation until that bind no teammate of the slot is kept working (§18.2).
   Workers' prompts, the hook and the
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

`ccp tasks next [--scope IDS] [--explain]` returns, of the `pending` tasks whose `depends_on` are
all `done`, the lowest-numbered; a dependency may have a higher number than its dependant.
`--scope` (task ids or `NNNN`) restricts the candidates (their dependencies may lie outside it);
while `work.json` `status` is `running`, the scope defaults to `work.json`'s. It reads each task's
status at the integration tip: when the checkout lacks commits of `origin/<integration branch>`
(nothing is fetched), each task's status is its file's there. A task still pending there that the
queue holds `done` or `dropped` is skipped, and counts as done for no dependant until the task log
says so. The order:

1. **The lead's preference list** (`work.json` `next_tasks`, §10.4): its first entry that is
   ready and in the scope (or one the scope reaches, §20), its `why:` line giving its place ("2 of
   3"). An entry waiting on a dependency is skipped and keeps its place; one done, dropped, unknown
   or out of scope is ignored with a note on stderr.
2. **The review point's refactors** (`review_point_refactors`, §20).
3. **The plane's own order** (`ccp/selection.py` `ranked`, shared with the board).

A task whose `brief` sign-off is due and not recorded, is stale, or whose `sign_off:` value is malformed (§3.5) is passed over the same way, and stderr names which, so the runner takes the next task it can claim.
A held task (§10.4) is passed over, a held refactor and a held preference alike, and stderr says so;
`--explain` prints the whole ranked queue with the pick and the holds marked. The runner always
takes `next`'s pick and turns a lead's "take X next" back to the lead as `ccp tasks prefer X`. With
several runners `next` also applies §16.3 (head of line, exit 7). With no gate lane it names no task
and exits 2 (§14.1).

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
- **Release** (lead or runner). `ccp tasks release <id> [--keep-branch] --reason "…"` undoes a claim: a task leased
  (or blocked) in the queue with no run at all (nor, from before run records, a prompt audit) or,
  with `--keep-branch`, a claimed task whose runs are all closed, keeping its branch and PR, goes
  back to `pending`. Its wait is cleared through `set-waiting-on.sh`, its phase moves to `pending`
  (the `queue/pending/` marker), then a `lease` `clear` event with `released: true` and the reason;
  `lease_since`, `claimed_at` and `implementation_started_at` are cleared, and it leaves `work.json`
  as `ccp tasks sync` does (out of `in_flight`, the next task in flight becomes current, none left
  makes `runtime_status` `idle`). The worktree and branch are kept, and a later claim resumes in
  them. It refuses (exit 3) a task with no lease, in another status, or with a run; with
  `--keep-branch`, one with an open run, one `merging` or one merged by close. No `--reason` is
  exit 2. A hold stays; a preference entry the claim removed is not restored. A task's time starts
  at its first claim after its last release.
- **Drop** (lead or runner). `ccp tasks drop <id> --reason "…"`, for a task its file on the integration tip marks
  `dropped` whose PR did not merge, whatever its phase: it abandons its open runs (`task dropped`),
  clears its wait and lease, sets the queue status `dropped`, takes it out of `work.json` and prints
  `idle_runners`. Its worktree and branch are kept.
- **Sync.** `ccp tasks sync` makes the queue follow the log for tasks done or dropped there; it
  skips a task still leased in a mid-flight phase (close or drop settles it) and never takes a
  lease from a live runner.

### 10.5 Claim and close

**`ccp tasks claim <id> [--holder <slot>]`** runs the product's auth probes first
(`auth_check.probes`, §30) and exits 8 when one fails: no task is taken, the claim fires the `blocker` notice (§3.6), and the runner raises a `reauth` gate to the lead (probes: `[{id, cmd}]`, each given 60 seconds).
Before the probes, a new claim of a task that declares a `brief` sign-off with none recorded, or with a
stale one (its head lacks the task file's last change), or whose `sign_off:` value is malformed, exits
3, naming it; no task is taken (§3.5).
Then it takes the lease, writes `work.json` (`task_id`, `phase`,
`runtime_status`, `in_flight`) and `tasks/<id>.json` from the task file, makes the task's implement
worktree (`ccp wt create --kind impl`, §12), takes an allowance reading (§25.1) and writes a heartbeat. A
`draining` or `stopped` `work.json` refuses a new task. A legacy `in_progress` or `blocked` file
status reads as `pending`. With several runners, §16.3 and §16.4 apply.

**A claimed task's file is edited only in its PR.** From the claim until the lease clears (close,
release, drop or sync), the task's file changes on the integration branch only by the task's own squash
merge and reconcile, and by the lead marking it `dropped` (§10.4). A ruling or clarification on a
claimed task goes to the runner holding it, which passes it verbatim in the next implementer prompt;
the implementer writes it into the task file's `Context (not checked)` section on the task branch,
besides its Implementation notes, so it lands in the task's PR (§17.4). A change to the task's
intent, scope, `dod_checks`, id or dependencies is not a clarification: it follows the task-log
owner's limit (§17.4: never once a task is claimed without superseding it), so the runner releases
the task (with `--keep-branch` once its runs are all closed, keeping its branch and PR, §10.4) or the
lead supersedes it, and the lead edits the file unleased on the integration branch; a released task
is claimed again under the same id and resumes on its branch.
**`ccp tasks check --lease [--staged]`** (needs `QUEUE_ROOT`) exits 1 naming each such edit, with the
task and its lease holder, for every task with a live lease (`lease_holder` set, the queue status
neither `done` nor `dropped`): the commits on the integration branch's first-parent history (the
local branch and `origin/<branch>`, each that exists; nothing is fetched) committed after
`lease_since` that change the task's file; with `--staged`, the staged change instead, only while
HEAD is on the integration branch. The task's own squash merge and reconcile are known by their
subject, in the §10.7 rule 1 and 2 forms (any commit in those forms passes); a lease with no
`lease_since` is timed from `claimed_at`, and one with neither stamp is not judged.
It reads git and the queue and writes nothing; `ccp tasks check` without the flag does not run it. The
plane's commit hook template (`scripts/git-hooks/pre-commit.template`) runs it with `--staged` when
`QUEUE_ROOT` is set and `ccp` is on PATH, and refuses the commit only on exit 1.

**`ccp tasks close <id> --pr N [--summary "…"]`** is one resumable step:

1. `ccp verify merge-ok` and the merge pinned to the verified head (§15.5). It refuses before
   merging when the checkout it runs from has changes or a rebase in progress; with several runners it
   refuses a head behind the tip unless it catches it up (§16.5 rule 4). It refuses (exit 1) a task
   whose due sign-off (§3.5: declared, or `build` from its verdict's `spec_beyond_intent`) is missing,
   or whose `build` sign-off covers another head than the one it merges and close's own catch-up did not carry it there (§16.5 rule 4), or whose
   `sign_off:` value is malformed, naming it; nothing is merged, and on a re-run after a merge the
   reconcile waits for it too.
2. **Reconcile:** the task file's status and Verification notes line (from the verifier's record),
   dated by the clock; `review_point` stamped when the task has none; `ccp tasks index` and
   `check`; the product's `reconcile.log` entry and `reconcile.hooks` (§8; a hook must be
   idempotent, a re-run runs it again); a commit by path and a push, retried once after a fresh
   pull. There is no `--no-push`. The reconcile is made, its hooks run and it is pushed in close's
   own **merge worktree**, `merge-<nnnn>` under the worktree directory (§12.1), detached at `origin/<integration>`
   with the `worktrees.links` linked in; close removes it once the reconcile has landed, and a re-run
   after a failed reconcile discards what the earlier close left in it. With it, the main checkout's
   HEAD and branch never move. A product that still sets `worktrees.dir` to null (§29.3) reconciles
   in the checkout close runs from.
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

### 10.7 Changes from outside the plane

A change made outside the runner (by another agent, the operator directly, a tool) reaches the
integration branch through a task (§15.6 rule 7): the lead writes a task for it, and the change comes
in on that task's branch through implement, review, verify and the gate like any other.

A change that merged first gets an **after-the-fact task**: a task, of the kind its change fits,
whose frontmatter `covers:` lists the merged commits (an inline list of shas, each 7 to 40 hex
digits, a prefix naming its commit). The lead names those commits in the task's Scope and writes its
dod_checks for what the change lacks against the standing DoD (tests, SPEC text, docs), so the
implementer, review and verify see the named change through the task file.

**`ccp tasks orphans --since <ref> [--json]`** lists the commits on the integration branch's
first-parent history after `<ref>` that no task covers, oldest first. The integration branch is the
binding's (with `QUEUE_ROOT` set), else `main`; the tip is `origin/<branch>` when that ref is in the
checkout, else the local branch, and nothing is fetched. The task log read is the checkout's, so a
covering task merged on the remote counts once the checkout has it. A commit is covered when:

1. it is a task's merge (§27.1): a merge commit, or a commit whose subject ends `(#N)`, that merged
   a `task/<NNNN>-…` branch or whose subject starts `Task <NNNN>: `, for a task in the log;
2. it is a reconcile commit as `ccp tasks close` writes it (`Reconcile <NNNN>: done (PR #<n>,
   squash <sha>)`, §10.5) for a task in the log;
3. a task not `dropped` names it in `covers:`; or
4. it changes nothing outside the task log (its task files, `INDEX.yaml`, the reconcile log) and the SPEC files (`spec_paths`): the lead's own task-log commits and spec rulings, however they were merged.

A merge commit is one commit: its change against its first parent. A `covers:` entry that is not a
sha is a warning. Exit 0 with nothing listed, 1 with a commit listed, 2 when a ref does not
resolve. It reads git and the task log only and writes nothing; it blocks no push.

## 11. Runs and process locks

### 11.1 Runs

A **run** is one launch of one worker for one phase of one task: the unit time and tokens are
reported in.

- **Id:** `<task_id>/<phase>[-<n>]`, phase `implement`, `pr`, `review`, `fix`, `verify`, `merge` or `ruling`,
  the same name as its report file `progress/<task_id>/<phase>[-<n>].md`. Runs outside a task:
  `_runner/spawn-<n>`, `_architect/<review_id>`, `_triage/<review_id>`.
- **Record:** `QUEUE_ROOT/runs/<task_id>/<phase>[-<n>].json` (`contracts/run.schema.json`):
  `run_id`, `task_id`, `phase`, `round`, `seat`, `agent_type`, `expected_model`,
  `expected_effort`, `prompt_ref`, `mode` (`resolution` on a resolution review, §13.2), `resolution` and
  `affected_checks` (a resolution review's report lines, §13.4), `opened_at`, `opened_by` (the runner slot), `agent_id`,
  `session_id`, `worktree`, `started_at`, `stopped_at`, `reported_at`, `abandoned_at`,
  `abandoned_reason`, `abandoned_by`, `outcome`, `suite_tests`, `suite_seconds`, `severity`
  (BLOCKER, MAJOR, MINOR, NIT counts), `friction_count`, `usage` (§24), `observed_models`,
  `observed_efforts`, `integration_merges` and `before_review` (a done implement, fix, merge or ruling
  round with a head).
  `ccp report` computes them when the round reports, never from the report's prose: `integration_merges` lists,
  oldest first, the merge commits on the head's first-parent line, from the task's previous done change round's
  reported head (for its first, from `origin/<integration>`) to this head, whose second parent is an ancestor of
  `origin/<integration>`, leaving out every commit already on `origin/<integration>` (a branch rebuilt on a newer
  tip does not count the tip's own merges), each as `{sha, conflicted, files}` (whether git's own merge of its two
  parents conflicts, and in how many files, `ccp/gitmerge.py`); `before_review` is true when the round opened before
  the task's first review run that reported `done`. A round that cannot be measured (no product checkout, a commit
  not in the object store, a failed merge probe) records no `integration_merges`, and its report is accepted.
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

`ccp wt create --kind KIND --task ID [--sha SHA] [--name N] [--seat S] [--tag T] [--shallow]` makes a git
worktree under the worktree directory, `.plane-runtime` in the main checkout (a `worktrees.dir` a
product still sets, which applies with a warning, §29.3, is a path relative to the main checkout,
which may lead outside it with `..`, such as a sibling directory, or an absolute path; not the main
checkout itself), named
`<kind>-<nnnn>[-<n>]`. Kinds: `impl` (the implementer's, on `task/<id>` from
`origin/<integration>`; `ccp tasks claim` makes it), `rev` and `ver` (detached at the head they
judge), `mut` (a mutation copy) and `mac` (a machine check), all detached at `--sha`, and `base`
(below).
`worktrees.links` are linked in from the main checkout and named in the repository's
`info/exclude`. Each worktree is recorded in `QUEUE_ROOT/worktrees/<name>.json`
(`contracts/worktree.schema.json`): kind, task, seat, tag, path, branch, sha, state and URLs.

- `ccp wt list [--task ID]` shows the records and any unrecorded worktree; `ccp wt remove NAME`
  removes one.
- `merge-<nnnn>` is `ccp tasks close`'s own worktree, not a `ccp wt` kind and not recorded: close
  makes it for the reconcile and removes it once the reconcile has landed (§10.5).
- `arch-<review id>` is an architect pass's own worktree (§19.7), not a `ccp wt` kind and not recorded:
  the pass makes it detached at the head it reviews, links `worktrees.links` into it, and removes it
  when it ends, as does the check that marks a dead pass `failed`. With no `worktrees.dir` the pass runs
  in the product root.
- `ccp tasks close` removes every worktree of the task, and its branch. `ccp tasks drop` and
  `release` keep them: an implementer may still be working there, and a later claim resumes in them.
- `ccp wt gc` prunes git's worktree list, forgets records whose worktree is gone, and removes the
  worktrees of tasks done or dropped in the queue and leased by no one.
- A worktree made before records (`impl-`, `rev-`, `ver-` with the task's number) is removed by
  close, or adopted by `create`. `create` reuses an existing worktree only at the `--sha` asked for;
  at another head it refuses (exit 3). A default name taken meanwhile moves to the next `-<n>`. Under a worktree directory that resolves outside the main checkout (a `worktrees.dir` a product still sets, which applies with a warning, §29.3), which another checkout may share, a directory with no worktree record is listed by `ccp wt list`, removed by `ccp wt remove NAME` or by close's fallback, swept by `ccp wt gc`, or adopted by `create` only when `git worktree list --porcelain` run in the main checkout names it; `ccp wt remove NAME` and `create` refuse any other (exit 3), and the rest leave it alone. Inside the main checkout these act on any matching directory, as above.
- Workers make theirs with `ccp wt create`, never `git worktree add`.
- A worktree's kind, seat and round reach what runs for it, besides its name: a worker's
  `prompts.worker_env` templates get `{{kind}}`, `{{seat}}` and `{{round}}` (§8.1, §13.3), and a lane's
  stages run in it get `CCP_WT_KIND`, `CCP_WT_SEAT` and `CCP_WT_ROUND` with its task as `CCP_TASK_ID`
  and `CCP_NNNN` (§14.2).
- `--shallow` (kinds `rev`, `ver`, `mut` and `mac`) makes it a clone of depth 1 at `--sha` (a short sha
  is resolved first), not a git worktree, so a check can prove a test passes without git history. Its
  git-LFS files are checked out with the smudge filter skipped, then filled from the main checkout's LFS
  store (a file whose object the store lacks stays a pointer, with a warning that `git lfs fetch` in the
  main checkout fills it). The merge base of `--sha` and `origin/<integration>`, taken in the main
  checkout, is fetched into it at depth 1 and recorded as `merge_base`, which `ccp mutate --revert` uses
  there (no merge base is a warning, and none is recorded). It fetches that commit by its sha from the
  main checkout, which needs git protocol v2 (git's default since 2.26). It is recorded with `shallow: true`, set up and removed like any other (removing
  deletes the clone), and its links are named in its own `info/exclude`. An existing worktree is
  reused only as shallow as asked (exit 3 otherwise); `--shallow` is refused (exit 2) on any other
  kind or action.
- `ccp wt exec [NAME] -- ARGS` runs the `bin/ccp` of worktree NAME (recorded; default the checkout
  `ccp` runs in: `--root`, else `$CCP_ROOT`, else the working directory's git toplevel) with ARGS
  verbatim, in the caller's directory and environment, and exits with its code; `--print` prints that
  path instead, which shows which `ccp` runs. NAME with no `QUEUE_ROOT`, or no NAME outside a git
  checkout, is refused (exit 2). It loads no plane.json, so a reviewer or verifier can run
  the change under review's own `ccp`, new subcommands included; `ccp` on PATH stays the released one.
- `ccp wt create --kind base --task ID --sha HEAD [--timeout S] -- COMMAND` runs COMMAND (argv, no
  shell) on the task's merge base: it fetches (a failed fetch is a warning that the base, taken from
  `origin/<integration>` as last fetched, may be stale), makes a `base-<nnnn>[-<n>]` worktree detached
  at the merge base of HEAD and `origin/<integration>`, recorded (with `head`) and set up like any
  other, runs COMMAND there in its own process group with its output passed through, then removes the
  worktree and its record whatever COMMAND did, and whatever failed once the worktree was made. It
  prints `{name, head, merge_base, exit, removed, timed_out}` and exits with COMMAND's code (127 when
  it is not found, 128 + N when signal N ended it). COMMAND still running after `--timeout` seconds
  (default plane.json `env.timeout_seconds`) is killed with its process group: exit 124. A descendant
  that left that process group and keeps COMMAND's output open is not killed, and holds the run open
  past the timeout until it exits or closes the output. A SIGTERM to `ccp` kills COMMAND's process
  group, removes the worktree and its record, and exits 143 with `signal: 15` in the result; one that
  comes before the worktree exists exits 143 as well, its result naming no worktree (`name` null) and
  nothing run. Its own refusals and failures exit 125, so they never read as a COMMAND's 2 or 3,
  print why on stderr and no result: no command or no `--sha`, a bad `--timeout`, a HEAD with no
  merge base, a `--name` already in use, a worktree that could not be made or recorded. A command,
  or `--timeout`, is refused (exit 2) on any other kind. A dry run on the merge base (§15.1) uses it,
  never `git stash` or a hand-made worktree.
- `ccp wt create --kind ver --baseline [--seat S] [--tag T]` makes the one worktree that needs no task:
  `ver-baseline`, detached at `origin/<integration>` after a fetch, recorded with an empty task and
  number (`{task_id}` and `{nnnn}` are empty in its hooks) and set up like any other. An adopting lead
  runs the gate lane there once, to learn whether the tip is green before the first verifier does
  (§4.5), then removes it with `ccp wt remove ver-baseline`; `gc` and close leave it alone. It
  refuses (exit 2) `--task`, `--sha`, `--name` and any other kind; with no integration tip, or an
  existing `ver-baseline` at another head, it refuses (exit 3). Without `--baseline`, `--kind ver`
  still needs a task.

**The lead and the runners.** The lead keeps the product's main checkout and pulls it when a merge is
reported. Each runner merges and runs operator steps from its own **runner worktree**
(`<product_root>/.plane-runtime/runner`, made by the single runner's `team.sh runner spawn` or `ccp tasks worktree`
when missing; with several runners that path with `-<slot>` added, made by
`ccp tasks worktree --runner <slot>` when missing), detached at `origin/<integration_branch>` (the
main checkout holds the branch). An existing one that holds no task (detached, with nothing to
commit and no untracked file) is fetched and moved to `origin/<integration_branch>` by the same
spawn or `ccp tasks worktree`; one on a branch or with changes is left as it is, with a warning
naming why; one the spawn cannot make is a
warning, except a missing `origin/<integration_branch>`, which refuses the spawn (exit 3), dry run
or real, naming the ref, and the runner's `ccp tasks worktree` makes it once the cause is fixed. No
runner makes it with `git worktree add`. It fetches and re-detaches before each task. Unless a
product still sets `worktrees.dir` to null (§29.3), `ccp tasks close` makes the reconcile in its `merge-<nnnn>` worktree and pushes it with
`git push origin HEAD:<integration_branch>` (§10.5); run from any checkout, it does not move that
checkout's branch or HEAD, except that a detached runner worktree is moved to the reconcile commit
once it has landed. Each implementer works in its task's `impl` worktree.

### 12.2 Environment hooks

plane.json `env` holds shell command templates or null: `setup` when a worktree is made, `teardown`
when it is removed, `up` and `down` to start and stop what it serves, `urls` to say where it serves.

- A hook runs in the worktree, in its own process group, killed whole after 600 seconds. Its output goes to `QUEUE_ROOT/worktrees/<name>.<hook>.log`, and it returns when its
  shell exits, so `up` must start services in the background and exit.
- The fields `{task_id} {nnnn} {kind} {seat} {tag} {worktree} {main_checkout} {name}` are filled in
  (the path fields `{worktree}`, `{main_checkout}` and `{name}` shell-quoted; any other brace is
  literal) and are also in the environment as `CCP_WT_<FIELD>`, raw (`"$CCP_WT_WORKTREE"`).
- A failed `setup` removes the half-made worktree and `create` exits non-zero. A failed `teardown`
  or `down` is a warning (the worktree is removed regardless). A failed `up` leaves the worktree
  `down` and `ccp wt up` exits non-zero. When a worktree's path is gone, `teardown` and `down` are
  skipped with a warning.
- A worktree made with `ccp wt create … --own-hooks` (recorded `own_hooks: true`) takes its hooks and
  their timeout from its own plane.json, not the caller's, so a hook naming its scripts relative to the
  worktree runs the head's own.

### 12.3 Up, down and URLs

`ccp wt up NAME` runs `env.up` (with no hook it only marks the worktree up), then `env.urls`;
`ccp wt down NAME` runs `env.down`; removing an up worktree runs `down` first. `env.urls` prints a
JSON list of `{name, url}`, as many as the product serves (none, one or many; names unique; a URL
has a scheme). `ccp wt urls NAME` runs it and records the list; `up` records it too (a bad list is a
warning there, an error from `urls`). The verify prompt tells the verifier to bring its worktree up
and use those URLs for checks that need the running product, browser checks included.

### 12.4 Legacy keys

`adapter.worktree_dir`, `adapter.worktree_links` and `adapter.post_close` are merged keys (§29.3): the first two read as `worktrees.dir` and `worktrees.links` (setting both is an error); `adapter.post_close` commands (`{task_id}`, `{nnnn}`, run in the main checkout) still run once at close, before the worktrees are removed, with a warning that they move to `reconcile.hooks`. After the grace release none is read. The binding's `adapter` and
`adapter_config_path` are ignored. A product with no `env` block behaves as before.

## 13. Workers and prompts

### 13.1 Workers

The runner's workers are subagents of fixed agent types (§2): the implementer, the reviewer and the
verifier. The implementer writes the change and, **in the same worker** (resumed by name), opens the
PR with `/mk-pr`; a cold `/mk-pr` is forbidden. The review is a clean separate worker, never the
implementer's session. Every worker runs the PATH `claude`, never `--bare`. Workers never merge,
never edit a task's checks and never create a task: a follow-up a worker finds goes to the lead.
Each worker reports through `ccp report` and a `SendMessage` to its runner (§13.4).

The implementer, reviewer and verifier definitions each state four generic rules, worded for the
worker: a test module the task's change necessarily breaks is in scope even if the task's Scope does
not name it; a test failing under load is rerun alone before it is called a finding; line numbers a
task file cites may be stale, so the code is read at the merge base; a test run cited as evidence, a
mutation check included, goes through `ccp suite run --run <run_id> --lane <lane> -- <command>` or
`ccp mutate --run <run_id> …` (§20.6), never a bare test runner, so it is recorded.

### 13.2 Prompt assembly

`ccp prompt <phase> <id> [--round n] [--note "…" | --note-file PATH]` builds every implementer,
reviewer, fixer and verifier prompt from four parts, in order, writes the prompt audit, opens the run
(§11.1) and prints the prompt path, the report path and the exact Agent call (agent type, no
`model`):

1. **The plane template** `templates/prompts/<phase>.md` (with `templates/prompts/_common.md`): the rules that hold
   in every product, among them working only in one's own worktree, foreground commands only, never
   merging, the review and verify standards (adversarial; reject only on BLOCKER or MAJOR; prove an
   absence pattern on a known positive; mutation-test a test that could pass vacuously, the verifier
   with `ccp mutate --revert` from its own worktree, §20.6), the report contract, every test command
   through `ccp suite run` with the phase's lane (§14), a run cited as evidence, a mutation check
   included, through it or `ccp mutate` with the run's id filled in, never a bare test runner, the refactor DoD for a `kind: refactor` task
   (§20), and for the reviewer and verifier `ccp report` before removing their own checkout.
2. **The product fragment**: `docs/delivery/WORKERS.md` when it exists, or the file plane.json `prompts.fragment` names, holding the product's
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
run apart from the fields it fills in (such as paths, the run id and round, the head, the runner's
note) and the end token, which differs on every run (below).

**The prompt's end.** The rendered prompt's last line is `Prompt end: <token>`, the token a short hash
of the run id and the text above it, kept on the run (`prompt_token`); the report contract tells the
worker to repeat it (§13.4). The Agent call's prompt is a pointer to the rendered file ("Your full
instructions are in <path>. Read that file in full first and follow it exactly."), never its text
retyped.

**Round kinds.** The implementer's rounds are `implement`, `fix` (on review or verify findings; it
needs such a report), `merge` and `ruling`, each with its own template and run name. An `implement` or `fix` round's last step before it pushes the head it reports is a catch-up: it merges the integration tip into the task branch (§15.6 rule 2: never a rebase), resolves any conflict, listing each in its report, and runs its suite (§14) on the merged code. The other two:

- `ccp prompt merge <id> --pr <n> --head <sha>` only merges the integration tip into the task branch
  (§15.6 rule 2), resolving conflicts and adapting the task's code to the tip, nothing else;
- `ccp prompt ruling <id> --pr <n> --head <sha> --note-file <the ruling>` only applies a lead's ruling
  (written into the task's Context section, §10.5), before or after a review; without a note it is
  refused (exit 2), nothing opened.

Each opens a run of that kind, moves the task to `fixing` and reports as a fix round (§13.4). Review
and verify treat a merge or ruling round's head as a fix round's: the review prompt lists its report,
`ccp prompt verify` and `ccp verify record` count it as a fix round newer than the last review (§15.2),
`verify.skip_review` or a review prover may prove it, `verify.skip_review_after_clean` may take it as
the fix of a clean review's minor findings (§15.2), and it counts as a fix round between verify rounds
(§15.6 rule 4).
Rounds since the last review that are all merge rounds need no new review when the head carries the
reviewed change unchanged (the same patch id, §15.2). After a merge round whose merge conflicted, `ccp prompt review <id> --pr <n> --head <sha> --mode resolution` opens a resolution review in place of a full one: a review run with `mode: resolution`, rendered from the review template, whose reviewer reads only the resolution (`git show --remerge-diff` of the head, which shows how the committed merge differs from git's own merge) and reports whether it stays within the conflict hunks and which dod_checks it can affect (§13.4). It is refused (exit 2, nothing opened) when the task has no review that reported `done`, when the latest such review is a resolution review that judged the resolution `beyond` (a full review is due, §15.2), when a round since the latest such review is not a merge round, when the head can be neither read nor fetched from origin, when the head is not a merge commit, or when the head's remerge diff is empty.

### 13.3 Worker environment

When plane.json names `prompts.worker_env` (§8), `ccp prompt` also writes the run's environment
beside the prompt (`<phase>[-n]-env.sh`, plain `export NAME='value'` lines rendered from its
templates, values shell-quoted), and the prompt tells the worker to start each command with
`. <that file> && `: a worker's shell calls share no environment. A value that looks like a secret is
refused.

`ccp prompt env <worktree>` (its path, or its name as `ccp wt` recorded it) prints the lines a
worker of that worktree would get, rendered from its record (its task, kind and seat), with
`run_id` and `phase` from the open run bound to it, else left as `<run_id>` and `<phase>`. It opens no
run, writes no prompt audit or file, and refuses a worktree with no record (exit 2) or a value that
looks like a secret, as `ccp prompt` does.

### 13.4 Reports

A worker submits its report with `ccp report <run_id> FILE`, which checks its shape, stores it at the
run's report path (`progress/<task_id>/<phase>[-<n>].md`), closes the run, and records the suite
metrics and every friction line. A run already reported takes a corrected report, checked like a first
one, until a later run of its task opens (by then the runner may have acted on the report, so the
correction is refused naming that run): the run's report fields become the corrected report's, the earlier stored report is
kept beside it as `<stem>.superseded-<k>.md` and listed in the run's `corrections`, and the friction lines
and suite filing stay the first submission's. Report lines:

- `Outcome: done|blocked|failed` always;
- `PR:` and `Head:` for implement, fix, merge and ruling;
- `Severity: BLOCKER=… MAJOR=… MINOR=… NIT=…` for review (a review with a BLOCKER or MAJOR is
  recorded as `changes`, otherwise `clean`);
- `## Spec beyond intent` for review with `Outcome: done`: a `- ` line for each passage of normative
  text beyond the task's intent, or the single line `none` (§3.5; the run keeps only their count);
- for a review with `mode: resolution` and `Outcome: done`, `Resolution: contained` (the resolution changes nothing of the task's own beyond the conflict hunks) or `Resolution: beyond` followed by why, and `Affected checks:` followed by the ids of the task's dod_checks the resolution can affect, comma-separated, or `none`; a report missing either line, or naming an id that is not a dod_check of the task, is refused (exit 1, nothing written), and the run keeps `resolution` and `affected_checks`;
- `Verdict:` and `Head:` for verify, matching the verdict `ccp verify record` noted;
- `Suite:` when the full suite ran, or `Suite: from <suite_id>`, or none (filled from the run's
  record, §14.4);
- `## Friction` as `- ` (or `* `) lines, or `none`;
- `Prompt: <token>` always, the token on the last line of the run's prompt (§13.2). A report with none,
  or with a token that is not the run's, is refused (exit 2, nothing written, the run left open), naming
  the run's token and saying the prompt the worker read was probably cut; the runner launches the
  worker again with the pointer (`--supersede` when the run never started). A run with no token
  recorded (opened before it) is not held to it;
- for implement, fix, merge and ruling, `## Tests for new behaviour` (§13.5);
- for implement, fix, merge and ruling with `Outcome: done`, each verdict the product declares in plane.json
  `report.required_fields` (a list of `{name, values}`, default none), as `<name>: <value>` with one
  of its declared values. A report missing one, or giving another value, is refused with the field
  and its allowed values. A field is stated once; a field on two lines is refused. A declared value
  followed by `|` (the pasted template `a|b`), or by `/`, `,` or the word `or` and then another of
  the field's declared values (the template respelled: `a / b`, `a, b`, `a or b`, and the longer forms
  such as `a, b or c`) with no words after the last of them or a `|` between them, is read as the
  template and refused; any other text after the value is a reason and is accepted, even one that
  starts with another declared value (`yes, no downtime needed`). The values are kept on the run
  (`fields`); the implement, fix, merge and ruling prompts list the declared fields, and the review
  prompt and `ccp prompt review`'s output show them as the task's latest done implement, fix, merge
  or ruling report states them. Whether a verdict is right is not judged.

`ccp verify record` notes the verdict on the task's open verify run and emits `verify/recorded`; the
verifier's `ccp report` closes the run.

### 13.5 Worker efficiency

None of these changes what is checked; they change what each request carries and how soon a failure
shows.

- **Tool allowlist.** Every delivery agent definition names its tools (`tools`, `disallowedTools`),
  with no `Skill`; `SendMessage` stays reachable through `ToolSearch`.
- **Cache lifetime.** `experimental.cacheTtl: 1h` in every delivery definition covers worker
  subagents; the runner teammate's comes from `subagentPromptCacheTtl` in settings (§2.4). `ccp usage`
  shows the 1-hour cache writes (`W-1H`) per run and seat.
- **Fail fast.** Before the full suite, the implementer and fixer run a pre-gate: the product's `architect.checks` commands (rendered from plane.json), or, when plane.json `suite.lanes` declares a `pregate` lane, that lane through `ccp suite run --lane pregate` in their place, and the run `ccp suite affected` prints on stderr (§14.7), through `ccp suite run`: the part lane, or, when it says the change reaches most of the suite, no pre-gate and the full lane. It never stands in for the full suite, which runs on the final code and must be green.
- **Exploration hygiene.** What the task cites is read in full; a listing, search or log likely past
  about 200 lines goes to a scratch file and is read in slices; independent reads go as parallel tool
  calls in one turn.
- **The self-check.** Before the full suite, the implementer and fixer list each branch, field,
  refusal or behaviour their commits add or change with the test that fails without it, write the
  missing tests, and report the list under `## Tests for new behaviour`; the reviewer checks those
  lists against the diff (a later round, the fix reports' lists against the fix commits) and rates a
  gap as it would a missing test.
- **One statement of each rule.** The worker definitions do not repeat the `ccp suite run` rule
  (they name the command only in §13.1's evidence rule), and
  the verifier's definition defers to its prompt's test-cache rule. The review and verify briefs run
  `ccp report` from their own checkout before removing it (or from anywhere with `--root`).

## 14. Test runs

### 14.1 The rule and the lanes

Implementer, fixer, reviewer and verifier workers run **every** test command (the full suite, the
gate, a subset of modules, every rerun) through
`ccp suite run --run <run_id> --lane <lane> -- <command>`, outermost, around any wrapper the product's rules give, never inside a script. The
plane reads three lane **roles**: `full` (the implementer's and fixer's full suite), `gate` (the
verifier's formal gate, whose script picks its own lanes) and `part` (a subset, such as the
reviewer's modules or a mutation check). Each role's lane is the `suite.lanes` lane of the role's own
name, except that a product declaring a gate lane and no full lane runs the gate lane for the full
role too (in the briefs, and for a run with no `--lane`). The gate
role's lane is required: every task's verify runs it, and so does its catch-up with the tip before
review, so with none `ccp tasks claim` and `ccp tasks next` refuse (exit 2, §8.1); `ccp init --gate`
writes it. The other roles' lanes are optional; the prompts,
the report's auto-fill and the health series use these names. `--lane` is a short label; without `-- <command>` it runs what plane.json `suite.lanes` gives that lane, from the checkout's root: an argv, or stages (§14.2). A run
with no `--lane` is recorded without a lane (filed as part); for an exclusive lane's lock and its
usual duration it counts as the `full` role's lane. `ccp report` warns, never refuses, when a report
has a `Suite:` line but no suite run is recorded for its run.

### 14.2 The command

- It runs the command in the foreground with stdin inherited and exits with its exit code (128 + N
  when signal N ended it).
- **Stages.** A `suite.lanes` entry may be an ordered list of `{name, cmd}` stages instead of an argv:
  a stage name is a lane-like label, unique in the lane; `cmd` is a shell command (`/bin/sh -c`), exit
  0 = pass. `ccp` runs the stages in order from the checkout's root, times each, and stops at the
  first that exits non-zero or that a signal ends: no later stage runs, and the run exits with that
  stage's code. A signal N that arrives between stages stops the run before the next starts: it exits
  128 + N and names that stage as `failed_stage` (§14.3), so it never passes with a stage unrun. Each
  stage gets its own `CCP_SUITE_RESULT`. The gate role's staged lane ends with a
  stage `ccp` adds itself, `plane-docs`, which runs `ccp docs check` (§21.2), so no product stage calls
  `ccp`; no product stage may take that name, and no other lane gets it. An argv lane runs as one stage
  named after the lane, with no `plane-docs` stage; a command after `--` is no stage, and `ccp suite run` refuses one (exit 2, nothing recorded) on a lane plane.json gives stages, naming the lane, so a staged gate cannot be replaced by a command. On the `full` or `gate` role's lane, where plane.json gives an argv that differs from the command after `--`, the command still runs, after one warning on stderr naming the lane, its argv and that this run replaces it, and saying to run the lane with nothing after `--` to use it. With stages, a
  line marks each stage's start and end in the log (on stderr with `--full`), and the summary gets one
  line before its last: each stage that ran, passed or FAILED with its exit code, and its seconds, then
  the stages not run. A nested run (below) of a staged lane runs its stages in order, unrecorded.
- **Provers.** A declared prover that exits 0 on the diff skips the step it names, recorded on the run.
  plane.json `verify.provers` (`[{name, command, skips}]`; empty, the default, is none) declares them:
  `name` a label unique among them, `skips` `review` (§15.2) or a stage the gate role's lane declares
  (never `plane-docs`). `ccp` fetches `origin/<integration branch>` and reads them from plane.json
  there, never from the checkout or the head under test: a prover a task adds or changes in its own diff
  does not apply to that task, and a failed fetch, or an integration plane.json that does not load,
  declares none, so nothing is skipped. Provers run from the integration tip's checkout: a clean,
  detached worktree of the `origin/<integration branch>` commit the rules were read at, made in the
  product's repository (so `{from}` and `{head}` resolve in it) and removed when the run ends, on an
  error, SIGINT, SIGTERM or SIGHUP too. Nothing a task's diff changes, a script the command runs
  included, can alter their verdict. There `HEAD`, the index and the tree are the tip's, so a command
  names the diff it judges only through `{from}` and `{head}`; the checkout's untracked and ignored
  files (installed dependencies, generated files) are absent, so a prover that needs them fails and
  skips nothing. One checkout serves a run's provers, in order: what one writes there, the next sees.
  On a run of that lane that is recorded and names its task, before such a stage starts, `ccp` runs the
  stage's provers in order there (`/bin/sh -c`, output discarded, at most 600 s), with `{task_id}`,
  `{from}` (the head's merge base with `origin/<integration branch>`) and `{head}` (the task head
  under test: the HEAD of the product checkout the run started in, not of the tip's checkout the
  provers run in) filled in; the first that exits 0 skips the stage. A non-zero exit or a timeout
  skips nothing, and a checkout with uncommitted changes, a head with no merge base, or a tip git
  cannot check out runs no prover. A skipped stage is neither in `stages` nor among the stages not
  run: the `ended` row and its event record `proven_skips` (`[{stage, prover, exit_code, run_id}]`,
  `prover` its name in `verify.provers`, `run_id` the suite run's run or null), and the summary's stage
  line names each skipped stage and its prover. No record holds a prover's command text (§14.4): the
  name looks it up in plane.json. The prover is product tooling, not the plane's.
- **Summary mode** is the default when stdin is not a terminal (`--summary` forces it). The
  command's stdout and stderr both go to one log file, in the order written: `--log PATH`, else next
  to the run's record (`QUEUE_ROOT/runs/<task>/<phase>[-n]-suite-<suite_id>.log`), else
  `QUEUE_ROOT/runs/_suite-logs/<suite_id>.log` for an unbound run, else a temp file. `ccp` prints a
  start line naming the log and, when the command ends, a summary:
  - on a failure (a non-zero exit, or a failure counted), the failing tests' sections in full
    (`section_re`; unittest's `FAIL:` and `ERROR:` blocks), then the log's last 40
    lines not inside a shown section. They share a cap of 40,000 characters: the sections first, less a
    reserve for the tail (a quarter of the cap at most); the tail is cut from its front, so the log's
    last lines and its final error always show. A log no longer than 40 lines is shown whole; an
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
- When the options do not parse (an unknown flag, an option missing its value or given a bad one,
  `--full` with `--summary`), nothing runs: `ccp` exits 2, naming the problem, even with a command
  after `--`.
- When the command exits, `ccp` exits within a couple of seconds, even if a background child holds
  its output open. SIGINT and SIGTERM sent to `ccp` reach the command's whole process group; such a
  run is recorded as interrupted. No background or detached mode exists.
- **Waiting on a run.** `ccp suite wait <suite_id> [--timeout SECONDS]` waits in the
  foreground, up to 540 seconds or `--timeout`, on a run already started: one that outlasts the caller's command limit, or that its
  harness moved to the background. When the run's `ended` row is written it prints the summary
  `ccp suite run` prints, rebuilt from the row and the log (the failure ids of a gate's result file and
  the stages not run are not recorded, so not shown), and exits 0 when the run passed and 1 when it
  failed (§10.6), the summary showing the run's own exit code. Still running at the timeout, it prints
  the run's elapsed time and exits 3 (§10.6: not done yet); the caller calls it again. A run that §14.4 counts as `killed` is a failed run, so `ccp suite wait` exits 1 at
  once (§10.6). An id with no record in the queue is refused (exit 2). It writes nothing. The worker
  prompts give `ccp suite run` and `ccp mutate` the Bash tool's full `timeout: 600000` and send a
  worker whose `ccp suite run` went on past its call to `ccp suite wait`, never to a loop reading the
  log; exit 3 means only that the run is still going.
- **Environment:** the caller's, unchanged, plus `CCP_SUITE_ID` and `CCP_SUITE_RESULT` (and
  `CCP_SUITE_COLD` with `--cold`, below). In a worktree
  `ccp wt` made (§12.1), a lane's stages also get its `CCP_WT_<FIELD>` variables, the ones its env
  hooks get (§12.2), and its task as `CCP_TASK_ID` (the full id) and `CCP_NNNN`, both empty in
  `ver-baseline`; a command after `--` and a run elsewhere get none. `bin/ccp` sets no variable.
  A `QUEUE_ROOT` that `ccp` found from the binding stays `ccp`'s own. A `ccp suite run` inside it
  becomes its command, records nothing and writes no log.
- **A cold run.** `ccp suite run --cold` asks for a cold run the same way in every product: what the
  run starts (a lane's stages, or a command after `--`) also gets `CCP_SUITE_COLD=1`, which a
  product's gate reads as its own cold option (§15.3),
  and the `ended` row and its event record `cold` from the run's own count alone (§14.6): asking for a cold run does not make it one.
- The run it belongs to is `--run`, else `--task` (and `--phase`)'s latest open run, else the one
  running worker run whose worktree holds the current directory; otherwise it is recorded unbound.

### 14.3 Counts: the gate-result contract and the output

- **The gate-result contract** (ADR-0014). A command may write a JSON result to `CCP_SUITE_RESULT`
  (`contracts/suite_result.schema.json`): `tests` (tests that ran), `ran` and `cached` (units run
  and served from the product's cache, in the product's unit), `cached_tests` (the tests behind the
  cached units), `skipped`, `failed`, `failures` (`[{id, message?}]`), `seconds`, `modules`
  (`[{name, seconds, tests}]`, each test module the gate ran) and `extra`; at least one of `tests`,
  `ran`, `cached`. When written and valid it is the run's record: the output's
  counts are not used, a counter it leaves out is absent (null), and `failed` defaults to the number
  of `failures`. It is read without following a symlink, at most 1 MB, and removed once read. For a
  lane plane.json names, `ccp` adds `stages` (`[{name, seconds, exit_code}]`, each stage that ran, in
  order) and `failed_stage` (the stage whose non-zero exit stopped the run, the first stage a signal
  kept from starting (§14.2), or null) to the run's
  result (§14.2); with several stages, the counters of every stage's valid result are summed. Only
  counters and `modules` are recorded: `modules` on the `ended` row, every stage's in order, at most
  1,000, an entry that is not a name, seconds and tests dropped (§27.2 reads it). Failure ids are
  shown in the summary and never recorded; `seconds` (the
  record keeps `ccp`'s wall time), `message` and `extra` are ignored. An invalid result gets its own
  summary line and a `result_problem` label, and the output's counts stand. `counts_from` says which
  (`result` or `output`).
- **Without a result file** the counts are read from the output: each line matched against
  `suite.count_re` (default: the language pack's, §21.4; Python's reads unittest's `Ran N tests in`), a pattern or a list of patterns: the first
  pattern a line matches counts it, its first group as the count, or the line as one when the pattern
  has no group, so no line counts twice; the matches summed; `suite.summary`'s
  `failed_re` and `skipped_re` (a pattern or a list, first group a number, summed) give the failures
  and skips. The defaults are the language pack's (Python's read
  unittest's `OK (skipped=N)` and `FAILED (failures=N, errors=N, skipped=N)`); with `language: none`
  there are none, and only the product's own patterns count. No pattern reads the units ran or cached
  from the output unless a product still sets `suite.summary`'s `ran_re`, `cached_re` or
  `cached_tests_re` (§29.3): those (a pattern or a list, first group a number, summed) give the units
  ran and cached and the tests behind the cached units. The older keys `suite.summary.modules_ran_re` and `modules_cached_re` are removed
  keys (§29.3). `section_re` and `show_re` shape the summary.
- **An all-cached run:** with no test count found and the run saying 0 units ran and some cached,
  the test count is 0, not none; `cached_tests` is recorded beside it, and the summary ends
  `; N tests behind the cached results`.

### 14.4 Records and citing them

`QUEUE_ROOT/runs/_suites.jsonl`, append-only: a `started` and an `ended` row per run sharing a
`suite_id`, and a `suite/recorded` event at the end. Numbers, ids and short labels only: the lane,
the output mode (`output`), the command's basename and argument count; the `ended` row adds `tests`,
`failed`, `skipped`, `ran`, `cached`, `cached_tests` (null when not found), `counts_from`, summary
mode's `log` path, `cold` (§14.6) and, for a lane plane.json names, `stages` and `failed_stage` (§14.3), `modules` when the result gave
them (§14.3; on the row only, never the event), and
`proven_skips` when a prover skipped a stage (§14.2: the prover's name, exit code and the run id, never
its command). A staged
lane's `started` row has `cmd` `stages` and its stage count as `argc`. A run from a git checkout with
nothing to commit adds `tree`, the `HEAD^{tree}` it ran (§16.6), and a run that skipped an exclusive
lane's lock adds `lane_skipped` and `green_from`. Never the command's arguments,
never its output; the event carries the numbers, `cold` and the stages, not the path. A row naming `modules_ran` and `modules_cached` reads as `ran` and `cached`.

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
  another phase's, or an earlier verify round's is refused. `cold` is filled as `true` when the cited
  run has `cached == 0` and the entry leaves it out; an explicit `cold` from the verifier wins.
- **Logs are pruned.** A recording `ccp suite run` removes summary-mode logs
  (`runs/<task>/*-suite-st-*.log`, `runs/_suite-logs/st-*.log`) older than 14 days: no other file, no symlink, nothing outside `runs/`, at most 5,000 looked at, a failure
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
not set, there is no git checkout, `plane.json` is unreadable, an option's value is wrong (a bad
`--lane` label or `--phase`) or a write fails. `ccp` prints one `ccp suite:` warning and
records nothing more. It exits 2 only with no command to run, with a command after `--` on a staged lane, or with options that do not parse
(§14.2): then it runs nothing, so no run goes unrecorded.

### 14.6 The gate fits the agent's shell limit

An agent runs the gate in its own foreground shell, which its harness ends at a fixed limit (600 s in
Claude Code). A cold gate run must fit that limit with room to spare.

- **The limit and the line:** the plane takes the harness's limit as 600 seconds, and the cut line
  below it as 90% of the limit.
- **Every run records whether it was cold:** the `ended` row and its event carry `cold`: `true` when
  the run counted nothing cached (`cached` 0), `false` when any unit was cached,
  null when it gave no `cached` count, a `--cold` run included (§14.2).
  A command's own `cold` in its result file is ignored.
- **Judged on cold runs only.** `ccp health` judges the latest cold run of the gate role's lane,
  cold as §27.2 decides (passed, counted tests, and nothing cached or no test cache yet). Warm,
  unverified, failed, interrupted and killed runs, and other lanes' runs, are not judged against
  the line.
- **Over the line** (longer than the cut line), `ccp health` reports the run as an advisory
  finding: the run (its suite id, task and start), its seconds, the line, the limit and its slowest
  stage (§14.2; none for a run with no stage timings). The task-log owner decides whether to file a
  refactor task (§20.3) that brings its cold run under the line. **Over the limit** it is reported
  as a health breach (`over_limit`). Under the line it reports nothing. `ccp health --json` carries
  it as `gate_time` (`finding` null when there is none), and the architect's health summary carries
  the same line.
- **Killed at the limit.** A run of the gate role's lane with no `ended` row whose elapsed time
  reached the limit is reported as killed at the shell limit. `gate_time.killed` carries
  each such run's suite id, task, run and start; the health and architect summaries give one line
  with their count and the latest to start (its suite id, task and start). Its elapsed time runs to
  the earliest of its run's stop, report or abandonment when known (as §14.4's totals reckon it),
  else to now. A run with no `ended` row that stopped before the limit is not reported. Only runs
  started after the latest run of that lane that passed or failed are listed, so such a run clears
  the earlier ones.

### 14.7 The tests a change touches

`ccp suite affected [--since <ref> | --paths <path>…]` prints the test modules a change touches, one
per line, sorted, so a worker picks the `part` lane from them after a merge or a fix instead of
guessing. It runs nothing and records nothing. After the list it prints, on stderr, the command that
runs them on the `part` role's lane (`ccp suite run --lane <part lane> -- <command> <modules>`), for a
language whose command it names (Python: `python3 -m unittest`); stdout keeps the list alone. When the list holds more than a fixed share of the suite's test modules (a constant in code; the pack counts the suite), the stderr line says instead to skip the pre-gate and run the `full` role's lane: the part lane runs its modules one after another, and past that share it is slower than the full lane. A product that maps tests with `suite.affected_map` alone has no suite count and always gets the part-lane line.

- **The change** is `--paths`, normalised relative to the product root (`./` stripped, `..`
  collapsed, an absolute path made relative), else the files `git diff <ref>` names against the
  working tree (a rename as both its paths) plus the untracked files git does not ignore; `--since`
  defaults to `HEAD`, the uncommitted change. A range `<a>..<b>` given to `--since` is the files
  `git diff <a>..<b>` names, without the working tree.
- **The product's language pack reads the tests** (`language`, §8.1). A pack with no test reader (`none`) exits 2 unless plane.json `suite.affected_map` is set, which then reads the tests alone.
- **Python.** A test module is a `test*.py` file git tracks or does not ignore, named by its dotted
  path from the root (`tests/test_a.py` is `tests.test_a`). It is touched when it changed itself;
  when it imports a changed module directly (any `import` or `from … import`, a relative one or one
  inside a function too; importing `p.m` imports `p`, and `from p import m` imports `p.m`) or
  through one package level (it imports a package whose `__init__.py` imports the changed module);
  or when its text names a changed file's name: only a path that has an extension (a dotfile such as
  `.gitignore` has none) and is not a directory matches tests by name.
- **A product's map.** plane.json `suite.affected_map` maps globs to test ids: each changed path is
  matched against every glob (`fnmatch.fnmatchcase` on the root-relative path, so `*` crosses `/`),
  and the ids of each match are added to what the pack reads; the list stays sorted, each id once.
- With nothing changed, or no test touched, it prints nothing, says so on stderr and exits 0. A ref
  git cannot read, or a path outside the root, exits 2.

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

A `dod_check`'s dry run on the merge base (that the check fails without the task's code) is run with
`ccp wt create --kind base --task <id> --sha <PR head> -- <command>` (§12.1): the command brings in
what it needs from the head (`git checkout <PR head> -- <test path>`), and its exit code is the
result.

### 15.2 Review

- **Review starts on a settled head.** The runner opens a review (`ccp prompt review --head`) only
  once the task's open spec questions are answered and their rulings are on the PR.
  `ccp prompt review` refuses (exit 2), naming the task and the PR, a PR whose body does not contain
  the task id; the runner repairs the body first. It refuses (exit 4, nothing opened) a head behind the integration tip (`behind_tip`, §16.5 rule 4) only when merging the tip into it would conflict in a file outside the task log and `merge.behind_tip_ignore`, judged with `git merge-tree`, which writes nothing; the refusal names the conflicted files, and `ccp prompt merge` has the implementer resolve them. A head behind by a clean merge is reviewed, and a later catch-up handles it (§15.6 rule 3, §16.5 rule 4). A tip or head that cannot be fetched to judge is a warning on the run, and the review opens. A commit landing while a review runs makes its head
  stale.
- **A fix round is reviewed again before it is verified**, unless a proof or a clean review covers it
  (the next three rules). A resolution review (§13.2) that reported `done` with `Resolution: contained` is the review of the head it judged; one with `Resolution: beyond` is not, and the head is reviewed again in full.
  `ccp prompt verify` refuses (exit 4,
  nothing opened) when the task's latest fix run, or a merge or ruling round (§13.2), that was not
  abandoned opened no later than its latest review run that reported `done`, or when `--head` is not
  the head that review judged (its run's `head`; a short sha matches). A head that differs from the
  reviewed one only by merging the
  integration branch, its own diff against its merge base unchanged (the same patch id), needs no new
  review; integration changes inside the PR's own hunks or their context lines change the patch id,
  and a head with no change of its own, or one that cannot be fetched, is reviewed again. A task with
  no runs passes. Only on the lead's or the operator's word, 
  `--allow-unreviewed-fix --reason "<their words>"` opens it anyway: the run records `allow_unreviewed_fix` (`reason`, `was`), a friction note
  with source `allow-unreviewed-fix` goes to `health/notes.jsonl`, and a `note`/`set` event to the
  ledger. `ccp verify record` refuses an approve under the same condition (judged at the record's
  `head_sha`) unless the task's open verify run carries that override, a `review_skip` that
  `verify.skip_review` or a review prover proved at that head, or a minor-only `review_skip`
  (`verify.skip_review_after_clean`, below) on a verify run of that head; a reject is never held back.
- **A proven fix within declared paths needs no new review** (ADR-0035 D4). plane.json
  `verify.skip_review` (`{"paths": [<paths>], "proof": "<command>"}`; null, the default, is off) lets
  a fix round opened since the last review that reported `done` go straight to verify when: the fix
  diff, from the reviewed head's change carried onto the head's base on the integration branch (it
  must merge cleanly) to the head, touches at least one file and only files under `paths` (git
  pathspecs relative to the product root, never the root itself); and the product's `proof` command,
  run on that diff (from the integration tip's checkout, below) with `{task_id}`, `{reviewed}` (the
  head the review judged), `{head}` and `{from}` (the tree the fix diff starts from) filled in, exits 0.
  Otherwise the refusal stands and says why the skip does not apply. The verify run records
  `review_skip` (`reviewed`, `head`, `fix`, `files`, a count). `ccp` fetches `origin` and reads
  `verify.skip_review` from plane.json on `origin/<integration branch>`, never from the runner's
  checkout or the head under test: a setting a task adds or changes in its own diff does not apply to
  that task. A failed fetch, or an integration plane.json that does not load, sets none: nothing is
  skipped, and the refusal says so. The `proof` runs from the integration tip's checkout, as a gate
  stage's prover does (§14.2), so nothing the task's diff changes can alter its verdict: its `HEAD`,
  index and tree are the tip's, so it names the fix diff only through `{from}` and `{head}`, and the
  checkout's untracked and ignored files are absent. The prover is product tooling, not the plane's.
- **A declared prover of the review.** A declared prover that exits 0 on the diff skips the step it
  names, recorded on the run: a `verify.provers` entry (§14.2) whose `skips` is `review` judges the fix
  diff `verify.skip_review` judges (at least one file; no paths rule of its own), its `command` run as
  `proof` is, with the same fields filled in, and it is read from the integration branch's plane.json
  as `verify.skip_review` is. `verify.skip_review`, when set, is tried first, then each such prover in
  order, all from one integration tip's checkout (§14.2); the first to prove the fix sends it straight
  to verify. The verify run's `review_skip` then adds `prover` (its name) and `exit_code`,
  never the command text (§14.4).
- **A fix of a clean review's minor findings needs no new review.** plane.json
  `verify.skip_review_after_clean` (boolean; false, the default, is off) lets the fix round after the
  latest review that reported `done` go straight to verify when that review recorded no BLOCKER or MAJOR
  finding and at least one MINOR or NIT, the fix round (a merge or ruling round counts as one, §13.2)
  reported `Outcome: done` with the head being verified, and no verify run opened since that review
  rejected. A fix round that reported `failed` or `blocked` never skips. With more than one fix round
  since that review, the latest is the one judged, so a second fix round may skip as well when it meets
  these conditions. The verify run
  records `review_skip` (`reason: "minor-only"`, `review_run`, `reviewed`: the head it judged, `report`:
  its report's path, `findings`: its MINOR and NIT counts); the plane stores no finding text. The verify
  prompt gives those counts and the report, and asks the verifier to read the report and confirm the fix
  diff, from the reviewed head to the verified one, addresses each MINOR and NIT finding there and changes
  nothing beyond them; a change beyond them is a REJECT, and after a reject the task goes back to review.
  Otherwise the refusal stands and says why the skip does not apply.
- **The signed SPEC text, checked.** `ccp verify spec-text <task_id> [--base REF] [--head REF]` reads each passage
  the task's Scope, or a section of the task whose heading begins `Rule changes`, carries for the operator's sign-off (§3.5: a `PROPOSED:` marker followed by `> `
  blockquote lines)
  and looks for it, whitespace-normalised, in each hunk the branch's diff makes to files under `spec_paths`, read with the unchanged lines around it up to the nearest blank line on each side, where it covers at least one line the hunk adds
  (`git diff <base>...<head>`, each SPEC file read as it is at `<head>`, which defaults to `HEAD`; the base defaults to `origin/<integration branch>`,
  and nothing is fetched). A passage not found there is looked for in the same way in the hunks the diff makes
  to the one file its own block names, in its `(<path> at <commit>)` locator or opening the line just above it,
  such as a contract whose text the operator signed; a path inside quoted text names nothing, and a file under
  `tests/` or the task log's directory is never searched. The result names the file each passage was found in.
  It exits 0 when every passage is found, 1 naming each that is not, and 2 when the task carries no
  `PROPOSED:` block, names no task, or gives a `--head` that names no commit or a base the diff cannot be read
  against. For a task with `sign_off: brief`, the reviewer and the
  verifier run it and report its result.

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
  for a cold run; a cited suite run with `cached == 0` gives it (§14.4), and an explicit value still
  wins. `ccp verify record` refuses an approve with no gate run giving both counts, and on a
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
is `ran: false`, `pass: null`, and `rests_on` names what it rests on, in one of the three forms below:
neither a pass nor a fail. Under `adr.strict`, `ccp verify record` also refuses an approve of a head
on which a decision the task's `adr_refs` cite is still recorded `not_built` (§6.7's in-force check,
judged on the head's files as if the task were done, as close makes it), naming the decision and the
`ccp adr decide` command that flips it; when the task cites a decision, a head the checkout does not
hold is refused. A product with `ci: github-actions` in its binding may cite a green CI run at the
same head (`gate.ci_run`) beside its own runs, never in place of them; `ccp verify record` refuses a
`gate.ci_run` otherwise.

A record carries the schema version of the `ccp` that wrote it (`schema_version`, an integer):
`ccp verify record` stamps its own, whatever the input said, and holds the record to its own
contract. A change that adds a key to the record's contract, at any depth, raises that version. A
reader older than the record (`ccp verify merge-ok`, `ccp verify check` and `ccp tasks close` from
the run checkout before the release, §29.3) passes over keys its contract does not name and still
refuses a key it names that holds a bad value. A record with no version, or one no newer than the
reader, is refused for an extra key. So a task that adds a field to the record is verified with
the PR head's `ccp` and merged and closed with the one on PATH. The verify prompt and the verifier's
definition say so: when the task's own diff changes the record's contract
(`contracts/verification.schema.json`, or the record's version), the verifier records with the head's
own `ccp`, `ccp wt exec <its worktree> -- verify record <file>` (§12.1). `ccp verify record`'s refusal of
a key its contract does not know adds a line saying the same.

Each check names the seat that produced its evidence (`produced_by`: `verifier`, `implementer`,
`reviewer`, `architect`, `operator`, `runner` or `lead`), whether the verifier ran it or not. A ruling
is not evidence: a check the owner's ruling closed is `ran: false` with `rests_on` naming the ruling
(ADR-0035 D7), and its `produced_by` names the seat that produced the evidence the ruling weighed,
never `lead`; with no evidence under the waiver it names none. `ccp verify record` accepts the
`rests_on` of a `ran: false` check in exactly three forms and refuses any other, naming the check: a
ruling, naming spec question ids, gate ids or lead ruling ids (`<task_id>-r<n>`, §17.5) that all exist
(a gate's file is the gate it is cited
as: its `escalation_id` and `task_id` are those of the cited gate id, §17.9; a spec question has its
question file as well as its answer file, §17.5), every gate closed and approved and every spec
question answered with verdict `resolved`; a carried verdict, `approve at <sha>` (§15.6 rule 3),
where `<sha>` resolves to a commit; or evidence the operator produced, `produced_by: operator` with
free text. It refuses a check that names no
`produced_by` unless it is `ran: false` with `rests_on`, and one whose evidence a seat that rules
on the task produced (`lead`, `runner`, §2.3) unless its `operator_step` names an approved operator
step: the task's gate `<task_id>-<n>` (§17.9) of class `operator`, closed and approved (a standing
approval is such a gate). It names the check and the seat; an `operator_step` that is not such a gate
is refused whoever produced the evidence. `ccp verify merge-ok` and `ccp verify check` read a
record written before the field and refuse a ruling seat's evidence on the same terms.

A check the verifier ran whose expectation cannot hold as written is recorded `as_written: false`,
with `held_instead`, what it checked in its place,
and `ruling`, the spec question, gate or lead ruling ids that let it, in the ruling form above.
It is still a pass or a fail. `ccp verify record` refuses one
without both, or on a check not run, naming the check. `ccp tasks close` lists each one (its id,
`held_instead` and `ruling`) before it merges, and does not refuse on it.

A check recorded `ran: false` that does not rest on a carried verdict may be run after its task
closed: the lead or the runner records the result with `ccp verify later <task_id> --check <id>
--pass|--fail --evidence "<one line>" --produced-by <seat> [--operator-step <gate>]`, appended to
`verification/<task_id>.later.jsonl`, never to the verdict record. It refuses a task not done, a
check not recorded so, evidence that is empty, over 500 characters, on more than one line or looks
like a secret, and a producer the verdict record would refuse (a ruling seat without an approved
operator step). `ccp verify deferred` lists each such check of a done task as open, passed or
failed. A failed result reopens nothing.

### 15.5 Merge

The runner merges a PR only when `ccp verify merge-ok <pr> --task <task_id>` exits 0, and then pinned
to that head: plane.json `merge.command`, a template naming `{pr}`, `{head_sha}` (required) and
`{task_id}`; null means the PR host's merge, pinned to the PR's full head `merge-ok` prints
(`match_head_commit`). Close confirms the merge through the PR host (the merge commit is the one the
host names; a merge the host accepts without merging, such as a merge queue, stops it). The plane
reaches the PR host only through one interface (open, view, diff, edit, merge, confirm; ADR-0040),
which workers and the runner use as `ccp pr open|view|diff|edit|merge`, each given the PR number
except open, never a forge's CLI. `merge-ok`
reads the PR through the host and refuses unless the PR is open, its head is the
record's `head_sha` or a head recorded as its catch-up (§16.5 rule 4), the record passes `ccp
verify`'s rules and is `approve` with no failed check, it carries the verifier's `gate` with every
run at exit 0, its `task_id` names the record it is in, and it was written no earlier than its
`checked_at`. A refusal for a PR already merged says whether the
approval was recorded before or after the merge. `merge-ok` lists `unrun_checks`, `gate_runs` and
`match_head_commit`. A PR that is not a task's (a reconcile, a SPEC or ADR PR, a docs-only PR) is
approved in `verification/pr-<n>.json`, whose verdict's `task_id` is exactly `pr-<n>`. `ccp verify
check <task_id> --head <sha>` serves a merge step that does not read the PR host.

### 15.6 Merge and verify rules

They hold for every PR the runner merges, a task's or not (ADR-0011).

1. **Merge only on an approval at the head** (§15.5). A verdict at another head, one written after
   the merge, or one relayed in a message is not an approval; a push after the verdict needs a new
   verdict.
2. **Merge only from the integration tip.** `ccp prompt verify` refuses a head that lacks code merged
   since (`behind_tip`; commits that touch only the task log or the product's
   `merge.behind_tip_ignore` paths do not count, §16.5 rule 4) before a verifier starts, with one
   runner or several, so the runner merges the tip into the head before asking for a verify. Under
   several runners `ccp tasks close` also refuses such a verified head unless it catches it up (§16.5
   rule 4); with one runner `close` does not run this check. The task branch takes the integration
   branch by a merge, never a rebase (a rebase needs a force-push).
3. **Re-verify after an integration merge.** When the head moved only by merging the integration
   branch and the PR's own change is unchanged (same patch id), no new review is needed (§15.2). The
   verdict must still be at the new head: the runner opens `ccp prompt verify --head <new> --note
   "head moved by an integration merge; prior approve at <old>"`; the verifier runs the gate at the
   new head through `ccp suite run` (bound to this run), records each `dod_check` it does not rerun
   as `ran: false`, `pass: null`, `rests_on: "approve at <old>"`, and puts in `findings` the command
   showing the PR's own files are unchanged (for example `git diff <old> <new> -- <the PR's files>`
   printing nothing). A merge whose own change moved is reviewed and verified in full, except that a merge with a conflict must have a resolution review, or a full round (§13.2): after a resolution review, the verifier reruns the checks that review names in `Affected checks` and runs the gate at the new head through `ccp suite run`, and records every other check `ran: false`, `pass: null`, `rests_on: "approve at <old>"`, `<old>` the head of the task's latest approve (with no approve yet, it runs every check); `ccp verify record` refuses an approve that leaves an affected check not run. A resolution the reviewer judges `beyond` the conflict hunks is reviewed and verified
   in full. A new head needs a new verdict, except a catch-up close made itself (§16.5 rule 4).
4. **Minors before merge; reasons and the rest in the verifier's record.** A minor finding that
   could cost a later cycle is fixed before the merge. A second verify round with no fix round,
   or a merge or ruling round (§13.2), between says why in its `findings` (from the runner's
   `--note`); minor findings not fixed before the merge are listed there too. `ccp tasks close`
   writes the Verification notes line from that
   record; nobody edits a task's notes by hand.
5. **One seat runs an approved spend step** (a live step that spends allowance or money): the one
   the approval (gate or standing approval, §17.9)
   names; another seat that sees it pending asks that seat.
6. **Who writes the task file** is the §5 table: Implementation notes by the runner from the
   implementer's output, Verification notes by the verifier's record through `ccp tasks close`,
   `dropped` by the task-log owner (the lead); on a claimed task, the Context section by the implementer,
   writing a ruling the runner passes (§10.5).
7. **Code from outside the runner** reaches the integration branch through the task log: a task
   file, then implement, review, verify and gate; a change that merged first gets an after-the-fact
   task, and `ccp tasks orphans` lists the commits no task covers (§10.7). The lead's own commits to
   the integration branch keep `ccp docs check` green; a house rule whose check command does not
   exist yet goes in as `check: pass` until the task that builds it lands.

### 15.7 Optional CI and store tests

A product may copy `templates/github/workflows/formal-unit-lint.yml` to
`.github/workflows/formal-unit-lint.yml`. It runs `scripts/gate.sh`, `scripts/unit.sh` or `python3 -m unittest discover`, then `scripts/lint.sh`, calls no agent and reads no secrets; its result is
evidence only (§15.4). Store tests must not silently skip: in the verifier's run a skipped store test
counts in `tests_skipped` and is not a pass. The template's defaults are neutral: it ships no
database service, `STORE_TEST_PATTERN` is empty and `EXPECT_STORE_TESTS` is `0`. A product with store
tests adds its service, names the tests expected in `STORE_TEST_PATTERN` and sets
`EXPECT_STORE_TESTS=1`; then a skipped test matching the pattern fails the job, and so does a run in
which no matching test ran. A service password is an image default for an ephemeral database, never
a product credential.

### 15.8 Queue rules beside the gate

- **Steps only the operator's machine can run.** A step needing the live store or the operator's
  machine (a live upgrade, creating a database role) that the workers cannot take is parked with
  `waiting_on=operator_step` (`set-waiting-on.sh set <task_id> operator_step --detail "<step>"`).
  The task may merge code-only, the step listed as a follow-up. A parked step, and any check needing
  that machine, runs in a worktree of its own at the PR head (`ccp wt create --kind mac`), never in
  the main checkout.
- **The seat that rules does not produce its evidence.** The lead or the runner runs a task's check
  only as an approved operator step; the verify record names each check's producer
  and `ccp verify` refuses a ruling seat's evidence otherwise (§2.3, §15.4).
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
a head that contains the current integration tip (the task log and the paths in
`merge.behind_tip_ignore` aside, §16.5 rule 4), verified there or caught up by close (§16.5 rule 4),
and git resolves the rest with no merge lock. Two merges that conflict: the later fails, and its
implementer resolves it. A merge landing between another task's catch-up and its merge is a small
window, accepted. Under `parallel.schedule: clashes`, the default, the writer's `clashes_with` decides what to start together, and paths still decide which tasks `parallel.exclusive` keeps apart (§16.3 rule 4); under `paths`, declared paths decide. Parallel work is on by default; `max_in_flight: 1` is the single-runner behaviour, exactly.

### 16.2 The knob

```json
"parallel": { "max_in_flight": 2, "exclusive": ["db/schema.sql"], "shared": [] },
"suite": { "exclusive_lanes": ["gate", "full"] },
"merge": { "behind_tip_ignore": ["docs/notes"] }
```

With no `parallel` block, several tasks run at once, scheduled by clashes (the defaults are in code and the schema); `max_in_flight: 1` runs one task at a time. `max_in_flight` is 1 to 4;
`exclusive` lists paths and globs (`**` spans directories) whose concurrent edits git cannot merge
safely (a schema or migration file). The session ceiling is 60%. `shared` (empty by
default) lists paths and globs that tasks only append lines to, such as a package doc's file map; two
tasks may hold one at once (rule 3), and close merges them as §16.5 rule 4 says. A path may not be
both `shared` and `exclusive`. `schedule` picks claim rule 3 (§16.3): `clashes`, the default, keeps apart only tasks that clash (`clashes_with`, §5), whatever their paths, and `shared` then matters only at close (§16.5 rule 4); `paths` keeps apart tasks whose paths meet. Any other value is refused. `merge.behind_tip_ignore`
(empty by default) lists the paths whose commits on the tip do not make a head behind it (§16.5 rule
4); it applies with one runner too. Config loading validates these blocks; unknown keys are handled as §8 says.
Lowering `parallel.max_in_flight` is completed by `stop --slot` for the extra slots.

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
3. Under `parallel.schedule: paths`, no path of C meets a path of a task in A (equal, one a directory holding the other, or a glob or
   bare name of one matching the other), unless both are covered by a `parallel.shared` entry. Under `clashes`, C clashes with no task in A: neither names the other in `clashes_with` (§5), whether or not their paths meet.
4. No task in A meets an `exclusive` entry that C also meets: a path of each meeting the same entry
   (a task that says `parallel: true` meets none). A task meeting an exclusive entry runs beside
   tasks that do not.
5. The account's session-window usage, in the reading in force (the latest good reading no older
   than 15 minutes, §25.1), is below the session ceiling (the gating session window, §25). A
   reading whose weekly figure is known but has no session figure means the account has no
   session limit: the rule passes. With no reading in force, a second claim refuses; a failed read
   is never judged. `ccp tasks next` judges this rule on the reading in force and, with none,
   leaves it to the claim, which reads. A machine without `allowance_cmd` reads no usage: the rule
   passes (§25.1).

A claim into an empty active set is judged as single-runner; a resume is never refused by these
rules. A claim by a runner that already holds a task not closed or released refuses (exit 7).

**`ccp tasks next`** ranks as before (§10.3), then walks the ready tasks not in A in that order and returns the first that could be claimed beside A and that rules 3 and 4 would not keep from joining any task it passed over; it passes over, naming each, a task that rules 3 and 4 alone keep from joining A and a task that they would keep from joining one it passed over; a task that any other rule keeps from joining A ends the walk with none (head of line: no task waits forever behind smaller ones, and a task passed over waits only for the in-flight tasks rules 3 and 4 keep it from: those its paths meet, or under `clashes` those it clashes with, and those meeting an exclusive entry it meets).
Returning none because of A (full, head of line, the ceiling), it
exits 7 with `slots_full: true` and the in-flight tasks to resume; exit 3 still means nothing is
ready. `ccp tasks check` warns when a task not yet done has neither a path nor `parallel: true` while
`max_in_flight` is above 1: it will only ever run alone.

### 16.4 Queue state

- **Runners.** `work.json` `runners` maps each runner's **slot** (`runner-1` … `runner-N`; one
  runner: `runner`) to `bound_name`, `spawned_at`, `tasks_done`, `bind_pending`, `rotated_at`
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
- `in_flight` is every runner's tasks; each task's phase lives in `tasks/<id>.json`. `task_id` and
  `phase` in `work.json` mean "the task a runner acted on last"; no decision rests on them alone. Each
  runner slot keeps its own lease.
- Every read-modify-write of `work.json` takes its lock (`file_lock`) and computes what it writes
  from the file as read under the lock (`save_work(edit=…)`): claim, release, close,
  `set-waiting-on.sh`'s writer and `team.py`'s. A wait, gate or question on one task never repoints
  `work.json` `task_id` (`set-waiting-on.sh` acts as with `--task-only`).

### 16.5 How the runners work

**The lead:** `team.sh runner spawn --count N` (N at most `max_in_flight`; default 1) records N slots
and prints one spawn per slot, each naming its slot; with slots recorded it adds slots up to N and
respawns none that are live. Claim rule 1 is the real bound: a runner beyond `max_in_flight` finds no
task and idles. With one runner, a spawn while the runner is still live (`work.json` `status`
`running` or `draining`, not rotated since its spawn) stops it first: it emits `runner`/`stop`
(reason `respawn`) and prints a `shutdown_teammate` action for its bound name ahead of the spawn, so
one runner is left. `bind --as <slot>`, `rotate --slot`, `stop --slot [--drain]` act on one
runner; `stop [--drain]` with no slot on all. Gate decisions, question answers, a lead's `release` and the session wake (`--fire`, per parked task) name the bound name of the
task's holder.

`team.sh runner spawn --dry-run` (with any of the spawn's other flags) runs the spawn's refusals and
prints what the spawn would print, its `actions` included, with `dry_run: true`, and the readiness
checks of §10.2 that a machine can answer: every scope entry names a task in the task log, `ccp tasks
check` is clean, and the one runner's worktree (§12.1) is a working tree or can be made: its path
is absent or an empty directory. A runner worktree that is not a working tree yet needs
`origin/<integration_branch>`: when that ref does not resolve, the dry run is refused before the
checks, as the spawn is (exit 3, §12.1). It exits 0 with `ready: true` when every check passes, and 1
with `ready: false` when any fails, naming the failing checks in `failed` and on stderr; a refusal
exits as the spawn would. It writes nothing: no `work.json`, prompt audit, event or worktree.
`--dry-run` with another `runner` op is refused (exit 2).

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
   the task log and the declared paths (`git log <head>..origin/<integration> -- . ':!<tasks dir>'
   ':!<INDEX.yaml>' ':!<reconcile.log path>' ':!<each declared path>'` is not empty). The declared
   paths are plane.json `merge.behind_tip_ignore`, paths relative to the product root (a directory
   covers everything under it), empty by default: a merge that only adds commits under them keeps the
   verified head valid. Another task's reconcile alone does not hold a task back. A re-run after a
   failed reconcile (the PR already merged) skips the check. `ccp prompt verify` runs the same check
   on `--head`, with one runner too, and refuses (exit 4, nothing opened) a head that lacks the tip
   beyond those paths: merge the tip in first. A tip or head it cannot fetch is a warning there; with
   several runners close still checks.
   When the merge with the tip is clean, or its only conflicts are in `parallel.shared` paths where both
   sides only added lines (resolved as the tip's lines, then the task's), the tip's new commits change no
   file the task's own diff or declared paths change other than a `parallel.shared` path (under `parallel.schedule: paths`), or, under `parallel.schedule: clashes`, the default, the task's own patch is unchanged by the merge, whatever files the tip changed and whether or not the task declares paths (the same `git patch-id --stable` of its diff from its merge base with the tip, before the merge and after it, `parallel.shared` paths left out of both),
   and any build sign-off due on the task (§3.5) is recorded for the verified head, with, under `paths`, the tip's new commits changing no file the task's own diff changes, a `parallel.shared` path included, or, under `clashes`, the task's whole own patch, `parallel.shared` paths included, unchanged by the merge, close merges the tip into the verified head itself,
   runs the gate lane on the result as a recorded run in its `merge-<nnnn>` worktree, whose stages
   get that worktree's `CCP_WT_<FIELD>` variables (kind `merge`) and `prompts.worker_env` rendered for it,
   re-checks the tip (at most 3 catch-ups), and on a green gate merges that commit,
   recording the catch-up in the verification record, with `sign_off_carried`, the head the build sign-off covers, when it carried one.
   Review and verify are not repeated: the task's own diff is
   unchanged. A break outside the gate lane's coverage is not caught here; the gate lane is what the
   integration branch is held to. Otherwise it refuses as above, naming the condition that failed.
   The task's implementer merges `origin/<integration>` into the task branch (a plain push; PRs
   squash-merge) and resolves any conflict; the task is verified again on the new head (§15.6
   rule 3). A merge the hosting service refuses for a conflict is the same case.
5. **The reconcile retries on a moved tip.** When the push after a reconcile is rejected, or its
   rebase conflicts, `close` aborts the rebase, fetches, detaches at the fresh `origin/<integration>`
   and rebuilds: a task file already `done` there leaves nothing to do; otherwise it redoes the task
   file, the log entry, the reconcile hooks and the index, commits and pushes, up to 5 times. The
   legacy `post_close` runs once, after the push that lands.
6. **The session park parks every task in flight** (§25, exit 6), whoever holds it; the lead's wake
   resumes every runner.
7. **A freed slot wakes the idle.** After `ccp tasks close` or `release`, which name the runners
   holding no task (`idle_runners`), the runner sends each one message: "a slot is free: `ccp tasks
   next`". Close, release and drop also name `vacant_slots`, the slots rotated and not respawned, which
   `idle_runners` leaves out, and the runner tells the lead each slot and its `team.sh runner spawn
   --slot <slot>`.

### 16.6 Exclusive test lanes

plane.json `suite.exclusive_lanes` names the `ccp suite run` lanes that run one at a time in a queue
(a run with no `--lane` counts as `full`). A run of an exclusive lane takes
`QUEUE_ROOT/locks/suite-exclusive.lock` first. Held, `ccp suite run` exits 75 at once, saying who
holds it, since when, and the holder's usual duration; the worker does other work and retries.
`--wait SECONDS` waits up to that bound instead (the wait plus the run stay under the worker shell's
600 s limit), recorded as `wait_s` apart from the run's time. `--wait auto` takes the bound from that
limit (§14.6) less the lane's usual cold run (the median of its last ten passing cold runs, else of
its last ten passing runs) and a 30 s margin, never below 0; with no passing run of the lane recorded
it waits 0 s and says so. A lock whose holder process is gone is
taken over with a warning. A run whose clean checkout (nothing to commit, untracked files included)
has the tree of a passing run of the same lane and command already recorded in the queue does not
take the lock: it runs at once, recorded `lane_skipped: "green_tree"` with `green_from` naming that run,
since the product's test cache answers most of it; a run bound to a task whose gate is cold (§15.3)
takes the lock as any other. The verifier still runs its gate (§15.3). Busy exits are recorded on the run (`lane_busy`). A run that has started
and outlasts its caller's command limit is waited on by its suite id with `ccp suite wait` (§14.2).

### 16.7 Records, forecast, usage and the board

- **Actuals:** each closed task records `peak_in_flight` (the most tasks in flight during its window)
  and `undeclared_paths` (files its PR changed that its declared paths did not name). Calibration may
  split by `peak_in_flight` once enough tasks exist; until then it is recorded, not used.
- **Forecast** (§26): `max_in_flight` slots; a task starts at the earliest free slot after its
  dependencies and after every task ahead of it that claim rule 3 keeps it from running beside (§16.3, by `parallel.schedule`: paths that meet, or a clash); one without paths and without `parallel: true`, or saying `parallel: false`, takes
  every slot, and one touching an exclusive entry starts after each task ahead of it that touches
  the same entry (rule 4); gaps between tasks are drawn only from closes with `peak_in_flight` 1. One slot is the
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
team lead (ADR-0005), through the question channel (§17.3). Whatever needs the operator is raised in the lead's session (§17.10), and on a trigger of §3.6 reaches the product's notify channel too. None of
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
binding is needed for the lead to be the maintainer; a binding's `spec_maintainer` block is a removed key
(§8.3) and is not read. The lead's protocol is the
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
  durable task files; on a claimed task, only through the runner (§10.5).
- **Chooses the route itself:** rule and commit, or escalate with `needs_operator`; no second reviewer.
- **Every `resolved` ruling lands in git**, `commit_sha` required. A ruling that needs no SPEC or
  PROJECT wording is recorded in the context section of each blocked task file; for a claimed task
  it goes to the runner and lands in the task's PR, never on the integration branch (§10.5), and
  `commit_sha` names the task-branch commit that carries it or, if the ruling is given before that
  commit exists, the integration tip it was ruled against.
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

A ruling the lead gives a runner by message, outside a spec question, is recorded with `ccp tasks ruling <task_id> --words "…" [--check <dod_check_id>]`: a `ruling` `recorded` event in the ledger (§23.2) with the check and the words, its id `<task_id>-r<n>`, `n` counting from 1 per task. A verdict may cite that id wherever it cites a ruling (§15.4); the runner passes it on with the ruling.

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

Whatever needs the operator is raised in the lead's session: the runner's question or gate reaches
the lead through the mailbox, and the lead asks the operator or decides it (§17.9). On the triggers
of §3.6 (`blocker`, `decision`, `review_point_done`, `allowance_checkpoint`) the plane renders and
records the notice, and of the seats only the lead sends it, over a configured channel: `ccp` runs
the product's notify command, if it names one; with a `notify.lead` tool the lead sends each pending
notice from its own session and records it (`ccp notify sent`), and it may also send on its own
judgment (trigger `other`). With neither, the lead's session is the route. The runner and the workers
never send. The
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

- It acts only on a bound runner (`work.json` `runners` bound names, else `runner`), only while `work.json` says `status: running`. It fires inside a runner's subagents
  too, with the runner's `teammate_name`; it acts only when there is no `agent_id`, or `agent_type` is
  the runner's (`delivery-runner`).
- Every input's non-secret fields (a whitelist: event, teammate and team name, agent id and type,
  session id, cwd, permission mode, and the list of keys) are appended to
  `observability/runner-idle-inputs.jsonl` (trimmed past 256 KiB); its block counter per slot is in
  `observability/runner-idle.json`. With no `work.json` it exits before logging.
- It exits 2 ("scope not finished: <task_id> is ready") when the task the runner holds is ready (not
  waiting on anyone), or, when it holds none, when a task in scope is ready (a legacy `in_progress` file status, whatever its dependencies; or
  `pending`, or a legacy `blocked` read as pending, with its dependencies done) and not held by
  its runtime `waiting_on`, an open question's `blocks`, or an undecided gate. `work.json`'s own
  `waiting_on` is not a scope-wide stop.
- With the architect seat adopted (§19.11), it also exits 2 when nothing is ready but the runner
  (its slot, with several) holds in-flight tasks that all wait, none on `quota`, and `ccp tasks
  next` answers that a pass is due (§19.6): the runner starts the pass with `ccp architect run
  --detach` meanwhile. A held task waiting on `quota`, or a triage overdue, lets it idle.
- It lets the runner go idle when its slot's rotation is due, after 3
  consecutive blocks on the same ready set (the value `ccp where` reports as `idle_limit`), and while a task is parked on a session window
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
  window parks at 95%), `ccp tasks claim` and `ccp prompt` park
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
