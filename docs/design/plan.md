# The plan and backlog: design notes

Non-normative notes behind SPEC §22.9–§22.10.

- **Built in** `ccp/adr.py`, `ccp/plan.py` and the board page's Plan and backlog section.
- **One selection.** `ccp/selection.py` reads the queue's inputs (the default scope, the review
  point's refactors, the lead's preference), and `tasklog.ranked` orders the ready tasks. `next`
  returns row 0, and `next_task` is row 0 with no preference. Sharing it is why `next` gained a
  `why:` line for a refactor made due by `refactor_every` (before, that pick had `"why": null`).
- **ADRs** were first read through a one-off importer of an older header format,
  `ccp docs adr convert`, since retired (§6).
- **Review points before the register.** `team.sh runner spawn` makes the same pattern check as
  `close` (`lifecycle.review_point_problem`).
- **Cost.** On a scratch copy of a product with a few hundred tasks and a few dozen ADRs, the plan
  adds roughly 140 KB to `board.json` and the build stays under 3 seconds.
- **Robustness.** Each section renderer (seats, quality, plan, and within it the burn-up and the
  graph) runs inside `safe()`, so a renderer that throws shows its own "section failed" banner and
  the rest of the page renders. Every task and ADR string is rendered through `esc()`; the node
  render test makes every string hostile and covers the whole section. A part that fails leaves its
  error under `plan.errors`, the page shows it, and the rest builds.
