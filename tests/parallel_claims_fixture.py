"""A product with six scoped tasks, parallel on at 2, for the parallel claim tests. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import TASK, machine_file
from tests.toolkit_fixture import ToolkitFixture


def task(tid: str, scope_in: str, status: str = "pending", extra: str = "") -> str:
    text = TASK.format(tid=tid, title=tid[5:].title(), status=status, deps="", ver="*Append-only.*")
    text = text.replace("- **In:** it", f"- **In:** {scope_in}\n- **Out:** `other/thing.py`")
    return text.replace("updated: 2026-09-30\n", f"updated: 2026-09-30\n{extra}") if extra else text


class ParallelFixture(ToolkitFixture):
    """Six tasks with Scope paths, parallel on at 2, a 5-hour reading the test sets."""

    def setUp(self):
        super().setUp()
        self.reading = Path(self._tmp.name) / "reading.json"
        self.five(10)
        self.plane(max_in_flight=2, exclusive=["db/schema.sql"])
        self.write("Makefile", "all:\n")
        self.write("docs/delivery/tasks/0002-second.md",
                   task("0002-second", "`src/app/pool.py` (`coverage`), `tests/test_pool.py`, `Makefile`"))
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/views.py`, `tests/test_views.py`"))
        self.write("docs/delivery/tasks/0004-fourth.md", task("0004-fourth", "`src/app/pool.py` (the probe rule)"))
        self.write("docs/delivery/tasks/0005-fifth.md", task("0005-fifth", "`db/schema.sql`, `src/db.py`"))
        self.write("docs/delivery/tasks/0006-sixth.md", task("0006-sixth", "an operator step, nothing in the repo"))
        self.write("docs/delivery/tasks/0007-watch.md", task("0007-watch", "a watch", extra="parallel: true\n"))
        (self.q / "work.json").write_text(json.dumps({"status": "running"}))

    def plane(self, **par):
        machine_file(self, allowance_cmd=f"cat '{self.reading}'")
        # the default schedule is `clashes`: these tests are about paths
        self.edit_plane(lambda cfg: cfg.update(parallel={"schedule": "paths", **par}))

    def five(self, pct):
        self.reading.write_text(json.dumps({"five_hour": {"utilization": pct}, "seven_day": {"utilization": 5}}))

    def claim(self, tid):
        return self.ccp("tasks", "claim", tid, root=self.main)

    def next(self):
        return self.ccp("tasks", "next", root=self.main)

    def work(self):
        return json.loads((self.q / "work.json").read_text())
