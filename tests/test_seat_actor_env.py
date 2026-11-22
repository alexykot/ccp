"""SPEC §9.1, §11.1, §18.2: the plugin's hooks drop an `ACTOR` the session exports before they run `ccp`, so each
call records as `queue.actor`'s default whatever the session names; only the lead's own calls name the lead."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import LEAD_ENV, PLANE_ROOT, Product

HOOKS = PLANE_ROOT / "plugin" / "hooks"
STUB = """#!/usr/bin/env bash
# A stand-in `ccp`: logs the call (`<command> [<action>]`) and the ACTOR it sees, then answers as ccp would.
printf '%s\\t%s\\n' "$3${{4:+ $4}}" "${{ACTOR-unset}}" >> {log}
case "$3 ${{4:-}}" in
  "where "*) echo '{where}' ;;
  "tasks rotation-due") echo '{{"due": false}}' ;;
  "tasks list") echo '[{{"task_id": "0001-a", "status": "pending", "depends_on": ""}}]' ;;
  "tasks next") echo '{{}}' ;;
esac
exit 0
"""


class TheHooksDropTheSessionsActor(unittest.TestCase):
    """Each hook, run with the lead's `ACTOR` exported and a stub `ccp` on PATH that logs the `ACTOR` it sees."""

    def setUp(self):
        self.prod = Product({"architect": {}})  # the seat on: the idle hook asks `ccp tasks next` too
        self.addCleanup(self.prod.cleanup)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        self.q, self.log, bin_dir = d / "queue", d / "calls.log", d / "bin"
        self.q.mkdir()
        bin_dir.mkdir()
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a"]}))
        stub = bin_dir / "ccp"
        where = json.dumps({"queue_root": str(self.q), "ccp": str(stub), "plane": str(PLANE_ROOT)})
        stub.write_text(STUB.format(log=self.log, where=where))
        stub.chmod(0o755)
        self.env = {**os.environ, **LEAD_ENV, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                    "CLAUDE_PROJECT_DIR": str(self.prod.root)}

    def calls(self) -> dict[str, str]:
        """Each `ccp` call the hook made, by command, with the ACTOR the stub saw."""
        lines = self.log.read_text().splitlines() if self.log.is_file() else []
        return dict(line.split("\t", 1) for line in lines)

    def hook(self, name: str, *args: str, stdin: dict) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HOOKS / name), *args], input=json.dumps(stdin), capture_output=True,
                              text=True, env=self.env, cwd=self.prod.root, timeout=60)

    def test_the_run_binding_hook_runs_ccp_with_actor_unset(self):
        r = self.hook("run-binding.sh", "start", stdin={"agent_id": "a1", "agent_type": "ccp:delivery-implementer"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), {"agent start": "unset"})

    def test_each_of_the_idle_hook_s_four_ccp_calls_runs_with_actor_unset(self):
        r = self.hook("runner-idle.sh", stdin={"hook_event_name": "TeammateIdle", "teammate_name": "runner",
                                               "cwd": str(self.prod.root)})
        self.assertEqual(r.returncode, 2, r.stderr)  # 0001-a is ready: the runner is kept working
        self.assertEqual(self.calls(), {"where": "unset", "tasks rotation-due": "unset", "tasks list": "unset",
                                        "tasks next": "unset"})


if __name__ == "__main__":
    unittest.main()
