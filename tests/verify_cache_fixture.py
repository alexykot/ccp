"""The toolkit product with `verify.accept_cache` set, for the review cache tests. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import PLANE_ROOT
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture


class CacheFixture(ToolkitFixture):
    def plane(self, accept_cache=None, commit=True) -> None:
        body = dict(self.PLANE_JSON)
        if accept_cache is not None:
            body["verify"] = {"accept_cache": accept_cache}
        self.write("docs/delivery/plane.json", json.dumps(body))
        if commit:
            git(self.main, "add", "-A")
            git(self.main, "commit", "-q", "-m", "plane.json")
            git(self.main, "push", "-q", "origin", "main")
            git(self.runner, "fetch", "-q", "origin")
            git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def verify_prompt(self) -> str:
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        return (self.q / "prompts/0002-second/verify-prompt.md").read_text()

    def record(self, gate_runs: list[dict]):
        rec = json.loads((PLANE_ROOT / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", project_id="demo", head_sha="a" * 40)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        rec["gate"] = {"runs": gate_runs}
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))
