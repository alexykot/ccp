"""A command on a task's merge base (SPEC §12.1): `ccp wt create --kind base --task ID --sha HEAD -- COMMAND`."""
from __future__ import annotations

import json
import signal
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import wt
from tests.test_toolkit import git
from tests.test_wt import WtFixture

FEATURE_TEST = """import unittest


class Feature(unittest.TestCase):
    def test_feature(self):
        from feature import answer
        self.assertEqual(answer(), 42)
"""


class OnTheMergeBase(WtFixture, unittest.TestCase):
    """A task branch that adds a test and the code it needs; the integration branch moved on since."""

    def setUp(self):
        super().setUp()
        self.base = self.head()
        work = Path(self._tmp.name) / "work"
        git(self.main, "worktree", "add", "-q", "-b", "task/0002-second", str(work), "origin/main")
        (work / "feature.py").write_text("def answer():\n    return 42\n")
        (work / "tests").mkdir()
        (work / "tests" / "test_feature.py").write_text(FEATURE_TEST)
        git(work, "add", "feature.py", "tests/test_feature.py")
        git(work, "commit", "-q", "-m", "Task 0002: the feature and its test")
        git(work, "push", "-q", "-u", "origin", "task/0002-second")
        self.pr_head = git(work, "rev-parse", "HEAD")
        self.write("later.txt", "the integration branch moved on\n")
        git(self.main, "add", "later.txt")
        git(self.main, "commit", "-q", "-m", "later")
        git(self.main, "push", "-q", "origin", "main")
        self.tip = self.head()

    def base_run(self, *command: str, sha: str | None = None, extra: tuple[str, ...] = ()):
        args = ["create", "--kind", "base", "--task", "0002", *(["--sha", sha or self.pr_head]), *extra]
        code, _, body, err = self.wt(*args, *(["--", *command] if command else []))
        i = body.rfind("\n{")
        result = json.loads(body[i + 1 if i >= 0 else 0:]) if "{" in body else None
        return code, result, body, err

    def assert_nothing_left(self, name: str = "base-0002") -> None:
        self.assertFalse((self.main / ".rt" / name).exists())
        self.assertFalse((self.q / "worktrees" / f"{name}.json").exists())
        self.assertNotIn(name, git(self.main, "worktree", "list"))

    def test_the_heads_test_fails_on_the_merge_base_and_nothing_is_left(self):
        code, res, body, err = self.base_run(
            "sh", "-c", f"git checkout -q {self.pr_head} -- tests/test_feature.py && "
                        f"{sys.executable} -B -m unittest tests.test_feature")
        self.assertEqual(code, 1, err)
        self.assertIn("No module named 'feature'", body)
        self.assertIn("FAILED", body)
        self.assertEqual((res["exit"], res["ok"], res["removed"]), (1, False, True))
        self.assertEqual((res["merge_base"], res["head"], res["name"]), (self.base, self.pr_head, "base-0002"))
        self.assert_nothing_left()

    def test_it_runs_detached_at_the_merge_base_and_passes_the_commands_exit_code(self):
        code, res, body, err = self.base_run("git", "rev-parse", "HEAD")
        self.assertEqual(code, 0, err)
        self.assertIn(self.base, body)
        self.assertNotEqual(self.base, self.tip)
        self.assertEqual((res["exit"], res["ok"], res["integration"]), (0, True, "origin/main"))
        self.assertEqual(self.base_run("sh", "-c", "exit 5")[0], 5)
        self.assert_nothing_left()

    def test_it_is_recorded_while_its_command_runs(self):
        code, _, body, err = self.base_run("cat", str(self.q / "worktrees" / "base-0002.json"))
        self.assertEqual(code, 0, err)
        st = json.loads(body[:body.rfind("\n{") + 1])
        self.assertEqual((st["kind"], st["seat"], st["tag"], st["sha"], st["head"]),
                         ("base", "ver", "base", self.base, self.pr_head))
        self.assertIsNone(st["branch"])
        self.assert_nothing_left()

    def test_setup_and_teardown_run_around_the_command(self):
        log = Path(self._tmp.name) / "hooks.log"
        self.plane(env={"setup": f"echo setup {{kind}} >> {log}", "teardown": f"echo teardown {{name}} >> {log}"})
        code, _, _, err = self.base_run("sh", "-c", f"echo command >> {log}")
        self.assertEqual(code, 0, err)
        self.assertEqual(log.read_text().split("\n")[:3], ["setup base", "command", "teardown base-0002"])
        self.assert_nothing_left()

    def test_a_command_that_cannot_be_found_is_127_and_its_worktree_is_removed(self):
        code, res, _, err = self.base_run("no-such-command-anywhere")
        self.assertEqual((code, res["exit"]), (127, 127), err)
        self.assert_nothing_left()

    def test_a_signal_ending_the_command_is_128_plus_the_signal(self):
        code, _, _, _ = self.base_run("sh", "-c", "kill -TERM $$")
        self.assertEqual(code, 143)
        self.assert_nothing_left()

    def test_refusals(self):
        code, _, _, err = self.base_run()
        self.assertEqual(code, 125, err)  # no command
        self.assertIn("not its command's exit code", err)
        code, _, _, err = self.wt("create", "--kind", "base", "--task", "0002", "--", "true")
        self.assertEqual(code, 125, err)  # no --sha
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.pr_head, "--", "true")
        self.assertEqual(code, 2, err)  # only a base worktree runs a command
        self.assertFalse((self.main / ".rt" / "ver-0002").exists())
        code, _, _, err = self.base_run("true", sha="f" * 40)
        self.assertEqual(code, 125, err)
        self.assertIn("no merge base", err)
        other = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.pr_head)[1]["path"]
        code, _, _, err = self.base_run("true", extra=("--name", "base-0002"))
        self.assertEqual(code, 0, err)
        (self.main / ".rt" / "base-0002").mkdir()
        code, res, _, err = self.base_run("true", extra=("--name", "base-0002"))
        self.assertEqual(code, 125, err)  # never one it did not make
        self.assertIsNone(res)  # a refusal prints no result: nothing ran
        self.assertTrue((self.main / ".rt" / "base-0002").is_dir())
        self.assertTrue(Path(other).is_dir())

    def test_its_own_refusal_differs_from_a_command_exiting_2_or_3(self):
        self.assertEqual(self.base_run("sh", "-c", "exit 2")[0], 2)
        self.assertEqual(self.base_run("sh", "-c", "exit 3")[0], 3)
        self.assertEqual(self.base_run("true", sha="f" * 40)[0], 125)
        self.assertEqual(self.wt("create", "--kind", "base", "--task", "0099", "--sha", self.pr_head, "--", "true")[0],
                         125)  # no such task
        self.assert_nothing_left()

    def test_a_failure_saving_its_record_leaves_nothing(self):
        real = wt.save

        def save(q, st):
            if "head" in st:
                raise OSError("disk full")
            real(q, st)

        with mock.patch.object(wt, "save", save):
            code, res, _, err = self.base_run("true")
        self.assertEqual(code, 125, err)
        self.assertIn("disk full", err)
        self.assertIsNone(res)
        self.assert_nothing_left()

    def test_a_failure_after_the_worktree_is_added_leaves_nothing(self):
        with mock.patch.object(wt, "save", side_effect=OSError("disk full")):
            code, _, _, err = self.base_run("true")
        self.assertEqual(code, 125, err)
        self.assert_nothing_left()

    def test_a_command_that_outlives_the_timeout_is_killed_with_its_children(self):
        started = time.monotonic()
        code, res, _, err = self.base_run("sh", "-c", "sleep 30 & sleep 30", extra=("--timeout", "1"))
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual((code, res["exit"], res["timed_out"], res["ok"]), (124, 124, True, False), err)
        self.assertIn("--timeout 1 s", err)
        self.assert_nothing_left()
        code, res, _, err = self.base_run("true", extra=("--timeout", "60"))
        self.assertEqual((code, res["timed_out"]), (0, False), err)

    def test_the_timeout_defaults_to_the_env_hook_timeout(self):
        self.plane(env={"timeout_seconds": 1})
        started = time.monotonic()
        code, res, _, err = self.base_run("sleep", "30")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual((code, res["timed_out"]), (124, True), err)
        self.assert_nothing_left()

    def test_timeout_refusals(self):
        for bad in ("0", "-1", "soon"):
            code, _, _, err = self.base_run("true", extra=("--timeout", bad))
            self.assertEqual(code, 125, err)
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.pr_head, "--timeout", "5")
        self.assertEqual(code, 2, err)
        self.assertFalse((self.main / ".rt" / "ver-0002").exists())
        self.assert_nothing_left()

    def test_a_sigterm_to_ccp_stops_the_command_and_leaves_nothing(self):
        got: list[int] = []
        previous = signal.signal(signal.SIGTERM, lambda n, _f: got.append(n))  # never the test process's death
        self.addCleanup(signal.signal, signal.SIGTERM, previous)
        mine = signal.getsignal(signal.SIGTERM)
        started = time.monotonic()
        code, res, _, err = self.base_run("sh", "-c", "kill -TERM $PPID; sleep 30")
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual((code, res["exit"], res["signal"], res["removed"]), (143, 143, 15, True), err)
        self.assertEqual(got, [])  # ccp's own handler took it
        self.assertIs(signal.getsignal(signal.SIGTERM), mine)  # and gave the caller's back
        self.assert_nothing_left()

    def test_a_failed_fetch_warns_that_the_base_may_be_stale(self):
        git(self.main, "remote", "set-url", "origin", str(Path(self._tmp.name) / "gone.git"))
        code, res, body, err = self.base_run("git", "rev-parse", "HEAD")
        self.assertEqual(code, 0, err)
        self.assertIn("git fetch origin failed", err)
        self.assertIn("may be stale", err)
        self.assertTrue(any("may be stale" in w for w in res["warnings"]))
        self.assertIn(self.base, body)
        self.assert_nothing_left()

    def test_a_fetch_that_works_warns_of_nothing(self):
        code, res, _, err = self.base_run("true")
        self.assertEqual((code, res["warnings"]), (0, []), err)


if __name__ == "__main__":
    unittest.main()
