"""A command on a task's merge base (SPEC §12.1): `ccp wt create --kind base --task ID --sha HEAD -- COMMAND`."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

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
        self.assertEqual(self.base_run()[0], 2)  # no command
        code, _, _, err = self.wt("create", "--kind", "base", "--task", "0002", "--", "true")
        self.assertEqual(code, 2, err)  # no --sha
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.pr_head, "--", "true")
        self.assertEqual(code, 2, err)  # only a base worktree runs a command
        self.assertFalse((self.main / ".rt" / "ver-0002").exists())
        code, _, _, err = self.base_run("true", sha="f" * 40)
        self.assertEqual(code, 3, err)
        self.assertIn("no merge base", err)
        other = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.pr_head)[1]["path"]
        code, _, _, err = self.base_run("true", extra=("--name", "base-0002"))
        self.assertEqual(code, 0, err)
        (self.main / ".rt" / "base-0002").mkdir()
        code, _, _, err = self.base_run("true", extra=("--name", "base-0002"))
        self.assertEqual(code, 3, err)  # never one it did not make
        self.assertTrue((self.main / ".rt" / "base-0002").is_dir())
        self.assertTrue(Path(other).is_dir())


if __name__ == "__main__":
    unittest.main()
