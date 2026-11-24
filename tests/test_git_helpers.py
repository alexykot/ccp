"""The shared git runner (`tests/git_helpers.py`): stripped or raw output, a failing command fails the test with its
stderr, `env` over the test identity, and `commit` at a given time."""
import tempfile
import unittest
from pathlib import Path

from tests.git_helpers import HEALTH_T0, commit, git


class SharedGitRunner(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        git(self.root, "init", "-q", "-b", "main")

    def test_output_is_stripped_unless_raw(self):
        self.assertEqual(git(self.root, "symbolic-ref", "--short", "HEAD"), "main")
        self.assertEqual(git(self.root, "symbolic-ref", "--short", "HEAD", raw=True), "main\n")

    def test_a_failing_command_fails_the_test_naming_the_command_and_stderr(self):
        with self.assertRaises(AssertionError) as caught:
            git(self.root, "checkout", "no-such-ref")
        self.assertIn("checkout no-such-ref", str(caught.exception))
        self.assertIn("did not match", str(caught.exception))

    def test_env_goes_over_the_test_identity(self):
        git(self.root, "commit", "-q", "--allow-empty", "-m", "one", env={"GIT_AUTHOR_EMAIL": "other@example.com"})
        self.assertEqual(git(self.root, "log", "-1", "--format=%ae,%ce"), "other@example.com,t@example.com")

    def test_commit_stamps_the_given_time(self):
        commit(self.root, "when", HEALTH_T0, "--allow-empty")
        self.assertEqual(git(self.root, "log", "-1", "--format=%at,%ct"), f"{HEALTH_T0},{HEALTH_T0}")


if __name__ == "__main__":
    unittest.main()
