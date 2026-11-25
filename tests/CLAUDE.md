# tests — the plane's suite

Run it with `scripts/gate.sh`; the house rules for it are E1, E2 and E4 (`docs/ENGINEERING.md`). `test_self_hosting.py`
runs the plane's own checks against this repo, read-only. Every test builds its product in a temp directory, points
`QUEUE_ROOT` at a temp queue, and stubs headless Claude calls.

## Shared fixtures

Modules share fixtures; reuse one before building another. Each lives in a module that holds no tests
(`helpers.py`, the four `*_helpers.py` modules, `review_flow.py` and the `*_fixture.py` modules), and a test module
imports it from there (E4: a helper a second module needs moves to a fixture module first). Each module's docstring
says what it holds and how to use it; this list names the concern and the one or two things a new test reaches for
first. Where a check needs no repository, queue or subprocess, test a function on plain values instead
(`test_catch_up_decision.py`). Each `<name>_fixture.py` holds the fixture `test_<name>.py` and its neighbours share.

- `helpers.py`: a temp product root and the small shared constants and builders. `Product`, `PLANE_ROOT` (the one
  name for the plane checkout, so a search for the tests that read a repo file finds them all), `run_clock` (the one
  run clock a test's runs open at).
- `git_helpers.py`: the one git runner, taken from here and never from a fixture. `git`.
- `report_helpers.py`: reports, verdicts and the marked-check text. `done_report`.
- `ledger_helpers.py`: ledger events, suite rows and usage rows. `ledger_event`, `FoldRuns`.
- `render_helpers.py`: what renders a page or a prompt. `phase_values`, `BoardPage`.
- `toolkit_fixture.py`: a git product (bare origin, main clone, runner worktree) and a queue on the local PR host;
  the most reused fixture, for every test that runs `ccp` against a real repository. `ToolkitFixture`, `edit_plane`
  (the way a test changes the fixture's plane.json).
- `review_flow.py`: mixins that drive a claimed task through review, fix and verify rounds. `ReviewFlow`, `SkipFlow`.
