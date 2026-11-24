# `ccp` commands: 03-quality

Call syntax and flags for the commands of SPEC part `docs/spec/03-quality.md`. The rules each
command follows are in the SPEC, not here; `ccp <command> -h` is the source of truth for flags.
Every command runs in the product checkout (`--root DIR`, else `$CCP_ROOT`, else the git toplevel of
the working directory).

| Command | What it does | Cost | SPEC |
| --- | --- | --- | --- |
| `ccp tasks check [--closed-points]` / `ccp tasks check --stale` | Hold the task log to the canonical format (every worker) | Free; on a failure, the command again at the merge base | §21.1, §21.2, §22.2 |
| `ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]` | Run a task's dod_check commands (the lead; `--here`, any worker) | Runs each command once | §21.1 |
| `ccp tasks checks <id> [--json]` | A task's dod_checks, each with its `runs_on` value (any seat) | Free | §5.5 |
| `ccp docs check [--only <id>]` | Run the checks §21.2 lists (every worker), or with `--only <id>` one `architect.checks` or `docs.checks` entry | Free; on a failure, the command again at the merge base | §21.2 |
| `ccp docs history-paths [--attr A]` | Tracked paths carrying the history attribute (any seat) | Free | §21.6 |
| `ccp architect due [--scope IDS]` | Whether an architect pass is due (the architect seat) | Free | §19 |
| `ccp architect run [--mode pass\|shape] [--lens L,…] [--adr ID[,ID…]\|due] [--force] [--detach] [--scope IDS] [--actor A]` | Run an architect pass, or with `--mode shape` shape ADRs (the architect seat) | One Claude session per pass, one per ADR for a shape | §19 |
| `ccp architect triage <id> [--backfill <id> <sha>] [--apply <id>]` | Triage an architect report (the architect seat) | Free | §19 |
| `ccp architect status` | The state of the architect's passes (the architect seat) | Free | §19 |
| `ccp budgets check --base REF [--json]` | House-rule budgets on the files this change grew (any worker) | Free | §20.2 |
| `ccp mutate --run RUN_ID --test ID [--test ID …] [--mutant M …] [--mutant-file PATH …] [--revert PATH[:N[-M][,N[-M]…]] …] [--together]` | Apply each mutant and run the tests (workers) | Each test once, then per mutant | §20.6 |
| `ccp health note --text T [--task ID] [--by WHO]` / `ccp health record --task ID --metric k=v …` | Record a friction line or metric (the runner) | Free | §19.6 |
| `ccp review-points [list] [--json]` | Read the register (any seat) | Free, read-only | §22.8 |
| `ccp review-points show R<n> [--json]` | Read one point of the register (any seat) | Free, read-only | §22.8 |
| `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` | Attach tasks to a point (the lead) | Free | §22.4 |
| `ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` | Rename a point used before the register (the lead) | Free | §22.7 |
| `ccp tasks backfill-review-points [--dry-run] [--json]` | Stamp tasks closed before the stamp at close (the lead) | Free | §22.6 |

Exit codes for these commands follow §10's contract: 0 ok, 1 check failures or a failed run, 2
usage or configuration, 3 not due or busy, and 4 from `ccp tasks next` while an architect pass or
triage is overdue (§19.6).
