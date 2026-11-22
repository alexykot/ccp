"""SPEC §9: the orientation hook reads the orientation from the plugin the harness names in
`CLAUDE_PLUGIN_ROOT`, and from its own plugin directory when that is unset."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PLANE_ROOT, Product

PLANE = PLANE_ROOT
HOOK = PLANE / "plugin" / "hooks" / "orientation.sh"


class OrientationHookPluginRoot(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._plugin = tempfile.TemporaryDirectory()
        self.plugin = Path(self._plugin.name)

    def tearDown(self):
        self.p.cleanup()
        self._plugin.cleanup()

    def run_hook(self, plugin_root: Path | None):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        env["CLAUDE_PROJECT_DIR"] = str(self.p.root)
        if plugin_root is not None:
            env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
        return subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env)

    def test_the_named_plugins_orientation_is_given(self):
        (self.plugin / "orientation.md").write_text("<!-- a maintainer's note -->\n# Elsewhere\nmarker-7f3a\n")
        r = self.run_hook(self.plugin)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("marker-7f3a", text)
        self.assertNotIn("a maintainer's note", text)
        self.assertNotEqual(text, json.loads(self.run_hook(None).stdout)["hookSpecificOutput"]["additionalContext"])

    def test_a_named_plugin_with_no_orientation_says_nothing(self):
        r = self.run_hook(self.plugin)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_unset_it_reads_its_own_plugins(self):
        r = self.run_hook(None)
        self.assertEqual(r.returncode, 0, r.stderr)
        own = (PLANE / "plugin" / "orientation.md").read_text()
        text = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(text.strip() and text.strip().splitlines()[0] in own)


if __name__ == "__main__":
    unittest.main()
