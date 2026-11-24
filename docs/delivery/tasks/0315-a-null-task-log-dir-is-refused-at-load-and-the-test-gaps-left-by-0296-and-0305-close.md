---
task_id: 0315-a-null-task-log-dir-is-refused-at-load-and-the-test-gaps-left-by-0296-and-0305-close
title: plane.json refuses a task_log.dir that is not a path at load, notify's unreadable-plane.json branch and close's not_merged call each get a test, the architect fixture waits for its detached passes before cleanup, and affected_usage is tested on plain values
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S29", "S3", "S10", "S14", "S19"]
review_refs: ["ar-20261123T230912Z-197a#F10"]
review_point: R32
paths: ["ccp/config.py", "tests/test_plane_config_defaults.py", "tests/test_notify_lead.py", "tests/test_tasks_close.py", "tests/architect_fixture.py", "tests/test_suite_run_affected.py"]
clashes_with: ["0191-the-grace-release-ends", "0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log", "0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0315-a-null-task-log-dir-is-refused-at-load-and-the-test-gaps-left-by-0296-and-0305-close

## Intent

A product whose plane.json sets `task_log.dir` to `null` (or to anything but a path) is told so when the
config loads, by key, with exit 2, instead of a `TypeError` traceback from whichever command first reads its
task directory. The open test gaps that 0296 and 0305 left are closed: the spec-question script's warning
for a plane.json it cannot read has a test, and close's call of `not_merged` has one whole-close test that a
mutant of the call fails. The architect tests that start a detached pass no longer race their own temporary
queue's cleanup, and `ccp suite run`'s `--affected` flag rules are tested on plain values, with one
end-to-end refusal kept for the wiring.

## Context (not checked)

Covers these open follow-ups (`QUEUE_ROOT=<queue> ccp --root . tasks follow-ups --open`), the lead's flake
note, and finding F10 of architect pass `ar-20261123T230912Z-197a`
(`docs/delivery/reviews/ar-20261123T230912Z-197a.md`):

- `0296-…/implement#1`, `/review#1`, `/fix#1`, `/review-2#1`, `/fix-2#1`, `/verify#1`: a null `task_log.dir`
  loads, then `Config.delivery_dir` raises a `TypeError`, which `check_task_ids` now reaches.
- `0296-…/implement#2`: `notify_operator`'s `product_config(root, strict=True)` branch (a plane.json that exists
  but does not load gives the "could not read" warning) has no test.
- `0305-…/implement#2`, `/review#2`, `/fix#1` (its second half), `/verify#2`: close's call of `not_merged` (the
  call, and its `not already` argument) has no test since 0305's ruled drop of the two whole-close host tests;
  the reviewer measured both mutants surviving `tests.test_tasks_close`, `tests.test_behind_tip_catch_up` and
  `tests.test_parallel_merging`.
- The lead's note: `tests.test_architect` failed once in a close gate with `OSError: [Errno 66] Directory not
  empty` in `tearDown`'s `self._q.cleanup()` (`tests/architect_fixture.py`), in
  `test_adr_due_detached_with_one_adr_due_still_prints_review_ids` (suite run `st-20261123T233751Z-d4bd83`, the
  gate of 0305's verify, cold).

Measured at `bb102371` (origin/main after 0305's reconcile):

- **The null dir.** A probe, a scratch git product whose plane.json is
  `{"project_id": "p", "language": "python", "suite": {"lanes": {"gate": ["true"]}}, "task_log": {"dir": null}}`:
  `CCP_DEV=1 ./bin/ccp --root <product> tasks check` printed a traceback ending
  `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'NoneType'`, exit 1. `"def delivery_dir"` in
  `ccp/config.py` is `return self.root / self.task_log["dir"]`; `"def _task_log"` merges the given block over
  `TASK_LOG_DEFAULTS` with no check of `dir`. The sibling `"def _adr"` already refuses a non-path:
  `if not (isinstance(a["dir"], str) and a["dir"].strip()): bad.append("adr.dir must be a path")`.
  Ruled: refuse, not default. The schema (`contracts/plane_config.schema.json`) types `task_log.dir` as a
  string, and `adr.dir` and `worktrees.dir` already refuse a non-path at load; a `null` is not "a value other
  than the constant" that §29.3 lets apply, since it is no value at all. A `task_log.dir` that is not a
  non-empty string is refused at load as the other `task_log` errors are, with the message
  `task_log.dir must be a path relative to the product root; delete the key to take the constant`. A string
  value keeps today's handling (the constant warning of §29.3 when it differs from `docs/delivery`).
  The test is `test_a_task_log_dir_that_is_not_a_path_is_refused_at_load` in `tests/test_plane_config_defaults.py`,
  for `null`, `""` and `5`.
- **The notify branch.** `"def notify_operator"` in `scripts/observability/spec_maintainer.py` calls
  `product_config(root, strict=True)` and, when it raises, appends the warning that starts
  `notify: could not read the product's plane.json`, then records and prints the notice anyway.
  `git grep -n 'could not read the product' -- tests` at `bb102371`: no line. The new test,
  `test_an_unreadable_plane_json_warns_and_the_notice_is_still_recorded` in `tests/test_notify_lead.py` (class `Gates`,
  beside `test_ask_operator_records_a_pending_decision_and_prints_it`), gives a
  product whose plane.json is `{not json` and asserts the warning's token `could not read` and the pending
  notice on record.
- **The close call.** `"if refused := not_merged(prhost.label(cfg), pr, tid, facts, not already)"` in
  `"def close"` (`ccp/lifecycle.py`); `not_merged`'s branches are tested on plain values in
  `tests/test_close_merge_outcome.py`. The new test,
  `test_a_pr_the_host_reports_open_after_a_clean_merge_is_refused` in `tests/test_tasks_close.py` (class
  `CloseKeepsTheCaller`, beside `test_a_merge_the_host_refuses_names_the_host`), runs one
  whole close (the module's existing `_to_approved_pr()` path) with `prhost.merge` returning a clean merge and
  `prhost.confirm` returning `PrFacts` with `state="open"`, and asserts exit 1 with the token `OPEN` in the
  refusal and the task not done. That one test fails both mutants: with `already` for `not already`, the open PR
  is judged by the merge-commit branch and refused with another message; with the call removed, close goes on.
- **The architect race.** By reading `"def _spawn"` and the pass's end in `ccp/architect.py`: the detached child
  sets the review's status to `reported` (`move("reported")`) and only then, in its `finally`, drops its own
  worktree and releases the architect lock in the queue, and its stdout goes to `reviews/<rid>.log` in the
  queue. The tests that pass `--detach` (`git grep -n '"--detach")' -- tests/test_architect.py` at `bb102371`:
  `test_reviewers_repro_detached_pass_that_fails`, `test_detached_run_returns_while_the_pass_goes_on`,
  `test_adr_due_detached_runs_every_shape_in_one_process` and
  `test_adr_due_detached_with_one_adr_due_still_prints_review_ids`: four) wait for a status and then return, so `tearDown` can remove the queue while the child still writes to it.
  The implementer confirms the child's last writes with a probe before building, and names them in the report.
  Ruled: `Harness.setUp` (`tests/architect_fixture.py`) wraps `architect.spawn_detached` (`mock.patch.object`) so
  each child's `Popen` is kept; `tearDown` waits for each with a 30-second timeout before it removes anything,
  and a child still running then is killed and the test fails with the line `detached pass <pid> still running
  after 30 s`. No production code changes.
- **The flag rules.** `"def affected_usage"` in `ccp/suite.py` is a plain function of the parsed flags with four
  refusals; `git grep -n affected_usage -- tests` at `bb102371`: no line.
  `test_affected_with_a_lane_a_command_or_since_alone_exits_2_with_nothing_run` in
  `tests/test_suite_run_affected.py` runs `ccp` as a subprocess for each of the four. Ruled: a new
  `AffectedUsage` class calls `suite.affected_usage` on an `argparse.Namespace` for each refusal (each asserting
  its flag's token: `--since`, `--lane`, `--`), and for `--affected` alone and for neither flag (None); the
  end-to-end test keeps one combination (`--affected --lane part`) with its exit 2 and nothing run.
- **No SPEC change.** `git grep -n 'task_log.dir' -- docs/spec` at `bb102371`: no line refusing or defaulting a
  null; §8.1 already refuses a plane.json that does not validate. The other items add tests only.

## Scope

- **In:** `ccp/config.py` (`_task_log`, or the `task_log` validation beside `reviews_dir`'s);
  `tests/test_plane_config_defaults.py`; `tests/test_notify_lead.py`; `tests/test_tasks_close.py`;
  `tests/architect_fixture.py` (`Harness.setUp` and `tearDown`); `tests/test_suite_run_affected.py`.
- No SPEC change (Context, *No SPEC change*).
- **Out:** `ccp/architect.py`, `ccp/lifecycle.py`, `ccp/suite.py` and `scripts/observability/spec_maintainer.py`
  (their code is not changed); 0305's `cmd-01` (dropped by the triage: a done task's check is history).

## dod_checks

- id: `cmd-01`
  story: As a product owner, a plane.json whose task_log.dir is null is refused by name when it loads.
  setup: A checkout of the PR head at `<checkout>` (any seat). A scratch git repo `<product>` outside it (`git init`) holding `docs/delivery/plane.json` = `{"project_id": "p", "language": "python", "suite": {"lanes": {"gate": ["true"]}}, "task_log": {"dir": null}}`, and a scratch `QUEUE_ROOT`.
  steps:
    1. Run `CCP_DEV=1 <checkout>/bin/ccp --root <product> tasks check; echo "exit $?"`.
  expect: stderr names `task_log.dir`, no line holds `Traceback`, and the last line is `exit 2`.
  dry run (`bb102371`): printed a traceback ending `TypeError: unsupported operand type(s) for /: 'PosixPath' and 'NoneType'`, then `exit 1`.
- id: `code-01`
  story: As a plane developer, the null-dir refusal and the unreadable-plane.json warning each have a test that bites.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_plane_config_defaults.PlaneConfigDefaults.test_a_task_log_dir_that_is_not_a_path_is_refused_at_load tests.test_notify_lead.Gates.test_an_unreadable_plane_json_warns_and_the_notice_is_still_recorded` (the ids are given whole, so the run's exit code decides).
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_notify_lead --mutant 'scripts/observability/spec_maintainer.py:product_config(root, strict=True)=>product_config(root)'`.
  expect: step 1 exits 0; step 2 prints the mutant `killed`.
  dry run: n/a — the tests are new; step 2's old text is found once in `scripts/observability/spec_maintainer.py` at `bb102371` (`grep -c 'product_config(root, strict=True)'`: 1).
- id: `code-02`
  story: As a plane developer, close's call of not_merged is tested end to end, and both mutants of it fail that test.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_tasks_close.CloseKeepsTheCaller.test_a_pr_the_host_reports_open_after_a_clean_merge_is_refused`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_tasks_close --mutant 'ccp/lifecycle.py:facts, not already)=>facts, already)' --mutant 'ccp/lifecycle.py:if refused := not_merged(=>if False and not_merged('`.
  expect: step 1 exits 0; step 2 prints both mutants `killed`.
  dry run: n/a — the test is new; each old text is found once in `ccp/lifecycle.py` at `bb102371` (`grep -c 'facts, not already)'`: 1; `grep -c 'if refused := not_merged('`: 1).
- id: `code-03`
  story: As a plane developer, an architect test that starts a detached pass waits for it before removing the queue it writes to.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_architect`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_architect.OneCallShapesEveryAdrDue.test_adr_due_detached_with_one_adr_due_still_prints_review_ids --mutant 'ccp/architect.py:move("reported")=>move("reported"); time.sleep(45)'`.
  expect: step 1 exits 0; step 2 prints the mutant `killed` (the fixture waited 30 s, then failed the test naming the pid). At the merge base the same mutant survives: the test returns while the child sleeps.
  dry run: n/a — needs the build; `move("reported")` is found once in `ccp/architect.py` at `bb102371` (`grep -c 'move("reported")'`: 1), and `time` is imported there.
- id: `code-04`
  story: As a plane developer, suite run's --affected flag rules are judged on plain values, and one end-to-end refusal stays.
  setup: As `code-01`.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_suite_run_affected.AffectedUsage`.
    2. Run `git grep -c 'affected_usage(' -- tests/test_suite_run_affected.py`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_suite_run_affected.AffectedUsage --mutant 'ccp/suite.py:if a.lane is not None:=>if False:'`.
  expect: step 1 exits 0; step 2 prints a number of at least 5; step 3 prints the mutant `killed`.
  dry run (`bb102371`): step 2 printed nothing (exit 1); `if a.lane is not None:` is found once in `ccp/suite.py` (`grep -c`: 1).

## Implementation notes

## Verification notes
