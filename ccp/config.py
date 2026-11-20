"""The product root and its `docs/delivery/plane.json` (SPEC §8.1).

The file is product-owned: it travels with the code it describes, so a worktree or a verifier
checkout needs nothing from the queue. Its presence is the opt-in — a product without it has
not adopted `ccp`, and every command says so rather than guessing. Every key but `project_id` and
`language` has a plane default; a block that is absent means "use the defaults", and `"architect": false`
is the one way to turn the architect seat off (§19.11). The package-doc checks
follow `language`: a pack turns them on, with the `package_docs` block's settings or its defaults,
and `none` turns them off. A command that needs the language and finds it unset warns during the
grace release (`REQUIRED_KEYS_GRACE`) and behaves as before; after it, it refuses (`require_language`).
`suite.lanes` must name the gate role's lane: `ccp tasks claim` and `ccp tasks next` ask
`require_gate_lane`, which warns the same way during the grace release and refuses after it.
The `architect` block is checked value by value as well as key by key: it drives a gate at
`ccp tasks next`, so a wrong type must fail loudly rather than turn the gate off.
"""
from __future__ import annotations

import copy
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp import models as role_models
from ccp import refs

CONFIG_REL = "docs/delivery/plane.json"

TASK_LOG_DEFAULTS: dict[str, Any] = {
    "dir": "docs/delivery",
    "required": ["task_id", "title", "status", "depends_on", "spec_refs", "created", "updated"],
    # At least one of these must be non-empty: a task that cites nothing is not traceable.
    "refs_any": ["spec_refs"],
    # SPEC §5: the canonical sections, required by default; a product may require more.
    "sections": ["Intent", "Context (not checked)", "Scope", "dod_checks",
                 "Implementation notes", "Verification notes"],
    # SPEC §5.5, §20.4: per kind, the ref lists it cites one of (`refs_any`, default the task log's)
    # and the ones it leaves empty (`forbid`). Read with the architect seat on, for tasks from its adoption point.
    "kinds": {"feature": {}, "refactor": {"refs_any": ["rule_refs", "review_refs"],
                                          "forbid": ["spec_refs", "adr_refs"]}},
    # Shaping records (`sh-*.md`) and triage records, under `dir` (§19.6).
    "reviews_dir": "reviews",
    "max_checks": 6,
    "soft_words": ["should", "may", "might", "as appropriate", "gracefully", "robust", "robustly"],
    # SPEC §5.7: INDEX.yaml is the product's choice. Its format is frozen; with false there is none.
    "index": True,
    # SPEC §10: a not-done task's check that runs a command records its
    # writer's dry run, or says why there is none. Off unless the product turns it on.
    "dry_run": False,
}
# SPEC §3.5, §26.3: the top-level `spec_paths`, the paths that hold the SPEC (a path ending in `/` is a
# directory). A task not yet done whose `paths` name one, with no `brief` sign-off and no `§31.1` in its Scope,
# is warned about; the estimator reads the directories as their `*.md`.
SPEC_PATHS_DEFAULT: tuple[str, ...] = ("docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/")
OPTIONAL_TOP_KEYS = ("spec_paths",)
# SPEC §16.2: several tasks in flight under one runner; 1 is one task at a time. `shared` lists the paths
# tasks only append lines to: they keep no two tasks apart (§16.3 rule 3), and close's catch-up merges their
# appended lines (§16.5 rule 4). `schedule` picks claim rule 3 (§16.3): `clashes` (the default) keeps apart
# only tasks that clash (`clashes_with`, §5), `paths` tasks whose paths meet.
PARALLEL_SCHEDULES = ("paths", "clashes")
PARALLEL_DEFAULTS: dict[str, Any] = {"max_in_flight": 3, "exclusive": [], "shared": [], "session_ceiling_pct": 60,
                                     "schedule": "clashes"}
# §22: the review-point register, a product file (ccp/reviewpoints.py).
REVIEW_POINTS_DEFAULTS: dict[str, Any] = {"file": "docs/delivery/review-points.yaml"}

PACKAGE_DOCS_DEFAULTS: dict[str, Any] = {
    "doc_name": ".claude.md",
    # Directories (relative to the root) documented by an auto-loaded CLAUDE.md instead of doc_name. A
    # directory of documents only (.md) needs a package doc only when it is listed here.
    "claude_md_dirs": [],
    # Deprecated: the top-level `language` replaces it (§8.1). Read in its place, with a warning, while
    # `language` is unset (§29.3); ignored, with a warning, when `language` is set. null: not given.
    "language": None,
    # null: the core's own plus the pack's (§21.4 names them). A list replaces both.
    "source_suffixes": None,
    "exempt_dirs": None,
    "size_ratio": 0.5,
    "banned_headings": ["future", "planned", "next steps", "roadmap", "todo"],
    # Backticked paths with these suffixes in a package doc must exist.
    "path_ref_suffixes": [".py", ".sql", ".json", ".md", ".sh"],
    # Files under these globs get the language pack's per-file checks (Python: a module docstring).
    "docstring_globs": [],
    # No task, finding or ruling id in a package doc or a code comment (§21.3); false turns it off.
    "no_delivery_ids": True,
    # The product's own id regexes (its findings, rulings, tickets), checked beside the plane's.
    "delivery_id_patterns": [],
    # Opt-in generic rules (ccp/docrules.py), each off until configured.
    "rules": {},
}
# §21.5: product commands `ccp docs check` runs, not tied to a house rule (exit 0 = pass). `workers`:
# how many check commands (these and `architect.checks`) run at once; 1 runs them one after another.
# §20.5 `starter_rules`: null (the starter house rules not adopted) or {declined?: {name: reason}}.
DOCS_DEFAULTS: dict[str, Any] = {"checks": [], "workers": 1, "starter_rules": None}
DOC_RULES = {"citations": {"globs", "targets", "ignore"}, "no_ids": {"globs", "patterns"}, "history_attr": None,
             "no_overlap": None, "no_call_bullets": None}

ARCHITECT_DEFAULTS: dict[str, Any] = {
    # The house rules (SPEC §20.1): a product path; when the doc is missing a pass runs without them.
    "rules_doc": "docs/ENGINEERING.md",
    "rules_max_lines": 150,
    # Triggers (§19.6).
    "every_n_tasks": 4,
    "max_days": 14,
    "notes_due": 3,
    "drift_ratio": 1.5,
    # Enforcement at `ccp tasks next` (§19.6).
    "grace_tasks": 1,
    "triage_grace_tasks": 2,
    # Shaping (§19.6) and the adoption point: shape_from_task is the task number the seat's rules start
    # from (the next task number when it turned on), so no finished task is judged by rules written after
    # it; with shape_adrs on it is required. Unset: the seat enforces nothing.
    "shape_adrs": False,
    "shape_from_task": None,
    # Refactor lane (§20). "deps": a refactor joins a scope only when a scope task depends on it;
    # true: every scope; false: only a scope that names it.
    "refactor_every": 4,
    "refactor_in_scope": "deps",
    # The run (§19.7) and its triage (§19.8).
    "call_timeout_minutes": 45,
    "max_new_tasks": 5,
    "probes": [],
    # Product commands and ccp budgets, each tied to a house-rule id (§20.2).
    "checks": [],
    "budgets": [],
    # Extra numbers `ccp health record` accepts beside its own (§27).
    "metrics": [],
    # Globs that split a merge's files into areas for `ccp health` (§27).
    "areas": {},
    # Paths the architect reads for structure only (values never quoted) / never reads (§19.11).
    "shape_only_dirs": [],
    "private_dirs": [],
}
# §13.2: the product's own rules for worker prompts, rendered after the plane template.
# §13: `worker_env` names variables each worker's commands get, from these templates.
# §23.8: `keep_body` keeps the full prompt text in each prompt audit (off: ids, refs, hash and length
# only); `audit_keep_days` prunes audits older than that many days when `ccp prompt` writes one
# (null keeps them all).
PROMPTS_DEFAULTS: dict[str, Any] = {"fragment": None, "worker_env": {}, "keep_body": False, "audit_keep_days": None}
WORKER_ENV_FIELDS = ("run_id", "task_id", "nnnn", "phase", "kind", "seat", "round", "worktree", "main_checkout", "queue_root",
                     "project_id")
# §10.5 `ccp tasks close`: the product's records beside the task file. `log` prepends one entry to a
# product log (an `entry` template, placed before the first line matching `before`); `hooks` are
# product commands run in the runner worktree with TASK_ID, PR, HEAD_SHA, MERGE_SHA and SUMMARY set.
# A hook must be idempotent: a `close` re-run after a failure runs the hooks again.
RECONCILE_DEFAULTS: dict[str, Any] = {"log": None, "hooks": []}
RECONCILE_LOG_KEYS = {"path", "entry", "before"}
RECONCILE_LOG_FIELDS = ("date", "task_id", "nnnn", "pr", "head", "head7", "merge_sha", "merge7", "summary",
                        "review_point", "title")
# Legacy (before §12.1's worktrees/env blocks): `adapter.post_close` commands still run once at close, with a
# warning that they move to `reconcile.hooks` (`KEY_OUTCOMES`); `adapter.worktree_dir` and `adapter.worktree_links`
# are merged into `worktrees.dir` and `worktrees.links` when plane.json loads, so they have no default.
ADAPTER_DEFAULTS: dict[str, Any] = {"post_close": []}
# §12.1: where `ccp wt` makes worktrees (relative to the main checkout, `..` allowed, or absolute; not the
# main checkout itself; null = none) and what it links in.
WORKTREES_DEFAULTS: dict[str, Any] = {"dir": None, "links": []}
WORKTREES_DIR_RULE = "{} must be a path relative to the main checkout (`..` allowed) or an absolute path, or null"
# §12 env hooks: shell command templates `ccp wt` runs in a worktree (null = none).
ENV_DEFAULTS: dict[str, Any] = {"setup": None, "teardown": None, "up": None, "down": None, "urls": None,
                                "timeout_seconds": 600}
ENV_HOOKS = ("setup", "teardown", "up", "down", "urls")
WT_FIELDS = ("task_id", "nnnn", "kind", "seat", "tag", "worktree", "main_checkout", "name")
# §10.5: the merge `ccp tasks close` runs (null = `gh pr merge {pr} --squash --match-head-commit {head_sha}`).
# `behind_tip_ignore` (§16.5 rule 4): paths whose commits on the tip do not make a head behind it.
MERGE_DEFAULTS: dict[str, Any] = {"command": None, "behind_tip_ignore": []}
MERGE_FIELDS = ("pr", "head_sha", "task_id")


def fill(template: str, values: dict[str, str]) -> str:
    """A hook or merge template with each `{field}` it names replaced; any other brace is literal, so a
    command may carry JSON or shell braces as they are."""
    return re.sub(r"\{(" + "|".join(map(re.escape, values)) + r")\}", lambda m: values[m.group(1)], template)
# §30: auth probes the runner runs before each task (`ccp auth check`, and `ccp tasks claim`).
AUTH_CHECK_DEFAULTS: dict[str, Any] = {"probes": [], "timeout_seconds": 60}
# §24.4, §25.1, §28.1: read by later steps; validated now so a binding written early is not refused.
# `allowance_cmd` and `allowance_stop_weekly` are the machine's (§8.3, §25.1): the machine file holds them, and
# the plane.json keys here are the old place, read while the machine file lacks them (`KEY_OUTCOMES`); the
# session knobs and `windows` are constants (`KEY_OUTCOMES`), kept here at their values for the readers.
TELEMETRY_DEFAULTS: dict[str, Any] = {"allowance_cmd": None, "allowance_stop_weekly": None,
                                      # §24.5: the lead's expected model and effort, as advice only
                                      "design_seat": None,
                                      # §25.4 the session park: claim and prompt park the task at this 5-hour %
                                      # (null: no park, no wake, no 5-hour modelling in the forecast); the
                                      # lead arms a wake from `arm_pct`, at the window's reset plus `margin_s`
                                      "session_park_pct": 95, "session_wake_arm_pct": 50, "session_wake_margin_s": 180,
                                      # §25.4 the usage windows: {<name>: {kind: weekly|session, stop_pct, park_pct}};
                                      # merged over the two built-in ones (seven_day: weekly, stopping at the
                                      # machine's allowance_stop_weekly; five_hour: session, parking at session_park_pct)
                                      "windows": None}
# §25.3, §8.3: the weekly stop the machine file's `allowance_stop_weekly` defaults to, in percent.
ALLOWANCE_STOP_WEEKLY_DEFAULT = 90
# §8.3: the account's keys the machine file holds.
MACHINE_ACCOUNT_KEYS = ("allowance_cmd", "allowance_stop_weekly")
BOARD_DEFAULTS: dict[str, Any] = {"refresh_minutes": 5}
# §14.6 the gate's time: `shell_limit_seconds` is the agent harness's foreground command limit, which a
# cold gate run must fit; `cut_line_seconds` (null: 90% of the limit) the lower line above which the
# gate is cut down. `ccp health` judges the latest cold gate run against both.
GATE_DEFAULTS: dict[str, Any] = {"shell_limit_seconds": 600, "cut_line_seconds": None}
GATE_CUT_SHARE = 0.9  # the cut line's default, as a share of the limit
# §27.1 `ccp health`: a merged task whose diff (lines added + deleted) is under `small_task_lines` counts
# as small, and health reports the share of small tasks among those merged in its window. §27.2: from the
# cold gate runs that carry `modules`, the `slowest_modules` slowest modules of the latest, and the median
# seconds per test over the last `suite_trend_runs`.
HEALTH_DEFAULTS: dict[str, Any] = {"small_task_lines": 100, "slowest_modules": 5, "suite_trend_runs": 10}
# §24.6 `ccp usage` advice, a line each past its threshold: a seat whose 5-minute cache writes are more than
# `cache_5m_share` of its cache-write tokens; the lead or a runner whose median context per request exceeds
# `context_tokens`; a coordination share (lead plus runner cost over all seats') above `coordination_share`.
# The advice reads the requests of the last `window_hours` (0: every request).
USAGE_DEFAULTS: dict[str, Any] = {"advice": {"cache_5m_share": 0.5, "context_tokens": 300000,
                                             "coordination_share": 0.4, "window_hours": 0}}
# §2.4 the implementer's model per task: `implementer_model` (null: the definition's) maps `small` (a task whose
# estimate is at most `small_estimate_minutes`) and `refactor` (a task of that kind) to an alias the Agent call's
# `model` accepts, `WORKER_MODEL_ALIASES`: it takes nothing else, a full id included.
# `implementer_model` is deprecated: `models.implementer_small` and `models.implementer_refactor` replace its arms.
WORKERS_DEFAULTS: dict[str, Any] = {"implementer_model": None, "small_estimate_minutes": 30}
WORKER_MODEL_ARMS = ("small", "refactor")
WORKER_MODEL_ALIASES = role_models.ALIASES
# §2.4 `models`: each role's model, an alias the Agent call's `model` accepts (`WORKER_MODEL_ALIASES`); the
# defaults are the plane's role table (`ccp/models.py`).
MODELS_DEFAULTS: dict[str, Any] = {role: alias for role, (alias, _) in role_models.ROLES.items()}
# §26.3 estimation: `reference_since` (YYYY-MM-DD, or null) leaves tasks merged before a process change
# out of every reference class; `k` is the reference class's size (5 to 8).
ESTIMATE_DEFAULTS: dict[str, Any] = {"reference_since": None, "k": 6, "auto": False,  # auto: §26.3 phase B triggers
                                     # §26.3: which backticked suffixes count as cited paths (null: the built-in list)
                                     "path_suffixes": None,
                                     # phase D (ccp/calibrate.py): half_life in merges, min_pairs per source and
                                     # metric, k the shrinkage strength (null: fitted, empirical Bayes)
                                     "calibration": {"half_life": 40, "min_pairs": 8, "k": None}}
# §6.8: the product's ADRs (ccp/adr.py). The block is the opt-in: without it `ccp docs check` reads no
# ADR and the board's register has ids only. `index` is the generated ADR index (a path), or None for
# none; `transitions` the moves `ccp adr status` allows; `strict` turns the ADR warnings into failures;
# `template` a product's own template for `ccp adr new` (a path), or None for the plane's.
ADR_DEFAULTS: dict[str, Any] = {"dir": "docs/adr", "index": None,
                                "statuses": ["proposed", "accepted", "in-progress", "implemented", "rejected",
                                             "superseded", "withdrawn", "retired"],
                                "transitions": {"proposed": ["accepted", "rejected", "withdrawn"],
                                                "accepted": ["superseded", "retired"],
                                                "in-progress": ["accepted", "superseded", "retired"],
                                                "implemented": ["superseded", "retired"]},
                                "strict": False, "template": None}
# §14.1 `ccp suite run`: named lanes (a lane name to the argv it runs, from the checkout's root, or to
# an ordered list of `{name, cmd}` stages, §14.2) and the regular expression whose first group is a test count in the suite's output (summed over every
# line that matches; the default is the language pack's, ccp/doclang).
SUITE_DEFAULTS: dict[str, Any] = {"lanes": {}, "count_re": None, "summary": None, "log_keep_days": 14,
                                  # §14.7 `ccp suite affected`: a glob of root-relative paths to the test ids
                                  # its part lane runs, added to what the language pack reads ({} = none)
                                  "affected_map": {},
                                  # SPEC §16.6: lanes that run one at a time in a queue (a run with no lane
                                  # is the `full` role's lane)
                                  "exclusive_lanes": [],
                                  # §14.1: the lane name for each role the plane reads: `full` (the whole
                                  # suite), `gate` (the formal gate), `part` (a subset of the tests)
                                  "roles": {"full": "full", "gate": "gate", "part": "part"}}
SUITE_ROLES = ("full", "gate", "part")
# `log_keep_days`: summary-mode logs in the queue older than this are removed when a run starts.
# `suite.summary` (§14.1): what `ccp suite run` reads from the output when the gate writes no
# result file (CCP_SUITE_RESULT, contracts/suite_result.schema.json). Each `*_re` is a regular
# expression, or a list of them, whose first group is a number, summed over every matching line:
# `failed` (failures and errors), `skipped`, and, for a product with a test cache, `ran`
# and `cached` (units run and served from the cache, in the product's unit: tests, modules, files)
# and `cached_tests` (the tests behind the cached units). `failed_re`, `skipped_re` and
# `section_re` default to None, the language pack's (ccp/doclang, house rule E18); `ran`, `cached` and
# `cached_tests` match nothing until a product sets them. `section_re` starts a
# failing test's section (the line after a `====` rule); `show_re` lines are shown whatever the
# result; `tail_lines` and `max_chars` bound what a failure shows. A key left out keeps its default.
SUITE_SUMMARY_DEFAULTS: dict[str, Any] = {
    "failed_re": None,
    "skipped_re": None,
    "ran_re": [],
    "cached_re": [],
    "cached_tests_re": [],
    "section_re": None,
    "show_re": [],
    "tail_lines": 40,
    "max_chars": 40000,
}
# The verifier's gate (§15.3): `accept_cache` (null = off) lets a product's content-keyed test cache
# stand in for a rerun. A module the verifier's own gate run reports as a hit on identical inputs
# counts as run; an entry over `max_age_days` is no hit; a task whose id matches a `cold_tasks` glob,
# or whose frontmatter says `gate: cold`, has a cold gate. `review: true` extends the rule to the
# reviewer's touched and dependent modules (its order and mutation runs stay uncached).
# `skip_review` (null = off, §15.2): a fix round whose diff touches only `paths` (relative to the product
# root) and that the product's `proof` command passes (exit 0) goes to verify with no new review.
# `skip_review_after_clean` (false = off, §15.2): a fix round after a review with no BLOCKER or MAJOR
# finding goes to verify with no new review; the verifier confirms it answers only those findings.
# `provers` ([] = none, §14.2, §15.2): each `{name, command, skips}`; a prover whose command exits 0 on the
# task's diff (a gate stage) or the fix round's diff (`review`) skips the step `skips` names, recorded on
# the run. `verify.skip_review` is one such prover, of the review, with its own paths rule. Both are read
# from plane.json on the integration branch (`skip_rules_at`), never from the checkout or the head under test,
# and their commands run in a clean checkout of that branch's tip, so nothing the task's diff changes alters
# their verdict.
VERIFY_DEFAULTS: dict[str, Any] = {"accept_cache": None, "skip_review": None, "skip_review_after_clean": False,
                                   "provers": []}
PROVER_KEYS = {"name", "command", "skips"}
PROVER_REVIEW = "review"  # the step a prover's `skips` names for the review of a fix round (§15.2)
ACCEPT_CACHE_DEFAULTS: dict[str, Any] = {"max_age_days": None, "cold_tasks": [], "review": False}
SKIP_REVIEW_KEYS = {"paths", "proof"}
SKIP_REVIEW_FIELDS = ("task_id", "reviewed", "head", "from")
# §20.6 `ccp mutate`: `command` runs one named test (a shell template naming `{test}`, filled in
# shell-quoted; null, the default, means the product has none and `ccp mutate` refuses);
# `timeout_seconds` bounds one run of it (a mutant that hangs the test is killed); `unbuilt_re`, a
# regular expression or a list of them (null, the default, matches nothing), is a line the command
# prints when the code does not build or import: a failing run that prints one records the mutant `unbuilt`.
MUTATE_DEFAULTS: dict[str, Any] = {"command": None, "timeout_seconds": 600, "unbuilt_re": None}
# §13.4: verdict lines every done implement or fix report must state, each `{name, values}`: the line
# is `<name>: <one of values>`. `ccp report` refuses a report missing one; none by default.
REPORT_DEFAULTS: dict[str, Any] = {"required_fields": []}
# §3.6: the operator's channel. `command` is a shell command `ccp` runs on each trigger, given the trigger
# and ids in its environment (null, the default: the lead's session, and no command runs);
# `timeout_seconds` bounds one run of it. `lead`, `{tool, to}`, declares that the lead sends each notice
# with that tool from its own session (null, the default: no declared tool).
NOTIFY_DEFAULTS: dict[str, Any] = {"command": None, "timeout_seconds": 30, "lead": None}
NOTIFY_LEAD_KEYS = ("tool", "to")
# §29.3: the plane tasks' `adopt` steps this product declined, and those it took in a way `ccp upgrade
# status` cannot see, each task id -> reason; the command leaves both out of its steps (none by default).
UPGRADE_DEFAULTS: dict[str, Any] = {"declined": {}, "taken": {}}
# §8.1: plane.json's top-level blocks (besides `project_id`, `$schema` and `_note`), each with its defaults:
# the one place the block list and the merge of each block derive from. `ids` keeps its defaults in refs.py.
BLOCK_DEFAULTS: dict[str, dict[str, Any]] = {
    "task_log": TASK_LOG_DEFAULTS, "package_docs": PACKAGE_DOCS_DEFAULTS, "architect": ARCHITECT_DEFAULTS,
    "prompts": PROMPTS_DEFAULTS, "reconcile": RECONCILE_DEFAULTS, "adapter": ADAPTER_DEFAULTS,
    "worktrees": WORKTREES_DEFAULTS, "env": ENV_DEFAULTS, "merge": MERGE_DEFAULTS,
    "auth_check": AUTH_CHECK_DEFAULTS, "telemetry": TELEMETRY_DEFAULTS, "board": BOARD_DEFAULTS,
    "gate": GATE_DEFAULTS, "health": HEALTH_DEFAULTS, "usage": USAGE_DEFAULTS, "workers": WORKERS_DEFAULTS,
    "models": MODELS_DEFAULTS,
    "suite": SUITE_DEFAULTS, "adr": ADR_DEFAULTS, "verify": VERIFY_DEFAULTS,
    "review_points": REVIEW_POINTS_DEFAULTS, "estimate": ESTIMATE_DEFAULTS, "parallel": PARALLEL_DEFAULTS,
    "ids": refs.IDS_DEFAULTS, "docs": DOCS_DEFAULTS, "mutate": MUTATE_DEFAULTS, "report": REPORT_DEFAULTS,
    "notify": NOTIFY_DEFAULTS, "upgrade": UPGRADE_DEFAULTS}
BLOCKS = tuple(BLOCK_DEFAULTS)


# ---------------------------------------------------------------- keys the product no longer decides
# ADR-0043 D9, SPEC §29.3: a plane.json key that is not the product's to decide has one outcome here, and one
# loader (`_apply_outcomes`) applies it, so no outcome is written twice. The schema marks each such key
# `deprecated` with its outcome, and `ccp upgrade status` lists each one a product still sets.
REMOVED, MERGED, CONSTANT = "removed", "merged", "constant"


@dataclass(frozen=True)
class Outcome:
    """What becomes of one plane.json key (a dotted path). `removed`: ignored, with a warning. `merged`: read
    at `into` (`in_place`: still read where it is, the warning saying it moves there), the old place read
    only while `into` is unset (`exclusive`: both set to different values is an error; `blank`: null or an empty
    list is as good as unset; `globs`: an entry `dir/*.md` moves as `dir/`; `machine`: `into` is a key of the
    machine file (§8.3), whose own value wins, and the key stays read here, `in_place`, while the machine file
    lacks it). `constant`: the code uses `value`; a value the product sets other than it still applies, with a
    warning, until the key is deleted (`constant_override`). `why` is what the warning adds."""
    kind: str
    into: str = ""
    value: Any = None
    in_place: bool = False
    exclusive: bool = False
    blank: bool = False
    globs: bool = False
    machine: bool = False
    why: str = ""


_ACCOUNT_WHY = "the account is the machine's, not a product's: set it once in the machine file beside the bindings"
KEY_OUTCOMES: dict[str, Outcome] = {
    "task_log.statuses": Outcome(REMOVED, why="a task file's statuses are fixed, pending, done and dropped (§5)"),
    "suite.summary.modules_ran_re": Outcome(REMOVED, why="its name is `ran_re` (§14.1)"),
    "suite.summary.modules_cached_re": Outcome(REMOVED, why="its name is `cached_re` (§14.1)"),
    "task_log.spec_paths": Outcome(MERGED, into="spec_paths"),
    "estimate.spec_paths": Outcome(MERGED, into="spec_paths", globs=True),
    "adapter.worktree_dir": Outcome(MERGED, into="worktrees.dir", exclusive=True, blank=True),
    "adapter.worktree_links": Outcome(MERGED, into="worktrees.links", exclusive=True, blank=True),
    "adapter.post_close": Outcome(MERGED, into="reconcile.hooks", in_place=True, blank=True,
                                  why="the commands still run once at close; `$TASK_ID` stands for `{task_id}` there"),
    "task_log.review_point_pattern": Outcome(MERGED, into="ids.review_point.pattern"),
    # ADR-0043 D8: the account's facts are the machine's (the machine file, §8.3); the old place is read while it lacks them
    "telemetry.allowance_cmd": Outcome(MERGED, into="machine.json allowance_cmd", in_place=True, blank=True,
                                       machine=True, why=_ACCOUNT_WHY),
    "telemetry.allowance_stop_weekly": Outcome(MERGED, into="machine.json allowance_stop_weekly", in_place=True,
                                               blank=True, machine=True, why=_ACCOUNT_WHY),
    # the session park, wake and ceiling numbers, and the usage windows, are constants at today's values
    "telemetry.session_park_pct": Outcome(CONSTANT, value=TELEMETRY_DEFAULTS["session_park_pct"]),
    "telemetry.session_wake_arm_pct": Outcome(CONSTANT, value=TELEMETRY_DEFAULTS["session_wake_arm_pct"]),
    "telemetry.session_wake_margin_s": Outcome(CONSTANT, value=TELEMETRY_DEFAULTS["session_wake_margin_s"]),
    "telemetry.windows": Outcome(CONSTANT, value=TELEMETRY_DEFAULTS["windows"]),
    "parallel.session_ceiling_pct": Outcome(CONSTANT, value=PARALLEL_DEFAULTS["session_ceiling_pct"]),
}
UNSET: Any = object()  # `constant_override`: the key is not set


def old_keys(prefix: str) -> list[str]:
    """The names directly under `prefix` that `KEY_OUTCOMES` holds: keys the schema still lists."""
    head = prefix + "."
    return [k[len(head):] for k in KEY_OUTCOMES if k.startswith(head) and "." not in k[len(head):]]


def _lookup(raw: Any, key: str) -> tuple[bool, Any]:
    for part in key.split("."):
        if not isinstance(raw, dict) or part not in raw:
            return False, None
        raw = raw[part]
    return True, raw


def _put(raw: dict[str, Any], key: str, value: Any) -> bool:
    """Set the dotted `key` in `raw`, making the objects on the way; False (nothing set) when one is not an object."""
    *path, last = key.split(".")
    node = raw
    for part in path:
        if node.get(part) is None:
            node[part] = {}
        if not isinstance(node[part], dict):
            return False
        node = node[part]
    node[last] = value
    return True


def _remove(raw: dict[str, Any], key: str) -> None:
    *path, last = key.split(".")
    ok, node = _lookup(raw, ".".join(path)) if path else (True, raw)
    if ok and isinstance(node, dict):
        node.pop(last, None)


def _dir_forms(value: Any) -> tuple[Any, list[str]]:
    """`value`, a list of paths, with each entry `dir/*.md` (no glob in `dir`) as `dir/`, and the entries changed:
    `estimate.spec_paths` held globs, and `spec_paths` names a directory by a trailing `/` (§3.5)."""
    if not isinstance(value, list):
        return value, []
    out, changed = [], []
    for x in value:
        if isinstance(x, str) and x.endswith("/*.md") and not any(c in x[:-4] for c in "*?["):
            out.append(x[:-4])
            changed.append(x)
        else:
            out.append(x)
    return out, changed


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def machine_account() -> dict[str, Any]:
    """§8.3, §25.1: the account facts the machine file sets (`MACHINE_ACCOUNT_KEYS`), each only when its value is
    valid: `allowance_cmd` a non-empty command, `allowance_stop_weekly` a percentage above 0 and at most 100. A
    value that is not valid is ignored, with one warning naming the file. The one reader (`usage.account`, the
    loader's note for the old place) calls this."""
    from ccp.queue import lib  # noqa: PLC0415  (queue imports this module)
    data = lib.read_machine()
    out: dict[str, Any] = {}
    for key in MACHINE_ACCOUNT_KEYS:
        if key not in data:
            continue
        v = data[key]
        ok = (isinstance(v, str) and bool(v.strip())) if key == "allowance_cmd" else \
            (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 100)
        if ok:
            out[key] = v
        else:
            _warn_once(str(lib.machine_path()), f"{lib.machine_path()}: {key} must be "
                       + ("a command" if key == "allowance_cmd" else "a percentage above 0, at most 100")
                       + f", not {v!r}; it is ignored (SPEC §8.3)")
    return out


def constant_override(key: str, given: Any = UNSET, *, notes: list[str] | None = None, where: str = CONFIG_REL) -> Any:
    """The value to use for `key`, a registry entry (`KEY_OUTCOMES`) with the outcome `constant`: its value
    when `given` is UNSET; else, with one warning naming the key and the constant, `given` when it is another
    value (it applies until the product deletes the key or the plane takes a proposal to keep it), or the
    constant when `given` is the constant's own value (the warning says the key can be deleted). The warning
    goes to `notes` when that is given (once per key), else to stderr once per `where` and process. Every
    reader of a constant calls this: plane.json's loader, the account knobs, the runner numbers (SPEC §29.3)."""
    out = KEY_OUTCOMES[key]
    if out.kind != CONSTANT:
        raise KeyError(f"{key} is not a constant")
    if given is UNSET:
        return out.value
    if _same(given, out.value):
        msg = (f"{where}: {key} is a constant in code ({out.value!r}) and is set to that value: delete it "
               "(SPEC §29.3)")
        use = out.value
    else:
        msg = (f"{where}: {key} is a constant in code ({out.value!r}); the value {given!r} set here still "
               "applies until you delete the key, or file a plane proposal to keep it (SPEC §29.3)")
        use = given
    if notes is None:
        _warn_once(where, msg)
    elif msg not in notes:
        notes.append(msg)
    return use


def _apply_outcomes(raw: dict[str, Any], ignored: dict[str, str] | None = None, *,
                    strict: bool = True) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """plane.json `raw` (a copy) with each `KEY_OUTCOMES` key it sets applied, and one finding per such key:
    `{key, outcome, set, note, ...}` (`note` the warning; a merged key has `replacement`, a constant `constant`
    and `differs`). `ignored` maps a merged key to why it is ignored whatever its place. `strict`: an exclusive
    key set to a value other than its new place's is a ConfigError (else the new place wins)."""
    raw = copy.deepcopy(raw)
    found: list[dict[str, Any]] = []
    for key, o in KEY_OUTCOMES.items():
        here, given = _lookup(raw, key)
        if not here:
            continue
        f: dict[str, Any] = {"key": key, "outcome": o.kind, "set": given}
        where = f"{CONFIG_REL}: {key}"
        if o.kind == REMOVED:
            _remove(raw, key)
            f["note"] = f"{where} is removed and ignored" + (f": {o.why}" if o.why else "") + "; delete it (SPEC §29.3)"
        elif o.kind == MERGED:
            f["replacement"] = o.into
            new_set, new = _lookup(raw, o.into)
            new_set = new_set and not (o.blank and new in (None, []))
            if key in (ignored or {}):
                _remove(raw, key)
                f["note"] = f"{where} is ignored: {ignored[key]}; delete it (SPEC §29.3)"
            elif o.blank and given in (None, []):
                _remove(raw, key)
                f["note"] = f"{where} is empty and ignored: delete it (SPEC §29.3)"
            elif o.machine:
                name = key.rsplit(".", 1)[1]
                from ccp.queue import lib  # noqa: PLC0415  (queue imports this module)
                if name in machine_account():
                    f["note"] = (f"{where} is ignored: the machine file {lib.machine_path()} sets {name}, which wins "
                                 "for every product on the machine; delete it (SPEC §29.3)")
                else:
                    f["note"] = (f"{where} has moved to {name} in the machine file {lib.machine_path()}: {o.why}. "
                                 f"It is still read from here while the machine file lacks {name}, which a later "
                                 f"release ends: set {name} there and delete {key} (SPEC §29.3)")
            elif o.in_place:
                f["note"] = (f"{where} moves to {o.into}: {o.why}; a later release ends it, so move them and "
                             "delete the key (SPEC §29.3)")
            elif new_set:
                if strict and o.exclusive and not _same(new, given):
                    raise ConfigError(f"{CONFIG_REL}: set {o.into} or the old {key}, not both")
                _remove(raw, key)
                f["note"] = f"{where} is ignored: {o.into} is set; delete it (SPEC §29.3)"
            elif _put(raw, o.into, _dir_forms(given)[0] if o.globs else given):
                _remove(raw, key)
                f["moved"] = True
                f["note"] = (f"{where} has moved to {o.into}; it is read from its old place while {o.into} is "
                             f"unset, which a later release ends: set {o.into} and delete {key} (SPEC §29.3)")
                changed = _dir_forms(given)[1] if o.globs else []
                if changed:
                    f["note"] += (f"; {', '.join(changed)} read as "
                                  f"{', '.join(_dir_forms(changed)[0])} (a directory ends in `/`, not `/*.md`)")
            else:  # the object it would move into is no object: the block's own check says so
                f["note"] = f"{where} has moved to {o.into} (SPEC §29.3)"
        else:
            notes: list[str] = []
            use = constant_override(key, given, notes=notes)
            _put(raw, key, use)
            f.update(constant=o.value, differs=not _same(given, o.value), note=notes[0])
        found.append(f)
    return raw, found


def _at_origin(message: str, found: list[dict[str, Any]]) -> str:
    """`message`, a check's error about a value that `_apply_outcomes` moved, naming the key the product wrote
    (the old place) where it names the new one."""
    for f in found:
        if f.get("moved"):
            message = re.sub(r"(?<![\w.])" + re.escape(f["replacement"]) + r"(?![\w])", f["key"], message)
    return message


def key_outcomes_set(plane: Any) -> list[dict[str, Any]]:
    """§29.3: each key the plane.json data `plane` sets that has an outcome (`KEY_OUTCOMES`) the product acts
    on: a removed key, a merged one (with `replacement`), a constant set to a value other than the constant."""
    if not isinstance(plane, dict):
        return []
    return [f for f in _apply_outcomes(plane, strict=False)[1] if f["outcome"] != CONSTANT or f["differs"]]


# The blocks with a loader of their own (a check or a merge beyond the plain one); `_toolkit` merges the rest.
_OWN_LOADER_BLOCKS = ("task_log", "package_docs", "architect", "usage", "suite", "adr", "ids", "docs", "upgrade",
                      "models")
# The keys of the objects inside blocks that the validators below read key by key.
CHECK_KEYS = ("id", "cmd", "timeout_seconds")  # an entry of docs.checks or architect.checks
BUDGET_KEYS = ("id", "glob", "path", "max_lines", "max_bytes", "cut_line")  # architect.budgets
PROBE_KEYS = ("id", "cmd")  # auth_check.probes
KIND_KEYS = ("refs_any", "forbid")  # each kind under task_log.kinds
WINDOW_KEYS = ("kind", "stop_pct", "park_pct")  # each window under telemetry.windows
DESIGN_SEAT_KEYS = ("model", "effort")  # telemetry.design_seat
REPORT_FIELD_KEYS = ("name", "values")  # an entry of report.required_fields
REPORT_FIELD_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]{0,39}$")
# The lines `ccp report` already reads: a declared field may not take one of their names.
REPORT_OWN_LINES = ("outcome", "pr", "head", "verdict", "severity", "suite")
SUITE_LANE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")
# §5, §14.1: the placeholder a gate lane is written with before the product names its own command.
LANE_PLACEHOLDER = "<your test command>"
# §14.2: a lane's stages are `{name, cmd}` (a stage name is a lane-like label; `cmd` a shell command run
# from the root). The gate role's staged lane ends with the plane's doc checks under this name.
SUITE_STAGE_KEYS = {"name", "cmd"}
PLANE_DOCS_STAGE = "plane-docs"
_INTS = {"rules_max_lines": 1, "every_n_tasks": 1, "max_days": 1, "notes_due": 1, "grace_tasks": 0,
         "triage_grace_tasks": 0, "refactor_every": 0, "call_timeout_minutes": 1, "max_new_tasks": 0}
_STR_LISTS = ("probes", "metrics", "shape_only_dirs", "private_dirs")
RULE_ID_RE = refs.DEFAULT.rule_id_re  # the default house-rule id; a product may set ids.rule (refs.py)
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# §4.5, §8.3: the binding's `lead` block. `auto_compact_window` is the `autoCompactWindow` `ccp init` writes
# into a product's `.claude/settings.json` when it has none.
LEAD_DEFAULTS: dict[str, Any] = {"auto_compact_window": 350000}
# §8.1: the top-level keys plane.json must give. `language` names a language pack (ccp/doclang) or `none`
# and has no default. While REQUIRED_KEYS_GRACE is true (the grace release, §29.3), a command that needs a
# required key and finds it unset warns and behaves as before the key was required; once it is false, it
# refuses (exit 2).
REQUIRED_KEYS = ("project_id", "language")
REQUIRED_KEYS_GRACE = True
# §29.3: the language a product that names none is read with during the grace release, as before the key
# was required (the old `package_docs.language` default).
GRACE_LANGUAGE = "python"


def lead_auto_compact_window(lead: dict[str, str]) -> int:
    """The binding's `lead.auto_compact_window` (§4.5) from its `lead` block's scalars: a positive whole
    number, else the default (absent, or not one). One that is set but is not a positive whole number warns
    on stderr, naming the key and the value."""
    v = str(lead.get("auto_compact_window", "")).strip()
    if re.fullmatch(r"[0-9]+", v) and int(v) >= 1:
        return int(v)
    default = LEAD_DEFAULTS["auto_compact_window"]
    if v:
        print(f"warning: the binding's lead.auto_compact_window is {v!r}, not a positive whole number; "
              f"reading it as the default, {default}", file=sys.stderr)
    return default


class ConfigError(Exception):
    """The product has no usable plane.json."""


@dataclass(frozen=True)
class Config:
    root: Path
    project_id: str
    task_log: dict[str, Any]
    package_docs: dict[str, Any] | None
    # §8.1: the product's language (a pack's name, or `none`), from the top-level `language` or, while that
    # is unset, the old `package_docs.language`; None when neither names one.
    language: str | None = None
    # Where `language` came from when it was not the top-level key: "package_docs.language" (read at its old
    # place), or "ignored" (both given: the old place is ignored); "" otherwise.
    language_moved: str = ""
    docs: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DOCS_DEFAULTS))
    # The architect's settings (the defaults when plane.json has no block), or None when plane.json sets
    # `"architect": false`: the seat is off.
    architect: dict[str, Any] | None = None
    # Whether plane.json names architect.rules_doc itself: a rules doc it names that is missing is an error
    # for `ccp docs check`; the default one missing only means a pass runs without house rules (§19.11).
    rules_doc_set: bool = False
    prompts: dict[str, Any] | None = None
    reconcile: dict[str, Any] | None = None
    adapter: dict[str, Any] | None = None
    worktrees: dict[str, Any] | None = None
    env: dict[str, Any] | None = None
    merge: dict[str, Any] | None = None
    auth_check: dict[str, Any] | None = None
    telemetry: dict[str, Any] | None = None
    board: dict[str, Any] | None = None
    gate: dict[str, Any] | None = None
    health: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    workers: dict[str, Any] | None = None
    models: dict[str, Any] | None = None
    suite: dict[str, Any] | None = None
    adr: dict[str, Any] | None = None
    verify: dict[str, Any] | None = None
    review_points: dict[str, Any] | None = None
    estimate: dict[str, Any] | None = None
    parallel: dict[str, Any] | None = None
    mutate: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    notify: dict[str, Any] | None = None
    upgrade: dict[str, Any] | None = None
    # §3.5: the top-level `spec_paths` (or, while it is unset, the old `task_log.spec_paths` or
    # `estimate.spec_paths`), the default otherwise; read through `spec_paths(cfg)`.
    spec_paths: tuple[str, ...] = SPEC_PATHS_DEFAULT
    # §29.3: one warning for each plane.json key with an outcome (`KEY_OUTCOMES`) that the product sets.
    key_notes: tuple[str, ...] = ()
    # The `models` keys plane.json sets itself: a key it leaves out may still be set by the deprecated
    # `workers.implementer_model` (`models.model_for`).
    models_given: tuple[str, ...] = ()
    # The product's id and reference patterns (plane.json `ids`, SPEC §7); the defaults otherwise.
    ids: refs.Ids = refs.DEFAULT

    # §8.1: the keys plane.json holds that this ccp does not know, dotted (`verify.future_knob`): ignored when
    # it loads, with a warning, and refused by `ccp docs check`.
    unknown_keys: tuple[str, ...] = ()

    @property
    def delivery_dir(self) -> Path:
        return self.root / self.task_log["dir"]

    @property
    def tasks_dir(self) -> Path:
        return self.delivery_dir / "tasks"

    @property
    def reviews_dir(self) -> Path:
        return self.delivery_dir / str(self.task_log.get("reviews_dir") or "reviews")

    @property
    def index_path(self) -> Path:
        return self.delivery_dir / "INDEX.yaml"

    def rel(self, p: Path) -> str:
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)


def find_root(arg: str | None = None) -> Path:
    """--root, else $CCP_ROOT, else the git toplevel of the working directory."""
    if arg or envvar("CCP_ROOT"):
        return Path(arg or envvar("CCP_ROOT")).resolve()
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if r.returncode != 0:
        raise ConfigError("not inside a git checkout: run from the product repo or pass --root")
    return Path(r.stdout.strip()).resolve()


def _task_log(given: Any) -> dict[str, Any]:
    """The task_log block; `kinds` merges per kind, so a product naming one kind keeps the others."""
    out = _merge(TASK_LOG_DEFAULTS, given, "task_log")
    if isinstance(given, dict) and isinstance(given.get("kinds"), dict):
        out["kinds"] = {**copy.deepcopy(TASK_LOG_DEFAULTS["kinds"]), **given["kinds"]}
    return out


def _suite(given: Any) -> dict[str, Any]:
    """The suite block; `roles` merges per role, so a product naming one lane keeps the others."""
    out = _merge(SUITE_DEFAULTS, given, "suite")
    if isinstance(given, dict) and isinstance(given.get("roles"), dict):
        out["roles"] = {**SUITE_DEFAULTS["roles"], **given["roles"]}
    return out


class MissingKey(ConfigError):
    """A required plane.json key (§8.1) is unset, and the grace release that introduced it has ended."""


_LANGUAGE_WARNED: set[str] = set()  # the products already warned about an unset language in this process


def language_name(cfg: Any) -> str:
    """The language pack a product's facts come from: its `language`, or, while it names none (the grace
    release, §29.3), GRACE_LANGUAGE, as before the key was required."""
    return str(getattr(cfg, "language", None) or GRACE_LANGUAGE) if cfg is not None else GRACE_LANGUAGE


def package_docs_on(cfg: Any) -> bool:
    """Whether the package-doc checks (§21.3, §21.4) run: `language` names a pack; with no language (the
    grace release), whether plane.json has a `package_docs` block, as before the key was required."""
    lang = getattr(cfg, "language", None)
    if lang is None:
        return getattr(cfg, "package_docs", None) is not None
    return lang != "none"


def missing_language(what: str) -> str:
    """The line that says a product names no language, which `what` needs (§8.1)."""
    return (f"{CONFIG_REL} sets no `language` (one of {', '.join(_language_names())}), which {what} needs "
            "(SPEC §8.1)")


def require_language(cfg: Any, what: str) -> str | None:
    """§8.1: the product's language for a command that needs it (`what`). Unset: during the grace release
    (REQUIRED_KEYS_GRACE) a warning on stderr, once per product and process, naming the key and its upgrade
    step, and None, so the command behaves as before; after it, MissingKey (exit 2)."""
    lang = getattr(cfg, "language", None)
    if lang is not None:
        return str(lang)
    if not REQUIRED_KEYS_GRACE:
        raise MissingKey(f"{missing_language(what)}: set it")
    key = str(getattr(cfg, "root", ""))
    if key not in _LANGUAGE_WARNED:
        _LANGUAGE_WARNED.add(key)
        print(f"ccp: warning: {missing_language(what)}; this release still runs as before it was required, and a "
              "later one refuses: set it (the upgrade step `required: plane.json language`, `ccp upgrade status`)",
              file=sys.stderr)
    return None


_GATE_WARNED: set[str] = set()  # the products already warned about a missing gate lane in this process


def gate_lane_missing(cfg: Any) -> str | None:
    """§8.1, §14.1: the line that says the product has no gate lane, or None when it has one. The gate lane
    is the lane `suite.lanes` gives the gate role (`lane_for`); it is missing when there is no such entry,
    its argv or stages are empty, or a command in it still holds LANE_PLACEHOLDER."""
    lane = lane_for(cfg, "gate")
    v = ((getattr(cfg, "suite", None) or {}).get("lanes") or {}).get(lane)
    cmds = [str(st.get("cmd") or "") for st in v] if lane_stages(v) is not None else \
        [str(a) for a in v] if isinstance(v, list) else []
    if any(c.strip() for c in cmds) and not any(LANE_PLACEHOLDER in c for c in cmds):
        return None
    return (f"no gate lane: plane.json suite.lanes names no lane {lane!r} for the gate role (§14.1); every task's "
            "verify runs it")


def require_gate_lane(cfg: Any) -> str | None:
    """§8.1: for `ccp tasks claim` and `ccp tasks next`, None when the product has a gate lane. Without one:
    during the grace release (REQUIRED_KEYS_GRACE) the warning to print, once per product and process ("" when
    already given), naming its upgrade step; after it, MissingKey (exit 2) with gate_lane_missing's line."""
    why = gate_lane_missing(cfg)
    if why is None:
        return None
    if not REQUIRED_KEYS_GRACE:
        raise MissingKey(why)
    key = str(getattr(cfg, "root", ""))
    if key in _GATE_WARNED:
        return ""
    _GATE_WARNED.add(key)
    return (f"{why}; this release still runs as before it was required, and a later one refuses: name it (the "
            "upgrade step `required: plane.json suite.lanes.gate`, `ccp upgrade status`; `ccp init --gate` writes it)")


def _language_names() -> tuple[str, ...]:
    from ccp import doclang  # noqa: PLC0415
    return doclang.NAMES


def _language(raw: dict[str, Any]) -> tuple[str | None, str]:
    """(the product's language, where it came from) from plane.json's top-level `language` and the old
    `package_docs.language` (§8.1, §29.3). Each value given must be a pack's name or `none`."""
    names = _language_names()
    pkg = raw.get("package_docs")
    old = pkg.get("language") if isinstance(pkg, dict) else None
    if old is not None and old not in names:
        raise ConfigError(f"{CONFIG_REL}: package_docs.language {old!r} is not one of {', '.join(names)}")
    if "language" not in raw:
        return (old, "package_docs.language") if old is not None else (None, "")
    lang = raw["language"]
    if not isinstance(lang, str) or lang not in names:
        raise ConfigError(f"{CONFIG_REL}: language {lang!r} is not one of {', '.join(names)}")
    return lang, ("ignored" if old is not None else "")


def language_warnings(cfg: Any) -> list[str]:
    """§29.3: what plane.json says about the language at the old place, `package_docs.language`."""
    moved = getattr(cfg, "language_moved", "")
    if moved == "package_docs.language":
        return [f"{CONFIG_REL}: package_docs.language has moved to the top-level `language`; it is read from "
                "its old place while `language` is unset, which a later release ends: set `language` and delete "
                "package_docs.language (SPEC §29.3)"]
    if moved == "ignored":
        return [f"{CONFIG_REL}: package_docs.language is ignored: the top-level `language` is set; delete it "
                "(SPEC §29.3)"]
    return []


def unknown_key_errors(cfg: Any) -> list[str]:
    """§8.1: one failure per plane.json key this ccp does not know, for `ccp docs check`."""
    return [f"{CONFIG_REL}: unknown key {k}: a typo, or a key this ccp predates (update ccp)"
            for k in getattr(cfg, "unknown_keys", ())]


def config_warnings(cfg: Any) -> list[str]:
    """What plane.json says that is accepted but has no effect, for `ccp tasks check` to show."""
    return [*getattr(cfg, "key_notes", ()), *language_warnings(cfg)]


def spec_paths(cfg: Any) -> list[str]:
    """§3.5: the paths that hold the product's SPEC (plane.json `spec_paths`); the default for a config without one."""
    return list(getattr(cfg, "spec_paths", SPEC_PATHS_DEFAULT))


def gate_limits(cfg: Any) -> tuple[float, float]:
    """(the shell limit, the cut line) in seconds (plane.json `gate`, §14.6); the defaults without one."""
    g = (getattr(cfg, "gate", None) or GATE_DEFAULTS) if cfg is not None else GATE_DEFAULTS
    limit = g.get("shell_limit_seconds") or GATE_DEFAULTS["shell_limit_seconds"]
    cut = g.get("cut_line_seconds")
    return limit, (cut if cut is not None else round(limit * GATE_CUT_SHARE, 3))


def lane_for(cfg: Any, role: str) -> str:
    """The lane name the product gives a role (`full`, `gate`, `part`; plane.json `suite.roles`)."""
    roles = ((getattr(cfg, "suite", None) or {}).get("roles") or {}) if cfg is not None else {}
    return str(roles.get(role) or SUITE_DEFAULTS["roles"][role])


def architect_on(cfg: Any) -> bool:
    """Whether the architect seat is on for the product: the one test every on/off site asks (§19). It is
    on unless plane.json sets `"architect": false`, which leaves `cfg.architect` None."""
    return getattr(cfg, "architect", None) is not None


def adoption_point(cfg: Any) -> int | None:
    """The task number the architect starts from (`architect.shape_from_task`, a number or an id), or
    None when the architect is off or names none: then it enforces nothing (§19.11)."""
    sft = (getattr(cfg, "architect", None) or {}).get("shape_from_task")
    m = refs.ids(cfg).task_number_re.match(str(sft or ""))
    return int(m.group(1)) if m else None


def architect_adopted(cfg: Any) -> bool:
    """Whether the seat enforces anything (§19.11): it is on and has an adoption point. The seat on with no
    adoption point enforces nothing: no cadence, no block at `next`, no kind or shaping check."""
    return architect_on(cfg) and adoption_point(cfg) is not None


def _merge(defaults: dict[str, Any], given: Any, name: str) -> dict[str, Any]:
    if given is None:
        return copy.deepcopy(defaults)
    if not isinstance(given, dict):
        raise ConfigError(f"{CONFIG_REL}: `{name}` must be an object")
    unknown = sorted(set(given) - set(defaults))
    if unknown:
        raise ConfigError(f"{CONFIG_REL}: unknown key(s) in `{name}`: {', '.join(unknown)}")
    out = copy.deepcopy(defaults)
    out.update(given)
    return out


def _entries(a: dict[str, Any], key: str, allowed: set[str], required: set[str], ids: refs.Ids) -> None:
    where = f"{CONFIG_REL}: architect.{key}"
    if not isinstance(a[key], list):
        raise ConfigError(f"{where} must be a list")
    for i, e in enumerate(a[key]):
        if not isinstance(e, dict):
            raise ConfigError(f"{where}[{i}] must be an object")
        unknown = sorted(set(e) - allowed)
        missing = sorted(required - set(e))
        if unknown or missing:
            raise ConfigError(f"{where}[{i}]: " + "; ".join(
                ([f"unknown key(s) {', '.join(unknown)}"] if unknown else [])
                + ([f"missing {', '.join(missing)}"] if missing else [])))
        if not ids.is_rule_id(e["id"]):
            raise ConfigError(f"{where}[{i}]: id {e['id']!r} is not a house-rule id ({ids.rule_shape})")


def _package_docs(given: Any, language: str | None) -> dict[str, Any] | None:
    """§21: the block's settings over their defaults, loaded when plane.json gives the block or `language`
    names a pack (the package-doc checks run on the defaults); None otherwise. Each opt-in rule is checked
    (the language is checked by `_language`)."""
    if given is None and (language is None or language == "none"):
        return None
    pd = _merge(PACKAGE_DOCS_DEFAULTS, given, "package_docs")
    for k in ("source_suffixes", "exempt_dirs"):
        if pd[k] is not None and not (isinstance(pd[k], list) and all(isinstance(x, str) for x in pd[k])):
            raise ConfigError(f"{CONFIG_REL}: package_docs.{k} must be a list of strings or null")
    if not (isinstance(pd["path_ref_suffixes"], list)
            and all(isinstance(x, str) and x.startswith(".") for x in pd["path_ref_suffixes"])):
        raise ConfigError(f"{CONFIG_REL}: package_docs.path_ref_suffixes must be a list like [\".py\", \".md\"]")
    if not isinstance(pd["no_delivery_ids"], bool):
        raise ConfigError(f"{CONFIG_REL}: package_docs.no_delivery_ids must be true or false")
    pats = pd["delivery_id_patterns"]
    if not (isinstance(pats, list) and all(isinstance(x, str) and x for x in pats)):
        raise ConfigError(f"{CONFIG_REL}: package_docs.delivery_id_patterns must be a list of regexes")
    for rx in pats:
        try:
            re.compile(rx)
        except re.error as e:
            raise ConfigError(f"{CONFIG_REL}: package_docs.delivery_id_patterns: {rx!r} is not a regex ({e})") from None
    rules = pd["rules"]
    if not isinstance(rules, dict) or set(rules) - set(DOC_RULES):
        raise ConfigError(f"{CONFIG_REL}: package_docs.rules takes only {', '.join(DOC_RULES)}")
    for name, keys in DOC_RULES.items():
        v = rules.get(name)
        if v is None:
            continue
        if keys is None:
            ok = (isinstance(v, str) and bool(v.strip())) if name == "history_attr" else isinstance(v, bool)
        else:
            ok = (isinstance(v, dict) and set(v) <= keys and "globs" in v
                  and all(isinstance(v.get(k, []), list) and all(isinstance(x, str) for x in v.get(k, []))
                          for k in keys))
            if ok and name == "citations":
                ok = bool(v.get("targets"))
            for k in ("patterns", "ignore"):
                for rx in (v.get(k) or []) if ok else []:
                    try:
                        re.compile(rx)
                    except re.error as e:
                        raise ConfigError(f"{CONFIG_REL}: package_docs.rules.{name}.{k}: {rx!r} is not a regex ({e})") from None
        if not ok:
            want = {"citations": "{globs: [...], targets: [...]}", "no_ids": "{globs: [...], patterns?: [...]}",
                    "history_attr": "a git attribute name", "no_overlap": "true or false",
                    "no_call_bullets": "true or false"}[name]
            raise ConfigError(f"{CONFIG_REL}: package_docs.rules.{name} must be {want}")
    return pd


def _docs(given: Any) -> dict[str, Any]:
    """§21.5: `docs.checks`, product commands `ccp docs check` runs (exit 0 = pass), and `docs.workers`,
    how many check commands run at once."""
    d = _merge(DOCS_DEFAULTS, given, "docs")
    w = d["workers"]
    if isinstance(w, bool) or not isinstance(w, int) or w < 1:
        raise ConfigError(f"{CONFIG_REL}: docs.workers must be an integer >= 1")
    seen: set[str] = set()
    if not isinstance(d["checks"], list):
        raise ConfigError(f"{CONFIG_REL}: docs.checks must be a list of {{id, cmd}}")
    for i, c in enumerate(d["checks"]):
        if not isinstance(c, dict) or set(c) - set(CHECK_KEYS):
            raise ConfigError(f"{CONFIG_REL}: docs.checks[{i}] takes id, cmd and timeout_seconds")
        if not (isinstance(c.get("id"), str) and c["id"].strip()) or c["id"] in seen:
            raise ConfigError(f"{CONFIG_REL}: docs.checks[{i}].id must be a unique non-empty string")
        seen.add(c["id"])
        if not (isinstance(c.get("cmd"), str) and c["cmd"].strip()):
            raise ConfigError(f"{CONFIG_REL}: docs.checks[{i}].cmd must be a command")
        t = c.get("timeout_seconds", 600)
        if isinstance(t, bool) or not isinstance(t, int) or t < 1:
            raise ConfigError(f"{CONFIG_REL}: docs.checks[{i}].timeout_seconds must be an integer >= 1")
    sr = d["starter_rules"]
    if sr is not None:
        declined = sr.get("declined", {}) if isinstance(sr, dict) else None
        if not isinstance(sr, dict) or set(sr) - {"declined"} or not (
                isinstance(declined, dict)
                and all(isinstance(v, str) and v.strip() for v in declined.values())):
            raise ConfigError(f"{CONFIG_REL}: docs.starter_rules must be null or "
                              '{"declined": {"<starter rule>": "<reason>"}}')
        from ccp import rules  # noqa: PLC0415
        unknown = sorted(set(declined) - set(rules.starter_rules()))
        if unknown:
            raise ConfigError(f"{CONFIG_REL}: docs.starter_rules.declined: {', '.join(unknown)} is not a starter "
                              f"rule ({', '.join(rules.starter_rules())})")
    return d


def _architect(given: Any, ids: refs.Ids = refs.DEFAULT) -> dict[str, Any] | None:
    if given is False:
        return None  # the one way to turn the seat off (§19.11)
    if given is True:
        raise ConfigError(f"{CONFIG_REL}: `architect` must be an object, or false to turn the seat off")
    a = _merge(ARCHITECT_DEFAULTS, given, "architect")
    bad = []
    for k, lo in _INTS.items():
        v = a[k]
        if isinstance(v, bool) or not isinstance(v, int) or v < lo:
            bad.append(f"{k} must be an integer >= {lo}")
    if isinstance(a["drift_ratio"], bool) or not isinstance(a["drift_ratio"], (int, float)) or a["drift_ratio"] <= 0:
        bad.append("drift_ratio must be a number > 0")
    if not isinstance(a["shape_adrs"], bool):
        bad.append("shape_adrs must be true or false")
    if not isinstance(a["refactor_in_scope"], bool) and a["refactor_in_scope"] != "deps":
        bad.append('refactor_in_scope must be "deps", true or false')
    for k in _STR_LISTS:
        if not isinstance(a[k], list) or not all(isinstance(x, str) and x.strip() for x in a[k]):
            bad.append(f"{k} must be a list of non-empty strings")
    if a["rules_doc"] is not None and not (isinstance(a["rules_doc"], str) and a["rules_doc"].strip()):
        bad.append("rules_doc must be a path")
    sft = a["shape_from_task"]
    if sft is not None and not re.match(rf"^[0-9]{{{ids.task_width}}}(?:-|$)", str(sft)):
        bad.append("shape_from_task must be a task number (NNNN) or id")
    if a["shape_adrs"] is True and sft is None:
        bad.append("shape_adrs needs shape_from_task, so tasks written before the check do not fail")
    areas = a["areas"]
    if not isinstance(areas, dict) or not all(
            isinstance(v, list) and all(isinstance(g, str) and g for g in v) for v in areas.values()):
        bad.append("areas must map an area name to a list of globs")
    if bad:
        raise ConfigError(f"{CONFIG_REL}: architect: " + "; ".join(bad))
    _entries(a, "checks", set(CHECK_KEYS), {"id", "cmd"}, ids)
    _entries(a, "budgets", set(BUDGET_KEYS), {"id"}, ids)
    for i, b in enumerate(a["budgets"]):
        if ("glob" in b) == ("path" in b) or not ({"max_lines", "max_bytes"} & set(b)):
            raise ConfigError(f"{CONFIG_REL}: architect.budgets[{i}] needs one of glob or path, "
                              "and max_lines or max_bytes")
        for k in ("glob", "path"):
            if k in b and not (isinstance(b[k], str) and b[k].strip()):
                raise ConfigError(f"{CONFIG_REL}: architect.budgets[{i}].{k} must be a path or glob")
        for k in ("max_lines", "max_bytes"):
            if k in b and (isinstance(b[k], bool) or not isinstance(b[k], int) or b[k] < 1):
                raise ConfigError(f"{CONFIG_REL}: architect.budgets[{i}].{k} must be an integer >= 1")
        if "cut_line" in b:  # a warning line below the one limit it sits under (§20.2)
            limits = [b[k] for k in ("max_lines", "max_bytes") if k in b]
            c = b["cut_line"]
            if len(limits) != 1:
                raise ConfigError(f"{CONFIG_REL}: architect.budgets[{i}].cut_line needs exactly one of max_lines "
                                  "or max_bytes, the limit it sits under")
            if isinstance(c, bool) or not isinstance(c, int) or not 1 <= c < limits[0]:
                raise ConfigError(f"{CONFIG_REL}: architect.budgets[{i}].cut_line must be an integer >= 1 "
                                  f"and below the limit ({limits[0]})")
    for i, c in enumerate(a["checks"]):
        if not isinstance(c["cmd"], str) or not c["cmd"].strip():
            raise ConfigError(f"{CONFIG_REL}: architect.checks[{i}].cmd must be a command")
        t = c.get("timeout_seconds", 600)
        if isinstance(t, bool) or not isinstance(t, int) or t < 1:
            raise ConfigError(f"{CONFIG_REL}: architect.checks[{i}].timeout_seconds must be an integer >= 1")
    overlaps = _check_overlaps(a["checks"])
    if overlaps:
        raise ConfigError(f"{CONFIG_REL}: architect.checks: " + "; ".join(overlaps)
                          + " (a test runs once per gate, under one check)")
    return a


def _check_overlaps(checks: list[dict[str, Any]]) -> list[str]:
    """§19.11: each pair of checks whose test selectors meet, the same module, class or test, or one
    inside the other, naming both ids and the narrower selector, which both would run."""
    from ccp import docrules  # noqa: PLC0415
    sels = [(c["id"], docrules.test_selectors(c["cmd"])) for c in checks]
    out = []
    for i, (a, sa) in enumerate(sels):
        for b, sb in sels[i + 1:]:
            shared = {max(x, y, key=len) for x in sa for y in sb
                      if x == y or y.startswith(x + ".") or x.startswith(y + ".")}
            out += [f"{a} and {b} both select {s}" for s in sorted(shared)]
    return out


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def lane_stages(v: Any) -> list[dict[str, str]] | None:
    """A `suite.lanes` value's stages (§14.2) when it is the staged form, a list of objects; None for
    the argv form."""
    if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
        return v
    return None


def _stages_problem(lane: str, v: list[dict[str, Any]]) -> str | None:
    seen: set[str] = set()
    for i, st in enumerate(v):
        name = st.get("name")
        if set(st) != SUITE_STAGE_KEYS or not isinstance(name, str) or not SUITE_LANE_RE.match(name) \
                or not isinstance(st.get("cmd"), str) or not st["cmd"].strip():
            return (f"suite.lanes.{lane}[{i}] must be {{name, cmd}}: a stage name (lowercase, at most 32 "
                    "characters) and a non-empty shell command")
        if name == PLANE_DOCS_STAGE:
            return f"suite.lanes.{lane}[{i}]: the stage name {PLANE_DOCS_STAGE!r} is the plane's own (§14.2)"
        if name in seen:
            return f"suite.lanes.{lane}: the stage name {name!r} is given twice"
        seen.add(name)
    return None


def gate_stage_names(suite_block: dict[str, Any]) -> list[str]:
    """The stages the gate role's lane declares (§14.2), the ones a prover may skip; [] for an argv lane or
    none. The plane's own `plane-docs` stage is never among them."""
    roles = suite_block.get("roles") if isinstance(suite_block.get("roles"), dict) else {}
    lanes = suite_block.get("lanes") if isinstance(suite_block.get("lanes"), dict) else {}
    st = lane_stages(lanes.get(str(roles.get("gate") or SUITE_DEFAULTS["roles"]["gate"])))
    return [str(x.get("name")) for x in st or []]


def _provers_problems(v: Any, suite_block: dict[str, Any]) -> list[str]:
    """`verify.provers` (§14.2, §15.2): a list of `{name, command, skips}`, each name a unique label and
    `skips` the review or a stage of the gate role's lane."""
    if not isinstance(v, list):
        return ["verify.provers must be a list of {name, command, skips}"]
    bad: list[str] = []
    seen: set[str] = set()
    stages = gate_stage_names(suite_block)
    for i, p in enumerate(v):
        where = f"verify.provers[{i}]"
        if not isinstance(p, dict) or set(p) != PROVER_KEYS:
            bad.append(f"{where} must be {{name, command, skips}}")
            continue
        name, cmd, skips = p["name"], p["command"], p["skips"]
        if not isinstance(name, str) or not SUITE_LANE_RE.match(name):
            bad.append(f"{where}.name must be a label (lowercase, at most 32 characters)")
        elif name in seen:
            bad.append(f"verify.provers: the name {name!r} is given twice")
        else:
            seen.add(name)
        if not (isinstance(cmd, str) and cmd.strip()):
            bad.append(f"{where}.command must be a shell command (exit 0 = the step it skips is redundant)")
        if skips != PROVER_REVIEW and (not isinstance(skips, str) or skips not in stages):
            bad.append(f"{where}.skips must be {PROVER_REVIEW!r} or a stage the gate lane declares "
                       f"(stages: {', '.join(stages) or 'none'})")
    return bad


def _rel_path(v: Any) -> bool:
    """A path relative to the product root, as a git pathspec: not empty, not absolute, no `..`, no `:`
    pathspec magic."""
    return isinstance(v, str) and bool(v.strip()) and not v.startswith(("/", ":")) and ".." not in Path(v).parts


# Paths a match-everything entry would cover (`_every_path`): each below a directory, as nearly every file
# in a product is, in unlike directories and names, so only a pattern that leaves at most the top-level
# files to its check matches them all.
EVERY_PATH_PROBES = ("a/b", "src/pkg/mod.py", ".github/workflows/ci.yml", "Docs/Read Me", "0/1/2/3/x.tar.gz",
                     "_/.env", "Z/q")


def _pathspec_hits(spec: str, path: str) -> bool:
    """Does the git pathspec `spec` (no magic, already normalised) cover `path`, as git's default matching
    does: the path itself or a directory above it, or the whole path as a wildcard pattern in which `*`
    and `?` also match `/` and `[!…]` or `[^…]` negates a set."""
    if path == spec or path.startswith(spec.rstrip("/") + "/"):
        return True
    return bool(set("*?[") & set(spec)) and fnmatch.fnmatchcase(path, spec.replace("[^", "[!"))


def _every_path(where: str, paths: list[Any]) -> list[str]:
    """The entries of a path list that match every path, so a check they narrow would never fire: the root
    itself (`.`, `./`, anything that normalises to it), or a pattern that covers every path in
    `EVERY_PATH_PROBES` (`*`, `**`, `./*`, `*/**`, `**/*`, `?*` alike). Each is named;
    `merge.behind_tip_ignore` and `verify.skip_review.paths` refuse them alike."""
    norm = [(x, os.path.normpath(x)) for x in paths if isinstance(x, str) and x.strip()]
    return [f"{where}: {x!r} matches every path; name the paths it covers" for x, n in norm
            if n == "." or all(_pathspec_hits(n, p) for p in EVERY_PATH_PROBES)]


def _notify_lead(lead: Any) -> str | None:
    """§3.6 `notify.lead`: null, or exactly `{tool, to}`, each a non-empty one-line string. The reason
    it is refused, else None."""
    if lead is None:
        return None
    want = "notify.lead must be an object with exactly `tool` and `to`, each a non-empty one-line string"
    if not isinstance(lead, dict) or set(lead) != set(NOTIFY_LEAD_KEYS):
        extra = sorted(set(lead) - set(NOTIFY_LEAD_KEYS)) if isinstance(lead, dict) else []
        missing = [k for k in NOTIFY_LEAD_KEYS if isinstance(lead, dict) and k not in lead]
        return want + "".join([f" (unknown: {', '.join(extra)})" if extra else "",
                               f" (missing: {', '.join(missing)})" if missing else ""])
    # one line as render takes it: neither a newline nor a carriage return
    if not all(isinstance(lead[k], str) and lead[k].strip() and not {"\n", "\r"} & set(lead[k])
               for k in NOTIFY_LEAD_KEYS):
        return want
    return None


def _opt_str(v: Any) -> bool:
    return v is None or (isinstance(v, str) and bool(v.strip()))


def _report_fields(fields: Any) -> list[str]:
    """§13.4 `report.required_fields`: a list of `{name, values}`, names unique and none of the lines
    `ccp report` already reads, values a non-empty list of distinct one-line strings."""
    where = "report.required_fields"
    if not isinstance(fields, list):
        return [f"{where} must be a list of {{name, values}}"]
    bad: list[str] = []
    seen: set[str] = set()
    for i, f in enumerate(fields):
        if not isinstance(f, dict) or set(f) != set(REPORT_FIELD_KEYS):
            bad.append(f"{where}[{i}] must be {{name, values}}")
            continue
        name, values = f["name"], f["values"]
        if not isinstance(name, str) or not REPORT_FIELD_NAME_RE.match(name) or name != name.strip():
            bad.append(f"{where}[{i}].name must be a letter then up to 39 letters, digits, spaces, `_` or `-`")
        elif name.lower() in REPORT_OWN_LINES:
            bad.append(f"{where}[{i}].name {name!r} is a line ccp report already reads")
        elif name.lower() in seen:
            bad.append(f"{where}[{i}].name {name!r} is declared twice")
        else:
            seen.add(name.lower())
        if not (isinstance(values, list) and values and all(
                isinstance(v, str) and v.strip() == v and v and "\n" not in v and "\r" not in v for v in values)
                and len({v.lower() for v in values}) == len(values)):
            bad.append(f"{where}[{i}].values must be a non-empty list of distinct one-line strings")
    return bad


def _usage(given: Any) -> dict[str, Any]:
    """§24.6 the `usage` block: `advice` merged key by key over its defaults, so one knob given keeps the others."""
    out = _merge(USAGE_DEFAULTS, given, "usage")
    out["advice"] = _merge(USAGE_DEFAULTS["advice"], given.get("advice") if isinstance(given, dict) else None,
                           "usage.advice")
    return out


def _models(given: Any) -> dict[str, Any]:
    """§2.4 the `models` block: the role defaults with the roles plane.json names, each an alias the Agent
    call's `model` accepts (`WORKER_MODEL_ALIASES`); a key that is no role, or any other value, is refused."""
    if given is None:
        return copy.deepcopy(MODELS_DEFAULTS)
    if not isinstance(given, dict):
        raise ConfigError(f"{CONFIG_REL}: `models` must be an object")
    bad = []
    for k, v in given.items():
        if k not in MODELS_DEFAULTS:
            bad.append(f"models.{k} is not a role: one of " + ", ".join(MODELS_DEFAULTS))
        elif v not in WORKER_MODEL_ALIASES:
            bad.append(f"models.{k} must be one of " + ", ".join(WORKER_MODEL_ALIASES)
                       + f", the aliases the Agent call's model accepts, not {v!r} (SPEC §2.4)")
    if bad:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad))
    return {**MODELS_DEFAULTS, **given}


def _workers_problems(w: dict[str, Any]) -> list[str]:
    """§2.4 the `workers` block: `implementer_model` null or an object of `small` and `refactor`, each an alias
    the Agent call's `model` accepts (`WORKER_MODEL_ALIASES`), `small_estimate_minutes` an integer >= 1."""
    bad = []
    im = w["implementer_model"]
    if im is not None:
        if not isinstance(im, dict) or not set(im) <= set(WORKER_MODEL_ARMS):
            bad.append("workers.implementer_model must be null or an object of " + " and ".join(WORKER_MODEL_ARMS)
                       + ", each one of " + ", ".join(WORKER_MODEL_ALIASES))
        else:
            for k, v in im.items():
                if v not in WORKER_MODEL_ALIASES:
                    bad.append(f"workers.implementer_model.{k} must be one of " + ", ".join(WORKER_MODEL_ALIASES)
                               + f", the aliases the Agent call's model accepts, not {v!r} (SPEC §2.4)")
    m = w["small_estimate_minutes"]
    if isinstance(m, bool) or not isinstance(m, int) or m < 1:
        bad.append("workers.small_estimate_minutes must be an integer >= 1")
    return bad


def _toolkit(raw: dict[str, Any], root: Path) -> dict[str, dict[str, Any]]:
    """The §10 blocks, merged with their defaults and checked value by value: they drive merges,
    commits and commands, so a wrong type fails loudly."""
    out = {b: _merge(BLOCK_DEFAULTS[b], raw.get(b), b) for b in BLOCKS if b not in _OWN_LOADER_BLOCKS}
    out["usage"] = _usage(raw.get("usage"))
    out["suite"] = _suite(raw.get("suite"))
    out["models"] = _models(raw.get("models"))
    bad = []
    if not isinstance(raw.get("task_log", {}).get("index", True), bool):
        bad.append("task_log.index must be true or false")
    kinds = raw.get("task_log", {}).get("kinds", TASK_LOG_DEFAULTS["kinds"])
    if not isinstance(kinds, dict) or not kinds or not all(
            isinstance(k, str) and isinstance(v, dict) and set(v) <= set(KIND_KEYS)
            and all(isinstance(v.get(x, []), list) and all(isinstance(i, str) for i in v.get(x, []))
                    for x in ("refs_any", "forbid")) for k, v in kinds.items()):
        bad.append("task_log.kinds must map each kind to {refs_any: [lists], forbid: [lists]}")
    rd = raw.get("task_log", {}).get("reviews_dir", "reviews")
    if not (isinstance(rd, str) and rd.strip()) or rd.startswith("/") or ".." in Path(rd).parts:
        bad.append("task_log.reviews_dir must be a path relative to task_log.dir")
    if not isinstance(raw.get("task_log", {}).get("dry_run", False), bool):
        bad.append("task_log.dry_run must be true or false")
    sp = raw.get("spec_paths", list(SPEC_PATHS_DEFAULT))
    if not isinstance(sp, list) or not all(isinstance(x, str) and x.strip() and not x.startswith("/")
                                           and ".." not in Path(x).parts for x in sp):
        bad.append("spec_paths must be a list of paths relative to the product root")
    par = out["parallel"]
    mif = par["max_in_flight"]
    if isinstance(mif, bool) or not isinstance(mif, int) or not 1 <= mif <= 4:
        bad.append("parallel.max_in_flight must be an integer from 1 to 4")
    if not isinstance(par["exclusive"], list) or not all(isinstance(x, str) and x.strip() for x in par["exclusive"]):
        bad.append("parallel.exclusive must be a list of paths or globs")
    if not isinstance(par["shared"], list) or not all(isinstance(x, str) and x.strip() for x in par["shared"]):
        bad.append("parallel.shared must be a list of paths or globs")
    elif isinstance(par["exclusive"], list):  # §16.2: an entry listed in both, as written (`./`, a trailing `/` aside)
        both = sorted({x.strip().removeprefix("./").rstrip("/") for x in par["shared"]}
                      & {x.strip().removeprefix("./").rstrip("/") for x in par["exclusive"] if isinstance(x, str)})
        if both:
            bad.append(f"parallel.shared and parallel.exclusive both list {', '.join(both)}: a path may not be both")
    scp = par["session_ceiling_pct"]
    if isinstance(scp, bool) or not isinstance(scp, (int, float)) or not 0 < scp <= 100:
        bad.append("parallel.session_ceiling_pct must be a number above 0, at most 100")
    if par["schedule"] not in PARALLEL_SCHEDULES:
        bad.append(f"parallel.schedule must be one of {', '.join(PARALLEL_SCHEDULES)}, not {par['schedule']!r}")
    rpf = out["review_points"]["file"]
    if not (isinstance(rpf, str) and rpf.strip()) or rpf.startswith("/") or ".." in Path(rpf).parts:
        bad.append("review_points.file must be a path relative to the product root")
    bad += _report_fields(out["report"]["required_fields"])
    if not _opt_str(out["prompts"]["fragment"]):
        bad.append("prompts.fragment must be a path")
    if not isinstance(out["prompts"]["keep_body"], bool):
        bad.append("prompts.keep_body must be true or false")
    akd = out["prompts"]["audit_keep_days"]
    if akd is not None and (isinstance(akd, bool) or not isinstance(akd, int) or akd < 1):
        bad.append("prompts.audit_keep_days must be an integer >= 1 (days a prompt audit is kept), or null to keep all")
    wenv = out["prompts"]["worker_env"]
    if not isinstance(wenv, dict):
        bad.append("prompts.worker_env must be an object of NAME: template")
    else:
        for k, v in wenv.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k):
                bad.append(f"prompts.worker_env: {k!r} is not a shell variable name")
            elif not isinstance(v, str) or "\n" in v or "\0" in v:
                bad.append(f"prompts.worker_env.{k} must be a one-line string")
            elif unknown := sorted(set(re.findall(r"\{\{(\w+)\}\}", v)) - set(WORKER_ENV_FIELDS)):
                bad.append(f"prompts.worker_env.{k} names {', '.join(unknown)}; the fields are "
                           f"{', '.join(WORKER_ENV_FIELDS)}")
    log = out["reconcile"]["log"]
    if log is not None:
        if not isinstance(log, dict) or set(log) - RECONCILE_LOG_KEYS or not {"path", "entry"} <= set(log) \
                or not all(isinstance(v, str) and v.strip() for v in log.values()):
            bad.append("reconcile.log must be {path, entry[, before]}, each a non-empty string")
        elif "before" in log:
            try:
                re.compile(log["before"])
            except re.error as e:
                bad.append(f"reconcile.log.before is not a regular expression ({e})")
    if isinstance(log, dict) and isinstance(log.get("entry"), str):
        try:
            log["entry"].format(**{k: "x" for k in RECONCILE_LOG_FIELDS})
        except (KeyError, IndexError, ValueError) as e:
            bad.append(f"reconcile.log.entry: {e!r}; it may name {', '.join(RECONCILE_LOG_FIELDS)}")
    for cmd in out["adapter"]["post_close"] if _str_list(out["adapter"]["post_close"]) else []:
        try:
            cmd.format(task_id="x", nnnn="x")
        except (KeyError, IndexError, ValueError) as e:
            bad.append(f"adapter.post_close {cmd!r}: {e!r}; it may name task_id and nnnn")
    if not _str_list(out["reconcile"]["hooks"]):
        bad.append("reconcile.hooks must be a list of commands")
    if not _str_list(out["adapter"]["post_close"]):
        bad.append("adapter.post_close must be a list of non-empty strings")
    bad += _worktree_blocks(raw, out, root)
    tel = out["telemetry"]
    if not _opt_str(tel["allowance_cmd"]):
        bad.append("telemetry.allowance_cmd must be a command")
    stop = tel["allowance_stop_weekly"]
    if stop is not None and (isinstance(stop, bool) or not isinstance(stop, (int, float)) or not 0 < stop <= 100):
        bad.append("telemetry.allowance_stop_weekly must be a percentage")
    for k in ("session_park_pct", "session_wake_arm_pct"):
        v = tel[k]
        if (v is not None or k == "session_wake_arm_pct") and (isinstance(v, bool) or not isinstance(v, (int, float))
                                                               or not 0 < v <= 100):
            bad.append(f"telemetry.{k} must be a percentage" + (" or null" if k == "session_park_pct" else ""))
    mg = tel["session_wake_margin_s"]
    if isinstance(mg, bool) or not isinstance(mg, int) or not 0 <= mg <= 3600:
        bad.append("telemetry.session_wake_margin_s must be whole seconds from 0 to 3600")
    wins = tel["windows"]
    if wins is not None:
        ok = isinstance(wins, dict) and all(
            isinstance(n, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", n) and isinstance(w, dict)
            and not set(w) - set(WINDOW_KEYS) and w.get("kind", "weekly") in ("weekly", "session")
            and all(w.get(k) is None or (not isinstance(w[k], bool) and isinstance(w[k], (int, float)) and 0 < w[k] <= 100)
                    for k in ("stop_pct", "park_pct"))
            for n, w in wins.items())
        if not ok:
            bad.append("telemetry.windows must map window names to {kind: weekly|session, stop_pct, park_pct} "
                       "(percentages or null)")
        else:
            builtin = {"seven_day": "weekly", "five_hour": "session"}
            given = raw.get("telemetry") or {}
            for n, w in wins.items():
                kind = w.get("kind", builtin.get(n, "weekly"))
                if kind == "session" and w.get("stop_pct") is not None:
                    bad.append(f"telemetry.windows.{n}: a session window has no stop_pct (it parks: park_pct)")
                if kind == "weekly" and w.get("park_pct") is not None:
                    bad.append(f"telemetry.windows.{n}: a weekly window has no park_pct (it stops: stop_pct)")
            if "allowance_stop_weekly" in given and "stop_pct" in (wins.get("seven_day") or {}):
                bad.append("telemetry: set the seven_day stop once, as allowance_stop_weekly or windows.seven_day.stop_pct")
            if "session_park_pct" in given and "park_pct" in (wins.get("five_hour") or {}):
                bad.append("telemetry: set the five_hour park once, as session_park_pct or windows.five_hour.park_pct")
    ds = tel["design_seat"]
    if ds is not None and (not isinstance(ds, dict) or set(ds) - set(DESIGN_SEAT_KEYS)
                           or not all(isinstance(v, str) and v.strip() for v in ds.values())):
        bad.append("telemetry.design_seat must be {model, effort}, each a string")
    est = out["estimate"]
    ps = est["path_suffixes"]
    if ps is not None and not (_str_list(ps) and all(s.startswith(".") for s in ps)):
        bad.append("estimate.path_suffixes must be a list of suffixes like \".py\", or null")
    rs = est["reference_since"]
    if rs is not None and not (isinstance(rs, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", rs)):
        bad.append("estimate.reference_since must be a date (YYYY-MM-DD) or null")
    if isinstance(est["k"], bool) or not isinstance(est["k"], int) or not 5 <= est["k"] <= 8:
        bad.append("estimate.k must be an integer from 5 to 8")
    if not isinstance(est["auto"], bool):
        bad.append("estimate.auto must be true or false")
    cal = est["calibration"]
    _num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if not isinstance(cal, dict) or set(cal) - set(ESTIMATE_DEFAULTS["calibration"]):
        bad.append("estimate.calibration must be {half_life, min_pairs, k}")
    else:
        if "half_life" in cal and not (_num(cal["half_life"]) and cal["half_life"] > 0):
            bad.append("estimate.calibration.half_life must be a positive number of merges")
        if "min_pairs" in cal and not (isinstance(cal["min_pairs"], int) and not isinstance(cal["min_pairs"], bool)
                                       and cal["min_pairs"] >= 3):
            bad.append("estimate.calibration.min_pairs must be an integer of at least 3")
        if cal.get("k") is not None and not (_num(cal["k"]) and cal["k"] > 0):
            bad.append("estimate.calibration.k must be a positive number or null")
    rm = out["board"]["refresh_minutes"]
    if isinstance(rm, bool) or not isinstance(rm, int) or rm < 1:
        bad.append("board.refresh_minutes must be an integer >= 1")
    lim, cut = out["gate"]["shell_limit_seconds"], out["gate"]["cut_line_seconds"]
    if not (_num(lim) and lim > 0):
        bad.append("gate.shell_limit_seconds must be a number of seconds above 0")
    elif cut is not None and not (_num(cut) and 0 < cut <= lim):
        bad.append("gate.cut_line_seconds must be a number of seconds above 0, at most gate.shell_limit_seconds, "
                   "or null for 90% of it")
    stl = out["health"]["small_task_lines"]
    if isinstance(stl, bool) or not isinstance(stl, int) or stl < 1:
        bad.append("health.small_task_lines must be an integer >= 1")
    for k in ("slowest_modules", "suite_trend_runs"):
        v = out["health"][k]
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            bad.append(f"health.{k} must be an integer >= 1")
    adv = out["usage"]["advice"]
    for k in ("cache_5m_share", "coordination_share"):
        if not (_num(adv[k]) and 0 <= adv[k] <= 1):
            bad.append(f"usage.advice.{k} must be a number from 0 to 1")
    ct = adv["context_tokens"]
    if isinstance(ct, bool) or not isinstance(ct, int) or ct < 1:
        bad.append("usage.advice.context_tokens must be an integer >= 1")
    wh = adv["window_hours"]
    if isinstance(wh, bool) or not isinstance(wh, int) or wh < 0:
        bad.append("usage.advice.window_hours must be an integer >= 0 (0: every request)")
    lanes = out["suite"]["lanes"]
    if not isinstance(lanes, dict) or not all(
            isinstance(k, str) and SUITE_LANE_RE.match(k) and (_str_list(v) and v or lane_stages(v) is not None)
            for k, v in lanes.items()):
        bad.append("suite.lanes must map a lane name (lowercase, at most 32 characters) to a non-empty argv list "
                   "or a non-empty list of {name, cmd} stages")
    elif staged := [p for k, v in lanes.items() if (st := lane_stages(v)) is not None
                    and (p := _stages_problem(k, st))]:
        bad.append(staged[0])
    elif held := [k for k, v in lanes.items()
                  if any(LANE_PLACEHOLDER in a for a in ([x["cmd"] for x in lane_stages(v) or []] or v))]:
        bad.append(f"suite.lanes {', '.join(held)} still hold the placeholder {LANE_PLACEHOLDER!r}: "
                   "write the command that runs the product's tests in its place")
    xl = out["suite"]["exclusive_lanes"]
    if not isinstance(xl, list) or not all(isinstance(x, str) and SUITE_LANE_RE.match(x) for x in xl):
        bad.append("suite.exclusive_lanes must be a list of lane names")
    ro = out["suite"]["roles"]
    if not isinstance(ro, dict) or set(ro) - set(SUITE_ROLES) or not all(
            isinstance(v, str) and SUITE_LANE_RE.match(v) for v in ro.values()):
        bad.append(f"suite.roles must map {', '.join(SUITE_ROLES)} to lane names")
    elif len(set({**SUITE_DEFAULTS["roles"], **ro}.values())) < len(SUITE_ROLES):
        bad.append("suite.roles must give each role its own lane name")
    cre = out["suite"]["count_re"]
    if cre is not None:
        if not (_str_list([cre]) or _str_list(cre) and cre):  # a blank pattern would count every line
            bad.append("suite.count_re must be a regular expression or a non-empty list of them")
        else:
            try:
                for pat in [cre] if isinstance(cre, str) else cre:
                    re.compile(pat)
            except re.error as e:
                bad.append(f"suite.count_re is not a regular expression ({e})")
    am = out["suite"]["affected_map"]
    if not isinstance(am, dict) or not all(k.strip() and _str_list(v) and v for k, v in am.items()):
        bad.append("suite.affected_map must map a path glob to a list of test ids (§14.7)")
    kd = out["suite"]["log_keep_days"]
    if isinstance(kd, bool) or not isinstance(kd, int) or kd < 1:
        bad.append("suite.log_keep_days must be an integer >= 1 (days a summary-mode log is kept)")
    sm = out["suite"]["summary"]
    if sm is not None:
        if not isinstance(sm, dict) or set(sm) - set(SUITE_SUMMARY_DEFAULTS):
            bad.append(f"suite.summary must be an object of {', '.join(SUITE_SUMMARY_DEFAULTS)}")
        else:
            for k, v in sm.items():
                if k in ("tail_lines", "max_chars"):
                    if isinstance(v, bool) or not isinstance(v, int) or v < (0 if k == "tail_lines" else 1000):
                        bad.append(f"suite.summary.{k} must be an integer >= {0 if k == 'tail_lines' else 1000}")
                    continue
                pats = v if isinstance(v, list) else [v]
                need = 0 if k in ("section_re", "show_re") else 1
                try:
                    if not pats and need or not all(isinstance(x, str) and re.compile(x).groups >= need for x in pats):
                        raise re.error("each needs a group that captures the number" if need else "not a pattern")
                except re.error as e:
                    bad.append(f"suite.summary.{k} is not a regular expression, or a list of them, "
                               f"{'with a number group ' if need else ''}({e})")
    ac = out["verify"]["accept_cache"]
    if ac is not None:
        if not isinstance(ac, dict) or set(ac) - set(ACCEPT_CACHE_DEFAULTS):
            bad.append("verify.accept_cache must be {max_age_days[, cold_tasks][, review]}, or null for off")
        else:
            ac = out["verify"]["accept_cache"] = {**ACCEPT_CACHE_DEFAULTS, **ac}
            age = ac["max_age_days"]
            if isinstance(age, bool) or not isinstance(age, int) or age < 1:
                bad.append("verify.accept_cache.max_age_days must be an integer >= 1")
            if not isinstance(ac["cold_tasks"], list) or not all(isinstance(x, str) and x.strip() for x in ac["cold_tasks"]):
                bad.append("verify.accept_cache.cold_tasks must be a list of task-id globs")
            if not isinstance(ac["review"], bool):
                bad.append("verify.accept_cache.review must be true or false")
    sr = out["verify"]["skip_review"]
    if sr is not None:
        if not isinstance(sr, dict) or set(sr) != SKIP_REVIEW_KEYS:
            bad.append("verify.skip_review must be {paths, proof}, or null for off")
        else:
            if not isinstance(sr["paths"], list) or not sr["paths"] or not all(_rel_path(x) for x in sr["paths"]):
                bad.append("verify.skip_review.paths must be a non-empty list of paths relative to the product root, "
                           "none of them the root itself")
            else:
                bad += _every_path("verify.skip_review.paths", sr["paths"])
            if not (isinstance(sr["proof"], str) and sr["proof"].strip()):
                bad.append("verify.skip_review.proof must be a shell command (exit 0 = the fix is proven)")
    if not isinstance(out["verify"]["skip_review_after_clean"], bool):
        bad.append("verify.skip_review_after_clean must be true or false")
    bad += _provers_problems(out["verify"]["provers"], out["suite"])
    mu = out["mutate"]
    if not _opt_str(mu["command"]):
        bad.append("mutate.command must be a shell command naming {test}, or null for none")
    elif mu["command"] is not None and "{test}" not in mu["command"]:
        bad.append("mutate.command must name {test}: it runs the one test a mutant is judged by (§20.6)")
    t = mu["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("mutate.timeout_seconds must be an integer >= 1")
    ub = mu["unbuilt_re"]
    if ub is not None:
        try:
            if not (_str_list([ub]) or _str_list(ub) and ub):
                raise re.error("a blank pattern would match every line")
            for pat in [ub] if isinstance(ub, str) else ub:
                re.compile(pat)
        except re.error as e:
            bad.append(f"mutate.unbuilt_re must be a regular expression or a non-empty list of them, or null ({e})")
    bad += _workers_problems(out["workers"])
    nt = out["notify"]
    if not _opt_str(nt["command"]):
        bad.append("notify.command must be a shell command, or null for the lead's session")
    t = nt["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("notify.timeout_seconds must be an integer >= 1")
    if (why := _notify_lead(nt["lead"])):
        bad.append(why)
    if bad:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad))
    return out


def _is_main_checkout(root: Path, d: Any) -> bool:
    """§12.1: whether `worktrees.dir` `d` names the main checkout of the product at `root` itself. One with
    no `..` and not absolute does when it normalises to `.`; any other is resolved against the main checkout
    (`wt.main_of`, which asks git) and compared with it."""
    if not isinstance(d, str) or not d.strip():
        return False
    if not Path(d).is_absolute() and ".." not in Path(d).parts:
        return os.path.normpath(d) == "."
    from ccp.wt import main_of  # noqa: PLC0415  (wt imports this module)

    main = main_of(root)
    return (main / d).resolve() == main.resolve()


def _worktree_blocks(raw: dict[str, Any], out: dict[str, Any], root: Path) -> list[str]:
    """§12.1: worktrees, env hooks, merge and auth probes (`worktrees.dir` and `.links` were `adapter.worktree_dir`
    and `.worktree_links`, merged in when plane.json loads)."""
    bad: list[str] = []
    wt = out["worktrees"]
    if not _opt_str(wt["dir"]):
        bad.append(WORKTREES_DIR_RULE.format("worktrees.dir"))
    elif _is_main_checkout(root, wt["dir"]):
        bad.append(WORKTREES_DIR_RULE.format("worktrees.dir") + ", not the main checkout itself")
    if not isinstance(wt["links"], list) or not all(isinstance(x, str) and x.strip() for x in wt["links"]):
        bad.append("worktrees.links must be a list of paths")
    env = out["env"]
    for h in ENV_HOOKS:
        if not _opt_str(env[h]):
            bad.append(f"env.{h} must be a shell command, or null")
    t = env["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("env.timeout_seconds must be an integer >= 1")
    mc = out["merge"]["command"]
    if not _opt_str(mc):
        bad.append("merge.command must be a shell command, or null for the default")
    elif mc is not None and "{head_sha}" not in mc:
        bad.append("merge.command must name {head_sha}: the merge is pinned to the verified head (§15.5)")
    bti = out["merge"]["behind_tip_ignore"]
    if not isinstance(bti, list) or not all(_rel_path(x) for x in bti):
        bad.append("merge.behind_tip_ignore must be a list of paths relative to the product root")
    else:
        bad += _every_path("merge.behind_tip_ignore", bti)
    au = out["auth_check"]
    pr = au["probes"]
    if not isinstance(pr, list) or not all(isinstance(x, dict) and set(x) == set(PROBE_KEYS)
                                           and all(isinstance(x[k], str) and x[k].strip() for k in ("id", "cmd"))
                                           for x in pr):
        bad.append("auth_check.probes must be a list of {id, cmd}")
    elif len({x["id"] for x in pr}) != len(pr):
        bad.append("auth_check.probes ids must be unique")
    t = au["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("auth_check.timeout_seconds must be an integer >= 1")
    return bad


def _adr(given: Any) -> dict[str, Any] | None:
    if given is None:
        return None
    a = _merge(ADR_DEFAULTS, given, "adr")
    bad = []
    if not (isinstance(a["dir"], str) and a["dir"].strip()):
        bad.append("adr.dir must be a path")
    if not _opt_str(a["index"]):
        bad.append("adr.index must be a path, or null for no index")
    if not _str_list(a["statuses"]) or not a["statuses"]:
        bad.append("adr.statuses must be a non-empty list of strings")
    tr = a["transitions"]
    if not isinstance(tr, dict) or not all(isinstance(k, str) and _str_list(v) for k, v in tr.items()):
        bad.append("adr.transitions must map a status to the list of statuses it may move to")
    elif _str_list(a["statuses"]) and any(s not in a["statuses"] for k, v in tr.items() for s in [k, *v]):
        bad.append("adr.transitions names a status that is not in adr.statuses")
    if not isinstance(a["strict"], bool):
        bad.append("adr.strict must be true or false")
    if not _opt_str(a["template"]):
        bad.append("adr.template must be a path, or null for the plane's template")
    if bad:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad))
    return a


def _upgrade(given: Any) -> dict[str, Any]:
    """§29.3: `upgrade.declined` and `upgrade.taken`, each task id -> the reason the product declined that
    task's `adopt` step, or took it in a way `ccp upgrade status` cannot see."""
    u = _merge(UPGRADE_DEFAULTS, given, "upgrade")
    for key, what in (("declined", "declined its adopt step"), ("taken", "took its adopt step")):
        d = u[key]
        if not isinstance(d, dict) or not all(isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
                                              for k, v in d.items()):
            raise ConfigError(f"{CONFIG_REL}: upgrade.{key} must map a plane task id to the reason the product "
                              f"{what} (SPEC §29.3)")
    return u


@dataclass(frozen=True)
class _Each:
    """In `PLANE_KEYS`: a list, or an object whose names are the product's own, whose every item has `shape`."""
    shape: Any


def _known(keys: Any, *, old: str = "", **nested: Any) -> dict[str, Any]:
    """An object's known keys (a defaults dict's, or a sequence, and the `KEY_OUTCOMES` keys under the dotted
    path `old`), each with no shape of its own but `nested`'s."""
    return {**dict.fromkeys(keys), **dict.fromkeys(old_keys(old)), **nested}


# §8.1: the keys plane.json may hold, at every level `ccp` reads by key. A dict maps each known key to the
# shape of its value (None: not read by key here); `_Each` is a list or a map of named items, each of that
# shape. A key outside it is unknown: `load` ignores it with a warning and `ccp docs check` refuses it.
_BLOCK_KEYS: dict[str, Any] = {
    "task_log": _known(TASK_LOG_DEFAULTS, old="task_log", kinds=_Each(_known(KIND_KEYS))),
    "package_docs": _known(PACKAGE_DOCS_DEFAULTS, rules={n: None if k is None else _known(sorted(k))
                                                         for n, k in DOC_RULES.items()}),
    "architect": _known(ARCHITECT_DEFAULTS, checks=_Each(_known(CHECK_KEYS)), budgets=_Each(_known(BUDGET_KEYS))),
    "prompts": _known(PROMPTS_DEFAULTS),
    "reconcile": _known(RECONCILE_DEFAULTS, log=_known(sorted(RECONCILE_LOG_KEYS))),
    "adapter": _known(ADAPTER_DEFAULTS, old="adapter"),
    "worktrees": _known(WORKTREES_DEFAULTS),
    "env": _known(ENV_DEFAULTS),
    "merge": _known(MERGE_DEFAULTS),
    "auth_check": _known(AUTH_CHECK_DEFAULTS, probes=_Each(_known(PROBE_KEYS))),
    "telemetry": _known(TELEMETRY_DEFAULTS, design_seat=_known(DESIGN_SEAT_KEYS), windows=_Each(_known(WINDOW_KEYS))),
    "board": _known(BOARD_DEFAULTS),
    "gate": _known(GATE_DEFAULTS),
    "health": _known(HEALTH_DEFAULTS),
    "usage": _known(USAGE_DEFAULTS, advice=_known(USAGE_DEFAULTS["advice"])),
    "workers": _known(WORKERS_DEFAULTS, implementer_model=_known(WORKER_MODEL_ARMS)),
    "models": None,  # not read by key here: `_models` refuses a key that is no role, naming it
    "suite": _known(SUITE_DEFAULTS, lanes=_Each(_Each(_known(sorted(SUITE_STAGE_KEYS)))),
                    summary=_known(SUITE_SUMMARY_DEFAULTS, old="suite.summary"), roles=_known(SUITE_ROLES)),
    "adr": _known(ADR_DEFAULTS),
    "verify": _known(VERIFY_DEFAULTS, accept_cache=_known(ACCEPT_CACHE_DEFAULTS),
                     skip_review=_known(sorted(SKIP_REVIEW_KEYS)), provers=_Each(_known(sorted(PROVER_KEYS)))),
    "review_points": _known(REVIEW_POINTS_DEFAULTS),
    "estimate": _known(ESTIMATE_DEFAULTS, old="estimate", calibration=_known(ESTIMATE_DEFAULTS["calibration"])),
    "parallel": _known(PARALLEL_DEFAULTS),
    "ids": {k: _known(v) for k, v in refs.IDS_DEFAULTS.items()},
    "docs": _known(DOCS_DEFAULTS, checks=_Each(_known(CHECK_KEYS)), starter_rules=_known(["declined"])),
    "mutate": _known(MUTATE_DEFAULTS),
    "report": _known(REPORT_DEFAULTS, required_fields=_Each(_known(REPORT_FIELD_KEYS))),
    "notify": _known(NOTIFY_DEFAULTS, lead=_known(NOTIFY_LEAD_KEYS)),
    "upgrade": _known(UPGRADE_DEFAULTS),
}
PLANE_KEYS: dict[str, Any] = {"$schema": None, "_note": None, **dict.fromkeys(REQUIRED_KEYS),
                              **dict.fromkeys(OPTIONAL_TOP_KEYS),
                              **{b: _BLOCK_KEYS[b] for b in BLOCKS}}


def _drop_unknown(v: Any, shape: Any, where: str, out: list[str]) -> Any:
    """`v` without the keys `shape` does not know, each appended to `out` as its dotted path; a value of
    another type than the shape expects is kept as it is, for its block's validator to judge."""
    if isinstance(shape, _Each):
        if isinstance(v, list):
            return [_drop_unknown(x, shape.shape, f"{where}[{i}]", out) for i, x in enumerate(v)]
        if isinstance(v, dict):
            return {k: _drop_unknown(x, shape.shape, f"{where}.{k}", out) for k, x in v.items()}
        return v
    if not isinstance(shape, dict) or not isinstance(v, dict):
        return v
    kept = {}
    for k, x in v.items():
        path = f"{where}.{k}" if where else k
        if k in shape:
            kept[k] = _drop_unknown(x, shape[k], path, out)
        else:
            out.append(path)
    return kept


_WARNED: set[tuple[str, str]] = set()  # (file, key) already warned about in this process


def _warn_once(where: str, msg: str) -> None:
    """Print `msg` to stderr, once per `where` and process."""
    if (where, msg) not in _WARNED:
        _WARNED.add((where, msg))
        print(f"ccp: warning: {msg}", file=sys.stderr)


def load(root: Path) -> Config:
    p = root / CONFIG_REL
    if not p.is_file():
        raise ConfigError(f"no {CONFIG_REL} in {root}: this product has not adopted ccp "
                          "(control-plane SPEC §8.1)")
    cfg = _parse(root, p.read_text())
    for w in [*language_warnings(cfg), *cfg.key_notes]:  # §29.3: a moved or removed key, once per file and process
        _warn_once(str(p), w)
    new = [k for k in cfg.unknown_keys if (str(p), k) not in _WARNED]
    if new:
        _WARNED.update((str(p), k) for k in new)
        print(f"ccp: warning: {p}: unknown key(s) {', '.join(new)} ignored: this ccp may predate them "
              "(update it); if they are typos, fix them (`ccp docs check` fails on them, §8.1)", file=sys.stderr)
    return cfg


def skip_rules_at(root: Path, rev: str, label: str | None = None) -> tuple[dict[str, Any], str]:
    """The `verify` block of plane.json as committed at `rev`, loaded and checked as `load` does (§14.2,
    §15.2): the skip rules (`verify.skip_review`, `verify.provers`) are read from the integration branch
    this way, so a rule a task adds or changes in its own diff does not apply to that task. The defaults
    (nothing skipped) when `rev` or its plane.json does not exist, with "" as the reason; the defaults and
    why, naming `rev` as `label` (`rev` itself by default), when that plane.json does not load."""
    r = subprocess.run(["git", "-C", str(root), "show", f"{rev}:{CONFIG_REL}"], capture_output=True, text=True)
    if r.returncode != 0:
        return copy.deepcopy(VERIFY_DEFAULTS), ""
    try:
        return _parse(root, r.stdout).verify, ""
    except ConfigError as e:
        return copy.deepcopy(VERIFY_DEFAULTS), f"plane.json on {label or rev} does not load ({str(e)[:200]})"


def _ignored_keys(root: Path, raw: dict[str, Any]) -> dict[str, str]:
    """The merged keys plane.json's `raw` sets that are ignored whatever their place: `task_log.review_point_pattern`
    once the product keeps a review-point register (§22), which holds strict `R<n>` ids."""
    rp = raw.get("review_points")
    file = rp.get("file") if isinstance(rp, dict) else None
    file = file if isinstance(file, str) and file.strip() else REVIEW_POINTS_DEFAULTS["file"]
    try:
        kept = (root / file).is_file()
    except (OSError, ValueError):
        kept = False
    return {"task_log.review_point_pattern": f"the review-point register {file} exists, and review points are "
                                             "then R<number> in it (SPEC §22)"} if kept else {}


def _parse(root: Path, text: str) -> Config:
    """plane.json's text, parsed and checked, as the Config of the product at `root`."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{CONFIG_REL}: not valid JSON ({e})") from e
    if not isinstance(raw, dict) or not str(raw.get("project_id") or "").strip():
        raise ConfigError(f"{CONFIG_REL}: `project_id` is required")
    if not PROJECT_ID_RE.match(str(raw["project_id"]).strip()):
        raise ConfigError(f"{CONFIG_REL}: project_id {raw['project_id']!r} is not lowercase letters, digits and hyphens")
    unknown: list[str] = []
    raw = _drop_unknown(raw, PLANE_KEYS, "", unknown)
    raw, found = _apply_outcomes(raw, _ignored_keys(root, raw))
    try:
        return _config_of(root, raw, found, unknown)
    except ConfigError as e:
        raise ConfigError(_at_origin(str(e), found)) from None


def _config_of(root: Path, raw: dict[str, Any], found: list[dict[str, Any]], unknown: list[str]) -> Config:
    """The Config of plane.json's checked data `raw` (outcomes applied: `found`, what they did)."""
    bad_ids = refs.validate(raw.get("ids"))
    if bad_ids:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad_ids))
    ids = refs.from_config(raw.get("ids"))
    pkg = raw.get("package_docs")
    tl = raw.get("task_log")
    language, moved = _language(raw)
    return Config(
        root=root,
        project_id=str(raw["project_id"]).strip(),
        language=language,
        language_moved=moved,
        key_notes=tuple(f["note"] for f in found),
        models_given=tuple(raw["models"]) if isinstance(raw.get("models"), dict) else (),
        task_log=_task_log(tl),
        package_docs=_package_docs(pkg, language),
        docs=_docs(raw.get("docs")),
        architect=_architect(raw.get("architect"), ids),
        rules_doc_set=isinstance(raw.get("architect"), dict) and "rules_doc" in raw["architect"],
        ids=ids,
        adr=_adr(raw.get("adr")),
        upgrade=_upgrade(raw.get("upgrade")),
        unknown_keys=tuple(unknown),
        **_toolkit(raw, root),
        spec_paths=tuple(raw["spec_paths"]) if isinstance(raw.get("spec_paths"), list) else SPEC_PATHS_DEFAULT,
    )
