# Engineering rules

The control plane's house rules. Every change follows them; every rule says how it is checked. The
format is the one `ccp` reads (SPEC §20.1). Until the architect block is enabled, the command rules
run through `docs.checks` and the gate (`scripts/gate.sh`) rather than `architect.checks`.

## Tests

- **E1** The full suite passes on every change: `python3 -m unittest discover -s tests -t .`.
  check: command — `ccp suite run --lane gate` (scripts/gate.sh)
- **E2** Tests are fenced: no live queue, no real plane or product repo, no GitHub, no launchd; no test
  leaves a `state/*` branch behind.
  check: command — scripts/gate.sh fails on a leftover `state/*` branch; fencing in tests/__init__.py
- **E4** A test checks behaviour, not wording: no assertion on prose, help text or prompt text beyond
  the token it pins.
  check: pass

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

## Docs

- **E10** The SPEC is normative and current: a rule, its knob and its default. Rationale lives in
  ADRs (docs/adr), history in Git. A § rule change needs the operator's approval (SPEC §31).
  check: pass
- **E11** Durable knowledge from a change lands in the SPEC, the docs or an ADR in the same PR.
  check: pass

## Known intentional

- The suite has no per-module cache: it is fast enough to run whole.
