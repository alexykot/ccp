# tests — the plane's suite

Run it with `scripts/gate.sh`; the house rules for it are E1, E2 and E4 (`docs/ENGINEERING.md`). `test_self_hosting.py`
runs the plane's own checks against this repo, read-only. Every test builds its product in a temp directory, points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls.

## Shared fixtures

Modules share fixtures; reuse one before building another. Each lives in a module that holds no tests
(`helpers.py`, the four `*_helpers.py` modules, `review_flow.py` and the `*_fixture.py` modules), and a test module
imports it from there (E4: a helper a second module needs moves to a fixture module first). Where a check needs no repository, queue or subprocess,
test a function on plain values instead (`test_catch_up_decision.py`). Each `<name>_fixture.py` holds the fixture
`test_<name>.py` and its neighbours share; its module docstring says what it builds. The ones worth naming:
- `helpers.py`'s `Product`: a temp product root with a plane config and helpers to add tasks and files.
  Most modules build on it.
- `helpers.py`'s `binding(**keys)`: the text of a binding, `project_id: demo` first, then each key. A test
  that needs a binding writes it with this; only a test of the binding's format or of `ccp init`'s output
  keeps literal text. A test names the worktrees directory as `config.WORKTREES_DIR`.
- `report_helpers.py`'s `done_report(phase, *lines)`: the text of a done report of a phase that `ccp report` accepts,
  with the section the phase needs when done. A test that files a done report for something else writes it with this.
  The module also holds `implement_report`, `approve_verdict`, `judge_merge_ok`, `held_otherwise`, `HEAD_A`, `HEAD_B`
  and the marked-check text (`MARKED_CHECK_ID`, `MARKED_TASK_ID`, `MARKED_BLOCK`).
- `git_helpers.py`'s `git(cwd, *args, env=None, raw=False)`: the one git runner. It runs `git -C <cwd>` with `GIT_ENV`
  (a test identity, no global or system config) and `env`, fails the test naming the command and its stderr on a
  non-zero exit, and returns stdout stripped, or as written with `raw=True`. A test does not define a runner of its
  own. The module also holds `run(cmd, **kw)` (any command with `GIT_ENV`, a `CompletedProcess`), `commit(root, msg,
  at, *extra)` (a commit made at the epoch second `at`) and `HEALTH_T0`.
- `ledger_helpers.py`: ledger events and usage rows. `ledger_event`, `spawn_event`, `lease_event`, `suite_started`,
  `suite_ended` and `SUITE_RUN_ID`, `good_then_failed`, `api_request`, `advice_row` and `ADVICE_SPANS`, `epoch_iso`,
  `T0`, and `FoldRuns` (`mkrun`, `write`, `rows`: run records and usage rows in a temp queue), a mixin for a `TestCase`.
- `render_helpers.py`: what renders a page or a prompt. `phase_values`, `render_phase_values`, `PROMPT_TEMPLATES` and
  `BoardPage` (`page`: the board page's script run under node), a mixin for a `TestCase`.
- `helpers.py`'s small shared constants and builders, each named for what it makes: `GIT_ENV`, `PLANE_ROOT`,
  `LEAD_ENV` and `as_lead()` (the environment with the lead's `ACTOR`, for a call to a command only the lead may
  run), `as_actor(value)` (`ACTOR` set to another value, or unset), `file_tree` and the rest. `helpers.py`
  loads no `ccp` module on import, so the fence in `tests/__init__.py` comes first; a module takes the plane root
  from `PLANE_ROOT` and git's identity from `GIT_ENV`. It imports none of the four `*_helpers.py` modules, and a
  module imports a helper from the module that holds it: an edit to one concern then marks only its importers
  affected.
- `toolkit_fixture.py`'s `ToolkitFixture`: a git product (a bare origin, a main clone and a runner worktree) and
  a queue, on the local PR host (`pr_host.adapter: local`); `open_pr()` opens the task's PR and `pr_record()`
  reads its record. The most reused one: for close, claim, verify and every test that runs `ccp` against a
  real repository. No test code stands in for a PR host; only the GitHub adapter's own tests stub `gh`.
  Each test class builds the three repositories once (`setUpClass`, from the class's own `PLANE_JSON`) and every
  test copies that tree; a class that changes the build before `setUp` ends sets `SHARED_REPO = False`.
- `review_flow.py`'s `ReviewFlow`: a mixin (before `ToolkitFixture`) that drives a claimed task through review,
  fix and verify rounds (`run_phase`, `review`, `fix`, `verdict`, `verify_round`) and commits in a worktree (`commit`).
- `review_flow.py`'s `SkipFlow`: `ReviewFlow` plus a proof command and the task's worktree, for `verify.skip_review`
  (`reviewed`, `push`, `verify`, its own `commit` and `fix`; `PROOF`, `SKIP_REVIEW_PLANE`).
