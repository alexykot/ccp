"""`ccp suite run|list` (SPEC §14.1): a transparent test wrapper that records time, count and exit
code against the run, and never stands between a worker and its tests."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
import sys
import time
import unittest
from unittest import mock
from pathlib import Path

from ccp import board, config, suite
from tests.test_toolkit import ToolkitFixture

PLANE = Path(__file__).resolve().parents[1]
CCP = str(PLANE / "bin" / "ccp")
PY = sys.executable


def ccp_proc(cwd: Path, *args: str, env: dict | None = None, stdin: bytes | None = None,
             unset: tuple[str, ...] = ()) -> subprocess.CompletedProcess[bytes]:
    e = {**os.environ, **(env or {})}
    e.pop("CCP_SUITE_ID", None) if "CCP_SUITE_ID" not in (env or {}) else None
    for k in unset:
        e.pop(k, None)
    return subprocess.run([CCP, *args], cwd=cwd, env=e, input=stdin, capture_output=True, timeout=60)


def _kill(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


# A product whose gate prints its own cache tally (`<name>: N modules ran, N cached; …the cached
# modules' last runs: N tests…`) and writes no result file keeps its counts with these knobs.
TALLY_SUMMARY = {
    "ran_re": r"^\S+: (\d+) modules? ran, \d+ cached",
    "cached_re": r"^\S+: \d+ modules? ran, (\d+) cached",
    "cached_tests_re": r"^\S+: \d+ modules? ran, .*\bcached modules' last runs: (\d+) tests?\b",
    "show_re": [r"^\S+: \d+ modules? ran, \d+ cached", r"^\S+: failed: ", r"^exit [1-9]\d*: "],
}


class SuiteFixture(ToolkitFixture):
    def tally(self, summary: dict | None = None) -> None:
        """Configure the product's tally regexes (the pre-contract defaults) in its plane.json."""
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg.setdefault("suite", {})["summary"] = summary or TALLY_SUMMARY
        p.write_text(json.dumps(cfg))

    def rows(self) -> list[dict]:
        p = self.q / "runs" / "_suites.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def run_suite(self, *args: str, **kw) -> subprocess.CompletedProcess[bytes]:
        return ccp_proc(self.runner, "suite", "run", *args, **kw)

    def implementing(self) -> None:
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)


class Transparency(SuiteFixture, unittest.TestCase):
    def test_output_and_exit_code_pass_through_unchanged(self):
        script = ("import sys; sys.stdout.buffer.write(b'out \\xff\\n' * 3 + b'no newline'); sys.stdout.flush(); "
                  "sys.stderr.buffer.write(b'err line\\n'); sys.exit(3)")
        r = self.run_suite("--full", "--lane", "part", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout, b"out \xff\n" * 3 + b"no newline")
        self.assertEqual(r.stderr, b"err line\n")
        ended = [x for x in self.rows() if x["op"] == "ended"]
        self.assertEqual([x["exit_code"] for x in ended], [3])

    def test_stdin_is_the_commands_and_a_zero_exit_is_zero(self):
        r = self.run_suite("--full", "--", PY, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())", stdin=b"abc\n")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"ABC\n", b""))

    def test_a_missing_command_exits_127(self):
        r = self.run_suite("--", "/nonexistent/suite-command")
        self.assertEqual(r.returncode, 127)
        self.assertEqual([x["exit_code"] for x in self.rows() if x["op"] == "ended"], [127])

    def test_duration_and_count_are_recorded_and_output_is_not(self):
        script = ("import sys, time; time.sleep(0.3); print('SECRET-OUTPUT-LINE'); "
                  "print('Ran 4 tests in 0.2s', file=sys.stderr); print('Ran 6 tests in 0.1s', file=sys.stderr)")
        r = self.run_suite("--lane", "full", "--", PY, "-c", script, "ARG-NOT-STORED")
        self.assertEqual(r.returncode, 0, r.stderr)
        started, ended = self.rows()
        self.assertEqual((started["op"], ended["op"]), ("started", "ended"))
        self.assertEqual(started["suite_id"], ended["suite_id"])
        self.assertEqual((started["lane"], started["cmd"], started["argc"]), ("full", Path(PY).name, 3))
        self.assertGreaterEqual(ended["seconds"], 0.3)
        self.assertEqual(ended["tests"], 10)
        self.assertIsNone(ended["interrupted"])
        ev = [e for e in self.events() if e["type"] == "suite"]
        self.assertEqual([(e["op"], e["payload"]["tests"], e["payload"]["lane"]) for e in ev], [("recorded", 10, "full")])
        stored = (self.q / "runs" / "_suites.jsonl").read_text() + (self.q / "observability/events.jsonl").read_text()
        for leak in ("SECRET-OUTPUT-LINE", "ARG-NOT-STORED", "import sys"):
            self.assertNotIn(leak, stored)

    def test_no_count_line_records_no_count(self):
        r = self.run_suite("--", PY, "-c", "print('nothing here')")
        self.assertEqual(r.returncode, 0)
        self.assertIsNone(self.rows()[-1]["tests"])

    def test_a_real_unittest_run_is_counted(self):
        d = Path(self._tmp.name) / "ut"
        d.mkdir()
        (d / "test_x.py").write_text("import unittest\nclass T(unittest.TestCase):\n"
                                     "    def test_a(self): pass\n    def test_b(self): pass\n")
        r = self.run_suite("--full", "--", PY, "-m", "unittest", "discover", "-s", str(d), "-t", str(d))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"Ran 2 tests", r.stderr)
        self.assertEqual(self.rows()[-1]["tests"], 2)


class Binding(SuiteFixture, unittest.TestCase):
    def test_run_flag_binds_to_the_run(self):
        self.implementing()
        r = self.run_suite("--run", "0002-second/implement", "--lane", "full", "--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        started = self.rows()[0]
        self.assertEqual((started["run_id"], started["task_id"], started["phase"], started["seat"], started["bound_by"]),
                         ("0002-second/implement", "0002-second", "implement", "implementer", "run"))
        ev = [e for e in self.events() if e["type"] == "suite"][0]
        self.assertEqual((ev["task_id"], ev["payload"]["run_id"]), ("0002-second", "0002-second/implement"))

    def test_task_flag_binds_to_its_latest_open_run(self):
        self.implementing()
        r = self.run_suite("--task", "0002", "--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.rows()[0]["run_id"], self.rows()[0]["bound_by"]), ("0002-second/implement", "task"))

    def test_without_flags_a_running_run_binds_only_inside_its_worktree(self):
        self.implementing()
        wt = self.main / ".rt" / "impl-0002"
        ccp_proc(wt, "suite", "run", "--", PY, "-c", "pass")
        self.assertIsNone(self.rows()[0]["run_id"])  # pending, not running: unbound
        self.ccp("agent", "start", stdin=json.dumps({"agent_id": "a1", "agent_type": "delivery-implementer"}))
        self.run_suite("--", PY, "-c", "pass")  # the runner worktree is not the run's
        self.assertIsNone(self.rows()[2]["run_id"])
        (wt / "sub").mkdir()
        ccp_proc(wt / "sub", "suite", "run", "--", PY, "-c", "pass")
        self.assertEqual((self.rows()[4]["run_id"], self.rows()[4]["bound_by"]), ("0002-second/implement", "worktree"))

    def test_an_unknown_run_is_recorded_against_its_task_unbound(self):
        r = self.run_suite("--run", "0002-second/review-3", "--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0)
        self.assertIn(b"no run 0002-second/review-3", r.stderr)
        self.assertEqual((self.rows()[0]["run_id"], self.rows()[0]["task_id"], self.rows()[0]["phase"]),
                         (None, "0002-second", "review"))

    def test_list_usage_and_board_totals_per_run_and_phase(self):
        self.implementing()
        for _ in range(2):
            self.run_suite("--run", "0002-second/implement", "--", PY, "-c", "import time; time.sleep(0.05)")
        code, body, out, err = self.ccp("suite", "list", "--task", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(body["suites"]), 2)
        self.assertEqual(body["by_run"]["0002-second/implement"]["suite_runs"], 2)
        phases = body["by_task"]["0002-second"]["phases"]
        self.assertEqual(list(phases), ["implement"])
        self.assertGreater(phases["implement"]["suite_s"], 0.09)
        code, body, out, err = self.ccp("usage", "--task", "0002", "--json")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["runs"][0]["suite"]["suite_runs"], 2)
        self.assertEqual(body["suite_total"]["phases"]["implement"]["suite_runs"], 2)
        code, _, out, _ = self.ccp("usage", "--task", "0002")
        self.assertIn("task 0002-second: 2 suite run(s)", out)
        fields = board._suite_fields(suite.totals(suite.fold(self.q))["by_task"]["0002-second"])
        self.assertEqual((fields["suite_runs"], fields["suite_phases"]["implement"]["suite_runs"]), (2, 2))
        self.assertEqual(board._suite_fields(None), {"suite_s": 0.0, "suite_runs": 0, "suite_killed": 0, "suite_phases": {}})

    def test_an_open_run_counts_nowhere_until_it_is_known_killed(self):
        from ccp.queue import iso
        self.implementing()
        rid = "0002-second/implement"
        suite._append(self.q, {"op": "started", "suite_id": "st-new", "at": iso(), "run_id": rid,
                               "task_id": "0002-second", "phase": "implement"})
        rows = suite.fold(self.q)
        self.assertEqual(rows[0]["state"], "open")
        self.assertEqual(suite.totals(rows), {"by_run": {}, "by_task": {}})
        # older than 15 minutes, its run still open: killed, time unknown
        suite._append(self.q, {"op": "started", "suite_id": "st-old", "at": "2026-10-01T00:00:00Z",
                               "task_id": "0002-second", "phase": "implement"})
        old = [r for r in suite.fold(self.q) if r["suite_id"] == "st-old"][0]
        self.assertEqual((old["state"], old["seconds"]), ("killed", None))
        # its run stopped since: killed, timed to the stop
        rec = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        rec["stopped_at"] = "2099-01-01T00:00:00Z"
        (self.q / "runs/0002-second/implement.json").write_text(json.dumps(rec))
        new = [r for r in suite.fold(self.q, now=0) if r["suite_id"] == "st-new"][0]
        self.assertEqual(new["state"], "killed")
        self.assertGreater(new["seconds"], 0)
        t = suite.totals(suite.fold(self.q))["by_task"]["0002-second"]
        self.assertEqual((t["suite_runs"], t["suite_killed"]), (2, 2))
        code, body, _, _ = self.ccp("usage", "--task", "0002", "--json")
        self.assertEqual(body["suite_total"]["suite_killed"], 2)

    def test_a_damaged_suites_file_breaks_no_reader(self):
        self.implementing()
        (self.q / "runs" / "_suites.jsonl").write_bytes(b'\xff\xfe{"op": "started", "suite_id": 3}\n[1]\nnot json\n')
        self.assertEqual(suite.safe_totals(self.q), {"by_run": {}, "by_task": {}})
        code, _, out, err = self.ccp("usage", "--task", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("\n\n", out)
        code, _, out, err = self.ccp("usage")
        self.assertFalse(out.endswith("\n\n"))


class NeverBlocks(SuiteFixture, unittest.TestCase):
    def test_no_queue_root_runs_warns_once_and_records_nothing(self):
        r = self.run_suite("--full", "--", PY, "-c", "import sys; print('hi'); sys.exit(5)", unset=("QUEUE_ROOT",))
        self.assertEqual((r.returncode, r.stdout), (5, b"hi\n"))
        self.assertEqual(r.stderr.count(b"ccp suite:"), 1)
        self.assertIn(b"QUEUE_ROOT is not set", r.stderr)
        self.assertFalse((self.q / "runs" / "_suites.jsonl").exists())

    def test_a_failed_write_still_runs_and_keeps_the_exit_code(self):
        (self.q / "runs").write_text("not a directory")
        r = self.run_suite("--full", "--", PY, "-c", "import sys; print('ran'); sys.exit(9)")
        self.assertEqual((r.returncode, r.stdout), (9, b"ran\n"))
        self.assertEqual(r.stderr.count(b"ccp suite:"), 1)
        self.assertIn(b"not recorded", r.stderr)


    def test_a_broken_plane_json_still_runs_a_command(self):
        (self.runner / "docs/delivery/plane.json").write_text("{not json")
        r = self.run_suite("--full", "--", PY, "-c", "print('ran')")
        self.assertEqual((r.returncode, r.stdout), (0, b"ran\n"))
        self.assertFalse((self.q / "runs" / "_suites.jsonl").exists())
        r = self.run_suite("--lane", "full")
        self.assertEqual(r.returncode, 2)

    def test_a_non_utf8_plane_json_or_no_git_still_runs_a_command(self):
        (self.runner / "docs/delivery/plane.json").write_bytes(b'{"project_id": "\xff"}')
        r = self.run_suite("--full", "--", PY, "-c", "print('ran')")
        self.assertEqual((r.returncode, r.stdout), (0, b"ran\n"), r.stderr)
        bare = Path(self._tmp.name) / "no-git"
        bare.mkdir()
        r = ccp_proc(bare, "suite", "run", "--full", "--", PY, "-c", "print('ran')", env={"GIT_CEILING_DIRECTORIES": self._tmp.name})
        self.assertEqual((r.returncode, r.stdout), (0, b"ran\n"), r.stderr)
        self.assertEqual(r.stderr.count(b"ccp suite:"), 1)

    def test_a_background_child_holding_the_pipe_does_not_hold_ccp(self):
        t0 = time.monotonic()
        r = self.run_suite("--full", "--", "sh", "-c", "sleep 30 & echo $!; exit 3")
        self.addCleanup(_kill, int(r.stdout))
        self.assertEqual(r.returncode, 3)
        self.assertLess(time.monotonic() - t0, 10)

    def test_a_signal_reaches_the_commands_children_and_a_dead_ccp_leaves_no_suite(self):
        def alive(pid: int) -> bool:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return False
            # a zombie of ours does not count
            st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
            return bool(st) and not st.startswith("Z")

        for sig in (signal.SIGTERM, signal.SIGKILL):
            p = subprocess.Popen([CCP, "suite", "run", "--full", "--", "sh", "-c", "sleep 300 & echo $!; wait"], cwd=self.runner,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=dict(os.environ))
            grandchild = int(p.stdout.readline())
            self.addCleanup(_kill, grandchild)
            self.assertTrue(alive(grandchild))
            p.send_signal(sig)
            p.wait(timeout=20)
            deadline = time.time() + 10
            while time.time() < deadline and alive(grandchild):
                time.sleep(0.1)
            self.assertFalse(alive(grandchild), sig.name)
            p.stdout.close()
            p.stderr.close()

    def test_a_closed_stdout_still_runs_the_command(self):
        mark = Path(self._tmp.name) / "ran"
        r = subprocess.run(["sh", "-c", f'exec 1>&-; exec {CCP} suite run -- {PY} -c "open(\'{mark}\', \'w\'); raise SystemExit(6)"'],
                           cwd=self.runner, env=dict(os.environ), capture_output=False, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertTrue(mark.is_file())
        self.assertEqual([x["exit_code"] for x in self.rows() if x["op"] == "ended"], [6])

    def test_without_process_group_support_the_command_still_runs(self):
        from unittest import mock
        import io
        real = subprocess.Popen

        def popen(*args, **kw):
            if "process_group" in kw or "preexec_fn" in kw:
                raise TypeError("unexpected keyword argument")
            return real(*args, **kw)
        a = type("A", (), {"lane": None, "phase": None, "run": None, "task": None, "root": None})()
        with mock.patch("subprocess.Popen", popen), mock.patch("os.isatty", lambda fd: False), \
                mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}), mock.patch("sys.stderr", io.StringIO()):
            code = suite.run(None, a, [PY, "-c", "raise SystemExit(5)"], record=False)
        self.assertEqual(code, 5)

    def test_root_is_not_abbreviated(self):
        r = ccp_proc(self.runner, "--ro", str(self.runner), "suite", "run", "--", PY, "-c", "raise SystemExit(3)")
        self.assertEqual(r.returncode, 3, r.stderr)  # `--ro` is refused, and the command still runs, unrecorded
        self.assertIn(b"without recording", r.stderr)
        self.assertEqual(self.rows(), [])
        r = ccp_proc(self.runner, "--root", str(self.runner), "suite", "run", "--", PY, "-c", "pass")
        self.assertEqual((r.returncode, [x["op"] for x in self.rows()]), (0, ["started", "ended"]))

    def test_a_nested_lane_resolves_from_the_root(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"lanes": {"rel": ["sh", "-c", "pwd"]}}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        (self.runner / "deep").mkdir()
        r = ccp_proc(self.runner / "deep", "suite", "run", "--lane", "rel", env={"CCP_SUITE_ID": "st-outer"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(r.stdout.decode().strip()).resolve(), self.runner.resolve())
        self.assertEqual(self.rows(), [])

    def test_a_nested_run_passes_through_unrecorded(self):
        inner = f"{CCP} suite run --lane part -- {PY} -c \"print('Ran 2 tests in 0s')\""
        r = self.run_suite("--full", "--lane", "full", "--", "sh", "-c", inner)
        self.assertEqual((r.returncode, r.stdout), (0, b"Ran 2 tests in 0s\n"), r.stderr)
        self.assertEqual([x["op"] for x in self.rows()], ["started", "ended"])
        self.assertEqual((self.rows()[0]["lane"], self.rows()[1]["tests"]), ("full", 2))

    def test_one_destination_gets_one_pipe_and_keeps_the_order(self):
        out = Path(self._tmp.name) / "merged.log"
        script = ("import sys\nfor i in range(50):\n    (sys.stdout if i % 2 else sys.stderr).write(f'{i}\\n')\n"
                  "    (sys.stdout if i % 2 else sys.stderr).flush()\n")
        with out.open("wb") as fh:
            r = subprocess.run([CCP, "suite", "run", "--full", "--", PY, "-c", script], cwd=self.runner, stdout=fh,
                               stderr=subprocess.STDOUT, env=dict(os.environ), timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(out.read_text(), "".join(f"{i}\n" for i in range(50)))

    def test_signals_are_forwarded_and_the_run_recorded_as_interrupted(self):
        child = ("import signal, sys, time\n"
                 "signal.signal(signal.SIGTERM, lambda *a: (print('got term', flush=True), sys.exit(7)))\n"
                 "print('ready', flush=True)\ntime.sleep(30)\n")
        for sig, argv, want in ((signal.SIGTERM, [PY, "-c", child], 7), (signal.SIGINT, ["sleep", "30"], 130)):
            p = subprocess.Popen([CCP, "suite", "run", "--full", "--", *argv], cwd=self.runner, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=dict(os.environ))
            if argv[0] == PY:
                self.assertEqual(p.stdout.readline(), b"ready\n")
            else:
                deadline = time.time() + 10
                while time.time() < deadline and [x["op"] for x in self.rows()][-1:] != ["started"]:
                    time.sleep(0.05)
                time.sleep(0.3)  # the child is started just after its row
            p.send_signal(sig)
            out, _err = p.communicate(timeout=20)
            self.assertEqual(p.returncode, want, _err)
            if want == 7:
                self.assertIn(b"got term", out)
            self.assertEqual(self.rows()[-1]["interrupted"], sig.name)
            self.assertEqual(self.rows()[-1]["exit_code"], want)
        self.assertEqual([s["state"] for s in suite.fold(self.q)], ["interrupted", "interrupted"])


class Counting(unittest.TestCase):
    def test_an_over_long_line_is_not_matched_by_its_tail(self):
        c = suite._Counter(re.compile(rb"^Ran (\d+) tests? in "))
        c.feed(b"x" * (suite.LINE_MAX + 10))
        c.feed(b"Ran 5 tests in 1s\nRan 2 tests in 0s\n")
        c.close()
        self.assertEqual(c.total, 2)


class Lanes(SuiteFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"lanes": {"full": [PY, "-c", "import os; print(os.getcwd()); print('7 passed')"]},
                        "count_re": r"^(\d+) passed"}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        (self.runner / "sub").mkdir()

    def test_a_named_lane_runs_from_the_root_and_uses_the_products_count(self):
        r = ccp_proc(self.runner / "sub", "suite", "run", "--full", "--lane", "full")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(r.stdout.decode().splitlines()[0]).resolve(), self.runner.resolve())
        self.assertEqual((self.rows()[0]["lane"], self.rows()[-1]["tests"]), ("full", 7))

    def test_an_unknown_lane_or_no_command_runs_nothing(self):
        for args, why in ((("--lane", "nope"), b"names no lane 'nope'"), ((), b"give the command"),
                          (("--lane", "Bad Label"), b"short label"), (("--lane", "full", "--phase", "x"), b"--phase")):
            r = self.run_suite(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(why, r.stderr)
        self.assertEqual(self.rows(), [])

    def test_a_usage_error_beside_a_command_still_runs_it_unrecorded(self):
        for args in (("--lane", "Bad Label"), ("--phase", "nope"), ("--bogus-flag",), ("--lane",)):
            r = self.run_suite("--full", *args, "--", PY, "-c", "import sys; print('ran'); sys.exit(4)")
            self.assertEqual(r.returncode, 4, (args, r.stderr))
            if args[0].startswith("--bogus") or args == ("--lane",):  # unparsed: no terminal, so summary mode
                self.assertEqual(_start_log(r.stdout).read_text(), "ran\n")
                self.assertIn(b"did not parse", r.stderr)
            else:
                self.assertEqual(r.stdout, b"ran\n", args)
            self.assertIn(b"without recording", r.stderr)
        self.assertEqual(self.rows(), [])

    def test_the_command_after_dashes_wins_over_the_lane(self):
        r = self.run_suite("--full", "--lane", "full", "--", PY, "-c", "print('other')")
        self.assertEqual(r.stdout, b"other\n")

    def test_config_refuses_bad_lanes_and_patterns(self):
        for bad in ({"lanes": {"full": []}}, {"lanes": {"Full Lane": ["x"]}}, {"lanes": ["x"]},
                    {"count_re": "("}, {"count_re": "no group"}, {"other": 1}):
            self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": bad}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": {"lanes": {"unit": ["s"]}}}))
        self.assertEqual(config.load(self.main).suite["lanes"], {"unit": ["s"]})


class ReportCrossCheck(SuiteFixture, unittest.TestCase):
    REPORT = f"""\
        Built it.
        Outcome: done
        PR: #7
        Head: {'a' * 40}
        Suite: 12 tests, 3 s

        ## Friction
        none
        """

    def test_a_suite_line_without_a_recorded_run_warns_and_is_accepted(self):
        self.implementing()
        code, body, out, err = self.report("0002-second/implement", self.REPORT)
        self.assertEqual(code, 0, out + err)
        self.assertIn("no suite run is recorded for 0002-second/implement", err)
        self.assertEqual(body["suite_runs_recorded"], 0)

    def test_a_recorded_run_satisfies_it(self):
        self.implementing()
        self.run_suite("--run", "0002-second/implement", "--", PY, "-c", "pass")
        code, body, out, err = self.report("0002-second/implement", self.REPORT)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("no suite run", err)
        self.assertEqual(body["suite_runs_recorded"], 1)
        rec = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(rec["suite_runs_recorded"], 1)

    def fill_report(self, suite_line: str, run_id: str = "0002-second/implement"):
        return self.report(run_id, self.REPORT.replace("Suite: 12 tests, 3 s", suite_line))

    def suite_ok(self, lane: str = "full", tests: int = 7, run: str = "0002-second/implement") -> str:
        r = self.run_suite("--run", run, "--lane", lane, "--", PY, "-c",
                           f"import time; time.sleep(0.05); print('Ran {tests} tests in 0.1s')")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.rows()[-1]["suite_id"]

    def test_suite_from_takes_the_recorded_numbers(self):
        self.implementing()
        sid = self.suite_ok(tests=7)
        self.suite_ok(lane="part", tests=1)
        code, body, out, err = self.fill_report(f"Suite: from {sid}")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["suite_tests"], body["suite_from"], body["suite_filled"]), (7, sid, "from"))
        self.assertLess(body["suite_seconds"], 10)
        rec = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual((rec["suite_tests"], rec["suite_from"]), (7, sid))
        metrics = [json.loads(x) for x in (self.q / "health/metrics.jsonl").read_text().splitlines()]
        self.assertIn(("suite_tests", 7), [(m["metric"], m["value"]) for m in metrics])

    def test_suite_from_an_all_cached_gate_takes_zero_tests_ran(self):
        self.implementing()
        self.tally()
        script = ("print('gate: 0 modules ran, 3 cached; 0 tests ran in 0 s, 0 skipped; the cached modules\\' "
                  "last runs: 11 tests, 0 skipped; a warm run')")
        r = self.run_suite("--run", "0002-second/implement", "--lane", "gate", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stderr)
        sid = self.rows()[-1]["suite_id"]
        code, body, out, err = self.fill_report(f"Suite: from {sid}")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["suite_tests"], body["suite_ran"], body["suite_cached"]), (0, 0, 3))

    def test_no_suite_line_takes_the_runs_latest_full_or_gate_run(self):
        self.implementing()
        self.suite_ok(tests=3)
        sid = self.suite_ok(tests=9)
        self.suite_ok(lane="part", tests=1)  # a part run is not the suite
        code, body, out, err = self.report("0002-second/implement", self.REPORT.replace("Suite: 12 tests, 3 s\n", ""))
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["suite_tests"], body["suite_from"], body["suite_filled"]), (9, sid, "auto"))

    def test_a_failed_latest_run_fills_nothing_and_warns(self):
        self.implementing()
        self.suite_ok(tests=9)
        self.run_suite("--run", "0002-second/implement", "--lane", "full", "--", PY, "-c",
                       "import sys; print('Ran 4 tests in 0.1s'); sys.exit(1)")
        failed = self.rows()[-1]["suite_id"]
        code, body, out, err = self.report("0002-second/implement", self.REPORT.replace("Suite: 12 tests, 3 s\n", ""))
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("suite_tests", body)
        self.assertIn(f"latest full suite run ({failed}) failed with exit 1: nothing was filled in", err)
        # §27.2: the earlier passing run is a cold measurement; the failed one is in no series
        metrics = [json.loads(x) for x in (self.q / "health/metrics.jsonl").read_text().splitlines()]
        self.assertEqual({m["suite_id"] for m in metrics}, {self.rows()[-3]["suite_id"]})
        self.assertNotIn(failed, {m["suite_id"] for m in metrics})

    def test_a_report_that_is_not_done_files_no_suite_time(self):
        self.implementing()
        self.suite_ok(tests=9)
        code, body, out, err = self.report("0002-second/implement", "Stuck.\nOutcome: blocked\n\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.q / "health/metrics.jsonl").exists())  # §27: only a done (approved) report counts

    def test_suite_from_a_failed_run_keeps_its_numbers_out_of_health(self):
        self.implementing()
        self.run_suite("--run", "0002-second/implement", "--lane", "full", "--", PY, "-c",
                       "import sys; print('Ran 4 tests in 0.1s'); sys.exit(1)")
        code, body, out, err = self.fill_report(f"Suite: from {self.rows()[-1]['suite_id']}")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["suite_tests"], 4)
        self.assertFalse((self.q / "health/metrics.jsonl").exists())

    def test_an_unparsed_suite_line_warns_and_is_not_filled_over(self):
        self.implementing()
        self.suite_ok(tests=9)
        code, body, out, err = self.fill_report("Suite: all green, about five minutes")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("suite_tests", body)
        self.assertIn("`Suite: all green, about five minutes` line is neither", err)

    def test_no_suite_line_and_no_full_run_fills_nothing(self):
        self.implementing()
        self.suite_ok(lane="part")
        code, body, out, err = self.report("0002-second/implement", self.REPORT.replace("Suite: 12 tests, 3 s\n", ""))
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("suite_tests", body)

    def test_a_hand_written_line_stays(self):
        self.implementing()
        self.suite_ok(tests=7)
        code, body, out, err = self.fill_report("Suite: 12 tests, 3 s")
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["suite_tests"], body["suite_seconds"]), (12, 3))
        self.assertNotIn("suite_filled", body)

    def test_suite_from_an_unknown_or_foreign_run_is_refused(self):
        self.implementing()
        code, _, _, err = self.fill_report("Suite: from st-20990101T000000Z-abcdef")
        self.assertEqual(code, 1)
        self.assertIn("no suite run st-20990101T000000Z-abcdef is recorded", err)
        r = self.run_suite("--", PY, "-c", "print('Ran 2 tests in 0s')")  # unbound
        code, _, _, err = self.fill_report(f"Suite: from {self.rows()[-1]['suite_id']}")
        self.assertEqual(code, 1)
        self.assertIn("recorded against no run, not 0002-second/implement", err)
        self.run_suite("--run", "0002-second/implement", "--", PY, "-c", "print('nothing counted')")
        code, _, _, err = self.fill_report(f"Suite: from {self.rows()[-1]['suite_id']}")
        self.assertEqual(code, 1)
        self.assertIn("has not ended with a test count", err)
        self.assertFalse((self.q / "progress/0002-second/implement-report.md").exists())

    def test_the_prompt_tells_workers_to_use_it(self):
        self.implementing()
        text = (self.q / "prompts/0002-second/implement-prompt.md").read_text()
        self.assertIn(f"QUEUE_ROOT={self.q} ", text)
        self.assertIn("suite run --run 0002-second/implement --lane <lane> -- <command>", text)
        self.assertIn("`--lane full` for the product's full suite", text)
        self.assertIn("Never call `ccp suite run` inside a script", text)
        self.assertIn("never `cat` the whole log", text)
        self.assertIn("`Suite: from <suite_id>`", text)
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        vtext = (self.q / "prompts/0002-second/verify-prompt.md").read_text()
        self.assertIn("put its `suite_id` (from the summary)", vtext)
        from ccp import prompt as prompt_mod
        self.assertIn("`--lane gate`", vtext)
        self.assertIn("`--lane {gate}`", prompt_mod.SUITE_LANES["verify"])
        self.assertIn("`--lane {part}`", prompt_mod.SUITE_LANES["review"])
        rec = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(rec["worktree"], str(self.main / ".rt" / "impl-0002"))
        # §14.1 (amended 2026-10-22): the rule is stated once, in the prompt, not again in the definitions
        for a in ("implementer", "reviewer", "verifier"):
            self.assertNotIn("ccp suite run", (PLANE / f"plugin/agents/delivery-{a}.md").read_text(), a)


FAILING_MODULE = """\
import unittest
class T(unittest.TestCase):
    def test_ok(self):
        for i in range(300):
            print(f"noise line {i}")
    def test_bad(self):
        self.assertEqual(1, 2, "one is not two")
    def test_err(self):
        raise RuntimeError("boom")
    @unittest.skip("later")
    def test_skip(self):
        pass
"""


def _start_log(stdout: bytes) -> Path:
    first = stdout.decode().splitlines()[0]
    m = re.search(r"the output goes to (\S+); a summary follows", first)
    assert m, first
    return Path(m.group(1))


class Summary(SuiteFixture, unittest.TestCase):
    """§14.3 summary mode (2026-10-22): the output goes to a log file; the caller gets a start line,
    the counts, and on a failure the failing tests' sections."""

    def module(self, text: str = FAILING_MODULE) -> Path:
        d = Path(self._tmp.name) / "ut"
        d.mkdir(exist_ok=True)
        (d / "test_x.py").write_text(text)
        return d

    def ut(self, d: Path) -> list[str]:
        return [PY, "-m", "unittest", "discover", "-v", "-s", str(d), "-t", str(d)]

    def test_a_pass_prints_the_start_and_the_summary_only(self):
        script = ("import sys\nfor i in range(500): print(f'line-{i}')\n"
                  "print('Ran 3 tests in 0.1s', file=sys.stderr); print('OK (skipped=1)', file=sys.stderr)\n")
        r = self.run_suite("--lane", "full", "--", PY, "-c", script, env={"PYTHONUNBUFFERED": "1"})
        self.assertEqual((r.returncode, r.stderr), (0, b""), r.stderr)
        out = r.stdout.decode()
        self.assertNotIn("line-", out)
        lines = out.splitlines()
        self.assertEqual(len(lines), 3, out)
        log = _start_log(r.stdout)
        self.assertRegex(lines[1], r"^ccp suite: st-\S+: passed, exit 0, lane full, \d+\.\d s; 3 tests, 1 skipped$")
        self.assertEqual(lines[2], f"ccp suite: log: {log}")
        self.assertEqual(log.read_text().splitlines()[:500], [f"line-{i}" for i in range(500)])
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["skipped"], ended["failed"], ended["log"]), (3, 1, None, str(log)))
        self.assertEqual(log.parent, self.q / "runs" / "_suite-logs")  # unbound
        self.assertEqual(self.rows()[0]["output"], "summary")

    def test_a_failure_shows_the_failing_sections_and_the_tail(self):
        r = self.run_suite("--lane", "part", "--", *self.ut(self.module()), env={"PYTHONUNBUFFERED": "1"})
        self.assertEqual(r.returncode, 1, r.stderr)
        out = r.stdout.decode()
        for want in ("failing tests' sections (2)", "ERROR: test_err", "RuntimeError: boom", "FAIL: test_bad",
                     "AssertionError: 1 != 2 : one is not two", "FAILED (failures=1, errors=1, skipped=1)",
                     ": FAILED, exit 1, lane part,", "4 tests, 2 failed, 1 skipped", "ccp suite: full log: "):
            self.assertIn(want, out)
        self.assertNotIn("noise line", out)
        self.assertEqual(out.count("RuntimeError: boom"), 1)  # a section is not repeated in the tail
        log = _start_log(r.stdout)
        self.assertEqual(log.read_text().count("noise line"), 300)
        ended = self.rows()[-1]
        self.assertEqual((ended["exit_code"], ended["tests"], ended["failed"], ended["skipped"]), (1, 4, 2, 1))
        stored = (self.q / "runs" / "_suites.jsonl").read_text() + (self.q / "observability/events.jsonl").read_text()
        for leak in ("boom", "noise line", "one is not two"):
            self.assertNotIn(leak, stored)
        ev = [e for e in self.events() if e["type"] == "suite"][-1]["payload"]
        self.assertEqual((ev["failed"], ev["skipped"]), (2, 1))
        self.assertNotIn("log", ev)

    def test_what_a_failure_shows_is_capped(self):
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"summary": {"max_chars": 3000, "tail_lines": 5}}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        body = "import unittest\nclass T(unittest.TestCase):\n" + "".join(
            f"    def test_{i:02d}(self):\n        self.fail('x' * 400 + ' failure {i:02d}')\n" for i in range(40))
        r = self.run_suite("--", *self.ut(self.module(body)))
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode()
        self.assertLess(len(out), 3000 + 1500, out)
        self.assertIn("FAIL: test_00", out)
        self.assertRegex(out, r"failing tests' sections \(\d+, \d+ more not shown\)")
        self.assertIn("40 tests, 40 failed", out)
        self.assertEqual(_start_log(r.stdout).read_text().count("FAIL: test_"), 40)

    def test_one_huge_failure_is_cut_not_dropped(self):
        body = "import unittest\nclass T(unittest.TestCase):\n    def test_big(self):\n" \
               "        self.fail('\\n'.join(f'detail {i}' for i in range(20000)))\n"
        r = self.run_suite("--", *self.ut(self.module(body)))
        out = r.stdout.decode()
        self.assertIn("FAIL: test_big", out)
        self.assertIn("the rest is in the log", out)
        self.assertLess(len(out), 45000)

    def test_the_log_is_complete_and_in_order_and_exit_codes_pass_through(self):
        script = ("import sys\nfor i in range(50):\n    (sys.stdout if i % 2 else sys.stderr).write(f'{i}\\n')\n"
                  "    (sys.stdout if i % 2 else sys.stderr).flush()\n"
                  "sys.stdout.buffer.write(b'raw \\xff no newline'); sys.exit(3)\n")
        r = self.run_suite("--", PY, "-c", script)
        self.assertEqual(r.returncode, 3)
        log = _start_log(r.stdout)
        self.assertEqual(log.read_bytes(), "".join(f"{i}\n" for i in range(50)).encode() + b"raw \xff no newline")
        self.assertIn("raw \ufffd no newline", r.stdout.decode())  # the tail, decoded
        self.assertEqual(self.rows()[-1]["exit_code"], 3)
        r = self.run_suite("--", "/nonexistent/suite-command")
        self.assertEqual(r.returncode, 127)

    def test_stdin_still_reaches_the_command(self):
        r = self.run_suite("--", PY, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())", stdin=b"abc\n")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(_start_log(r.stdout).read_text(), "ABC\n")

    def test_a_bound_run_logs_next_to_its_record(self):
        self.implementing()
        r = self.run_suite("--run", "0002-second/implement", "--lane", "full", "--", PY, "-c", "print('x')")
        log = _start_log(r.stdout)
        sid = self.rows()[0]["suite_id"]
        self.assertEqual(log, self.q / "runs" / "0002-second" / f"implement-suite-{sid}.log")
        self.assertEqual(log.read_text(), "x\n")
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_log_names_the_file_and_an_unusable_one_streams(self):
        sub = Path(self._tmp.name) / "logs"
        sub.mkdir()
        r = ccp_proc(sub, "--root", str(self.runner), "suite", "run", "--log", "mine.log", "--", PY, "-c", "print('x')")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(_start_log(r.stdout), (sub / "mine.log").resolve())
        self.assertEqual((sub / "mine.log").read_text(), "x\n")
        blocker = Path(self._tmp.name) / "a-file"
        blocker.write_text("")
        r = self.run_suite("--log", str(blocker / "x.log"), "--", PY, "-c", "print('streamed'); raise SystemExit(4)")
        self.assertEqual((r.returncode, r.stdout), (4, b"streamed\n"))
        self.assertIn(b"no log file", r.stderr)

    def test_without_a_queue_the_log_is_a_temp_file(self):
        r = self.run_suite("--", PY, "-c", "print('hi'); raise SystemExit(5)", unset=("QUEUE_ROOT",))
        self.assertEqual(r.returncode, 5)
        log = _start_log(r.stdout)
        self.addCleanup(log.unlink)
        self.assertTrue(log.name.startswith("ccp-suite-st-"))
        self.assertEqual(log.parent, Path(os.environ["CCP_SUITE_LOG_DIR"]))  # the tests' fence; else the temp dir
        self.assertEqual(log.read_text(), "hi\n")
        self.assertIn(b"QUEUE_ROOT is not set", r.stderr)

    def test_a_nested_run_passes_through_into_the_outer_log(self):
        inner = f"{CCP} suite run --summary --lane part -- {PY} -c \"print('Ran 2 tests in 0s')\""
        r = self.run_suite("--lane", "full", "--", "sh", "-c", inner)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(_start_log(r.stdout).read_text(), "Ran 2 tests in 0s\n")
        self.assertEqual(r.stdout.decode().count("ccp suite: st-"), 2)  # the outer's start and summary lines
        self.assertEqual([x["op"] for x in self.rows()], ["started", "ended"])
        self.assertEqual(self.rows()[1]["tests"], 2)
        self.assertEqual(list((self.q / "runs" / "_suite-logs").iterdir()), [_start_log(r.stdout)])

    def test_signals_still_reach_the_command_and_its_group(self):
        child = ("import signal, sys, time\n"
                 "signal.signal(signal.SIGTERM, lambda *a: (print('got term', flush=True), sys.exit(7)))\n"
                 "print('ready', flush=True)\ntime.sleep(30)\n")
        p = subprocess.Popen([CCP, "suite", "run", "--", PY, "-c", child], cwd=self.runner, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=dict(os.environ))
        log = _start_log(p.stdout.readline())
        deadline = time.time() + 10
        while time.time() < deadline and "ready" not in (log.read_text() if log.exists() else ""):
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        out, err = p.communicate(timeout=20)
        self.assertEqual(p.returncode, 7, err)
        self.assertIn(b"interrupted (SIGTERM), exit 7", out)
        self.assertIn("got term", log.read_text())
        self.assertEqual(self.rows()[-1]["interrupted"], "SIGTERM")
        # a dead ccp still leaves no suite behind
        p = subprocess.Popen([CCP, "suite", "run", "--", "sh", "-c", "sleep 300 & echo $!; wait"], cwd=self.runner,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=dict(os.environ))
        log = _start_log(p.stdout.readline())
        deadline = time.time() + 10
        while time.time() < deadline and not (log.exists() and log.read_text().strip()):
            time.sleep(0.05)
        grandchild = int(log.read_text())
        self.addCleanup(_kill, grandchild)
        p.send_signal(signal.SIGKILL)
        p.wait(timeout=20)
        p.stdout.close()
        p.stderr.close()
        deadline = time.time() + 10
        while time.time() < deadline:
            st = subprocess.run(["ps", "-o", "stat=", "-p", str(grandchild)], capture_output=True, text=True).stdout.strip()
            if not st or st.startswith("Z"):
                break
            time.sleep(0.1)
        else:
            self.fail("the suite outlived a killed ccp")

    def test_a_background_child_does_not_hold_ccp(self):
        t0 = time.monotonic()
        r = self.run_suite("--", "sh", "-c", "sleep 30 & echo $!; exit 3")
        self.addCleanup(_kill, int(_start_log(r.stdout).read_text()))
        self.assertEqual(r.returncode, 3)
        self.assertLess(time.monotonic() - t0, 10)

    def test_a_cache_tally_gives_the_module_counts(self):
        script = ("print('cache: 120 entries under this key'); print('run: tests.test_a (no entry)');"
                  "print('Ran 3 tests in 0.100s'); print(); print('OK (skipped=1)');"
                  "print('cached: tests.test_b (4 tests, 0 skipped)');"
                  "print('gate: 1 modules ran, 1 cached; 3 tests ran in 0 s, 1 skipped; the cached modules\\' "
                  "last runs: 4 tests, 0 skipped; a warm run'); print('exit 0: suite')")
        self.tally()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.decode()
        self.assertIn("3 tests, 1 skipped; ran 1, cached 1", out)
        self.assertIn("\ngate: 1 modules ran, 1 cached; 3 tests ran", out)  # the product's own tally line
        self.assertNotIn("run: tests.test_a", out)
        self.assertIn("ran 1, cached 1; 4 tests behind the cached results", out)
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["ran"], ended["cached"], ended["cached_tests"], ended["counts_from"]),
                         (3, 1, 1, 4, "output"))
        fields = suite.fold(self.q)[-1]
        self.assertEqual((fields["ran"], fields["cached"], fields["skipped"], fields["cached_tests"]), (1, 1, 1, 4))

    def test_without_tally_knobs_a_tally_line_counts_nothing(self):
        script = "print('Ran 3 tests in 0.100s'); print('gate: 1 modules ran, 1 cached')"
        r = self.run_suite("--lane", "gate", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stderr)
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["ran"], ended["cached"], ended["cached_tests"]), (3, None, None, None))

    def test_the_legacy_knob_names_still_read(self):
        self.tally({"modules_ran_re": TALLY_SUMMARY["ran_re"], "modules_cached_re": TALLY_SUMMARY["cached_re"]})
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print('Ran 1 test in 0.1s'); print('g: 2 modules ran, 5 cached')")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.rows()[-1]["ran"], self.rows()[-1]["cached"]), (2, 5))

    ALL_CACHED = ("print('cached: tests.test_a (5 tests, 0 skipped)'); print('cached: tests.test_b (4 tests, 0 skipped)');"
                  "print('gate: 0 modules ran, 2 cached; 0 tests ran in 0 s, 0 skipped; the cached modules\\' "
                  "last runs: 9 tests, 0 skipped; a warm run')")

    def test_an_all_cached_gate_counts_zero_tests_ran_and_its_cached_tests(self):
        # no unittest ran, so no `Ran N tests` line
        self.tally()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", self.ALL_CACHED)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.decode()
        self.assertIn("passed, exit 0, lane gate", out)
        self.assertIn("; 0 tests; ran 0, cached 2; 9 tests behind the cached results", out)
        self.assertNotIn("no test count found", out)
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["ran"], ended["cached"], ended["cached_tests"]), (0, 0, 2, 9))
        rec = [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("suite", "recorded")][-1]
        self.assertEqual((rec["tests"], rec["cached_tests"]), (0, 9))

    def test_a_module_that_ran_without_a_count_line_leaves_no_count(self):
        # a worker that died before its result: the module ran, so 0 would be false
        self.tally()
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print('gate: 1 modules ran, 2 cached; 0 tests ran in 0 s, "
                           "0 skipped; the cached modules\\' last runs: 9 tests, 0 skipped; a warm run')")
        self.assertEqual(r.returncode, 0, r.stderr)
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["cached_tests"]), (None, 9))

    def test_a_quoted_tally_inside_a_line_is_not_counted(self):
        script = ('print("AssertionError: \'gate: 0 modules ran, 2 cached; the cached modules\' last runs: 9 tests\'");'
                  "print('Ran 4 tests in 0.1s')")
        r = self.run_suite("--lane", "gate", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.rows()[-1]["tests"], self.rows()[-1]["cached_tests"]), (4, None))

    def test_no_tally_still_means_no_count(self):
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print('gate: 0 modules ran, 0 cached')")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no test count found", r.stdout.decode())
        self.assertIsNone(self.rows()[-1]["tests"])

    def test_full_still_counts_the_fields(self):
        r = self.run_suite("--full", "--", *self.ut(self.module()))
        self.assertEqual(r.returncode, 1)
        self.assertIn(b"noise line 299", r.stdout)
        ended = self.rows()[-1]
        self.assertEqual((ended["tests"], ended["failed"], ended["skipped"], ended["log"]), (4, 2, 1, None))
        self.assertEqual(self.rows()[0]["output"], "full")

    def test_a_red_gate_step_after_many_failures_survives_the_cap(self):
        body = "import unittest\nclass T(unittest.TestCase):\n" + "".join(
            f"    def test_{i:02d}(self):\n        self.fail('\\n'.join(['detail {i:02d} ' + 'y' * 80] * 45))\n"
            for i in range(12))
        self.module(body)
        d = Path(self._tmp.name) / "ut"
        gate = (f"{PY} -m unittest discover -s {d} -t {d} 2>&1; echo 'exit 1: suite'; "
                "for i in $(seq 1 30); do echo \"src/x.py:$i:1: E501 Line too long ($i)\"; done; "
                "echo 'Found 30 errors.'; echo 'exit 1: scripts/lint.sh'; exit 1")
        r = self.run_suite("--lane", "gate", "--", "sh", "-c", gate)
        self.assertEqual(r.returncode, 1)
        out = r.stdout.decode()
        self.assertLess(len(out), 40000 + 3000)
        self.assertIn("FAIL: test_00", out)
        self.assertRegex(out, r"failing tests' sections \(\d+, \d+ more not shown\)")
        self.assertIn("exit 1: scripts/lint.sh", out)
        self.assertIn("exit 1: suite", out)
        self.assertIn("E501 Line too long (30)", out)
        self.assertIn("Found 30 errors.", out)
        lines = out.splitlines()
        self.assertTrue(lines[-2].startswith("ccp suite: st-") and lines[-1].startswith("ccp suite: full log:"))

    def test_long_lines_then_a_final_error_shows_the_final_error(self):
        script = ("import sys\nfor i in range(100): print(f'{i} ' + 'z' * 1900)\n"
                  "print('fatal: the final error', file=sys.stderr); sys.exit(2)\n")
        r = self.run_suite("--", PY, "-c", script, env={"PYTHONUNBUFFERED": "1"})
        self.assertEqual(r.returncode, 2)
        out = r.stdout.decode()
        self.assertIn("fatal: the final error", out)
        self.assertLess(len(out), 40000 + 3000)
        self.assertRegex(out, r"more cut to fit")

    def test_a_short_log_is_shown_whole_and_an_empty_one_says_so(self):
        script = ("import sys\nprint('child: Error: db refused', file=sys.stderr)\n"
                  "print('=' * 70); print('FAIL: test_x (m.T.test_x)'); print('-' * 70); print('boom')\n"
                  "print('-' * 70); print('Ran 1 test in 0s'); print(); print('FAILED (failures=1)'); sys.exit(1)\n")
        r = self.run_suite("--", PY, "-c", script, env={"PYTHONUNBUFFERED": "1"})
        out = r.stdout.decode()
        self.assertIn("the whole log (9 line(s)):", out)
        self.assertIn("child: Error: db refused", out)
        self.assertEqual(out.count("FAIL: test_x"), 1)
        r = self.run_suite("--", PY, "-c", "raise SystemExit(3)")
        self.assertEqual(r.returncode, 3)
        self.assertIn(b"ccp suite: the command printed nothing", r.stdout)

    def test_pruning_never_follows_a_symlinked_directory(self):
        old = time.time() - 15 * 86400
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        victim = outside / "implement-suite-st-9.log"
        victim.write_text("x")
        os.utime(victim, (old, old))
        (self.q / "runs").mkdir(parents=True, exist_ok=True)
        (self.q / "runs" / "linked-task").symlink_to(outside)
        self.assertEqual(suite.prune_logs(self.q, 14), 0)
        self.assertTrue(victim.exists())

    def test_old_logs_are_pruned_and_nothing_else(self):
        old = time.time() - 15 * 86400
        runs = self.q / "runs"
        keep, gone = [], []
        for rel, prune in (("0002-second/implement-suite-st-1.log", True), ("_suite-logs/st-2.log", True),
                           ("0002-second/implement-report.md", False), ("0002-second/notes.log", False),
                           ("_suite-logs/other.txt", False), ("0002-second/review-suite-st-3.log", False)):
            f = runs / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x")
            if not rel.endswith("st-3.log"):
                os.utime(f, (old, old))
            (gone if prune else keep).append(f)
        link = runs / "_suite-logs" / "st-link.log"
        link.symlink_to(keep[0])
        os.utime(link, (old, old), follow_symlinks=False)
        r = self.run_suite("--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([f.exists() for f in gone], [False, False])
        self.assertTrue(all(f.exists() for f in keep))
        self.assertTrue(link.is_symlink())
        self.assertTrue(_start_log(r.stdout).exists())  # this run's own log
        self.assertEqual(suite.prune_logs(self.q / "nonexistent", 14), 0)
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["suite"] = {"log_keep_days": 100}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        f = runs / "_suite-logs" / "st-4.log"
        f.write_text("x")
        os.utime(f, (old, old))
        self.run_suite("--", PY, "-c", "pass")
        self.assertTrue(f.exists())
        for bad in (0, "14", True):
            self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": {"log_keep_days": bad}}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)

    def test_a_terminal_defaults_to_full(self):
        a = type("A", (), {"output": None})()
        with mock.patch("os.isatty", lambda fd: True):
            self.assertEqual(suite._mode(a), "full")
        with mock.patch("os.isatty", lambda fd: False):
            self.assertEqual(suite._mode(a), "summary")
            a.output = "full"
            self.assertEqual(suite._mode(a), "full")
        with mock.patch("os.isatty", lambda fd: True):
            a.output = "summary"
            self.assertEqual(suite._mode(a), "summary")

    def test_config_refuses_bad_summary_patterns(self):
        for bad in ({"summary": {"failed_re": "no group"}}, {"summary": {"skipped_re": "("}},
                    {"summary": {"tail_lines": -1}}, {"summary": {"max_chars": 10}}, {"summary": {"other": 1}},
                    {"summary": "x"}, {"summary": {"failed_re": []}}):
            self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": bad}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": {"summary": {
            "failed_re": [r"(\d+) failed"], "show_re": "^summary", "tail_lines": 0}}}))
        self.assertEqual(config.load(self.main).suite["summary"]["tail_lines"], 0)


class GateFromSuite(SuiteFixture, unittest.TestCase):
    """`ccp verify record`: a gate run that names its `ccp suite run` takes its numbers from it."""

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)

    def record(self, gate_runs: list[dict]):
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", project_id="demo", head_sha="a" * 40)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        rec["gate"] = {"runs": gate_runs}
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))

    def gate(self, code: int = 0) -> str:
        self.tally()
        script = ("import sys; print('Ran 5 tests in 0.1s'); print('OK (skipped=2)');"
                  f"print('gate: 2 modules ran, 3 cached; 5 tests ran in 0 s'); sys.exit({code})")
        self.run_suite("--run", "0002-second/verify", "--lane", "gate", "--", PY, "-c", script)
        return self.rows()[-1]["suite_id"]

    def test_the_numbers_come_from_the_record(self):
        sid = self.gate()
        code, _, out, err = self.record([{"suite_id": sid}, {"command": "ccp docs check", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)
        run = json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"][0]
        self.assertEqual({k: run[k] for k in ("suite_id", "exit_code", "tests_run", "tests_skipped", "ran", "cached")},
                         {"suite_id": sid, "exit_code": 0, "tests_run": 5, "tests_skipped": 2, "ran": 2, "cached": 3})
        self.assertIn("ccp suite run --lane gate", run["command"])
        self.assertGreater(run["seconds"], 0)

    def test_a_given_number_stays_and_a_wrong_exit_code_or_unknown_id_is_refused(self):
        sid = self.gate()
        code, _, out, err = self.record([{"suite_id": sid, "command": "scripts/gate.sh main", "tests_run": 99}])
        self.assertEqual(code, 0, out + err)
        run = json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"][0]
        self.assertEqual((run["command"], run["tests_run"], run["exit_code"]), ("scripts/gate.sh main", 99, 0))
        code, _, _, err = self.record([{"suite_id": sid, "exit_code": 1}])
        self.assertEqual(code, 1)
        self.assertIn("differs from the recorded 0", err)
        code, _, _, err = self.record([{"suite_id": "st-nope"}])
        self.assertEqual(code, 1)
        self.assertIn("no such suite run", err)

    def test_only_the_latest_verify_runs_bound_suite_runs_count(self):
        self.run_suite("--lane", "gate", "--", PY, "-c", "print('Ran 1 test in 0s')")  # unbound
        unbound = self.rows()[-1]["suite_id"]
        code, _, _, err = self.record([{"suite_id": unbound}])
        self.assertEqual(code, 1)
        self.assertIn("bound to no run", err)
        old = self.gate()
        rec = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        rec.update(reported_at="2026-10-22T00:00:00Z", outcome="done")
        (self.q / "runs/0002-second/verify.json").write_text(json.dumps(rec))
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "b" * 40,
                                     "--note", "a second round with no fix since")
        self.assertEqual(code, 0, out + err)
        code, _, _, err = self.record([{"suite_id": old}])
        self.assertEqual(code, 1)
        self.assertIn("an earlier verify round; 0002-second's latest verify run is 0002-second/verify-2", err)
        self.run_suite("--run", "0002-second/verify-2", "--lane", "gate", "--", PY, "-c", "print('Ran 1 test in 0s')")
        code, _, out, err = self.record([{"suite_id": self.rows()[-1]["suite_id"]}])
        self.assertEqual(code, 0, out + err)

    def test_another_phases_suite_run_is_refused(self):
        suite._append(self.q, {"op": "started", "suite_id": "st-impl", "at": "2026-10-22T00:00:00Z",
                               "run_id": "0002-second/implement", "task_id": "0002-second", "phase": "implement"})
        suite._append(self.q, {"op": "ended", "suite_id": "st-impl", "at": "2026-10-22T00:01:00Z", "exit_code": 0,
                               "seconds": 60, "tests": 3, "interrupted": None})
        code, _, _, err = self.record([{"suite_id": "st-impl"}])
        self.assertEqual(code, 1)
        self.assertIn("not a verify run of 0002-second", err)

    def test_a_failed_gate_run_fills_a_failing_exit_code(self):
        sid = self.gate(code=1)
        code, _, out, err = self.record([{"suite_id": sid}])
        self.assertEqual(code, 1, out + err)  # an approve on a failed gate: the filled exit code says so
        self.assertIn("exited 1", err)

    def cold_gate_task(self) -> None:
        """The product accepts its cache's hits and 0002's gate is cold (§15.3)."""
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["verify"] = {"accept_cache": {"max_age_days": 3, "cold_tasks": []}}
        p.write_text(json.dumps(cfg))
        t = self.runner / "docs/delivery/tasks/0002-second.md"
        t.write_text(t.read_text().replace("status: pending", "status: pending\ngate: cold", 1))

    def gate_cached(self, cached: int) -> str:
        self.tally()
        script = f"print('Ran 5 tests in 0.1s'); print('OK'); print('gate: 5 modules ran, {cached} cached; 5 tests ran in 0 s')"
        self.run_suite("--run", "0002-second/verify", "--lane", "gate", "--", PY, "-c", script)
        return self.rows()[-1]["suite_id"]

    def test_a_recorded_run_with_nothing_cached_counts_as_cold(self):
        sid = self.gate_cached(0)
        self.cold_gate_task()
        code, _, out, err = self.record([{"suite_id": sid}, {"command": "ccp docs check", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)
        runs_ = json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"]
        self.assertEqual((runs_[0]["cached"], runs_[0]["cold"]), (0, True))
        self.assertNotIn("cold", runs_[1])  # a run citing no suite run is not marked

    def test_a_recorded_run_with_cached_units_is_not_cold(self):
        sid = self.gate_cached(3)
        self.cold_gate_task()
        code, _, _, err = self.record([{"suite_id": sid}])
        self.assertEqual(code, 1)
        self.assertIn("gate is cold", err)

    def test_the_verifiers_own_cold_stays(self):
        sid = self.gate_cached(0)
        code, _, out, err = self.record([{"suite_id": sid, "cold": False}])
        self.assertEqual(code, 0, out + err)
        run = json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"][0]
        self.assertIs(run["cold"], False)


class Digest(unittest.TestCase):
    def digest(self, text: bytes, **over) -> dict:
        import tempfile
        from ccp.config import SUITE_SUMMARY_DEFAULTS
        f = tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(os.unlink, f.name)
        f.write(text)
        f.close()
        scfg = suite._summary_cfg(None)
        scfg.update(over)
        self.assertEqual(set(scfg), set(SUITE_SUMMARY_DEFAULTS))
        return suite.digest(Path(f.name), scfg, re.compile(rb"^Ran (\d+) tests? in "))

    def test_a_section_ends_at_the_rule_before_the_count(self):
        eq, dash = b"=" * 70, b"-" * 70
        text = b"\n".join([b"test_a ... FAIL", eq, b"FAIL: test_a (m.T.test_a)", dash, b"Traceback", b"  line",
                           dash, b"not the end", eq, b"ERROR: test_b (m.T.test_b)", dash, b"boom", b"", dash,
                           b"Ran 2 tests in 0.1s", b"", b"FAILED (failures=1, errors=1)"]) + b"\n"
        d = self.digest(text)
        bodies = [b for _s, _e, b in d["sections"]]
        self.assertEqual(len(bodies), 2)
        self.assertEqual(bodies[0][1], "FAIL: test_a (m.T.test_a)")
        self.assertIn("not the end", bodies[0])
        self.assertEqual(bodies[1][-2:], ["boom", ""])
        self.assertNotIn("Ran 2 tests in 0.1s", bodies[1])

    def test_an_over_long_line_is_cut_and_reading_is_bounded(self):
        d = self.digest(b"x" * (suite.LINE_MAX * 3) + b"\nlast\n", tail_lines=2)
        self.assertEqual([ln for _i, ln in d["tail"]][-1], "last")
        self.assertEqual(d["lines"], 2)
        self.assertLessEqual(len(d["tail"][0][1]), suite.SHOW_LINE_MAX + 40)


if __name__ == "__main__":
    unittest.main()


DUMP_ENV = "import json, os, sys; json.dump(dict(os.environ), open(sys.argv[1], 'w'))"


SUITE_VARS = ("CCP_SUITE_ID", "CCP_SUITE_RESULT")


class CallerEnvironment(SuiteFixture, unittest.TestCase):
    """§14.2: the command sees the caller's environment plus CCP_SUITE_ID and CCP_SUITE_RESULT, and
    nothing else, so a test cache that hashes the environment (less those two) hits from a plain shell
    and from `ccp suite run` alike (`bin/ccp` once put the plane on PYTHONPATH)."""

    def child_env(self, env: dict, cwd: Path | None = None) -> dict:
        out = Path(self._tmp.name) / "child-env.json"
        r = subprocess.run([CCP, "suite", "run", "--lane", "part", "--", PY, "-c", DUMP_ENV, str(out)],
                           cwd=cwd or self.runner, env=env, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(out.read_text())

    def caller(self, **extra: str) -> dict:
        e = {k: v for k, v in os.environ.items() if k not in SUITE_VARS}
        e.pop("PYTHONPATH", None)
        return {**e, **extra}

    def test_the_child_gets_the_callers_environment_and_ccp_suite_id_only(self):
        for parent in (self.caller(), self.caller(PYTHONPATH="/elsewhere/lib"), self.caller(PYTHONPATH="")):
            with self.subTest(pythonpath=parent.get("PYTHONPATH")):
                child = self.child_env(parent)
                self.assertRegex(child.pop("CCP_SUITE_ID"), r"^st-")
                self.assertRegex(child.pop("CCP_SUITE_RESULT"), r"ccp-suite-result-st-[^/]+\.json$")
                self.assertEqual(child, parent)
        self.assertEqual([x["op"] for x in self.rows()].count("ended"), 3)  # recorded, all the same

    def test_outside_a_product_the_unrecorded_run_is_the_same(self):
        parent = self.caller(PYTHONPATH="/elsewhere/lib")
        child = self.child_env(parent, cwd=Path(self._tmp.name))
        for k in SUITE_VARS:
            child.pop(k)
        self.assertEqual(child, parent)

    def test_a_queue_root_ccp_found_from_the_binding_stays_ccps(self):
        out = Path(self._tmp.name) / "child-env.json"
        a = type("A", (), {"lane": "part", "phase": None, "run": None, "task": None, "root": str(self.runner)})()
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "CCP_NO_BINDING_QUEUE")}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("ccp.cli.binding_queue_root", return_value=str(self.q)):
            code = suite.main_run(a, [PY, "-c", DUMP_ENV, str(out)])
            self.assertEqual(os.environ.get("QUEUE_ROOT"), str(self.q))  # ccp recorded against it
        self.assertEqual(code, 0)
        child = json.loads(out.read_text())
        self.assertNotIn("QUEUE_ROOT", child)
        self.assertEqual([x["op"] for x in self.rows()], ["started", "ended"])

    def test_bin_ccp_sets_no_variable(self):
        text = (PLANE / "bin" / "ccp").read_text()
        self.assertNotIn("PYTHONPATH=", text)
        self.assertNotIn("os.environ", text)


WRITE_RESULT = ("import json, os, sys; print('Ran 99 tests in 0.1s'); "
                "json.dump(json.loads(sys.argv[1]), open(os.environ['CCP_SUITE_RESULT'], 'w'))")


class ResultContract(SuiteFixture, unittest.TestCase):
    """§14: a gate that writes CCP_SUITE_RESULT is the record; without one, the output is read."""

    def test_the_result_file_is_authoritative_and_removed(self):
        res = {"tests": 12, "ran": 4, "cached": 30, "cached_tests": 200, "skipped": 1,
               "failures": [], "extra": {"note": "never recorded"}}
        r = self.run_suite("--lane", "gate", "--", PY, "-c", WRITE_RESULT, json.dumps(res))
        self.assertEqual(r.returncode, 0, r.stderr)
        ended = self.rows()[-1]
        self.assertEqual({k: ended[k] for k in ("tests", "ran", "cached", "cached_tests", "skipped", "counts_from")},
                         {"tests": 12, "ran": 4, "cached": 30, "cached_tests": 200, "skipped": 1, "counts_from": "result"})
        self.assertNotIn("never recorded", json.dumps(self.rows()))
        self.assertFalse(list(Path(tempfile.gettempdir()).glob(f"ccp-suite-result-{ended['suite_id']}.json")))

    def test_failure_ids_are_shown_and_counted_never_recorded(self):
        res = {"tests": 3, "failures": [{"id": "pkg.test_a", "message": "boom"}, {"id": "pkg.test_b"}]}
        r = self.run_suite("--lane", "gate", "--", PY, "-c", WRITE_RESULT + "; sys.exit(1)", json.dumps(res))
        self.assertEqual(r.returncode, 1)
        self.assertIn("failing (from the gate's result): pkg.test_a, pkg.test_b", r.stdout.decode())
        ended = self.rows()[-1]
        self.assertEqual(ended["failed"], 2)
        self.assertNotIn("pkg.test_a", json.dumps(self.rows()))

    def test_no_result_file_reads_the_output(self):
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print('Ran 7 tests in 0.1s')")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.rows()[-1]["tests"], self.rows()[-1]["counts_from"]), (7, "output"))

    def test_a_bad_result_file_warns_and_the_output_stands(self):
        for bad in ('"tests": "many"', '"ran": -1', '"note": 1'):
            with self.subTest(bad=bad):
                script = ("import os; print('Ran 5 tests in 0.1s'); "
                          f"open(os.environ['CCP_SUITE_RESULT'], 'w').write('{{{bad}}}')")
                r = self.run_suite("--lane", "gate", "--", PY, "-c", script)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn("the gate's result file was not used", r.stdout.decode())
                row = self.rows()[-1]
                self.assertEqual((row["tests"], row["counts_from"]), (5, "output"))
                self.assertTrue(row["result_problem"])

    def test_the_bad_result_line_survives_another_warning(self):
        # a bad --phase is the run's one `ccp suite:` warning; the result's problem still shows
        script = "import os; print('Ran 1 test in 0.1s'); open(os.environ['CCP_SUITE_RESULT'], 'w').write('nope')"
        r = self.run_suite("--phase", "nonsense", "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("ccp suite:", r.stderr.decode())
        self.assertIn("the gate's result file was not used (not JSON", r.stdout.decode())

    def test_a_counter_the_result_leaves_out_is_absent(self):
        res = {"ran": 2, "cached": 3}
        r = self.run_suite("--lane", "gate", "--", PY, "-c",
                           WRITE_RESULT.replace("Ran 99 tests", "Ran 9 tests") + "; print('OK (skipped=4)')",
                           json.dumps(res))
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.rows()[-1]
        self.assertEqual((row["tests"], row["skipped"], row["ran"], row["cached"]), (None, None, 2, 3))

    def test_a_symlinked_or_huge_result_is_refused(self):
        target = Path(self._tmp.name) / "elsewhere.json"
        target.write_text('{"tests": 1}')
        p = Path(self._tmp.name) / "link.json"
        p.symlink_to(target)
        res, problem = suite.read_result(p)
        self.assertIsNone(res)
        self.assertIn("symlink", problem)
        self.assertTrue(target.exists())  # the link is removed, never its target
        big = Path(self._tmp.name) / "big.json"
        big.write_text('{"tests": 1, "extra": "' + "x" * (suite.RESULT_MAX + 10) + '"}')
        self.assertEqual(suite.read_result(big), (None, "larger than 1 MB"))

    def test_read_result_validates(self):
        p = Path(self._tmp.name) / "r.json"
        self.assertEqual(suite.read_result(p), (None, None))
        p.write_text('{"tests": 3, "cached": 2, "seconds": 1.5}')
        self.assertEqual(suite.read_result(p), ({"tests": 3, "cached": 2}, None))
        self.assertFalse(p.exists())
        p.write_text("[]")
        self.assertEqual(suite.read_result(p)[1], "not a JSON object")

    def test_the_schema_names_every_counter_read(self):
        schema = json.loads((PLANE / "contracts/suite_result.schema.json").read_text())
        self.assertTrue(set(suite.RESULT_INTS) | {"seconds", "failures"} <= set(schema["properties"]))


class ResultForTheVerifier(SuiteFixture, unittest.TestCase):
    record = GateFromSuite.record

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)

    def test_accept_cache_counts_come_from_the_result(self):
        res = {"tests": 6, "ran": 2, "cached": 40}
        self.run_suite("--run", "0002-second/verify", "--lane", "gate", "--", PY, "-c", WRITE_RESULT, json.dumps(res))
        sid = self.rows()[-1]["suite_id"]
        code, _, out, err = self.record([{"suite_id": sid}, {"command": "ccp docs check", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)
        run = json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"][0]
        self.assertEqual((run["tests_run"], run["ran"], run["cached"]), (6, 2, 40))


class ReviewFixes(SuiteFixture, unittest.TestCase):
    def test_the_new_knob_name_wins_and_the_old_one_is_flagged(self):
        self.tally({"modules_ran_re": r"^m: (\d+) old", "ran_re": r"^m: \d+ old, (\d+) new"})
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "print('Ran 1 test in 0.1s'); print('m: 7 old, 3 new')")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.rows()[-1]["ran"], 3)
        c = config.load(self.runner)
        self.assertEqual(c.suite_aliases_ignored, ("modules_ran_re",))
        from ccp import tasklog
        self.assertTrue(any("suite.summary.modules_ran_re is ignored" in w for w in tasklog.warnings(c)))

    def test_usual_seconds_reads_an_unlabelled_run_as_the_full_roles_lane(self):
        rows = [{"op": "started", "suite_id": "s1", "lane": None}, {"op": "ended", "suite_id": "s1", "exit_code": 0, "seconds": 8},
                {"op": "started", "suite_id": "s2", "lane": "ci"}, {"op": "ended", "suite_id": "s2", "exit_code": 0, "seconds": 4}]
        (self.q / "runs").mkdir(parents=True, exist_ok=True)
        (self.q / "runs/_suites.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
        self.assertEqual(suite.usual_seconds(self.q, "ci", default="ci"), 8.0)  # median of 4 and 8: index 1
        self.assertEqual(suite.usual_seconds(self.q, None), 8.0)

    def test_two_roles_may_not_share_a_lane(self):
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg.setdefault("suite", {})["roles"] = {"gate": "full"}
        p.write_text(json.dumps(cfg))
        with self.assertRaises(config.ConfigError):
            config.load(self.runner)

    def test_no_module_wording_is_left_in_the_contracts_and_prompts(self):
        pc = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        self.assertNotIn("modules_ran", pc["properties"]["verify"]["properties"]["accept_cache"]["description"])
        vs = json.loads((PLANE / "contracts/verification.schema.json").read_text())
        self.assertNotIn("modules_ran", vs["properties"]["gate"]["properties"]["runs"]["items"]["properties"]["suite_id"]["description"])
        self.assertNotIn("modules ran", (PLANE / "templates/prompts/review.md").read_text())


class LaneRoles(SuiteFixture, unittest.TestCase):
    def test_roles_rename_the_lanes_in_prompts_and_defaults(self):
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg.setdefault("suite", {})["roles"] = {"gate": "formal"}
        p.write_text(json.dumps(cfg))
        c = config.load(self.runner)
        self.assertEqual(c.suite["roles"], {"full": "full", "gate": "formal", "part": "part"})
        from ccp import prompt as prompt_mod
        self.assertIn("`--lane formal` for the formal gate", prompt_mod.suite_lanes(c, "verify"))
        cfg["suite"]["roles"] = {"gate": "Not A Lane"}
        p.write_text(json.dumps(cfg))
        with self.assertRaises(config.ConfigError):
            config.load(self.runner)

    def test_the_mutation_runs_name_the_part_roles_lane(self):
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg.setdefault("suite", {})["roles"] = {"part": "subset"}
        p.write_text(json.dumps(cfg))
        self.ccp("tasks", "claim", "0002")
        for phase, marker in (("review", "and any mutation run"), ("verify", "is mutation-tested")):
            code, _, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", "a" * 40)
            self.assertEqual(code, 0, out + err)
            text = (self.q / f"prompts/0002-second/{phase}-prompt.md").read_text()
            line = next(ln for ln in text.splitlines() if marker in ln)
            self.assertIn("`--lane subset`", line, phase)
