"""SPEC §21.1, §5.5, §10.5: what `ccp tasks check` warns about in a task's Context: measured figures gone
stale since the commit they were measured at, and numbers stated with no command, which a ruling written
as a quoted block does not raise."""
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
        return [w for w in tasklog.warnings(self.p.cfg) if w.startswith(FILE) and self.base in w]

    def test_a_commit_since_the_measurement_that_changed_a_declared_path_warns_naming_it(self):
        sha = self.commit("src/a.py", "change a")
        ws = self.stale()
        self.assertEqual(len(ws), 1, ws)
        self.assertIn(sha, ws[0])

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


class QuotedRulings(unittest.TestCase):
    """A ruling written verbatim into Context as a quoted block keeps its numbers without a warning."""

    def test_a_quoted_line_raises_no_number_warning_and_the_same_line_unquoted_does(self):
        p = Product()
        self.addCleanup(p.cleanup)
        ruling = "per §10.5, from round 2 on, at most a few of the 42 sites"
        f = p.task(TID)
        f.write_text(f.read_text().replace("- background", f"> {ruling}\n>\n> 7 more lines\n\n{ruling}"))
        lines = f.read_text().split("\n")
        ws = [w for w in tasklog.warnings(p.cfg) if "Context states a number" in w]
        self.assertEqual([w.split(": Context")[0] for w in ws], [f"{FILE}:{lines.index(ruling) + 1}"], ws)
        self.assertEqual(ws[0].split("number (")[1].split(")")[0], "2, 42")


if __name__ == "__main__":
    unittest.main()
