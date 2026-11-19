---
task_id: 0184-init-turns-telemetry-on
title: ccp init tags the product's telemetry and, with the operator's consent once per machine, turns telemetry on
status: pending
kind: feature
depends_on: ["0175-one-binding-reader", "0181-models-block-and-role-defaults"]
spec_refs: ["S4", "S8", "S24"]
adr_refs: ["0043 D6"]
review_point: R12
paths: ["ccp/init.py", "ccp/cli.py", "ccp/otel.py", "ccp/board.py", "ccp/config.py", "scripts/observability/lib.py", "contracts/machine.schema.json", "contracts/plane_config.schema.json", "README.md", "docs/spec/01-model.md", "docs/spec/04-observability.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_init_telemetry.py"]
adopt: ".claude/settings.json env.OTEL_RESOURCE_ATTRIBUTES ccp.project_id=<project_id> (ccp init writes it when absent)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0184-init-turns-telemetry-on

## Intent

An operator adopting a product gets working telemetry without reading §24: `ccp init` tags the
product's sessions with its project id, and, once the operator consents for the machine (told plainly
that it covers every Claude Code session there), writes the user-level telemetry keys and installs the
receiver and the product's board timer. Prompt and tool-content logging stay off. An operator who
declines is not asked again on that machine, and delivery runs without telemetry. The receiver's port
is no longer a product setting.

## Context (not checked)

- ADR-0043 D6, accepted 2026-11-19.
- Depends on 0175 (one binding module, `scripts/observability/lib.py`, which also resolves the machine
  file this task adds) and 0181 (init's settings writer gains the lead's `model` there; this task adds
  the telemetry tag beside it, and edits the same §4.5 bullet after it).
- Today, at `e9ff0fc`: a fresh sandbox's `.claude/settings.json` holds no `env.OTEL_RESOURCE_ATTRIBUTES`
  (its `env` is `{"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}`); init never looks at the receiver or the
  user settings. `telemetry.otel_port` is read only by its own validation:
  `git grep -n 'otel_port' -- ccp scripts plugin` at `e9ff0fc`: 3 lines, all in `ccp/config.py`.
- D6 left to shaping whether a project directory can turn telemetry off locally. The shape did not
  check it. §24.1 already states that Claude Code ignores the enabling keys in a project's
  `.claude/settings.json`; the same keys set to off there are ignored the same way, so a directory
  cannot turn it off: the SPEC says so (below). An operator who needs a directory off launches its
  sessions with the keys unset in that shell, which the SPEC does not promise.
- Decided here:
  - The machine file is `machine.json` in the bindings directory (`lib.bindings_dir()`, so
    `CCP_BINDINGS_DIR` fences tests and sandboxes), contract `contracts/machine.schema.json` (new). Its
    name does not match the bindings' `*.yaml` glob. This task gives it one key, `telemetry`: `"on"` or
    `"off"`, the operator's consent; 0186 adds the account keys.
  - `ccp init --telemetry on|off` records the consent. With `on` (now or recorded earlier), init writes
    the user-level keys `ccp otel env` prints into `~/.claude/settings.json` `env` (adding absent keys,
    never overwriting one), installs the receiver as `ccp otel install` does and the product's board
    timer as `ccp board install` does (macOS only; elsewhere it prints the commands), then checks the
    receiver; when it is down, init prints the command to run in a normal terminal. With `off`, init
    writes nothing outside the product and is silent about telemetry thereafter. With no consent
    recorded and no flag, init prints that telemetry covers every Claude Code session on this machine
    and that `--telemetry on` turns it on, and writes nothing outside the product.
  - The product's tag, `env.OTEL_RESOURCE_ATTRIBUTES = ccp.project_id=<project_id>`, is written into its
    `.claude/settings.json` whatever the consent, when absent, never overwritten.
  - `OTEL_LOG_USER_PROMPTS` and `OTEL_LOG_TOOL_DETAILS` are never written (§24.1, house rule E5).
  - `telemetry.otel_port` is removed from the code and the schema: a plane.json that still sets it
    loads with the unknown-key warning (§8.1).
  - Tests stub the launchd and user-settings writes (E2: no launchd, no real home directory).
- This task marks ADR-0043 D6 built in its own PR.

## Scope

- **In:**
  - `ccp/init.py`, `ccp/cli.py`: `--telemetry`; the tag; the consent and the machine setup.
  - `ccp/otel.py`, `ccp/board.py`: the install steps callable from init.
  - `scripts/observability/lib.py`: `machine_path()` and `read_machine()`;
    `contracts/machine.schema.json` (new).
  - `ccp/config.py`, `contracts/plane_config.schema.json`: `otel_port` removed.
  - `README.md`: the adoption steps say what `--telemetry on` does and that it covers the machine.
  - `tests/test_init_telemetry.py` (new).
  - `docs/spec/01-model.md` §4.5: CURRENT (at `e9ff0fc`): "- the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, with
    `subagentPromptCacheTtl: "1h"` and `autoCompactWindow` (the binding's `lead.auto_compact_window`,
    default `350000`) added when absent and never overwritten, and the one `CLAUDE.md` line, once
    (§4.3);" PROPOSED:
    > - the anchor merged into `.claude/settings.json`, leaving its other keys and values alone, with `subagentPromptCacheTtl: "1h"`, `autoCompactWindow` (the binding's `lead.auto_compact_window`, default `350000`), the lead's `model` (§2.4) and the telemetry tag `env.OTEL_RESOURCE_ATTRIBUTES` (`ccp.project_id=<project_id>`, §24.1) added when absent and never overwritten, and the one `CLAUDE.md` line, once (§4.3);
  - `docs/spec/01-model.md` §4.5, after that list item: CURRENT: none (a new list item). PROPOSED:
    > - with the operator's consent for the machine (`--telemetry on`, recorded once in the machine file beside the bindings, §8.3), the user-level telemetry keys (§24.1), the receiver and the product's board timer; it says first that the keys cover every Claude Code session on the machine. `--telemetry off` records a refusal, and init then writes nothing outside the product. With neither recorded, it prints what `--telemetry on` would do and writes nothing outside the product. When the receiver is down, it prints the command to run in a normal terminal: the receiver cannot be started from inside Claude Code, and only macOS has a service definition;
  - `docs/spec/04-observability.md` §24.1: CURRENT (at `e9ff0fc`): "endpoint `http://127.0.0.1:<telemetry.otel_port>`, and no project
    id. Claude Code ignores these enabling keys in a project's `.claude/settings.json`, so a product
    carries none of them." PROPOSED:
    > endpoint `http://127.0.0.1:<the receiver's port>` (the receiver owns it), and no project id. `ccp init --telemetry on` writes them, with the operator's consent for the machine (§4.5). Claude Code ignores these keys in a project's `.claude/settings.json`, so a product carries none of them, and a project directory cannot turn telemetry off for its sessions.
  - `docs/spec/01-model.md` §8.4: CURRENT (at `e9ff0fc`): "- `telemetry.otel_port` (default 4318); `board.refresh_minutes` (default 5)." PROPOSED:
    > - `board.refresh_minutes` (default 5).
  - `docs/spec/01-model.md` §8.1, the example: CURRENT (at `e9ff0fc`): `"telemetry": { "otel_port": 4318, "allowance_cmd": "<command printing the allowance JSON>" },` PROPOSED:
    > "telemetry": { "allowance_cmd": "<command printing the allowance JSON>" },
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D6 marked built; `docs/adr/INDEX.md`.
- **Out:**
  - The account keys in the machine file (0186). A service definition for another OS.

## dod_checks

- id: `tel-01`
  story: As an operator adopting a product, its sessions are tagged with its project id.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp sandbox create <dir>` and read `<dir>/product/.claude/settings.json` `env`.
  expect: `env.OTEL_RESOURCE_ATTRIBUTES` is `ccp.project_id=product`, beside `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`.
  dry run (`e9ff0fc`): `env` is `{"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}`.
- id: `tel-02`
  story: As an operator, init asks once per machine, does the setup on my consent, and writes nothing outside the product without it.
  setup: a checkout of the PR head.
  steps:
    1. Run `python3 -B -m unittest -q tests.test_init_telemetry`.
  expect: exits 0; its tests, with a fenced bindings directory and home and stubbed launchd, cover: no consent recorded and no flag (the machine-wide notice printed; no user settings, plist or machine file written); `--telemetry on` (the user keys added without overwriting a differing one, neither prompt-logging key written, the receiver and board installs called, `machine.json` `telemetry` `on`); a later init on that machine with no flag (the setup checked again, no notice); `--telemetry off` (recorded, nothing written outside the product); a receiver that stays down (the normal-terminal command printed).
  dry run: n/a — new module; `ccp init --telemetry` is refused as an unknown argument at `e9ff0fc`.
- id: `tel-03`
  story: As an operator, the receiver's port is not a product setting.
  setup: a checkout of the PR head.
  steps:
    1. Run `git grep -n 'otel_port' -- ccp scripts plugin contracts`.
  expect: prints nothing.
  dry run (`e9ff0fc`): 3 lines in `ccp/config.py` and the schema's `otel_port` property.
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D6 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0184-init-turns-telemetry-on --base origin/main`.
    2. Run `grep -n '"D6 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2 prints `- "D6 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D6 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

## Verification notes
