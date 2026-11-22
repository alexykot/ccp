"""A scratch plane, product and queue for the upgrade tests. A fixture module: it holds no tests."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli

from tests.helpers import GIT_ENV, Product, TASK


def task_text(tid: str, status: str, title: str, adopt: str | None) -> str:
    ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
    text = TASK.format(tid=tid, title=title, status=status, deps="", ver=ver)
    if adopt is not None:
        text = text.replace(f"status: {status}", f"status: {status}\nadopt: \"{adopt}\"", 1)
    return text


class UpgradeFixture:
    """A scratch plane (a git repo with a task log, standing in for the checkout `ccp` runs from), a
    scratch product and a scratch queue."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name).resolve()
        self.q = t / "queue"
        self.q.mkdir()
        self.bindings = t / "bindings"
        self.bindings.mkdir()
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(self.q), "ACTOR": "task-runner",
                                                "CCP_BINDINGS_DIR": str(self.bindings)})
        self.env.start()
        self.plane = Product()
        self.git("init", "-q", "-b", "main")
        self.plane_patch = mock.patch("ccp.queue.PLANE", self.plane.root)
        self.plane_patch.start()
        self.product = Product()

    def tearDown(self):
        self.plane_patch.stop()
        self.env.stop()
        self.plane.cleanup()
        self.product.cleanup()
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.plane.root), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def plane_task(self, tid: str, status: str, title: str = "A task", adopt: str | None = None) -> None:
        self.plane.write(f"docs/delivery/tasks/{tid}.md", task_text(tid, status, title, adopt))

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.product.root), *args])
        body = out.getvalue()
        return code, (json.loads(body) if body.strip().startswith("{") else None), err.getvalue()

    def product_json(self, **extra) -> None:
        self.product.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **extra}))

    def proposal(self, pid: str, status: str | None = None, built_task: str | None = None) -> None:
        p = self.q / "plane" / "proposals.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"op": "proposed", "id": pid, "at": "2026-11-01T00:00:00Z", "by": "implementer", "task_id": None,
                 "need": "a knob", "generic": "any product", "workaround": None, "frequency": "per-task"}]
        if status:
            rows.append({"op": "triaged", "id": pid, "at": "2026-11-02T00:00:00Z", "by": "plane-session",
                         "decision": status, "merged_into": None, "reason": "plane task"})
        if built_task:
            rows.append({"op": "built", "id": pid, "at": "2026-11-03T00:00:00Z", "by": "plane-session",
                         "built_task": built_task, "adopt": "x"})
        with p.open("a") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows)
