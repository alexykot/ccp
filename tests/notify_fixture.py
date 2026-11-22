"""A scratch product whose notify command appends a line to a file. A fixture module: it holds no tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest import mock

from ccp import config, tasklog

from tests.helpers import PLANE_ROOT
from tests.toolkit_fixture import ToolkitFixture, git


# One line per run: the trigger, project, task, id, reason, and the line ccp composes, `|`-separated
APPEND = ('printf \'%s|%s|%s|%s|%s|%s\\n\' "$CCP_NOTIFY_TRIGGER" "$CCP_PROJECT_ID" "$CCP_TASK_ID" '
          '"$CCP_NOTIFY_ID" "$CCP_NOTIFY_REASON" "$CCP_NOTIFY_LINE" >> "$NOTIFY_OUT"')


class ChannelFixture(ToolkitFixture):
    """A scratch product whose notify command appends a line to a file; no tests of its own."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "notify": {"command": APPEND}}

    def setUp(self):
        super().setUp()
        self.out = Path(self._tmp.name) / "notified.txt"
        self.out_env = mock.patch.dict(os.environ, {"NOTIFY_OUT": str(self.out)})
        self.out_env.start()
        self.addCleanup(self.out_env.stop)

    def set_plane(self, **blocks) -> None:
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg.update(blocks)
        self.write("docs/delivery/plane.json", json.dumps(cfg))

    def tag(self, *tids: str) -> None:
        """Give each task `review_point: R1`, commit and push it, and bring the runner worktree along."""
        for tid in tids:
            p = next((self.main / "docs/delivery/tasks").glob(f"{tid}-*.md"))
            p.write_text(p.read_text().replace("depends_on:", "review_point: R1\ndepends_on:", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "-A", "docs/delivery")
        git(self.main, "commit", "-q", "-m", "tag R1")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")


PLANE = PLANE_ROOT
