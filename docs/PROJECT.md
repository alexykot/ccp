# CCP — Claude Control Plane

## Goal

A project-agnostic control plane for multi-agent software delivery with Claude Code, aiming at
**L4.5 autonomy**: between L4, where a human writes the specs and checks the outcome, and L5, the
"dark factory" with no human in the loop. It takes a feature from its definition to production. A
Claude agent team does the work: a lead (design seat), runner teammates and worker subagents. They
break the work into tasks and implement, review, verify, merge and, by default, release it.

A developer stays in the loop as the operator. They set the direction, turn business requirements
into ADRs with the design seat, hold the architectural vision and, in rare cases, look at a
specific piece of logic. They are the escalation point, not the reviewer of each change.

Today the plane stops at the integration branch: production promotion is an operator gate
(SPEC §3.4). Releasing by default is the target, and it needs its own SPEC change.

## Assumptions

- Claude Code is the interface: every seat is a Claude Code session, teammate or subagent.
- Claude is the target model.
- One operator runs the plane on their own machine, and relies on Claude Code's permission controls
  to keep agents in check.

## Why

Agent teams lose discipline without structure: duties that live only in prompts decay, review and
verification blur, and nobody owns the whole. The plane makes the delivery mechanics explicit:
canonical formats (task files, ADRs, house rules), a runtime queue with leases and gates, recorded
runs and telemetry, and checks that hold every change to the same standard. That structure is what
lets the developer step back from each change without losing control of the product.

## Non-goals

- Product code, domain logic or product-specific tooling: a product supplies those through config
  and hooks.
- Replacing the developer's judgement on intent and architecture: the operator remains the
  escalation gate for those decisions, credentials, spend and irreversible operations.
- Hosting agents itself: seats run in Claude Code.
- Other agent harnesses or model providers, for now.

## Success

- A new product adopts the plane with a `plane.json`, its hooks and the plugin, and no plane change.
- Every change to a managed product is claimed, implemented, reviewed, verified against its checks
  and merged through `ccp`, with its time, tokens and outcome recorded.
- A verified change reaches production with no human step, by default, in a product that has a
  production.
- The plane manages its own development the same way, and is published as open source.
