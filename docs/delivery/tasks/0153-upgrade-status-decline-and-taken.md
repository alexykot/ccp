---
task_id: 0153-upgrade-status-decline-and-taken
title: A product records an adopt step as declined or taken with one command, upgrade status names the steps it saw taken, and each change line reads as written
status: pending
kind: feature
depends_on: []
spec_refs: ["S29"]
review_point: R10
paths: ["ccp/upgrade.py", "ccp/cli.py", "docs/spec/05-operations.md", "docs/cli/05-operations.md", "contracts/plane_config.schema.json", "tests/test_upgrade.py"]
adopt: "none"
created: 2026-11-18
updated: 2026-11-18
---

# Task: 0153-upgrade-status-decline-and-taken
## Intent

A lead reviewing a plane release settles each `adopt` step with one command, declined or taken, each
with its reason, so `ccp upgrade status` converges to no open steps without anyone hand-editing
plane.json. The lead also sees which steps the command found already taken, and every change line
reads as a sentence, whatever the step's wording.

## Context (not checked)

- What exists: plane.json `upgrade.declined` (from ADR-0041 D2) and `upgrade.taken` (task 0120), each an
  object of plane task ids to reasons. `status` in `ccp/upgrade.py` skips a declined task and lists a
  recorded one under `taken` (`"if tid in recorded:"`). Nothing writes either object: `ccp upgrade
  --help` at `85d388b` offers only `notes` and `status`, and the only plane.json writer is `ccp init`
  (`git grep -n "CONFIG_REL" -- ccp/` at `85d388b`: the reads in `ccp/config.py`, and no write outside
  `ccp/init.py`).
- The premise "taken stayed [] after a step was taken" is true but by design. `taken` lists only steps
  recorded in `upgrade.taken`, which the command cannot see. A step whose key the product's file holds
  is skipped (`if _has(sources[parsed[0]], parsed[1]): continue`) and listed nowhere, so the step just
  disappears. This task keeps `taken` as it is and adds `detected` beside it for those steps.
- The `change` text: `_change` renders `set <key> in <file> to <rest of the step>`. Dry run at
  `85d388b` (`CCP_DEV=1 ./bin/ccp --root . upgrade status`, in a plane checkout): 0034 reads "set
  `docs.starter_rules` in docs/delivery/plane.json to {} to adopt the starter house rules", 0068 reads
  "... to with tool and to naming the lead's message channel", and 0126 reads "... to listing the paths ...".
- §31.1: the §29.3 sentences below describe this task's own commands and output field.

## Scope

- **In:**
  - `ccp/upgrade.py` and `ccp/cli.py`: two subcommands, added by this task:
    `ccp upgrade decline <task> --reason R` and `ccp upgrade take <task> --reason R`. Each writes the
    product's plane.json (`docs/delivery/plane.json` under `--root`): `decline` sets
    `upgrade.declined.<task id>` to R, and `take` sets `upgrade.taken.<task id>` to R. Each removes the
    same id from the other object, so a task is never in both. The file is rewritten as
    `json.dumps(data, indent=2)` plus a newline, keys in their existing order. Each prints
    `{"ok": true, "task", "recorded": "declined"|"taken", "reason"}`. Neither commits anything.
  - Refused with exit 2 and nothing written: a blank or missing `--reason`; a task that is not a merged
    plane task (`merged_task`); a task whose step asks nothing (`tasklog.asks_nothing`); a plane.json
    that does not load (`config.load`), or that would not load after the change. `<task>` may be the
    full id or its number, resolved against the plane's merged tasks.
  - `status`: a new list `detected`, beside `steps` and `taken`, holding each step the command checked
    and found taken (its key present), as `{task, title, adopt}`. `taken` is unchanged: only what
    `upgrade.taken` records.
  - `status`'s `change` for a step it can check: with no value, `set `<key>` in <file>`; with a value
    of one word (no whitespace), `set `<key>` in <file> to <value>`; with more than one word,
    `set `<key>` in <file>: <the rest as written>`.
  - §31.1: `docs/spec/05-operations.md` §29.3, after the `upgrade.taken` clause, one sentence:
    `ccp upgrade decline <task> --reason R` and `ccp upgrade take <task> --reason R` write those
    entries (each removing the task from the other), and `ccp upgrade status` lists under `detected`
    each step it found taken in the product's files.
  - `docs/cli/05-operations.md`: the two commands in the Releases block.
  - `contracts/plane_config.schema.json`: the `upgrade.declined` and `upgrade.taken` descriptions name
    the command that writes each.
  - `tests/test_upgrade.py`: the tests for this task. `test_a_settings_step_with_no_settings_file_is_not_taken`
    asserts `"1h"` in `change`, which still holds.
- **Out:**
  - Committing plane.json, or writing the binding or `.claude/settings.json`.
  - Telling the product when a step it declined has changed since (a new task supersedes it).
  - `ccp notify upgrade`'s notice body, which reads `steps` and is unchanged.

## dod_checks

- id: `cmd-01`
  story: As a lead, I decline a step with one command and status stops listing it.
  setup: the scratch plane and product of `tests/test_upgrade.py`, with one merged plane task whose step is `plane.json alpha.on` and the product's plane.json without `alpha`.
  steps:
    1. Run `ccp upgrade decline <that task> --reason "not for us"`.
    2. Run `ccp upgrade status`.
  expect: step 1 exits 0 and plane.json `upgrade.declined.<task id>` is `"not for us"`; plane.json still loads; in step 2 the task is in none of `steps`, `taken` and `detected`.
  dry run: n/a.
- id: `cmd-02`
  story: As a lead, I record a step as taken, and switching a record moves it.
  setup: the plane and product of cmd-01, after its step 1.
  steps:
    1. Run `ccp upgrade take <that task> --reason "done by hand"`.
    2. Run `ccp upgrade status`.
  expect: step 1 exits 0; plane.json `upgrade.taken.<task id>` is `"done by hand"` and `upgrade.declined` no longer holds the id; step 2 lists the task under `taken` with that reason.
  dry run: n/a.
- id: `cmd-03`
  story: As a lead, a bad record is refused before anything is written.
  setup: the plane and product of cmd-01, plus a merged plane task whose adopt step is `none`.
  steps:
    1. Run `ccp upgrade decline <task> --reason " "`, then `ccp upgrade decline 9999-no-such --reason x`, then `ccp upgrade take <the none task> --reason x`.
  expect: each exits 2 and plane.json is byte for byte as before.
  dry run: n/a.
- id: `cmd-04`
  story: As a lead, I see which steps the command found taken.
  setup: the plane of cmd-01; the product's plane.json holds `alpha.on: true`.
  steps:
    1. Run `ccp upgrade status`.
  expect: the task is not in `steps`; it is in `detected` with its `task`, `title` and `adopt`; `taken` is `[]`.
  dry run: n/a.
- id: `cmd-05`
  story: As a lead, each change line reads as a sentence.
  setup: a scratch plane with three merged tasks whose steps are `plane.json a.b`, `plane.json c.d 1h` and `plane.json e.f with tool and to naming the channel`, and a product that holds none of the keys.
  steps:
    1. Run `ccp upgrade status`.
  expect: the three `change` values are exactly ``set `a.b` in docs/delivery/plane.json``, ``set `c.d` in docs/delivery/plane.json to 1h`` and ``set `e.f` in docs/delivery/plane.json: with tool and to naming the channel``.
  dry run (`85d388b`): the plane's own 0068 step reads "... to with tool and to naming the lead's message channel" (the defect).
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): `ccp upgrade decline|take <task> --reason R` (`ccp/upgrade.py` `_record`)
  resolve the task against the plane's merged tasks by id or number (`refs.ids(...).same_task`), refuse a
  blank or missing reason, an unmerged task and a step that asks nothing, load plane.json, set the entry,
  remove the id from the other object, check the result with `config._parse` (the parse `config.load`
  runs) and write it through `queue.write_json` (`json.dumps(data, indent=2)` plus a newline, atomic
  replace). An `upgrade.<other>` object left empty stays as `{}`. `--reason` is optional in argparse so a
  missing one is refused by the command, exit 2. `status` gains `detected`; `_change` renders the three
  forms. The premises re-run at `7fc5197` held (help offered only notes and status; no plane.json
  writer outside `ccp/init.py`; the dry run showed the 0034, 0068 and 0126 lines as the task quotes).

## Verification notes
