"""A plane-launched `claude -p` (SPEC §24.3, house rule E8): its environment, its JSON, its quota stop."""
from __future__ import annotations

import json
import os
import unittest
from unittest import mock

from ccp import headless


class HeadlessEnv(unittest.TestCase):
    def test_tags_project_and_seat_and_keeps_other_attributes(self):
        keys = {k: "k" for k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        with mock.patch.dict(os.environ, {"OTEL_RESOURCE_ATTRIBUTES": "team=x,ccp.project_id=old", **keys}):
            env = headless.headless_env("demo", "docs-audit")
        self.assertEqual(env["OTEL_RESOURCE_ATTRIBUTES"], "team=x,ccp.project_id=demo,ccp.seat=docs-audit")
        for k in keys:
            self.assertNotIn(k, env)


class ClaudeArgv(unittest.TestCase):
    def test_the_keys_are_stripped_and_the_seat_s_override_is_the_binary(self):
        with mock.patch.dict(os.environ, {"CCP_TEST_SEAT_CLAUDE_BIN": "/opt/stub-claude"}):
            argv = headless.claude_argv("CCP_TEST_SEAT_CLAUDE_BIN", "Do it.", ["--output-format", "json"])
        self.assertEqual(argv, ["env", "-u", "ANTHROPIC_API_KEY", "-u", "CLAUDE_API_KEY", "-u", "ANTHROPIC_AUTH_TOKEN",
                                "/opt/stub-claude", "-p", "Do it.", "--output-format", "json"])
        with mock.patch.dict(os.environ, {"CCP_TEST_SEAT_CLAUDE_BIN": ""}):  # empty counts as unset
            self.assertEqual(headless.claude_argv("CCP_TEST_SEAT_CLAUDE_BIN", "x", [])[7:], ["claude", "-p", "x"])


class ClaudeJson(unittest.TestCase):
    def test_the_result_entry_of_a_list_or_the_last_object_line(self):
        res = {"type": "result", "result": "done"}
        self.assertEqual(headless.parse_claude_json(json.dumps([{"type": "system"}, res])), res)
        self.assertEqual(headless.parse_claude_json(f"noise\n{json.dumps(res)}\n"), res)
        self.assertEqual(headless.parse_claude_json(""), {})


class Quota(unittest.TestCase):
    def test_a_limit_error_is_a_session_stop_with_its_reset(self):
        res = {"is_error": True, "result": "5-hour limit reached; resets at 2026-11-22T10:00:00+00:00"}
        self.assertEqual(headless.detect_quota(res, "", ""), (True, "session", "2026-11-22T10:00:00Z"))

    def test_a_credit_error_and_a_clean_result(self):
        self.assertEqual(headless.detect_quota({"is_error": True, "result": "credit balance too low"}, "", "")[:2],
                         (True, "credit"))
        self.assertEqual(headless.detect_quota({"result": "ok"}, "", ""), (False, None, None))


if __name__ == "__main__":
    unittest.main()
