---
task_id: 0175-one-binding-reader
title: One module resolves and parses a product's binding, and the binding schema is readable
status: pending
kind: refactor
depends_on: []
spec_refs: ["S8"]
review_refs: ["sh-20261119T170325Z-8142#F07"]
rule_refs: ["E17"]
review_point: R12
paths: ["scripts/observability/lib.py", "scripts/observability/spec_maintainer.py", "ccp/cli.py", "ccp/init.py", "ccp/otel.py", "ccp/queue.py", "ccp/seats.py", "ccp/upgrade.py", "ccp/lifecycle.py", "ccp/usage.py", "scripts/sync-product-docs.sh", "contracts/project.schema.json", "tests/test_binding_reader.py"]
adopt: "none"
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0175-one-binding-reader

## Intent

Every reader of a product's binding resolves it and parses it through one module, so when ADR-0043
removes most of the binding's keys (0188) the change touches one parser, and the binding schema is
written on several lines so its diff can be read. Nothing the plane does changes.

## Context (not checked)

- Shape `sh-20261119T170325Z-8142`, finding F07 and preparatory refactor P4; house rule E17 (added in
  this triage).
- The parsers, `git grep -nP "def (binding_file|binding_queue_root|binding_scalar|binding_runner_name|_binding_block|binding_keys)\b|def _scalar\(text" -- ccp scripts`
  at `e9ff0fc`: 10 lines: `ccp/cli.py` (`binding_file`, `_scalar`, `binding_queue_root`),
  `ccp/init.py` (`_scalar`), `ccp/otel.py` (`_scalar`), `ccp/queue.py` (`binding_scalar`,
  `binding_runner_name`), `ccp/seats.py` (`_binding_block`), `ccp/upgrade.py` (`binding_keys`),
  `scripts/observability/spec_maintainer.py` (`binding_queue_root`). The shape counts six; the two
  further `_scalar` copies in `init.py` and `otel.py` read the binding too. `ccp/adr.py`'s `_scalar`
  reads ADR frontmatter and is not a binding reader.
- Inline regex readers besides those functions,
  `git grep -nP 're\.(search|match)\(r?f?"\^(queue_root|product_root|project_id|integration_branch|runner)' -- ccp scripts ':(exclude)scripts/observability/lib.py'`
  at `e9ff0fc`: 6 lines: `ccp/lifecycle.py` (`runner.worktree`), `ccp/queue.py` (`runner.name`),
  `ccp/usage.py` (`product_root`, `runner.worktree`), `scripts/observability/spec_maintainer.py`
  (`project_id`, `product_root`). The shape does not list these; they move too.
- Two resolutions exist and both stay, in the one module: by queue (`lib.binding_path(root)`:
  `PROJECT_YAML`, else the binding whose `queue_root` is the queue, else the retired queue copy) and by
  product (`cli.binding_file(cfg)`: `PROJECT_YAML`, else `<bindings>/<project_id>.yaml`, each only when
  its `product_root` is this checkout or its main checkout). Their rules are unchanged.
- Decided here: the module is `scripts/observability/lib.py`, which `ccp` already imports
  (`from ccp.queue import lib`). It gains `read_binding(text) -> dict` (the nested parser
  `upgrade.binding_keys` has today, moved; scalars as strings, blocks as dicts, list items not read)
  and `product_binding(project_id, roots) -> Path | None` (the by-product resolution, moved from
  `cli.binding_file`). Every reader above calls `binding_path` or `product_binding`, then
  `read_binding`, and reads its key from the dict; the regexes go. `lib._yaml_block_scalars` and
  `lib.project_seat_agent` read through `read_binding` too.
- `scripts/sync-product-docs.sh` reads the binding's `spec_maintainer` block by regex for an old-shape
  note; it imports `lib` and uses `read_binding` too.
- `contracts/project.schema.json` is one line of 6858 bytes at `e9ff0fc` (`wc -lc`); it is rewritten
  with two-space indentation, its content unchanged.
- No SPEC change: §8.3 already says every reader resolves through one resolver; this makes it true for
  parsing as well (`git grep -n "one resolver" -- docs/spec` at `e9ff0fc`: one line, §8.3).

## Scope

- **In:**
  - `scripts/observability/lib.py`: `read_binding`, `product_binding`; `binding_path` unchanged.
  - The readers listed above, and `scripts/sync-product-docs.sh`, through them; the regex parsers
    removed.
  - `contracts/project.schema.json`: indented, the same JSON.
  - `tests/test_binding_reader.py` (new): `read_binding` on a binding with scalars, a block, a comment
    and a list; both resolutions on a fenced bindings directory (`CCP_BINDINGS_DIR`).
- **Out:**
  - Removing any binding key (0188), and the schema's `required` list.

## dod_checks

- id: `bind-01`
  story: As a plane developer, one module parses the binding.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -nP "def (binding_file|binding_queue_root|binding_scalar|binding_runner_name|_binding_block|binding_keys)\b|def _scalar\(text" -- ccp scripts`.
    2. Run `git grep -nP 're\.(search|match)\(r?f?"\^(queue_root|product_root|project_id|integration_branch|runner)' -- ccp scripts ':(exclude)scripts/observability/lib.py'`.
  expect: step 1 prints nothing outside `scripts/observability/lib.py`; step 2 prints nothing.
  dry run (`e9ff0fc`): step 1 printed the 10 lines listed in Context; step 2 printed the 6 lines listed in Context (the positive the check removes).
- id: `bind-02`
  story: As a plane developer, the binding schema reads line by line and says the same.
  setup: a checkout of the PR head.
  steps:
    1. Run `wc -l contracts/project.schema.json`.
    2. Run `python3 -B -c "import json, subprocess; a=json.loads(subprocess.check_output(['git','show','origin/main:contracts/project.schema.json'])); b=json.load(open('contracts/project.schema.json')); print(a==b)"`.
  expect: step 1 prints more than 50 lines; step 2 prints `True`.
  dry run (`e9ff0fc`): step 1 printed `1`; step 2 printed `True` (the same file).
- id: `bind-03`
  story: As a plane developer, every binding reader behaves as before, and the new tests bite.
  setup: a checkout of the PR head; then a separate copy where `read_binding` drops block keys.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_binding_reader tests.test_init tests.test_suite tests.test_upgrade tests.test_board_seats tests.test_team_hosting`.
    2. In the copy, run `python3 -B -m unittest -q tests.test_binding_reader tests.test_upgrade`.
  expect: step 1 exits 0; step 2 exits non-zero.
  dry run (`e9ff0fc`): step 1's existing modules pass at the base; `tests.test_binding_reader` is new.

## Implementation notes

*Append-only, newest last.*

## Verification notes
