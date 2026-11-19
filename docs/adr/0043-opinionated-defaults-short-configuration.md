---
id: ADR-0043
title: "Opinionated defaults, short configuration"
status: proposed
date: "2026-11-19"
deciders: operator
spec_refs: [S2, S4, S8, S10, S14, S16, S18, S19, S20, S21, S23, S24, S25, S26, S27]
notes: |-
  Proposed from the operator's configuration principles (2026-11-19, in the lead session), quoted in
  Context, and an audit of every per-product setting. It changes stated defaults in many SPEC
  passages and partly supersedes ADR-0042 D1 and ADR-0012 D5, so the operator decides it. Tasks
  follow the architect's shape.
---
# ADR-0043 — Opinionated defaults, short configuration

## Context

The operator set these principles for a product's configuration (2026-11-19):

> - The standard configuration should not make assumptions about what the project exactly is or how
>   it should be configured, but it should provide enough of these sane defaults that it can run well
>   without changes.
> - There should be sensible, high-performance settings by default. Parallel execution enabled, path
>   conflicts disabled.
> - Opinionated model settings should be defined for every role by default.
> - It should not make assumptions on the language. If the language setting is required for
>   operation, then it should be left empty, and it should refuse to start without it.
> - Telemetry should be on and fully working by default.
> - Architect should be on and working by default.
> - Values that are unlikely to need to be changed shouldn't really be in configuration at all.

An audit of the configuration against them found:

- **Size.** A product has 194 settings: 147 accepted in `plane.json` and 47 in the local binding, of
  which code reads about 18.
- **Dead keys.** `telemetry.otel_port` and `task_log.statuses` in `plane.json`, and most of the
  binding, are read by nothing.
- **Duplicates.** Several keys exist twice or have legacy aliases. Every default is restated in the
  schema, the SPEC and the README.
- **Account facts per product.** The usage allowance and session-window knobs describe the Claude
  account on the machine, not the product. Two products can disagree about the same account.
- **A language assumption.** `package_docs.language` defaults to Python, and the test-output parsers
  read only Python's unittest.
- **Required but defaulted.** A gate lane is needed to operate, yet it defaults to none.
- **Off by default.** Parallel work is off, scheduling is by shared paths, and the architect is off
  unless a product adds its block. Telemetry needs steps `ccp init` does not take.
- **Models.** They are set per seat in the agent definitions. Only the implementer's is configurable.

## Decision

### D1. Defaults run well with no changes

Every setting has a default that works for any product, or is required (D4). A setting exists only
when a reasonable product would change it. Anything else is a constant in code, or is removed (D8).
Each default is defined once in code: the schema is held to it by a test (house rule E12), and the
SPEC states the behaviour, not the number.

### D2. Parallel by default

`parallel.max_in_flight` defaults to 3 and `parallel.schedule` to `clashes`. This replaces ADR-0042
D1's clause that the default changes only after D5's measurement: the operator decided it here. It
retires what remained of ADR-0012 D5. `parallel: false`, `parallel.exclusive` and `clashes_with`
still keep tasks apart.

### D3. A default model for every role

| Role | Model |
|---|---|
| Lead | Opus (`ccp init` writes it into the product's settings) |
| Runner | Sonnet |
| Implementer, and its fix, merge and ruling rounds | Opus, and Sonnet for a small task or a refactor (`workers.implementer_model` defaults to that) |
| Reviewer | Opus |
| Verifier | Sonnet |
| Architect | Opus |
| Estimator | Sonnet |

The reviewer moves from Sonnet to Opus: the reviewer is where defects are caught before verify, and
one run per round is a small cost. The SPEC's seat table names every role, the estimator included.
`workers.implementer_model` stays configurable. The other roles' models are per role, not per
product.

### D4. No language default

`package_docs.language` has no default, and `none` is a valid answer. A product's gate lane in
`suite.lanes` is required as well. Until both are set, `ccp` refuses every delivery command (exit 2)
and names the missing key. `ccp init` asks for both.

Parsing test output (the test count, failures and skips) belongs to the language pack. For a product
with language `none`, the product's patterns apply, or nothing is counted.

### D5. Telemetry on and working by default

- `ccp init` writes the product's telemetry tag (`OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=<id>`)
  into the product's settings.
- It checks the receiver and the user-level keys. With the operator's consent, given once per
  machine, it writes the user-level keys and installs the receiver and the board timer.
- A directory may still turn telemetry off in its own settings, and the SPEC says so.
- `telemetry.otel_port` is removed: the receiver owns its port.

Two limits are accepted:

- The receiver cannot be started from inside Claude Code. When it is down, `ccp init` prints the
  command to run in a normal terminal.
- Only macOS has a service definition.

### D6. Architect on by default

- **On without a block:** the architect runs with its defaults when `plane.json` has no `architect`
  block. Only `"architect": false` turns it off.
- **Cadence from adoption:** the cadence counts from the product's adoption, or from the release
  that turned the architect on, never from its first task. An upgraded product therefore does not
  owe a pass at once.
- **Init writes the rules:** `ccp init` writes the starter house rules, and `rules_doc` defaults to
  them.
- **Shaping on, from now on:** shaping before tasking is on. Its cutoff, and the cutoff for the
  task-kind and refactor-reference checks, is the next task number at adoption, so finished tasks
  are not judged by rules that did not exist when they were written.
- **The pass needs a logged-in Claude Code:** it runs headless and needs Claude Code logged in on
  the machine. A machine without it records a failed pass and does not block delivery.

### D7. Account facts move to the machine

The allowance command and the weekly stop, which defaults to 90%, move from each product's
`plane.json` to one installation config per machine. The session park, wake and ceiling knobs become
constants there. The provider's session window is optional, and the rules already pass when an
account has none.

### D8. A short configuration

- **Dead keys are removed:** `telemetry.otel_port`, `task_log.statuses`, and the binding keys no
  code reads.
- **Duplicates merge into one key:**
  - the two spec-path lists;
  - the two review-point patterns;
  - the legacy `adapter.*` aliases into `worktrees.*` and `reconcile.hooks`;
  - the binding's docs path into `task_log.dir`;
  - the two runner-context limits.
- **Tuning constants become code:** among them the architect cadence numbers, the health and usage
  thresholds, the timeouts and the id formats.
- **The binding keeps only where things are:** `project_id`, `integration_branch`, `product_root`,
  `queue_root`, `ci` and `notes`.
- **Three behaviours are fixed:**
  - `adr.strict` on;
  - a fix round with only minor findings skips the second review (`skip_review_after_clean` on);
  - `task_log.dry_run` at today's behaviour.

Each removed key keeps working for one release. `ccp` warns and ignores it, and the release's upgrade
notice tells each product what to delete. The target is about 78 settings: about 70 in `plane.json`,
6 in the binding and 2 per machine.

## Consequences

- A new product runs parallel, with the architect and telemetry on and every role on a set model,
  once its language and gate lane are named.
- **Spend rises.** More tasks run at once, the reviewer runs on Opus, and the architect and the
  estimator run for every product. The session ceiling and the weekly stop are what bound it.
- **Products with history feel the change at their next release:**
  - Parallel and clash scheduling apply unless the product sets them back.
  - The architect starts counting from that release.
  - A product with no language set must set one before delivery continues. The upgrade notice says so
    as a required step.
- The SPEC states behaviour rather than numbers, so defaults have fewer copies to keep in sync.
- Telemetry stays machine-wide by the operator's consent. A directory that must not be measured
  turns it off locally.
- **Partly supersedes:**
  - ADR-0042 D1: the default schedule.
  - ADR-0012 D1: off by default.
  - ADR-0012 D5: paths decide co-scheduling.
- Rules out per-product model choice for any role other than the implementer.
