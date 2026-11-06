---
id: ADR-0035
title: "Tool-proposal triage rulings (2026-11-06)"
status: accepted
date: "2026-11-06"
deciders: operator
spec_refs: [S5, S15, S19, S20, S31]
decisions:
  - "D1 not_built"
  - "D2 not_built"
  - "D3 not_built"
  - "D4 not_built"
  - "D5 live"
  - "D6 live"
  - "D7 live"
  - "D8 built"
notes: "2026-11-06: status proposed → accepted"
---
# ADR-0035 — Tool-proposal triage rulings (2026-11-06)

## Context

A managed product's seats had filed a batch of tool proposals. Triage sorted them against the plane
as it stands after the reshape. Some needs were generic and became plane tasks. Some were already
built. Some were the product's own business: lints over its conventions, tools over its data and a
prover for its language. Several needed the operator's ruling because they change a rule. The volume
of product-specific proposals also showed that seats had no test for what belongs to the plane, so
they filed whatever `cpl` lacked.

## Decision

### D1. Declared paths do not make a head behind the tip

A product setting lists paths whose commits on the integration branch do not count as "behind the
tip" when a task closes. It is empty by default. A merge that only adds such commits keeps the
verified head valid.

### D2. Verify refuses a head that lacks the tip

`cpl prompt verify` refuses a head that does not contain the integration tip, beyond the paths of
D1. Merging the tip in first is cheap, and a stale head wastes a whole verify round.

### D3. Drift is measured on active time

The architect's drift trigger compares active time: wall time minus waits and exclusive-lane waits.
A task waiting on the operator or on a lane does not count as slower work.

### D4. Declared paths may skip re-review, with a product proof

A generic setting lists paths a fix round may touch without a fresh review, for example comments or
docstrings in tests. A product-supplied proof hook shows that the diff touches nothing else. The
prover is product tooling, not part of the plane.

### D5. The owner may amend a task file at any time

A task file is not locked while it is leased. The task-log owner may amend it at any time, as §5
states.

### D6. A dry run may be "n/a" with a reason

A dod_check's dry-run line may read `dry run: n/a — <reason>`. Nothing refuses it.

### D7. No "closed by ruling" verification outcome

A check closed by the owner's ruling is recorded with `ran: false` and `rests_on` naming the ruling.
The verification record gains no new outcome.

### D8. A tool proposal must pass the plane-or-product test

A need is the plane's only if any product would need it, whatever its language, domain or
conventions. `cpl plane propose` requires `--generic` saying why. Everything else is product work:
built in the product's repo, wired in through `docs.checks`, an env hook, `architect.checks` or
`reconcile.hooks`, and written as a product task by the product's lead (§31.4).

## Consequences

- D1–D4 need code. They are plane tasks 0021, 0022 and 0023.
- D5–D7 restate rules already in force.
- D8 should stop product-specific proposals reaching the plane. When it is unclear whether a need
  is generic, the seat states why it thinks so, and triage still decides.
