# Runtime queue (`.delivery-queue/<project_id>/`)

**Not** the durable task log. The durable log lives in the **product** repo under `docs/delivery/` (tasks never deleted; status and notes stay in git).

This directory is **runtime only**: leases, live Claude session ids, `running.json`, auth status, transient blockers for the watchdog.

## Layout (indicative)

```
.delivery-queue/<project_id>/
  auth/
    status.json          # from auth_check.probes (ccp tasks claim / ccp auth check)
  running.json           # live Claude / shell lease (delete after assess)
  last-session.json      # last assessed session
  work.json              # optional hot pointer at active durable task id
  blocker.md             # optional; Claude/runtime blocker text
  observability/         # events.jsonl, now.json, STATUS.md, seats/*.json
  prompts/<task_id>/     # Layer 2 audit JSON — never commit
  scripts/               # optional project-local copies of plane scripts
```

For example:

`$HOME/projects/.delivery-queue/<project_id>`

## Rules

| Do | Don’t |
| --- | --- |
| Put session ids, pids, auth JSON, leases here | Store the canonical task brief or DoD here |
| Clear or rotate between slices | Delete durable `docs/delivery/` tasks because the queue was cleaned |
| Point `QUEUE_ROOT` / `project.example.yaml` `queue_root` here | Commit this tree into any branch of the product |

## Auth

`ccp tasks claim` (and `ccp auth check`) runs the product's plane.json `auth_check.probes` and writes `auth/status.json` (SPEC §11). On a failure the claim refuses; the runner sets `waiting_on=reauth` and raises it to the lead.

## Worktrees

`worktrees/<name>.json`: one record per plane-made worktree (`ccp wt`, SPEC §28.29, `contracts/worktree.schema.json`).

## Observability

`scripts/observability/status.sh` folds `observability/events.jsonl` + live probes into `observability/now.json`. See `scripts/observability/README.md` and SPEC §20.

## See also

- Durable log templates: `templates/docs-delivery/`
- SPEC.md §5 (runtime vs durable) and §20 (observability)
