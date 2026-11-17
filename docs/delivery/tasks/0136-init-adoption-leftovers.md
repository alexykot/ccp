---
task_id: 0136-init-adoption-leftovers
title: ccp init checks a kept binding's shape, agrees with ccp where on paths, lists a kept INDEX.yaml and writes the gate into the standing DoD
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S8", "S9", "S21"]
review_point: R9
paths: ["ccp/init.py", "ccp/cli.py", "README.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "tests/test_init.py", "tests/test_plugin.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0136-init-adoption-leftovers
## Intent

A lead re-adopting a product with `ccp init` learns from init's own output what is still wrong: a
kept binding missing its `runner` block or carrying retired keys is named; the paths init prints are
the ones `ccp where` prints, from a worktree too; a kept `INDEX.yaml` is listed as kept, as the
README says; and the standing DoD names the gate init was given, with `ccp docs check` warning while
a placeholder item is left.

## Context (not checked)

- Reported while re-adopting a product under an earlier plane generation (four findings; a fifth,
  the `task_log.spec_paths` default, is task 0144, because §3.5 states that default and changing it
  is a rule change).
- Kept binding, read at `921507e`: `def init` in `ccp/init.py` keeps an existing binding without
  `--force` after checking only its `product_root` and `queue_root`; nothing compares it with
  `contracts/project.schema.json`. A binding from an earlier generation with no `runner` block and
  old `seats`/`cadence`/`email` keys is reported only as kept.
- Paths, read at `921507e`: init prints `product_root` as `_main_worktree(root.resolve())` and
  `queue_root` resolved; `def cmd_where` in `ccp/cli.py` prints `cfg.root` (the worktree it ran in)
  and `QUEUE_ROOT` as the binding spells it (`def binding_queue_root` expands `~` and does not
  resolve links), and the binding path unresolved.
- INDEX.yaml: the report's premise ("init did not write one") is not true as stated. At `921507e`
  `def init` runs `tasklog.write_index(cfg)` when the product keeps an index and has no
  `INDEX.yaml`, or with `--force`. What is true: an existing `INDEX.yaml` is neither rewritten nor
  listed in init's `kept`, while the README's adoption paragraph says init writes it. Ruling: init
  keeps it and lists it as kept (rewriting it could drop titles an earlier generation's files need,
  task 0134), and the README says so.
- Standing DoD: `templates/docs-delivery/standing-dod.md` ends with the placeholder item `7. …`
  under "This product's standing items", and the gate item says "The gate command is named below."
  At `921507e` init copies the template verbatim whatever `--gate` says.
- Rulings taken here:
  - Missing keys: the schema's `required` keys, `product_root`, and a `runner` block with
    `agent_type` and `name`. Obsolete keys: those §8.3 says are ignored (`seats.runner`,
    `seats.verifier`, `seats.watchdog`, `email`, `cadence.verify_stale_minutes`), every top-level
    key whose schema `description` says ignored or retired (not `auth_check` or `spec_maintainer`, which the code still reads), and every top-level key the schema
    does not list. Each is a warning (init still succeeds) in the result's `warnings`, naming the binding
    file and the fix: edit it, or `ccp init --force` to rewrite it (its other edits are lost).
  - `ccp where` prints `product_root` as the main checkout (as init does) and `binding` and
    `queue_root` as real paths; init prints `binding` as its real path too.
  - With `--gate` and the file written (new, or `--force`), the placeholder line `7. …` becomes
    ``7. **The gate is `<gate>`**, run by the verifier at the PR head (item 5).``; a kept file is not
    touched. `ccp docs check` warns (does not fail) while `docs/delivery/standing-dod.md` holds a
    numbered line that is only `…`.
- §31.1: the SPEC text below only describes this task's own messages and outputs.

## Scope

- **In:**
  - `ccp/init.py`: the kept-binding warnings; `binding` printed as its real path; `INDEX.yaml`
    listed in `kept` when it exists and is not rewritten; the gate written into
    `standing-dod.md`'s placeholder item when init writes that file with `--gate`.
  - `ccp/cli.py` `cmd_where`: `product_root` the main checkout; `binding` and `queue_root` real
    paths. `cmd_docs_check`: the placeholder warning.
  - `README.md`, the adoption paragraph: "…a minimal `plane.json` in `docs/delivery/`, and
    `INDEX.yaml`." becomes "…a minimal `plane.json` in `docs/delivery/`, and `INDEX.yaml` when there
    is none (an existing one is kept and listed as kept; `ccp tasks index` regenerates it)."
  - §31.1: `docs/spec/01-model.md` §8.3, appending to "It keeps an existing binding unless given `--force`, and refuses one that names another product root.":
    > A kept binding is checked against the current shape: init warns, naming each missing key (the schema's required keys, `product_root`, a `runner` block with `agent_type` and `name`) and each obsolete one (the ignored keys below, a key the schema marks ignored or retired, a key it does not list).
  - §31.1: `docs/spec/01-model.md` §9.2. CURRENT (at `921507e`): "`ccp where` prints the project, the binding file's path, the queue, the plane checkout and the `ccp` path." PROPOSED:
    > `ccp where` prints the project, the product root (the main checkout, from any worktree), the binding file's path, the queue, the plane checkout and the `ccp` path, each path as its real path, as `ccp init` prints them.
  - §31.1: `docs/spec/01-model.md` §4.5. CURRENT (at `921507e`): "and `INDEX.yaml` when the product keeps one (§5.7);" PROPOSED:
    > and `INDEX.yaml` when the product keeps one (§5.7) and has none yet (an existing one is kept and listed as kept); with `--gate`, the gate command written into `standing-dod.md`'s placeholder product item;
  - §31.1: `docs/spec/03-quality.md` §21.2, a sentence after "…and `ccp tasks check`.":
    > It warns, without failing, while `docs/delivery/standing-dod.md` holds a numbered item that is only `…`, the template's placeholder.
  - `tests/test_init.py`, `tests/test_plugin.py` (its `where` tests): the checks below.
- **Out:**
  - A `binding migrate` command or `--force-binding`.
  - The `task_log.spec_paths` default (task 0144).

## dod_checks

- id: `bind-01`
  story: As a lead re-adopting a product, init names what my kept binding lacks and carries.
  setup: a fenced product with a binding already in the (temporary) bindings directory naming its product root and queue, with no `runner` block and with `seats:` (`runner: x`), `email:` and `hosting:` blocks.
  steps:
    1. Run `ccp init` in the product.
  expect: exit 0; the binding is listed as kept and unchanged; `warnings` names the binding file, the missing `runner` block, and `seats.runner`, `email` and `hosting` as obsolete; a second fenced product whose binding init wrote itself gets no such warning on a rerun.
  dry run: n/a — the warning is new.
- id: `where-01`
  story: As a lead adopting from a linked worktree, init and `ccp where` print the same paths.
  setup: a fenced product whose queue root in the binding is reached through a symlinked directory; a linked worktree `W` of it (`git worktree add`).
  steps:
    1. Run `ccp --root W init`, then `ccp --root W where` with `QUEUE_ROOT` unset.
  expect: both print the same `product_root` (the main checkout's real path), `binding` and `queue_root` (real paths, no symlinked prefix).
  dry run: n/a — at `921507e` `where` printed `W` as `product_root` (`def cmd_where`: `str(cfg.root)`).
- id: `idx-01`
  story: As an adopter following the README, init's output accounts for `INDEX.yaml`.
  setup: a fenced product with a committed `docs/delivery/INDEX.yaml` before init.
  steps:
    1. Run `ccp init`; read the README's adoption paragraph.
  expect: init lists `docs/delivery/INDEX.yaml` in `kept` and leaves it byte for byte; the README paragraph says an existing one is kept and `ccp tasks index` regenerates it.
  dry run: n/a — at `921507e` init's `kept` left `INDEX.yaml` out.
- id: `dod-01`
  story: As a verifier, the standing DoD names the gate init was given.
  setup: two fresh fenced products.
  steps:
    1. In the first, run `ccp init --gate "python3 -m unittest"`, then `ccp docs check`.
    2. In the second, run `ccp init` without `--gate`, then `ccp docs check`.
  expect: the first's `standing-dod.md` has no `7. …` line and names `python3 -m unittest` in item 7, and its docs check prints no placeholder warning; the second keeps `7. …` and its docs check exits 0 with a warning naming the placeholder.
  dry run: n/a — at `921507e` init wrote `7. …` with `--gate` given.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
