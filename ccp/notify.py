"""Notifying the operator (SPEC §3.6, §17.10): the plane owns the trigger, the content and the record;
the lead dispatches; the channel is the product's `notify` block.

The plane names four triggers on which the operator must hear: a `blocker` (a wait only the operator
clears: `reauth`, `operator_step`), a `decision` (a wait on `operator_decision`: a gate taken to the
operator, a spec question answered `needs_operator`), `review_point_done` (a close that leaves its
review point with no open task) and `allowance_checkpoint` (a claim refused at the weekly checkpoint).
A notice the lead sends on its own judgment is trigger `other`.

When a trigger fires (`fire`), `ccp` writes a `notify` `pending` event to the ledger and prints the
rendered notice on stderr with the channel to use. plane.json `notify.command` is the unattended
channel: a shell command run, with an empty stdin, in the checkout the call came from (as reconcile
hooks are; for a gate or a spec question, the binding's product root), given the trigger and ids only
in its environment (`CCP_NOTIFY_TRIGGER`, `CCP_PROJECT_ID`, `CCP_TASK_ID`, `CCP_NOTIFY_ID`,
`CCP_NOTIFY_REASON`, and all of them as one line, `CCP_NOTIFY_LINE`); `ccp` records its send as a
`notify` `sent` event, `via: command`, `ok` false when it failed or timed out. Sending is best effort:
a failure is a warning on the step, never a refusal, and the step itself has already happened.
`notify.lead` (`{tool, to}`) declares that the lead sends with that tool from its own session: it
renders the notice (`render`), sends it and records it (`record_sent`, `via: lead`). With neither,
the lead's session is the route. `pending` lists every fired notice no successful `sent` matches.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ccp.config import Config
from ccp.envvars import for_child

TRIGGERS = ("blocker", "decision", "review_point_done", "allowance_checkpoint")
# `other`: a notice the lead sends on its own judgment; never fired by the plane
RENDER_TRIGGERS = TRIGGERS + ("other",)
VIAS = ("command", "lead")
# §3.6: the waits that are the operator's to clear; every other wait is the lead's or the plane's
BLOCKER_WAITS = ("reauth", "operator_step")
DECISION_WAITS = ("operator_decision",)
NOTE_MAX = 4000  # §8.4: the `--note` limit


def trigger_for_wait(reason: str) -> str | None:
    """The trigger a wait set with this reason fires, or None for a wait the operator is not told of."""
    if reason in DECISION_WAITS:
        return "decision"
    if reason in BLOCKER_WAITS:
        return "blocker"
    return None


def channel(cfg: Config) -> str | None:
    """The product's notify command, or None when it names none."""
    return (cfg.notify or {}).get("command") or None


def lead_channel(cfg: Config) -> dict[str, str] | None:
    """The product's `notify.lead` (`{tool, to}`), or None when it declares no tool for the lead."""
    return (cfg.notify or {}).get("lead") or None


def channel_text(cfg: Config) -> str:
    """The channel to use, in one phrase: the lead's tool, else the command, else the lead's session."""
    if lead := lead_channel(cfg):
        return f"the lead sends it with {lead['tool']} to {lead['to']}"
    if channel(cfg):
        return "the product's notify command"
    return "the lead's session"


def line(trigger: str, project_id: str, task_id: str = "", ident: str = "", reason: str = "") -> str:
    """The one line a command may pass on as it is: the trigger, then each id that is set."""
    parts = [trigger, f"project={project_id}"]
    parts += [f"{k}={v}" for k, v in (("task", task_id), ("id", ident), ("reason", reason)) if v]
    return " ".join(parts)


def _one_line(name: str, value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError(f"{name} must be one line")
    if len(value) > NOTE_MAX:
        raise ValueError(f"{name} is {len(value)} characters; the limit is {NOTE_MAX}")
    return value


def render(project_id: str, trigger: str, task_id: str = "", ident: str = "", reason: str = "") -> dict[str, Any]:
    """The notice: a subject, `[<project>] <trigger>: <task or id>`, and a body of one `key: value`
    line each for project, trigger, task, id and reason, those given; and those fields. Ids and a
    short reason only: never a brief, a question's text or file content."""
    if trigger not in RENDER_TRIGGERS:
        raise ValueError(f"unknown notify trigger {trigger!r}")
    fields = {k: _one_line(k, str(v).strip()) for k, v in (("project", project_id), ("trigger", trigger),
                                                            ("task", task_id or ""), ("id", ident or ""),
                                                            ("reason", reason or "")) if str(v or "").strip()}
    head = fields.get("task") or fields.get("id")
    subject = f"[{project_id}] {trigger}" + (f": {head}" if head else "")
    return {"subject": subject, "body": "\n".join(f"{k}: {v}" for k, v in fields.items()), **fields}


def record_command(trigger: str, task_id: str = "", ident: str = "") -> str:
    """The `ccp notify sent` call that records a lead's send of this notice."""
    return " ".join(["ccp notify sent", trigger, *([f"--task {task_id}"] if task_id else []),
                     *([f"--id {ident}"] if ident else []), "--via lead"])


def send(cfg: Config, trigger: str, task_id: str = "", ident: str = "", reason: str = "") -> dict[str, Any] | None:
    """Run the channel command for one trigger. None when the product names no command (nothing runs);
    else `{trigger, exit}`, with `warning` when the command failed or timed out. Never raises on the
    command's account: the step that fired the trigger has happened either way."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown notify trigger {trigger!r}")
    cmd = channel(cfg)
    if not cmd:
        return None
    from ccp import wt  # noqa: PLC0415  (wt imports the queue; notify stays light for its callers)
    env = for_child({"CCP_NOTIFY_TRIGGER": trigger, "CCP_PROJECT_ID": cfg.project_id, "CCP_TASK_ID": task_id or "",
                     "CCP_NOTIFY_ID": ident or "", "CCP_NOTIFY_REASON": reason or "",
                     "CCP_NOTIFY_LINE": line(trigger, cfg.project_id, task_id, ident, reason)})
    timeout = int((cfg.notify or {}).get("timeout_seconds") or 30)
    try:
        # an empty stdin: a channel that reads a body (`mail`) must not wait on ccp's own
        code, _ = wt.run_cmd(cmd, cfg.root, timeout, env, no_stdin=True)
    except OSError as exc:
        return {"trigger": trigger, "exit": None, "warning": f"notify: the {trigger} command could not start ({exc})"}
    out: dict[str, Any] = {"trigger": trigger, "exit": code}
    if code == 124:
        out["warning"] = f"notify: the {trigger} command timed out after {timeout} s; raise it in the lead's session"
    elif code != 0:
        out["warning"] = f"notify: the {trigger} command exited {code}; raise it in the lead's session"
    return out


def _emit(q: Path, cfg: Config, op: str, task_id: str, payload: dict[str, Any], who: str | None) -> dict[str, Any]:
    from ccp import queue  # noqa: PLC0415  (the queue loads the ledger library)
    return queue.emit(q, cfg, task_id, "notify", op, payload, who)


def record_pending(q: Path, cfg: Config, trigger: str, task_id: str = "", ident: str = "", reason: str = "",
                   who: str | None = None) -> dict[str, Any]:
    """The `notify` `pending` event: a trigger fired."""
    return _emit(q, cfg, "pending", task_id, {"trigger": trigger, "project": cfg.project_id, "task": task_id or "",
                                              "id": ident or "", "reason": reason or ""}, who)


def record_sent(q: Path, cfg: Config, trigger: str, task_id: str = "", ident: str = "", *, via: str, ok: bool = True,
                note: str = "", who: str | None = None) -> dict[str, Any]:
    """The `notify` `sent` event: a notice sent over `via`, by the seat that ran it (`by`), `ok` false
    for a command that failed or timed out. A notice on the lead's own judgment (`other`) carries a
    one-line note; every other field is an id."""
    from ccp import queue  # noqa: PLC0415
    if trigger not in RENDER_TRIGGERS:
        raise ValueError(f"unknown notify trigger {trigger!r}")
    if via not in VIAS:
        raise ValueError(f"--via must be one of {', '.join(VIAS)}")
    note = _one_line("--note", (note or "").strip())
    if trigger == "other" and not note:
        raise ValueError("a notice on the lead's own judgment (other) needs --note: ids and a short reason, one line")
    task_id, ident = _one_line("--task", (task_id or "").strip()), _one_line("--id", (ident or "").strip())
    by = who or queue.actor("design-seat")
    payload = {"trigger": trigger, "project": cfg.project_id, "task": task_id, "id": ident, "via": via, "by": by,
               "ok": bool(ok), **({"note": note} if note else {})}
    return _emit(q, cfg, "sent", task_id, payload, by)


def fire(cfg: Config, q: Path, trigger: str, task_id: str = "", ident: str = "", reason: str = "",
         who: str | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """A trigger fired: record it `pending`, run the command channel if the product names one (and
    record its send), and print the rendered notice on stderr with the channel to use. Returns the
    command's result (None when none ran) and the step's warnings. Never raises on the notice's
    account: the step that fired it has happened either way."""
    if trigger not in TRIGGERS:
        raise ValueError(f"unknown notify trigger {trigger!r}")
    from ccp import queue  # noqa: PLC0415
    who = who or queue.actor()  # the seat whose step fired it ran the command too
    warns: list[str] = []
    try:
        record_pending(q, cfg, trigger, task_id, ident, reason, who)
    except Exception as exc:  # noqa: BLE001  (the step happened; only the record is lost)
        warns.append(f"notify: could not record the {trigger} notice ({exc}); raise it in the lead's session")
    sent = send(cfg, trigger, task_id, ident, reason)
    if sent is not None:
        warns += warnings(sent)
        try:
            record_sent(q, cfg, trigger, task_id, ident, via="command", ok=sent.get("exit") == 0, who=who)
        except Exception as exc:  # noqa: BLE001
            warns.append(f"notify: could not record the {trigger} command's send ({exc})")
    done = sent is not None and sent.get("exit") == 0
    try:
        n = render(cfg.project_id, trigger, task_id, ident, reason)
        how = "sent by the product's notify command" if done else channel_text(cfg)
        out = [f"operator notice (SPEC §3.6), channel: {how}", f"  subject: {n['subject']}",
               *(f"  {x}" for x in n["body"].splitlines())]
        if not done:
            out.append(f"  once sent, record it: {record_command(trigger, task_id, ident)}")
        print("\n".join(out), file=sys.stderr)
    except ValueError:
        pass  # an id that is not one line cannot be rendered; the record holds it
    return sent, warns


def pending(cfg: Config, q: Path) -> list[dict[str, Any]]:
    """Every notice fired and not yet sent: one per trigger, task and id, however often it fired,
    until a later `sent` event for the same trigger, task and id with `ok` true. Ledger order."""
    from ccp import queue  # noqa: PLC0415
    open_: dict[tuple[str, str, str], dict[str, Any]] = {}
    for ev in queue.lib.load_events(queue.events_path(q)):
        p = ev.get("payload")
        if ev.get("type") != "notify" or not isinstance(p, dict):
            continue
        key = (str(p.get("trigger") or ""), str(p.get("task") or ""), str(p.get("id") or ""))
        if ev.get("op") == "sent" and p.get("ok") is True:
            open_.pop(key, None)
        elif ev.get("op") == "pending":
            if key in open_:
                open_[key]["fired"] += 1
                continue
            open_[key] = {"trigger": key[0], "project": str(p.get("project") or ev.get("project_id") or ""),
                          "task": key[1], "id": key[2], "reason": str(p.get("reason") or ""),
                          "at": ev.get("at"), "fired": 1}
    out = []
    for n in open_.values():
        try:
            r = render(n["project"] or cfg.project_id, n["trigger"], n["task"], n["id"], n["reason"])
        except ValueError:
            r = {"subject": "", "body": ""}
        out.append({**n, "subject": r["subject"], "body": r["body"],
                    "record": record_command(n["trigger"], n["task"], n["id"])})
    return out


def review_point_done(cfg: Config, rp: str) -> bool:
    """Whether the task log's tasks that carry review point `rp` are all closed (done or dropped), one
    of them at least done: the close that makes this so fires `review_point_done`."""
    from ccp import tasklog  # noqa: PLC0415
    if not rp:
        return False
    statuses = [tasklog.canonical_status(t.get("status")) for t in tasklog.load(cfg)
                if str(t.get("review_point") or "") == rp]
    return "done" in statuses and all(s in ("done", "dropped") for s in statuses)


def warnings(sent: dict[str, Any] | None) -> list[str]:
    """The warning a send left, as a list to add to a command's own."""
    return [sent["warning"]] if sent and sent.get("warning") else []


# ------------------------------------------------------------------ `ccp notify`

def _task(cfg: Config, task: str | None) -> str:
    """A `--task` as the task log names it: a full id or its NNNN, resolved as `ccp tasks` does; one
    that matches no task is refused (exit 2). Empty when none is given."""
    from ccp import queue  # noqa: PLC0415
    return str(queue.task_meta(cfg, task.strip())["task_id"]) if task and task.strip() else ""


def toolkit(cfg: Config, a: argparse.Namespace) -> dict[str, Any]:
    """`ccp notify sent` and `ccp notify pending` (JSON out; QUEUE_ROOT)."""
    from ccp import queue  # noqa: PLC0415
    q = queue.root()
    if a.cmd == "pending":
        rows = pending(cfg, q)
        return {"ok": True, "channel": channel_text(cfg), "count": len(rows), "pending": rows}
    try:
        ev = record_sent(q, cfg, a.trigger, _task(cfg, a.task), a.id or "", via=a.via, ok=True, note=a.note or "")
    except ValueError as exc:
        raise queue.QueueError(str(exc), 2) from exc
    return {"ok": True, "recorded": ev.get("payload", ev)}


def cmd_render(cfg: Config, a: argparse.Namespace) -> int:
    """`ccp notify render`: the subject and the body, or both and their fields as JSON; nothing else."""
    from ccp.queue import QueueError  # noqa: PLC0415
    try:
        n = render(cfg.project_id, a.trigger, _task(cfg, a.task), a.id or "", a.reason or "")
    except (ValueError, QueueError) as exc:
        print(f"ccp notify render: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(n, indent=2, ensure_ascii=False) if a.json else f"{n['subject']}\n\n{n['body']}")
    return 0


def add_parser(sub: Any, toolkit_wrap: Any) -> None:
    """The `ccp notify` subcommands (SPEC §3.6)."""
    nt = sub.add_parser("notify", help="the operator's notices: render one, record a send, list the pending "
                                       "(SPEC §3.6)").add_subparsers(dest="cmd", required=True)
    p = nt.add_parser("render", help="the notice to send for a trigger: a subject and a body of ids, nothing else")
    p.add_argument("trigger", choices=RENDER_TRIGGERS)
    p.add_argument("--task", help="the task: its id or NNNN (a task the log does not have is refused)")
    p.add_argument("--id", help="the gate, question or review point")
    p.add_argument("--reason", help="one line: the wait's reason, or a short reason for `other`")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_render)
    p = nt.add_parser("sent", help="record a notice sent: the trigger, its ids, the channel and the seat (needs "
                                   "QUEUE_ROOT)")
    p.add_argument("trigger", choices=RENDER_TRIGGERS)
    p.add_argument("--task", help="the task: its id or NNNN (a task the log does not have is refused)")
    p.add_argument("--id", help="the gate, question or review point, as `ccp notify pending` lists it")
    p.add_argument("--via", required=True, choices=VIAS)
    p.add_argument("--note", help="one line: ids and a short reason, no content (required for `other`)")
    p.set_defaults(fn=toolkit_wrap(toolkit))
    p = nt.add_parser("pending", help="every notice fired and not yet sent (needs QUEUE_ROOT)")
    p.set_defaults(fn=toolkit_wrap(toolkit))
