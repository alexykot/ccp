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
- **E4** A test checks behaviour, not wording: no assertion on prose, help text or prompt text beyond the token it
  pins. A test names a plane constant or shared fixture fact (the worktrees directory, a binding) through the code or
  a fixture helper, never as a copied literal. A fixture or helper other modules reuse lives in a module that holds no
  tests; no module imports a test module or binds another module's test-class methods.
  check: command — architect.checks `E4`: greps and scripts/house_checks.py `e4-imports`, each printing its hits, and its
  `e4-count` of assert calls with a string argument of 40+ characters (plain, f-string or concatenated), naming count and figure when over
- **E15** Decision logic is separate from git, process and file I/O, so each branch is unit-tested on
  plain values. End-to-end tests cover the wiring, not every branch: a change that gives a branch a
  plain-value test cuts that branch's end-to-end test in the same change.
  check: pass — the architect looks for branches reachable only through a fixture repo, and for refusals
  tested both on plain values and end to end; the health summary's slowest modules point at them
- **E21** A dod_check proves behaviour with the head's own tool: a check of a `ccp` command runs the checkout's
  `bin/ccp` (or `ccp wt exec … --`), never `ccp` on PATH, which is the released plane. A check that runs tests runs
  them through `bin/ccp suite run --lane <part lane> -- <command>` and pins a named test by giving its id to that
  command, so the run's exit code decides, never by a grep of the runner's text or a bare test runner's output. A
  check that needs a modified copy (a planted fault) names `ccp mutate` where it can run one test (§20.6), else a
  `ccp wt create --kind mut` worktree, never a hand `git worktree add`. Signed SPEC text is proved by
  `bin/ccp verify spec-text <task>`; a doc grep pins one token, never a sentence or a table row. A check that needs a
  scratch product builds it with `bin/ccp sandbox create` in the step that uses it and runs `ccp` there, with no `<…>`
  placeholder but the verifier's `<your run>`.
  check: pass — the architect and the reviewer read new tasks' dod_checks

## Publishing

- **E3** No managed product's names, ids, paths, data or rulings in tracked files, commit messages or
  PR titles. Rules are written generically, with knobs that have neutral defaults.
  check: command — scripts/leak-check.sh (architect.checks `E3`), patterns in a local denylist: `CCP_LEAK_DENYLIST`, else `leak-denylist.txt` in the bindings directory (`CCP_BINDINGS_DIR`, else beside the binding `ccp where` names)
- **E5** Telemetry carries numbers and ids only: never prompt, response, command or file content, and the receiver keeps
  a field whitelist. A queue record may hold a worker's own short statement lines (friction, follow-ups, a proposal's
  need), each refused when it looks like a secret; such text never goes to the telemetry receiver.
  check: pass — the architect looks for text fields on queue records without a secret refusal, and for
  text in the receiver's whitelist

## Architecture

- **E6** The plane never parses a product's prose for a fact: the product declares it in `plane.json` or reports it as
  JSON. An action the plane needs from a product is a hook, never an instruction in prompt prose.
  check: pass
- **E7** Every queue write goes through `ccp` and records its own event. A script a seat or product calls only wraps
  `ccp` or Git; a plane-development script (the gate's, the house checks') may hold its own program and writes no queue
  state.
  check: pass — the architect lists the scripts/ files that write the queue or that a seat calls, and compares them with ccp
- **E8** Headless children strip `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
  check: pass
- **E9** Readers accept every value a live queue may hold; writers emit only the current one. A renamed value stays as
  a deprecated alias in code and schema until the managed products have rewritten their data; then the alias is
  removed. A contract no code writes or reads is removed, not kept.
  check: pass — the architect lists contracts with no writer or reader
- **E27** A seat's actor id (the lead's, the runner's, the verifier's) is named once, in the seat table, and code and tests
  read it by name. A command the SPEC gives to one seat refuses, through one shared guard, every ACTOR that does not name
  that seat (unset or unknown included), and a reader counts only that seat's records.
  check: command — architect.checks `E27`; pass for the guard (the architect compares the commands the SPEC gives one seat)
- **E12** One source per enumerated concept: a list of values (round phases, event types and ops, plane.json's blocks,
  their keys and defaults, the roles and their default models) is defined once in code. Other code derives from it.
  One test compares every plane.json block's keys and defaults with contracts/plane_config.schema.json, one compares
  the ledger's event types, ops and required payloads with contracts/observability_event.schema.json, and one compares
  the agent definitions' models with the role table.
  check: pass, plus the gate — tests.test_plane_config_defaults and tests.test_event_registry run in
  the gate (E1); no architect.checks entry, so the pre-gate never renders a bare test run
- **E14** Git merge analysis (merge-tree, patch-id, remerge-diff) goes through one helper module; no
  other module calls those git subcommands.
  check: command — architect.checks `E14`
- **E16** Only ccp/config.py reads plane.json. A hook, script, shared library or ccp module that
  needs a setting asks `ccp` (JSON out) or takes it from ccp.config's loaded Config; it never opens
  the file, by literal name or by `CONFIG_REL`, and never defaults a key itself. A command that
  records into plane.json edits its text through ccp/jsonedit.py.
  check: command — architect.checks `E16`
- **E17** One module, scripts/observability/lib.py, resolves and parses a product's binding; every other reader calls it.
  check: command — architect.checks `E17` (the parser); pass — the architect looks for binding paths resolved outside lib.py
- **E18** A language's facts (its doc conventions, test-output patterns including the line that says the code did
  not build or import, the command that runs named tests or one test, and import reading) live in its language
  pack (ccp/doclang); plane.json may override them. Core code names no language and no test runner.
  check: command — architect.checks `E18`
- **E19** Only the PR-host module (ccp/prhost.py) reaches a PR host: a forge's CLI or API, its ref layout (refs/pull/…),
  or the local PR record. Other code sees a PR as the normalised facts it returns (number, state, head, branch, merge
  commit, merge time, body), never a host's field names; prompts and briefs name `ccp pr`, never a forge's CLI.
  check: command — architect.checks `E19`
- **E20** One function judges whether a verdict lets a head merge: `ccp verify merge-ok`, `ccp verify
  check` and `ccp tasks close` call it, and `ccp verify record` refuses every approve it would refuse.
  check: pass — the architect compares the refusal lists of the merge-time judges
- **E22** One parser per durable grammar: one tasklog function finds a task file's sections, one splits its
  dod_checks; no other module matches a task file's `## ` heading or `CHECK_RE`, or re-splits a section.
  check: command — architect.checks `E22`
- **E23** One parser per reference form: an ADR-decision link (`<ADR id>[ Dn]`, as `adr_refs`,
  `requires` and `retired by` write it), a task-id reference and a task merge's subject (§10.7 rule 1)
  are parsed by ccp/refs.py; no other module in ccp or scripts holds a regex for any of them.
  check: command — architect.checks `E23`
- **E25** The parser is the one source of the command surface. Call syntax is written by hand in one place (docs/cli),
  held to the parser by a test: a row gives the syntax, who calls it, at most one clause of purpose and the §, never
  the SPEC's rules or exit codes; no module docstring in ccp/ carries a usage table.
  check: command — architect.checks `E25` (no docs/cli command row over 300 bytes, none naming an exit code); plus the gate — tests.test_cli_reference (E1)

## Docs

- **E10** The SPEC is normative and current: a rule and its knob, stated as behaviour. A default's
  value lives in code and the schema (E12), not in SPEC text. Rationale lives in ADRs (docs/adr),
  history in Git. A § rule change needs the operator's approval (SPEC §31).
  check: pass
- **E11** Durable knowledge from a change lands in the SPEC, the docs or an ADR in the same PR.
  check: pass
- **E26** A house rule is stated once, in this doc. The standing DoD and the package docs name its id; they never
  restate its text, a prohibition included. The root CLAUDE.md, the session's own instructions, is exempt.
  check: pass — the architect greps each package doc for a rule's distinctive clause (`git grep -n 'only wrap\|imports another\|copied literal\|names no language' -- '*/CLAUDE.md'`)
- **E13** Briefs and prompt templates name the command and the § that decides; they never restate a rule's conditions,
  a tool's quirk a `ccp` command can absorb, or a sample record (a sample lives in contracts/ as `*.example.json`, and
  a test runs it through the command). The report's lines and sections are given once, in the rendered prompt's last
  part, from the parser's own table. An instruction several phases share is written once, in `_common.md` or a shared
  part, and template text is one sentence per line. The command's refusal names the condition that failed.
  check: pass, plus command — architect.checks `E13`: `awk 'length > 600' templates/prompts/*.md` prints nothing, a
  proxy for one sentence per line, not a rule of its own; the architect compares plugin/agents and templates/prompts
  with the § rules they cite, ccp/report.py's sections, and looks for inline sample records and sentences repeated
  across templates
- **E24** A module docstring names the § it implements and what the module is for; it never lists the
  keys, checks, refusals, exit codes or formats the code or the SPEC holds.
  check: pass, plus command — architect.checks `E24`: scripts/house_checks.py `e24`, the counts of ccp module docstrings
  over 30 lines and stating an exit code, each at or below its figure (named when over); the architect compares the rest with their §

## Known intentional

- Line grammars that are not references stay with their reader (E23): ccp/adr.py's `DECISION_RE` (a decision's
  state line) and `_DEC_HEAD` and `_DEC_MARK` (the line grammar of a decision's heading and mark; its other decision
  patterns derive from them).
- The gate's test cache keys every module on all the inputs it shares (every tracked and untracked file but the
  test modules), not on what it imports: one source edit reruns every module (scripts/gate_parallel.py).
- Health's before-review conflict catch-up figures (`ccp/health.py` `conflict_catch_ups`) are the
  whole implement or fix rounds' wall time and tokens, as §27.1 says and the text line labels them:
  no round records a merge step's own cost (ar-20261121T174754Z-7df5 F12).
- The architect's prompt lists every friction note since the last pass, the runner's `allow-overdue` override
  rows included (§19.6: all the notes go to the pass); only the due trigger leaves overrides out (ar-20261123T230912Z-197a F09).
- Close's overlap refusal keeps its end-to-end test: it alone kills a mutant that drops the tip's files from the catch-up's (b) call (E15; ar-20261124T034246Z-e089 F11).
- Dry-run's placeholder pattern also lists a redirection such as `sort <in >out` or `<<EOF >f` as not run: safe, as it runs nothing (0320; ar-20261124T034246Z-e089).
- The worker definitions state §13.1's four generic rules, the evidence rule among them, which `_common.md` also gives as rendered commands: §13.1 puts them in the definitions (ar-20261124T205520Z-4ce8 F04).
