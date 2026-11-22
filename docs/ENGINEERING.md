# Engineering rules

The control plane's house rules. Every change follows them; every rule says how it is checked. The
format is the one `ccp` reads (SPEC §20.1). The command rules run through `architect.checks` in
`docs/delivery/plane.json` (SPEC §19.11), except E1, which the verifier's gate (`scripts/gate.sh`) runs.

## Tests

- **E1** The full suite passes on every change: `scripts/gate.sh` (a plane worker runs it through
  `ccp suite run` on the full role's lane), the same modules as `python3 -m unittest discover -s tests -t .`,
  run in parallel, with the test cache.
  check: pass — the verifier's gate runs the suite on every task (§15); an architect.checks entry would run the gate inside itself
- **E2** Tests are fenced: no live queue, no real plane or product repo, no forge (GitHub or other), no launchd;
  end-to-end tests use the local PR host; no test leaves a `state/*` branch behind.
  check: command — scripts/gate.sh fails on a leftover `state/*` branch; fencing in tests/__init__.py
- **E4** A test checks behaviour, not wording: no assertion on prose, help text or prompt text beyond
  the token it pins. A test names a plane constant or shared fixture fact (the worktrees directory, a
  binding) through the code or a fixture helper, never as a copied literal. A fixture class other
  modules reuse holds no test methods; a class with tests is never imported into another module, and no
  module binds another module's test-class methods as its own helpers.
  check: command — architect.checks `E4`: the borrowed-helper grep, the worktrees-literal grep, and the count of
  assertIn and assertNotIn lines on a long string literal in tests/*.py held at or below the figure in the
  command (lowered as tasks remove them)
- **E15** Decision logic is separate from git, process and file I/O, so each branch is unit-tested on
  plain values. End-to-end tests cover the wiring, not every branch.
  check: pass — the architect looks for branches reachable only through a fixture repo; the health
  summary's slowest modules point at them
- **E21** A dod_check proves behaviour with the head's own tool: a check of a `ccp` command runs the
  checkout's `bin/ccp` (or `ccp wt exec … --`), never `ccp` on PATH, which is the released plane. A
  check that needs a modified copy (a planted fault) names `ccp mutate`, or a `ccp wt create --kind mut`
  worktree, never a hand `git worktree add`. Signed SPEC text is proved by `bin/ccp verify spec-text
  <task>`; a doc grep pins one token, never a sentence or a table row.
  check: pass — the architect and the reviewer read new tasks' dod_checks

## Publishing

- **E3** No managed product's names, ids, paths, data or rulings in tracked files, commit messages or
  PR titles. Rules are written generically, with knobs that have neutral defaults.
  check: command — scripts/leak-check.sh (architect.checks `E3`), patterns in a local denylist: `CCP_LEAK_DENYLIST`, else `leak-denylist.txt` in the bindings directory (`CCP_BINDINGS_DIR`, else beside the binding `ccp where` names)
- **E5** Telemetry carries numbers and ids only: never prompt, response, command or file content, and
  the receiver keeps a field whitelist. A queue record may hold a worker's own short statement lines
  (friction, follow-ups, a proposal's need), each refused when it looks like a secret; such text never
  goes to the telemetry receiver.
  check: pass — the architect looks for text fields on queue records without a secret refusal, and for
  text in the receiver's whitelist

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
- **E27** A seat's actor id (the lead's, the runner's) is named once, in the seat table, and code reads it
  by name. A command the SPEC gives to one seat refuses another seat's ACTOR through one shared guard,
  and a reader counts only that seat's records.
  check: pass — the architect compares the lead's commands; it becomes also a command check with task
  0272 (architect.checks `E27`: `! git grep -n '"design-seat"' -- ccp scripts
  ':(exclude)ccp/board_page.html' ':(exclude)scripts/observability/lib.py'`)
- **E12** One source per enumerated concept: a list of values (round phases, event types and
  ops, plane.json's blocks, their keys and defaults, the roles and their default models) is defined
  once in code. Other code derives from it. One test compares every plane.json block's keys and
  defaults with contracts/plane_config.schema.json, one compares the ledger's event types, ops and
  required payloads with contracts/observability_event.schema.json, and one compares the agent
  definitions' models with the role table.
  check: pass, plus the gate — tests.test_plane_config_defaults and tests.test_event_registry run in
  the gate (E1); no architect.checks entry, so the pre-gate never renders a bare test run
- **E14** Git merge analysis (merge-tree, patch-id, remerge-diff) goes through one helper module; no
  other module calls those git subcommands.
  check: command — `git grep -n "merge-tree\|patch-id\|remerge-diff" -- ccp` lists only the helper
  module
- **E16** Only ccp/config.py reads plane.json. A hook, script, shared library or ccp module that
  needs a setting asks `ccp` (JSON out) or takes it from ccp.config's loaded Config; it never opens
  the file, by literal name or by `CONFIG_REL`, and never defaults a key itself. A command that
  records into plane.json edits its text through ccp/jsonedit.py.
  check: command — `! git grep -nE '(plane\.json"|CONFIG_REL)\)\.read_text' -- ccp plugin scripts ':(exclude)ccp/config.py'`
  (architect.checks `E16`)
- **E17** One module resolves and parses a product's binding; every other reader calls it.
  check: pass — the architect looks for binding regexes outside that module
- **E18** A language's facts (its doc conventions, test-output patterns, test command and import
  reading) live in its language pack (ccp/doclang). Core code names no language and no test runner.
  check: command — `! git grep -n unittest -- ccp ':(exclude)ccp/doclang'` (architect.checks
  `E18`)
- **E19** Only the PR-host module (ccp/prhost.py) reaches a PR host: a forge's CLI or API, its ref
  layout (refs/pull/…), or the local PR record. Other code sees a PR as the normalised facts it returns
  (number, state, head, branch, merge commit, merge time, body), never a host's field names; prompts
  and briefs name `ccp pr`, never a forge's CLI.
  check: command — architect.checks `E19`: `! git grep -nE 'CCP_GH_BIN|headRefOid|mergeCommit' -- ccp ':(exclude)ccp/prhost.py'`
  and `! git grep -n 'gh pr' -- templates plugin/agents`, then `! git grep -n 'refs/pull' -- ccp ':(exclude)ccp/prhost.py'`
  (added by task 0266)
- **E20** One function judges whether a verdict lets a head merge: `ccp verify merge-ok`, `ccp verify
  check` and `ccp tasks close` call it, and `ccp verify record` refuses every approve it would refuse.
  check: pass — the architect compares the refusal lists of the merge-time judges
- **E22** One parser per durable grammar: a task file's dod_checks are split and read by one tasklog
  function; no other module matches `CHECK_RE` or re-splits the section.
  check: command — architect.checks `E22`: `! git grep -n CHECK_RE -- ccp ':(exclude)ccp/tasklog.py'`
- **E23** One parser per reference form: an ADR-decision link (`<ADR id>[ Dn]`, as `adr_refs`,
  `requires` and `retired by` write it) and a task-id reference are parsed by ccp/refs.py; no other
  module holds a regex for either.
  check: pass — the architect looks for ADR-link and task-id regexes outside ccp/refs.py, the known
  intentional ones below excepted
- **E25** The parser is the one source of the command surface. Call syntax is written by hand in one
  place (docs/cli), held to the parser by a test; no module docstring in ccp/ carries a usage table.
  check: pass, plus the gate — tests.test_cli_reference checks the docs against the parser and every ccp
  module's docstring for usage lines; the gate runs it (E1); no architect.checks entry

## Docs

- **E10** The SPEC is normative and current: a rule and its knob, stated as behaviour. A default's
  value lives in code and the schema (E12), not in SPEC text. Rationale lives in ADRs (docs/adr),
  history in Git. A § rule change needs the operator's approval (SPEC §31).
  check: pass
- **E11** Durable knowledge from a change lands in the SPEC, the docs or an ADR in the same PR.
  check: pass
- **E26** A house rule is stated once, in this doc. The standing DoD and the package docs name its id;
  they never restate its text. The root CLAUDE.md, the session's own instructions, is exempt.
  check: pass — the architect looks for a rule's sentence outside this doc (`git grep -n 'short statement lines'`)
- **E13** Briefs and prompt templates name the command and the § that decides; they never restate a
  rule's conditions, a tool's quirk a `ccp` command can absorb, or a sample record (a sample lives in
  contracts/ as `*.example.json`, and a test runs it through the command). The report's lines and
  sections are given once, in the rendered prompt's last part, from the parser's own table. An
  instruction several phases share is written once, in `_common.md` or a shared part, and template
  text is one sentence per line. The command's refusal names the condition that failed.
  check: pass — the architect compares plugin/agents and templates/prompts with the § rules they cite,
  ccp/report.py's sections, and looks for inline sample records and sentences repeated across templates
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

- Health's before-review conflict catch-up figures (`ccp/health.py` `conflict_catch_ups`) are the
  whole implement or fix rounds' wall time and tokens, as §27.1 says and the text line labels them:
  no round records a merge step's own cost (ar-20261121T174754Z-7df5 F12).
