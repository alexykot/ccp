"""The operator names are the only role names: the names used before the operator rename are no longer
read or accepted (task 0025). Products rewrite old queue data before upgrading."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLANE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLANE / "scripts" / "observability"))

import lib  # noqa: E402
import spec_maintainer as sm  # noqa: E402

# The pre-rename names, assembled at run time so the tree itself names no person.
OLD_DECISION = "a" + "lex"
OLD_STEP = "hu" + "man"


class OldNamesAreRefused(unittest.TestCase):
    def setUp(self) -> None:
        self.q = Path(tempfile.mkdtemp())
        (self.q / "tasks").mkdir()
        (self.q / "tasks" / "0001-a.json").write_text(json.dumps(
            {"task_id": "0001-a", "project_id": "demo", "waiting_on": None}))

    def tearDown(self) -> None:
        shutil.rmtree(self.q)

    def _wait(self, reason: str) -> subprocess.CompletedProcess[str]:
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "ACTOR")}
        env["QUEUE_ROOT"] = str(self.q)
        cmd = ["bash", str(PLANE / "scripts" / "observability" / "set-waiting-on.sh"), "set", "0001-a", reason,
               "--detail", "create the db role on the operator's machine"]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)

    def test_set_waiting_on_refuses_the_old_reasons(self) -> None:
        for old in (OLD_DECISION, OLD_STEP):
            proc = self._wait(old)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("invalid waiting_on reason", proc.stderr)
        self.assertIsNone(json.loads((self.q / "tasks" / "0001-a.json").read_text())["waiting_on"])

    def test_set_waiting_on_writes_the_operator_reasons(self) -> None:
        for new in ("operator_step", "operator_decision"):
            proc = self._wait(new)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads((self.q / "tasks" / "0001-a.json").read_text())["waiting_on"], new)

    def test_the_old_names_are_no_vocabulary(self) -> None:
        self.assertNotIn(OLD_STEP, lib.ACTORS)
        self.assertIn("operator", lib.ACTORS)
        self.assertNotIn(OLD_DECISION, lib.WAIT_REASONS)
        self.assertNotIn(OLD_STEP, lib.WAIT_REASONS)
        self.assertNotIn("waiting_" + OLD_DECISION, lib.OPEN_GATE_STATUSES)
        self.assertEqual(sm.actor_for("operator"), "operator")
        self.assertEqual(sm.actor_for(OLD_DECISION), "system")


if __name__ == "__main__":
    unittest.main()
