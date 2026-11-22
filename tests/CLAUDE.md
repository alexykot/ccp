# tests — the plane's suite

Run it with `scripts/gate.sh`; the house rules for it are E1, E2 and E4 (`docs/ENGINEERING.md`). `test_self_hosting.py`
runs the plane's own checks against this repo, read-only. Every test builds its product in a temp directory, points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls.

## Shared fixtures

Modules share fixtures; reuse one before building another. Each lives in a module that holds no tests
(`helpers.py`, `review_flow.py` and the `*_fixture.py` modules, one for each test module whose fixtures others
use), and a test module imports it from there. No test module imports another. Where a check needs no repository,
queue or subprocess, test a function on plain values instead (`test_catch_up_decision.py`).
- `helpers.py`'s `Product`: a temp product root with a plane config and helpers to add tasks and files.
  Most modules build on it.
- `helpers.py`'s `binding(**keys)`: the text of a binding, `project_id: demo` first, then each key. A test
  that needs a binding writes it with this; only a test of the binding's format or of `ccp init`'s output
  keeps literal text. A test names the worktrees directory as `config.WORKTREES_DIR`, never as a copied literal.
- `helpers.py`'s `done_report(phase, *lines)`: the text of a done report of a phase that `ccp report` accepts,
  with the section the phase needs when done. A test that files a done report for something else writes it with this.
- `helpers.py`'s `FoldRuns` (`mkrun`, `write`, `rows`: run records and usage rows in a temp queue) and `BoardPage`
  (`page`: the board page's script run under node): mixins for a `TestCase`.
- `helpers.py`'s small shared constants and builders, each named for what it makes: `GIT_ENV`, `PLANE_ROOT`,
  `git_run` and the `*_git` runners, `ledger_event`, `approve_verdict`, `implement_report`, `api_request`, `file_tree`
  and the rest; `with_test_methods(text)` writes the text of a test module with its `def t_x` methods named `test_x`,
  for a fixture that writes a test module and so holds no `test_` method itself.
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
- `team_hosting_fixture.py`'s `TeamCase`: a `Product` and a claude-team queue (its binding, work state and
  claimed task files) with a `run_cmd` that runs a script against it.
- `init_fixture.py`'s `InitCase`: a temp git repository, a temp home and bindings directory, and `ccp()` and
  `init()` to run `ccp init` there.
- `gate_parallel_fixture.py`'s `GateFixture`: a temp git repository holding copies of the gate scripts, and
  `module()`, `gate()` and `read()` to write test modules and run the gate on them.
- `suite_fixture.py`'s `SuiteFixture` (a `ToolkitFixture` for `ccp suite run`) and `suite_stages_fixture.py`'s
  `StagedFixture` (it, with a `lanes()` setter for plane.json `suite.lanes`).
- `wt_fixture.py`'s `WtFixture`, `rotation_fixture.py`'s `RotationFixture`, `parallel_claims_fixture.py`'s
  `ParallelFixture`, `verify_cache_fixture.py`'s `CacheFixture` and `notify_fixture.py`'s `ChannelFixture`: each a
  `ToolkitFixture` set up for its feature's tests. `upgrade_fixture.py`'s `UpgradeFixture` is a mixin of its own:
  a scratch plane, product and queue.
- `board_drill_fixture.py`'s `Fixture`, `board_quality_fixture.py`'s `Base` and `board_seats_fixture.py`'s `Base`:
  the board tabs' fixtures; `estimate_fixture.py`'s `EstimatePage`: the estimates tab under node, a mixin.
- `sandbox_fixture.py`'s `SandboxCase`, `binding_reader_fixture.py`'s `BindingDir` and `architect_fixture.py`'s
  `Harness`: a `TestCase` base for the sandbox, binding reader and architect tests.

**Reuse rule.** A fixture shared across modules is a class with no test methods (`ToolkitFixture` and the
mixins above mix into a `TestCase`; the others are `TestCase` bases that hold no tests), in a module that holds no
tests, imported by name. No test module imports another, so an edit to one stays an input of that module alone
(the gate's cache and `ccp suite affected` read imports); a helper a second module needs moves to a fixture
module first. No module binds another module's test-class methods as its own helpers (a class attribute assigned
from `test_x.Class`): the helper moves to a mixin or a fixture. The architect's `E4` command check fails on an
import of a test module and on the binding.
