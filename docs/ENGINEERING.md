# Engineering rules

The control plane's house rules. Every change follows them; every rule says how it is checked. The
format is the one `ccp` reads (SPEC §20.1). The command rules run through `architect.checks` in
`docs/delivery/plane.json` (SPEC §19.11), except E1, which the verifier's gate (`scripts/gate.sh`) runs.

## Tests

- **E1** The full suite passes on every change: `scripts/gate.sh` (a plane worker runs it as
  `ccp suite run --lane full`), the same modules as `python3 -m unittest discover -s tests -t .`, run in
  parallel, with the test cache.
  check: pass — the verifier's gate runs the suite on every task (§15); an architect.checks entry would run the gate inside itself
- **E2** Tests are fenced: no live queue, no real plane or product repo, no GitHub, no launchd; no test
  leaves a `state/*` branch behind.
  check: command — scripts/gate.sh fails on a leftover `state/*` branch; fencing in tests/__init__.py
- **E4** A test checks behaviour, not wording: no assertion on prose, help text or prompt text beyond
  the token it pins. A test names a plane constant or shared fixture fact (the worktrees directory, a
  binding) through the code or a fixture helper, never as a copied literal. A fixture class other
  modules reuse holds no test methods; a class with tests is never imported into another module (it
  would run twice).
  check: pass — the architect counts long string-literal assertions and constants copied into tests
- **E15** Decision logic is separate from git, process and file I/O, so each branch is unit-tested on
  plain values. End-to-end tests cover the wiring, not every branch.
  check: pass — the architect looks for branches reachable only through a fixture repo; the health
  summary's slowest modules point at them
- **E21** A dod_check proves behaviour with the head's own tool: a check of a `ccp` command runs the
  checkout's `bin/ccp` (or `ccp wt exec … --`), never `ccp` on PATH, which is the released plane.
  Signed SPEC text is proved by `bin/ccp verify spec-text <task>`; a doc grep pins one token, never a
  sentence or a table row.
  check: pass — the architect and the reviewer read new tasks' dod_checks

## Publishing

- **E3** No managed product's names, ids, paths, data or rulings in tracked files, commit messages or
  PR titles. Rules are written generically, with knobs that have neutral defaults.
  check: command — scripts/leak-check.sh (architect.checks `E3`), patterns in a local denylist: `CCP_LEAK_DENYLIST`, else `leak-denylist.txt` in the bindings directory (`CCP_BINDINGS_DIR`, else beside the binding `ccp where` names)
- **E5** Telemetry and records carry numbers and ids only: never prompt, response, command or file
  content. The receiver keeps a field whitelist.
  check: pass

## Architecture

- **E6** The plane never parses a product's prose for a fact: the product declares it in
  `plane.json` or reports it as JSON. An action the plane needs from a product is a hook, never an
  instruction in prompt prose.
  check: pass
- **E7** Every queue write goes through `ccp` and records its own event; scripts only wrap `ccp` or Git.
  check: pass
- **E8** Headless children strip `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
  check: pass
- **E9** Readers accept every value a live queue may hold; writers emit only the current one. A
  renamed value stays as a deprecated alias in code and schema until the managed products have
  rewritten their data; then the alias is removed. A contract no code writes or reads is removed,
  not kept.
  check: pass — the architect lists contracts with no writer or reader
- **E12** One source per enumerated concept: a list of values (round phases, event types,
  plane.json's blocks, their keys and defaults, the roles and their default models) is defined once in
  code. Other code derives from it; one test compares every plane.json block's keys and defaults with
  contracts/plane_config.schema.json, and the agent definitions' models with the role table.
  check: command — the schema-defaults test, `python3 -B -m unittest -q tests.test_plane_config_defaults` (architect.checks `E12`); the gate (`ccp suite run --lane gate`) runs it too
- **E14** Git merge analysis (merge-tree, patch-id, remerge-diff) goes through one helper module; no
  other module calls those git subcommands.
  check: command — `git grep -n "merge-tree\|patch-id\|remerge-diff" -- ccp` lists only the helper
  module
- **E16** Only ccp/config.py reads plane.json. A hook or script that needs a setting asks `ccp` (JSON
  out) or imports ccp.config; it never reads the file and defaults a key itself.
  check: command — `! git grep -nE 'plane\.json"\)\.read_text' -- plugin scripts` (architect.checks
  `E16`)
- **E17** One module resolves and parses a product's binding; every other reader calls it.
  check: pass — the architect looks for binding regexes outside that module
- **E18** A language's facts (its doc conventions, test-output patterns, test command and import
  reading) live in its language pack (ccp/doclang). Core code names no language and no test runner.
  check: command — `! git grep -n unittest -- ccp ':(exclude)ccp/doclang'` (architect.checks
  `E18`)
- **E19** Only the PR-host module (ccp/prhost.py) reaches a PR host: a forge's CLI or API, or the
  local PR record. Other code sees a PR as the normalised facts it returns (number, state, head,
  branch, merge commit, merge time, body), never a host's field names; prompts and briefs name
  `ccp pr`, never a forge's CLI.
  check: pass — the architect reads the PR-host callers and the prompts; it becomes a command check
  (architect.checks `E19`: `! git grep -nE 'CCP_GH_BIN|headRefOid|mergeCommit' -- ccp ':(exclude)ccp/prhost.py'`
  and `! git grep -n 'gh pr' -- templates plugin/agents`) with the task that moves the prompts
- **E20** One function judges whether a verdict lets a head merge: `ccp verify merge-ok`, `ccp verify
  check` and `ccp tasks close` call it, and `ccp verify record` refuses every approve it would refuse.
  check: pass — the architect compares the refusal lists of the merge-time judges
- **E22** One parser per durable grammar: a task file's dod_checks are split and read by one tasklog
  function; no other module matches `CHECK_RE` or re-splits the section.
  check: pass — the architect looks for check-grammar readers outside tasklog; it becomes a command
  check (architect.checks `E22`: `! git grep -n CHECK_RE -- ccp ':(exclude)ccp/tasklog.py'`) once
  the parser is in
- **E23** One parser per reference form: an ADR-decision link (`<ADR id>[ Dn]`, as `adr_refs`,
  `requires` and `retired by` write it) and a task-id reference are parsed by ccp/refs.py; no other
  module holds a regex for either.
  check: pass — the architect looks for ADR-link and task-id regexes outside ccp/refs.py, the known
  intentional ones below excepted

## Docs

- **E10** The SPEC is normative and current: a rule and its knob, stated as behaviour. A default's
  value lives in code and the schema (E12), not in SPEC text. Rationale lives in ADRs (docs/adr),
  history in Git. A § rule change needs the operator's approval (SPEC §31).
  check: pass
- **E11** Durable knowledge from a change lands in the SPEC, the docs or an ADR in the same PR.
  check: pass
- **E13** Briefs and prompt templates name the command and the § that decides; they never restate a
  rule's conditions, a tool's quirk a `ccp` command can absorb, or a sample record (a sample lives in
  contracts/ as `*.example.json`, and a test runs it through the command). The report's lines and
  sections are given once, in the rendered prompt's last part, from the parser's own table. The
  command's refusal names the condition that failed.
  check: pass — the architect compares plugin/agents and templates/prompts with the § rules they cite,
  ccp/report.py's sections, and looks for inline sample records
- **E24** A module docstring names the § it implements and what the module is for; it never lists the
  keys, checks or formats the code or the SPEC holds.
  check: pass — the architect compares module docstrings with the constants and § they would restate

## Known intentional

- Line grammars that are not references stay with their reader (E23): ccp/health.py's squash-subject
  pattern `^Task (\d{width}): `, and ccp/adr.py's `DECISION_RE` (a decision's state line),
  `_MARK_PARTS` and `_HEAD_PARTS` (a decision's mark and heading in an ADR's body).

- The gate's test cache keys every module on all the inputs it shares (every tracked and untracked
  file but the test modules no other imports), not on what it imports: one source edit reruns every
  module (scripts/gate_parallel.py).
