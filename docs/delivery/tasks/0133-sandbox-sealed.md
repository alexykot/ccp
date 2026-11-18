---
task_id: 0133-sandbox-sealed
title: A ccp sandbox is sealed: init and every command inside it resolve to its own binding and queue, and it can fire a test notice
status: pending
kind: feature
depends_on: []
spec_refs: ["S3", "S8", "S9", "S29"]
review_point: R9
sign_off: brief
paths: ["ccp/sandbox.py", "ccp/cli.py", "ccp/init.py", "ccp/notify.py", "docs/spec/05-operations.md", "docs/spec/01-model.md", "docs/cli/05-operations.md", "docs/cli/01-model.md", "tests/test_sandbox.py", "tests/test_notify.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0133-sandbox-sealed
## Intent

An operator or a seat testing adoption in a `ccp sandbox` can run any `ccp` command there, `ccp init`
and `ccp init --force` included, and nothing lands outside the sandbox: no binding in the
installation's bindings directory, no queue under `~/.delivery-queue`. A check that needs an
operator notice fires one with a real command instead of inventing one.

## Context (not checked)

- Found while adopting a product under an earlier plane generation: a `ccp init --force` run inside
  a sandbox (a check of task 0128) wrote a binding into the installation's `projects/` and made a
  queue under `~/.delivery-queue`.
- Reproduced at `921507e` with `HOME` and `CCP_BINDINGS_DIR` pointed at scratch directories:
  `ccp sandbox create S`, then, with the printed `env` lines exported, `ccp --root S/product init --force`
  wrote `product.yaml` into the (scratch) installation bindings directory and made
  `~/.delivery-queue/product`.
- Why, read at `921507e`: `def init` in `ccp/init.py` takes the binding as
  `lib.bindings_dir() / f"{pid}.yaml"` and the queue default as `Path.home() / ".delivery-queue" / pid`;
  it reads neither `PROJECT_YAML` nor `QUEUE_ROOT`. `ccp sandbox create` only works because it runs
  init as a child with `CCP_BINDINGS_DIR` set and `--queue-root` given (`def _build` in
  `ccp/sandbox.py`). Other commands find the sandbox's binding through `PROJECT_YAML` only when the
  caller exported the `env` lines (`def binding_file` in `ccp/cli.py`).
- Task 0128's check-02 had to name a `ccp notify fire other` that does not exist (`ccp notify --help`
  at `921507e`: render, sent, pending, upgrade). `notify.fire` exists in `ccp/notify.py` but only
  steps call it.
- This describes task 0127's own feature, the sandbox (§31.1): no rule changes. §8.3's init default
  (`~/.delivery-queue/<project_id>/`) stays the rule outside a sandbox.
- Rulings taken here:
  - A directory is in a sandbox when its main checkout's parent directory holds the `.ccp-sandbox`
    marker file (a regular file, not a link), the layout 0127 made (`product/` beside the marker).
  - Inside a sandbox the env names are set, not merely defaulted: an exported `PROJECT_YAML`,
    `CCP_BINDINGS_DIR` or `QUEUE_ROOT` naming a path outside the sandbox is refused, naming
    the variable and the sandbox, with a usage exit code, so a shell left pointing at a real product cannot reach it.
  - The test notice is a new `ccp notify fire`, refused outside a sandbox: firing a made-up notice
    in a real product would reach the operator.
- Lead's ruling on spec question sm-20261118T074808Z-0cd1 (operator accepted the amended text,
  2026-11-18: 'accept 0133's amended sealing text'), commit 57630bc700cfbc09f9245947ba75a22144d7d318:
  Build as implemented: inside a sandbox CCP_BINDINGS_DIR is replaced by the sandbox's own; an
  exported PROJECT_YAML, or a QUEUE_ROOT or --queue-root, naming a path outside it is refused (exit 2).
  In PR #159, amend the task's signed PROPOSED §29.3 sentence and the SPEC text identically to:
  '`CCP_BINDINGS_DIR` is replaced by the sandbox's own, an exported `PROJECT_YAML` or a `QUEUE_ROOT`
  or `--queue-root` naming a path outside it is refused (exit 2)' in place of the clause
  '`CCP_BINDINGS_DIR`, `PROJECT_YAML` and `QUEUE_ROOT` are set to the sandbox's own, an exported value
  or a `--queue-root` naming a path outside it is refused (exit 2)'. Note the change in the task's
  Implementation notes. The smaller choice stands: init refuses a --queue-root inside the sandbox other
  than its own queue directory.

## Scope

- **In:**
  - `ccp/sandbox.py`: one function that says whether a directory is in a sandbox and returns its
    directory (the marker rule above).
  - `ccp/cli.py` `main`: before any group runs (init included, `sandbox create` and `sandbox remove`
    excluded), when the `--root` directory (or the working directory) is in a sandbox, set
    `CCP_BINDINGS_DIR` to the sandbox's bindings directory, `PROJECT_YAML` to the binding there when one
    exists, and `QUEUE_ROOT` to the sandbox's queue directory, in `os.environ`, so child processes (hooks, seat scripts,
    gate runs) inherit them; an exported `CCP_BINDINGS_DIR` is replaced, and an exported `PROJECT_YAML`
    or `QUEUE_ROOT` naming a path outside the sandbox is refused (exit 2).
  - `ccp/init.py`: inside a sandbox, the binding is `<project_id>.yaml` in the sandbox's bindings
    directory and the queue is the sandbox's queue directory, `--force` or not; re-running init re-uses both (a kept binding stays
    kept, a forced one is rewritten in the same place); `--queue-root` naming a path outside the
    sandbox is refused (exit 2), writing nothing.
  - `ccp notify fire TRIGGER [--task ID] [--id ID] [--reason R]` (new), in `ccp/notify.py`: fires
    the notice as a step does (`notify.fire`: the `pending` record, the product's notify command
    when it names one, the rendered notice on stderr), TRIGGER any of `blocker`, `decision`,
    `review_point_done` or `allowance_checkpoint` (the triggers `notify.fire` accepts); refused (exit 2) outside a sandbox and
    for `upgrade` (recorded by `ccp notify upgrade`).
  - Rule change, signed at tasking (it makes an exception to §8.3's `PROJECT_YAML` resolution and init's
    default queue): `docs/spec/05-operations.md` §29.3, the sandbox bullet. CURRENT: none (new text). Appended after "…works only below
    the fence's temporary root.". PROPOSED:
    > Inside a sandbox (a directory whose main checkout sits beside the marker), `ccp init`, `--force` or not, and every other command use the sandbox's binding and queue: `CCP_BINDINGS_DIR` is replaced by the sandbox's own, an exported `PROJECT_YAML` or a `QUEUE_ROOT` or `--queue-root` naming a path outside it is refused (exit 2), and nothing is written to the installation's bindings directory or the default queue directory (§8.3). `ccp notify fire <trigger> [--task ID] [--id ID] [--reason R]` fires a test notice there as a step would (§3.6), and is refused outside a sandbox.
  - Signed with the above: `docs/spec/01-model.md` §3.6. CURRENT: none (new text). A new bullet after **Record.**. PROPOSED:
    > - **Test notice.** In a sandbox only (§29.3), `ccp notify fire <trigger>` fires a notice as a step would: the `pending` record, the command channel, the rendered notice.
  - `docs/cli/05-operations.md` and `docs/cli/01-model.md`: the `ccp notify fire` line.
  - `tests/test_sandbox.py`, `tests/test_notify.py`: the checks below; `test_project_yaml_naming_another_products_binding_is_not_taken` changes, since inside a sandbox the sandbox's binding is taken.
- **Out:**
  - Sealing the plugin's hook scripts when run outside `ccp` (they call `ccp where`, which this seals).
  - A notify command for real products.

## dod_checks

- id: `seal-01`
  story: As an operator testing adoption, `ccp init --force` in a sandbox stays inside it.
  setup: a fenced test: `HOME` and `CCP_BINDINGS_DIR` pointed at empty temporary directories (the stand-in installation), a sandbox `S` made by `ccp sandbox create S`; no env lines exported.
  steps:
    1. Run `ccp --root S/product init --force`, then `ccp --root S/product init`.
    2. List the stand-in bindings directory and `HOME/.delivery-queue`.
  expect: both inits exit 0 and print `binding` under `S/bindings` and `queue_root` equal to `S/queue`; the second lists the binding as kept; the stand-in bindings directory is empty and `HOME/.delivery-queue` does not exist.
  dry run: n/a — the sealing is what this task adds; at `921507e` step 1 wrote `product.yaml` into the stand-in bindings directory and made `HOME/.delivery-queue/product`.
- id: `seal-02`
  story: As a seat, every command in a sandbox sees the sandbox's binding and queue without exporting anything.
  setup: the sandbox of seal-01, `QUEUE_ROOT`, `PROJECT_YAML` and `CCP_BINDINGS_DIR` unset.
  steps:
    1. Run `ccp --root S/product where` and `ccp --root S/product upgrade status`.
  expect: `where` prints `binding` `S/bindings/<project_id>.yaml` and `queue_root` `S/queue`; `upgrade status` exits 0.
  dry run: n/a — sealing not built.
- id: `seal-03`
  story: As an operator whose shell still points at a real product, the sandbox refuses it.
  setup: the sandbox of seal-01; a scratch directory `R` outside `S`.
  steps:
    1. Run `ccp --root S/product where` with `QUEUE_ROOT=R` exported.
    2. Run `ccp --root S/product init --queue-root R`.
  expect: both exit 2, naming the outside path and the sandbox; `R` stays empty and the stand-in bindings directory stays empty.
  dry run: n/a — sealing not built.
- id: `notice-01`
  story: As a check writer, I fire a test notice in a sandbox and see it pending.
  setup: the sandbox of seal-01, its plane.json with no `notify` block.
  steps:
    1. Run `ccp --root S/product notify fire blocker --id G1 --reason test`.
    2. Run `ccp --root S/product notify pending`.
  expect: step 1 exits 0 and prints the rendered notice on stderr; step 2 lists one `blocker` notice with id `G1`.
  dry run: n/a — `ccp notify fire` is new.
- id: `notice-02`
  story: As the operator, nothing fires a made-up notice in a real product.
  setup: a fenced test product adopted with `ccp init` outside any sandbox, with a queue.
  steps:
    1. Run `ccp notify fire blocker` there, then `ccp notify pending`.
  expect: step 1 exits 2 naming the sandbox rule; step 2 lists no notice.
  dry run: n/a — `ccp notify fire` is new.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): `ccp/sandbox.py` gains `sandbox_of` (the marker rule: the main checkout's
  parent holds `.ccp-sandbox`, a regular file, not a link) and `seal`. `ccp/cli.py` `main` resolves the
  root once and seals it before every group but `sandbox`. Sealing sets `CCP_BINDINGS_DIR` and
  `QUEUE_ROOT` to the sandbox's directories and `PROJECT_YAML` to `<project_id>.yaml` there when that file
  exists (the id from the checkout's plane.json), in `os.environ`, so children inherit them.
- An exported `PROJECT_YAML` or `QUEUE_ROOT` naming a path outside the sandbox is refused (exit 2). An
  outside `CCP_BINDINGS_DIR` is overridden, not refused: seal-01's setup exports one (the stand-in
  installation's bindings directory) and expects init to succeed, and the test fence exports one for
  every test. This was raised with the runner as a conflict with the ruling's list of three names.
- `ccp/init.py` decides the binding and queue from the sandbox itself, independent of the environment,
  so a direct call is sealed too. A `--queue-root` other than the sandbox's queue is refused (exit 2,
  nothing written). That covers outside the sandbox (the task's rule) and, the narrowest reading of
  "the queue is the sandbox's queue directory", any other path inside it.
- `ccp notify fire` checks the sandbox before anything else, then refuses `upgrade` and an id or reason
  that is not one line. `test_project_yaml_naming_another_products_binding_is_not_taken` now uses a
  product outside every sandbox (the resolver's product_root check). A new test covers a sandbox refusing
  another sandbox's `PROJECT_YAML`.
- 2026-11-18 (implementer, ruling round 1): the lead ruled (sm-20261118T074808Z-0cd1, the operator
  accepted the amended text) that the build stands: an outside `CCP_BINDINGS_DIR` is replaced, not
  refused. The signed PROPOSED §29.3 sentence in Scope and the SPEC text in
  `docs/spec/05-operations.md` §29.3 now read, identically, "`CCP_BINDINGS_DIR` is replaced by the
  sandbox's own, an exported `PROJECT_YAML` or a `QUEUE_ROOT` or `--queue-root` naming a path outside
  it is refused (exit 2)", in place of the clause that listed all three names as set and refused. No
  code or test changed. §3.6 (`docs/spec/01-model.md`) and `docs/cli` do not restate the sealing
  clause and still agree.
- 2026-11-18 (implementer, fix round 1): the two signed-text markers in Scope now end "PROPOSED:" on the
  line right above their blockquotes ("Appended after … PROPOSED:" and "A new bullet after **Record.**.
  PROPOSED:"), so `ccp verify spec-text` finds both passages; the quoted text is unchanged. The Scope
  bullet for `ccp/cli.py` `main` now matches the ruling (an exported `CCP_BINDINGS_DIR` is replaced; an
  outside `PROJECT_YAML` or `QUEUE_ROOT` is refused). `tests/test_notify.py`: `TestNotice`'s refusal test
  adds `--task 9999` (exit 2, nothing pending), and the class sits above the `__main__` block.

## Verification notes

*Append-only.*
