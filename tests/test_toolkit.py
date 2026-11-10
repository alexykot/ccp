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

from ccp import cli, config, prompt as prompt_mod
from ccp.queue import QueueError
from tests.helpers import TASK

PLANE = Path(__file__).resolve().parents[1]
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

FAKE_GH = r'''#!/usr/bin/env python3
"""A stand-in for gh: `pr view` reads the PR from FAKE_GH_DIR, `pr merge` squash-merges its branch."""
import json, os, subprocess, sys, tempfile
d = os.environ["FAKE_GH_DIR"]
pr = json.load(open(os.path.join(d, "pr.json")))
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    print(json.dumps({"number": int(args[2]), "state": pr["state"], "headRefOid": pr["head"], "mergedAt": pr.get("merged_at"),
                      "mergeCommit": {"oid": pr["merge"]} if pr.get("merge") else None}))
    sys.exit(0)
if args[:2] == ["pr", "merge"]:
    open(os.path.join(d, "merge-called"), "w").write(" ".join(args))
    head = args[args.index("--match-head-commit") + 1]
    if head != pr["head"]:
        print("head moved", file=sys.stderr); sys.exit(1)
    w = tempfile.mkdtemp()
    run = lambda *a: subprocess.run(["git", "-C", w, *a], check=True, capture_output=True)
    subprocess.run(["git", "clone", "-q", pr["origin"], w], check=True, capture_output=True)
    run("checkout", "-q", pr["base"])
    run("merge", "--squash", "origin/" + pr["branch"])
    run("commit", "-q", "-m", f"Task {pr['branch'][5:9]}: done (#{args[2]})")
    run("push", "-q", "origin", pr["base"])
    pr["state"] = "MERGED"
    import datetime
    pr["merged_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pr["merge"] = subprocess.run(["git", "-C", w, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump(pr, open(os.path.join(d, "pr.json"), "w"))
    sys.exit(0)
sys.exit(2)
'''


def git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(a)}: {r.stderr}")
    return r.stdout.strip()


class ToolkitFixture:
    """A git product (bare origin, main checkout, runner worktree) and a Claude team queue."""

    PLANE_JSON = {
        "project_id": "demo",
        "prompts": {"fragment": "docs/delivery/WORKERS.md"},
        "reconcile": {"log": {"path": "docs/LOG.md", "entry": "**{date} (runner):** `{nnnn}` done: {summary} PR #{pr}, squash `{merge7}`.",
                              "before": r"^\*\*\d{4}-"}},
        "adapter": {"worktree_dir": ".rt", "worktree_links": [".venv"], "post_close": ["touch closed-{nnnn}"]},
    }

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name).resolve()
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(t / "queue"), "ACTOR": "task-runner",
                                                "CCP_GH_BIN": str(t / "gh"), "FAKE_GH_DIR": str(t / "ghstate")})
        self.env.start()
        self.origin = t / "origin.git"
        git(t, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.main = t / "product"
        git(t, "clone", "-q", str(self.origin), str(self.main))
        git(self.main, "checkout", "-q", "-b", "main")
        self.write("docs/delivery/plane.json", json.dumps(self.PLANE_JSON))
        self.write("docs/delivery/WORKERS.md", "Use the scratch database helper for every test run.")
        self.write("docs/LOG.md", "# Log\n\n**2026-10-20 (runner):** older entry.\n")
        self.write("docs/delivery/tasks/0001-first.md", TASK.format(tid="0001-first", title="First", status="done", deps="",
                                                                    ver="- 2026-09-30 — `cmd-01` pass — ran it"))
        self.write("docs/delivery/tasks/0002-second.md", TASK.format(tid="0002-second", title="Second", status="pending",
                                                                     deps='"0001-first"', ver="*Append-only, per check id: pass or fail, with evidence.*"))
        self.write(".venv/marker", "")
        self.write(".gitignore", ".venv/\n.rt/\nclosed-*\n")
        (self.main / ".claude/agents").mkdir(parents=True)
        for a in ("implementer", "reviewer", "verifier"):
            shutil.copy(PLANE / f"plugin/agents/delivery-{a}.md", self.main / f".claude/agents/delivery-{a}.md")
        from ccp import tasklog
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "init")
        git(self.main, "push", "-q", "-u", "origin", "main")
        self.runner = self.main / ".rt" / "runner"
        git(self.main, "worktree", "add", "-q", "--detach", str(self.runner), "origin/main")
        self.q = t / "queue"
        self.q.mkdir()
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: main\n")
        (t / "ghstate").mkdir()
        (t / "gh").write_text(FAKE_GH)
        (t / "gh").chmod(0o755)
        self.ghstate = t / "ghstate"

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        p = self.main / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

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

    def report(self, run_id: str, text: str):
        f = Path(self._tmp.name) / f"report-{run_id.replace('/', '_')}.md"
        f.write_text(textwrap.dedent(text))
        return self.ccp("report", run_id, str(f))

    # ------------------------------------------------------------------ config

    # ------------------------------------------------------------------ render

    # ------------------------------------------------------------------ claim

    # ------------------------------------------------------------------ prompt and runs

    # ------------------------------------------------------------------ verify and close

    def _to_approved_pr(self) -> str:
        """Claim 0002, commit work on its branch, push it, verify it: the PR head."""
        self.ccp("tasks", "claim", "0002")
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        git(wt, "add", "feature.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(wt, "rev-parse", "HEAD")
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "OPEN", "head": head, "origin": str(self.origin),
                                                           "base": "main", "branch": "task/0002-second"}))
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it"}]
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
        self.assertEqual(cfg.adapter["worktree_links"], [".venv"])
        self.assertEqual(cfg.telemetry["otel_port"], 4318)
        for bad in ({"adapter": {"worktree_dir": 3}}, {"reconcile": {"hooks": "make"}},
                    {"reconcile": {"log": {"path": "x"}}}, {"prompts": {"other": 1}}, {"telemetry": {"otel_port": 0}},
                    {"reconcile": {"log": {"path": "x", "entry": "y", "before": "("}}}):
            self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **bad}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)

    def test_plane_config_schema_lists_every_block(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        for block, defaults in (("prompts", config.PROMPTS_DEFAULTS), ("reconcile", config.RECONCILE_DEFAULTS),
                                ("adapter", config.ADAPTER_DEFAULTS), ("telemetry", config.TELEMETRY_DEFAULTS),
                                ("board", config.BOARD_DEFAULTS), ("docs", config.DOCS_DEFAULTS)):
            self.assertEqual(set(schema["properties"][block]["properties"]), set(defaults), block)

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
        lines = {"review": "Severity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0", "fix": f"PR: #7\nHead: {'a' * 40}",
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
        self.assertEqual(wt, self.main / ".rt" / "impl-0002")
        self.assertEqual(git(wt, "rev-parse", "--abbrev-ref", "HEAD"), "task/0002-second")
        self.assertTrue((wt / ".venv").is_symlink())
        self.assertNotIn(".venv", git(wt, "status", "--porcelain"))  # the link is excluded, so `add -A` cannot take it
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual((st["status"], st["lease_holder"]), ("leased", "runner"))
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["task_id"], w["status"], w["in_flight"]), ("0002-second", "running", ["0002-second"]))
        self.assertIn(("lease", "set"), self.ops())
        self.assertIn(("phase", "transition"), self.ops())
        self.assertTrue((self.q / "queue/leased/0002-second").exists())
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
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: grok\nintegration_branch: main\n"
                                             "grok:\n  state_ref: plane\n")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.q / "observability/events.jsonl").is_file())
        self.assertFalse((self.q / "observability/events.grok.jsonl").exists())

    def test_plane_check_accepts_the_bindings_auth_check(self):
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: main\n"
                                             "auth_check:\n  script: scripts/auth-check.sh\n")
        (self.q / "scripts").mkdir()
        (self.q / "scripts/auth-check.sh").write_text("#!/bin/sh\n")
        (self.q / "scripts/with-scratch-db.sh.orig-0153").write_text("old\n")
        code, body, _, _ = self.ccp("plane", "check")
        self.assertEqual(body["scripts"], ["unknown: scripts/with-scratch-db.sh.orig-0153"])

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
        for want in ("Use the scratch database helper", "line numbers are stale", str(self.main / ".rt" / "impl-0002"),
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
        code, _, _, err = self.report("0002-second/implement", "Outcome: done\n## Friction\nnone\n")
        self.assertEqual(code, 1)
        self.assertIn("already reported", err)

    def test_review_report_records_severity(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        code, body, out, err = self.report("0002-second/review", """\
            Outcome: done
            Severity: BLOCKER=0 MAJOR=1 MINOR=2 NIT=0
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
        head = self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head)
        git(self.main, "fetch", "-q", "origin")
        task = git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md")
        self.assertIn("status: done", task)
        self.assertIn(f"PR #7 head `{head[:7]}`", task)
        self.assertNotIn("*Append-only, per check id", task)
        log = git(self.main, "show", "origin/main:docs/LOG.md")
        self.assertLess(log.index("`0002` done: it is built. PR #7"), log.index("older entry"))
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/INDEX.yaml").split("0002-second")[1])
        self.assertTrue(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile 0002"))
        self.assertFalse((self.main / ".rt" / "impl-0002").exists())
        self.assertTrue((self.main / "closed-0002").exists())
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertEqual(st["status"], "done")
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["in_flight"], w["runner_tasks_done"], w["task_id"]), ([], 1, None))
        for op in (("durable", "reconcile"), ("lease", "clear")):
            self.assertIn(op, self.ops())

    def test_close_refuses_without_an_approval_and_merges_nothing(self):
        self.ccp("tasks", "claim", "0002")
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "OPEN", "head": "b" * 40, "origin": str(self.origin),
                                                           "base": "main", "branch": "task/0002-second"}))
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("nothing merged", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_an_approval_recorded_after_a_merge_by_hand_is_not_one(self):
        import time
        self.ccp("tasks", "claim", "0002")
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        git(wt, "add", "feature.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(wt, "rev-parse", "HEAD")
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "OPEN", "head": head, "origin": str(self.origin),
                                                           "base": "main", "branch": "task/0002-second"}))
        subprocess.run([os.environ["CCP_GH_BIN"], "pr", "merge", "7", "--squash", "--match-head-commit", head], check=True)
        time.sleep(1.2)
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it"}]
        f = Path(self._tmp.name) / "late.json"
        f.write_text(json.dumps(rec))
        self.assertEqual(self.ccp("verify", "record", str(f))[0], 0)
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("recorded after it", err)
        self.assertNotIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))

    def test_close_refuses_a_dirty_runner_worktree(self):
        self._to_approved_pr()
        (self.runner / "stray.txt").write_text("x")
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 2)
        self.assertIn("has changes", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_close_after_a_failed_reconcile_finishes_without_merging_again(self):
        # the failing hook lands before the task's branch is cut, so its head contains the tip (§16.5 rule 4)
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["exit 3"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a failing hook")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        head = self._to_approved_pr()
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("PR 7 is merged", err)
        self.assertIn("run `ccp tasks close 0002-second --pr 7` again", err)
        git(self.runner, "reset", "-q", "--hard")
        cfg["reconcile"]["hooks"] = []
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "the hook fixed")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        (self.ghstate / "merge-called").unlink()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])
        self.assertFalse((self.ghstate / "merge-called").exists())
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")  # a third run changes nothing
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
        cfg["architect"] = {"refactor_in_scope": True}
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
        cfg["architect"] = {}  # §20: "deps" is the default
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
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {}}))
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
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {"allowance_cmd": cmd, **({"allowance_stop_weekly": stop} if stop else {})}
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))

    def test_claim_samples_and_stops_past_the_weekly_gate(self):
        sample = json.dumps({"five_hour": {"utilization": 12.0}, "seven_day": {"utilization": 85.0,
                                                                               "resets_at": "2026-10-27T04:00:00Z"}})
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
        self.assertIn("allowance reading is unknown", err)
        row = json.loads((self.q / "board/allowance.jsonl").read_text().splitlines()[-1])
        self.assertIsNone(row["seven_day"])


class Checkpoint(ToolkitFixture, unittest.TestCase):
    plane_json = Allowance.plane_json

    def test_the_operator_decides_to_continue_until_the_next_checkpoint(self):
        sample = lambda pct: json.dumps({"seven_day": {"utilization": pct, "resets_at": "2026-10-27T04:00:00Z"}})
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
        self.plane_json(sample(72, "2026-10-27T03:59:59.52Z"), stop=80)
        self.ccp("allowance", "status", "--sample")
        code, _, out, err = self.ccp("allowance", "continue", "--to", "95", "--reason", "the product may go on to 95%")
        self.assertEqual(code, 0, out + err)
        self.plane_json(sample(85, "2026-10-27T04:00:00.24Z"), stop=80)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, _, _ = self.ccp("allowance", "status")
        self.assertEqual((body["checkpoint"], len(body["decisions"])), (95.0, 1))

    def test_a_decision_holds_for_its_weekly_window_only(self):
        self.plane_json("echo '" + json.dumps({"seven_day": {"utilization": 85, "resets_at": "2026-10-27T04:00:00Z"}}) + "'", stop=80)
        self.ccp("tasks", "claim", "0002")
        self.ccp("allowance", "continue", "--to", "95", "--reason", "go on")
        self.plane_json("echo '" + json.dumps({"seven_day": {"utilization": 85, "resets_at": "2026-11-03T04:00:00Z"}}) + "'", stop=80)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 5)
