"""`ccp verify`'s actions each take their own arguments (SPEC §15.2, §15.4, §15.5): a flag only another action
takes is refused by the parser, exit 2, with the usage of the action that was called, never dropped."""
from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr
from unittest import mock

from ccp import cli

# Each action called with its own arguments, and a flag that only another action takes.
OWN = {
    "record": (["verdict.json"], ["--check", "c-01", "--pass"]),
    "merge-ok": (["7", "--task", "0001-a"], ["--head", "abc1234"]),
    "check": (["0001-a", "--head", "abc1234"], ["--task", "0001-a"]),
    "spec-text": (["0001-a", "--base", "main", "--head", "abc1234"], ["--evidence", "ran it"]),
    "later": (["0001-a", "--check", "c-01", "--pass", "--evidence", "ran it", "--produced-by", "operator",
               "--operator-step", "0001-a-1"], ["--json"]),
    "deferred": (["--task", "0001-a", "--json"], ["--base", "main"]),
}


def parse(*words: str) -> tuple[argparse.Namespace | None, int, str]:
    """The parsed namespace, or None with the parser's exit code; its stderr either way."""
    err = io.StringIO()
    with redirect_stderr(err):
        try:
            return cli.build_parser().parse_args(["verify", *words]), 0, err.getvalue()
        except SystemExit as e:
            return None, int(e.code or 0), err.getvalue()


class VerifyParser(unittest.TestCase):
    def test_each_action_parses_its_own_arguments(self):
        for action, (own, _) in OWN.items():
            a, code, err = parse(action, *own)
            self.assertEqual(code, 0, f"{action}: {err}")
            self.assertEqual(a.action, action)

    def refused(self, action: str) -> None:
        own, foreign = OWN[action]
        a, code, err = parse(action, *own, *foreign)
        self.assertIsNone(a, action)
        self.assertEqual(code, 2, action)
        self.assertIn("unrecognized arguments", err)
        self.assertIn(foreign[0], err)
        self.assertTrue(err.startswith(f"usage: ccp verify {action} "), err)

    def test_record_refuses_a_later_flag(self):
        self.refused("record")

    def test_merge_ok_refuses_a_check_flag(self):
        self.refused("merge-ok")

    def test_check_refuses_a_merge_ok_flag(self):
        self.refused("check")

    def test_spec_text_refuses_a_later_flag(self):
        self.refused("spec-text")

    def test_later_refuses_a_deferred_flag(self):
        self.refused("later")

    def test_deferred_refuses_a_spec_text_flag(self):
        self.refused("deferred")

    def test_deferred_refuses_a_positional_task(self):
        a, code, err = parse("deferred", "0001-a")
        self.assertEqual((a, code), (None, 2), err)
        self.assertIn("0001-a", err)

    def test_an_action_refuses_a_missing_argument_it_needs(self):
        for words in (["record"], ["merge-ok"], ["check", "0001-a"], ["spec-text"],
                      ["later", "0001-a", "--check", "c-01", "--evidence", "ran it", "--produced-by", "operator"],
                      ["later", "0001-a", "--pass", "--fail", "--check", "c-01", "--evidence", "e",
                       "--produced-by", "operator"]):
            a, code, err = parse(*words)
            self.assertEqual((a, code), (None, 2), f"{words}: {err}")

    def test_merge_ok_takes_only_a_pr_number(self):
        a, code, err = parse("merge-ok", "task/0001-a")
        self.assertEqual((a, code), (None, 2), err)

    def test_each_action_says_what_it_does(self):
        sub = next(x for x in cli.build_parser()._actions if isinstance(x, argparse._SubParsersAction))  # noqa: SLF001
        verify = sub.choices["verify"]
        actions = next(x for x in verify._actions if isinstance(x, argparse._SubParsersAction))  # noqa: SLF001
        helps = {c.dest: c.help for c in actions._choices_actions}  # noqa: SLF001  (argparse keeps no public list)
        self.assertEqual(set(helps), set(OWN))
        self.assertEqual([a for a, h in helps.items() if not (h or "").strip()], [])

    def test_a_blank_target_is_refused_naming_the_argument(self):
        for words, metavar in ((["record", ""], "FILE"), (["record", " "], "FILE"), (["check", "", "--head", "abc1234"], "TASK"),
                               (["spec-text", " "], "TASK"),
                               (["later", "", "--check", "c-01", "--pass", "--evidence", "e", "--produced-by", "verifier"],
                                "TASK")):
            a, code, err = parse(*words)
            self.assertEqual((a, code), (None, 2), f"{words}: {err}")
            self.assertIn(f"argument {metavar}: takes a non-blank value", err)

    def test_a_target_keeps_its_value(self):
        a, code, err = parse("check", " 0001-a", "--head", "abc1234")
        self.assertEqual((code, a.target), (0, " 0001-a"), err)

    def test_a_parsed_verify_record_still_refreshes_the_board(self):
        for words, fires in ((["record", "verdict.json"], True), (["check", "0001-a", "--head", "abc1234"], False)):
            a, code, err = parse(*words)
            self.assertEqual(code, 0, err)
            with mock.patch("ccp.board.refresh") as r:
                cli.refresh_board(mock.Mock(), a, 0)
            self.assertEqual(r.call_count, int(fires), words)


if __name__ == "__main__":
    unittest.main()
