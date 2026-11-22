---
task_id: 0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured
title: ccp tasks check warns on a check step that runs the language's test command outside ccp suite run, a brief sign-off of a stale brief prints what changed its paths, the writing-tasks skill says how a check runs tests and how a new task meets a pending ruling, and E4's command finds every form of a test-module import
status: pending
kind: feature
depends_on: ["0275-stale-briefs-reach-who-acts-and-a-respawn-keeps-the-lead-s-scope", "0298-the-cli-reference-reads-each-span-s-flags-and-tests-take-the-plane-root-and-git-env-from-helpers"]
spec_refs: ["S3", "S5", "S21"]
rule_refs: ["E21", "E4"]
review_refs: ["ar-20261122T141424Z-e148#F03"]
review_point: R27
paths: ["ccp/tasklog.py", "ccp/lifecycle.py", "plugin/skills/writing-tasks/SKILL.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "tests/test_bare_test_runner_warning.py", "tests/test_sign_off_stale_brief.py", "docs/delivery/plane.json", "tests/test_self_hosting.py", "docs/ENGINEERING.md"]
adopt: "none"
sign_off: brief
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured

## Intent

A task writer learns, from `ccp tasks check`, that a check step running the tests bare gives the verifier
nothing to cite, and writes it through `ccp suite run`, so the verifier runs it once. A lead recording the
operator's sign-off on a brief sees, at that moment, the merges that changed the brief's paths since it was
measured, so a ruling a later task has overtaken is caught before it is signed rather than by the implementer.
The writing-tasks skill says both, and says how a new task that changes logic a pending brief rules on meets
that ruling. The architect's E4 command finds a test module importing another in every form Python allows, so no
such import slips past it now that the gate's cache treats every test module as a leaf.

## Context (not checked)

From the triage of architect pass `ar-20261122T141424Z-e148` (F03) and the lead's process note on 0271 and
0291 (the record is in `docs/delivery/reviews/`, its third question). Measured at `d17505a`.

- **F03.** Task files 0260-0298 with a bare step (`grep -l 'Run .python3 -B -m unittest' docs/delivery/tasks/02[6-9]*.md | wc -l` at `d17505a`: 28 of 39).
  `templates/prompts/_common.md` says "Never a bare test runner … it records
  nothing you can cite", and `plugin/agents/delivery-verifier.md` says a cited test run is a recorded one, so a
  verifier runs such a step for its output and again recorded (0294's verifier's note, queue data).
  `grep -c 'unittest\|suite run --lane part --' plugin/skills/writing-tasks/SKILL.md` at `d17505a`: 0, the skill
  says nothing on how a check runs tests. The language's test command is the pack's (`doclang.for_tests(cfg).test_command`;
  Python's `python3 -m unittest`), so the check names no runner of its own (E18).
- **Pending briefs it will name** (`grep -l 'Run .python3 -B -m unittest' $(grep -l '^status: pending' docs/delivery/tasks/*.md) | wc -l` at `d17505a`: 10):
  0275, 0278, 0283, 0285, 0286, 0292, 0293, 0296, 0297, 0298. A warning never
  fails, and the signed ones keep it until they close.
- **The process note.** 0271's brief was measured at `76f41dd` and signed at 2026-11-22T12:57:49Z (its `sign_off`
  event, head `1416898`). 0291 (`932d480`, merged 11:03:22Z) had already changed `ccp/mutate.py`, one of 0271's
  `paths`, and ruled the not-found refusal differently; 0271's implementer met the clash and raised a scope
  question, and the lead ruled the narrow reading (0271's ruling r1), leaving follow-up `implement#1` open.
  `"def stale_context"` in `ccp/tasklog.py` would have named `932d480` at the signing, but nothing showed it then:
  `"def sign_off"` in `ccp/lifecycle.py` reads no staleness. 0285 (signed the same minute, measured at `76f41dd`)
  rules a `--test` help text that 0271 has since overtaken. At `d17505a`, `ccp tasks check` gives a stale-Context
  warning for 7 pending tasks (`CCP_DEV=1 ./bin/ccp --root . tasks check 2>&1 | grep -c 'Measured at'`), all but
  two of them signed: the signal is coarse (any commit on a path), so a refusal would send nearly every brief back
  for a refresh before each signing; this task warns.
- **E4's import check.** 0295's open follow-ups (`review#1`, `fix#1`, `verify#1` of
  `0295-package-docs-name-rules-by-id-and-every-test-module-is-a-cache-leaf`): plane.json `architect.checks` `E4`'s
  import part, `! git grep -nE '^[[:space:]]*(from tests\.test_|from tests import test_|import tests\.test_|from \.test_)' -- tests`
  at `d17505a`, misses `from . import test_x`, `from tests import a, test_x` and a parenthesised `from tests import (…)`
  spanning lines. Since 0295 the gate's cache treats every test module as a leaf (an input of itself only), so such an
  import would let a stale cache hit stand. `tests/test_self_hosting.py`'s `e4_import_check` takes the one part of the
  command holding `from tests`; `test_the_check_finds_each_way_to_import_a_test_module` lists five forms. 0298 (in
  flight) adds two greps to the same command, hence the dependency. E4's rule text already covers every form ("no
  module imports a test module").
- **0275 first.** 0275 (signed, in flight) shows the stale-Context warning to the lead at the spawn and to the
  implementer in its prompt, and adds `ccp tasks check --stale`; it covers merges after a signature. It edits the
  same §21.1 paragraph (the next sentence) and `"def warnings"`.

### Rulings for the build (the lead's)

- **The bare-runner warning.** For a task not yet done or dropped, each check step's backticked commands
  (as `"def _check_refactor_gate"` reads them) are split into simple commands at `|`, `||`, `&&` and `;`. One
  is bare when, after leading `NAME=value` words and an `env`, `time` or `timeout N` prefix, its words, less those
  that start with `-` and are not among the pack command's words, start with the pack command's words. A command
  that starts with `ccp` or `bin/ccp` (`./bin/ccp`) is never bare. Each task with a bare step gets one warning:
  "`<rel>`: dod_check(s) `<ids>` run `<pack command>` outside `ccp suite run`: run tests through `ccp suite run
  --lane <part lane> -- <command>` and cite its log (§21.1)", the part lane from `lane_for(cfg, "part")`. A pack
  with no test command gives none.
- **The sign-off warning.** `ccp tasks sign-off --stage brief` (or a single due `brief` stage), given neither
  `--head` nor `--from`, prints each line `stale_context` gives for the task on stderr as `warning: …`, then records
  as today; exit code and payload unchanged.
- **The skill.** `plugin/skills/writing-tasks/SKILL.md`, *Commands and searches in checks*, gains: "**A check that
  runs tests runs them through `ccp suite run`** (`bin/ccp suite run --lane <part lane> -- <test command> <tests>`),
  so the run is recorded, and pins a named test by grepping that run's log; never a bare test runner's output.
  `ccp tasks check` warns on a step that runs the language's test command bare." *Changing a task* gains: "**Before
  you ask the operator to sign a brief**, re-read it against the commits `ccp tasks check --stale` names for it;
  `ccp tasks sign-off` prints them again as it records." and "**A new task that changes logic a pending brief rules
  on** names it in `clashes_with` and says in Context how the two rulings fit; when the pending brief is signed,
  the new task builds on its ruling or waits for it in `depends_on`."

- **E4's import part** becomes one `python3 -B -c` program (no ` && ` inside it, and its text keeps the words
  `from tests`, so `e4_import_check` still finds the one part) that parses each `tests/*.py` file git tracks
  (`git ls-files`) with `ast` and exits 1, printing `<path>:<line>` for each, on: an `import` of a name starting
  `tests.test_`; a `from` import whose module's last part starts `test_` (`tests.test_a`, `.test_a`); and a `from`
  import from `tests` or from `.` (no module) that imports a name starting `test_`, parenthesised or not. It exits 0
  otherwise. `test_the_check_finds_each_way_to_import_a_test_module` gains `from . import test_a`,
  `from tests import a, test_a` and `from tests import (\n    a,\n    test_a,\n)`; the fixture test keeps passing.
- **E4's `check:` line** in `docs/ENGINEERING.md` names the parts as they then are: after 0298 it reads "(five greps
  and the long-literal count it holds at or below its figure)"; this task makes it "(four greps, an import check over
  the tracked test files, and the long-literal count it holds at or below its figure)". E4's rule text is unchanged.
- **The skill's clash sentence** keeps the words `pending brief rules on` on one line, as doc-01 reads them.

## Scope

- **In:** `ccp/tasklog.py` (`"def warnings"`, the bare-runner reader), `ccp/lifecycle.py` (`"def sign_off"`),
  `plugin/skills/writing-tasks/SKILL.md`, `docs/delivery/plane.json` (E4's import part), `tests/test_self_hosting.py`,
  `docs/ENGINEERING.md` (E4's `check:` line only), `tests/test_bare_test_runner_warning.py` (new),
  `tests/test_sign_off_stale_brief.py` (new).
- **SPEC, signed before the claim (`sign_off: brief`):** one passage in `docs/spec/01-model.md` and one in
  `docs/spec/03-quality.md`, each CURRENT at `3368264`.

    CURRENT (`docs/spec/01-model.md` at `3368264`), §3.5, the paragraph on `ccp tasks sign-off`:
    > A later record of a stage replaces the earlier.

    PROPOSED:
    > A later record of a stage replaces the earlier. A `brief` sign-off recorded without `--head` or `--from` for a task whose Context is stale (§21.1) prints that warning on stderr, naming the commits, and is recorded all the same, so the lead sees what has changed the brief's paths since it was measured; a brief that no longer holds is amended and signed again.

    CURRENT (`docs/spec/03-quality.md` at `3368264`), §21.1, the paragraph that starts "It warns, without failing":
    > It warns, without failing, when a task not yet done names a later task as a prerequisite in prose: the prerequisite goes in `depends_on` instead.

    PROPOSED:
    > It warns, without failing, when a task not yet done names a later task as a prerequisite in prose: the prerequisite goes in `depends_on` instead. It warns about a task not yet done with a check step that runs the language pack's test command (§21.4) outside `ccp suite run`, naming the checks: a check runs tests through `ccp suite run`, so the run is recorded (§14.4) and its log can be cited.
- **Out:** a refusal at sign-off; `stale_context`'s rule; the verifier's and implementer's briefs (already say it);
  rewriting existing tasks' steps.

## dod_checks

- id: `spec-01`
  story: As the operator, §3.5 and §21.1 say what I signed.
  setup: A checkout of the PR head.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0301`.
  expect: exit 0, both PROPOSED passages found.
  dry run (simulated at `d17505a`: this task file committed, then each passage applied, its CURRENT found once, committed in a scratch copy; `CCP_DEV=1 ./bin/ccp verify spec-text 0301 --base HEAD~1`): `"ok": true`, every passage found.
- id: `cmd-01`
  story: As a task writer, a check that runs the tests bare is named, and one through ccp suite run is not.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_bare_test_runner_warning`.
    2. Run `grep -e bare -e '^OK' <the log step 1 names>`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_bare_test_runner_warning --mutant-file <file>`, the file's mutant making a command that starts with `bin/ccp` count as bare.
  expect: step 1 exits 0; step 2 lists, each `ok`, tests whose names hold `bare` showing that a pending task whose step is `` `python3 -B -m unittest -v tests.x 2>&1 | grep OK` `` gets one warning naming that check, that `` `CCP_DEV=1 ./bin/ccp suite run --lane part -- python3 -m unittest tests.x` `` and a done task's bare step get none, and that a product whose pack has no test command gets none; then `OK`. Step 3 prints the mutant `killed`.
  dry run: n/a — the module is new.
- id: `cmd-02`
  story: As the lead recording a brief sign-off, I see the merges that changed the brief's paths since it was measured.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_sign_off_stale_brief`.
    2. Run `grep -e stale -e '^OK' <the log step 1 names>`.
  expect: step 1 exits 0; step 2 lists, each `ok`, tests whose names hold `stale` showing that, for a task with `sign_off: brief` whose Context says ``Measured at `<sha>` `` and a later commit changing one of its paths, `ccp tasks sign-off` prints a `warning:` line naming that commit and records the sign-off (exit 0, the event written), and that with `--head` given it prints no such line; then `OK`.
  dry run: n/a — the module is new.
- id: `doc-01`
  story: As a task writer reading the skill, I know how a check runs tests and how my task meets a pending ruling.
  setup: A checkout of the PR head.
  steps:
    1. Run `grep -c -F -e '<test command> <tests>' -e 'tasks check --stale' plugin/skills/writing-tasks/SKILL.md`.
    2. Run `grep -c -F 'pending brief rules on' plugin/skills/writing-tasks/SKILL.md`.
  expect: step 1 prints `2` (the test-run token, and the stale-brief token in *Changing a task*); step 2 prints `1`.
  dry run (`d17505a`): step 1 printed `0`; step 2 printed `0`.
- id: `cfg-01`
  story: As the architect, E4 fails on a test module importing another in any form.
  setup: A checkout of the PR head, in your own worktree.
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest -v tests.test_self_hosting`.
    2. Run `grep -e each_way -e fixture -e '^OK' <the log step 1 names>`.
    3. Run `bash -c "$(python3 -B -c "import json;print([c['cmd'] for c in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if c['id']=='E4'][0])")"; echo "exit $?"`.
    4. Run `c=$(python3 -B -c "import json;print([x['cmd'] for x in json.load(open('docs/delivery/plane.json'))['architect']['checks'] if x['id']=='E4'][0])") && d=$(mktemp -d) && mkdir "$d/tests" && printf 'from tests import (\n    a,\n    test_a,\n)\n' > "$d/tests/test_b.py" && git -C "$d" init -q && git -C "$d" add tests && (cd "$d" && bash -c "$c"); echo "exit $?"`.
  expect: step 1 exits 0; step 2 lists `test_the_check_finds_each_way_to_import_a_test_module` and `test_the_check_lets_a_test_import_a_fixture_module`, each `ok`, the first holding the three new forms, then `OK`; step 3 ends `exit 0` (the plane's own tests import no test module); step 4 ends `exit 1` (the parenthesised import spanning lines is found).
  dry run (`d17505a`): steps 1 and 2: n/a — the three forms are the build's; step 3 printed `exit 0`; step 4 printed `exit 0` (today's grep misses the form).

## Implementation notes

## Verification notes
