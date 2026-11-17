---
task_id: 0127-throwaway-adopted-product
title: ccp sandbox makes a throwaway adopted product, fenced from real queues, for end-to-end checks
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S8"]
review_point: R8
paths: ["ccp/sandbox.py", "ccp/cli.py", "docs/spec/05-operations.md", "tests/test_sandbox.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0127-throwaway-adopted-product
## Intent

An implementer or verifier exercises init, adoption, close and upgrade paths end to end on a real,
adopted product made by one command and removed by another, never touching a real product's queue
or binding.

## Context (not checked)

- Seats hand-build these fixtures today (a temp repo, a plane.json, a binding, a queue) and get the
  binding resolution wrong, which risks a real queue.
- `ccp/sandbox.py` (new) is the module.
- §31.1: the SPEC paragraph only describes the command.
- Lead's ruling for the first fix round (verbatim): "run one fix round, covering three things.
  1. `binding_file` (ccp/cli.py) honours PROJECT_YAML when it is set, ahead of CCP_BINDINGS_DIR. The
  sandbox exists so the operator can test adoption, and an `upgrade status` blind to the binding
  defeats that, so it is within intent. ccp/cli.py is in 0127's paths. Add a test.
  2. `sandbox remove .` inside a sandbox refuses cleanly (exit 2) instead of emptying it and then
  tracebacking. (Reviewer's suggestion: rmtree the resolved path, or refuse a DIR that resolves to the
  cwd; choose what keeps the result clean.)
  3. `create -- -h` exits cleanly, with no traceback (e.g. turn a non-JSON init output into a
  SandboxError, or refuse -h/--help).
  Keep the SPEC §29.3 sandbox bullet's text unchanged unless a fix makes it false; if one does, say
  exactly what changed in your report. Record these rulings in the task file's Context (not checked)
  section. Resolved flagged choices: keep CCP_SANDBOX_ROOT as built; env keeps its two lines
  (binding_file honouring PROJECT_YAML makes the third unnecessary)."

## Scope

- **In:**
  - `ccp sandbox create [DIR] [-- <ccp init options>]` (new): under `DIR` (default a new temporary
    directory) makes a git repository with one commit, runs `ccp init` there with the options given,
    writing the binding and the queue inside `DIR` (never the installation's bindings directory),
    commits what init wrote, writes a marker file, and prints JSON: `root`, `binding`, `queue_root`,
    and `env`, the `PROJECT_YAML` and `QUEUE_ROOT` lines that point `ccp` at it.
  - `ccp sandbox remove DIR` (new): removes a directory holding the marker; any other directory is
    refused (exit 2).
  - Under the test fence (`tests/__init__.py`), `create` works only below the fence's temporary root.
  - §31.1: `docs/spec/05-operations.md`, one paragraph describing both commands.
- **Out:**
  - A remote, a hosting service or a telemetry receiver for the sandbox.

## dod_checks

- id: `cmd-01`
  story: As a verifier, I get an adopted product in one command.
  setup: a scratch directory `S` that does not exist.
  steps:
    1. Run `ccp sandbox create S`.
    2. With the printed `env` lines exported, run `ccp tasks check` and `ccp upgrade status` in the printed `root`.
  expect: step 1 exits 0 and prints the four keys, each path under `S`; step 2's commands exit 0.
  dry run: n/a.
- id: `cmd-02`
  story: As the installation, my bindings are untouched.
  setup: the run of cmd-01.
  steps:
    1. List the installation's bindings directory before and after cmd-01.
  expect: the two listings are equal.
  dry run: n/a.
- id: `cmd-03`
  story: As an operator, remove deletes only a sandbox.
  setup: the sandbox `S` of cmd-01 and a scratch directory `T` without the marker.
  steps:
    1. Run `ccp sandbox remove T`, then `ccp sandbox remove S`.
  expect: the first exits 2 and `T` remains; the second exits 0 and `S` is gone.
  dry run: n/a.
- id: `cmd-04`
  story: As a task, init options pass through.
  setup: a scratch directory `U` that does not exist.
  steps:
    1. Run `ccp sandbox create U -- --gate "python3 -m unittest"`.
  expect: the sandbox's plane.json names that command as its gate lane.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 (implementer): `ccp/sandbox.py`, wired in `ccp/cli.py` (it runs before plane.json
  loads, like `init`; the words after `--` go to init). Layout under `DIR`: `product/` (the repo,
  branch `main`, one commit, then a second with what init wrote), `bindings/` (init runs as a child
  with `CCP_BINDINGS_DIR` pointing there), `queue/` (passed as `--queue-root`) and the marker
  `.ccp-sandbox`. Narrow choices beyond the task's text: `DIR` must not exist or be empty (exit 2);
  `--queue-root`, `--permissions`, `--rules-doc`, `--adopt` and `--root` after `--` are refused
  (exit 2); a failed init removes what create made and passes init's exit code on; `remove` refuses
  a link, a marker that is a link, init options and a missing `DIR`. The fence: `tests/__init__.py`
  sets `CCP_SANDBOX_ROOT` to a temporary directory removed at exit; `create` refuses a `DIR` outside
  it and makes its default directory inside it. `env` holds the two lines the task names; `ccp`'s
  product-to-binding lookup reads the bindings directory, not `PROJECT_YAML`, so `ccp upgrade status`
  in a sandbox runs (exit 0) without seeing its binding. SPEC: one bullet at the end of §29.3 (§31.1);
  also `docs/cli/05-operations.md` and `ccp/CLAUDE.md`'s layout.
- 2026-11-17 (implementer, fix round 1, per the lead's ruling above): `binding_file` (`ccp/cli.py`)
  takes the file `PROJECT_YAML` names ahead of `<bindings>/<project_id>.yaml`, under the same
  product_root check, so a `PROJECT_YAML` naming another product's binding is not taken (the lookup
  then falls back to the bindings directory). With the sandbox's `env` lines, `ccp where`,
  `ccp upgrade status` and the queue default (§9.2) now see its binding. `sandbox remove` refuses
  (exit 2) a sandbox that holds the working directory (`remove .` inside it, `remove ..` from its
  `product/`), and removes the resolved path, so a `..` path no longer ends in a traceback.
  `create` turns init output that is not a binding's JSON (`-- -h`, `-- --help`) into a refusal
  (exit 2, init's output shown, nothing kept). The §29.3 bullet's text is unchanged.

## Verification notes
