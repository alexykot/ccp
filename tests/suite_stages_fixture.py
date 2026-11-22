"""The suite fixture with a plane.json `suite.lanes` setter, for the staged lanes' tests. A fixture module: it
holds no tests."""
from __future__ import annotations

import json

from tests.suite_fixture import PY, SuiteFixture


def _shell_py(code: str) -> str:
    """A stage command that runs a line of Python (quoted for the shell)."""
    return f"{PY} -c {json.dumps(code)}"


class StagedFixture(SuiteFixture):
    def lanes(self, lanes: dict, **suite_extra) -> None:
        """Set the runner checkout's plane.json suite lanes."""
        p = self.runner / "docs/delivery/plane.json"
        cfg = json.loads(p.read_text())
        cfg["suite"] = {"lanes": lanes, **suite_extra}
        p.write_text(json.dumps(cfg))

    def ended(self) -> dict:
        return [x for x in self.rows() if x["op"] == "ended"][-1]
