"""A temp git repository, home and bindings directory, to run `ccp init` against. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import GIT_ENV, PLANE_ROOT

PLANE = PLANE_ROOT
CCP = PLANE / "bin" / "ccp"


class InitCase(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        base = Path(self._d.name).resolve()
        self.home, self.bindings, self.repo = base / "home", base / "bindings", base / "repo"
        self.home.mkdir()
        self.repo.mkdir()
        self.git("init", "-q", ".")
        self.env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        self.env.update(GIT_ENV, HOME=str(self.home), CCP_BINDINGS_DIR=str(self.bindings))

    def tearDown(self):
        self._d.cleanup()

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True, env={**os.environ, **GIT_ENV})

    def ccp(self, *args, cwd=None, **env):
        return subprocess.run([str(CCP), *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              env={**self.env, **env})

    def init(self, *args, cwd=None):
        r = self.ccp("init", *args, cwd=cwd)
        return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)

    def machine_reads_usage(self) -> None:
        """The machine file sets an allowance command, so init has no unread-usage warning to count (§25.1)."""
        self.bindings.mkdir(exist_ok=True)
        (self.bindings / "machine.json").write_text(json.dumps({"allowance_cmd": "true"}))

    @property
    def binding(self) -> Path:
        return self.bindings / "demo.yaml"

    @property
    def queue(self) -> Path:
        return self.home / ".delivery-queue" / "demo"
