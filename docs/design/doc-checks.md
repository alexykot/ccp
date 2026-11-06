# Doc checks: design notes

Non-normative notes behind SPEC §21.

- **Where the tools came from.** `ccp/tasklog.py` and `ccp/pkgdocs.py` began as ports of a managed
  product's own task-log and doc-check tools. Against that product's checkout they reported the
  same failures and the same source directories. Deliberate changes in the port: inline
  `# comments` in frontmatter are stripped; soft language is only looked for inside
  `## dod_checks`; "done without verification notes" means no `- ` line under
  `## Verification notes`. A rule that no module computes a path from `__file__` is a code invariant
  of that product, not a documentation rule, and stayed in the product as a test.
- **Settings are product-owned** (`docs/delivery/plane.json`) because the rules describe the
  product's own tree, change with its code, and must work in a worktree or a verifier checkout that
  never sees the queue. Its presence is the opt-in.
- **One installed CLI, stdlib only** (`ccp/`, `bin/ccp`, `pyproject.toml`): seats, implementers and
  verifiers run it from a product checkout, and `bin/ccp` works from any clone without installing.
- **The task-log shape is enforced, not described:** frontmatter a parser can read, a generated
  INDEX that cannot drift, and a validator the verifier gates on.
- **The plane's task template** moved from a `## Meta` table to frontmatter.
- **The docs audit as a review kind.** Isolation, prompt audit, prepaid login, report validation and
  triage by the task-log owner are the architecture review's; only the skill, the trigger and the
  finding categories differed. It is now the architect's `docs` lens.
