# `ccp` commands: 04-observability

Call syntax and flags for the commands of SPEC part `docs/spec/04-observability.md`. The rules each
command follows are in the SPEC, not here.

| Command | What it does |
|---|---|
| `ccp board build [--quiet]` | Fold the sources into the board and the day's snapshot (the rebuild timer, the lead; §28) |
| `ccp board status` | Terminal summary (any seat; §23.4) |
| `ccp board task <id\|NNNN>` | One task's drill-down (any seat) |
| `ccp board install\|uninstall\|timer` | The per-project rebuild timer (the operator) |
| `ccp otel serve [--port N]` | The telemetry receiver (the machine's service manager; §24.2) |
| `ccp otel env [--project ID]` | Print the user-settings block (the operator; §24.1) |
| `ccp otel install\|uninstall\|status` | The receiver's service; `status` reports the counts and checks the user settings (the operator) |
| `ccp usage [--task ID] [--since DATE] [--json]` | Per-run and per-seat tokens and cost (the lead; §24.4, §24.6) |
| `ccp usage --system [--since DATE] [--json]` | The system sink by cwd and day (the lead; §24.3) |
| `ccp usage --by-model [--seat SEAT] [--json]` | One seat's tasks compared by model (the lead; §2.4; default `implementer`) |
| `ccp allowance status [--sample]` | The allowance state (any seat; §25.3) |
| `ccp allowance continue --to <percent> --reason "<the operator's words>"` | Record the operator's decision past the checkpoint (the lead) |
| `ccp allowance session-wake [--sample] [--armed] [--fire]` | The session wake (the lead; §25.4) |
| `ccp tasks estimate ID [--baseline] [--force] [--dry-run] [--json] [--print-prompt ID]` | Estimate one task (the lead; §26.3) |
| `ccp tasks estimate --all [--baseline] [--max N] [--detach]` | Estimate every task that needs it (the lead) |
| `ccp tasks estimate show ID` | A task's estimates, latest of each source (any seat) |
| `ccp estimate backfill [--dry-run] [--json]` | Baselines and actuals for merged tasks (the lead; §26.3) |
| `ccp estimate accuracy [--json]` | The accuracy panel (any seat) |
| `ccp estimate calibration [--json]` | The calibration factors (any seat; §26.6) |
| `ccp forecast [--point R<n> \| --backlog] [--json]` | The completion forecast (the lead; §26.4, §26.5) |
| `ccp health [--since DATE] [--json]` | Measurements and suite series since the adoption point, or `--since`, and the usage cost advice (the lead; §27.1, §27.2, §14.6, §24.6) |
| `ccp health record --task <id> --metric <name>=<n>` | Record a product metric (the runner; §27.1) |
| `ccp health note --text TEXT` | Record a friction note (the runner; §19.6) |

Scripts kept as wrappers over `ccp`: `scripts/observability/emit-event.sh`, `heartbeat.sh`,
`write-prompt-audit.sh`, `prune-prompts.sh`. `scripts/observability/set-waiting-on.sh` is waiting_on's
single writer, which `ccp tasks wait|resume` call (§10.1). `status.sh` and `rebuild-now.sh` are
retired: the status is `ccp board status` (§23.4).
