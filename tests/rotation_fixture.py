"""A team queue and binding for the rotation tests. A fixture module: it holds no tests."""
from __future__ import annotations

import json
import subprocess
import time

from tests.helpers import binding, PLANE_ROOT
from tests.toolkit_fixture import ToolkitFixture


TEAM = PLANE_ROOT / "scripts" / "team.sh"


def iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


class RotationFixture(ToolkitFixture):
    def setUp(self):
        super().setUp()
        self.binding()

    def binding(self, **runner):
        (self.q / "project.yaml").write_text(
            binding(integration_branch="main", product_root=self.main, runner=runner or None))

    def slots(self, **rec):
        spawned = iso(time.time() - 3600)
        slot = {"bound_name": "runner-1", "spawned_at": spawned, "tasks_done": 0, "rotated_at": None, **rec}
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0002-second"],
                                                      "runners": {"runner-1": slot}}))

    def work(self):
        return json.loads((self.q / "work.json").read_text())

    def claim(self, holder="runner-1"):
        return self.ccp("tasks", "claim", "0002", "--holder", holder, root=self.main)

    def team(self, *argv):
        r = subprocess.run(["bash", str(TEAM), *argv], capture_output=True, text=True)
        return r.returncode, r.stdout, r.stderr

    def span(self, name, tokens, at):
        (self.q / "board").mkdir(exist_ok=True)
        with (self.q / "board" / "usage-spans.jsonl").open("a") as fh:
            fh.write(json.dumps({"request_id": f"r{at}", "agent_id": f"{name}@session-abc", "at": iso(at),
                                 "input_tokens": 10, "cache_read_tokens": tokens - 110, "cache_creation_tokens": 100,
                                 "output_tokens": 999}) + "\n")

    def health(self):
        code, body, out, err = self.ccp("health", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        return body["rotation"]
