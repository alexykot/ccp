# `ccp` commands: 03-quality

Call syntax and flags for the commands of SPEC part `docs/spec/03-quality.md`. The rules each
command follows are in the SPEC, not here; `ccp <command> -h` is the source of truth for flags.
Every command runs in the product checkout (`--root DIR`, else `$CCP_ROOT`, else the git toplevel of
the working directory).

| Command | What it does | Cost | SPEC |
| --- | --- | --- | --- |
| `ccp tasks check [--closed-points]` / `ccp tasks check --stale` | Hold the task log to the canonical format; with `--closed-points`, also fail on a review point the register records closed while a follow-up of one of its tasks is undecided. That reads `QUEUE_ROOT`; without it, a note. The tasks whose Context was measured before commits that changed their paths are counted in one warning; `--stale` (with no other flag, else exit 2) names each instead of the other warnings, the exit code as without it. A failure the merge base with `origin/<integration>` shows too, in no file and no checker the branch changes (§21.2), prints after the others, under `pre-existing on <integration> at <sha>, …`, and does not fail it | Free; on a failure, the command again at the merge base | §21.1, §21.2, §22.2 |
| `ccp tasks dry-run <id> [--write] [--check <check-id>] [--here]` | Run a task's dod_check commands, each through `bash -c`, at the integration tip, in a temporary worktree, and print what each printed; with `--write`, write each check's dry-run record. `--check` runs only that check (exit 2: the task has no such check); `--here` runs in this checkout at its HEAD, writes nothing (exit 2 with `--write`) and takes a claimed task. Needs `QUEUE_ROOT` | Runs each command once | §21.1 |
| `ccp tasks checks <id> [--json]` | A task's dod_checks in the checkout, each id with its `runs_on` value, or null for a check the workers run; exit 2 for an unknown task | Free | §5.5 |
| `ccp docs check [--only <id>]` | Package-doc rules, opted-in generic rules, house rules' shape, `architect.checks`, `docs.checks`, the ADR check and `ccp tasks check`. A failure the merge base with `origin/<integration>` shows too, in no file and no checker the branch changes (§21.2), prints after the others, under `pre-existing on <integration> at <sha>, …`, and does not fail it. `--only <id>` runs that one `architect.checks` or `docs.checks` entry, judged the same way, and nothing else (exit 2: no such check) | Free; on a failure, the command again at the merge base | §21.2 |
| `ccp docs history-paths [--attr A]` | Tracked paths carrying the history attribute, one per line | Free | §21.6 |
| `ccp architect due [--scope IDS]` | The architect seat: whether a pass is due. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp architect run [--mode pass\|shape] [--lens L,…] [--adr ID[,ID…]\|due] [--force] [--detach] [--scope IDS] [--actor A]` | The architect seat: run a pass, or with `--mode shape` shape ADRs. Needs `QUEUE_ROOT` | One Claude session per pass, one per ADR for a shape | §19 |
| `ccp architect triage <id> [--backfill <id> <sha>] [--apply <id>]` | The architect seat: a report's triage. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp architect status` | The architect seat: the state of its passes. Needs `QUEUE_ROOT` | Free | §19 |
| `ccp budgets check --base REF [--json]` | House-rule budgets on the files this change grew | Free | §20.2 |
| `ccp mutate --run RUN_ID --test ID [--test ID …] [--mutant M …] [--mutant-file PATH …] [--revert PATH[:N[-M]] …] [--together]` | In the seat's `impl`, `mut`, `rev` or `ver` worktree, apply each mutant (`<file>:<old>=><new>`, a mutant file holding the path, `=== old`, the old text, `=== new` and the new text, a patch file, or a revert to the merge base's version of a file or line range) alone, or with `--together` all of them applied as one mutant, run plane.json `mutate.command`, else the language pack's per-test runner, for each test in the order given until one fails (each id may name a single method; for a product whose tests are whole scripts, `sh {test}` with the script's path as the id), restore the tree and record killed or survived on the run, with the test that decided it and the failing tests its output names, or `unbuilt` for a failing run with a line plane.json `mutate.unbuilt_re` (else the language pack's did-not-build lines) matches; it refuses a substitution whose new text is its old text. Needs `QUEUE_ROOT` | Runs each named test once unmutated, then, per mutant, the tests in order until one fails | §20.6 |
| `ccp health note --text T [--task ID] [--by WHO]` / `ccp health record --task ID --metric k=v …` | Record a worker's friction line or metric. Needs `QUEUE_ROOT` | Free | §19.6 |
| `ccp review-points [list] [--json]` | Read the register | Free, read-only | §22.8 |
| `ccp review-points show R<n> [--json]` | Read one point of the register | Free, read-only | §22.8 |
| `ccp review-points tag R<n> [ID …] [--from-work] [--dry-run]` | Attach tasks to a point (working tree only); in short, `ccp review-points tag R<n> …` | Free | §22.4 |
| `ccp review-points migrate --from OLD --to R<n> [--dry-run] [--merge]` | Rename a point used before the register | Free | §22.7 |
| `ccp tasks backfill-review-points [--dry-run] [--json]` | Stamp tasks closed before the stamp at close (working tree only) | Free | §22.6 |

Exit codes for these commands follow §10's contract: 0 ok, 1 check failures or a failed run, 2
usage or configuration, 3 not due or busy, and 4 from `ccp tasks next` while an architect pass or
triage is overdue (§19.6).
