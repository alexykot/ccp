# ccp — the plane's command-line tool

Every command the plane runs inside a product checkout. Entry points: `bin/ccp`, `python3 -m ccp`.
Standard library only. Each module's docstring names the SPEC section it implements; the SPEC is
normative, and a module that disagrees with it is the bug.

## Layout

- **Entry and configuration:** `cli.py` (argument parsing, one function per command), `config.py`
  (the product root and its docs/delivery/plane.json), `envvars.py` (the plane's `CCP_*` environment
  variables, read and set in one place), `refs.py` (every id and reference pattern), `init.py`
  (`ccp init`: a product adopted in one command, §4.3, §8.3).
- **Durable formats:** `tasklog.py` (task files, §5.6, and the one reader of their signed blocks, §3.5),
  `dryrun.py` (`ccp tasks dry-run`: a task's check commands run at the integration tip and their dry-run
  records written, §21.1), `taskmigrate.py` (an earlier plane generation's task
  files, converted in place, §5.3), `adr.py` (ADRs, §6), `reviewpoints.py`,
  `rules.py` (house rules, the starter set and budgets), `pkgdocs.py`, `docrules.py` and `doclang/` (doc checks),
  `baseline.py` (a docs or tasks check failure already at the merge base, reported as pre-existing, §21.2).
- **The runtime queue:** `queue.py` (QUEUE_ROOT, the ledger, the runner's work.json, the open spec
  questions), `lifecycle.py` (claim, phase, wait, release, close), `selection.py` and `parallel.py` (what the runner may take),
  `prhost.py` (the one module that reaches a PR host; the rest see `PrFacts`, house rule E19),
  `runs.py`, `followups.py` (the lead's outcome for each worker follow-up, and the open ones, §13.4),
  `report.py`, `submit.py` (formal-submit, `ccp tasks submit`, §15.1), `verify.py`, `schema.py` (the one schema checker
  for `contracts/`), `suite.py`, `wt.py`,
  `mutate.py`, `prompt.py`, `plane.py`,
  `gitmerge.py` (the one reading of git's merge analysis, house rule E14),
  `upgrade.py` (what a plane release asks of a product, §29.3),
  `jsonedit.py` (one member of a JSON object edited in its text, every other byte kept: the plane.json records, §29.3),
  `sandbox.py` (a throwaway adopted product for end-to-end checks, §29.3),
  `notify.py` (the operator's notices: fired, rendered, recorded and listed pending, §3.6).
- **Seats that run headless:** `architect.py`, `estimator.py`, both launched through `headless.py` (a plane-launched
  `claude -p`: its environment without the API keys, its JSON and its quota stop, §24.3, house rule E8).
- **Measurement and the board:** `health.py`, `estimate.py`, `calibrate.py`, `forecast.py`,
  `usage.py`, `otel.py`, `seats.py`, `models.py` (each role's default model and effort, and does an observed model id match a pin, §24.5),
  `board.py`, `drill.py`, `plan.py`, `quality.py`, `backfill.py`.
- **Helpers:** `graph.py` (the cycles in a dependency map and what a node depends on, over plain ids).

## Conventions

- Writes to the queue are atomic: `lib.write_atomic`, or `queue.write_json`, which calls it, under
  `file_lock` where two writers can meet; events go through `queue.emit`.
  A command records its own events.
- House rules E5, E6 and E8 (`docs/ENGINEERING.md`) apply to every module here.
