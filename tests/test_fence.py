"""The test fence (tests/__init__.py): a caller's exported queue and binding never reach a test (§14)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
