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

#### 20.1.3 The retired snapshot

The older snapshot (`now.json`, `STATUS.md`) and its scripts (`rebuild-now.sh`, `status.sh`) are
retired (SPEC §23.4, ADR-0034 D7): nothing writes or reads them, and an old copy left in a queue is
ignored. The board (`board/board.json`, built by `ccp board build`, §28) is the status, and
`ccp board status` its terminal summary. The deprecated `contracts/observability_now.schema.json`
records the snapshot's shape.


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
  "prompt_sha256": "…",
  "prompt_chars": 1234,
  "prompt_body": "the full text, only when plane.json prompts.keep_body is true",
  "notes": "optional"
}
```

`prompt_body` is opt-in (`prompts.keep_body`, default false; ADR-0034 D8): without it the audit holds
the hash and the length, and an `argv` entry that is the prompt itself reads `<prompt>`. Health's
prompt sizes (§27.1) read `prompt_chars`, or the body's length in an audit from before it.
`prompts.audit_keep_days` (default null, keep all) has `ccp prompt` remove audits older than that
many days, by the stamp in the file name, each time it writes one; the rendered prompt and env
files beside them are not audits and stay. `prune-prompts.sh` prunes on demand.


## 20.4 Acceptance (plane-level)

1. `ccp board status` shows runtime against durable divergence until reconciled.
2. After a deliberate `waiting_on=quota` park with `resets_at`, the wait is a blocker of `ccp board status`; after clear, the wait interval closes.
3. `ccp tasks claim` and `close` write seat heartbeats; no seat is ever stale and no blocker comes from seat or verifier silence (§18.3).
4. One Runner Claude launch produces a `prompts/…json` with `prompt_sha256` (and `prompt_body` only under `prompts.keep_body`) and a matching `claude/launch` event `prompt_ref`.
5. Merging a task updates durable status or records an explicit reconcile event in the same session as merge.
6. No secrets in events, the board, prompts, or escalation email.

Items 1 and 4–5 need live Mac `QUEUE_ROOT` after merge. Plane CI / examples cover fold + emit + wait timers.

