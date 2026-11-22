# Runtime queue (`.delivery-queue/<project_id>/`)

**Not** the durable task log. The durable log lives in the **product** repo under `docs/delivery/` (tasks never deleted; status and notes stay in git).

This directory is **runtime only**: leases, live Claude session ids, auth status and the ledger. It lives outside the product's git, wherever `QUEUE_ROOT` points (for example `$HOME/projects/.delivery-queue/<project_id>`).

The queue's files and the commands that write them are SPEC §23.7.

## Rules

| Do | Don’t |
| --- | --- |
| Put session ids, pids, auth JSON, leases here | Store the canonical task brief or DoD here |
| Clear or rotate between slices | Delete durable `docs/delivery/` tasks because the queue was cleaned |
| Point `QUEUE_ROOT` / `project.example.yaml` `queue_root` here | Commit this tree into any branch of the product |
