---
task_id: 0280-the-base-run-reads-the-denylist-the-head-run-reads-and-tests-make-no-base-run
title: The run at the merge base reads the leak denylist the HEAD run reads, tests never make a base run of the real repo, and a multi-path non-ASCII diff is pinned
status: pending
kind: feature
depends_on: []
spec_refs: ["S21"]
review_point: R24
paths: ["ccp/baseline.py", "tests/__init__.py", "tests/test_preexisting_checks.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0280-the-base-run-reads-the-denylist-the-head-run-reads-and-tests-make-no-base-run

## Intent

When a worker runs `ccp docs check` through its worktree's own `bin/ccp` and the leak check fails on a
hit that is already on the integration branch, the hit is reported as pre-existing and does not fail the
check, because the run at the merge base reads the same denylist the run at `HEAD` read. The plane's own
test suite never makes a worktree of the real repository for a base run. A branch whose diff holds
several paths, one of them non-ASCII, is judged on each path whole, and a test holds it.

## Context (not checked)

Measured at `b4af31e` (origin/main). This task covers task 0259's open worker follow-ups
(`ccp tasks follow-ups --open`):

| Follow-up | Item here |
| --- | --- |
| `0259-…/implement#2`, `review#1`, `fix#1`, `verify#2` | the base run's bindings directory (`code-01`) |
| `0259-…/implement#3`, `review#2` | the fence on base runs in tests (`code-02`) |
| `0259-…/verify#1` | the multi-path non-ASCII fixture (`code-03`) |

**1. The base run's bindings directory.** `"def run_at_base"` in `ccp/baseline.py` gives the base run
`"CCP_BINDINGS_DIR": str(queue.lib.bindings_dir())` (`git grep -c '"CCP_BINDINGS_DIR": str(queue.lib.bindings_dir())' -- ccp` at `b4af31e`: 1 line, `ccp/baseline.py`). With `CCP_BINDINGS_DIR` unset, that is
`projects/` beside the running `ccp`'s code (`"def bindings_dir"` in `scripts/observability/lib.py`). Under a
worktree's own `bin/ccp` (what `ccp wt exec` runs) it is `<worktree>/projects`, which does not exist. At
`HEAD`, `scripts/leak-check.sh` (step 3 of its header) resolves the directory through `ccp --root <repo> where`
from PATH instead, which names the run checkout's binding. Probes at `b4af31e`, in this repo's worktree, with
`CCP_BINDINGS_DIR` unset:
- `python3 -c "from ccp import queue; p = queue.lib.bindings_dir(); print(p.exists())"`: `<worktree>/projects`, `False`;
- `env -u CCP_BINDINGS_DIR scripts/leak-check.sh`: `denylist found (bindings dir)`, `clean`;
- `CCP_BINDINGS_DIR=$PWD/projects scripts/leak-check.sh`, what the base run gets: `no denylist found … nothing checked`.

A fixture probe at `b4af31e` (a fixture repo whose `architect.checks` runs a copy of `scripts/leak-check.sh`,
a denylist hit committed on `main`, a task branch changing another file, `CCP_BINDINGS_DIR` unset, a stub
`ccp` on PATH whose `where` names a binding in a temporary directory holding `leak-denylist.txt`, and
`queue.lib.bindings_dir` patched to a directory that does not exist): `ccp docs check` exited 1 with the hit
counted, no pre-existing heading. The same probe with the base run given the directory the stub's `where`
names ended with exit 0, the hit under the heading. So a leak already on main is never excused today; it fails safe.

**No SPEC change.** `git grep -n CCP_BINDINGS_DIR -- SPEC.md docs/spec` at `b4af31e`: 2 lines; the one that
rules this is §21.2 (`docs/spec/03-quality.md:549`): the base run gets "`CCP_BINDINGS_DIR` set to the bindings
directory the `HEAD` run resolved, so an input outside git, such as a denylist, is the same at both". Today the
code breaks that sentence; this task makes it hold. How the `HEAD` side resolves the directory is already
written in E3 (`docs/ENGINEERING.md:39` at `b4af31e`: "`CCP_BINDINGS_DIR`, else beside the binding `ccp where`
names"). The SPEC text stays as it is; no sign-off.

**2. The fence.** `tests/test_self_hosting.py` runs this repo's own `bin/ccp docs check` and `tasks check`
on the real checkout (`"def ccp"` there, `--root ROOT`). When either fails on a branch, 0259's code makes a
temporary detached worktree of the real repo for the base run. It is removed afterwards, but the module calls
itself read-only. The tests' fence is `tests/__init__.py`. Its switches that turn a side effect off follow one
pattern (`CCP_NO_BOARD_REFRESH`, `CCP_NO_ESTIMATOR_SPAWN`). None is a SPEC rule
(`git grep -n "CCP_NO_" -- SPEC.md docs/spec` at `b4af31e`: no match); `docs/design/board.md` names the first.
`git grep -n CCP_NO_BASE_RUN -- .` at `b4af31e`: no match. Under the fence, a docs-check failure already on
main fails the self-hosting test, as it did before 0259; such a failure fails main's own suite too, so it is
fixed on main.
`git grep -n "pre-existing on" -- tests` at `b4af31e`: 1 line, `tests/test_preexisting_checks.py`, the only
module that needs base runs, so it is the only one that lifts the fence.

**3. `-z` and `quotepath`.** `"def changed_paths"` runs
`git -c core.quotepath=off diff --name-only -z <base>...HEAD`. With `-z`, git prints each path verbatim
whatever `core.quotepath` says. A probe at `b4af31e` (a repo with `a.md` and `café.py`,
`git -c core.quotepath=true diff --name-only -z`): `a.md\0café.py\0`, unquoted; without `-z`, the second path
printed as `"caf\303\251.py"`. So `quotepath=off` cannot be pinned while `-z` is there, and nothing pins `-z`
today. Probes at `b4af31e` in a scratch copy, running `python3 -B -m unittest tests.test_preexisting_checks.DocsCheck`
with a prototype of `code-03`'s test added:
- with `"-c", "core.quotepath=off", ` removed from `changed_paths`, every test passed, the existing
  `"def test_a_branch_adding_a_non_ascii_file_to_the_checker_leaves_the_hit_failing"` too;
- with `"-z",` removed, the prototype failed, because the diff's two paths reach `checker_changed` as one
  string starting `app/`.

### Rulings for the build (the lead's)

- **`"def head_bindings_dir"`** (new, `ccp/baseline.py`, taking the `Config`): the bindings directory the
  `HEAD` run's checks read, as E3 resolves it. It returns `CCP_BINDINGS_DIR` when that is set (through
  `envvar`). Otherwise it runs `ccp --root <cfg.root> where` from PATH (`shutil.which("ccp")`), with this
  process's environment, stdin closed and a 30-second timeout. From that it returns the directory of the
  printed `binding`, or `<plane>/projects` when `binding` is null. With no `ccp` on PATH, a non-zero exit, a
  timeout or output that does not parse, it returns `queue.lib.bindings_dir()`, as today. `"def run_at_base"`
  sets the base run's `CCP_BINDINGS_DIR` to it. `scripts/leak-check.sh` stays as it is. The docstring of
  `head_bindings_dir` names the third step of leak-check.sh as the resolution it mirrors.
- **The fence.** `NO_BASE_RUN = "CCP_NO_BASE_RUN"` in `ccp/baseline.py`. When `envvar(NO_BASE_RUN)` is set,
  `"def judge"` makes no base run and every failure counts. The module docstring names the switch and says the
  tests' fence sets it. `tests/__init__.py` sets `os.environ["CCP_NO_BASE_RUN"] = "1"`, with a one-line comment
  citing §21.2, beside the other `CCP_NO_*` lines. `tests/test_self_hosting.py` is not edited; it inherits the
  fence. In `tests/test_preexisting_checks.py`, `Repo.make` lifts it for its tests:
  `mock.patch.dict(os.environ, {"CCP_NO_BASE_RUN": ""})`, started there and stopped by `addCleanup`. An empty
  value counts as unset under `envvar`.
- **`changed_paths`** drops `"-c", "core.quotepath=off"`, and its docstring says the paths come NUL-separated,
  which git prints verbatim, so a non-ASCII path is named whole.
- **Tests**, all in `tests/test_preexisting_checks.py`:
  - `BaseRun.test_a_leak_on_main_is_preexisting_when_the_head_run_finds_the_denylist_through_ccp_where`: the
    probe in Context as a test. The fixture repo commits a copy of `scripts/leak-check.sh` and runs it as an
    `architect.checks` command. It expects exit 0 and `check E1` under the heading.
  - `BaseRun.test_the_fence_makes_no_base_run`: with `CCP_NO_BASE_RUN=1`, a fixture with a hit on main and a
    task branch gives exit 1, no heading, and a marker file showing the failing check ran once.
  - `DocsCheck.test_a_multi_path_diff_with_a_non_ascii_checker_file_leaves_the_hit_failing`: the repo holds
    `ccp/__init__.py` on main and has `core.quotepath` set to `true`. The task branch commits `app/other.md`
    and `ccp/café.py` in one commit. It expects exit 1 and nothing under the heading.
  - `BaseRun.test_the_base_run_gets_the_bindings_directory_the_head_run_resolved` changes: with
    `CCP_BINDINGS_DIR` set to a temporary directory, the base run sees that same directory. Today it expects
    the patched `lib.bindings_dir()` instead.

## Scope

- **In:** `ccp/baseline.py` (`head_bindings_dir`, the `CCP_NO_BASE_RUN` switch in `judge`, `changed_paths`
  without `core.quotepath`, the docstrings); `tests/__init__.py` (one line and its comment);
  `tests/test_preexisting_checks.py` (three tests added, one changed, the fence lifted in `Repo.make`).
- **Out:** `scripts/leak-check.sh` and the denylist; `docs/spec/03-quality.md` (§21.2 stays); setting
  `CCP_BINDINGS_DIR` for workers (the other option the follow-ups name, not taken); `tests/test_self_hosting.py`;
  `docs/ENGINEERING.md`.

## dod_checks

- id: `code-01`
  story: As a worker running a worktree's own `bin/ccp`, a leak hit already on main is reported as pre-existing, because the base run reads the denylist the HEAD run found through `ccp where`.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for step 2.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_preexisting_checks.BaseRun`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_preexisting_checks.BaseRun.test_a_leak_on_main_is_preexisting_when_the_head_run_finds_the_denylist_through_ccp_where --revert ccp/baseline.py`.
  expect: step 1 exits 0 and lists `test_a_leak_on_main_is_preexisting_when_the_head_run_finds_the_denylist_through_ccp_where` and `test_the_base_run_gets_the_bindings_directory_the_head_run_resolved` as `ok`; step 2 prints the mutant `killed`.
  dry run: n/a — the test is new. The fixture probe in Context exited 1 at `b4af31e`, which is what the revert brings back.
- id: `code-02`
  story: As a plane developer, the test suite never makes a worktree of the real repository for a base run.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for step 3.
  steps:
    1. Run `git grep -n 'CCP_NO_BASE_RUN' -- tests/__init__.py`.
    2. Run `python3 -B -m unittest -v tests.test_preexisting_checks.BaseRun.test_the_fence_makes_no_base_run`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_preexisting_checks.BaseRun.test_the_fence_makes_no_base_run --revert ccp/baseline.py`.
  expect: step 1 prints exactly one line; step 2 exits 0 with the test `ok`; step 3 prints the mutant `killed`.
  dry run (`b4af31e`): step 1 printed nothing (exit 1); steps 2 and 3 n/a — the test is new.
- id: `code-03`
  story: As a plane developer, a branch whose diff holds several paths, one non-ASCII, is judged on each path whole.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for step 3.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_preexisting_checks.DocsCheck`.
    2. Run `git grep -n quotepath -- ccp/baseline.py`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_preexisting_checks.DocsCheck.test_a_multi_path_diff_with_a_non_ascii_checker_file_leaves_the_hit_failing --mutant 'ccp/baseline.py:"--name-only", "-z",=>"--name-only",'`.
  expect: step 1 exits 0 and lists `test_a_multi_path_diff_with_a_non_ascii_checker_file_leaves_the_hit_failing` as `ok`; step 2 prints nothing (exit 1); step 3 prints the mutant `killed`.
  dry run (`b4af31e`): step 2 printed 2 lines (`ccp/baseline.py:197`, `ccp/baseline.py:199`); in a scratch copy with the prototype test, removing `"-z",` failed it and removing the quotepath flag did not (Context, item 3); steps 1 and 3 n/a — the test is new.

## Implementation notes

## Verification notes
