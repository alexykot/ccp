"""A worker's prompt arrives whole (SPEC §13.2, §13.4): `ccp prompt` ends the rendered prompt with
`Prompt end: <token>`, keeps the token on the run, and hands the runner a pointer to the file;
`ccp report` refuses a report that does not repeat the run's token as `Prompt: <token>`."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.test_report_fields import HEAD, implement_report
from tests.test_toolkit import ToolkitFixture

RUN = "0002-second/implement"


class PromptEnd(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")

    def implement(self) -> dict:
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        return body

    def run_rec(self, run_id: str = RUN) -> dict:
        return json.loads((self.q / "runs" / f"{run_id}.json").read_text())

    def stored(self) -> Path:
        return self.q / "progress/0002-second/implement-report.md"

    def test_the_prompt_ends_with_the_token_the_run_keeps(self):
        body = self.implement()
        text = Path(body["prompt_path"]).read_text()
        token = self.run_rec()["prompt_token"]
        self.assertTrue(token)
        self.assertEqual(text.splitlines()[-1], f"Prompt end: {token}")
        self.assertEqual(text.count(token), 1)  # only the last line carries it, so a cut prompt lacks it
        self.assertEqual(body["prompt_token"], token)
        self.assertIn("`Prompt: <token>`", text)  # the report contract asks for it

    def test_the_agent_call_points_at_the_file(self):
        body = self.implement()
        self.assertIn(body["prompt_path"], body["agent_call"]["prompt"])

    def test_each_run_has_its_own_token(self):
        self.implement()
        first = self.run_rec()["prompt_token"]
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        second = self.run_rec(body["run_id"])["prompt_token"]
        self.assertNotEqual(first, second)
        self.assertEqual(Path(body["prompt_path"]).read_text().splitlines()[-1], f"Prompt end: {second}")

    def test_a_report_without_the_runs_token_is_refused_and_the_right_one_is_accepted(self):
        self.implement()
        token = self.run_rec()["prompt_token"]
        for text in (implement_report(), implement_report("Prompt: 0123456789ab"),
                     implement_report(f"Prompt end: {token}"), implement_report(outcome="blocked")):
            code, _, out, err = self.report(RUN, text, token=False)
            self.assertEqual(code, 2, text + out + err)
            self.assertIn(token, err)
            self.assertFalse(self.stored().exists())
            self.assertIsNone(self.run_rec()["reported_at"])
        code, _, out, err = self.report(RUN, implement_report(f"- **Prompt:** `{token}`"), token=False)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.stored().exists())
        self.assertIsNotNone(self.run_rec()["reported_at"])

    def test_a_run_opened_before_the_token_is_not_held_to_it(self):
        self.implement()
        path = self.q / "runs" / f"{RUN}.json"
        rec = json.loads(path.read_text())
        del rec["prompt_token"]
        path.write_text(json.dumps(rec))
        code, _, out, err = self.report(RUN, implement_report(), token=False)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.stored().exists())

    def test_every_phase_asks_for_the_token(self):
        for args in (("review", "0002", "--pr", "7", "--head", HEAD), ("verify", "0002", "--pr", "7", "--head", HEAD)):
            code, body, out, err = self.ccp("prompt", *args)
            self.assertEqual(code, 0, out + err)
            text = Path(body["prompt_path"]).read_text()
            self.assertIn("`Prompt: <token>`", text, args[0])
            self.assertEqual(text.splitlines()[-1], f"Prompt end: {self.run_rec(body['run_id'])['prompt_token']}")


if __name__ == "__main__":
    unittest.main()
