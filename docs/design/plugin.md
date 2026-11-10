# The plugin and the product footprint: how they were built

Non-normative. The rules are SPEC §4.3, §5.7, §8.3 and §9.

## Why a plugin

A managed product used to hold many plane artefacts (managed copies of agent briefs, skills, hooks
and protocols, a vendored copy of `ccp` under `.control-plane/` for cloud agents, hook entries with
absolute plane paths in `.claude/settings.local.json`, plane paths restated in its own docs), each of
which had to move whenever the plane changed. A Claude Code plugin ships agents with pinned model and
effort, skills and hooks; a managed copy is a fork waiting to drift. The product keeps a static
anchor and its own records.

## Spike: what the plugin mechanism does

Tested headless (`claude -p --plugin-dir`) with a probe plugin:

- The Agent tool takes a plugin-scoped `subagent_type` (`cp-probe:probe-worker`); the worker ran on
  its pinned model (`claude-haiku-5-5`) under a different session model, per `modelUsage`.
- The plugin's SubagentStart and SubagentStop hooks fire. Their input carries the scoped agent type,
  `agent_id` and `session_id`; SubagentStop also carries `effort.level`, the effort the worker ran at
  (`effort.level: low`, as pinned).
- Plugin skills load (`cp-probe:probe-skill`).
- SessionStart `additionalContext` reaches the main session, not subagents.

With teammates, in an interactive agent-team session: a teammate of the plugin agent type spawned
and ran; the SubagentStart, SubagentStop and TeammateIdle hooks fired for it; for a teammate the hook
input's agent type is the teammate's name, not the plugin type (the idle hook matches on
`teammate_name`); the SessionStart context did not reach it.

## Implementation notes

- **Layout.** `plugin/` holds what used to be templates: `plugin/agents/delivery-*.md` (was
  `templates/claude-agents/`); `plugin/skills/architect/` (was `templates/claude-skills/architect/`);
  `plugin/skills/{spec-maintainer,review-triage,writing-tasks}/SKILL.md` (was
  `templates/docs-delivery/{SPEC-MAINTAINER,REVIEW-TRIAGE,WRITING-tasks}.md`); `plugin/orientation.md`
  (was `templates/docs-delivery/CONTROL-PLANE.md`); `plugin/hooks/` (was `templates/claude-hooks/`).
  `.claude-plugin/marketplace.json` names `./plugin`; `claude plugin validate` passes. The plugin has
  no `version`, so each commit on `main` is a version (Claude Code's rule), which is how "merged is
  released" reaches plugin users.
- **Agent types.** `ccp prompt` prints `ccp:<type>` and reads the expected model and effort
  from the plugin's definition, unless the product still has its own copy in `.claude/agents/`.
  `team.sh runner spawn` names the product's own runner type while it has the copy.
- **The project lookup.** A binding (`projects/*.yaml`) maps a product checkout to its queue;
  `ccp architect` and its triage use the product's own architect skill and
  `REVIEW-TRIAGE.md` while it has them, else the plugin's, and add `--plugin-dir` for headless runs.
  The lookup needs both a valid `project_id` and a binding whose `product_root` is this checkout or
  its main checkout, so a scratch clone or a fork naming a live project's id gets no queue.
  The test suite sets `CCP_NO_BINDING_QUEUE=1` and clears an inherited `QUEUE_ROOT` and
  `PROJECT_YAML` (`tests/__init__.py`), so no test reaches a live queue, even in a seat that
  exports one.
- **The checkout warning.** Every `ccp` call warns on stderr when its checkout has local changes to
  tracked files, is off `main`, or is behind its last-fetched `origin/main`; git runs with
  `--no-optional-locks`, and a head detached exactly at `origin/main` counts as `main`. `CCP_DEV=1`
  silences it.
- **The run checkout.** `scripts/run-checkout.sh install|update|status`: `install` clones the
  repository's origin to `CCP_RUN_CHECKOUT` (default: `control-plane-run` beside the clone's main
  worktree) and points the `ccp` symlink on PATH (`CCP_BIN_LINK`, default `~/.local/bin/ccp`) at it.
- **INDEX.** With `task_log.index: false`, `ccp tasks check` requires no index, no command writes
  one, and the plane's readers (`lib.load_durable_statuses` and the other readers in `lib.py` and
  `architect.py`; formerly `spec_maintainer.descendants` in `spec_maintainer.py`) read the task files.
  `render_index` is documented as frozen at its five fields; the extra fields (`merge_sha`,
  `done_at`, …) go to `board.json`.
- **The docs warning.** `ccp docs check` warns on tracked files matching
  `/control-plane(-run)?/(bin/ccp|scripts/|templates/|plugin/|projects/|SPEC.md)`, except under
  `docs/delivery/tasks/`, `docs/delivery/reviews/` and `.control-plane/`.
- **Sync in plugin mode.** A product whose settings enable `ccp@…` gets no managed copies;
  a sync removes copies carrying the managed-copy header (`--check` reports them as `retired`), never
  edits a `CLAUDE.md` import (it reports it for the product to remove), and reports settings hook entries that still
  call `.claude/hooks/` copies (`stale_hooks`), which would otherwise run twice.
- **The protocol doc.** `spec_maintainer.protocol_doc: plugin:ccp:spec-maintainer` resolved
  to the plugin's skill file while the headless maintainer existed.
- **Checked live.** A headless session with `--plugin-dir plugin`, in a product holding only
  `plane.json`, had the orientation and saw the four `ccp:` agent types and the four skills.
- **Fenced tests.** An early draft of the removed cloud-state work wrote `state/*` branches into the
  plane repository (`state/<project_id>`; a `state/demo` fixture was pushed before it was caught),
  which is why the tests are fenced from the real plane repository.

## Acceptance walk-through

1. A product with only the anchor, `plane.json` and its own docs runs a task end to end; the runner
   and its workers are the plugin's types; runs bind; events and reports are recorded.
2. A change in the development checkout (a branch, an uncommitted edit) changes nothing a product
   runs; after a merge and a pull of the run checkout, the next `ccp` call and session use it.
3. `ccp` warns when the run checkout is dirty, off `main`, or behind `origin/main`.
4. With `task_log.index: false`, `ccp tasks check` passes without an index.
5. `ccp docs check` warns on a plane checkout path in a product doc.
6. The runner spawns as the plugin's `ccp:delivery-runner` teammate, with the plugin's idle
   hook.
