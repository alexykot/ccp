"""Notifying the operator (SPEC §3.6, §17.10): when, by the plane; how, by the product's `notify` block.

The plane names four triggers on which the operator must hear: a `blocker` (a wait only the operator
clears: `reauth`, `operator_step`), a `decision` (a wait on `operator_decision`: a gate taken to the
operator, a spec question answered `needs_operator`), `review_point_done` (a close that leaves its
review point with no open task) and `allowance_checkpoint` (a claim refused at the weekly checkpoint).

plane.json `notify.command` names the channel: a shell command run in the product root on each
trigger, given the trigger and ids only in its environment (`CCP_NOTIFY_TRIGGER`, `CCP_PROJECT_ID`,
`CCP_TASK_ID`, `CCP_NOTIFY_ID`, `CCP_NOTIFY_REASON`, and all of them as one line, `CCP_NOTIFY_LINE`).
Null, the default, is the lead's session: no command runs, and the lead raises it there as before.
Sending is best effort: a command that fails or overruns `notify.timeout_seconds` is a warning on the
step, never a refusal, and the step itself has already happened.
"""
from __future__ import annotations

from typing import Any

from ccp.config import Config
from ccp.envvars import for_child

TRIGGERS = ("blocker", "decision", "review_point_done", "allowance_checkpoint")
# §3.6: the waits that are the operator's to clear; every other wait is the lead's or the plane's
BLOCKER_WAITS = ("reauth", "operator_step")
DECISION_WAITS = ("operator_decision",)


def trigger_for_wait(reason: str) -> str | None:
    """The trigger a wait set with this reason fires, or None for a wait the operator is not told of."""
    if reason in DECISION_WAITS:
        return "decision"
    if reason in BLOCKER_WAITS:
        return "blocker"
    return None


def channel(cfg: Config) -> str | None:
    """The product's notify command, or None for the lead's session."""
    return (cfg.notify or {}).get("command") or None


def line(trigger: str, project_id: str, task_id: str = "", ident: str = "", reason: str = "") -> str:
    """The one line a command may pass on as it is: the trigger, then each id that is set."""
    parts = [trigger, f"project={project_id}"]
    parts += [f"{k}={v}" for k, v in (("task", task_id), ("id", ident), ("reason", reason)) if v]
    return " ".join(parts)


def send(cfg: Config, trigger: str, task_id: str = "", ident: str = "", reason: str = "") -> dict[str, Any] | None:
    """Run the channel command for one trigger. None when the product names no channel (nothing runs);
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
        code, _ = wt.run_cmd(cmd, cfg.root, timeout, env)
    except OSError as exc:
        return {"trigger": trigger, "exit": None, "warning": f"notify: the {trigger} command could not start ({exc})"}
    out: dict[str, Any] = {"trigger": trigger, "exit": code}
    if code == 124:
        out["warning"] = f"notify: the {trigger} command timed out after {timeout} s; raise it in the lead's session"
    elif code != 0:
        out["warning"] = f"notify: the {trigger} command exited {code}; raise it in the lead's session"
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
