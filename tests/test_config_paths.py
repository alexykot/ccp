"""plane.json path lists that narrow a check (SPEC §15.2 `verify.skip_review.paths`, §16.5 rule 4
`merge.behind_tip_ignore`): an entry that matches every path is refused, naming it, whatever its spelling;
an entry that names some paths loads."""
from __future__ import annotations

import json
import unittest

from ccp import config
from tests.helpers import Product

EVERY = ("*/**", "**/*", "?*", "*/*", "[!z]*", "[^z]*", "**/**", "./**/*")
SOME = ("docs", "docs/notes", "*.md", "src/**", "**/*.py", "?", "tests/test_*.py", "[ab]*")


class EveryPath(unittest.TestCase):
    def setUp(self):
        self.prod = Product()
        self.addCleanup(self.prod.cleanup)

    def plane(self, **blocks) -> None:
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **blocks}))

    def test_behind_tip_ignore_refuses_a_pattern_that_matches_every_path(self):
        for every in EVERY:
            with self.subTest(every=every):
                self.plane(merge={"behind_tip_ignore": ["docs/notes", every]})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.prod.root)
                self.assertIn(f"merge.behind_tip_ignore: {every!r} matches every path", str(cm.exception))
                self.assertNotIn("'docs/notes' matches", str(cm.exception))

    def test_skip_review_paths_refuse_a_pattern_that_matches_every_path(self):
        for every in EVERY:
            with self.subTest(every=every):
                self.plane(verify={"skip_review": {"paths": ["docs", every], "proof": "true"}})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.prod.root)
                self.assertIn(f"verify.skip_review.paths: {every!r} matches every path", str(cm.exception))

    def test_a_pattern_that_names_some_paths_loads(self):
        self.plane(merge={"behind_tip_ignore": list(SOME)},
                   verify={"skip_review": {"paths": list(SOME), "proof": "true"}})
        cfg = config.load(self.prod.root)
        self.assertEqual((cfg.merge["behind_tip_ignore"], cfg.verify["skip_review"]["paths"]), (list(SOME), list(SOME)))


if __name__ == "__main__":
    unittest.main()
