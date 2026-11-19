"""A review opens only on a PR whose body names its task (SPEC §15.2): `ccp prompt review` reads the
body with `gh pr view <pr> --json body` and refuses (exit 2), nothing opened, a body that does not
contain the task id; a body `gh` cannot read is a warning on the run. The implementer's prompt gives the
body's first line, with the full id."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

from tests.test_toolkit import ToolkitFixture

BODY_GH = r'''#!/usr/bin/env python3
"""A stand-in for gh: `pr view <n> --json body` prints the body in FAKE_GH_BODY, and logs its argv."""
import json, os, sys
open(os.environ["FAKE_GH_BODY"] + ".argv", "a").write(json.dumps(sys.argv[1:]) + "\n")
if sys.argv[1:3] == ["pr", "view"] and "body" in sys.argv:
    print(json.dumps({"body": open(os.environ["FAKE_GH_BODY"]).read()}))
    sys.exit(0)
print("unexpected call", file=sys.stderr)
sys.exit(1)
'''


class PrBody(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        t = Path(self._tmp.name)
        (t / "body-gh").write_text(BODY_GH)
        (t / "body-gh").chmod(0o755)
        self.body = t / "body.md"
        gh = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(t / "body-gh"), "FAKE_GH_BODY": str(self.body)})
        gh.start()
        self.addCleanup(gh.stop)

    def review(self):
        return self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "abc1234")

    def runs(self) -> list[str]:
        return sorted(p.name for p in (self.q / "runs").glob("0002-second/*.json")) if (self.q / "runs").is_dir() else []

    def test_a_body_naming_another_task_is_refused_naming_the_task_and_the_pr(self):
        self.body.write_text("## What\n\nTask 0003-third: something else entirely.\n")
        code, _, out, err = self.review()
        self.assertEqual(code, 2, out + err)
        self.assertIn("0002-second", err)
        self.assertIn("#7", err)
        self.assertEqual(self.runs(), [])  # nothing opened
        self.assertEqual(list(self.q.glob("prompts/0002-second/review*")), [])
        argv = [json.loads(x) for x in Path(str(self.body) + ".argv").read_text().splitlines()]
        self.assertEqual(argv, [["pr", "view", "7", "--json", "body"]])  # the PR asked for by its number

    def test_a_body_naming_its_task_renders_the_prompt(self):
        self.body.write_text("## What\n\nTask 0002-second: the change.\n")
        code, body, out, err = self.review()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(Path(body["prompt_path"]).is_file())
        self.assertEqual([w for w in body.get("warnings", []) if not w.startswith("behind_tip not checked")], [])
        self.assertEqual(self.runs(), ["review.json"])

    def test_a_body_gh_cannot_read_is_a_warning_and_the_review_opens(self):
        with mock.patch.dict(os.environ, {"CCP_GH_BIN": str(Path(self._tmp.name) / "no-such-gh")}):
            code, body, out, err = self.review()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("not checked for 0002-second" in w for w in body["warnings"]), body)

    def test_a_failing_gh_is_a_warning_too(self):
        code, body, out, err = self.review()  # no body file: the stand-in exits 1 with a traceback
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("not checked for 0002-second" in w for w in body["warnings"]), body)

    def test_other_phases_do_not_read_the_body(self):
        self.body.write_text("Task 0003-third\n")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(Path(str(self.body) + ".argv").exists())

    def test_the_implement_prompt_gives_the_body_its_first_line_with_the_full_id(self):
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertIn("`Task: 0002-second`", Path(body["prompt_path"]).read_text())


if __name__ == "__main__":
    unittest.main()
