---
task_id: 0205-threat-model
title: A threat model for the plane, and roadmap notes for a batching merge queue and seat isolation
status: done
kind: feature
depends_on: []
spec_refs: ["S2", "S15", "S23", "S30"]
review_point: R14
paths: ["docs/design/threat-model.md", "docs/ROADMAP.md", "README.md"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-21
---

# Task: 0205-threat-model

## Intent

Today an adopter cannot tell what the plane protects and what it leaves to Claude Code. Every seat
runs as the operator's OS user, with the operator's credentials. Some controls are real boundaries;
others only stop accidents. After this task, a non-normative threat model names the assets, the
trust boundaries, the threats and, for each control, whether it is a boundary or a guard. It also
lists the risks a single-operator install accepts and the controls a shared install would need. The
roadmap gains two later items, a batching merge queue and OS-level seat isolation, each with the
trigger that would make it worth building.

## Context (not checked)

- Three plane proposals were accepted at triage: the threat model as a document, and two notes for
  later, a batching merge queue and OS-level seat isolation. Any rule the threat model implies goes
  through §31 later, not here.
- What the proposal listed, to be checked against the code before it is written down:
  - **Assets:** the forge token with repo write; SSH keys; model credentials; product repos and
    integration branches; queue and verdict records; other products on the same host; the
    operator's files.
  - **Threats and controls:**
    - T1, prompt injection through text an agent reads (issue and PR text, dependency docs, test
      output, fetched pages), acted on with the operator's rights;
    - T2, the gate runs untrusted code on the host;
    - T3, destructive or escaping commands: the deny list is prefix-matched, and `README.md`'s
      Permissions section names its gaps;
    - T4, forged or tampered evidence: separation of duties is enforced by schemas and refusals, but
      every seat can write the queue as the same user;
    - T5, exfiltration over an unrestricted network;
    - T6, one product's agents reaching another product's repo and queue;
    - T7, telemetry leakage: controlled by the numbers-and-ids whitelist;
    - T8, credentials in headless children: controlled, the API keys are stripped;
    - T9, unreviewed reach to production: controlled, promotion is an operator gate.
- Where the controls live (`git grep -n` at `58cf1d0`): the key strip `STRIP_KEYS` in
  `scripts/observability/spec_maintainer.py`; the architect's denied tools `DENY_TOOLS` in
  `scripts/observability/architecture_review.py`; the deny list `ccp init --permissions` prints, in
  `ccp/init.py`; the telemetry receiver's field whitelist, `REQUEST_FIELDS` and `SPAN_FIELDS` in
  `ccp/otel.py`; promotion as an operator gate in SPEC §3.4.
- `README.md`'s "What will work in the future" says "No threat model is written yet"
  (`grep -n 'No threat model' README.md` at `58cf1d0`: one line).
- `docs/ROADMAP.md`'s "After the reshape" has a **Merge handling** item, which the merge-queue note
  joins. Seat isolation is a new item.
- No SPEC change: the document is non-normative (`docs/design/README.md`: "A note here never
  overrides the SPEC").

## Scope

- **In:** `docs/design/threat-model.md` (new), `docs/ROADMAP.md`, `README.md`.
- **`docs/design/threat-model.md` (new)**, non-normative, under these headings in this order:
  `# Threat model`, `## Scope and assumptions` (one operator, Anthropic models, current scale, every
  seat as the operator's user), `## Assets`, `## Trust boundaries`, `## Threats and controls`,
  `## Accepted risks`, `## What a shared install needs`.
  - Under **Threats and controls**, one `### T<n> <name>` subsection for each of T1 to T9. Each
    names its controls, and each control is on a line starting `- **Boundary:**` or `- **Guard:**`,
    with the file or SPEC section that implements it. A threat with no control has a line
    `- **Gap:** <what is missing>`.
  - Every control named is checked against the code at the commit the PR is based on. A control
    the proposal named that the code does not have is written as a gap.
  - **Accepted risks** lists each gap a single-operator install accepts, and why, in one line each.
  - **What a shared install needs** lists, at least: per-product scoped forge tokens, sandboxed
    command execution, a network allowlist, and queue write protection. Each is one line, pointing
    to the roadmap item.
  - The document names no managed product, path on any machine, or person (house rule E3).
  - A file it names in backticks is a path from the repository root (`ccp/otel.py`, not `otel.py`).
- **`docs/ROADMAP.md`:**
  - under **Merge handling**, a sub-bullet "**Later: a batching merge queue.**" Today each PR merges
    alone, pinned to its verified head, and every merge sends the other runners to catch up and
    re-run the gate. A queue would run the gate once per batch on the merged stack and bisect
    failures. It needs its own strategy, and a rule for what a verdict binds to when the landed
    commit is a batch: §15.5 stops close when the host accepts a merge without merging. Trigger:
    merge catch-ups, not the number of runners, become the throughput limit;
  - a new item "**Seat isolation (later).**" Options by cost: Claude Code's command sandbox,
    per-product scoped forge tokens, a container per worker, a separate OS user or VM per product.
    In-process teammates share the lead's process, so isolation per seat beyond the command sandbox
    means headless worker processes. Trigger: other models behind the harness, many more runners,
    or several operators' products on one host. It follows the threat model.
- **`README.md`:** the "A threat model and isolation" bullet links `docs/design/threat-model.md` and
  says isolation is on the roadmap. It no longer says no threat model is written.
- **Out:** any SPEC rule, any code, and any new control.

## dod_checks

- id: `tm-01`
  story: As an adopter, I find the threat model with every threat and its controls labelled.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -c '^### T[1-9] ' docs/design/threat-model.md`.
    2. Run `grep -n '^## ' docs/design/threat-model.md`.
    3. Run `grep -cE '^- \*\*(Boundary|Guard|Gap):\*\*' docs/design/threat-model.md`.
  expect: step 1 prints 9. Step 2 lists the six `##` headings of the Scope, in order. Step 3 prints at
    least 9.
  dry run (`58cf1d0`): the file does not exist.

- id: `tm-02`
  story: As a reviewer, every file the threat model cites exists.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -c "import re,os; [print('missing', f) for f in sorted(set(re.findall(r'\x60([A-Za-z0-9_./-]+[.](?:py|sh|json|md))\x60', open('docs/design/threat-model.md').read()))) if not os.path.exists(f)]"`.
  expect: prints nothing.
  dry run (`58cf1d0`): the file does not exist; the same command on `docs/ROADMAP.md` reads 14
    names and prints two that are not root paths, so it does find a missing file.

- id: `tm-03`
  story: As the operator, the roadmap holds both later items and the README points at the model.
  setup: a checkout of the PR head.
  steps:
    1. Run `grep -n 'batching merge queue\|Seat isolation' docs/ROADMAP.md`.
    2. Run `grep -n 'threat-model.md' README.md; grep -c 'No threat model' README.md`.
  expect: step 1 shows both items, the merge queue under Merge handling. Step 2 shows the link and
    then 0.
  dry run (`58cf1d0`): step 1 prints nothing; step 2 prints only `1`.

- id: `tm-04`
  story: As the plane, the change is docs only and names no product.
  setup: a checkout of the PR head.
  steps:
    1. Run `git diff --stat origin/main...HEAD -- . ':!docs/design' ':!docs/ROADMAP.md' ':!README.md' ':!docs/delivery'`.
    2. Run `scripts/leak-check.sh`.
  expect: step 1 prints nothing; step 2 exits 0.
  dry run: n/a.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `docs/design/threat-model.md` (new): the seven headings of the Scope, T1 to T9 each with its
  controls labelled Boundary, Guard or Gap. A boundary is defined there as a control enforced outside
  the seat's session that no tool the seat holds turns off; a guard as one a seat with the operator's
  rights can get past. Every control was checked against the code at 361fc1a.
- Proposal items written as gaps, because the code does not have them: T6 (nothing confines a seat to
  its own product), T9 beyond the rule (nothing stops a seat holding deploy credentials; the plane has no
  deploy step), and for T8 the lead, teammates and subagents, which the plane does not launch and whose
  environment it does not strip (only the architect and the estimator are stripped, via `STRIP_KEYS`).
- Controls found beyond the proposal's list: the estimator's no-tools launch (`ccp/estimator.py`, a
  boundary for T1), the merge pinned with `--match-head-commit` (`ccp/lifecycle.py`, a boundary for T4),
  provers run from the integration tip's checkout (SPEC §14.2, a guard for T4), and the
  `ccp otel status` warning on `OTEL_LOG_USER_PROMPTS` / `OTEL_LOG_TOOL_DETAILS` (a guard for T7).
- The architect's read-only tool set is labelled a guard, not a boundary: its allowed `Bash` commands
  and the product's probes are prefix-matched.
- `docs/ROADMAP.md`: the batching merge queue under Merge handling; Seat isolation as a new item after
  it. `README.md`: the threat-model bullet links the note and the roadmap. Its separate "A batching
  merge queue" bullet is unchanged (out of the Scope).
- Fix round 1 (review of 27f508b):
  - T4's merge pin is now a guard, not a boundary: only the merge `ccp tasks close` runs carries
    `--match-head-commit`, and the permission block allows `gh pr` and `git push`, so a seat can
    merge without the pin or push to the integration branch. The note says so; the label count
    is unchanged.
  - T4's accepted risk drops the claim that a forged record shows as a disagreement with the forge's
    merge history (a forged approve followed by a merge leaves all three in agreement); the reason
    kept is that every seat acts for the one operator, and it now also covers unpinned merges.
  - T4's gap cites E7 for what it says (every queue write goes through `ccp`) and SPEC §23.2 for the
    append-only ledger.
  - T1: a change passes the verifier, and the reviewer unless SPEC §15.2 skips its review, instead
    of "two seats".
  - Queue write protection says it would come from the hosted backend behind the `Store` interface,
    which the ROADMAP's Store item does not plan yet; the ROADMAP is unchanged.
- Fix round 2 (review of 5061a70), wording only:
  - T4: the integration-branch read covers provers and `verify.skip_review` only; the gate lane,
    its scripts and the tests come from the head under test, so the note no longer says a task's
    diff cannot change its own verdict.
  - T3 and T9: the merge guards name the runner's merge through `ccp tasks close` and point to T4
    for the `gh pr` and `git push` way round it, instead of reading as unconditional.
  - T6: the permission block also allows bare `ccp`, so a `ccp --root` naming another product
    passes; the note says so.

## Verification notes
- 2026-11-21 — verifier, PR #242 head `60ea499` (close's catch-up of the approved `d6bc604`, gate run st-20261121T030553Z-e8e6a4) (squash `543a21f`): APPROVE. Passed: tm-01, tm-02, tm-03, tm-04, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0205-threat-model.json.

