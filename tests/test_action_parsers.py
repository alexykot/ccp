"""The commands that take their action as a first word give each action only its own arguments (SPEC §6.6, §12.1,
§19, §25.4, §26.6, §28.3): an argument that belongs to another action is refused by the parser, exit 2, with the
usage of the action that was called, never accepted and dropped. `ccp pr` refuses an unknown flag with the called
action's usage too (§15.5)."""
from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr

from ccp import cli

# Each command: an action called with its own arguments, and an argument that only another of its actions takes.
OWN = {
    "estimate": (["backfill", "--dry-run", "--json"], ["accuracy", "--dry-run"]),
    "board": (["build", "--quiet"], ["status", "--quiet"]),
    "allowance": (["session-wake", "--armed"], ["status", "--armed"]),
    "docs adr": (["list", "--json", "--dir", "d"], ["index", "--json"]),
    "wt": (["create", "--kind", "impl", "--task", "0001", "--shallow", "--own-hooks"], ["list", "--kind", "impl"]),
    "adr": (["supersede", "1", "2", "--decisions", "D2", "--by", "D1", "--archive"], ["check", "--note", "x"]),
    "architect": (["run", "--mode", "shape", "--adr", "1", "--actor", "x", "--review-id", "r", "--detach"],
                  ["triage", "--force"]),
}


def parse(*words: str) -> tuple[argparse.Namespace | None, int, str]:
    """The parsed namespace, or None with the parser's exit code; its stderr either way."""
    err = io.StringIO()
    with redirect_stderr(err):
        try:
            return cli.build_parser().parse_args(list(words)), 0, err.getvalue()
        except SystemExit as e:
            return None, int(e.code or 0), err.getvalue()


class ActionParsers(unittest.TestCase):
    def test_each_command_parses_an_actions_own_arguments(self):
        for command, (own, _) in OWN.items():
            a, code, err = parse(*command.split(), *own)
            self.assertEqual(code, 0, f"{command}: {err}")
            self.assertEqual(a.action, own[0], command)

    def refused(self, command: str) -> None:
        action, *foreign = OWN[command][1]
        a, code, err = parse(*command.split(), action, *foreign)
        self.assertEqual((a, code), (None, 2), err)
        self.assertIn("unrecognized arguments", err)
        self.assertIn(foreign[0], err)
        self.assertTrue(err.startswith(f"usage: ccp {command} {action} "), err)

    def test_estimate_accuracy_refuses_a_backfill_flag(self):
        self.refused("estimate")

    def test_board_status_refuses_a_build_flag(self):
        self.refused("board")

    def test_allowance_status_refuses_a_session_wake_flag(self):
        self.refused("allowance")

    def test_docs_adr_index_refuses_a_list_flag(self):
        self.refused("docs adr")

    def test_wt_list_refuses_a_create_flag(self):
        self.refused("wt")

    def test_adr_check_refuses_a_status_flag(self):
        self.refused("adr")

    def test_architect_triage_refuses_a_run_flag(self):
        self.refused("architect")

    def test_an_action_refuses_another_actions_positional(self):
        for words in (["board", "build", "0001"], ["adr", "check", "1"], ["architect", "status", "ar-1"],
                      ["wt", "gc", "ver-0001"]):
            a, code, err = parse(*words)
            self.assertEqual((a, code), (None, 2), f"{words}: {err}")
            self.assertTrue(err.startswith(f"usage: ccp {' '.join(words[:2])} "), err)

    def test_a_flag_before_the_action_word_is_refused(self):
        a, code, err = parse("wt", "--task", "0001", "list")
        self.assertEqual((a, code), (None, 2), err)

    def test_architect_actions_without_actor_or_scope_flags_still_carry_them_for_the_handler(self):
        for action, keys in (("due", ("actor",)), ("triage", ("actor",)), ("status", ("actor", "scope"))):
            a, code, err = parse("architect", action)
            self.assertEqual(code, 0, err)
            for key in keys:
                self.assertIsNone(getattr(a, key), (action, key))

    def test_the_parent_defaults_reach_every_action(self):
        a, code, err = parse("docs", "adr", "index")
        self.assertEqual(code, 0, err)
        self.assertEqual((a.fn, a.args, a.dry_run), (cli.cmd_adr, [], False))
        a, code, err = parse("wt", "gc")
        self.assertEqual(code, 0, err)
        self.assertEqual((a.fn, a.command), (cli.cmd_wt, []))

    def test_pr_refuses_an_unknown_flag_with_the_called_actions_usage(self):
        a, code, err = parse("pr", "view", "3", "--bogus")
        self.assertEqual((a, code), (None, 2), err)
        self.assertIn("--bogus", err)
        self.assertTrue(err.startswith("usage: ccp pr view "), err)


if __name__ == "__main__":
    unittest.main()
