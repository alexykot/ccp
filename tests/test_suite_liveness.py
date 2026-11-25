"""A suite run's liveness (SPEC §14.4): a `started` row with no end is open while its recording `ccp` is alive and
killed once it is gone, whatever its age; a row it cannot judge keeps the run and age rules; and a worker run that
reports or is abandoned has its live suite runs ended, while one that only stops does not."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import config, runs, suite
from ccp.queue import iso
from tests.report_helpers import done_report
from tests.suite_fixture import CCP, PY, SuiteFixture, ccp_proc

RUN = "0002-second/implement"


def ago(minutes: float) -> str:
    return iso(datetime.now(timezone.utc) - timedelta(minutes=minutes))


class Liveness(SuiteFixture, unittest.TestCase):
    def start(self, run: str | None = None) -> tuple[subprocess.Popen, dict]:
        """A real `ccp suite run` of a command that sleeps, once its command is running: its process and its
        `started` row."""
        mark = Path(self._tmp.name) / f"ready-{time.monotonic_ns()}"
        child = f"import time; open({str(mark)!r}, 'w').close(); time.sleep(60)"
        env = dict(os.environ)
        env.pop("CCP_SUITE_ID", None)
        p = subprocess.Popen([CCP, "suite", "run", *(["--run", run] if run else []), "--", PY, "-c", child],
                             cwd=self.runner, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        self.addCleanup(self.end, p)
        deadline = time.time() + 30
        while time.time() < deadline and not mark.exists():
            time.sleep(0.05)
        self.assertTrue(mark.exists(), "the run's command started")
        row = [r for r in self.rows() if r["op"] == "started"][-1]
        self.assertEqual(row["pid"], p.pid)
        return p, row

    @staticmethod
    def end(p: subprocess.Popen) -> None:
        if p.poll() is None:
            p.terminate()  # ccp forwards it to the command's group
        p.wait(timeout=30)

    def state(self, suite_id: str) -> dict:
        return [s for s in suite.fold(self.q) if s["suite_id"] == suite_id][0]

    def set_rows(self, edit) -> None:
        p = self.q / "runs" / "_suites.jsonl"
        rows = [json.loads(x) for x in p.read_text().splitlines()]
        p.write_text("".join(json.dumps(edit(r)) + "\n" for r in rows))

    def append(self, row: dict) -> None:
        (self.q / "runs").mkdir(parents=True, exist_ok=True)
        with (self.q / "runs" / "_suites.jsonl").open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def wait_for(self, sid: str) -> subprocess.CompletedProcess[bytes]:
        return ccp_proc(self.runner, "suite", "wait", sid, "--timeout", "0")

    def test_a_live_run_past_thirty_minutes_is_open(self):
        p, row = self.start()
        for k in ("host", "pstart"):
            self.assertTrue(row.get(k), k)
        self.set_rows(lambda r: {**r, "at": "2026-01-01T00:00:00Z"} if r["suite_id"] == row["suite_id"] else r)
        self.assertEqual(self.state(row["suite_id"])["state"], "open")
        self.assertEqual(suite.totals(suite.fold(self.q)), {"by_run": {}, "by_task": {}})
        w = self.wait_for(row["suite_id"])
        self.assertEqual(w.returncode, 3, w.stdout + w.stderr)  # still running
        self.assertEqual(p.poll(), None)

    def test_a_run_whose_process_is_gone_is_killed_at_once(self):
        p, row = self.start()
        p.kill()
        p.wait(timeout=30)
        st = self.state(row["suite_id"])
        self.assertEqual((st["state"], st["seconds"]), ("killed", None))  # no worker run: its time is unknown
        w = self.wait_for(row["suite_id"])
        self.assertEqual(w.returncode, 1, w.stdout + w.stderr)
        self.assertIn(f"({suite.KILLED_GONE})", w.stdout.decode())

    def test_a_row_without_a_pid_keeps_the_age_rule(self):
        gone = subprocess.Popen(["true"])
        gone.wait()  # a process id no process has now
        base = {"op": "started", "lane": "part", "cmd": "python3", "argc": 1, "output": "summary"}
        self.append({**base, "suite_id": "st-young", "at": ago(10)})
        self.append({**base, "suite_id": "st-old", "at": ago(31)})
        self.append({**base, "suite_id": "st-nostart", "at": ago(10), "pid": gone.pid, "host": socket.gethostname()})
        self.append({**base, "suite_id": "st-elsewhere", "at": ago(10), "pid": gone.pid, "host": "elsewhere.invalid",
                     "pstart": "Thu Jan  1 00:00:00 2026"})
        self.assertEqual([self.state(s)["state"] for s in ("st-young", "st-old", "st-nostart", "st-elsewhere")],
                         ["open", "killed", "open", "open"])
        w = self.wait_for("st-old")
        self.assertEqual(w.returncode, 1, w.stdout + w.stderr)
        self.assertIn(f"({suite.KILLED_AGE})", w.stdout.decode())

    def test_a_reused_pid_is_not_the_run(self):
        self.implementing()
        other = subprocess.Popen(["sleep", "60"])  # a live process that is not a `ccp suite run`
        self.addCleanup(lambda: (other.kill(), other.wait()))
        p, row = self.start()  # a live `ccp suite run`, unbound
        base = {"op": "started", "lane": "part", "cmd": "python3", "argc": 1, "output": "summary", "at": ago(1),
                "run_id": RUN, "task_id": "0002-second", "phase": "implement", "host": socket.gethostname()}
        lstart = suite._ps(other.pid, "lstart")
        self.assertTrue(lstart)
        self.append({**base, "suite_id": "st-command", "pid": other.pid, "pstart": lstart})
        self.append({**base, "suite_id": "st-started", "pid": p.pid, "pstart": "Thu Jan  1 00:00:00 2026"})
        self.assertEqual(suite._alive({**base, "pid": p.pid, "pstart": row["pstart"]}), suite.ALIVE)
        for sid in ("st-command", "st-started"):
            self.assertEqual(self.state(sid)["state"], "killed", sid)
            self.assertEqual(suite._alive(self.state(sid)), suite.DEAD, sid)
        self.assertEqual(suite.end_bound_runs(self.q, RUN), [])
        time.sleep(0.3)
        self.assertEqual((other.poll(), p.poll()), (None, None))  # neither was signalled

    def test_when_ps_cannot_answer_the_age_rule_holds(self):
        self.implementing()
        p, row = self.start(run=RUN)
        slow = Path(self._tmp.name) / "slow-ps"
        slow.write_text("#!/bin/sh\nsleep 3\n")
        slow.chmod(0o755)
        failing = Path(self._tmp.name) / "failing-ps"
        failing.write_text("#!/bin/sh\nexit 1\n")
        failing.chmod(0o755)
        for ps, timeout in (("/nonexistent/ps", 5.0), (str(failing), 5.0), (str(slow), 0.3)):
            with self.subTest(ps=ps), mock.patch.object(suite, "PS", ps), mock.patch.object(suite, "PS_TIMEOUT_S", timeout):
                self.assertEqual(suite._alive(self.state(row["suite_id"])), suite.UNKNOWN)
                self.assertEqual(self.state(row["suite_id"])["state"], "open")  # started moments ago
                self.assertEqual(suite.end_bound_runs(self.q, RUN), [])  # a run it cannot judge is never signalled
                self.set_rows(lambda r: {**r, "at": ago(31)} if r["suite_id"] == row["suite_id"] else r)
                self.assertEqual(self.state(row["suite_id"])["state"], "killed")  # the 30 minutes hold
                self.set_rows(lambda r: {**r, "at": iso()} if r["suite_id"] == row["suite_id"] else r)
        self.assertEqual(p.poll(), None)
        self.assertEqual(self.state(row["suite_id"])["state"], "open")  # ps answers again: alive

    def test_a_reported_or_abandoned_workers_live_run_is_ended_and_recorded_interrupted(self):
        self.implementing()
        cfg = config.load(self.runner)
        p, row = self.start(run=RUN)
        runs.abandon(self.q, cfg, runs.load(self.q, RUN), "superseded in a test")
        p.wait(timeout=30)
        ended = [r for r in self.rows() if r["op"] == "ended" and r["suite_id"] == row["suite_id"]]
        self.assertEqual([r["interrupted"] for r in ended], ["SIGTERM"])
        self.assertEqual(self.state(row["suite_id"])["state"], "interrupted")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        rid = body["run_id"]
        self.assertNotEqual(rid, RUN)
        p, row = self.start(run=rid)
        code, _, out, err = self.report(rid, done_report("implement", "PR: #7", "Head: " + "a" * 40))
        self.assertEqual(code, 0, out + err)
        p.wait(timeout=30)
        ended = [r for r in self.rows() if r["op"] == "ended" and r["suite_id"] == row["suite_id"]]
        self.assertEqual([r["interrupted"] for r in ended], ["SIGTERM"])
        self.assertEqual(self.state(row["suite_id"])["state"], "interrupted")

    def test_a_stopped_workers_live_run_is_left_running(self):
        self.implementing()
        cfg = config.load(self.runner)
        rec = runs.load(self.q, RUN)
        rec["agent_id"] = "agent-under-test"
        runs.save(self.q, rec)
        p, row = self.start(run=RUN)
        self.assertIsNotNone(runs.stop(self.q, cfg, "agent-under-test"))
        time.sleep(0.5)
        self.assertEqual(p.poll(), None)
        self.assertEqual(self.state(row["suite_id"])["state"], "open")  # its run stopped since, but it is alive
        self.assertFalse([r for r in self.rows() if r["op"] == "ended"])


if __name__ == "__main__":
    unittest.main()
