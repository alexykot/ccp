# Part I — Model

What the plane is, who works in it, and what a managed product holds. Rules only: the reasons are in
the ADRs (`docs/adr/`) and the implementation notes in `docs/design/`.

## 1. Purpose and principles

### 1.1 Purpose

Hand a product's PROJECT and SPEC to a team of agents and get working software on its integration
branch with minimal supervision. A Claude Code agent team is the whole team (§2): a lead that
steers, and a runner whose subagents implement, review and verify. The operator is an escalation
gate, not the message bus (§3).

### 1.2 Principles

- **Project-agnostic.** A product binds to the plane through its `plane.json` (§8.1): worktrees and
  environment hooks (§12), not an adapter layer.
- **Vendor orchestrators:** none; the plane is fully custom.
- The plane's standing principles are recorded in ADR-0001 (products bind by configuration and
  hooks) and ADR-0003 (one home per fact).

### 1.3 Goals and non-goals

Goals:

- a role split with hard allowlists (§2);
- a standing pre-merge definition of done;
- a durable project goal, behavioural SPEC and task log in the product's git (§4);
- a thin runtime queue for leases, runs, waits and credential status (§4.2);
- an implementer that opens its own pull request in the session that built it, and a review in a
  separate context;
- a verifier that proves each task against PROJECT, SPEC and the task, and a runner that merges
  only after its approve;
- escalation up the chain, and surviving silence, including quota and expired credentials;
- reuse across products through configuration and hooks.

Non-goals, for now:

- browser end-to-end suites and post-merge whole-system smoke tests as part of the gate;
- automatic promotion to production;
- a vendor control plane;
- an unbounded flat task list with no PROJECT or SPEC above it.

## 2. Seats

### 2.1 The seats

| Seat | Hosted as | May | Must not |
|---|---|---|---|
| **Design seat** (spec maintainer, task-log owner, gate approver) | the **lead** of the product's agent team: the operator's interactive session, in the product's main checkout | rule on spec questions and commit the ruling (§17); own the task log (write, amend, drop tasks; §4.2); set review points; approve the runner's gates (§3.3); spawn, message, rotate and stop runners; read the board | claim or implement tasks; launch implementers or verifiers; merge; run operator steps; edit source or tests |
| **Runner** | a **teammate** of agent type `ccp:delivery-runner`, holding one task at a time | claim tasks; launch the workers below; answer implementation questions; raise spec questions and gates to the lead; merge, itself, after the verifier's approve, once `ccp verify merge-ok` exits 0 and pinned to the head it names (§15); run approved operator steps; append implementation notes | invent intent; rule spec questions; edit SPEC, PROJECT, ADRs or task intent; talk product direction with the operator; approve its own gates; have an agent perform an action the harness denied |
| **Implementer** | the runner's **subagent**, agent type `ccp:delivery-implementer`, in the task's worktree (§12) | edit the worktree; make safe fixes; open the pull request from the session that built the change | merge; set a task done; promote to production; invent intent |
| **Reviewer** | the runner's fresh subagent, agent type `ccp:delivery-reviewer`, with no implementer context | review the change and write its report | share the implementer's context |
| **Verifier** | the runner's fresh subagent, agent type `ccp:delivery-verifier`, with a fixed packet (§4.1) and no implementer context | run the formal gate itself at the PR head and prove each `dod_check`; approve or reject through `ccp verify record` (§15); raise spec questions and hold approval until answered | merge; edit source; rewrite SPEC or PROJECT |
| **Architect** | a fresh headless read-only Claude session that `ccp architect` launches (§19, §21); its runs are recorded with `modelUsage` | read the product; run read-only commands and the binding's probes; return one report | edit, commit, write, spend, send, triage or create tasks |

Each of the runner's steps is a `ccp` command (§10): no hand-written queue state, prompts or
reconcile edits. The lead reads the board (§28) rather than asking the runner, and is told the plane's triage
of tool proposals (§31).

Plane development sessions (the plane's own repo) build the plane; they do not operate a product's
tasks.

### 2.2 Hosting

- There is one hosting: the Claude Code agent team (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). A
  binding's `hosting` line, where one is left, is ignored.
- The **design seat is the lead**, not a teammate: the lead is fixed for its lifetime and is the
  session `/resume` restores; teammates are not restored. The runner keeps its state in git and the
  queue, so it can be replaced at any time.
- The **runner's workers are subagents**, not teammates: teammates cannot spawn teammates, and
  dispatching workers from the lead would put dispatch in the design seat's context. Only their
  reports enter the runner's context.
- Liveness is the team's: idle and failure notices reach the lead, and the `TeammateIdle` hook
  keeps a runner working while in-scope work is ready (§18). There is no watchdog seat.
- The route to the operator is the lead's session, and on the triggers of §3.6 the product's notify
  channel as well.

### 2.3 Separation of duties

- **No combined seats.** A seat does not take another seat's duties.
- **The seat that rules never produces the evidence it rules on.** The seats that rule on a task are
  the lead and the runner at a gate. Evidence either produced does not count, except an operator step
  the operator approved (an approved `operator` gate, §17.9). The verify record names the seat that
  produced each piece of evidence, and `ccp verify` holds it to this rule (§15.4).
- Authority granted in a role's instructions applies only to that role.

### 2.4 Models, effort and tools

Each seat's model and effort is fixed in its agent definition (or launch flags) and never depends on
the lead session's settings:

| Seat | Model | Effort |
|---|---|---|
| Design seat (lead) | the operator's choice (the plane advises; it cannot set it) | the operator's choice |
| Runner | `claude-sonnet-5-5` | `high` |
| Implementer | `claude-opus-5-5` | `high` |
| Reviewer | `claude-sonnet-5-5` | `high` |
| Verifier | `claude-sonnet-5-5` | `high` |
| Architect | `claude-opus-5-5` | `high` (`--model`, `--effort`) |

- Models are **full ids**, never aliases: with an alias (`opus`, `sonnet`) or `inherit`, a subagent
  of the lead's model family runs on the lead's exact model, including its `[1m]` suffix. Moving to
  a newer model is a deliberate change of the definitions.
- The runner launches each worker by its agent type and **never passes `model`** in the Agent call:
  a call's `model` overrides the definition.
- Every seat's effort is fixed in its own definition, the runner's included; none is inherited from
  the design seat.
- Each worker definition names its tools (`tools:`, an allowlist that replaces the default set):
  the implementer (and so the fixer) and the verifier `Bash, Read, Edit, Write, Grep, Glob, SendMessage, ToolSearch`;
  the reviewer the same without `Edit`. The verifier keeps `Edit` for its mutation runs in a scratch
  worktree; the reviewer keeps `Write` for its report; `ToolSearch` stays because `SendMessage` is a
  deferred tool. The runner's allowlist is `Agent, Bash, Read, Edit, Write`.
- Every delivery definition, the runner's included, sets `experimental: {cacheTtl: 1h}`: a one-hour
  prompt-cache lifetime, so a long suite run or a wait on a worker does not expire the cache. A
  `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` environment variable, a `subagentPromptCacheTtl` setting or
  `FORCE_PROMPT_CACHING_5M` overrides it, and Claude Code ignores `1h` while a subscription is in
  overage.

### 2.5 How workers report

A teammate's Agent call returns at once and the subagent runs in the background; when the runner
then ends its turn, the subagent's final handback cannot reach it. So the handback is never the
channel. Every worker prompt ends with an instruction to:

1. submit its full report with `ccp report <run_id> FILE`; and
2. send the runner a short `SendMessage` naming it, addressed by the runner name that `work.json`
   `runner` binds (§16; `ccp prompt` writes it into the prompt).

The message wakes the runner. The runner treats the message, or the recorded report when the
message is missing, as the result; it never waits for a handback and never asks a worker to resend.
After launching a worker the runner may end its turn.

### 2.6 Seat knobs

- `runner.rotate_after_tasks` (default 4).
- The lead may run several runners at once (`--count`), up to `parallel.max_in_flight`, sharing one
  review-point scope, each holding one task (§16).
- The verifier is the runner's subagent with a fixed packet (the alternative, a teammate spawned by
  the lead, would cost the lead's context).

## 3. The operator and operator gates

### 3.1 The operator

- The operator is an escalation gate, not the message bus. Only the design seat brings a decision to
  the operator, in its own session (§17). The plane names when the operator must hear, and the
  product names the channel (§3.6).
- There is no operator approval for a merge to the integration branch: the runner merges after the
  verifier's approve (§15).
- The operator's own records (PROJECT with the design seat, the ADRs they accept, approvals of SPEC
  changes, §31) are what the design seat answers to.

### 3.2 Operator gates

1. Product intent the design seat will not call (a spec question it returns `needs_operator`, §17).
2. Security-sensitive changes.
3. Promotion from the integration branch to production.
4. Destructive operations.
5. Legal or compliance matters.
6. Re-authenticating an expired credential.
7. New production / MCP credentials.
8. Escalations marked `waiting_operator`.
9. Text a task declares for the operator's sign-off (§3.5).

Not operator-gated: a merge to the integration branch after the verifier's approve; a review the
runner launches; a quota pause.

### 3.3 Delegation to the design seat

The operator delegates these gates, as far as a runner hits them, to the design seat. The design
seat brings a gate to the operator when approving it would contradict a decision the operator
recorded, when it needs the operator's hands (single sign-on, credentials, payments), or when it is
production promotion or irreversible without a verified backup. The gate mechanics (escalation
files, decisions, standing approvals) are §17.

### 3.4 Production

Promotion to production is operator-gated and never automated. A product's branch names are its
binding's (`integration_branch`, `production_branch`, §8.3).

### 3.5 Operator sign-off

A task that carries text the operator must sign (a SPEC CURRENT → PROPOSED, a contract) declares
it in its frontmatter, `sign_off:`:

- `brief`: the text is known when the task is written. It is signed before the claim, and the
  sign-off covers the commit that last changed the task file.
- `build`: the build finds the text. It is signed after verify, and the sign-off covers the head
  that merges.
- `[brief, build]`: both.

Any other value (no stage, or one that is not `brief` or `build`) fails `ccp tasks check`, and claim
and close refuse the task until it is fixed.

The lead records each sign-off with `ccp tasks sign-off <id> --by <who> --words "…"
[--stage brief|build] [--head <sha>]`: a `sign_off` `recorded` event in the ledger (§23.2) with
`stage`, `by`, `words` and `head`; the event's `at` is when. A `build` sign-off's head defaults to the
verified head (`verification/<id>.json`); without one the command refuses unless `--head` is given.
A later record of a stage replaces the earlier. The command refuses (exit 2) a task that declares
no `sign_off`, a stage it does not declare, and, when it declares both, a call without `--stage`.

`ccp tasks claim` refuses a task whose `brief` sign-off is missing, or whose head does not contain
the commit that last changed the task file in the checkout it claims from (stale: the text changed
after the signing, and the operator signs it again); a head that is that commit or a descendant of it
holds. `ccp tasks close` refuses one whose declared sign-off is missing, or whose `build` sign-off
covers another head than the one it merges (stale: the operator signs the new head) (§10.5). How the
operator is asked is not part of this rule.

### 3.6 Notifying the operator

The plane names when the operator must hear; the product names the channel.

| Trigger | Fired by | Ids it carries |
|---|---|---|
| `blocker` | `ccp tasks wait <id> reauth` or `operator_step`: a wait only the operator clears | the task; the wait's reason |
| `decision` | a decision the operator must take: `team.sh gate ask-operator` (§17.9), a spec question answered `needs_operator` (§17.6), or `ccp tasks wait <id> operator_decision` | the task; the gate or question id |
| `review_point_done` | `ccp tasks close`, when the reconcile leaves the task's review point with no open task (every task that carries it done or dropped) | the task; the review point |
| `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint (exit 5, §25.3) | the task |

Every other wait (quota, the lead's own gates and questions) is not a trigger.

The channel is plane.json `notify` (§8.1): `command`, a shell command (default null), and
`timeout_seconds` (default 30).

- With no command the channel is the lead's session: the runner raises the trigger to the lead, who
  brings it to the operator (§17.10), and no command runs.
- With one, `ccp` runs it on each trigger, besides the lead's session, with an empty stdin, in the
  checkout the call came from (for a gate or a spec question, the binding's
  product root). Its environment carries the trigger and ids only: `CCP_NOTIFY_TRIGGER`,
  `CCP_PROJECT_ID`, `CCP_TASK_ID`, `CCP_NOTIFY_ID` (the gate, question or review point),
  `CCP_NOTIFY_REASON` (the wait's reason), and all of them as one line, `CCP_NOTIFY_LINE`. Never a
  brief, a question's text or file content. The command is the product's (an email, a chat message,
  another tool); the plane ships no client.
- Sending is best effort: a command that fails or overruns its timeout is a `notify:` warning on the
  step, which has happened all the same; the lead's session still carries the trigger.
- Each trigger sends once per call: a repeated wait, `gate ask-operator` or refused claim sends
  again. A close sends on the call that reconciles, or on the retry that records the task done
  after a close that crashed in between; a re-run that finds both done sends nothing, nor does
  `process` on an answer it already applied.

## 4. Product footprint

### 4.1 Three layers of product docs

Each managed product's repository holds:

```
docs/
  PROJECT.md          # goal, why, non-goals, success criteria (stable; rare edits)
  SPEC.md             # or spec/ — behavioural and domain truth
  adr/                # architecture decision records (§6), when the product keeps them
  delivery/
    plane.json        # the product's delivery configuration (§8.1)
    INDEX.yaml        # generated index of the task log (§5.7), when the product keeps one
    tasks/<id>.md     # durable task log (§5) — never deleted
    reviews/<id>.md   # durable review and shaping records (§19)
```

| Layer | Owner | Tasks must |
| --- | --- | --- |
| PROJECT | the operator with the design seat | respect it; never contradict it without escalating to the operator |
| SPEC | the design seat, as spec maintainer (§17) | cite it through `spec_refs` |
| `docs/delivery/tasks` | the design seat writes tasks; the runner and the verifier append notes; `ccp tasks close` sets `done` | be one unit of work toward the SPEC or PROJECT |

PROJECT and SPEC (`docs/PROJECT.md` and `docs/SPEC.md`, or `spec/`) sit above the task log: a task
answers to them.

**The verifier's packet always includes** a PROJECT summary (or its success-criteria excerpt), the
cited SPEC sections, the task file, its `dod_checks`, the proof URLs the worktree reports (§12) and
the pull request.

A tension between SPEC and PROJECT goes to the design seat, which rules and commits, or returns
`needs_operator`; only the design seat may decide that a spec question needs the operator (§17).

### 4.2 Task log and runtime queue

| Layer | Path | Contents | Lifecycle |
| --- | --- | --- | --- |
| **Task log** | `docs/delivery/` | task id, title, intent, refs, `dod_checks`, dependencies, terminal status, implementation and verification notes | **permanent**, in the product's git; a task is never deleted |
| **Runtime queue** | `.delivery-queue/<project>/` (one directory per project id), outside the product's git | leases, phases, runs, waits, questions, gates, credential status, the board | ephemeral |

- The queue is the only runtime state. There are no state branches, in the plane's repository or a
  product's.

**Who writes what:**

| Field | Writer |
| --- | --- |
| task id, title, intent, refs, `dod_checks`, dependencies | the task-log owner (the design seat); a claimed task is changed only by superseding it (§5, §17.4) |
| the task file's `## Context (not checked)` section | the task-log owner; the design seat when ruling on a spec question (commit `spec(<question_id>): …`, §17); on a claimed task, the implementer, writing a ruling the runner passes (§10.5) |
| status (`done` at close; `dropped` by the task-log owner, §5.3) | `ccp tasks close`; the task-log owner |
| implementation notes | the runner, from the implementer's output |
| verification notes and evidence | the verifier; `ccp tasks close` |
| lease, session id, ports, `waiting_on` | **runtime only**, never committed (`ccp tasks check` refuses them in a task file's frontmatter) |
| spec questions (`questions/sm-*.json`) | the raising seat (runner or verifier); runtime only (§17) |
| answer files (`questions/<question_id>.answer.json`) | the design seat; runtime only (§17) |

### 4.3 What a product holds

**Its own, changed only when the product changes:**

- `docs/PROJECT.md`, the SPEC, the ADRs, the house rules (`architect.rules_doc`, §20);
- the durable task log: `docs/delivery/tasks/`, `reviews/`, and `INDEX.yaml` when it keeps one
  (§5.7);
- `docs/delivery/plane.json`, its delivery choices (§8.1). The plane only ever adds optional keys to
  its schema, so an old `plane.json` stays valid;
- its rules for workers (`docs/delivery/WORKERS.md`, §13; `LOCAL.md`; `standing-dod.md`; its own
  `WRITING-tasks.md` and `TEMPLATE-task.md` if it keeps them);
- its permission allowlist in `.claude/settings.json`, because plugins cannot ship permissions. The
  allowlist names `ccp`, not a path.

**The anchor, written once by `ccp init` (§4.5)**: two settings entries naming the plane, not a
version, so a release needs no product commit, and the agent-team flag the hosting needs (§2.2):

```json
"extraKnownMarketplaces": {
  "ccp": {"source": {"source": "github", "repo": "alexykot/ccp"}, "autoUpdate": true}
},
"enabledPlugins": {"ccp@ccp": true},
"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
```

plus one line in the product's `CLAUDE.md`: "This repo is delivered by CCP (Claude Control Plane):
its plugin and `ccp`." Nothing else about the plane goes into the product. Everything the plane
owns (agents, skills, hooks, the orientation) reaches the product at run time from the plugin (§9)
and `ccp` on PATH (§29).

**Telemetry is not part of the product.** Its `env` block lives in the user settings, for every
session (§24). Claude Code ignores it in a project's `.claude/settings.json`; a block left there does
nothing, and `scripts/sync-product-docs.sh` notes that it can be removed.

### 4.4 Product docs

- A product's docs name the plane in one line (§4.3) and do not restate its mechanics, commands or
  paths.
- `ccp docs check` warns, and does not fail, on any plane checkout path in a tracked product file
  outside the task log and reviews: a product decides its own docs.

### 4.5 Adopting a product

A product is adopted by running `ccp init` in its repository. It writes:

- the PROJECT, SPEC and delivery templates (`templates/docs-project/`, `templates/docs-delivery/`)
  and, with `--starter-rules`, the starter house rules as `docs/ENGINEERING.md` (§20.5);
- a minimal `docs/delivery/plane.json` (§8.1): the project id, the worktrees directory, with
  `--gate` the gate lane, and with `--starter-rules` `docs.starter_rules` and the `package_docs`
  settings the starter rules' checks name; and `INDEX.yaml` when the product keeps one (§5.7);
- `.plane-runtime/` in `.gitignore`;
- the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, and the
  one `CLAUDE.md` line, once (§4.3);
- outside the repository, the local binding and its queue directory (§8.3).

It keeps a file that already exists and lists it as kept, unless given `--force`, so running it again
changes nothing. It refuses, writing nothing, when keeping would leave the product inconsistent: a
`plane.json` naming another project id, a binding for the id naming another product root or another
`--queue-root`, or a `.claude/settings.json` that is not a JSON object. The product commits what it
wrote, and adds its own worktree and environment hooks to `plane.json` (§12).

## 5. Task files

The task file is the plane's format, the same for every product. It holds knowledge and outcomes:
what the task is for, what proves it, and how it ended. Who is working on it and in which phase is
runtime state, in the queue (`contracts/task.schema.json`), never in the file.

Template: `templates/docs-delivery/TEMPLATE-task.md`. Writing rules: the plugin's `writing-tasks`
skill, then the product's `docs/delivery/WRITING-tasks.md`. Standing definition of done:
`templates/docs-delivery/standing-dod.md`, the plane's items then the product's. Frontmatter
contract: `contracts/task_file.schema.json`.

A copy of the template that was not filled in fails `ccp tasks check`:
- A task file not yet `done` or `dropped` that still holds `NNNN-kebab-slug`, `YYYY-MM-DD`,
  `As a <role>`, `<preconditions`, `<concrete, observable result>` or `One line, imperative` is
  refused. The message names each placeholder and its line. A placeholder quoted in a code span or a
  fenced block is not read.
- A task that cites no ref list, where `spec_refs` is one of the lists it may cite, is told to list
  the SPEC sections in `spec_refs` and cite them in its text.
- `plane.json` validation refuses a `suite.lanes` command that holds `<your test command>`.

### 5.1 File

`docs/delivery/tasks/<task_id>.md` (`task_log.dir`). `task_id` is the file name: a number of
`ids.task.width` digits and a kebab slug (§7). Never deleted, never renumbered; filesystem order is
execution order.

### 5.2 Frontmatter

One `key: value` per line, lists inline.

| Key | Required | Meaning |
|---|---|---|
| `task_id`, `title`, `status`, `depends_on`, `created`, `updated` | always | `depends_on` lists earlier tasks only |
| `spec_refs`, `adr_refs`, `rule_refs`, `review_refs` | per `task_log.required`, `refs_any` and the kind | what the task answers to (§7 for ref shapes) |
| `kind` | no (default `feature`) | a key of `task_log.kinds`; read with the architect block on (§20) |
| `review_point` | no | the review point whose scope it belongs to (§22) |
| `paths` | no | files or globs it touches, declared by its writer; parallel safety reads them before the Scope **In:** item (§16) |
| `parallel` | no | whether it may run beside other tasks (§16) |
| `gate` | no | `cold` only (§15) |
| `shaping` | no | `waived — <reason>` (§19) |
| `renamed_from` | no | the old id after an amended slug |
| `covers` | no | an after-the-fact task's merged commits, as shas (§10.7) |

A product may require more keys (`task_log.required`) and add its own. Runtime keys (lease, session,
`waiting_on`, ports, …) are refused.

### 5.3 Status

`pending`, `done` or `dropped`. `ccp tasks close` writes `done` with the verification note; the
task-log owner writes `dropped`, with a note naming what replaced the task.

There is no in-flight status in the file: claimed, implementing, in review and verifying are queue
states. `blocked` is not a file status either: what blocks a task is a dependency (`depends_on`), a
runtime wait (`waiting_on`, an open question or gate), or a planning decision, recorded by
superseding or dropping the task. A file written before this rule may still say `in_progress` or
`blocked`: it reads as `pending`, and `ccp tasks check` warns.

### 5.4 Kinds

`task_log.kinds`, read with the architect block on. Each kind names `refs_any` (the ref lists it
cites at least one of; default the task log's) and `forbid` (lists it leaves empty). The default:
`feature` uses the task log's `refs_any`; `refactor` cites `rule_refs` or `review_refs` and no
`spec_refs` or `adr_refs` (a refactor changes no rule, §20).

### 5.5 Sections

In order, each a `## ` heading:

| Section | Written by | Content |
|---|---|---|
| `Intent` | task writer | one paragraph: what is true for the user when this is done |
| `Context (not checked)` | task writer; the design seat when ruling (§17); on a claimed task, the implementer, writing a ruling the runner passes (§10.5) | background and constraints the verifier does not walk as checks. `Context (not verified)` is read as this heading |
| `Scope` | task writer | `- **In:** …` and `- **Out:** …` |
| `dod_checks` | task writer | 1..`max_checks` checks, each `` - id: `kind-NN` `` then `story`, `setup`, `steps`, `expect`; a check whose steps run a command carries `dry run (<commit>): …` or `dry run: n/a — <reason>` when `task_log.dry_run` is on (§10). No soft language |
| `Implementation notes` | runner, from the implementer's output | append-only |
| `Verification notes` | verifier; `ccp tasks close` | append-only, one `- ` line per check; a `done` task has at least one |

### 5.6 Fixed and configurable

The section names, the check grammar and the statuses are fixed: they are what `ccp` reads and
writes. A product configures which keys and sections are required (it may add, not rename),
`refs_any`, the kinds, `max_checks`, the soft words, `dry_run`, the records directory
(`task_log.reviews_dir`, default `reviews`) and the ids (§7).

### 5.7 `INDEX.yaml`

- `INDEX.yaml` is generated from the task files by `ccp tasks index` and never hand-edited.
- Its format is **frozen** at the fields `id`, `status`, `title`, `depends_on`, `path`. The plane never
  changes it; new task fields (`merge_sha`, `done_at`, …) go to the board's data, `board.json` (§28),
  instead.
- It is the product's choice: `task_log.index: true` (the default) or `false`. With `false`,
  `ccp tasks check` does not require it, no command writes one, and the plane's readers use the task
  files.
- The plane's own readers read the task files, not the index.

## 6. ADRs

An ADR (architecture decision record) is the plane's format for a design decision, the same for
every product, and wholly the plane's: format, checks, commands and register. Like the task file it
holds knowledge and outcomes, in git. The `adr` block of `plane.json` (§8.1) turns it on; without
the block no ADR is read.

### 6.1 File

`<adr.dir>/NNNN-slug.md` (or `<prefix>NNNN-slug.md`), id `<prefix>NNNN` (`ids.adr`, §7; default
`ADR-NNNN`). Subdirectories of `adr.dir` (an `archive/`) are read too and marked archived. The id
equals the file's number; a number is never reused.

### 6.2 Frontmatter

`contracts/adr.schema.json`. YAML, read without a YAML dependency: the subset of plain, quoted, `|-`
block and list values; a line outside it fails the check.

| Key | | Meaning |
|---|---|---|
| `id`, `title`, `status`, `date` | required | `status` one of `adr.statuses`; `date` `YYYY-MM-DD` |
| `deciders` | optional | who decides |
| `supersedes`, `superseded_by`, `amends` | optional | links, each a list of `<ADR id>` or `<ADR id> Dn` |
| `review_points` | optional | the review points it is built in (§22) |
| `spec_refs` | optional | SPEC sections it relies on or changes |
| `decisions` | optional | each decision's build state (§6.3) |
| `notes` | optional | free text, including the dated notes `ccp adr status --note` adds |

Any other key is read and warned about (move it into `notes`).

### 6.3 Decisions

- The body numbers its decisions as headings, **`### D1. Title`** (letter suffixes allowed: `D2a`),
  the one canonical marker.
- Other styles (a bold bullet `- **D1. …**`, a bold lead `**D1 — …**`, a paragraph `D1. …`) are read
  for compatibility and warned about. `ccp adr migrate --markers` rewrites them, changing only the
  marker line: a bold title that closes on the line and ends a sentence becomes the heading's title;
  any other text stays, bold intact, as the decision's first line; a decision that is one item of a
  list of other things is left for a person and named.
- A decision is the id's heading, else its first marker; a later line reusing the id (an
  implementation note, an acceptance list) is not a decision.
- `decisions:` records the state of each, one string per decision,
  `D<n> <state>[ by <ADR id>[ D<n>]][ — <note>]`, state one of:
  - `not_built` — accepted, not yet in the code;
  - `built` — merged;
  - `live` — in use (rolled out, migrated);
  - `retired` — no longer in force; `by` names what replaced it.

What is built and what still stands is a field per decision, never free text.

### 6.4 Statuses and moves

- `adr.statuses` is the vocabulary (default `proposed`, `accepted`, `in-progress`, `implemented`,
  `rejected`, `superseded`, `withdrawn`, `retired`; `in-progress` and `implemented` are kept for older
  ADRs, the build state lives per decision).
- `adr.transitions` lists the moves `ccp adr status` allows (default `proposed` → `accepted` |
  `rejected` | `withdrawn`; `accepted` → `superseded` | `retired`).
- Accepting an ADR records every body decision not yet recorded as `not_built`; retiring it retires
  every decision.

### 6.5 Links

- `supersedes` on the new ADR and `superseded_by` on the old one name each other.
- A link to one decision (`<ADR id> D2`) supersedes that decision only: the old ADR records it as
  `retired by …` and keeps its status (`--archive` refuses it). A decision link never answers a
  whole-ADR one.
- `amends` changes an ADR or decision without replacing it.
- Each link must resolve (the ADR, and the decision when named); a missing reverse link is a
  warning.

### 6.6 Commands

`ccp adr` (`ccp docs adr index|list` is the same):

- `new "<title>"` (`ccp adr new`) — the next number, a slug, `adr.template` (or the plane's), status `proposed`;
- `status N <status> [--note T]` — a move `adr.transitions` allows (`superseded` only through
  `supersede`);
- `supersede OLD NEW [--decisions D2,D4] [--by Dk] [--archive]` — both links; without `--decisions`
  OLD becomes `superseded` with every decision retired, and `--archive` moves it into
  `adr.dir/archive/` (`git mv`); with it only those decisions are retired, and `--archive` is
  refused;
- `decide N Dn <state> [--by REF] [--note T]` — one decision's state; `--by` must name an existing
  ADR or decision;
- `check`, `index [--stdout]`, `list [--json]`, `migrate --markers [--dry-run]`.

The commands rewrite only the frontmatter keys they change; every other line is kept byte for byte.
They regenerate `adr.index` when it is set. Call syntax: `docs/cli/01-model.md`.

### 6.7 Checks

`ccp adr check`, and so `ccp docs check`:

- **Failures:** frontmatter the reader cannot read; a missing required key; an id that is not the
  file's number; a status outside `adr.statuses`; `superseded` without `superseded_by`; a link or `by`
  that resolves to no ADR or decision; a malformed or duplicate `decisions` entry, or one naming no
  body decision; a task `adr_refs` entry citing a decision (`NNNN Dn`) its ADR does not have; a stale
  or missing index.
- **Warnings, failures under `adr.strict`:** a non-canonical decision marker; two `### Dn.` headings
  for one id; a missing reverse link; a link key holding prose; and **in force**: a `done` task
  citing a decision recorded `not_built`.
- **Always warnings:** undeclared keys; decisions out of number order.

The in-force check also runs before a task's verdict, on its PR head: under `adr.strict`, `ccp verify
record` refuses an approve of a head on which a decision the task cites is recorded `not_built`
(§15.4), so the task flips it in its own PR rather than at close.

### 6.8 Register

The board's ADR register (§28) shows each decision's state. When an ADR records any state, its
built % is built or live over its decisions not retired, a decision with no recorded state counting
as not built, and n/a when every decision is retired; otherwise it is the task-derived figure (done
over the citing tasks).

## 7. Ids and references

### 7.1 The `ids` block

The plane parses every id and reference it reads in a product's docs with one set of patterns
(`ccp/refs.py`), set by `plane.json`'s optional `ids` block. An absent key keeps its default:

```json
"ids": {
  "task":         { "width": 4 },
  "adr":          { "prefix": "ADR-", "width": 4 },
  "spec":         { "prefix": "S" },
  "rule":         { "pattern": "E[0-9]+" },
  "review_point": { "pattern": "R[1-9][0-9]*" }
}
```

An ADR prefix that would read a decision ref as an ADR (`D`, `D-`) is refused.

### 7.2 Parsing rules

- **Task ids:** `<width digits>-<kebab slug>`; the number names the task's worktrees, its scratch
  resources (`{nnnn}`) and its log entries. Run ids and queue files accept any width; the task log
  enforces the product's.
- **ADR ids and refs:** an ADR file is `NNNN-slug.md` or `<prefix>NNNN-slug.md`, its id
  `<prefix>NNNN`. An `adr_refs` entry cites an ADR when it opens with its number (with or without the
  prefix) or names its file; `Dn` (or `Dna`) after the number cites a decision, and any other
  trailing text is a section anchor (`0028 Acceptance tests arms-12`).
- **SPEC refs:** `<prefix><n>` and ranges (`S3–S5`). The citation rule of the doc checks (§21) reads
  them with `ids.spec.prefix`.
- **House-rule and review-point ids** match their pattern in full. A review point's first run of
  digits orders the points. `task_log.review_point_pattern` keeps its meaning for a product without
  a register (§22).

Where this SPEC writes `NNNN`, `ADR-NNNN`, `S<n>`, `E<n>` or `R<n>`, it means the default pattern.

## 8. Configuration

### 8.1 `docs/delivery/plane.json`

- Product-owned; contract `contracts/plane_config.schema.json`; example
  `templates/docs-delivery/example-plane.json`. The rules it sets describe the product's own tree,
  change with its code, and work in a worktree or a verifier checkout that never sees the queue.
- Its presence is the opt-in: `ccp` refuses to guess for a product without one. Only `project_id` is
  required: lowercase letters, digits and hyphens.
- Unknown keys are refused, so a typo cannot silently turn a rule off. The schema only gains
  optional keys.
- Each block is off, or at its defaults, when absent:

| Block | Sets | § |
|---|---|---|
| `ids` | id and reference patterns | §7 |
| `task_log` | task directory, required keys and sections, `refs_any`, `kinds`, `max_checks`, soft words, `dry_run`, `reviews_dir`, `index`; the statuses are fixed | §5, §10 |
| `adr` | `dir`, `index` (or `null`), `statuses`, `transitions`, `strict`, `template` (or `null` for the plane's) | §6 |
| `package_docs`, `docs` | doc checks (`claude_md_dirs`, `language`, `path_ref_suffixes`, `docstring_globs`, `no_delivery_ids`, `delivery_id_patterns`, `rules`), product check commands (`docs.checks`, `docs.workers`), the starter house rules (`docs.starter_rules`, §20.5) | §21 |
| `architect` | the architect seat, house rules, budgets, refactors | §19, §20 |
| `review_points` | the review-point register | §22 |
| `worktrees`, `env`, `merge`, `auth_check` | worktrees and environment hooks (`ccp wt`), the merge step (`merge.command`) and the paths that do not make a head behind the tip (`merge.behind_tip_ignore`), credential probes (`auth_check.probes`) | §12, §15, §16, §30 |
| `prompts` | the worker prompt fragment and `worker_env`; the prompt audit's `keep_body` (default `false`) and `audit_keep_days` (default `null`, keep all) | §13, §23.8 |
| `reconcile` | commands run at close | §10 |
| `gate` | the agent's shell limit and the gate's cut line (`shell_limit_seconds`, `cut_line_seconds`) | §14.6 |
| `suite`, `verify` | test runs and lanes (an argv or ordered `{name, cmd}` stages), verification and cache acceptance (`verify.accept_cache`), the fix rounds that need no new review (`verify.skip_review`) | §14, §15 |
| `parallel` | several runners | §16 |
| `report` | the verdicts every implementer report must state (`report.required_fields`) | §13.4 |
| `notify` | the operator's channel on each trigger (`command`, `timeout_seconds`) | §3.6 |
| `telemetry`, `board`, `estimate` | usage, allowance windows, the board, estimation | §24–§28 |

An example, with neutral values:

```json
"architect": {
  "rules_doc": "docs/ENGINEERING.md",
  "rules_max_lines": 150,
  "every_n_tasks": 4, "max_days": 14, "notes_due": 3, "drift_ratio": 1.5,
  "grace_tasks": 1, "triage_grace_tasks": 2,
  "shape_adrs": true, "shape_from_task": "0100",
  "refactor_every": 4, "refactor_in_scope": "deps",
  "call_timeout_minutes": 45, "max_new_tasks": 5,
  "probes": ["<read-only command prefix>"],
  "checks": [{"id": "E3", "cmd": "<product command; exit 0 = pass>"}],
  "budgets": [{"id": "E7", "glob": "src/**/*.py", "max_lines": 800}],
  "areas": {"code": ["src/**"], "tests": ["tests/**"], "docs": ["docs/**", "**/*.md"]},
  "private_dirs": [".env"]
},
"prompts": { "fragment": "docs/delivery/WORKERS.md",
             "worker_env": { "<NAME>": "<template: {{main_checkout}}, {{worktree}}, {{queue_root}}, …>" },
             "keep_body": false, "audit_keep_days": null },
"reconcile": { "hooks": ["<product command, run in close's merge worktree (§10.5)>"] },
"telemetry": { "otel_port": 4318, "allowance_cmd": "<command printing the allowance JSON>" },
"board": { "refresh_minutes": 5 },
"adr": { "dir": "docs/adr", "index": "docs/adr/INDEX.md" },
"suite": { "lanes": { "full": ["scripts/test.sh"],
                      "gate": [{"name": "lint", "cmd": "scripts/lint.sh"}, {"name": "tests", "cmd": "scripts/test.sh"}] },
           "summary": { "tail_lines": 40, "max_chars": 40000 },
           "log_keep_days": 14 }
```

- `reconcile.hooks` commands get `TASK_ID`, `PR`, `HEAD_SHA`, `MERGE_SHA` and `SUMMARY` in their
  environment (§10).
- `prompts.worker_env` maps a shell variable name to a one-line template. The fields are `run_id`,
  `task_id`, `nnnn`, `phase`, `worktree` (the worker's own: the task worktree for implement and fix,
  the reviewer's or verifier's for theirs), `main_checkout`, `queue_root` and `project_id`;
  `ccp docs check` and every command refuse another name. §13 says how the values reach the worker.

### 8.2 `ccp`

- One installed command, standard library only (`ccp/`, `bin/ccp`, `pyproject.toml`): seats,
  implementers and verifiers all run it from a product checkout, and the plane takes no third-party
  dependencies. `bin/ccp` works from any clone without installing.
- It runs in the product checkout: `--root DIR`, else `$CCP_ROOT`, else the git top level of the
  working directory.
- The task log's shape is enforced, not described: frontmatter a parser reads, a generated index that
  cannot drift, and a validator the verifier gates on (§10).

### 8.3 The binding

A product's binding is local configuration of the plane installation, not part of either
repository: `projects/<project_id>.yaml` beside the run checkout's code, gitignored, until the store
holds bindings (§29). Contract: `contracts/project.schema.json`; required: `project_id`,
`integration_branch`, `queue_root`, `durable_docs_path`.

```yaml
project_id: example-product
integration_branch: main
production_branch: main
product_root: /path/to/example-product          # the product's main checkout
durable_docs_path: docs/delivery/
queue_root: /path/to/.delivery-queue/example-product
runner:
  agent_type: ccp:delivery-runner      # the plugin's runner (§9)
  name: runner                                   # the teammate name asked for at a spawn; work.json `runner` binds the actual one (§16)
  worktree: /path/to/example-product/.plane-runtime/runner   # runner.worktree: with several runners, the prefix (§16)
  rotate_after_tasks: 4
  idle_block_limit: 3
```

- `ccp` maps a directory to its binding (`product_root`, or its main checkout for a worktree) and the
  binding to its queue (§9.2).
- The binding is the one source of truth. Every reader (`ccp`, the team scripts, the hooks) resolves
  it through one resolver, so an edit to it reaches them all. For a queue, the resolver takes
  `PROJECT_YAML` when it names a file, else the binding whose `queue_root` is that queue. The queue
  holds no copy: a `QUEUE_ROOT/project.yaml` left from before is read only when no binding names the
  queue. `ccp where` names the binding it resolved.
- `ccp init` writes the binding and creates its queue (default `~/.delivery-queue/<project_id>/`),
  with the product footprint (§4.3). It keeps an existing binding unless given `--force`, and refuses
  one that names another product root.
- A binding whose `product_root` is the plane's own repository is the plane managing itself; its
  usage counts as non-product use (§24).
- A `spec_maintainer` block is accepted, deprecated: the lead is every project's spec maintainer
  (§17). `seats.runner`, `seats.verifier`, `seats.watchdog` and `email` are
  ignored, as is a leftover `hosting:` line; the operator's channel is plane.json `notify` (§3.6). `cadence.verify_stale_minutes` is retired with the
  `verify_stale` blocker (§18.3).

### 8.4 Configuration knobs

- `telemetry.otel_port` (default 4318); `board.refresh_minutes` (default 5).
- The `--note` length limit on `ccp` commands that take one (4000 characters).
- How long the usage records (`usage.jsonl`) are kept (default: everything; they hold no content).

## 9. The plugin and orientation

### 9.1 The plugin

`plugin/` in this repository, with `.claude-plugin/marketplace.json` at the root naming it.

| Part | Notes |
|---|---|
| `agents/delivery-{runner,implementer,reviewer,verifier}.md` | named `ccp:delivery-runner` and so on; the binding's `runner.agent_type` and `ccp`'s run binding use the scoped names |
| `skills/architect/` | `ccp:architect` |
| `skills/spec-maintainer/`, `skills/review-triage/`, `skills/writing-tasks/` | loaded when the role needs them |
| `orientation.md` | the role-neutral orientation (§9.3) |
| `hooks/hooks.json` | **SessionStart** injects the orientation (`orientation.sh`); **SubagentStart** and **SubagentStop** call `ccp agent start|stop` (`run-binding.sh`); **TeammateIdle** runs the idle check (`runner-idle.sh`, §18) |

- A product's own copy of an agent definition in `.claude/agents/` wins over the plugin's while it
  keeps one; run binding and the agent hooks accept either name.
- Workers get their instructions from their agent definition and from `ccp prompt` (§13).

### 9.2 Finding the project

A hook receives `CLAUDE_PROJECT_DIR`. `ccp` maps it to a binding (§8.3, `projects/*.yaml`) and the binding to the queue:
no hook entry names a path. A directory that maps to no binding makes every hook a no-op. When
`QUEUE_ROOT` is unset, `ccp` sets it from the binding for the `project_id` in the product's
`plane.json`, the same from the main checkout and from any worktree; `ccp where` prints the project,
the binding file's path, the queue, the plane checkout and the `ccp` path.

### 9.3 Orientation

- The plugin's SessionStart hook injects the role-neutral orientation into the lead's and any
  interactive session in a managed product, kept under the hook's 10,000-character cap.
  SessionStart context does not reach subagents or teammates; workers are oriented by their
  definitions and prompts.
- The orientation is short (aim for one screen), in plain language, with no role-specific
  permissions. It covers:
  - what the plane is: a delivery loop run by a Claude Code agent team, a lead that steers and a
    runner whose subagents implement, review and verify; the operator is gated only on product
    decisions, sign-on and payments, and blockers nobody else can resolve;
  - the seats and what each does (§2.1);
  - where truth lives: product intent in PROJECT and SPEC, the durable task log in
    `docs/delivery/`, runtime state in the queue outside the repository (never edited by hand from a
    Claude session unless its role says so); rulings and durable facts live in git, never only in a
    session's memory;
  - how questions flow: implementation questions go to the runner, spec questions to the design
    seat, and only the design seat may bring a question to the operator; on the triggers of §3.6
    the operator is also notified (the plane names the triggers, the product the channel);
  - where each role's instructions are: an implementer's task prompt and the standing definition of
    done (`docs/delivery/standing-dod.md`); the design seat's `spec-maintainer` skill; an interactive session with the operator has no
    delivery role unless given one;
  - that authority in a role's instructions applies only to that role (§2.3).
- In the plane's own repository the hook gives one line pointing at its `CLAUDE.md` instead: a plane
  development session is not a seat.

### 9.4 Headless runs

Headless runs (`claude -p` for architect passes, audits and triage) get the plugin from `ccp` itself,
`--plugin-dir <run checkout>/plugin`; they do not depend on folder trust or marketplace installs.

### 9.5 No managed copies

- The plugin ships the agents, skills, hooks and orientation; no product holds a managed copy of
  them. `scripts/sync-product-docs.sh --check` reports a leftover managed copy as stale.
- Product-specific additions to the plane's instructions go in a product-owned file (for example
  `docs/delivery/LOCAL.md`).

### 9.6 Package docs

A session loads a product's docs in three tiers (§21.3): the root `CLAUDE.md` at every session start;
a `CLAUDE.md` below the root when Claude Code reads a file under its directory; a dot-prefixed
`.claude.md` only when the session reads it. The plane adds no loader: the first two are Claude
Code's own. The orientation (§9.3) and the `writing-tasks` skill point at §21.3 rather than restate
the convention.
