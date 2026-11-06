# CCP — Claude Control Plane

## Goal

A project-agnostic control plane for multi-agent software delivery with Claude Code. It turns a
product's durable task log into delivered, reviewed, verified and merged changes, run by a Claude
agent team: a lead (design seat), runner teammates and worker subagents. The operator steers and
approves; the plane does the rest.

## Why

Agent teams lose discipline without structure: duties that live only in prompts decay, review and
verification blur, and nobody owns the whole. The plane makes the delivery mechanics explicit:
canonical formats (task files, ADRs, house rules), a runtime queue with leases and gates, recorded
runs and telemetry, and checks that hold every change to the same standard.

## Non-goals

- Product code, domain logic or product-specific tooling: a product supplies those through config
  and hooks.
- Replacing the operator's judgement: the operator remains the escalation gate for decisions,
  credentials, spend and anything irreversible.
- Hosting agents itself: seats run in Claude Code.

## Success

- A new product adopts the plane with a `plane.json`, its hooks and the plugin, and no plane change.
- Every change to a managed product is claimed, implemented, reviewed, verified against its checks
  and merged through `ccp`, with its time, tokens and outcome recorded.
- The plane manages its own development the same way, and is published as open source.
