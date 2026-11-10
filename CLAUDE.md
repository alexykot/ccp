# CLAUDE.md

For Claude Code sessions that develop CCP (Claude Control Plane) itself: this repo and its CLI, `ccp`.
`README.md` covers the layout. `SPEC.md` is normative. `docs/ROADMAP.md` holds the plan and what is
done.
Operator-specific instructions, if any, are in `CLAUDE.local.md` (gitignored, never committed).

## Checkouts and releases

There are two clones, side by side:
- **The dev checkout** (this repo's main worktree) stays on `main`.
- **The run checkout**, `../control-plane-run`, is the clone that `ccp` on PATH and the plugin run
  from. It also keeps the local, unversioned `projects/` bindings, which are gitignored.
- **Plane sessions** load the plugin from the gitignored `.claude/settings.local.json` (the marketplace
  anchor and `enabledPlugins`); the committed `.claude/settings.json` carries no repository anchor.

Rules:
- **Never `git checkout`, edit or commit in either clone.** Develop in a worktree:
  `scripts/dev-worktree.sh <branch>`. The pre-commit hook refuses commits on `main`; install it once
  per clone with `scripts/install-git-hooks.sh`.
- **A merge to `main` is a release.** After merging, run `scripts/release.sh <worktree>` from the
  dev checkout or a worktree of it, never from the run checkout. Removing the worktree removes the
  session's cwd if the session was in it. It:
  - fast-forwards the dev checkout;
  - moves the run checkout and restarts the telemetry receiver;
  - checks each bound product's integration branch against the new rules and prints what went
    stale (SPEC §29.3): tell that product's lead;
  - checks that the receiver is up;
  - removes the worktree.
- **The telemetry receiver can't be restarted from inside Claude Code.** If `release.sh` reports it
  down, the operator restarts it from a normal terminal.
- **Plugin changes** (agents, hooks, orientation) reach a product's lead only at its next session
  start.

## Rules

- **Review before merge.** Every PR gets an independent review by a fresh subagent. Give the
  reviewer the code and the intent, not your conclusions. Auto mode blocks a merge it sees as
  unreviewed: then open the PR, report it, and let the operator merge.
- **SPEC §31:** a change to a § rule needs the operator's approval. The PR body states each change
  and the text it replaces. Non-normative notes need no approval, and neither does text that only
  describes an accepted task's own feature (§31.1); a new rule beyond the task's intent still does.
- **Tests are fenced** (`tests/__init__.py`): no live queue, no real plane repo, no GitHub.
  - Run the full suite: `python3 -m unittest discover -s tests -t .`.
  - Afterwards, `git branch --list 'state/*'` must print nothing.
- **Never write to a managed product's queue or repo.**
  - Reading them is fine.
  - Changes go to the product's lead as a prompt.
  - The one exception is triage: plane proposals from a product (`plane/proposals.jsonl`) are
    triaged and recorded by the plane session with `ccp plane triage` (SPEC §31.5). The lead is
    told the outcome, never asked to record it.
- **Telemetry carries numbers and ids only.** The receiver keeps a whitelist of fields.
  - Never add prompt, response, command or file content.
  - Keep `OTEL_LOG_USER_PROMPTS` and `OTEL_LOG_TOOL_DETAILS` unset.
- **Headless children** strip `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN`.
- **Git hygiene:** stage only the paths you touched (never `git add -A`), and push immediately.
- **No product specifics in this repo:**
  - No managed product's names, ids, paths, data or rulings in code defaults, SPEC text, docs,
    commit messages or PR titles.
  - Rules are written generically, with knobs that have neutral defaults.
- **Write it down.** Durable knowledge from a session goes into the docs, the SPEC or the roadmap, in
  the same PR as the work, never only in chat.
