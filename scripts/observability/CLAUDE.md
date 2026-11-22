# observability — the ledger and the seat scripts (SPEC §23, §17, §2)

`lib.py` is shared by `ccp` and every script here: it writes and folds the event ledger
(`QUEUE_ROOT/observability/events.jsonl`), holds the work.json lock and the values only read, never
written (`WAIT_READ_ONLY`, `LEGACY_EVENT_TYPES`: house rule E9). `team.py` runs the runner teammate's
lifecycle and the gate ledger, `spec_maintainer.py` spec questions to the lead (the open-question
rule is `ccp/queue.py`'s, the headless launch `ccp/headless.py`'s), `architecture_review.py` the review kit the architect seat runs on (§19). The shell scripts are thin
single writers: `set-waiting-on.sh` (the only writer of `waiting_on`), `emit-event.sh`, `heartbeat.sh`,
`prune-prompts.sh`, `write-prompt-audit.sh`. The status is the board (`ccp board`, §28).

Every script takes `QUEUE_ROOT` (the runtime queue, outside product git) and answers `--help`; `OBS_NOW` pins the
clock for an example or a test. `heartbeat.sh <seat>` takes the seat ids of §18.3. An old ledger's rows of a seat
since retired (`LEGACY_ACTORS`) are read and never written. The timer formulas are SPEC §23.3 (`lib.py`'s docstring
repeats them); the contracts are `contracts/observability_event.schema.json` and `contracts/prompt_audit.schema.json`.
`prompts/` (the audit files) is never committed.
