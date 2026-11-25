---
task_id: 0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs
title: A feature task may cite the accepted ADR decisions it builds in adr_refs in place of spec_refs, and a task citing neither is told both lists
status: pending
kind: feature
depends_on: []
spec_refs: ["S5", "S21", "S29"]
review_point: R36
paths: ["ccp/config.py", "ccp/tasklog.py", "contracts/plane_config.schema.json", "tests/test_kinds.py", "tests/test_plane_json_constants.py", "tests/test_task_placeholders.py", "tests/test_task_format.py", "plugin/skills/writing-tasks/SKILL.md", "docs/spec/01-model.md", "docs/adr/0043-opinionated-defaults-short-configuration.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0335-absence-checks-allow-indented-forms-the-repo-s-task-rules-point-at-e21-and-init-counts-only-files-git-keeps", "0337-five-constants-become-plane-json-settings-again", "0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock"]
adopt: "none"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs

## Intent

A product's feature task that builds an accepted ADR decision cites it in `adr_refs` and passes `ccp tasks check`
without a `spec_refs` key: by default a feature task cites at least one of `spec_refs` and `adr_refs`, and neither key
is required on its own. A task that cites neither is told to list the SPEC sections in `spec_refs` or the ADR
decisions in `adr_refs`. A refactor's rules are unchanged.

## Context (not checked)

A managed product filed a plane proposal: an accepted ADR decision is as traceable as a SPEC section, and its feature
tasks that build a decision had to carry a SPEC citation only to pass the check. ADR-0043 D9 made the canonical task
format (`task_log.required`, `task_log.refs_any`) constants, so the product could not change it. The lead accepted the
proposal, and the operator ruled on 2026-11-24:

> Agree with all recommendations. Go ahead.

That ruling approves this task's § text, which only describes the new default and the message (§31.1). It changes
the two constants' values for every product.

Measured at `554fe3a`:

- `"TASK_LOG_DEFAULTS"` in `ccp/config.py` holds `"required": ["task_id", "title", "status", "depends_on",
  "spec_refs", "created", "updated"]` and `"refs_any": ["spec_refs"]`; the schema's defaults are the same
  (`python3 -c 'import json; s = json.load(open("contracts/plane_config.schema.json"))["properties"]["task_log"]["properties"]; print(s["required"]["default"], s["refs_any"]["default"])'`).
- `"SPEC_REFS_HINT = "` in `ccp/tasklog.py` is the one hint text, returned by `"def _spec_hint"` when
  `spec_refs` is among the lists a task must cite one of.
- A scratch feature task citing only `adr_refs` fails `ccp tasks check` twice: the frontmatter misses the
  `spec_refs` key, and it `cites none of spec_refs` (cmd-01's dry run).
- The refactor kind (`task_log.kinds`) already forbids both `spec_refs` and `adr_refs`, and `"def kind_forbids"`
  adds the task log's `refs_any` lists a kind with its own `refs_any` does not share, so a refactor still may cite
  neither.

**Ruled.**

- **Defaults.** `TASK_LOG_DEFAULTS["required"]` drops `"spec_refs"`; `TASK_LOG_DEFAULTS["refs_any"]` becomes
  `["spec_refs", "adr_refs"]`. Both stay constants (§29.3): a product that sets the old value keeps it, with the
  constant warning; one that sets the new value is told it can delete the key. The schema's two defaults and
  descriptions follow (`Constant, ["spec_refs", "adr_refs"]` for `refs_any`).
- **The hint.** When both `spec_refs` and `adr_refs` are among the lists a task must cite one of, the hint is
  " — list the SPEC sections this task answers to in `spec_refs`, or the ADR decisions it builds in `adr_refs`,
  and cite them in its text (§5.2)", each list name in backticks as today's hint writes `spec_refs`; with only
  `spec_refs` among them, it is today's.
- **Tests.** `tests/test_kinds.py` gains class `FeatureCitesAdrRefs(unittest.TestCase)` on a product that sets no
  `task_log` block: `test_a_feature_citing_only_adr_refs_passes`, `test_a_feature_citing_only_spec_refs_passes`,
  `test_a_task_citing_neither_is_told_both_lists` and `test_a_refactor_citing_adr_refs_is_still_refused`.
  `tests/test_plane_json_constants.py` `WAS` holds the two new values, each with a comment naming this task.
  `tests/test_task_placeholders.py`: `test_an_empty_spec_refs_says_to_list_the_sections_and_cite_them` (no
  `task_log` block) and `test_with_the_architect_block_a_feature_gets_the_same_hint` (`refs_any` both lists) expect
  the two-list hint ("or the ADR decisions it builds in `adr_refs`, and cite them");
  `test_a_kind_with_its_own_refs_naming_spec_refs_gets_the_hint` (a feature kind whose own `refs_any` is
  `["spec_refs"]`) keeps today's hint. `tests/test_task_format.py` `Kinds.test_a_configured_kind_sets_its_own_refs`
  expects `kind_refs(p.cfg, "feature") == ["spec_refs", "adr_refs"]`. No other test expectation changes.
- **Skill.** `plugin/skills/writing-tasks/SKILL.md`, the `spec_refs`, `adr_refs` frontmatter row: by default a
  feature task cites at least one of the two (`task_log.refs_any`), and neither key is required on its own; a kind
  with its own `refs_any` (a refactor) cites its own lists. The sentence that says `spec_refs` is a required key goes.
- **ADR-0043.** Its `notes` gain one line, `2026-11-24: operator: a feature task cites spec_refs or adr_refs;
  task_log.required no longer lists spec_refs`; in the appendix the `required`, `refs_any`, ... bullet ends
  `(refs_any spec_refs or adr_refs, required without spec_refs: operator 2026-11-24)`. Nothing else in the ADR
  changes.

Lead's ruling on this task (0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs-r1, 2026-11-25), as the
runner passed it:

> Ruling 0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs-r1 (the lead, 2026-11-25): Option (a). Drop
> `adr_refs: ["0043 D9"]` from this task's file on the task branch, as task 0192 did, so the edit lands in your PR.
> adr.strict refuses approving a head whose cited decision is still not_built; D9 stays not_built until 0191. The
> task's authority is the operator's 2026-11-24 ruling, which its Context quotes. Do not run `ccp adr decide 43 D9
> built`. Remove the field outright (as 0192 did), quote this ruling in the task's Context (not checked) section, and
> keep the rest of the task as written. Note: this task's own checks (a feature task citing only adr_refs) concern
> scratch products, not this task's file, so dropping its adr_refs should leave its spec_refs (S5, S21, S29) as its
> citations.

## Scope

- **In:** `ccp/config.py` (two defaults), `ccp/tasklog.py` (the hint), `contracts/plane_config.schema.json` (two
  defaults and descriptions), `tests/test_kinds.py` (class `FeatureCitesAdrRefs`), `tests/test_plane_json_constants.py`
  (`WAS`), `tests/test_task_placeholders.py` (two hint expectations), `tests/test_task_format.py` (one `kind_refs`
  expectation), `plugin/skills/writing-tasks/SKILL.md` (one row), `docs/adr/0043-opinionated-defaults-short-configuration.md`
  (the note and one appendix bullet); the SPEC, describing this task's own feature (§31.1, on the operator's ruling
  of 2026-11-24): the two passages below. No other § sentence changes.

  CURRENT (`docs/spec/01-model.md` at `3539c23`), §5.4, the paragraph:
  > Two kinds, read with the architect seat on, for tasks from its adoption point (§19.11). Each names
  > the ref lists a task of that kind cites at least one of, and the lists it leaves empty: `feature`
  > cites `spec_refs`; `refactor` cites `rule_refs` or `review_refs` and no `spec_refs` or `adr_refs` (a
  > refactor changes no rule, §20).

  PROPOSED:
  > Two kinds, read with the architect seat on, for tasks from its adoption point (§19.11). Each names the ref lists a task of that kind cites at least one of, and the lists it leaves empty: `feature` cites `spec_refs` or `adr_refs` (an accepted ADR decision is as traceable as a SPEC section); `refactor` cites `rule_refs` or `review_refs` and no `spec_refs` or `adr_refs` (a refactor changes no rule, §20).

  CURRENT (`docs/spec/01-model.md` at `3539c23`), §5, the list item:
  > - A task that cites no ref list, where `spec_refs` is one of the lists it may cite, is told to list
  >   the SPEC sections in `spec_refs` and cite them in its text.

  PROPOSED:
  > - A task that cites no ref list, where `spec_refs` is one of the lists it may cite, is told to list the SPEC sections in `spec_refs` (or, where `adr_refs` is one too, the ADR decisions it builds in `adr_refs`) and cite them in its text.
- **Out:** `task_log.kinds` and the refactor rules; making either key a setting; `templates/docs-delivery/`
  (a product's managed copies; the template's comment that a product may require `adr_refs` stays true); the
  §20.3 refactor text; checking that a cited ADR decision exists beyond what `ccp tasks check` checks today.

## dod_checks

- id: `cmd-01`
  story: As a product's lead, a feature task citing only the ADR decision it builds passes the task check.
  setup: A checkout of the PR head (any seat); the step builds its scratch product with one such task.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; json.dump(c, open(p, "w"))' "$P" && printf -- '---\ntask_id: 0001-first\ntitle: Do the first thing\nstatus: pending\ndepends_on: []\nadr_refs: ["0001 D1"]\nparallel: true\ncreated: 2026-11-25\nupdated: 2026-11-25\n---\n\n## Intent\n\nA.\n\n## Context (not checked)\n\nB.\n\n## Scope\n\n- **In:** c.\n- **Out:** d.\n\n## dod_checks\n\n- id: \140cmd-01\140\n  story: As a user, I see it.\n  setup: none.\n  steps:\n    1. Look.\n  expect: it is there.\n\n## Implementation notes\n\n## Verification notes\n' > "$P/docs/delivery/tasks/0001-first.md" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" tasks index >/dev/null 2>&1; env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" tasks check > "$D/out" 2>&1; echo "exit $?"; grep -cE 'missing .spec_refs.|cites none of' "$D/out"`.
  expect: exactly two lines: `exit 0`, then `0`.
  dry run (`3539c23`): printed `exit 1`, then `2` (the missing `spec_refs` key, and `cites none of spec_refs`).
- id: `cmd-02`
  story: As a product's lead, a task citing nothing is told it can cite the SPEC or the ADR decision it builds.
  setup: A checkout of the PR head (any seat); the step builds its scratch product with a task citing nothing.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; json.dump(c, open(p, "w"))' "$P" && printf -- '---\ntask_id: 0001-first\ntitle: Do the first thing\nstatus: pending\ndepends_on: []\nspec_refs: []\nparallel: true\ncreated: 2026-11-25\nupdated: 2026-11-25\n---\n\n## Intent\n\nA.\n\n## Context (not checked)\n\nB.\n\n## Scope\n\n- **In:** c.\n- **Out:** d.\n\n## dod_checks\n\n- id: \140cmd-01\140\n  story: As a user, I see it.\n  setup: none.\n  steps:\n    1. Look.\n  expect: it is there.\n\n## Implementation notes\n\n## Verification notes\n' > "$P/docs/delivery/tasks/0001-first.md" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" tasks index >/dev/null 2>&1; env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" tasks check > "$D/out" 2>&1; echo "exit $?"; grep -c 'cites none of spec_refs, adr_refs — list the SPEC sections this task answers to in .spec_refs., or the ADR decisions it builds in .adr_refs.' "$D/out"`.
  expect: exactly two lines: `exit 1`, then `1`.
  dry run (`3539c23`): printed `exit 1`, then `0` (the message names `spec_refs` only).
- id: `code-01`
  story: As a plane developer, the tests hold the new default, the hint and the unchanged refactor rule.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_kinds.FeatureCitesAdrRefs.test_a_feature_citing_only_adr_refs_passes tests.test_kinds.FeatureCitesAdrRefs.test_a_feature_citing_only_spec_refs_passes tests.test_kinds.FeatureCitesAdrRefs.test_a_task_citing_neither_is_told_both_lists tests.test_kinds.FeatureCitesAdrRefs.test_a_refactor_citing_adr_refs_is_still_refused tests.test_plane_json_constants.TheConstants tests.test_task_placeholders tests.test_task_format.Kinds`.
  expect: exit 0.
  dry run (`3539c23`): exit 1, the run FAILED (`FeatureCitesAdrRefs` does not exist yet).
- id: `doc-01`
  story: As a product's lead, the contract and the task-writing skill give the new default.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -c 'import json; s = json.load(open("contracts/plane_config.schema.json"))["properties"]["task_log"]["properties"]; print("spec_refs" in s["required"]["default"], s["refs_any"]["default"])'`.
    2. Run `grep -c 'is a required key by default' plugin/skills/writing-tasks/SKILL.md`.
  expect: step 1 prints `False ['spec_refs', 'adr_refs']`; step 2 prints `0`.
  dry run (`3539c23`): step 1 printed `True ['spec_refs']`; step 2 printed `1`.
- id: `spec-01`
  story: As the operator, §5 and §5.4 say a feature cites spec_refs or adr_refs, and what a task citing neither is told.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0338`.
  expect: exit 0, both PROPOSED passages found.
  dry run (`3539c23`, with this brief): exit 1, both passages `not found in the SPEC`.

## Implementation notes

## Verification notes
