---
id: ADR-0046
title: "Decisions may depend on other ADRs' decisions"
status: proposed
date: "2026-11-20"
deciders: operator
spec_refs: [S6, S10, S22]
notes: |-
  Proposed from a product's plane proposal: a decision sometimes presupposes a decision in another
  ADR, and nothing records it or orders the work by it. It changes the ADR format and SPEC rules
  (listed under Consequences), so the operator decides it.
---
# ADR-0046 — Decisions may depend on other ADRs' decisions

## Context

A decision often only makes sense once another one is in force. ADRs already say so, but only in
prose:

- ADR-0043 D5 requires a gate lane because "its catch-up with the integration tip before review"
  is ADR-0042 D3 (`docs/adr/0043-opinionated-defaults-short-configuration.md:119-121`).
- ADR-0042 D4 keeps "the verdict ... at the head that merges (ADR-0012 D3)"
  (`docs/adr/0042-tasks-run-together-unless-they-clash.md:115`).

The format has no field for this. An ADR's links (§6.5, `docs/spec/01-model.md:632-640`;
`LINK_KEYS` in `ccp/adr.py:46`) are `supersedes`, `superseded_by` and `amends`: all three replace or
change a decision, and none says that one decision rests on another. So:

- Nothing stops a task building a decision before the decision it rests on is built. `ccp tasks
  next` orders by `depends_on` between tasks only (§10.3, `docs/spec/02-delivery.md:94-101`), and
  the plan (§22.9, `docs/spec/03-quality.md:760`) shares that selection.
- When a prerequisite is superseded, nothing tells the ADRs that rest on it.

## Options considered

1. **Leave it to task `depends_on` and the architect's shape.** No format change. The dependency
   then lives only in the tasks of one tasking round, and nothing finds it when the prerequisite is
   superseded. Rejected.
2. **A `Requires:` line in each decision's body.** It reads well next to the decision. But every
   other link is in the frontmatter, where `ccp adr` reads and rewrites it, and a body line adds a
   second place to parse. Rejected.
3. **A frontmatter `requires` key, in the shape of the existing links.** One list, read and checked
   like `amends`, with `ccp adr supersede` able to follow it. Chosen.

## Decision

### D1. `requires` names a decision's prerequisites

An ADR's frontmatter may carry `requires`: a list of `"<Dn> <ADR id> <Dm>"` entries, each saying that
this ADR's decision Dn rests on decision Dm of that ADR. `"<Dn> <Dm>"` names a decision of the same
ADR. For example, `requires: ["D5 ADR-0042 D3"]`. Only decisions are named: a whole ADR is never a
prerequisite.

### D2. `ccp adr check` checks the links

- **Failures:** an entry whose own decision or target decision does not exist; a target in a
  `rejected` or `withdrawn` ADR; a cycle, across ADRs included.
- **Warnings, failures under `adr.strict`:** a target recorded `retired` (D4).
- `ccp adr status N accepted` refuses while a target's ADR is still `proposed`, naming it: the
  prerequisite is accepted first.

### D3. Tasking waits for a prerequisite to be built

A task cites a decision in `adr_refs` (`NNNN Dn`; a whole-ADR citation cites each of its decisions).

- `ccp tasks next` passes over a task whose cited decision has a prerequisite that is neither
  recorded `built` or `live` nor cited by the same task. stderr names the prerequisite, the same way
  `next` reports a due sign-off (§10.3). The board's next pick follows, since the plan shares the
  selection (§22.9).
- `ccp tasks check` reports a pending task held this way when no pending task cites the prerequisite,
  since nothing would ever release it. That is a failure under `adr.strict` and a warning otherwise.

### D4. A superseded prerequisite moves to its replacement

When `ccp adr supersede OLD NEW --decisions Dm --by Dk` retires a prerequisite, it rewrites each
`requires` entry that names `OLD Dm` to name `NEW Dk`. It edits only that key and adds a dated note,
as the commands already do for `superseded_by`, and prints each ADR it changed. A prerequisite
retired with no replacement decision (no `--by`, a whole-ADR supersede, or a retirement) stays
named. D2 then flags it, and the dependent decision goes to the operator: amend, supersede or retire
it.

## Consequences

- A decision's prerequisites are recorded where the tools read them. The order of building follows
  them without the task writer restating them as `depends_on`.
- A retired prerequisite either moves to its replacement, or puts the decision that rests on it in
  front of the operator. It is never silently lost.
- `ccp adr supersede` gains a write to other ADRs' frontmatter, limited to `requires`.
- Existing ADRs carry no `requires`, and their behaviour is unchanged. Adding entries for past prose
  dependencies is optional.
- No runtime spend: everything runs in the existing checks.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §6.2: the `requires` key, and `contracts/adr.schema.json`.
  - §6.5: `requires` as a link that is not a replacement.
  - §6.6: `status` accepted refuses a proposed prerequisite; `supersede` rewrites `requires`.
  - §6.7: the new failures and warnings.
  - §10.3: `next` passes over a task held by an unbuilt prerequisite.
  - The `ccp tasks check` report of a held task that nothing releases.

## Notes

- The architect's shape pass and the writing-tasks skill read `requires` when they order a plan's
  tasks. That is guidance, not a check.
- The board's dependency graph (§22.9) could draw these links. This ADR does not ask for it.
