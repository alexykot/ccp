# `ccp` commands: 02-delivery

Call syntax and flags for the commands of SPEC part `docs/spec/02-delivery.md`. The rules each
command follows are in the SPEC, not here. Commands that act on the queue need `QUEUE_ROOT`. A task
argument takes the full id or its number.

## Tasks

| Command | Who | SPEC |
|---|---|---|
| `ccp tasks list [--status S] [--json]` | anyone | every task, in number order |
| `ccp tasks next [--scope IDS] [--json]` (also `--explain`) | runner | §10.3, §16.3 |
| `ccp tasks index [--stdout]` | lead | regenerates `INDEX.yaml` (§5) |
| `ccp tasks claim <id> [--holder <slot>]` | runner | §10.5, §16.3 |
| `ccp tasks phase <id> <phase>` | runner | §10.1 |
| `ccp tasks wait <id> <reason> [--until T] [--detail …]` / `ccp tasks resume <id>` | runner, lead | §10.1, §3.6 (a wait on `reauth`, `operator_step` or `operator_decision` fires a notice: pending on record, and the notify command if any) |
| `ccp tasks close <id> --pr N [--summary "…"]` | runner | §10.5, §15.5, §16.5 |
| `ccp tasks prefer [<id>… [--reason "…"] \| --clear]` | lead | §10.4 |
| `ccp tasks hold [<id> [--reason "…"] \| --clear <id>]` | lead | §10.4 |
| `ccp tasks sign-off <id> --by <who> --words "…" [--stage brief\|build] [--head\|--from <sha>] [--at <date>]` | lead | §3.5, §10.5 |
| `ccp tasks release <id> --reason "…"` | lead, runner | §10.4 |
| `ccp tasks drop <id> --reason "…"` | lead, runner | §10.4 |
| `ccp tasks sync` | lead, runner | §10.4 |
| `ccp tasks orphans --since <ref> [--json]` | lead | §10.7 |
| `ccp tasks check --lease [--staged]` | lead, the commit hook template (`scripts/git-hooks/pre-commit.template`) | §10.5 |
| `ccp tasks worktree [--runner <slot>]` | runner | §12.1 (`--runner` with several runners) |

## Runs, prompts, reports and verdicts

| Command | Who | SPEC |
|---|---|---|
| `ccp prompt <phase> <id> [--round n] [--note "…"]` (`<phase>`: `implement`, `fix`, `merge`, `ruling`, `review` or `verify`; `--note-file PATH` for the note; `--head SHA`, `--supersede`, `--allow-unreviewed-fix --reason "…"`; a verify round with no fix round since the last needs `--note`) | runner | §13.2, §15.2, §15.6 |
| `ccp report <run_id> FILE` | each worker | §13.4 |
| `ccp agent start\|stop` | the harness's hooks | §11.1 |
| `ccp runs gc [--dry-run]` | lead, runner | §11.1 |
| `ccp verify record FILE` | verifier | §15.4, §15.6, §6.7 |
| `ccp verify merge-ok <pr> [--task <task_id>]` | runner | §15.5 |
| `ccp verify check <task_id> --head <sha>` | a merge step without `gh` | §15.5 |
| `ccp auth check` | runner, lead | §10.5 |

## Test runs

| Command | Who | SPEC |
|---|---|---|
| `ccp suite run [--lane L] [--run <run_id> \| --task <id> [--phase P]] [--full \| --summary] [--log PATH] [-- <command>]` (also `--wait SECONDS`) | each worker | §14 |
| `ccp suite list [--task ID]` | anyone | §14.4 |
| `ccp suite affected [--since REF \| --paths PATH …]` | each worker | §14.7 |

## Worktrees

| Command | Who | SPEC |
|---|---|---|
| `ccp wt create --kind KIND --task ID [--sha SHA] [--name N] [--seat S] [--tag T] [--shallow]` | runner, workers | §12.1 |
| `ccp wt create --kind base --task ID --sha HEAD [--name N] [--timeout S] -- COMMAND` | verifier, reviewer | §12.1, §15.1 |
| `ccp wt create --kind ver --baseline [--seat S] [--tag T]` | lead (adoption) | §4.5, §12.1 |
| `ccp wt list [--task ID]` | anyone | §12.1 |
| `ccp wt remove NAME` | workers, runner | §12.1 |
| `ccp wt up NAME` / `ccp wt down NAME` / `ccp wt urls NAME` | workers | §12.3 |
| `ccp wt gc` | lead, runner | §12.1 |
| `ccp wt exec [NAME] [--print] [-- ARGS]` | reviewer, verifier | §12.1 |

## The team and gates (`scripts/team.sh`)

| Command | Who | SPEC |
|---|---|---|
| `team.sh runner spawn --scope … [--review-point …] [--count N]` | lead | §10.2, §16.5 |
| `team.sh runner spawn --dry-run …` (the spawn's flags; exit 1 when a readiness check fails) | lead | §16.5 |
| `team.sh runner bind --name <actual> --as <slot>` (one runner: no `--as`) | lead | §10.2 |
| `team.sh runner rotate [--slot S]` / `team.sh runner stop [--drain]` (also `--slot S`) | lead | §10.2 |
| `team.sh runner scope --add <id>` (also `--remove <ids>`) | lead | §10.2 |
| `team.sh runner status` | lead | §10.2 |
| `team.sh gate open\|decide\|ask-operator\|status …` | runner, lead | §17.9, §3.6 (`ask-operator` fires a `decision` notice) |

## Spec questions (`scripts/spec-maintainer-ask.sh`)

| Command | Who | SPEC |
|---|---|---|
| `spec-maintainer-ask.sh raise …` (`--task-id <id> --blocks <ids>`, the question fields) | runner | §17.3 |
| `spec-maintainer-ask.sh process <question_id>` | runner | §17.3, §17.5 |
| `spec-maintainer-ask.sh blocked` | runner | §17.7 |
