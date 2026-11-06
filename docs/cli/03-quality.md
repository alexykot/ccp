# `ccp` commands: 03-quality

Call syntax and flags for the commands of SPEC part `docs/spec/03-quality.md`. The rules each
command follows are in the SPEC, not here; `ccp <command> -h` is the source of truth for flags.
Every command runs in the product checkout (`--root DIR`, else `$CCP_ROOT`, else the git toplevel of
the working directory).

| Command | What it does | Cost | SPEC |
| --- | --- | --- | --- |
| `ccp tasks check` | Hold the task log to the canonical format | Free | §21.1 |
| `ccp docs check` | Package-doc rules, opted-in generic rules, house rules' shape, `architect.checks`, `docs.checks`, the ADR check and `ccp tasks check` | Free | §21.2 |
| `ccp docs history-paths [--attr A]` | Tracked paths carrying the history attribute, one per line | Free | §21.6 |
| `ccp docs audit due\|run [--force]\|triage <id>\|status` | The docs review as its own kind (an alias of `ccp architect` once a product has the `architect` block). Needs `QUEUE_ROOT` | `run` launches one Claude session | §21.7, §19.12 |
| `ccp architect due \| run [--mode pass\|shape] [--lens L,…] [--adr ID] [--force] [--detach] [--scope IDS] \| triage <id> [--backfill <id> <sha>] \| status` | The architect seat. Needs `QUEUE_ROOT` | `run` launches one Claude session | §19 |
| `scripts/architecture-review.sh due\|run\|triage\|status` | Older alias of `ccp architect` | as above | §19.12 |
| `ccp budgets check --base REF` | House-rule budgets on the files this change grew | Free | §20.2 |
| `ccp health note --text T [--task ID]` / `ccp health record --task ID --metric k=v …` | Record a worker's friction line or metric. Needs `QUEUE_ROOT` | Free | §19.6 |
| `ccp review-points [list\|show R<n>] [--json]` | Read the register | Free, read-only | §22.8 |
| `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` | Attach tasks to a point (working tree only); in short, `ccp review-points tag R<n> …` | Free | §22.4 |
| `ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` | Rename a point used before the register | Free | §22.7 |
| `ccp tasks backfill-review-points [--dry-run] [--json]` | Stamp tasks closed before the stamp at close (working tree only) | Free | §22.6 |

Exit codes for these commands follow §10's contract: 0 ok, 1 check failures or a failed run, 2
usage or configuration, 3 not due or busy, and 4 from `ccp tasks next` while an architect pass or
triage is overdue (§19.6).
