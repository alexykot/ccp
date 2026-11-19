"""`usage.account`: the one function that reads the facts about the account on the machine (the
allowance command, the weekly stop, the usage windows, the session park and wake, the parallel session
ceiling), and the readers that take them from it."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path

from ccp import config, parallel, usage


def cfg_with(telemetry=None, parallel_block=None) -> config.Config:
    return config.Config(root=Path("."), project_id="x", task_log={}, package_docs=None,
                         telemetry=telemetry, parallel=parallel_block)


class AccountTests(unittest.TestCase):
    def test_no_telemetry_or_parallel_block_gives_the_defaults(self):
        for tel in (None, {}):
            a = usage.account(cfg_with(tel, None))
            self.assertEqual((a["park_pct"], a["wake_arm_pct"], a["wake_margin_s"], a["ceiling_pct"]),
                             (95, 50, 180, 60))
            self.assertIsNone(a["stop_weekly"])
            self.assertIsNone(a["allowance_cmd"])
            self.assertEqual(a["windows"], {
                "seven_day": {"kind": "weekly", "stop_pct": None, "park_pct": None},
                "five_hour": {"kind": "session", "stop_pct": None, "park_pct": 95.0}})

    def test_the_built_in_defaults_give_the_same(self):
        a = usage.account(cfg_with(copy.deepcopy(config.TELEMETRY_DEFAULTS), copy.deepcopy(config.PARALLEL_DEFAULTS)))
        self.assertEqual((a["park_pct"], a["wake_arm_pct"], a["wake_margin_s"], a["ceiling_pct"],
                          a["stop_weekly"], a["allowance_cmd"]), (95, 50, 180, 60, None, None))

    def test_each_key_set(self):
        tel = {**config.TELEMETRY_DEFAULTS, "allowance_cmd": "echo {}", "allowance_stop_weekly": 88,
               "session_park_pct": 90, "session_wake_arm_pct": 40, "session_wake_margin_s": 30}
        par = {**config.PARALLEL_DEFAULTS, "session_ceiling_pct": 45}
        a = usage.account(cfg_with(tel, par))
        self.assertEqual((a["allowance_cmd"], a["stop_weekly"], a["park_pct"], a["wake_arm_pct"],
                          a["wake_margin_s"], a["ceiling_pct"]), ("echo {}", 88, 90.0, 40.0, 30, 45))
        self.assertEqual(a["windows"]["seven_day"]["stop_pct"], 88)
        self.assertEqual(a["windows"]["five_hour"]["park_pct"], 90.0)

    def test_session_park_pct_null_turns_the_park_off(self):
        a = usage.account(cfg_with({**config.TELEMETRY_DEFAULTS, "session_park_pct": None}, None))
        self.assertIsNone(a["park_pct"])
        self.assertIsNone(a["windows"]["five_hour"]["park_pct"])
        self.assertEqual(usage.session_settings(cfg_with({"session_park_pct": None}))[0], None)

    def test_bad_wake_values_fall_back_to_the_defaults(self):
        a = usage.account(cfg_with({"session_wake_arm_pct": 0, "session_wake_margin_s": True}))
        self.assertEqual((a["wake_arm_pct"], a["wake_margin_s"]), (50.0, 180))

    def test_windows_merge_over_the_built_in_two(self):
        tel = {"allowance_stop_weekly": 85, "windows": {
            "seven_day": {"stop_pct": 70}, "extra": {"kind": "session", "park_pct": 80}, "other": {"stop_pct": 60}}}
        w = usage.account(cfg_with(tel))["windows"]
        self.assertEqual(w["seven_day"], {"kind": "weekly", "stop_pct": 70.0, "park_pct": None})
        self.assertEqual(w["five_hour"]["park_pct"], 95.0)
        self.assertEqual(w["extra"], {"kind": "session", "stop_pct": None, "park_pct": 80.0})
        self.assertEqual(w["other"], {"kind": "weekly", "stop_pct": 60.0, "park_pct": None})
        self.assertEqual(usage.window_rules(cfg_with(tel)), w)


class ReadersTests(unittest.TestCase):
    def test_the_usage_rule_follows_the_allowance_command(self):
        self.assertFalse(parallel.reads_usage(cfg_with(None)))
        self.assertTrue(parallel.reads_usage(cfg_with({"allowance_cmd": "echo {}"})))

    def test_rule_5_judges_by_the_account_ceiling(self):
        cfg = cfg_with({"allowance_cmd": "echo {}"}, {**config.PARALLEL_DEFAULTS, "max_in_flight": 2,
                                                    "session_ceiling_pct": 40})
        cand = {"task_id": "a", "parallel": True}
        busy = [{"task_id": "b", "parallel": True}]
        why = parallel.join_refusal(cfg, cand, busy, {"five_hour": 50.0, "seven_day": 1.0})
        self.assertIn("session_ceiling_pct 40%", why or "")
        self.assertIsNone(parallel.join_refusal(cfg, cand, busy, {"five_hour": 30.0, "seven_day": 1.0}))


if __name__ == "__main__":
    unittest.main()
