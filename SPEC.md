# CCP — Claude Control Plane: SPEC

The normative specification of CCP: what a managed product, its seats and the `ccp` tool must and
must not do. It states rules only. The SPEC is five parts in `docs/spec/`, numbered by
topic and continuously across parts (§1–§31, subsections §N.M); a reference to "SPEC §N" anywhere in
the repository names one of these sections.

| Part | File | Sections |
|---|---|---|
| I Model | [`docs/spec/01-model.md`](docs/spec/01-model.md) | §1 Purpose and principles · §2 Seats · §3 The operator and operator gates · §4 Product footprint · §5 Task files · §6 ADRs · §7 Ids and references · §8 Configuration · §9 The plugin and orientation |
| II Delivery | [`docs/spec/02-delivery.md`](docs/spec/02-delivery.md) | §10 Task lifecycle · §11 Runs and process locks · §12 Worktrees and environments · §13 Workers and prompts · §14 Test runs · §15 Review, verification and merge · §16 Parallel runners · §17 Spec questions, escalation and gate decisions · §18 Liveness, operating window and quota |
| III Quality | [`docs/spec/03-quality.md`](docs/spec/03-quality.md) | §19 The architect seat · §20 House rules, budgets and refactors · §21 Doc checks · §22 Review points and the plan |
| IV Observability and spend | [`docs/spec/04-observability.md`](docs/spec/04-observability.md) | §23 Ledger, snapshot and queue data · §24 Usage and telemetry · §25 Allowance and usage windows · §26 Estimation and forecast · §27 Health measurements · §28 The board |
| V Operations | [`docs/spec/05-operations.md`](docs/spec/05-operations.md) | §29 Releases and the run checkout · §30 Security: keys and wallets · §31 Governance: SPEC changes, ADRs and tool proposals |

Alongside the parts:

- **Design notes** (non-normative: implementation notes, spikes, rationale): [`docs/design/`](docs/design/).
- **Command reference** (call syntax and flags): [`docs/cli.md`](docs/cli.md) and `docs/cli/`.
- **Decisions behind the rules**: the ADRs in [`docs/adr/`](docs/adr/).
- **The restructure**: the layout is ADR-0033; [`docs/spec/MAP.md`](docs/spec/MAP.md) maps every
  pre-restructure section to its new place, and [`docs/spec/RULINGS.md`](docs/spec/RULINGS.md) lists the
  rules the operator ruled on during it (ADR-0034).

A change to a § rule needs the operator's approval (§31.1).
