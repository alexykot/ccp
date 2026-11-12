# Design notes: the agent team (runner, lead, workers)

Non-normative. The rules are SPEC §10–§18; these notes record what the design rests on and how to
check it end to end.

## Agent-team limits the design rests on

- Teammates cannot spawn teammates; only the lead's Agent tool can, so `team.sh runner spawn` only
  records and prints the call, and the lead makes it verbatim (the prompt audit then matches what was
  sent).
- In-process teammates are not restored by `/resume`, and `-p` sessions cannot spawn teammates: a
  resumed lead respawns its runners (SPEC §10.2 step 5).
- Teammate permission prompts surface in the lead's session (SPEC §18.5).
- A message from another agent is never treated as the user's consent (SPEC §17.9 *Harness limits*).
- A teammate's own subagents do not report back in the foreground: the Agent call returns at once and
  the handback lands in the lead. So workers report by `SendMessage` to their runner plus a report
  file through `ccp report` (SPEC §13.4).
- A teammate's Agent call blocks until its worker ends, and an in-process teammate cannot start
  background agents: one runner runs one worker at a time, which is why parallel work is several
  runners (SPEC §16).

## Implementation notes

- **Implementers never merge.** The harness refused implementer merges as "merge without review"
  while the runner's own merges went through; the runner merges (SPEC §10.2).
- **The hook ignores the runner's subagents and logs its inputs** (SPEC §18.2), and
  `spec-maintainer-ask.sh raise` refuses `--blocks` entries that are not task ids: a comma-split
  sentence once became `work.json`'s `task_id`.
- **Models and effort** are pinned per agent definition (SPEC §2); before that, a runner with
  `model: inherit` and untyped general-purpose workers ran every seat on the lead's model, effort and
  context window. The headless reviewers take `architecture_review.HEADLESS_MODEL` 
  (`--model claude-opus-5-5 --effort high`).
- **A shadowed name.** In `architecture_review.py` `triage()`, a local `kind` once shadowed the review
  `Kind` parameter, so every triage path past it raised `AttributeError`; the owner's kind is now
  `owner`.
- **The hook reads its input from the environment.** Its body is a Python heredoc, which takes stdin,
  so the bash wrapper reads the hook JSON first and passes it as `HOOK_INPUT`. The hook ships with
  the plugin; a product that installed a copy at `.claude/hooks/runner-idle.sh` keeps it working.
- **Rotation names.** While the old teammate still holds the name, the harness gives the fresh one a
  suffixed name (`runner-2`); a spawn records the binding's `runner.name` and the bind records the
  name the harness gave into `work.json` (single runner: `runner`, with `runner_tasks_done: 0` at
  spawn). When a rotation is due (SPEC §10.2 step 4: `tasks_done ≥ rotate_after_tasks`, or the latest
  request context at `rotate_at_context_tokens`), `ccp tasks claim` refuses the slot a new task
  (`lifecycle.rotation_due`) until `team.sh runner rotate` records the rotation; `ccp health` lists
  the due slot.
- **The usage-limit wake.** When a session limit is hit, the runner's idle notice fails, the lead's
  own turn on that notice fails on the same limit, `TeammateIdle` does not fire on a failed idle, and
  `autoContinueAtUsageLimit` does not resume the lead. So the wake is armed before the limit, while
  the lead can still act, at the window's actual reset plus a margin (SPEC §18.4).
- **Board seats.** Under the agent team (`claude-team` in older records) every seat is event-only
  (SPEC §18.3).

## Acceptance checks (walkable)

1. The lead spawns `runner` from its agent type; `events.jsonl` shows `runner`/`spawn` with a prompt
   audit.
2. The runner completes one task end to end; its queue files match the queue shape field for field.
3. A spec question raised by the runner is answered by the lead, committed as `spec(<qid>): …`, and
   applied by `spec-maintainer-ask.sh process` without launching Claude.
4. An operator step not covered by a standing approval produces an escalation file; the runner waits;
   the lead closes it with `decided_by` and `authority`; the runner proceeds.
5. The `TeammateIdle` hook keeps a runner working when an in-scope task is ready, and lets it go idle
   when the only ready tasks wait on the lead.
6. Resuming the lead, then asking it to continue, respawns a runner that picks up a mid-flight task at
   its recorded phase.
