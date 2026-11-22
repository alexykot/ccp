---
name: writing-tasks
description: How to write durable control-plane delivery tasks (docs/delivery/tasks/NNNN-*.md) in the plane's canonical task format: intent, scope, dod_checks that can fail, refs, dependencies, declared paths. Use it when creating or amending a task in a control-plane project.
---
# How to write durable delivery tasks

For the task-log owner (the design seat: the team lead, who is also the spec maintainer). This is the
plane's canonical task format (plane SPEC §5) and its generic writing rules. A product keeps its own
additions in `docs/delivery/WRITING-tasks.md` (template: `templates/docs-delivery/WRITING-tasks.md`);
where they are stricter, they win. Template: `templates/docs-delivery/TEMPLATE-task.md`.

## The file

`docs/delivery/tasks/NNNN-<kebab-slug>.md`. `NNNN` is zero-padded (`ids.task.width`, default 4). The run
order follows `depends_on`, the number breaking ties (SPEC §10.3), so a new task can go before pending
ones without renumbering them. Never delete a task file, never renumber, never reuse a
number: a task no longer wanted is `status: dropped`, with a note naming what replaced it.

### Frontmatter

One `key: value` per line; lists inline (`["a", "b"]`), on one line.

| Key | What it is |
| --- | --- |
| `task_id`, `title` | the file name without `.md`; one imperative line |
| `status` | `pending`, `done` or `dropped`. Nothing else: claimed, implementing, in review and verifying are queue states, never written here. `ccp tasks close` writes `done` |
| `depends_on` | task ids that must be `done` first; one may have a higher number. A cycle is refused |
| `created`, `updated` | `YYYY-MM-DD` |
| `spec_refs`, `adr_refs` | the SPEC sections it must satisfy; the decisions it builds (`"0031 D2"`). `spec_refs` is a required key by default (`task_log.required`), and by default a task must cite at least one SPEC section there (`task_log.refs_any`), even when it also cites `rule_refs` or `review_refs`. Only a kind with its own `refs_any`, read with the architect seat on (a refactor, below), leaves it out |
| `kind` | `feature` (default) or `refactor` (with the architect seat; see below) |
| `rule_refs`, `review_refs` | a refactor's house rules (`"E3"`) or review findings (`"<review_id>#F03"`) |
| `review_point` | the review point whose scope it belongs to (`R<n>`) |
| `paths` | the files or globs it touches. Parallel scheduling reads these first; without them it guesses from Scope **In:** |
| `parallel` | `true`: changes no file and runs beside anything; `false`: always alone |
| `clashes_with` | ids of tasks it clashes with: both change the same logic in different ways, so they run in either order, never together. Symmetric (a clash recorded on either task holds for both). Read only under plane.json `parallel.schedule: clashes`; an id that names no task, or the task itself, is refused |
| `shaping` | `waived — <reason>`, only for an ADR that truly needs no shape |
| `gate` | `cold`: the verifier accepts no test cache for this task |
| `sign_off` | text the operator must sign (a SPEC CURRENT → PROPOSED, a contract): `brief` when the task carries it, signed before the claim; `build` when the build finds it, signed after verify at the head that merges; `[brief, build]` for both. The lead records each with `ccp tasks sign-off`; claim and close refuse without it (SPEC §3.5). By default a task declares none: SPEC or contract text that follows from its accepted ADR and brief, describing only the accepted feature, needs no sign-off. Text the build adds beyond that intent is caught by the reviewer and the verifier (`spec_beyond_intent`), which makes a `build` sign-off due without a declaration |
| `covers` | an after-the-fact task's merged commits (shas, 7 to 40 hex digits) that came in outside the plane; `ccp tasks orphans` stops listing them (SPEC §10.7) |
| `adopt` | what a product must do to use what the task delivers, one line: `none` (it applies by itself), or one concrete step naming the file and key (`plane.json verify.accept_cache`, `.claude/settings.json subagentPromptCacheTtl 1h`). A step that starts with the word `none` is read as `none`, so a step that must be taken never starts with that word. A step a product must take for the plane to keep working with it starts with `required:` (`required: plane.json x.y`); any other step is optional, and `ccp upgrade status` marks each. A task that ships an off-by-default knob carries its step, never `none`. Give it on every task that adds a knob, a setting or a file a product must create; a missing key reads as `none`. `ccp upgrade status` checks a `plane.json`, `binding` or `.claude/settings.json` step by its key and lists any other as "check by hand" (SPEC §5.2, §29.3) |

Never write runtime state here (`waiting_on`, leases, session ids, ports): `ccp tasks check` refuses it.
`ccp tasks check` holds `adopt` to SPEC §5.2.

### Sections, in this order

| Section | Purpose | Verified? |
| --- | --- | --- |
| `## Intent` | One paragraph: what is true for the product's user when this is done. An outcome, not a diff | context |
| `## Context (not checked)` | Background, constraints, policy, why: anything that shapes the build but is not a pass/fail walkthrough | **no** |
| `## Scope` | `- **In:** …` and `- **Out:** …`. In **In:**, mark a path the task creates `(new)` and one it deletes `(removed)` (see below) | context |
| `## dod_checks` | Walkthroughs someone else can run: setup → steps → expect | **yes, only these**, plus the standing DoD |
| `## Implementation notes` | Append-only; the runner, from the implementer's report | — |
| `## Verification notes` | Append-only; the verifier, one `- ` line per check; `ccp tasks close` writes the merge record | — |

### Path markings in Scope **In:**

`ccp tasks check` warns, for a task not yet `done` or `dropped`, about each backticked path in the
**In:** item that does not exist in the checkout. A token is read as a path when it holds a `/` and
is not a glob; a trailing `:<line>` is ignored. A path does not warn when:

- the word `new` (a path the task creates) or `removed` (one it deletes) appears, as a whole word in
  any case, within the 25 characters after the path's closing backtick: `` `src/export.py` (new) ``,
  `` `docs/old.md` (removed) ``. A `removed` path passes whether or not it still exists;
- a task in `depends_on` names it (in its `paths`, else in its own **In:** item): the file it makes.

The warning does not fail the check. Mark the path right after it, so the word does not drift out
of reach when the sentence is edited.

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
- At most six checks. More, or a scope with "and then also", is two tasks. Findings bundled in one
  area are not "and then also": they are one task, a check per finding (see *Writing the brief*).
- Never re-list the standing DoD (`docs/delivery/standing-dod.md`): it always applies.
- Each check names the seat that can run it. An operator prerequisite (a new key, role or grant) is
  done before the claim, so every seat gates the branch as it will run.

### A check only the operator's machine can run

A check the workers cannot take (a real device, a signed build, a live account) carries
`runs_on: operator-machine` on the line after `setup:` (plane SPEC §5.5). It holds only the steps that
machine runs: a check that mixes them with steps the workers can take is split in two, one marked and
one not. `ccp tasks dry-run` does not run a marked check, so its dry-run line says why:

```markdown
- id: `dev-02`
  story: As an operator, an export reaches the live account.
  setup: The PR head's build installed on the operator's machine, signed in to the live account.
  runs_on: operator-machine
  steps:
    1. Run `tool exports send --pending`, then open the account's inbox.
  expect: The two queued exports are in the inbox; exit code 0.
  dry run: n/a — runs on the operator's machine
```

`ccp tasks check` refuses another value, or the line anywhere but right after `setup:`.
`ccp tasks checks <id> --json` lists a task's checks with their `runs_on`.

### Commands and searches in checks

- **Every command a check gives is run once by its writer** before the task is committed, against
  the current tool. With `task_log.dry_run` on, each such check records `dry run (<commit>): <what
  it printed or its count>`, or `dry run: n/a — <why it cannot run yet>`. `ccp tasks dry-run <id>
  --write` runs only the steps that are one backticked command and nothing else (``Run `…`.``) and
  writes their checks' records (plane SPEC §21.1); the writer runs and records any other command
  step (such as "On the head, run `…`") by hand. The writer reads that output against the `expect`.
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
  planted fault) names the copy: `ccp mutate --mutant` (or `--mutant-file`) when a test judges the
  fault and the product declares `mutate.command` or its language pack has a per-test runner,
  otherwise a `ccp wt create --kind mut` worktree at the head, removed with `ccp wt remove`; never
  the branch's own worktree and never a hand `git worktree add`.
- **A speed check states an absolute target**, never "as fast as before".
- **A check that runs tests runs them through `ccp suite run`**
  (`bin/ccp suite run --lane <part lane> -- <test command> <tests>`), so the run is recorded, and pins a
  named test by grepping that run's log; never a bare test runner's output. `ccp tasks check` warns on
  a step that runs the language's test command bare.
- **A check of a `ccp` command runs the head's `bin/ccp`** where the head carries one (the plane's own
  repo), never `ccp` on PATH, which is the released plane. Signed SPEC text is checked with
  `bin/ccp verify spec-text <task>` (`ccp verify spec-text <task>` in a product's checkout), never by a
  grep for a sentence.
- **A doc presence check pins the token the rule turns on** (the flag, the key, the § cite), never a
  whole sentence or a table row; signed SPEC text is proved by `ccp verify spec-text`.
- **An expect counts only what the task changes**, never a figure that moves when another task lands
  (another task's status, frontmatter or count).

## Writing the brief

- **Rule your own choices.** Every alternative a brief names ("A or B") is decided before it is
  committed. Where the task leaves something open, the implementer writes the narrowest rule and
  flags it, which costs a round trip.
- **New behaviour carries its SPEC text.** A task that changes the SPEC quotes each sentence it
  changes or removes (CURRENT, at a named commit) and gives the new text (PROPOSED), naming every
  sentence the change retires. An implementer writes no SPEC text of its own.
- **Rule text is signed when the task is written.** A task that adds or changes a § rule carries the
  exact CURRENT → PROPOSED text of each passage in its Scope and declares `sign_off: brief`, so the
  operator signs the words before the claim. A task whose SPEC text only describes its own feature
  (§31.1) says `§31.1` on a Scope line instead. `ccp tasks check` warns on a task whose `paths` name
  the SPEC (`spec_paths`) with neither (plane SPEC §3.5). Every PROPOSED, §31.1 text included, goes in a
  `> ` blockquote under a `PROPOSED:` line: `ccp verify spec-text` reads no other shape (plane SPEC
  §15.2), and `ccp tasks check` warns on one given inline.
- **"No SPEC change" is measured:** cite a SPEC search, at a named commit, for each concept the task
  adds, renames or changes.
- **Locate code by symbol with a short quote** (`"def export_rows"`), never by a bare `path:line`:
  lines move before the claim. A line number appears only beside a named commit.
- **A claim about the code cites its proof** (a probe or dry run), re-measured at the brief's commit,
  never copied from a report. A task that renames something lists in Scope every file a search for
  the old name finds.
- **A measured premise names its measurement.** Any count, size, list of sites or "X already
  happens" / "X never happens" claim in a brief names, in Context and on the same line, the command
  that measured it, in backticks, and the commit it ran at: `` `git grep -c foo -- src/` at `abc1234`:
  2 call sites ``. The implementer re-runs it at its base before building and, if the figure changed
  materially, stops with a scope question. `ccp tasks check` warns, without failing, about a task not
  yet `done` or `dropped` whose Context states a number with no backticked command (a code span of
  two words or more) on its line. A stated limit (the number right after `at most`, `at least`,
  `up to`, `no more than`, `no less than`, `within` or `under`) and a protocol code (right after
  `status`, `status code`, `HTTP`, `exit`, `exits` or `exit code`) are not measurements and are skipped.
- **Copy into Context what workers cannot reach**: data only the live system, a session or the
  operator holds.
- **A ruling or sign-off is in git before anyone acts on it**: in the task's notes or a commit,
  verbatim where it sets SPEC text. A ruling written into Context goes in as a quoted block (`> `),
  which the number warning skips (plane SPEC §10.5). A PR comment is not a record.
- **The docs a task touches follow the package-doc convention** (plane SPEC §21.3), which
  `ccp docs check` enforces; a brief does not restate it.
- **Follow-ups are bundled by area.** Every task pays a fixed cost (claim, worker start-up, review,
  verify, merge, reconcile), so follow-ups, review leftovers and architect findings (code, tests and
  docs alike) go into one task per area, aiming at a few hundred changed lines (`ccp health` shows
  the share of tasks under `health.small_task_lines`). The task declares the union of their paths in
  `paths` and carries one `dod_check` per finding; every finding is still fixed. An area with more
  findings than `max_checks` (default 6) fills a second task for that area. A finding goes
  into a pending brief instead only when it is inside that brief's Scope. A finding that changes
  stored data or a contract keeps its own task (see the `review-triage` skill).

## Changing a task

- Only the task-log owner creates a task or changes its intent, `dod_checks`, id or `depends_on`.
- **Before the claim**, edit in place (git keeps the trail). Implementation notes start at the claim.
  For a task that declares `sign_off: brief` (or `[brief, build]`), an edit to its file after the
  brief sign-off makes the sign-off stale: the claim refuses until the operator signs the new text
  (SPEC §3.5). A task that declares no `brief` sign-off has none to go stale.
- **After the claim**, a change is a new task that supersedes it; the old one is `dropped`, with a
  note naming the new one. Whether a task is claimed is in the queue (`ccp tasks list`, the runner's
  leases), not in its file. A claimed task's file is not edited on the integration branch.
- **A prerequisite** is never written as prose ("gated on 0197"): it goes in `depends_on`, whatever
  its number. `ccp tasks check` warns on such a sentence naming a later task.
- **Before a task is preferred**, reread its checks against these rules, refresh any check anchored
  at a commit older than what has merged since, and re-measure the counts its Context states.
- **Before you ask the operator to sign a brief**, re-read it against the commits
  `ccp tasks check --stale` names for it; `ccp tasks sign-off` prints them again as it records.
- **A new task that changes logic a pending brief rules on** names it in `clashes_with` and says in
  Context how the two rulings fit; when the pending brief is signed, the new task builds on its ruling
  or waits for it in `depends_on`.
- Then run `ccp tasks index` and commit the index with the task file (when the product keeps one).

## Kinds (plane SPEC §20.3, with the architect seat)

`task_log.kinds` says, per kind, which refs it cites. By default a **refactor** changes no rule: it
cites `rule_refs` or `review_refs`, never `spec_refs` or `adr_refs`. Its standing DoD: behaviour is
unchanged, the suite passes, no test expectation changes except where the task names it, the SPEC
does not change. A change to behaviour or stored data is a feature. A refactor joins a runner's
scope when a task in the scope depends on it (`refactor_in_scope: "deps"`), so a task that needs one
says so in `depends_on`. A refactor brief does not re-list the gate as a check: its checks prove
the change by its own commands, since the verifier runs the gate anyway. `ccp tasks check` refuses a
refactor not yet done whose check step runs the gate or full lane (the lanes `suite.roles` names, as
`suite.lanes` declares them) in a one-line backticked command: as a whole command, also behind `env`,
`bash`/`sh`, `time` or `timeout N` or before a redirection, or as `ccp suite run --lane <lane>`.

## Wide plans, not deep chains

A review point written as one long chain, each task waiting on the one before, runs one task at a
time. Write it wide:

- Sequence two tasks only for a dependency or a clash, never because they touch the same files.
- For a feature, write one thin first task that fixes the interfaces, then tasks that build on it in
  parallel.
- Make tasks smaller where each piece still works on its own. There is no hard size cap.
- Read the cited ADRs' `requires` (§6.2): a task building a decision depends on a task that builds
  each prerequisite not yet built. `ccp tasks check` reports the `depends_on` that is missing (§21.1).

`ccp tasks check` notes each review point's longest `depends_on` chain and its width at each depth,
and warns when the chain is long and the plan narrow.

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
pending, with a warning), a dependency that doesn't exist, a cycle of `depends_on` (named), a task
citing nothing, zero or more than `max_checks` checks, duplicate check ids, soft language inside `## dod_checks` ("should",
"may", "gracefully", "robust"), a `done` task with no verification note, runtime state in frontmatter,
a `runs_on:` line with a value other than `operator-machine` or not right after `setup:`,
a task file that is gone (restore it; convert an earlier generation's file with
`ccp tasks migrate`), a number held by another file without `renamed_from`, a kind's ref rules broken, and (with `shape_adrs`) a new task citing an unshaped ADR
without a waiver. A `review_point` not in the register (or, without one, not matching
`ids.review_point.pattern`). A task not yet `done` or `dropped` that still holds a template
placeholder (`NNNN-kebab-slug`, `YYYY-MM-DD`, `As a <role>`, `<preconditions`,
`<concrete, observable result>`, `One line, imperative`), named with its line; a placeholder quoted
in a code span or a fenced block is not read. A task citing nothing, where `spec_refs` is one of the
lists it may cite, is told to list the SPEC sections in `spec_refs` and cite them in its text.
`plane.json` validation refuses a `suite.lanes` command that holds `<your test command>`.

## When the operator says "not verifiable"

Tighten **expect**, split checks, move policy to **Context**, move blockers to **`depends_on`**.
