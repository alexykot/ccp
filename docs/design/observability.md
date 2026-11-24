# Observability: implementation notes

Non-normative notes behind SPEC §23. The rules are in `docs/spec/04-observability.md`.

## Examples

A `phase` event's `from` and `to` are the SPEC §10.1 phase names, as the task's `progress/<task_id>.json` (`contracts/progress.schema.json`) records them.

#### Event log schema (`events.jsonl`)

One JSON object per line. Append-only; never rewrite history. Contract: `contracts/observability_event.schema.json`.

**Required fields:**

```json
{
  "at": "2026-09-18T07:34:39Z",
  "project_id": "example",
  "task_id": "0007-example-task",
  "actor": "task-runner|task-verifier|design-seat|adapter|operator|system|plane-session",
  "type": "phase|waiting_on|lease|claude|auth|seat|durable|note|question|spec_maintainer",
  "op": "set|clear|transition|launch|exit|heartbeat|reconcile|raised|answered|escalated|resolved_by_operator|rebound",
  "payload": {}
}
```

Seat ids are the three of §18.3: `task-runner`, `task-verifier` and `design-seat`; an old ledger may hold rows of a seat since retired, which are read and never written (`lib.LEGACY_ACTORS`). `task_id` may be empty on seat-only or project-level auth events.

#### The retired snapshot

The older snapshot (`now.json`, `STATUS.md`) and its scripts (`rebuild-now.sh`, `status.sh`) are
retired (SPEC §23.4, ADR-0034 D7): nothing writes or reads them, and an old copy left in a queue is
ignored. The board (`board/board.json`, built by `ccp board build`, §28) is the status, and
`ccp board status` its terminal summary.


#### Audit file schema

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

`prompts.keep_body` and `prompts.audit_keep_days` are constants (ADR-0043 D9): an audit holds the hash and the length, never
the body, and an `argv` entry that is the prompt itself reads `<prompt>`; every audit is kept (SPEC §23.8). A product that
still sets either key gets its value until it deletes the key, and `ccp upgrade status` lists it (SPEC §29.3):
`keep_body: true` keeps the body, and `audit_keep_days: N` has `ccp prompt` remove audits older than N days, by the stamp in
the file name, each time it writes one; the rendered prompt and env files beside them are not audits and stay. Health's
prompt sizes (§27.1) read `prompt_chars`, or the body's length in an audit from before it. `prune-prompts.sh` prunes on demand.

Health (§27) and the board's per-task drill-down (§28.3) read each audit's name stamp as a worker's
launch time: a task's prompt count and sizes, and the start of each phase's span. A pruned audit
drops out of both, so a task whose audits are pruned loses its launch times, and its spans fall back
to the previous phase's end. A product that still sets `audit_keep_days` keeps it above the longest life of a task, from its first
launch to its close, so no audit of a task still measured is pruned.


## Acceptance (plane-level)

1. `ccp board status` shows runtime against durable divergence until reconciled.
2. After a deliberate `waiting_on=quota` park with `resets_at`, the wait is a blocker of `ccp board status`; after clear, the wait interval closes.
3. `ccp tasks claim` and `close` write seat heartbeats; no seat is ever stale and no blocker comes from seat or verifier silence (§18.3).
4. One Runner Claude launch produces a `prompts/…json` with `prompt_sha256` (and `prompt_body` only under `prompts.keep_body`) and a matching `claude/launch` event `prompt_ref`.
5. Merging a task updates durable status or records an explicit reconcile event in the same session as merge.
6. No secrets in events, the board, prompts, or escalation email.

Items 1 and 4–5 need live Mac `QUEUE_ROOT` after merge. Plane CI / examples cover fold + emit + wait timers.

