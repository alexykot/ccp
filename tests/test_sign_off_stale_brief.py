"""SPEC §3.5, §21.1: a `brief` sign-off recorded without `--head` or `--from` for a task whose Context is stale
prints the stale-Context warning on stderr, naming the commits, and is recorded all the same."""
from __future__ import annotations

import unittest

from ccp import config, tasklog
from tests.helpers import as_lead
from tests.toolkit_fixture import ToolkitFixture, git

TASK_FILE = "docs/delivery/tasks/0002-second.md"
SOURCE = "src/feature.py"


class StaleBriefSignOff(ToolkitFixture, unittest.TestCase):
    """0002 declares a brief sign-off, `paths: [src/feature.py]` and a Context measured at the first commit; a
    later commit changes that path."""

    def setUp(self):
        super().setUp()
        self.measured = git(self.main, "rev-parse", "--short=7", "HEAD")
        p = self.main / TASK_FILE
        p.write_text(p.read_text().replace("depends_on:", f'sign_off: brief\npaths: ["{SOURCE}"]\ndepends_on:', 1)
                     .replace("- background", f"- Measured at `{self.measured}`.", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", TASK_FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-q", "-m", "0002 needs a brief sign-off")
        self.brief_head = git(self.main, "rev-parse", "HEAD")
        (self.main / SOURCE).parent.mkdir(parents=True, exist_ok=True)
        (self.main / SOURCE).write_text("x = 1\n")
        git(self.main, "add", SOURCE)
        git(self.main, "commit", "-q", "-m", "change the feature")
        self.change = git(self.main, "rev-parse", "--short=7", "HEAD")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def sign(self, *extra: str):
        with as_lead():  # only the lead records a sign-off (§3.5)
            return self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed as written", *extra)

    def signed(self) -> list[dict]:
        return [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("sign_off", "recorded")]

    def stale_lines(self, err: str) -> list[str]:
        return [ln for ln in err.splitlines() if ln.startswith("warning: ") and "Measured at" in ln]

    def test_a_stale_brief_s_sign_off_warns_naming_the_commit_and_is_recorded(self):
        code, body, out, err = self.sign()
        self.assertEqual(code, 0, out + err)
        lines = self.stale_lines(err)
        self.assertEqual(len(lines), 1, err)
        self.assertIn(self.change, lines[0])
        self.assertIn(f"`{self.measured}`", lines[0])
        self.assertEqual(body["sign_off"]["head"], self.brief_head)
        self.assertEqual([(s["stage"], s["head"]) for s in self.signed()], [("brief", self.brief_head)])

    def test_a_sign_off_given_a_head_prints_no_stale_warning(self):
        code, _, out, err = self.sign("--head", self.brief_head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.stale_lines(err), [])
        self.assertEqual([s["stage"] for s in self.signed()], ["brief"])


if __name__ == "__main__":
    unittest.main()
