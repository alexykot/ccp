# observability — the ledger and the seat scripts (SPEC §23, §17, §2)

`lib.py` is shared by `ccp` and every script here: it writes and folds the event ledger
(`QUEUE_ROOT/observability/events.jsonl`), holds the work.json lock and the values only read, never
written (`WAIT_READ_ONLY`, `LEGACY_EVENT_TYPES`: house rule E9). `team.py` runs the runner teammate's
lifecycle and the gate ledger, `spec_maintainer.py` spec questions to the lead (the open-question
rule is `ccp/queue.py`'s, the headless launch `ccp/headless.py`'s), `architecture_review.py` the review kit the architect seat runs on (§19). The shell scripts are thin
single writers: `set-waiting-on.sh` (the only writer of `waiting_on`), `emit-event.sh`, `heartbeat.sh`,
`prune-prompts.sh`, `write-prompt-audit.sh`. The status is the board (`ccp board`, §28).
