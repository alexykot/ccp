"""A run in flight with telemetry and suites, for the board's drill-down tests and the estimate page. A fixture
module: it holds no tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from tests.board_quality_fixture import Base


T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc).timestamp()  # in the past: an open task runs to now


def at(s: float) -> str:
    """T0 + s as the RFC3339 the plane writes (with a fraction, as the telemetry does)."""
    return datetime.fromtimestamp(T0 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def at_s(s: float) -> str:
    return datetime.fromtimestamp(T0 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Fixture(Base):
    """A run of 0002-second with telemetry and suites, in flight."""

    def seed(self, n_requests: int = 3, note: str = "suite runs took long", wait: str = "spec_maintainer"):
        rid = "0002-second/implement"
        d = self.q / "runs" / "0002-second"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({
            "schema_version": 1, "run_id": rid, "task_id": "0002-second", "phase": "implement", "round": 1,
            "seat": "implementer", "agent_type": "delivery-implementer", "expected_model": "claude-opus-5-5",
            "expected_effort": "high", "opened_at": at_s(0), "agent_id": "agent-1", "started_at": at_s(10),
            "stopped_at": at_s(2000), "reported_at": at_s(1990), "outcome": "done"}))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "task_id": "0002-second", "phase": "implementing"}))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({
            "task_id": "0002-second", "status": "implementing", "claimed_at": at_s(0), "depends_on": ["0001-first"]}))
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        with (b / "usage-requests.jsonl").open("w") as rq, (b / "usage-spans.jsonl").open("w") as sp:
            # requests every 5 s from 10 s, 3 s each; then nothing from the last one to 2000 s
            for i in range(n_requests):
                a = 10 + 5 * i
                rq.write(json.dumps({"at": at(a + 3), "request_id": f"r{i}", "model": "claude-opus-5-5", "effort": "high",
                                     "query_source": "agent:custom", "input_tokens": 1, "output_tokens": 2,
                                     "cache_read_tokens": 3, "cache_creation_tokens": 4, "cost_usd": 0.01,
                                     "duration_ms": 3000}) + "\n")
                sp.write(json.dumps({"at": at(a), "end": at(a + 3), "request_id": f"r{i}", "agent_id": "agent-1",
                                     "model": "claude-opus-5-5", "effort": "high"}) + "\n")
        with (self.q / "runs" / "_suites.jsonl").open("w") as fh:
            fh.write(json.dumps({"op": "started", "suite_id": "st-1", "at": at_s(100), "lane": "full", "cmd": "unit.sh",
                                 "argc": 0, "run_id": rid, "task_id": "0002-second", "phase": "implement"}) + "\n")
            fh.write(json.dumps({"op": "ended", "suite_id": "st-1", "at": at_s(400), "exit_code": 0, "seconds": 300,
                                 "tests": 12, "interrupted": None}) + "\n")
        ev = self.q / "observability" / "events.jsonl"
        ev.parent.mkdir(exist_ok=True)
        with ev.open("a") as fh:
            for e in ({"type": "lease", "op": "set", "at": at_s(0), "payload": {"holder": "runner"}},
                      {"type": "waiting_on", "op": "set", "at": at_s(500), "payload": {"reason": wait, "detail": "sm-1"}},
                      {"type": "waiting_on", "op": "clear", "at": at_s(800), "payload": {"reason": "spec_resolved", "was": wait}}):
                fh.write(json.dumps({"project_id": "demo", "task_id": "0002-second", "actor": "task-runner", **e}) + "\n")
        self.note(at_s(1990), "implementer", note)
        return rid


HASH_STUB = """
const out = [], panel = [];
const el = (id) => ({style: {}, dataset: {}, hidden: true, addEventListener() {}, append(x) { out.push(x); }, setAttribute() {},
  querySelectorAll: () => [], set innerHTML(h) { if (id === "drill") panel.push(h); }, get innerHTML() { return ""; }});
globalThis.document = {createElement: () => { const t = {set innerHTML(h) { this.content = h; }}; return t; },
  getElementById: (id) => el(id), querySelectorAll: () => [], documentElement: el()};
globalThis.localStorage = {getItem: () => null, setItem() {}};
globalThis.matchMedia = () => ({matches: false});
globalThis.innerWidth = 800; globalThis.innerHeight = 800; globalThis.setTimeout = () => 0;
globalThis.history = {replaceState() {}};
"""
