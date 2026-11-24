"""The plane.json blocks' keys and defaults are written once, in `config.BLOCK_DEFAULTS`; this is the one test
that holds `contracts/plane_config.schema.json` to it: the schema lists exactly the registry's blocks and each
block's keys, and every `default` it states is the code's value. A `task_log.dir` that is not a path relative to the
product root is refused at load, and a `task_log` block given as null loads as the defaults (§8.1)."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from typing import Any

from ccp import config
from tests.helpers import PLANE_ROOT, Product

SCHEMA = json.loads((PLANE_ROOT / "contracts/plane_config.schema.json").read_text())

# The nested objects whose defaults the code keeps in a dict of their own, not inside the block's: the block,
# the key, the dict, and the extra keys the schema lists besides it (the keys the plane removed or merged, which
# `config.KEY_OUTCOMES` holds and the schema marks deprecated).
SEPARATE = (("suite", "summary", config.SUITE_SUMMARY_DEFAULTS, tuple(config.old_keys("suite.summary"))),
            ("verify", "accept_cache", config.ACCEPT_CACHE_DEFAULTS, ()))


class PlaneConfigDefaults(unittest.TestCase):
    def compare(self, where: str, props: dict[str, Any], defaults: dict[str, Any], *, extra: tuple = (),
                every_default: bool = False) -> None:
        """The schema's `props` name exactly the keys of `defaults` (and `extra`), and each `default` it states
        equals the code's value. `every_default`: a key that is not itself an object of listed keys must state one."""
        self.assertEqual(set(props), set(defaults) | set(extra), f"{where}: the schema's keys and the code's")
        for key, value in defaults.items():
            prop = props[key]
            nested = isinstance(value, dict) and bool(value) and "properties" in prop  # {}: any keys are allowed
            if "default" in prop:
                self.assertEqual(prop["default"], value, f"{where}.{key}: the schema's default and the code's")
            elif every_default and not nested:
                self.fail(f"{where}.{key}: the schema states no default (the code's is {value!r})")
            if nested:
                self.compare(f"{where}.{key}", prop["properties"], value)

    def test_the_schema_lists_the_registry_blocks_and_nothing_else(self):
        self.assertEqual(set(SCHEMA["properties"]) - {"$schema", "_note", *config.REQUIRED_KEYS,
                                                      *config.OPTIONAL_TOP_KEYS},
                         set(config.BLOCK_DEFAULTS))
        self.assertEqual(SCHEMA["properties"]["spec_paths"]["default"], list(config.SPEC_PATHS_DEFAULT))
        self.assertEqual(SCHEMA["required"], list(config.REQUIRED_KEYS))
        self.assertEqual(config.BLOCKS, tuple(config.BLOCK_DEFAULTS))

    def test_every_block_has_the_schemas_keys_and_defaults(self):
        for block, defaults in config.BLOCK_DEFAULTS.items():
            with self.subTest(block=block):
                self.compare(block, SCHEMA["properties"][block]["properties"], defaults,
                             extra=tuple(config.old_keys(block)), every_default=True)

    def test_nested_defaults_the_code_keeps_apart_match_the_schema(self):
        for block, key, defaults, extra in SEPARATE:
            with self.subTest(block=block, key=key):
                self.compare(f"{block}.{key}", SCHEMA["properties"][block]["properties"][key]["properties"],
                             defaults, extra=extra)

    def test_a_task_log_dir_that_is_not_a_path_is_refused_at_load(self):
        for bad in (None, "", 5):
            with self.subTest(dir=bad):
                p = Product({"project_id": "demo", "language": "none", "task_log": {"dir": bad}}, bare=True)
                self.addCleanup(p.cleanup)
                with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
                    config.load(p.root)
                self.assertIn("task_log.dir", str(cm.exception))

    def test_a_null_task_log_block_loads_as_the_defaults(self):
        p = Product({"project_id": "demo", "language": "none", "task_log": None}, bare=True)
        self.addCleanup(p.cleanup)
        with redirect_stderr(io.StringIO()):
            cfg = config.load(p.root)
        self.assertEqual(cfg.task_log, config.TASK_LOG_DEFAULTS)

    def test_an_absolute_or_parent_task_log_dir_is_refused_at_load(self):
        for bad in ("/tmp/x", "../x", "docs/../../x"):
            with self.subTest(dir=bad):
                p = Product({"project_id": "demo", "language": "none", "task_log": {"dir": bad}}, bare=True)
                self.addCleanup(p.cleanup)
                with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
                    config.load(p.root)
                self.assertIn("task_log.dir", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
