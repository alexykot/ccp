"""SPEC §9.3: `ccp orientation` prints what the plugin's SessionStart hook gives a session in this
product, for a session that started before the product was adopted."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from tests.helpers import Product

PLANE = Path(__file__).resolve().parents[1]
HOOK = PLANE / "plugin" / "hooks" / "orientation.sh"


def hook_text(root: Path) -> str:
    r = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True,
                       env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)})
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


def ccp(root: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["--root", str(root), "orientation"])
    return code, out.getvalue(), err.getvalue()


class TestOrientationCommand(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def test_a_managed_product_gets_the_hooks_orientation(self):
        code, out, err = ccp(self.p.root)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n"), hook_text(self.p.root).rstrip("\n"))
        self.assertIn("# CCP — Claude Control Plane", out)

    def test_the_planes_own_repo_gets_the_hooks_one_line(self):
        self.p.write("ccp/refs.py", "")  # what the hook takes for the plane's own repo
        self.p.write(".claude-plugin/marketplace.json", json.dumps({"name": "ccp"}))
        code, out, err = ccp(self.p.root)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.rstrip("\n"), hook_text(self.p.root))
        self.assertEqual(len(out.strip().splitlines()), 1)

    def test_a_directory_with_no_plane_json_is_refused(self):
        with tempfile.TemporaryDirectory() as other:
            code, out, _err = ccp(Path(other))
        self.assertEqual((code, out), (2, ""))

    def test_a_plugin_with_no_orientation_fails(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch("ccp.queue.PLANE", Path(empty)):
            code, out, err = ccp(self.p.root)
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no orientation", err)
