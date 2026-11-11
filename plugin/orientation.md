<!--
  Control-plane orientation (SPEC §9). Role-neutral. The control-plane plugin's SessionStart
  hook gives it to every session in a managed product; a product still on managed copies imports
  its copy (docs/delivery/CONTROL-PLANE.md) from CLAUDE.md. Keep it to about one screen, and well
  under the hook's 10,000-character cap. No role-specific permissions here: those live in role docs.
-->
# CCP — Claude Control Plane

This repo is delivered by **CCP** (Claude Control Plane): seats that steer, run and check the work,
with Claude Code implementing it. The operator, the human, is asked only for product decisions,
SSO/payments, and blockers that nobody else can resolve. The seats are a **Claude agent team**
whose lead is the design seat (plane SPEC §2).

## Seats

| Seat | Who |
| --- | --- |
| Design seat / spec maintainer: rules spec questions, owns the task log | **The team lead**: the session the operator works in. Also decides the runner's gates and is the only route to the operator |
| Task Runner: claims tasks, launches the implementer, reviewer and verifier, merges, reconciles | A **teammate** of the lead (agent type `delivery-runner`); its workers are its own subagents |
| Task Verifier: judges each task against its `dod_checks` | The runner's fresh subagent (agent type `delivery-verifier`), given a fixed packet |
| Liveness, quota waits, wakes | No watchdog: the lead sees idle and failure notices; a `TeammateIdle` hook keeps the runner going |
| Architect (SPEC §19) | A fresh read-only `claude -p` that `ccp` makes due and `ccp tasks next` enforces; the task-log owner triages its report |

## Where truth lives

- Product intent: docs/PROJECT.md and docs/SPEC.md.
- The durable task log: docs/delivery/ (one file per task under docs/delivery/tasks/, never deleted).
- Runtime state (leases, sessions, questions, gates, events): the queue folder outside this repo.
  A Claude session never edits it by hand unless its role doc says so.
- Rulings and durable facts live in git, never only in a session's memory.
- Package docs and code comments follow the plane's package-doc convention (plane SPEC §21.3);
  `ccp docs check` holds them to it.

## How questions flow

- Implementation questions (how to build it) go to the Task Runner.
- Spec questions (what the product should do; a task against the spec; the spec against the
  project) go to the spec maintainer.
- Only the spec maintainer may escalate to the operator.
- To raise a question, message the lead. The plane names when the operator is
  notified (a blocker, a decision, a finished review point, the allowance
  checkpoint) and the product names the channel: on those, `ccp` also runs the
  product's notify command if it names one (plane SPEC §3.6).

## Tools

- Every step that changes delivery state is a `ccp` command (plane SPEC §10), and `ccp` records
  it. Seats do not edit queue files, write worker prompts or copy reports by hand.
- Tests run through `ccp suite run [--lane L] -- <command>`: the exit code passes through, the
  output goes to a log file and a summary is printed (the failing tests' sections on a failure;
  `--full` streams it all), and `ccp` records the time and the counts (SPEC §14.1).
- Every seat and subagent runs long commands in the foreground: an agent waiting on a
  background command stalls.
- After a command that was interrupted (a timeout, a cancelled call, a lost shell), check git, the
  store it writes (the queue's records, the product's data) and the ledger
  (`observability/events.jsonl` in the queue) before reporting that it did nothing: it may have done
  part or all of its work.
- **No seat writes its own script, helper or wrapper for a plane step**: not in the queue, not in this
  repo, not anywhere (SPEC §31.4). A missing tool is either the plane's or this product's:
  - **the plane's** only if any product would need it, whatever its language, domain or conventions:
    propose it with `ccp plane propose --need "…" --generic "<why any product needs it>"`;
  - **this product's** otherwise (a lint over its own conventions, a tool over its data, stores or
    domain, a prover for its language): the lead writes it as a product task, built in this repo and
    wired in through `docs.checks`, an env hook, `architect.checks` or `reconcile.hooks`.

  A worker names the need in its report's Friction section and says which it is; the runner proposes
  plane needs and passes product needs to the lead.

## Your role

Role docs come from the ccp plugin: agents `ccp:delivery-*`, skills
`ccp:spec-maintainer`, `ccp:review-triage`, `ccp:architect` and
`ccp:writing-tasks`. A product still on managed copies has them in .claude/agents/,
.claude/skills/ and docs/delivery/ instead.

- Launched as the **implementer**: your task prompt and docs/delivery/standing-dod.md govern you
  and your agent definition (the reviewer and verifier have theirs).
- Working as the **team lead** (the spec maintainer): the spec-maintainer protocol governs you.
  When asked to triage an architect report or a review, the review-triage protocol governs that
  triage. Writing or amending a task: writing-tasks.
  To direct the runner's next tasks, the lead runs `ccp tasks prefer <id> [<id>…] --reason "…"`, never a
  "take X next" message, which races the claim: `ccp tasks next` returns the first ready one, and its
  claim removes only that one (SPEC §10.4). A new list replaces the old; `--clear` empties it.
  **Changes from outside the plane** (another agent, the operator, a tool) reach the integration
  branch through a task you write (SPEC §10.7). `ccp tasks orphans --since <ref>` lists the
  commits that merged without one: for each, write an after-the-fact task naming it in `covers:`,
  so review and verify cover it.
  **A claimed task's file is edited only in its PR** (SPEC §10.5): send a ruling or amendment on a
  task the runner holds to the runner, never commit it to the integration branch. Marking it
  `dropped` is the one exception. `ccp tasks check --lease` names such an edit; the plane's commit
  hook template refuses one.
  **The 5-hour session wake** (SPEC §25.4): at the limit your own turn fails too, so arm the wake
  early. On every runner message, and on any 5-hour warning, run `ccp allowance session-wake --sample`.
  When it prints `arm: true`, call CronCreate with its `cron`, `recurring: false` and its `prompt`,
  then run `ccp allowance session-wake --armed`. When the wake fires, run
  `ccp allowance session-wake --fire` and do what it prints.
- Spawned as the **runner teammate**: your agent definition governs you.
- Launched as the **architect**: the `architect` skill governs you, and you are read-only.
- Whatever your role, read the house rules when docs/delivery/plane.json names them
  (`architect.rules_doc`): they are this product's engineering standards.
- In an **interactive session with the operator** outside the team: you have no delivery role unless they
  give you one.

Authority granted in a role doc applies only to that role. For example, only the spec
maintainer may commit spec changes as a ruling; an implementer, a runner or an interactive session
may not. The team lead never runs tasks; the runner never rules or talks product with the operator.

If docs/delivery/LOCAL.md exists, it holds this project's own additions; read it too. It is
owned by this repo. This orientation is not: it is CCP's, and `ccp` is its tool.
