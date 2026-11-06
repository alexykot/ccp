#!/usr/bin/env python3
"""Architecture review driver (SPEC §19): due check, isolated reviewer call, triage hand-off.

Runtime files only (QUEUE_ROOT, outside product git); the durable record is written by the
triage owner in the product repo (docs/delivery/reviews/<review_id>.md). No secrets.

  due      Is a review due? (every_n_tasks done since the last review, or max_days with >= 1 done)
  run      Launch a fresh, read-only Claude session in product_root running the architecture-review
           skill; parse its report; write QUEUE_ROOT/reviews/<review_id>.json + .md
  triage   Hand a report to the task-log owner (spec maintainer resume under its lock, the team
           lead, or steerer wake); apply the triage file when present
  status   Print the review state

The triage half is shared with the docs audit (SPEC §21.7) and the architect (SPEC §19, `ccp architect`):
each is a review *kind* (`Kind`), with its own state file, lock, id prefixes, event type and finding
categories, and one triage protocol.

When the product's `docs/delivery/plane.json` has an `architect` block, this script is a thin alias
of `ccp architect` (§19). Without one it reads project.yaml's `architecture_review` block as
before, and runs the product's `architect` skill (structure lens) where the sync has replaced the
old `architecture-review` skill.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import socket
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from lib import (  # noqa: E402
    ACTORS,
    _yaml_block_scalars,
    append_event,
    die,
    fmt_dt,
    load_durable_statuses,
    looks_like_secret,
    parse_dt,
    project_yaml_text,
    read_json,
    write_json,
)
import spec_maintainer as sm  # noqa: E402  (lock, quota parse, Claude JSON parse, binding helpers)

DEFAULTS = {"every_n_tasks": 8, "max_days": 14, "call_timeout_minutes": 45, "max_new_tasks": 5}
CATEGORIES = ("holdover", "not-first-class", "duplication", "vocabulary-drift", "dead-surface",
              "incoherence", "unobserved", "cost", "rule-cost")


class Kind(NamedTuple):
    """One kind of review: where its runtime files live and what its findings may say."""
    name: str            # observability event type
    label: str           # "Architecture review"
    prefix: str          # review id prefix
    state: str           # QUEUE_ROOT state file
    lock: str            # QUEUE_ROOT reviewer lock
    audit_task: str      # prompt-audit task id and phase
    categories: tuple[str, ...]
    triage_cmd: str      # how the Runner re-runs triage
    alt_prefixes: tuple[str, ...] = ()  # more id prefixes of the same kind (the architect's `sh-` shapes)

    @property
    def rid_re(self) -> re.Pattern[str]:
        p = "|".join((self.prefix, *self.alt_prefixes))
        return re.compile(rf"^(?:{p})-[0-9]{{8}}T[0-9]{{6}}Z-[0-9a-f]{{4}}$")


AR = Kind("architecture_review", "Architecture review", "ar", "architecture-review.json",
          "architecture-review.lock", "architecture-review", CATEGORIES, "architecture-review.sh triage")
# Kept for callers that predate Kind.
STATE, LOCK, AUDIT_TASK, RID_RE = AR.state, AR.lock, AR.audit_task, AR.rid_re
DISPOSITIONS = ("task", "spec", "defer", "needs_operator", "duplicate", "reject")
BASE_READ_TOOLS = ["Read", "Grep", "Glob", "Skill",
                   "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git ls-files:*)",
                   "Bash(git grep:*)", "Bash(git status:*)", "Bash(git rev-parse:*)", "Bash(git blame:*)",
                   "Bash(ls:*)", "Bash(wc:*)"]
DENY_TOOLS = "Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent,Task"
# Fresh headless reviewers (this review and the docs audit) pin their own model and effort rather
# than take the operator's defaults (SPEC §2.4 *Models and effort*). The resumed owner triage keeps
# the owner session's own settings.
HEADLESS_MODEL = ["--model", "claude-opus-5-5", "--effort", "high"]
OLD_SKILL = ".claude/skills/architecture-review/SKILL.md"
ARCHITECT_SKILL = ".claude/skills/architect/SKILL.md"  # §19: replaces OLD_SKILL at the product's next sync
PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugin"


def architect_skill(product: str | Path) -> str:
    """SPEC §9.1: the product's own architect skill while it has a managed copy, else the plugin's."""
    own = Path(product) / ARCHITECT_SKILL
    return str(own) if own.is_file() else str(PLUGIN_DIR / "skills" / "architect" / "SKILL.md")


def plugin_args(product: str | Path) -> list[str]:
    """A headless run in a product on the plugin loads it explicitly, without trust or installs (§9)."""
    return [] if (Path(product) / ARCHITECT_SKILL).is_file() else ["--plugin-dir", str(PLUGIN_DIR)]


def triage_doc(base: str) -> str:
    """The review-triage protocol: the product's docs/delivery/REVIEW-TRIAGE.md, else the plugin skill."""
    own = f"{base.rstrip('/')}/docs/delivery/REVIEW-TRIAGE.md" if base else "docs/delivery/REVIEW-TRIAGE.md"
    return own if os.path.isfile(own) else str(PLUGIN_DIR / "skills" / "review-triage" / "SKILL.md")


# ---------------------------------------------------------------- helpers

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def out(obj: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    return code


def cfg(root: Path) -> dict[str, Any]:
    """The binding's architecture_review block. Scalars via the plane's tiny YAML reader; `probes` is
    an inline JSON-style list (probes: ["a", "b"])."""
    text = project_yaml_text(root)
    raw = _yaml_block_scalars(text, "architecture_review")
    c: dict[str, Any] = {"enabled": str(raw.get("enabled", "false")).lower() in ("true", "yes", "1")}
    for k, d in DEFAULTS.items():
        try:
            v = int(str(raw.get(k) or d))
            c[k] = v if v > 0 else d
        except ValueError:
            c[k] = d
    probes: list[str] = []
    m = re.search(r"^architecture_review:\s*\n((?:[ \t]+.*\n?|\s*\n)*)", text, re.M)
    if m:
        pm = re.search(r"^\s+probes:\s*(\[.*\])\s*$", m.group(1), re.M)
        if pm:
            try:
                probes = [str(p) for p in json.loads(pm.group(1)) if str(p).strip()]
            except json.JSONDecodeError:
                die("project.yaml architecture_review.probes must be an inline JSON list of strings", 2)
    c["probes"] = probes
    return c


def product_root(root: Path) -> str:
    pr = sm.product_root(root)
    if not pr or not os.path.isdir(pr):
        die(f"project.yaml product_root missing or not a directory: {pr!r}", 2)
    return pr


def state_path(root: Path, kind: Kind = AR) -> Path:
    return root / kind.state


def load_state(root: Path, kind: Kind = AR) -> dict[str, Any]:
    p = state_path(root, kind)
    return read_json(p) if p.is_file() else {"schema_version": 1, "reviews": {}}


def save_state(root: Path, st: dict[str, Any], kind: Kind = AR) -> None:
    write_json(state_path(root, kind), st)


@contextmanager
def state_lock(root: Path, kind: Kind = AR):
    """The state file's own lock, held for one read-modify-write (milliseconds, never across a call).
    A detached architect pass writes its record while `ccp tasks next` and triage write theirs."""
    fd = os.open(str(state_path(root, kind)) + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def update_state(root: Path, kind: Kind, fn: Any) -> dict[str, Any]:
    """Re-read the state under its lock, apply `fn` to it, save it; returns what was saved."""
    with state_lock(root, kind):
        st = load_state(root, kind)
        st.setdefault("reviews", {})
        fn(st)
        save_state(root, st, kind)
    return st


def rdir(root: Path) -> Path:
    d = root / "reviews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def report_path(root: Path, rid: str) -> Path:
    return rdir(root) / f"{rid}.json"


def triage_path(root: Path, rid: str) -> Path:
    return rdir(root) / f"{rid}.triage.json"


def actor_of(arg: str | None) -> str:
    a = arg or os.environ.get("ACTOR") or "task-runner"
    return a if a in ACTORS else "system"


def emit(root: Path, actor: str, op: str, payload: dict[str, Any], kind: Kind = AR) -> None:
    append_event(root, {"at": fmt_dt(now_utc()), "project_id": sm.project_id(root), "task_id": "",
                        "actor": actor, "type": kind.name, "op": op, "payload": payload})


def transition(root: Path, st: dict[str, Any], rid: str, to: str, actor: str, kind: Kind = AR) -> None:
    """Move one review to `to`, carrying the caller's fields for that review onto a fresh read of the
    state (so a stale `st` never overwrites another writer's records), and emit the event."""
    mine = dict((st.get("reviews") or {}).get(rid) or {})
    frm: list[str] = []

    def apply(fresh: dict[str, Any]) -> None:
        rec = fresh["reviews"].setdefault(rid, {})
        frm.append(rec.get("status") or mine.get("status") or "none")
        rec.update({k: v for k, v in mine.items() if k not in ("status", "updated_at")})
        rec["status"] = to
        rec["updated_at"] = fmt_dt(now_utc())

    fresh = update_state(root, kind, apply)
    st.setdefault("reviews", {})[rid] = fresh["reviews"][rid]
    emit(root, actor, "transition", {"review_id": rid, "from": frm[0], "to": to}, kind)


def done_count(root: Path) -> int:
    return sum(1 for s in load_durable_statuses(root).values() if s == "done")


def git(cwd: str, *a: str) -> str:
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def last_json_object(text: str) -> dict[str, Any] | None:
    """The last top-level JSON object in a model's final message (fenced or bare)."""
    t = text or ""
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    for c in reversed(fences):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    end = t.rfind("}")
    while end != -1:
        depth, i = 0, end
        while i >= 0:
            if t[i] == "}":
                depth += 1
            elif t[i] == "{":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(t[i:end + 1])
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
                    break
            i -= 1
        end = t.rfind("}", 0, end)
    return None


def validate_report(r: Any, rid: str, pid: str, kind: Kind = AR, max_findings: int = 25) -> list[str]:
    errs: list[str] = []
    if not isinstance(r, dict):
        return ["report is not an object"]
    for k in ("summary", "findings"):
        if k not in r:
            errs.append(f"missing {k}")
    if r.get("review_id") not in (None, rid):
        errs.append(f"review_id {r.get('review_id')!r} != {rid}")
    f = r.get("findings")
    if not isinstance(f, list):
        return errs + ["findings is not a list"]
    if len(f) > max_findings:
        errs.append(f"{len(f)} findings > {max_findings}")
    for i, x in enumerate(f):
        if not isinstance(x, dict):
            errs.append(f"finding {i} is not an object")
            continue
        for k in ("id", "title", "category", "severity", "confidence", "what", "evidence", "fix", "proposal"):
            if not x.get(k):
                errs.append(f"{x.get('id') or i}: missing {k}")
        if x.get("category") and x["category"] not in kind.categories:
            errs.append(f"{x.get('id')}: category {x['category']!r}")
        if x.get("confidence") == "low":
            errs.append(f"{x.get('id')}: low confidence is not reported (skill rule)")
        if x.get("category") == "rule-cost" and (not x.get("needs_decision") or x.get("fix") != "decide"):
            errs.append(f"{x.get('id')}: a rule-cost finding needs a decision (needs_decision: true, fix: decide)")
        if not isinstance(x.get("evidence"), list) or not x.get("evidence"):
            errs.append(f"{x.get('id')}: no evidence")
    if looks_like_secret(json.dumps(r)):
        errs.append("report contains a secret-like string")
    return errs


COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def is_commit_sha(value: Any) -> bool:
    """A git sha. The word pending is not one: it marks an applied rule change still to land."""
    return isinstance(value, str) and bool(COMMIT_SHA_RE.fullmatch(value))


def validate_triage(t: Any, rid: str) -> list[str]:
    errs: list[str] = []
    if not isinstance(t, dict):
        return ["triage is not an object"]
    if t.get("review_id") != rid:
        errs.append(f"review_id {t.get('review_id')!r} != {rid}")
    for k in ("record", "dispositions", "answered_by"):
        if k not in t:
            errs.append(f"missing {k}")
    for d in t.get("dispositions") or []:
        if not isinstance(d, dict) or d.get("disposition") not in DISPOSITIONS or not d.get("reason"):
            errs.append(f"bad disposition {d!r}"[:200])
    if not isinstance(t.get("tasks_created", []), list):
        errs.append("tasks_created is not a list")
    if (t.get("tasks_created") or any((d or {}).get("disposition") in ("task", "spec") for d in t.get("dispositions") or [])) \
            and not is_commit_sha(t.get("commit_sha")):
        errs.append("tasks or rulings without commit_sha")
    if looks_like_secret(json.dumps(t)):
        errs.append("triage contains a secret-like string")
    return errs


def render_md(r: dict[str, Any], kind: Kind = AR) -> str:
    lines = [f"# {kind.label} {r.get('review_id')}", "",
             f"project `{r.get('project_id')}` · head `{r.get('head')}` · base `{r.get('base')}`", "",
             r.get("summary") or "", "", "| id | sev | category | title | fix |", "| --- | --- | --- | --- | --- |"]
    for f in r.get("findings") or []:
        lines.append(f"| {f.get('id')} | {f.get('severity')} | {f.get('category')} | {f.get('title')} | {f.get('fix')} |")
    for f in r.get("findings") or []:
        lines += ["", f"## {f.get('id')} · {f.get('title')}", "", f.get("what") or "", "", "Evidence:"]
        lines += [f"- {e}" for e in f.get("evidence") or []]
        lines += ["", f"Proposal ({f.get('fix')}; touches {', '.join(f.get('touches') or [])}): {f.get('proposal')}"]
        if f.get("needs_decision"):
            lines.append("Needs a decision.")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- lock (reviewer runs only)

def lock_take(root: Path, actor: str, rid: str, ttl_s: int, kind: Kind = AR) -> tuple[bool, dict[str, Any] | None]:
    path = root / kind.lock
    for _ in range(2):
        body = {"holder": actor, "pid": os.getpid(), "host": socket.gethostname(), "since": fmt_dt(now_utc()),
                "ttl_seconds": ttl_s, "review_id": rid}
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            cur = read_json(path) if path.is_file() else {}
            if sm.lock_is_stale(cur, now_utc()):
                emit(root, actor, "clear", {"holder": cur.get("holder"), "reason": "stale", "review_id": cur.get("review_id")}, kind)
                path.unlink(missing_ok=True)
                continue
            return False, cur
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(body, indent=2) + "\n")
        emit(root, actor, "set", {"holder": actor, "reason": "review", "review_id": rid}, kind)
        return True, body
    return False, None


def lock_release(root: Path, actor: str, rid: str, kind: Kind = AR) -> None:
    path = root / kind.lock
    try:
        cur = read_json(path)
    except (OSError, ValueError):
        return
    if cur.get("pid") in (os.getpid(), str(os.getpid())):
        path.unlink(missing_ok=True)
        emit(root, actor, "clear", {"holder": actor, "reason": "released", "review_id": rid}, kind)


# ---------------------------------------------------------------- due

def due_info(root: Path) -> dict[str, Any]:
    c = cfg(root)
    st = load_state(root)
    last = st.get("last") or {}
    done = done_count(root)
    since = done - int(last.get("done_count") or 0) if last else done
    days = None
    if last.get("at"):
        days = round((now_utc() - parse_dt(last["at"])).total_seconds() / 86400, 1)
    pending = [rid for rid, rec in (st.get("reviews") or {}).items()
               if rec.get("status") in ("reported", "triage_sent", "triage_failed")]
    running = [rid for rid, rec in (st.get("reviews") or {}).items() if rec.get("status") == "running"]
    info: dict[str, Any] = {"enabled": c["enabled"], "done_total": done, "done_since_last": since,
                            "days_since_last": days, "every_n_tasks": c["every_n_tasks"], "max_days": c["max_days"],
                            "last_review_id": last.get("review_id"), "pending_triage": pending, "running": running}
    if not c["enabled"]:
        info.update(due=False, reason="architecture_review.enabled is not true in project.yaml")
    elif running:
        info.update(due=False, reason=f"review {running[0]} is running")
    elif pending:
        info.update(due=False, reason=f"review {pending[0]} awaits triage: run `architecture-review.sh triage {pending[0]}`")
    elif not last:
        info.update(due=since >= 1, reason="no review yet" + ("" if since >= 1 else " and no task done yet"))
    elif since >= c["every_n_tasks"]:
        info.update(due=True, reason=f"{since} task(s) done since {last.get('review_id')} (>= {c['every_n_tasks']})")
    elif days is not None and days >= c["max_days"] and since >= 1:
        info.update(due=True, reason=f"{days} days and {since} task(s) done since {last.get('review_id')}")
    else:
        info.update(due=False, reason=f"{since} of {c['every_n_tasks']} tasks done since the last review")
    return info


def cmd_due(args: argparse.Namespace) -> int:
    info = due_info(sm.root_dir())
    return out(info, 0 if info["due"] else 3)


# ---------------------------------------------------------------- run

def reviewer_prompt(pid: str, rid: str, head: str, base: str | None, dirty: bool, probes: list[str],
                    architect: bool = False) -> str:
    probe_txt = ", ".join(f"`{p}`" for p in probes) or "none (read-only git and file commands only)"
    if architect:  # the product has the §19 skill: a structure-lens pass under the §19 binding
        head_txt = (f"/architect mode=pass lenses=structure review_id={rid} project_id={pid} head={head} base={base or 'none'}\n\n"
                    f"You are the isolated architect for project {pid} (control-plane SPEC §19, run through the §19 "
                    f"alias). If the architect skill is not loaded, read {ARCHITECT_SKILL} now and follow it exactly. "
                    "Mode: pass. Lenses: structure. ")
    else:
        head_txt = (f"/architecture-review review_id={rid} project_id={pid} head={head} base={base or 'none'}\n\n"
                    f"You are the isolated architecture reviewer for project {pid} (control-plane SPEC §19). "
                    f"If the architecture-review skill is not loaded, read {OLD_SKILL} now and follow it exactly. ")
    return (
        head_txt
        + "You are read-only: no edits, no commits, nothing that writes, spends or sends.\n"
        f"Allowed probe commands besides read-only git/ls/wc: {probe_txt}.\n"
        + ("The working tree has uncommitted changes from other work: review the committed state "
           "(`git show HEAD:<path>` for any modified file).\n" if dirty else "")
        + "Finish with the report JSON object as your final message and nothing after it.\n"
    )


def cmd_run(args: argparse.Namespace) -> int:
    root = sm.root_dir()
    actor = actor_of(args.actor)
    c = cfg(root)
    info = due_info(root)
    if not args.force and not info["due"]:
        return out({"outcome": "not_due", **info}, 3)
    if info["running"] or info["pending_triage"]:
        return out({"outcome": "blocked", "reason": info["reason"]}, 3)
    pid = sm.project_id(root)
    pr = product_root(root)
    head = git(pr, "rev-parse", "HEAD")
    if not head:
        die(f"not a git checkout: {pr}", 2)
    dirty = bool(git(pr, "status", "--porcelain", "--untracked-files=no"))
    use_architect = (Path(pr) / ARCHITECT_SKILL).is_file()
    if not use_architect and not (Path(pr) / OLD_SKILL).is_file():
        die(f"missing {Path(pr) / ARCHITECT_SKILL}: install it with scripts/sync-product-docs.sh {pid} and commit "
            "(SPEC §19)", 1)
    st = load_state(root)
    base = (st.get("last") or {}).get("head")
    rid = f"ar-{now_utc().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
    timeout_s = c["call_timeout_minutes"] * 60
    ok, cur = lock_take(root, actor, rid, timeout_s + 600)
    if not ok:
        return out({"outcome": "locked", "lock": cur}, 3)
    result: dict[str, Any] = {"review_id": rid, "head": head, "base": base, "dirty": dirty}
    try:
        st["reviews"][rid] = {"status": "none", "head": head, "base": base, "done_count": done_count(root),
                              "started_at": fmt_dt(now_utc())}
        transition(root, st, rid, "running", actor)
        prompt = reviewer_prompt(pid, rid, head, base, dirty, c["probes"], use_architect)
        tools = BASE_READ_TOOLS + [f"Bash({p}:*)" for p in c["probes"]]
        argv = ["env"]
        for k in sm.STRIP_KEYS:
            argv += ["-u", k]
        argv += [os.environ.get("AR_CLAUDE_BIN") or "claude", "-p", prompt, *HEADLESS_MODEL, *plugin_args(pr),
                 "--output-format", "json", "--allowedTools", ",".join(tools), "--disallowedTools", DENY_TOOLS]
        audit = subprocess.run(
            ["bash", str(HERE / "write-prompt-audit.sh"), "--task-id", AUDIT_TASK, "--phase", "architecture-review",
             "--prompt-file", "-", "--argv", json.dumps(argv), "--actor", actor, "--project-id", pid,
             "--worktree", pr, "--git-head", head, "--notes", f"review_id={rid}"],
            input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
        if audit.returncode != 0:
            raise RuntimeError(f"write-prompt-audit failed: {audit.stderr.strip()}")
        prompt_ref = audit.stdout.strip().splitlines()[-1]
        emit(root, actor, "launch", {"review_id": rid, "phase": "review", "prompt_ref": prompt_ref})
        env = sm.headless_env(pid, "architecture-review")
        try:
            proc = subprocess.run(argv, cwd=pr, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout_s, env=env)
            code, so, se, to = proc.returncode, proc.stdout, proc.stderr, False
        except subprocess.TimeoutExpired as exc:
            so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            code, se, to = 124, "timeout", True
        res = sm.parse_claude_json(so)
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
            from ccp import usage as _usage  # noqa: PLC0415
            _usage.record_headless(root, "architecture-review", rid, res)
        except Exception:  # noqa: BLE001  (usage is a diagnostic; never fail a review over it)
            pass
        summary = str(res.get("result") or se or "")[:300]
        emit(root, actor, "exit", {"review_id": rid, "phase": "review", "exit_code": code, "timeout": to,
                                   "result_summary": "[redacted: secret-like]" if looks_like_secret(summary) else summary})
        is_quota, qclass, resets = sm.detect_quota(res, so, se)
        if is_quota:
            transition(root, st, rid, "quota_parked", actor)
            return out({**result, "outcome": "quota_parked", "quota_class": qclass, "resets_at": resets,
                        "actions": [{"action": "retry_after_reset", "detail": "Run `architecture-review.sh run --force` after the reset."}]}, 1)
        report = last_json_object(str(res.get("result") or ""))
        errs = validate_report(report, rid, pid) if report is not None else ["no JSON report in the final message"]
        if errs:
            (rdir(root) / f"{rid}.failed.txt").write_text((str(res.get("result") or se or ""))[-20000:])
            transition(root, st, rid, "failed", actor)
            return out({**result, "outcome": "failed", "errors": errs,
                        "actions": [{"action": "retry_next_due", "detail": "The next `due` check will offer a new review; "
                                     f"raw output kept in reviews/{rid}.failed.txt."}]}, 1)
        report.update({"schema_version": 1, "review_id": rid, "project_id": pid, "head": head, "base": base})
        write_json(report_path(root, rid), report)
        (rdir(root) / f"{rid}.md").write_text(render_md(report))
        st = load_state(root)
        st["last"] = {"review_id": rid, "at": fmt_dt(now_utc()), "head": head, "done_count": st["reviews"][rid]["done_count"]}
        n = len(report["findings"])
        st["reviews"][rid]["findings"] = n
        save_state(root, st)
        if n == 0:
            transition(root, st, rid, "no_findings", actor)
            return out({**result, "outcome": "no_findings", "report": str(report_path(root, rid))})
        transition(root, st, rid, "reported", actor)
        return out({**result, "outcome": "reported", "findings": n, "report": str(report_path(root, rid)),
                    "actions": [{"action": "triage", "cmd": f"architecture-review.sh triage {rid}"}]})
    except Exception as exc:  # noqa: BLE001
        st = load_state(root)
        if rid in st.get("reviews", {}):
            transition(root, st, rid, "failed", actor)
        return out({**result, "outcome": "failed", "errors": [str(exc)]}, 1)
    finally:
        lock_release(root, actor, rid)


# ---------------------------------------------------------------- triage

def triage_prompt(pid: str, doc: str, rp: Path, tp: Path, max_new: int, kind: Kind = AR, extra: str = "") -> str:
    return (
        f"You own the task log of project {pid}. {'An' if kind.label[0] in 'AEIOU' else 'A'} "
        f"{kind.label.lower()} needs triage (control-plane SPEC §19).\n"
        f"Re-read {doc} now and follow it exactly.\n"
        f"Review report: {rp}\n"
        f"max_new_tasks: {max_new}\n"
        + extra
        + f"Write your triage to: {tp}\n"
        "Then print the same triage JSON as your final message.\n"
    )


def apply_triage(root: Path, rid: str, actor: str, t: dict[str, Any], kind: Kind = AR) -> dict[str, Any]:
    st = load_state(root, kind)
    recorded = {"commit_sha": t.get("commit_sha"), "tasks_created": t.get("tasks_created") or [],
                "record": t.get("record"), "triaged_at": t.get("triaged_at")}
    if t.get("commit_sha") == "pending":
        recorded["pending_change"] = t.get("pending_change")
    st.setdefault("reviews", {}).setdefault(rid, {}).update(recorded)
    transition(root, st, rid, "triaged", actor, kind)
    actions: list[dict[str, Any]] = []
    if t.get("tasks_created"):
        actions.append({"action": "register_tasks", "task_ids": t["tasks_created"],
                        "detail": "Pull the integration branch and register each new durable task in the runtime queue "
                                  "(tasks/<id>.json, status pending) exactly as for any new durable task."})
    if t.get("question_for_operator"):
        # §17.10: nothing emails; the lead asks the operator in its own session.
        actions.append({"action": "lead_asks_operator", "question": t["question_for_operator"],
                        "detail": "The lead (the task-log owner) asks the operator in its own session and records "
                                  "their answer."})
    if t.get("commit_sha") == "pending":
        actions.append({
            "action": "backfill",
            "cmd": f"ccp architect triage --backfill {rid} <sha>",
            "detail": "Triage is final. When this change is on the integration branch, record its sha. "
                      f"Pending: {t.get('pending_change')}",
        })
    counts: dict[str, int] = {}
    for d in t.get("dispositions") or []:
        counts[d["disposition"]] = counts.get(d["disposition"], 0) + 1
    return {"outcome": "triaged", "review_id": rid, "commit_sha": t.get("commit_sha"), "record": t.get("record"),
            "dispositions": counts, "actions": actions}


def cmd_triage(args: argparse.Namespace) -> int:
    return triage(sm.root_dir(), args.review_id, actor_of(args.actor), AR)


def _checkout(named: str, product_dir: str | None) -> str:
    """A product directory that exists. A Mac path recorded in the queue is not one on a cloud seat."""
    if named and os.path.isdir(named):
        return named
    if product_dir and os.path.isdir(product_dir):
        return product_dir
    return product_dir or named or ""


def triage(root: Path, rid: str, actor: str, kind: Kind, max_new: int | None = None,
           probes: list[str] | None = None, prompt_extra: str = "", extra_check: Any = None,
           product_dir: str | None = None) -> int:
    """Hand one report of this kind to the task-log owner, or apply its triage file (§19.8).

    The architect (§19) passes its own `max_new` and `probes` (from plane.json rather than
    project.yaml), `prompt_extra` for §19.8's steps, `extra_check(triage, report) -> errors`, and
    `product_dir` for a queue whose project.yaml names no product_root."""
    if not kind.rid_re.match(rid):
        die(f"bad review id {rid!r}", 2)
    rp, tp = report_path(root, rid), triage_path(root, rid)
    if not rp.is_file():
        die(f"no report {rp}", 2)
    st = load_state(root, kind)
    status = (st.get("reviews", {}).get(rid) or {}).get("status")
    if status == "triaged":
        return out({"outcome": "already_triaged", "review_id": rid})
    # A triage file already present (async owner, earlier call, or written by hand in the session)?
    def check(t: Any) -> list[str]:
        errs = validate_triage(t, rid)
        if not errs and extra_check is not None:
            errs = extra_check(t, read_json(rp))
        return errs

    if tp.is_file():
        t = read_json(tp)
        errs = check(t)
        if not errs:
            return out(apply_triage(root, rid, actor, t, kind))
        return out({"outcome": "invalid_triage", "review_id": rid, "errors": errs}, 1)
    pid = sm.project_id(root)
    c = cfg(root)
    if max_new is not None:
        c["max_new_tasks"] = max_new
    if probes is not None:
        c["probes"] = probes
    pr = _checkout(sm.product_root(root), product_dir)
    doc = triage_doc(pr or "")
    if not os.path.isfile(doc):
        die(f"missing {doc}: the review-triage protocol (the plugin's skill, or docs/delivery/REVIEW-TRIAGE.md)", 1)
    prompt = triage_prompt(pid, doc, rp, tp, c["max_new_tasks"], kind, prompt_extra)
    # §17, §17.3: the lead (the task-log owner) triages in its own session and writes the triage file.
    transition(root, st, rid, "triage_sent", actor, kind)
    act = {"action": "send_message_to_lead", "to": "team-lead", "message": prompt,
           "detail": f"Async: run `{kind.triage_cmd} {rid}` on a later wake to apply the triage file."}
    return out({"outcome": "sent_async", "review_id": rid, "actions": [act]})


# ---------------------------------------------------------------- status

def cmd_status(args: argparse.Namespace) -> int:
    root = sm.root_dir()
    st = load_state(root)
    return out({"due": due_info(root), "last": st.get("last"), "reviews": st.get("reviews")})


def architect_product(root: Path) -> str | None:
    """The product root when its plane.json has an `architect` block (then this is an alias), else None."""
    pr = sm.product_root(root)
    try:
        return pr if pr and "architect" in json.loads((Path(pr) / "docs/delivery/plane.json").read_text()) else None
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Architecture review (SPEC §19)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    r = sub.add_parser("run")
    r.add_argument("--force", action="store_true", help="run even if not due (on demand)")
    r.add_argument("--actor")
    t = sub.add_parser("triage")
    t.add_argument("review_id")
    t.add_argument("--actor")
    sub.add_parser("status")
    a = ap.parse_args(argv)
    pr = architect_product(sm.root_dir())
    if pr:  # §19: the product moved to the architect seat; this command is its alias
        sys.path.insert(0, str(HERE.parent.parent))
        from ccp.cli import main as dp_main  # noqa: PLC0415
        print(f"architecture-review.sh: {pr} has an architect block; running `ccp architect {a.cmd}` (SPEC §19)",
              file=sys.stderr)
        return dp_main(["--root", pr, "architect", a.cmd]
                       + ([a.review_id] if a.cmd == "triage" else [])
                       + (["--force"] if a.cmd == "run" and a.force else [])
                       + (["--actor", a.actor] if getattr(a, "actor", None) else []))
    return {"due": cmd_due, "run": cmd_run, "triage": cmd_triage, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
