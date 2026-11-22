"""SPEC §2.4, §4.5: `ccp init` adds the session settings to `.claude/settings.json` when absent, the
runner teammate's prompt-cache lifetime and the lead's compaction window (350000, or the value a binding
still sets, with a warning, §29.3), and never overwrites one the product set. Scratch HOME, bindings, repos
and queues."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr

from ccp import config
from tests.init_fixture import PLANE, InitCase


class SessionSettings(InitCase):
    @property
    def settings_path(self):
        return self.repo / ".claude" / "settings.json"

    def write_settings(self, data):
        self.settings_path.parent.mkdir(exist_ok=True)
        self.settings_path.write_text(json.dumps(data))

    def settings(self):
        return json.loads(self.settings_path.read_text())

    def write_binding(self, window):
        self.bindings.mkdir(exist_ok=True)
        self.binding.write_text(f"project_id: demo\nintegration_branch: main\nproduct_root: {self.repo}\n"
                                f"queue_root: {self.queue}\n"
                                f"lead:\n  auto_compact_window: {window}\n")

    def adopt(self, *args):
        code, res = self.init("--project-id", "demo", *args)
        self.assertEqual(code, 0, res)
        return res

    def test_both_settings_are_added_beside_the_products_own_keys(self):
        self.write_settings({"permissions": {}})
        res = self.adopt()
        settings = self.settings()
        self.assertEqual(settings["subagentPromptCacheTtl"], "1h")
        self.assertEqual(settings["autoCompactWindow"], 350000)
        self.assertEqual(settings["permissions"], {})
        self.assertEqual(res["settings"], {"subagentPromptCacheTtl": "added", "autoCompactWindow": "added", "model": "added"})
        self.assertIn(".claude/settings.json", res["merged"])

    def test_values_the_product_set_are_kept_whatever_the_binding_says(self):
        self.write_settings({"subagentPromptCacheTtl": "5m", "autoCompactWindow": 200000})
        self.write_binding(500000)
        for args in ((), ("--force",)):
            res = self.adopt(*args)
            settings = self.settings()
            self.assertEqual((settings["subagentPromptCacheTtl"], settings["autoCompactWindow"]), ("5m", 200000), args)
            self.assertEqual(res["settings"], {"subagentPromptCacheTtl": "kept", "autoCompactWindow": "kept",
                                            "model": "kept" if args else "added"}, args)

    def test_one_setting_kept_the_other_added(self):
        self.write_settings({"autoCompactWindow": 200000})
        res = self.adopt()
        self.assertEqual(self.settings()["subagentPromptCacheTtl"], "1h")
        self.assertEqual(self.settings()["autoCompactWindow"], 200000)
        self.assertEqual(res["settings"], {"subagentPromptCacheTtl": "added", "autoCompactWindow": "kept", "model": "added"})

    def test_the_kept_bindings_window_goes_into_a_new_settings_file(self):
        self.write_binding(500000)
        res = self.adopt()
        self.assertIn("binding", res["kept"])
        self.assertEqual(self.settings()["autoCompactWindow"], 500000)
        self.assertEqual(self.settings()["subagentPromptCacheTtl"], "1h")

    def test_a_binding_rewritten_by_force_gives_the_default_window(self):
        self.write_binding(500000)
        res = self.adopt("--force")
        self.assertIn("binding", res["written"])
        self.assertEqual(self.settings()["autoCompactWindow"], 350000)

    def test_a_window_that_is_no_positive_whole_number_reads_as_the_default(self):
        for bad in ("big", "0", "-5", "2.5"):
            self.settings_path.unlink(missing_ok=True)
            self.write_binding(bad)
            self.adopt()
            self.assertEqual(self.settings()["autoCompactWindow"], 350000, bad)


    def test_a_mistyped_window_is_named_on_stderr_and_reads_as_the_default(self):
        self.write_binding("35O000")
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("lead.auto_compact_window", r.stderr)
        self.assertIn("35O000", r.stderr)
        self.assertEqual(self.settings()["autoCompactWindow"], 350000)

class LeadKnob(unittest.TestCase):
    def test_the_binding_contract_carries_the_window_and_its_default(self):
        schema = json.loads((PLANE / "contracts/project.schema.json").read_text())
        window = schema["properties"]["lead"]["properties"]["auto_compact_window"]
        self.assertEqual(window["default"], config.LEAD_DEFAULTS["auto_compact_window"])
        self.assertEqual(window["type"], "integer")

    def test_the_window_reads_a_positive_whole_number_else_the_default(self):
        self.assertEqual(config.lead_auto_compact_window({"auto_compact_window": "500000"}), 500000)
        self.assertEqual(config.lead_auto_compact_window({"auto_compact_window": " 7 "}), 7)
        for lead in ({}, {"auto_compact_window": "0"}, {"auto_compact_window": "x"}, {"other": "1"}):
            self.assertEqual(config.lead_auto_compact_window(lead), 350000, lead)

    def test_only_a_window_that_is_set_and_wrong_warns(self):
        for lead, warned in (({}, False), ({"other": "1"}, False), ({"auto_compact_window": "500000"}, False),
                             ({"auto_compact_window": "0"}, True), ({"auto_compact_window": "x"}, True)):
            err = io.StringIO()
            with redirect_stderr(err):
                config.lead_auto_compact_window(lead)
            self.assertEqual("lead.auto_compact_window" in err.getvalue(), warned, lead)


if __name__ == "__main__":
    unittest.main()
