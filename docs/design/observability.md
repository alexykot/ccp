# Observability: implementation notes

Non-normative notes behind SPEC §23. The rules are in `docs/spec/04-observability.md`.

## Examples

A `phase` event's `from` and `to` are the phase or status names of `progress.schema` and the task status enum.

#### 20.1.2 Event log schema (`events.jsonl`)

One JSON object per line. Append-only; never rewrite history. Contract: `contracts/observability_event.schema.json`.

**Required fields:**

```json
{
  "at": "2026-09-18T07:34:39Z",
  "project_id": "example",
  "task_id": "0007-example-task",
  "actor": "task-runner|task-verifier|delivery-watchdog|adapter|operator|system",
  "type": "phase|waiting_on|lease|claude|auth|seat|durable|note|question|spec_maintainer",
  "op": "set|clear|transition|launch|exit|heartbeat|reconcile|raised|answered|escalated|resolved_by_operator|rebound",
  "payload": {}
}
```

Seat ids / actors for the three operational seats: `task-runner`, `task-verifier`, `delivery-watchdog`. `task_id` may be empty on seat-only or project-level auth events.

#### 20.1.3 Snapshot schema (`now.json`)

Regenerate by folding `events.jsonl` + live probes (`ps` for pid, `auth/status.json`). Contract: `contracts/observability_now.schema.json`. Writer: `scripts/observability/rebuild-now.sh`.

*Amended by §28.3: replaced by `board/board.json`, built by `ccp board build`.*

```json
{
  "schema_version": 1,
  "generated_at": "RFC3339",
  "project_id": "example",
  "queue_root": "/absolute/path",
  "auth": {
    "overall": "ok|degraded|expired",
    "checked_at": "RFC3339",
    "ambient_api_key": false,
    "failed_checks": []
  },
  "seats": {
    "<seat_id>": {
      "last_wake_at": "RFC3339|null",
      "wake_kind": "cron|priority|manual|null",
      "last_action": "string",
      "cron_expected": "*/30 * * * *|event",
      "stale": true
    }
  },
  "tasks": [
    {
      "task_id": "0007-example-task",
      "durable_status": "pending|…",
      "runtime_status": "implemented|…",
      "phase": "review|…",
      "waiting_on": "quota|null",
      "waiting_on_since": "RFC3339|null",
      "planned_resume_at": "RFC3339|null",
      "quota_class": "session|credit|null",
      "implementation_started_at": "RFC3339|null",
      "wall_hours": 47.4,
      "work_hours": 0.0,
      "wait_hours": 0.0,
      "pr_url": "…",
      "head_sha": "…",
      "running_pid": null,
      "running_pid_alive": false,
      "lease_holder": "…",
      "prompt_last_ref": "prompts/…/….json|null"
    }
  ],
  "blockers": [
    {
      "task_id": "…",
      "kind": "quota|reauth|operator_decision|spec_maintainer|stale_seat|verify_stale|ambient_key|other",
      "since": "RFC3339",
      "detail": "…"
    }
  ],
  "questions": [],
  "spec_maintainer": null,
  "totals": {
    "tasks_active": 1,
    "tasks_done": 1,
    "tasks_blocked": 1,
    "open_blockers": 1
  }
}
```


#### 20.2.2 Audit file schema

Contract: `contracts/prompt_audit.schema.json`.

```json
{
  "schema_version": 1,
  "at": "RFC3339",
  "project_id": "example",
  "task_id": "0007-example-task",
  "phase": "implement|fix-review|mk-pr|review|spec-maintainer|…",
  "actor": "task-runner",
  "session_id": "uuid|null",
  "resume": false,
  "argv": ["claude", "-p", "…"],
  "env_stripped": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN"],
  "wallet": "prepaid_oauth",
  "git_head": "sha",
  "worktree": "/path",
  "durable_task_path": "docs/delivery/tasks/….md",
  "spec_refs": ["…"],
  "prompt_body": "FULL TEXT given to Claude",
  "prompt_sha256": "…",
  "notes": "optional"
}
```


## 20.4 Acceptance (plane-level)

1. `status.sh` on Mac shows 0001/0002/0003 with correct runtime vs durable divergence until reconciled.
2. After a deliberate `waiting_on=quota` park with `resets_at`, `now.json` shows `wait_hours` increasing and `planned_resume_at` set; after clear, wait interval closes.
3. Watchdog wake writes seat heartbeat; forcing staleness (past the seat threshold with mid-flight task) surfaces `stale_seat` blocker; a `submitted` task with no verdict/Verifier progress for ≥30m surfaces `verify_stale`.
4. One Runner Claude launch produces a `prompts/…json` with non-empty `prompt_body` and a matching `claude/launch` event `prompt_ref`.
5. Merging a task updates durable status or records an explicit reconcile event in the same session as merge.
6. No secrets in events, `now.json`, prompts, or escalation email.

Items 1 and 4–5 need live Mac `QUEUE_ROOT` after merge. Plane CI / examples cover fold + emit + wait timers.

