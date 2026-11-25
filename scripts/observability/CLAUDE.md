# observability — the ledger and the seat scripts (SPEC §23, §17, §2)

The ledger library, `ccp/lib.py`, is `ccp`'s own module (`ccp` imports nothing from `scripts/`, house rule E7), and every
script here is built on it: it writes and folds the event ledger
(`QUEUE_ROOT/observability/events.jsonl`), holds the work.json lock, the one atomic write (`write_atomic`: a
unique temporary name beside the file, removed when the write fails), the one reader of a product's binding
(`read_binding`, with `binding_path`, `product_binding`, `binding_data` and the machine file's `read_machine`),
the seat table (`RUNNER`, `VERIFIER`, `LEAD`, `SEAT_IDS`: house rules E17 and E27) and the values only read, never
written (`WAIT_READ_ONLY`, `LEGACY_EVENT_TYPES`: house rule E9). `team.py` runs the runner teammate's
lifecycle and the gate ledger, `spec_maintainer.py` spec questions to the lead (the open-question
rule is `ccp/queue.py`'s, the headless launch `ccp/headless.py`'s). The review kit the architect seat runs on (§19) is
`ccp/architecture_review.py`. The shell scripts are single writers: `set-waiting-on.sh` (the only writer of `waiting_on`), `emit-event.sh`, `heartbeat.sh`,
`prune-prompts.sh`, `write-prompt-audit.sh`. The status is the board (`ccp board`, §28).

Every script takes `QUEUE_ROOT` (the runtime queue, outside product git) and answers `--help`; `OBS_NOW` pins the
clock for an example or a test. `heartbeat.sh <seat>` takes the seat ids of §18.3. An old ledger's rows of a seat
since retired (`LEGACY_ACTORS`) are read and never written. The timer formulas are SPEC §23.3; the contracts are
`contracts/observability_event.schema.json` and `contracts/prompt_audit.schema.json`. `prompts/` (the audit files) is never committed.
