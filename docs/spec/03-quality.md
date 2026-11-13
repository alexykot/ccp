# Part III — Quality

How the plane keeps a product's structure, its documents and its delivery process healthy: the
architect seat, the house rules and refactor tasks, the checks `ccp` runs on documents, and the
review points the operator reviews progress by. The reasons behind these rules are in ADR-0015
(review points), ADR-0016 (the architect seat, house rules and budgets) and ADR-0017 (doc checks).
Call syntax is in [`docs/cli/03-quality.md`](../cli/03-quality.md); implementation notes are in
`docs/design/` (`architect.md`, `doc-checks.md`, `plan.md`, `review-points.md`).

## 19. The architect seat

### 19.1 Purpose

Each task's reviewer and verifier judge that task; nobody owns the whole. One seat, the
**architect**, owns the structural health of a product: its code, tests and docs, and the delivery
process itself. It has four parts:

- **house rules** the product owns and the seat maintains (§20.1);
- **passes `ccp` triggers mechanically** (§19.6), never by a seat remembering to;
- **a lane, with reserved capacity, for refactor tasks** (§20.3);
- **measurements** that show when delivery degrades (`ccp health`, §27).

The seat looks for **incidental** work: work a change needed only because of how the product is
built (copies to keep in sync, tests that pin text, compatibility paths, gates that check unrelated
code). It is not a size target. It never asks an implementer to do less than a task needs, no seat
is measured on the size of a change, and reviewers still reject a corner cut. Its numbers are
diagnostics, never targets.

### 19.2 Principles

- **The pass is isolated and read-only:** a fresh headless `claude -p` session, never resumed (no `--resume`), with
  its limits enforced by tool allowlists rather than instructions (§19.7).
- **`ccp` computes when a pass is due and enforces it at `ccp tasks next`** (§19.6), so any runner
  meets the trigger on its next task.
- **The architect proposes, the task-log owner triages, the operator decides policy.** The
  architect has no product context; the owner does. A rule the owner or the operator set is not the
  architect's to waive.
- **Every finding carries checkable evidence** the triager can re-run.
- **A durable record lives in product git** (`docs/delivery/reviews/<id>.md`), so each pass builds
  on the last and the operator has one place to see what was found and decided.
- **The measurements come from data the plane already holds:** the queue's progress files, prompt
  audits and git.

### 19.3 Pieces

| Piece | Where |
| --- | --- |
| Skill | The plugin's `architect` skill. It carries the structure and docs lenses that replaced the `architecture-review` and `docs-audit` skills |
| Triage protocol | The plugin's `review-triage` skill (a product may still carry `docs/delivery/REVIEW-TRIAGE.md`) |
| House rules | Product-owned, at `plane.json` `architect.rules_doc`; template `templates/docs-project/ENGINEERING.md` (§20.1), optional starter set `templates/docs-project/starter-rules.md` (§20.5) |
| Driver | `ccp architect due \| run [--mode pass\|shape] [--lens L,…] [--adr ID] [--force] \| triage <id> \| status` |
| Measurements | `ccp health [--since DATE] [--json]`, `ccp health note`, `ccp health record` (§27) |
| Contracts | `contracts/architect_report.schema.json`: the report with `mode`, `lenses`, `rule_changes` and `metrics`; the triage contract `contracts/architecture_review_triage.schema.json` with §19.8's dispositions |
| Binding | The `architect` block of the product-owned `docs/delivery/plane.json` (§19.11), so worktrees and verifier checkouts see it |
| Runtime | `QUEUE_ROOT/architect.json` (state), `architect.lock`, `reviews/ar-*.json` and `.md`, `health/notes.jsonl`, `health/metrics.jsonl` |
| Durable record | `docs/delivery/reviews/<id>.md` in the product, written by the triager |

### 19.4 Lenses and categories

| Lens | What it looks for | Categories |
| --- | --- | --- |
| `structure` | Commands, tables and config keys a later decision replaced; two sources of truth for one concept; a first-class feature for what should be one instance of a general mechanism; placeholder surface that only says "not built"; rules that cost more than their purpose | `holdover`, `not-first-class`, `duplication`, `vocabulary-drift`, `dead-surface`, `incoherence`, `unobserved`, `cost`, `rule-cost` |
| `docs` | Whether each doc's statements are true of the code beside it; current docs carrying history (a ruling trail in the spec, operator records in a runbook, task-named sections); facts restated from code that must then be kept in sync | `doc-wrong`, `doc-missing`, `doc-aspirational`, `doc-padding`, `doc-history` |
| `tests` | Fixtures that rebuild expensive state per test; tests of paused code on the per-task gate; tests that pin prose or restated facts rather than behaviour; tests that fail under load | `test-cost`, `test-brittle` |
| `process` | From `ccp health`, the prompt audits and the standing DoD: per-task time and where it goes; full runs repeated across seats; mandates in prompts or the DoD that no longer earn their cost; the reading list a fresh implementer is given; carried-over rules that belong in a doc | `process-cost` |

A docs finding's fix is `rewrite`, `cut` or `add`, with a code quote and a doc quote as evidence.

**`rule-cost`:** a rule of the product (from the spec, an ADR, the house rules or the standing DoD),
applied as written, forces work or keeps something alive that the rule's purpose does not need.
Its evidence is the rule's text, what it keeps alive (paths and counts) and what it costs each
task. It always carries `needs_decision: true` and fix `decide`, goes to the operator in triage, and
is never rejected as intentional without the operator's word.

### 19.5 Modes

- **`pass`** is the periodic review. It covers every lens, or the lenses its trigger names, and
  reports at most 25 findings plus `rule_changes`: proposed additions, amendments and deletions to
  the house rules, each naming the rule id, the action and the check that would enforce it.
- **`shape`** runs before an accepted ADR is tasked. It reads the ADR and the code the ADR will
  touch and returns, in at most 10 findings plus a `shape` object (`hot_spots`,
  `preparatory_refactors`, `single_sources`, `task_graph`):
  - the hot spots;
  - **preparatory refactors** that shrink the change without cutting its scope;
  - the facts the change would update in several places, and the single source to create first;
  - a task graph that lets tasks run in parallel where the code allows.

  Its advice is advisory: the owner decides. A shape report is always triaged, never resets the
  cadence, and counts toward the triage block like a pass. Ids are `sh-…`.
- **The shaping record is the architect's own output:** `ccp architect run --mode shape`, whose
  triage writes `docs/delivery/reviews/sh-*.md`. The task-log owner never writes a shape of its own,
  which would let `ccp tasks check` pass on self-review.

### 19.6 When a pass is due, and how `ccp` enforces it

`ccp architect due` exits 0 when a pass is due. A **merge** is a task reaching `done` in the task
log. A pass is due when **any** of these holds (each threshold is a knob, §19.11):

1. **Cadence.** `every_n_tasks` tasks (default 4) have merged since the last pass, or `max_days`
   (default 14) have passed with at least one merge. Each pass records the done set at its start;
   with no pass yet, every done task counts.
2. **A review point closes.** Every task in the runner's scope is `done`. The scope's closing pass
   is part of its review pack. `ccp architect due|run --scope` (default: the running runner's
   `work.json` scope) carries the scope.
3. **Friction notes.** `notes_due` notes (default 3) have arrived since the last pass's start. Any
   worker (implementer, reviewer, verifier) may report friction in the *Friction* section of its
   report, and the runner records each line with `ccp health note`: a fact changed in many places, a
   test that pinned wording, a document read that did not help, a rule that forced extra work. The
   notes go to the next pass as leads.
4. **Health drift.** `ccp health` finds the median active time of the last 5 tasks above
   `drift_ratio` (default 1.5) times the median of the 10 before them (drift needs 15 timed tasks),
   or a house-rule budget (§20.2) over its limit on the integration branch. A task's active time is
   its wall time less its waits: every interval §23.3's `wait_hours` counts, whatever it waited on,
   plus its suite runs' waits on an exclusive lane (§16.6), each instant counted once and only inside
   its wall time. Time spent waiting does not count as slower work. Drift and budget triggers fire
   only when the last pass did not see them, so a lasting drift does not call a pass at every merge.
5. **On demand.** The owner or the operator runs `ccp architect run --force`. It works with no
   `architect` block too (an on-demand pass needs no scheduled reviews), but it is still refused
   while a pass is running or a report awaits triage; a `shape` run is refused only while one is
   running.

**When a trigger fired.** Cadence's moment is computed from the merges; every other trigger's moment
is the done count when `ccp` first saw it, kept in `architect.json` (`seen`), and the grace counts
from there.

**Citing an ADR.** An `adr_refs` entry cites an ADR when it opens with the ADR's number (`"0031 D1"`,
`"ADR-0031"`) or names its `adr/NNNN…` file (§7).

**Shape is due** when a pending task cites, in `adr_refs`, an ADR with no shaping record (a
`docs/delivery/reviews/sh-*.md` naming it on an `ADR: ADR-NNNN` line, or by any `ADR-NNNN` mention
when it has no such line; a bare number never counts). With `architect.shape_adrs` on (which needs
`shape_from_task`), `ccp tasks check` fails such a task unless its frontmatter says
`shaping: waived — <reason>` (§15). Only `pending` tasks from `shape_from_task` on are checked, so
older tasks never fail.

**Enforcement at `ccp tasks next`.** With an `architect` block, `ccp tasks next` needs `QUEUE_ROOT`
(exit 2 without it). It exits **4** and names no task when:

- a due pass has not started within `grace_tasks` further merges (default 1), counted from the
  moment it became due, printing the due
  reason;
- a report has waited for triage for at least `triage_grace_tasks` merges (default 2);
- `next` would name no task at all and a pass is due: a due pass then blocks at once, so a runner
  never stops with a due pass behind it.

A running pass does not block `next`: task work goes on beside it. A started pass that failed
restarts the grace: it blocks again only after one more merge (or on `--force`), naming the failure
and the first line of its `failed.txt`. After two failed passes in a row, `next` stops blocking on
the pass and tells the runner to take it to the owner. `--allow-overdue "<reason>"` overrides the
block once, and the override is recorded as a friction note with source `allow-overdue`.

**The runner, on exit 4:** it runs `ccp architect run` (a pass is due) or tells the owner, the lead
(triage is waiting), then asks `next` again. The idle hook (`TeammateIdle`) lets the runner idle while
`next` is blocked on a triage.

A pass never blocks task work otherwise: it sets no `waiting_on`, holds no task lease and does not
count toward any task's timers.

### 19.7 The run

1. **Preconditions.** Take `architect.lock` (atomic; stale after the call timeout plus 10 minutes,
   by §11's stale rule). The architect skill must be present (the plugin's, or a product copy); the
   run fails closed without it. Record `head` (HEAD of the product root, `product_root`), `base` (the previous pass's
   `head`) and whether the tree is dirty. A `running` pass whose lock is gone or stale is marked
   `failed` at the next check.
2. **Launch.** Write the prompt audit (§23; phases `architect-pass`, `architect-shape`,
   `architect-triage`, under `prompts/architect/`), emit the `architect` launch event, then run a
   fresh `claude -p "/architect …"` from the product root:
   - with the read-only tool list: `Read`, `Grep`, `Glob`, `Skill`, and `Bash` for `git log`,
     `git show`, `git diff`, `git ls-files`, `git grep`, `git status`, `git rev-parse`, `git blame`,
     `ls` and `wc`, plus each probe in `architect.probes` as `Bash(<probe>:*)`;
   - with `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `WebSearch`, `Agent` and `Task` disallowed,
     and `Read(./<p>)` / `Read(./<p>/**)` denied for each `private_dirs` entry;
   - with the API-key variables stripped (§30), the seat's pinned model and effort (`claude-opus-5-5` at
     `high`, §2), and
     `call_timeout_minutes` (default 45).

   The prompt carries the mode and lenses, `head` and `base`, the `ccp health` summary, the friction
   notes since the last pass, the rules doc's path and, for `shape`, the ADR. `ccp architect run
   --detach` starts the pass in its own session and returns once it runs; plain `run` is
   synchronous.
3. **Result.** The architect's final message is one JSON report. The driver refuses it unless the
   required fields are present, the findings are within the mode's cap, every finding has evidence
   and no `low` confidence, its category belongs to the run's lenses, a `rule-cost` finding has
   `needs_decision: true` and fix `decide`, every `rule_changes` entry names a rule id, an action
   and a check, and there are no secret-like strings. It then writes `reviews/<id>.json` and a
   rendered `.md`. Zero findings is `no_findings` and nothing is triaged. An invalid report is
   `failed`, its raw output kept in `reviews/<id>.failed.txt`, and the next due check offers a new
   pass. A quota stop is `quota_parked`: retry with `run --force` after the reset.
4. Emit the exit event and release the lock, always.

**Probes** are read-only command prefixes (a project's `--help`, a status or a task list). A probe
must not write, spend allowance, send anything or call an agent. Choosing them is the product's
decision, in `plane.json`.

Every write to a review state file is a short read-modify-write under its own lock, since `next`,
triage and a detached pass may write it at once.

### 19.8 Triage

The runner runs `ccp architect triage <id>` straight after a `reported` result and on later wakes
until the review is `triaged`. Triage goes to the **task-log owner, the team lead** (`team-lead`, §17):
`triage` prints the message for the lead and sets the review to `triage_sent`; a later
`triage <id>` applies the triage file once the lead has written it. Applying a valid triage file
sets the review to `triaged` and prints the seat's remaining actions:

- `register_tasks`: pull the integration branch and register each created task in the queue;
- `lead_asks_operator`: the owner's `question_for_operator`, which the lead asks the operator in
  its own session (§17.10; §3.6 names the triggers that also reach the product's notify channel).

An invalid or missing triage file is `triage_failed`, and the next wake retries.

**Triage authority** extends the spec maintainer's (§17), for triage only. The owner may create new task files and
their INDEX entries (never editing existing ids, `depends_on` or `dod_checks`), write
`docs/delivery/reviews/<id>.md`, record known-intentional notes in the house rules, and record
deferrals in the project's planning document. It re-checks each finding's evidence, gives every
finding one disposition (`task`, `spec`, `defer`, `needs_operator`, `duplicate` or `reject`),
creates at most `max_new_tasks` tasks (default 5, grouping related findings; doc fixes grouped into
one or two tasks), and commits by path with `review(<id>): triage — …`. Product decisions reach the
operator only through `needs_operator`.

**Architect-specific triage:**

- `rule-cost` always goes to `needs_operator`, with the architect's evidence and the owner's
  recommendation.
- Each `rule_changes` entry is applied to `rules_doc`, rejected with a reason, or sent to
  `needs_operator`. An applied change not yet on the integration branch uses `commit_sha: pending`
  and `pending_change` (what the commit will contain); `ccp architect triage --backfill <id> <sha>`
  records the sha once the commit exists, and `ccp architect status` lists unfinished backfills.
- The plane refuses a triage file where a `rule-cost` finding is not `needs_operator`, a rule change
  has no entry, a `needs_operator` has no question, or an applied change has neither a commit sha
  nor `commit_sha: pending` with `pending_change`.
- After a `shape` report, the owner adjusts the ADR's task graph and creates up to 3 preparatory
  refactor tasks; the ADR's first feature tasks depend on them.

### 19.9 Seats

| Seat | Duty |
| --- | --- |
| Architect (a fresh headless session) | Reads, measures and proposes, through its report only. It never edits, triages or creates tasks |
| Runner | Handles `next`'s exit 4. Records workers' friction lines (`ccp health note`) and metrics (`ccp health record`). Puts `rules_doc` in every implementer prompt. Never triages or edits the product itself |
| Implementer, reviewer, verifier | Read `rules_doc` (the implementer prompt lists it among the first reads). Report friction in the *Friction* section. The verifier gates on `ccp docs check`, which includes `architect.checks` (§21.2). Tasks created by triage are verified like any other |
| Task-log owner (the lead) | Triages. Applies rule changes. Creates refactor tasks. Runs `shape` before tasking an ADR, or records the waiver. Takes `rule-cost` findings to the operator |
| The operator | Decides `rule-cost` findings and architecture-level rules |

### 19.10 Events and statuses

- Event type `architect`, project-level (`task_id` empty). Ops and their payloads:
  - `launch`: `review_id`, `phase` (`review` or `triage`), `prompt_ref`;
  - `exit`: `review_id`, `phase`, `exit_code`;
  - `transition`: `review_id`, `from`, `to`;
  - `set` / `clear`: `holder`, `reason` (the lock).
- These events never move a task phase, open a work interval or start a task timer.
- Statuses: `running`, `reported`, `no_findings`, `failed`, `quota_parked`, `triaging`,
  `triage_sent`, `triage_failed`, `triaged`.

### 19.11 Binding and knobs

The seat is on when `plane.json` has an `architect` block (§8; unknown keys are refused):

| Key | Default | Meaning |
| --- | --- | --- |
| `rules_doc`, `rules_max_lines` | —, 150 | The house rules (§20.1), for example `docs/ENGINEERING.md` |
| `every_n_tasks`, `max_days`, `notes_due`, `drift_ratio` | 4, 14, 3, 1.5 | The triggers (§19.6) |
| `grace_tasks`, `triage_grace_tasks` | 1, 2 | The enforcement at `next` |
| `shape_adrs`, `shape_from_task` | off, — | The shaping check (§19.6) |
| `refactor_every`, `refactor_in_scope` | 4, `"deps"` | Refactor capacity and reach (§20.3, §20.4) |
| `call_timeout_minutes`, `max_new_tasks` | 45, 5 | The run and triage caps |
| `probes`, `checks`, `budgets` | — | Read-only probes (§19.7), product check commands and budgets (§20.1, §20.2) |
| `areas`, `metrics`, `private_dirs`, `shape_only_dirs` | — | Path groups for measurements, extra metrics (§27), paths the architect may not read, paths judged on shape only |

**No test under two checks.** A test runs once per gate, and a failure belongs to one check. The
config is refused when two `checks` select the same tests: each check's `cmd` resolves to the test
modules, classes and tests it names (`tests.test_x`, `tests.test_x.Case`, `tests/test_x.py::Case`).
Two checks overlap when they name the same module, class or test, or one contains the other. The
refusal names both checks and the shared module or class. A test directory or a `discover` run
names no module and is not judged.

Every default above can be overridden per product. `shape` is started by the task-log owner, when
`ccp tasks check` fails on an unshaped ADR; it never runs on its own when an ADR is accepted.

### 19.12 Older commands

`scripts/architecture-review.sh` and `ccp docs audit`, the thin aliases of the architect seat, are
retired: every bound project has moved to the architect seat. A sync removes a product's leftover
managed copies of the two older skills and `--check` reports them as `retired`.

## 20. House rules, budgets and refactors

### 20.1 House rules (`rules_doc`)

The house rules are the product's own engineering standards: product-owned, current-only (no
history), and short, because every implementer reads them. They are at most `rules_max_lines`
lines (default 150), which `ccp docs check` enforces.

**Sections:**

- **Architecture:** the parts of the product, and which may depend on which.
- **Single sources:** for each concept that tends to be copied (registries, enums, id formats,
  counts), the one place that owns it and how everything else derives from it.
- **Tests:** what a test checks (behaviour, not wording), the fixture policy, and what runs in the
  per-task gate and what does not.
- **Docs:** which document holds what, which are current and which are history, and what is never
  restated.
- **Budgets:** each budget with its check (§20.2).
- **Known intentional:** deliberate oddities, so passes do not raise them again.

**Every rule has an id and a check.** A rule is a list item opening `- **E<n>**` (the id pattern is
`ids.rule`, §7), and its check a line opening `check: pass|budget|command|docs`:

- `budget`: a `ccp` budget in `architect.budgets` with the rule's id;
- `command`: a product command in `architect.checks` (`{id, cmd, timeout_seconds?}`, default
  timeout 600), exit 0 = pass, run inside `ccp docs check` so the verifier gates on it (§21.2);
- `docs`: a rule `ccp docs check` runs, named after a dash by its `plane.json` key, several
  separated by commas: `package_docs` (§21.3, §21.4) or `package_docs.rules.<name>` (§21.6);
- `pass`: the architect judges it.

A budget or command rule needs its entry, a docs rule needs each key it names set, and every entry
needs its rule. A rule with neither a
check nor a lens that judges it is deleted at the next pass. `ccp docs check` holds the doc's shape,
its line cap and the `architect.checks` commands.

**Who changes the rules:** the architect proposes (`rule_changes`); the owner applies or rejects
each proposal in triage; a rule that changes the product's architecture, or contradicts a decision
the operator recorded, goes to the operator (`needs_operator`).

### 20.2 Budgets

`ccp` provides two language-agnostic budgets: `max_lines` per glob (source files and docs alike) and
`max_bytes` per named doc, measured over tracked files.

- **Budgets are not in the verifier's gate.** They are diagnostics: `ccp architect due` measures
  them, where a breach on the integration branch makes a pass due with a reason naming the budget
  (§19.6), and `ccp health` reports them. One file growing never fails an unrelated task's verifier.
- **A change's own budgets.** `ccp budgets check --base <ref>` judges the budgets on the files the
  change touches: the working tree (commits, edits, new files) against the merge base of HEAD and
  `<ref>`. A touched file over its budget fails it (exit 1, naming the file, its size and the
  budget) when the change grew it, by crossing the budget or growing while already over. A touched
  file over its budget that the change did not grow only warns; untouched files are not judged. With
  `architect.budgets` set, the implement brief runs it in the pre-gate and again before the PR, the
  fix brief before the push, and the verify brief as part of the gate, each with
  `--base origin/<integration>`.
- **A cut line.** A budget with one limit (`max_lines` or `max_bytes`) may declare `cut_line`, an
  integer below that limit. `ccp budgets check` warns for a touched file at or above the cut line and
  within the limit, naming the file, its size, the cut line and the limit, so a cut is tasked before
  the limit fails the gate; the warning never changes the exit code. A file over the limit is judged
  as above.

### 20.3 Refactor tasks

Kinds exist only with an `architect` block; without one, `kind:` is not read and a refactor is an
ordinary task.

- **Frontmatter `kind: refactor`** (the default kind is `feature`, §5). A refactor cites `rule_refs`
  (house-rule ids) or `review_refs` (finding ids) in place of `spec_refs`/`adr_refs`, and may leave
  the task log's `refs_any` keys out of its frontmatter. `ccp tasks check` refuses a refactor whose
  `spec_refs` or `adr_refs` are non-empty, because a refactor changes no rule. These are the default
  per-kind rules of `task_log.kinds` (§5).
- **Its own standing DoD: behaviour is unchanged.** The suite and the product's scenario checks
  pass; no test expectation changes except where the task names it; the SPEC does not change. A
  change to behaviour or to stored data is not a refactor: it is a feature task under the product's
  rules.
- **Capacity.** Once `refactor_every` feature tasks (default 4; `refactor_every: 0` turns it off) have merged since the
  last refactor merged, `ccp tasks next` returns a ready refactor the scope reaches (§20.4) ahead of
  any feature task, with a `why:` line ("a refactor, due after N feature merges since the last").
  "Merged since the last refactor" follows the git order in which task files became `done`, else
  task order.
- **Preparatory refactors from a `shape` pass** are ordinary refactor tasks; the ADR's first feature
  tasks depend on them.

### 20.4 Which refactors a scope reaches (`refactor_in_scope`)

A refactor relevant to the current work is done as part of it; one that is not immediately needed is
not added to the current scope, but waits at the top of the next review point's scope, so it sits
out one cycle at most.

- **`"deps"`** (the default, also when the key is left out): a refactor is in a scope when a task in
  the scope depends on it, directly or transitively (the walk passes through tasks of any kind; a
  done or dropped task pulls nothing in and ends the walk). `ccp tasks next` widens the scope to
  those refactors only, and its `why:` line names the scope task that needs it.
- **Every other outstanding refactor** (`status: pending`, ready or not) is placed at the top of the
  next review point's scope when that review point is started (§22.5), in task-number order, whether
  or not it relates to that scope. `ccp tasks next` returns a ready one of them before any other task
  in the scope, lowest number first, with a `why:` line saying so; only the lead's preference
  (`ccp tasks prefer`, §10) comes before them. A refactor still waits on its own dependencies.
  `work.json` keeps the list for the review point (`review_point_refactors`), so a respawn of the
  same review point puts back the ones still pending; it never adds a refactor filed during the
  cycle. The lead may take one out with `team.sh runner scope --remove`, which drops it from the
  list. When a spawn starts no new review point, or `runner scope --add` widens the scope, while
  refactors wait, `team.sh` says how many wait and that they join only at a new `--review-point`.
- **`true`:** refactors belong to every runner's scope. **`false`:** a refactor runs only in a scope
  that names it.

The board shows the waiting refactors (`now.refactors_waiting`: count, ids, the oldest, the mode;
with no scope in `work.json`, every pending refactor; `null` without an `architect` block), and
`ccp board status` prints a line when the count is not zero (§28).

### 20.5 Starter rules

The plane ships an optional starter set of generic house rules, `templates/docs-project/starter-rules.md`,
in the format of §20.1: one owner for every count or list, one home per fact, tests check behaviour,
deterministic tests, current-only docs, package docs are maps, and every reference resolves. Each
rule states its purpose, names itself in the set on a `starter: <name>` line, and names its check;
where the check is mechanical it is a `docs` check. No starter rule is mandatory.

- **Adopt.** `docs.starter_rules` in `plane.json` adopts the set (default `null`: not adopted; `{}`
  adopts every rule). `ccp init --starter-rules` writes the set to `docs/ENGINEERING.md` and, in a
  `plane.json` it writes, `docs.starter_rules` and the `package_docs` settings its `docs` checks name
  (§4.5). With the set adopted, `ccp docs check` fails while an adopted rule's `docs` check is not
  set, naming the rule and the key. It does not set `architect.rules_doc`: until the product sets it
  to the rules doc, no architect judges the `pass` rules.
- **Decline.** The product names the rule with its reason in `docs.starter_rules.declined`
  (`{"<name>": "<reason>"}`) and deletes it from its rules doc. `ccp docs check` does not run what a
  declined rule's check names, set or not, unless an adopted rule names it too, and prints each
  decline with its reason. Declining `package-maps` turns off the package-doc checks of §21.3 and
  §21.4, `no_delivery_ids` and the path check included; the `package_docs.rules` checks (§21.6)
  still run. A name outside the set is refused when the config loads.
- **Override.** The product tunes its check's settings in `plane.json` (globs, targets, patterns) or
  rewords the rule in its own rules doc; to replace the check, it declines the rule and writes its
  own in its place.

### 20.6 Mutation checks (`ccp mutate`)

`ccp mutate --run <run_id> --test <id> [--mutant <m> …] [--revert <path>[:<lines>] …]` tells "the
test passes" from "the test checks something", in any language. It runs in the calling seat's
worktree, a mutation worktree (`ccp wt create --kind mut`, §12.1) or the reviewer's or verifier's
own (`rev`, `ver`), and changes nothing else.

- **The product's command.** plane.json `mutate.command` is a shell template that runs one test,
  `{test}` (required) filled in shell-quoted; exit 0 means the test passed. `--test` is one test id,
  passed whole, so it may name a single test method (`<module>.<Class>.<method>` for a unittest
  command); what runs is the command's. It runs in the worktree's root, in its own process group,
  killed after `mutate.timeout_seconds` (default 600); a run killed at the limit counts as the test
  failing. With no command (`null`, the default) `ccp mutate` refuses (exit 2). Its test runs are not suite runs (§14.1): `ccp mutate` runs the command itself, and
  records them in its own rows and log, not as `suite` events.
- **A mutant** is `<file>:<old>=><new>`, the text `old` found exactly once in `file` (a path relative
  to the worktree's root, inside it) replaced by `new`, or the path of a patch `git apply` takes. A
  value with no `=>` is a patch. Every mutant is checked before any test runs; one that does not
  apply refuses the call (exit 2), nothing run.
- **A revert** (`--revert <path>[:<n>[-<m>]]`) is a mutant that puts back the merge base's version
  of the file (the merge base of HEAD and `origin/<integration>`, §12.1; a file the change added is
  removed). With a line range (1-based, inclusive, lines of the worktree's file) it puts back only
  the changes from the merge base those lines overlap, and a deletion inside the range or next to
  it. A revert that changes nothing, or a range outside the file, refuses the call (exit 2). The
  call takes at least one mutant; the `--mutant`s are numbered first, then the `--revert`s, each in
  the order given.
- **Killed only when the named test fails.** The test first runs unmutated; when it fails, the call
  stops (exit 1), nothing applied or recorded. Then each mutant is applied alone, the test runs, and
  the mutant is `killed` when it exits non-zero and `survived` when it exits 0. Another test the
  mutant breaks does not count.
- **The tree is restored** after each mutant: every file it touched is written back byte for byte
  (a file it made is removed, with any directory it made) and checked before the next. A file that
  cannot be restored stops the call (exit 1). A SIGTERM at any point of the call kills the running
  test, restores the files and exits 143.
- **Bound to the calling seat's run.** `--run` names the run, which must be open (not reported or
  abandoned), and the worktree must be a recorded `mut`, `rev` or `ver` worktree of the run's task;
  otherwise it refuses (exit 2). Each mutant adds a row to the run record's `mutation` list: the
  test id, the mutant's number, `kind` (`text`, `patch` or `revert`), the files it touched, a
  12-character digest, the outcome, the exit code, the seconds, `timed_out` and the worktree's name;
  never the mutant's text, old or new, or the test's output, which goes to `<run record>-mutate.log`
  beside the run record.
  The call ends with one `run`/`recorded` event (run id and the counts).
- **Exit codes:** 0 when every mutant was killed, 1 when one survived.

Choosing mutants is the seat's; the plane ships no mutation operators.

## 21. Doc checks

### 21.1 `ccp tasks check`: the task-log rules

`ccp tasks check` holds the task log to the canonical format (§5) and fails (exit 1) on:

- a filename that is not `NNNN-kebab-slug.md` at the product's width (§7), or a reused `NNNN`;
- missing required frontmatter, or a `task_id` that is not the filename;
- a status other than `pending`, `done` or `dropped` (a legacy `in_progress` or `blocked` reads as
  `pending` and warns);
- a dependency that does not exist, or a cycle of `depends_on` (named);
- no `refs_any` list non-empty (per kind, §20.3), or a missing required section;
- a `kind: refactor` task whose dod_check runs the gate or full lane (named);
- other than 1..`max_checks` unique `` - id: `kind-NN` `` checks, or soft language inside
  `## dod_checks` (dry-run lines are left out of that scan, since they quote output);
- a `done` task with no verification note (no `- ` line under `## Verification notes`);
- with `task_log.dry_run: true`, a `dod_check` of a task not `done` or `dropped` whose numbered step
  runs a backticked command but that carries no ``dry run (`<commit>`): <what it printed>`` line, or
  `dry run: n/a — <reason>` when it cannot be run yet, each with text after it (the check is that
  the line is there, not that it is true);
- a runtime key (`waiting_on`, lease fields, session ids) in frontmatter;
- a task file gone (an id in the committed INDEX.yaml, or a file git history deleted, with no file
  now), or a gone task's number held by another file that does not say `renamed_from: <old id>`;
- with an index, an INDEX.yaml that is missing or differs from what `ccp tasks index` would write
  (`ccp tasks index` refuses, writing nothing, while a task file is gone);
- with a review-point register, an unknown point (§22.3); with `shape_adrs`, an unshaped ADR
  citation (§19.6).

It warns, without failing, when a task not yet done names a later task as a prerequisite in prose:
the prerequisite goes in `depends_on` instead. Inline `# comments` in frontmatter are ignored.

### 21.2 `ccp docs check`

`ccp docs check` runs, in the product root: the package-doc rules (§21.3, §21.4) and the opted-in
generic rules (§21.6), less those a declined starter rule names, the house rules' shape and line cap
and the `architect.checks` commands (§20.1), the adopted starter rules' settings (§20.5), the
product's `docs.checks` commands (§21.5), the ADR check (§6), and `ccp tasks check`.
It is free and deterministic. It is part of the verifier's gate (§15), run by the verifier itself at
the PR head, and `ccp docs check` clean is part of the standing DoD where the product declares it.
A gate lane declared as stages also runs it as its last stage, `plane-docs` (§14.2).

### 21.3 Package-doc rules: the core

The plane owns the package-doc convention; a product's docs and the plane's own instructions point
here rather than restate it. A product's docs come in three tiers, by how a session loads them (§9.6):

| Tier | File | Loaded |
|---|---|---|
| Project brief | the root `CLAUDE.md` | always |
| Package doc | `CLAUDE.md` in a source directory (`claude_md_dirs`, or `doc_name: CLAUDE.md`) | automatically, when a session reads a file under that directory |
| On-demand package doc | `doc_name` (default `.claude.md`) in a source directory | when a session reads it |

A package doc is a map of what exists in its directory: what each part is for and where to look. It
is never a record of what a task did; that is the task log and Git.

The rules are opt-in: they run only with a `package_docs` block. The core is language-neutral.
Every directory below the root that holds source (not exempt) carries a package doc (`doc_name`, or
`CLAUDE.md` for `claude_md_dirs`), and the language pack's files carry module docstrings (§21.4).
A directory whose source files are all `.md` holds documents only and needs no package doc unless
`claude_md_dirs` lists it; a directory with any other source file still needs one. Each doc:

- opens with a `# ` title;
- has no heading naming a plan (`banned_headings`);
- is no longer than `size_ratio` × its directory's source lines;
- names no backticked path with a `path_ref_suffixes` suffix (default `.py .sql .json .md .sh`)
  that exists neither from the root nor from its directory;
- names no delivery id (below).

**No delivery ids (`no_delivery_ids`, default `true`).** No line of a package doc, and no code
comment of a file under `docstring_globs`, carries a task, finding or ruling id. Comments are read
only in files under `docstring_globs`, as the language pack reads them (§21.4): a product without
`docstring_globs` gets no comment check, and strings and docstrings are not comments. Each is
reported as `file:line` with the ids it carries. The plane's ids are:

- a task in the task log, at `ids.task.width` (§7): its id (`NNNN-slug`), unless a file extension
  follows it (`0001-init.sql` is a file name, a task's own file name included); its zero-padded
  number standing alone (`0042`, which a full stop may follow and a decimal's digits may not); or
  `task 42`, `task #0042` or `Task: 42`. Each counts only when its number names a task file in the
  task log, which `ccp docs check` reads once per run: a number that names none (`chmod 0644`,
  `task 2026`, `2026-q3-review`) is not an id. The same task forms, matched the same way, are
  `rules.no_ids`'s default (§21.6);
- always, an architect pass or one of its findings: `ar-<stamp>-<hex4>` or `sh-<stamp>-<hex4>`,
  with `#F<n>` for a finding;
- always, a spec question, whose answer is a ruling (§17): `sm-<stamp>-<hex4>`.

`delivery_id_patterns` adds the product's own ids (its findings, rulings, tickets) as regexes,
checked when the config loads. `false` turns the check off. Paths under `rules.history_attr`
(§21.6) are skipped.

In a git checkout only tracked files count. The root is not judged: its `CLAUDE.md` is the project
brief.

### 21.4 Language packs

`package_docs.language` selects a pack (default `python`; `none` runs the core alone; any other name
is a configuration error that lists the packs). A pack adds its source suffixes and directory names
to the core's, and it runs its per-file checks over `docstring_globs`. `language: none` with
`docstring_globs` set warns.

- **`source_suffixes`** defaults to the core's `.sql .json .md` plus the pack's.
- **`exempt_dirs`** defaults to the core's `.git .idea .claude docs node_modules` plus the pack's.
- A list given for either replaces both the core's and the pack's defaults: a product that sets one
  names every entry it keeps.

The packs:

- **python:** source `.py`, exempt `__pycache__ .venv`. Each file under `docstring_globs` (skipping
  `__pycache__`) parses and carries a module docstring. Its comments are its `#` comments. Opt-in `rules.no_call_bullets: true`: the
  docstring does not list functions as backticked call bullets (`` - `name(...)` ``).

A pack is a module in `ccp/doclang/`.

### 21.5 Product check commands (`docs.checks`)

`docs.checks` (`[{id, cmd, timeout_seconds?}]`) are product commands `ccp docs check` runs in the
root, exit 0 = pass, like `architect.checks` (§20.1) but not tied to a house rule. A failure is
reported as `docs check <id>` (a house-rule check as `check <id>`). Both kinds run in their own
process group, killed whole on timeout, and keep the last 20,000 characters of output.
`docs.workers` (default 1) is how many check commands (`docs.checks` and `architect.checks`) run at
once, each under its own timeout; results are reported in declared order.

### 21.6 Opt-in generic rules (`package_docs.rules`)

Each is off until named.

- **`citations: {globs, targets, ignore?}`.** Outside fenced code, every SPEC ref in a file under
  `globs` names a heading of a `targets` doc (fenced headings do not count) that starts with that
  ref. A ref is `ids.spec.prefix` + number (§7), optionally `.n` subsections, or a range `S3–S5`,
  standing alone: no letter, digit, `-` or `/` touching it (`S3-bucket`, `s3://`, `MS3` are not
  refs). A subsection cites its own heading if there is one, else its section's. A reversed range is
  an error. Lines matching an `ignore` regex are skipped. Every `[x](doc.md#anchor)` link names a
  heading of that doc by GitHub's anchor rules (link text kept, inline code unwrapped, lowercased,
  punctuation other than `-` and `_` removed, spaces to `-`, a repeated heading numbered `-1`, `-2`,
  …).
- **`no_ids: {globs, patterns?}`.** No line of a file under `globs` carries a delivery id, reported
  as `file:line`. By default: the task forms of §21.3, matched the same way (only a task in the task
  log counts, so an empty log gives none), at the product's task width. Other ids (findings,
  tickets) are the product's own regex `patterns`, which replace the defaults and are checked when
  the config loads.
- **`history_attr: <name>`.** Tracked files whose git attribute `<name>` is set are history
  (untracked files never are); the rules above skip them, and `ccp docs history-paths` lists them for
  the product's own absence checks. When git cannot answer, nothing counts as history.
- **`no_overlap: true`.** No two check commands (`architect.checks`, `docs.checks`) run the same
  command or the same test module; a module and a class or test inside it (`tests.test_x`,
  `tests.test_x.Case.test_y`, `tests/test_x.py::Case`) overlap.

### 21.7 The docs lens

What a rule cannot see, whether each doc's statements are true of the code beside it, is the
architect's `docs` lens (§19.4).

### 21.8 Who runs the checks

| Seat | Duty |
| --- | --- |
| Runner | `ccp tasks index` in the same commit as every durable status change, where the product keeps an index |
| Verifier | `ccp tasks check && ccp docs check` in the submitted checkout before walking a task's `dod_checks`, recorded in its verdict's `gate` (§15). A failure is a reject with its output |
| Implementer | `ccp docs check` clean, where the product declares it in its standing DoD |
| Task-log owner | Triage of the docs lens's findings, as for any pass (§19.8) |

## 22. Review points and the plan

### 22.1 What a review point is

A review point is a batch of tasks and ADRs the runner works through and stops at, for the operator
to review progress at a functional level (§3). It is the unit of scope the operator signs off, and
the unit for reporting time and tokens on that work. Review points are optional: a product uses
them by keeping a register.

### 22.2 The register

A product that uses review points keeps a register at `review_points.file` (default
`docs/delivery/review-points.yaml`): YAML, a list of mappings at the top level or under
`review_points:`:

```yaml
review_points:
  - id: R1
    name: first release
    goal: |-
      What finishing this point achieves.
    status: current        # planned | current | closed
    opened: 2026-01-15     # optional, YYYY-MM-DD; closed: only with status closed
```

- Each point has an `id` (`R<n>`, by `ids.review_point`, §7), a short `name` (one line, at most 40
  characters), a `goal`, a `status` (`planned`, `current` or `closed`; at most one current) and
  optional `opened` / `closed` dates.
- The task-log owner writes it with the operator; no tool or seat invents a name.
- The check refuses an id that does not match (`R1`, never `R0` or `R01`), a repeated id, a missing
  or multi-line name or one over 40 characters, a missing goal, an unknown status or key, more than
  one current point, a date that is not a date, a closed date on a point that is not closed, and a
  close before the open. A line the reader cannot read is a check failure. Entries are read with the
  plane's own frontmatter reader (plain, quoted and `|-` values); the plane takes no YAML
  dependency.
- `ccp tasks check` and `ccp docs check` validate it.

### 22.3 Two regimes

- **With a register,** a review point is `R<n>` and one of the register's ids everywhere: task
  frontmatter, ADR frontmatter, `work.json`, `team.sh runner spawn --review-point` (refused
  otherwise, before any write), the stamp at close and the backfill. A `task_log.review_point_pattern`
  key is then ignored, with a warning.
- **Without one,** a task's `review_point` is held to `task_log.review_point_pattern` (default
  `^R[0-9]+$`), with no strict error; while any task carries a review point, `ccp tasks check`,
  `ccp docs check`, the backfill, `ccp review-points` and the spawn each print one warning ("no
  review-point register: <path>; review points are unchecked — create it") and the board shows a
  banner suggesting the register. While any ADR carries `review_points`, `ccp adr check`, and so
  `ccp docs check`, print one warning naming those ADRs and the missing register; under
  `adr.strict` it stays a warning.

Every caller asks the same question (`reviewpoints.problem`): with a register, `R<n>` and one of
its ids; without one, the pattern.

### 22.4 Attaching tasks and ADRs

- **Task frontmatter `review_point: R<n>` is the plan:** the task-log owner sets it when scoping.
  `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` writes it as the frontmatter's last
  line of each task that has none (`--from-work`: every task in `work.json`'s scope). A task on
  another point is refused. It writes the working tree only: a target with uncommitted changes is
  refused, `ccp tasks check` runs before and after, and the exact `git commit` is printed.
- **An ADR may name the points it is built in:** `review_points: [R<n>, …]`, validated against the
  register. The ADR index gains a "Review points" column once one ADR has the field.
- With the register, `ccp tasks check` refuses an unknown point.

### 22.5 The runner's scope

With a register, `team.sh runner spawn --review-point R` without `--scope` takes the open tasks
tagged R, plus the waiting refactors on top (§20.4). With `--scope`, it warns about scope tasks not
tagged R and about open R tasks left out. Without a register, the scope is `--scope` or `work.json`'s
scope, with a warning for a point the pattern refuses. A review point counts as new when
`--review-point` is given and differs from `work.json`'s; the spawn reads the product's `plane.json`
and task log through `ccp` and refuses (exit 2, before any write) when either is unreadable.

### 22.6 Stamping at close, and the backfill

- **Stamp at close, as a fallback.** `ccp tasks close` stamps the runner's review point
  (`work.json` `review_point`) into the task file it closes when the file carries none and the point
  is accepted, in the reconcile commit; otherwise it says why in its `warnings`. A value already set
  is kept. The stamp keeps a CRLF file CRLF and every other byte, and warns when it cannot find the
  frontmatter's end. The board counts the current point's scope tasks that do not carry it yet as
  `unstamped`.
- **`ccp tasks backfill-review-points [--dry-run] [--json]`** gives tasks closed before the stamp
  their point once, from the queue's history, strongest source first:
  1. **the product log:** the first line of `reconcile.log.entry` becomes a pattern (`{review_point}`
     and `{nnnn}` or `{task_id}` captured); a matching entry is what `close` wrote at the time. Two
     different points for one task send it to the ledger;
  2. **the ledger's runners:** each `runner`/`spawn` opens a runner with its `review_point` and
     `scope`; `scope` events add to it; the next spawn or a `stop` ends it. A task's claim is its
     first `lease`/`set` or `phase` move to `leased` or `implementing`, else the queue file's
     `claimed_at`, else its `implementation_started_at`. The runner live at the claim wins when its
     scope listed the task; else the latest earlier runner whose scope listed it; else the first
     later one, spawned before the task was done, that did;
  3. **time:** the runner live at the claim, with no scope naming the task.

  A task with no such evidence stays unset, as does a point that is not accepted. It never
  overwrites a value. It writes the working tree only, as `tag` does (§22.4), with `close`'s own
  stamping helper, reads the queue and writes nothing there, commits nothing, and prints the exact
  `git commit -- <files>` for the lead. The dry run prints each task's point, claim time and source,
  and counts per point.

### 22.7 Renaming a point

`ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` renames a point used before
the register. It rewrites `review_point: OLD` in the task files (that line only; quotes, a trailing
comment and CRLF kept), sets `work.json`'s `review_point` when it is OLD, and records one ledger
event, `runner`/`set` `{field: review_point, from, to}`. The ledger's spawns and the product log keep
OLD (history is not rewritten); the backfill reads OLD as the new id through that event. It refuses a
target not in the register, and a target tasks already carry unless `--merge`. A second run changes
nothing.

### 22.8 Reading the register

`ccp review-points [list|show R<n>] [--json]` prints each point with its name, status, done/total,
open tasks by status and dates, the runner's point marked; `show` adds the goal and the open tasks.
It orders points by their number (by the configured pattern) and writes nothing.

### 22.9 The plan

The board's plan section (§28) and `ccp tasks next` share one selection (§10): the board's **next
pick** is `next`'s row 0, flagged when it is already in flight, followed by the rest in the order
`next` would take them if each merged in turn; the tasks `work.json` has in flight are listed apart.

The plan reads the task files, the ADR frontmatter, the queue's task records and `work.json`, and one
`git log` for the merges. It runs no product command and writes only `board/`. Its parts:

- tiles: tasks done of those not dropped, ready now, the current review point, ADRs fully built;
- **review points:** per point, its tasks (dropped left out), done, remaining, first and last done;
  the current point's name, goal and progress; its open tasks as in flight, ready, blocked or
  waiting on dependencies; the ADRs it builds with built % in the point and overall. A runner on a
  point the register does not have, or off the current one, is a banner;
- **ADR register:** id, title, status (superseded by, supersedes), date, each decision's state (§6),
  the points each ADR names (with built % per point: the citing tasks tagged that point, done over
  all) and, greyed, the points its citing tasks are on that it does not name; **built %** is built
  or live over the decisions not retired when the ADR records them, else done over the tasks citing
  the ADR in `adr_refs`, dropped ones left out; without an `adr` block, the cited ADRs by number;
- **burn-up:** per day, tasks in the log (not dropped, from `created`, or from the done day if
  earlier) against tasks done, at most 180 days;
- **dependency graph:** the open tasks in rows by depth, five to a row, open dependencies drawn and
  done ones counted, ready, in-flight, refactor and out-of-scope tasks marked, with a text list
  saying the same; past 150 open tasks, the first 150;
- **task board:** the open tasks, the 15 done most recently, and every task in a fold.

The ready queue, task board and ADR register carry the review point per row, with a filter (All,
Current, each point, None) kept per browser. `ccp board status` prints tasks done, ready, the next
pick and the current point.

### 22.10 INDEX and the plan's task fields

INDEX.yaml keeps its frozen format (§5); with `task_log.index: false` there is no INDEX. The fields
a plan needs per task (`kind`, `adr_refs`, `spec_refs`, `review_point`, `pr`, `merge_sha`,
`done_at`) are on `board.json`'s `plan.tasks`, one row per task. `pr`, `merge_sha` and `done_at` come
from the queue's close record (`tasks/<id>.json`), else from git's merge of the task (the subject's
`(#N)`), else from the close's verification note; `done_at` falls back to the task file's `updated`
date. An open task's row keeps its `depends_on`; a closed task's are in INDEX.yaml and its file.
