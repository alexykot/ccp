# `ccp` command reference

Call syntax and flags, moved out of the SPEC (ADR-0033 D3). What each command must do is a SPEC
rule; this reference only says how to call it. `ccp <command> -h` is the source of truth for flags, and a
test holds these files to the parser: every command and long flag it defines is written here, and no other.

| Part | File |
|---|---|
| Model | [`cli/01-model.md`](cli/01-model.md) |
| Delivery | [`cli/02-delivery.md`](cli/02-delivery.md) |
| Quality | [`cli/03-quality.md`](cli/03-quality.md) |
| Observability and spend | [`cli/04-observability.md`](cli/04-observability.md) |
| Operations | [`cli/05-operations.md`](cli/05-operations.md) |
