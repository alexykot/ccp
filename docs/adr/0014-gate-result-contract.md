---
id: ADR-0014
title: "Gate-result contract"
status: accepted
date: "2026-11-05"
deciders: operator
spec_refs: [S14, S15]
decisions:
  - "D1 live"
  - "D2 built"
  - "D3 built"
  - "D4 built"
  - "D5 live"
notes: "2026-11-05: status proposed → accepted"
---
# ADR-0014 — Gate-result contract

## Context

Parsing a product's test-runner output ties the plane to one tool and one cache. A product should report its own counts in a defined shape. Product-specific tally parsing in the plane was removed.

## Decision

### D1. Test runs are recorded

Test runs go through a plane command that records start, end, counts and exit code.

### D2. A JSON result

A gate may write a JSON result to a path the plane provides; when valid it is the run's record.

### D3. Standard defaults only

Output parsing defaults to the standard library test runner only; a product's test cache stays in the product.

### D4. Generic counters

Counters are generic (ran, cached, skipped, failed), in the product's own unit.

### D5. Opt-in cache acceptance

A product may let the verifier accept its cache hits, with reviewers checking them.

## Consequences

- Any test runner can report to the plane.
- Products with a custom tally either write the JSON or configure regular expressions.
