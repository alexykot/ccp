# Review points: design notes

Non-normative notes behind SPEC §22.

- **Built in** `ccp/reviewpoints.py` (the register, `problem()`, list, tag, migrate) and
  `ccp/backfill.py` (the backfill).
- **Why the backfill and `tag` write the working tree only.** `close`'s path checks out the
  integration branch detached in a clean runner worktree, commits and pushes: right for one task
  after its merge, wrong for a one-off edit to many task files that the lead should read first. So
  they refuse a target with uncommitted changes, write `review_point: R` as the frontmatter's last
  line with `close`'s own helper (`lifecycle.stamp_review_point`: CRLF kept, every other byte
  kept), run `ccp tasks check` before and after, commit nothing, and print the exact
  `git commit -- <files>`. The backfill's dry run prints
  `task -> point (claim time and source; how: spawn time, scope hit)`; `--json` gives the whole plan.
- **The backfill's log source.** `reconcile.log.entry`'s first line becomes a pattern with the
  other fields loose; a matching entry is what `close` wrote then, the same value it stamps today.
- **Two regimes keep a release safe.** Without a register everything behaves as before it (the same
  messages and exit codes, spawn's warning rather than a refusal) plus one warning per command
  (`reviewpoints.notes`), so the plane can ship before a product migrates. A product's checks turn
  strict the moment it commits the register, so it writes the register and migrates in one sitting.
  A test runs a product with an older point name, a widened pattern and no register through
  `ccp tasks check` and `ccp docs check`: exit 0, one warning each.
- **`migrate` keeps history.** The ledger's spawns and the product log keep the old name; the
  backfill reads it as the new id through the `runner`/`set` event `migrate` records.
- **Board rendering.** The Queue tab's *Review points* card lists the points newest first, the
  current one marked (id · name, the goal truncated with the whole on hover, status, done/total,
  open, opened and closed, falling back to the first and last done task). The header's Now line reads
  `R<n> · <name>`. Every register string goes through `esc()`, and the node render test makes each
  one hostile.
- **Longer notes.** `--note-file` is read as UTF-8, stripped, with the same 4000-character cap and
  the same rendering as `--note`; both refuse a value `health.looks_like_secret` flags. The prompt
  audit's `notes` takes the text either way.
- **Why `prompts.worker_env` is a rendered file** rather than values `ccp suite run` exports: the
  worker's commands outside the suite (the product's helpers, its CLI) need them too, and Claude
  Code's Bash tool keeps no environment between calls. The file is plain `export NAME='value'` lines
  (`shlex.quote`), so `. file && cmd` works in sh and zsh; sourced before `ccp suite run`, its child
  inherits them. A typical need: a fresh git clone has no `.env` of its own and no main checkout to
  fall back to, so a product helper needs a variable naming the main checkout's env file.
