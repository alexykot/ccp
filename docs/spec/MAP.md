# The SPEC's layout

ADR-0033 sets the layout. The SPEC is five parts in this directory, numbered by topic and
continuously across parts (§1–§31, subsections §N.M). `SPEC.md` at the repo root is a short
index. Implementation notes, spikes and acceptance walk-throughs go to
`docs/design/`; the command reference goes to `docs/cli/` (index `docs/cli.md`); history and
incident narratives are dropped.

## Outline

| Part | File | Sections |
|---|---|---|
| Part I Model | [`01-model.md`](01-model.md) | §1 Purpose and principles · §2 Seats · §3 The operator and operator gates · §4 Product footprint · §5 Task files · §6 ADRs · §7 Ids and references · §8 Configuration · §9 The plugin and orientation |
| Part II Delivery | [`02-delivery.md`](02-delivery.md) | §10 Task lifecycle · §11 Runs and process locks · §12 Worktrees and environments · §13 Workers and prompts · §14 Test runs · §15 Review, verification and merge · §16 Parallel runners · §17 Spec questions, escalation and gate decisions · §18 Liveness, operating window and quota |
| Part III Quality | [`03-quality.md`](03-quality.md) | §19 The architect seat · §20 House rules, budgets and refactors · §21 Doc checks · §22 Review points and the plan |
| Part IV Observability and spend | [`04-observability.md`](04-observability.md) | §23 Ledger, snapshot and queue data · §24 Usage and telemetry · §25 Allowance and usage windows · §26 Estimation and forecast · §27 Health measurements · §28 The board |
| Part V Operations | [`05-operations.md`](05-operations.md) | §29 Releases and the run checkout · §30 Security: keys and wallets · §31 Governance: SPEC changes, ADRs and tool proposals |
