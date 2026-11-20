---
task_id: 0201-plane-json-records-keep-layout
title: Commands that record into plane.json change only their own key and keep the file's layout
status: pending
kind: feature
depends_on: []
spec_refs: ["S8", "S29"]
review_point: R14
paths: ["ccp/jsonedit.py", "ccp/upgrade.py", "ccp/CLAUDE.md", "tests/test_jsonedit.py", "tests/test_upgrade.py"]
adopt: "none"
created: 2026-11-20
updated: 2026-11-20
---

# Task: 0201-plane-json-records-keep-layout

## Intent

`ccp upgrade take` and `ccp upgrade decline` record one entry in a product's plane.json. To do it,
they load the whole file and write it back with `json.dumps(indent=2)`. Every compact list and
inline object in the file is spread over many lines, so a one-entry change shows up as a diff of the
whole file, and the lead has to check it by hand. After this task, they change only the entry they
record: every other byte of the file stays as it was, and the diff is the entry alone.

## Context (not checked)

Measured at `58cf1d0`.

- `ccp/upgrade.py` `_record` reads `data = json.loads(path.read_text())`, sets
  `upgrade[key][tid] = reason`, pops the id from `upgrade[other]` and calls
  `queue.write_json(path, data)` (`git grep -n 'queue.write_json(path, data)' ccp/upgrade.py` at
  `58cf1d0`: one line). `queue.write_json` is `lib.write_json`, which writes
  `json.dumps(obj, indent=2) + "\n"`.
- Probe at `58cf1d0`. A temp product's plane.json held `"suite": {"lanes": {"gate": ["true"]}},` on
  one line. `ccp --root <temp> upgrade take 0185 --reason "kept off"` spread that line over seven and
  appended the `upgrade` block (`diff <before> <after>` at `58cf1d0`: 2 lines replaced by 13).
- No other command rewrites an existing plane.json: `ccp init` keeps one it finds unless `--force`
  (`keep_plane_json` in `ccp/init.py`), and writes a new one with its own layout
  (`git grep -n 'CONFIG_REL' ccp/*.py` at `58cf1d0`: plane.json is written only in `init.py` and
  `upgrade.py`).
- `tests/test_upgrade.py` passes 38 tests at the base (`python3 -B -m unittest -q tests.test_upgrade`
  at `58cf1d0`).
- No SPEC change. The one SPEC sentence on these commands (§29.3, `docs/spec/05-operations.md`: "write
  those entries (each removing the task from the other)") stays true
  (`grep -n 'write those entries' docs/spec/05-operations.md` at `58cf1d0`: one line).

## Scope

- **In:** `ccp/jsonedit.py` (new), `ccp/upgrade.py`, `ccp/CLAUDE.md`, `tests/test_jsonedit.py`
  (new), `tests/test_upgrade.py`.
- **`ccp/jsonedit.py` (new)**, a text-level JSON editor with no dependency:
  - `set_member(text, path, key, value) -> str`: in the object found at `path` (a list of keys from
    the top), set `key` to `value`. An existing member's value span is replaced by
    `json.dumps(value, ensure_ascii=False)`. A new member goes after the object's last member, on a
    line of its own, indented like that member, or, in an empty or inline object, written inline as
    `, "key": value`. A missing object on `path` is made the same way, as `{"key": value}` inline.
  - `delete_member(text, path, key) -> str`: removes the member and its separating comma; a key that
    is not there returns the text unchanged.
  - The scanner reads strings with their escapes, numbers, literals, nested objects and arrays, and
    whitespace, and reports each member's key span and value span. It never reformats anything
    outside the spans it changes.
  - After each edit, `json.loads` of the result must equal the same edit made on the loaded data.
    When it does not, the function raises `ValueError`, and the caller writes nothing.
- **`_record`** builds the new text with `set_member(text, ["upgrade", key], tid, reason)` and, when
  the id is under `other`, `delete_member(text, ["upgrade", other], tid)`. It validates the result
  with `config._parse` as today, and writes it atomically (a temp file, then replace). A
  `ValueError` from the editor refuses the command (exit 2, "plane.json could not be edited in
  place: <why>"), nothing written.
- `ccp/CLAUDE.md` lists the new module in one line.
- **Tests:**
  - `tests/test_jsonedit.py` (new): set a new member in an indented object, in an inline object and
    in an empty one; replace an existing member; delete a member in first, middle and last place;
    make a missing parent; strings holding `{`, `}`, `"`, `\\` and a non-ASCII character; the
    equality guard raising on a hand-broken edit. Every case also asserts that each byte outside the
    changed member is unchanged.
  - `tests/test_upgrade.py`: `take` then `decline` of the same task on a plane.json with compact
    lists and inline objects leaves every line but the `upgrade` entries byte-identical, the file
    loads, and the id moved from `taken` to `declined`.
- **Out:** `ccp init`'s own writes, and the binding (YAML) and settings files.

## dod_checks

- id: `je-01`
  story: As a lead, `ccp upgrade take` changes only the entry it records.
  setup: a checkout of the PR head; a temp git repo with `docs/delivery/plane.json` holding the
    lines `{`, `  "project_id": "demo",`, `  "language": "none",`,
    `  "suite": {"lanes": {"gate": ["true"]}},`, `  "architect": false`, `}`, and a copy of it as
    `<temp>/before.json`; `CCP_BINDINGS_DIR` set to an empty temp dir.
  steps:
    1. Run `ccp --root <temp> upgrade take 0185 --reason "kept off"`.
    2. Run `diff <temp>/before.json <temp>/docs/delivery/plane.json`.
  expect: step 1 exits 0. Step 2 shows only lines added for the `upgrade` entry, plus at most the
    comma added to the line before it; the `suite` line is unchanged.
  dry run (`58cf1d0`): step 2 shows lines 4-5 replaced by 13 lines, the `suite` line spread over 7.

- id: `je-02`
  story: As a plane developer, the editor keeps every byte it does not change.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_jsonedit tests.test_upgrade 2>&1 | tail -40`.
  expect: exit 0, with the Scope's editor cases and the take-then-decline test listed `ok`.
  dry run (`58cf1d0`): `tests/test_jsonedit.py` does not exist; `tests.test_upgrade` runs 38 tests,
    OK.

- id: `je-03`
  story: As a plane developer, the layout test bites.
  setup: a copy of the PR head (`git worktree add --detach <tmp> HEAD`) in which `_record` writes with
    `queue.write_json(path, json.loads(text))` again.
  steps:
    1. In the copy, run `python3 -B -m unittest -q tests.test_upgrade`.
  expect: at least one failure, naming the take-then-decline test.
  dry run: n/a — the test is new.

- id: `suite-01`
  story: As the plane, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `scripts/gate.sh`, then `git branch --list 'state/*'`.
  expect: the gate exits 0 and the branch list is empty.
  dry run: n/a.

## Implementation notes

## Verification notes
