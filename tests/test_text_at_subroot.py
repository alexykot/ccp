"""A product whose root sits below its git toplevel (SPEC §6.7, §10.4): task and ADR files read at a commit
(`tasklog.text_at`) come from the product's own path, so `ccp tasks drop` reads the tip's copy of the task file and
`adr.in_force_at` reads the ADRs at the head."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import adr, cli, config, tasklog
from ccp.queue import lib, task_meta
from tests.helpers import GIT_ENV, TASK, binding, merged_plane
from tests.git_helpers import git

TID = "0002-second"


def task_text(status: str, refs: str = '"ADR-0001 D1"') -> str:
    """The task file of `TID`, citing `refs` in `adr_refs`."""
    text = TASK.format(tid=TID, title="Second", status=status, deps='"0001-first"', ver="*Append-only.*")
    return text.replace('spec_refs: ["S1"]\n', f'spec_refs: ["S1"]\nadr_refs: [{refs}]\n', 1)


def adr_text(d1: str) -> str:
    """ADR-0001 with its D1 in the state `d1`."""
    return adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted", "date": "2026-01-01",
                     "decisions": [f"D1 {d1}"]}) + "# ADR-0001 — T\n\n## Decision\n\n### D1. First\n\nOne.\n"


class SubRoot(unittest.TestCase):
    """The git repo's toplevel holds the product root `product/`, its origin a bare repo beside it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        t = Path(self._tmp.name).resolve()
        env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(t / "queue"), "ACTOR": lib.RUNNER})
        env.start()
        self.addCleanup(env.stop)
        git(t, "init", "-q", "--bare", "-b", "main", str(t / "origin.git"))
        self.repo = t / "repo"
        git(t, "clone", "-q", str(t / "origin.git"), str(self.repo))
        git(self.repo, "checkout", "-q", "-b", "main")
        self.root = self.repo / "product"
        self.write("docs/delivery/plane.json", json.dumps(merged_plane({"adr": {"dir": "docs/adr", "strict": True}})))
        self.write("docs/delivery/tasks/0001-first.md", TASK.format(
            tid="0001-first", title="First", status="done", deps="", ver="- 2026-09-30 — `cmd-01` pass — ran it"))
        self.task = self.write(f"docs/delivery/tasks/{TID}.md", task_text("pending"))
        self.write("docs/adr/0001-a.md", adr_text("not_built"))
        (self.repo / "README.md").write_text("the repo's own file, above the product root\n")
        tasklog.write_index(self.cfg)
        self.not_built = self.commit("init")
        git(self.repo, "push", "-q", "-u", "origin", "main")
        q = t / "queue"
        q.mkdir()
        (q / "project.yaml").write_text(binding(integration_branch="main", product_root=self.root))
        self.q = q

    @property
    def cfg(self) -> config.Config:
        return config.load(self.root)

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def commit(self, msg: str) -> str:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)
        return git(self.repo, "rev-parse", "HEAD")

    def ccp(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.root), *args])
        return code, out.getvalue() + err.getvalue()

    def test_the_root_is_below_the_toplevel(self):
        self.assertEqual(Path(git(self.root, "rev-parse", "--show-toplevel")).resolve(), self.repo)

    def test_text_at_reads_a_task_file_at_a_commit(self):
        rel = self.cfg.rel(self.task)
        committed = self.task.read_text()
        self.task.write_text(task_text("dropped"))  # the checkout's copy moves on; the commit's does not
        self.assertEqual(tasklog.text_at(self.cfg, self.not_built, rel), committed)
        self.assertIsNone(tasklog.text_at(self.cfg, "HEAD", "README.md"))  # the toplevel's file is not the root's

    def test_tasks_drop_reads_the_tips_copy(self):
        code, out = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out)
        self.task.write_text(task_text("dropped"))
        self.commit("Drop 0002")
        git(self.repo, "push", "-q", "origin", "HEAD:main")
        code, out = self.ccp("tasks", "drop", "0002", "--reason", "superseded")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads((self.q / "tasks" / f"{TID}.json").read_text())["status"], "dropped")

    def test_in_force_at_reads_the_adr_at_the_head(self):
        self.write("docs/adr/0001-a.md", adr_text("built"))
        flipped = self.commit("flip D1")
        meta = task_meta(self.cfg, TID)
        lines = adr.in_force_at(self.cfg, meta, self.not_built)  # the checkout says built; the head does not
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("`ccp adr decide 1 D1 built`", lines[0])
        self.assertEqual(adr.in_force_at(self.cfg, meta, flipped), [])


if __name__ == "__main__":
    unittest.main()
