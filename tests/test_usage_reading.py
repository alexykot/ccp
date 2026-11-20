"""SPEC §25.1 the shared allowance reader: one reader per machine, a reading younger than READ_TTL_S
reused, a failed read backing off (and honouring `retry_after_s`), every rule judging the latest good
reading, the unread stop (§25.3), and a refused prompt reading nothing (§25.4)."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, usage
from tests.helpers import TASK, machine_file
from tests.test_toolkit import ToolkitFixture

T0 = float(int(time.time()))


def utc(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def task(tid: str, path: str) -> str:
    text = TASK.format(tid=tid, title=tid[5:].title(), status="pending", deps="", ver="*Append-only.*")
    return text.replace("- **In:** it", f"- **In:** `{path}`\n- **Out:** `other/thing.py`")


class ReaderFixture(ToolkitFixture):
    """A product whose machine runs a stub allowance command: each run appends a line to `counter` and
    prints what the test set. Shared reads (the test-only switch unset), a temp bindings directory, and
    the reader's one clock, `usage.now`, at `self.t`."""

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(usage.UNSHARED_ENV, None)
        self.t = T0
        clock = mock.patch.object(usage, "now", lambda: self.t)
        clock.start()
        self.addCleanup(clock.stop)
        d = Path(self._tmp.name)
        self.counter, self.out, self.err, self.code = d / "counter", d / "out.json", d / "err.txt", d / "code"
        (d / "stub.sh").write_text(f"echo run >> '{self.counter}'\ncat '{self.out}'\ncat '{self.err}' >&2\n"
                                   f"exit \"$(cat '{self.code}')\"\n")
        self.cmd = f"sh '{d / 'stub.sh'}'"
        machine_file(self, allowance_cmd=self.cmd)
        self.good()
        for n, name in enumerate(("third", "fourth", "fifth"), start=3):
            self.write(f"docs/delivery/tasks/000{n}-{name}.md", task(f"000{n}-{name}", f"src/{name}.py"))
        self.write("docs/delivery/tasks/0002-second.md", task("0002-second", "src/second.py"))

    def stub(self, out: str = "", err: str = "", code: int = 0) -> None:
        self.out.write_text(out)
        self.err.write_text(err)
        self.code.write_text(str(code))

    def good(self, five: float = 20.0, seven: float = 50.0, **extra) -> None:
        self.stub(json.dumps({"five_hour": {"utilization": five, "resets_at": utc(T0 + 4 * 3600)},
                              "seven_day": {"utilization": seven, "resets_at": utc(T0 + 5 * 86400)}, **extra}))

    def runs(self) -> int:
        return len(self.counter.read_text().splitlines()) if self.counter.is_file() else 0

    def rows(self, q: Path | None = None) -> list[dict]:
        p = (q or self.q) / "board/allowance.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def log(self, *rows: dict) -> None:
        p = self.q / "board/allowance.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def good_row(self, ago: float, five: float = 20.0, seven: float = 50.0) -> dict:
        wins = [{"name": "five_hour", "pct": five, "resets_at": utc(T0 + 4 * 3600)},
                {"name": "seven_day", "pct": seven, "resets_at": utc(T0 + 5 * 86400)}]
        return {"at": utc(self.t - ago), "five_hour": five, "seven_day": seven, "resets_at": wins[1]["resets_at"],
                "five_hour_resets_at": wins[0]["resets_at"], "windows": wins}

    def cache(self) -> dict:
        p = usage.cache_path(self.cmd)
        return json.loads(p.read_text()) if p.is_file() else {}

    def set_cache(self, **keys) -> None:
        usage.cache_path(self.cmd).write_text(json.dumps(keys))

    def plane(self, **blocks) -> None:
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg.update(blocks)
        self.write("docs/delivery/plane.json", json.dumps(cfg))

    def claim(self, tid: str):
        return self.ccp("tasks", "claim", tid, root=self.main)


class SharedReading(ReaderFixture, unittest.TestCase):
    def test_two_claims_within_the_ttl_read_once(self):
        self.plane(telemetry={"windows": {"week": {"kind": "weekly", "stop_pct": 90}}})
        self.stub(json.dumps({"windows": [{"name": "seven_day", "pct": 85, "resets_at": utc(T0 + 5 * 86400)},
                                          {"name": "week", "pct": 80, "resets_at": utc(T0 + 6 * 86400)},
                                          {"name": "five_hour", "pct": 20, "resets_at": utc(T0 + 4 * 3600)}]}))
        self.assertEqual(self.claim("0002")[0], 0)
        self.t = T0 + 30
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.runs(), 1)
        mine = self.rows()
        self.assertEqual(len(mine), 1)  # the product's log already holds that reading
        self.assertEqual(mine[0]["weekly_window"], "seven_day")
        # another product on the machine: its own queue, a decision raising its seven_day checkpoint
        q2 = Path(tempfile.mkdtemp(dir=self._tmp.name))
        (q2 / "board").mkdir()
        (q2 / "board/allowance-decisions.jsonl").write_text(json.dumps(
            {"at": utc(T0), "to": 99, "resets_at": utc(T0 + 5 * 86400), "window": "seven_day"}) + "\n")
        self.t = T0 + 40
        usage.reading(config.load(self.main), q2)
        self.assertEqual(self.runs(), 1)
        theirs = self.rows(q2)
        self.assertEqual(len(theirs), 1)
        self.assertTrue(theirs[0]["reused"])
        self.assertEqual(theirs[0]["at"], mine[0]["at"])
        self.assertEqual(theirs[0]["weekly_window"], "week")  # its own `project`, from the shared raw windows

    def test_a_failed_read_backs_off(self):
        self.stub(err="secret-text", code=1)
        self.assertEqual(self.claim("0002")[0], 0)
        lines = (self.q / "board/allowance.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn("secret-text", lines[0])
        row = json.loads(lines[0])
        self.assertEqual((row["failed"], row["exit"]), (True, 1))
        self.t = T0 + 30
        self.assertEqual(self.claim("0003")[0], 0)
        self.assertEqual((self.runs(), len(self.rows())), (1, 1))  # inside the backoff: no run, no row
        self.t = T0 + 61
        self.assertEqual(self.claim("0004")[0], 0)
        self.assertEqual(self.runs(), 2)
        self.assertEqual(self.cache()["backoff_s"], 120)
        self.good()
        self.t = T0 + 61 + 121
        self.assertEqual(self.claim("0005")[0], 0)
        self.assertEqual(self.runs(), 3)
        c = self.cache()
        self.assertEqual((c["backoff_s"], c["backoff_until"], c["failing_since"]), (None, None, None))
        self.assertFalse(self.rows()[-1].get("failed"))

    def test_retry_after_is_honoured(self):
        self.stub(json.dumps({"retry_after_s": 300}), code=1)
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.rows()[-1]["retry_after_s"], 300)
        self.t = T0 + 200
        self.assertEqual(self.claim("0003")[0], 0)
        self.assertEqual(self.runs(), 1)
        self.t = T0 + 301
        self.assertEqual(self.claim("0004")[0], 0)
        self.assertEqual(self.runs(), 2)

    def test_a_failed_read_keeps_the_good_reading(self):
        self.plane(parallel={"max_in_flight": 2})
        self.log(self.good_row(ago=600))
        self.stub(code=1)  # as on HTTP 429
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertTrue(self.rows()[-1]["failed"])
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)  # not slots full
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 0, out + err)  # rule 5 judged on the 20% reading still in force
        # a weekly figure past the checkpoint (90), 40 minutes old, its reset still ahead: a new claim stops
        self.log(self.good_row(ago=2400, seven=95))
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 5, out + err)
        self.assertIn("seven_day window is at 95%", err)

    def test_an_hour_unread_refuses_a_new_claim(self):
        self.stub(code=1)
        self.log(self.good_row(ago=70 * 60))  # below every threshold, past the reading in force
        self.set_cache(good=None, failing_since=utc(T0 - 61 * 60), backoff_s=900, backoff_until=utc(T0 + 300))
        code, _, out, err = self.claim("0002")
        self.assertEqual(code, 5, out + err)
        self.assertIn("usage", err)
        self.assertIn("not been read", err)
        self.assertEqual(self.runs(), 0)
        pending = [e for e in self.events() if (e["type"], e["op"]) == ("notify", "pending")]
        self.assertEqual([(e["payload"]["trigger"], e["payload"]["reason"]) for e in pending],
                         [("allowance_checkpoint", "usage unread")])
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.set_cache(good=None, failing_since=utc(T0 - 59 * 60), backoff_s=900, backoff_until=utc(T0 + 300))
        code, _, out, err = self.claim("0002")
        self.assertEqual(code, 0, out + err)  # into an empty active set, with the warning
        self.assertIn("no good allowance reading in force", err)

    def test_a_refused_prompt_reads_nothing(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.counter.write_text("")
        self.t = T0 + usage.READ_TTL_S + 1  # a prompt that passed its gates would read
        d = self.q / "runs/0002-second"
        d.mkdir(parents=True)
        (d / "verify-1.json").write_text(json.dumps({
            "run_id": "0002-second/verify-1", "task_id": "0002-second", "phase": "verify",
            "opened_at": utc(T0), "reported_at": utc(T0 + 10)}))
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "1", "--head", "a" * 40, root=self.main)
        self.assertEqual(code, 4, out + err)
        self.assertEqual(self.runs(), 0)


if __name__ == "__main__":
    unittest.main()
