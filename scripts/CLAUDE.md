# scripts — the plane's entry points and its development programs

- **Plane development:** `dev-worktree.sh` (a worktree for a change), `release.sh` (after a merge to
  main), `run-checkout.sh` (the clone `ccp` on PATH runs from), `install-git-hooks.sh` and
  `git-hooks/` (no commits on main; the commit hook template, no edit to a leased task file), `gate.sh`, `gate_parallel.py` and `gate_result.py` (the plane's own test gate, run through `ccp suite run`: each test module in its own process, `GATE_WORKERS` at a time, those in its `SERIAL` list alone; a module whose inputs are unchanged since it passed is served from the test cache, `GATE_CACHE_DIR`, and `GATE_COLD=1` is its cold option, which `ccp suite run --cold` sets through `CCP_SUITE_COLD`),
  `leak-check.sh` (no managed-product specifics in tracked files), `house_checks.py` (the programs of the
  house rules' command checks, a subcommand each, that plane.json `architect.checks` calls with their figures).
- **Seat helpers products call:** `team.sh` (the runner teammate and gates, §2), `spec-maintainer-ask.sh`
  (the runner raises a spec question to the lead, §17), `sync-product-docs.sh` (managed copies for
  products not on the plugin), `formal-submit.template.sh` (formal-submit, a wrapper of `ccp tasks submit`, §15.1).
- `observability/` holds the ledger writers (§23) that `ccp` and the hooks share.

Scripts follow E7.
