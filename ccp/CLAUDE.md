# ccp — the plane's command-line tool

Every command the plane runs inside a product checkout. Entry points: `bin/ccp`, `python3 -m ccp`.
Standard library only. Each module's docstring names the SPEC section it implements; the SPEC is
normative, and a module that disagrees with it is the bug.

## Layout

- **Entry and configuration:** `cli.py` (argument parsing, one function per command), `config.py`
  (the product root and its docs/delivery/plane.json), `refs.py` (every id and reference pattern).
- **Durable formats:** `tasklog.py` (task files, §5.6), `adr.py` (ADRs, §6), `reviewpoints.py`,
  `rules.py` (house rules, the starter set and budgets), `pkgdocs.py`, `docrules.py` and `doclang/` (doc checks).
- **The runtime queue:** `queue.py` (QUEUE_ROOT, the ledger, the runner's work.json), `lifecycle.py` (claim,
  phase, wait, release, close), `selection.py` and `parallel.py` (what the runner may take),
  `runs.py`, `report.py`, `verify.py`, `suite.py`, `wt.py`, `mutate.py`, `prompt.py`, `plane.py`,
  `notify.py` (the operator's channel on each trigger, §3.6).
- **Seats that run headless:** `architect.py`, `estimator.py`.
- **Measurement and the board:** `health.py`, `estimate.py`, `calibrate.py`, `forecast.py`,
  `usage.py`, `otel.py`, `seats.py`, `board.py`, `drill.py`, `plan.py`, `quality.py`, `backfill.py`.

## Conventions

- Writes to the queue go through `queue.py`'s helpers (atomic replace, `file_lock`); events go
  through `queue.emit`. A command records its own events.
- A product fact is read from the product's plane.json or reported by the product as JSON; never parsed from
  product prose.
- Headless children strip `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
- Telemetry and records carry numbers and ids, never prompt, response or file content.
