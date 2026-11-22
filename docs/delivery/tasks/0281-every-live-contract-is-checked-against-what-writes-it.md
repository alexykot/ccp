---
task_id: 0281-every-live-contract-is-checked-against-what-writes-it
title: Every live contract is checked against the record its writer writes, and the schema checker knows every keyword the contracts use
status: pending
kind: refactor
depends_on: ["0279-contract-writer-tests-for-the-answer-file-and-wt-up-down"]
clashes_with: ["0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events"]
rule_refs: ["E9", "E12"]
review_point: R24
paths: ["ccp/schema.py", "contracts/task_file.example.md", "contracts/CLAUDE.md", "tests/test_contract_writers.py"]
adopt: "none"
created: 2026-11-22
updated: 2026-11-22
---

# Task: 0281-every-live-contract-is-checked-against-what-writes-it

## Intent

A change to `plane.json`, a binding, the machine file, a local PR record, a prompt audit, a ledger event, an
ADR's frontmatter, the architect's report, the gate result or a task file's frontmatter fails a test when the
record and its contract stop agreeing, as it already does for the queue records task 0263 covered. No contract
uses a keyword the schema checker cannot check, so no part of a schema passes by being skipped.

## Context (not checked)

Measured at `5fc9cb9` (origin/main, after 0279 merged). Lines that name `b4af31e` were measured there first; the counts that 0279 changed are re-measured below, and the mutant anchors still occur once each at `5fc9cb9`. The class names this task adds do not exist in `tests/test_contract_writers.py` at `5fc9cb9`. This
task covers these open worker follow-ups (`ccp tasks follow-ups --open`):
- `0263-…/implement#1`: "`plane_config.schema.json`, `project.schema.json`, `task_file.schema.json`,
  `adr.schema.json` and the others are still validated by nothing through this checker";
- `0279-contract-writer-tests-for-the-answer-file-and-wt-up-down/implement#1` and `…/verify#1`: both say
  0263 `implement#1` stays open for the ten remaining contracts.

**The ten contracts.** `ls contracts/*.schema.json | wc -l` at `5fc9cb9`: 21 (23 at `b4af31e`; 0279
removed `architecture_review` and `result`).
`git grep -ho '[a-z_]*\.schema\.json' $(git grep -l schema_errors -- tests) | sort -u` at `5fc9cb9`: 12
names (0279 added `question_answer`), and `project.schema.json` among them is read only for an enum
(`tests/test_verify.py`). That leaves these ten (same commands): `adr`, `architect_report`, `machine`, `observability_event`, `plane_config`,
`pr_record`, `project`, `prompt_audit`, `suite_result`, `task_file`. This is the list task 0279 measured at `254bb64`.

**The checker cannot read three of them today.** `"def schema_errors"` in `ccp/schema.py` fails closed on
a keyword outside `_ANNOTATIONS` and `_KEYWORDS`, and only for the part of the schema a record reaches.
`git grep -cE '"(\$defs|\$ref|maxItems|uniqueItems|maximum|exclusiveMinimum|propertyNames|deprecated)"' -- 'contracts/*.schema.json'` at `5fc9cb9`: 5 files (6 at `b4af31e`, with `architecture_review`):
- `adr` uses `$defs` and `$ref`;
- `architect_report` uses `maxItems` and `uniqueItems`;
- `machine` uses `maximum` and `exclusiveMinimum`;
- `plane_config` uses `deprecated`, `exclusiveMinimum`, `maximum`, `propertyNames` and `uniqueItems`;
- `project` uses `deprecated`.

A walk over the schema positions found the same keywords, file for file. Behaviour outside the tests does
not change. `git grep -n schema_errors -- ccp scripts` at `b4af31e`: `ccp/verify.py` is the one caller outside
`ccp/schema.py`, and it reads `verification.schema.json`, which the grep above does not name.

**Probes at `b4af31e`** (scratch copies, writers run as each ruling below says, each record run through
`schema_errors`):
- `ccp sandbox create -- --project-id demo --language python`: `plane.json`, the binding (through
  `lib.read_binding`) and `machine.json` each gave `[]`.
- The local PR host fixture (`tests/test_prhost_local.py`, `LocalHost`: claim 0002, push, `ccp pr open`,
  `ccp prompt implement 0002 --base abc1234`): the PR record, the prompt audit and all 5 lines of
  `observability/events.jsonl` gave `[]`.
- `adr.new` on that fixture gave `record: the schema uses $defs, which ccp verify cannot check`. With the
  probe's prototype of `$defs` and `$ref` in the checker it gave `[]`. The last three ADRs in `docs/adr/` gave
  `[]` too.
- `ccp architect run --force` on `tests/test_architect.py`'s `Harness` (stub report `[FINDING]` plus one rule
  change), the written report: `findings: the schema uses maxItems …` and `lenses: the schema uses uniqueItems …`.
  With the prototype keywords it gave `[]`.
- `scripts/gate_result.py` on a log with two `gate module` lines, a `FAIL:` line and
  `FAILED (failures=1, skipped=1)`: `[]`.
- A neutral task file (the example ruled below) in a `tests.helpers.Product`: frontmatter `[]`, and
  `ccp tasks check` printed `tasks: clean (1 tasks)`, exit 0.
- With the prototype keywords in place, `python3 -B -m unittest tests.test_contract_writers tests.test_verify`: OK.
  `docs/delivery/plane.json` of this repo also gave `[]`.
- Each mutant named in the checks, applied in a scratch copy, made its record fail validation: the PR state
  `"open"`, a 12-character sha, `at` without its `T`, the binding without `integration_branch`, `telemetry`
  `false`, `schema_version` `2`, `seconds` `"7"`, and the ADR date `2026-11-22T00:00` (with the prototype). The
  `language.upper()` mutant made `ccp init` itself fail, so the sandbox printed nothing; that still fails the test.

**Grouping.** Ten contracts fit in five checks by fixture: `ccp init`, the local PR host, the reports, and the
frontmatter, plus the checker. One task, not two.

**Writers and readers** (contracts/CLAUDE.md: a record its writer writes, or an example its reader
accepts where a seat writes it):
- `ccp init` writes `plane.json`, the binding and `machine.json`;
- `ccp/prhost.py` writes the PR record, `scripts/observability/write-prompt-audit.sh` the prompt audit,
  and `lib.append_event` the ledger;
- `ccp adr new` writes an ADR's frontmatter, `ccp architect run` the architect's report, and
  `scripts/gate_result.py` this repo's gate result;
- the task file is the lead's (a seat writes it), so it gets an example that `ccp tasks check` accepts.

**No SPEC change.** `git grep -nE 'maxItems|uniqueItems|propertyNames|exclusiveMinimum|\$defs' -- SPEC.md docs/spec` at `b4af31e`: no match. The checker's keyword set is not a rule.

**0279's sentence.** 0279 (done, `5fc9cb9`) made contracts/CLAUDE.md's "Not yet checked: `question_answer`." read
"Not yet checked by a written record: `adr`, `architect_report`, `machine`, `observability_event`,
`plane_config`, `pr_record`, `project`, `prompt_audit`, `suite_result`, `task_file`." This task removes that
sentence, hence `depends_on`. Both edit `tests/test_contract_writers.py`.

**The clash with 0268** (pending, R21, signed). 0268 changes the local PR record's state words
(`"OPEN"` to `open`, in `ccp/prhost.py` and `contracts/pr_record.schema.json`) and makes each write of it
append a `pr` ledger event (`contracts/observability_event.schema.json`, `scripts/observability/lib.py`).
This task's `QueueRecordContracts` test validates exactly those records against those contracts, and its
mutants target `ccp/prhost.py` and `lib.append_event`. The two tasks change the same records in different
ways, so they run in either order, never together. The clash is set here only, because 0268's file is signed and
`clashes_with` is symmetric. `code-03`'s PR-record mutant anchors on `opened_at`, which 0268's brief leaves
alone (`git grep -n opened_at -- docs/delivery/tasks/0268-the-local-pr-record-keeps-the-plane-s-state-words-and-writes-ledger-events.md`
at `5fc9cb9`: no match). Whichever task merges second re-measures its anchors at its claim.

### Rulings for the build (the lead's)

- **The checker** (`ccp/schema.py`):
  - `deprecated` and `$defs` join `_ANNOTATIONS`. `$defs` is never judged itself.
  - `$ref` joins `_KEYWORDS`, for local refs only. `schema_errors` takes a keyword-only `root=None`, which
    defaults to the schema passed in, and every recursive call passes it on. A `$ref` of the form
    `#/$defs/<name>` is checked as `root["$defs"][<name>]`, along with the `$ref`'s sibling keywords. Any other
    `$ref`, or a name `$defs` lacks, is an error ending in `_UNCHECKABLE`'s text.
  - `maxItems`: at most that many items. `uniqueItems: true`: no two items equal, compared as `const`
    compares (value and `_kind`). `maximum`: a number at most that. `exclusiveMinimum`: a number above that.
    `propertyNames`: each key of an object holds the sub-schema, reported at `<at>.<key>`.
  - The module docstring stays true; nothing else in `ccp/` changes.
- **Tests** go in `tests/test_contract_writers.py`. They import fixture classes, which hold no tests
  (`tests.test_architect.Harness`, `tests.test_toolkit.ToolkitFixture`), and helper functions. They never
  import a TestCase class that has tests of its own (such as `tests.test_prhost_local.LocalHost`), because an
  imported test class runs again in this module.
  - `Checker`:
    - `test_defs_and_a_local_ref` (also a non-local ref, which gives the uncheckable error);
    - `test_max_items_and_unique_items`;
    - `test_maximum_and_exclusive_minimum`;
    - `test_property_names_holds_each_key`;
    - `test_deprecated_only_describes`;
    - `test_every_contract_uses_only_keywords_the_checker_knows`: walks each `contracts/*.schema.json` over
      the values of `properties` and `$defs`, the sub-schemas of `items`, `additionalProperties` and
      `propertyNames`, `not`, `if` and `then`, and each of `allOf`, `anyOf` and `oneOf`. It asserts that no
      file uses a key outside the checker's two sets, naming the file and key when one does.
  - `InitContracts.test_the_plane_json_binding_and_machine_file_ccp_init_writes_validate`: run
    `bin/ccp sandbox create -- --project-id demo --language python` as a subprocess (under the fence's
    `CCP_SANDBOX_ROOT`). Validate `docs/delivery/plane.json` against `plane_config`, the binding (through
    `queue.lib.read_binding`) against `project`, and `machine.json` beside the binding against `machine`. Then
    `ccp sandbox remove` the root.
  - `QueueRecordContracts.test_the_pr_record_prompt_audit_and_events_a_claimed_task_writes_validate`, on
    `ToolkitFixture` with `CCP_GH_BIN` pointed at a missing file, as `LocalHost.setUp` does. Claim 0002,
    commit and push on its branch, then `ccp pr open`, and validate `prs/1.json` against `pr_record`. Run
    `ccp prompt implement 0002 --base abc1234` and validate the audit `prompt_ref` names against
    `prompt_audit`. Then validate every line of `observability/events.jsonl` against `observability_event`.
  - `ReportContracts(Harness).test_the_report_ccp_architect_run_writes_validates`: stub report `[FINDING]` with
    one rule change (as `RuleChangesAndShape` writes one), `ccp architect run --force`, outcome `reported`. The
    file `report` names validates against `architect_report`.
  - `GateResultContract.test_the_result_gate_result_py_writes_validates`: `scripts/gate_result.py` on a log
    with two `gate module` lines (one `ok`, one `cached`), one `FAIL:` line and a `FAILED` summary. Its JSON
    validates against `suite_result`.
  - `FrontmatterContracts.test_the_frontmatter_ccp_adr_new_writes_validates`: `ccp adr new "A decision"` in a
    `tests.helpers.Product`. The frontmatter, through `adr.parse` of the block between the first two `---`
    lines, validates against `adr`.
  - `Examples.test_the_task_file_example_validates_and_ccp_tasks_check_accepts_it`: the example's frontmatter
    (`tasklog.frontmatter`) validates against `task_file`. Copied to `docs/delivery/tasks/<task_id>.md` of a
    `tests.helpers.Product`, with the index written, `ccp tasks check` exits 0.
- **`contracts/task_file.example.md`** (new): a complete pending task. Its frontmatter: `task_id:
  0001-an-example-task`, a title, `status: pending`, `kind: feature`, `depends_on: []`, `spec_refs: ["S5"]`,
  `paths` naming two neutral files, `adopt: "none"`, and `created` and `updated` dates. Then the six sections,
  with one `cmd-01` check whose dry run is `n/a`. Neutral values only. The text `status: pending` occurs once in it. A task file is Markdown, so its example
  is `.md`.
- **contracts/CLAUDE.md**:
  - "a `<name>.example.json` its reader accepts" becomes "a `<name>.example.json` (for the task file,
    `task_file.example.md`) its reader accepts";
  - 0279's "Not yet checked by a written record: …" sentence is removed;
  - "The checker fails closed on a keyword it does not know, so a schema that needs a new one extends it."
    gains: "; a test holds every schema to the keywords it knows".

## Scope

- **In:** `ccp/schema.py` (the keywords and `root`); `contracts/task_file.example.md` (new);
  `contracts/CLAUDE.md` (the three edits); `tests/test_contract_writers.py` (the tests listed).
- **Out:** every writer named in Context (no writer changes); the schemas' text; the run record and
  `_suites.jsonl` (no contract by design); the SPEC.

## dod_checks

- id: `code-01`
  story: As a plane developer, no contract uses a keyword the checker cannot check, and each keyword the contracts use holds a value to it.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for step 2.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.Checker`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.Checker --revert ccp/schema.py`.
  expect: step 1 exits 0 and lists the six tests the ruling names under `Checker` as `ok`; step 2 prints the mutant `killed` (with `ccp/schema.py` at the merge base, the walk names the six files of Context's grep less any 0279 removed, and the keyword tests fail).
  dry run: n/a — the tests are new. The keyword grep in Context found 6 files at `b4af31e`.
- id: `code-02`
  story: As a plane developer, a change to what `ccp init` writes that breaks plane.json's, the binding's or the machine file's contract fails a test.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for steps 2 to 4.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.InitContracts`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.InitContracts --mutant 'ccp/init.py:f"integration_branch: {branch}\n"=>""'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.InitContracts --mutant 'ccp/init.py:"telemetry": value}=>"telemetry": value == "on"}'`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.InitContracts --mutant 'ccp/init.py:{"language": language} if language=>{"language": language.upper()} if language'`.
  expect: step 1 exits 0 with `test_the_plane_json_binding_and_machine_file_ccp_init_writes_validate` `ok`; steps 2, 3 and 4 each print the mutant `killed`.
  dry run (`b4af31e`): each mutant's old text occurs once in `ccp/init.py`. In the scratch probe the first gave `record: missing integration_branch` and the second `record.telemetry: false is not one of on, off`; under the third, `ccp init` failed (Context). Step 1 n/a — the test is new.
- id: `code-03`
  story: As a plane developer, a change to the local PR record, the prompt audit or a ledger event that breaks its contract fails a test.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for steps 2 to 4.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.QueueRecordContracts`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.QueueRecordContracts --mutant 'ccp/prhost.py:"opened_at": iso(), "merged_at": None,=>"opened_at": None, "merged_at": None,'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.QueueRecordContracts --mutant 'scripts/observability/write-prompt-audit.sh:"prompt_sha256": digest,=>"prompt_sha256": digest[:12],'`.
    4. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.QueueRecordContracts --mutant 'scripts/observability/lib.py:"at": ev["at"],=>"at": ev["at"].replace("T", " "),'`.
  expect: step 1 exits 0 with `test_the_pr_record_prompt_audit_and_events_a_claimed_task_writes_validate` `ok`; steps 2, 3 and 4 each print the mutant `killed`.
  dry run (`b4af31e`): each old text occurs once in its file. A PR record with `opened_at` null gave `record.opened_at: null is not string` (at `5fc9cb9`); in the scratch probe the other two mutants gave `record.prompt_sha256: … does not match ^[a-f0-9]{64}$` and `record.at: … is not an RFC 3339 date-time` on every event. If 0268 merges first, re-measure the three anchors at the claim. Step 1 n/a — the test is new.
- id: `code-04`
  story: As a plane developer, a change to the architect's report or the gate result that breaks its contract fails a test.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for steps 2 and 3.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.ReportContracts tests.test_contract_writers.GateResultContract`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.ReportContracts --mutant 'ccp/architect.py:report.update({"schema_version": 1,=>report.update({"schema_version": 2,'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.GateResultContract --mutant 'scripts/gate_result.py:"seconds": int(sys.argv[2])}=>"seconds": str(sys.argv[2])}'`.
  expect: step 1 exits 0 with `test_the_report_ccp_architect_run_writes_validates` and `test_the_result_gate_result_py_writes_validates` `ok`; steps 2 and 3 each print the mutant `killed`.
  dry run (`b4af31e`): each old text occurs once in its file. In the scratch probe the mutants gave `record.schema_version: 2 is not 1` and `record.seconds: "7" is not number`. Step 1 n/a — the tests are new.
- id: `code-05`
  story: As a plane developer, an ADR's frontmatter as `ccp adr new` writes it, and a task file as the lead writes it, each match their contract.
  setup: A checkout of the PR head, any seat with QUEUE_ROOT for steps 2 and 3.
  steps:
    1. Run `python3 -B -m unittest -v tests.test_contract_writers.FrontmatterContracts tests.test_contract_writers.Examples`.
    2. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.FrontmatterContracts --mutant 'ccp/adr.py:date: "{date}"=>date: "{date}T00:00"'`.
    3. Run `CCP_DEV=1 ./bin/ccp mutate --run <your run> --test tests.test_contract_writers.Examples.test_the_task_file_example_validates_and_ccp_tasks_check_accepts_it --mutant 'contracts/task_file.example.md:status: pending=>status: claimed'`.
  expect: step 1 exits 0 with `test_the_frontmatter_ccp_adr_new_writes_validates` and `test_the_task_file_example_validates_and_ccp_tasks_check_accepts_it` `ok`; steps 2 and 3 each print the mutant `killed`.
  dry run (`b4af31e`): step 2's old text occurs once in `ccp/adr.py`; with the prototype checker the mutant gave `record.date: '2026-11-22T00:00' does not match …`. Steps 1 and 3 n/a — the test and the example are new.
- id: `doc-01`
  story: As a plane developer, contracts/CLAUDE.md lists no contract as unchecked and names the task file's example.
  setup: A checkout of the PR head.
  steps:
    1. Run `git grep -n 'Not yet checked' -- contracts/CLAUDE.md`.
    2. Run `git grep -n 'task_file.example.md' -- contracts/CLAUDE.md`.
  expect: step 1 prints nothing (exit 1); step 2 prints exactly one line.
  dry run (`5fc9cb9`): step 1 printed 1 line (`contracts/CLAUDE.md:11`, 0279's sentence); step 2 printed nothing (exit 1).

## Implementation notes

- Premises re-run at `245528cb`: 21 schema files; 12 names validated through the checker (`project` for an enum only);
  the keyword grep found the same 5 files; `ccp/verify.py` is still the one outside caller; no SPEC match for the
  new keywords. The figures hold.
- `ccp/schema.py`: `deprecated` and `$defs` in `_ANNOTATIONS`; `$ref`, `maxItems`, `uniqueItems`, `maximum`,
  `exclusiveMinimum` and `propertyNames` in `_KEYWORDS`. `schema_errors` takes keyword-only `root`; `_ref` (new)
  resolves `#/$defs/<name>` in it, and `_combined` passes it on. Messages the task leaves open: `items are not unique`,
  `more than N item(s)`, `V is above N`, `V is not above N`, and for a `$ref` the checker cannot follow
  `the schema's $ref "<ref>" is not a local #/$defs/<name>, which ccp verify cannot check`.
- `uniqueItems` compares two items equal when `==` and `_kind` agree (a shallow compare: a nested `[1]` and `[true]`
  would count as equal).
- `maximum` and `exclusiveMinimum` judge a number only (a boolean is not one), as `minimum` already did.
- `tests.test_contract_writers`: `Checker` (six tests), `InitContracts`, `QueueRecordContracts(ToolkitFixture)`,
  `ReportContracts(Harness)`, `GateResultContract`, `FrontmatterContracts`, and the task-file test in `Examples`.
- `contracts/task_file.example.md` is new; `contracts/CLAUDE.md` has the three edits.
- `ccp sandbox create` prints `root` as the product directory; the sandbox is its parent, which `sandbox remove` takes.

## Verification notes
