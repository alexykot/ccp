"""The seats tab's base fixture: a product with a design seat and its request rows. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests.toolkit_fixture import ToolkitFixture


def at(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class SeatsBase(ToolkitFixture):
    def design_seat(self, model="claude-opus-5-5", effort="xhigh"):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "telemetry": {"design_seat": {"model": model, "effort": effort}}}))

    def requests(self, *rows, spans=()):
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        (b / "usage-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        if spans:
            (b / "usage-spans.jsonl").write_text("".join(json.dumps(s) + "\n" for s in spans))

    def build(self):
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text())

    def rows(self, b):
        return {r["seat"]: r for r in b["now"]["seats"]["rows"]}

    def open_implement(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        return "0002-second/implement"


def req(rid, minutes_ago, model, effort, out=100, **extra):
    return {"request_id": rid, "at": at(minutes_ago), "model": model, "effort": effort, "input_tokens": 10,
            "output_tokens": out, "cache_read_tokens": 0, "cache_creation_tokens": 0, "cost_usd": 0.01, **extra}
