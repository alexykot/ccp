"""The plane.json blocks' keys and defaults are written once, in `config.BLOCK_DEFAULTS`; this is the one test
that holds `contracts/plane_config.schema.json` to it: the schema lists exactly the registry's blocks and each
block's keys, and every `default` it states is the code's value."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from ccp import config

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())

# The nested objects whose defaults the code keeps in a dict of their own, not inside the block's: the block,
# the key, the dict, and the extra keys the schema lists besides it (the names a key had before).
SEPARATE = (("suite", "summary", config.SUITE_SUMMARY_DEFAULTS, tuple(config.SUITE_SUMMARY_ALIASES)),
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
        self.assertEqual(set(SCHEMA["properties"]) - {"$schema", "_note", *config.REQUIRED_KEYS},
                         set(config.BLOCK_DEFAULTS))
        self.assertEqual(SCHEMA["required"], list(config.REQUIRED_KEYS))
        self.assertEqual(config.BLOCKS, tuple(config.BLOCK_DEFAULTS))

    def test_every_block_has_the_schemas_keys_and_defaults(self):
        for block, defaults in config.BLOCK_DEFAULTS.items():
            with self.subTest(block=block):
                self.compare(block, SCHEMA["properties"][block]["properties"], defaults, every_default=True)

    def test_nested_defaults_the_code_keeps_apart_match_the_schema(self):
        for block, key, defaults, extra in SEPARATE:
            with self.subTest(block=block, key=key):
                self.compare(f"{block}.{key}", SCHEMA["properties"][block]["properties"][key]["properties"],
                             defaults, extra=extra)


if __name__ == "__main__":
    unittest.main()
