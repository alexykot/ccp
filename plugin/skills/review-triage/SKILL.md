---
name: review-triage
description: The control plane's review triage protocol (SPEC §19, §19.8): how the task-log owner triages an architect or review report into tasks, house-rule changes, waivers and questions for the operator. Use it when asked to triage an architect report or a review in a control-plane project.
---
<!--
  Control-plane review triage protocol (SPEC §19; architect §19.8). Installed in every product repo
  at docs/delivery/REVIEW-TRIAGE.md by scripts/sync-product-docs.sh (SPEC §9.5). Read by the
  owner of the task log, the team lead (the spec maintainer). Sync drops this comment.
  Source: control-plane plugin/skills/review-triage/SKILL.md.
-->
# Review triage

You own this project's task log as its team lead (the spec maintainer). An
isolated reviewer has checked the project and you have been given its report. Your prompt names
its kind:

- an **architect pass** (`ar-…`, SPEC §19, `ccp architect`): the project's structural health
  through four lenses (structure, docs, tests, process), with proposed changes to the house rules
  (`rule_changes`);
- an **architect shape** (`sh-…`, SPEC §19.5): advice on an accepted ADR before it is tasked
  (see *After a shape*, below).

Bundle findings by area: code, test and doc findings alike go into one task per area, never one
task per finding (see *Bundling by area*, below). Re-read this file every time you triage; it is
the whole of your standing instructions for triage, and you may be a brand-new session.

The reviewer found and proved problems. You decide what happens to each one. Nothing the
reviewer says is a decision.

## Your authority for triage

For triage only, SPEC §19 extends the spec maintainer's authority (§17.4). You may:

- **create new task files** under `docs/delivery/tasks/`, and add them to
  `docs/delivery/INDEX.yaml` the way this project does it: by hand, or with its generator if the
  file says it is generated. Follow `docs/delivery/WRITING-tasks.md`. A new task gets the next
  free `NNNN`, its own `depends_on` and `dod_checks`, and `status: pending`;
- rule on the spec exactly as you do for a spec question: edit `docs/PROJECT.md` within your
  §17 limits, and `docs/SPEC.md` (or `spec/`);
- write the review record `docs/delivery/reviews/<review_id>.md`;
- apply the architect's rule changes you accept to the house rules (`architect.rules_doc` in
  `docs/delivery/plane.json`), within its line cap, each rule with its id and its `check:`, and add
  any `architect.checks` or `architect.budgets` entry an applied rule needs;
- add a known-intentional note to the *Known intentional* section of the house rules (or, without
  them, to `docs/delivery/LOCAL.md`), so later passes stop raising it;
- record a deferral in the project's planning document (its plan or backlog file), naming the
  review and the finding.

You must not:

- edit existing tasks' ids, `depends_on` or `dod_checks`, source code or tests, runtime queue
  files other than your triage file, or control-plane config;
- create a task that changes what the product is for, or that contradicts a decision the project
  owner stated. Those go to the owner (`needs_operator`, below);
- apply a rule change that changes the product's architecture or contradicts a decision the
  project owner recorded: that is `needs_operator` too.

## How to triage

1. **Read** the report (the path is in your prompt), the house rules if the product has them,
   `docs/delivery/LOCAL.md`, earlier reviews in `docs/delivery/reviews/`, and the open tasks.
2. **Check each finding's evidence yourself.** Re-run its commands or open its paths. If it
   doesn't reproduce, reject it and say so. The reviewer is not trusted by default.
3. **Check it against the design record.** If it's intentional, reject it with the reason and
   add a known-intentional note (to the house rules, or to `LOCAL.md` without them). A `rule-cost`
   finding is never rejected as intentional: it goes to the owner. If it's already covered by a
   task or an earlier disposition, mark it `duplicate`.
4. **Give each finding one disposition:**

| Disposition | When | What you do |
| --- | --- | --- |
| `task` | Real, and fixable within the current spec and design | Put it in the new task for its area (*Bundling by area*, below). Separate anything that changes stored data or a contract into its own task, with a migration or rehearsal step in its `dod_checks`. A clean-up that changes no behaviour is a **refactor task** (`kind: refactor`, citing `review_refs: ["<review_id>#F01"]` or `rule_refs`, never `spec_refs`/`adr_refs`; SPEC §20) |
| `spec` | The fix is a spec ruling or wording change | Rule and commit it, as for a spec question |
| `defer` | Real, but it belongs to planned future work | Record it in the planning document with a pointer to this review, and give the path |
| `needs_operator` | The fix is a product or design decision the owner reserves, or it contradicts something the owner decided. **Always** for a `rule-cost` finding: a rule applied past its purpose is the owner's call, never rejected as intentional without their word | Write one exact question with the options and your recommendation. Group all such findings into one question if you can |
| `duplicate` | Already covered | Name the task or earlier finding |
| `reject` | Doesn't reproduce, is intentional, or isn't worth the change | Give the reason |

A finding that asks for a **tool** is a `task` here, in this product, unless any product would need
it whatever its language, domain or conventions (SPEC §31.4). Lints over this product's own
conventions, tools over its data or domain and provers for its language are product tasks, wired in
through `docs.checks`, an env hook, `architect.checks` or `reconcile.hooks`. Only a need that passes
that test goes to the plane, as `ccp plane propose --need "…" --generic "<why any product needs it>"`.

5. **Respect the cap.** Create at most `max_new_tasks` new tasks (default 5; the number is in
   your prompt). Beyond that, defer, and say so.
6. **Rule changes (architect reports).** Apply each `rule_changes` entry to the house rules, or
   reject it with a reason. A change that alters the product's architecture, or contradicts a
   decision the project owner recorded, is `needs_operator`: put it in your question. Keep the rules
   doc under its line cap; a rule with no check you can name is not added.
7. **Write the review record** `docs/delivery/reviews/<review_id>.md` (for a shape, see below). It is the durable memory
   that stops the next review from repeating this one. It holds:
   - a header with the review id, date, the `head` and `base` commits, and the reviewer's
     summary;
   - one table: finding id | title | category | severity | disposition | target (task id,
     commit, plan path or reason);
   - the evidence of each finding you accepted, copied from the report, so the record stands
     without the runtime file.
8. **Commit** only the files you changed, by explicit path (`git commit -- <paths>`), on the
   integration branch in this directory. Use the message
   `review(<review_id>): triage — <n> tasks, <n> rulings, <n> deferred, <n> rejected`, then
   push. If you can't commit or push, set every finding you had made a `task` or `spec` to
   `needs_operator` and say why.
9. **Write the triage file** (the path is in your prompt), then print the same JSON as your final
   message:

```json
{
  "schema_version": 1,
  "review_id": "<from report>",
  "project_id": "<from report>",
  "triaged_at": "<UTC RFC3339>",
  "commit_sha": "<sha of your triage commit, null if nothing was committed, or pending>",
  "pending_change": "<required when commit_sha is pending: the rule change still to land>",
  "record": "docs/delivery/reviews/<review_id>.md",
  "tasks_created": ["<task_id>"],
  "dispositions": [
    {"finding": "F01", "disposition": "task | spec | defer | needs_operator | duplicate | reject",
     "target": "<task id | commit sha | plan path | earlier finding or task | null>",
     "reason": "<one sentence>"}
  ],
  "rule_changes": [
    {"rule": "E8", "action": "add | amend | delete", "disposition": "applied | rejected | needs_operator",
     "reason": "<one sentence>"}
  ],
  "question_for_operator": "<one exact question with options and your recommendation, or null>",
  "answered_by": "spec_maintainer | steerer",
  "session_id": "<this session id if known, else null>"
}
```

`rule_changes` has one entry per change the architect proposed (leave it out for other kinds).
The plane refuses a triage of an architect report where a `rule-cost` finding is not
`needs_operator`, a proposed rule change has no entry, or a change is `applied` with neither a
commit sha nor `commit_sha: pending` plus `pending_change`. `pending` lets triage finalise
before that commit is on the integration branch. When the commit lands, record it with
`ccp architect triage --backfill <review_id> <sha>`. `ccp architect status` lists any backfill
still unfinished.
No secrets, keys or `.env` contents anywhere.

## Bundling by area

Every task pays a fixed cost (claim, worker start-up, review, verify, merge, reconcile), so pay it
once per area, not once per finding:

- Put the findings you make `task`, and any follow-ups or leftovers of earlier tasks in the same
  area, into **one task per area** (a package, a command, a doc set), aiming at a few hundred
  changed lines. `ccp health` shows the share of merged tasks under `health.small_task_lines`.
- The task declares the **union of the findings' paths** in `paths` and carries **one `dod_check`
  per finding**. An area with more findings than `max_checks` (default 6) fills a second task.
- **Every finding is still fixed**: bundling changes how many tasks there are, never what is done.
- A finding that changes stored data or a contract keeps its own task, as the `task` row says.

## After a shape (`sh-…`)

A shape advises how to task an accepted ADR. You still give each finding a disposition, then:

- write the shaping record `docs/delivery/reviews/<review_id>.md` with a line `ADR: ADR-NNNN`
  naming the ADR it shaped: `ccp tasks check` looks for that line before it accepts new tasks
  citing the ADR (when `architect.shape_adrs` is on);
- adjust the ADR's task graph (its tasks' `depends_on` and order) as far as the advice holds;
- create at most **3 preparatory refactor tasks** (`kind: refactor`, citing the shape's findings in
  `review_refs`), and make the ADR's first feature tasks depend on them.

A task citing an ADR that needs no shaping carries `shaping: waived — <reason>` in its frontmatter
instead.

## What you never do

- Change runtime task state, `waiting_on` or events. The Task Runner registers your new tasks in
  the runtime queue, as it does for any new durable task.
- Send the operator anything but a plane-rendered notice over the configured channel, or send one
  without recording it (`ccp notify sent`, SPEC §3.6): of the seats, only the lead sends. Your
  `question_for_operator` you ask the operator in your own session when `ccp architect triage`
  prints `lead_asks_operator` (SPEC §19.8).
- Implement any fix yourself.
