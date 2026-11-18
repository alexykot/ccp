---
id: ADR-0042
title: "Tasks run together unless they clash"
status: proposed
date: "2026-11-18"
deciders: operator
spec_refs: [S5, S10, S15, S16, S19, S24]
notes: |-
  Proposed from three accepted plane proposals by a product's lead (a fourth was merged into one of
  them): schedule by logical clash rather than shared files, make conflicts cheap by catching up
  before review, and write wide plans rather than deep chains. It changes SPEC §16.3 claim rule 3,
  §15.6 rule 3 and §16.5 rule 4, so the operator decides it. Tasks follow the architect's shape.
---
# ADR-0042 — Tasks run together unless they clash

## Context

ADR-0012 lets several runners work at once and keeps correctness off declared paths: a task merges
only from a head that contains the integration tip, verified there. Its D5 left one use for paths:
deciding which tasks start together. Claim rule 3 (SPEC §16.3) refuses a task whose paths meet an
in-flight task's paths.

That rule serialises far more than it needs to:

- **Hub files.** Every codebase has files that most tasks touch without sharing any logic: the SPEC,
  a runbook, a CLI entry point, a registry, and the file map the plane's own package-doc convention
  (§21.3) puts in every directory's `.claude.md`. Two unrelated tasks that both add a line to such a
  file cannot run together. `parallel.shared` patches this for append-only files, one entry at a
  time.
- **Measured cost.** With two runners and a ceiling of four, products have spent most of a day with
  exactly one task in flight. In this plane's own review point R10, from task 0158 on, every
  remaining task ran alone. Most of the overlaps were on the SPEC file, not on shared logic.
- **Conflicts are rare and found late.** Few tasks ever needed a merge round. When one does, it is
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
time as `clashes_with: [<ids>]`. The relation is symmetric: either order, never together. A task
with neither relation to an in-flight task may be claimed beside it, whatever files the two touch.

The plane-level knob `parallel.schedule` picks the rule: `paths` (today's claim rule 3, the default)
or `clashes`. A product opts in. The default changes only by a later decision, once D5's measurement
shows the trade pays.

`parallel: false` and `parallel.exclusive` stay: some files git cannot merge safely, such as a schema
or a migration. Under `clashes`, `parallel.shared` has no effect.

### D2. Paths stay as information

A task still declares `paths`. They feed the reviewer, the declared-paths rules of review and verify
(ADR-0035), conflict forecasting, and `parallel.exclusive`. Under `clashes` they no longer gate a
claim. `ccp tasks next` skips a task held back only by a clash or a dependency on an in-flight task,
the way it now skips one held back only by rule 3.

### D3. The implementer catches up before review

The implementer's last step before submitting for review is to bring its branch up to the
integration tip:

1. fetch;
2. rebase onto the tip, or merge where a rebase is impractical;
3. resolve any conflicts;
4. rerun the gate lane;
5. open or update the PR.

The implement prompt and the implementer's brief say so. `ccp prompt review` refuses a head behind the
tip beyond `merge.behind_tip_ignore`, as `ccp prompt verify` already does.

### D4. A catch-up after review is checked by its resolution

When the tip moves during review or verify and the catch-up conflicts, the conflict is resolved and
the gate lane runs at the new head. Review and verify then look at the resolution only: the new
head's diff against the reviewed head and the tip. They rerun only the `dod_checks` whose paths the
resolution touched. A resolution that changes the task's own logic beyond the conflict hunks falls
back to a full round, as today. The reviewer of the resolution judges that and says why.

The verdict is still given at the head that merges (ADR-0012 D3).

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
- More textual conflicts happen. Most are resolved before review (D3), at the cost of one rebase
  and one gate run for each task.
- A conflict after review costs a resolution check, not a full round (D4). It still runs the gate at
  the merging head, so a semantic clash that git merges cleanly is caught the same way as today.
- A clash the writer missed costs a conflict resolution, not correctness: ADR-0012 D3 still holds.
- The task-log owner takes on one more judgement per task (D1) and the shape of the plan (D6).
- Under `clashes`, `parallel.shared` is retired. It stays under `paths`.
- Partly supersedes ADR-0012 D5 ("Paths decide co-scheduling") for products that opt in. The SPEC
  rules that change are §16.3 claim rule 3 and `ccp tasks next`, §15.6 rule 3 and §16.5 rule 4. A
  task that changes them carries their exact text for the operator's signature (§31).
- Rules out: scheduling by an automatic analysis of the code. The clash is the writer's call.
