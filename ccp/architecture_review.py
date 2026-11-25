"""The §19 review kit the architect seat (`ccp architect`, SPEC §19) runs on: the seat's state file, lock,
id prefixes, event type, lenses and finding categories, the reviewer lock, report and triage validation,
rendering, and the triage hand-off to the task-log owner.

Runtime files only (QUEUE_ROOT, outside product git); the durable record is written by the triage
owner in the product repo (docs/delivery/reviews/<review_id>.md). No secrets.

The kit serves the architect seat alone. The older architecture-review and docs-audit aliases are
retired (§19.12); their queue records stay readable by the board and health.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import socket
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import models, refs, schema
from ccp.lib import (
    ACTORS,
    RUNNER,
    append_event,
    die,
    fmt_dt,
    lock_is_stale,
    looks_like_secret,
    product_root,
    project_id,
    read_json,
    write_json,
)

EVENT = "architect"              # observability event type
LABEL = "Architect pass"
PREFIXES = ("ar", "sh")           # review id prefixes: a pass, a shape
STATE = "architect.json"          # QUEUE_ROOT state file
LOCK = "architect.lock"           # QUEUE_ROOT reviewer lock
AUDIT_TASK = "architect"          # prompt-audit task id
TRIAGE_CMD = "ccp architect triage"  # how the Runner re-runs triage
RID_RE = re.compile(rf"^(?:{'|'.join(PREFIXES)})-{refs.STAMP_ID}$")

STRUCTURE_CATEGORIES = ("holdover", "not-first-class", "duplication", "vocabulary-drift", "dead-surface",
                        "incoherence", "unobserved", "cost", "rule-cost")
LENSES: dict[str, tuple[str, ...]] = {
    "structure": STRUCTURE_CATEGORIES,
    "docs": ("doc-wrong", "doc-missing", "doc-aspirational", "doc-padding", "doc-history"),
    "tests": ("test-cost", "test-brittle"),
    "process": ("process-cost",),
}
CATEGORIES = tuple(c for cats in LENSES.values() for c in cats)  # every lens's, in order

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
REPORT_SCHEMA = CONTRACTS / "architect_report.schema.json"
TRIAGE_SCHEMA = CONTRACTS / "architecture_review_triage.schema.json"
DISPOSITIONS = ("task", "spec", "defer", "needs_operator", "duplicate", "reject")
BASE_READ_TOOLS = ["Read", "Grep", "Glob", "Skill",
                   "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git ls-files:*)",
                   "Bash(git grep:*)", "Bash(git status:*)", "Bash(git rev-parse:*)", "Bash(git blame:*)",
                   "Bash(ls:*)", "Bash(wc:*)"]
DENY_TOOLS = "Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent,Task"
# Fresh headless reviewers pin their own model and effort rather than take the operator's defaults
# (SPEC §2.4 *Models and effort*). The resumed owner triage keeps the owner session's own settings.
HEADLESS_MODEL = models.headless_flags("architect")


def headless_flags(cfg: Any = None) -> list[str]:
    """The `claude -p` flags for the architect's model: the product's (`models.architect`, with `cfg`), else the default."""
    return models.headless_flags("architect", cfg)


ARCHITECT_SKILL = ".claude/skills/architect/SKILL.md"  # §19: a product's managed copy, if it keeps one
PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugin"


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


def state_path(root: Path) -> Path:
    return root / STATE


def load_state(root: Path) -> dict[str, Any]:
    p = state_path(root)
    return read_json(p) if p.is_file() else {"schema_version": 1, "reviews": {}}


def save_state(root: Path, st: dict[str, Any]) -> None:
    write_json(state_path(root), st)


@contextmanager
def state_lock(root: Path):
    """The state file's own lock, held for one read-modify-write (milliseconds, never across a call).
    A detached architect pass writes its record while `ccp tasks next` and triage write theirs."""
    fd = os.open(str(state_path(root)) + ".lock", os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def update_state(root: Path, fn: Any) -> dict[str, Any]:
    """Re-read the state under its lock, apply `fn` to it, save it; returns what was saved."""
    with state_lock(root):
        st = load_state(root)
        st.setdefault("reviews", {})
        fn(st)
        save_state(root, st)
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
    a = arg or os.environ.get("ACTOR") or RUNNER
    return a if a in ACTORS else "system"


def emit(root: Path, actor: str, op: str, payload: dict[str, Any]) -> None:
    append_event(root, {"at": fmt_dt(now_utc()), "project_id": project_id(root), "task_id": "",
                        "actor": actor, "type": EVENT, "op": op, "payload": payload})


def transition(root: Path, st: dict[str, Any], rid: str, to: str, actor: str) -> None:
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

    fresh = update_state(root, apply)
    st.setdefault("reviews", {})[rid] = fresh["reviews"][rid]
    emit(root, actor, "transition", {"review_id": rid, "from": frm[0], "to": to})


def git(cwd: str, *a: str) -> str:
    r = subprocess.run(["git", "-C", cwd, *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def last_json_object(text: str) -> dict[str, Any] | None:
    """The last top-level JSON object in a model's final message (fenced or bare).

    A fenced ```json block wins. Otherwise the message is read left to right: at each `{` a JSON
    decode is tried, and a decoded object is skipped whole, so braces quoted inside its strings
    never count and only top-level objects are found; the last one wins.
    """
    t = text or ""
    fences = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    for c in reversed(fences):
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    dec = json.JSONDecoder()
    last: dict[str, Any] | None = None
    i = t.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(t, i)
        except json.JSONDecodeError:
            i = t.find("{", i + 1)
            continue
        if isinstance(obj, dict):
            last = obj
        i = t.find("{", end)
    return last


def validate_report(r: Any, rid: str, pid: str, categories: tuple[str, ...] = CATEGORIES, max_findings: int = 25,
                    ids: refs.Ids = refs.DEFAULT) -> list[str]:
    """A report as written against its contract (`REPORT_SCHEMA`, by `ccp.schema`'s one checker), then what the
    contract cannot say: the review id is this review's, a finding's category is within the pass's lenses
    (`categories`), no low confidence, a rule-cost finding asks for a decision, a rule change's rule id has the
    product's shape (`ids`), and no secret."""
    if not isinstance(r, dict):
        return ["report is not an object"]
    errs = schema.schema_errors(r, json.loads(REPORT_SCHEMA.read_text()), at="report")
    if r.get("review_id") not in (None, rid):
        errs.append(f"review_id {r.get('review_id')!r} != {rid}")
    f = r.get("findings")
    if isinstance(f, list) and len(f) > max_findings:
        errs.append(f"{len(f)} findings > {max_findings}")
    for x in f if isinstance(f, list) else []:
        if not isinstance(x, dict):
            continue
        if x.get("category") and x["category"] not in categories:
            errs.append(f"{x.get('id')}: category {x['category']!r}")
        if x.get("confidence") == "low":
            errs.append(f"{x.get('id')}: low confidence is not reported (skill rule)")
        if x.get("category") == "rule-cost" and (not x.get("needs_decision") or x.get("fix") != "decide"):
            errs.append(f"{x.get('id')}: a rule-cost finding needs a decision (needs_decision: true, fix: decide)")
    rc = r.get("rule_changes")
    for i, c in enumerate(rc if isinstance(rc, list) else []):
        if isinstance(c, dict) and isinstance(c.get("rule"), str) and not ids.is_rule_id(c["rule"]):
            errs.append(f"rule_changes[{i}]: rule {c['rule']!r} is not a rule id ({ids.rule_shape})")
    if looks_like_secret(json.dumps(r)):
        errs.append("report contains a secret-like string")
    return errs


COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")


def is_commit_sha(value: Any) -> bool:
    """A git sha. The word pending is not one: it marks an applied rule change still to land."""
    return isinstance(value, str) and bool(COMMIT_SHA_RE.fullmatch(value))


def validate_triage(t: Any, rid: str, ids: refs.Ids = refs.DEFAULT) -> list[str]:
    """A triage against its contract (`TRIAGE_SCHEMA`, by `ccp.schema`'s one checker), then what the contract
    cannot say: a task id and a rule id have the product's shapes (`ids`, SPEC §7.1), the review id is this review's,
    a task or ruling has a commit sha, and no secret."""
    if not isinstance(t, dict):
        return ["triage is not an object"]
    errs = schema.schema_errors(t, json.loads(TRIAGE_SCHEMA.read_text()), at="triage")
    created = t.get("tasks_created")
    for i, tid in enumerate(created if isinstance(created, list) else []):
        if isinstance(tid, str) and not ids.task_id_re.match(tid):
            errs.append(f"triage.tasks_created[{i}]: {tid!r} is not a task id (ids.task.width {ids.task_width})")
    changes = t.get("rule_changes")
    for i, c in enumerate(changes if isinstance(changes, list) else []):
        if isinstance(c, dict) and isinstance(c.get("rule"), str) and not ids.is_rule_id(c["rule"]):
            errs.append(f"triage.rule_changes[{i}].rule: {c['rule']!r} is not a rule id ({ids.rule_shape})")
    if t.get("review_id") != rid:
        errs.append(f"review_id {t.get('review_id')!r} != {rid}")
    if (t.get("tasks_created") or any((d or {}).get("disposition") in ("task", "spec") for d in t.get("dispositions") or []
                                      if isinstance(d, dict))) and not is_commit_sha(t.get("commit_sha")):
        errs.append("tasks or rulings without commit_sha")
    if looks_like_secret(json.dumps(t)):
        errs.append("triage contains a secret-like string")
    return errs


def render_md(r: dict[str, Any], label: str = LABEL) -> str:
    lines = [f"# {label} {r.get('review_id')}", "",
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

def lock_take(root: Path, actor: str, rid: str, ttl_s: int) -> tuple[bool, dict[str, Any] | None]:
    path = root / LOCK
    for _ in range(2):
        body = {"holder": actor, "pid": os.getpid(), "host": socket.gethostname(), "since": fmt_dt(now_utc()),
                "ttl_seconds": ttl_s, "review_id": rid}
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            cur = read_json(path) if path.is_file() else {}
            if lock_is_stale(cur, now_utc()):
                emit(root, actor, "clear", {"holder": cur.get("holder"), "reason": "stale", "review_id": cur.get("review_id")})
                path.unlink(missing_ok=True)
                continue
            return False, cur
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(body, indent=2) + "\n")
        emit(root, actor, "set", {"holder": actor, "reason": "review", "review_id": rid})
        return True, body
    return False, None


def lock_release(root: Path, actor: str, rid: str) -> None:
    path = root / LOCK
    try:
        cur = read_json(path)
    except (OSError, ValueError):
        return
    if cur.get("pid") in (os.getpid(), str(os.getpid())):
        path.unlink(missing_ok=True)
        emit(root, actor, "clear", {"holder": actor, "reason": "released", "review_id": rid})


# ---------------------------------------------------------------- triage

def triage_prompt(pid: str, doc: str, rp: Path, tp: Path, max_new: int, extra: str = "") -> str:
    return (
        f"You own the task log of project {pid}. {'An' if LABEL[0] in 'AEIOU' else 'A'} "
        f"{LABEL.lower()} needs triage (control-plane SPEC §19).\n"
        f"Re-read {doc} now and follow it exactly.\n"
        f"Review report: {rp}\n"
        f"max_new_tasks: {max_new}\n"
        + extra
        + f"Write your triage to: {tp}\n"
        "Then print the same triage JSON as your final message.\n"
    )


def apply_triage(root: Path, rid: str, actor: str, t: dict[str, Any]) -> dict[str, Any]:
    st = load_state(root)
    recorded = {"commit_sha": t.get("commit_sha"), "tasks_created": t.get("tasks_created") or [],
                "record": t.get("record"), "triaged_at": t.get("triaged_at")}
    if t.get("commit_sha") == "pending":
        recorded["pending_change"] = t.get("pending_change")
    st.setdefault("reviews", {}).setdefault(rid, {}).update(recorded)
    transition(root, st, rid, "triaged", actor)
    actions: list[dict[str, Any]] = []
    if t.get("tasks_created"):
        actions.append({"action": "register_tasks", "task_ids": t["tasks_created"],
                        "detail": "Pull the integration branch and register each new durable task in the runtime queue "
                                  "(tasks/<id>.json, status pending) exactly as for any new durable task."})
    if t.get("question_for_operator"):
        # §17.10: the lead asks the operator in its own session (not a §3.6 notify trigger).
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


def _checkout(named: str, product_dir: str | None) -> str:
    """A product directory that exists. A Mac path recorded in the queue is not one on a cloud seat."""
    if named and os.path.isdir(named):
        return named
    if product_dir and os.path.isdir(product_dir):
        return product_dir
    return product_dir or named or ""


def triage(root: Path, rid: str, actor: str, max_new: int, prompt_extra: str = "",
           extra_check: Any = None, product_dir: str | None = None, ids: refs.Ids = refs.DEFAULT) -> int:
    """Hand one report to the task-log owner, or apply its triage file (§19.8).

    The architect (§19) passes `max_new` (its `max_new_tasks`), `prompt_extra` for §19.8's steps,
    `extra_check(triage, report) -> errors`, and `product_dir` for a queue whose binding (§8.3) names
    no product_root; `ids` is the product's id shapes (§7.1)."""
    if not RID_RE.match(rid):
        die(f"bad review id {rid!r}", 2)
    rp, tp = report_path(root, rid), triage_path(root, rid)
    if not rp.is_file():
        die(f"no report {rp}", 2)
    st = load_state(root)
    status = (st.get("reviews", {}).get(rid) or {}).get("status")
    if status == "triaged":
        return out({"outcome": "already_triaged", "review_id": rid})
    # A triage file already present (async owner, earlier call, or written by hand in the session)?
    def check(t: Any) -> list[str]:
        errs = validate_triage(t, rid, ids)
        if not errs and extra_check is not None:
            errs = extra_check(t, read_json(rp))
        return errs

    if tp.is_file():
        t = read_json(tp)
        errs = check(t)
        if not errs:
            return out(apply_triage(root, rid, actor, t))
        return out({"outcome": "invalid_triage", "review_id": rid, "errors": errs}, 1)
    pid = project_id(root)
    pr = _checkout(product_root(root), product_dir)
    doc = triage_doc(pr or "")
    if not os.path.isfile(doc):
        die(f"missing {doc}: the review-triage protocol (the plugin's skill, or docs/delivery/REVIEW-TRIAGE.md)", 1)
    prompt = triage_prompt(pid, doc, rp, tp, max_new, prompt_extra)
    # §17, §17.3: the lead (the task-log owner) triages in its own session and writes the triage file.
    transition(root, st, rid, "triage_sent", actor)
    act = {"action": "send_message_to_lead", "to": "team-lead", "message": prompt,
           "detail": f"Async: run `{TRIAGE_CMD} {rid}` on a later wake to apply the triage file."}
    return out({"outcome": "sent_async", "review_id": rid, "actions": [act]})
