---
task_id: 0101-spec-text-catches-up-with-the-code
title: SPEC passages that say less than the code does, or the wrong thing, are corrected
status: pending
kind: docs
depends_on: [0104-command-edge-fixes]
spec_refs: ["S2", "S3", "S4", "S5", "S10", "S12", "S13", "S14", "S15", "S16", "S27", "S28"]
review_point: R6
paths: ["docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "README.md", "docs/design/toolkit.md", "docs/design/team.md"]
created: 2026-11-16
updated: 2026-11-16
---

# Task: 0101-spec-text-catches-up-with-the-code

## Intent

Earlier tasks made SPEC passages false or incomplete. This task corrects each one so that it says
what the code does. All of it is §31.1 text: it describes accepted features or corrects passages a
merged change made false. It adds no rule and changes no code.

## Context (not checked)

- Eleven accepted plane proposals (operator, 2026-11-16: all approved), the follow-ups of earlier tasks.
  Each one names a passage below.
- The tool and test follow-ups from the same proposals are tasks 0102–0105. This task is text only.

## Scope

- **In**, one correction per passage:
  - §4.5: `ccp` is allowed by name. Only `team.sh` and `spec-maintainer-ask.sh` are allowed by path,
    as §4.3 and the template already do.
  - §10.3: `ccp tasks next` reads task statuses at the integration tip, and skips tasks the queue
    holds as done or dropped.
  - §2.6: the seat knobs list `rotate_at_context_tokens` beside `rotate_after_tasks`, and state that
    single-runner mode does not take the claim's holder into account for rotation.
  - §4.5 or `ccp init`'s section: an origin on GitHub Enterprise is warned about as "not GitHub". This
    is deliberate, and the text says so.
  - §3.6: `notify.lead`'s `tool` and `to` are "non-empty, single-line strings".
  - §5.5: the marking window stops at the next backtick. §13.4: say which report-field values count as
    the pasted template, as the code now judges them.
  - §13.2 and the last sentence of §15.2's lead bullet: name the minor-only skip of the re-review, as
    §15.2 states it elsewhere.
  - §14.2: `{head}` is the task head under test (the product checkout's HEAD), not the HEAD of the
    tip's worktree where provers now run.
  - §12.1: a SIGTERM before the worktree exists exits 143 with no result JSON, unless task 0104 makes
    it emit one: write whichever is true at merge. A descendant that leaves the process group can
    hold a timeout open. `--shallow` needs git protocol v2.
  - §16.5: "or can be made" is stated as it is checked (the dry run does not check that
    `origin/<integration>` resolves, unless task 0103 adds that check: write whichever is true at
    merge).
  - §27.1 and §28.3: the round lists name merge and ruling rounds.
  - README: the deny rules are prefix matches. They catch the spellings listed, not every spelling
    (task 0102 adds more forms; the README says what holds after it).
  - Since task 0099, a rendered prompt carries a per-run end token, and the Agent call `ccp prompt`
    prints passes a pointer to the prompt file rather than its text verbatim. §13.2 and
    docs/design/toolkit.md still say a prompt renders the same text every run apart from paths, and
    docs/design/team.md says the prompt is passed verbatim: say what holds now.
  - §4.5 names only the `rules_max_lines` refusal of `ccp init --adopt`. Since task 0102 it also
    refuses (exit 1, nothing written) when a re-parse of the text it would write shows an adopted
    rule not reading `pass` or another rule's check changing, and the rules parser skips fenced code
    blocks: say both.
- **Out:**
  - Any change to code, or to what a rule requires.

## dod_checks

- id: `check-01`
  story: As a reader of the SPEC, each listed passage says what the code does.
  setup: a checkout of the PR head.
  steps:
    1. For each passage in Scope, read the new text and the code it describes.
  expect: each one matches the code at the head, and none adds a requirement the code does not
    enforce.
  dry run: n/a.
- id: `check-02`
  story: As the operator, nothing here needed my approval.
  setup: the PR diff.
  steps:
    1. Read every changed SPEC line.
  expect: each one describes existing behaviour or corrects a false passage (§31.1). The verdict's
    `spec_beyond_intent` is empty.
  dry run: n/a.
- id: `check-03`
  story: As a plane developer, nothing else changed.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite, `ccp tasks check`, `ccp docs check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- 2026-11-16 (implementer): one correction per Scope passage, each read against the code at 982787c
  (0102, 0103 and 0104 merged; 0105 not yet).
  - §2.6: both rotation knobs (`lifecycle.rotation_knobs`); with one runner `rotation_due` reads the
    single-runner fields whatever `--holder` says.
  - §3.6: `notify.lead`'s `tool` and `to` are non-empty, single-line strings (`config` `_notify_lead`
    and the schema's pattern); a blank value or a line break is refused.
  - §4.5: `ccp` is allowed by name, the two seat scripts by path, each of the three also behind
    `QUEUE_ROOT=` (`init.permissions`). Only `github.com` and its subdomains count as GitHub
    (`init.is_github`), so a GitHub Enterprise host on its own domain gets the warning, stated as
    deliberate. `--adopt` also refuses (exit 1, nothing written) when the re-parse shows an adopted rule
    not reading `pass` or another rule's check changed, and the rules parser skips fenced blocks
    (`rules.rule_blocks`, `docrules.unfenced`).
  - §5.5: the `new`/`removed` window stops at the next backtick (`parallel.missing_paths`).
  - §10.3: `next` reads statuses at `origin/<integration>` when the checkout lags it, and skips a task
    the queue holds `done` or `dropped` (`selection.current`).
  - §12.1: since 0104, a SIGTERM before the base worktree exists exits 143 with a result (`name`
    null). A descendant that left the process group and holds the output keeps the run open past the
    timeout (the read loop waits on the pipe). `--shallow` fetches a sha by id: protocol v2.
  - §13.2: the verify render differs between runs only in filled-in fields and the end token; a merge
    or ruling round may be skipped by a review prover or the minor-only skip too.
  - §13.4: the template test as `report._template` judges it now (a `|`, or `/`, `,`, `or` followed
    by another declared value). Task 0105 changes this rule and edits the same sentence.
  - §14.2: `{head}` is the HEAD of the checkout the run started in (`suite.task_diff`), not the tip's.
  - §15.2: the lead bullet's last sentence names the minor-only skip `verify.review_errors` accepts.
  - §16.5: "can be made" is the path being absent or an empty directory (`team.py` `readiness`); a
    missing `origin/<integration_branch>` refuses the dry run first (0103's
    `refuse_without_integration_ref`).
  - §27.1, §28.3: merge and ruling rounds (health's `merge_rounds`, `ruling_rounds`; the drill view).
  - README: the deny list and that its rules are prefix matches, with spellings they miss.
  - docs/design/toolkit.md: as §13.2. docs/design/team.md: the runner spawn is still made verbatim (true:
    its prompt is short text); a worker's call passes a pointer to the prompt file.

## Verification notes
