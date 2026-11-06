---
id: ADR-0021
title: "Estimation and forecast"
status: accepted
date: "2026-10-22"
deciders: operator
spec_refs: [S26]
decisions:
  - "D1 live"
  - "D2 live"
  - "D3 live"
  - "D4 live"
  - "D5 live"
  - "D6 not_built"
  - "D7 built"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0021 — Estimation and forecast

## Context

Once task history exists, wall time and tokens can be estimated before work starts, and the remaining plan forecast against the allowance. Estimates must be scored against actuals and corrected, or they mislead.

## Decision

### D1. Records and a baseline

Estimate records per task, with actuals at close, plus a reference-class baseline with no model call.

### D2. An estimator seat

A headless estimator seat with no tools estimates tasks as they are prepared, optionally automatically.

### D3. A forecast

A Monte Carlo completion forecast over the ready order, with an allowance fit and modelled pauses.

### D4. Calibration

A calibration loop corrects bias by kind and family and widens bands from scored pairs.

### D5. Capped bands

Each band's upper percentile is capped relative to its median.

### D6. Fall back to the baseline

If the estimator seat does not beat the baseline, the baseline is used.

### D7. Configurable inputs

Estimator inputs (families, path suffixes, spec locations) come from configuration.

## Consequences

- Plans come with ranges grounded in the product's own history.
- Estimates cost a little per task.
