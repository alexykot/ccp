"""`ccp suite wait` (SPEC §14.2, §16.6): a worker waits on a started run's summary by its suite id,
within its command limit, instead of reading the log in a loop. A finished run exits 0 or 1, so only
a run still going exits 3."""
from __future__ import annotations

import json
import re
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

from ccp.queue import iso
from tests.suite_fixture import FAILING_MODULE, PY, SuiteFixture, _start_log, ccp_proc


def _secs(text: str) -> str:
    """The text with each `, N.N s` time masked: a rebuilt summary formats the recorded seconds."""
    return re.sub(r", \d+(\.\d)? s", ", N s", text)


class Wait(SuiteFixture, unittest.TestCase):
    def wait(self, *args: str):
        t0 = time.monotonic()
        r = ccp_proc(self.runner, "suite", "wait", *args)
        return r, time.monotonic() - t0

    def append(self, row: dict) -> None:
        p = self.q / "runs" / "_suites.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps(row) + "\n")

    def started(self, sid: str, at: str | None = None, lane: str = "full") -> None:
        self.append({"op": "started", "suite_id": sid, "at": at or iso(), "lane": lane, "cmd": "python3",
                     "argc": 1, "output": "summary", "run_id": None})

    def ended(self, sid: str, code: int, **extra) -> None:
        self.append({"op": "ended", "suite_id": sid, "at": iso(), "exit_code": code, "seconds": 8.5,
                     "tests": 9, "failed": 1 if code else None, "skipped": None, "ran": None, "cached": None,
                     "cached_tests": None, "cold": None, "counts_from": "output", "log": None,
                     "interrupted": None, **extra})

    def test_a_failed_run_prints_the_summary_run_printed_and_its_exit_code(self):
        d = self.module()
        r = self.run_suite("--lane", "part", "--", PY, "-m", "unittest", "discover", "-v", "-s", str(d), "-t", str(d),
                           env={"PYTHONUNBUFFERED": "1"})
        self.assertEqual(r.returncode, 1, r.stderr)
        sid = self.rows()[-1]["suite_id"]
        w, _ = self.wait(sid)
        self.assertEqual(w.returncode, 1, w.stderr)
        out = w.stdout.decode()
        for want in ("failing tests' sections (2)", "ERROR: test_err", "RuntimeError: boom", "FAIL: test_bad",
                     f"ccp suite: {sid}: FAILED, exit 1, lane part,", "4 tests, 2 failed, 1 skipped",
                     f"ccp suite: full log: {_start_log(r.stdout)}"):
            self.assertIn(want, out)
        run_out = r.stdout.decode().splitlines()
        self.assertEqual(_secs(out), _secs("\n".join(run_out[1:]) + "\n"))  # the run's summary, past its start line

    def module(self):
        d = self.main.parent / "ut"
        d.mkdir(exist_ok=True)
        (d / "test_x.py").write_text(FAILING_MODULE)
        return d

    def test_a_passed_run_exits_0_with_its_counts(self):
        r = self.run_suite("--lane", "part", "--", PY, "-c", "import sys; print('Ran 3 tests in 0.1s', file=sys.stderr)")
        self.assertEqual(r.returncode, 0, r.stderr)
        sid = self.rows()[-1]["suite_id"]
        w, _ = self.wait(sid)
        self.assertEqual(w.returncode, 0, w.stderr)
        self.assertRegex(w.stdout.decode(), rf"ccp suite: {sid}: passed, exit 0, lane part, \S+ s; 3 tests\n"
                                            rf"ccp suite: log: \S+\n$")

    def test_a_run_still_going_returns_exit_3_at_the_timeout_with_its_elapsed_time(self):
        self.started("st-going", at=iso(datetime.now(timezone.utc) - timedelta(seconds=70)))
        w, took = self.wait("st-going", "--timeout", "2")
        self.assertEqual(w.returncode, 3, w.stderr)
        self.assertLess(took, 5)
        self.assertGreaterEqual(took, 2)
        self.assertRegex(w.stdout.decode(), r"st-going: .*\b7\d s\b")  # its elapsed time

    def test_a_run_that_ends_while_waiting_returns_at_once_failed_with_its_code_in_the_summary(self):
        self.started("st-late")
        timer = threading.Timer(2.0, self.ended, ("st-late", 4))
        timer.start()
        try:
            w, took = self.wait("st-late", "--timeout", "30")
        finally:
            timer.cancel()
        self.assertEqual(w.returncode, 1, w.stderr)
        self.assertLess(took, 10)
        self.assertIn("st-late: FAILED, exit 4, lane full, 8.5 s; 9 tests, 1 failed", w.stdout.decode())

    def test_a_finished_run_whose_command_exited_3_ends_the_wait_with_exit_1(self):
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": {"three": ["sh", "-c", "exit 3"]}}
        p.write_text(json.dumps(cfg))
        r = self.run_suite("--lane", "three")
        self.assertEqual(r.returncode, 3, r.stderr)
        sid = self.rows()[-1]["suite_id"]
        w, took = self.wait(sid, "--timeout", "30")
        self.assertEqual(w.returncode, 1, w.stderr)
        self.assertLess(took, 10)
        self.assertIn(f"ccp suite: {sid}: FAILED, exit 3, lane three,", w.stdout.decode())
        self.assertNotIn("still running", w.stdout.decode())

    def test_a_finished_run_exits_0_or_1_whatever_its_own_code(self):
        for code, want in ((0, 0), (1, 1), (3, 1), (75, 1), (130, 1), (2, 1)):
            sid = f"st-code-{code}"
            self.started(sid)
            self.ended(sid, code, **({"interrupted": "SIGINT"} if code == 130 else {}))
            w, _ = self.wait(sid)
            self.assertEqual(w.returncode, want, (code, w.stderr))
            self.assertIn(f"exit {code}", w.stdout.decode())

    def test_the_worker_prompts_say_only_exit_3_means_still_going(self):
        from ccp.prompt import TEMPLATES
        text = (TEMPLATES / "_common.md").read_text()
        self.assertIn("exit 3 means only that the run is still going", text)
        self.assertNotIn("whatever the exit code", text)

    def test_an_unknown_id_is_refused_naming_it(self):
        w, _ = self.wait("st-nope")
        self.assertEqual(w.returncode, 2)
        self.assertIn("st-nope", w.stderr.decode())
        self.assertEqual(w.stdout, b"")

    def test_a_negative_timeout_is_refused(self):
        self.started("st-going")
        w, _ = self.wait("st-going", "--timeout", "-1")
        self.assertEqual(w.returncode, 2)
        self.assertIn("--timeout", w.stderr.decode())

    def test_a_killed_run_exits_1_at_once(self):
        self.started("st-old", at=iso(datetime.now(timezone.utc) - timedelta(minutes=31)))
        w, took = self.wait("st-old", "--timeout", "30")
        self.assertEqual(w.returncode, 1, w.stderr)
        self.assertLess(took, 10)
        self.assertIn("st-old: killed", w.stdout.decode())

    def test_without_its_log_the_result_line_still_shows(self):
        self.started("st-gone")
        self.ended("st-gone", 1, log=str(self.q / "runs" / "_suite-logs" / "st-gone.log"),
                   stages=[{"name": "unit", "seconds": 3.0, "exit_code": 1}], failed_stage="unit",
                   result_problem="not JSON")
        w, _ = self.wait("st-gone")
        self.assertEqual(w.returncode, 1, w.stderr)
        out = w.stdout.decode()
        self.assertIn("st-gone: stages: unit FAILED (exit 1) 3.0 s", out)
        self.assertIn("st-gone: FAILED, exit 1, lane full, 8.5 s; 9 tests, 1 failed", out)
        self.assertIn("(not JSON)", out)

    def test_a_row_from_before_the_result_contract_shows_its_units(self):
        self.started("st-older")
        self.append({"op": "ended", "suite_id": "st-older", "at": iso(), "exit_code": 0, "seconds": 8.5, "tests": 9,
                     "modules_ran": 2, "modules_cached": 5, "log": None, "interrupted": None})
        w, _ = self.wait("st-older")
        self.assertEqual(w.returncode, 0, w.stderr)
        self.assertIn("; ran 2, cached 5", w.stdout.decode())

    def test_it_writes_nothing(self):
        self.started("st-done")
        self.ended("st-done", 0)
        before = (self.q / "runs" / "_suites.jsonl").read_text()
        events = self.q / "observability" / "events.jsonl"
        ev_before = events.read_text() if events.is_file() else ""
        w, _ = self.wait("st-done")
        self.assertEqual(w.returncode, 0, w.stderr)
        self.assertIn("st-done: passed, exit 0", w.stdout.decode())
        self.assertEqual((self.q / "runs" / "_suites.jsonl").read_text(), before)
        self.assertEqual(events.read_text() if events.is_file() else "", ev_before)


if __name__ == "__main__":
    unittest.main()
