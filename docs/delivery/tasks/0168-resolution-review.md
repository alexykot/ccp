---
task_id: 0168-resolution-review
title: A conflicted integration merge gets a resolution review mode, which names the dod_checks the resolution can affect, and the verifier reruns those
status: pending
kind: feature
depends_on: ["0162-git-merge-helper"]
spec_refs: ["S13", "S15", "S11"]
adr_refs: ["0042 D4"]
review_point: R11
paths: ["ccp/prompt.py", "ccp/cli.py", "ccp/runs.py", "ccp/report.py", "ccp/verify.py", "ccp/health.py", "templates/prompts/review.md", "templates/prompts/verify.md", "plugin/agents/delivery-runner.md", "plugin/agents/delivery-verifier.md", "docs/spec/02-delivery.md", "docs/cli/02-delivery.md", "tests/test_resolution_review.py"]
adopt: "none"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0168-resolution-review
## Intent

When the integration tip moves after a task's review and merging it in conflicts, the implementer
resolves the conflict in a merge round as today. The task then no longer pays a full review and a full
verify. Its new head gets a resolution review: the reviewer reads only how the committed merge
differs from git's own merge, says whether the resolution stays within the conflict hunks, and names
the dod_checks it can affect. The verifier reruns those checks and the gate at the new head, and every
other check rests on the earlier approve. A resolution that reaches into the task's own logic falls
back to a full round, on the reviewer's word. The round phases are listed once, in `runs.PHASES`.

## Context (not checked)

- ADR-0042 D4 (accepted 2026-11-19), its conflicted-merge branch; shape `sh-20261119T072530Z-663f`
  findings F02 and F08.
- **Today, a conflicted merge gets a full round.** §15.6's re-verify rule, at `b9e58ce`: "A merge with a
  conflict, or one whose own change moved, is reviewed and verified in full." `runs.unreviewed_fix`
  lets a head through to verify only when every round since the last done review is a merge round and
  the head carries the reviewed change unchanged (`same_change`, the same patch id). A conflicted
  merge usually changes the patch, so `ccp prompt verify` refuses it (exit 4) until a new full review.
- **A mode, not a phase (F08).** The resolution review is built as a `mode` on a review run, not as a
  seventh phase. `unreviewed_fix` then takes a done resolution review as the last review of its head
  with no change: it compares the head that review judged.
- **Phase lists today.** The phases are written out as literals beside `runs.PHASES`.
  `git grep -n -e '"implement", "fix", "merge", "ruling", "review", "verify"' -e '"implement", "review", "fix", "merge", "ruling", "verify"' -- ccp`
  at `b9e58ce` prints 3 lines: `ccp/cli.py:1201` (the `ccp prompt` phase choices), `ccp/health.py:806`
  (`ROUND_KINDS`) and `ccp/runs.py:24` (`PHASES`). `prompt.PHASE_STATUS` maps each phase to a queue
  status, which is not a copy of the list, so it stays.
- **E14** (`docs/ENGINEERING.md`): git merge analysis goes through one helper module. Its check is
  `git grep -n "merge-tree\|patch-id\|remerge-diff" -- ccp`.
  - This task reads the head's remerge diff only through `gitmerge.remerge_diff` from 0162-git-merge-helper
    (`ccp/gitmerge.py`), and names none of those subcommands in any other `ccp` module.
  - The command the reviewer runs, `git show --remerge-diff <head>`, is written in
    `templates/prompts/review.md`, outside `ccp/`.
  - `git --version` on this machine: 2.56.0. `--remerge-diff` needs git 2.36 or later.
- **No contract file for runs.** §11.1 names `contracts/run.schema.json`, but `ls contracts` at
  `b9e58ce` lists no such file: run records have no schema. So the new run keys (`mode`, `resolution`,
  `affected_checks`) go into §11.1's field list (§31.1, this task's own feature) and the code.
- **Report refusals.** `ccp report` refuses a malformed report with exit 1, "report refused, nothing
  written" (`report.submit`). `ccp verify record` refuses with exit 1, "refused, nothing written".
- Rules this brief sets:
  - The resolution review is allowed only after a done review and only over merge rounds. It never
    stands in for a task's first review.
  - "Earlier approve" means the head of the task's latest `approve` verdict. A task with no approve
    yet has nothing to rest on, so its verifier runs every check.
  - `Affected checks: none` is allowed: the gate lane still runs.
- §31: the meaning of §13.2's round kinds, §15.2's review gate and §15.6's re-verify rule changes, so this task
  carries signed text. The §13.4 report lines are signed with it, since they add a refusal. The §11.1
  run fields only describe this task's feature (§31.1).

## Scope

- **In:**
  - `ccp/cli.py`:
    - `ccp prompt` gains `--mode {resolution}`, accepted with `review` only; any other phase refuses
      it with exit 2;
    - the phase choices are `(*runs.PHASES, "env")`, not a literal (F08);
    - the usage line in the module docstring gains `[--mode resolution]`.
  - `ccp/health.py`: `ROUND_KINDS = runs.PHASES` (F08). The order of health's round buckets follows
    `runs.PHASES`.
  - `ccp/prompt.py`, review with `--mode resolution`:
    - it refuses (exit 2, nothing opened) when the task has no review run that reported `done`; when a
      run since the latest such review is not a merge round; when `--head` is not a merge commit (two
      parents or more); or when `gitmerge.remerge_diff` gives an empty diff for it ("no conflict was resolved: a
      clean merge needs no resolution review").
    - Otherwise it opens a review run with `mode: "resolution"` and renders `review.md`'s
      `{{#resolution}}` section with the head.
    - Verify after a done resolution review with `resolution: contained`: the verify prompt lists its
      `affected_checks` to rerun. It names the head of the task's latest approve as `<old>` for the
      other checks' `rests_on: "approve at <old>"`, or says every check runs when there is no approve.
  - `templates/prompts/review.md`: a `{{#resolution}}...{{/resolution}}` section (new). It replaces the
    full-diff instruction in this mode with:
    - read only `git show --remerge-diff {{head}}`, the task file's dod_checks and the conflict
      hunks' surroundings;
    - judge whether the resolution keeps both sides' intent and changes nothing of the task's own
      beyond the conflict hunks;
    - report `Resolution:` and `Affected checks:` as §13.4 says.
    Outside this mode the template renders as today.
  - `templates/prompts/verify.md`: a section, rendered after a contained resolution review, that says
    which checks to rerun and how the rest rest on `<old>`.
  - `ccp/report.py`: for a review run with `mode: "resolution"` and `Outcome: done`:
    - it reads `Resolution: contained` or `Resolution: beyond <why>`;
    - it reads `Affected checks: <id>, <id>` or `Affected checks: none`, and checks each id against
      the task file's dod_check ids (`tasklog.CHECK_RE`);
    - it refuses (exit 1, nothing written), naming the line, a report that misses a line or names an
      unknown id;
    - it stores `resolution` and `affected_checks` on the run.
  - `ccp/runs.py` `unreviewed_fix`: a done review run with `resolution: "beyond"` does not count as a
    review. The refusal names it and says "the resolution review judged it beyond the conflict hunks:
    run a full `ccp prompt review`".
  - `ccp/verify.py`: `record` refuses (exit 1) an approve when the task's latest done review is a
    contained resolution review at the record's `head_sha` and an id in its `affected_checks` is
    missing from the record or recorded `ran: false`. The refusal names the ids. A reject is never
    held back.
  - `plugin/agents/delivery-runner.md`, the Merge rules bullet "A conflict or a changed own diff:
    review, then verify, in full." becomes: a merge round whose merge conflicted goes to
    `ccp prompt review --mode resolution` (SPEC §13.2, §15.6 rule 3); a resolution judged `beyond`, or
    any other change to the own diff, goes to a full review and verify.
  - `plugin/agents/delivery-verifier.md`, the integration-merge bullet: after a resolution review,
    rerun the checks your prompt names and the gate; the rest rest on the approve your prompt names
    (SPEC §15.6 rule 3).
  - `docs/cli/02-delivery.md`: the `ccp prompt` row gains `--mode resolution` (review only).
  - `docs/spec/02-delivery.md` §11.1 (§31.1, this task's own feature): the run record field list gains
    `mode` (`resolution` on a resolution review), `resolution` and `affected_checks`.
  - `docs/spec/02-delivery.md`, four signed passages. Each PROPOSED goes in on lines of its own,
    unwrapped:
    1. §13.2. CURRENT (at `b9e58ce`): "reviewed change unchanged (the same patch id, §15.2)." PROPOSED:
       > reviewed change unchanged (the same patch id, §15.2). After a merge round whose merge conflicted, `ccp prompt review <id> --pr <n> --head <sha> --mode resolution` opens a resolution review in place of a full one: a review run with `mode: resolution`, rendered from the review template, whose reviewer reads only the resolution (`git show --remerge-diff` of the head, which shows how the committed merge differs from git's own merge) and reports whether it stays within the conflict hunks and which dod_checks it can affect (§13.4). It is refused (exit 2, nothing opened) when the task has no review that reported `done`, when a round since the latest such review is not a merge round, when the head is not a merge commit, or when the head's remerge diff is empty.
    2. §13.4, a new bullet after the `## Spec beyond intent` bullet. CURRENT: none (new text). PROPOSED:
       > - for a review with `mode: resolution` and `Outcome: done`, `Resolution: contained` (the resolution changes nothing of the task's own beyond the conflict hunks) or `Resolution: beyond` followed by why, and `Affected checks:` followed by the ids of the task's dod_checks the resolution can affect, comma-separated, or `none`; a report missing either line, or naming an id that is not a dod_check of the task, is refused (exit 1, nothing written), and the run keeps `resolution` and `affected_checks`;
    3. §15.2, the fix-round bullet. CURRENT (at `b9e58ce`): "(the next three rules)." PROPOSED:
       > (the next three rules). A resolution review (§13.2) that reported `done` with `Resolution: contained` is the review of the head it judged; one with `Resolution: beyond` is not, and the head is reviewed again in full.
    4. §15.6 rule 3. CURRENT (at `b9e58ce`): "printing nothing). A merge with a conflict, or one whose own change moved, is reviewed and verified" PROPOSED:
       > printing nothing). A merge whose own change moved is reviewed and verified in full, except that a merge with a conflict may have a resolution review instead (§13.2): the verifier then reruns the checks that review names in `Affected checks` and runs the gate at the new head through `ccp suite run`, and records every other check `ran: false`, `pass: null`, `rests_on: "approve at <old>"`, `<old>` the head of the task's latest approve (with no approve yet, it runs every check); `ccp verify record` refuses an approve that leaves an affected check not run. A resolution the reviewer judges `beyond` the conflict hunks is reviewed and verified
  - `tests/test_resolution_review.py` (new): the checks below, on fenced temp products and queues.
- **Out:**
  - Close's own catch-up (task 0167).
  - The implementer's catch-up before review and the review refusal of a conflicting head (task 0166).
  - Counting conflict catch-ups (task 0169).
  - A seventh phase, or a change to `prompt.PHASE_STATUS`.
  - Any change to a review or verify outside resolution mode.

## dod_checks

- id: `rr-01`
  story: As a runner, after a conflicted merge round I open a resolution review, and it is refused where it does not apply.
  setup: a fenced product and queue: task 0002 claimed, a review run reported `done` at head H1, then a merge round reported at H2, a merge commit whose merge of the tip conflicted and was resolved; a second product the same but with H2 a clean merge; a third with no done review.
  steps:
    1. Run `ccp prompt review 0002 --pr <n> --head H2 --mode resolution` in the first product.
    2. Run the same command in the second and third products.
    3. Run `ccp prompt verify 0002 --pr <n> --head H2 --mode resolution` in the first product.
  expect: step 1 exits 0, the run record has `mode: "resolution"`, and the rendered prompt holds `git show --remerge-diff` with H2; step 2 exits 2 in both, nothing opened, naming the empty remerge diff and the missing done review; step 3 exits 2 naming `--mode`.
  dry run (`b9e58ce`): `ccp prompt --help | grep -c -- --mode` prints 0: there is no such option.
- id: `rep-01`
  story: As a reviewer, my resolution report must say how far the resolution reaches and which checks it can affect.
  setup: the first product of rr-01 with its resolution review run open; the task file has checks `cmd-01` and `cmd-02`.
  steps:
    1. Submit a done report with `Severity:`, `## Spec beyond intent`, `Resolution: contained` and no `Affected checks:` line, through `ccp report`.
    2. Submit one with `Affected checks: cmd-01, cmd-09`.
    3. Submit one with `Resolution: contained` and `Affected checks: cmd-01`.
  expect: steps 1 and 2 exit 1, nothing written, naming `Affected checks` and `cmd-09`; step 3 exits 0 and the run keeps `resolution: "contained"` and `affected_checks: ["cmd-01"]`.
  dry run: n/a — resolution review runs do not exist at `b9e58ce`.
- id: `gate-01`
  story: As a runner, a contained resolution review lets verify open at its head; a beyond one sends the task to a full review.
  setup: the product of rep-01 after step 3, plus a copy whose resolution report said `Resolution: beyond the fix renames a function the task adds`.
  steps:
    1. Run `ccp prompt verify 0002 --pr <n> --head H2 --note "conflicted merge, resolution review"` in each.
  expect: in the first, exit 0, and the verify prompt names `cmd-01` to rerun and H1 as `approve at` for `cmd-02`; in the copy, exit 4, nothing opened, the message naming the resolution review and `full`.
  dry run (`b9e58ce`): with only H1's review and the merge round at H2 (a changed patch), `ccp prompt verify` refuses exit 4, "merge round … is newer than the last review": `python3 -m unittest tests.test_prompt_rounds -k test_a_merge_that_moved_the_reviewed_change_is_reviewed_again` ran 1 test, OK.
- id: `rec-01`
  story: As the plane, an approve after a resolution review must rerun every affected check.
  setup: the first product of gate-01 with its verify run open at H2, and the task's earlier approve at H1.
  steps:
    1. Run `ccp verify record <file>` with an approve at H2 recording `cmd-01` as `ran: false`, `rests_on: "approve at H1"`.
    2. Run it again with `cmd-01` run and passed and `cmd-02` as `ran: false`, `rests_on: "approve at H1"`.
  expect: step 1 exits 1, nothing written, naming `cmd-01`; step 2 exits 0.
  dry run: n/a — at `b9e58ce` step 1's record is refused for another reason (the merge round is newer than the last review); the affected-check refusal does not exist.
- id: `f08-01`
  story: As a plane maintainer, the round phases are listed once.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n -e '"implement", "fix", "merge", "ruling", "review", "verify"' -e '"implement", "review", "fix", "merge", "ruling", "verify"' -- ccp`.
    2. Run `git grep -n "merge-tree\|patch-id\|remerge-diff" -- ccp`.
  expect: step 1 prints exactly one line, `ccp/runs.py` (`PHASES`); step 2 lists only `ccp/gitmerge.py` (E14).
  dry run (`b9e58ce`): step 1 prints 3 lines (`ccp/cli.py:1201`, `ccp/health.py:806`, `ccp/runs.py:24`).
- id: `suite-01`
  story: As a plane developer, the SPEC carries the signed words and nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0168-resolution-review --base origin/main`.
    2. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: step 1 exits 0 with all four passages found in `docs/spec/02-delivery.md`; step 2's commands all pass and the branch list is empty.
  dry run: n/a — the passages are not in the SPEC at `b9e58ce`.

## Implementation notes

*Append-only, newest last.*

## Verification notes
