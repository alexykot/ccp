---
task_id: 0027-ccp-init
renamed_from: 0027-cpl-init
title: ccp init scaffolds a product and writes its binding from one source of truth
status: pending
kind: feature
depends_on: ["0026-readme-homepage"]
spec_refs: ["S4", "S8"]
review_point: R1
paths: ["ccp/", "scripts/team.sh", "scripts/observability/lib.py", "docs/spec/01-model.md", "docs/cli/", "README.md", "tests/"]
created: 2026-11-06
updated: 2026-11-06
---

# Task: 0027-ccp-init

## Intent

A new user adopts a product with one command. `ccp init` run in a product's repository writes the
product footprint (§4.3) and the local binding and queue (§8.3), and every reader of the binding
sees the same values. The README's manual adoption steps shrink to that command.

## Context (not checked)

- Today the binding has two homes: `ccp where` and `ccp` resolve `$PLANE/projects/<id>.yaml`, while
  `team.sh`, `ccp/queue.py`'s binding readers and `ccp/verify.py` read `PROJECT_YAML` or
  `QUEUE_ROOT/project.yaml`. The README tells the user to copy one to the other, which drifts after
  an edit.
- Either the queue copy is written and refreshed by `ccp` from the plane binding (on `init` and
  whenever `ccp` resolves a binding newer than the copy), or every reader goes through one resolver
  and the copy is retired. The implementer picks one, records it in §8.3, and says which in the PR.
- Standing ruling from the lead for R1: when a task carries out an operator ruling recorded in
  docs/spec/RULINGS.md that names the task, the implementer also removes or rewords, in the same PR
  and without asking, every SPEC/docs passage the change makes false, listing each edit with its old
  text in the PR body's "Operator approval (SPEC S31)" section and citing the RULINGS row. Ask only
  when an edit would change a rule the row does not cover, or when no row names the task. History
  records stay as written.
- Ruling sm-20261110T010828Z-0e49 (2026-11-10), in PR #10: (1) §4.5 "Adopting a product" becomes the
  `ccp init` path: the command, what it writes, and the manual steps only as what init does, not as a
  second procedure. (2) §4.3's anchor example and the `CLAUDE.md` line match exactly what `ccp init`
  writes; there is one source for both, and the README quotes the same text. (3) §8.3's single
  resolver, with the queue copy of the binding retired, is confirmed: it is the task's own scope.
  (4) Keeping existing files is fine as long as every dod_check passes as written; where a check
  expects a refusal without `--force`, the check wins. (5) The `plugin/hooks/runner-idle.sh` edit is
  accepted if it only follows the binding-source change; the PR body lists it as outside the declared
  paths. No RULINGS row names this task, so these § edits need the operator's GitHub review approval
  (§31) before the merge.

## Scope

- **In:** `ccp init [--project-id ID] [--queue-root DIR] [--integration-branch B] [--gate CMD] [--force]`:
  copies `templates/docs-project/{PROJECT,SPEC}.md` and the delivery templates, writes a minimal
  `plane.json`, adds `.plane-runtime/` to `.gitignore`, merges the plugin anchor into
  `.claude/settings.json` (never overwriting other keys), appends the one `CLAUDE.md` line once,
  writes the binding and creates the queue; refuses to overwrite existing files without `--force`;
  the single source of truth for the binding; §8.3 and `docs/cli/` updated; the README quick start
  uses `ccp init`.
- **Out:** remote marketplace setup; the hosted store (§29).

## dod_checks

- id: `init-01`
  story: As a new user, I adopt an empty repository with one command.
  setup: a scratch `HOME`, a clone of the PR head, an empty git repository.
  steps:
    1. Run `ccp init --project-id demo` in the repository.
    2. Run `ccp tasks check`, `ccp docs check` and `ccp where`.
  expect: the footprint files exist; the checks pass; `ccp where` prints the binding and the queue.
  dry run: n/a — `ccp init` does not exist yet.
- id: `init-02`
  story: As an operator, a binding edit reaches every reader.
  setup: the repository from `init-01`.
  steps:
    1. Change `runner.name` to `steward` in the binding `ccp where` names.
    2. Run `QUEUE_ROOT=<queue> scripts/team.sh runner spawn --scope <a task>`.
  expect: the printed spawn asks for the name `steward`.
  dry run: n/a — without a manual copy, `team.sh` still reads the old queue copy.
- id: `init-03`
  story: As a user with an existing setup, `init` does not clobber my files.
  setup: a repository with its own `.claude/settings.json` holding another key, and a `CLAUDE.md`.
  steps:
    1. Run `ccp init --project-id demo` twice.
  expect: the other settings key survives; the `CLAUDE.md` line appears once; existing docs are not
    overwritten without `--force`.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-10 (implementer): binding design: **one resolver, the queue copy retired**. `lib.binding_path`
  (scripts/observability/lib.py) is the resolver: `PROJECT_YAML` when it names a file, else the binding
  in `lib.bindings_dir()` (`CCP_BINDINGS_DIR`, else `<plane>/projects`) whose `queue_root` is the queue,
  else a leftover `QUEUE_ROOT/project.yaml` (read only when no binding names the queue, E9). Every
  binding reader goes through it: `lib.project_yaml_text` and `resolve_durable_docs_dir` (so
  `team.sh`, `queue.binding_*`, `spec_maintainer.py`), `verify._ci`, `otel.bindings_dir`, `cli.binding_file`
  and `binding_queue_root`; `ccp where` gains `binding`; `plugin/hooks/runner-idle.sh` reads the
  binding `ccp where` names in plugin mode (outside the declared paths: it read the queue copy
  directly). Recorded in SPEC §8.3.
- `ccp init` (ccp/init.py): keeps every existing file unless `--force` and lists it as kept, so a rerun
  or a rerun after a binding edit changes nothing; refuses (exit 2, nothing written) on a plane.json
  naming another id, a binding for the id naming another product root, a kept binding naming
  another `--queue-root`, or settings that are not a JSON object. The project id defaults to
  plane.json's, else the directory name. It also writes `INDEX.yaml` (task_log.index defaults on) and
  merges `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, as the README's manual steps did. The anchor and
  the `CLAUDE.md` line follow the README (marketplace `ccp`), not SPEC §4.3's example; see the report.
- 2026-11-10 (implementer, round 2, ruling sm-20261110T010828Z-0e49): SPEC §4.5 now describes `ccp init`
  and what it writes, keeps and refuses; §4.3's anchor example gains the `ccp` marketplace key and the
  agent-team `env` entry, and its `CLAUDE.md` line is the one init writes. `ccp/init.py` holds the one
  source (`ANCHOR`, `CLAUDE_LINE`); the README's step 2 quotes both, and `tests/test_init.py` checks
  that SPEC §4.3 and the README quote them exactly. init-01..init-03 walked in scratch directories:
  each passes as written, and none expects a refusal, so the keep-existing-files behaviour stays.

## Verification notes

*Append-only.*
