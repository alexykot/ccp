---
id: ADR-0042
title: "Tasks run together unless they clash"
status: proposed
date: "2026-11-18"
deciders: operator
spec_refs: [S5, S10, S13, S15, S16, S19, S27]
notes: |-
  Proposed from three accepted plane proposals by a product's lead (a fourth was merged into one of
  them): schedule by logical clash rather than shared files, make conflicts cheap by catching up
  before review, and write wide plans rather than deep chains. It changes SPEC rules (listed under
  Consequences), so the operator decides it. Tasks follow the architect's shape.
---
# ADR-0042 — Tasks run together unless they clash

## Context

ADR-0012 lets several runners work at once and keeps correctness off declared paths: a task merges
only from a head that contains the integration tip, verified there. Its D5 lets declared paths and a
short exclusive list decide which tasks start together. Claim rule 3 (SPEC §16.3) refuses a task
whose paths meet an in-flight task's paths, unless `parallel.shared` covers both.

That rule serialises far more than it needs to:

- **Hub files.** Every codebase has files that many tasks touch without sharing any logic: the SPEC,
  a runbook, a CLI entry point and its docs, a registry, and the file map in each source directory's
  package doc (§21.3). Two unrelated tasks that both add a line to such a file cannot run together.
  `parallel.shared` lifts this for files tasks only append to, but each such file must be listed by
  hand.
- **Measured cost.** In this plane's own review point R10, from task 0158 on, every remaining task
  ran alone. Each met the next on the SPEC file and the CLI docs; some also shared real code.
- **Conflicts are rare and found late.** Few tasks need a merge round. When one does, the conflict is
  found at verify or close, after a full review, and costs another full review and verify (§15.6
  rule 3).
- **Deep plans.** Feature work is often written as a chain where each task depends on the one before.
  Wall time is then bounded by the chain's length, and no number of runners shortens it.

Human teams change the same files in parallel and resolve textual conflicts when they merge. The
only reason to keep two pieces of work apart is a logical clash: one builds on what the other will
change, or both change the same logic in different ways. Only the task's writer can judge that.

## Decision

### D1. A logical clash decides co-scheduling, not shared files

Two tasks run in sequence only when one depends on the other (`depends_on`, as today) or they clash:
both change the same logic in different ways. The task-log owner records a clash at task-writing
time as `clashes_with: [<ids>]` in the task's frontmatter. The relation is symmetric: either order,
never together. `ccp tasks check` refuses an id that names no task.

The plane-level knob `parallel.schedule` picks the claim rule: `paths` (today's rule 3, the default)
or `clashes`. Under `clashes`, rule 3 refuses a claim only when the task clashes with an in-flight
task; shared files no longer refuse it. A product opts in. The default changes only by a later
decision, once D5's measurement shows the trade pays.

The other claim rules stay:

- `parallel: false` still runs alone, and `parallel.exclusive` still keeps apart files git cannot
  merge safely, such as a schema or a migration.
- Rule 2 stays: a task with no paths and no `parallel: true` still runs alone, because its paths are
  what `exclusive` and the forecast read.
- `parallel.shared` keeps its meaning at close (D4): close resolves an append-only conflict in a
  shared path itself.

### D2. Paths stay as information

A task still declares `paths`. They feed the reviewer, `parallel.exclusive`, the forecast and its
`undeclared_paths` check (§16.7), and close's catch-up condition (§16.5 rule 4). Under `clashes` they
no longer decide rule 3.

`ccp tasks next` walks the ready tasks as today. Under `clashes` it passes over a task held back only
by a clash with an in-flight task. It also passes over a task that clashes with one it passed over,
so a later task never overtakes an earlier one it clashes with.

### D3. The implementer catches up before review

The implementer's last step before submitting for review is to bring its branch up to the
integration tip by a merge (§15.6 rule 2: never a rebase), resolve any conflicts, rerun the gate
lane, and then open or update the PR. The implement prompt and the implementer's brief say so.

`ccp prompt review` refuses a head behind the tip, beyond `merge.behind_tip_ignore`, only when
merging the tip into it would conflict (checked with `git merge-tree`, which writes nothing). A head
behind by a clean merge goes to review, and the later catch-up handles it. This keeps a moving tip
from sending the implementer back again and again.

### D4. A catch-up is checked by its resolution

When the tip moves after review, the catch-up is a merge of the tip into the task branch.

- **A clean merge whose own patch is unchanged** (same patch id) is re-verified as §15.6 rule 3 says
  today: the gate lane runs at the new head and the dod_checks rest on the earlier approve. Under
  `clashes`, close may make this catch-up itself, even when the tip changed a file the task changes.
  Today close refuses that case (§16.5 rule 4). Close still resolves an append-only conflict in a
  `parallel.shared` path itself.
- **A merge with a conflict** is resolved by the implementer. It then gets a resolution review, a new
  review mode, instead of a full round:
  - The reviewer reads only the resolution: `git show --remerge-diff` of the merge commit, which shows
    how the committed result differs from git's own merge, conflict hunks only.
  - The reviewer names which dod_checks the resolution can affect. The verifier reruns those and the
    gate lane at the new head; every other check rests on the earlier approve.
  - A resolution that changes the task's own logic beyond the conflict hunks falls back to a full
    round, as today. The reviewer judges that and says why.
- The verdict is still given at the head that merges (ADR-0012 D3). `ccp verify record` and the
  review gate (§15.2) accept a resolution review as the review of that head.

### D5. Measure conflicts

`ccp health` reports conflict catch-ups for each product: how many, their wall time and tokens, and
whether they came before or after review. This shows whether running overlapping tasks together
costs less than waiting. It is the evidence for changing D1's default.

### D6. Plans are wide, not deep

The writing-tasks skill, the architect's shape pass and review triage give the same guidance:

- Sequence two tasks only for a dependency or a clash, never because they touch the same files.
- For a feature, prefer one thin first task that fixes the interfaces (types, table shapes,
  signatures, the CLI surface with stubs), then tasks that build on it in parallel, over a chain.
- Prefer smaller tasks where each piece still works on its own. There is no hard size cap: some
  changes are coherent only as one piece.

`ccp tasks check` reports, for the pending scope, the longest `depends_on` chain and the graph's
width at each depth. It warns when the chain is long relative to the width.

## Consequences

- Unrelated tasks run together, so wall time falls for products with more than one runner.
- More textual conflicts happen. Most are resolved before review (D3), at the cost of one merge and
  one gate run for each task that meets one.
- **A conflicted merge after review is checked less than today.** Today it gets a full review and
  every dod_check. Under D4 it gets a review of the conflict hunks, the checks the reviewer names, and
  the gate lane. The fallback to a full round, at the reviewer's judgement, is the safeguard.
- A semantic clash that git merges cleanly is caught only by the gate lane, as today. Under `clashes`
  such merges become more common, including merges over files both tasks changed.
- A clash the writer missed costs a conflict resolution, not a wrong merge: the head that merges
  still contains the tip and is verified there.
- The task-log owner takes on one more judgement per task (D1) and the shape of the plan (D6).
- Partly supersedes ADR-0012 D5 ("Paths decide co-scheduling") for products that opt in.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §5: the `clashes_with` field.
  - §10.3 and §16.3: claim rule 3 and the `next` walk.
  - §13.2: the implement prompt's catch-up and the resolution review mode.
  - §15.2: review's refusal of a head behind the tip, and a resolution review as a head's review.
  - §15.6 rule 3: the conflicted merge.
  - §16.2: the `parallel.schedule` knob.
  - §16.5 rule 4: close's catch-up over overlapping files.
  - §16.7: the forecast models clashes.
  - §27: health reports conflict catch-ups.
  - The `ccp tasks check` chain and width warning.
- Rules out: scheduling by an automatic analysis of the code. The clash is the writer's call.
