# `ccp` commands: 03-quality

Call syntax and flags for the commands of SPEC part `docs/spec/03-quality.md`. The rules each
command follows are in the SPEC, not here; `ccp <command> -h` is the source of truth for flags.
Every command runs in the product checkout (`--root DIR`, else `$CCP_ROOT`, else the git toplevel of
the working directory).

| Command | Who | SPEC |
| --- | --- | --- |
| `ccp tasks check [--closed-points]` / `ccp tasks check --stale` | every worker | §21.1, §21.2, §22.2 (hold the task log to the canonical format) |
| `ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]` | lead; `--here`, any worker | §21.1 (run a task's dod_check commands) |
| `ccp tasks checks <id> [--json]` | any seat | §5.5 (a task's dod_checks, each with its `runs_on` value) |
| `ccp docs check [--only <id>]` | every worker | §21.2 (`--only <id>`: one `architect.checks` or `docs.checks` entry) |
| `ccp docs history-paths [--attr A]` | any seat | §21.6 (the tracked paths carrying the history attribute) |
| `ccp architect due [--scope IDS]` | architect | §19 (whether an architect pass is due) |
| `ccp architect run [--mode pass\|shape] [--lens L,…] [--adr ID[,ID…]\|due] [--force] [--detach] [--scope IDS] [--actor A]` | architect | §19 (run a pass, or with `--mode shape` shape ADRs) |
| `ccp architect triage <id> [--backfill <id> <sha>] [--apply <id>]` | architect | §19 (triage an architect report) |
| `ccp architect status` | architect | §19 (the state of the architect's passes) |
| `ccp budgets check --base REF [--json]` | any worker | §20.2 (house-rule budgets on the files this change grew) |
| `ccp mutate --run RUN_ID --test ID [--test ID …] [--mutant M …] [--mutant-file PATH …] [--revert PATH[:N[-M][,N[-M]…]] …] [--together]` | workers | §20.6 (apply each mutant and run the tests) |
| `ccp health note --text T [--task ID] [--by WHO]` | runner | §19.6 (record a friction line) |
| `ccp review-points [list] [--json]` | any seat | §22.8 (read the register) |
| `ccp review-points show R<n> [--json]` | any seat | §22.8 (read one point of the register) |
| `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` | lead | §22.4 (attach tasks to a point) |
| `ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` | lead | §22.7 (rename a point used before the register) |
| `ccp tasks backfill-review-points [--dry-run] [--json]` | lead | §22.6 (stamp tasks closed before the stamp at close) |
