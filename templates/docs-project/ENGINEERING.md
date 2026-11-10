<!--
  Control-plane template for a product's house rules (SPEC §20.1). Copy it to the path in
  docs/delivery/plane.json `architect.rules_doc` (for example docs/ENGINEERING.md) and make it the
  product's own: it is product-owned, never a managed copy. Delete this comment and every
  placeholder rule you don't keep.

  The format `ccp docs check` reads:
  - a rule is a list item that opens with its id: `- **E<n>** <the rule>`;
  - the rule carries a `check:` line: `pass` (the architect judges it), `budget` (an
    `architect.budgets` entry with the same id; a breach makes an architect pass due, it never fails
    a verifier), `command` (an `architect.checks` entry with the same id, run by `ccp docs check`;
    exit 0 = pass) or `docs — <plane.json key>` (a rule `ccp docs check` runs, which must be set),
    optionally followed by ` — <what it measures>`;
  - at most `architect.rules_max_lines` lines (default 150), this comment included;
  - current only: no history, no dates, no "was X". Git holds the history.
  The architect proposes changes in its reports; the task-log owner applies or rejects them.
  For a ready set of generic rules with their checks, see starter-rules.md beside this file
  (`ccp init --starter-rules`, plane SPEC §20.5).
-->
# Engineering rules

The house rules of this product. Every implementer reads them before starting a task; every rule
says how it is checked. Changes come through the architect's `rule_changes` and the owner's triage.

## Architecture

The parts of the product, and which may depend on which.

- **E1** <part A> may import <part B>; <part B> never imports <part A>.
  check: command — <a product command that fails on a forbidden import>

## Single sources

For each concept that tends to be copied, the one place that owns it. Everything else derives from it.

- **E2** <concept, e.g. the list of roles> lives in <path>; docs and tests read it from there, never restate it.
  check: pass

## Tests

- **E3** A test checks behaviour, not wording: no assertion on prose, help text or prompt text.
  check: pass
- **E4** Fixtures build expensive state once per module, not once per test.
  check: pass
- **E5** The per-task gate runs <the suites that guard current code>; paused code's tests run only when <condition>.
  check: pass

## Docs

Which document holds what, which are current and which are history, and what is never restated.

- **E6** <SPEC, RUNBOOK, ...> are current-only; records of what a task did go in its task file.
  check: pass

## Budgets

- **E7** No source file over <n> lines.
  check: budget
- **E8** <a current doc> stays under <n> bytes.
  check: budget

## Known intentional

Deliberate oddities, so that passes don't raise them again. No ids: these are not rules.

- <the oddity> — <why it stays>.
