# `ccp` commands: 01-model

Call syntax and flags for the commands of SPEC part `docs/spec/01-model.md`. The rules each command follows are in the SPEC, not here.

| Command | Who | SPEC |
|---|---|---|
| `ccp adr new "<title>"` | any seat | §6.6 (the next ADR, from the template, `proposed`) |
| `ccp adr status N <status> [--note T]` | any seat | §6.4, §6.6 (an allowed status move) |
| `ccp adr supersede OLD NEW [--decisions D2,D4] [--by Dk] [--archive]` | any seat | §6.5, §6.6 (links both ways; retires the decisions or the ADR) |
| `ccp adr decide N Dn <state> [--by REF] [--note T]` | any seat | §6.3 (one decision's build state) |
| `ccp adr check` | any seat | §6.7 (`ccp docs check` runs them) |
| `ccp adr index [--stdout]` | any seat | §6.6 (regenerate the ADR index) |
| `ccp adr list [--json] [--dir DIR]` | any seat | §6.6 (every ADR's frontmatter) |
| `ccp adr migrate --markers [--dry-run]` | any seat | §6.3 (rewrite non-canonical decision markers) |
| `ccp docs adr index [--stdout]` | any seat | §6.6 (the same as `ccp adr index\|list`) |
| `ccp docs adr list [--json] [--dir DIR]` | any seat | §6.6 (the same as `ccp adr index\|list`) |
| `ccp tasks index [--stdout]` | lead, runner | §5.7 (regenerate `INDEX.yaml`) |
| `ccp init [--project-id ID] [--queue-root DIR] [--integration-branch B] [--language L] [--gate CMD] [--no-starter-rules] [--starter-rules] [--telemetry on\|off] [--force]` | operator | §4.3, §4.5, §8.3, §20.5 (`--starter-rules` is a no-op) |
| `ccp init --rules-doc PATH [--adopt]` | operator | §4.5, §20.1, §20.5 (`--adopt` gives each rule with no `check:` line `check: pass`) |
| `ccp init --permissions` | operator | §4.5, §18.5 (the runner's and workers' permissions as a JSON `permissions` block) |
| `ccp notify render <trigger> [--task ID] [--id ID] [--reason R] [--json]` | any seat | §3.6 (the notice for a trigger) |
| `ccp notify sent <trigger> [--task ID] [--id ID] --via command\|lead [--note T]` | lead | §3.6 (record a notice sent) |
| `ccp notify fire <trigger> [--task ID] [--id ID] [--reason R]` | plane developers | §3.6, §29.3 (a test notice, in a sandbox) |
| `ccp notify pending` | lead | §3.6 (the notices fired and not yet sent) |
| `ccp notify upgrade [--since COMMIT]` | `scripts/run-checkout.sh update` | §3.6, §29.3 (record this product's `upgrade` notice) |
| `ccp spec show <ref> [<ref> …]` | any seat | §7.2 (each cited SPEC section, in the order given) |
| `ccp where` | any seat | §8.3, §9.2 (the binding this directory resolves to) |
| `ccp orientation` | any session that started before adoption | §9.3 (the orientation a session gets) |
| `ccp orientation --tail` | the SessionStart hook | §9.3 (the text the hook appends to the orientation) |

Global: `--root DIR` (else `$CCP_ROOT`, else the git top level), §8.2.
