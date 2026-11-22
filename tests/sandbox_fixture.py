"""A temp tree inside the sandbox fence for the `ccp sandbox` tests. A fixture module: it holds no tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PLANE_ROOT

PLANE = PLANE_ROOT
CCP = PLANE / "bin" / "ccp"


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.fence = Path(os.environ["CCP_SANDBOX_ROOT"]).resolve()
        self.base = Path(tempfile.mkdtemp(dir=self.fence)).resolve()
        self._out = tempfile.TemporaryDirectory()  # outside the fence's root
        self.installation = Path(self._out.name).resolve() / "projects"
        self.installation.mkdir()
        (self.installation / "live.yaml").write_text("project_id: live\nqueue_root: /nonexistent/live-queue\n")
        self.env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        self.env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        CCP_BINDINGS_DIR=str(self.installation))

    def tearDown(self):
        self._out.cleanup()
        shutil.rmtree(self.base, ignore_errors=True)

    def ccp(self, *args, cwd=None, **env):
        return subprocess.run([str(CCP), *args], cwd=cwd or self.base, capture_output=True, text=True,
                              env={**self.env, **env})

    def create(self, *args):
        r = self.ccp("sandbox", "create", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True,
                              env=self.env).stdout

    def listing(self):
        return {p.name: p.read_text() for p in self.installation.iterdir()}

    def plain(self, name="P"):
        """A product adopted with `ccp init` outside every sandbox: its binding in the stand-in installation,
        its queue beside it. Returns the product root and its queue."""
        root, q = Path(self._out.name).resolve() / name, Path(self._out.name).resolve() / f"{name}-queue"
        root.mkdir()
        self.git(str(root), "init", "-q")
        self.git(str(root), "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "commit.gpgsign=false",
                 "commit", "-q", "--allow-empty", "-m", "first")
        r = self.ccp("--root", str(root), "init", "--project-id", name.lower(), "--queue-root", str(q))
        self.assertEqual(r.returncode, 0, r.stderr)
        return root, q
