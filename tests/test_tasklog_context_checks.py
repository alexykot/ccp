"""SPEC §21.1: what `ccp tasks check` warns about in a task's Context: measured figures gone stale since the
commit they were measured at (counted in its warnings, named by `--stale`)."""
from __future__ import annotations

import unittest

from ccp import tasklog
from tests.helpers import Product
from tests.toolkit_fixture import git

TID = "0001-a"
FILE = f"docs/delivery/tasks/{TID}.md"


class StaleContext(unittest.TestCase):
    """A git product whose task 0001 declares `src/a.py` in its paths and was measured at the first commit."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self.p.write("src/a.py", "a = 1\n")
        self.p.write("src/b.py", "b = 1\n")
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")
        self.base = git(self.p.root, "rev-parse", "--short=7", "HEAD")
        self.measured(self.base)

    def measured(self, sha: str, status: str = "pending") -> None:
        f = self.p.task(TID, status)
        f.write_text(f.read_text().replace("spec_refs:", 'paths: ["src/a.py"]\nspec_refs:')
                     .replace("- background", f"- Measured at `{sha}`."))

    def commit(self, rel: str, msg: str) -> str:
        self.p.write(rel, (self.p.root / rel).read_text() + "x = 2\n")
        git(self.p.root, "add", rel)
        git(self.p.root, "commit", "-qm", msg)
        return git(self.p.root, "rev-parse", "--short", "HEAD")

    def stale(self) -> list[str]:
        return [w for w in tasklog.stale(self.p.cfg) if w.startswith(FILE) and self.base in w]

    def test_a_commit_since_the_measurement_that_changed_a_declared_path_warns_naming_it(self):
        sha = self.commit("src/a.py", "change a")
        ws = self.stale()
        self.assertEqual(len(ws), 1, ws)
        self.assertIn(sha, ws[0])

    def test_the_task_check_warnings_count_it_instead_of_naming_it(self):
        self.commit("src/a.py", "change a")
        ws = tasklog.warnings(self.p.cfg)
        self.assertIn(tasklog.stale_count(1)[0], ws)
        self.assertEqual([w for w in ws if w.startswith(FILE) and self.base in w], [])

    def test_a_commit_that_changed_only_an_undeclared_path_does_not_warn(self):
        self.commit("src/b.py", "change b")
        self.assertEqual(self.stale(), [])

    def test_an_unknown_sha_does_not_warn(self):
        self.commit("src/a.py", "change a")
        self.base = "0badc0d"
        self.measured(self.base)
        self.assertEqual(self.stale(), [])

    def test_a_done_or_dropped_task_does_not_warn(self):
        self.commit("src/a.py", "change a")
        for status in tasklog.TERMINAL:
            self.measured(self.base, status)
            self.assertEqual(self.stale(), [], status)

    def test_past_the_named_commits_the_rest_are_counted(self):
        shas = [self.commit("src/a.py", f"change a {n}") for n in range(tasklog.STALE_NAMED + 2)]
        ws = self.stale()
        self.assertEqual(len(ws), 1, ws)
        for sha in shas[-tasklog.STALE_NAMED:]:
            self.assertIn(sha, ws[0])
        for sha in shas[:2]:
            self.assertNotIn(sha, ws[0])
        self.assertIn(" 2 ", ws[0])


if __name__ == "__main__":
    unittest.main()
