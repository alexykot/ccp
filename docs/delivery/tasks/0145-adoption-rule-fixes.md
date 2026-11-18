---
task_id: 0145-adoption-rule-fixes
title: The permission block the plane prints no longer trips its own docs check, and ccp upgrade status marks each step required or optional
status: pending
kind: feature
depends_on: []
spec_refs: ["S4", "S5", "S29"]
review_point: R9
sign_off: brief
paths: ["ccp/cli.py", "ccp/upgrade.py", "ccp/tasklog.py", "contracts/task_file.schema.json", "docs/spec/01-model.md", "docs/spec/05-operations.md", "plugin/skills/writing-tasks/SKILL.md", "tests/test_init_permissions.py", "tests/test_upgrade.py", "tests/test_tasklog_adopt.py"]
adopt: "none"
created: 2026-11-17
updated: 2026-11-17
---

# Task: 0145-adoption-rule-fixes
## Intent

A product that applies the permission block `ccp init --permissions` prints gets no standing docs-check
warning for doing what the SPEC told it to, and a product reading `ccp upgrade status` can tell the steps
it must take from the ones it may take, and which plane commit the reading came from.

## Context (not checked)

- Two adoption findings that each need a § rule change, split from tasks 0138 and 0139 so those can
  run unsigned. They share no code; they are one task only because they share the sign-off.
- **Permissions.** §4.5 has `ccp init --permissions` print "the plane's `team.sh` and
  `spec-maintainer-ask.sh` by absolute path" (`SEAT_SCRIPTS` and `"def permissions"` in `ccp/init.py`),
  and the operator applies the block to `.claude/settings.json`. §4.4 has `ccp docs check` warn on "any
  plane checkout path in a tracked product file" (`"def plane_path_warnings"` in `ccp/cli.py`), so the
  applied block draws a standing warning. §4.3 already says "The allowlist names `ccp`, not a path",
  which §4.5 contradicts. Probe (a sandbox, `ccp init --permissions` at `921507e`): four allow entries
  name the plane checkout's `scripts/team.sh` and `scripts/spec-maintainer-ask.sh`.
- Ruling: exempt those entries rather than drop them. The runner runs `team.sh gate open` and `gate
  status` itself (the header of `scripts/team.sh`), so an allowlist without them prompts on every gate;
  the other route, a `ccp` subcommand wrapping each seat script, is a larger change for no gain here.
- **Upgrade status.** It lists one entry per `adopt` step not taken (`"def status"` in `ccp/upgrade.py`)
  and is a function of the plane checkout's done tasks and the product's three files only: adding an
  unrelated plane.json block cannot add a step (`_has` reads only the step's own key). A reading that
  went from one step to eleven most likely spans the release of task 0120, which gave eleven done tasks
  a parseable step (`git log --oneline -1 2821df0`: "Task 0120: adopt steps on opt-in tasks, and
  upgrade.taken"). The output names no plane commit, so two readings cannot be compared; and nothing
  says which steps a product must take. Recording a step as taken or declined exists already
  (`upgrade.taken`, `upgrade.declined`, §29.3).
- Every step on the log today is an opt-in knob, so this task marks none `required:`.

## Rule changes (signed at tasking)

1. `docs/spec/01-model.md` §4.3. CURRENT (at `921507e`): "its permission allowlist in `.claude/settings.json`, because plugins cannot ship permissions. The allowlist names `ccp`, not a path." PROPOSED:
   > its permission allowlist in `.claude/settings.json`, because plugins cannot ship permissions. The allowlist names `ccp`, and the plane's seat scripts by the absolute paths `ccp init --permissions` prints (§4.5), and no other plane path.
2. `docs/spec/01-model.md` §4.4. CURRENT (at `921507e`): "`ccp docs check` warns, and does not fail, on any plane checkout path in a tracked product file outside the task log and reviews: a product decides its own docs." PROPOSED:
   > `ccp docs check` warns, and does not fail, on any plane checkout path in a tracked product file outside the task log and reviews: a product decides its own docs. A `permissions` entry of `.claude/settings.json` naming one of the seat scripts `ccp init --permissions` prints (§4.5) is not warned about.
3. `docs/spec/01-model.md` §5, the `adopt` row. CURRENT (at `921507e`): "| `adopt` | no (default `none`) | what a product must do to use what the task delivers: `none`, or one concrete step naming the file and key (ADR-0041 D1). A task that ships an off-by-default knob carries its step, never `none`; `ccp tasks check` warns on a `none` value that names a plane.json, binding or settings key |" PROPOSED:
   > | `adopt` | no (default `none`) | what a product must do to use what the task delivers: `none`, or one concrete step naming the file and key (ADR-0041 D1). A task that ships an off-by-default knob carries its step, never `none`; `ccp tasks check` warns on a `none` value that names a plane.json, binding or settings key. A step a product must take for the plane to keep working with it starts with `required:`; any other step is optional |
4. `docs/spec/05-operations.md` §29.3. CURRENT (at `921507e`): "`ccp upgrade status`, run in a product, lists each `adopt` step of a merged plane task that the product's plane.json, binding and `.claude/settings.json` do not show taken, with the task, the product's own proposal for it when there is one, and the change to make;" PROPOSED:
   > `ccp upgrade status`, run in a product, lists each `adopt` step of a merged plane task that the product's plane.json, binding and `.claude/settings.json` do not show taken, with the task, whether the step is `required` or `optional`, the product's own proposal for it when there is one, and the change to make, and names the plane checkout's commit it read;

## Scope

- **In:**
  - `docs/spec/01-model.md` and `docs/spec/05-operations.md`: the four PROPOSED texts, word for word.
  - `ccp/cli.py` `plane_path_warnings`: a match in `.claude/settings.json` is read as JSON; entries of
    `permissions.allow` and `permissions.deny` that name a plane path only through `scripts/team.sh` or
    `scripts/spec-maintainer-ask.sh` are set aside, and the file is warned about only when a plane path
    remains elsewhere in it. A file that is not JSON is warned about as today.
  - `ccp/tasklog.py`: `adopt_step` keeps the value; a helper says whether it is required (first word
    `required:`) and gives the step without the prefix, which `asks_nothing`, `hidden_step` and
    `upgrade.parse_step` read. `contracts/task_file.schema.json`: the `adopt` description says so.
  - `ccp/upgrade.py` `status`: each step gains `required` (true or false); the result gains `plane`, the
    plane checkout's HEAD commit.
  - `plugin/skills/writing-tasks/SKILL.md`: the `adopt` row says a must-take step starts `required:`.
- **Out:**
  - Marking any existing task's step required.
  - A `ccp` subcommand for the seat scripts.

## dod_checks

- id: `perm-01`
  story: As a lead who applied the printed permissions, docs check stays quiet.
  setup: a fenced scratch product whose plane path matches the docs check's pattern, adopted, with the block `ccp init --permissions` printed applied to `.claude/settings.json` and committed.
  steps:
    1. Run `ccp docs check`.
  expect: no warning names `.claude/settings.json`.
  dry run: n/a — the fence's plane path at `921507e` does not match the pattern, so the test builds one that does.
- id: `perm-02`
  story: As a product, another plane path in settings is still caught.
  setup: the product of perm-01, plus a `hooks` entry in `.claude/settings.json` naming the plane's `plugin/hooks/runner-idle.sh` by path.
  steps:
    1. Run `ccp docs check`.
  expect: one warning naming `.claude/settings.json` and §4.4.
  dry run: n/a.
- id: `up-01`
  story: As a product, I see which steps I must take and which plane I read.
  setup: a scratch plane task log with two done tasks, adopt `required: plane.json alpha.on` and `plane.json beta.on`, and a scratch product holding neither key.
  steps:
    1. Run `ccp upgrade status`.
  expect: two steps, the first `required: true` with change `set \`alpha.on\` in docs/delivery/plane.json`, the second `required: false`; `plane` is the scratch plane's HEAD.
  dry run: n/a.
- id: `up-02`
  story: As a product, an unrelated block does not change my reading.
  setup: the product of up-01.
  steps:
    1. Run `ccp upgrade status`, add a plane.json block no step names, run it again.
  expect: the two outputs are equal.
  dry run: n/a.
- id: `check-01`
  story: As the operator, the SPEC says what I signed.
  setup: the PR diff.
  steps:
    1. Compare the §4.3, §4.4, §5 and §29.3 edits with the PROPOSED texts above.
  expect: they match word for word, and no other § rule changes.
  dry run: n/a.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-18 (implementer): premises re-checked at `f3db9fb`: `git log --oneline -1 2821df0` names task 0120;
  `SEAT_SCRIPTS` holds the two seat scripts, each printed bare and behind `QUEUE_ROOT=` (four entries); no
  `adopt:` value on the log starts with `required:`.
  - **Docs check.** `ccp/cli.py` names the pattern once (`PLANE_PATH_RE`, with `PLANE_DIR_RE` for the
    checkout directory). A match in `.claude/settings.json` is re-read as JSON: an entry of
    `permissions.allow` or `permissions.deny` that names a plane path only through a seat script (the
    checkout directory followed by an entry of `init.SEAT_SCRIPTS`, not followed by a word character, `.` or
    `-`) is set aside, and the rest of the file is searched again. A file that does not load as JSON is
    warned about as before. The seat-script list stays in `ccp/init.py`, its one home.
  - **Required steps.** `tasklog.adopt_required(step)` returns (required, the step without the prefix); the
    prefix is matched case-insensitively, as `none` is. `asks_nothing` and `upgrade.parse_step` read the
    step through it, so `hidden_step` does too (through `asks_nothing`): its key scan needs no change, since
    `required` is no dotted key. `adopt_step` and the `adopt` field of `ccp upgrade status` and `notes` keep
    the whole value; a by-hand step's `change` is the step without the prefix. `ccp upgrade status` gains
    `plane`, the plane checkout's HEAD (`null` when that is not a git checkout). Entries under `taken` carry
    no `required` (the task names the steps only).
  - **Fix round 1 (review MINORs and one NIT).** Two tests pin what the review's mutants showed loose: a
    seat-script entry under `permissions.deny` draws no warning, and an entry naming `scripts/team.sh.bak`
    or `scripts/team.sh-x` under the plane checkout is still warned about (the boundary after the script
    name). A step of only `required:` is now listed by hand with the step as written for its `change`,
    not an empty one.

## Verification notes
