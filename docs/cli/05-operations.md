# `ccp` commands: 05-operations

Call syntax and flags for the commands of SPEC part `docs/spec/05-operations.md`. The rules each
command follows are in the SPEC, not here.

## Credentials (§30.1)

| Command | Who | SPEC |
|---|---|---|
| `ccp auth check` | runner, lead | §30.1, §10.5 |

## Tool proposals and triage (§31.4, §31.5)

| Command | Who | SPEC |
|---|---|---|
| `ccp plane propose --need "…" --generic "<why any product needs it>" [--task <id>] [--workaround "…"] [--frequency per-task\|per-run\|once]` | any seat | §31.4 |
| `ccp plane propose --again <id>` | any seat | §31.4 (record a repeat of the step by hand) |
| `ccp plane list [--open]` | any seat | §31.4 |
| `ccp plane triage <id> --accept \| --merge-into <id> \| --decline --reason "…"` | the plane session | §31.5 |
| `ccp plane built <id> --task <plane task id>` | the plane session | §31.5 (close an accepted proposal as built) |

## The queue's leftovers (§31.3)

| Command | Who | SPEC |
|---|---|---|
| `ccp plane check [--archive]` | lead | §31.3 (the queue entries the plane does not write) |

## Releases (§29)

| Command | Who | SPEC |
|---|---|---|
| `ccp upgrade notes [--since <commit>]` | the plane session | §29.3 |
| `ccp upgrade status` | lead | §29.3 |
| `ccp upgrade decline <task> --reason R` | lead | §29.3 (record the task's adopt step as declined) |
| `ccp upgrade take <task> --reason R` | lead | §29.3 (record the task's adopt step as taken) |
| `ccp sandbox create [DIR] [-- <ccp init options>]` | plane developers, workers | §29.3 |
| `ccp sandbox remove DIR` | plane developers, workers | §29.3 |
| `scripts/run-checkout.sh install \| update \| status` | operator, the plane session | §29.2, §29.3 |
| `scripts/release.sh [worktree]` | the plane session | §29.2 (the release, after a merge) |
