---
task_id: 0287-action-parsers-own-their-flags-and-describe-their-actions
title: ccp verify -h describes its actions and refuses a blank target, and the flat action parsers and ccp pr refuse another action's flag with the called action's usage
status: pending
kind: feature
depends_on: []
clashes_with: ["0271-mutate-takes-several-tests-refuses-a-no-op-and-names-the-failing-tests", "0272-the-lead-s-records-share-one-guard-and-one-actor-id", "0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0284-shared-test-fixtures-live-in-modules-that-hold-no-tests", "0285-seats-run-one-check-as-the-plane-does-and-lane-text-names-declared-lanes"]
spec_refs: ["S6", "S12", "S15", "S19", "S25", "S26", "S28"]
rule_refs: ["E25"]
review_point: R25
paths: ["ccp/cli.py", "docs/cli/01-model.md", "docs/cli/04-observability.md", "tests/test_verify_parser.py", "tests/test_action_parsers.py", "tests/test_wt.py", "tests/test_session_park.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0287-action-parsers-own-their-flags-and-describe-their-actions

## Intent

`ccp verify -h` says what each of its six actions does, and a blank target (`ccp verify check ''`) is
refused by the parser, naming the argument. Every command that takes its action as a first word and
whose actions take different flags (`ccp estimate`, `board`, `allowance`, `adr`, `docs adr`,
`architect`, `wt`) gives each action only its own flags: a flag that belongs to another action is
refused with the usage of the action that was called, instead of being accepted and ignored. `ccp pr`
refuses an unknown flag with the called action's usage, not the whole command's.

## Context (not checked)

The open follow-ups of 0269 (`ccp tasks follow-ups --open`), all three covered here:

- `0269-verify-actions-own-their-flags-and-prompts-link-cited-findings/implement#1`: other flat action
  parsers take every action's flags; `_OwnArgs` is ready to reuse; `ccp pr`'s subparsers print the
  top-level usage on an unknown flag (`ccp pr view 3 --bogus`).
- `0269-verify-actions-own-their-flags-and-prompts-link-cited-findings/review#1`: a non-blank `type=` on
  `ccp verify`'s target arguments.
- `0269-verify-actions-own-their-flags-and-prompts-link-cited-findings/verify#1`: the same, and `help=`
  on the verify action parsers.

Measured at `b5f2273` (origin/main).

- **verify -h.** `COLUMNS=200 CCP_DEV=1 ./bin/ccp verify -h | grep -cE '^ {4}(record|merge-ok|check|spec-text|later|deferred) +[a-z]'` at `b5f2273`: 0
  (the action parsers in `ccp/cli.py` `vf.add_parser("record")` … carry no `help=`).
- **Blank targets.** `record`'s FILE and `check`, `spec-text` and `later`'s TASK take any string;
  `merge-ok`'s PR already has `type=_pr_number`. At `b5f2273`, `ccp verify check '' --head abc`,
  `later '' …` and `record ''` stop on QUEUE_ROOT and `spec-text ''` prints `no task  in docs/delivery/tasks`.
- **Which flat parsers have the shape.** Twelve parsers take the action as a positional with `choices`: `grep -c 'add_argument("action"' ccp/cli.py ccp/otel.py` at `b5f2273`.
  Measured one by one (their help texts name the action each flag is for):
  - **In, seven**: `estimate` (`--dry-run` is backfill's), `board` (`task_id` is task's, `--quiet` and
    `--drain` build's), `allowance` (`--to`/`--reason` continue's, `--armed`/`--fire` session-wake's),
    `docs adr` (`--stdout` index's, `--json`/`--dir` list's), `wt` (nine create-only flags, `--task`
    create's and list's, `--print` exec's), `adr` (each flag one or two actions'), `architect` (`--mode`, `--lens`, `--adr`, `--force`,
    `--detach`, `--actor`, `--review-id` run's; `--backfill`, `--apply`, `review_id` triage's).
  - cli-03's probe, `python3 -B -` with its flag-of-another-action calls through `cli.build_parser().parse_args`, at `b5f2273`: none of fourteen refused.
  - **Out, five**: `review-points` and `health` have a default action called without its word
    (`ccp review-points [list] [--json]`, `ccp health [--since DATE] [--json]` in `docs/cli/03-quality.md` and
    `docs/cli/04-observability.md`): subparsers cannot take the default action's flags without the
    word unless the parent keeps them, which leaves them on every action. `sandbox` (one DIR both
    actions use, no flags) and `agent` (no arguments) have nothing to misplace. `otel` is its own parser
    in `ccp/otel.py`, which `ccp.cli.main` hands the words before `build_parser` runs (the receiver needs
    no product) and which `tests/test_cli_reference.py` holds as `DELEGATED`; reusing `_OwnArgs` there
    would mean moving it out of `ccp/cli.py`, more than a follow-up asks.
- **`ccp pr`.** `CCP_DEV=1 ./bin/ccp pr view 3 --bogus 2>&1 | head -1` at `b5f2273`: `usage: ccp [-h] [--root ROOT]`
  (the subparsers are made without `parser_class=_OwnArgs`). The other nested groups (`tasks`, `runs`,
  `suite`, `budgets`, `docs`, `auth`, `notify` and the rest) behave the same but no follow-up names
  them, and their actions already take only their own flags: Out.
- **Rulings.**
  - verify: each action parser gets `help=`, these texts: record `record the verifier's verdict from its
    JSON file (- for stdin)`; merge-ok `the runner's merge gate: whether the task's record approves the
    PR`; check `the merge gate's judgement at a given head, without the PR host`; spec-text `check the
    branch's SPEC lines against the signed text (§15.2)`; later `record the result of a deferred check
    run after its task closed (§15.4)`; deferred `the deferred checks still to record (§15.4)`.
  - verify targets: FILE and TASK take `type=_nonblank`, a new function beside `_pr_number` that returns
    the value unchanged and raises `argparse.ArgumentTypeError("takes a non-blank value, not " + repr(raw))`
    when `raw.strip()` is empty. argparse then prints `argument TASK: takes a non-blank value, not ''`,
    exit 2.
  - The seven: each becomes `add_subparsers(dest="action", required=True, parser_class=_OwnArgs)`, one
    parser per action, as 0269 did for verify. An action takes the flags its `docs/cli` row gives
    (`docs/cli/01-model.md`, `02-delivery.md`, `03-quality.md`, `04-observability.md`), with today's
    types, defaults, choices and help, plus the suppressed `board build --drain` and `architect run
    --review-id`; `estimate backfill` keeps `--json` (its handler reads it; `cmd_estimate`'s docstring
    gives it) and its row in `docs/cli/04-observability.md` becomes `ccp estimate backfill [--dry-run] [--json]`.
    Positionals keep their `nargs` and the handlers keep their arity checks (`adr`'s `args`, `board
    task`'s `task_id`, `architect triage`'s `review_id`, `wt`'s `name_arg` for remove, up, down, urls,
    exec). Each action parser's `help=` is its `docs/cli` row's description column with the backticks
    dropped (`docs adr index`/`list` take the `ccp adr index`/`list` rows'); `wt`'s rows name seats, so
    its texts are: create `make a task's worktree (base: run the command after -- at the merge base,
    then remove it; ver --baseline: the adoption baseline)`, remove `remove a worktree`, list `the
    recorded worktrees, or one task's`, up `run the worktree's env.up hook`, down `run the worktree's
    env.down hook and mark it down`, urls `the worktree's environment URLs`, gc `prune the worktrees
    of done or dropped tasks no one leases`, exec `run, or with --print print, a worktree's own bin/ccp`.
    The parent's `set_defaults` stay on the parent; `dest="action"` keeps `REFRESHES` matching.
    `docs/cli/01-model.md`'s row `ccp docs adr index|list [--stdout] [--json] [--dir DIR]` splits into
    `ccp docs adr index [--stdout]` and `ccp docs adr list [--json] [--dir DIR]`, each keeping the
    row's description and § column, so each row gives only its own action's flags.
  - Dropping `--actor` from `architect triage` and `--scope` from `architect status` is deliberate: it
    matches §19 (`docs/spec/03-quality.md` names `ccp architect triage <id>`, `triage --backfill`,
    `triage --apply` and a bare `ccp architect status`) and the `docs/cli/03-quality.md` rows, and nothing
    calls those forms: `git grep -nE "architect (triage|status)[^|\`]*--(actor|scope)" -- . ':!docs/delivery/tasks'` at `b5f2273`: nothing.
  - After the split, a flag given before the action word (for example `ccp wt --task X list`) is refused,
    since the flag now belongs to the action's parser. No caller does this:
    `git grep -nE "ccp (estimate|board|allowance|adr|architect|wt|docs adr) --[a-z]" -- . ':!docs/delivery/tasks'` at `b5f2273`: nothing, and
    `git grep -nE '"(estimate|board|allowance|adr|architect|wt)", "--' -- ccp tests scripts plugin` at `b5f2273`: only `tasks estimate` calls.
  - Where a shared handler reads an attribute for an action whose parser no longer defines it, that
    action's parser supplies it with `set_defaults` at today's default (for example `architect`'s
    `actor=None` on due, triage and status, `scope=None` on status). A hand refusal that only rejects a
    flag on an action that no longer takes it goes: `_allowance`'s `--armed and --fire are for
    session-wake`, `cmd_wt`'s `a.action != "create"` clauses of the `--shallow`, `--own-hooks` and
    `--baseline` refusals (their checks within `create` stay), and `cmd_wt_exec`'s `--timeout` refusal.
  - `ccp pr`: its `add_subparsers` takes `parser_class=_OwnArgs`. Nothing else in `pr` changes.
- **Tests this breaks** (each asserts a returned exit code that becomes argparse's `SystemExit`, which
  `ToolkitFixture.ccp` does not catch; the assertions change to `assertRaises(SystemExit)` with the same
  exit code, the fixture unchanged): `tests/test_wt.py` (`("list", "--baseline")` in
  `"def test_baseline_refuses_a_task_a_sha_a_name_another_kind_or_action"`, the `exec … --timeout` calls in
  `"def test_a_timeout_is_refused_and_nothing_runs"`, `self.wt("list", "--shallow")`, `self.wt("list",
  "--own-hooks")`, `self.wt("remove", "ver-0002", "--own-hooks")`) and `tests/test_session_park.py`
  (`self.ccp("allowance", "status", "--armed")` in `"def test_flags_are_for_session_wake_and_one_at_a_time"`).
  Found by `git grep -nE '"(exec|list|remove|gc|up|down|urls)"[^)]*"--(timeout|shallow|own-hooks|baseline|kind|sha|name|seat|tag|task|print)"' -- tests`
  and `git grep -nE '"(continue|status)"[^)]*"--(armed|fire|to|reason|sample)"' -- tests` at `b5f2273`; the
  architect, adr, board and estimate calls in `tests/` all pass flags their own action takes (same
  greps for those commands: no other hit).
- **No SPEC change:** `git grep -nE "unrecognized|own usage|exec takes none|--shallow is|non-blank|blank target" -- docs/spec docs/cli`
  at `b5f2273`: nothing; the SPEC names no parser refusal or help text. `docs/cli` changes only the
  estimate row and the split `docs adr` row (non-normative), so `tests/test_cli_reference.py` keeps holding the docs to the parser.

## Scope

- **In:**
  - `ccp/cli.py` (`_nonblank`, the verify action parsers' `help=` and target types, the seven parsers,
    the `pr` subparsers, the dead refusals in `_allowance`, `cmd_wt` and `cmd_wt_exec`).
  - `docs/cli/01-model.md` (the `docs adr` row, split), `docs/cli/04-observability.md` (the `estimate backfill` row).
  - `tests/test_verify_parser.py`, `tests/test_action_parsers.py` (new), `tests/test_wt.py`,
    `tests/test_session_park.py`.
- **Out:** `review-points`, `health`, `sandbox`, `agent`, `otel` (see Context); the nested subcommand
  groups other than `pr`; `ToolkitFixture`; the handlers' arity checks; verify `check`'s blank `--head`
  refusal.

## dod_checks

- id: `cli-01`
  story: As a verifier, `ccp verify -h` tells me what each action does.
  setup: A checkout of the PR head.
  steps:
    1. Run `COLUMNS=200 CCP_DEV=1 ./bin/ccp verify -h | grep -cE '^ {4}(record|merge-ok|check|spec-text|later|deferred) +[a-z]'`.
  expect: step 1 prints `6`.
  dry run (`b5f2273`): printed `0`.
- id: `cli-02`
  story: As a runner, a blank verify target is refused by the parser, naming the argument.
  setup: A checkout of the PR head, QUEUE_ROOT unset.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify check '' --head abc 2>&1 | grep -c 'argument TASK: takes a non-blank value'`.
    2. Run `CCP_DEV=1 ./bin/ccp verify spec-text ' ' 2>&1 | grep -c 'argument TASK: takes a non-blank value'`.
    3. Run `CCP_DEV=1 ./bin/ccp verify later '' --check x --pass --evidence e --produced-by verifier 2>&1 | grep -c 'argument TASK: takes a non-blank value'`.
    4. Run `CCP_DEV=1 ./bin/ccp verify record '' 2>&1 | grep -c 'argument FILE: takes a non-blank value'`.
  expect: steps 1 to 4 each print `1`.
  dry run (`b5f2273`): each printed `0` (1, 3, 4 stopped on QUEUE_ROOT; 2 printed `no task  in docs/delivery/tasks`).
- id: `cli-03`
  story: As a worker, a flag that belongs to another action of a flat command is refused with the called action's usage, and each action's own flags still parse.
  setup: A checkout of the PR head, QUEUE_ROOT unset.
  steps:
    1. Run this script from the checkout's root (it only parses; nothing runs), with stderr discarded:
       ```
       python3 -B - 2>/dev/null <<'EOF'
       from ccp import cli
       def refused(words):
           try:
               cli.build_parser().parse_args(words.split())
           except SystemExit as e:
               return e.code == 2
           return False
       bad = ['estimate accuracy --dry-run', 'board status --quiet', 'board build 0001', 'allowance status --to 5', 'allowance continue --sample', 'docs adr index --json', 'wt list --kind impl', 'wt gc --print', 'wt exec --task 0001', 'adr check --note x', 'adr index --json', 'architect due --mode shape', 'architect triage --force', 'architect status --lens docs']
       good = ['estimate backfill --dry-run --json', 'board build --quiet', 'board task 0001', 'allowance continue --to 5 --reason r', 'allowance session-wake --armed', 'docs adr list --json --dir d', 'wt create --kind impl --task 0001 --shallow --own-hooks', 'wt exec w1 --print', 'adr supersede 1 2 --decisions D2 --by D1 --archive', 'adr migrate --markers --dry-run', 'architect run --mode shape --adr 1 --actor x --review-id r --detach', 'architect triage ar-1 --apply ar-1', 'architect due --scope 0001']
       print(sum(map(refused, bad)), 'of', len(bad), 'refused;', sum(map(refused, good)), 'of', len(good), 'own refused')
       EOF
       ```
    2. Run `CCP_DEV=1 ./bin/ccp adr check --note x 2>&1 | head -1`.
  expect: step 1 prints `14 of 14 refused; 0 of 13 own refused`; step 2 prints a line starting `usage: ccp adr check`.
  dry run (`b5f2273`): step 1 printed `0 of 14 refused; 0 of 13 own refused`; step 2 printed `adr: clean`.
- id: `cli-04`
  story: As a reviewer, an unknown flag on a `ccp pr` action shows that action's usage.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp pr view 3 --bogus 2>&1 | head -1`.
  expect: step 1 prints a line starting `usage: ccp pr view`.
  dry run (`b5f2273`): printed `usage: ccp [-h] [--root ROOT]`.
- id: `test-01`
  story: As a plane developer, tests hold each converted parser, the verify help and blank-target refusals and the pr usage, they bite, and the CLI reference and the modules this breaks still pass.
  setup: A checkout of the PR head; then two separate copies of it: in copy A the `pr` subparsers are made without `parser_class=_OwnArgs`; in copy B verify `record`'s FILE has no `type=`.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_action_parsers tests.test_verify_parser tests.test_cli_reference tests.test_wt tests.test_session_park tests.test_adr tests.test_architect tests.test_verify_later`.
    2. In copy A, run `python3 -B -m unittest -q tests.test_action_parsers`.
    3. In copy B, run `python3 -B -m unittest -q tests.test_verify_parser`.
  expect: step 1 exits 0, `tests/test_action_parsers.py` holding, for each of the seven commands, a test that one flag of another action exits 2 with a usage line naming the called action, and a test that `ccp pr view 3 --bogus` shows `usage: ccp pr view`; `tests/test_verify_parser.py` holding a test that the six actions have non-empty help and that each of FILE and TASK refuses `''` with `takes a non-blank value`; steps 2 and 3 each exit non-zero.
  dry run (`b5f2273`): step 1 without `tests.test_action_parsers` (new) exited 0 (`OK`); steps 2 and 3 n/a (the tests are new).

## Implementation notes

- `ccp/cli.py`: `_nonblank` beside `_pr_number`; verify's six action parsers carry the ruled `help=` texts and
  FILE/TASK take `type=_nonblank`; `pr`'s subparsers take `parser_class=_OwnArgs`.
- The seven (`estimate`, `board`, `allowance`, `docs adr`, `wt`, `adr`, `architect`) are each
  `add_subparsers(dest="action", required=True, parser_class=_OwnArgs)`, one parser per action in the old
  `choices` order, each flag with today's type, default, choices and help string (a flag shared by two
  actions keeps its one help string, which names both). `ccp adr index|list` and `ccp docs adr index|list`
  share one builder, `_adr_index_list`. The parents keep their `set_defaults`; `architect` due, triage and
  status set `actor=None`, status `scope=None` too.
- Gone: `_allowance`'s `--armed and --fire are for session-wake`, `cmd_wt`'s `a.action != "create"` clauses
  (the checks within create stay), `cmd_wt_exec`'s `--timeout` refusal.
- Docs: the `docs adr` row split in `docs/cli/01-model.md`; `estimate backfill` gains `[--json]` in
  `docs/cli/04-observability.md`.
- Tests: `tests/test_action_parsers.py` (new); `tests/test_verify_parser.py` gains the help and blank-target
  tests; `tests/test_wt.py` and `tests/test_session_park.py` assert `SystemExit` code 2 where the parser now
  refuses.

## Verification notes
