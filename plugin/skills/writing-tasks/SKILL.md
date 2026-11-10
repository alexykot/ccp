---
name: writing-tasks
description: How to write durable control-plane delivery tasks (docs/delivery/tasks/NNNN-*.md) in the plane's canonical task format: intent, scope, dod_checks that can fail, refs, dependencies, declared paths. Use it when creating or amending a task in a control-plane project.
---
# How to write durable delivery tasks

For the task-log owner (the design seat, or a steerer). This is the plane's canonical task format
(plane SPEC §5) and its generic writing rules. A product keeps its own additions in
`docs/delivery/WRITING-tasks.md` (template: `templates/docs-delivery/WRITING-tasks.md`); where they
are stricter, they win. Template: `templates/docs-delivery/TEMPLATE-task.md`.

## The file

`docs/delivery/tasks/NNNN-<kebab-slug>.md`. `NNNN` is zero-padded (`ids.task.width`, default 4) and
**is** the execution order (filesystem sort). Never delete a task file, never renumber, never reuse a
number: a task no longer wanted is `status: dropped`, with a note naming what replaced it.

### Frontmatter

One `key: value` per line; lists inline (`["a", "b"]`), on one line.

| Key | What it is |
| --- | --- |
| `task_id`, `title` | the file name without `.md`; one imperative line |
| `status` | `pending`, `done` or `dropped`. Nothing else: claimed, implementing, in review and verifying are queue states, never written here. `ccp tasks close` writes `done` |
| `depends_on` | task ids that must be `done` first; each sorts earlier |
| `created`, `updated` | `YYYY-MM-DD` |
| `spec_refs`, `adr_refs` | the SPEC sections it must satisfy; the decisions it builds (`"0031 D2"`) |
| `kind` | `feature` (default) or `refactor` (with the architect seat; see below) |
| `rule_refs`, `review_refs` | a refactor's house rules (`"E3"`) or review findings (`"<review_id>#F03"`) |
| `review_point` | the review point whose scope it belongs to (`R<n>`) |
| `paths` | the files or globs it touches. Parallel scheduling reads these first; without them it guesses from Scope **In:** |
| `parallel` | `true`: changes no file and runs beside anything; `false`: always alone |
| `shaping` | `waived — <reason>`, only for an ADR that truly needs no shape |
| `gate` | `cold`: the verifier accepts no test cache for this task |
| `covers` | an after-the-fact task's merged commits (shas, 7 to 40 hex digits) that came in outside the plane; `ccp tasks orphans` stops listing them (SPEC §10.7) |

Never write runtime state here (`waiting_on`, leases, session ids, ports): `ccp tasks check` refuses it.

### Sections, in this order

| Section | Purpose | Verified? |
| --- | --- | --- |
| `## Intent` | One paragraph: what is true for the product's user when this is done. An outcome, not a diff | context |
| `## Context (not checked)` | Background, constraints, policy, why: anything that shapes the build but is not a pass/fail walkthrough | **no** |
| `## Scope` | `- **In:** …` and `- **Out:** …` | context |
| `## dod_checks` | Walkthroughs someone else can run: setup → steps → expect | **yes, only these**, plus the standing DoD |
| `## Implementation notes` | Append-only; the runner, from the implementer's report | — |
| `## Verification notes` | Append-only; the verifier, one `- ` line per check; `ccp tasks close` writes the merge record | — |

## A good `dod_check`

```markdown
- id: `cmd-01`
  story: As an operator, I list pending exports so I can see what is queued.
  setup: A fresh store with two exports queued and one sent.
  steps:
    1. Run `tool exports list --pending`.
  expect: Exactly the two queued exports are listed, each with its id and queue time; exit code 0.
  dry run (`a1b2c3d`): printed 2 rows (the fixture's two queued exports), exit 0.
```

- A stable `id`: a lowercase kind and a number (`cmd-01`, `data-02`, `code-01`, `ui-01`).
- **story**: what it demonstrates, in one line. **setup**: exact preconditions. **steps**: numbered,
  concrete enough for someone who did not write the task. **expect**: one observable result, pass or
  fail, no judgement call.
- At most six checks. More, or a scope with "and then also", is two tasks.
- Never re-list the standing DoD (`docs/delivery/standing-dod.md`): it always applies.
- Each check names the seat that can run it. A step only the operator's machine can run is marked
  as such in its `setup`. An operator prerequisite (a new key, role or grant) is done before the
  claim, so every seat gates the branch as it will run.

### Commands and searches in checks

- **Every command a check gives is run once by its writer** before the task is committed, against
  the current tool. With `task_log.dry_run` on, the check records `dry run (<commit>): <what it
  printed or its count>`, or `dry run: n/a — <why it cannot run yet>`. The writer reads that output
  against the `expect`.
- **A search's pattern matches only what its expect counts**, and spells a value the way the code
  spells it. Its expected count or list is the brief's own list, item for item, stated at the head
  or at a named commit, never "at the merge base".
- **An absence check first shows its pattern finding a known positive**, names its pathspec
  explicitly, excludes the code whose job is the removal, and covers only the Scope's paths (or the
  Scope names every path it reaches). Use `git grep -nwP`; macOS `git grep -E` ignores `\b`.
- **A check that a branch leaves paths unchanged reads the branch's own diff**
  (`git diff origin/<integration>...HEAD -- <paths>` prints nothing), never a diff from a fixed commit.
- **A behaviour-preserving change** (move, rename, split) is checked by the tests that already hold
  the behaviour, named, plus a mutation showing they bite. A check that changes a tracked file (a
  planted fault) does it in a separate copy, never in the branch's own worktree.
- **A speed check states an absolute target**, never "as fast as before".

## Writing the brief

- **Rule your own choices.** Every alternative a brief names ("A or B") is decided before it is
  committed. Where the task leaves something open, the implementer writes the narrowest rule and
  flags it, which costs a round trip.
- **New behaviour carries its SPEC text.** A task that changes the SPEC quotes each sentence it
  changes or removes (CURRENT, at a named commit) and gives the new text (PROPOSED), naming every
  sentence the change retires. An implementer writes no SPEC text of its own.
- **"No SPEC change" is measured:** cite a SPEC search, at a named commit, for each concept the task
  adds, renames or changes.
- **Locate code by symbol with a short quote** (`"def export_rows"`), never by a bare `path:line`:
  lines move before the claim. A line number appears only beside a named commit.
- **A claim about the code cites its proof** (a probe or dry run), re-measured at the brief's commit,
  never copied from a report. A task that renames something lists in Scope every file a search for
  the old name finds.
- **Copy into Context what workers cannot reach**: data only the live system, a session or the
  operator holds.
- **A ruling or sign-off is in git before anyone acts on it**: in the task's notes or a commit,
  verbatim where it sets SPEC text. A PR comment is not a record.
- **The docs a task touches follow the package-doc convention** (plane SPEC §21.3), which
  `ccp docs check` enforces; a brief does not restate it.
- **A follow-up gets its own task.** Another task's leftover goes into a small task of its own, or
  into a pending brief only when it is inside that brief's Scope.

## Changing a task

- Only the task-log owner creates a task or changes its intent, `dod_checks`, id or `depends_on`.
- **Before the claim**, edit in place (git keeps the trail). Implementation notes start at the claim.
- **After the claim**, a change is a new task that supersedes it; the old one is `dropped`, with a
  note naming the new one. Whether a task is claimed is in the queue (`ccp tasks list`, the runner's
  leases), not in its file. A claimed task's file is not edited on the integration branch.
- **A prerequisite that sorts later** is never written as prose ("gated on 0197"): supersede the
  waiting task with one numbered after the prerequisite that lists it in `depends_on`.
  `ccp tasks check` warns on such a sentence.
- **Before a task is preferred**, reread its checks against these rules, refresh any check anchored
  at a commit older than what has merged since, and re-measure the counts its Context states.
- Then run `ccp tasks index` and commit the index with the task file (when the product keeps one).

## Kinds (plane SPEC §20.3, with the architect seat)

`task_log.kinds` says, per kind, which refs it cites. By default a **refactor** changes no rule: it
cites `rule_refs` or `review_refs`, never `spec_refs` or `adr_refs`. Its standing DoD: behaviour is
unchanged, the suite passes, no test expectation changes except where the task names it, the SPEC
does not change. A change to behaviour or stored data is a feature. A refactor joins a runner's
scope when a task in the scope depends on it (`refactor_in_scope: "deps"`), so a task that needs one
says so in `depends_on`. A refactor brief does not re-list the gate as a check.

## Review points and shaping

- **Review points** (§22.1, §22): set `review_point: R<n>` when scoping (`ccp review-points tag`).
  With the register (`docs/delivery/review-points.yaml`) the point must be in it, named with the
  operator.
- **Shaping** (§19.6): with `architect.shape_adrs` on, a new task citing an ADR needs that ADR's
  shaping record (`docs/delivery/reviews/sh-*.md`, the line `ADR: ADR-NNNN`) from
  `ccp architect run --mode shape --adr <id>`. The task-log owner never writes a shape itself.

## What `ccp tasks check` refuses

A filename that isn't `NNNN-kebab-slug.md`, a reused number, missing frontmatter keys or sections, a
status other than `pending`, `done` or `dropped` (a legacy `in_progress` or `blocked` reads as
pending, with a warning), a dependency that doesn't exist or runs later, a task citing nothing, zero
or more than `max_checks` checks, duplicate check ids, soft language inside `## dod_checks` ("should",
"may", "gracefully", "robust"), a `done` task with no verification note, runtime state in frontmatter,
a task file that is gone (restore it as `dropped`), a number held by another file without
`renamed_from`, a kind's ref rules broken, and (with `shape_adrs`) a new task citing an unshaped ADR
without a waiver. A `review_point` not in the register (or, without one, not matching
`task_log.review_point_pattern`). A task not yet `done` or `dropped` that still holds a template
placeholder (`NNNN-kebab-slug`, `YYYY-MM-DD`, `As a <role>`, `<preconditions`,
`<concrete, observable result>`, `One line, imperative`), named with its line; a placeholder quoted
in a code span or a fenced block is not read. A task citing nothing, where `spec_refs` is one of the
lists it may cite, is told to list the SPEC sections in `spec_refs` and cite them in its text.
`plane.json` validation refuses a `suite.lanes` command that holds `<your test command>`.

## When the operator says "not verifiable"

Tighten **expect**, split checks, move policy to **Context**, move blockers to **`depends_on`**.
