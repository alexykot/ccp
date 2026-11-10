# Part V — Operations

How the plane is released and run, how credentials are kept apart, and how its own rules change.

## 29. Releases and the run checkout

ADR-0023 and ADR-0024 carry the reasons.

### 29.1 Merged is released

- Products run the plane's `main`. There is no separate stable branch and no second promotion step:
  the gate is the pull request — the suite green, an independent review, and the operator's recorded
  approval for any change to a § rule (§31.1).
- A rollback is a revert pull request on `main`, then a release (§29.2). Products run `main`; there is
  no plane pin.

### 29.2 The run checkout

- The run checkout is a clean clone of the plane that tracks `origin/main` and is moved only by
  `git pull --ff-only`. `ccp` on PATH is a link to its `bin/ccp` (`scripts/run-checkout.sh install`); the bindings and headless runs
  (`--plugin-dir`) name it. Its path is a knob (§29.5).
- No one develops in the run checkout. Development happens in the development clone and its
  worktrees, which no product runs.
- **After a merge** the plane session runs the release, which pulls the run checkout. `ccp` warns on
  stderr when the run checkout has local changes, is not on `main`, or is behind `origin/main`.
- The per-product bindings (`projects/<project_id>.yaml`) are local and gitignored in the run
  checkout; a release never loses them.

### 29.3 Compatibility across a release

A release can land while a task is in flight, so:

- Runtime formats (queue files, run records, events, reports) only gain optional fields. A change
  beyond that carries a `schema_version`, and the new code still reads the old version.
- `plane.json`'s schema only gains optional keys.
- A release that changes the runner's contract (its brief, or what a command expects of it) says so
  in its pull request and is followed by a runner rotation in each live product, because workers'
  prompts render per launch while the runner's brief loads at spawn.

### 29.4 `ccp` on PATH

- Templates, briefs, prompts and product docs say `ccp`, never a path to the plane. `ccp prompt` and
  the agent definitions do not print the plane's path.
- `.control-plane/` and the old `vendor` command are retired: no product carries a vendored copy of
  the plane.

### 29.5 Knobs

| Knob | Default |
|---|---|
| The run checkout's path (`CCP_RUN_CHECKOUT`) | `control-plane-run` beside the development clone |
| The prefix of the plane's launchd labels (`CCP_LAUNCHD_PREFIX`) | `dev.ccp` (`<prefix>.control-plane.otel`, `<prefix>.control-plane.board.<project_id>`) |
| A product's marketplace `autoUpdate` | `true`; a product may set `autoUpdate: false` and update the plugin by hand |

## 30. Security: keys and wallets

ADR-0026 carries the reasons.

### 30.1 Credential checks

- The product declares its credential checks as `plane.json` `auth_check.probes` (`[{id, cmd}]`;
  exit 0 means the credential works; a probe never prints a secret). They run before each new task.
- `ccp tasks claim` runs the probes before each new task and refuses with exit 8 when one fails: no
  task is taken, and the runner raises it to the lead as a `reauth` gate. `ccp auth check` runs them on
  demand.
- The status is kept in the runtime `auth/status.json`; a probe's output is withheld when it looks
  like a credential.
- An expired credential sets `waiting_on=reauth`, raised to the lead.
- The plane checks only what a product's probes check, so a product's probes should cover both the
  Claude login (valid) **and** forbidden ambient API keys (absent from the checked shell and the
  `launchctl` environment). An ambient key present means `degraded` (or delivery launches fail) until
  it is cleared; it is never "auth OK for implement".

### 30.2 Two wallets

| Wallet | Pays for | Allowed |
|---|---|---|
| **Prepaid Claude allowance** (CLI login / subscription quota) | Implementer `claude -p`, same-session `/mk-pr`, a clean `/review`, fix loops | **Development only** |
| **API credits** (`ANTHROPIC_API_KEY` and similar) | The product's own runtime model calls (app, staging) | **Product only** — never Claude Code or `claude -p` |

### 30.3 No ambient keys

- Product API keys never live in the user's `launchctl` environment, login-shell exports, or any
  ambient environment that agent shells inherit. They reach the product only through process
  configuration the product loads (for example an app's `.env`), never exported for the whole user
  session.
- **Launch hygiene.** Before every Claude Code launch, the plane strips `ANTHROPIC_API_KEY`,
  `CLAUDE_API_KEY`, `ANTHROPIC_AUTH_TOKEN` (and equivalents) from that process's environment, so the
  CLI uses the prepaid login. Automation never relies on an interactive "use custom API key?" prompt.
- **Misuse, or credit running low on the API pool during CLI work:** set `waiting_on=quota` (or
  `operator_decision`), stop retrying, and raise it to the lead as a gate, without secrets.

## 31. Governance: SPEC changes, ADRs and tool proposals

### 31.1 Changing the SPEC

A change that adds, changes or retires a § rule reaches `main` as a pull request, never as a direct
push, and merges only with the operator's approval recorded in the pull request. The PR body names
the decision it implements (the operator's words and the date) and, for each changed rule, the
text it replaces. ADR-0024 and ADR-0030 carry the reasons.

### 31.2 ADRs

Standing decisions are ADRs in the format of §6.

### 31.3 No local automation

This rule is in every seat brief and in the plugin's orientation (§9).

- **No seat writes an executable file to automate a plane step**, whether in the queue, the product or
  anywhere else. Product helpers belong in the product repository, reviewed as product code, and are
  called through an env hook (§12) or `reconcile.hooks`.
- There is **no settings deny** on the queue's `scripts/`.
- **Checks:**
  - The board warns of an unknown or drifted file in `QUEUE_ROOT/scripts/`.
  - `ccp tasks claim` prints the same warning on stderr, so the runner sees it on its next task.

### 31.4 Proposing a tool

- **Plane or product? Decide before proposing.** A need belongs to the plane only if **any product
  would need it, whatever its language, domain or conventions**: the delivery mechanisms the plane
  owns (lifecycle, queue, records, gates, prompts, and the formats of §5–§7). Everything else is
  product work: built in the product repository, reviewed as product code, wired in through
  `docs.checks` (§21), an env hook (§12), `architect.checks` (§20) or `reconcile.hooks`, and written
  as a product task by the product's lead. **It is never a plane proposal.**
  - *Plane:* a lease or claim rule every runner hits; a field a verdict record cannot express for
    any product; a gate or prompt step every task goes through; a check over a plane-owned format.
  - *Product:* a lint over the product's own writing conventions; a tool over its data, stores or
    domain; a prover for its language; a check over its own directory layout or runtime files.
- **When a seat needs a plane tool `ccp` does not have, or a change to one, it proposes it:**
  `ccp plane propose --need "…" --generic "<why any product needs this>" [--task <id>] [--workaround "…"] [--frequency per-task|per-run|once]`.
  `ccp` refuses a proposal without `--generic`. This appends to `QUEUE_ROOT/plane/proposals.jsonl`
  and emits `plane/proposed`.
- Until the tool exists, the seat does the step by hand and records each repeat with
  `ccp plane propose --again <id>`, so the cost shows.
- A proposal untriaged for 7 days is flagged: `ccp plane list` and the board mark it `stale`. Its age
  counts from its last `--again` or its creation, whichever is later.

### 31.5 Triage

- **The plane session triages.** The session that develops the plane reviews each proposal, takes the
  decision to the operator where it needs them, and records it itself with
  `ccp plane triage <id> --accept|--merge-into <id>|--decline --reason "…"`, whose actor is
  `plane-session` (a non-seat actor beside `operator` and `system`).
- The triage — its row in `plane/proposals.jsonl` and its `plane/triaged` event — is the one write a
  plane session makes to a product's queue.
- An accepted proposal becomes plane work. Anything that changes a § rule goes to the operator
  (§31.1).
- The product's lead is told the decisions and what changes for the product; it does not record them.
