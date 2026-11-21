# ccp — the plane's command-line tool

Every command the plane runs inside a product checkout. Entry points: `bin/ccp`, `python3 -m ccp`.
Standard library only. Each module's docstring names the SPEC section it implements; the SPEC is
normative, and a module that disagrees with it is the bug.

## Layout

- **Entry and configuration:** `cli.py` (argument parsing, one function per command), `config.py`
  (the product root and its docs/delivery/plane.json), `refs.py` (every id and reference pattern).
- **Durable formats:** `tasklog.py` (task files, §5.6), `taskmigrate.py` (an earlier plane generation's task
  files, converted in place, §5.3), `adr.py` (ADRs, §6), `reviewpoints.py`,
  `rules.py` (house rules, the starter set and budgets), `pkgdocs.py`, `docrules.py` and `doclang/` (doc checks).
- **The runtime queue:** `queue.py` (QUEUE_ROOT, the ledger, the runner's work.json), `lifecycle.py` (claim,
  phase, wait, release, close), `selection.py` and `parallel.py` (what the runner may take),
  `prhost.py` (the one module that reaches a PR host; the rest see `PrFacts`, house rule E19),
  `runs.py`, `report.py`, `verify.py`, `suite.py`, `wt.py`, `mutate.py`, `prompt.py`, `plane.py`,
  `gitmerge.py` (the one reading of git's merge analysis, house rule E14),
  `upgrade.py` (what a plane release asks of a product, §29.3),
  `jsonedit.py` (one member of a JSON object edited in its text, every other byte kept: the plane.json records, §29.3),
  `sandbox.py` (a throwaway adopted product for end-to-end checks, §29.3),
  `notify.py` (the operator's notices: fired, rendered, recorded and listed pending, §3.6).
- **Seats that run headless:** `architect.py`, `estimator.py`.
- **Measurement and the board:** `health.py`, `estimate.py`, `calibrate.py`, `forecast.py`,
  `usage.py`, `otel.py`, `seats.py`, `models.py` (each role's default model and effort, and does an observed model id match a pin, §24.5),
  `board.py`, `drill.py`, `plan.py`, `quality.py`, `backfill.py`.
- **Helpers:** `graph.py` (the cycles in a dependency map and what a node depends on, over plain ids).

## Conventions

- Writes to the queue go through `queue.py`'s helpers (atomic replace, `file_lock`); events go
  through `queue.emit`. A command records its own events.
- A product fact is read from the product's plane.json or reported by the product as JSON; never parsed from
  product prose.
- Headless children strip `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
- Telemetry carries numbers and ids, never prompt, response or file content. A queue record may hold a
  worker's own short statement lines (friction, follow-ups, a proposal's need), refused when they look
  like a secret and never sent to telemetry (E5).
