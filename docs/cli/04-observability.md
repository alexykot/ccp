# `ccp` commands: 04-observability

Call syntax and flags for the commands of SPEC part `docs/spec/04-observability.md`. The rules each
command follows are in the SPEC, not here.

| Command | What it does |
|---|---|
| `ccp board build [--quiet]` | Fold the sources into `board/board.json`, the page and the day's snapshot (§28) |
| `ccp board status` | Terminal summary (§23.4) |
| `ccp board task <id\|NNNN>` | One task's drill-down in the terminal |
| `ccp board install\|uninstall\|timer` | The per-project rebuild timer |
| `ccp otel serve [--port N]` | The telemetry receiver (§24.2) |
| `ccp otel env [--project ID]` | Print the user-settings block, and with `--project` the product's block (§24.1) |
| `ccp otel install\|uninstall\|status` | The receiver's service; `status` reports rows written, routed, pending and refused, and checks the user settings |
| `ccp usage [--task ID] [--since DATE] [--json]` | Per-run and per-seat tokens, cost, models and coverage (§24.4), and the cost advice past plane.json `usage.advice` (§24.6), from `--since` or the last `usage.advice.window_hours` (the lead) |
| `ccp usage --system [--since DATE] [--json]` | The system sink by cwd and day |
| `ccp usage --by-model [--seat SEAT] [--json]` | One seat's tasks compared by model, for a trial of plane.json `models` (the lead; §2.4) |
| `ccp allowance status [--sample]` | Latest sample, checkpoint in force, resets and decisions (§25.3) |
| `ccp allowance continue --to <percent> --reason "<the operator's words>"` | Record the operator's decision past the checkpoint |
| `ccp allowance session-wake [--sample] [--armed] [--fire]` | The session wake (§25.4) |
| `ccp tasks estimate ID [--baseline] [--force] [--dry-run] [--json] [--print-prompt ID]` | Estimate one task (§26.3) |
| `ccp tasks estimate --all [--baseline] [--max N] [--detach]` | Estimate every task that needs it |
| `ccp tasks estimate show ID` | A task's rows, latest of each source, raw and calibrated |
| `ccp estimate backfill [--dry-run] [--json]` | Baselines and actuals for merged tasks (§26.3) |
| `ccp estimate accuracy [--json]` | The accuracy panel |
| `ccp estimate calibration [--json]` | The calibration factors and rolling check (§26.6) |
| `ccp forecast [--point R<n> \| --backlog] [--json]` | The completion forecast and allowance projection (§26.4) |
| `ccp health [--since DATE] [--json]` | Measurements, suite series and the usage cost advice since the adoption point, or `--since` (the lead; §27.1, §27.2, §14.6, §24.6) |
| `ccp health record --task <id> --metric <name>=<n>` | Record a product metric |
| `ccp health note --text TEXT` | Record a friction note |

Scripts kept as wrappers over `ccp`: `scripts/observability/emit-event.sh`, `heartbeat.sh`,
`write-prompt-audit.sh`, `prune-prompts.sh`. `scripts/observability/set-waiting-on.sh` is waiting_on's
single writer, which `ccp tasks wait|resume` call (§10.1). `status.sh` and `rebuild-now.sh` are
retired: the status is `ccp board status` (§23.4).
