# Engineering rules

The control plane's house rules. Every change follows them; every rule says how it is checked. The
format is the one `ccp` reads (SPEC §20.1). Until the architect block is enabled, the command rules
run through `docs.checks` and the gate (`scripts/gate.sh`) rather than `architect.checks`.

## Tests

- **E1** The full suite passes on every change: `scripts/gate.sh` (a plane worker runs it as
  `ccp suite run --lane full`), the same modules as `python3 -m unittest discover -s tests -t .`, run in
  parallel, with the test cache.
  check: command — `ccp suite run --lane gate` (scripts/gate.sh)
- **E2** Tests are fenced: no live queue, no real plane or product repo, no GitHub, no launchd; no test
  leaves a `state/*` branch behind.
  check: command — scripts/gate.sh fails on a leftover `state/*` branch; fencing in tests/__init__.py
- **E4** A test checks behaviour, not wording: no assertion on prose, help text or prompt text beyond
  the token it pins. A fixture class other modules reuse holds no test methods; a class with tests
  is never imported into another module (it would run twice).
  check: pass
- **E15** Decision logic is separate from git, process and file I/O, so each branch is unit-tested on
  plain values. End-to-end tests cover the wiring, not every branch.
  check: pass — the architect looks for branches reachable only through a fixture repo; the health
  summary's slowest modules point at them

## Publishing

- **E3** No managed product's names, ids, paths, data or rulings in tracked files, commit messages or
  PR titles. Rules are written generically, with knobs that have neutral defaults.
  check: command — scripts/leak-check.sh (docs.checks `leak-check`), patterns in a local denylist
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
  rewritten their data; then the alias is removed (the role's old names went this way, task 0025).
  check: pass
- **E12** One source per enumerated concept: a list of values (round phases, event types, a
  plane.json block's keys and defaults) is defined once in code. Other code derives from it, and a
  test holds each schema enum or default to it.
  check: pass — the architect looks for literal copies; a test per schema compares its enum or
  defaults with the code constant
- **E14** Git merge analysis (merge-tree, patch-id, remerge-diff) goes through one helper module; no
  other module calls those git subcommands.
  check: command — `git grep -n "merge-tree\|patch-id\|remerge-diff" -- ccp` lists only the helper
  module

## Docs

- **E10** The SPEC is normative and current: a rule, its knob and its default. Rationale lives in
  ADRs (docs/adr), history in Git. A § rule change needs the operator's approval (SPEC §31).
  check: pass
- **E11** Durable knowledge from a change lands in the SPEC, the docs or an ADR in the same PR.
  check: pass
- **E13** Briefs and prompt templates name the command and the § that decides; they never restate a
  rule's conditions. The command's refusal names the condition that failed.
  check: pass — the architect compares plugin/agents and templates/prompts with the § rules they cite

## Known intentional

- The gate's test cache keys every module on all the inputs it shares (every tracked and untracked
  file but the test modules no other imports), not on what it imports: one source edit reruns every
  module (scripts/gate_parallel.py).
