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

Every role has a default model, set by the plane, and its effort is fixed in its agent definition (or
launch flags); neither depends on the lead session's settings. A product may override any role's model in
plane.json `models` (`lead`, `runner`, `implementer`, `implementer_small`, `implementer_refactor`,
`reviewer`, `verifier`, `architect`, `estimator`), each an alias the Agent call's `model` accepts (`sonnet`,
`opus`, `haiku`, `fable`). The implementer's model is chosen per task: `implementer_small` for a task whose
estimate is at most 30 minutes, `implementer_refactor` for a task of that kind, else
`implementer`; its fix, merge and ruling rounds take the same model. Without an estimate the small choice
cannot apply, and `ccp prompt implement` warns. The defaults:

| Role | Model | Effort |
|---|---|---|
| Design seat (lead) | Opus: `ccp init` writes it into the product's `.claude/settings.json` when no `model` is set there, and never overwrites one | the operator's choice |
| Runner | Sonnet | `high` |
| Implementer (and its fix, merge and ruling rounds) | Opus; Sonnet for a small task or a refactor | `high` |
| Reviewer | Opus | `high` |
| Verifier | Sonnet | `high` |
| Architect | Opus | `high` (`--model`, `--effort`) |
| Estimator | Sonnet | `medium` (`--model`, `--effort`) |

- Models in agent definitions are **full ids**, never aliases: with an alias (`opus`, `sonnet`) or
  `inherit`, a subagent of the lead's model family runs on the lead's exact model, including its
  `[1m]` suffix. Moving to a newer model is a deliberate change of the definitions.
  `models` takes aliases, because the Agent call's `model` accepts nothing else; a definition's full id is its role's default model, which a test holds to the plane's role table.
- The runner launches each worker by its agent type and passes `model` in the Agent call only when `ccp prompt` prints an alias for that round: when the role's model for the task (§2.4 `models`, or its default) is not the definition's. A call's `model` overrides the definition. The runner's own spawn carries an alias the same way.
- Every seat's effort is fixed in its own definition, the runner's included; none is inherited from
  the design seat.
- Each worker definition names its tools (`tools:`, an allowlist that replaces the default set):
  the implementer (and so the fixer) and the verifier `Bash, Read, Edit, Write, Grep, Glob, SendMessage, ToolSearch`;
  the reviewer the same without `Edit`. The verifier keeps `Edit` for its mutation runs in a scratch
  worktree; the reviewer keeps `Write` for its report; `ToolSearch` stays because `SendMessage` is a
  deferred tool. The runner's allowlist is `Agent, Bash, Read, Edit, Write`.
- Every delivery definition sets `experimental: {cacheTtl: 1h}`: a one-hour prompt-cache lifetime
  for worker subagents, so a long suite run does not expire the cache. The runner is an agent-team
  teammate, whose cache lifetime comes from the `subagentPromptCacheTtl` setting, not its definition;
  `ccp init` sets it to `1h` (§4.5). A `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` environment variable, a
  `subagentPromptCacheTtl` setting or `FORCE_PROMPT_CACHING_5M` overrides a worker definition's `cacheTtl`, and Claude Code ignores
  `1h` while a subscription is in overage.

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

- A runner's rotation is due after 4 tasks, or at a request context of a size that is off unless
  a binding still sets one (§10.2 step 4, §29.3). With one runner, rotation reads
  the single-runner fields of `work.json` whatever holder the claim names; only with several runners
  does the holder pick the slot.
- `autoCompactWindow` (350000): `ccp init` writes it into the product's settings (§4.5).
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
9. Text a task declares for the operator's sign-off, or that its verdict finds beyond its intent (§3.5).

Not operator-gated: a merge to the integration branch after the verifier's approve; a review the
runner launches; a quota pause.

### 3.3 Delegation to the design seat

The operator delegates these gates, as far as a runner hits them, to the design seat. The design
seat brings a gate to the operator when approving it would contradict a decision the operator
recorded, when it needs the operator's hands (single sign-on, credentials, payments), or when it is
production promotion or irreversible without a verified backup. The gate mechanics (escalation
files, decisions, standing approvals) are §17.

### 3.4 Production

Promotion to production is operator-gated and never automated. A product's integration branch is its
binding's (`integration_branch`, §8.3).

### 3.5 Operator sign-off

A task that carries text the operator must sign (a SPEC CURRENT → PROPOSED, a contract) declares
it in its frontmatter, `sign_off:`:

- `brief`: the text is known when the task is written. It is signed before the claim, and the
  sign-off covers the commit that last changed the task file.
- `build`: the build finds the text.
  It is signed after verify, and the sign-off covers the head that merges, or the verified head when close's own catch-up carried it to the head that merges (§16.5 rule 4).
- `[brief, build]`: both.

Any other value (no stage, or one that is not `brief` or `build`) fails `ccp tasks check`, and claim
and close refuse the task until it is fixed.

A task whose change adds or changes a § rule carries, in its Scope, the exact CURRENT → PROPOSED text
of each passage and declares `sign_off: brief`, so the operator signs the words before the claim.
`ccp tasks check` warns on a task not yet `done` or `dropped` whose `paths` name a SPEC file
(plane.json `spec_paths`, default `["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"]`; a path meets an entry it equals or, for an entry ending in `/`, lies under, so `docs/spec` without its `/` meets none) and that neither declares a
`brief` sign-off nor says in its Scope that its SPEC text only describes its own feature (the word
`§31.1` on a Scope line). Rule text the build finds that the brief does not carry goes to a follow-up
proposal (`ccp plane propose`), and the PR merges on the signed text. Only text without which the
code cannot be correct goes to the lead as a spec question, and then a `build` sign-off is due
(below).

Text that only describes what the task's accepted brief and ADR call for (§31.1) needs no sign-off: a
task whose SPEC or contract text follows from them declares no `sign_off`. Text beyond that intent is
caught at review and verify. The reviewer's report carries a `## Spec beyond intent` section and the
verifier's verdict a `spec_beyond_intent` list (§15.4): each passage of normative text (SPEC, contract)
the PR adds or changes that the brief and its ADR do not call for, named by file and section; `none`, or
an empty list, when there is none. `ccp report` refuses a done review report without the section, and
`ccp verify record` a task's verdict without the list (a `pr-<n>` verdict may leave it out; a record
written before the field reads as listing none). A non-empty `spec_beyond_intent` in the task's latest
verdict makes a `build` sign-off due even when the task declares none: the runner tells the lead which
text needs it, and the lead records it as any other `build` sign-off.

The lead records each sign-off with `ccp tasks sign-off <id> --by <who> --words "…"
[--stage brief|build] [--head <sha>] [--at <date>]`: a `sign_off` `recorded` event in the ledger (§23.2)
with `stage`, `by`, `words` and `head`; the event's `at` is when. A `build` sign-off's head defaults to the
verified head (`verification/<id>.json`); without one the command refuses unless `--head` is given.
A sign-off the operator gave before it could be recorded (in git, before the product adopted the
plane) is recorded with `--at`, the date it was given (`YYYY-MM-DD`, a UTC date, or an RFC 3339 time
with its offset), which the payload keeps as `signed_at`, and `--from <commit>`, the commit it covers:
another name for `--head`, with the same defaults (for `brief`, the commit that last changed the task
file). `--at` refuses (exit 2) a value that is not such a date or is later than now: a date, when it is
later than today's UTC date, whatever the local zone. Claim and close judge it as any other sign-off.
A later record of a stage replaces the earlier. The command refuses (exit 2) a task with no sign-off
due (it declares no `sign_off`, and its verdict lists no `spec_beyond_intent`), a stage not due, and,
when both are due, a call without `--stage`.

`ccp tasks claim` refuses a task whose `brief` sign-off is missing, or whose head does not contain
the commit that last changed the task file in the checkout it claims from (stale: the text changed
after the signing, and the operator signs it again); a head that is that commit or a descendant of it
holds. `ccp tasks close` refuses one whose due sign-off (declared, or `build` from its verdict) is
missing, naming the verdict's passages beyond intent,
or whose `build` sign-off covers another head than the one it merges and close's own catch-up did not carry it there (stale: the operator signs the new head) (§10.5).
How the operator is asked is not part of this rule.

### 3.6 Notifying the operator

The plane names when the operator must hear; the product names the channel.

| Trigger | Fired by | Ids it carries |
|---|---|---|
| `blocker` | `ccp tasks wait <id> reauth` or `operator_step`: a wait only the operator clears; `ccp tasks claim` refused by a failed auth probe (exit 8, §30.1) | the task; the wait's reason, `reauth` for the refused claim |
| `decision` | a decision the operator must take: `team.sh gate ask-operator` (§17.9), a spec question answered `needs_operator` (§17.6), or `ccp tasks wait <id> operator_decision` | the task; the gate or question id |
| `review_point_done` | `ccp tasks close`, when the reconcile leaves the task's review point with no open task (every task that carries it done or dropped) | the task; the review point |
| `allowance_checkpoint` | `ccp tasks claim` refused at a weekly checkpoint, or with the account's usage unread for 60 minutes (exit 5, §25.3) | the task; the reason `usage unread` for the latter |
| `upgrade` | `scripts/run-checkout.sh update`, for each bound product with an `adopt` step it has not taken among the tasks the release brought (§29.3) | the release's commit; the steps |

Every other wait (quota, the lead's own gates and questions) is not a trigger.

The plane owns the trigger, the content and the record; the lead dispatches; the channel is
configuration.

- **Firing.** When a trigger fires, `ccp` writes a `notify` `pending` event to the ledger (§23.2;
  payload `trigger`, `project`, `task`, `id`, `reason`) and prints the rendered notice on stderr with
  the channel to use. The runner's message to the lead names the trigger.
- **Content.** `ccp notify render <trigger> [--task ID] [--id ID] [--reason R] [--json]`, the
  trigger one of the five above or `other`, prints a subject, `[<project_id>] <trigger>: <task or
  id>`, and a body of one line each for project, trigger, task, id and reason, those given, and
  nothing else: never a brief, a question's text or file content. `--json` gives the subject, the
  body and those fields.
- **Record.** `ccp notify sent <trigger> [--task ID] [--id ID] --via command|lead [--note TEXT]`
  writes a `notify` `sent` event (`trigger`, `project`, `task`, `id`, `via`, `by`: the seat it was
  run as, `ok`, `note`). A notice the lead sends on its own judgment is trigger `other` with a
  one-line `--note` (ids and a short reason, no content); `other` without one is refused (exit 2).
  `ccp notify pending` lists every notice fired with no later `sent` event for the same trigger,
  task and id with `ok` true, once however often it fired, so a trigger that fired while the lead
  was idle is still found.
- **Test notice.** In a sandbox only (§29.3), `ccp notify fire <trigger>` fires a notice as a step would: the `pending` record, the command channel, the rendered notice. It needs `--task` or `--id`, as every step that fires one gives; without either it refuses (exit 2) and records nothing.
- **Channels** (plane.json `notify`, §8.1):
  - `command`, a shell command, which `ccp` gives 30 seconds: the unattended
    channel `ccp` runs on each trigger but `upgrade`, which is only recorded for the lead to dispatch, so a release runs no product command, with an empty stdin, in the checkout the call came from (for
    a gate or a spec question, the binding's product root). Its environment carries the trigger and
    ids only: `CCP_NOTIFY_TRIGGER`, `CCP_PROJECT_ID`, `CCP_TASK_ID`, `CCP_NOTIFY_ID` (the gate,
    question or review point), `CCP_NOTIFY_REASON` (the wait's reason), and all of them as one line,
    `CCP_NOTIFY_LINE`. Never a brief, a question's text or file content. The command is the
    product's (an email, a chat message, another tool); the plane ships no client. `ccp` records its
    send itself (`via: command`, `ok: false` when it failed or timed out).
  - `lead`, `{"tool": …, "to": …}`, both non-empty, single-line strings: the lead
    sends each notice with that tool from its own session (a tool that exists only there, such as an
    MCP mail or chat server). Any other key, a missing one, or a value that is blank or holds a line
    break, is refused.
  - With neither, the lead's session is the route: the lead brings the notice to the operator there
    (§17.10).
- **Seats.** Of the seats, only the lead sends (the command is `ccp`'s). With a `lead` channel it renders each pending notice, sends it with
  the tool and records it (`--via lead`); it may also send on its own judgment (trigger `other`). The
  runner and the workers never send; `by` records the seat a `sent` was run as (`$ACTOR` when it
  names a ledger actor, else `design-seat`).
- Sending is best effort: a command that fails or overruns its timeout is a `notify:` warning on the
  step, which has happened all the same, and its notice stays pending for the lead.
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
  allowlist names `ccp`, and the plane's seat scripts by the absolute paths `ccp init --permissions`
  prints (§4.5), and no other plane path.

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
  outside the task log and reviews: a product decides its own docs. A `permissions` entry of
  `.claude/settings.json` naming one of the seat scripts `ccp init --permissions` prints (§4.5) is not
  warned about.

### 4.5 Adopting a product

A product is adopted by running `ccp init` in its repository. It writes:

- the PROJECT, SPEC and delivery templates (`templates/docs-project/`, `templates/docs-delivery/`)
  and the starter house rules as `docs/ENGINEERING.md` unless the product has it or `--no-starter-rules` says not (§20.5);
- a minimal `docs/delivery/plane.json` (§8.1): the project id, with
  `--language` the language, with `--gate` the gate lane (one stage, `gate`, running the line as given), and with the starter rules
  `docs.starter_rules` and the `package_docs` settings the starter rules' checks name; and `INDEX.yaml` when the product keeps one (§5.7) and has
  none yet (an existing one is kept and listed as kept); with `--gate`, the gate command written into
  `standing-dod.md`'s placeholder product item;
- in a `plane.json` it writes, the architect's adoption point (`architect.shape_from_task`, the next task number, §19.11), and the starter house rules unless the product has a rules doc (§20.5);
- `.plane-runtime/` in `.gitignore`;
- the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, with `subagentPromptCacheTtl: "1h"`, `autoCompactWindow` (`350000`), the lead's `model` (§2.4) and the telemetry tag `env.OTEL_RESOURCE_ATTRIBUTES` (`ccp.project_id=<project_id>`, §24.1) added when absent and never overwritten, and the one `CLAUDE.md` line, once (§4.3);
- with the operator's consent for the machine (`--telemetry on`, recorded once in the machine file beside the bindings, §8.3), the user-level telemetry keys (§24.1), the receiver and the product's board timer; it says first that the keys cover every Claude Code session on the machine, and that a project turns telemetry off in its own `.claude/settings.json` (§24.1). `--telemetry off` records a refusal, and init then writes nothing outside the product. With neither recorded, it prints what `--telemetry on` would do and writes nothing outside the product. When the receiver is down, it prints the command to run in a normal terminal: the receiver cannot be started from inside Claude Code, and only macOS has a service definition;
- outside the repository, the local binding and its queue directory (§8.3).

It records the adoption as a `plane`/`adopted` ledger event (§23.2) when it writes the binding, and
when the queue's ledger holds no such event yet (a queue from before the event, re-adopted), with `since`, the binding file's last change, as the adoption point `ccp health` reads in place of the event's time; a rerun on an adopted product records nothing.

It keeps a file that already exists and lists it as kept, unless given `--force`, so running it again
changes nothing. Even with `--force` it merges into `.claude/settings.json` and keeps every value already there, `subagentPromptCacheTtl` and `autoCompactWindow` included. It refuses, writing nothing, when keeping would leave the product inconsistent: a
`plane.json` naming another project id, a binding for the id naming another product root or another
`--queue-root`, or a `.claude/settings.json` that is not a JSON object. The product commits what it
wrote, and adds its own worktree and environment hooks to `plane.json` (§12). It warns, on stderr
and in its result's `warnings`, when the product has no `origin` or its origin is not on GitHub, and
adopts it all the same: review, merge and close need a GitHub origin until the PR host adapter of
ADR-0040 exists. Its result, and its stderr, list each required plane.json key (§8.1) still unset, as
a step to take before the first task. Only `github.com` and its subdomains count as GitHub, so an origin on a GitHub
Enterprise host on its own domain is warned about as not on GitHub. This is deliberate: the plane
knows GitHub by that host name only, and the warning does not stop the adoption.

- **The adoption checklist.** The plane's README lists each `plane.json` key a product may need beyond
  the minimal file, with what it is for and when a product needs it.
- **The permission list.** `ccp init --permissions` writes nothing. In an adopted product it prints the
  runner's and workers' permissions (§18.5) as a JSON `permissions` block:
  - an allowlist: `ccp` by name (§4.3), and the plane's `team.sh` and `spec-maintainer-ask.sh` by
    absolute path, each of the three also behind the binding's `QUEUE_ROOT=`; git by verb; `gh pr`;
    and the gate lane's commands;
  - a deny list of destructive commands.

  It refuses (exit 2) another init flag, and a product without a `plane.json` that loads or without
  its binding and queue. The operator applies the block to the product's `.claude/settings.json`
  (§4.3).
- **The gate on the tip.** Before the first task, the lead runs the gate lane once in the baseline
  worktree, `ccp wt create --kind ver --baseline` (§12.1), which needs no task, so a red tip is known
  before the first verifier finds it.
- **An existing rules doc.** `ccp init --rules-doc PATH` (relative to the product root) lists each
  rule of the product's own house-rules doc that has no `check:` line (§20.1) and points at the
  starter rules (§20.5); it writes nothing. With `--adopt` it gives each such rule a `check: pass`
  line at the end of its item, and refuses (exit 1), writing nothing, when that would put the doc over
  its 150-line cap (§20.1), or when the doc, parsed again with those lines, would have an adopted rule not
  reading `pass` or another rule's check changed (a fenced block left open, for one). The rules parser
  skips fenced code blocks: a line inside one opens no rule and is no rule's `check:`. The rule ids
  and the cap are the product's when its `plane.json` loads. It does not set `architect.rules_doc`,
  and refuses (exit 2) another init flag and a missing doc.

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

`docs/delivery/tasks/<task_id>.md`. `task_id` is the file name: a number of
`ids.task.width` digits and a kebab slug (§7). Never deleted, never renumbered.

### 5.2 Frontmatter

One `key: value` per line, lists inline.

| Key | Required | Meaning |
|---|---|---|
| `task_id`, `title`, `status`, `depends_on`, `created`, `updated` | always | a `depends_on` naming a later task is allowed; a cycle or a missing id is refused |
| `spec_refs`, `adr_refs`, `rule_refs`, `review_refs` | per the kind (§5.4) | what the task answers to (§7 for ref shapes) |
| `kind` | no (default `feature`) | `feature` or `refactor` (§5.4); read with the architect seat on, for tasks from its adoption point (§19.11, §20) |
| `review_point` | no | the review point whose scope it belongs to (§22) |
| `paths` | no | files or globs it touches, declared by its writer; parallel safety reads them before the Scope **In:** item (§16) |
| `parallel` | no | whether it may run beside other tasks (§16) |
| `clashes_with` | no | ids of tasks it clashes with: both change the same logic in different ways, so they run in either order, never together; the relation is symmetric, a clash recorded on either task holds for both. Read only under `parallel.schedule: clashes` (§16.3); an id that names no task, or the task itself, is refused |
| `gate` | no | `cold` only (§15) |
| `shaping` | no | `waived — <reason>` (§19) |
| `renamed_from` | no | the old id after an amended slug |
| `covers` | no | an after-the-fact task's merged commits, as shas (§10.7) |
| `adopt` | no | what a product must do to use what the task delivers: `none` (also when the key is absent), or one concrete step naming the file and key (ADR-0041 D1). A task that ships an off-by-default knob carries its step, never `none`; `ccp tasks check` warns on a `none` value that names a plane.json, binding or settings key. A step a product must take for the plane to keep working with it starts with `required:`; any other step is optional |

A product may add keys of its own. Runtime keys (lease, session,
`waiting_on`, ports, …) are refused.

### 5.3 Status

`pending`, `done` or `dropped`. `ccp tasks close` writes `done` with the verification note; the
task-log owner writes `dropped`, with a note naming what replaced the task.

There is no in-flight status in the file: claimed, implementing, in review and verifying are queue
states. `blocked` is not a file status either: what blocks a task is a dependency (`depends_on`), a
runtime wait (`waiting_on`, an open question or gate), or a planning decision, recorded by
superseding or dropping the task. A file written before this rule may still say `in_progress` or
`blocked`: it reads as `pending`, and `ccp tasks check` warns.

A task file from an earlier plane generation (no frontmatter: a Meta and a Refs table) is converted
in place by `ccp tasks migrate [--dry-run] [--drop-open]`: its frontmatter from those tables and the
title from the committed `INDEX.yaml`, its old text kept under `Context (not checked)`, a done or
dropped record marked converted and not re-verified. An open task is converted only with
`--drop-open`, as `dropped`; a file it cannot convert is named with the reason and left as it is
(exit 1).

### 5.4 Kinds

Two kinds, read with the architect seat on, for tasks from its adoption point (§19.11). Each names
the ref lists a task of that kind cites at least one of, and the lists it leaves empty: `feature`
cites `spec_refs`; `refactor` cites `rule_refs` or `review_refs` and no `spec_refs` or `adr_refs` (a
refactor changes no rule, §20).

### 5.5 Sections

In order, each a `## ` heading:

| Section | Written by | Content |
|---|---|---|
| `Intent` | task writer | one paragraph: what is true for the user when this is done |
| `Context (not checked)` | task writer; the design seat when ruling (§17); on a claimed task, the implementer, writing a ruling the runner passes (§10.5) | background and constraints the verifier does not walk as checks. `Context (not verified)` is read as this heading. A count, size, site list or "already"/"never" claim in it names, on its line, the command that measured it and the commit it ran at; `ccp tasks check` warns, without refusing, about a line of it, in a task not yet done, that states a number with no backticked command on it |
| `Scope` | task writer | `- **In:** …` and `- **Out:** …`. In **In:**, a path the task creates is marked `new` and one it deletes `removed`, the word within the 25 characters after the path and before the next backtick; `ccp tasks check` warns, for a task not yet done, about a path there (holding a `/`, not a glob) that does not exist, is not marked and is not in a dependency's **In:** (§16.3) |
| `dod_checks` | task writer | 1..6 checks, each `` - id: `kind-NN` `` then `story`, `setup`, `steps`, `expect`; a check whose steps run a command carries `dry run (<commit>): …` or `dry run: n/a — <reason>` where dry runs are required (§21.1). No soft language |
| `Implementation notes` | runner, from the implementer's output | append-only |
| `Verification notes` | verifier; `ccp tasks close` | append-only, one `- ` line per check; a `done` task has at least one |

### 5.6 Fixed and configurable

The section names, the check grammar and the statuses are fixed: they are what `ccp` reads and
writes, and so are the required keys and sections, the kinds, the check count, the soft words and
the records directory (`docs/delivery/reviews`). A product configures the SPEC paths (`spec_paths`,
§3.5) and the ids (§7).

### 5.7 `INDEX.yaml`

- `INDEX.yaml` is generated from the task files by `ccp tasks index` and never hand-edited.
- Its format is **frozen** at the fields `id`, `status`, `title`, `depends_on`, `path`. The plane never
  changes it; new task fields (`merge_sha`, `done_at`, …) go to the board's data, `board.json` (§28),
  instead.
- Every product keeps one. A product that still sets `task_log.index: false` (§29.3) keeps none:
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
| `id`, `title`, `status`, `date` | required | `status` one of the statuses (§6.4); `date` `YYYY-MM-DD` |
| `deciders` | optional | who decides |
| `supersedes`, `superseded_by`, `amends` | optional | links, each a list of `<ADR id>` or `<ADR id> Dn` |
| `requires` | optional | prerequisites, each `"<Dn> <ADR id> <Dm>"` (this ADR's Dn rests on that ADR's Dm) or `"<Dn> <Dm>"` within the ADR; only decisions are named (§6.5) |
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

- The statuses are `proposed`, `accepted`, `in-progress`, `implemented`, `rejected`, `superseded`,
  `withdrawn` and `retired` (`in-progress` and `implemented` are kept for older ADRs, the build state
  lives per decision).
- `ccp adr status` allows the moves `proposed` → `accepted` | `rejected` | `withdrawn` and
  `accepted` → `superseded` | `retired`, and for older ADRs
  `in-progress` → `accepted` | `superseded` | `retired` and `implemented` → `superseded` | `retired`.
- Accepting an ADR records every body decision not yet recorded as `not_built`; retiring it retires
  every decision. Accepting refuses while another ADR its `requires` names is still `proposed`,
  naming it: the prerequisite is accepted first.

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
- `status N <status> [--note T]` — a move §6.4 allows (`superseded` only through
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
  file's number; a status outside §6.4's; `superseded` without `superseded_by`; a link or `by`
  that resolves to no ADR or decision; a malformed or duplicate `decisions` entry, or one naming no
  body decision; a task `adr_refs` entry citing a decision (`NNNN Dn`) its ADR does not have; a stale
  or missing index.
- **Warnings, failures under `adr.strict`:** a non-canonical decision marker; two `### Dn.` headings
  for one id; a missing reverse link; a link key holding prose; and **in force**: a `done` task
  citing a decision recorded `not_built`.
- **Always warnings:** undeclared keys; decisions out of number order; ADRs carrying `review_points`
  with no review-point register, one warning naming them (§22.3).

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
  digits orders the points. Without a register, a task's review point is held to `ids.review_point.pattern` (§22).

Where this SPEC writes `NNNN`, `ADR-NNNN`, `S<n>`, `E<n>` or `R<n>`, it means the default pattern.

## 8. Configuration

### 8.1 `docs/delivery/plane.json`

- Product-owned; contract `contracts/plane_config.schema.json`; example
  `templates/docs-delivery/example-plane.json`. The rules it sets describe the product's own tree,
  change with its code, and work in a worktree or a verifier checkout that never sees the queue.
- Its presence is the opt-in: `ccp` refuses to guess for a product without one. Two keys are
  required: `project_id` (lowercase letters, digits and hyphens) and `language`, the product's
  language pack (§21.4) or `none`; the plane assumes no language. `suite.lanes` must name a gate lane
  (§14.1): without one, `ccp tasks claim` and `ccp tasks next` refuse with exit 2, naming it. A
  command that needs the language (the package-doc checks and with them `ccp docs check`, `ccp suite
  affected`, and the reading of test output, §14.1) refuses with exit 2, naming the key, when it is
  unset; other commands run.
  During the grace release that introduces a required key (§29.3), a command that needs it warns
  instead, naming the key and its upgrade step, and behaves as before the key was required.
- Unknown keys warn when the configuration loads (stderr, naming each and saying the running `ccp`
  may predate it) and are otherwise ignored, so a `ccp` older than a key keeps working until it is
  updated; `ccp docs check`, which every gate runs, refuses them, so a typo cannot silently turn a
  rule off. The schema gains a required key, or drops or moves one, only as §29.3 allows.
- A key that is not the product's to decide is a constant in code. The schema keeps a key that was removed, merged or made constant, marked deprecated with its outcome, and `ccp upgrade status` lists each one a product still sets (§29.3).
- Each block is off, or at its defaults, when absent. Each key's default is in the schema
  (`contracts/plane_config.schema.json`), which the plane's tests hold to the code. The blocks that
  hold settings:

| Block | Sets | § |
|---|---|---|
| `ids` | id and reference patterns | §7 |
| `spec_paths` | the SPEC files, read by the sign-off checks and the estimator | §3.5, §26 |
| `adr` | `dir`, `index` (or `null`), `strict`, `template` (or `null` for the plane's) | §6 |
| `package_docs`, `docs` | doc checks, run when `language` names a pack (`claude_md_dirs`, `docstring_globs`, `delivery_id_patterns`, `rules`), product check commands (`docs.checks`), the starter house rules (`docs.starter_rules`, §20.5) | §21 |
| `architect` | the architect seat, house rules, budgets, refactors | §19, §20 |
| `worktrees`, `env`, `merge`, `auth_check` | worktree links and environment hooks (`ccp wt`), the merge step (`merge.command`) and the paths that do not make a head behind the tip (`merge.behind_tip_ignore`), credential probes (`auth_check.probes`) | §12, §15, §16, §30 |
| `prompts` | the worker prompt fragment and `worker_env` | §13 |
| `reconcile` | commands run at close | §10 |
| `suite`, `verify` | test runs and lanes (an argv or ordered `{name, cmd}` stages), verification and cache acceptance (`verify.accept_cache`), the fix rounds that need no new review (`verify.skip_review`, `verify.skip_review_after_clean`), the declared provers that skip a gate stage or the review (`verify.provers`) | §14, §15 |
| `parallel` | several runners | §16 |
| `report` | the verdicts every implementer report must state (`report.required_fields`) | §13.4 |
| `notify` | the operator's channels on each trigger: the command `ccp` runs (`command`) and the lead's tool (`lead`: `tool`, `to`) | §3.6 |
| `estimate` | estimation | §26 |

An example, with neutral values:

```json
"architect": {
  "rules_doc": "docs/ENGINEERING.md",
  "every_n_tasks": 4,
  "shape_adrs": true, "shape_from_task": "0100",
  "refactor_every": 4,
  "probes": ["<read-only command prefix>"],
  "checks": [{"id": "E3", "cmd": "<product command; exit 0 = pass>"}],
  "budgets": [{"id": "E7", "glob": "src/**/*.py", "max_lines": 800}],
  "areas": {"code": ["src/**"], "tests": ["tests/**"], "docs": ["docs/**", "**/*.md"]},
  "private_dirs": [".env"]
},
"prompts": { "fragment": "docs/delivery/WORKERS.md",
             "worker_env": { "<NAME>": "<template: {{main_checkout}}, {{worktree}}, {{queue_root}}, {{round}}, …>" } },
"reconcile": { "hooks": ["<product command, run in close's merge worktree (§10.5)>"] },
"adr": { "dir": "docs/adr", "index": "docs/adr/INDEX.md" },
"suite": { "lanes": { "full": ["scripts/test.sh"],
                      "gate": [{"name": "lint", "cmd": "scripts/lint.sh"}, {"name": "tests", "cmd": "scripts/test.sh"}] } }
```

- `reconcile.hooks` commands get `TASK_ID`, `PR`, `HEAD_SHA`, `MERGE_SHA` and `SUMMARY` in their
  environment (§10).
- `prompts.worker_env` maps a shell variable name to a one-line template. The fields are `run_id`,
  `task_id`, `nnnn`, `phase`, `kind` and `seat` (the worker's worktree's: the record of the
  worktree its run is bound to, §12.1, when `ccp wt` made one there; otherwise as `ccp wt create`
  records them by default: `impl` for implement, fix, merge and ruling, `rev` for review, `ver` for
  verify), `round` (the worker's worktree's round: n when its name ends `-n`, otherwise 1),
  `worktree` (the worker's own: the task worktree for implement and fix, the reviewer's or
  verifier's for theirs), `main_checkout`, `queue_root` and `project_id`; `ccp docs check` and every
  command refuse another name. §13 says how the values reach the worker.

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
holds bindings (§29). Contract: `contracts/project.schema.json`; required: `project_id`, `integration_branch`, `queue_root`, `product_root`. Optional: `ci` and `notes`. Nothing else is read: the runner's agent (`ccp:delivery-runner`), name (`runner`) and worktree (`<product_root>/.plane-runtime/runner`, the prefix with several runners, §16) are derived, and its rotation (after 4 tasks, §10.2) and idle limit are constants.

```yaml
project_id: example-product
integration_branch: main
product_root: /path/to/example-product   # the product's main checkout
queue_root: /path/to/.delivery-queue/example-product
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
  one that names another product root. A kept binding is checked against the current shape: init warns,
  naming each missing key (the schema's required keys) and each obsolete one (a key the schema marks deprecated, a key it does not list).
- A binding whose `product_root` is the plane's own repository is the plane managing itself; its
  usage counts as non-product use (§24).
- A binding key not listed above is a removed key (§29.3): it loads with a warning naming it and is otherwise ignored. The lead is every project's spec maintainer (§17), and the operator's channel is plane.json `notify` (§3.6).

**The machine file**, `machine.json` beside the bindings (`contracts/machine.schema.json`), holds what belongs to the machine's account, not to a product: `telemetry` (the operator's consent, §4.5), `allowance_cmd` and `allowance_stop_weekly` (§25). Beside it, the shared allowance reader keeps one cache file per allowance command (`allowance-cache-<hash>.json`) and its lock (§25.1); they are state, not configuration, and may be deleted.

### 8.4 Configuration knobs

- The `--note` length limit on `ccp` commands that take one (4000 characters).
- How long the usage records (`usage.jsonl`) are kept (default: everything; they hold no content).

## 9. The plugin and orientation

### 9.1 The plugin

`plugin/` in this repository, with `.claude-plugin/marketplace.json` at the root naming it.

| Part | Notes |
|---|---|
| `agents/delivery-{runner,implementer,reviewer,verifier}.md` | named `ccp:delivery-runner` and so on; the runner's agent (`ccp:delivery-runner`) and `ccp`'s run binding use the scoped names |
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
the product root (the main checkout, from any worktree), the binding file's path, the queue, the plane
checkout and the `ccp` path, each path as its real path, as `ccp init` prints them, and the idle hook's
limit (`idle_limit`, §18.2).

### 9.3 Orientation

- The plugin's SessionStart hook injects the role-neutral orientation into the lead's and any
  interactive session in a managed product, kept under the hook's 10,000-character cap.
  SessionStart context does not reach subagents or teammates; workers are oriented by their
  definitions and prompts.
- After the orientation, the hook and `ccp orientation` list the product's pending notices (`ccp notify pending`, §3.6): each one's subject, reason and the call that records it sent, within the hook's cap.
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
- `ccp orientation` prints the text that hook gives a session in this product (the orientation, or the
  plane's one line), from `ccp`'s own plugin, and writes nothing. It is for a session that started
  before the product was adopted: its SessionStart ran before `plane.json` existed.

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
