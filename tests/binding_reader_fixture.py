"""A temp bindings directory with one binding, its queue and its product, for the binding reader's tests. A fixture
module: it holds no tests."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class BindingDir(unittest.TestCase):
    """A temp bindings directory with one binding, its queue and its product (no tests of its own)."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        base = Path(self._d.name).resolve()
        self.bindings = base / "bindings"
        self.bindings.mkdir()
        self.queue = base / "queue"
        self.queue.mkdir()
        self.product = base / "product"
        self.product.mkdir()
        self.binding = self.bindings / "demo.yaml"
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}\nqueue_root: {self.queue}\n"
                                "integration_branch: steward\n")
        env = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings)})
        env.start()
        self.addCleanup(env.stop)
        for k in ("PROJECT_YAML", "PLANE_PROJECT_YAML"):
            os.environ.pop(k, None)
