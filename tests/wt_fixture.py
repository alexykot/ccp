"""The toolkit product with plane.json rewritten in the main checkout, for the worktree tests. A fixture module: it
holds no tests."""
from __future__ import annotations

import json

from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture


class WtFixture(ToolkitFixture):
    """The toolkit product with plane.json rewritten in the main checkout (ccp runs with --root main)."""

    def plane(self, **blocks) -> None:
        body = {**self.PLANE_JSON, **blocks}
        self.write("docs/delivery/plane.json", json.dumps(body))

    def head(self) -> str:
        return git(self.main, "rev-parse", "origin/main")

    def wt(self, *args: str):
        code, parsed, body, err = self.ccp("wt", *args, root=self.main)
        if parsed is None and body.strip().startswith("["):
            parsed = json.loads(body)
        return code, parsed, body, err
