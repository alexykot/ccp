---
task_id: 0308-module-docstrings-and-queue-docs-stop-restating-the-spec
title: The prompt, verify, submit, lifecycle and observability-lib docstrings name their § and purpose only, emit-event's help names the registry, and the queue's layout is described once, in the SPEC
status: pending
kind: refactor
depends_on: []
rule_refs: ["E24", "E10", "E12"]
review_refs: ["ar-20261122T162238Z-9098#F02", "ar-20261122T162238Z-9098#F05", "ar-20261122T162238Z-9098#F06"]
review_point: R28
clashes_with: ["0191-the-grace-release-ends", "0293-the-lead-s-preference-and-holds-need-the-lead-and-seat-ids-and-suite-roles-are-named-once", "0296-the-spec-question-script-loads-the-product-config-once-and-reads-its-task-dir", "0301-tasks-check-warns-on-a-bare-test-runner-and-a-brief-sign-off-shows-what-changed-since-measured", "0302-submit-names-no-review-record-it-lacks-and-skip-tests-share-one-integration-commit-helper", "0303-observability-writers-refuse-an-unknown-actor-before-writing-and-the-audit-docs-follow-the-constants", "0305-a-task-s-merge-is-read-one-way-and-close-s-merge-outcome-refusals-are-judged-on-plain-values", "0306-verify-record-refuses-a-head-that-is-not-the-verify-run-s-first-and-the-unused-re-verify-packet-goes"]
paths: ["ccp/prompt.py", "ccp/verify.py", "ccp/submit.py", "ccp/lifecycle.py", "docs/delivery/plane.json", "scripts/observability/lib.py", "scripts/observability/emit-event.sh", "scripts/observability/CLAUDE.md", "queue/README.md", "scripts/queue/README.md"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0308-module-docstrings-and-queue-docs-stop-restating-the-spec

## Intent

A rule change edits the SPEC and the code, not a third copy in a docstring or a README. The four ccp
modules this window's tasks edited most say which § they implement and what they are for, and stop
listing the refusals, overrides and exit codes the SPEC states; house rule E24's count of over-long
module docstrings falls from 18 to 15 and its check holds it there. The observability library stops
carrying its own wording of the §23.3 timer formulas and a § history of its event types, and
`emit-event.sh --help` names the registry instead of a partial list. The runtime queue's files are
described once, by §23.7: `queue/README.md` says what the directory is and points there, and the second
queue README under `scripts/queue/`, which holds no scripts, goes.

## Context (not checked)

From architect pass `ar-20261122T162238Z-9098`, F02 (`duplication`), F05 (`doc-aspirational`) and F06
(`doc-history`); the record is in `docs/delivery/reviews/`. Measured at `0f44fb3` (origin/main).

- **The module copies (F02).** `python3 -c` over `ast.get_docstring` of each module at `0f44fb3`: `ccp/prompt.py`
  47 lines (6 `exit <n>` statements, 13 mentions of a refusal), `ccp/verify.py` 40 (1, 5), `ccp/lifecycle.py` 53
  (4, 13), `ccp/submit.py` 12 (2, 2). 0278 (`git show --stat 94fc84c5`) changed one rule, a submit's proof reused
  by verify, and edited its text in the SPEC, docs/cli, `ccp/prompt.py`'s module and function docstrings and
  `ccp/submit.py`'s module docstring.
- **E24** (amended by this triage): a module docstring names the § it implements and what the module is for; it never lists the keys, checks, refusals, exit codes or formats the code or the SPEC holds. Its command, `architect.checks` `E24`, holds the count of ccp modules whose docstring is over 30 lines at or below 18 (`git ls-files 'ccp/*.py'` through the same `ast` count at `0f44fb3`: 18). Cutting `prompt`, `verify` and `lifecycle` under 30 lines takes it to 15.
- **The library (F06).** `scripts/observability/lib.py`'s module docstring holds "Timer formula (stable — SPEC §23.3): …", worded differently from §23.3 (`docs/spec/04-observability.md`); the comment above `REVIEW_EVENT_TYPES` starts "# §17.8 adds question + spec_maintainer types …" and tells which § added which type. `scripts/observability/CLAUDE.md` says "The timer formulas are SPEC §23.3 (`lib.py`'s docstring repeats them)". `emit-event.sh`'s usage lists `--type TYPE  phase|waiting_on|lease|claude|auth|seat|durable|note` and `--op OP  set|clear|transition|launch|exit|heartbeat|reconcile`, a part of `EVENT_TYPES` and `EVENT_OPS`. `git grep -n -e 'Timer formula' -e '§17.8 adds' -e 'docstring repeats' -- scripts` at `0f44fb3`: 2 lines (`lib.py` 2; the CLAUDE.md sentence is split across lines, so its check below reads it whole). The operator chose to keep the formulas in §23.3 alone (`ar-20261122T055103Z-11aa`, question 1, (a)).
- **The queue docs (F05).** `git grep -c -e 'running.json' -e 'last-session.json' -e 'blocker.md' -e 'watchdog' -e '§28.29' -- queue/README.md` at `0f44fb3`: 5 lines, each a file nothing writes, the retired watchdog or a § that does not exist. `git ls-files scripts/queue` at `0f44fb3`: 1 file, `scripts/queue/README.md`, a second, longer layout. §23.7 ("Who writes the queue files") already lists the files and their writers. `docs/delivery/plane.json` `package_docs.exempt_dirs` names `scripts/queue`; `templates/docs-delivery/README.md` points at `queue/README.md`, which stays.
- **Other tasks.** 0303 (pending) changes `lib.py`'s `validate_event` and `emit-event.sh`'s usage examples, and one
  sentence of `ccp/prompt.py`'s module docstring; 0296 (pending) edits a row of `scripts/queue/README.md`;
  0293 (claimed), 0305 and 0306 (pending) change code in `ccp/lifecycle.py`, `ccp/verify.py` or `ccp/submit.py`;
  0191 (pending) changes code in `ccp/prompt.py`, `ccp/lifecycle.py` and `lib.py`. Recorded as clashes where the
  files meet.

### Rulings for the build (the lead's)

- Each of the four ccp module docstrings keeps the § (or §§) the module implements, what the module is for, and
  how it relates to its neighbours, in at most 15 lines. It drops each refusal, override, exit code, key list and
  format the SPEC or docs/cli states. A fact it drops that neither states moves to the docstring of the function it
  describes; the build adds no SPEC or docs/cli text and lists any such fact in its report's `## Follow-ups`.
- `docs/delivery/plane.json` `architect.checks` `E24`'s figure goes from `-le 18` to `-le 15`.
- `lib.py`'s docstring drops the "Timer formula" block and says the timers are SPEC §23.3's; the comment above
  `REVIEW_EVENT_TYPES` goes (Git holds the history). `scripts/observability/CLAUDE.md` drops "(`lib.py`'s docstring
  repeats them)".
- `emit-event.sh`'s usage reads `--type TYPE  an event type in lib.py's EVENT_TYPES` and
  `--op OP  an op in lib.py's EVENT_OPS`.
- `scripts/queue/README.md` is removed and `scripts/queue` leaves `package_docs.exempt_dirs`. `queue/README.md`
  keeps its first two paragraphs' point (runtime only, outside product git, `QUEUE_ROOT`) and its Rules table, and
  replaces the layout block, Auth, Worktrees, Observability and See also with one line: the files and their writers
  are SPEC §23.7.
- No code or test changes; no test expectation changes.

## Scope

- **In:** the module docstrings of `ccp/prompt.py`, `ccp/verify.py`, `ccp/submit.py` and `ccp/lifecycle.py`, and the
  function docstrings a dropped fact moves to; `docs/delivery/plane.json` (`architect.checks` `E24`,
  `package_docs.exempt_dirs`); `scripts/observability/lib.py` (its docstring and the comment above
  `REVIEW_EVENT_TYPES`); `scripts/observability/emit-event.sh` (the `--type` and `--op` usage lines);
  `scripts/observability/CLAUDE.md`; `queue/README.md`; `scripts/queue/README.md` (removed).
- No SPEC change: the build cuts copies and writes no SPEC or docs/cli text.
- **Out:** the other 15 ccp modules over 30 lines (E24's check keeps the count from rising); any code; §23.3 and
  §23.7; `emit-event.sh`'s examples (0303); `templates/docs-delivery/README.md`.

## dod_checks

- id: `doc-01`
  story: As a plane developer, the four module docstrings are short and state no exit code.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -c 'import ast,re; [print(m, len(d.splitlines()), len(re.findall(r"\bexit \d", d)), "§" in d.split("\n\n")[0]) for m in ("prompt", "verify", "submit", "lifecycle") for d in [ast.get_docstring(ast.parse(open(f"ccp/{m}.py").read())) or ""]]'`.
  expect: four lines, one per module in that order, each with a line count of at most 15, `0` exit statements, and `True` (its first paragraph names a §).
  dry run (`0f44fb3`): printed `prompt 47 6 True`, `verify 40 1 True`, `submit 12 2 True`, `lifecycle 53 4 True`.
- id: `cfg-01`
  story: As the architect, E24's check holds the lower count.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `cmd=$(python3 -c 'import json; print([c["cmd"] for c in json.load(open("docs/delivery/plane.json"))["architect"]["checks"] if c["id"] == "E24"][0])'); echo "$cmd" | grep -c -- '-le 15'; bash -c "$cmd"; echo "exit=$?"`.
  expect: prints `1`, then `exit=0`.
  dry run (`0f44fb3`, with this triage's plane.json): printed `0`, then `exit=0` (the figure is 18; the count is 18).
- id: `doc-02`
  story: As a reader of the observability scripts, the timer formulas and the event registry each have one home.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git grep -n -e 'Timer formula' -e '§17.8 adds' -e 'phase|waiting_on|lease' -e 'set|clear|transition' -- scripts; tr '\n' ' ' < scripts/observability/CLAUDE.md | grep -c "docstring repeats"`.
    2. Run `scripts/observability/emit-event.sh --help | grep -c -e 'EVENT_TYPES' -e 'EVENT_OPS'`.
  expect: step 1 prints only `0`; step 2 prints `2`.
  dry run (`0f44fb3`): step 1 printed 4 lines (`lib.py` 2, `emit-event.sh` 2), then `1`; step 2 printed `0`.
- id: `doc-03`
  story: As a reader of the runtime queue, its files are described once, by the SPEC.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `git ls-files scripts/queue | wc -l; git grep -c -e 'running.json' -e 'last-session.json' -e 'blocker.md' -e 'watchdog' -e '§28.29' -- queue/README.md; git grep -c '§23.7' -- queue/README.md; python3 -c 'import json; print("scripts/queue" in json.load(open("docs/delivery/plane.json"))["package_docs"]["exempt_dirs"])'`.
  expect: prints `0`, then `queue/README.md:1` (the §23.7 line; the first grep prints nothing), then `False`.
  dry run (`0f44fb3`): printed `1`, `queue/README.md:5`, nothing for `§23.7` (exit 1), `True`.
- id: `code-01`
  story: As a plane developer, cutting the docstrings changed no code.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `for f in ccp/prompt.py ccp/verify.py ccp/submit.py ccp/lifecycle.py scripts/observability/lib.py; do diff <(git show origin/main:$f | python3 -c 'import ast,sys; t=ast.parse(sys.stdin.read()); [setattr(n, "body", n.body[1:]) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str)]; print(ast.dump(t))') <(python3 -c 'import ast,sys; t=ast.parse(open(sys.argv[1]).read()); [setattr(n, "body", n.body[1:]) for n in ast.walk(t) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) and isinstance(getattr(n.body[0], "value", None), ast.Constant) and isinstance(n.body[0].value.value, str)]; print(ast.dump(t))' $f) >/dev/null && echo "$f same" || echo "$f differs"; done`.
  expect: five lines, each `<file> same`: with every docstring set aside, each module's syntax tree is the one on origin/main.
  dry run (`0f44fb3`): printed the five `same` lines (the checkout is origin/main).

## Implementation notes

## Verification notes
