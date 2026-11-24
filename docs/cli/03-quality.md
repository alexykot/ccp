# `ccp` commands: 03-quality

Call syntax and flags for the commands of SPEC part `docs/spec/03-quality.md`. The rules each
command follows are in the SPEC, not here; `ccp <command> -h` is the source of truth for flags.
Every command runs in the product checkout (`--root DIR`, else `$CCP_ROOT`, else the git toplevel of
the working directory).

| Command | What it does | Cost | SPEC |
| --- | --- | --- | --- |
| `ccp tasks check [--closed-points]` / `ccp tasks check --stale` | Hold the task log to the canonical format (every worker); `--closed-points` also checks follow-ups, `--stale` names stale Context | Free; on a failure, the command again at the merge base | §21.1, §21.2, §22.2 |
| `ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]` | Run a task's dod_check commands at the integration tip, or with `--here` in this checkout (the lead, the implementer). Needs `QUEUE_ROOT` | Runs each command once | §21.1 |
| `ccp tasks checks <id> [--json]` | A task's dod_checks in the checkout, each with its `runs_on` value (any seat) | Free | §5.5 |
| `ccp docs check [--only <id>]` | Run the package-doc, house-rule and `architect.checks` checks, the ADR check and `ccp tasks check` (every worker); `--only <id>` runs one check | Free; on a failure, the command again at the merge base | §21.2 |
| `ccp docs history-paths [--attr A]` | Tracked paths carrying the history attribute, one per line | Free | §21.6 |
| `ccp architect due [--scope IDS]` | The architect seat: whether a pass is due. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp architect run [--mode pass\|shape] [--lens L,…] [--adr ID[,ID…]\|due] [--force] [--detach] [--scope IDS] [--actor A]` | The architect seat: run a pass, or with `--mode shape` shape ADRs. Needs `QUEUE_ROOT` | One Claude session per pass, one per ADR for a shape | §19 |
| `ccp architect triage <id> [--backfill <id> <sha>] [--apply <id>]` | The architect seat: a report's triage. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp architect status` | The architect seat: the state of its passes. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp budgets check --base REF [--json]` | House-rule budgets on the files this change grew | Free | §20.2 |
| `ccp mutate --run RUN_ID --test ID [--test ID …] [--mutant M …] [--mutant-file PATH …] [--revert PATH[:N[-M][,N[-M]…]] …] [--together]` | Apply each mutant, run the tests, record killed or survived on the run (workers). Needs `QUEUE_ROOT` | Each test once, then per mutant | §20.6 |
| `ccp health note --text T [--task ID] [--by WHO]` / `ccp health record --task ID --metric k=v …` | Record a worker's friction line or metric. Needs `QUEUE_ROOT` | Free | §19.6 |
| `ccp review-points [list] [--json]` | Read the register | Free, read-only | §22.8 |
| `ccp review-points show R<n> [--json]` | Read one point of the register | Free, read-only | §22.8 |
| `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` | Attach tasks to a point (working tree only); in short, `ccp review-points tag R<n> …` | Free | §22.4 |
| `ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` | Rename a point used before the register | Free | §22.7 |
| `ccp tasks backfill-review-points [--dry-run] [--json]` | Stamp tasks closed before the stamp at close (working tree only) | Free | §22.6 |

Exit codes for these commands follow §10's contract: 0 ok, 1 check failures or a failed run, 2
usage or configuration, 3 not due or busy, and 4 from `ccp tasks next` while an architect pass or
triage is overdue (§19.6).
