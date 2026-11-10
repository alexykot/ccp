# CCP — Claude Control Plane

A delivery control plane for software products built by a **Claude Code agent team**.

> **Status: experimental.** CCP is built and run by one operator on macOS, with Claude Code's
> experimental agent teams. It works for that setup daily; expect rough edges elsewhere. Open work
> is in [docs/ROADMAP.md](docs/ROADMAP.md).

CCP solves the problem of agent supervision: having to babysit individual agents implementing
specific tasks.

CCP creates a team of agents with the design seat (the lead) at the top. The operator (the human)
works with the design seat to prepare a set of changes, defined as ADRs. The design seat turns the
ADRs into tasks, defines their dependencies, and spawns runners, who in turn spawn implementation,
review and verification agents.

The babysitting — providing the next prompts, answering small queries, clarifying the spec and
minor implementation issues — is done by the design seat without the operator's attention. Problems
the design seat cannot resolve are raised back to the operator, with options and a recommendation
for each.

You keep a product's intent in the product's own repository: what to build, and the tasks that get
it there. The plane runs the loop that turns each task into a reviewed, verified, merged change:
claim, worktree, implement, review, verify, merge, close. It records every step in a local queue, so
the team's state survives restarts. Questions the team cannot settle from the docs go to the
operator (you) as recorded gates.

It has two parts:
- **`ccp`**, a command-line tool that runs from your clone of this repository;
- a **Claude Code plugin** that gives the team its agents, skills and hooks. Claude Code installs it
  from the GitHub marketplace entry, not from your clone.

**It is for** people running long-lived products with Claude Code who want a repeatable delivery
loop with separation of duties. These are done by separate, dedicated roles:

- product design and specification oversight (the design seat);
- architecture review and refactoring (the architect);
- task implementation;
- code review;
- verification.

So the product designer doesn't run out of context after a single task, the implementation agent
doesn't approve its own work, architecture smells are addressed as they appear, and work can
continue around the clock with attention needed only at the critical points.

**It is not** a CI system, a hosted service, or a framework your code depends on. The product holds
only documents and one settings entry. You are expected to bring your own CI system, appropriate
for your project, and connect it through the hooks a product provides (`docs.checks`,
`architect.checks`, `reconcile.hooks`, env hooks).

**It is** an agent orchestration system, designed to work with Claude Code, running on the
developer's machine.

**Terms.** A *seat* is a role in the team. The **lead** is your interactive Claude Code session in
the product: the design seat, which owns the task log and maintains the spec. A **runner** is a
teammate the lead spawns to drive tasks through the loop. The **architect** is an optional headless
pass that reviews the product's structure. The **operator** is you.

## Quick start

### Prerequisites

- `git`, with `user.name` and `user.email` set; the product is a git repository.
- Python 3.9 or newer (`ccp` uses only the standard library; on macOS the launchd services run it
  with the system `python3`).
- [Claude Code](https://docs.claude.com/en/docs/claude-code).
- **Claude Code agent teams**: experimental and off by default; CCP needs them. They are turned on
  with `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, which step 2 puts in the product's
  `.claude/settings.json`.
- The GitHub CLI `gh`, logged in (`gh auth login`): the runner merges through pull requests.
- macOS, only for the optional telemetry and board (local dashboard) services (they install launchd
  agents).

Replace `my-product` with your product's id.

### 1. Install `ccp`

```bash
PLANE=~/ccp
BIN=${BIN:-$HOME/.local/bin}          # any directory on your PATH
git clone https://github.com/alexykot/ccp.git "$PLANE"
mkdir -p "$BIN" && ln -sfn "$PLANE/bin/ccp" "$BIN/ccp"
ccp --help
```

Keep the clone on `main`; `ccp` warns when it is dirty, off `main`, or behind `origin/main`. To
upgrade, `git pull` the clone. The plugin updates itself from the marketplace (`autoUpdate` below),
or update it with `/plugin` in Claude Code; keep both on the same release.

### 2. Adopt a product

Run this from the root of the product's repository:

```bash
ccp init --project-id my-product --gate "python3 -m unittest discover -s tests"
```

In the repository it writes `docs/PROJECT.md` and `docs/SPEC.md` from the templates, the delivery
templates and a minimal `plane.json` in `docs/delivery/`, and `INDEX.yaml`. It adds `.plane-runtime/`
to `.gitignore`. It merges the plugin anchor into `.claude/settings.json`, leaving its other keys
alone:

```json
"extraKnownMarketplaces": {
  "ccp": {"source": {"source": "github", "repo": "alexykot/ccp"}, "autoUpdate": true}
},
"enabledPlugins": {"ccp@ccp": true},
"env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}
```

It appends one line to `CLAUDE.md`, once: "This repo is delivered by CCP (Claude Control Plane): its
plugin and `ccp`." Outside the repository it writes the binding, `$PLANE/projects/my-product.yaml`,
and creates the queue, `~/.delivery-queue/my-product/` (`--queue-root` picks another).

- Put your own test command in `--gate`; the example is Python's.
- It never overwrites a file without `--force`: it keeps the file and lists it as kept, so running it
  again is safe.
- The binding is the one place for the product root, the queue and the runner: edit it there, and
  `ccp`, the team scripts and the hooks all read the change. `ccp where` names it.

### 3. Write a first task and check

This first task passes the checks as written (the heredoc escapes its backticks). Edit its text to fit your product, or copy
`docs/delivery/TEMPLATE-task.md` and replace every placeholder (`task_id`, the `# Task:` heading,
`title`, `spec_refs`, cited in the text, `created`/`updated`, Scope, each dod_check).

```bash
cat > docs/delivery/tasks/0001-smoke-test.md <<EOF
---
task_id: 0001-smoke-test
title: Add a smoke test the gate can run
status: pending
kind: feature
depends_on: []
spec_refs: ["docs/SPEC.md#overview"]
paths: ["tests/"]
created: $(date +%F)
updated: $(date +%F)
---

# Task: 0001-smoke-test

## Intent

The product has a test suite: the gate lane finds and passes at least one test.

## Context (not checked)

- Grounds the gate for every later task (docs/SPEC.md#overview).

## Scope

- **In:** one test under \`tests/\`.
- **Out:** product behaviour.

## dod_checks

- id: \`test-01\`
  story: As a developer, I run the gate and it passes.
  setup: a checkout of the change.
  steps:
    1. Run \`python3 -m unittest discover -s tests\`.
  expect: it prints \`OK\` after running at least one test.
  dry run: n/a — no tests exist yet.

## Implementation notes

*Append-only, newest last.*

## Verification notes

*Append-only.*
EOF
ccp tasks index      # writes docs/delivery/INDEX.yaml
ccp tasks check      # the task log is well formed
ccp docs check       # package-doc rules and the task log
ccp tasks next       # 0001-smoke-test
ccp where            # the binding and queue ccp resolved
git add docs .claude CLAUDE.md .gitignore && git commit -m "Adopt CCP"
```

### 4. Start the team

Open Claude Code in the product repo. The plugin orients the session as the lead. The lead starts a
runner with:

```bash
QUEUE_ROOT=~/.delivery-queue/my-product ~/ccp/scripts/team.sh runner spawn --scope 0001-smoke-test
```

It prints the Agent tool call to make. The runner claims the task, has subagents implement, review
and verify it, merges it through a pull request, and closes it.

Optional, macOS only (each writes a launchd agent to `~/Library/LaunchAgents`):
- `ccp otel install` runs the telemetry receiver; put the block that `ccp otel env` prints into your
  user settings (`~/.claude/settings.json`), not the product's.
- `ccp board install` keeps a static board at `$QUEUE/board/index.html`.

## How it works

```
ccp repo                  product repo (git)          local, outside git
──────────────────        ──────────────────          ──────────────────────────────────────
ccp                       docs/PROJECT.md             $PLANE/projects/<id>.yaml   binding
plugin/  agents, skills,  docs/SPEC.md                ~/.delivery-queue/<id>/     queue: leases,
         hooks            docs/adr/                                               runs, verdicts
docs/spec/  the rules     docs/delivery/              <product>/.plane-runtime/   worktrees
templates/                  plane.json, tasks/,       ~/.local/state/control-plane/  telemetry
                            INDEX.yaml
.claude/settings.json ──▶ loads the plugin
```

### Seats

| Seat | Does | Never |
|---|---|---|
| **Lead** (design seat) | Writes intent, specs and tasks; starts runners; asks the operator | Implements tasks |
| **Runner** (teammate) | Claims tasks, drives each through the loop, merges, closes | Writes product code or verdicts |
| **Implementer, reviewer, verifier** (subagents) | Write the change; review it; run the gate on the exact commit | Judge their own work |
| **Architect** (headless, optional) | Reviews structure — house rules, budgets, drift — when `ccp architect` runs; its report goes to the lead for triage. Scheduled passes are on with the `architect` block; `ccp architect run --force` works without it | Changes code or the task log |
| **Operator** (you) | Rules on escalations, approves rule changes, merges when policy requires | Is asked what the docs already answer |

### The split

The plane owns **formats, lifecycles and mechanisms**: the task format, leases, the verdict log,
worktrees, merging, telemetry. The product supplies **content, config and hooks**: its docs, its
tasks, its test command, its environment scripts. The plane reads structured fields, never prose.
Knowledge lives in git; live state lives in the queue. Tooling that is specific to one product stays
in that product (SPEC §31.4).

### What a product provides

- `docs/PROJECT.md` (purpose, users, constraints) and `docs/SPEC.md` (what to build).
- Tasks in `docs/delivery/tasks/NNNN-slug.md`, in the canonical format: frontmatter plus intent,
  scope and `dod_checks`. Statuses are `pending`, `done` and `dropped`.
- `docs/delivery/plane.json`. Only `project_id` is required; unknown keys are refused. Optional
  blocks:
  - `suite.lanes`, the test commands; a gate may write `$CCP_SUITE_RESULT`;
  - `worktrees`, with `env.setup`, `teardown`, `up`, `down` and `urls` hooks;
  - `docs.checks`, `architect.checks`, `auth_check.probes`;
  - `merge.command`, `adr`, `review_points`, `parallel`.

  See SPEC §8.1 in [`docs/spec/01-model.md`](docs/spec/01-model.md).

### Where files go

| Path | In git | What |
|---|---|---|
| `<product>/docs/delivery/` | yes | `plane.json`, tasks, `INDEX.yaml`, review points |
| `<product>/.plane-runtime/` | no (gitignored) | worktrees for implement, review and verify |
| `$PLANE/projects/<id>.yaml` | no (gitignored) | the binding: product root, queue, runner |
| `~/.delivery-queue/<id>/` | no | the queue: leases, runs, verdicts, the board |
| `~/.local/state/control-plane/` | no | telemetry: numbers and ids only, never content |

## `ccp` in brief

| Command | What it does |
|---|---|
| `ccp init` | Adopt a product: its docs, `plane.json`, the plugin anchor, the binding and the queue |
| `ccp tasks list` · `next` · `check` · `index` | List the backlog, pick the next task, validate the log, rebuild `INDEX.yaml` |
| `ccp tasks claim <task>` · `close <task> --pr N` | Take a task's lease; close it after merge |
| `ccp tasks prefer` · `hold` · `release` · `drop` | Steer the order; pause, free or drop a task |
| `ccp tasks estimate` | Size a task for the forecast |
| `ccp prompt implement\|review\|verify\|fix <task>` | Print the brief for a seat |
| `ccp report <run_id> <file>` | Record a seat's report |
| `ccp verify record\|merge-ok\|check <target>` | Record a verdict bound to a commit; check it allows a merge |
| `ccp suite run --lane gate -- <cmd>` | Run a test lane and record time, exit code and test count |
| `ccp wt create\|up\|urls\|remove` | Manage worktrees and their environments |
| `ccp docs check` | Package-doc rules and the task log |
| `ccp adr new\|status\|decide\|supersede\|check` | Write and maintain ADRs |
| `ccp architect` · `ccp review-points list` | Architecture passes; the review-point register |
| `ccp board build\|status\|install` | The static board |
| `ccp allowance status` · `ccp forecast` | Usage windows; forecast a review point or the backlog |
| `ccp plane propose --need … --generic …` | Propose a missing plane tool instead of writing one |
| `ccp otel install\|status` · `ccp where` | Telemetry receiver; show the resolved binding |

Other groups, among them `estimate`, `health`, `auth`, `budgets` and `runs`, are in the full
reference, [`docs/cli.md`](docs/cli.md). `ccp <command> -h` is authoritative for flags.

## Documentation

- [`SPEC.md`](SPEC.md) leads to the normative rules in [`docs/spec/`](docs/spec/).
- [`docs/adr/`](docs/adr/): the standing decisions.
- [`docs/design/`](docs/design/): design notes per subsystem.
- [`docs/ROADMAP.md`](docs/ROADMAP.md): the plan and what is done.
- [`CLAUDE.md`](CLAUDE.md): how to develop CCP itself. CCP manages its own development:
  see [`docs/delivery/`](docs/delivery/).

## License

MIT — see [`LICENSE`](LICENSE).
