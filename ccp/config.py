"""The product root and its `docs/delivery/plane.json` (SPEC §8.1).

The file is product-owned: it travels with the code it describes, so a worktree or a verifier
checkout needs nothing from the queue. Its presence is the opt-in — a product without it has
not adopted `ccp`, and every command says so rather than guessing. Every key but `project_id`
has a plane default; a block that is absent means "use the defaults", except `package_docs` and
`architect`, whose absence turns that part off (they are a product's choice, not a plane rule).
The `architect` block is checked value by value as well as key by key: it drives a gate at
`ccp tasks next`, so a wrong type must fail loudly rather than turn the gate off.
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp import refs

CONFIG_REL = "docs/delivery/plane.json"

TASK_LOG_DEFAULTS: dict[str, Any] = {
    "dir": "docs/delivery",
    # SPEC §5: the task file's statuses are fixed (pending, done, dropped; in-flight states live in
    # the queue). Kept so a plane.json that names it still loads; it is not read.
    "statuses": ["pending", "done", "dropped"],
    "required": ["task_id", "title", "status", "depends_on", "spec_refs", "created", "updated"],
    # At least one of these must be non-empty: a task that cites nothing is not traceable.
    "refs_any": ["spec_refs"],
    # SPEC §5: the canonical sections, required by default; a product may require more.
    "sections": ["Intent", "Context (not checked)", "Scope", "dod_checks",
                 "Implementation notes", "Verification notes"],
    # SPEC §5.5, §20.4: per kind, the ref lists it cites one of (`refs_any`, default the task log's)
    # and the ones it leaves empty (`forbid`). Read only with the architect block on.
    "kinds": {"feature": {}, "refactor": {"refs_any": ["rule_refs", "review_refs"],
                                          "forbid": ["spec_refs", "adr_refs"]}},
    # Shaping records (`sh-*.md`) and triage records, under `dir` (§19.6).
    "reviews_dir": "reviews",
    "max_checks": 6,
    "soft_words": ["should", "may", "might", "as appropriate", "gracefully", "robust", "robustly"],
    # SPEC §5.7: INDEX.yaml is the product's choice. Its format is frozen; with false there is none.
    "index": True,
    # SPEC §22: honoured only while the product keeps no review-point register. With the
    # register, review points are strict R<n> in it, and this key is ignored with a warning.
    "review_point_pattern": "^R[0-9]+$",
    # SPEC §10: a not-done task's check that runs a command records its
    # writer's dry run, or says why there is none. Off unless the product turns it on.
    "dry_run": False,
}
# SPEC §16.2: several tasks in flight under one runner. 1 (the default) is one task at a time.
PARALLEL_DEFAULTS: dict[str, Any] = {"max_in_flight": 1, "exclusive": [], "session_ceiling_pct": 60}
# §22: the review-point register, a product file (ccp/reviewpoints.py).
REVIEW_POINTS_DEFAULTS: dict[str, Any] = {"file": "docs/delivery/review-points.yaml"}

PACKAGE_DOCS_DEFAULTS: dict[str, Any] = {
    "doc_name": ".claude.md",
    # Directories (relative to the root) documented by an auto-loaded CLAUDE.md instead of doc_name.
    "claude_md_dirs": [],
    # The language pack (ccp/doclang): it adds its suffixes and directory names to the core's and runs
    # its per-file checks on docstring_globs. "none" runs the language-neutral core alone.
    "language": "python",
    # null: the core's own plus the pack's. A list replaces both.
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
    # The house rules (SPEC §20.1): a product path, or None for none yet.
    "rules_doc": None,
    "rules_max_lines": 150,
    # Triggers (§19.6).
    "every_n_tasks": 4,
    "max_days": 14,
    "notes_due": 3,
    "drift_ratio": 1.5,
    # Enforcement at `ccp tasks next` (§19.6).
    "grace_tasks": 1,
    "triage_grace_tasks": 2,
    # Shaping (§19.6): with shape_adrs on, shape_from_task is required, so turning the check on
    # never fails the tasks written before it.
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
WORKER_ENV_FIELDS = ("run_id", "task_id", "nnnn", "phase", "worktree", "main_checkout", "queue_root", "project_id")
# §10.5 `ccp tasks close`: the product's records beside the task file. `log` prepends one entry to a
# product log (an `entry` template, placed before the first line matching `before`); `hooks` are
# product commands run in the runner worktree with TASK_ID, PR, HEAD_SHA, MERGE_SHA and SUMMARY set.
# A hook must be idempotent: a `close` re-run after a failure runs the hooks again.
RECONCILE_DEFAULTS: dict[str, Any] = {"log": None, "hooks": []}
RECONCILE_LOG_KEYS = {"path", "entry", "before"}
RECONCILE_LOG_FIELDS = ("date", "task_id", "nnnn", "pr", "head", "head7", "merge_sha", "merge7", "summary",
                        "review_point", "title")
# Legacy (before §12.1's worktrees/env blocks): `adapter.worktree_dir` and `adapter.worktree_links`
# read as `worktrees.dir` and `worktrees.links`; `adapter.post_close` commands still run once at close.
ADAPTER_DEFAULTS: dict[str, Any] = {"worktree_dir": None, "worktree_links": [], "post_close": []}
# §12.1: where `ccp wt` makes worktrees (relative to the main checkout; null = none) and what it links in.
WORKTREES_DEFAULTS: dict[str, Any] = {"dir": None, "links": []}
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
TELEMETRY_DEFAULTS: dict[str, Any] = {"otel_port": 4318, "allowance_cmd": None, "allowance_stop_weekly": None,
                                      # §24.5: the lead's expected model and effort, as advice only
                                      "design_seat": None,
                                      # §25.4 the session park: claim and prompt park the task at this 5-hour %
                                      # (null: no park, no wake, no 5-hour modelling in the forecast); the
                                      # lead arms a wake from `arm_pct`, at the window's reset plus `margin_s`
                                      "session_park_pct": 95, "session_wake_arm_pct": 50, "session_wake_margin_s": 180,
                                      # §25.4 the usage windows: {<name>: {kind: weekly|session, stop_pct, park_pct}};
                                      # merged over the two built-in ones (seven_day: weekly, stopping at
                                      # allowance_stop_weekly; five_hour: session, parking at session_park_pct)
                                      "windows": None}
BOARD_DEFAULTS: dict[str, Any] = {"refresh_minutes": 5}
# §14.6 the gate's time: `shell_limit_seconds` is the agent harness's foreground command limit, which a
# cold gate run must fit; `cut_line_seconds` (null: 90% of the limit) the lower line above which the
# gate is cut down. `ccp health` judges the latest cold gate run against both.
GATE_DEFAULTS: dict[str, Any] = {"shell_limit_seconds": 600, "cut_line_seconds": None}
GATE_CUT_SHARE = 0.9  # the cut line's default, as a share of the limit
# §26.3 estimation: `reference_since` (YYYY-MM-DD, or null) leaves tasks merged before a process change
# out of every reference class; `k` is the reference class's size (5 to 8).
ESTIMATE_DEFAULTS: dict[str, Any] = {"reference_since": None, "k": 6, "auto": False,  # auto: §26.3 phase B triggers
                                     # §26.3: where the estimator looks for cited SPEC headings (globs, in order),
                                     # and which backticked suffixes count as cited paths (null: the built-in list)
                                     "spec_paths": ["docs/SPEC.md", "SPEC.md", "docs/spec/*.md", "spec/*.md"],
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
# line that matches; the default reads unittest's "Ran N tests in Xs").
SUITE_DEFAULTS: dict[str, Any] = {"lanes": {}, "count_re": None, "summary": None, "log_keep_days": 14,
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
# `failed` (unittest's failures and errors), `skipped`, and, for a product with a test cache, `ran`
# and `cached` (units run and served from the cache, in the product's unit: tests, modules, files)
# and `cached_tests` (the tests behind the cached units). The defaults read Python unittest only;
# `ran`, `cached` and `cached_tests` match nothing until a product sets them. `section_re` starts a
# failing test's section (the line after a `====` rule); `show_re` lines are shown whatever the
# result; `tail_lines` and `max_chars` bound what a failure shows. A key left out keeps its default.
SUITE_SUMMARY_DEFAULTS: dict[str, Any] = {
    "failed_re": [r"^FAILED \(.*\bfailures=(\d+)", r"^FAILED \(.*\berrors=(\d+)"],
    "skipped_re": r"^(?:OK|FAILED) \(.*\bskipped=(\d+)",
    "ran_re": [],
    "cached_re": [],
    "cached_tests_re": [],
    "section_re": r"^(?:FAIL|ERROR|UNEXPECTED SUCCESS): ",
    "show_re": [],
    "tail_lines": 40,
    "max_chars": 40000,
}
# Names `suite.summary` keys had before the gate-result contract: read as their new key.
SUITE_SUMMARY_ALIASES = {"modules_ran_re": "ran_re", "modules_cached_re": "cached_re"}
# The verifier's gate (§15.3): `accept_cache` (null = off) lets a product's content-keyed test cache
# stand in for a rerun. A module the verifier's own gate run reports as a hit on identical inputs
# counts as run; an entry over `max_age_days` is no hit; a task whose id matches a `cold_tasks` glob,
# or whose frontmatter says `gate: cold`, has a cold gate. `review: true` extends the rule to the
# reviewer's touched and dependent modules (its order and mutation runs stay uncached).
# `skip_review` (null = off, §15.2): a fix round whose diff touches only `paths` (relative to the product
# root) and that the product's `proof` command passes (exit 0) goes to verify with no new review.
VERIFY_DEFAULTS: dict[str, Any] = {"accept_cache": None, "skip_review": None}
ACCEPT_CACHE_DEFAULTS: dict[str, Any] = {"max_age_days": None, "cold_tasks": [], "review": False}
SKIP_REVIEW_KEYS = {"paths", "proof"}
SKIP_REVIEW_FIELDS = ("task_id", "reviewed", "head", "from")
# §20.6 `ccp mutate`: `command` runs one named test (a shell template naming `{test}`, filled in
# shell-quoted; null, the default, means the product has none and `ccp mutate` refuses);
# `timeout_seconds` bounds one run of it (a mutant that hangs the test is killed).
MUTATE_DEFAULTS: dict[str, Any] = {"command": None, "timeout_seconds": 600}
# §13.4: verdict lines every done implement or fix report must state, each `{name, values}`: the line
# is `<name>: <one of values>`. `ccp report` refuses a report missing one; none by default.
REPORT_DEFAULTS: dict[str, Any] = {"required_fields": []}
# §3.6: the operator's channel. `command` is a shell command `ccp` runs on each trigger, given the trigger
# and ids in its environment (null, the default: the lead's session, and no command runs);
# `timeout_seconds` bounds one run of it.
NOTIFY_DEFAULTS: dict[str, Any] = {"command": None, "timeout_seconds": 30}
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


class ConfigError(Exception):
    """The product has no usable plane.json."""


@dataclass(frozen=True)
class Config:
    root: Path
    project_id: str
    task_log: dict[str, Any]
    package_docs: dict[str, Any] | None
    docs: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DOCS_DEFAULTS))
    architect: dict[str, Any] | None = None
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
    suite: dict[str, Any] | None = None
    adr: dict[str, Any] | None = None
    verify: dict[str, Any] | None = None
    review_points: dict[str, Any] | None = None
    estimate: dict[str, Any] | None = None
    parallel: dict[str, Any] | None = None
    mutate: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    notify: dict[str, Any] | None = None
    # Whether plane.json names task_log.review_point_pattern itself (§22: ignored, with a warning,
    # once the product keeps a review-point register).
    review_point_pattern_set: bool = False
    # §14.1: suite.summary's pre-contract knob names given beside their new names (the new one wins).
    suite_aliases_ignored: tuple[str, ...] = ()
    # The product's id and reference patterns (plane.json `ids`, SPEC §7); the defaults otherwise.
    ids: refs.Ids = refs.DEFAULT

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


def _aliases_ignored(suite: Any) -> tuple[str, ...]:
    sm = suite.get("summary") if isinstance(suite, dict) else None
    if not isinstance(sm, dict):
        return ()
    return tuple(old for old, new in SUITE_SUMMARY_ALIASES.items() if old in sm and new in sm)


def config_warnings(cfg: Any) -> list[str]:
    """What plane.json says that is accepted but has no effect, for `ccp tasks check` to show."""
    return [f"{CONFIG_REL}: suite.summary.{old} is ignored: {SUITE_SUMMARY_ALIASES[old]} is given too and wins "
            "(remove the old name, §14.1)" for old in getattr(cfg, "suite_aliases_ignored", ())]


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


def _package_docs(given: Any) -> dict[str, Any] | None:
    """§21: absent means off. The language must be a known pack; each opt-in rule is checked."""
    if given is None:
        return None
    from ccp import doclang  # noqa: PLC0415
    pd = _merge(PACKAGE_DOCS_DEFAULTS, given, "package_docs")
    if pd["language"] not in doclang.PACKS:
        raise ConfigError(f"{CONFIG_REL}: package_docs.language {pd['language']!r} is not one of "
                          f"{', '.join(doclang.NAMES)}")
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
        if not isinstance(c, dict) or set(c) - {"id", "cmd", "timeout_seconds"}:
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
    if given is None:
        return None
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
    _entries(a, "checks", {"id", "cmd", "timeout_seconds"}, {"id", "cmd"}, ids)
    _entries(a, "budgets", {"id", "glob", "path", "max_lines", "max_bytes"}, {"id"}, ids)
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


def _rel_path(v: Any) -> bool:
    """A path relative to the product root, as a git pathspec: not empty, not absolute, no `..`, no `:`
    pathspec magic."""
    return isinstance(v, str) and bool(v.strip()) and not v.startswith(("/", ":")) and ".." not in Path(v).parts


def _every_path(where: str, paths: list[Any]) -> list[str]:
    """The entries of a path list that match every path, so a check they narrow would never fire: the root
    itself (`.`, `./`, anything that normalises to it) or wildcards alone (`*`, `**`, `./*`). Each is
    named; `merge.behind_tip_ignore` and `verify.skip_review.paths` refuse them alike."""
    norm = [(x, os.path.normpath(x)) for x in paths if isinstance(x, str) and x.strip()]
    return [f"{where}: {x!r} matches every path; name the paths it covers" for x, n in norm
            if n == "." or set(n) == {"*"}]


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
        if not isinstance(f, dict) or set(f) != {"name", "values"}:
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


def _toolkit(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The §10 blocks, merged with their defaults and checked value by value: they drive merges,
    commits and commands, so a wrong type fails loudly."""
    out = {"prompts": _merge(PROMPTS_DEFAULTS, raw.get("prompts"), "prompts"),
           "reconcile": _merge(RECONCILE_DEFAULTS, raw.get("reconcile"), "reconcile"),
           "adapter": _merge(ADAPTER_DEFAULTS, raw.get("adapter"), "adapter"),
           "worktrees": _merge(WORKTREES_DEFAULTS, raw.get("worktrees"), "worktrees"),
           "env": _merge(ENV_DEFAULTS, raw.get("env"), "env"),
           "merge": _merge(MERGE_DEFAULTS, raw.get("merge"), "merge"),
           "auth_check": _merge(AUTH_CHECK_DEFAULTS, raw.get("auth_check"), "auth_check"),
           "telemetry": _merge(TELEMETRY_DEFAULTS, raw.get("telemetry"), "telemetry"),
           "board": _merge(BOARD_DEFAULTS, raw.get("board"), "board"),
           "gate": _merge(GATE_DEFAULTS, raw.get("gate"), "gate"),
           "suite": _suite(raw.get("suite")),
           "verify": _merge(VERIFY_DEFAULTS, raw.get("verify"), "verify"),
           "review_points": _merge(REVIEW_POINTS_DEFAULTS, raw.get("review_points"), "review_points"),
           "estimate": _merge(ESTIMATE_DEFAULTS, raw.get("estimate"), "estimate"),
           "parallel": _merge(PARALLEL_DEFAULTS, raw.get("parallel"), "parallel"),
           "mutate": _merge(MUTATE_DEFAULTS, raw.get("mutate"), "mutate"),
           "report": _merge(REPORT_DEFAULTS, raw.get("report"), "report"),
           "notify": _merge(NOTIFY_DEFAULTS, raw.get("notify"), "notify")}
    bad = []
    if not isinstance(raw.get("task_log", {}).get("index", True), bool):
        bad.append("task_log.index must be true or false")
    kinds = raw.get("task_log", {}).get("kinds", TASK_LOG_DEFAULTS["kinds"])
    if not isinstance(kinds, dict) or not kinds or not all(
            isinstance(k, str) and isinstance(v, dict) and set(v) <= {"refs_any", "forbid"}
            and all(isinstance(v.get(x, []), list) and all(isinstance(i, str) for i in v.get(x, []))
                    for x in ("refs_any", "forbid")) for k, v in kinds.items()):
        bad.append("task_log.kinds must map each kind to {refs_any: [lists], forbid: [lists]}")
    rd = raw.get("task_log", {}).get("reviews_dir", "reviews")
    if not (isinstance(rd, str) and rd.strip()) or rd.startswith("/") or ".." in Path(rd).parts:
        bad.append("task_log.reviews_dir must be a path relative to task_log.dir")
    if not isinstance(raw.get("task_log", {}).get("dry_run", False), bool):
        bad.append("task_log.dry_run must be true or false")
    par = out["parallel"]
    mif = par["max_in_flight"]
    if isinstance(mif, bool) or not isinstance(mif, int) or not 1 <= mif <= 4:
        bad.append("parallel.max_in_flight must be an integer from 1 to 4")
    if not isinstance(par["exclusive"], list) or not all(isinstance(x, str) and x.strip() for x in par["exclusive"]):
        bad.append("parallel.exclusive must be a list of paths or globs")
    scp = par["session_ceiling_pct"]
    if isinstance(scp, bool) or not isinstance(scp, (int, float)) or not 0 < scp <= 100:
        bad.append("parallel.session_ceiling_pct must be a number above 0, at most 100")
    rpp = raw.get("task_log", {}).get("review_point_pattern", TASK_LOG_DEFAULTS["review_point_pattern"])
    try:
        if not isinstance(rpp, str) or not rpp:
            raise re.error("it must be a non-empty string")
        re.compile(rpp)
    except re.error as e:
        bad.append(f"task_log.review_point_pattern is not a regular expression ({e})")
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
    ad = out["adapter"]
    if not _opt_str(ad["worktree_dir"]):
        bad.append("adapter.worktree_dir must be a path relative to the product root")
    for k in ("worktree_links", "post_close"):
        if not _str_list(ad[k]):
            bad.append(f"adapter.{k} must be a list of non-empty strings")
    bad += _worktree_blocks(raw, out)
    tel = out["telemetry"]
    if isinstance(tel["otel_port"], bool) or not isinstance(tel["otel_port"], int) or not 1 <= tel["otel_port"] <= 65535:
        bad.append("telemetry.otel_port must be a port number")
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
            and not set(w) - {"kind", "stop_pct", "park_pct"} and w.get("kind", "weekly") in ("weekly", "session")
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
    if ds is not None and (not isinstance(ds, dict) or set(ds) - {"model", "effort"}
                           or not all(isinstance(v, str) and v.strip() for v in ds.values())):
        bad.append("telemetry.design_seat must be {model, effort}, each a string")
    est = out["estimate"]
    if not _str_list(est["spec_paths"]):
        bad.append("estimate.spec_paths must be a list of path globs relative to the product root")
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
    if not isinstance(cal, dict) or set(cal) - {"half_life", "min_pairs", "k"}:
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
        try:
            if not isinstance(cre, str) or re.compile(cre).groups < 1:
                raise re.error("it needs a group that captures the count")
        except re.error as e:
            bad.append(f"suite.count_re is not a regular expression with a count group ({e})")
    kd = out["suite"]["log_keep_days"]
    if isinstance(kd, bool) or not isinstance(kd, int) or kd < 1:
        bad.append("suite.log_keep_days must be an integer >= 1 (days a summary-mode log is kept)")
    sm = out["suite"]["summary"]
    if sm is not None:
        if not isinstance(sm, dict) or set(sm) - set(SUITE_SUMMARY_DEFAULTS) - set(SUITE_SUMMARY_ALIASES):
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
    mu = out["mutate"]
    if not _opt_str(mu["command"]):
        bad.append("mutate.command must be a shell command naming {test}, or null for none")
    elif mu["command"] is not None and "{test}" not in mu["command"]:
        bad.append("mutate.command must name {test}: it runs the one test a mutant is judged by (§20.6)")
    t = mu["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("mutate.timeout_seconds must be an integer >= 1")
    nt = out["notify"]
    if not _opt_str(nt["command"]):
        bad.append("notify.command must be a shell command, or null for the lead's session")
    t = nt["timeout_seconds"]
    if isinstance(t, bool) or not isinstance(t, int) or t < 1:
        bad.append("notify.timeout_seconds must be an integer >= 1")
    if bad:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad))
    return out


def _worktree_blocks(raw: dict[str, Any], out: dict[str, Any]) -> list[str]:
    """§12.1: worktrees, env hooks, merge and auth probes; the legacy adapter keys fold into worktrees."""
    bad: list[str] = []
    ad, wt = out["adapter"], out["worktrees"]
    given = raw.get("worktrees") if isinstance(raw.get("worktrees"), dict) else {}
    if ad["worktree_dir"] is not None:
        if given.get("dir") not in (None, ad["worktree_dir"]):
            bad.append("set worktrees.dir or the legacy adapter.worktree_dir, not both")
        wt["dir"] = ad["worktree_dir"]
    if ad["worktree_links"]:
        if given.get("links") not in (None, [], ad["worktree_links"]):
            bad.append("set worktrees.links or the legacy adapter.worktree_links, not both")
        wt["links"] = list(ad["worktree_links"])
    d = wt["dir"]
    if not _opt_str(d) or (isinstance(d, str) and (d.startswith("/") or ".." in Path(d).parts)):
        bad.append("worktrees.dir must be a path relative to the main checkout, or null")
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
    if not isinstance(pr, list) or not all(isinstance(x, dict) and set(x) == {"id", "cmd"}
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


def load(root: Path) -> Config:
    p = root / CONFIG_REL
    if not p.is_file():
        raise ConfigError(f"no {CONFIG_REL} in {root}: this product has not adopted ccp "
                          "(control-plane SPEC §8.1)")
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        raise ConfigError(f"{CONFIG_REL}: not valid JSON ({e})") from e
    if not isinstance(raw, dict) or not str(raw.get("project_id") or "").strip():
        raise ConfigError(f"{CONFIG_REL}: `project_id` is required")
    if not PROJECT_ID_RE.match(str(raw["project_id"]).strip()):
        raise ConfigError(f"{CONFIG_REL}: project_id {raw['project_id']!r} is not lowercase letters, digits and hyphens")
    unknown = sorted(set(raw) - {"$schema", "_note", "project_id", "task_log", "package_docs", "architect",
                                 "prompts", "reconcile", "adapter", "worktrees", "env", "merge",
                                 "auth_check", "telemetry", "board", "gate", "suite",
                                 "adr", "verify", "review_points", "estimate", "parallel", "ids", "docs",
                                 "mutate", "report", "notify"})
    if unknown:
        raise ConfigError(f"{CONFIG_REL}: unknown top-level key(s): {', '.join(unknown)}")
    bad_ids = refs.validate(raw.get("ids"))
    if bad_ids:
        raise ConfigError(f"{CONFIG_REL}: " + "; ".join(bad_ids))
    ids = refs.from_config(raw.get("ids"))
    pkg = raw.get("package_docs")
    tl = raw.get("task_log")
    return Config(
        root=root,
        project_id=str(raw["project_id"]).strip(),
        review_point_pattern_set=isinstance(tl, dict) and "review_point_pattern" in tl,
        suite_aliases_ignored=_aliases_ignored(raw.get("suite")),
        task_log=_task_log(tl),
        package_docs=_package_docs(pkg),
        docs=_docs(raw.get("docs")),
        architect=_architect(raw.get("architect"), ids),
        ids=ids,
        adr=_adr(raw.get("adr")),
        **_toolkit(raw),
    )
