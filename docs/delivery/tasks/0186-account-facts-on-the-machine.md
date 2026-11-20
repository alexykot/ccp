---
task_id: 0186-account-facts-on-the-machine
title: The allowance command and the weekly stop live in the machine file, the weekly stop defaults to 90%, and an unread allowance is said out loud
status: pending
kind: feature
depends_on: ["0173-plane-json-block-registry", "0175-one-binding-reader", "0179-one-account-accessor", "0184-init-turns-telemetry-on", "0187-short-plane-json"]
spec_refs: ["S8", "S16", "S24", "S25"]
adr_refs: ["0043 D8"]
review_point: R12
paths: ["ccp/config.py", "ccp/usage.py", "ccp/parallel.py", "ccp/board.py", "ccp/init.py", "ccp/upgrade.py", "plugin/hooks/", "scripts/observability/lib.py", "contracts/machine.schema.json", "contracts/plane_config.schema.json", "README.md", "docs/spec/01-model.md", "docs/spec/02-delivery.md", "docs/spec/04-observability.md", "docs/adr/0043-opinionated-defaults-short-configuration.md", "docs/adr/INDEX.md", "tests/test_machine_account.py", "tests/"]
adopt: "machine.json allowance_cmd (move telemetry.allowance_cmd and telemetry.allowance_stop_weekly out of each product's plane.json into the machine file beside the bindings, once per machine)"
sign_off: brief
created: 2026-11-19
updated: 2026-11-19
---

# Task: 0186-account-facts-on-the-machine

## Intent

The account is the machine's, not a product's: the command that reads its allowance and the weekly
stop are set once, in the machine file beside the bindings, and every product on the machine uses them.
The weekly stop applies by default at 90%, so an unattended team stops for the weekly allowance
without anyone setting it. When no allowance can be read, the plane bounds nothing, and it says so:
`ccp init` and the session-start check warn, and the board shows "usage unread". The session park,
wake and ceiling numbers are constants.

## Context (not checked)

- ADR-0043 D8, accepted 2026-11-19.
- Depends on 0179 (every reader of these keys goes through `usage.account(cfg)`; this task changes
  where that reads them), 0184 (the machine file, `machine.json` in `lib.bindings_dir()`, and its
  contract), 0175 (the one binding module that resolves it), 0173 (the block registry) and 0187 (the
  constant mechanism, `config.constant_override`, and the upgrade step that lists constants: this
  task marks its knobs constant through it and builds no mechanism of its own).
- Today, at `e9ff0fc`: with no `telemetry` block the window rules have no weekly stop:
  `usage.window_rules(cfg)` prints `{'seven_day': {'kind': 'weekly', 'stop_pct': None, 'park_pct': None}, 'five_hour': {'kind': 'session', 'stop_pct': None, 'park_pct': 95.0}}`
  (`python3 -B -c "…usage.window_rules(config.load(d))…"` on a plane.json of `project_id` only, at
  `e9ff0fc`). Nothing warns that no allowance command is set.
- Decided here:
  - The machine file gains `allowance_cmd` (a shell command, default none) and `allowance_stop_weekly`
    (a percentage, default 90). `usage.account(cfg)` reads them from it.
  - **Old place.** A plane.json `telemetry.allowance_cmd` or `telemetry.allowance_stop_weekly` is still
    honoured when the machine file lacks the key, with one stderr warning naming the move; when both
    set it, the machine file wins and the warning says the product's value is ignored. 0191 ends this.
  - **Constants**, at today's defaults: `session_park_pct` 95, `session_wake_arm_pct` 50,
    `session_wake_margin_s` 180, `parallel.session_ceiling_pct` 60, and `telemetry.windows` (the two
    built-in windows), each marked constant in the registry so 0187's mechanism applies: a non-default
    value keeps applying with a warning, and `ccp upgrade status` lists it.
  - **Unread usage.** With no allowance command: `ccp init` and the session-start hook print one
    warning that no usage is read and nothing bounds spend, naming `allowance_cmd` and the machine
    file; the board's usage panel shows `usage unread`, and its JSON carries `"usage_read": false`.
  - A built-in usage reader is out (ADR-0043 D8: a later decision).
- This task marks ADR-0043 D8 built in its own PR.

## Scope

- **In:**
  - `ccp/usage.py`, `ccp/parallel.py`, `ccp/config.py`: as decided; the constants in code.
  - `scripts/observability/lib.py`, `contracts/machine.schema.json`: the two keys.
  - `contracts/plane_config.schema.json`: the moved and constant keys marked deprecated.
  - `ccp/board.py`: `usage unread`. `ccp/init.py` and the session-start hook under `plugin/hooks/`: the
    warning. `ccp/upgrade.py`: the move and the non-default constants.
  - `README.md`: the account row moves to the machine file.
  - `tests/test_machine_account.py` (new); tests that set the moved keys in plane.json set them in a
    fenced machine file instead.
  - `docs/spec/04-observability.md` §25.1: CURRENT (at `e9ff0fc`): "`ccp tasks claim` and `ccp board build` run the binding's `telemetry.allowance_cmd`." PROPOSED:
    > `ccp tasks claim` and `ccp board build` run the machine's `allowance_cmd`, from the machine file beside the bindings (§8.3), shared by every product on the machine. Without it no usage is read and nothing bounds spend: `ccp init` and the session-start check warn, naming the key, and the board shows `usage unread`.
  - `docs/spec/04-observability.md` §25.2: CURRENT (at `e9ff0fc`): "Each window has a rule, `telemetry.windows`: `{<name>: {kind: weekly|session, stop_pct, park_pct}}`,
    merged over two built-in ones: `seven_day` (weekly, `stop_pct` = `telemetry.allowance_stop_weekly`)
    and `five_hour` (session, `park_pct` = `telemetry.session_park_pct`, default 95)." PROPOSED:
    > Each window has a rule: `{kind: weekly|session, stop_pct, park_pct}`. There are two: `seven_day` (weekly, `stop_pct` = the machine's `allowance_stop_weekly`, default 90) and `five_hour` (session, `park_pct` 95).
  - `docs/spec/04-observability.md` §25.3: CURRENT (at `e9ff0fc`): "(the gating weekly window's `stop_pct`; by default
    `telemetry.allowance_stop_weekly`)" PROPOSED:
    > (the gating weekly window's `stop_pct`, the machine's `allowance_stop_weekly`, default 90%)
  - `docs/spec/04-observability.md` §25.4: CURRENT (at `e9ff0fc`): "`telemetry.session_wake_margin_s` (default 180 s;" PROPOSED:
    > 180 s (
  - `docs/spec/04-observability.md` §25.4: CURRENT (at `e9ff0fc`): "From `telemetry.session_wake_arm_pct` (default 50)," PROPOSED:
    > From 50% of the session window,
  - `docs/spec/02-delivery.md` §16.2: CURRENT (at `e9ff0fc`): "`session_ceiling_pct` defaults to 60." PROPOSED:
    > The session ceiling is 60%.
  - `docs/spec/02-delivery.md` §16.3: CURRENT (at `e9ff0fc`): "A product without `telemetry.allowance_cmd` reads no usage: the rule passes." PROPOSED:
    > A machine without `allowance_cmd` reads no usage: the rule passes (§25.1).
  - `docs/spec/01-model.md` §8.3: CURRENT: none (a new paragraph, after the binding's key list). PROPOSED:
    > **The machine file**, `machine.json` beside the bindings (`contracts/machine.schema.json`), holds what belongs to the machine's account, not to a product: `telemetry` (the operator's consent, §4.5), `allowance_cmd` and `allowance_stop_weekly` (§25).
  - `docs/adr/0043-opinionated-defaults-short-configuration.md`: D8 marked built; `docs/adr/INDEX.md`.
  - The §25.4 park sentence naming `telemetry.session_park_pct` and the §16.2 example's `session_ceiling_pct` are corrected under §31.1 and quoted in the PR body, with any other sentence this makes false.
- **Out:**
  - A built-in usage reader. Removing the old place (0191).

## dod_checks

- id: `acc-01`
  story: As an operator, the weekly stop applies at 90% without my setting it.
  setup: a checkout of the PR head; a temp product whose plane.json is `{"project_id": "demo", "language": "none"}`; `CCP_BINDINGS_DIR` pointed at an empty temp dir.
  steps:
    1. Run `python3 -B -c "from ccp import config, usage; print(usage.window_rules(config.load('<dir>'))['seven_day']['stop_pct'])"`.
  expect: prints `90` or `90.0`.
  dry run (`e9ff0fc`): prints `None` (the probe in Context, on `project_id` alone).
- id: `acc-02`
  story: As an operator, the machine file's allowance command serves every product, and a product's own old value still works with a warning.
  setup: a checkout of the PR head; then a separate copy where `usage.account` ignores the machine file.
  steps:
    1. On the head, run `python3 -B -m unittest -q tests.test_machine_account`.
    2. In the copy, run the same.
  expect: step 1 exits 0, its tests covering: the machine's `allowance_cmd` read for two products; a plane.json `telemetry.allowance_cmd` honoured with the move warning when the machine file lacks it, and ignored with a warning when both set it; a plane.json `session_park_pct: 90` honoured with a warning naming the constant 95; step 2 exits non-zero.
  dry run: n/a — new module.
- id: `acc-03`
  story: As an operator with no allowance command, the board and init tell me nothing is bounded.
  setup: a checkout of the PR head; `ccp sandbox create <dir>`, its `PROJECT_YAML`, `QUEUE_ROOT` and `CCP_BINDINGS_DIR` exported; no machine `allowance_cmd`.
  steps:
    1. Read the init output `sandbox create` printed.
    2. In the product root, run `ccp board build`, then read the board JSON it wrote.
  expect: step 1 carries a warning naming `allowance_cmd`; step 2's JSON has `"usage_read": false`.
  dry run (`e9ff0fc`): step 1's only warning is the no-origin one; the board JSON has no `usage_read` key (`git grep -c usage_read -- ccp` at `e9ff0fc`: 0).
- id: `spec-01`
  story: As the operator, the SPEC carries the words I signed, and D8 is recorded as built.
  setup: a checkout of the PR head.
  steps:
    1. Run `ccp verify spec-text 0186-account-facts-on-the-machine --base origin/main`.
    2. Run `grep -n '"D8 ' docs/adr/0043-opinionated-defaults-short-configuration.md`.
  expect: step 1 exits 0 with every passage found; step 2's output contains `- "D8 built"`.
  dry run (`e9ff0fc`): step 2 printed `- "D8 not_built"`.
- id: `suite-01`
  story: As a plane developer, nothing else broke.
  setup: a checkout of the PR head.
  steps:
    1. Run the full suite through `ccp suite run`, then `ccp tasks check`, `ccp docs check`, `ccp adr check`, then `git branch --list 'state/*'`.
  expect: all pass and the branch list is empty.
  dry run: n/a.

## Implementation notes

*Append-only, newest last.*

- Premise re-run at 5e9a8f7: the Context probe (`usage.window_rules` on a plane.json of `project_id` and `language`) printed `stop_pct` None before the change (the task states `e9ff0fc`: the same); it prints 90 now.
- `config.machine_account()` is the one reader of the machine file's two account keys (valid values only; a bad one is ignored with a warning naming the file). `usage.account(cfg)` takes `allowance_cmd` and `allowance_stop_weekly` from it, else from plane.json's old `telemetry` key, else 90 (`config.ALLOWANCE_STOP_WEEKLY_DEFAULT`). The two old keys are registry entries (`KEY_OUTCOMES`, merged, `machine=True`, `in_place`): the loader gives the one warning (moved, or ignored because the machine file sets it), so `ccp upgrade status` lists them through the existing `plane.json keys` step. The five constants are registry entries at today's values; `telemetry.windows`' constant is its default, null (no window beyond the built-in two), so its warning reads "a constant in code (None)".
- Rules the task left open, written narrowest: an old `telemetry.allowance_stop_weekly: null` is unset (the default 90 applies; before, null meant no weekly stop); an invalid machine value is ignored with a warning, not refused; `machine.json <key>` is a valid `adopt` step (`ccp upgrade status` checks it against the machine file: taken once the key is there); the unread-usage warning text comes from `usage.unread_warning()` and the session-start hook adds whatever `ccp allowance status` returns under `warning` (E13), so the hook needs no change to its wording; `usage_read` sits in the board JSON's `usage` object (and in `now.allowance`, from `usage.status`, which the hook reads).
- Files outside the task's `paths` that had to change: `ccp/board_page.html` (the weekly tile shows `usage unread`), `plugin/skills/spec-maintainer/SKILL.md` (a sentence naming `telemetry.session_park_pct`), `docs/design/allowance.md` and `docs/design/telemetry.md` (prose). Tests: `tests/helpers.py` gains `machine_file(case, **keys)`, the fenced machine file; the modules that set the moved keys in plane.json use it (`test_toolkit`, `test_parallel_claims`, `test_session_park`, `test_notify`, `test_notify_lead`, `test_forecast`); `test_init` writes a machine command where a test counts init's warnings; `test_account_accessor`, `test_config_unknown_keys`, `test_board_layout`, `test_init_permissions`, `test_init_telemetry`, `test_short_plane_json` follow the new defaults and contract. `test_allowance_windows`, `test_allowance_lapse` and `test_account_accessor` still set the old keys on a config object: they test the old place and the window merge, not a plane.json file.
- §31.1 corrections beyond the task's passages (quoted in the PR body): the `telemetry` line of §8.1's example (`01-model.md`), the `session_ceiling_pct` of §16.2's example, §16.3 rule 5's `session_ceiling_pct` (now "the session ceiling"), and §18.4's `telemetry.session_park_pct, default 95` (now "95%"). §16.2's "`session_ceiling_pct` defaults to 60." became "(file). The session ceiling is 60%." and §25.4's margin passage reads "180 s (`set-waiting-on.sh …`)" with no space after the bracket.

## Verification notes
