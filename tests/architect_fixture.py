"""The architect tests' harness: a committed product with the architect skill, a team-lead queue and a stub claude.
A fixture module: it holds no tests."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli

from tests.helpers import Product, binding


STUB = """#!/usr/bin/env bash
# Stub claude: answer with the report in $DA_STUB_REPORT, as `claude -p --output-format json` would.
python3 - "$@" <<'PY'
import json, os, re, subprocess, sys, time
prompt = sys.argv[sys.argv.index("-p") + 1]
R = os.environ["DA_STUB_REPORT"]
open(R + ".argv", "w").write(json.dumps(sys.argv[1:]))
open(R + ".cwd", "w").write(os.getcwd())
open(R + ".head", "w").write(subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip())
if os.environ.get("DA_STUB_LINK"):  # is this path a symlink in the pass's cwd
    open(R + ".link", "w").write(str(os.path.islink(os.environ["DA_STUB_LINK"])))
if os.environ.get("DA_STUB_WATCH"):  # read a file, wait for the test's go, read it again
    first = open(os.environ["DA_STUB_WATCH"]).read()
    open(R + ".started", "w").write("")
    for _ in range(400):
        if os.path.exists(R + ".go"):
            break
        time.sleep(0.05)
    open(R + ".reads", "w").write(json.dumps([first, open(os.environ["DA_STUB_WATCH"]).read()]))
open(os.environ["DA_STUB_REPORT"] + ".otel", "w").write(os.environ.get("OTEL_RESOURCE_ATTRIBUTES", ""))
rid = re.search(r"review_id=(\\S+)", prompt).group(1)
rep = json.loads(open(os.environ["DA_STUB_REPORT"]).read())
rep["review_id"] = rid
print(json.dumps({"type": "result", "subtype": "success", "is_error": False,
                  "result": "Done.\\n```json\\n" + json.dumps(rep) + "\\n```", "session_id": "stub"}))
PY
"""
FINDING = {"id": "F01", "title": "Two registries for one concept", "category": "duplication", "severity": "medium",
           "confidence": "high", "what": "Arms are listed twice.", "evidence": ["app/a.py:1 — ARMS", "app/b.py:1 — ARMS"],
           "fix": "merge", "proposal": "Keep app/a.py's list.", "touches": ["code"]}


def git(root: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                   capture_output=True)


class Harness(unittest.TestCase):
    """A committed product with the architect skill, a team-lead runtime queue and a stub claude."""

    ARCHITECT: dict = {"shape_from_task": "0001"}
    TASKS = 8

    def setUp(self):
        self.p = Product({"architect": self.ARCHITECT})
        self.p.write(".claude/skills/architect/SKILL.md", "---\nname: architect\n---\n# Architect\n")
        self.p.write("docs/delivery/REVIEW-TRIAGE.md", "# triage\n")
        for i in range(1, self.TASKS + 1):
            self.p.task(f"{i:04d}-t{i}")
        self.p.index()
        git(self.p.root, "init", "-q")
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", "init")
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text(binding(product_root=self.p.root))
        stub = self.q / "claude-stub"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.report = self.q / "stub-report.json"
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "PROJECT_YAML": str(self.q / "project.yaml"),
                                                "DA_CLAUDE_BIN": str(stub), "DA_STUB_REPORT": str(self.report),
                                                "ACTOR": "task-runner"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli.main(["--root", str(self.p.root), *args])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
                err.write(str(e.code))
        return code, out.getvalue(), err.getvalue()

    def dpj(self, *args):
        code, out, err = self.ccp(*args)
        return code, json.loads(out), err

    def merge(self, n: int, kind: str | None = None):
        """Mark task n done, as a reconcile after its merge would, and commit."""
        tid = f"{n:04d}-t{n}"
        f = self.p.task(tid, "done")
        if kind:
            f.write_text(f.read_text().replace("status: done", f"status: done\nkind: {kind}"))
        self.p.index()
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", f"Reconcile {tid}")

    def stub_report(self, findings, **extra):
        self.report.write_text(json.dumps({"schema_version": 1, "project_id": "demo", "head": "x",
                                           "summary": "A look.", "findings": findings, **extra}))

    def state(self):
        return json.loads((self.q / "architect.json").read_text())
