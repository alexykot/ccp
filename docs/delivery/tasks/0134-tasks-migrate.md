---
task_id: 0134-tasks-migrate
title: ccp tasks migrate converts an earlier plane generation's task files in place, and the task-log checks point at it
status: done
kind: feature
depends_on: []
spec_refs: ["S5", "S21"]
review_point: R9
paths: ["ccp/tasklog.py", "ccp/taskmigrate.py", "ccp/cli.py", "ccp/init.py", "docs/spec/01-model.md", "docs/spec/03-quality.md", "docs/cli/02-delivery.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_tasks_migrate.py", "tests/test_tasklog.py", "tests/test_init.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0134-tasks-migrate
## Intent

A product adopted under an earlier plane generation keeps its task history as done records: one
command converts its old task files to the current format in place, `ccp tasks check` and
`ccp docs check` are clean after it, and every message on the way (a file with no frontmatter, a
file that is gone, a slug renamed in git, `ccp tasks list`) names the fix instead of a misleading one.

## Context (not checked)

- Reported while re-adopting a product under an earlier plane generation: its task files have no
  frontmatter, so `ccp docs check` fails right after `ccp init` and standing DoD item 1 fails every
  task. `ccp adr migrate` and `ccp review-points migrate` exist; tasks has none (`ccp tasks --help`
  at `921507e`).
- Archiving instead (moving the files out of `tasks/`) cannot pass: `def missing_task_files` in
  `ccp/tasklog.py` reads `git log --no-renames --diff-filter=D`, so a moved file is a gone file, and
  §5.1 says a task file is never deleted. This task therefore converts in place and has no
  `--archive`: an archive area would change §5.1 and §21.1, a rule change this task does not make.
- Measured at `921507e` in a scratch product (made with `ccp sandbox create`, a file with no
  frontmatter added as `tasks/0007-export-ledger.md`):
  - `ccp tasks list` printed one row `?  ?` and exited 0;
  - `ccp tasks check` printed 18 failures (`ccp tasks check | head -1`), nine of them for that one
    file (missing keys one by one, `task_id None`, `status None`);
  - after `git mv` to `0007-export-the-ledger.md`, the gone-file message led with "restore
    0007-export-ledger with `status: dropped` and give 0007-export-the-ledger the next free number";
    `renamed_from` appears only in its last sentence. The proposal's "the message does not mention
    `renamed_from`" is therefore not quite true on main; what is true is that it leads with the
    wrong fix for a rename.
- The earlier format is inferred from the reports, not from a copy of such a product: a `# Task
  NNNN: <title>` heading, a `## Meta` table (`| Field | Value |` rows `ID`, `Status`, `Depends on`,
  `Created`), a `## Refs` table (`| Kind | Ref |` rows such as `SPEC`, `ADR`), then free sections; the
  title lives in the old `INDEX.yaml` (`- id:` / `title:` entries). The test fixture below is that
  shape; the implementer matches table keys case-insensitively and flags in its report any variant
  it chose to accept beyond it.
- Rulings taken here:
  - Statuses: `done`, `complete`, `completed` → `done`; `dropped`, `cancelled`, `canceled`,
    `superseded`, `abandoned` → `dropped`; anything else is an open task.
  - An open task is not converted (its old checks are not current `dod_checks`), unless
    `--drop-open` is given: then it becomes `dropped` with the note "dropped at migration: rewrite it
    as a new task if it is still wanted".
  - A converted file keeps its old text, verbatim, under `## Context (not checked)`, so nothing is
    lost; `## Intent` says "Converted from an earlier plane generation's task record; the original
    text is under Context."; `## Scope` is `- **In:** see Context.` and `- **Out:** nothing recorded.`;
    `## dod_checks` holds one check `legacy-01` (story: the record converted; expect: the original
    text is under Context), which passes the check grammar and holds no soft word; `## Verification
    notes` gets one line `- <today> — converted by ccp tasks migrate from an earlier plane
    generation's <old status> record; not re-verified under this plane.`
  - Frontmatter: `task_id` the file stem; `title` from the `INDEX.yaml` committed at HEAD, else the
    heading without its `Task NNNN:` prefix; `status` as above; `depends_on` the `Depends on` row's
    ids (`-` or empty: `[]`); `spec_refs` each `§N`, `§N.M` or `SN` in the `SPEC` row as the product's
    spec ref for section N (`refs.Ids.spec_ref`), deduplicated in order; `created` the `Created`
    row, `updated` the same; `adopt: "none"`. ADR and other Refs rows stay in the kept text only.
  - Cannot convert (listed with its reason, the file untouched, a failing exit): a name that is not
    `NNNN-kebab-slug.md`, no Meta table, no `Status` row, an open task without `--drop-open`, no
    SPEC section in the Refs table, a `Created` that is not `YYYY-MM-DD`, a `Depends on` id with no
    file. A file that already has frontmatter is skipped silently.
- §31.1: the SPEC text below only describes this task's own command and messages; §5.1 and §21.1's
  rules (never deleted, gone files fail) are unchanged.

## Scope

- **In:**
  - `ccp tasks migrate [--dry-run] [--drop-open]` (new), in `ccp/taskmigrate.py` (new), wired in
    `ccp/cli.py`: converts each task file with no frontmatter by the rulings above, then, when the
    product keeps an index, runs `ccp tasks index`; prints one line per file (converted, skipped,
    or cannot convert: reason). `--dry-run` writes nothing and prints the same lines. Exit 0 when
    every file converted, 1 when any could not.
  - `ccp/tasklog.py` `check`: a task file with no frontmatter gives one failure, "no frontmatter: an
    earlier plane generation's task file? convert it with `ccp tasks migrate`", instead of one per
    missing key.
  - `ccp/tasklog.py` `missing_task_files`: a gone file's message names the restore command
    (`git checkout <sha>^ -- <path>`), then: an earlier generation's file (its last committed text has
    no frontmatter) is converted with `ccp tasks migrate`; a done task stays `done`; only a task no
    longer wanted is `status: dropped`. When git shows the gone file renamed (`git log -M
    --diff-filter=R`) to a file present now with the same NNNN, the message is only "renamed to
    <new file> in <sha>: add `renamed_from: <old id>` to its frontmatter".
  - `ccp/cli.py` `cmd_tasks_list`: a file with no frontmatter or no `task_id` is not a row; for each,
    stderr names its path and the reason and points at `ccp tasks check` and `ccp tasks migrate`;
    `--json` leaves it out too; exit stays 0.
  - `ccp/init.py`: when the task directory holds files with no frontmatter, the result's `warnings`
    names their count and `ccp tasks migrate`.
  - §31.1: `docs/spec/01-model.md` §5.3, a new paragraph at its end:
    > A task file from an earlier plane generation (no frontmatter: a Meta and a Refs table) is converted in place by `ccp tasks migrate [--dry-run] [--drop-open]`: its frontmatter from those tables and the title from the committed `INDEX.yaml`, its old text kept under `Context (not checked)`, a done or dropped record marked converted and not re-verified. An open task is converted only with `--drop-open`, as `dropped`; a file it cannot convert is named with the reason and left as it is (exit 1).
  - §31.1: `docs/spec/03-quality.md` §21.1, appending to the gone-file bullet ("…that does not say `renamed_from: <old id>`;"):
    > the message names the restore, `ccp tasks migrate` for an earlier generation's file and, for a file git shows renamed, the `renamed_from` line to add; a task file with no frontmatter is one failure naming `ccp tasks migrate`;
  - `docs/cli/02-delivery.md`: the `ccp tasks migrate` row. `plugin/skills/writing-tasks/SKILL.md`,
    "What `ccp tasks check` refuses": "a task file that is gone (restore it as `dropped`)" becomes
    "a task file that is gone (restore it; convert an earlier generation's file with `ccp tasks
    migrate`)".
  - `tests/test_tasks_migrate.py` (new) with the fixture below; `tests/test_tasklog.py` and
    `tests/test_init.py` for the messages.
- **Out:**
  - Archiving task files out of the task log (a §5.1 rule change).
  - Converting an earlier generation's README, WRITING or standing-dod docs.

## dod_checks

- id: `mig-01`
  story: As a lead re-adopting a product, its done history converts and the checks pass.
  setup: a fenced product adopted with `ccp init`, holding the fixture: `INDEX.yaml` committed with entries `0001-ledger-store` (title "Store the ledger") and `0002-export-ledger` (title "Export the ledger as CSV"); `0001-ledger-store.md` with Meta `Status: done`, `Created: 2025-03-01`, Refs `SPEC: §4.2, §6`; `0002-export-ledger.md` with Meta `Status: completed`, `Depends on: 0001-ledger-store`, `Created: 2025-03-02`, Refs `SPEC: §4`, `ADR: 0012`, and a `## Goal` section.
  steps:
    1. Run `ccp tasks migrate`, then `ccp tasks check` and `ccp docs check`.
    2. Read `0002-export-ledger.md`.
  expect: step 1's three commands exit 0; the file has `title: Export the ledger as CSV`, `status: done`, `depends_on: ["0001-ledger-store"]`, `spec_refs: ["S4"]`, `created: 2025-03-02`, its `## Goal` text verbatim under `## Context (not checked)`, and one verification note naming the conversion.
  dry run: n/a — `ccp tasks migrate` is new.
- id: `mig-02`
  story: As a lead, what cannot be converted is named and left alone.
  setup: the fixture of mig-01 plus `0003-retry-export.md` (Meta `Status: in progress`) and `0004-notes.md` (no Meta table).
  steps:
    1. Run `ccp tasks migrate --dry-run`, then `ccp tasks migrate`.
    2. Run `ccp tasks migrate --drop-open`.
  expect: `--dry-run` changes no file (`git status --porcelain` empty) and prints the same lines as the run after it; that run exits 1 naming 0003 (open task) and 0004 (no Meta table), converts 0001 and 0002, and leaves 0003 and 0004 byte for byte; step 2 converts 0003 as `status: dropped` with the drop note and still exits 1 naming 0004.
  dry run: n/a — `ccp tasks migrate` is new.
- id: `msg-01`
  story: As a lead, a file with no frontmatter points me at migrate, in check and in list.
  setup: a fenced product with one task file and `0002-export-ledger.md` of the fixture.
  steps:
    1. Run `ccp tasks check`, then `ccp tasks list`, then `ccp tasks list --json`.
  expect: check has exactly one failure for that file, naming `ccp tasks migrate`; `list` prints no `?` row, exits 0, and its stderr names the file's path, `ccp tasks check` and `ccp tasks migrate`; the JSON holds only the other task.
  dry run (`921507e`): check printed nine failures for such a file; list printed a `?  ?` row.
- id: `msg-02`
  story: As a lead, a gone file's message names the right fix.
  setup: a fenced product with two committed task files: `0001-a` (current format, `status: done`) and `0002-b` (no frontmatter); then one commit deleting `0001-a.md` and moving `0002-b.md` out of `tasks/`.
  steps:
    1. Run `ccp tasks check`.
  expect: exit 1; the 0001 message names the restore command and does not say `status: dropped` is its fix; the 0002 message names the restore command and `ccp tasks migrate`.
  dry run (`921507e`): a deleted current-format file's message said "restore it with `status: dropped` and a note naming what replaced it"; every gone file takes that branch of `def missing_task_files`.
- id: `msg-03`
  story: As a lead who renamed a slug, the check tells me to add `renamed_from`.
  setup: a fenced product with committed `0001-old-slug.md` (current format), then `git mv` to `0001-new-slug.md` committed, with no `renamed_from`.
  steps:
    1. Run `ccp tasks check`; then add `renamed_from: 0001-old-slug` to the new file and run it again.
  expect: the first exits 1 with one message for 0001 naming `0001-new-slug.md` and the `renamed_from: 0001-old-slug` line, and not "never reused"; the second exits 0.
  dry run (`921507e`): the first message led with "A number is never reused: restore 0001-old-slug with `status: dropped`".
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-17 — implementer: `ccp tasks migrate` in `ccp/taskmigrate.py`, wired in `ccp/cli.py`; it
  regenerates the index only when it converted a file and is not a dry run. A file already in the
  current format gets no line of its own; a closing line counts converted, already current and cannot
  convert. The old text is kept byte for byte in a tilde fence (one tilde longer than any tilde fence
  in it) under `## Context (not checked)`. Accepted beyond the fixture: a bare task number in
  `Depends on` names the one file holding it; the product's own spec prefix as well as `S`; Meta and
  Refs headings in any case; a title from the slug when neither the committed index nor a `# ` heading
  gives one. `ccp/tasklog.py`: `has_frontmatter`; `check` gives one failure for a file with none;
  `missing_task_files` names `git checkout <sha>^ -- <path>` (or `git checkout HEAD -- <path>` for a
  file deleted since HEAD; no command outside git), then `ccp tasks migrate` when the last committed text
  has no frontmatter, else that a done task stays `done`; a rename `git log -M --diff-filter=R` shows to
  the file holding the number gets only the `renamed_from` line. `ccp tasks list` skips such files with
  a stderr line; `ccp init` counts them in `warnings`.
- 2026-11-17 — implementer, fix round 1: the kept old text sits first in the converted file, and the
  section reader takes the first heading of a name, so an old `## dod_checks` or `## Verification notes`
  shadowed the converted file's own and `ccp tasks check` failed a file migrate called converted. Now
  `migrate` renders every file first, runs `tasklog.check` with the rendered texts standing in for the
  files (`load` and `check` take an optional `texts`), and a rendered file with failures of its own is
  "cannot convert: converted, it would fail `ccp tasks check`: <its failures>", not written; it repeats
  until none fails, so a file depending on one left unconverted is left too. `--dry-run` runs the same
  check, so its lines stay the run's. The section reader is unchanged. `has_frontmatter` searches from
  the same offset as `frontmatter`. mig-02's "the same lines" is read as the per-file lines: the closing
  count line says `(dry run, nothing written)` and the real run adds the index line.

## Verification notes

- 2026-11-17 — verifier, PR #148 head `ea8bcc5` (squash `f0ff53e`): APPROVE. Passed: mig-01, mig-02, msg-01, msg-02, msg-03, suite-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0, `ccp adr check` exit 0. Record: verification/0134-tasks-migrate.json.
