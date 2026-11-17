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

## Releases (§29)

```
ccp upgrade notes [--since <commit>]
ccp upgrade status
ccp sandbox create [DIR] [-- <ccp init options>]
ccp sandbox remove DIR
scripts/run-checkout.sh install | update | status
scripts/release.sh [worktree]
```
