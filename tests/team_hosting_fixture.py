"""A product and a claude-team queue with a `run_cmd` that runs a script against it. A fixture module: it holds no
tests."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import binding, PLANE_ROOT, Product


TEAM = PLANE_ROOT / "scripts" / "team.sh"
HOOK = PLANE_ROOT / "plugin" / "hooks" / "runner-idle.sh"


class TeamCase(unittest.TestCase):
    # The runner's worktree is derived from the binding's product root (SPEC §8.3), so a spawn makes it from
    # origin/<integration>: the product has an origin with its `main` pushed unless a class sets this False.
    with_origin = True

    def setUp(self):
        self.prod = Product()
        self.prod.write("docs/delivery/SPEC-MAINTAINER.md", "# protocol\n")
        self.prod.write("docs/delivery/REVIEW-TRIAGE.md", "# triage\n")
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text(binding(product_root=self.prod.root))
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        (self.q / "tasks").mkdir()
        for tid in ("0001-a", "0002-b"):  # claimed tasks have a runtime file (the runner writes it at claim)
            (self.q / "tasks" / f"{tid}.json").write_text(json.dumps({"task_id": tid, "waiting_on": None}))
        self.env = {**os.environ, "QUEUE_ROOT": str(self.q)}
        self.env.pop("PROJECT_YAML", None)
        self.env.pop("ACTOR", None)
        self._origin: Path | None = None
        if self.with_origin:
            self.origin()

    def tearDown(self):
        self.prod.cleanup()
        self._q.cleanup()

    def patch_default(self, table: str, key: str, value) -> None:
        """Run the child processes of this test with `ccp.config.<table>[key]` set to `value`: a reader that
        takes the setting from ccp's loaded configuration follows it, one with a default of its own does not."""
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        (Path(d.name) / "sitecustomize.py").write_text(
            f"import sys\nsys.path.insert(0, {str(PLANE_ROOT)!r})\nfrom ccp import config\n"
            f"config.{table}[{key!r}] = {value!r}\n")
        self.env["PYTHONPATH"] = os.pathsep.join(p for p in (d.name, os.environ.get("PYTHONPATH")) if p)

    def run_cmd(self, *argv, stdin=None):
        return subprocess.run([str(a) for a in argv], capture_output=True, text=True, env=self.env, input=stdin)

    def team(self, *argv):
        r = self.run_cmd("bash", TEAM, *argv)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else r.stdout), r.stderr

    def events(self):
        p = self.q / "observability" / "events.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines()] if p.is_file() else []

    def origin(self, push: bool = True) -> Path:
        """Make the product a git checkout with a bare origin; push its `main` there unless `push` is False
        (an origin with no integration branch). Returns the origin; a second call returns the same one."""
        from tests.git_helpers import git
        if self._origin is not None:
            return self._origin
        o = tempfile.TemporaryDirectory()
        self.addCleanup(o.cleanup)
        bare = Path(o.name) / "origin.git"
        git(Path(o.name), "init", "-q", "--bare", "-b", "main", str(bare))
        git(self.prod.root, "init", "-q", "-b", "main")
        git(self.prod.root, "remote", "add", "origin", str(bare))
        git(self.prod.root, "add", ".")
        git(self.prod.root, "commit", "-q", "--allow-empty", "-m", "base")
        if push:
            git(self.prod.root, "push", "-q", "-u", "origin", "main")
        self._origin = bare
        return bare

    def task_wait(self, tid):
        p = self.q / "tasks" / f"{tid}.json"
        return json.loads(p.read_text()).get("waiting_on") if p.is_file() else None
