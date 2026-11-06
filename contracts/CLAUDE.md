# contracts — JSON Schemas for every record the plane reads or writes

One schema per format: product config (`plane_config.schema.json`), bindings, task and ADR
frontmatter, queue records (events, snapshots, escalations, questions and answers, verification,
worktrees, prompt audits), architect reports, and the product-reported contracts (gate results,
allowance windows). A renamed value stays listed as a deprecated, read-only alias so old records
still validate. Code and schema change in the same commit; tests check that they agree.
