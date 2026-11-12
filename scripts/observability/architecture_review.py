"""The §19 review kit the architect seat (`ccp architect`, SPEC §19) runs on: review kinds, the
reviewer lock, report and triage validation, rendering, and the triage hand-off to the task-log owner.

Runtime files only (QUEUE_ROOT, outside product git); the durable record is written by the triage
owner in the product repo (docs/delivery/reviews/<review_id>.md). No secrets.

A review *kind* (`Kind`) names its own state file, lock, id prefixes, event type and finding
categories; every function takes the kind it works on. The older architecture-review and docs-audit
aliases are retired (§19.12); their queue records stay readable by the board and health.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
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
    append_event,
    die,
    fmt_dt,
    looks_like_secret,
    read_json,
    write_json,
)
import spec_maintainer as sm  # noqa: E402  (lock, quota parse, Claude JSON parse, binding helpers)

CATEGORIES = ("holdover", "not-first-class", "duplication", "vocabulary-drift", "dead-surface",
              "incoherence", "unobserved", "cost", "rule-cost")


class Kind(NamedTuple):
    """One kind of review: where its runtime files live and what its findings may say."""
    name: str            # observability event type
    label: str           # "Architect pass"
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


DISPOSITIONS = ("task", "spec", "defer", "needs_operator", "duplicate", "reject")
BASE_READ_TOOLS = ["Read", "Grep", "Glob", "Skill",
                   "Bash(git log:*)", "Bash(git show:*)", "Bash(git diff:*)", "Bash(git ls-files:*)",
                   "Bash(git grep:*)", "Bash(git status:*)", "Bash(git rev-parse:*)", "Bash(git blame:*)",
                   "Bash(ls:*)", "Bash(wc:*)"]
DENY_TOOLS = "Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent,Task"
# Fresh headless reviewers pin their own model and effort rather than take the operator's defaults
# (SPEC §2.4 *Models and effort*). The resumed owner triage keeps the owner session's own settings.
HEADLESS_MODEL = ["--model", "claude-opus-5-5", "--effort", "high"]
ARCHITECT_SKILL = ".claude/skills/architect/SKILL.md"  # §19: a product's managed copy, if it keeps one
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


def state_path(root: Path, kind: Kind) -> Path:
    return root / kind.state


def load_state(root: Path, kind: Kind) -> dict[str, Any]:
    p = state_path(root, kind)
    return read_json(p) if p.is_file() else {"schema_version": 1, "reviews": {}}


def save_state(root: Path, st: dict[str, Any], kind: Kind) -> None:
    write_json(state_path(root, kind), st)


@contextmanager
def state_lock(root: Path, kind: Kind):
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


def emit(root: Path, actor: str, op: str, payload: dict[str, Any], kind: Kind) -> None:
    append_event(root, {"at": fmt_dt(now_utc()), "project_id": sm.project_id(root), "task_id": "",
                        "actor": actor, "type": kind.name, "op": op, "payload": payload})


def transition(root: Path, st: dict[str, Any], rid: str, to: str, actor: str, kind: Kind) -> None:
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


def validate_report(r: Any, rid: str, pid: str, kind: Kind, max_findings: int = 25) -> list[str]:
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


def render_md(r: dict[str, Any], kind: Kind) -> str:
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

def lock_take(root: Path, actor: str, rid: str, ttl_s: int, kind: Kind) -> tuple[bool, dict[str, Any] | None]:
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


def lock_release(root: Path, actor: str, rid: str, kind: Kind) -> None:
    path = root / kind.lock
    try:
        cur = read_json(path)
    except (OSError, ValueError):
        return
    if cur.get("pid") in (os.getpid(), str(os.getpid())):
        path.unlink(missing_ok=True)
        emit(root, actor, "clear", {"holder": actor, "reason": "released", "review_id": rid}, kind)


# ---------------------------------------------------------------- triage

def triage_prompt(pid: str, doc: str, rp: Path, tp: Path, max_new: int, kind: Kind, extra: str = "") -> str:
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


def apply_triage(root: Path, rid: str, actor: str, t: dict[str, Any], kind: Kind) -> dict[str, Any]:
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


def triage(root: Path, rid: str, actor: str, kind: Kind, max_new: int, prompt_extra: str = "",
           extra_check: Any = None, product_dir: str | None = None) -> int:
    """Hand one report of this kind to the task-log owner, or apply its triage file (§19.8).

    The architect (§19) passes `max_new` (its `max_new_tasks`), `prompt_extra` for §19.8's steps,
    `extra_check(triage, report) -> errors`, and `product_dir` for a queue whose binding (§8.3) names
    no product_root."""
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
    pr = _checkout(sm.product_root(root), product_dir)
    doc = triage_doc(pr or "")
    if not os.path.isfile(doc):
        die(f"missing {doc}: the review-triage protocol (the plugin's skill, or docs/delivery/REVIEW-TRIAGE.md)", 1)
    prompt = triage_prompt(pid, doc, rp, tp, max_new, kind, prompt_extra)
    # §17, §17.3: the lead (the task-log owner) triages in its own session and writes the triage file.
    transition(root, st, rid, "triage_sent", actor, kind)
    act = {"action": "send_message_to_lead", "to": "team-lead", "message": prompt,
           "detail": f"Async: run `{kind.triage_cmd} {rid}` on a later wake to apply the triage file."}
    return out({"outcome": "sent_async", "review_id": rid, "actions": [act]})
