---
id: ADR-0046
title: "Decisions may depend on other ADRs' decisions"
status: accepted
date: "2026-11-20"
deciders: operator
spec_refs: [S6, S10, S21, S22]
notes: |-
  Proposed from a product's plane proposal: a decision sometimes presupposes a decision in another
  ADR, and nothing records it or orders the work by it. It changes the ADR format and SPEC rules
  (listed under Consequences), so the operator decides it.
  2026-11-20: status proposed → accepted: Operator: "accept 0044, 0045, 0046" (2026-11-20)
decisions:
  - "D1 built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
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
`LINK_KEYS` in `ccp/adr.py:46`) are `supersedes`, `superseded_by` and `amends`. All three replace
or change a decision; none says that one decision rests on another. So:

- Nothing stops a task building a decision before the one it rests on is built. `ccp tasks next`
  orders by `depends_on` between tasks; no ADR link is read (§10.3,
  `docs/spec/02-delivery.md:94-101`). The plan (§22.9, `docs/spec/03-quality.md:760`) shares that
  selection.
- When a prerequisite is superseded, nothing points the ADRs that rest on it at the replacement.

## Options considered

1. **Leave it to task `depends_on` and the architect's shape.** No format change. The dependency
   then lives only in the tasks of one tasking round, and nothing finds it when the prerequisite is
   superseded. Rejected.
2. **A `Requires:` line in each decision's body.** It reads well next to the decision. But every
   other link is in the frontmatter, where `ccp adr` reads it, and a body line adds a second place to
   parse. Rejected.
3. **A frontmatter `requires` key, checked by `ccp tasks next`, which holds a task until its
   prerequisite is built.** That orders the work automatically, but it adds a runtime hold that
   `depends_on` already expresses, and it can stall silently. Rejected in favour of option 4.
4. **A frontmatter `requires` key, checked when the tasks are written.** `ccp tasks check` reports a
   task that could be built before its prerequisite, and the writer adds the `depends_on`. Ordering
   stays in one place. Chosen.

## Decision

### D1. `requires` names a decision's prerequisites

An ADR's frontmatter may carry `requires`: a list of `"<Dn> <ADR id> <Dm>"` entries, each saying that
this ADR's decision Dn rests on decision Dm of that ADR. `"<Dn> <Dm>"` names a decision of the same
ADR. For example, `requires: ["D5 ADR-0042 D3"]`. Only decisions are named: a whole ADR is never a
prerequisite.

### D2. `ccp adr check` checks the links

- **Failures:** an entry whose own decision or target decision does not exist; a target in a
  `rejected` or `withdrawn` ADR; a cycle, across ADRs included.
- **Warnings, failures under `adr.strict`:** a target whose replacement chain (D4) ends in a retired
  decision with no replacement.
- `ccp adr status N accepted` refuses while a target's ADR is still `proposed`, naming it: the
  prerequisite is accepted first.

### D3. `ccp tasks check` reports a task that can run before its prerequisite

A task cites a decision in `adr_refs` (`NNNN Dn`; a whole-ADR citation cites each of its decisions).
`ccp tasks check` reports a pending task that cites a decision when any of that decision's
prerequisites (resolved as D4 says) is:

- not recorded `built` or `live`; and
- not cited by the task itself, or by any task in its `depends_on` closure.

It names the prerequisite and both remedies: add a `depends_on` on a task that builds it, or, when
no task cites the prerequisite, write one or record it built with `ccp adr decide`. The report is a failure under
`adr.strict` and a warning otherwise. `ccp tasks next` does not change.

### D4. A superseded prerequisite resolves through `retired by`

No command rewrites another ADR's `requires`. A prerequisite recorded `retired by <ADR id> Dk`
(§6.3) resolves to Dk, following the chain while each link is retired by another decision. D3 checks
the decision at the end of the chain. When the chain ends in a decision retired with no replacement,
D2 warns, and the decision that rests on it goes to the operator to amend, supersede or retire.

## Consequences

- A decision's prerequisites are recorded where the tools read them. The task log cannot be written
  so that a decision is built before the decision it rests on, without the check saying so.
- A retired prerequisite either resolves to its replacement or puts the decision that rests on it
  in front of the operator. It is never silently lost.
- Existing ADRs carry no `requires`, and nothing about them changes. Adding entries for past prose
  dependencies is optional.
- No runtime spend: everything runs in the existing checks.
- **SPEC rules that change**, each through a task that carries its exact text for the operator's
  signature (§31):
  - §6.2: the `requires` key, and `contracts/adr.schema.json`.
  - §6.5: `requires` as a link that replaces nothing, and its resolution through `retired by`.
  - §6.6: accepting an ADR refuses a proposed prerequisite.
  - §6.7: the new failures and warnings.
  - §21.1: `ccp tasks check`'s report of a task that can run before its prerequisite.

## Notes

- **Limit: a decision built by several tasks.** The first of those tasks flips the decision to
  `built` in its own PR (§6.7's in-force check), before the others merge. From then on D3 treats the
  prerequisite as built, and a dependent task can run before the rest of it lands. The writer
  catches that with an explicit `depends_on`.
- The architect's shape pass and the writing-tasks skill read `requires` when they order a plan's
  tasks.
- The board's dependency graph (§22.9) could draw these links. This ADR does not ask for it.
