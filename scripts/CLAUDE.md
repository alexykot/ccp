# scripts — shell entry points around `ccp`

- **Plane development:** `dev-worktree.sh` (a worktree for a change), `release.sh` (after a merge to
  main), `run-checkout.sh` (the clone `ccp` on PATH runs from), `install-git-hooks.sh` and
  `git-hooks/` (no commits on main), `gate.sh` and `gate_result.py` (the plane's own test gate, run through `ccp suite run`),
  `leak-check.sh` (no managed-product specifics in tracked files), `spec_map_check.py` (the SPEC
  restructure's map checks: coverage, a part's completeness, references).
- **Seat helpers products call:** `team.sh` (the runner teammate and gates, §2), `spec-maintainer-ask.sh`
  (the runner raises a spec question to the lead, §17), `sync-product-docs.sh` (managed copies for
  products not on the plugin), `formal-submit.template.sh`.
- `observability/` holds the ledger and snapshot writers (§23) that `ccp` and the hooks share.

New behaviour goes into `ccp`, not into a new script: a script here only wraps `ccp` or Git.
