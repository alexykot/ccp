"""`ccp suite run` of a staged lane (SPEC §14.2): plane.json names a lane's stages, `ccp` runs them in
order, times each, stops at the first failure and records which stage failed; the gate role's
staged lane ends with the plane's doc checks as their own stage."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, suite
from tests.test_suite import CCP, PY, SuiteFixture, ccp_proc


def _shell_py(code: str) -> str:
    """A stage command that runs a line of Python (quoted for the shell)."""
    return f"{PY} -c {json.dumps(code)}"


class StagedFixture(SuiteFixture):
    def lanes(self, lanes: dict, **suite_extra) -> None:
        """Set the runner checkout's plane.json suite lanes."""
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": lanes, **suite_extra}
        p.write_text(json.dumps(cfg))

    def ended(self) -> dict:
        return [x for x in self.rows() if x["op"] == "ended"][-1]


class StagesRunInOrder(StagedFixture, unittest.TestCase):
    def test_a_failing_stage_stops_the_run_and_is_named(self):
        later = self.runner / "later-ran"
        self.lanes({"gate": [
            {"name": "lint", "cmd": _shell_py("print('lint ok')")},
            {"name": "tests", "cmd": _shell_py("import sys, time; time.sleep(0.2); print('Ran 3 tests in 0.2s'); "
                                               "sys.exit(4)")},
            {"name": "e2e", "cmd": f"touch {later}"},
        ]})
        r = self.run_suite("--lane", "gate")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertFalse(later.exists())
        row = self.ended()
        self.assertEqual([(s["name"], s["exit_code"]) for s in row["stages"]], [("lint", 0), ("tests", 4)])
        self.assertEqual(row["failed_stage"], "tests")
        self.assertTrue(all(isinstance(s["seconds"], float) for s in row["stages"]))
        self.assertGreaterEqual(row["stages"][1]["seconds"], 0.2)
        self.assertEqual((row["exit_code"], row["tests"]), (4, 3))
        ev = [e for e in self.events() if e["type"] == "suite"][-1]["payload"]
        self.assertEqual((ev["failed_stage"], [s["name"] for s in ev["stages"]]), ("tests", ["lint", "tests"]))
        stage_lines = [ln for ln in r.stdout.decode().splitlines() if ": stages: " in ln]
        self.assertEqual(len(stage_lines), 1)
        self.assertIn("e2e", stage_lines[0].split("not run:")[1])

    def test_the_gate_ends_with_the_plane_doc_checks_as_their_own_stage(self):
        self.lanes({"gate": [{"name": "lint", "cmd": "true"},
                             {"name": "tests", "cmd": _shell_py("print('Ran 2 tests in 0.1s')")}]})
        r = self.run_suite("--lane", "gate")
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        row = self.ended()
        self.assertEqual([(s["name"], s["exit_code"]) for s in row["stages"]],
                         [("lint", 0), ("tests", 0), (config.PLANE_DOCS_STAGE, 0)])
        self.assertIsNone(row["failed_stage"])
        self.assertEqual(row["tests"], 2)

    def test_a_doc_check_failure_fails_its_stage(self):
        self.lanes({"gate": [{"name": "tests", "cmd": "true"}]})
        (self.runner / "docs/delivery/tasks/0003-bad.md").write_text("no frontmatter here\n")
        r = self.run_suite("--lane", "gate")
        self.assertNotEqual(r.returncode, 0)
        row = self.ended()
        self.assertEqual(row["failed_stage"], config.PLANE_DOCS_STAGE)
        self.assertEqual([s["name"] for s in row["stages"]], ["tests", config.PLANE_DOCS_STAGE])

    def test_a_staged_lane_other_than_the_gate_gets_no_doc_stage(self):
        self.lanes({"gate": ["true"], "fast": [{"name": "unit", "cmd": "true"}, {"name": "lint", "cmd": "true"}]})
        r = self.run_suite("--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([s["name"] for s in self.ended()["stages"]], ["unit", "lint"])

    def test_a_renamed_gate_role_takes_the_doc_stage(self):
        self.lanes({"verify": [{"name": "unit", "cmd": "true"}], "gate": [{"name": "unit", "cmd": "true"}]},
                   roles={"gate": "verify"})
        self.assertEqual(self.run_suite("--lane", "gate").returncode, 0)
        self.assertEqual([s["name"] for s in self.ended()["stages"]], ["unit"])
        self.assertEqual(self.run_suite("--lane", "verify").returncode, 0)
        self.assertEqual([s["name"] for s in self.ended()["stages"]], ["unit", config.PLANE_DOCS_STAGE])

    def test_stages_run_from_the_root_through_the_shell(self):
        out = self.runner / "where"
        self.lanes({"fast": [{"name": "pwd", "cmd": f"pwd > {out} && test -f docs/delivery/plane.json"}]})
        (self.runner / "sub").mkdir()
        r = ccp_proc(self.runner / "sub", "suite", "run", "--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(out.read_text().strip()).resolve(), self.runner.resolve())

    def test_the_started_row_names_no_command(self):
        self.lanes({"fast": [{"name": "unit", "cmd": "echo SECRET-STAGE-ARG"}, {"name": "lint", "cmd": "true"}]})
        self.assertEqual(self.run_suite("--lane", "fast").returncode, 0)
        started = [x for x in self.rows() if x["op"] == "started"][-1]
        self.assertEqual((started["cmd"], started["argc"]), ("stages", 2))
        self.assertNotIn("SECRET-STAGE-ARG", (self.q / "runs" / "_suites.jsonl").read_text())

    def test_stage_results_are_summed(self):
        write = ("import json, os, sys; json.dump({'tests': int(sys.argv[1]), 'failures': []}, "
                 "open(os.environ['CCP_SUITE_RESULT'], 'w'))")
        self.lanes({"fast": [{"name": "a", "cmd": f"{_shell_py(write)} 2"},
                             {"name": "b", "cmd": "true"},
                             {"name": "c", "cmd": f"{_shell_py(write)} 3"}]})
        r = self.run_suite("--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.ended()
        self.assertEqual((row["tests"], row["counts_from"], row["failed"]), (5, "result", 0))

    def test_a_bad_stage_result_leaves_the_others_standing(self):
        write = "import os; open(os.environ['CCP_SUITE_RESULT'], 'w').write('{\"tests\": 6}')"
        bad = "import os; print('Ran 40 tests in 1s'); open(os.environ['CCP_SUITE_RESULT'], 'w').write('nope')"
        self.lanes({"fast": [{"name": "a", "cmd": _shell_py(write)}, {"name": "b", "cmd": _shell_py(bad)}]})
        r = self.run_suite("--lane", "fast")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.ended()
        self.assertEqual((row["tests"], row["counts_from"]), (6, "result"))
        self.assertTrue(row["result_problem"])
        self.assertIn("the gate's result file was not used", r.stdout.decode())

    def test_streaming_marks_each_stage_on_stderr(self):
        self.lanes({"fast": [{"name": "unit", "cmd": "echo one"}, {"name": "lint", "cmd": "echo two"}]})
        r = self.run_suite("--full", "--lane", "fast")
        self.assertEqual((r.returncode, r.stdout.splitlines()[:2]), (0, [b"one", b"two"]), r.stderr)
        self.assertIn(b"stage lint", r.stderr)
        self.assertEqual(len([ln for ln in r.stdout.splitlines() if b": stages: " in ln]), 1)

    def test_a_nested_staged_lane_runs_its_stages_unrecorded(self):
        later = self.runner / "later-ran"
        self.lanes({"fast": [{"name": "a", "cmd": "echo first"}, {"name": "b", "cmd": "exit 3"},
                             {"name": "c", "cmd": f"touch {later}"}]})
        r = ccp_proc(self.runner, "suite", "run", "--lane", "fast", env={"CCP_SUITE_ID": "st-outer"})
        self.assertEqual((r.returncode, r.stdout), (3, b"first\n"), r.stderr)
        self.assertFalse(later.exists())
        self.assertEqual(self.rows(), [])

    def test_a_signal_stops_the_stages(self):
        later = self.runner / "later-ran"
        self.lanes({"fast": [{"name": "wait", "cmd": "sleep 30"}, {"name": "after", "cmd": f"touch {later}"}]})
        p = subprocess.Popen([CCP, "suite", "run", "--full", "--lane", "fast"], cwd=self.runner,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
        deadline = time.time() + 10
        while time.time() < deadline and [x["op"] for x in self.rows()][-1:] != ["started"]:
            time.sleep(0.05)
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=20)
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse(later.exists())
        row = self.ended()
        self.assertEqual((row["interrupted"], [s["name"] for s in row["stages"]], row["failed_stage"]),
                         ("SIGTERM", ["wait"], "wait"))


    def test_a_signal_between_stages_never_passes(self):
        later = self.runner / "later-ran"
        self.lanes({"fast": [{"name": "first", "cmd": "sleep 0.2"}, {"name": "second", "cmd": f"touch {later}"}]})
        real = suite._run_stage

        def then_signal(sig):
            def run_stage(*args, **kw):
                out = real(*args, **kw)
                os.kill(os.getpid(), sig)  # the first stage has ended; the second has not started
                return out
            return run_stage
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        cfg = config.load(self.runner)
        a = type("A", (), {"lane": "fast", "phase": None, "run": None, "task": None, "root": None,
                           "output": "summary", "log": None, "wait": None})()
        for sig, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            with self.subTest(sig=sig.name):
                said: list[str] = []
                with mock.patch.object(suite, "_run_stage", then_signal(sig)), \
                        mock.patch.object(suite, "_say", said.append):
                    self.assertEqual(suite.run(cfg, a, None), code)
                self.assertFalse(later.exists())
                row = self.ended()
                self.assertEqual((row["exit_code"], row["interrupted"], row["failed_stage"]),
                                 (code, sig.name, "second"))
                self.assertEqual([(s["name"], s["exit_code"]) for s in row["stages"]], [("first", 0)])
                self.assertIn("second", "".join(said).split("not run:")[1])

    def test_a_signal_a_stage_survives_stops_the_run_before_the_next(self):
        later = self.runner / "later-ran"
        for sig, code in ((signal.SIGTERM, 143), (signal.SIGINT, 130)):
            with self.subTest(sig=sig.name):
                # The first stage ignores the signal it sends to ccp, so it ends passing; the second never starts.
                self.lanes({"fast": [{"name": "first", "cmd": f"trap '' {sig.name[3:]}; kill -{sig.name[3:]} $PPID; "
                                                              "sleep 0.2"},
                                     {"name": "second", "cmd": f"touch {later}"}]})
                r = self.run_suite("--lane", "fast")
                self.assertEqual(r.returncode, code, r.stdout.decode() + r.stderr.decode())
                self.assertFalse(later.exists())
                row = self.ended()
                self.assertEqual((row["interrupted"], row["failed_stage"]), (sig.name, "second"))
                self.assertEqual([(s["name"], s["exit_code"]) for s in row["stages"]], [("first", 0)])


class OldLaneForm(StagedFixture, unittest.TestCase):
    def test_an_argv_gate_lane_runs_as_one_stage_as_before(self):
        self.lanes({"gate": [PY, "-c", "print('Ran 4 tests in 0.1s')"]})
        r = self.run_suite("--lane", "gate")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = self.ended()
        self.assertEqual([(s["name"], s["exit_code"]) for s in row["stages"]], [("gate", 0)])
        self.assertEqual((row["failed_stage"], row["tests"]), (None, 4))
        self.assertNotIn(b": stages: ", r.stdout)
        started = [x for x in self.rows() if x["op"] == "started"][-1]
        self.assertEqual((started["cmd"], started["argc"]), (Path(PY).name, 2))

    def test_a_failing_argv_lane_names_itself(self):
        self.lanes({"gate": [PY, "-c", "raise SystemExit(2)"]})
        self.assertEqual(self.run_suite("--lane", "gate").returncode, 2)
        self.assertEqual(self.ended()["failed_stage"], "gate")

    def test_a_command_lane_that_cannot_start_is_its_failed_stage(self):
        self.lanes({"gate": ["/nonexistent/gate-command"]})
        self.assertEqual(self.run_suite("--lane", "gate").returncode, 127)
        self.assertEqual((self.ended()["failed_stage"], self.ended()["stages"][0]["exit_code"]), ("gate", 127))

    def test_a_command_after_dashes_records_no_stages(self):
        self.lanes({"gate": [{"name": "unit", "cmd": "exit 9"}]})
        r = self.run_suite("--lane", "gate", "--", PY, "-c", "pass")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("stages", self.ended())
        self.assertNotIn("failed_stage", self.ended())


class StageConfig(unittest.TestCase):
    def load(self, lanes) -> config.Config:
        from tests.helpers import Product
        p = Product({"suite": {"lanes": lanes}})
        self.addCleanup(p.cleanup)
        return p.cfg

    def test_config_refuses_bad_stages(self):
        for bad in ([{"name": "unit"}], [{"name": "unit", "cmd": ""}], [{"name": "Unit", "cmd": "x"}],
                    [{"name": "unit", "cmd": "x", "timeout": 3}], [{"name": "unit", "cmd": ["x"]}],
                    [{"name": "unit", "cmd": "x"}, {"name": "unit", "cmd": "y"}],
                    [{"name": config.PLANE_DOCS_STAGE, "cmd": "x"}], [{"name": "unit", "cmd": "x"}, "y"],
                    [{"name": "unit", "cmd": f"run {config.LANE_PLACEHOLDER}"}]):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError):
                self.load({"gate": bad})

    def test_config_takes_stages_and_argv_lanes(self):
        lanes = {"gate": [{"name": "lint", "cmd": "make lint"}, {"name": "tests", "cmd": "make test"}],
                 "full": ["make", "test"]}
        cfg = self.load(lanes)
        self.assertEqual(cfg.suite["lanes"], lanes)
        self.assertEqual([(s["name"], s["argv"][-1]) for s in suite.resolve_stages(cfg, "gate", None)],
                         [("lint", "make lint"), ("tests", "make test"), (config.PLANE_DOCS_STAGE, "check")])
        self.assertEqual(suite.resolve_stages(cfg, "full", None), [{"name": "full", "argv": ["make", "test"]}])

    def test_the_schema_takes_both_lane_forms(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())
        lane = schema["properties"]["suite"]["properties"]["lanes"]["additionalProperties"]
        kinds = {json.dumps(x["items"].get("type")) for x in lane["anyOf"]}
        self.assertEqual(kinds, {'"string"', '"object"'})
        result = json.loads((Path(__file__).resolve().parents[1] / "contracts/suite_result.schema.json").read_text())
        self.assertTrue({"stages", "failed_stage"} <= set(result["properties"]))


if __name__ == "__main__":
    unittest.main()
