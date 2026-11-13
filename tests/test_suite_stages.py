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


DOCS_ONLY = "test -z \"$(git diff --name-only {from} {head} -- . ':!docs')\""  # exit 0: the diff is docs only


class ProversSkipStages(StagedFixture, unittest.TestCase):
    """§14.2: a declared prover that exits 0 on the task's diff skips the gate stage it names, recorded on
    the run; a prover that fails, or cannot judge the diff, skips nothing. The provers are read from the
    integration branch's plane.json, never from the head under test, and run in a clean checkout of its tip."""

    def setUp(self):
        super().setUp()
        self.marker = Path(self._tmp.name) / "suite-ran"
        self.seen = Path(self._tmp.name) / "prover-saw"

    def product(self, provers: list, lanes: dict | None = None, integration: bool = True) -> None:
        """Commit the runner checkout's plane.json with these gate stages and provers and, with
        `integration`, push it to origin/main, the integration branch; without, it is only the head's."""
        from tests.test_toolkit import git
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": lanes or {"gate": [
            {"name": "lint", "cmd": "true"},
            {"name": "suite", "cmd": f"touch {self.marker} && " + _shell_py("print('Ran 3 tests in 0.1s')")}]}}
        cfg["verify"] = {"provers": provers}
        p.write_text(json.dumps(cfg))
        git(self.runner, "add", "docs/delivery/plane.json")
        git(self.runner, "commit", "-q", "-m", "provers")
        if integration:
            git(self.runner, "push", "-q", "origin", "HEAD:main")

    def change(self, rel: str) -> str:
        from tests.test_toolkit import git
        (self.runner / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.runner / rel).write_text("changed\n")
        git(self.runner, "add", rel)
        git(self.runner, "commit", "-q", "-m", f"change {rel}")
        return git(self.runner, "rev-parse", "HEAD")

    def gate(self, *extra: str) -> subprocess.CompletedProcess[bytes]:
        r = self.run_suite("--lane", "gate", *extra)
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        return r

    def test_a_docs_only_diff_skips_the_suite_stage_on_the_record(self):
        self.product([{"name": "docs-only", "command": DOCS_ONLY, "skips": "suite"}])
        self.change("docs/guide.md")
        self.implementing()
        r = self.gate("--run", "0002-second/implement")
        self.assertFalse(self.marker.exists())
        row = self.ended()
        self.assertEqual([s["name"] for s in row["stages"]], ["lint", config.PLANE_DOCS_STAGE])
        want = [{"stage": "suite", "prover": "docs-only", "exit_code": 0, "run_id": "0002-second/implement"}]
        self.assertEqual(row["proven_skips"], want)
        self.assertEqual((row["failed_stage"], row["tests"]), (None, None))
        ev = [e for e in self.events() if e["type"] == "suite"][-1]["payload"]
        self.assertEqual(ev["proven_skips"], want)
        # the records name the prover, never its command: plane.json looks the command up by the name
        self.assertNotIn("git diff --name-only", (self.q / "runs" / "_suites.jsonl").read_text())
        self.assertNotIn("git diff --name-only", (self.q / "observability" / "events.jsonl").read_text())
        line = next(ln for ln in r.stdout.decode().splitlines() if ": stages: " in ln)
        self.assertIn("skipped: suite (prover docs-only)", line)
        self.assertNotIn("not run:", line)

    def test_a_failing_prover_skips_nothing(self):
        self.product([{"name": "docs-only", "command": DOCS_ONLY, "skips": "suite"}])
        self.change("src/app.py")
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        row = self.ended()
        self.assertEqual([s["name"] for s in row["stages"]], ["lint", "suite", config.PLANE_DOCS_STAGE])
        self.assertNotIn("proven_skips", row)
        self.assertEqual(row["tests"], 3)

    def test_a_prover_the_task_declares_or_changes_in_its_own_diff_skips_nothing(self):
        # the head adds a prover the integration branch does not have
        self.product([{"name": "always", "command": "true", "skips": "suite"}], integration=False)
        self.change("docs/guide.md")
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        self.assertNotIn("proven_skips", self.ended())
        self.marker.unlink()
        self.product([{"name": "always", "command": "exit 1", "skips": "suite"}])  # integration's fails
        self.product([{"name": "always", "command": "true", "skips": "suite"}], integration=False)  # the head's passes
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        self.assertNotIn("proven_skips", self.ended())

    def test_a_head_that_edits_plane_json_still_gets_the_integration_branchs_verdict(self):
        self.product([{"name": "always", "command": "true", "skips": "suite"}])
        self.product([], integration=False)  # the head drops it: the integration branch's rule still applies
        self.change("src/app.py")
        self.implementing()
        self.gate("--run", "0002-second/implement")
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.ended()["proven_skips"],
                         [{"stage": "suite", "prover": "always", "exit_code": 0, "run_id": "0002-second/implement"}])

    def script(self, text: str, rel: str = "scripts/prove.sh") -> None:
        """A prover's script, on the integration branch: `text` decides its exit, whatever the diff."""
        from tests.test_toolkit import git
        (self.runner / rel).parent.mkdir(exist_ok=True)
        (self.runner / rel).write_text(text)
        git(self.runner, "add", rel)
        git(self.runner, "commit", "-q", "-m", "the prover's script")
        git(self.runner, "push", "-q", "origin", "HEAD:main")

    def edit_script(self, text: str, rel: str = "scripts/prove.sh") -> None:
        from tests.test_toolkit import git
        (self.runner / rel).write_text(text)
        git(self.runner, "commit", "-q", "-am", "the task edits the prover's script")

    SCRIPTED = {"name": "scripted", "command": "sh ./scripts/prove.sh {from} {head}", "skips": "suite"}

    def test_a_diff_that_edits_the_provers_script_gets_the_integration_branchs_verdict(self):
        self.script("exit 1\n")  # the integration branch's script proves nothing
        self.product([self.SCRIPTED])
        self.edit_script("exit 0\n")  # the task's copy would prove anything
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        row = self.ended()
        self.assertNotIn("proven_skips", row)
        self.assertIn("prover scripted exit 1\n", Path(row["log"]).read_text())  # it ran: not 127

    def test_a_diff_that_breaks_the_provers_script_still_skips(self):
        self.script("exit 0\n")
        self.product([self.SCRIPTED])
        self.edit_script("exit 1\n")
        self.gate("--task", "0002")
        self.assertFalse(self.marker.exists())
        self.assertEqual([x["prover"] for x in self.ended()["proven_skips"]], ["scripted"])

    def worktrees(self) -> str:
        from tests.test_toolkit import git
        return git(self.runner, "worktree", "list", "--porcelain")

    def test_the_prover_runs_in_a_clean_checkout_of_the_integration_tip_removed_after_the_run(self):
        from tests.test_toolkit import git
        self.product([{"name": "where", "command": f"pwd -P > {self.seen}; git rev-parse HEAD >> {self.seen}; "
                                                   f"git status --porcelain >> {self.seen}; exit 1", "skips": "suite"}])
        tip = git(self.runner, "rev-parse", "origin/main")
        self.change("src/app.py")  # the head is not the tip
        before = self.worktrees()
        self.gate("--task", "0002")
        where, rev, *dirty = self.seen.read_text().splitlines()
        self.assertNotEqual(Path(where), self.runner.resolve())
        self.assertEqual((rev, dirty), (tip, []))
        self.assertFalse(Path(where).exists())
        self.assertEqual(self.worktrees(), before)

    def test_the_provers_checkout_is_removed_after_an_error(self):
        self.product([{"name": "always", "command": "true", "skips": "suite"}])
        self.change("src/app.py")
        seen: list[Path] = []

        def boom(_cmd, cwd, *_a):
            seen.append(Path(cwd))
            raise RuntimeError("the prover broke")
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        before = self.worktrees()
        a = type("A", (), {"lane": "gate", "phase": None, "run": None, "task": "0002", "root": None,
                           "output": "summary", "log": None, "wait": None})()
        with mock.patch.object(suite, "_prove", boom), mock.patch.object(suite, "_say", lambda _t: None), \
                self.assertRaises(RuntimeError):
            suite.run(config.load(self.runner), a, None)
        self.assertTrue(seen)
        self.assertFalse(seen[0].exists())
        self.assertEqual(self.worktrees(), before)

    def test_no_temp_dir_for_the_checkout_runs_no_prover_and_the_stage(self):
        self.product([{"name": "spy", "command": f"touch {self.seen}", "skips": "suite"}])
        self.change("docs/guide.md")
        real = suite.tempfile.mkdtemp

        def full(*a, **kw):
            if kw.get("prefix") == "ccp-prover-":
                raise OSError(28, "No space left on device")
            return real(*a, **kw)
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        a = type("A", (), {"lane": "gate", "phase": None, "run": None, "task": "0002", "root": None,
                           "output": "summary", "log": None, "wait": None})()
        with mock.patch.object(suite.tempfile, "mkdtemp", full), mock.patch.object(suite, "_say", lambda _t: None):
            code = suite.run(config.load(self.runner), a, None)
        self.assertEqual(code, 0)
        self.assertFalse(self.seen.exists())
        self.assertTrue(self.marker.exists())  # nothing proven: the stage ran
        self.assertIn("no clean checkout of the integration tip", Path(self.ended()["log"]).read_text())

    def test_the_gate_fetches_the_integration_branch_before_reading_the_provers(self):
        from tests.test_toolkit import git
        self.product([])  # the integration branch declares no prover, as the runner last fetched it
        self.change("src/app.py")
        # another clone adds a prover to the integration branch; the runner's checkout has not fetched it
        other = Path(self._tmp.name) / "other-clone"
        git(Path(self._tmp.name), "clone", "-q", git(self.runner, "remote", "get-url", "origin"), str(other))
        p = other / "docs/delivery/plane.json"
        p.write_text(json.dumps({**json.loads(p.read_text()),
                                 "verify": {"provers": [{"name": "always", "command": "true", "skips": "suite"}]}}))
        git(other, "commit", "-q", "-am", "a prover")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.gate("--task", "0002")
        self.assertFalse(self.marker.exists())
        self.assertEqual([x["prover"] for x in self.ended()["proven_skips"]], ["always"])

    def test_a_failed_fetch_of_the_integration_branch_skips_nothing(self):
        from tests.test_toolkit import git
        self.product([{"name": "always", "command": "true", "skips": "suite"}])
        self.change("src/app.py")
        git(self.runner, "remote", "set-url", "origin", str(Path(self._tmp.name) / "no-such-remote"))
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        row = self.ended()
        self.assertNotIn("proven_skips", row)
        self.assertIn("the fetch of origin/main failed", Path(row["log"]).read_text())

    def test_an_integration_plane_json_that_does_not_load_declares_no_prover(self):
        from tests.test_toolkit import git
        self.product([{"name": "always", "command": "true", "skips": "suite"}])
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        p.write_text(json.dumps({**cfg, "verify": {"provers": [{"name": "always", "command": "true", "skips": "nowhere"}]}}))
        git(self.runner, "commit", "-q", "-am", "a prover of no stage")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        p.write_text(json.dumps(cfg))  # the head's own plane.json loads, and declares the prover
        git(self.runner, "commit", "-q", "-am", "the head's plane.json")
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())
        row = self.ended()
        self.assertNotIn("proven_skips", row)
        self.assertIn("does not load", Path(row["log"]).read_text())

    def test_the_first_prover_to_pass_skips_the_stage(self):
        self.product([{"name": "never", "command": "exit 1", "skips": "suite"},
                      {"name": "always", "command": "true", "skips": "suite"}])
        self.change("src/app.py")
        self.gate("--task", "0002")
        self.assertFalse(self.marker.exists())
        self.assertEqual([x["prover"] for x in self.ended()["proven_skips"]], ["always"])

    def test_the_prover_gets_the_task_and_the_diff(self):
        from tests.test_toolkit import git
        self.product([{"name": "show", "command": f"echo {{task_id}} {{from}} {{head}} > {self.seen}; exit 1",
                       "skips": "suite"}])
        head = self.change("src/app.py")
        self.gate("--task", "0002")
        self.assertEqual(self.seen.read_text().split(),
                         ["0002-second", git(self.runner, "merge-base", "HEAD", "origin/main"), head])

    def test_no_prover_runs_without_a_task_a_clean_checkout_or_the_gate_lane(self):
        spy = {"name": "spy", "command": f"touch {self.seen}", "skips": "suite"}
        self.product([spy])
        self.change("docs/guide.md")
        self.gate()  # no task: the skip could not be put on a task's record
        self.gate("--task", "0002", "--", "true")  # a command after `--` is no lane's stages
        self.assertFalse(self.seen.exists())
        lanes = {"gate": [{"name": "suite", "cmd": "true"}], "fast": [{"name": "suite", "cmd": f"touch {self.marker}"}]}
        self.product([spy], lanes)
        self.assertEqual(self.run_suite("--lane", "fast", "--task", "0002").returncode, 0)
        self.assertTrue(self.marker.exists())  # only the gate role's lane skips
        self.assertFalse(self.seen.exists())
        self.marker.unlink()
        self.product([spy])
        (self.runner / "untracked.txt").write_text("not committed\n")
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())  # uncommitted changes: the diff is not what the stages test
        self.assertFalse(self.seen.exists())
        self.marker.unlink()
        (self.runner / "untracked.txt").unlink()
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: nowhere\n")
        self.gate("--task", "0002")
        self.assertTrue(self.marker.exists())  # no integration branch to fetch: no prover is read
        self.assertFalse(self.seen.exists())

    def test_a_prover_that_times_out_proves_nothing(self):
        with mock.patch.object(suite, "PROVER_TIMEOUT", 1):
            t0 = time.monotonic()
            self.assertIsNone(suite._prove("sleep 30", self.runner, dict(os.environ), {}))
            self.assertLess(time.monotonic() - t0, 10)
        self.assertEqual(suite._prove("exit 3", self.runner, dict(os.environ), {}), 3)

    def test_a_signal_while_proving_stops_the_run_before_the_stage(self):
        self.product([{"name": "docs-only", "command": DOCS_ONLY, "skips": "suite"}])
        self.change("docs/guide.md")
        real = suite._prove
        seen: list[Path] = []
        before = self.worktrees()

        def then_signal(*args, **kw):
            seen.append(Path(args[1]))
            out = real(*args, **kw)
            os.kill(os.getpid(), signal.SIGTERM)
            return out
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        cfg = config.load(self.runner)
        a = type("A", (), {"lane": "gate", "phase": None, "run": None, "task": "0002", "root": None,
                           "output": "summary", "log": None, "wait": None})()
        with mock.patch.object(suite, "_prove", then_signal), mock.patch.object(suite, "_say", lambda _t: None):
            self.assertEqual(suite.run(cfg, a, None), 143)
        self.assertFalse(self.marker.exists())
        row = self.ended()
        self.assertEqual((row["interrupted"], row["failed_stage"]), ("SIGTERM", "suite"))
        self.assertNotIn("proven_skips", row)
        self.assertFalse(seen[0].exists())  # the provers' checkout is gone after the signal too
        self.assertEqual(self.worktrees(), before)

    def test_config_takes_and_refuses_provers(self):
        from tests.helpers import Product
        lanes = {"gate": [{"name": "lint", "cmd": "true"}, {"name": "suite", "cmd": "true"}],
                 "fast": [{"name": "unit", "cmd": "true"}]}

        def load(provers, lanes=lanes, **suite_extra):
            prod = Product({"suite": {"lanes": lanes, **suite_extra}, "verify": {"provers": provers}})
            self.addCleanup(prod.cleanup)
            return prod.cfg
        good = [{"name": "docs-only", "command": "x", "skips": "suite"}, {"name": "fix", "command": "y", "skips": "review"}]
        self.assertEqual(load(good).verify["provers"], good)
        for bad in ({"name": "docs-only", "command": "x"}, {"name": "Docs", "command": "x", "skips": "suite"},
                    {"name": "a", "command": "", "skips": "suite"}, {"name": "a", "command": "x", "skips": "unit"},
                    {"name": "a", "command": "x", "skips": config.PLANE_DOCS_STAGE},
                    {"name": "a", "command": "x", "skips": "suite", "paths": ["docs"]}, "a"):
            with self.subTest(bad=bad), self.assertRaises(config.ConfigError) as cm:
                load([bad])
            self.assertIn("verify.provers", str(cm.exception))
        with self.assertRaises(config.ConfigError):
            load([good[0], {**good[0], "command": "z"}])  # a name given twice
        with self.assertRaises(config.ConfigError):
            load({"name": "a"})
        with self.assertRaises(config.ConfigError):
            load([good[0]], {"gate": ["make", "test"]})  # an argv gate lane has no stage to skip
        unit = [{"name": "a", "command": "x", "skips": "unit"}]
        self.assertEqual(load(unit, roles={"gate": "fast"}).verify["provers"], unit)  # the gate role's own lane
        with self.assertRaises(config.ConfigError):
            load([good[0]], roles={"gate": "fast"})
        self.assertEqual(load([], lanes).verify["provers"], [])

    def test_the_contracts_name_the_provers_and_the_skips(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "contracts/plane_config.schema.json").read_text())
        item = schema["properties"]["verify"]["properties"]["provers"]["items"]
        self.assertEqual((set(item["properties"]), set(item["required"])), (config.PROVER_KEYS, config.PROVER_KEYS))
        result = json.loads((root / "contracts/suite_result.schema.json").read_text())
        self.assertEqual(set(result["properties"]["proven_skips"]["items"]["properties"]),
                         {"stage", "prover", "exit_code", "run_id"})


WT_VARS = tuple(f"CCP_WT_{f.upper()}" for f in config.WT_FIELDS)
TASK_VARS = ("CCP_TASK_ID", "CCP_NNNN")
SHOW_WT = 'echo "wt=$CCP_WT_NAME"'
SHOW_TASK = 'echo "wt=$CCP_TASK_ID|$CCP_NNNN|$CCP_WT_KIND"'


class StagesGetTheWorktreesFields(StagedFixture, unittest.TestCase):
    """§14.2: in a worktree `ccp wt` made, a lane's stages get its CCP_WT_* fields, as its env hooks do."""

    def worktree(self, lanes: dict, kind: str = "rev", task: str = "0002") -> Path:
        hook = self.main / "docs/delivery/plane.json"
        body = json.loads(hook.read_text())
        body["env"] = {"setup": "env | grep '^CCP_WT_' | sort > hook.env"}
        hook.write_text(json.dumps(body))
        head = subprocess.run(["git", "rev-parse", "origin/main"], cwd=self.main, capture_output=True,
                              text=True, check=True).stdout.strip()
        code, made, _, err = self.ccp("wt", "create", "--kind", kind, "--task", task, "--sha", head, root=self.main)
        self.assertEqual(code, 0, err)
        path = Path(made["path"])
        p = path / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": lanes}
        p.write_text(json.dumps(cfg))
        return path

    def run_in(self, cwd: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[bytes]:
        return ccp_proc(cwd, "suite", "run", "--full", *args, env=env,
                        unset=tuple(v for v in (*WT_VARS, *TASK_VARS) if v not in (env or {})))

    def shown(self, r: subprocess.CompletedProcess[bytes]) -> list[str]:
        return [ln[3:] for ln in r.stdout.decode().splitlines() if ln.startswith("wt=")]

    def test_a_gate_stage_in_a_worktree_gets_the_fields_its_hooks_get(self):
        path = self.worktree({"gate": [{"name": "lint", "cmd": "true"},
                                       {"name": "show", "cmd": f"{SHOW_WT}; env | grep '^CCP_WT_' | sort > stage.env"}]})
        r = self.run_in(path, "--lane", "gate", env={"CCP_WT_NAME": "a-stale-name"})
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        self.assertEqual(self.shown(r), ["rev-0002"])
        hook_env = (path / "hook.env").read_text()
        self.assertEqual(len(hook_env.splitlines()), len(WT_VARS))
        self.assertEqual((path / "stage.env").read_text(), hook_env)

    def test_a_gate_stage_knows_its_task_number_and_kind(self):
        path = self.worktree({"gate": [{"name": "show", "cmd": SHOW_TASK}]}, kind="ver", task="0001")
        r = self.run_in(path, "--lane", "gate", env={"CCP_TASK_ID": "a-stale-id", "CCP_NNNN": "9999"})
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        self.assertEqual(self.shown(r), ["0001-first|0001|ver"])

    def test_a_worktree_made_with_the_full_id_gives_it_too(self):
        path = self.worktree({"fast": [{"name": "show", "cmd": SHOW_TASK}]}, task="0002-second")
        r = self.run_in(path, "--lane", "fast")
        self.assertEqual((r.returncode, self.shown(r)), (0, ["0002-second|0002|rev"]), r.stderr)

    def test_the_baseline_worktree_gives_an_empty_task(self):
        self.worktree({})  # the setup hook
        code, made, _, err = self.ccp("wt", "create", "--kind", "ver", "--baseline", root=self.main)
        self.assertEqual(code, 0, err)
        path = Path(made["path"])
        p = path / "docs/delivery/plane.json"
        lanes = {"fast": [{"name": "s", "cmd": SHOW_TASK}]}
        p.write_text(json.dumps({**json.loads(p.read_text()), "suite": {"lanes": lanes}}))
        r = self.run_in(path, "--lane", "fast", env={"CCP_TASK_ID": "a-stale-id", "CCP_NNNN": "9999"})
        self.assertEqual((r.returncode, self.shown(r)), (0, ["||ver"]), r.stderr)

    def test_an_argv_lane_and_a_nested_staged_lane_get_them_too(self):
        path = self.worktree({"full": ["/bin/sh", "-c", SHOW_WT],
                              "fast": [{"name": "a", "cmd": "true"}, {"name": "b", "cmd": SHOW_WT}]})
        r = self.run_in(path, "--lane", "full")
        self.assertEqual((r.returncode, self.shown(r)), (0, ["rev-0002"]), r.stderr)
        r = self.run_in(path, "--lane", "fast", env={"CCP_SUITE_ID": "st-outer"})
        self.assertEqual((r.returncode, self.shown(r)), (0, ["rev-0002"]), r.stderr)
        r = self.run_in(path, "--lane", "full", env={"CCP_SUITE_ID": "st-outer"})
        self.assertEqual((r.returncode, self.shown(r)), (0, ["rev-0002"]), r.stderr)

    def test_a_command_after_dashes_gets_only_the_callers(self):
        path = self.worktree({"fast": [{"name": "a", "cmd": SHOW_WT}]})
        r = self.run_in(path, "--", "/bin/sh", "-c", SHOW_WT)
        self.assertEqual((r.returncode, self.shown(r)), (0, [""]), r.stderr)
        r = self.run_in(path, "--", "/bin/sh", "-c", SHOW_TASK)
        self.assertEqual((r.returncode, self.shown(r)), (0, ["||"]), r.stderr)
        r = self.run_in(path, "--", "/bin/sh", "-c", SHOW_WT, env={"CCP_WT_NAME": "the-callers"})
        self.assertEqual((r.returncode, self.shown(r)), (0, ["the-callers"]), r.stderr)

    def test_a_checkout_ccp_did_not_make_gets_none(self):
        self.worktree({})  # the queue holds another checkout's record: it is not this one's
        self.lanes({"fast": [{"name": "a", "cmd": "true"},
                             {"name": "b", "cmd": f"{SHOW_WT}; test -z \"$(env | grep -E '^(CCP_WT_|CCP_TASK_ID=|CCP_NNNN=)')\""}]})
        r = self.run_in(self.runner, "--lane", "fast")
        self.assertEqual((r.returncode, self.shown(r)), (0, [""]), r.stderr)

    def test_a_lookup_that_fails_warns_and_adds_nothing(self):
        cfg = config.load(self.runner)
        said: list[str] = []
        with mock.patch("ccp.wt.recorded_at", side_effect=OSError("unreadable")):
            self.assertEqual(suite.worktree_env(cfg, None, said.append), {})
        self.assertEqual(len(said), 1)


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
