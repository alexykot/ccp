---
task_id: 0337-five-constants-become-plane-json-settings-again
title: architect.rules_max_lines, notes_due and max_new_tasks, task_log.dry_run and docs.workers are plane.json settings again, with their constants as defaults, so a product that sets one hears no constant warning
status: done
kind: feature
depends_on: []
spec_refs: ["S4", "S8", "S19", "S20", "S21", "S29"]
review_point: R36
paths: ["ccp/config.py", "contracts/plane_config.schema.json", "tests/test_plane_json_constants.py", "tests/test_doc_rules.py", "README.md", "docs/spec/01-model.md", "docs/spec/03-quality.md", "docs/adr/0043-opinionated-defaults-short-configuration.md"]
clashes_with: ["0191-the-grace-release-ends", "0331-ccp-holds-its-own-ledger-library-and-review-kit-validates-a-triage-by-its-schema-and-reads-a-binding-by-id-through-the-one-resolver", "0335-absence-checks-allow-indented-forms-the-repo-s-task-rules-point-at-e21-and-init-counts-only-files-git-keeps", "0338-a-feature-task-may-cite-adr-refs-in-place-of-spec-refs", "0341-an-exclusive-lane-may-declare-a-cache-probe-that-lets-a-fully-cached-run-skip-the-lock"]
adopt: "plane.json task_log.dry_run true, for a product that wants a recorded dry run on each check that runs a command"
created: 2026-11-25
updated: 2026-11-25
---

# Task: 0337-five-constants-become-plane-json-settings-again

## Intent

A product sets the length cap of its house-rules document, the architect's friction cadence and triage cap, whether
its tasks must record a dry run, and how many docs-check commands run at once, as ordinary plane.json settings again:
`architect.rules_max_lines` (default 150), `architect.notes_due` (default 3), `architect.max_new_tasks` (default 5),
`task_log.dry_run` (default off) and `docs.workers` (default: as many as there are checks). A value it sets applies
with no "constant in code" warning on any command, `ccp upgrade status` no longer lists the key, and the schema and
the SPEC describe each as a setting with its default.

## Context (not checked)

ADR-0043 D9 kept "choices a product makes: refactor capacity, the architect's cadence, quality knobs" as settings,
but its appendix made these five constants. A managed product filed plane proposals to keep them (a rules document's
length scales with the product; the architect's cadence is the product's; a dry-run requirement the operator had
approved as an opt-in on 2026-10-24 was made a constant at off; a docs-check cap protects a resource only the product
knows). The lead accepted them, and the operator ruled on 2026-11-24:

> Agree with all recommendations. Go ahead.

That ruling approves this task's § text, which only describes the five keys as settings and corrects the passages
that called them constants (§31.1). `worktrees.dir` stays a constant: its proposal was declined.

Measured at `554fe3a`:

- The five keys are constants: `python3 -c 'from ccp import config; print([k for k in ("architect.rules_max_lines", "architect.notes_due", "architect.max_new_tasks", "task_log.dry_run", "docs.workers") if config.KEY_OUTCOMES[k].kind == config.CONSTANT])'`
  printed all five. They come from `"_CONSTANT_KEYS: tuple"` in `ccp/config.py`: `"dry_run"` in the `task_log`
  entry, `("workers",)` in the `docs` entry, and `"rules_max_lines"`, `"notes_due"`, `"max_new_tasks"` in the
  `architect` entry. The `docs.workers` entry is also re-shaped by
  `KEY_OUTCOMES["docs.workers"] = replace(KEY_OUTCOMES["docs.workers"], shown="as many as there are checks")`.
- Every reader already reads the loaded block (`ccp/rules.py` `a["rules_max_lines"]` and
  `(cfg.docs or {}).get("workers")`, `ccp/architect.py` `_settings(cfg)["notes_due"]` and `s["max_new_tasks"]`,
  `ccp/init.py` `["rules_max_lines"]`, `ccp/tasklog.py` the `task_log` block's `dry_run`), and the loader's
  validation (`"_INTS = {"` for the three architect keys, `"tl.get(\"dry_run\", False)"`, `_workers_problems`)
  is unchanged; so the change is the registry, the schema, the tests and the text.
- `contracts/plane_config.schema.json` marks each `"deprecated": true` with a description starting `Constant`.
- A scratch product setting all five gets five `is a constant in code` warnings from `ccp docs check` (cmd-01's
  dry run).

**Ruled.**

- **Registry.** The five keys leave `_CONSTANT_KEYS` (and the `docs.workers` `replace(...)` line goes), so they are
  no `KEY_OUTCOMES` entries; their defaults stay in `TASK_LOG_DEFAULTS`, `DOCS_DEFAULTS` and `ARCHITECT_DEFAULTS`
  as today (150, 3, 5, false, null). Nothing else in `_CONSTANT_KEYS` changes.
- **Schema.** Each of the five loses `"deprecated": true`, keeps its type, minimum and default, and gets a
  description that names it a setting with its default and cites its §: `architect.rules_max_lines` §20.1,
  `architect.notes_due` §19.6, `architect.max_new_tasks` §19.8, `task_log.dry_run` §21.1, `docs.workers` §21.5
  (null: every check command at once).
- **Tests.** `tests/test_plane_json_constants.py`: the five leave `CONSTANTS` and `WAS`, and join `KEPT`. A new
  class `TheSettingsAgain(unittest.TestCase)` with `test_the_five_keys_are_settings_with_their_old_defaults` (no
  `KEY_OUTCOMES` entry, not deprecated in the schema, the block default unchanged) and
  `test_a_value_set_loads_with_no_warning_and_applies` (a plane.json setting all five loads with empty stderr and
  empty `key_notes`, and each loaded block holds the value set). `TheUpgradeStatus.test_a_constant_in_words_is_named_in_words`
  is deleted: its subject, `docs.workers` named in words as a constant, is gone. `Outcome.shown` and the `shown`
  branch of `"def shown_constant"` (`ccp/upgrade.py`) stay, because a binding constant still names itself in words
  (`"runner.rotate_at_context_tokens": c.Outcome(c.CONSTANT, value=None, shown="off")` in
  `ccp/lib.py`, at `554fe3a`); only the `docs.workers` `replace(...)` line goes.
  `tests/test_doc_rules.py` `ParallelChecks`: `test_a_number_set_still_caps_them_with_the_constant_warning` becomes
  `test_a_number_set_caps_them_with_no_warning` (the cap holds, stderr carries no `is a constant in code`), and
  `test_an_explicit_null_is_the_constant_and_warns_that_the_key_can_go` becomes
  `test_an_explicit_null_loads_with_no_warning` (every check at once, no warning). No other test expectation
  changes.
- **README.** The `--adopt` sentence under the rules-doc adoption (`over its 150-line limit (SPEC §20.1)`) names the
  setting: "over its line limit, `architect.rules_max_lines` (default 150; SPEC §20.1)".
- **ADR-0043.** Its `notes` gain one line, `2026-11-24: operator: architect.rules_max_lines, notes_due and
  max_new_tasks, task_log.dry_run and docs.workers are settings again, defaults unchanged ("Agree with all
  recommendations. Go ahead.")`. In the appendix the five move from "`plane.json`, constants" to
  "`plane.json`, kept", each followed by `(a setting again, operator 2026-11-24)`, and D9's `task_log.dry_run`
  bullet ends `(reversed 2026-11-24: a setting, default off)`. D9 stays `not_built`; nothing else in the ADR changes.

Ruling 0337-five-constants-become-plane-json-settings-again-r1 (the lead, 2026-11-25), as the runner passed it:

> Option (a). Drop `adr_refs: ["0043 D9"]` from this task's file on the task branch, so the edit lands in PR #413, as
> task 0192 did. adr.strict refuses approving a head whose cited decision is still not_built. D9 stays not_built
> until 0191. The task's authority is the operator's 2026-11-24 ruling, which its Context quotes. Do not run
> `ccp adr decide 43 D9 built`. Change nothing else; the front matter becomes `adr_refs: []` (or the field removed,
> as 0192 did). Re-run tasks check and docs check.

## Scope

- **In:** `ccp/config.py` (the registry), `contracts/plane_config.schema.json` (five descriptions),
  `tests/test_plane_json_constants.py` (the lists, class `TheSettingsAgain`, one test deleted),
  `tests/test_doc_rules.py` (two tests renamed and re-expected), `README.md` (one sentence),
  `docs/adr/0043-opinionated-defaults-short-configuration.md` (the note and the appendix); the SPEC, describing this
  task's own feature (§31.1, on the operator's ruling of 2026-11-24): the eight passages below, which only name the keys as settings with their defaults and correct the text that called
  them constants. No other § sentence changes.

  CURRENT (`docs/spec/03-quality.md` at `3539c23`), §19.6 trigger 3, its first sentence (the rest of the item
  unchanged):
  > 3. **Friction notes.** Enough distinct tasks have a worker's friction note since the last pass's
  >    start: a fixed number (a constant in code) times the product's `parallel.max_in_flight` (1 when
  >    tasks run one at a time, §16.2), as for the cadence.

  PROPOSED:
  > 3. **Friction notes.** Enough distinct tasks have a worker's friction note since the last pass's start: `architect.notes_due` (default 3) times the product's `parallel.max_in_flight` (1 when tasks run one at a time, §16.2), as for the cadence.

  CURRENT (`docs/spec/03-quality.md` at `3539c23`), §19.8, *Triage authority*, the clause:
  > creates at most 5 tasks (grouping related findings; doc fixes grouped into
  > one or two tasks),

  PROPOSED:
  > creates at most `architect.max_new_tasks` tasks (default 5; grouping related findings; doc fixes grouped into one or two tasks),

  CURRENT (`docs/spec/03-quality.md` at `3539c23`), §20.1, the paragraph's last sentence:
  > They are at most 150
  > lines, which `ccp docs check` enforces.

  PROPOSED:
  > They are at most `architect.rules_max_lines` lines (default 150), which `ccp docs check` enforces.

  CURRENT (`docs/spec/03-quality.md` at `3539c23`), §21.1, the list item's opening (the rest of the item
  unchanged):
  > - in a product that still sets `task_log.dry_run: true` (§29.3), a `dod_check` of a task not `done` or `dropped` whose numbered step

  PROPOSED:
  > - with `task_log.dry_run` on (default off), a `dod_check` of a task not `done` or `dropped` whose numbered step

  CURRENT (`docs/spec/03-quality.md` at `3539c23`), §21.5, the paragraph's last sentence:
  > A number in `docs.workers` still caps them, with the
  > constant warning (§29.3).

  PROPOSED:
  > A number in `docs.workers` caps how many run at once (default none: every check command at once).

  CURRENT (`docs/spec/01-model.md` at `3539c23`), §4.5 *An existing rules doc*, the clause:
  > its 150-line cap (§20.1),

  PROPOSED:
  > its line cap, `architect.rules_max_lines` (§20.1),

  CURRENT (`docs/spec/01-model.md` at `3539c23`), §8.1, the table row the new row follows, unchanged (the new row
  goes after it and retires no sentence):
  > | `spec_paths` | the SPEC files, read by the sign-off checks and the estimator | §3.5, §26 |

  PROPOSED:
  > | `task_log` | whether each check that runs a command must record a dry run (`task_log.dry_run`, default off) | §5.5, §21.1 |

  CURRENT (`docs/spec/01-model.md` at `3539c23`), §8.1, the table row:
  > | `package_docs`, `docs` | doc checks, run when `language` names a pack (`claude_md_dirs`, `docstring_globs`, `delivery_id_patterns`, `rules`), product check commands (`docs.checks`), the starter house rules (`docs.starter_rules`, §20.5) | §21 |

  PROPOSED:
  > | `package_docs`, `docs` | doc checks, run when `language` names a pack (`claude_md_dirs`, `docstring_globs`, `delivery_id_patterns`, `rules`), product check commands (`docs.checks`) and how many run at once (`docs.workers`), the starter house rules (`docs.starter_rules`, §20.5) | §21 |
- **Out:** `worktrees.dir` and every other constant; `task_log.required` and `task_log.refs_any` (0338); marking
  ADR-0043 D9 built (0191); any reader's behaviour; `Outcome.shown` (a binding constant uses it); the rest of
  `README.md` (it already calls `task_log.dry_run` a product's choice).

## dod_checks

- id: `cmd-01`
  story: As a product's lead, the five keys I set apply with no constant warning on any command.
  setup: A checkout of the PR head (any seat); the step builds its scratch product.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["architect"].update(rules_max_lines=200, notes_due=2, max_new_tasks=3); c["task_log"] = {"dry_run": True}; c["docs"]["workers"] = 2; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" docs check > "$D/out" 2>&1; echo "exit $?"; grep -c 'is a constant in code' "$D/out"`.
  expect: exactly two lines: `exit 0`, then `0`.
  dry run (`3539c23`): printed `exit 0`, then `5` (one warning for each of the five keys).
- id: `cmd-02`
  story: As a product's lead, ccp upgrade status no longer lists the five keys as constants I still set.
  setup: A checkout of the PR head (any seat); the step builds its scratch product.
  steps:
    1. Run `D=$(mktemp -d) && CCP_DEV=1 ./bin/ccp sandbox create "$D" >/dev/null 2>&1 && P="$D/product" && python3 -c 'import json, sys; p = sys.argv[1] + "/docs/delivery/plane.json"; c = json.load(open(p)); c["estimate"] = {"auto": False}; c["architect"].update(rules_max_lines=200, notes_due=2, max_new_tasks=3); c["task_log"] = {"dry_run": True}; c["docs"]["workers"] = 2; json.dump(c, open(p, "w"))' "$P" && env -u QUEUE_ROOT -u PROJECT_YAML CCP_DEV=1 ./bin/ccp --root "$P" upgrade status 2>/dev/null | grep -cE '"key": "(architect\.(rules_max_lines|notes_due|max_new_tasks)|task_log\.dry_run|docs\.workers)"'`.
  expect: prints `0`.
  dry run (`3539c23`): printed `5` (each of the five listed under the `plane.json keys` step, as a constant to delete), exit 0.
- id: `code-01`
  story: As a plane developer, the tests hold the five keys as settings with their old defaults, applied with no warning.
  setup: A checkout of the PR head, in your own worktree, with your open run (a delivery-verifier seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp suite run --lane part --summary -- python3 -B -m unittest tests.test_plane_json_constants.TheSettingsAgain.test_the_five_keys_are_settings_with_their_old_defaults tests.test_plane_json_constants.TheSettingsAgain.test_a_value_set_loads_with_no_warning_and_applies tests.test_plane_json_constants.TheConstants tests.test_doc_rules.ParallelChecks.test_a_number_set_caps_them_with_no_warning tests.test_doc_rules.ParallelChecks.test_an_explicit_null_loads_with_no_warning`.
  expect: exit 0.
  dry run (`3539c23`): exit 1, the run FAILED (`TheSettingsAgain` and the two renamed `ParallelChecks` tests do not exist yet).
- id: `doc-01`
  story: As a product's lead reading the contract, the five keys are settings, not deprecated constants, and ADR-0043 records the ruling.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `python3 -c 'import json; s = json.load(open("contracts/plane_config.schema.json"))["properties"]; ps = [s["architect"]["properties"][k] for k in ("rules_max_lines", "notes_due", "max_new_tasks")] + [s["task_log"]["properties"]["dry_run"], s["docs"]["properties"]["workers"]]; print([p.get("deprecated", False) or p["description"].startswith("Constant") for p in ps], [p["default"] for p in ps])'`.
    2. Run `grep -o 'a setting again, operator 2026-11-24' docs/adr/0043-opinionated-defaults-short-configuration.md | wc -l | tr -d ' '`.
  expect: step 1 prints `[False, False, False, False, False] [150, 3, 5, False, None]`; step 2 prints `5`.
  dry run (`3539c23`): step 1 printed `[True, True, True, True, True] [150, 3, 5, False, None]`; step 2 printed `0`.
- id: `spec-01`
  story: As the operator, the SPEC names the five keys as settings with their defaults.
  setup: A checkout of the PR head (any seat).
  steps:
    1. Run `CCP_DEV=1 ./bin/ccp verify spec-text 0337`.
  expect: exit 0, all eight PROPOSED passages found.
  dry run (`3539c23`, with this brief): exit 1, all eight passages `not found in the SPEC`.

## Implementation notes

- Registry: `dry_run`, `workers` and `rules_max_lines`, `notes_due`, `max_new_tasks` left `_CONSTANT_KEYS` (the
  `docs` entry went whole, as `workers` was its only key) and the `docs.workers` `replace(..., shown=...)` line went;
  the block defaults are untouched. `Outcome.shown` and `ccp/upgrade.py`'s `shown` branch stay for the binding
  constant.
- Schema: the five lose `deprecated` and read `Setting, default <v> (SPEC §<n>): …`, type, minimum and default kept.
- Tests: the five left `CONSTANTS` and `WAS` and joined `KEPT`; `TheSettingsAgain` added; the `docs.workers`
  in-words upgrade test deleted; the two `ParallelChecks` tests renamed and re-expected (no `docs.workers` and no
  `is a constant in code` on stderr).
- ADR-0043: the appendix's kept entries carry a short default where the kept list's style gives one (`task_log.dry_run`
  default off, `docs.workers` as many as there are checks); D9 stays `not_built` (0191 marks it).
- Ruling r1 (lead, 2026-11-25): the `adr_refs: ["0043 D9"]` field is removed from the front matter, as 0192 did,
  because adr.strict refuses approving a head whose cited decision is still `not_built` and D9 stays `not_built`
  until 0191; the task's authority is the operator's 2026-11-24 ruling its Context quotes. Nothing else changed.

## Verification notes
- 2026-11-25 — verifier, PR #413 head `2b26d34` (squash `6cbbe7d`): APPROVE. Passed: cmd-01, cmd-02, code-01, doc-01, spec-01. Gate: `ccp suite run --lane gate` exit 0, `ccp tasks check` exit 0, `ccp docs check` exit 0. Record: verification/0337-five-constants-become-plane-json-settings-again.json.

