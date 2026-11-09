# Queue

Live queue state lives **outside** product git (e.g. `$HOME/projects/.delivery-queue/<project_id>`). Durable intent lives in product `docs/`.

## Env

| Var | Meaning |
| --- | --- |
| `QUEUE_ROOT` | Absolute path to `.delivery-queue/<project_id>` |
| `PROJECT_ID` | Optional label (e.g. `example`) |
| `DURABLE_DOCS` | Optional path to product `docs/delivery` (git) |

## Expected layout (live)

```
<queue_root>/
  queue/pending|leased|implementing|implemented|reviewed|submitted|verifying|merging|done|blocked|failed/
  tasks/<task_id>.json
  progress/<task_id>.json
  results/<task_id>.json
  review/<task_id>.json
  questions/<task_id>/<n>.json          # implementation-class questions the Runner answers itself
  questions/sm-<UTC>-<hex>.json         # SPEC §17 spec-maintainer question (flat; raised via ../spec-maintainer-ask.sh)
  questions/sm-<UTC>-<hex>.answer.json  # spec-maintainer answer (contracts/question_answer.schema.json)
  architecture-review.json, docs-audit.json  # the retired aliases' state (§19.12): older queues only, read, never written
  architect.json                        # §19 architect state (last pass, per-report status, when each trigger was first seen)
  architect.lock                        # §19 architect-run lock
  reviews/<review_id>.json|.md|.triage.json  # §19 report, rendering, triage (durable record is product docs/delivery/reviews/)
  reviews/<review_id>.log               # §19 a detached architect run's output
  health/notes.jsonl                    # §27.2 friction notes (ccp health note)
  health/metrics.jsonl                  # §27.2 numbers: suite series from ccp report, others from ccp health record
  escalations/<task_id>/<n>.json
  verification/<task_id>.json
  artifacts/<task_id>/
  auth/status.json
  work.json
  running.json
  observability/events.jsonl
  observability/now.json
  observability/seats/<seat_id>.json
  prompts/<task_id>/          # Layer 2; never commit
```

## Operations

| Script | Purpose |
| --- | --- |
| `ccp tasks claim\|phase\|wait\|resume\|release\|drop\|close` | Every task-state change (SPEC §10.5): the lease, the phase, waits, and the ledger events |
| `../formal-submit.template.sh` | Unit/lint + PR + review artifact; no spec judgement |
| `../spec-maintainer-ask.sh` | SPEC §17 spec question: `raise`, `<qid>` (apply the lead's answer), `blocked` |

Contracts: `../../contracts/*.schema.json`.

Observability (SPEC §23): `../observability/` — `emit-event.sh`, `set-waiting-on.sh` (event **before** wait-field writes), `rebuild-now.sh`, `status.sh`. Waiting_on changes must go through `set-waiting-on.sh`.

## Rules

- Never store secrets in queue JSON or emails.
- `implementation_started_at` is set **once**; the wall timer does **not** reset on reject.
- Same-session `/mk-pr`: persist `claude_session_id` on the task before mk-pr/merge resumes.
- Seats stay idle when there is no durable pending task in product `docs/delivery/` + matching `tasks/*.json`.
