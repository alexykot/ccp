"""The ledger and usage rows the tests share: events, suite rows, usage requests and run records. Holds no tests."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

T0 = 1_800_000_000 * 10**9  # 2027-01-15, in nanoseconds: the epoch the usage tests' times count from


class FoldRuns:
    """Mixin for a `TestCase` whose `self.q` is a temp queue: `mkrun` writes a run record (`start` and `stop`
    seconds from `T0`), `write` appends rows to a board file and `rows` makes usage-request rows (a `t` in
    seconds from `T0`)."""

    def mkrun(self, rid, seat, model, effort, agent, start, stop):
        f = lambda s: datetime.fromtimestamp(T0 / 1e9 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        task, phase = rid.split("/")
        p = self.q / "runs" / task / f"{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"run_id": rid, "task_id": task, "phase": phase, "seat": seat, "agent_type": f"delivery-{seat}",
                                 "expected_model": model, "expected_effort": effort, "agent_id": agent,
                                 "opened_at": f(start), "started_at": f(start), "stopped_at": f(stop)}))

    def write(self, name, rows):
        with (self.q / "board" / name).open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def rows(self, *rs):
        from ccp import otel  # noqa: PLC0415
        out = []
        for r in rs:
            r = dict(r)
            t = r.pop("t")
            out.append({k.replace("__", "_"): v for k, v in r.items()} | {"at": otel._iso(t)})
        return out


def ledger_event(at: str, typ: str, op: str, payload: dict, task_id: str = "") -> dict:
    from ccp.queue import lib  # noqa: PLC0415
    return {"at": at, "project_id": "demo", "task_id": task_id, "actor": lib.LEAD, "type": typ, "op": op,
            "payload": payload}


def spawn_event(at: str, rp: str, scope: list[str]) -> dict:
    return ledger_event(at, "runner", "spawn", {"name": "runner", "scope": scope, "review_point": rp})


def lease_event(at: str, tid: str) -> dict:
    return ledger_event(at, "lease", "set", {"holder": "runner"}, tid)


def epoch_iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def good_then_failed(q: Path, resets_in_s: float) -> dict:
    """The product's samples: a good reading two hours old, weekly at 95% with its reset `resets_in_s` from now,
    then a failed read a minute ago (§25.1: the unknown sample, no figures). Returns the good row."""
    t = time.time()
    resets = epoch_iso(t + resets_in_s)
    good = {"at": epoch_iso(t - 7200), "five_hour": 10, "seven_day": 95, "resets_at": resets, "five_hour_resets_at": None,
            "windows": [{"name": "seven_day", "pct": 95, "resets_at": resets}, {"name": "five_hour", "pct": 10, "resets_at": None}],
            "weekly_window": "seven_day", "session_window": "five_hour"}
    failed = {"at": epoch_iso(t - 60), "five_hour": None, "seven_day": None, "resets_at": None, "five_hour_resets_at": None,
              "windows": [], "failed": True, "exit": 1}
    (q / "board").mkdir(exist_ok=True)
    (q / "board" / "allowance.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (good, failed)))
    return good


SUITE_RUN_ID = "0002-second/verify"


def suite_started(sid, lane="gate", at="2026-11-01T10:00:00Z"):
    return {"op": "started", "suite_id": sid, "at": at, "lane": lane, "run_id": SUITE_RUN_ID, "task_id": "0002-second",
            "phase": "verify"}


def suite_ended(sid, seconds, code=0, tests=900, cached=None, stages=None, at="2026-11-01T10:20:00Z"):
    row = {"op": "ended", "suite_id": sid, "at": at, "exit_code": code, "seconds": seconds, "tests": tests,
           "failed": None, "skipped": None, "ran": None, "cached": cached, "interrupted": None}
    if stages is not None:
        row.update(stages=[{"name": n, "seconds": s, "exit_code": 0} for n, s in stages], failed_stage=None)
    return row


def api_request(rid, t, model="claude-opus-5-5", effort="high", source="agent:custom", out=100, **more):
    return {"t": T0 + t * 10**9, "event__name": "api_request", "request_id": rid, "model": model, "effort": effort,
            "query_source": source, "input_tokens": 2, "output_tokens": out, "cache_read_tokens": 1000,
            "cache_creation_tokens": 10, "cost_usd": 0.01, "session__id": "s1", **more}


ADVICE_SPANS = {"lead": {}, "runner": {"agent_id": "runner@session-abc"}, "worker": {"agent_id": "a1"}}


def advice_row(rid, who, ctx=None, cost=0.01, written=0, five=0, model="claude-opus-5-5", session="s1",
               at="2027-01-15T08:00:00Z"):
    """One request of `who` (lead, runner or worker) on `model` in `session` at `at`, sending `ctx` context
    tokens (default: the writes and a thousand more), `written` of them cache writes, `five` of those at 5
    minutes."""
    ctx = written + 1000 if ctx is None else ctx
    return ({"request_id": rid, "at": at, "session_id": session, "model": model,
             "effort": "high", "query_source": "repl_main_thread" if who == "lead" else "agent:custom",
             "input_tokens": 1, "output_tokens": 10, "cache_read_tokens": ctx - 1 - written,
             "cache_creation_tokens": written, "cache_creation_5m_tokens": five,
             "cache_creation_1h_tokens": written - five, "cost_usd": cost},
            {"request_id": rid, **ADVICE_SPANS[who]})
