---
task_id: 0309-the-bare-runner-warning-reads-past-env-and-timeout-options-and-e4-skips-a-test-file-it-cannot-read
title: ccp tasks check's bare-runner warning reads past the options of an env, time or timeout prefix and loses its dead ccp guard, and E4's import check skips a tracked test file it cannot read and says so
status: done
kind: feature
depends_on: []
spec_refs: ["S21"]
rule_refs: ["E4"]
review_point: R29
paths: ["ccp/tasklog.py", "tests/test_bare_test_runner_warning.py", "docs/delivery/plane.json", "tests/test_self_hosting.py"]
clashes_with: []
adopt: "none"
created: 2026-11-22
updated: 2026-11-24
---

# Task: 0309-the-bare-runner-warning-reads-past-env-and-timeout-options-and-e4-skips-a-test-file-it-cannot-read

## Intent

Three leftovers of 0301 close. `ccp tasks check` warns on a check step that runs the test command
bare behind `env -u NAME`, `timeout -k 5 60` or `timeout -s KILL 60`, as it already does behind
`env A=1` or `timeout 60`, so a step can't slip past the warning by adding a prefix option. The
`ccp`/`bin/ccp` guard in `runs_bare`, which no input reaches, is gone. And E4's import check, given
a tracked test file it can't open or parse, skips it with a line naming it, and judges the rest,
instead of stopping with a traceback and exit 1.

## Context (not checked)

Covers these follow-ups (`ccp --root . tasks follow-ups --open`), and the two nits of 0301's review
(`progress/0301-…/review-report.md` in the queue, NIT-1 and NIT-2), which the lead put in this task:

- `0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured/implement#2`
  and `/review#2`: `runs_bare` does not read past options after `env` or `timeout`.
- NIT-1: the `ccp`/`bin/ccp` guard in `runs_bare` is dead code.
- NIT-2: E4's import program exits 1 with a traceback on a tracked test file it can't read, where
  0301's ruling says it "exits 0 otherwise".

Measured at `15dbfe7a` (origin/main; first at `ad9b4f84`, every figure re-ran unchanged).

- **The dead guard.** In `"def runs_bare"` (`ccp/tasklog.py`), `if rest[:1] and rest[0] in CCP_COMMANDS: return False`.
  When `rest[0]` is `ccp` or `bin/ccp` it does not start with `-`, so it is kept as `kept[0]`, and it never equals a
  runner's first word (`python3`, or that of any pack command not starting with `ccp`): the comparison already
  answers not bare.
  `git grep -nw CCP_COMMANDS -- ccp tests` at `15dbfe7a`: 2 lines, the constant and the guard. In a scratch copy (`git archive`)
  with `CCP_COMMANDS = ()`, `python3 -B -m unittest tests.test_bare_test_runner_warning` printed `OK`: the mutant survives.
  Ruled: delete the guard, `CCP_COMMANDS` and the docstring's sentence "One that starts with `ccp` or `bin/ccp` never does."
  `test_a_run_through_ccp_suite_run_is_not_bare` and `test_a_ccp_command_or_another_command_is_not_bare` keep
  passing unchanged: the general rule already gives their answers.
- **The prefix options.** Today the walk reads past `NAME=value`, `env`, `time` and `timeout N`, and then drops every
  word starting with `-`, so `env -i python3 -m unittest` is already bare. A probe at `15dbfe7a`,
  `python3 -B -c 'from ccp import tasklog as t, doclang as d; r=t._tokens(d.get("python").test_command); print([t.runs_bare(t._tokens(c), r) for c in ("env -u X python3 -m unittest", "timeout -k 5 60 python3 -m unittest", "timeout -s KILL 60 python3 -m unittest", "env -i python3 -m unittest")])'`,
  printed `[False, False, False, True]`: an option's argument (`X`, `5`, `KILL`) is left as the first word.
  Ruled: a constant `PREFIX_OPTION_ARGS = {"env": ("-u", "-C", "-P", "--unset", "--chdir"), "time": ("-o", "-f", "--output", "--format"), "timeout": ("-k", "-s", "--kill-after", "--signal")}`,
  the options whose next word is their argument (a long form written `--signal=KILL` is one word). After `env`, `time` or `timeout`, the walk skips each word starting with `-`, and also
  the next word when the option is in that prefix's tuple. A `--name=value` word is one word. After `timeout` and its
  options a duration (`TIMEOUT_RE`) must follow, or the walk stops at `timeout`, as today, so `timeout python3 -m unittest`
  stays not bare. `env -S` is not read (its argument is the command string itself). A runner option that takes an
  argument (`python3 -X dev -m unittest`) stays not bare, as `RunsBare` pins it.
  The new test is `test_bare_past_env_time_and_timeout_options` in `RunsBare`, holding at least `env -u X python3 -m unittest`,
  `env -C /tmp python3 -m unittest`, `timeout -k 5 60 python3 -m unittest`, `timeout -s KILL 60 python3 -m unittest`,
  `timeout --signal=KILL 60 python3 -m unittest`, `env --unset X python3 -m unittest`, `env --chdir /tmp python3 -m unittest`,
  `timeout --kill-after 5 60 python3 -m unittest`, `timeout --signal KILL 60 python3 -m unittest`, `time -p python3 -m unittest`,
  `time -o out.txt python3 -m unittest`, `time -f %e python3 -m unittest`, `time --output out.txt python3 -m unittest`,
  `time --format %e python3 -m unittest` and `env -u X A=1 time -p timeout -k 5 60 python3 -m unittest` as bare, and `timeout -k 5 python3 -m unittest` as not bare.
- **E4's import check.** It is the `python3 -B -c` part of E4's command in `docs/delivery/plane.json` (the part holding
  `from tests`, which `e4_import_check` in `tests/test_self_hosting.py` extracts). It runs `open(f).read()` and `ast.parse`
  on each tracked `tests/*.py`. A probe at `15dbfe7a`, in a scratch repo with `tests/test_a.py` tracked then deleted from the
  working tree, ran the part: `FileNotFoundError`, exit 1; with a tracked `tests/test_b.py` holding `def (`: `SyntaxError`,
  exit 1; neither printed a `<path>:<line>`.
  Ruled: a file whose `open` raises `OSError` or whose `ast.parse` raises `SyntaxError` (or `ValueError`) is skipped,
  and the program prints `E4: skipped <path>: <the exception's message>` on stderr for it, then judges the other files
  as today: exit 1 with a `<path>:<line>` per hit on stdout, exit 0 otherwise. A syntax error is skipped, not fatal, because
  E4 judges imports; the gate fails a test file that does not parse. The part stays one `python3 -B -c` program with no
  ` && ` in it, keeps the words `from tests`, and may span lines inside its quotes. The new test is
  `test_the_check_skips_a_tracked_test_file_it_cannot_read_and_says_so` in `TestModulesImportNoTestModule`: one missing and
  one unparsable tracked file beside a clean one give exit 0 and both `skipped` lines; the same with a hit in the clean file
  give exit 1 and the hit's `<path>:` on stdout.
- **No SPEC change.** `git grep -nE 'CCP_COMMANDS|RUNNER_PREFIXES|runs_bare|timeout N' -- docs/spec` at `15dbfe7a`: no line.
  §21.1 (`docs/spec/03-quality.md`) says only that `ccp tasks check` warns on a step that runs the pack's test command
  outside `ccp suite run`, which this keeps. E4's rule text and its `check:` line in `docs/ENGINEERING.md` ("four greps, an
  import check over the tracked test files, and the long-literal count") stay as they are. So no sign-off.
- **Clashes.** A script over the pending tasks on `origin/main` at `15dbfe7a`, listed those whose `paths` name
  `ccp/tasklog.py`, `docs/delivery/plane.json`, `tests/test_self_hosting.py` or `tests/test_bare_test_runner_warning.py`:
  0304 (section finding), 0305 and 0308 (other `architect.checks` entries); 0293 (`WHOLE_SUITE_ROLES` and E27) was pending
  at `15dbfe7a` and is done since. Those naming `tests/` by other files only (0191, 0296, 0297, 0299, 0300, 0302, 0303,
  0306, 0307) were read too: none names a file of this task. None of them changes `runs_bare` or E4's import part
  (`git grep -nw 'runs_bare\|RUNNER_PREFIXES\|E4' -- <those task files>` finds E4 only in the `rule_refs` of 0293, 0297 and 0302
  and in 0302's Intent on its test helpers, never E4's import check), so `clashes_with` is empty.

## Scope

- **In:** `ccp/tasklog.py` (`runs_bare`, `RUNNER_PREFIXES`, `CCP_COMMANDS` removed, `PREFIX_OPTION_ARGS` added);
  `tests/test_bare_test_runner_warning.py` (the new `RunsBare` test); `docs/delivery/plane.json` (E4's import part);
  `tests/test_self_hosting.py` (the new `TestModulesImportNoTestModule` test).
- **Out:** `_command_starts` (the refactor gate's walk, which reads `env -i` and `-u NAME` already) is not changed.
  The SPEC, `docs/ENGINEERING.md` and E4's other parts are not changed.

## dod_checks

- id: `code-01`
  story: As a plane developer, `runs_bare` holds no guard that no input reaches, and a `ccp` command is still never bare.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `git grep -nw CCP_COMMANDS -- ccp tests`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_bare_test_runner_warning`.
    3. Run `grep -e a_run_through_ccp_suite_run_is_not_bare -e a_ccp_command_or_another_command_is_not_bare -e '^OK' <the log step 2 names>`.
  expect: step 1 prints nothing (exit 1); step 2 exits 0; step 3 lists `test_a_run_through_ccp_suite_run_is_not_bare` and `test_a_ccp_command_or_another_command_is_not_bare`, each `ok`, then `OK`.
  dry run (`15dbfe7a`): step 1 printed 2 lines (the constant and the guard); step 2 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 8 tests`; step 3 on its log listed both tests `ok`, then `OK`.
- id: `code-02`
  story: As a task writer, a step that runs the tests bare behind an `env`, `time` or `timeout` option is warned about.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat), with your open run.
  steps:
    1. Run `python3 -B -c 'from ccp import tasklog as t, doclang as d; r=t._tokens(d.get("python").test_command); print([t.runs_bare(t._tokens(c), r) for c in ("env -u X python3 -m unittest", "timeout -k 5 60 python3 -m unittest", "timeout -s KILL 60 python3 -m unittest", "env -i python3 -m unittest", "timeout python3 -m unittest")])'`.
    2. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_bare_test_runner_warning`.
    3. Run `grep -e env_time_and_timeout_options -e '^OK' <the log step 2 names>`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_bare_test_runner_warning --revert ccp/tasklog.py`.
  expect: step 1 prints `[True, True, True, True, False]`; step 2 exits 0; step 3 lists `test_bare_past_env_time_and_timeout_options` `ok`, then `OK`; step 4 prints the mutant `killed`.
  dry run (`15dbfe7a`): step 1 printed `[False, False, False, True, False]`; step 2 (scratch QUEUE_ROOT) printed `passed, exit 0, lane part … 8 tests`; step 3 on its log printed only `OK` (the test is new); step 4: n/a — `--revert` needs the branch.
- id: `cfg-01`
  story: As the architect, E4's import check skips a tracked test file it cannot read, names it, and still finds an import in the others.
  setup: A checkout of the PR head at `<checkout>`, in your own worktree. A scratch git repo `<repo>` outside it: `tests/test_a.py` holding `x = 1`, `tests/test_b.py` holding `def (`, `tests/test_c.py` holding `x = 1`, all added (`git add tests`); then `tests/test_a.py` deleted from the working tree (not from the index).
  steps:
    1. In `<repo>`, run `bash -c "$(python3 -B -c "import json;print([p for c in json.load(open('<checkout>/docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4' for p in c['cmd'].split(' && ') if 'from tests' in p][0])")"; echo "exit $?"`.
    2. Write `from tests import test_x` into `<repo>/tests/test_c.py`, then run step 1's command again.
    3. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_self_hosting.TestModulesImportNoTestModule` in `<checkout>`.
    4. Run `grep -e cannot_read -e '^OK' <the log step 3 names>`.
  expect: step 1 prints `E4: skipped tests/test_a.py: …` and `E4: skipped tests/test_b.py: …`, no traceback, then `exit 0`; step 2 prints the same two lines and `tests/test_c.py:1`, then `exit 1`; step 3 exits 0; step 4 lists `test_the_check_skips_a_tracked_test_file_it_cannot_read_and_says_so` `ok`, then `OK`.
  dry run (`15dbfe7a`): step 1 printed a `FileNotFoundError` traceback for `tests/test_a.py`, then `exit 1`; steps 3 and 4: n/a — the test is new (step 3's module runs today, its 3 tests passing).

## Implementation notes

- `runs_bare` (`ccp/tasklog.py`): the prefix walk is now an index loop with a helper `_skip_options` that, after `env`, `time` or `timeout`, skips each `-` word and the next word too when the option is in `PREFIX_OPTION_ARGS[prefix]`. `timeout` is read past only when a `TIMEOUT_RE` duration follows its options, else the walk stops at `timeout` (so `timeout -k 5 python3 -m unittest` and `timeout python3 -m unittest` stay not bare). `CCP_COMMANDS`, its guard and the docstring sentence are removed.
- E4's import part (`docs/delivery/plane.json`) is a multi-line `python3 -B -c` program (newlines inside its quotes, no ` && `): a `for` loop with `try`/`except (OSError, SyntaxError, ValueError)` prints `E4: skipped <path>: <message>` on stderr and goes on; hits still print `<path>:<line>` on stdout, exit 1 on a hit, 0 otherwise.
- New tests: `test_bare_past_env_time_and_timeout_options` (`RunsBare`) and `test_the_check_skips_a_tracked_test_file_it_cannot_read_and_says_so` (`TestModulesImportNoTestModule`).
- Fix round 1 (review MINOR-1, NIT-1; tests only, no code change): `test_bare_past_env_time_and_timeout_options` also asserts `timeout -k 5 foo python3 -m unittest` and `timeout foo python3 -m unittest` are not bare, which pins the duration check after `timeout`'s options; the E4 test tracks a fourth file, `tests/test_d.py` holding non-UTF-8 bytes, and asserts its `skipped` line in both runs, which pins `ValueError` in the part's `except`.

## Verification notes
- 2026-11-24 — verifier, PR #377 head `476ee34` (squash `7584bb9`): APPROVE. Passed: code-01, code-02, cfg-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0309-the-bare-runner-warning-reads-past-env-and-timeout-options-and-e4-skips-a-test-file-it-cannot-read.json.

