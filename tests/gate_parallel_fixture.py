"""A temp git repository holding copies of the gate scripts, with the test modules the gate tests write to it. A
fixture module: it holds no tests."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.helpers import with_test_methods


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ("gate.sh", "gate_parallel.py", "gate_result.py")
OK = with_test_methods("""
import unittest
class A(unittest.TestCase):
    def t_one(self): self.assertTrue(True)
    @unittest.skip("not here")
    def t_two(self): pass
""")
MORE = with_test_methods("""
import unittest
class B(unittest.TestCase):
    def t_a(self): self.assertEqual(1, 1)
    def t_b(self): self.assertEqual(2, 2)
    def t_c(self): self.assertEqual({lhs}, 3)
""")


class GateFixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        for s in SCRIPTS:
            shutil.copy(ROOT / "scripts" / s, self.repo / "scripts" / s)
        (self.repo / "tests" / "__init__.py").write_text("")
        (self.repo / ".gitignore").write_text("__pycache__/\n")  # as the plane's own repo has it
        self.meet = Path(self._tmp.name) / "meet"
        self.meet.mkdir()
        self.result = Path(self._tmp.name) / "result.json"
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", "init"], check=True)

    def module(self, name: str, body: str) -> None:
        (self.repo / "tests" / f"{name}.py").write_text(textwrap.dedent(body))

    def gate(self, workers: str | None = "2", names: tuple[str, ...] = (),
             **extra: str | None) -> subprocess.CompletedProcess[str]:
        """Run the fixture's gate, given `names` as its arguments; `extra` sets a variable, or unsets it with
        None. Its test cache is the fixture's own (GATE_CACHE_DIR), never the caller's, and it runs warm
        unless GATE_COLD or CCP_SUITE_COLD is given."""
        env = {k: v for k, v in os.environ.items()
               if k not in ("GATE_WORKERS", "CCP_SUITE_RESULT", "GATE_CACHE_DIR", "GATE_COLD", "CCP_SUITE_COLD")}
        env.update(MEET_DIR=str(self.meet), CCP_SUITE_RESULT=str(self.result),
                   GATE_CACHE_DIR=str(Path(self._tmp.name) / "gate-cache"))
        if workers is not None:
            env["GATE_WORKERS"] = workers
        for k, v in extra.items():
            env.pop(k, None) if v is None else env.__setitem__(k, v)
        return subprocess.run(["bash", str(self.repo / "scripts" / "gate.sh"), *names], capture_output=True,
                              text=True, env=env, timeout=120)

    def read(self) -> dict:
        return json.loads(self.result.read_text())
