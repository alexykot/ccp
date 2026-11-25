# `ccp` commands: 04-observability

Call syntax and flags for the commands of SPEC part `docs/spec/04-observability.md`. The rules each
command follows are in the SPEC, not here.

| Command | Who | SPEC |
|---|---|---|
| `ccp board build [--quiet]` | the rebuild timer, lead | §28 (fold the sources into the board and the day's snapshot) |
| `ccp board status` | any seat | §23.4 (the terminal summary) |
| `ccp board task <id\|NNNN>` | any seat | §28.3 (one task's drill-down) |
| `ccp board install\|uninstall\|timer` | operator | §28.2 (the per-project rebuild timer) |
| `ccp otel serve [--port N]` | the machine's service manager | §24.2 (the telemetry receiver) |
| `ccp otel env [--project ID]` | operator | §24.1 (print the user-settings block) |
| `ccp otel install\|uninstall\|status` | operator | §24.1, §24.2 (`status` reports the counts and checks the user settings) |
| `ccp usage [--task ID] [--since DATE] [--json]` | lead | §24.4, §24.6 (per-run and per-seat tokens and cost) |
| `ccp usage --system [--since DATE] [--json]` | lead | §24.3 (the system sink by cwd and day) |
| `ccp usage --by-model [--seat SEAT] [--json]` | lead | §2.4 (one seat's tasks compared by model, `implementer` by default) |
| `ccp allowance status [--sample]` | any seat | §25.3 (the allowance state) |
| `ccp allowance continue --to <percent> --reason "<the operator's words>"` | lead | §25.3 (record the operator's decision past the checkpoint) |
| `ccp allowance session-wake [--sample] [--armed] [--fire]` | lead | §25.4 (the session wake) |
| `ccp tasks estimate ID [--baseline] [--force] [--dry-run] [--json] [--print-prompt ID]` | lead | §26.3 (estimate one task) |
| `ccp tasks estimate --all [--baseline] [--max N] [--detach]` | lead | §26.3 (estimate every task that needs it) |
| `ccp tasks estimate show ID` | any seat | §26.2 (a task's estimates, latest of each source) |
| `ccp estimate backfill [--dry-run] [--json]` | lead | §26.3 (baselines and actuals for merged tasks) |
| `ccp estimate accuracy [--json]` | any seat | §26.3 (the accuracy panel) |
| `ccp estimate calibration [--json]` | any seat | §26.6 (the calibration factors) |
| `ccp forecast [--point R<n> \| --backlog] [--json]` | lead | §26.4, §26.5 (the completion forecast) |
| `ccp health [--since DATE] [--json]` | lead | §27.1, §27.2, §14.6, §24.6 (the measurements, suite series and usage cost advice) |
| `ccp health record --task <id> --metric <name>=<n>` | runner | §27.1 (record a product metric) |

Scripts kept as single writers built on `ccp/lib.py`, the ledger library `ccp` itself imports (§10.6):
`scripts/observability/emit-event.sh`, `heartbeat.sh`, `write-prompt-audit.sh`; `prune-prompts.sh` prunes the audit files.
`scripts/observability/set-waiting-on.sh` is waiting_on's
single writer, which `ccp tasks wait|resume` call (§10.1). `status.sh` and `rebuild-now.sh` are
retired: the status is `ccp board status` (§23.4).
