# observability — the ledger, the snapshot and the seat scripts (SPEC §23, §17, §2)

`lib.py` is shared by `ccp` and every script here: it writes and folds the event ledger
(`QUEUE_ROOT/observability/events.jsonl`), builds the now.json snapshot and STATUS.md, holds the
work.json lock and the alias table for values renamed over time (old values are read, only new ones
written). `team.py` runs the runner teammate's lifecycle and the gate ledger, `spec_maintainer.py`
spec questions to the lead, `architecture_review.py` the review kit the architect seat runs on
(§19). The shell scripts are thin single writers: `set-waiting-on.sh` (the only writer of `waiting_on`), `emit-event.sh`,
`heartbeat.sh`, `rebuild-now.sh`, `status.sh`, `prune-prompts.sh`, `write-prompt-audit.sh`.
