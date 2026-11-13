# `ccp` commands: 04-observability

Call syntax and flags for the commands of SPEC part `docs/spec/04-observability.md`. The rules each
command follows are in the SPEC, not here.

| Command | What it does |
|---|---|
| `ccp board build [--quiet] [--backfill]` | Fold the sources into `board/board.json`, the page and the day's snapshot (§28) |
| `ccp board status` | Terminal summary; exits non-zero on an open blocker (§23.4) |
| `ccp board html` | Write `board/index.html` |
| `ccp board task <id\|NNNN>` | One task's drill-down in the terminal |
| `ccp board install\|uninstall\|timer` | The per-project rebuild timer |
| `ccp otel serve [--port N]` | The telemetry receiver (§24.2) |
| `ccp otel env [--project ID]` | Print the user-settings block, and with `--project` the product's block (§24.1) |
| `ccp otel install\|uninstall\|status` | The receiver's service; `status` reports rows written, routed, pending and refused, and checks the user settings |
| `ccp usage [--task ID] [--json]` | Per-run and per-seat tokens, cost, models and coverage (§24.4) |
| `ccp usage --system [--since DATE] [--json]` | The system sink by cwd and day |
| `ccp allowance status [--sample]` | Latest sample, checkpoint in force, resets and decisions (§25.3) |
| `ccp allowance continue --to <percent> --reason "<the operator's words>"` | Record the operator's decision past the checkpoint |
| `ccp allowance session-wake [--sample] [--armed] [--fire]` | The session wake (§25.4) |
| `ccp tasks estimate ID [--baseline] [--force] [--dry-run] [--print-prompt ID]` | Estimate one task (§26.3) |
| `ccp tasks estimate --all [--baseline] [--max N] [--detach]` | Estimate every task that needs it |
| `ccp tasks estimate show ID` | A task's rows, latest of each source, raw and calibrated |
| `ccp estimate backfill [--dry-run]` | Baselines and actuals for merged tasks (§26.3) |
| `ccp estimate accuracy [--json]` | The accuracy panel |
| `ccp estimate calibration [--json]` | The calibration factors and rolling check (§26.6) |
| `ccp forecast [--point R<n> \| --backlog] [--json]` | The completion forecast and allowance projection (§26.4) |
| `ccp health [--json]` | Measurements, suite series (§27), the share of merged tasks under `health.small_task_lines` (`small_tasks`) and the gate's time against the shell limit (§14.6) |
| `ccp health record --task <id> --metric <name>=<n>` | Record a product metric |
| `ccp health note --text TEXT` | Record a friction note |

Scripts kept as wrappers over `ccp`: `scripts/observability/emit-event.sh`, `set-waiting-on.sh`,
`heartbeat.sh`, `write-prompt-audit.sh`, `prune-prompts.sh`. `status.sh` and `rebuild-now.sh` are
retired: the status is `ccp board status` (§23.4).
