# `ccp` commands: 02-delivery

Call syntax and flags for the commands of SPEC part `docs/spec/02-delivery.md`. The rules each
command follows are in the SPEC, not here. Commands that act on the queue need `QUEUE_ROOT`. A task
argument takes the full id or its number.

## Tasks

| Command | Who | SPEC |
|---|---|---|
| `ccp tasks list [--status S] [--json]` | anyone | §5 (list the tasks) |
| `ccp tasks next [--scope IDS] [--json] [--allow-overdue REASON] [--holder <slot>]` (also `--explain`) | runner | §10.3, §16.3, §23.2 (`--json` carries `passed_over`) |
| `ccp tasks claim <id> [--holder <slot>]` | runner | §10.5, §16.3 |
| `ccp tasks rotation-due [--holder <slot>]` | the `TeammateIdle` hook, runner, lead | §10.2 step 4, §18.2 |
| `ccp tasks phase <id> <phase> [--note T]` | runner | §10.1 |
| `ccp tasks submit <id>` | runner, `scripts/formal-submit.template.sh` | §15.1, §10.1 (formal-submit, before `ccp prompt verify`) |
| `ccp tasks wait <id> <reason> [--until T] [--quota-class session\|credit] [--detail …]` / `ccp tasks resume <id> [--detail …]` | runner, lead | §10.1, §3.6 (park a task on a reason, and resume it) |
| `ccp tasks close <id> --pr N [--summary "…"]` | runner | §10.5, §15.5, §16.5 (close a merged task) |
| `ccp tasks prefer [<id>… [--reason "…"] \| --clear]` | lead (writes need `ACTOR=design-seat`) | §10.4 |
| `ccp tasks hold [<id> [--reason "…"] \| --clear <id>]` | lead (writes need `ACTOR=design-seat`) | §10.4 |
| `ccp tasks sign-off <id> --by <who> --words "…" [--stage brief\|build] [--head\|--from <sha>] [--at <date>]` | lead (needs `ACTOR=design-seat`) | §3.5, §10.5 |
| `ccp tasks ruling <id> --words "…" [--check <dod_check_id>]` | lead (needs `ACTOR=design-seat`) | §17.5, §15.4 |
| `ccp tasks follow-up <run_id>#<n> (--task <id> \| --proposal <id> \| --drop "<reason>")` | lead (needs `ACTOR=design-seat`) | §13.4, ADR-0044 D2 (run again, it replaces the outcome) |
| `ccp tasks follow-ups [--open] [--json]` | lead | §13.4, ADR-0044 D4 (list the follow-ups) |
| `ccp tasks release <id> [--keep-branch] --reason "…"` | lead, runner | §10.4, §10.5, §16.5 (release a claimed task) |
| `ccp tasks drop <id> --reason "…"` | lead, runner | §10.4 |
| `ccp tasks sync [--dry-run]` | lead, runner | §10.4 |
| `ccp tasks orphans --since <ref> [--json]` | lead | §10.7 (list the commits no task covers) |
| `ccp tasks check --lease [--staged]` | lead, the commit hook template (`scripts/git-hooks/pre-commit.template`) | §10.5 |
| `ccp tasks worktree [--runner <slot>]` | runner | §12.1 (the runner's worktree path) |

## Runs, prompts, reports and verdicts

| Command | Who | SPEC |
|---|---|---|
| `ccp prompt <phase> <id> [--note "…" \| --note-file PATH] [--pr N] [--head SHA] [--base SHA] [--worktree PATH] [--holder <slot>] [--supersede]` | runner | §13.2, §15.6 (`<phase>`: `implement`, `fix`, `merge`, `ruling`, `review`, `verify`) |
| `ccp prompt fix <id> --allow-unreviewed-fix --reason "…"` | runner | §15.2 |
| `ccp prompt review <id> --mode resolution` | runner | §13.2 |
| `ccp prompt verify <id> --waived <check_id>=<ruling id>` (repeatable) | runner | §6.7, §15.4, §15.6 |
| `ccp prompt env <worktree>` | runner, lead | §13.3 (print the worker env of a worktree) |
| `ccp report <run_id> FILE` | each worker | §13.4 (record a worker's report) |
| `ccp agent start\|stop` | the harness's hooks | §11.1 |
| `ccp runs gc [--dry-run]` | lead, runner | §11.1 |
| `ccp verify record FILE` | verifier | §15.4, §15.6, §6.7 |
| `ccp verify merge-ok <pr> [--task <task_id>]` | runner | §15.5 |
| `ccp verify check <task_id> --head <sha>` | a merge step that does not read the PR host | §15.5 |
| `ccp verify spec-text <task_id> [--base <ref>] [--head <ref>]` | reviewer, verifier | §15.2, §3.5 |
| `ccp verify later <task_id> --check <id> --pass\|--fail --evidence "…" --produced-by <seat> [--operator-step <gate id>]` | lead, runner | §15.4 |
| `ccp verify deferred [--task <task_id>] [--json]` | lead, runner | §15.4 |

## Pull requests

Each takes the PR number, never the current branch's PR; open names the pushed branch.

| Command | Who | SPEC |
|---|---|---|
| `ccp pr open --branch <branch> --title <title> --body-file <file>` (`-` for stdin) | implementer | §15.5 (open a PR; prints its number) |
| `ccp pr view <pr> [--json]` | reviewer, verifier, runner | §15.5 (read a PR; `--json` gives one object) |
| `ccp pr diff <pr>` | reviewer, verifier | §15.5 |
| `ccp pr edit <pr> --body-file <file>` (`-` for stdin) | runner | §15.5, §15.2 |
| `ccp pr merge <pr> --head <sha> --task <task_id>` | runner | §15.5 (merge a PR) |

## Test runs

| Command | Who | SPEC |
|---|---|---|
| `ccp suite run [--lane L \| --affected [--since REF]] [--run <run_id> \| --task <id> [--phase P]] [--full \| --summary] [--log PATH] [--wait SECONDS\|auto] [--cold] [-- <command>]` | each worker | §14, §14.7 |
| `ccp suite wait <suite_id> [--timeout SECONDS]` | each worker | §14.2 |
| `ccp suite list [--task ID]` | anyone | §14.4 |
| `ccp suite affected [--since REF \| --since A..B \| --since REF... \| --paths PATH …]` | each worker | §14.7 |

## Worktrees

| Command | Who | SPEC |
|---|---|---|
| `ccp wt create --kind KIND --task ID [--sha SHA] [--name N] [--seat S] [--tag T] [--shallow] [--own-hooks]` | runner, workers | §12.1 |
| `ccp wt create --kind base --task ID --sha HEAD [--name N] [--timeout S] -- COMMAND` | verifier, reviewer | §12.1, §15.1 |
| `ccp wt create --kind ver --baseline [--seat S] [--tag T]` | lead (adoption) | §4.5, §12.1 |
| `ccp wt list [--task ID]` | anyone | §12.1 |
| `ccp wt remove NAME` | workers, runner | §12.1 |
| `ccp wt up NAME` / `ccp wt down NAME` / `ccp wt urls NAME` | workers | §12.3 |
| `ccp wt gc` | lead, runner | §12.1 |
| `ccp wt exec [NAME] [--print] [-- ARGS]` | workers | §12.1 |

## The team and gates (`scripts/team.sh`)

| Command | Who | SPEC |
|---|---|---|
| `team.sh runner spawn --scope … [--review-point …] [--count N]` | lead | §10.2, §16.5 |
| `team.sh runner spawn --dry-run …` (the spawn's flags) | lead | §16.5, §21.1 |
| `team.sh runner bind --name <actual> --as <slot>` (one runner: no `--as`) | lead | §10.2 |
| `team.sh runner rotate [--slot S]` / `team.sh runner stop [--drain]` (also `--slot S`) | lead | §10.2 |
| `team.sh runner scope --add <id>` (also `--remove <ids>`) | lead | §10.2 |
| `team.sh runner status` | lead | §10.2 |
| `team.sh gate open\|decide\|ask-operator\|status …` | runner, lead | §17.9, §3.6 (open and decide a gate) |

## Spec questions (`scripts/spec-maintainer-ask.sh`)

| Command | Who | SPEC |
|---|---|---|
| `spec-maintainer-ask.sh raise …` (`--task-id <id> --blocks <ids>`, the question fields) | runner | §17.3 |
| `spec-maintainer-ask.sh process <question_id>` | runner | §17.3, §17.5 |
| `spec-maintainer-ask.sh blocked` | runner | §17.7 |
