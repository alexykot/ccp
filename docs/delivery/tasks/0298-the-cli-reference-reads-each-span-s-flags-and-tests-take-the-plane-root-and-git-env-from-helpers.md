---
task_id: 0298-the-cli-reference-reads-each-span-s-flags-and-tests-take-the-plane-root-and-git-env-from-helpers
title: The CLI reference test holds each call span's flags to the commands that span names, the cache-leftover rule's symlink branch has tests, test_tasks_close drops its script mode, and E4 fails on a copied plane root or git identity
status: pending
kind: refactor
depends_on: []
rule_refs: ["E25", "E15", "E4"]
review_point: R26
paths: ["tests/test_cli_reference.py", "tests/test_wt_leftover.py", "tests/test_tasks_close.py", "tests/test_python_floor.py", "tests/test_rules.py", "tests/test_suite_affected.py", "tests/test_tasklog.py", "tests/test_estimate.py", "tests/test_machine_account.py", "tests/test_plane_workers_run_head.py", "docs/delivery/plane.json", "docs/ENGINEERING.md"]
clashes_with: ["0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0295-package-docs-name-rules-by-id-and-every-test-module-is-a-cache-leaf"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0298-the-cli-reference-reads-each-span-s-flags-and-tests-take-the-plane-root-and-git-env-from-helpers

## Intent

Four test-side leftovers close. The CLI reference test (E25) reads a flag as belonging to the commands
named in its own code span, so a docs row that joins two actions and gives one of them its sibling's
flag fails, as a row naming one action already does. `ccp wt remove`'s cache-only rule has a test for
its symlink branch: a symlinked directory in a leftover counts as a file, so the leftover stays and the
link's target is never read or removed. `tests/test_tasks_close.py` runs as every other module does,
with no script-mode import ahead of the tests' fence. And no test module computes the plane root or
writes git's identity of its own: each takes `PLANE_ROOT` and `GIT_ENV` from `tests/helpers.py`, and
the architect's E4 command fails on a new copy. No `ccp` behaviour changes.

## Context (not checked)

Covers these follow-ups (`ccp --root . tasks follow-ups --open`) and one review leftover:

- `0287-action-parsers-own-their-flags-and-describe-their-actions/implement#1`: a joined docs row's flags
  are credited to every command the row names.
- `0291-wt-remove-clears-a-cache-only-leftover-mutant-file-names-the-line-break-and-leak-check-reads-only-a-clean-where/implement#1`,
  `/review#1`, `/fix#1` and `/verify#1`: `_files_under`'s symlink handling has no test.
- `0290-test-modules-share-the-plane-root-and-git-env-and-helpers-import-lazily/implement#1`: nothing stops a module
  from computing the plane root or defining git's identity again. (`/implement#2`, the `tests/CLAUDE.md` line, goes to 0295.)
- 0290's review NIT, carried in its verify run's note: `tests/test_tasks_close.py` imports `helpers` before the fence in script mode.

Measured at `954bd72` (origin/main).

- **The CLI reference.** `"def problems_of"` in `tests/test_cli_reference.py` groups a doc's code by unit (a table
  row, a fenced line, a paragraph), takes every flag of the unit, credits it to every command the unit names
  (`credited.setdefault(strip_action(root, p), set()).update(flags)`) and checks it against the union of those
  commands' flags (`known = root.flags | {"--help"} | {fl for n in nodes for fl in n.flags}`). A probe at `954bd72` that
  puts the row `` `ccp adr index\|list [--stdout] [--json] [--dir DIR]` `` in place of the two `ccp adr` rows of
  `docs/cli/01-model.md` and calls `problems_of` on the copy printed `[]`, though `--stdout` is no flag of `ccp adr list`
  and `--json` and `--dir` are none of `ccp adr index`.
- **Can the docs express it.** Each row already writes each command's flags inside that command's own backticked span
  (`` `ccp tasks wait <id> <reason> [--until T] …` / `ccp tasks resume <id> [--detail …]` ``); a unit-wide reading flags 5
  rows whose prose names a second command (`ccp adr index|list` in the `ccp docs adr` rows' description, `ccp suite run`
  in `ccp suite affected`'s). A probe at `954bd72` reading each span on its own (`paths_in` on the span, `FLAG.findall` on
  the span) over every span that names a command found no flag outside its span's commands, and crediting each span's
  flags to its own commands (a span naming none credits the unit's, as today) left no parser flag uncredited.
- **The symlink branch.** `"def _files_under"` in `ccp/wt.py` adds `[rel / x for x in dirs if (Path(d) / x).is_symlink()]`;
  `os.walk` does not follow links. `tests/test_wt_leftover.py` holds `Leftover` (a recorded worktree git no longer lists)
  and `OnlyCaches` (plain values for `_only_caches`); `git grep -n '_files_under' -- tests` at `954bd72`: no line.
- **Script mode.** `git grep -nE '__name__ == "__main__":  #|^    from helpers import' -- tests` at `954bd72`: 2 lines, both in
  `tests/test_tasks_close.py` (the block before its `from ccp import …`). No other module runs as a script:
  `python3 -B tests/test_fence.py` at `954bd72` fails with `ModuleNotFoundError: No module named 'tests'`, as does any module that
  imports `tests.…`; the gate and `ccp suite` run modules with `-m unittest`. So script mode is dropped, not reordered.
- **Copies of the plane root and git's identity.** 0290 moved them to `tests/helpers.py` (`PLANE_ROOT`, `GIT_ENV`) but its grep
  covered only `parents[1]` and `GIT_ENV =`:
  `git grep -nF '__file__).resolve().parent' -- 'tests/*.py' ':(exclude)tests/helpers.py'` at `954bd72`: 4 lines (`tests/test_python_floor.py` `ROOT`,
  `tests/test_rules.py` `PLANE`, `tests/test_suite_affected.py` and `tests/test_tasklog.py` inline);
  `git grep -nw GIT_AUTHOR_NAME -- 'tests/*.py' ':(exclude)tests/helpers.py'` at `954bd72`: 3 lines in 3 files (`tests/test_estimate.py`,
  `tests/test_machine_account.py` `InitWarns.init`, `tests/test_plane_workers_run_head.py`). Two of them use the email `t@t` where
  `GIT_ENV` has `t@example.com`; no test reads an author's email or name back:
  `git grep -nE '%ae|%ce|%an|author.email|GIT_AUTHOR_EMAIL' -- 'tests/*.py' ':(exclude)tests/helpers.py'` at `954bd72`: the 3 dicts' own lines, nothing else.
  The one-command form `-c user.email=t@t -c user.name=t` is another shape, a git option on a single call
  (`git grep -l 'user.email=t@t' -- tests` at `954bd72`: 15 files), and stays: it defines no second environment.
- **E4.** Its plane.json command is three greps and a count joined by ` && `; `tests/test_self_hosting.py`'s `e4_import_check`
  takes the one part holding `from tests`, so two more parts leave it working. Its `check:` line in `docs/ENGINEERING.md` reads
  "(three greps and the long-literal count it holds at or below its figure)". E4's rule text already covers the copies
  ("A test names a plane constant or shared fixture fact … through the code or a fixture helper, never as a copied literal"),
  so the rule text does not change.

### Rulings for the build (the lead's)

- **CLI reference.** In `"def problems_of"`, each code span of a unit is read on its own: a span that names commands
  (`paths_in` on it, none of them delegated) holds its flags to every command it names, a flag no flag of one of them
  being the problem `f"{f.name}: `{fl}` is no flag of `ccp {' '.join(p)}`"` for that command, and credits them to those
  commands only. A span that names no command keeps today's reading against its unit's commands (credited to them, checked
  against their union). A new test, `test_a_joined_row_giving_an_action_its_siblings_flags_is_found`, makes the joined row
  of Context with `copy_with` and asserts `sorted(problems_of(d))` equals the three problems for `--dir` and `--json` on
  `ccp adr index` and `--stdout` on `ccp adr list`. The existing tests stay as they are.
- **Symlink branch.** `tests/test_wt_leftover.py` gains, in `Leftover`,
  `test_a_symlinked_directory_beside_a_cache_stays_and_its_target_is_untouched` (a leftover holding only the cache plus a
  symlink `.venv` to a temp directory that holds only a cache file: one warning, the directory and the link stay, the
  target's file is still there), and a plain-value test class `FilesUnder` whose test builds a tree with `a/f` and a link
  `l` to a directory holding files and asserts `sorted(wt._files_under(tree)) == [Path("a/f"), Path("l")]`.
- **Script mode.** The `if __name__ == "__main__":` block at the top of `tests/test_tasks_close.py` goes, with the `# noqa: E402`
  it made necessary and any import it alone used; the module's closing `unittest.main()` stays, as in every module.
- **Copies.** The four modules take `PLANE_ROOT` from `tests.helpers` in place of their own computation; the three take
  `GIT_ENV` (`{**os.environ, **GIT_ENV}`, or `env.update(GIT_ENV, HOME=…)` in `InitWarns.init`). If a test turns on the
  email or on reading a global git config, stop and ask.
- **E4.** Its command in `docs/delivery/plane.json` gains, after the import grep,
  ` && ! git grep -nF '__file__).resolve().parent' -- 'tests/*.py' ':(exclude)tests/helpers.py' && ! git grep -nw GIT_AUTHOR_NAME -- 'tests/*.py' ':(exclude)tests/helpers.py'`,
  and its `check:` line reads "(five greps and the long-literal count it holds at or below its figure)".

## Scope

- **In:** `tests/test_cli_reference.py`, `tests/test_wt_leftover.py`, `tests/test_tasks_close.py`, `tests/test_python_floor.py`,
  `tests/test_rules.py`, `tests/test_suite_affected.py`, `tests/test_tasklog.py`, `tests/test_estimate.py`,
  `tests/test_machine_account.py`, `tests/test_plane_workers_run_head.py`, `docs/delivery/plane.json` (E4's command),
  `docs/ENGINEERING.md` (E4's `check:` line only).
- No SPEC change: no § rule names the reference test, the cache rule's tests, script mode or E4's command
  (`git grep -n 'test_cli_reference\|_files_under\|run as a script\|architect.checks .E4' -- docs/spec` at `954bd72`: no line).
- **Out:** `ccp/wt.py` and `ccp/cli.py` (no code change); the docs/cli rows; E4's rule text; `tests/CLAUDE.md` (0295); the `-c user.email=… -c user.name=…` git calls.

## dod_checks

- id: `code-01`
  story: As a docs writer, a joined row that gives one action its sibling's flag fails the CLI reference test.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `python3 -B -m unittest -v tests.test_cli_reference 2>&1 | grep -e joined_row -e no_others -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_cli_reference --mutant-file <file>`, the file's mutant making a span that names commands credit and check its flags against its unit's commands, as at `954bd72`.
  expect: step 1 lists `test_a_joined_row_giving_an_action_its_siblings_flags_is_found` `ok` and `test_the_docs_hold_the_parsers_commands_and_flags_and_no_others` `ok`, then `OK`; step 2 prints the mutant `killed`.
  dry run (`954bd72`): the joined-row probe of Context printed `[]` from `problems_of`; `python3 -B -m unittest -q tests.test_cli_reference` printed `OK`.
- id: `code-02`
  story: As a plane developer, the cache-only leftover rule keeps a directory that holds a symlinked directory, and never touches its target.
  setup: A checkout of the PR head, in your own worktree (a delivery-verifier seat).
  steps:
    1. Run `python3 -B -m unittest -v tests.test_wt_leftover 2>&1 | grep -e symlinked -e FilesUnder -e '^OK'`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_wt_leftover --mutant 'ccp/wt.py: + [rel / x for x in dirs if (Path(d) / x).is_symlink()]=>'`.
  expect: step 1 lists `test_a_symlinked_directory_beside_a_cache_stays_and_its_target_is_untouched` `ok` and a `FilesUnder` test `ok`, then `OK`; step 2 prints the mutant `killed`.
  dry run: n/a — both tests are new; at `954bd72`, `python3 -B -m unittest -q tests.test_wt_leftover` printed `OK`.
- id: `code-03`
  story: As a plane developer, test_tasks_close runs like every other module, with nothing imported ahead of the fence.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -nE '__name__ == "__main__":  #|^    from helpers import' -- tests`.
    2. Run `python3 -B -m unittest -q tests.test_tasks_close 2>&1 | tail -1`.
  expect: step 1 prints nothing (exit 1); step 2 prints `OK`.
  dry run (`954bd72`): step 1 printed 2 lines in `tests/test_tasks_close.py`; step 2 printed `OK`.
- id: `cfg-01`
  story: As the architect, E4's command fails on a test module that computes the plane root or writes git's identity itself.
  setup: A checkout of the PR head, and a mutation worktree of it (`CCP_DEV=1 ./bin/ccp wt create --kind mut --task 0298 --sha HEAD --print`, removed afterwards with `ccp wt remove`).
  steps:
    1. In the checkout, run `bash -c "$(python3 -B -c "import json;print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4'][0])")"; echo "exit $?"`.
    2. In the mutation worktree, append the line `ROOT = Path(__file__).resolve().parent.parent` to `tests/test_rules.py`, `git add` it, run the same command, then `git checkout HEAD -- tests/test_rules.py`.
    3. In the mutation worktree, append the line `ENV = {"GIT_AUTHOR_NAME": "t"}` to `tests/test_rules.py`, `git add` it, and run the same command.
  expect: step 1 prints `exit 0`; steps 2 and 3 each print the planted line and `exit 1`.
  dry run (`954bd72`): step 1 printed `exit 0` (the command has no such grep); the two proposed greps at `954bd72` printed 4 and 3 lines (Context).

## Implementation notes

## Verification notes
