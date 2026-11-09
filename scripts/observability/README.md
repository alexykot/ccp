# Observability scripts (Layers 1+2)

The event ledger and the prompt audit. Live state lives under `$QUEUE_ROOT/observability/` — **outside** product git.
The status is the board (`ccp board status|build`, SPEC §23.4, §28). Retired: the older snapshot
(`now.json`, `STATUS.md`; one left in a queue is ignored) and its scripts (`rebuild-now.sh`, `status.sh`).

Example:

```bash
export QUEUE_ROOT="$HOME/projects/.delivery-queue/example"
```

Plane scripts (this directory) can be invoked in-place from a control-plane clone, or copied beside the queue.

## Layout (runtime)

```
$QUEUE_ROOT/
  observability/
    events.jsonl          # canonical append-only ledger
    seats/<seat_id>.json  # each seat's last wake (heartbeat.sh)
  prompts/<task_id>/<UTC>_<phase>.json   # Layer 2 audit; NEVER commit
  auth/status.json
  work.json
  tasks/<task_id>.json
  running.json
```

Seat ids (match actor enum): `task-runner`, `task-verifier`, `delivery-watchdog`.

## Scripts

| Script | Purpose |
| --- | --- |
| `emit-event.sh` | Append one JSONL event. `mkdir -p` as needed. |
| `set-waiting-on.sh` | **Event first**, then `work.json` / `tasks/*.json` wait fields. `--task-only` leaves `work.json` alone unless it names the task (`ccp tasks sync`). |
| `heartbeat.sh` | Write `seats/<id>.json` + `seat/heartbeat` event (every wake). |
| `write-prompt-audit.sh` | Layer 2 file; prints `prompt_ref` for `claude/launch`. |
| `prune-prompts.sh` | Optional retention. **Default off** (alpha keep-all). |
| `spec_maintainer.py` | SPEC §17 logic behind `../spec-maintainer-ask.sh` (question file, waits, answer validation and application); also the headless-`claude -p` helpers the architect and reviews use |

Every script accepts `-h` / `--help`.

```bash
export QUEUE_ROOT="$HOME/projects/.delivery-queue/example"
export PROJECT_ID=example
export ACTOR=task-runner

./emit-event.sh --type phase --op transition --task-id 0002-s1-llm-mcp-chat \
  --payload '{"from":"leased","to":"implementing"}'

./set-waiting-on.sh set 0002-s1-llm-mcp-chat quota \
  --quota-class session --resets-at 2026-09-18T12:00:00Z --detail "session limit"

./heartbeat.sh delivery-watchdog --wake-kind cron --action "auth-check + rebuild"

REF=$(./write-prompt-audit.sh --task-id 0002-s1-llm-mcp-chat --phase implement --prompt-file /tmp/prompt.txt)
./emit-event.sh --type claude --op launch --task-id 0002-s1-llm-mcp-chat \
  --payload "{\"phase\":\"implement\",\"prompt_ref\":\"$REF\"}"

ccp board status; echo exit=$?
```

The plane's own queue (it manages its own development) is the live reference.

## Spec questions (SPEC §17)

The runner raises a spec question; the team lead answers it in its own session and writes the
answer file; `process` applies it.

| Piece | Where |
| --- | --- |
| Event types | `question` (`raised`, `answered`, `escalated`, `resolved_by_operator`). `spec_maintainer` (`set`, `clear`, `rebound`) rows are historical (the removed headless maintainer's lock) and are read past. |
| Wait reason | `spec_maintainer` (`set-waiting-on.sh set <task> spec_maintainer --detail <question_id>`); a question escalated to the operator uses `operator_decision` with the same `--detail`. Blocker kinds `spec_maintainer` / `operator_decision` (detail = `question_id`). |
| Board | an open question, like a wait or an open gate, is a blocker of `ccp board status` (SPEC §23.4). |
| Runtime files | `QUEUE_ROOT/questions/sm-*.json` (+ `.answer.json`) |

The timer formula below is unchanged; the ledger fold in `lib.py` also splits the same wait intervals by reason.

```bash
export QUEUE_ROOT=… PROJECT_YAML=…/projects/<project_id>.yaml
../spec-maintainer-ask.sh raise --raised-by task-runner --task-id <id> --text "…" --inconsistency "…" --spec-refs '["docs/SPEC.md#…"]'
../spec-maintainer-ask.sh <question_id>        # apply the lead's answer (or re-print the lead message)
../spec-maintainer-ask.sh blocked --task-id <id>
```

## Timer formula (LOCKED — keep stable)

Chosen definition (interval, as SPEC prefers — not `wall − wait`):

| Field | Formula |
| --- | --- |
| `wall_hours` | `now − implementation_started_at` (null if never started); **does not reset**. A diagnostic, gating nothing. |
| `wait_hours` | Sum of `waiting_on` **set → clear** intervals, plus the open interval if currently waiting. |
| `work_hours` | Sum of intervals where **all** of: (1) `phase` ∈ work phases, (2) `waiting_on` is null, (3) a Claude launch is open (`claude/launch` without a later `claude/exit`). |

**Work phases:** `implement`, `implementing`, `mk_pr` / `mk-pr`, `review`, `fix-review`, `verify` / `verifying`, `merge` / `merging`.

Do **not** redefine `work_hours` as `wall − wait` without a SPEC change. That would count env-up / idle mid-flight time as work and hide the “47h wall / little Claude” problem this board exists to show.

Pin the clock with `OBS_NOW=2026-09-18T08:00:00Z` for examples / tests.

## Single-writer (`waiting_on`)

Any seat that changes wait state **must** use `set-waiting-on.sh` (or emit `waiting_on` set/clear **before** mutating `work.json` / task JSON). Last event wins.

Structured quota fields (`quota_class`, `resets_at` / `planned_resume_at`) beat prose-only emails. Watchdog Wake B: skip quota only while `planned_resume_at` is still in the future; after reset (or >2h with no timestamp) wake Runner on the first 30m tick at/after it — do not skip forever.

## Auth precedence (do not SIGTERM live prepaid Claude)

Failed ADC (or other unused checks) → emit `auth/transition`, escalate without secrets. **Do not** set `waiting_on=reauth` and SIGTERM a live prepaid implement/review session unless that session needs the failed credential. Park only when the next required step needs it.

Ambient product API key → `auth.ambient_api_key=true`, overall at best `degraded`, launches stay prepaid-stripped (`env -u ANTHROPIC_API_KEY …`).

## Seat liveness

Heartbeat files on disk record each seat's last wake.

**Cadence (2026-09-24):** Watchdog `*/30 * * * *` 24/7; Task Verifier **event-only** (`cron_expected: event`, no routine); Runner unchanged (`*/10` default). `heartbeat.sh` defaults `--cron-expected` per seat.

**No stale rule (SPEC §18.3):** every seat is event-only and never time-stale. Heartbeats still record each seat's last wake (`ccp tasks claim` and `close` write them), but nothing raises a seat-stale or verify-stale blocker. The binding's `cadence` verify-stale threshold is accepted and ignored.

## Layer 2 prompt audit

Before every plane-owned `claude -p` / `--resume` / `/mk-pr` / `/review`:

1. `write-prompt-audit.sh` → `prompts/<task_id>/<UTC>_<phase>.json` with full `prompt_body` + `prompt_sha256`.
2. `emit-event.sh --type claude --op launch` with that relative `prompt_ref`.

Never commit `prompts/` to product git or this repo. `prune-prompts.sh` exists but stays off until the operator says prune (`PRUNE_PROMPTS=1` + `--apply`).

## Secrets

Refuse API keys, ADC tokens, `.env` contents in events, prompts, the board, and escalation email. `emit-event.sh` / `write-prompt-audit.sh` reject secret-like values.

## Contracts

- `contracts/observability_event.schema.json`
- `contracts/observability_now.schema.json` (deprecated: the retired snapshot's shape)
- `contracts/prompt_audit.schema.json`

SPEC: §23 Observability.
