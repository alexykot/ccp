"""Live seats (SPEC §28.1 *Now*, §2.4 *Models and effort*): who is working right now, on which
model and effort, against what the plane pins.

One row per live seat of the Claude team: the design seat (the lead), the runner (the binding's
`runner` teammate), each open worker run (pending, running or stopped, with its phase), each
headless pass in progress (architect, docs audit, the estimator), and any other telemetry seat
seen in the last WINDOW_MINUTES (a teammate, or a seat the receiver adds).

Expected (pinned) values come from the pins in effect: a run's record (what `ccp prompt` read from
the definition), else the agent definition (`runs.definition`: the product's `.claude/agents` copy
while it has one, else the plugin's); the binding's runner agent type's definition; the product's
`telemetry.design_seat` (advisory, §24); the headless reviewers' `--model`/`--effort`
(`architecture_review.HEADLESS_MODEL`); the estimator's (`estimator.HEADLESS_MODEL`, §26.3).

Observed values come from `ccp usage`'s fold (`recent`): the requests attributed to that run or
seat, less those of sessions the plane launched headless (tagged, or in headless-usage.jsonl) on
the lead's and the runner's rows. Of its requests in the WINDOW_MINUTES up to its latest one, the model with the most tokens
(so a helper call on a small model does not hide the main loop), and the effort of the latest
request on it. Without any request the row says "no telemetry yet", never a guess.

Read-only: it reads the queue, the binding, the definitions and git refs, and writes nothing.
"""
from __future__ import annotations

from ccp.queue import events_path as _events_path

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import runs
from ccp.config import Config
from ccp.queue import read_json
from ccp.usage import UNTAGGED  # the fold's seat for `claude -p` rows with no tag and no placement

WINDOW_MINUTES = 30
NO_TELEMETRY = "no telemetry yet"
QUIET_AFTER_MINUTES = 120  # a live seat with no activity this long is flagged "quiet"
QUIET = {("seat", "heartbeat"), ("allowance", "sample")}  # ledger events that change no state


def _t(s: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


# ------------------------------------------------------------------------------------- expected

def _rel(cfg: Config, f: Path | None) -> str | None:
    if f is None:
        return None
    from ccp.queue import PLANE  # noqa: PLC0415
    for base, label in ((cfg.root, ""), (PLANE, "plane:")):
        try:
            return label + str(f.resolve().relative_to(Path(base).resolve()))
        except ValueError:
            continue
    return str(f)


def definition_pins(cfg: Config, agent_type: str) -> dict[str, Any]:
    """The model and effort an agent type's definition in effect pins, and which file that is."""
    agent_type = runs.unscoped(agent_type or "")
    if not agent_type:
        return {"model": None, "effort": None, "source": "unknown agent type"}
    launched, f = runs.definition(cfg, agent_type)
    model, effort = runs.expected(cfg, agent_type)
    where = "product copy" if not launched.startswith(runs.PLUGIN + ":") else "plugin"
    return {"model": model, "effort": effort,
            "source": f"{_rel(cfg, f)} ({where})" if f else f"no definition of {agent_type} found"}


def headless_pins() -> dict[str, Any]:
    from ccp import architect  # noqa: PLC0415  (imports the review kit: architecture_review)
    flags = list(architect.ar.HEADLESS_MODEL)
    pick = lambda k: flags[flags.index(k) + 1] if k in flags and flags.index(k) + 1 < len(flags) else None  # noqa: E731
    return {"model": pick("--model"), "effort": pick("--effort"),
            "source": "scripts/observability/architecture_review.py HEADLESS_MODEL (claude -p flags)"}


def _binding_block(text: str, key: str) -> dict[str, str]:
    """A flat `key:` block of the binding (indented `name: value` lines), comments dropped."""
    m = re.search(rf"^{re.escape(key)}:[ \t]*\n((?:[ \t]+.*\n|[ \t]*\n)*)", text + "\n", re.M)
    out: dict[str, str] = {}
    for line in (m.group(1) if m else "").splitlines():
        line = line.split("#", 1)[0].rstrip()
        if ":" in line and line.strip():
            k, _, v = line.strip().partition(":")
            if v.strip():
                out[k.strip()] = v.strip().strip("'\"")
    return out


# ------------------------------------------------------------------------------------- observed

def observed(reqs: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """The seat's model and effort from its latest requests, or None without any."""
    reqs = [r for r in reqs or [] if _t(r.get("at")) is not None]
    if not reqs:
        return None
    last = max(_t(r["at"]) for r in reqs)
    window = [r for r in reqs if _t(r["at"]) >= last - WINDOW_MINUTES * 60]
    by_model: dict[str, int] = {}
    for r in window:
        if r.get("model"):
            by_model[str(r["model"])] = by_model.get(str(r["model"]), 0) + int(r.get("tokens") or 0) + 1
    main = max(by_model, key=lambda m: by_model[m]) if by_model else None
    on_main = [r for r in window if str(r.get("model")) == main] if main else window
    latest = max(on_main, key=lambda r: _t(r["at"]))
    return {"model": main, "effort": latest.get("effort"), "at": max(window, key=lambda r: _t(r["at"]))["at"],
            "requests": len(window), "other_models": sorted(m for m in by_model if m != main)}


def _bare(model: Any) -> str:
    return re.sub(r"\[[^\]]*\]$", "", str(model))


def mismatch(exp: dict[str, Any], obs: dict[str, Any] | None, prefix: bool = False) -> list[str]:
    """What differs between the pins and what was observed; [] when in step or nothing to compare.
    `prefix`: the design seat, whose model may carry a context suffix such as `[1m]` (§24.5 advice):
    the ids are compared with any `[...]` suffix stripped on both sides."""
    if not obs:
        return []
    out = []
    m, em = obs.get("model"), exp.get("model")
    if m and em and not (_bare(m) == _bare(em) if prefix else m == em):
        out.append(f"model {m}, pinned {em}")
    if obs.get("effort") and exp.get("effort") and obs["effort"] != exp["effort"]:
        out.append(f"effort {obs['effort']}, pinned {exp['effort']}")
    return out


# ------------------------------------------------------------------------------------- ledger

def _events(q: Path) -> list[dict[str, Any]]:
    import json  # noqa: PLC0415
    p = _events_path(q)
    out = []
    for line in p.read_text(errors="replace").splitlines() if p.is_file() else []:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _last_event(events: list[dict[str, Any]], actor: str | None = None,
                state_changing: bool = False) -> dict[str, Any] | None:
    for e in reversed(events):
        if actor and e.get("actor") != actor:
            continue
        if state_changing and (e.get("type"), e.get("op")) in QUIET:
            continue
        return {"at": e.get("at"), "what": f"{e.get('type')} {e.get('op')}", "actor": e.get("actor"),
                "task_id": e.get("task_id") or None}
    return None


# ------------------------------------------------------------------------------------- rows

def _row(team: str, seat: str, kind: str, status: str, since: Any, exp: dict[str, Any],
         obs: dict[str, Any] | None, last: dict[str, Any] | None, *, advisory: bool = False,
         prefix: bool = False, notes: list[str] | None = None) -> dict[str, Any]:
    diff = mismatch(exp, obs, prefix)
    return {"team": team, "seat": seat, "kind": kind, "status": status, "since": since,
            "expected": {"model": exp.get("model"), "effort": exp.get("effort"), "source": exp.get("source"),
                         "advisory": advisory},
            "observed": ({"model": obs["model"], "effort": obs.get("effort"), "at": obs["at"],
                          "requests": obs["requests"], "other_models": obs["other_models"]} if obs else None),
            "observed_note": None if obs else NO_TELEMETRY,
            "mismatch": diff, "last_activity": last, "notes": notes or [], "stale": None}


def _activity(obs: dict[str, Any] | None, fallback: dict[str, Any] | None) -> dict[str, Any] | None:
    if obs:
        return {"at": obs["at"], "source": "telemetry"}
    return fallback


def _ev_activity(e: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"at": e["at"], "source": f"ledger: {e['what']}"} if e else None


def collect(cfg: Config, q: Path, report: dict[str, Any], work: dict[str, Any]) -> dict[str, Any]:
    from ccp.queue import binding_text  # noqa: PLC0415
    text = binding_text(q)
    team = "claude-team"
    recent = report.get("recent") or {"runs": {}, "seats": {}}
    events = _events(q)
    out: dict[str, Any] = {"team": team, "window_minutes": WINDOW_MINUTES,
                           "telemetry": bool(report.get("total", {}).get("requests")), "rows": []}
    rows = out["rows"]
    now = _now()
    tel = cfg.telemetry or {}
    ds = tel.get("design_seat") or {}
    # A headless session the plane launched (tagged with its seat, or named in headless-usage.jsonl)
    # is never the lead or the runner, whichever bucket a row of it landed in: set it aside there.
    headless_sids = {str(h.get("session_id")) for h in report.get("headless") or [] if h.get("session_id")}
    headless_sids |= {str(x.get("session_id")) for k, v in recent["seats"].items() if _tagged(k)
                      for x in v if x.get("session_id")}
    lead_reqs, lead_aside = _split(recent["seats"].get("design-seat"), headless_sids)
    lead_obs = observed(lead_reqs)
    active = lead_obs and (_t(lead_obs["at"]) or 0) >= now - WINDOW_MINUTES * 60
    notes = []
    if lead_aside:
        notes.append(f"{len(lead_aside)} request(s) of headless sessions set aside")
    untagged = observed(recent["seats"].get(UNTAGGED))
    if untagged and (_t(untagged["at"]) or 0) >= now - WINDOW_MINUTES * 60:
        notes.append(f"{len(recent['seats'][UNTAGGED])} untagged headless request(s) set aside "
                     f"(seat {UNTAGGED}), latest {untagged['at']}")
    rows.append(_row(team, "design seat", "lead", "active" if active else "idle" if lead_obs else "live team lead",
                     None,
                     {"model": ds.get("model"), "effort": ds.get("effort"),
                      "source": "docs/delivery/plane.json telemetry.design_seat (advisory, §24.5)" if ds
                      else "not set: telemetry.design_seat in docs/delivery/plane.json"},
                     lead_obs, _activity(lead_obs, _ev_activity(_last_event(events, "design-seat"))),
                     advisory=True, prefix=True, notes=notes))

    rb = _binding_block(text, "runner")
    rname = work.get("runner") or rb.get("name") or "runner"  # §10.2: the bound name after a rotation
    rexp = definition_pins(cfg, rb.get("agent_type") or "delivery-runner")
    r_reqs, r_aside = _split(recent["seats"].get("runner"), headless_sids)
    r_obs = observed(r_reqs)
    rstat = str(work.get("status") or "not running")
    slots = work.get("runners") if isinstance(work.get("runners"), dict) else {}
    if slots:  # §16.7: a row per runner slot, with the task it holds; telemetry is the runner seat, all slots
        from ccp.queue import load_task_state  # noqa: PLC0415
        first = sorted(slots)[0]
        for i, (slot, rec) in enumerate(sorted(slots.items())):
            rec = rec if isinstance(rec, dict) else {}
            held = [str(t) for t in work.get("in_flight") or [] if load_task_state(q, str(t)).get("lease_holder") == slot]
            phase = load_task_state(q, held[0]).get("status") if held else None
            bound = str(rec.get("bound_name") or slot)
            note = ([f"{len(r_aside)} request(s) of headless sessions set aside"] if r_aside and i == 0 else []) \
                + (["observed: every runner slot together (the runner seat)"] if i == 0 else [])
            row = _row(team, f"runner {slot}" + (f" ({bound})" if bound != slot else ""), "teammate",
                       f"{rstat} · {held[0]} {phase or ''}".strip() if held else f"{rstat} · no task",
                       rec.get("spawned_at") if work.get("status") in ("running", "draining") else work.get("updated_at"),
                       rexp, r_obs if i == 0 else None,
                       _activity(r_obs, _ev_activity(_last_event(events, "task-runner"))) if i == 0 else None,
                       notes=note or None)
            if i:
                row["observed_note"] = f"on the runner {first} row (every slot together)"
            rows.append(row)
        orphans = [str(t) for t in work.get("in_flight") or []
                   if (h := load_task_state(q, str(t)).get("lease_holder")) and h not in slots
                   and load_task_state(q, str(t)).get("status") != "done"]
        if orphans and rows:
            rows[-1]["notes"] = rows[-1]["notes"] + [f"held by no runner slot: {', '.join(orphans)} "
                                                     "(release it, or respawn its runner; SPEC §16.5)"]
    else:
        rows.append(_row(team, "runner" if rname == "runner" else f"runner ({rname})", "teammate", rstat,
                         work.get("runner_spawned_at") if work.get("status") in ("running", "draining") else work.get("updated_at"),
                         rexp, r_obs, _activity(r_obs, _ev_activity(_last_event(events, "task-runner"))),
                         notes=[f"{len(r_aside)} request(s) of headless sessions set aside"] if r_aside else None))

    for r in runs.open_on_live_tasks(q, cfg):  # §11.1: a done or dropped task's runs are not seats
        st = runs.state(r)
        if r.get("expected_model") or r.get("expected_effort"):
            exp = {"model": r.get("expected_model"), "effort": r.get("expected_effort"),
                   "source": f"run record (pinned by ccp prompt from {r.get('agent_type')})"}
        else:
            exp = definition_pins(cfg, str(r.get("agent_type") or runs.AGENT_TYPE.get(str(r.get("phase")), "")))
        obs = observed(recent["runs"].get(r["run_id"]))
        stamps = [x for x in (r.get("stopped_at"), r.get("started_at"), r.get("opened_at")) if _t(x)]
        fallback = {"at": max(stamps, key=_t), "source": "run record"} if stamps else None
        rows.append(_row(team, f"{r.get('seat') or 'worker'} {r['run_id']}", "worker", f"{st} · {r.get('phase')}",
                         r.get("started_at") or r.get("opened_at"), exp, obs, _activity(obs, fallback)))

    headless, claimed = _headless(q, team, recent, now)
    rows += headless

    # `other-sessions` aggregates every session outside the seats (§24): not one seat, not a row.
    known = {"design-seat", "runner", *runs.SEAT.values(), "worker", "other-sessions", UNTAGGED, *claimed}
    for seat, reqs in sorted(recent["seats"].items()):
        if seat in known:
            continue
        obs = observed(reqs)
        if obs and (_t(obs["at"]) or 0) >= now - WINDOW_MINUTES * 60:
            resumed = seat == "spec-maintainer" or seat.endswith("-triage")
            rows.append(_row(team, seat, "telemetry", "active", None, {"source": "not pinned by the plane"},
                             obs, _activity(obs, None),
                             notes=["resumes the spec maintainer's session, which keeps its own model and effort "
                                    "(§2.4)" if resumed else "a seat the plane pins no model or effort for"]))
    for row in rows:
        row["stale"] = row.get("stale") or _quiet(row.get("last_activity"), now)
    return out


def _tagged(seat: str) -> bool:
    """A seat the receiver tagged from a plane-launched `claude -p` (§24), not an interactive one."""
    return not (seat in ("design-seat", "runner", "other-sessions", "worker", UNTAGGED)
                or seat in runs.SEAT.values() or seat.startswith("teammate:"))


def _split(reqs: list[dict[str, Any]] | None, sids: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reqs = reqs or []
    aside = [r for r in reqs if r.get("session_id") and str(r["session_id"]) in sids]
    return [r for r in reqs if r not in aside], aside


def _quiet(last: dict[str, Any] | None, now: float) -> str | None:
    t = _t((last or {}).get("at"))
    if t is None or now - t < QUIET_AFTER_MINUTES * 60:
        return None
    return f"quiet {(now - t) / 3600:.0f} h"


def _lock_alive(q: Path, lock_name: str, rid: str) -> bool:
    """The read-only half of architect._reap: the pass's lock names it and is not stale (§11.2)."""
    from ccp import architect  # noqa: PLC0415
    cur = read_json(q / lock_name, {}) or {}
    return isinstance(cur, dict) and cur.get("review_id") == rid and not architect.sm.lock_is_stale(cur)


def _headless(q: Path, team: str, recent: dict[str, Any], now: float) -> tuple[list[dict[str, Any]], set[str]]:
    """Architect passes and docs audits recorded as running (read only: the board never reaps), and
    the telemetry seats they claim: the `ccp.seat` tag a plane-launched `claude -p` carries
    (`architect-<mode>`, `docs-audit`; §24). A pass whose lock is gone or stale past the reaper's
    grace is flagged "lock gone"."""
    from ccp import architect  # noqa: PLC0415
    rows, claimed = [], set()
    exp = None
    for state, lock_name, label, tag in (("architect.json", "architect.lock", "architect", "architect-{mode}"),
                                         ("docs-audit.json", "docs-audit.lock", "docs audit", "docs-audit")):
        st = read_json(q / state, {}) or {}
        reviews = st.get("reviews") if isinstance(st, dict) else None
        for rid, rec in sorted((reviews or {}).items()) if isinstance(reviews, dict) else []:
            if not isinstance(rec, dict) or rec.get("status") != "running":
                continue
            exp = exp or headless_pins()
            mode = str(rec.get("mode") or "pass")
            seat = tag.format(mode=mode)
            claimed.add(seat)
            obs = observed(recent["seats"].get(seat))
            row = _row(team, f"{label} {mode} {rid}", "headless", "running", rec.get("started_at"), exp, obs,
                       _activity(obs, {"at": rec.get("started_at"), "source": state} if rec.get("started_at") else None))
            start = _t(rec.get("started_at"))
            if not _lock_alive(q, lock_name, rid) and (start is None or now - start > architect.STALE_AFTER_S):
                row["stale"] = "lock gone"
            rows.append(row)
    # §26.3: the estimator seat, while a batch holds its lock (its telemetry tag is `estimator`).
    from ccp import estimator  # noqa: PLC0415
    claimed.add(estimator.SEAT)
    cur = estimator.running(q)
    if cur:
        obs = observed(recent["seats"].get(estimator.SEAT))
        rows.append(_row(team, f"estimator {cur.get('review_id')}" + (f" · {cur['task_id']}" if cur.get("task_id") else ""),
                         "headless", "running", cur.get("since"), estimator.pins(), obs,
                         _activity(obs, {"at": cur.get("task_since") or cur.get("since"), "source": estimator.LOCK})))
    return rows, claimed


# ------------------------------------------------------------------------------------- text

def _mo(m: Any, e: Any) -> str:
    return f"{m or '?'} / {e or '?'}"


def status_lines(s: dict[str, Any] | None) -> list[str]:
    if not s:
        return []
    if s.get("error"):
        return [f"seats failed: {s['error']}"]
    out = []
    for r in s.get("rows") or []:
        e, o = r["expected"], r["observed"]
        obs = _mo(o["model"], o["effort"]) if o else r["observed_note"]
        flag = ("ADVICE " if e.get("advisory") else "MISMATCH ") + "; ".join(r["mismatch"]) if r["mismatch"] \
            else ("ok" if o and (e.get("model") or e.get("effort")) else "-")
        last = (r.get("last_activity") or {}).get("at") or "-"
        out.append(f"seat {r['team']:<11} {r['seat']:<40} {r['status']} since {r.get('since') or '-'}  "
                   f"pinned {_mo(e.get('model'), e.get('effort'))}  observed {obs}  last {last}  [{flag}]"
                   + (f"  STALE: {r['stale']}" if r.get("stale") else "")
                   + "".join(f"  ({n})" for n in r.get("notes") or []))
    return out
