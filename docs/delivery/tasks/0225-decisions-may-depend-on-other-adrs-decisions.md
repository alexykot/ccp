---
task_id: 0225-decisions-may-depend-on-other-adrs-decisions
title: An ADR names the decisions each of its decisions rests on, and accepting it waits for theirs
status: done
kind: feature
depends_on: ["0239-one-adr-reference-parser-and-a-decision-index"]
spec_refs: ["S6"]
adr_refs: ["0046 D1", "0046 D2"]
review_point: R15
paths: ["ccp/adr.py", "contracts/adr.schema.json", "docs/spec/01-model.md", "docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md", "tests/test_adr_requires.py"]
adopt: "none"
sign_off: brief
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0225-decisions-may-depend-on-other-adrs-decisions

## Intent

A decision often makes sense only once another is in force, and ADRs say so only in prose. After
this task an ADR's frontmatter names each decision's prerequisites (`requires`), the schema and the
reader accept it as a link that replaces nothing, and accepting an ADR waits while another ADR it
requires is still `proposed`. The checks that hold those links (0251) and the task-log report (0252)
build on it.

## Context (not checked)

Measured at `8aefa59`.

- Builds ADR-0046 D1 and D2's accept refusal, accepted by the operator on 2026-11-20. D2's failures and
  D4 are 0251, D3 is 0252.
- **Shaped** by `sh-20261121T001225Z-7dbe`; its refactors are 0239 (one ADR-reference parser and the
  decision index) and 0250 (the graph helpers).
  - F02: `requires` targets are parsed by 0239's `refs.Ids.adr_link`, after splitting off the leading
    `Dn`.
  - F09: the accept refusal reads only targets in another ADR; a decision requiring one of its own
    ADR's decisions never blocks the ADR's own acceptance. The PROPOSED §6.4 text says "another ADR".
- **The links today.** `ccp/adr.py` `LINK_KEYS = ("supersedes", "superseded_by", "amends")`
  (`git grep -n '^LINK_KEYS' -- ccp/adr.py` at `8aefa59`: one line). `contracts/adr.schema.json` has
  no `requires` (`grep -c '"requires"' contracts/adr.schema.json` at `8aefa59`: 0), and no ADR carries
  one (`grep -rl '^requires:' docs/adr | wc -l` at `8aefa59`: 0), so nothing about existing ADRs
  changes.

## Scope

- **In:** `ccp/adr.py`, `contracts/adr.schema.json`, `docs/spec/01-model.md`,
  `docs/adr/0046-decisions-may-depend-on-other-adrs-decisions.md`, `tests/test_adr_requires.py` (new).
- **The key (D1).** `requires`: a list of `"<Dn> <ADR id> <Dm>"`, or `"<Dn> <Dm>"` for the same ADR.
  The schema gains it; `adr.py` reads it into the decision index (0239) as a link that needs no
  reverse entry.
- **The accept refusal (D2).** `ccp adr status N accepted` refuses (exit 2, nothing written) while a
  target in another ADR is in a `proposed` ADR, naming it.
- ADR-0046 D1 recorded `built`.
- **Tests** in `tests/test_adr_requires.py` (new), on a temp product with ADRs: both forms read; the
  accept refusal naming the target; an ADR requiring its own decision accepted.

### SPEC changes (signed in the brief, §31)

**a. §6.2, the frontmatter table.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> | `supersedes`, `superseded_by`, `amends` | optional | links, each a list of `<ADR id>` or `<ADR id> Dn` |

PROPOSED: (new lines after it)
> | `requires` | optional | prerequisites, each `"<Dn> <ADR id> <Dm>"` (this ADR's Dn rests on that ADR's Dm) or `"<Dn> <Dm>"` within the ADR; only decisions are named (§6.5) |

**b. §6.4, accepting an ADR.**

CURRENT (`docs/spec/01-model.md` at `8aefa59`):
> - Accepting an ADR records every body decision not yet recorded as `not_built`; retiring it retires
>   every decision.

PROPOSED:
> - Accepting an ADR records every body decision not yet recorded as `not_built`; retiring it retires
>   every decision. Accepting refuses while another ADR its `requires` names is still `proposed`,
>   naming it: the prerequisite is accepted first.

- **Out:** `ccp adr check`'s failures and warnings, and the `retired by` resolution (0251); the
  task-log report (0252); adding `requires` to existing ADRs.

## dod_checks

- id: `rq-01`
  story: As an ADR writer, I name a decision's prerequisites, and acceptance waits for them.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_adr_requires 2>&1 | tail -10`.
  expect: exit 0, with the Scope's tests listed `ok`.
  dry run: n/a — the module is new.

- id: `rq-02`
  story: As a plane developer, the accept refusal bites, and only across ADRs.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which the
    refusal also reads targets in the same ADR.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_adr_requires`.
  expect: at least one failure (the ADR requiring its own decision).
  dry run: n/a — the module is new.

- id: `rq-03`
  story: As a product with ADRs and no `requires`, nothing changes.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_adr tests.test_adr_decisions tests.test_tasklog_adr_unbuilt 2>&1 | tail -3`.
    2. Run `bin/ccp --root . adr check; echo rc=$?`.
  expect: step 1 exits 0 with `OK`; step 2 prints `rc=0`.
  dry run (`8aefa59`): step 1 `OK`; step 2 `rc=0`.

- id: `rq-04`
  story: As the operator, the signed SPEC text is what landed.
  setup: a checkout of the PR head, with QUEUE_ROOT a temp queue.
  steps:
    1. Run `bin/ccp --root . verify spec-text 0225 --base origin/main`.
  expect: exit 0, every passage found.
  dry run (`8aefa59`): exit 1, the passages not found.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `adr.parse_requires(s, adr, ids)` reads one entry: the leading `Dn` is split off and each part goes
  through `refs.Ids.adr_link` (F02); the own decision and a same-ADR target are read as
  `adr_link("<this ADR's id> Dn")`, so no new reference regex. An entry of neither form, or one naming a
  whole ADR, gives None and is left out of the index (0251's check reports it).
- `DecisionIndex.build` reads each ADR's `requires`: `required(adr)` gives the ADR's entries in file
  order as (own decision, (ADR, decision)), `requires(adr, d)` one decision's prerequisites. `requires`
  is in `OPTIONAL` (no undeclared-key warning) and not in `LINK_KEYS`, so it needs no reverse entry and
  no `<ADR id>[ Dn]` reading; it is not in `LIST_KEYS` either, so a scalar reads as one entry and no new
  check failure is added (the check is 0251's).
- `ccp adr status N accepted` (any move to `accepted`, after the transition check) refuses with exit 2,
  nothing written, while a target in another ADR is in a `proposed` ADR, naming each such entry and the
  target's file. A target in the ADR itself, by either form, never holds it (F09); a target naming no ADR
  does not either (the check's to report).
- Schema: `requires`, an array of `$defs/requirement` (`D<n>[ <ADR id>] D<m>`).
- ADR-0046 D1 recorded `built`. D2 is recorded `built` too, with a note that only the accept refusal is
  built: the task cites `0046 D2` and this repo runs `adr.strict`, so `ccp verify record` refuses an
  approve while it is `not_built`, and a done task citing it would fail `ccp adr check` on main
  (flagged to the runner; 0251 records it built again when the check's part lands).
- Fix round 1 (review MINOR 1): `test_other_moves_and_settled_prerequisites_do_not_wait` also gives
  the accepted ADR a target in a `withdrawn` ADR, so only a `proposed` target holds acceptance is pinned
  (a refusal on any target that is not `accepted` now fails it). The NIT (a pure helper split) is left,
  as the runner asked.

## Verification notes
- 2026-11-21 — verifier, PR #272 head `80bfd5b` (squash `4c7b5e7`): APPROVE. Passed: rq-01, rq-02, rq-03, rq-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0225-decisions-may-depend-on-other-adrs-decisions.json.

