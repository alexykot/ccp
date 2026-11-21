---
task_id: 0207-sync-product-docs-finds-the-binding-through-lib
title: scripts/sync-product-docs.sh finds a product's binding through the one binding module
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S9"]
rule_refs: ["E17"]
review_point: R14
paths: ["scripts/sync-product-docs.sh", "tests/test_binding_reader.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0207-sync-product-docs-finds-the-binding-through-lib

## Intent

House rule E17 says one module resolves and parses a product's binding. `scripts/sync-product-docs.sh`
now parses through it, but it still resolves the binding on its own, as `<plane>/projects/<id>.yaml`.
That ignores `CCP_BINDINGS_DIR`, which every other reader honours and the test fence sets. A sync
run without `--project-yaml` under the fence therefore reads the real installation's bindings
directory instead of the fenced one. After this task, the script asks the binding module where the
binding is, so `CCP_BINDINGS_DIR` applies to it as it does everywhere else.

## Context (not checked)

Measured at `58cf1d0`.

- The parse already goes through the module. `binding = lib.read_binding(yml.read_text())`, and
  `top(key)` returns `lib.binding_str(binding, key)` (`git grep -n 'lib.read_binding\|lib.binding_str' scripts/sync-product-docs.sh`
  at `58cf1d0`: two lines). Task 0194's follow-up named the `top()` parser, which task 0175 had
  already moved onto the module; what is left is the resolution.
- The resolution is the script's own: `yml = Path(project_yaml) if project_yaml else plane /
  "projects" / f"{project}.yaml"` (`git grep -n '"projects"' scripts/sync-product-docs.sh` at
  `58cf1d0`: one line). `lib.bindings_dir()` is the module's answer, honouring `CCP_BINDINGS_DIR`.
- Probe at `58cf1d0`: with `CCP_BINDINGS_DIR` set to a temp directory holding `demox.yaml`,
  `scripts/sync-product-docs.sh demox --check` exits 2 with "no project binding
  <plane>/projects/demox.yaml".
- The header comment's "Defaults: --project-yaml = <plane>/projects/<project_id>.yaml" follows.
- `tests/test_binding_reader.py` `SyncReaderTest` covers the script and passes, with the module's
  other tests (`python3 -B -m unittest -q tests.test_binding_reader` at `58cf1d0`: 23 tests).
- No SPEC change: §8.3 already says `CCP_BINDINGS_DIR` moves the bindings directory
  (`grep -n 'CCP_BINDINGS_DIR' docs/spec/01-model.md` at `58cf1d0`).

## Scope

- **In:** `scripts/sync-product-docs.sh`, `tests/test_binding_reader.py`.
- Without `--project-yaml`, the binding is `lib.bindings_dir() / f"{project}.yaml"`. With it, the
  given file, as today. The rest of the script is unchanged.
- `top()` is inlined as `lib.binding_str(binding, …)` at its call sites, so no local binding
  helper remains.
- The header's "Defaults:" line says `--project-yaml = <the bindings directory>/<project_id>.yaml
  (CCP_BINDINGS_DIR, else <plane>/projects)`.
- **Test** in `SyncReaderTest`: with `CCP_BINDINGS_DIR` set to the test's temp directory holding
  `demo.yaml`, the script with no `--project-yaml` reads that binding (its `--check` reports the
  managed copies for the test's product root).
- **Out:** the managed copies themselves, and the other binding readers (already on the module).

## dod_checks

- id: `sy-01`
  story: As a fenced test or an operator with a moved bindings directory, the sync finds the binding
    there.
  setup: a checkout of the PR head; a temp directory `<b>` holding `demox.yaml` with `project_id:
    demox` and `product_root: <an empty temp dir>`.
  steps:
    1. Run `CCP_BINDINGS_DIR=<b> scripts/sync-product-docs.sh demox --check; echo rc=$?`.
  expect: no "no project binding" line; the output has `DRIFT docs/delivery/CONTROL-PLANE.md: missing`,
    and `rc=1` (drift).
  dry run (`58cf1d0`): "sync-product-docs: no project binding <plane>/projects/demox.yaml", exit 2. With
    `--project-yaml <b>/demox.yaml` instead, it prints the `DRIFT … missing` lines and exits 1.

- id: `sy-02`
  story: As a plane developer, the script resolves no binding path of its own, and the test bites.
  setup: a checkout of the PR head; then a copy (`git worktree add --detach <tmp> HEAD`) in which
    the default is `plane / "projects" / f"{project}.yaml"` again.
  steps:
    1. On the head, run `git grep -n '"projects"\|def top' scripts/sync-product-docs.sh`.
    2. On the head, run `python3 -B -m unittest -q tests.test_binding_reader`.
    3. In the copy, run the same.
  expect: step 1 prints nothing; step 2 passes; step 3 fails, naming the `CCP_BINDINGS_DIR` test.
  dry run (`58cf1d0`): step 1 prints two lines; step 2 runs 23 tests, OK.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

- `scripts/sync-product-docs.sh`: without `--project-yaml` the binding is `lib.bindings_dir() / f"{project}.yaml"`; `top()` is gone, its four uses call `lib.binding_str(binding, ...)` directly; the header's Defaults line names `CCP_BINDINGS_DIR`, else `<plane>/projects`.
- `tests/test_binding_reader.py`: one `SyncReaderTest` test runs the script with no `--project-yaml` and `CCP_BINDINGS_DIR` at the temp directory. The existing tests still pass `--project-yaml`.
- The premise figures held at `56c65cc`: one `"projects"` line, 23 tests in the module before the change.

## Verification notes
