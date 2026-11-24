"""`ccp suite run --cold` (SPEC §14.2, §14.6): a worker asks any product's gate for a cold run the same
way. What the run starts gets CCP_SUITE_COLD=1, the run is recorded cold only when its own count shows
nothing cached, and the plane's own gate (scripts/gate.sh) reads the variable as its cold option."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from tests.git_helpers import git
from tests.gate_parallel_fixture import OK, SCRIPTS
from tests.helpers import PLANE_ROOT
from tests.suite_fixture import PY
from tests.suite_stages_fixture import StagedFixture, _shell_py

SHOW = "echo cold=[$CCP_SUITE_COLD]"


class TheColdOption(StagedFixture, unittest.TestCase):
    def log(self, _r: subprocess.CompletedProcess[bytes]) -> str:
        return Path(self.ended()["log"]).read_text()

    def suite_event(self) -> dict:
        return [e for e in self.events() if e["type"] == "suite"][-1]["payload"]

    def test_a_gate_that_ignores_it_and_counts_nothing_cached_is_not_recorded_cold(self):
        self.lanes({"gate": [{"name": "show", "cmd": f"{SHOW}; echo 'Ran 3 tests in 0.1s'"}]})
        r = self.run_suite("--lane", "gate", "--cold")
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        self.assertIn("cold=[1]", self.log(r))
        row = self.ended()
        self.assertEqual((row["tests"], row["cached"]), (3, None))
        self.assertIsNone(row["cold"])
        self.assertIn("cold", self.suite_event())
        self.assertIsNone(self.suite_event()["cold"])

    def test_without_it_the_stage_gets_nothing_and_cold_stays_unknown(self):
        self.lanes({"gate": [{"name": "show", "cmd": SHOW}]})
        r = self.run_suite("--lane", "gate")
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        self.assertIn("cold=[]", self.log(r))
        self.assertIsNone(self.ended()["cold"])

    def test_every_stage_of_a_lane_gets_it(self):
        self.lanes({"fast": [{"name": "one", "cmd": SHOW}, {"name": "two", "cmd": SHOW}]})
        r = self.run_suite("--lane", "fast", "--cold")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.log(r).count("cold=[1]"), 2)

    def test_a_command_after_the_separator_gets_it_too(self):
        r = self.run_suite("--lane", "part", "--cold", "--", "sh", "-c", SHOW)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cold=[1]", self.log(r))
        self.assertIsNone(self.ended()["cold"])  # it counted nothing cached, so it is not shown cold

    def test_the_runs_own_count_of_cached_units_wins(self):
        warm = _shell_py("import json, os; json.dump({'tests': 3, 'ran': 1, 'cached': 2}, "
                         "open(os.environ['CCP_SUITE_RESULT'], 'w'))")
        cold = warm.replace("'ran': 1, 'cached': 2", "'ran': 3, 'cached': 0")
        self.lanes({"fast": [{"name": "unit", "cmd": warm}], "slow": [{"name": "unit", "cmd": cold}]})
        r = self.run_suite("--lane", "fast", "--cold")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.ended()["cached"], self.ended()["cold"]), (2, False))
        r = self.run_suite("--lane", "slow", "--cold")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.ended()["cached"], self.ended()["cold"]), (0, True))

    def test_the_printed_count_decides_whether_or_not_it_was_asked(self):
        self.lanes({"slow": [{"name": "unit", "cmd": "echo 'ran 3, cached 0'"}],
                    "fast": [{"name": "unit", "cmd": "echo 'ran 1, cached 2'"}]},
                   summary={"ran_re": r"^ran (\d+), cached \d+", "cached_re": r"^ran \d+, cached (\d+)"})
        got = []
        for args in (("--lane", "slow", "--cold"), ("--lane", "fast", "--cold"), ("--lane", "slow")):
            r = self.run_suite(*args)
            self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
            got.append((self.ended()["ran"], self.ended()["cached"], self.ended()["cold"]))
        self.assertEqual(got, [(3, 0, True), (1, 2, False), (3, 0, True)])

    def test_a_nested_run_passes_it_to_its_command(self):
        r = self.run_suite("--cold", "--", "sh", "-c", SHOW, env={"CCP_SUITE_ID": "st-outer"})
        self.assertEqual((r.returncode, r.stdout.decode()), (0, "cold=[1]\n"), r.stderr)
        self.assertEqual(self.rows(), [])  # the outer run records


class ThePlanesGateReadsIt(StagedFixture, unittest.TestCase):
    def test_a_cold_run_serves_nothing_from_the_cache_and_a_warm_one_does(self):
        repo = Path(self._tmp.name) / "gate-repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "tests").mkdir()
        for s in SCRIPTS:
            (repo / "scripts" / s).write_text((PLANE_ROOT / "scripts" / s).read_text())
        (repo / "tests" / "__init__.py").write_text("")
        (repo / "tests" / "test_ok.py").write_text(OK)
        (repo / ".gitignore").write_text("__pycache__/\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "c")
        self.lanes({"fast": ["bash", str(repo / "scripts" / "gate.sh")]})
        env = {"GATE_CACHE_DIR": str(Path(self._tmp.name) / "gate-cache"), "GATE_WORKERS": "1"}
        got = []
        for args, extra in (((), {}), ((), {}), (("--cold",), {}), ((), {"CCP_SUITE_COLD": "0"})):
            r = self.run_suite("--lane", "fast", *args, env={**env, **extra}, unset=("GATE_COLD",))
            self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
            row = self.ended()
            got.append((row["ran"], row["cached"], row["cold"]))
        self.assertEqual(got, [(1, 0, True), (0, 1, False), (1, 0, True), (0, 1, False)])


class TheVerifierAsksForItThisWay(unittest.TestCase):
    def test_a_cold_gate_and_a_check_that_asks_for_one_name_the_option_on_the_gate_lane(self):
        from tests.render_helpers import render_phase_values as render
        for cold in (True, False):
            text = render("verify", accept_cache=True, cold_gate=cold, gate_lane="checks")
            self.assertIn("suite run --lane checks --cold", text, cold)
            self.assertNotIn("its cold option)", text, cold)


if __name__ == "__main__":
    unittest.main()
