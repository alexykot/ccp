"""Spec questions (SPEC §17): the runner raises them, the team lead answers them.

Called through scripts/spec-maintainer-ask.sh (raise, process, blocked). The lead (the design seat)
is the spec maintainer: the runner messages it, the lead rules in its own session and writes the
answer file, and `process` applies the answer. Runtime files only (QUEUE_ROOT/questions/).
Never writes project.yaml, product code or secrets; never sends messages itself: it prints the
exact actions the calling seat performs. The headless `claude --resume` maintainer, its lock and
its email were removed on 2026-11-05 (operator ruling D4).
"""

from __future__ import annotations

import argparse

import json

import os

import re

import secrets

import subprocess

import sys

from datetime import datetime, timezone

from pathlib import Path

from typing import Any

HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))

from lib import (  # noqa: E402
    ACTORS,
    RUNNER,
    append_event,
    apply_event,
    binding_data,
    binding_str,
    die,
    events_path,
    fmt_dt,
    load_events,
    lock_is_stale,  # noqa: F401  (re-exported: architecture_review.py's lock reads it)
    looks_like_secret,
    new_task_state,
    parse_dt,
    resolve_durable_docs_dir,
    read_json,
    wait_writer_cmd,
    write_json,
)

if str(HERE.parents[1]) not in sys.path:
    sys.path.insert(0, str(HERE.parents[1]))
from ccp import refs  # noqa: E402  (the id shapes, §7)

RAISERS = (RUNNER, "task-verifier")

VERDICTS = ("resolved", "needs_operator", "not_a_spec_question")

QID_RE = re.compile(rf"^{refs.QUESTION_ID}$")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def root_dir() -> Path:
    """The live queue: QUEUE_ROOT when set; else, as `ccp` finds it (SPEC §9.2), the queue the plane's own
    `bin/ccp --root <dir> where` prints for this product (the dir: CLAUDE_PROJECT_DIR, else the working
    directory). With neither, it dies naming `ccp init` and QUEUE_ROOT."""
    raw = os.environ.get("QUEUE_ROOT") or where_queue_root()
    if not raw:
        die("set QUEUE_ROOT to the live queue dir outside product git; no binding names this product: "
            "run `ccp init`, or set QUEUE_ROOT", 2)
    return Path(raw).expanduser().resolve()


def where_queue_root() -> str | None:
    """SPEC §9.2: the queue `ccp where` prints for the product at CLAUDE_PROJECT_DIR (else the working
    directory), from the plane's own `bin/ccp`; None when it names none or does not answer."""
    where = [sys.executable, str(HERE.parents[1] / "bin" / "ccp"),
             "--root", os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), "where"]
    try:
        r = subprocess.run(where, capture_output=True, text=True, timeout=30)
        q = json.loads(r.stdout).get("queue_root") if r.returncode == 0 else None
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError):
        return None
    return q if isinstance(q, str) and q else None


def project_id(root: Path, q: dict[str, Any] | None = None) -> str:
    pid = os.environ.get("PROJECT_ID") or (q or {}).get("project_id")
    return pid or binding_str(binding_data(root), "project_id") or root.name


def env_raiser() -> str | None:
    """$ACTOR only counts when it names a raising seat (an ambient ACTOR that names no raising seat must not leak in)."""
    a = os.environ.get("ACTOR")
    return a if a in RAISERS else None


def actor_for(holder: str | None) -> str:
    if holder in ACTORS:
        return str(holder)
    return "operator" if holder == "operator" else "system"


def emit(root: Path, pid: str, task_id: str, actor: str, typ: str, op: str, payload: dict[str, Any]) -> dict[str, Any]:
    return append_event(
        root,
        {
            "at": fmt_dt(now_utc()),
            "project_id": pid,
            "task_id": task_id or "",
            "actor": actor if actor in ACTORS else "system",
            "type": typ,
            "op": op,
            "payload": payload,
        },
    )


def qdir(root: Path) -> Path:
    return root / "questions"


def qpath(root: Path, qid: str) -> Path:
    return qdir(root) / f"{qid}.json"


def apath(root: Path, qid: str) -> Path:
    return qdir(root) / f"{qid}.answer.json"


def load_question(root: Path, ref: str) -> tuple[Path, dict[str, Any]]:
    p = Path(ref)
    if not p.is_file():
        p = qpath(root, ref)
    if not p.is_file():
        die(f"question not found: {ref}", 2)
    data = read_json(p)
    if not isinstance(data, dict):
        die(f"invalid question file {p}", 2)
    return p, data


def save_question(path: Path, q: dict[str, Any]) -> None:
    q["updated_at"] = fmt_dt(now_utc())
    if looks_like_secret(json.dumps(q)):
        die("refusing secret-like value in question file")
    write_json(path, q)


def validate_question(q: dict[str, Any]) -> list[str]:
    errs = []
    for k in ("task_id", "project_id", "question_id", "class", "text", "status", "asked_at", "route", "raised_by", "blocks", "dispatch"):
        if k not in q:
            errs.append(f"missing {k}")
    if q.get("class") != "spec":
        errs.append("class must be spec")
    if not QID_RE.match(str(q.get("question_id") or "")):
        errs.append("question_id must match sm-<yyyymmddThhmmssZ>-<4hex>")
    if q.get("route") not in ("spec_maintainer", "steerer"):
        errs.append("route invalid")
    if q.get("raised_by") not in RAISERS:
        errs.append("raised_by must be task-runner or task-verifier")
    if not isinstance(q.get("blocks"), list) or not q.get("blocks"):
        errs.append("blocks must be a non-empty list")
    if q.get("dispatch") not in ("pending", "in_call", "queued_lock", "quota_parked", "done"):
        errs.append("dispatch invalid")
    if q.get("status") not in ("open", "answered", "escalated"):
        errs.append("status invalid")
    return errs


def validate_answer(a: Any, qid: str) -> list[str]:
    """Mirror of contracts/question_answer.schema.json (no jsonschema dependency)."""
    if not isinstance(a, dict):
        return ["answer is not an object"]
    errs = []
    allowed = {
        "schema_version", "question_id", "project_id", "verdict", "ruling", "reasoning", "commit_sha",
        "files_changed", "question_for_operator", "guidance", "answered_by", "session_id", "answered_at",
        "supersedes", "written_by",
    }
    for k in a:
        if k not in allowed:
            errs.append(f"unexpected key {k}")
    for k in ("schema_version", "question_id", "project_id", "verdict", "reasoning", "answered_by", "answered_at"):
        if k not in a:
            errs.append(f"missing {k}")
    if a.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    if a.get("question_id") != qid:
        errs.append("question_id mismatch")
    v = a.get("verdict")
    if v not in VERDICTS:
        errs.append("verdict invalid")
    if not str(a.get("reasoning") or "").strip():
        errs.append("reasoning required")
    if a.get("answered_by") not in ("spec_maintainer", "operator_via_maintainer"):
        errs.append("answered_by invalid")
    try:
        parse_dt(a.get("answered_at"))
    except Exception:
        errs.append("answered_at not RFC3339")
    if v == "resolved":
        if not str(a.get("ruling") or "").strip():
            errs.append("resolved requires ruling")
        if not a.get("commit_sha") or len(str(a.get("commit_sha"))) < 4:
            errs.append("resolved requires commit_sha")
        if not isinstance(a.get("files_changed"), list) or not a.get("files_changed"):
            errs.append("resolved requires files_changed")
    if v == "needs_operator" and not str(a.get("question_for_operator") or "").strip():
        errs.append("needs_operator requires question_for_operator")
    if a.get("answered_by") == "operator_via_maintainer" and not isinstance(a.get("supersedes"), dict):
        errs.append("operator_via_maintainer requires supersedes object")
    if "written_by" in a and a["written_by"] not in ("maintainer", "seat"):
        errs.append("written_by invalid")
    if looks_like_secret(json.dumps(a)):
        errs.append("secret-like value in answer")
    return errs


def fold_tasks(root: Path) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    seats: dict[str, dict[str, Any]] = {}
    auth: dict[str, Any] = {}
    for ev in load_events(events_path(root)):
        apply_event(tasks, seats, auth, ev, {"questions": {}, "lock": None})
    tdir = root / "tasks"
    if tdir.is_dir():
        for p in tdir.glob("*.json"):
            try:
                t = read_json(p)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(t, dict):
                st = tasks.setdefault(t.get("task_id") or p.stem, new_task_state(t.get("task_id") or p.stem))
                if st.get("waiting_on") is None and t.get("waiting_on"):
                    st["waiting_on"] = t.get("waiting_on")
    return tasks


def waiting_for(root: Path, q: dict[str, Any], reasons: tuple[str, ...]) -> list[str]:
    tasks = fold_tasks(root)
    out = []
    for tid in q.get("blocks") or []:
        st = tasks.get(tid) or {}
        if st.get("waiting_on") in reasons and str(st.get("wait_detail") or "") == q["question_id"]:
            out.append(tid)
    return out

def product_config(root: Path) -> Any:
    """The product's loaded plane.json, at the product root the binding names (ccp.config); None with no
    product root, or a plane.json that is missing or cannot be read."""
    from ccp import config as ccp_config  # noqa: PLC0415
    prod = product_root(root)
    if not prod:
        return None
    try:
        return ccp_config.load(Path(prod))
    except Exception:  # noqa: BLE001  (no readable config: the caller falls back to the defaults or the queue)
        return None


def check_task_ids(root: Path, ids: list[str], flag: str) -> list[str]:
    """Refuse anything that is not a task id, before any write (no fragment ever becomes a task_id).

    Each entry must match the product's task-id shape at its width (ccp refs; the default `Ids` when no
    plane.json can be read). When the product's task log is reachable and has tasks, it must also name an
    existing task (docs/delivery/tasks/<id>.md) or a claimed one (QUEUE_ROOT/tasks/<id>.json).
    """
    shape = refs.ids(product_config(root))
    bad = [i for i in ids if not shape.task_id_re.match(i)]
    if bad:
        die(f"{flag}: not task ids: {', '.join(repr(b) for b in bad)}. Give task ids only, comma-separated "
            f"({'N' * shape.task_width}-slug, e.g. {shape.format_task_number(8)}-p1-regimes); put explanations "
            "in --text or --tried.", 2)
    docs = resolve_durable_docs_dir(root)
    tdir = docs / "tasks" if docs else None
    if tdir and tdir.is_dir() and any(tdir.glob("*.md")):
        unknown = [i for i in ids if not (tdir / f"{i}.md").is_file() and not (root / "tasks" / f"{i}.json").is_file()]
        if unknown:
            die(f"{flag}: no such task: {', '.join(unknown)} (not in {tdir} nor the queue's tasks/)", 2)
    return ids


def set_wait(root: Path, action: str, tid: str, reason: str, actor: str, pid: str, detail: str,
             resets_at: str | None = None, quota_class: str | None = None) -> None:
    cmd = wait_writer_cmd(action, tid, reason, actor=actor, project_id=pid, quota_class=quota_class,
                          resets_at=resets_at, detail=detail)
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
    if r.returncode != 0:
        die(f"set-waiting-on {action} {tid} failed: {r.stderr.strip()}")


def notify_operator(root: Path, trigger: str, task_id: str, ident: str, actor: str | None = None) -> list[str]:
    """SPEC §3.6: fire a trigger: its pending notice on record, the rendered notice on stderr, and the
    product's notify command when its plane.json names one. Best effort; returns the warnings to show
    (a command that failed, a record not written, or a plane.json that could not be read). With no
    product root or plane.json, or one that cannot be read, the notice is still recorded and printed,
    under the binding's project id, for the lead's session: no channel is configured, so none runs."""
    sys.path.insert(0, str(HERE.parents[1]))
    from ccp import config as ccp_config, notify  # noqa: PLC0415
    prod = product_root(root)
    warns: list[str] = []
    cfg = None
    if prod and (Path(prod) / ccp_config.CONFIG_REL).is_file():
        try:
            cfg = ccp_config.load(Path(prod))
        except Exception as e:  # noqa: BLE001  (the step happened; the notice goes to the lead's session)
            warns.append(f"notify: could not read the product's plane.json ({e}); raise the {trigger} in the "
                         "lead's session")
    if cfg is None:  # no channel configured: record it and print it for the lead's session
        cfg = ccp_config.Config(root=Path(prod) if prod else root, project_id=project_id(root), task_log={},
                                package_docs=None)
    return warns + notify.fire(cfg, root, trigger, task_id=task_id, ident=ident, who=actor)[1]


def product_root(root: Path) -> str:
    return binding_str(binding_data(root), "product_root") or ""


def protocol_doc_path(cfg: dict[str, str], root: Path) -> str:
    """Absolute path of the maintainer's protocol doc: `protocol_doc` relative to `cwd`, else the plugin skill (§17)."""
    doc = cfg.get("protocol_doc") or "docs/delivery/SPEC-MAINTAINER.md"
    if doc == "docs/delivery/SPEC-MAINTAINER.md":
        base = cfg.get("cwd") or product_root(root)
        if base and not os.path.isfile(f"{base.rstrip('/')}/{doc}"):
            doc = "plugin:ccp:spec-maintainer"  # §9.1: a product on the plugin has no copy
    if doc.startswith("plugin:"):
        # SPEC §9.1: the protocol is the plugin's skill, e.g. plugin:ccp:spec-maintainer.
        skill = doc.rsplit(":", 1)[-1]
        return str(Path(__file__).resolve().parents[2] / "plugin" / "skills" / skill / "SKILL.md")
    if doc.startswith("/"):
        return doc
    base = cfg.get("cwd") or product_root(root)
    return f"{base.rstrip('/')}/{doc}" if base else doc


def out(obj: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    return code


def act_on_answer(root: Path, qp: Path, q: dict[str, Any], ans: dict[str, Any], actor: str) -> dict[str, Any]:
    pid = project_id(root, q)
    qid = q["question_id"]
    verdict = ans["verdict"]
    events = load_events(events_path(root))
    result: dict[str, Any] = {"question_id": qid, "verdict": verdict, "actions": []}
    was_escalated = q.get("status") == "escalated"

    if ans.get("answered_by") == "operator_via_maintainer" and verdict in ("resolved", "not_a_spec_question"):
        seen = any(e.get("type") == "question" and e.get("op") == "resolved_by_operator"
                   and (e.get("payload") or {}).get("question_id") == qid for e in events)
        if not seen:
            emit(root, pid, q["task_id"], actor, "question", "resolved_by_operator",
                 {"question_id": qid, "commit_sha": ans.get("commit_sha")})

    already = any(e.get("type") == "question" and e.get("op") == "answered"
                  and (e.get("payload") or {}).get("question_id") == qid
                  and (e.get("payload") or {}).get("verdict") == verdict for e in events)
    q["status"] = "escalated" if verdict == "needs_operator" else "answered"
    q["dispatch"] = "done"
    q["answer_ref"] = f"questions/{qid}.answer.json"
    save_question(qp, q)
    if not already:
        payload = {"question_id": qid, "verdict": verdict, "answered_by": ans.get("answered_by")}
        if ans.get("commit_sha"):
            payload["commit_sha"] = ans["commit_sha"]
        emit(root, pid, q["task_id"], actor, "question", "answered", payload)

    if verdict in ("resolved", "not_a_spec_question"):
        clear_reason = "spec_resolved" if verdict == "resolved" else "not_a_spec_question"
        cleared = []
        for tid in waiting_for(root, q, ("spec_maintainer", "operator_decision", "steerer", "quota")):
            set_wait(root, "clear", tid, clear_reason, actor, pid, qid)
            cleared.append(tid)
        result["cleared"] = cleared
        if verdict == "resolved":
            note = f"Spec question `{qid}` resolved: {ans.get('ruling')}, commit `{ans.get('commit_sha')}`"
            result["actions"] += [
                {"action": "durable_log_note", "tasks": q.get("blocks"), "text": note},
                {"action": "pull_worktrees", "detail": "pull/rebase worktrees to pick up the spec commit before the next launch"},
                {"action": "resume_prompt_context", "ruling": ans.get("ruling"), "commit_sha": ans.get("commit_sha")},
            ]
        else:
            result["actions"] += [
                {"action": "decide_as_implementation_choice", "guidance": ans.get("guidance"),
                 "reasoning": ans.get("reasoning")},
                {"action": "durable_log_note", "tasks": q.get("blocks"),
                 "text": f"Spec question `{qid}` answered not_a_spec_question; seat decision: <record it>"},
            ]
        result["was_escalated"] = was_escalated
    else:  # needs_operator
        moved = []
        for tid in q.get("blocks") or []:
            set_wait(root, "set", tid, "operator_decision", actor, pid, qid)
            moved.append(tid)
        result["waiting_on_operator"] = moved
        if not already and (warn := notify_operator(root, "decision", str(q.get("task_id") or ""), qid, actor)):
            result["warnings"] = result.get("warnings", []) + warn
        # The notice is pending on record; a notify command, if any, has had the trigger (§3.6).
        result["actions"].append({
            "action": "wait_for_lead",
            "detail": "The design seat is asking the operator in its own session. It rewrites the answer file "
                      f"when they rule; then run spec-maintainer-ask.sh process {qid}. Skip ahead meanwhile.",
        })
    return result


def load_answer(root: Path, qid: str) -> tuple[dict[str, Any] | None, list[str]]:
    p = apath(root, qid)
    if not p.is_file():
        return None, ["answer file missing"]
    try:
        a = read_json(p)
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"answer file unreadable: {exc}"]
    errs = validate_answer(a, qid)
    return (a if not errs else None), errs


def cmd_raise(args: argparse.Namespace) -> int:
    root = root_dir()
    raised_by = args.raised_by or env_raiser()
    if raised_by not in RAISERS:
        die("--raised-by must be task-runner or task-verifier (the Watchdog never raises)", 2)
    pid = project_id(root)
    try:
        spec_refs = json.loads(args.spec_refs) if args.spec_refs.strip().startswith("[") else [x for x in args.spec_refs.split(",") if x]
        blocks = json.loads(args.blocks) if args.blocks and args.blocks.strip().startswith("[") else [x for x in (args.blocks or "").split(",") if x.strip()]
    except json.JSONDecodeError as exc:
        die(f"invalid JSON list: {exc}", 2)
    if not isinstance(blocks, list):
        die("--blocks must be task ids, comma-separated, or a JSON list", 2)
    blocks = [str(x).strip() for x in blocks]
    check_task_ids(root, [args.task_id], "--task-id")
    check_task_ids(root, blocks, "--blocks")
    if args.task_id not in blocks:
        blocks.insert(0, args.task_id)
    route = "spec_maintainer"
    t = now_utc()
    qid = f"sm-{t.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
    q = {
        "task_id": args.task_id,
        "project_id": pid,
        "question_id": qid,
        "class": "spec",
        "route": route,
        "text": args.text,
        "inconsistency": args.inconsistency,
        "spec_refs": spec_refs,
        "tried": args.tried,
        "blocks": blocks,
        "raised_by": raised_by,
        "status": "open",
        "dispatch": "pending",
        "answer_ref": None,
        "asked_at": fmt_dt(t),
        "updated_at": fmt_dt(t),
    }
    errs = validate_question(q)
    if errs:
        die("invalid question: " + "; ".join(errs), 2)
    if looks_like_secret(json.dumps(q)):
        die("refusing secret-like value in question")
    qd = qdir(root)
    qd.mkdir(parents=True, exist_ok=True)
    qp = qpath(root, qid)
    # 1. question file
    write_json(qp, q)
    # 2. waiting_on per blocked task (event first via set-waiting-on.sh)
    for tid in blocks:
        set_wait(root, "set", tid, "spec_maintainer", raised_by, pid, qid)
    # 3. question/raised
    emit(root, pid, args.task_id, raised_by, "question", "raised",
         {"question_id": qid, "raised_by": raised_by, "blocks": blocks, "route": route, "spec_refs": spec_refs})
    result: dict[str, Any] = {"question_id": qid, "question_file": str(qp), "route": route, "blocks": blocks}
    q["dispatch"] = "in_call"
    q["lead_messaged_at"] = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    save_question(qp, q)
    result["outcome"] = "sent_to_lead"
    result["actions"] = [lead_message_action(root, q)]
    return out(result)


def protocol_doc_label(root: Path) -> str:
    """Where the lead's protocol is: the product's SPEC-MAINTAINER.md when it has one, else the
    plugin's spec-maintainer skill (§9.1)."""
    p = protocol_doc_path({}, root)
    return "the control-plane plugin's spec-maintainer skill" if "/plugin/skills/" in p else p


def lead_message_action(root: Path, q: dict[str, Any]) -> dict[str, Any]:
    """§17.3: the one message the runner sends the team lead for a spec question."""
    qid = q["question_id"]
    return {
        "action": "send_message_to_lead",
        "to": "team-lead",
        "message": (f"Spec question {qid} for task {q['task_id']} (blocks {', '.join(q.get('blocks') or [])}). "
                    f"Question file: {qpath(root, qid)}. Answer file: {apath(root, qid)}. "
                    f"Rule per {protocol_doc_label(root)}, then reply with the verdict and commit sha."),
        "detail": "Then skip ahead (spec-maintainer-ask.sh blocked) or wait for the reply; on the reply run "
                  f"spec-maintainer-ask.sh process {qid}.",
    }


def process(root: Path, qp: Path, actor: str | None = None, extra: dict[str, Any] | None = None) -> int:
    q = read_json(qp)
    qid = q["question_id"]
    actor = actor or env_raiser() or q.get("raised_by") or RUNNER
    if actor not in ACTORS:
        actor = "system"
    result: dict[str, Any] = dict(extra or {})
    result.setdefault("question_id", qid)

    # Answer already present (lead wrote it, operator rewrite, earlier call wrote it)?
    ans, errs = load_answer(root, qid)
    if ans is not None:
        if q.get("status") == "open" or (q.get("status") == "escalated" and ans["verdict"] != "needs_operator"):
            result.update(act_on_answer(root, qp, q, ans, actor))
            result["outcome"] = "answered"
            return out(result)
        if q.get("status") == "answered":
            leftover = waiting_for(root, q, ("spec_maintainer", "operator_decision", "steerer"))
            if leftover:
                result.update(act_on_answer(root, qp, q, ans, actor))
            result["outcome"] = "already_answered"
            return out(result)
        result["outcome"] = "escalated_waiting_on_operator"
        return out(result)
    if q.get("status") != "open":
        result["outcome"] = f"nothing_to_do_status_{q.get('status')}"
        return out(result)

    # §17: the lead answers in its own session (a question raised before 2026-11-05 for the steerer
    # or a headless maintainer is sent to the lead the same way).
    # The lead gets the message once: a question raised before (by the steerer route, a headless call
    # that died mid-flight, or a lock or quota queue) carries no lead_messaged_at and is sent now; its
    # tasks' old steerer or quota wait becomes the spec-maintainer wait.
    result["outcome"] = "waiting_on_lead"
    if q.get("lead_messaged_at"):
        result["actions"] = [{"action": "skip_ahead", "detail": "No answer file yet: the lead has not ruled. "
                              "Continue unaffected work (spec-maintainer-ask.sh blocked) or wait for its reply."}]
        return out(result)
    result["actions"] = [lead_message_action(root, q)]
    tasks = fold_tasks(root)
    pid = q.get("project_id") or ""
    for tid in q.get("blocks") or []:
        if (tasks.get(tid) or {}).get("waiting_on") in ("steerer", "quota"):
            set_wait(root, "set", tid, "spec_maintainer", actor, pid, qid)
    q["dispatch"] = "in_call"
    q["lead_messaged_at"] = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    save_question(qp, q)
    return out(result)


def cmd_process(args: argparse.Namespace) -> int:
    root = root_dir()
    qp, _ = load_question(root, args.question)
    return process(root, qp, actor=args.actor)


def descendants(root: Path, seeds: list[str]) -> set[str]:
    """§17.7: the seeds plus every task whose `depends_on` closure holds one. The dependencies are the task
    log's (through the binding's product root) united with the queue's `tasks/*.json`; with no product root,
    or a plane.json that cannot be read, the queue's alone."""
    from ccp import graph, tasklog  # noqa: PLC0415
    deps: dict[str, list[str]] = {}

    def add(tid: str, ds: Any) -> None:
        ds = ds if isinstance(ds, list) else ([] if ds in (None, "") else [ds])
        deps[tid] = list(dict.fromkeys([*deps.get(tid, []), *(str(d) for d in ds)]))

    tdir = root / "tasks"
    if tdir.is_dir():
        for p in tdir.glob("*.json"):
            try:
                t = read_json(p)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(t, dict):
                add(str(t.get("task_id") or p.stem), t.get("depends_on"))
    cfg = product_config(root)
    if cfg is not None:
        try:
            log = tasklog.load(cfg)
        except (OSError, ValueError):
            log = []
        for t in log:
            add(str(t.get("task_id") or t["_file"].stem), t.get("depends_on"))
    want = set(seeds)
    return want | {tid for tid in deps if graph.closure(deps, tid) & want}


def cmd_blocked(args: argparse.Namespace) -> int:
    from ccp.queue import open_questions  # noqa: PLC0415  (the open-question rule, §17)
    root = root_dir()
    by_q = {}
    allb: set[str] = set()
    for q in open_questions(root):
        d = descendants(root, list(q.get("blocks") or []))
        by_q[q["question_id"]] = {"blocks": q.get("blocks"), "descendants": sorted(d - set(q.get("blocks") or []))}
        allb |= d
    obj: dict[str, Any] = {"blocked": sorted(allb), "by_question": by_q}
    if args.task_id:
        obj = {"task_id": args.task_id, "blocked": args.task_id in allb, "by_question": by_q}
    return out(obj)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Spec questions (SPEC §17): raise, process, blocked")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("raise")
    r.add_argument("--task-id", required=True)
    r.add_argument("--text", required=True)
    r.add_argument("--inconsistency", required=True)
    r.add_argument("--spec-refs", default="[]")
    r.add_argument("--tried", default="")
    r.add_argument("--blocks", default="")
    r.add_argument("--raised-by", default=None)
    r.set_defaults(fn=cmd_raise)
    p = sub.add_parser("process")
    p.add_argument("question")
    p.add_argument("--actor", default=None)
    p.set_defaults(fn=cmd_process)
    b = sub.add_parser("blocked")
    b.add_argument("--task-id", default=None)
    b.set_defaults(fn=cmd_blocked)
    args = ap.parse_args(argv)
    return int(args.fn(args) or 0)

if __name__ == "__main__":
    raise SystemExit(main())
