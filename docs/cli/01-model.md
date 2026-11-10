# `ccp` commands: 01-model

Call syntax and flags for the commands of SPEC part `docs/spec/01-model.md`. The rules each command follows are in the SPEC, not here.

| Command | What it does | SPEC |
|---|---|---|
| `ccp adr new "<title>"` | the next ADR, from the template, `proposed` | §6.6 |
| `ccp adr status N <status> [--note T]` | an allowed status move | §6.4, §6.6 |
| `ccp adr supersede OLD NEW [--decisions D2,D4] [--by Dk] [--archive]` | links both ways; retires the decisions or the ADR | §6.5, §6.6 |
| `ccp adr decide N Dn <state> [--by REF] [--note T]` | one decision's build state | §6.3 |
| `ccp adr check` | the ADR checks | §6.7 |
| `ccp adr index [--stdout]` | regenerate the ADR index | §6.6 |
| `ccp adr list [--json]` | every ADR's frontmatter | §6.6 |
| `ccp adr migrate --markers [--dry-run]` | rewrite non-canonical decision markers | §6.3 |
| `ccp docs adr index\|list` | the same as `ccp adr index\|list` | §6.6 |
| `ccp tasks index [--stdout]` | regenerate `INDEX.yaml` | §5.7 |
| `ccp init [--project-id ID] [--queue-root DIR] [--integration-branch B] [--gate CMD] [--starter-rules] [--force]` | adopt this repository: the templates, `plane.json`, `.gitignore`, the plugin anchor and the `CLAUDE.md` line, the binding and its queue; `--starter-rules` adds the starter house rules and their settings; keeps existing files unless `--force` | §4.3, §4.5, §8.3, §20.5 |
| `ccp where` | the project, binding, queue, plane checkout and `ccp` path for this directory | §8.3, §9.2 |

Global: `--root DIR` (else `$CCP_ROOT`, else the git top level), §8.2.
