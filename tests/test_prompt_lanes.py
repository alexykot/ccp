"""SPEC §14.1, §14.2: what names a lane names one the product declares. A run given neither a lane nor a
command is pointed at the full role's lane as plane.json declares it, and the verify prompt's part item sends a
mutation check to `ccp mutate`, not to the part lane's module names."""
from __future__ import annotations

import unittest

from ccp import config, prompt, suite
from ccp.queue import QueueError
from tests.helpers import Product

GATE = ["scripts/gate.sh"]


class NoLaneRefusal(unittest.TestCase):
    def refusal(self, lanes: dict) -> str:
        p = Product({"suite": {"lanes": lanes}})
        self.addCleanup(p.cleanup)
        with self.assertRaises(QueueError) as cm:
            suite.resolve_stages(p.cfg, None, None)
        self.assertEqual(cm.exception.code, 2)
        return str(cm.exception)

    def test_a_product_declaring_only_gate_and_part_is_pointed_at_the_gate_lane(self):
        said = self.refusal({"gate": GATE, "part": GATE})
        self.assertIn("--lane gate ", said)
        self.assertIn("`scripts/gate.sh`", said)
        self.assertNotIn(f"--lane {config.SUITE_DEFAULTS['roles']['full']}", said)

    def test_a_staged_full_role_lane_is_named_without_a_command(self):
        said = self.refusal({"gate": [{"name": "unit", "cmd": "make test"}]})
        self.assertIn("--lane gate ", said)
        self.assertNotIn("make test", said)

    def test_with_no_full_role_lane_declared_the_command_goes_after_the_dashes(self):
        said = self.refusal({"part": GATE})
        self.assertIn(f"--lane {config.lane_for(None, 'full')} -- <command>", said)


class VerifyPartItem(unittest.TestCase):
    def test_the_verify_prompts_part_item_names_ccp_mutate(self):
        for lanes in ({"gate": GATE, "part": GATE}, {"gate": GATE}):
            p = Product({"suite": {"lanes": lanes}})
            self.addCleanup(p.cleanup)
            part = f"--lane {config.lane_for(p.cfg, 'part')}"  # a declared argv lane backticks the whole command
            text = prompt.suite_lanes(p.cfg, "verify")
            self.assertIn(part, text, lanes)
            self.assertIn("`ccp mutate`", text.split(part, 1)[1], lanes)


if __name__ == "__main__":
    unittest.main()
