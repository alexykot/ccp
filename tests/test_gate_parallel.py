"""The plane's parallel gate (SPEC §14.3, ENGINEERING E1, E2): scripts/gate.sh runs each test module in
its own process, GATE_WORKERS at a time, fails when any module fails, keeps the `state/*` check after
them, and writes each module's seconds and tests to the result file, which `ccp suite run` records."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import suite
from tests.suite_stages_fixture import StagedFixture, _shell_py
from tests.gate_parallel_fixture import GateFixture, MORE, OK, ROOT


# Two modules that each wait for the other to have started: they pass only when run at the same time.
MEET = """
import os, time, unittest
from pathlib import Path
D = Path(os.environ["MEET_DIR"])
class M(unittest.TestCase):
    def test_meet(self):
        (D / "{me}").touch()
        end = time.monotonic() + 20
        while not (D / "{other}").exists() and time.monotonic() < end:
            time.sleep(0.05)
        self.assertTrue((D / "{other}").exists())
"""
# A module that writes when it started and ended, for checking that a SERIAL one runs alone.
STAMP = """
import os, time, unittest
from pathlib import Path
D = Path(os.environ["MEET_DIR"])
class S(unittest.TestCase):
    def test_stamp(self):
        (D / "{me}.start").write_text(repr(time.time()))
        time.sleep(0.3)
        (D / "{me}.end").write_text(repr(time.time()))
"""


class TheGateRunsModulesApart(GateFixture):
    def test_a_passing_run_lists_every_module_with_its_seconds_and_tests(self):
        self.module("test_ok", OK)
        self.module("test_more", MORE.format(lhs=3))
        r = self.gate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        res = self.read()
        self.assertEqual((res["tests"], res["skipped"], res["failed"]), (5, 1, 0))
        mods = {m["name"]: m for m in res["modules"]}
        self.assertEqual(set(mods), {"tests.test_ok", "tests.test_more"})
        self.assertEqual((mods["tests.test_ok"]["tests"], mods["tests.test_more"]["tests"]), (2, 3))
        self.assertTrue(all(isinstance(m["seconds"], float) and m["seconds"] >= 0 for m in mods.values()))
        self.assertEqual(sum(m["tests"] for m in res["modules"]), res["tests"])

    def test_modules_run_at_the_same_time(self):
        self.module("test_left", MEET.format(me="left", other="right"))
        self.module("test_right", MEET.format(me="right", other="left"))
        r = self.gate("2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read()["tests"], 2)

    def test_a_failing_module_fails_the_gate_naming_the_test_and_its_module(self):
        self.module("test_ok", OK)
        self.module("test_more", MORE.format(lhs=4))
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("FAIL: test_c (tests.test_more.B.test_c)", r.stdout)
        res = self.read()
        self.assertEqual((res["tests"], res["failed"]), (5, 1))
        self.assertEqual([f["id"] for f in res["failures"]], ["tests.test_more.B.test_c"])
        self.assertEqual({m["name"] for m in res["modules"]}, {"tests.test_ok", "tests.test_more"})

    def test_a_module_that_does_not_import_fails_under_its_own_name(self):
        self.module("test_ok", OK)
        self.module("test_broken", "import no_such_module_anywhere\n")
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        res = self.read()
        self.assertEqual([f["id"] for f in res["failures"]], ["tests.test_broken"])
        self.assertEqual(res["failed"], 1)

    def test_a_module_that_dies_without_naming_a_test_fails_under_its_own_name(self):
        self.module("test_ok", OK)
        self.module("test_dies", "import os\nos._exit(3)\n")
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        res = self.read()
        self.assertEqual(([f["id"] for f in res["failures"]], res["tests"]), (["tests.test_dies"], 2))
        self.assertIn({"name": "tests.test_dies", "seconds": mock.ANY, "tests": 0}, res["modules"])

    def test_a_leftover_state_branch_still_fails_a_passing_run(self):
        self.module("test_ok", OK)
        subprocess.run(["git", "-C", str(self.repo), "branch", "state/left"], check=True)
        r = self.gate()
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("state/left", r.stderr)

    def test_a_serial_module_runs_alone_after_the_others(self):
        for name in ("a", "b", "c"):
            self.module(f"test_{name}", STAMP.format(me=name))
        p = self.repo / "scripts" / "gate_parallel.py"
        p.write_text(p.read_text().replace("SERIAL: list[str] = []", 'SERIAL: list[str] = ["tests.test_a"]'))
        r = self.gate("3")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        alone = float((self.meet / "a.start").read_text())
        self.assertTrue(all(float((self.meet / f"{n}.end").read_text()) <= alone for n in ("b", "c")))

    def test_a_bad_worker_count_runs_nothing_and_exits_2(self):
        self.module("test_ok", OK)
        for bad in ("0", "x", "-2"):
            with self.subTest(bad=bad):
                r = self.gate(bad)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("GATE_WORKERS", r.stdout)  # gate.sh tees both streams
                self.assertEqual(self.read()["tests"], 0)


class GivenNamesTheGateRunsOnlyThose(GateFixture):
    def setUp(self):
        super().setUp()
        self.module("test_ok", OK)
        self.module("test_more", MORE.format(lhs=3))
        self.module("test_other", MORE.format(lhs=4))  # fails if it runs

    def ran(self, r: subprocess.CompletedProcess[str], state: str = "") -> set[str]:
        return {ln.split()[2].rstrip(":") for ln in r.stdout.splitlines()
                if ln.startswith("gate module ") and ln.split()[3].startswith(state)}

    def test_it_runs_the_named_modules_and_no_other(self):
        r = self.gate(names=("tests.test_ok", "tests.test_more"), GATE_COLD="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ran(r), {"tests.test_ok", "tests.test_more"})
        self.assertIn("gate: 2 modules, ran 2,", r.stdout)
        self.assertEqual({m["name"] for m in self.read()["modules"]}, {"tests.test_ok", "tests.test_more"})

    def test_named_modules_run_at_the_same_time(self):
        self.module("test_left", MEET.format(me="left", other="right"))
        self.module("test_right", MEET.format(me="right", other="left"))
        r = self.gate("2", names=("tests.test_left", "tests.test_right"), GATE_COLD="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.read()["tests"], 2)

    def test_an_unknown_name_runs_nothing_and_exits_2_naming_it(self):
        for bad in ("tests.test_no_such", "test_ok", "tests/test_ok.py"):
            with self.subTest(bad=bad):
                r = self.gate(names=("tests.test_ok", bad), GATE_COLD="1")
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(bad, r.stdout)  # gate.sh tees both streams
                self.assertEqual((self.ran(r), self.read()["tests"]), (set(), 0))

    def test_a_part_runs_cache_entry_is_the_full_runs_and_back(self):
        (self.repo / ".gitignore").write_text("__pycache__/\n")  # as the plane's own repo has it
        # test_more names test_ok, so test_ok is shared: a run of either alone must still find it in the suite
        self.module("test_more", "from tests import test_ok  # noqa: F401\n" + MORE.format(lhs=3))
        r = self.gate(names=("tests.test_ok",))
        self.assertEqual((r.returncode, self.ran(r, "ok")), (0, {"tests.test_ok"}), r.stdout + r.stderr)
        r = self.gate()  # every module: the one the part run passed is served from the cache
        self.assertEqual(self.ran(r, "cached"), {"tests.test_ok"}, r.stdout)
        self.assertEqual(self.ran(r, "ok"), {"tests.test_more"}, r.stdout)
        r = self.gate(names=("tests.test_more",))  # and the full run's entry serves a part run
        self.assertEqual((r.returncode, self.ran(r, "cached"), self.ran(r, "ok")), (0, {"tests.test_more"}, set()))


class TheWorkerCount(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("gate_parallel_under_test", ROOT / "scripts/gate_parallel.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_it_defaults_to_the_cpu_count_and_reads_the_variable(self):
        gp = self.load()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GATE_WORKERS", None)
            with mock.patch.object(gp.os, "cpu_count", return_value=7):
                self.assertEqual(gp.workers(), 7)
        with mock.patch.dict(os.environ, {"GATE_WORKERS": "3"}):
            self.assertEqual(gp.workers(), 3)

    def test_it_runs_every_test_module_of_the_repo(self):
        names = self.load().modules()
        self.assertEqual(sorted(names), sorted(f"tests.{p.stem}" for p in (ROOT / "tests").glob("test_*.py")))


    def test_names_select_from_the_suite_in_its_order_and_every_unknown_one_is_named(self):
        gp = self.load()
        suite_ = ["tests.test_big", "tests.test_mid", "tests.test_small"]
        self.assertEqual(gp.selected(suite_, []), suite_)
        self.assertEqual(gp.selected(suite_, ["tests.test_small", "tests.test_big", "tests.test_small"]),
                         ["tests.test_big", "tests.test_small"])
        with self.assertRaises(ValueError) as e:
            gp.selected(suite_, ["tests.test_x", "tests.test_mid", "tests.test_y"])
        self.assertIn("tests.test_x, tests.test_y", str(e.exception))

    def test_a_modules_count_sums_its_ran_lines_and_is_its_share_of_the_total(self):
        gp = self.load()
        output = "Ran 3 tests in 0.1s\n\nOK\nRan 4 tests in 0.2s\n\nOK\n"
        done = subprocess.CompletedProcess([], 0, stdout=output)
        printed = io.StringIO()
        with mock.patch.object(gp.subprocess, "run", return_value=done), mock.patch.object(gp.sys, "stdout", printed):
            self.assertEqual(gp.run_one("tests.test_x")[3], 7)
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log"
            log.write_text(printed.getvalue())
            out = json.loads(subprocess.run([sys.executable, str(ROOT / "scripts/gate_result.py"), str(log), "1"],
                                            capture_output=True, text=True, check=True).stdout)
        self.assertEqual((out["tests"], [m["tests"] for m in out["modules"]]), (7, [7]))

class TheResultFromALog(unittest.TestCase):
    def parse(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log"
            log.write_text(text)
            return json.loads(subprocess.run([sys.executable, str(ROOT / "scripts/gate_result.py"), str(log), "9"],
                                             capture_output=True, text=True, check=True).stdout)

    def test_the_counts_are_summed_over_every_module(self):
        out = self.parse("\n".join([
            "Ran 4 tests in 0.1s", "", "OK (skipped=1)", "gate module tests.test_a: ok, 1.25 s, 4 tests",
            "FAIL: test_x (tests.test_b.C.test_x)", "Ran 6 tests in 0.2s", "", "FAILED (failures=1, skipped=2)",
            "gate module tests.test_b: FAILED (exit 1), 12.50 s, 6 tests", ""]))
        self.assertEqual((out["tests"], out["skipped"], out["failed"]), (10, 3, 1))
        self.assertEqual(out["modules"], [{"name": "tests.test_a", "seconds": 1.25, "tests": 4},
                                          {"name": "tests.test_b", "seconds": 12.5, "tests": 6}])

    def test_a_log_with_no_module_lines_carries_no_modules(self):
        self.assertNotIn("modules", self.parse("Ran 2 tests in 0.1s\n\nOK\n"))


class TheRunRecordsTheModules(StagedFixture, unittest.TestCase):
    def gate(self, *results: dict) -> dict:
        write = "import os, sys; open(os.environ['CCP_SUITE_RESULT'], 'w').write(sys.argv[1])"
        self.lanes({"fast": [{"name": f"s{i}", "cmd": f"{_shell_py(write)} {shlex.quote(json.dumps(r))}"}
                             for i, r in enumerate(results)]})
        r = self.run_suite("--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.ended()

    def test_the_ended_row_keeps_the_modules_and_the_event_does_not(self):
        mods = [{"name": "tests.test_a", "seconds": 3.5, "tests": 4}, {"name": "tests.test_b", "seconds": 1, "tests": 2}]
        row = self.gate({"tests": 6, "modules": mods})
        self.assertEqual(row["modules"], [{"name": "tests.test_a", "seconds": 3.5, "tests": 4},
                                          {"name": "tests.test_b", "seconds": 1.0, "tests": 2}])
        self.assertEqual(suite.fold(self.q)[-1]["modules"], row["modules"])
        ev = [e for e in self.events() if e["type"] == "suite"][-1]["payload"]
        self.assertNotIn("modules", ev)

    def test_every_stages_modules_are_kept_in_order(self):
        row = self.gate({"tests": 1, "modules": [{"name": "x", "seconds": 1, "tests": 1}]},
                        {"tests": 2, "modules": [{"name": "y", "seconds": 2, "tests": 2}]})
        self.assertEqual([m["name"] for m in row["modules"]], ["x", "y"])

    def test_a_result_without_modules_records_none(self):
        self.assertNotIn("modules", self.gate({"tests": 3}))

    def test_read_result_keeps_only_whole_entries(self):
        p = Path(self._tmp.name) / "r.json"
        p.write_text(json.dumps({"tests": 3, "modules": [
            {"name": "ok", "seconds": 1.23456, "tests": 3}, {"name": "", "seconds": 1, "tests": 1},
            {"name": "neg", "seconds": -1, "tests": 1}, {"name": "flag", "seconds": True, "tests": 1},
            {"name": "notests", "seconds": 1}, {"name": "n" * 300, "seconds": 0, "tests": 0}, "junk"]}))
        res, problem = suite.read_result(p)
        self.assertIsNone(problem)
        self.assertEqual(res["modules"], [{"name": "ok", "seconds": 1.235, "tests": 3},
                                          {"name": "n" * 200, "seconds": 0.0, "tests": 0}])
        p.write_text('{"tests": 3, "modules": {"a": 1}}')
        self.assertEqual(suite.read_result(p), (None, "`modules` is not a list"))

    def test_the_schema_names_the_modules_field(self):
        props = json.loads((ROOT / "contracts/suite_result.schema.json").read_text())["properties"]
        self.assertEqual(props["modules"]["items"]["required"], ["name", "seconds", "tests"])


if __name__ == "__main__":
    unittest.main()
