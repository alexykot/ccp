---
task_id: 0318-module-docstrings-state-no-exit-codes-or-spec-grammar-and-the-queue-readme-loses-its-stale-rules
title: The suite, mutate, report, init, sandbox, architect and rules module docstrings state no exit code, refusal list or SPEC grammar, E24's two counts drop to match, and the queue README loses its stale Rules table
status: done
kind: refactor
depends_on: []
rule_refs: ["E24", "E10"]
review_refs: ["ar-20261123T230912Z-197a#F03", "ar-20261123T230912Z-197a#F08"]
review_point: R32
paths: ["ccp/suite.py", "ccp/mutate.py", "ccp/report.py", "ccp/init.py", "ccp/sandbox.py", "ccp/architect.py", "ccp/rules.py", "docs/delivery/plane.json", "queue/README.md"]
clashes_with: ["0191-the-grace-release-ends", "0310-worker-briefs-name-suite-run-affected-and-log-texts-follow-the-pruning-of-every-suite-run-log", "0311-suite-affected-and-suite-run-affected-run-a-staged-part-lane-as-declared", "0312-every-atomic-write-takes-a-unique-temporary-name-and-removes-it-when-the-write-fails", "0319-the-pack-stops-matching-a-path-the-affected-map-names-by-name-so-a-plane-json-edit-runs-the-tests-that-read-it"]
adopt: "none"
created: 2026-11-24
updated: 2026-11-24
---

# Task: 0318-module-docstrings-state-no-exit-codes-or-spec-grammar-and-the-queue-readme-loses-its-stale-rules

## Intent

A rule change edits the SPEC and the code, not also a module docstring that restates it. The seven module
docstrings that state exit codes, and the ones that list refusals or repeat a § grammar, name the § they
implement and what the module is for, as E24 says; E24's checks hold the lower counts. The queue's README
stops naming a file that does not exist and stops advising a clear-out of the queue that `ccp health` and the
architect read.

## Context (not checked)

Findings F03 and F08 of architect pass `ar-20261123T230912Z-197a` (`docs/delivery/reviews/ar-20261123T230912Z-197a.md`),
and E24 as that triage amended it, with its second count in `architect.checks` `E24`.

Measured at `bb102371`, with `git ls-files 'ccp/*.py' | python3 -c '…'` over each module docstring
(`ast.get_docstring`): its line count, its `exits? [0-9]` matches and its `refuse` matches:

- **Exit codes** (`exits? [0-9]`), 7 modules: `ccp/suite.py` 4, `ccp/sandbox.py` 2, and 1 each in `ccp/architect.py`,
  `ccp/init.py`, `ccp/mutate.py`, `ccp/report.py` and `ccp/rules.py`. E24's second count holds 7 after the triage.
- **Over 30 lines**, 15 modules (E24's first count holds 15): among them `ccp/mutate.py` 43, `ccp/suite.py` 43,
  `ccp/report.py` 41 and `ccp/init.py` 35. Refusals (`refuse`): `ccp/report.py` 4, `ccp/init.py` 3,
  `ccp/mutate.py` 3, `ccp/sandbox.py` 3.
- **SPEC grammar in mutate's docstring.** It says a `--mutant-file` text is "what lies between its marker line and
  the next (or the file's end), less the one line break that ends it", which §20.6 (`docs/spec/03-quality.md`, the
  `--mutant-file` bullet) says in the same words; 0300 (`ec6c0682`) changed both.
- **The queue README.** `queue/README.md`'s Rules table holds `Point \`QUEUE_ROOT\` / \`project.example.yaml\`
  \`queue_root\` here` (`git ls-files | grep -ci project.example`: 0) and `Clear or rotate between slices`, while the
  queue keeps the ledger, the suite records and `health/notes.jsonl`, which `"def add_note"` (`ccp/health.py`) appends to
  and the architect's prompt reads. The paragraphs above the table already say it is runtime only and outside git, and
  point to §23.7.
- **Ruled.** In those seven module docstrings, every exit code, refusal list and restated § grammar goes. A fact the
  SPEC holds is cut, and the docstring names its § instead; a fact the SPEC does not hold moves to the docstring of
  the function that implements it, and the implementer lists each such move in its report. `ccp/mutate.py`,
  `ccp/suite.py`, `ccp/report.py` and `ccp/init.py` each come to at most 30 lines. `ccp/architect.py` (35 lines,
  one exit statement) loses its exit-code sentence and any refusal or § grammar it restates, and no more: its length
  is no target, so it may stay over 30. The over-30 count is then at most 11 (11 if `ccp/architect.py` stays over 30,
  10 if the cut takes it under). In `docs/delivery/plane.json`, `architect.checks` `E24` holds `exit_max = 0` and
  `long_max = <the over-30 count measured at the build's head>`, the second figure `doc-01` prints. `queue/README.md` loses its
  `## Rules` heading and table; nothing else in it changes.
- **No SPEC change**: the build cuts copies and writes no SPEC or docs/cli text.

### Ruling 0318-module-docstrings-state-no-exit-codes-or-spec-grammar-and-the-queue-readme-loses-its-stale-rules-r1

As the runner passed it (lead, 2026-11-24, spec question `sm-20261124T012740Z-c6bd`):

> Option (a): cut the §19.6 restatements in ccp/architect.py's module docstring (the two sentences on the failed-pass
> grace restart and the two-failed-passes rule; keep the §19.6 pointer), and set E24's long_max to the count measured
> at the build's head (10 if architect.py drops under 30). No check needs amending: read the brief at the task branch's
> merge base (it is on main after the #372 review fix): cfg-01 expects `long_max = <n>` with n from doc-01, and doc-01
> expects at most 11. If your task file copy differs, merge origin/main in first.
>
> Also fix review round 1's MINOR 1 and NIT: (MINOR 1) ccp/init.py module docstring: do not credit §4.5 with every
> warning; name §25.1 for the missing allowance_cmd warning and §31.3 for the queue-leftovers warning, and add one
> clause to `init`'s docstring that it warns of task files with no frontmatter (`ccp tasks migrate`), a fact no § holds.
> (NIT) name the two knobs `grace_tasks` and `triage_grace_tasks` in `gate()`'s docstring in ccp/architect.py.
> Behaviour must stay unchanged.

## Scope

- **In:** the module docstrings of `ccp/suite.py`, `ccp/mutate.py`, `ccp/report.py`, `ccp/init.py`, `ccp/sandbox.py`,
  `ccp/architect.py` and `ccp/rules.py`, and the function docstrings a moved fact goes to; `docs/delivery/plane.json`
  (`architect.checks` `E24`, its two figures only); `queue/README.md` (the Rules table).
- No SPEC change.
- **Out:** any code; the other eleven modules over 30 lines; `docs/ENGINEERING.md` (amended by the triage).

## dod_checks

- id: `doc-01`
  story: As a plane developer, no module docstring states an exit code, and the four long ones are short.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git ls-files 'ccp/*.py' | python3 -c 'import ast,re,sys; ds={p: ast.get_docstring(ast.parse(open(p).read())) or "" for p in sys.stdin.read().split()}; print(sum(bool(re.search(r"exits? [0-9]", d)) for d in ds.values()), sum(len(d.splitlines()) > 30 for d in ds.values()), [len(ds[f"ccp/{m}.py"].splitlines()) for m in ("mutate", "suite", "report", "init")])'`.
  expect: prints `0 <n> [a, b, c, d]`, with `<n>` at most 11 and each of `a` to `d` at most 30.
  dry run (`bb102371`): printed `7 15 [43, 43, 41, 35]`.
- id: `cfg-01`
  story: As the architect, E24's check holds the lower counts.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `cmd=$(python3 -c 'import json; print([c["cmd"] for c in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if c["id"] == "E24"][0])'); echo "$cmd" | grep -oE '(long|exit)_max = [0-9]+' | tr '\n' ' '; echo; bash -c "$cmd"; echo "exit=$?"`.
  expect: the first line is `long_max = <n> exit_max = 0 `, with `<n>` the figure `doc-01` printed; then `exit=0`.
  dry run (`bb102371`, with this triage's plane.json): printed `long_max = 15 exit_max = 7 `, then `exit=0`.
- id: `doc-02`
  story: As an operator, the queue README neither names a file that does not exist nor advises clearing the queue.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -c -e 'project.example' -e 'slices' -e '## Rules' -- queue/README.md; git grep -c '§23.7' -- queue/README.md`.
  expect: the first grep prints nothing (exit 1); the second prints `queue/README.md:1`.
  dry run (`bb102371`): printed `queue/README.md:3`, then `queue/README.md:1`.
- id: `code-01`
  story: As a plane developer, cutting the docstrings changed no code.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `for f in ccp/suite.py ccp/mutate.py ccp/report.py ccp/init.py ccp/sandbox.py ccp/architect.py ccp/rules.py; do diff <(git show $(git merge-base origin/main HEAD):$f | python3 -c 'import ast,sys; t=ast.parse(sys.stdin.read()); [setattr(n, "body", n.body[1:]) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str)]; print(ast.dump(t))') <(python3 -c 'import ast,sys; t=ast.parse(open(sys.argv[1]).read()); [setattr(n, "body", n.body[1:]) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str)]; print(ast.dump(t))' $f) >/dev/null && echo "$f same" || echo "$f differs"; done`.
  expect: seven lines, each `<file> same`: with every docstring set aside, each module's syntax tree is the one at the merge base.
  dry run (`bb102371`): printed the seven `same` lines (the checkout is its own merge base).

## Implementation notes

- Premises re-measured at `261e7ef7`: the same figures as at `bb102371` (7 modules with an exit statement, 15 over
  30 lines, the four refusal counts, no `project.example` file).
- The seven module docstrings now name their § and what the module is for. Cut as SPEC-held: every exit code,
  refusal list and `--mutant-file`/`check:` grammar. Moved, as facts the SPEC does not hold, to function
  docstrings: `ccp/suite.py` `run` (a command after `--` runs from the current directory; a run that records
  nothing takes no lock) and `_run_stage` (the watchdog); `ccp/mutate.py` `together` (its files and digest) and
  `_test` (`PYTHONDONTWRITEBYTECODE`); `ccp/report.py` `submit` (what a correction rewrites and what it leaves);
  `ccp/init.py` `init` (the refusals §4.5 does not list); `ccp/rules.py` `rule_blocks` (a `docs` check's trailing
  description). The sandbox's moved facts were already in `seal`, `remove` and the `REFUSED` comment.
- `ccp/architect.py` loses only its exit-code sentence (now a § pointer) and stays over 30 lines (32), so the
  over-30 count is 11: E24 holds `long_max = 11` and `exit_max = 0`.
- Fix round 1 (the lead's ruling r1, in Context): `ccp/architect.py`'s module docstring loses the two §19.6 sentences on
  the failed-pass grace restart and the two-failed-passes rule (the § pointer stays) and drops under 30 lines, so the
  over-30 count measured at the head is 10 and E24 holds `long_max = 10`. `gate()`'s docstring names the knobs
  `grace_tasks` and `triage_grace_tasks`. `ccp/init.py`'s module docstring credits §25.1 with the missing
  `allowance_cmd` warning and §31.3 with the queue-leftovers warning, and `init`'s docstring says it warns of task
  files with no frontmatter (`ccp tasks migrate`). Docstrings and the one figure only; no code changed.

## Verification notes
- 2026-11-24 — verifier, PR #376 head `8d3eaf2` (squash `fb06104`): APPROVE. Passed: doc-01, cfg-01, doc-02, code-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0318-module-docstrings-state-no-exit-codes-or-spec-grammar-and-the-queue-readme-loses-its-stale-rules.json.

