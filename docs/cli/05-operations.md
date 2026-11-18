# `ccp` commands: 05-operations

Call syntax and flags for the commands of SPEC part `docs/spec/05-operations.md`. The rules each
command follows are in the SPEC, not here.

## Credentials (§30.1)

```
ccp auth check                 run the product's auth_check.probes now; writes auth/status.json
```

## Tool proposals and triage (§31.4, §31.5)

```
ccp plane propose --need "…" --generic "<why any product needs it>" [--task <id>] [--workaround "…"] [--frequency per-task|per-run|once]
ccp plane propose --again <id>
ccp plane list
ccp plane triage <id> --accept | --merge-into <id> | --decline --reason "…"
ccp plane built <id> --task <plane task id>
```

## The queue's leftovers (§31.3)

```
ccp plane check [--archive]    the queue entries the plane does not write (scripts, root); --archive moves them to QUEUE_ROOT/_legacy/<UTC date>/
                               not listed: a byte-identical plane script, the binding's auth_check.script (and a directory holding it), an atomic write's *.tmp
```

## Releases (§29)

```
ccp upgrade notes [--since <commit>]
ccp upgrade status
ccp upgrade decline <task> --reason R    record the task's adopt step as declined (plane.json upgrade.declined)
ccp upgrade take <task> --reason R       record it as taken (plane.json upgrade.taken); each removes the task from the other
ccp sandbox create [DIR] [-- <ccp init options>]
ccp sandbox remove DIR
ccp notify fire <trigger> [--task ID] [--id ID] [--reason R]    a test notice, in a sandbox only, with --task or --id (§3.6)
scripts/run-checkout.sh install | update | status
scripts/release.sh [worktree]
```
