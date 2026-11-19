"""The parallel defaults are written once, in `config.PARALLEL_DEFAULTS`: `parallel.settings` without a loaded
config reads a copy of it (the schema's `parallel` block is held to it by tests/test_plane_config_defaults.py)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import config, parallel

PLANE = Path(__file__).resolve().parents[1]


class ParallelDefaults(unittest.TestCase):
    def test_settings_without_a_loaded_config_is_a_copy_of_the_defaults(self):
        cfg = config.Config(root=PLANE, project_id="demo", task_log={}, package_docs=None)
        self.assertIsNone(cfg.parallel)
        got = parallel.settings(cfg)
        self.assertEqual(got, config.PARALLEL_DEFAULTS)
        before = json.dumps(config.PARALLEL_DEFAULTS)
        got["max_in_flight"] = 4
        got["shared"].append("x")
        got["exclusive"].append("y")
        self.assertEqual(json.dumps(config.PARALLEL_DEFAULTS), before)
        self.assertEqual(parallel.settings(cfg), config.PARALLEL_DEFAULTS)


if __name__ == "__main__":
    unittest.main()
