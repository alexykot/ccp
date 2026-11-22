# contracts — JSON Schemas for the records the plane reads or writes

One schema per format: product config (`plane_config.schema.json`), bindings, task and ADR
frontmatter, queue records (events, snapshots, escalations, questions and answers, verification,
worktrees, prompt audits, a task's phase moves in `progress/` and its review record in `review/`),
architect reports, and the product-reported contracts (gate results, allowance windows). A renamed
value stays listed as a deprecated, read-only alias so old records still validate. Code and schema
change in the same commit; tests check that they agree: `ccp/schema.py` is the one checker, and for the
contracts the tests name a test validates a record its writer writes or, where a seat or a machine command
writes it, a `<name>.example.json` (for the task file, `task_file.example.md`) its reader accepts (`tests/test_contract_writers.py`,
`tests/test_phase_contracts.py`, `tests/test_task_state_contract.py`).
The checker fails closed on a keyword it does not know, so a schema that needs a new one extends it; a test holds every schema to the keywords it knows.

Some queue records have no schema, among them run records (`runs/<task>/<run>.json`) and the suite rows
(`runs/_suites.jsonl`). Their own modules' tests (`ccp/runs.py`, `ccp/suite.py`) check those two.
