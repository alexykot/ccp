---
task_id: 0175-one-binding-reader
title: One module resolves and parses a product's binding, and the binding schema is readable
status: done
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
- Ruling `0175-one-binding-reader-r1` from the lead (verbatim): Accepted: differences (a)-(e) in how a
  hand-edited binding is read (whole value rather than first word; a comment needs ' #'; the last
  repeated key wins; only direct children of a block; 'key: # comment' opens a block) are forced by
  E17's one parser, and none affects a binding ccp init writes. Behaviour on init-written bindings stays
  unchanged, which is what the refactor rule protects. State these differences in the task's
  Implementation notes (list them: the review report's finding 1 at
  progress/0175-one-binding-reader/review-report.md in the queue
  names them). MINOR 2 (the second parser _parse_simple_yaml_scalar_map in
  scripts/observability/lib.py, used by resolve_durable_docs_dir; read durable_docs, product_root,
  durable_docs_path through binding_str(read_binding(text), ...) and delete it, keeping or dropping the
  legacy product-named root key deliberately and saying which) and NIT 4 (ccp/init.py refusal wording: readers
  now cut only at ' #') are fixed in this round. MINOR 3 (runner-idle.sh, run-checkout.sh) is out of
  paths; the lead files a follow-up. Also add the ruling to the task file's Context (not checked)
  section.

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

- Premises re-run at `052f9b3`: step 1 printed the 10 lines and step 2 the 6 lines the Context lists;
  `contracts/project.schema.json` was 1 line, 6858 bytes. No figure changed.
- `scripts/observability/lib.py` gained `read_binding` (the `upgrade.binding_keys` parser, moved; a
  scalar's surrounding quotes are dropped, as every regex reader did), `binding_str(data, *path)` (the
  scalar at a path, or None for a gap or a block), `binding_data(queue)` (`binding_path` then
  `read_binding`), `binding_runner_name(queue)` (default `runner`) and `product_binding(project_id, roots)`.
  `binding_path` keeps its three rules; it reads each candidate's `queue_root` through `read_binding`.
  `_yaml_block_scalars` is `read_binding` too: the strings directly under the block.
- `cli.binding_file` and `cli.binding_queue_root` are now `cli.product_binding(cfg)` (the id check and the
  checkout roots, then `lib.product_binding`) and `cli.product_queue_root(cfg)`: bind-01 forbids the old
  names outside `lib.py`. `queue.binding_scalar`, `queue.binding_runner_name` and `queue.binding_text`
  went; callers use `lib.binding_str(lib.binding_data(q), ...)`. The `spec_maintainer.py` function that
  asks `bin/ccp where` for the queue (no parsing) is renamed `where_queue_root` for the same reason.
- Two readers the task did not list went through the parser too, being binding regexes in the same
  modules: `queue._sanctioned_scripts` (`auth_check.script`) and `verify._ci` (`ci`).
- Left alone, outside the task's paths: `plugin/hooks/runner-idle.sh` (a block parser of its own, a
  plugin hook) and `scripts/run-checkout.sh` (shell `sed` for top-level scalars).
- A value is now read whole: `spec_maintainer.product_root` and `project_id` took the first word before,
  `otel` and `usage` cut at any `#` and now cut at ` #` (`ccp init` refuses a `#` in the paths it writes).
- `tests/test_suite.py` patches `ccp.cli.product_queue_root`, `tests/test_init.py` calls
  `lib.binding_runner_name`: renames only. `tests/test_board_seats.py` gained one test (the runner row
  reads the binding's `runner` block).
- `contracts/project.schema.json`: `json.dumps(indent=2)` of the same object, 305 lines.
- Ruling r1. The differences from the old readers, on a hand-edited binding only (none on a binding
  `ccp init` writes), accepted by the lead as forced by the one parser:
  (a) a value is read whole: `spec_maintainer.py` `project_id`/`product_root` and
  `sync-product-docs.sh` took the first word before;
  (b) a comment needs ` #`: `otel`, `usage`, `queue`, `lifecycle` and `seats` cut a value at any `#`;
  (c) a repeated key: the regex readers took the first, `read_binding` takes the last;
  (d) a block's scalars are its direct children only: `_yaml_block_scalars` (behind `team.runner_cfg`,
  `lifecycle.rotation_knobs`, init's `lead`, `project_seat_agent`) and `seats` read any depth;
  (e) `key: # comment` opens a block: the `lifecycle`/`usage`/`queue` `runner` regexes needed
  `runner:` then a newline.
- Ruling r1, MINOR 2: `lib._parse_simple_yaml_scalar_map` is gone; `resolve_durable_docs_dir` reads
  `durable_docs` (and `durable_docs_abs`), `product_root` and `durable_docs_path` with
  `binding_str(read_binding(text), ...)`. A legacy product-named root key was kept as a fallback at
  first; it was removed after merge because its name broke the no-product-specifics rule (E3) and no
  binding carries it. The old parser cut no comment (a value now ends at ` #`) and read
  `key: # comment` as the value `# comment` (now an empty block, so no value). New test:
  `test_binding_reader` `test_the_durable_docs_directory_is_read_from_the_binding`.
- Ruling r1, NIT 4: `ccp/init.py`'s `#` refusal and its docstring say the reader cuts a value at ` #`;
  the refusal still refuses any `#`.

## Verification notes
- 2026-11-19 — verifier, PR #200 head `bb10598` (squash `6ff9abc`): APPROVE. Passed: bind-01, bind-02, bind-03. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0175-one-binding-reader.json.

