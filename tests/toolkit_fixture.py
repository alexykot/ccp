"""A git product (a bare origin, a main clone and a runner worktree) and a queue on the local PR host. A fixture
module: it holds no tests."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, prhost
from ccp.queue import lib

from tests import helpers
from tests.helpers import binding, GIT_ENV, PLANE_ROOT, TASK


PLANE = PLANE_ROOT


def git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout.strip()


class ToolkitFixture:
    """A git product (bare origin, main checkout, runner worktree) and a Claude team queue."""

    PLANE_JSON = {
        **helpers.BASE_PLANE,
        "prompts": {"fragment": "docs/delivery/WORKERS.md"},
        "reconcile": {"log": {"path": "docs/LOG.md", "entry": "**{date} (runner):** `{nnnn}` done: {summary} PR #{pr}, squash `{merge7}`.",
                              "before": r"^\*\*\d{4}-"}},
        "worktrees": {"links": [".venv"]},
        "pr_host": {"adapter": "local"},
    }
    PR = "1"  # the number the local PR host gives the fixture's first PR (`open_pr`)

    # Each test class builds the three repositories once, in `setUpClass`, into a template under its own temp
    # directory (with its own `PLANE_JSON`), and each test copies that tree. `SHARED_REPO = False` keeps the
    # build per test, for a class that changes the build before `setUp` ends.
    SHARED_REPO = True
    _template: tempfile.TemporaryDirectory | None = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._template = None
        if cls.SHARED_REPO:
            cls._template = tempfile.TemporaryDirectory()
            cls.addClassCleanup(cls._template.cleanup)
            with mock.patch.dict(os.environ, GIT_ENV):
                cls._build_repos(Path(cls._template.name).resolve())

    @classmethod
    def _build_repos(cls, t: Path) -> None:
        """The bare origin, the main clone (holding the runner worktree) and the first commit, under `t`."""
        origin = t / "origin.git"
        git(t, "init", "-q", "--bare", "-b", "main", str(origin))
        main = t / "product"
        git(t, "clone", "-q", str(origin), str(main))
        git(main, "checkout", "-q", "-b", "main")

        def put(rel: str, text: str) -> None:
            p = main / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        put("docs/delivery/plane.json", json.dumps(cls.PLANE_JSON))
        put("docs/delivery/WORKERS.md", "Use the scratch database helper for every test run.")
        put("docs/LOG.md", "# Log\n\n**2026-10-20 (runner):** older entry.\n")
        put("docs/delivery/tasks/0001-first.md", TASK.format(tid="0001-first", title="First", status="done", deps="",
                                                             ver="- 2026-09-30 — `cmd-01` pass — ran it"))
        put("docs/delivery/tasks/0002-second.md", TASK.format(tid="0002-second", title="Second", status="pending",
                                                              deps='"0001-first"', ver="*Append-only, per check id: pass or fail, with evidence.*"))
        put(".venv/marker", "")
        put(".gitignore", f".venv/\n{config.WORKTREES_DIR}/\nclosed-*\n")
        (main / ".claude/agents").mkdir(parents=True)
        for a in ("implementer", "reviewer", "verifier"):
            shutil.copy(PLANE / f"plugin/agents/delivery-{a}.md", main / f".claude/agents/delivery-{a}.md")
        from ccp import tasklog
        tasklog.write_index(config.load(main))
        git(main, "add", "-A")
        git(main, "commit", "-q", "-m", "init")
        git(main, "push", "-q", "-u", "origin", "main")
        git(main, "worktree", "add", "-q", "--detach", str(main / config.WORKTREES_DIR / "runner"), "origin/main")
        for repo in (origin, main):  # packed, so each test copies a dozen fewer files
            git(repo, "gc", "-q")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name).resolve()
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(t / "queue"), "ACTOR": lib.RUNNER})
        self.env.start()
        self.origin = t / "origin.git"
        self.main = t / "product"
        self.runner = self.main / config.WORKTREES_DIR / "runner"
        if self.SHARED_REPO:
            template = type(self)._template
            self.assertIsNotNone(template, "ToolkitFixture comes before TestCase in the bases, so its setUpClass runs")
            shutil.copytree(template.name, t, symlinks=True, dirs_exist_ok=True, copy_function=shutil.copy)  # no times or xattrs: faster
            git(self.main, "remote", "set-url", "origin", str(self.origin))
            git(self.main, "worktree", "repair", str(self.runner))
        else:
            self._build_repos(t)
        self.q = t / "queue"
        self.q.mkdir()
        (self.q / "project.yaml").write_text(binding(integration_branch="main", product_root=self.main))

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        p = self.main / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def open_pr(self, branch: str = "task/0002-second", body: str = "Task: 0002-second\n") -> str:
        """The pushed `branch`'s PR, opened with the local PR host's `open` (ADR-0040 D3): its number, `PR`."""
        number = str(prhost.open(config.load(self.runner), branch, "main", "Task 0002: Second", body))
        self.assertEqual(number, self.PR)
        return number

    def assert_pr_not_merged(self) -> None:
        """The local PR host's record shows no merge: still open, no squash commit recorded."""
        rec = self.pr_record()
        self.assertEqual((rec["state"], rec["merge_commit"]), ("open", ""))

    def pr_record(self, number: str | None = None) -> dict:
        """The local PR host's record of PR `number` (`PR` by default)."""
        return json.loads((self.q / prhost.PRS_DIR / f"{number or self.PR}.json").read_text())

    def ccp(self, *args: str, stdin: str | None = None, root: Path | None = None):
        out, err = io.StringIO(), io.StringIO()
        patch = mock.patch("sys.stdin", io.StringIO(stdin)) if stdin is not None else mock.patch.dict(os.environ, {})
        with redirect_stdout(out), redirect_stderr(err), patch:
            code = cli.main(["--root", str(root or self.runner), *args])
        body = out.getvalue()
        try:
            parsed = json.loads(body) if body.strip().startswith("{") else None
        except ValueError:
            parsed = None
        return code, parsed, body, err.getvalue()

    def events(self) -> list[dict]:
        p = self.q / "observability" / "events.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []

    def ops(self) -> list[tuple[str, str]]:
        return [(e["type"], e["op"]) for e in self.events()]

    def report(self, run_id: str, text: str, token: bool = True):
        """Submit `text` as the run's report. With `token`, a report with no `Prompt:` line gets the run's
        prompt token (§13.4), before its first `## ` section, so a test about something else need not."""
        from ccp import report as report_mod, runs  # noqa: PLC0415
        body = textwrap.dedent(text)
        rec = runs.path(self.q, run_id)
        tok = json.loads(rec.read_text()).get("prompt_token") if token and rec.is_file() else None
        if tok and not report_mod.PROMPT_RE.search(body):
            lines = body.splitlines(keepends=True)
            at = next((i for i, ln in enumerate(lines) if ln.startswith("## ")), len(lines))
            if at == len(lines) and lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            body = "".join(lines[:at] + [f"Prompt: {tok}\n"] + lines[at:])
        f = Path(self._tmp.name) / f"report-{run_id.replace('/', '_')}.md"
        f.write_text(body)
        return self.ccp("report", run_id, str(f))

    # ------------------------------------------------------------------ config

    # ------------------------------------------------------------------ render

    # ------------------------------------------------------------------ claim

    # ------------------------------------------------------------------ prompt and runs

    # ------------------------------------------------------------------ verify and close

    def _push_task_work(self) -> str:
        """Claim 0002, commit work on its branch, push it, open its PR: the PR head."""
        self.ccp("tasks", "claim", "0002")
        wt = self.main / config.WORKTREES_DIR / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        git(wt, "add", "feature.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        self.open_pr()
        return git(wt, "rev-parse", "HEAD")

    def _to_approved_pr(self) -> str:
        """Claim 0002, commit work on its branch, push it, open its PR, verify it: the PR head."""
        head = self._push_task_work()
        self.ccp("prompt", "verify", "0002", "--pr", self.PR, "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, body, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], "0002-second/verify")
        return head
