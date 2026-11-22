# `ccp` commands: 02-delivery

Call syntax and flags for the commands of SPEC part `docs/spec/02-delivery.md`. The rules each
command follows are in the SPEC, not here. Commands that act on the queue need `QUEUE_ROOT`. A task
argument takes the full id or its number.

## Tasks

| Command | Who | SPEC |
|---|---|---|
| `ccp tasks list [--status S] [--json]` | anyone | every task, in number order |
| `ccp tasks next [--scope IDS] [--json] [--allow-overdue REASON] [--holder <slot>]` (also `--explain`) | runner | §10.3, §16.3 (a task passed over for a path in flight is named on stderr, `passed over <id>: <why>`, and in `--json` `passed_over`); §23.2 (with `--holder`, exit 3 records `runner`/`starved`, once per stretch) |
| `ccp tasks index [--stdout]` | lead | regenerates `INDEX.yaml` (§5) |
| `ccp tasks migrate [--dry-run] [--drop-open]` | lead | §5.3 (converts an earlier plane generation's task files in place; exit 1 when one cannot be converted) |
| `ccp tasks claim <id> [--holder <slot>]` | runner | §10.5, §16.3 |
| `ccp tasks rotation-due [--holder <slot>]` | the `TeammateIdle` hook, runner, lead | §10.2 step 4, §18.2 |
| `ccp tasks phase <id> <phase> [--note T]` | runner | §10.1 |
| `ccp tasks submit <id>` | runner, `scripts/formal-submit.template.sh` | §15.1, §10.1 (formal-submit, before `ccp prompt verify`: exit 4 naming each failed item, nothing moved; a pass moves the task to `submitted`; exit 3 for a task not mid-flight or past `submitted`) |
| `ccp tasks wait <id> <reason> [--until T] [--quota-class session\|credit] [--detail …]` / `ccp tasks resume <id> [--detail …]` | runner, lead | §10.1, §3.6 (a wait on `reauth`, `operator_step` or `operator_decision` fires a notice: pending on record, and the notify command if any) |
| `ccp tasks close <id> --pr N [--summary "…"]` | runner | §10.5, §15.5, §16.5 (names `idle_runners` and `vacant_slots`, the slots rotated and not respawned) |
| `ccp tasks prefer [<id>… [--reason "…"] \| --clear]` | lead | §10.4 |
| `ccp tasks hold [<id> [--reason "…"] \| --clear <id>]` | lead | §10.4 |
| `ccp tasks sign-off <id> --by <who> --words "…" [--stage brief\|build] [--head\|--from <sha>] [--at <date>]` | lead | §3.5, §10.5 |
| `ccp tasks ruling <id> --words "…" [--check <dod_check_id>]` | lead | §17.5, §15.4 |
| `ccp tasks follow-up <run_id>#<n> (--task <id> \| --proposal <id> \| --drop "<reason>")` | lead | §13.4, ADR-0044 D2 (refused, exit 2, when `ACTOR` names another seat, for an id that names no follow-up, a task not in the log at `origin/<integration>`, a proposal not in `plane/proposals.jsonl`, an empty or secret-like reason; run again, it replaces the outcome) |
| `ccp tasks follow-ups [--open] [--json]` | lead | §13.4, ADR-0044 D4 (`<id> <task_id> <outcome or open>: <text>` per follow-up, then `<n> open`) |
| `ccp tasks release <id> [--keep-branch] --reason "…"` | lead, runner | §10.4, §10.5, §16.5 (names `idle_runners` and `vacant_slots`, as close does) |
| `ccp tasks drop <id> --reason "…"` | lead, runner | §10.4 |
| `ccp tasks sync [--dry-run]` | lead, runner | §10.4 |
| `ccp tasks orphans --since <ref> [--json]` | lead | §10.7 (a commit that changes only the task log and the SPEC files is covered) |
| `ccp tasks check --lease [--staged]` | lead, the commit hook template (`scripts/git-hooks/pre-commit.template`) | §10.5 |
| `ccp tasks worktree [--runner <slot>]` | runner | §12.1 (`--runner` with several runners) |

## Runs, prompts, reports and verdicts

| Command | Who | SPEC |
|---|---|---|
| `ccp prompt <phase> <id> [--note "…"]` (`<phase>`: `implement`, `fix`, `merge`, `ruling`, `review` or `verify`; `--note-file PATH` for the note; `--pr N`, `--head SHA`, `--base SHA`, `--worktree PATH`, `--holder <slot>`, `--supersede`, `--allow-unreviewed-fix --reason "…"`, `--mode resolution` (review only: a conflicted integration merge's resolution), `--waived <check_id>=<ruling id>` (verify only, repeatable: a check marked `runs_on: operator-machine` a ruling waives); a verify round with no fix round since the last needs `--note`; a verify is refused while a marked check has no passed suite run at the head, unless it carries an earlier approve or is waived) | runner | §13.2, §15.2, §15.6 |
| `ccp prompt env <worktree>` (its path or recorded name: the `worker_env` lines its workers would get; opens no run) | runner, lead | §13.3 |
| `ccp report <run_id> FILE` (again, with a corrected report, until the task's next run opens; the earlier one is kept as superseded) | each worker | §13.4 |
| `ccp agent start\|stop` | the harness's hooks | §11.1 |
| `ccp runs gc [--dry-run]` | lead, runner | §11.1 |
| `ccp verify record FILE` | verifier | §15.4, §15.6, §6.7 |
| `ccp verify merge-ok <pr> [--task <task_id>]` | runner | §15.5 |
| `ccp verify check <task_id> --head <sha>` | a merge step that does not read the PR host | §15.5 |
| `ccp verify spec-text <task_id> [--base <ref>] [--head <ref>]` | reviewer, verifier | §15.2, §3.5 |
| `ccp verify later <task_id> --check <id> --pass\|--fail --evidence "…" --produced-by <seat> [--operator-step <gate id>]` | lead, runner | §15.4 |
| `ccp verify deferred [--task <task_id>] [--json]` | lead, runner | §15.4 |
| `ccp auth check` | runner, lead | §10.5 |

## Pull requests

Each takes the PR number, never the current branch's PR; open names the pushed branch. Exit 1 on a PR-host
error, naming it; 2 on a usage error.

| Command | Who | SPEC |
|---|---|---|
| `ccp pr open --branch <branch> --title <title> --body-file <file>` (`-` for stdin) | implementer | §15.5 (against the integration branch; prints the PR number) |
| `ccp pr view <pr> [--json]` | reviewer, verifier, runner | §15.5 (`--json`: the PR's facts as one object) |
| `ccp pr diff <pr>` | reviewer, verifier | §15.5 |
| `ccp pr edit <pr> --body-file <file>` (`-` for stdin) | runner | §15.5, §15.2 |
| `ccp pr merge <pr> --head <sha> --task <task_id>` | runner | §15.5 (`--head`: the PR's full head sha) |

## Test runs

| Command | Who | SPEC |
|---|---|---|
| `ccp suite run [--lane L] [--run <run_id> \| --task <id> [--phase P]] [--full \| --summary] [--log PATH] [-- <command>]` (also `--wait SECONDS\|auto`, `--cold`); a command after `--` that replaces the argv plane.json gives the full or gate role's lane runs after a warning | each worker | §14 |
| `ccp suite wait <suite_id> [--timeout SECONDS]` | each worker | §14.2 |
| `ccp suite list [--task ID]` | anyone | §14.4 |
| `ccp suite affected [--since REF \| --since A..B \| --paths PATH …]`; plane.json `suite.affected_map` adds the test ids of each glob a changed path matches; on stderr, `ccp suite run --lane <part lane> -- <command> <modules>`, the command the argv plane.json gives the part role's lane, else the language's | each worker | §14.7 |

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
