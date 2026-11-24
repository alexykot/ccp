# Runtime queue (`.delivery-queue/<project_id>/`)

**Not** the durable task log. The durable log lives in the **product** repo under `docs/delivery/` (tasks never deleted; status and notes stay in git).

This directory is **runtime only**: leases, live Claude session ids, auth status and the ledger. It lives outside the product's git, wherever `QUEUE_ROOT` points (for example `$HOME/projects/.delivery-queue/<project_id>`).

The queue's files and the commands that write them are SPEC §23.7.
