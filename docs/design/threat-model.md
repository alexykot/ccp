# Threat model

Non-normative. This note says what the plane protects, what it leaves to Claude Code and the host,
and which of its controls hold against a seat that misbehaves. It states no rule: a rule it implies
goes through SPEC §31 first. Each control is named with the file or SPEC section that implements it,
as the code stands.

## Scope and assumptions

- **One operator, on their own machine.** The operator is trusted, and so are the host and its OS
  account. The queue is local files.
- **Anthropic models through Claude Code.** Every seat is a Claude Code session, teammate or
  subagent on a Claude model (SPEC §2). Claude Code's permission checks behave as documented.
  Other harnesses and providers are out of scope.
- **Current scale.** One product or a few per host, each with one lead and a few runners
  (SPEC §16).
- **Every seat runs as the operator's OS user**, with the operator's credentials: the forge login
  `gh` uses, the SSH keys, and the Claude login. Teammates and subagents share the lead's process.
  The plane adds no OS-level sandbox (`README.md`, "Current Assumptions").

Two kinds of control appear below:

- A **boundary** holds even when a seat tries to get round it: it is enforced outside the seat's
  session (by Claude Code's tool gating, by a separate process, or by the forge), and the seat has
  no tool that turns it off.
- A **guard** stops accidents and honest mistakes. A seat acting with the operator's rights can get
  past it, by another spelling of a command, by writing a file directly, or by running a script.

## Assets

- **The forge token** that `gh` and git use: it can write to every repository the operator can,
  including merging pull requests and deleting branches.
- **SSH keys** in the operator's home directory, with whatever hosts and repositories they reach.
- **Model credentials:** the Claude login that pays from the prepaid allowance, and the product API
  keys that pay from API credits (SPEC §30.2).
- **Product repositories and their integration branches**, and the pull requests that reach them.
- **Queue and verdict records** under each product's `QUEUE_ROOT`: the ledger, the verify records,
  the reports, the runs and the prompt audits (SPEC §23).
- **Other products on the same host**: their repositories, queues and bindings.
- **The operator's files**: the home directory, other checkouts, and secrets in `.env` files.

## Trust boundaries

- **Model to host: Claude Code's permission checks.** The only control between a seat's decision
  and the operator's rights is Claude Code's: a worker's tool allowlist (SPEC §2.4), the
  permission rules in the product's `.claude/settings.json` (SPEC §4.5) and the prompts that block
  in the lead's session for anything else (SPEC §18.5). The plane configures them; it does not add
  its own.
- **Host to forge.** The forge enforces what it is asked to: a merge pinned to a head, and any
  branch protection the operator sets. What a seat can do there is whatever the token allows.
- **Session to telemetry receiver.** Sessions export to a receiver on localhost, a separate process
  that keeps a fixed set of fields (SPEC §24.2).
- **Not boundaries.** There is none between seats (one OS user, and teammates share a process),
  between products on one host, between a seat and the queue files, or between untrusted text and
  a seat's context: issue and pull-request text, dependency docs, test output and fetched pages are
  read as they are.

## Threats and controls

### T1 Prompt injection

Text an agent reads carries instructions, and the agent acts on them with the operator's rights.

- **Guard:** worker tool allowlists in `plugin/agents/delivery-implementer.md`,
  `plugin/agents/delivery-reviewer.md` and `plugin/agents/delivery-verifier.md` (SPEC §2.4) leave
  out `WebFetch` and `WebSearch`; `Bash` still reaches the network.
- **Guard:** the reviewer and the verifier are fresh subagents with none of the implementer's
  context (SPEC §2.1, §2.3), so a change an injected implementer makes must pass two seats that did
  not read its session. They may still read the same issue or pull-request text.
- **Guard:** the architect runs headless with a read-only tool list and `DENY_TOOLS` disallowed
  (`scripts/observability/architecture_review.py`, launched by `ccp/architect.py`, SPEC §19.7). Its
  allowed `Bash` commands and the product's probes are prefix-matched, so it is not a boundary.
- **Boundary:** the estimator runs with no tools, in an empty temporary directory
  (`ccp/estimator.py`, SPEC §26.3): an injection in its prompt cannot read or write anything.
- **Gap:** nothing separates untrusted text from instructions for the lead, the runner or the
  workers, and nothing marks where text came from.

### T2 The gate runs untrusted code on the host

The gate, and every test a task adds, runs agent-written code, and the implementer runs it before
any review.

- **Guard:** each task's code runs in its own worktree (SPEC §12.1), so a stray write misses the
  main checkout. A worktree is a directory, not a sandbox.
- **Gap:** the gate runs as the operator's user, with every file, credential and network route that
  user has; there is no sandbox, container or separate user for it.

### T3 Destructive or escaping commands

A seat deletes work, rewrites history or reaches outside its worktree.

- **Guard:** the deny list `DENY` in `ccp/init.py`, which `ccp init --permissions` prints and the
  operator merges into the product's settings (SPEC §4.5). Its rules are prefix matches, and
  `README.md`'s Permissions section names spellings that get through.
- **Guard:** the allow list in the same block: a command it does not name prompts in the lead's
  session (SPEC §18.5). The gate lane's commands are allowed, and they run whatever the worktree's
  scripts say.
- **Guard:** each task in its own worktree (SPEC §12.1), and the integration branch reached only by
  a merge (SPEC §15.5).
- **Gap:** no OS sandbox catches another spelling of a denied command, a script that runs one, or a
  write outside the worktree.

### T4 Forged or tampered evidence

A seat writes a verdict, a test result or a report that no seat produced, or edits one.

- **Guard:** `ccp verify record` holds a verdict to its contract and refuses evidence a seat that
  rules on the task produced (`ccp/verify.py`, SPEC §2.3, §15.4); test runs are recorded by
  `ccp suite run` (`ccp/suite.py`, SPEC §14), and the verifier runs the gate itself (SPEC §15.1).
- **Guard:** provers and `verify.skip_review` are read from the integration branch and run from the
  tip's checkout (SPEC §14.2, §15.2), so a task's diff cannot change its own verdict.
- **Boundary:** the merge is pinned to the verified head with `--match-head-commit`
  (`ccp/lifecycle.py`, SPEC §15.5): the forge refuses it when the head moved after the verdict.
- **Gap:** every seat can write the queue as the same OS user, so a verdict, a ledger line or a
  report can be written without `ccp`; the ledger is append-only by convention (house rule E7 in
  `docs/ENGINEERING.md`), not by protection.

### T5 Exfiltration over the network

A seat sends code, records or secrets to a host it should not reach.

- **Guard:** workers have no `WebFetch` or `WebSearch` (SPEC §2.4), and the architect has them
  disallowed (`scripts/observability/architecture_review.py`).
- **Guard:** no product API key is ambient (SPEC §30.3), so a seat's environment holds less to send.
- **Gap:** the network is unrestricted: `Bash` can reach any host, and git and `gh` push with the
  operator's token to any remote it reaches.

### T6 One product's agents reaching another product

A seat working on one product reads or writes another product's repository or queue.

- **Guard:** each product has its own binding, queue and worktrees (SPEC §4.2, §8.3), and the
  permission block `ccp/init.py` prints names only that product's queue root.
- **Gap:** the same OS user, forge token and SSH keys reach every product on the host; nothing
  confines a seat to its own product's paths.

### T7 Telemetry leakage

Prompt, response, command or file content leaves a session through telemetry or records.

- **Boundary:** the receiver keeps only the fields in `REQUEST_FIELDS` and `SPAN_FIELDS`
  (`ccp/otel.py`, SPEC §24.2). It is a separate process bound to localhost, and it drops anything
  else a session sends.
- **Guard:** `ccp otel status` warns when `OTEL_LOG_USER_PROMPTS` or `OTEL_LOG_TOOL_DETAILS` is set
  (`CONTENT_KEYS` in `ccp/otel.py`), since Claude Code would then export content.
- **Guard:** prompt audits keep ids, the prompt's hash and its length, and no key or `.env`
  content (SPEC §23.8); a product can turn on `prompts.keep_body` (`ccp/config.py`, off by
  default) to keep the full text.

### T8 Credentials in headless children

A `claude -p` the plane launches picks up an API key and spends API credits, or exposes the key.

- **Boundary:** `STRIP_KEYS` in `scripts/observability/spec_maintainer.py`: the architect
  (`ccp/architect.py`) and the estimator (`ccp/estimator.py`) launch `claude -p` with
  `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY` and `ANTHROPIC_AUTH_TOKEN` removed from its environment
  (SPEC §30.3).
- **Guard:** the product's credential probes, `auth_check.probes`, run before each claim and can
  check that no key is ambient (SPEC §30.1); they check only what the product declares.
- **Gap:** the lead, its teammates and their subagents are not launched by the plane: they get the
  environment the operator started the lead with, and the plane strips nothing from it.

### T9 Unreviewed reach to production

A change reaches production without review, or a seat promotes it.

- **Guard:** promotion is an operator gate, never automated (SPEC §3.4); the implementer must not
  promote (SPEC §2.1), and the plane has no deploy or promote step.
- **Guard:** a pull request merges only on the verifier's approve at its head
  (`ccp verify merge-ok`, `ccp/verify.py`, SPEC §15.5).
- **Gap:** nothing stops a seat that holds the operator's deploy credentials from running a
  product's deploy command; the control is that the plane has no such step, not that a seat cannot.

## Accepted risks

A single-operator install accepts these gaps:

- **T1, injection:** the operator is the escalation point and reads the board; filtering untrusted
  text is not something Claude Code offers a seat today.
- **T2, the gate on the host:** the gate runs the operator's own product code on the operator's own
  machine, as a developer's tests would.
- **T3, destructive commands:** work lives in git and on the forge, so a lost worktree costs a
  rerun; the deny list stops the common accidents.
- **T4, queue writes:** every seat acts for the one operator, and a forged record would show as a
  ledger and verify record that disagree with the forge's merge history.
- **T5, the open network:** the seats need the forge, package registries and the model provider,
  and an allowlist would have to be kept by hand on one machine.
- **T6, other products:** one operator owns every product on the host, so a crossing harms no other
  owner.
- **T8, the lead's environment:** the operator starts the lead, and SPEC §30.3 keeps API keys out of
  that environment.
- **T9, deploy credentials:** the operator decides which credentials the host holds.

## What a shared install needs

Several operators, or other people's products, on one host would need at least:

- **Per-product scoped forge tokens**, so a seat can write only its own product's repository:
  `docs/ROADMAP.md`, "Seat isolation (later)".
- **Sandboxed command execution**, Claude Code's command sandbox or a container per worker:
  `docs/ROADMAP.md`, "Seat isolation (later)".
- **A network allowlist** for the seats and the gate: `docs/ROADMAP.md`, "Seat isolation (later)".
- **Queue write protection**, so only `ccp` can write a verdict or a ledger line:
  `docs/ROADMAP.md`, "Store" (a hosted backend behind the `Store` interface).
- **A separate OS user or VM per product**, so one product's seats cannot read another's files:
  `docs/ROADMAP.md`, "Seat isolation (later)".
