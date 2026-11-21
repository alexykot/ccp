"""The seat toolkit (SPEC §10, §11.1, §13, §23.2, §31.4): claim, prompt, runs and their binding, report, verify
noting its run, close, wait, the proposal ledger and the queue's script check."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, prhost, prompt as prompt_mod
from ccp.queue import QueueError
from tests import helpers
from tests.helpers import TASK, binding

PLANE = Path(__file__).resolve().parents[1]
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

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
        git(t, "init", "-q", "--template=", "--bare", "-b", "main", str(origin))
        main = t / "product"
        git(t, "clone", "-q", "--template=", str(origin), str(main))
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
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(t / "queue"), "ACTOR": "task-runner"})
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
        self.assertEqual((rec["state"], rec["merge_commit"]), ("OPEN", ""))

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

    # ------------------------------------------------------------------ waits, scope, proposals


class Toolkit(ToolkitFixture, unittest.TestCase):
    def test_config_accepts_the_blocks_and_refuses_wrong_types(self):
        cfg = config.load(self.main)
        self.assertEqual(cfg.worktrees["links"], [".venv"])
        for bad in ({"adapter": {"worktree_dir": 3}}, {"reconcile": {"hooks": "make"}},
                    {"reconcile": {"log": {"path": "x"}}}, {"telemetry": {"allowance_cmd": 3}},
                    {"reconcile": {"log": {"path": "x", "entry": "y", "before": "("}}}):
            self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **bad}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)

    def test_render_sections_and_unknown_names(self):
        self.assertEqual(prompt_mod.render("a{{#x}}[{{y}}]{{/x}}{{^x}}none{{/x}}", {"x": "1", "y": "Y"}), "a[Y]")
        self.assertEqual(prompt_mod.render("{{#x}}[{{#z}}in{{/z}}]{{/x}}{{^x}}none{{/x}}", {"x": "", "z": 1}), "none")
        with self.assertRaises(QueueError):
            prompt_mod.render("{{nope}}", {})

    def test_every_template_renders_with_the_names_ccp_sets(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.report("0002-second/implement", f"""\
            Outcome: done
            PR: #7
            Head: {'a' * 40}
            ## Friction
            none
            """)
        lines = {"review": "Severity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0\n## Spec beyond intent\nnone", "fix": f"PR: #7\nHead: {'a' * 40}",
                 "verify": f"Verdict: reject\nHead: {'a' * 40}"}
        for phase in ("review", "fix", "verify"):
            # §15.2: a verify straight after a fix is refused without the lead's override
            extra = ("--allow-unreviewed-fix", "--reason", "render test") if phase == "verify" else ()
            code, body, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", "a" * 40, *extra)
            self.assertEqual(code, 0, f"{phase}: {out}{err}")
            text = Path(body["prompt_path"]).read_text()
            self.assertNotIn("{{", text)
            self.assertIn(f"report {body['run_id']} ", text)
            code, _, out, err = self.report(body["run_id"], f"Outcome: done\n{lines[phase]}\n## Friction\nnone\n")
            self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        fix = Path(self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", "a" * 40)[1]["prompt_path"]).read_text()
        self.assertIn("0002-second/review: ", fix)
        self.assertIn("0002-second/verify: ", fix)

    def test_claim_leases_records_and_makes_the_worktree(self):
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        wt = Path(body["worktree"]["path"])
        self.assertEqual(wt, self.main / config.WORKTREES_DIR / "impl-0002")
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD"), "task/0002-second")
        self.assertTrue((wt / ".venv").is_symlink())
        self.assertNotIn(".venv", git(wt, "status", "--porcelain"))  # the link is excluded, so `add -A` cannot take it
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual((st["status"], st["lease_holder"]), ("leased", "runner"))
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["task_id"], w["status"], w["in_flight"]), ("0002-second", "running", ["0002-second"]))
        self.assertIn(("lease", "set"), self.ops())
        self.assertIn(("phase", "transition"), self.ops())
        code, body, out, err = self.ccp("tasks", "claim", "0002")  # a resumed claim keeps the lease
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["resumed"])
        code, _, _, err = self.ccp("tasks", "claim", "0001")
        self.assertEqual(code, 3)
        self.assertIn("done", err)

    def test_a_leftover_hosting_lock_and_grok_block_are_ignored(self):
        # Grok hosting is gone; an old queue may still carry its lock and binding keys.
        (self.q / "hosting.lock").write_text(json.dumps({"live": "grok"}))
        (self.q / "STATE_REF").write_text("plane\n")
        (self.q / "project.yaml").write_text(binding(hosting="grok", integration_branch="main", product_root=self.main,
                                                          grok={"state_ref": "plane"}))
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.q / "observability/events.jsonl").is_file())
        self.assertFalse((self.q / "observability/events.grok.jsonl").exists())

    def test_plane_check_lists_a_script_the_binding_still_names_as_the_planes_do(self):
        # SPEC §29.3: the binding's `auth_check` is removed, so its script is no queue script the plane keeps.
        (self.q / "project.yaml").write_text(binding(integration_branch="main", product_root=self.main,
                                                          auth_check={"script": "scripts/auth-check.sh"}))
        (self.q / "scripts").mkdir()
        (self.q / "scripts/auth-check.sh").write_text("#!/bin/sh\n")
        (self.q / "scripts/with-scratch-db.sh.orig-0153").write_text("old\n")
        code, body, _, _ = self.ccp("plane", "check")
        self.assertEqual(body["scripts"], ["unknown: scripts/auth-check.sh",
                                           "unknown: scripts/with-scratch-db.sh.orig-0153"])

    def test_claim_warns_of_scripts_that_are_not_the_plane(self):
        (self.q / "scripts").mkdir()
        (self.q / "scripts/runner-close.sh").write_text("#!/bin/sh\n")
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIn("unknown: scripts/runner-close.sh", err)
        code, body, _, _ = self.ccp("plane", "check")
        self.assertEqual(code, 1)
        self.assertEqual(body["scripts"], ["unknown: scripts/runner-close.sh"])

    def test_a_retired_plane_script_is_reported_for_deletion(self):
        (self.q / "scripts").mkdir()
        (self.q / "scripts/spec-maintainer-lock.sh").write_text("#!/bin/sh\n")
        code, body, _, _ = self.ccp("plane", "check")
        self.assertEqual(len(body["scripts"]), 1)
        self.assertTrue(body["scripts"][0].startswith("retired: scripts/spec-maintainer-lock.sh"))
        self.assertIn("delete it", body["scripts"][0])

    def test_prompt_renders_audits_and_opens_a_run(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note", "line numbers are stale")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], "0002-second/implement")
        self.assertEqual(body["agent_call"]["subagent_type"], "delivery-implementer")
        self.assertEqual(body["agent_call"]["description"], "0002 implement")
        self.assertEqual((body["expected_model"], body["expected_effort"]), ("claude-opus-5-5", "high"))
        text = Path(body["prompt_path"]).read_text()
        for want in ("Use the scratch database helper", "line numbers are stale", str(self.main / config.WORKTREES_DIR / "impl-0002"),
                     f"report 0002-second/implement {self.q}/progress/0002-second/implement-report.md", "abc1234"):
            self.assertIn(want, text)
        self.assertNotIn("kind: refactor", text)
        self.assertTrue((self.q / body["prompt_ref"]).is_file())
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual((run["round"], run["agent_type"], run["agent_id"]), (1, "delivery-implementer", None))
        self.assertEqual(json.loads((self.q / "work.json").read_text())["phase"], "implementing")
        self.assertIn(("run", "opened"), self.ops())

    def test_a_second_pending_run_of_a_type_is_refused_until_superseded(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 3)
        self.assertIn("still pending", err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], "0002-second/implement-2")
        first = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertTrue(first["abandoned_at"])
        self.assertIn(("run", "abandoned"), self.ops())

    def test_hooks_bind_the_oldest_pending_run_and_stop_it(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        start = json.dumps({"agent_id": "a1", "agent_type": "delivery-implementer", "session_id": "s1"})
        code, body, _, _ = self.ccp("agent", "start", stdin=start)
        self.assertEqual((code, body["bound"]), (0, "0002-second/implement"))
        code, body, _, _ = self.ccp("agent", "start", stdin=start)  # a resumed agent is not bound twice
        self.assertIsNone(body["bound"])
        code, body, _, _ = self.ccp("agent", "start", stdin=json.dumps({"agent_id": "x", "agent_type": "Explore"}))
        self.assertIn("not a plane worker", body["skipped"])
        code, body, _, _ = self.ccp("agent", "stop", stdin=json.dumps({"agent_id": "a1", "agent_type": "delivery-implementer"}))
        self.assertEqual(body["stopped"], "0002-second/implement")
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual((run["agent_id"], run["session_id"]), ("a1", "s1"))
        self.assertTrue(run["started_at"] and run["stopped_at"])
        code, body, _, _ = self.ccp("agent", "start", stdin="not json")
        self.assertEqual(code, 0)
        self.assertFalse(body["ok"])

    def test_report_is_checked_then_recorded(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        code, _, _, err = self.report("0002-second/implement", "Outcome: done\nPR: #7\n")
        self.assertEqual(code, 1)
        for missing in ("Head:", "Friction"):
            self.assertIn(missing, err)
        self.assertFalse((self.q / "progress/0002-second/implement-report.md").exists())
        code, body, out, err = self.report("0002-second/implement", f"""\
            Built it.
            Outcome: done
            PR: #7
            Head: {'a' * 40}
            Suite: 412 tests, 88.5 s

            ## Friction
            - the same fact sits in three files
            - a test pinned the wording of an error
            """)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["outcome"], body["pr"], body["suite_tests"], body["friction_count"]), ("done", "7", 412, 2))
        self.assertTrue((self.q / "progress/0002-second/implement-report.md").is_file())
        notes = [json.loads(x) for x in (self.q / "health/notes.jsonl").read_text().splitlines()]
        self.assertEqual([n["by"] for n in notes], ["implementer", "implementer"])
        metrics = {json.loads(x)["metric"] for x in (self.q / "health/metrics.jsonl").read_text().splitlines()}
        self.assertEqual(metrics, {"suite_tests", "suite_seconds"})
        self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)  # the next run: the report was acted on
        code, _, _, err = self.report("0002-second/implement", "Outcome: done\n## Friction\nnone\n")
        self.assertEqual(code, 1)
        self.assertIn("already reported", err)
        self.assertIn("0002-second/review", err)

    def test_review_report_records_severity(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        code, body, out, err = self.report("0002-second/review", """\
            Outcome: done
            Severity: BLOCKER=0 MAJOR=1 MINOR=2 NIT=0
            ## Spec beyond intent
            none
            ## Friction
            none
            """)
        self.assertEqual(code, 0, out + err)
        ev = [e for e in self.events() if e["type"] == "review"]
        self.assertEqual(ev[0]["payload"]["verdict"], "changes")
        self.assertEqual(ev[0]["payload"]["severity"]["MAJOR"], 1)

    def test_fix_needs_a_report_to_fix_from(self):
        self.ccp("tasks", "claim", "0002")
        code, _, _, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 2)
        self.assertIn("no review or verify report", err)

    def test_verify_record_notes_the_verdict_on_its_run(self):
        head = self._to_approved_pr()
        run = json.loads((self.q / "runs/0002-second/verify.json").read_text())
        self.assertEqual((run["verdict"], run["head"]), ("approve", head))
        self.assertIn(("verify", "recorded"), self.ops())

    def test_close_merges_reconciles_pushes_and_clears_the_queue(self):
        self.write("docs/delivery/plane.json", json.dumps({**self.PLANE_JSON, "adapter": {"post_close": ["touch closed-{nnnn}"]}}))
        git(self.main, "commit", "-q", "-am", "post_close hook")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        head = self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)
        self.assertTrue(any("adapter.post_close moves to reconcile.hooks" in w for w in body["warnings"]), body)
        git(self.main, "fetch", "-q", "origin")
        task = git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md")
        self.assertIn("status: done", task)
        self.assertIn(f"PR #{self.PR} head `{head[:7]}`", task)
        self.assertNotIn("*Append-only, per check id", task)
        log = git(self.main, "show", "origin/main:docs/LOG.md")
        self.assertLess(log.index(f"`0002` done: it is built. PR #{self.PR}"), log.index("older entry"))
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/INDEX.yaml").split("0002-second")[1])
        self.assertTrue(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile 0002"))
        self.assertFalse((self.main / config.WORKTREES_DIR / "impl-0002").exists())
        self.assertTrue((self.main / "closed-0002").exists())
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual(st["status"], "done")
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["in_flight"], w["runner_tasks_done"], w["task_id"]), ([], 1, None))
        for op in (("durable", "reconcile"), ("lease", "clear")):
            self.assertIn(op, self.ops())

    def test_close_and_gc_leave_the_baseline_worktree_alone(self):
        self._to_approved_pr()
        code, body, out, err = self.ccp("wt", "create", "--kind", "ver", "--baseline")
        self.assertEqual(code, 0, out + err)
        baseline = Path(body["path"])
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.main / config.WORKTREES_DIR / "impl-0002").exists())  # the task's own worktree went
        code, gc, out, err = self.ccp("wt", "gc")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("ver-baseline", gc["removed"] + gc["forgot"])
        self.assertTrue(baseline.is_dir())
        self.assertTrue((self.q / "worktrees" / "ver-baseline.json").is_file())

    def test_close_refuses_without_an_approval_and_merges_nothing(self):
        self._push_task_work()
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 1)
        self.assertIn("nothing merged", err)
        self.assert_pr_not_merged()

    def test_an_approval_recorded_after_a_merge_by_hand_is_not_one(self):
        import time
        head = self._push_task_work()
        code, _, out, err = self.ccp("pr", "merge", self.PR, "--head", head, "--task", "0002-second")
        self.assertEqual(code, 0, out + err)
        time.sleep(1.2)
        self.ccp("prompt", "verify", "0002", "--pr", self.PR, "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "late.json"
        f.write_text(json.dumps(rec))
        self.assertEqual(self.ccp("verify", "record", str(f))[0], 0)
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 1)
        self.assertIn("recorded after it", err)
        self.assertNotIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))

    def test_close_refuses_a_dirty_runner_worktree(self):
        self._to_approved_pr()
        (self.runner / "stray.txt").write_text("x")
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 2)
        self.assertIn(f"{self.runner.resolve()} has changes: the checkout `ccp tasks close` runs from must be clean", err)
        self.assertNotIn("runner worktree", err)  # close may run from any checkout (§10.5)
        self.assert_pr_not_merged()

    def test_close_after_a_failed_reconcile_finishes_without_merging_again(self):
        # the failing hook lands before the task's branch is cut, so its head contains the tip (§16.5 rule 4)
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["exit 3"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a failing hook")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        head = self._to_approved_pr()
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 1)
        self.assertIn(f"PR {self.PR} is merged", err)
        self.assertIn(f"run `ccp tasks close 0002-second --pr {self.PR}` again", err)
        merged = self.pr_record()["merge_commit"]
        self.assertTrue(merged)
        git(self.runner, "fetch", "-q", "origin")  # close left the runner worktree where it was (§10.5)
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        cfg["reconcile"]["hooks"] = []
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "the hook fixed")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])
        self.assertEqual((self.pr_record()["state"], self.pr_record()["merge_commit"]), ("MERGED", merged))  # not merged again
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)  # a third run changes nothing
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["reconciled_now"])
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner_tasks_done"], 1)

    def test_a_draining_or_stopped_runner_takes_no_new_task(self):
        for status in ("draining", "idle"):
            (self.q / "work.json").write_text(json.dumps({"status": status}))
            code, _, _, err = self.ccp("tasks", "claim", "0002")
            self.assertEqual(code, 3, status)
            self.assertIn(status, err)

    def test_a_task_id_that_is_not_its_file_name_is_refused(self):
        self.write("docs/delivery/tasks/0003-x.md", TASK.format(tid="0003-x/../../../evil", title="X", status="pending",
                                                                deps="", ver="*Append-only.*"))
        git(self.main, "add", "-A")
        git(self.main, "commit", "-qm", "evil")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "pull", "-q", "origin", "main")
        code, _, _, err = self.ccp("tasks", "claim", "0003")
        self.assertEqual(code, 2)
        self.assertIn("is not its file name", err)
        self.assertFalse(any(self.q.parent.glob("evil*")))

    def test_prompt_needs_a_claimed_task(self):
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 3)
        self.assertIn("not claimed", err)
        self.assertFalse((self.q / "prompts").exists())

    def test_a_refused_prompt_writes_nothing(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        before = sorted(p.name for p in (self.q / "prompts/0002-second").iterdir())
        code, _, _, _ = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 3)
        self.assertEqual(sorted(p.name for p in (self.q / "prompts/0002-second").iterdir()), before)

    def test_friction_lines_may_wrap_and_use_stars(self):
        from ccp.report import friction
        self.assertEqual(friction("## Friction\n- one fact in\n  three files\n* a pinned test\n"),
                         ["one fact in three files", "a pinned test"])
        self.assertEqual(friction("## Friction\nnone.\n"), [])
        self.assertEqual(friction("## Friction\n- none\n"), [])
        self.assertEqual(friction("## Friction\n* None.\n"), [])
        self.assertIsNone(friction("## Friction\nNone.\n  nothing to add\n"))
        self.assertIsNone(friction("## Friction\n- a real one\n- none\n"))
        self.assertIsNone(friction("## Friction\nsome prose\n"))
        self.assertIsNone(friction("no section"))

    def test_a_verify_report_must_match_its_record(self):
        head = self._to_approved_pr()
        code, _, _, err = self.report("0002-second/verify", f"Outcome: done\nVerdict: reject\nHead: {head}\n## Friction\nnone\n")
        self.assertEqual(code, 1)
        self.assertIn("the recorded verdict is approve", err)
        self.assertFalse((self.q / "progress/0002-second/verify-report.md").exists())
        code, _, out, err = self.report("0002-second/verify", f"Outcome: done\nVerdict: approve\nHead: {head}\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)

    def test_mid_flight_counts_review_and_fix(self):
        from ccp import queue
        self.assertTrue({"reviewing", "fixing"} <= queue.MID_FLIGHT)

    def test_a_template_name_ccp_does_not_set_fails_even_in_an_empty_section(self):
        with self.assertRaises(QueueError):
            prompt_mod.render("{{#x}}{{nope}}{{/x}}", {"x": ""})

    def test_wait_and_resume_go_through_the_single_writer(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "0002-second-1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["waiting_on"], "design_seat")
        code, _, out, err = self.ccp("tasks", "resume", "0002", "gate_decided")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(json.loads((self.q / "tasks/0002-second.json").read_text())["waiting_on"])
        self.assertEqual([op for t, op in self.ops() if t == "waiting_on"], ["set", "clear"])

    def test_next_says_why_it_returns_a_refactor_outside_the_scope(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["architect"] = {"shape_from_task": "0001", "refactor_in_scope": True}
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        self.write("docs/delivery/tasks/0003-tidy.md", TASK.format(tid="0003-tidy", title="Tidy", status="pending", deps="",
                                                                   ver="*Append-only.*").replace('spec_refs: ["S1"]', 'spec_refs: []\nkind: refactor\nrule_refs: ["E1"]'))
        self.write("docs/delivery/tasks/0002-second.md", TASK.format(tid="0002-second", title="Second", status="done", deps='"0001-first"',
                                                                     ver="- 2026-09-30 — `cmd-01` pass — ran it"))
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            (self.q / "architect.json").write_text(json.dumps({"reviews": {}, "last": {"done_count": 99, "at": "2099-01-01T00:00:00Z"}}))
            code, _, out, err = self.ccp("tasks", "next", "--scope", "0002", root=self.main)
        self.assertIn("why:", out + err)
        self.assertIn("refactor_in_scope", out + err)

    def test_next_under_deps_says_which_scope_task_needs_the_refactor(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["architect"] = {"shape_from_task": "0001"}  # §20: "deps" is the default
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        refactor = lambda tid: TASK.format(tid=tid, title="Tidy", status="pending", deps="", ver="*Append-only.*").replace(  # noqa: E731
            'spec_refs: ["S1"]', 'spec_refs: []\nkind: refactor\nrule_refs: ["E1"]')
        self.write("docs/delivery/tasks/0003-tidy.md", refactor("0003-tidy"))
        self.write("docs/delivery/tasks/0004-unrelated.md", refactor("0004-unrelated"))
        self.write("docs/delivery/tasks/0005-uses.md", TASK.format(tid="0005-uses", title="Uses", status="pending",
                                                                   deps='"0003-tidy"', ver="*Append-only.*"))
        self.write("docs/delivery/tasks/0002-second.md", TASK.format(tid="0002-second", title="Second", status="done", deps='"0001-first"',
                                                                     ver="- 2026-09-30 — `cmd-01` pass — ran it"))
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            (self.q / "architect.json").write_text(json.dumps({"reviews": {}, "last": {"done_count": 99, "at": "2099-01-01T00:00:00Z"}}))
            code, _, out, err = self.ccp("tasks", "next", "--scope", "0005", root=self.main)
            self.assertEqual(code, 0, out + err)
            self.assertTrue(out.startswith("0003-tidy"), out)
            self.assertIn('why:       outside the given scope: a refactor that in-scope task 0005-uses depends on', out)
            self.assertIn('refactor_in_scope: "deps"', out)
            self.write("docs/delivery/tasks/0003-tidy.md", refactor("0003-tidy").replace("status: pending", "status: done"))
            code, _, out, err = self.ccp("tasks", "next", "--scope", "0005", root=self.main)
        self.assertTrue(out.startswith("0005-uses"), out + err)  # 0004-unrelated waits for the next review point

    def test_next_takes_the_review_points_refactors_first_and_says_why(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {"shape_from_task": "0001"}}))
        self.write("docs/delivery/tasks/0003-tidy.md", TASK.format(tid="0003-tidy", title="Tidy", status="pending", deps="",
                                                                   ver="*Append-only.*").replace('spec_refs: ["S1"]', 'spec_refs: []\nkind: refactor\nrule_refs: ["E1"]'))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0003-tidy", "0002-second"],
                                                      "review_point": "R8", "review_point_refactors": ["0003-tidy"]}))
        (self.q / "architect.json").write_text(json.dumps({"reviews": {}, "last": {"done_count": 99, "at": "2099-01-01T00:00:00Z"}}))
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0003-tidy"), out)
        self.assertIn("why:       a refactor waiting from an earlier cycle, taken first at review point R8", out)

    def test_next_takes_the_running_runners_scope(self):
        self.write("docs/delivery/tasks/0003-third.md", TASK.format(tid="0003-third", title="Third", status="pending",
                                                                    deps="", ver="*Append-only.*"))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0003-third"]}))
        code, _, out, err = self.ccp("tasks", "next", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0003-third"))
        self.assertIn("scope from work.json", err)
        code, _, out, _ = self.ccp("tasks", "next", "--scope", "0002", root=self.main)
        self.assertTrue(out.startswith("0002-second"))

    def test_proposals_fold_and_triage_once(self):
        code, _, _, err = self.ccp("plane", "propose", "--need", "a command that frees a task's resources")
        self.assertEqual(code, 2)                      # §31.4: no --generic, no proposal
        self.assertIn("--generic", err)
        self.assertIn("product work", err)
        code, body, out, err = self.ccp("plane", "propose", "--need", "a command that frees a task's resources",
                                        "--generic", "every product with per-task resources needs them freed at close",
                                        "--task", "0002-second", "--workaround", "free them by hand")
        self.assertEqual(code, 0, out + err)
        pid = body["id"]
        self.ccp("plane", "propose", "--again", pid)
        code, body, _, _ = self.ccp("plane", "list", "--open")
        self.assertEqual((body["proposals"][0]["id"], body["proposals"][0]["again"]), (pid, 1))
        code, _, _, err = self.ccp("plane", "triage", pid, "--accept")
        self.assertEqual(code, 2)
        self.assertIn("--reason", err)
        env = {k: v for k, v in os.environ.items() if k != "ACTOR"}  # the plane session sets no ACTOR
        with mock.patch.dict(os.environ, env, clear=True):
            code, body, _, _ = self.ccp("plane", "triage", pid, "--accept", "--reason", "plane task: post_close hook")
        self.assertEqual(body["status"], "accepted")
        # §31.5: the plane session's call, recorded as its own actor (the row and the event)
        self.assertEqual(json.loads((self.q / "plane/proposals.jsonl").read_text().splitlines()[-1])["by"], "plane-session")
        self.assertEqual([e["actor"] for e in self.events() if e["type"] == "plane" and e["op"] == "triaged"],
                         ["plane-session"])
        code, _, _, err = self.ccp("plane", "triage", pid, "--decline", "--reason", "x")
        self.assertEqual(code, 3)
        self.assertEqual([op for t, op in self.ops() if t == "plane"], ["proposed", "again", "triaged"])
        row = json.loads((self.q / "plane/proposals.jsonl").read_text().splitlines()[0])
        self.assertIn("per-task resources", row["generic"])
        code, _, _, err = self.ccp("plane", "propose", "--need", "token sk-ant-abcdefghijklmnopqrstuvwxyz0123456789",
                                   "--generic", "x")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

class Allowance(ToolkitFixture, unittest.TestCase):
    def plane_json(self, cmd, stop=None):
        helpers.machine_file(self, allowance_cmd=cmd, allowance_stop_weekly=stop)

    def test_claim_samples_and_stops_past_the_weekly_gate(self):
        sample = json.dumps({"five_hour": {"utilization": 12.0}, "seven_day": {"utilization": 85.0,
                                                                               "resets_at": "2099-10-27T04:00:00Z"}})
        self.plane_json(f"echo '{sample}'", stop=80)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 5)
        self.assertIn("allowance checkpoint", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        rows = [json.loads(x) for x in (self.q / "board/allowance.jsonl").read_text().splitlines()]
        self.assertEqual(rows[-1]["seven_day"], 85.0)
        self.assertIn(("allowance", "sample"), self.ops())

    def test_a_resumed_claim_is_not_refused(self):
        self.ccp("tasks", "claim", "0002")
        sample = json.dumps({"seven_day": {"utilization": "95"}})
        self.plane_json(f"echo '{sample}'", stop=80)
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["resumed"])
        self.assertEqual(json.loads((self.q / "board/allowance.jsonl").read_text().splitlines()[-1])["seven_day"], 95.0)

    def test_an_unknown_sample_never_stops_a_claim(self):
        self.plane_json("exit 1", stop=80)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIn("no good allowance reading in force", err)
        row = json.loads((self.q / "board/allowance.jsonl").read_text().splitlines()[-1])
        self.assertIsNone(row["seven_day"])
        self.assertTrue(row["failed"])
        self.assertIs(row["shared"], False)  # the suite reads unshared (tests/__init__.py)


class Checkpoint(ToolkitFixture, unittest.TestCase):
    plane_json = Allowance.plane_json

    def test_the_operator_decides_to_continue_until_the_next_checkpoint(self):
        sample = lambda pct: json.dumps({"seven_day": {"utilization": pct, "resets_at": "2099-10-27T04:00:00Z"}})
        self.plane_json(f"echo '{sample(85)}'", stop=80)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 5)
        self.assertIn("allowance checkpoint", err)
        self.assertIn("ccp allowance continue", err)
        code, _, _, err = self.ccp("allowance", "continue", "--to", "90")
        self.assertEqual(code, 2)
        self.assertIn("--reason", err)
        code, _, _, err = self.ccp("allowance", "continue", "--to", "75", "--reason", "x")
        self.assertEqual(code, 2)  # does not raise the checkpoint
        with mock.patch.dict(os.environ, {"ACTOR": "design-seat"}):
            code, body, out, err = self.ccp("allowance", "continue", "--to", "90", "--reason", "go on: 2 tasks left, resets Tuesday")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, _, _ = self.ccp("allowance", "status")
        self.assertEqual((body["checkpoint"], body["project_checkpoint"], len(body["decisions"])), (90.0, 80, 1))
        self.assertIn(("allowance", "decided"), self.ops())

    def test_a_decision_holds_while_resets_at_jitters(self):
        # A decision made below the checkpoint at 72%, then readings
        # whose resets_at differ by under a second, must keep the raised checkpoint in force.
        sample = lambda pct, at: "echo '" + json.dumps({"seven_day": {"utilization": pct, "resets_at": at}}) + "'"
        self.plane_json(sample(72, "2099-10-27T03:59:59.52Z"), stop=80)
        self.ccp("allowance", "status", "--sample")
        code, _, out, err = self.ccp("allowance", "continue", "--to", "95", "--reason", "the product may go on to 95%")
        self.assertEqual(code, 0, out + err)
        self.plane_json(sample(85, "2099-10-27T04:00:00.24Z"), stop=80)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, _, _ = self.ccp("allowance", "status")
        self.assertEqual((body["checkpoint"], len(body["decisions"])), (95.0, 1))

    def test_a_decision_holds_for_its_weekly_window_only(self):
        self.plane_json("echo '" + json.dumps({"seven_day": {"utilization": 85, "resets_at": "2099-10-27T04:00:00Z"}}) + "'", stop=80)
        self.ccp("tasks", "claim", "0002")
        self.ccp("allowance", "continue", "--to", "95", "--reason", "go on")
        self.plane_json("echo '" + json.dumps({"seven_day": {"utilization": 85, "resets_at": "2099-11-03T04:00:00Z"}}) + "'", stop=80)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 5)
