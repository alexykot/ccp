---
task_id: 0277-code-leftovers-of-r15-and-r17
title: Close the code follow-ups of R15 and R17 - one wait-writer command, close's removals through the unrecorded-worktree helper, review and question ids from refs.py, a requires remedy that never makes a cycle, and two tests that no longer depend on load or the cwd
status: done
kind: feature
depends_on: []
spec_refs: ["S7", "S10", "S12", "S21"]
review_point: R24
paths: ["scripts/observability/lib.py", "scripts/observability/spec_maintainer.py", "scripts/observability/architecture_review.py", "ccp/lifecycle.py", "ccp/wt.py", "ccp/tasklog.py", "tests/test_wait_reasons.py", "tests/test_wt_unrecorded.py", "tests/test_obs_ids.py", "tests/test_tasklog_requires.py", "tests/test_mutate.py", "tests/test_plugin.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0277-code-leftovers-of-r15-and-r17

## Intent

The code leftovers of the R15 and R17 tasks are closed. One function builds every call to
`waiting_on`'s single writer. `ccp tasks close` removes its merge worktree through the same helper the
architect and the dry run use, and still warns when the removal fails. The architect pass id and the
spec question id are parsed with the shapes in `ccp/refs.py`. The requires remedy of
`ccp tasks check` never tells the lead to add a `depends_on` that would make a cycle. The task check
says why it reads ADRs from the checkout. The mutate interrupt test and the run-checkout test pass
under load and from a removed working directory.

## Context (not checked)

Measured at `a80cee0` unless a line says otherwise.

Follow-ups covered (the lead's worker follow-up log): `0253-one-wait-reason-table/implement#3`,
`0254-close-and-architect-share-the-unrecorded-worktree-helper/implement#1`,
`0254-close-and-architect-share-the-unrecorded-worktree-helper/implement#2`,
`0254-close-and-architect-share-the-unrecorded-worktree-helper/review#1`,
`0252-the-task-check-reports-a-decision-built-before-its-prerequisite/implement#1`,
`0252-the-task-check-reports-a-decision-built-before-its-prerequisite/review#1`,
`0252-the-task-check-reports-a-decision-built-before-its-prerequisite/review#2`,
`0254-close-and-architect-share-the-unrecorded-worktree-helper/merge#1`,
`0258-the-plane-writes-the-pre-merge-phases/fix#4`.

- **Two writer calls.** `git grep -n 'set-waiting-on.sh"' -- ccp scripts` at `a80cee0`: 2 lines,
  `"def set_wait"` in `ccp/lifecycle.py` and `"def set_wait"` in
  `scripts/observability/spec_maintainer.py`. Each builds the argv itself. `scripts/observability/team.py`
  calls `sm.set_wait` (`git grep -c 'sm.set_wait' -- scripts/observability/team.py` at `a80cee0`: 3), so it needs no change of its own. `ccp/lifecycle.py` already imports the
  observability `lib` (`from ccp.queue import lib`).
- **Close's own removals.** `git grep -n '"worktree", "remove"' -- ccp/lifecycle.py ccp/wt.py` at `a80cee0`: 6 lines.
  Close's are the two in `ccp/lifecycle.py` (the merge worktree after the
  reconcile, and the catch-up's cleanup under `"except BaseException:"`) and `"def _remove_merge"` in
  `ccp/wt.py` (a failed close's leftover, from `ccp wt remove`/`gc`). The other three are
  `"def remove_unrecorded"`, the forced removal of a worktree being added, and the removal of a
  recorded worktree. `remove_unrecorded` ignores failures, while close warns on them. SPEC §12.1 says
  close "removes it once the reconcile has landed" and names no command, so routing it through the
  helper changes no SPEC text.
- **Id shapes.** `ARCH_RE` in `ccp/wt.py` is already built from `refs.PASS_ID` (0254's squash
  `81c0f20`: `git grep -n 'ARCH_RE = ' -- ccp/wt.py`). What still restates an id shape is
  `git grep -nE '\[0-9\]\{\{?8' -- scripts/observability` at `a80cee0`: 2 lines, `Kind.rid_re` in
  `architecture_review.py` and `QID_RE` in `spec_maintainer.py`. `ccp/refs.py` holds `STAMP_ID`,
  `PASS_ID` and `QUESTION_ID`. `architecture_review.py` already puts the plane root on `sys.path` and
  imports from `ccp`.
- **The requires remedy.** In `"def requires_report"` (`ccp/tasklog.py`), the remedy names every other
  task that cites the prerequisite (`citers`), including one whose `depends_on` closure holds the
  reported task, so its "add a depends_on on …" would make a cycle. The dropped half of 0252's
  follow-up is already done: `_cited_decisions` returns nothing for a dropped task, and
  `test_a_dropped_task_neither_clears_the_report_nor_is_named` (`tests/test_tasklog_requires.py`)
  holds it at `a80cee0`.
- **ADR texts under `texts` (0252 review#2), a false premise.** `ccp tasks check --lease [--staged]`
  never calls `tasklog.check`: `"def cmd_tasks_lease_check"` in `ccp/cli.py` reads only
  `lifecycle.lease_edits`. The one caller that passes `texts` is `ccp tasks migrate`:
  `git grep -nE 'tasklog\.check\(cfg, ' -- ccp` at `a80cee0` gives 1 line, `"def check_failures"` in
  `ccp/taskmigrate.py`. Migrate rewrites task files only, never an ADR, so the checkout's ADRs are the
  ones the rewritten log is judged against. The ruling is to say so, not to change the reads.
- **The mutate interrupt test.** It failed once in a gate run, with "the test command was left running" from `assert_gone` after its bound (`grep -n 'left running' <queue>/runs/0254-close-and-architect-share-the-unrecorded-worktree-helper/merge-suite-st-20261122T003256Z-702d41.log`: 1 line; queue data only the queue holds).
  When run alone it passes. On macOS, `os.killpg(pgid, 0)` on a group whose only member is an unreaped
  zombie raises `PermissionError`, which `assert_gone` reads as "still running". Probe at `a80cee0`:
  `python3 -c "import subprocess,os,time; p=subprocess.Popen(['sleep','0'],start_new_session=True); time.sleep(0.5); os.killpg(p.pid,0)"`
  raised `PermissionError`. A killed `sleep` waits as a zombie until launchd reaps it, and under load
  that can take longer than the bound.
- **The run-checkout test.** `tests.test_plugin.RunCheckout` runs `git` and `scripts/run-checkout.sh`
  with no `cwd`, so the calls inherit the process's working directory. Reproducer at `a80cee0`:
  `PYTHONPATH=$PWD python3 -B -c "import os,tempfile,unittest; d=tempfile.mkdtemp(); os.chdir(d); os.rmdir(d); unittest.main(module='tests.test_plugin', argv=['x','RunCheckout'])"`
  printed `FAILED (failures=2)`. In a scratch copy with the module's `run` helper defaulting `cwd` to
  the plane checkout, the same command printed `OK`, and so did the whole module (`argv=['x']`).
- **Other tasks on these files.** 0272 (R23) changes `team.py`'s and `lib.py`'s lead actor id, 0268
  and 0259 add other `lib.py` code, 0266 changes `ccp/lifecycle.py`'s PR-host calls, 0264 and 0275
  change other `ccp/tasklog.py` functions, and 0271 changes `ccp mutate`'s interface and its tests in
  `tests/test_mutate.py`. That is different logic in each case: no clash, only possible text merges.

### Rulings for the build (the lead's)

- **The writer command.** `scripts/observability/lib.py` gets
  `wait_writer_cmd(action, tid, reason, *, actor, project_id, task_only=False, quota_class=None, resets_at=None, planned_resume_at=None, detail=None) -> list[str]`.
  It returns the writer's path (`set-waiting-on.sh` beside `lib.py`), `action`, `tid`, `reason`,
  `--actor`, `--project-id`, then each option that is set, and `--task-only` when asked. Both
  `set_wait`s build their command with it and keep their own run and error handling: lifecycle keeps its
  timeout and `QueueError` codes, and spec_maintainer keeps `die`. spec_maintainer's `bash` prefix goes,
  since the writer is executable.
- **Close's removals.** `wt.remove_unrecorded(main, path)` returns git's failure text (stripped, at
  most 200 characters) when `git worktree remove --force` fails, else None. It prunes in both cases.
  Close's two removals in `ccp/lifecycle.py` and `wt._remove_merge` call it. The warnings keep their
  wording: `merge worktree <path>: <text>` after the reconcile, and `worktree <path>: <text>` from
  `_remove_merge`. The catch-up's cleanup still ignores a failure. The architect and the dry run
  ignore the return value. `tests/test_wt_unrecorded.py` gets a test where close's removal after the
  reconcile fails (with `wt.remove_unrecorded` patched to return a text) and close's output carries
  the `merge worktree <path>: <text>` warning.
- **Id shapes.** `Kind.rid_re` becomes `rf"^(?:{p})-{refs.STAMP_ID}$"`. `spec_maintainer.QID_RE`
  becomes `re.compile(rf"^{refs.QUESTION_ID}$")`, with spec_maintainer putting the plane root on
  `sys.path` before it imports `ccp.refs`, as `architecture_review.py` does. `tests/test_obs_ids.py`
  (new) holds both: each accepts a fresh id (`architect._new_rid` for the pass; an `sm-` id made the
  way spec_maintainer makes one) and rejects a malformed one (a three-hex-digit suffix).
- **The requires remedy.** `citers` leaves out each task whose `depends_on` closure
  (`graph.closure(deps, o)`) holds the reported task. When it leaves out every citer, the remedy reads:
  "`<ids>` cites it but depends on this task, so a depends_on would make a cycle: cite it from a task
  this one can depend on, or record it built with `ccp adr decide <n> D<d> built`". The rest of the
  line is unchanged.
- **The ADR reads.** No read changes. The docstring of `"def _requires_lines"` gains one sentence:
  "`check`'s `texts` stand in for task files only (its one caller, `ccp tasks migrate`, rewrites task
  files and no ADR), so the ADRs are read from the checkout."
- **The mutate interrupt test.** `tests/test_mutate.py` gets a module function `group_gone(pgid)`. It
  returns True when `ps -A -o pgid=,stat=` lists no process of that group whose state does not start
  with `Z`. `assert_gone` polls it with the same bound as `interrupt`'s waits (`deadline = time.monotonic() + 30`), and still sends
  SIGKILL and fails when the bound passes. Two tests hold the helper: a group whose only member is an
  unreaped zombie (`sleep 0`, started with `start_new_session=True` and not waited on) is gone, and a
  group running `sleep 30` is not (killed and reaped afterwards).
- **The run-checkout test.** `tests/test_plugin.py`'s `run` helper sets `cwd` to the plane checkout
  (`PLANE`) when the call gives none.

## Scope

- **In:** `scripts/observability/lib.py` (`wait_writer_cmd`), `scripts/observability/spec_maintainer.py`
  (`set_wait`, `QID_RE`), `scripts/observability/architecture_review.py` (`Kind.rid_re`),
  `ccp/lifecycle.py` (`set_wait`, close's two removals), `ccp/wt.py` (`remove_unrecorded`,
  `_remove_merge`), `ccp/tasklog.py` (`requires_report`, `_requires_lines`' docstring),
  `tests/test_wait_reasons.py`, `tests/test_wt_unrecorded.py`, `tests/test_obs_ids.py` (new), `tests/test_tasklog_requires.py`,
  `tests/test_mutate.py`, `tests/test_plugin.py`.
- No SPEC change. Each concept, searched in `docs/spec` at `a80cee0`:
  `git grep -n 'set-waiting-on.sh' -- docs/spec` finds 11 lines naming the script as the single
  writer, which stays true. `git grep -n 'merge-<nnnn>' -- docs/spec` finds 4 lines, none naming how close removes it.
  `git grep -n 'STAMP_ID\|rid_re\|QID_RE' -- docs/spec` finds nothing. The remedy wording is a warning's text:
  §21.1 says only that the line is "naming the remedies" (`git grep -n 'naming the remedies' -- docs/spec/03-quality.md`: 1 line).
- **Out:** `ccp/cli.py`'s lease check; `ccp tasks migrate`; `ccp mutate`'s own SIGTERM handling;
  `scripts/run-checkout.sh`; `team.py`.

## dod_checks

- id: `code-01`
  story: As a plane developer, one function builds every call to the wait writer.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'set-waiting-on.sh"' -- ccp scripts`.
    2. Run `python3 -B -m unittest -q tests.test_wait_reasons tests.test_operator_rename tests.test_notify tests.test_notify_lead 2>&1 | tail -1`.
  expect: step 1 prints exactly one line, in `scripts/observability/lib.py`; step 2 prints `OK`.
  dry run (`a80cee0`): step 1 printed 2 lines (`ccp/lifecycle.py:510`, `scripts/observability/spec_maintainer.py:300`); step 2 printed `OK`.
- id: `code-02`
  story: As the runner, close removes its merge worktree through the unrecorded-worktree helper and still warns when that fails.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `git grep -n '"worktree", "remove"' -- ccp/lifecycle.py ccp/wt.py`.
    2. Run `python3 -B -m unittest -v tests.test_wt_unrecorded 2>&1 | tail -3`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_wt_unrecorded --mutant-file <file>`, the file's mutant making `remove_unrecorded` return None whatever git said.
    4. Run the same with a second mutant file, whose mutant makes close's removal after the reconcile (`ccp/lifecycle.py`) drop the returned text instead of adding its warning.
  expect: step 1 prints exactly three lines, all in `ccp/wt.py`, one of them in `def remove_unrecorded`, none in `ccp/lifecycle.py`; step 2 ends `OK` and the run lists, `ok`, a test where `remove_unrecorded` on a path git cannot remove returns a text naming that path, and on a removed worktree returns None, and a test where close's removal fails and close's output carries `merge worktree <path>:` with that text; steps 3 and 4 each print the mutant `killed`.
  dry run (`a80cee0`): step 1 printed 6 lines (`ccp/lifecycle.py:1275`, `:1618`; `ccp/wt.py:355`, `:620`, `:635`, `:740`); step 2 ended `OK` (the new test n/a — it is new).
- id: `code-03`
  story: As a plane developer, the architect pass id and the spec question id take their shape from ccp/refs.py.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -nE '\[0-9\]\{\{?8' -- scripts/observability`.
    2. Run `git grep -n 'refs.STAMP_ID\|refs.QUESTION_ID' -- scripts/observability`.
    3. Run `python3 -B -m unittest -v tests.test_obs_ids tests.test_wt_unrecorded tests.test_notify 2>&1 | tail -3`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_obs_ids --mutant 'scripts/observability/spec_maintainer.py:QUESTION_ID=>QUESTION_ID[:-3]'`, adjusting the old text to the `QID_RE` line as built if it differs, and the same for `Kind.rid_re` with a mutant that ends the pattern before `refs.STAMP_ID`'s hex part.
  expect: step 1 prints nothing (exit 1); step 2 prints two lines, one in `architecture_review.py` and one in `spec_maintainer.py`; step 3 ends `OK` and lists, `ok`, tests where `Kind.rid_re` and `QID_RE` each accept a fresh id and reject a malformed one; step 4 prints each mutant `killed`.
  dry run (`a80cee0`): step 1 printed 2 lines (`architecture_review.py:63`, `spec_maintainer.py:72`); step 2 printed nothing; step 3 n/a — `tests/test_obs_ids.py` is new (`tests.test_wt_unrecorded tests.test_notify` printed `OK`).
- id: `code-04`
  story: As the lead, the requires remedy never asks for a depends_on that makes a cycle, and the task check says why it reads ADRs from the checkout.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_tasklog_requires 2>&1 | grep -e cycle -e dropped -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_tasklog_requires --mutant-file <file>`, the file's mutant putting every other citing task back into `citers`.
    3. Run `git grep -n -A6 'def _requires_lines' -- ccp/tasklog.py | grep -c 'ccp tasks migrate'`.
  expect: step 1 prints, each `ok`, `test_a_dropped_task_neither_clears_the_report_nor_is_named`, a new test where the only task citing the prerequisite depends on the reported task and the line names that task with `would make a cycle` and `ccp adr decide`, not `add a depends_on on`, and `OK`; step 2 prints the mutant `killed`; step 3 prints `1`.
  dry run (`a80cee0`): step 1 printed the dropped test `ok` and `OK` (the cycle test n/a — it is new); step 3 printed `0`.
- id: `test-01`
  story: As a worker under a loaded gate, the mutate interrupt test does not mistake a zombie for a running test.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_mutate 2>&1 | grep -e group -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_mutate --mutant-file <file>`, the file's mutant making `group_gone` read only `os.killpg(pgid, 0)` again, as `assert_gone` did.
  expect: step 1 prints, `ok`, a test where a group whose only member is an unreaped zombie is gone and one where a group running `sleep 30` is not, and `OK`; step 2 prints the mutant `killed`.
  dry run: n/a — `group_gone` and its tests are new.
- id: `test-02`
  story: As a worker, the run-checkout test passes whatever the process's working directory is.
  setup: A checkout of the PR head; run from its root.
  steps:
    1. Run `PYTHONPATH=$PWD python3 -B -c "import os,tempfile,unittest; d=tempfile.mkdtemp(); os.chdir(d); os.rmdir(d); unittest.main(module='tests.test_plugin', argv=['x','RunCheckout'])" 2>&1 | tail -1`.
  expect: prints `OK`.
  dry run (`a80cee0`): printed `FAILED (failures=2)`.

## Implementation notes

- The measured premises re-ran at `6c349b77` with the task's figures: 2 writer lines, 3 `sm.set_wait` calls in
  `team.py`, 6 `"worktree", "remove"` lines, 2 restated id shapes, 1 `tasklog.check(cfg, ` caller, the SPEC counts
  (11, 4, 0, 1), the zombie probe's `PermissionError` and the run-checkout reproducer's `FAILED (failures=2)`.
- `lib.wait_writer_cmd` leaves out an option whose value is empty, as lifecycle's builder did; spec_maintainer used
  to pass `--detail` whatever its value, and the writer reads an empty one as none, so nothing it records changes.
- `wt.remove_unrecorded` truncates git's text to 200 characters, so `_remove_merge`'s warning, untruncated before,
  is now capped like close's. Close's removal after the reconcile and the catch-up's cleanup import `wt` inside the
  function, as every other `wt` use in `lifecycle.py` does.
- The cycle remedy prints the citing ids bare, as the `add a depends_on on <ids>` remedy does; the ruling's
  backticks around `<ids>` are read as placeholder markup. When some citers would make a cycle and others would
  not, the remedy names only the others.
- `group_gone` reads `ps -A -o pgid=,stat=`; its zombie test waits for the exit with `os.waitid(..., WNOWAIT)`, which
  leaves the child unreaped, and reaps it in cleanup.
- Fix round 1 (review MINOR 1, NITs 1 and 2):
  - The interrupt test failed once more under heavy load after the zombie fix, with no clue what was left. The
    group's running processes now come from `group_running` (the `ps` rows: pid, stat, command; zombies left
    out), which `group_gone` is built on, and `assert_gone` puts those rows in its failure message before the
    SIGKILL. The interrupt's command now runs `exec sleep 60` after writing the pid file, so no fork follows it:
    a SIGTERM can no longer land while the shell is forking the sleep.
  - `_remove_merge`'s warning is now tested through `ccp wt gc` over a leftover `merge-0002` whose task is done,
    with `wt.remove_unrecorded` patched to fail (`tests/test_wt_unrecorded.py`).
  - `requires_report`'s docstring is rewrapped near 110 columns.

## Verification notes
- 2026-11-22 — verifier, PR #327 head `e94d67f` (squash `039d546`): APPROVE. Passed: code-01, code-02, code-03, code-04, test-01, test-02. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0277-code-leftovers-of-r15-and-r17.json.

