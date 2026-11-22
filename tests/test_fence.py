"""The test fence (tests/__init__.py): a caller's exported queue and binding never reach a test (§14); and the
shared helpers (tests/helpers.py) load no `ccp` module on import, so a module that imports them for a path pays
nothing for it."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PLANE_ROOT

REPO = PLANE_ROOT


class FenceTest(unittest.TestCase):
    def test_inherited_queue_and_binding_are_cleared(self):
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "QUEUE_ROOT": d, "PROJECT_YAML": str(Path(d) / "project.yaml")}
            r = subprocess.run(
                [sys.executable, "-c",
                 "import os, tests; print(os.environ.get('QUEUE_ROOT'), os.environ.get('PROJECT_YAML'))"],
                cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["None", "None"])


class SharedHelpersTest(unittest.TestCase):
    def test_importing_the_helpers_loads_no_ccp_module(self):
        r = subprocess.run(
            [sys.executable, "-B", "-c",
             "import sys, tests.helpers; print(sorted(m for m in sys.modules if m.split('.')[0] == 'ccp'))"],
            cwd=REPO, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
