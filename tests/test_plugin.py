"""SPEC §4: the control-plane plugin, the project lookup, the run checkout, INDEX as a product
choice, the plane-path warning and sync's plugin mode."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, runs, tasklog
from tests.helpers import Product

PLANE = Path(__file__).resolve().parents[1]
PLUGIN = PLANE / "plugin"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def frontmatter(p: Path) -> dict:
    return tasklog.frontmatter(p.read_text())


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **GIT_ENV, **kw.pop("env", {})}, **kw)


class ThePlugin(unittest.TestCase):
    def test_manifests_name_the_plugin(self):
        plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        market = json.loads((PLANE / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(plugin["name"], "ccp")
        self.assertEqual(market["plugins"][0], {**market["plugins"][0], "name": "ccp", "source": "./plugin"})

    def test_agents_pin_model_and_effort(self):
        for a in ("runner", "implementer", "reviewer", "verifier"):
            fm = frontmatter(PLUGIN / "agents" / f"delivery-{a}.md")
            self.assertEqual(fm["name"], f"delivery-{a}")
            self.assertTrue(fm["model"].startswith("claude-"), a)
            self.assertIn(fm.get("effort"), ("low", "medium", "high", "xhigh", "max"), a)  # §2.4: every seat pinned

    def test_skills_are_named_for_their_folders(self):
        for d in sorted((PLUGIN / "skills").iterdir()):
            fm = frontmatter(d / "SKILL.md")
            self.assertEqual(fm["name"], d.name)
            self.assertGreater(len(fm["description"]), 40)

    def test_hooks_name_executable_scripts(self):
        hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "SubagentStart", "SubagentStop", "TeammateIdle"})
        for entries in hooks.values():
            for h in entries[0]["hooks"]:
                script = re.search(r"/hooks/(\S+?\.sh)", h["command"]).group(1)
                self.assertTrue(os.access(PLUGIN / "hooks" / script, os.X_OK), script)

    def test_orientation_fits_the_hook_cap(self):
        text = re.sub(r"^<!--.*?-->\s*", "", (PLUGIN / "orientation.md").read_text(), flags=re.S)
        self.assertLess(len(text), 9500)
        self.assertTrue(text.startswith("# CCP — Claude Control Plane"))


class Hooks(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def test_orientation_only_in_a_managed_product(self):
        r = run([str(PLUGIN / "hooks/orientation.sh")], env={"CLAUDE_PROJECT_DIR": str(self.p.root)})
        body = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(body["hookEventName"], "SessionStart")
        self.assertIn("# CCP — Claude Control Plane", body["additionalContext"])
        with tempfile.TemporaryDirectory() as other:
            r = run([str(PLUGIN / "hooks/orientation.sh")], env={"CLAUDE_PROJECT_DIR": other})
            self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_run_binding_without_arguments_calls_ccp_on_path(self):
        with tempfile.TemporaryDirectory() as bindir:
            log = Path(bindir) / "log"
            fake = Path(bindir) / "ccp"
            fake.write_text(f"#!/bin/sh\necho \"$@\" >> {log}\ncat >> {log}\n")
            fake.chmod(0o755)
            r = run([str(PLUGIN / "hooks/run-binding.sh"), "start"], input='{"agent_id": "a1"}',
                    env={"PATH": f"{bindir}:{os.environ['PATH']}", "CLAUDE_PROJECT_DIR": str(self.p.root)})
            self.assertEqual(r.returncode, 0)
            self.assertEqual(log.read_text().splitlines(), [f"--root {self.p.root} agent start", '{"agent_id": "a1"}'])
            r = run([str(PLUGIN / "hooks/run-binding.sh"), "start"], input="{}", env={"PATH": "/usr/bin:/bin"})
            self.assertEqual(r.returncode, 0)  # no ccp on PATH: a no-op, never a failure


class Lookup(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._d = tempfile.TemporaryDirectory()
        self.plane = Path(self._d.name)
        self.q = self.plane / "queue"
        self.q.mkdir()
        (self.plane / "projects").mkdir()
        (self.plane / "projects/demo.yaml").write_text(f"project_id: demo\nproduct_root: {self.p.root}\nqueue_root: {self.q}\n")

    def tearDown(self):
        self.p.cleanup()
        self._d.cleanup()

    def where(self, env: dict) -> dict:
        out = io.StringIO()
        with mock.patch("ccp.queue.PLANE", self.plane), mock.patch.dict(os.environ, env), redirect_stdout(out):
            env_q = os.environ.pop("QUEUE_ROOT", None)
            try:
                self.assertEqual(cli.main(["--root", str(self.p.root), "where"]), 0)
            finally:
                os.environ.pop("QUEUE_ROOT", None)
                if env_q:
                    os.environ["QUEUE_ROOT"] = env_q
        return json.loads(out.getvalue())

    def test_the_queue_comes_from_the_binding(self):
        self.assertEqual(self.where({"CCP_NO_BINDING_QUEUE": "0"})["queue_root"], str(self.q))

    def test_tests_never_read_a_binding(self):
        self.assertIsNone(self.where({})["queue_root"])

    def test_a_scratch_clone_naming_a_live_project_gets_nothing(self):
        (self.plane / "projects/demo.yaml").write_text(f"project_id: demo\nproduct_root: /elsewhere\nqueue_root: {self.q}\n")
        self.assertIsNone(self.where({"CCP_NO_BINDING_QUEUE": "0"})["queue_root"])

    def test_a_project_id_cannot_walk_out_of_projects(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "../../evil"}))
        with self.assertRaises(config.ConfigError):
            config.load(self.p.root)


class AgentTypes(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def test_the_plugin_type_unless_the_product_has_its_own_copy(self):
        name, f = runs.definition(self.p.cfg, "delivery-implementer")
        self.assertEqual((name, f), ("ccp:delivery-implementer", PLUGIN / "agents/delivery-implementer.md"))
        self.assertEqual(runs.expected(self.p.cfg, "delivery-implementer"), ("claude-opus-5-5", "high"))
        self.p.write(".claude/agents/delivery-implementer.md", "---\nname: delivery-implementer\nmodel: claude-x\neffort: low\n---\n")
        self.assertEqual(runs.definition(self.p.cfg, "delivery-implementer")[0], "delivery-implementer")
        self.assertEqual(runs.expected(self.p.cfg, "delivery-implementer"), ("claude-x", "low"))

    def test_a_scoped_type_binds_its_run(self):
        self.assertEqual(runs.unscoped("ccp:delivery-verifier"), "delivery-verifier")
        self.assertEqual(runs.unscoped("delivery-verifier"), "delivery-verifier")
        self.assertEqual(runs.unscoped("other:delivery-verifier"), "other:delivery-verifier")


class Index(unittest.TestCase):
    def setUp(self):
        self.p = Product({"task_log": {"index": False}})
        self.p.task("0001-a")

    def tearDown(self):
        self.p.cleanup()

    def test_a_product_may_keep_no_index(self):
        self.assertEqual(tasklog.check(self.p.cfg), [])
        self.assertIn("no index", tasklog.write_index(self.p.cfg))
        self.assertFalse(self.p.cfg.index_path.exists())

    def test_the_index_format_is_frozen(self):
        p = Product()
        try:
            p.task("0001-a")
            lines = tasklog.render_index(p.cfg).splitlines()
            self.assertEqual([ln.strip().split(":")[0] for ln in lines[4:]], ["- id", "status", "title", "depends_on", "path"])
        finally:
            p.cleanup()

    def test_readers_use_the_task_files(self):
        import sys
        sys.path.insert(0, str(PLANE / "scripts/observability"))
        import lib
        with tempfile.TemporaryDirectory() as q:
            Path(q, "project.yaml").write_text(f"project_id: demo\nproduct_root: {self.p.root}\ndurable_docs_path: docs/delivery/\n")
            self.assertEqual(lib.load_durable_statuses(Path(q)), {"0001-a": "pending"})

    def test_index_must_be_a_boolean(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "task_log": {"index": "no"}}))
        with self.assertRaises(config.ConfigError):
            config.load(self.p.root)


class PlanePaths(unittest.TestCase):
    def test_docs_check_warns_on_a_plane_checkout_path(self):
        p = Product()
        try:
            p.index()
            p.write("docs/RUNBOOK.md", "Run /opt/src/control-plane/bin/ccp tasks next.\n")
            p.write("docs/delivery/tasks/notes.txt", "history: /opt/src/control-plane/bin/ccp\n")
            run(["git", "init", "-q"], cwd=p.root)
            run(["git", "add", "-A"], cwd=p.root)
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.main(["--root", str(p.root), "docs", "check"])
            self.assertEqual(code, 0, out.getvalue())
            self.assertIn("docs/RUNBOOK.md: names a control-plane checkout path", out.getvalue())
            self.assertNotIn("notes.txt", out.getvalue())
        finally:
            p.cleanup()


class CheckoutWarning(unittest.TestCase):
    def test_warns_off_main_and_dirty_and_not_on_clean_main(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run(["git", "init", "-q", "-b", "main"], cwd=repo)
            (repo / "f").write_text("x")
            run(["git", "add", "f"], cwd=repo)
            run(["git", "commit", "-qm", "init"], cwd=repo)
            with mock.patch("ccp.queue.PLANE", repo), mock.patch.dict(os.environ, {"CCP_DEV": "0"}):
                self.assertIsNone(cli.checkout_warning())
                (repo / "f").write_text("y")
                self.assertIn("local changes", cli.checkout_warning())
                run(["git", "checkout", "-q", "-b", "topic"], cwd=repo)
                self.assertIn("on topic, not main", cli.checkout_warning())
            with mock.patch("ccp.queue.PLANE", repo):
                self.assertIsNone(cli.checkout_warning())  # CCP_DEV=1 in tests


class RunCheckout(unittest.TestCase):
    def test_install_update_and_refusals(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            origin = d / "origin.git"
            run(["git", "init", "-q", "--bare", "-b", "main", str(origin)])
            seed = d / "seed"
            run(["git", "clone", "-q", str(origin), str(seed)])
            run(["git", "checkout", "-q", "-b", "main"], cwd=seed)
            (seed / "bin").mkdir()
            (seed / "bin/ccp").write_text("#!/bin/sh\n")
            run(["git", "add", "-A"], cwd=seed)
            run(["git", "commit", "-qm", "one"], cwd=seed)
            run(["git", "push", "-q", "origin", "main"], cwd=seed)
            env = {"CCP_RUN_CHECKOUT": str(d / "run"), "CCP_BIN_LINK": str(d / "bin/ccp")}
            script = str(PLANE / "scripts/run-checkout.sh")
            # install clones the plane's own origin; point it at ours through a copy of the script's repo
            r = run(["git", "clone", "-q", str(origin), str(d / "run")])
            self.assertEqual(r.returncode, 0)
            r = run([script, "install"], env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.readlink(d / "bin/ccp"), str(d / "run/bin/ccp"))
            self.assertEqual(run([script, "status"], env=env).returncode, 0)
            (seed / "two").write_text("2")
            run(["git", "add", "two"], cwd=seed)
            run(["git", "commit", "-qm", "two"], cwd=seed)
            run(["git", "push", "-q", "origin", "main"], cwd=seed)
            r = run([script, "update"], env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((d / "run/two").exists())
            (d / "run/two").write_text("edited")
            r = run([script, "update"], env=env)
            self.assertEqual(r.returncode, 1)
            self.assertIn("local changes", r.stderr)

    def test_update_keeps_local_dirs_a_commit_untracks(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            origin, seed = d / "origin.git", d / "seed"
            run(["git", "init", "-q", "--bare", "-b", "main", str(origin)])
            run(["git", "clone", "-q", str(origin), str(seed)])
            run(["git", "checkout", "-q", "-b", "main"], cwd=seed)
            (seed / "bin").mkdir()
            (seed / "bin/ccp").write_text("#!/bin/sh\n")
            (seed / "projects").mkdir()
            (seed / "projects/p.yaml").write_text("project_id: p\n")
            run(["git", "add", "-A"], cwd=seed)
            run(["git", "commit", "-qm", "one"], cwd=seed)
            run(["git", "push", "-q", "origin", "main"], cwd=seed)
            run(["git", "clone", "-q", str(origin), str(d / "run")])
            env = {"CCP_RUN_CHECKOUT": str(d / "run"), "CCP_BIN_LINK": str(d / "bin/ccp")}
            script = str(PLANE / "scripts/run-checkout.sh")
            run(["git", "rm", "-q", "-r", "--cached", "projects"], cwd=seed)
            (seed / ".gitignore").write_text("projects/\n")
            run(["git", "add", ".gitignore"], cwd=seed)
            run(["git", "commit", "-qm", "untrack projects"], cwd=seed)
            run(["git", "push", "-q", "origin", "main"], cwd=seed)
            r = run([script, "update"], env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((d / "run/projects/p.yaml").is_file())
            self.assertEqual((d / "run/projects/p.yaml").read_text(), "project_id: p\n")


class LaunchdLabel(unittest.TestCase):
    def test_run_checkout_and_ccp_build_the_same_label(self):
        from ccp import otel
        for v in ("", "dev.ccp", "com.example.", " .x.y. ", "bad prefix!", "a..b"):
            env = {k: x for k, x in os.environ.items() if k not in ("CCP_OTEL_LABEL", "CCP_LAUNCHD_PREFIX")}
            env["CCP_LAUNCHD_PREFIX"] = v
            out = subprocess.run(["bash", str(PLANE / "scripts/run-checkout.sh"), "label"], capture_output=True,
                                 text=True, env=env).stdout.strip()
            with mock.patch.dict(os.environ, {"CCP_LAUNCHD_PREFIX": v}):
                self.assertEqual(out, otel.launchd_label(), v)
        self.assertEqual(out, "dev.ccp.control-plane.otel")  # "a..b" is no reverse-DNS prefix


class SyncInPluginMode(unittest.TestCase):
    def test_a_product_on_the_plugin_gets_no_copies_and_loses_stale_ones(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "prod"
            (root / ".claude").mkdir(parents=True)
            (root / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"ccp@ccp": True}}))
            stale = root / "docs/delivery/REVIEW-TRIAGE.md"
            stale.parent.mkdir(parents=True)
            stale.write_text("> Managed copy of control-plane `templates/docs-delivery/REVIEW-TRIAGE.md` at abcdef1. Edit.\n\nold\n")
            mine = root / ".claude/agents/delivery-runner.md"
            mine.parent.mkdir(parents=True)
            mine.write_text("my own runner, no header\n")
            yml = Path(d) / "demo.yaml"
            yml.write_text(f"project_id: demo\nproduct_root: {root}\nhosting: claude-team\n")
            sync = [str(PLANE / "scripts/sync-product-docs.sh"), "demo", "--project-yaml", str(yml), "--allow-dirty"]
            r = run(["bash", *sync[0:1], *sync[1:], "--check"])
            self.assertIn("DRIFT docs/delivery/REVIEW-TRIAGE.md: retired", r.stdout, r.stdout + r.stderr)
            r = run(["bash", *sync])
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(stale.exists())
            self.assertTrue(mine.exists())  # no header: the product's own, left alone
            self.assertIn("left alone", r.stdout)
            self.assertFalse((root / "docs/delivery/CONTROL-PLANE.md").exists())
            self.assertFalse((root / "CLAUDE.md").exists())


class ProtocolFromThePlugin(unittest.TestCase):
    def test_plugin_protocol_doc_resolves_to_the_skill(self):
        import sys
        sys.path.insert(0, str(PLANE / "scripts/observability"))
        import spec_maintainer as sm
        path = sm.protocol_doc_path({"protocol_doc": "plugin:ccp:spec-maintainer"}, Path("/nonexistent"))
        self.assertEqual(Path(path), PLUGIN / "skills/spec-maintainer/SKILL.md")
        self.assertTrue(Path(path).is_file())


if __name__ == "__main__":
    unittest.main()


class ArchitectFromThePlugin(unittest.TestCase):
    def test_skill_triage_doc_and_plugin_dir_follow_the_product(self):
        import sys
        sys.path.insert(0, str(PLANE / "scripts/observability"))
        import architecture_review as ar
        p = Product()
        try:
            self.assertEqual(Path(ar.architect_skill(p.root)), PLUGIN / "skills/architect/SKILL.md")
            self.assertEqual(ar.plugin_args(p.root), ["--plugin-dir", str(PLUGIN)])
            self.assertEqual(Path(ar.triage_doc(str(p.root))), PLUGIN / "skills/review-triage/SKILL.md")
            p.write(".claude/skills/architect/SKILL.md", "---\nname: architect\n---\n")
            p.write("docs/delivery/REVIEW-TRIAGE.md", "mine\n")
            self.assertEqual(Path(ar.architect_skill(p.root)), p.root / ".claude/skills/architect/SKILL.md")
            self.assertEqual(ar.plugin_args(p.root), [])
            self.assertEqual(ar.triage_doc(str(p.root)), f"{p.root}/docs/delivery/REVIEW-TRIAGE.md")
        finally:
            p.cleanup()


class SyncFlagsStaleHookEntries(unittest.TestCase):
    def test_settings_hooks_that_call_copies_are_reported(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "prod"
            (root / ".claude").mkdir(parents=True)
            (root / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"ccp@ccp": True}}))
            (root / ".claude/settings.local.json").write_text(json.dumps({"hooks": {"TeammateIdle": [{"hooks": [
                {"type": "command", "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/runner-idle.sh --queue-root /q"}]}]}}))
            yml = Path(d) / "demo.yaml"
            yml.write_text(f"project_id: demo\nproduct_root: {root}\nhosting: claude-team\n")
            r = run(["bash", str(PLANE / "scripts/sync-product-docs.sh"), "demo", "--project-yaml", str(yml), "--check"])
            self.assertIn("DRIFT .claude/settings.local.json: stale_hooks", r.stdout, r.stdout + r.stderr)


class BindingNeedsNoChange(unittest.TestCase):
    """§9: a product moves to the plugin without its binding changing."""

    def test_runner_type_and_protocol_follow_the_product(self):
        import sys
        sys.path.insert(0, str(PLANE / "scripts/observability"))
        import spec_maintainer as sm
        import team
        p = Product()
        try:
            with tempfile.TemporaryDirectory() as q:
                Path(q, "project.yaml").write_text(f"project_id: demo\nproduct_root: {p.root}\nhosting: claude-team\n"
                                                   "runner:\n  agent_type: delivery-runner\n")
                self.assertEqual(team.runner_cfg(Path(q))["agent_type"], "ccp:delivery-runner")
                self.assertEqual(Path(sm.protocol_doc_path({}, Path(q))), PLUGIN / "skills/spec-maintainer/SKILL.md")
                p.write(".claude/agents/delivery-runner.md", "---\nname: delivery-runner\n---\n")
                p.write("docs/delivery/SPEC-MAINTAINER.md", "mine\n")
                self.assertEqual(team.runner_cfg(Path(q))["agent_type"], "delivery-runner")
                self.assertEqual(sm.protocol_doc_path({}, Path(q)), f"{p.root}/docs/delivery/SPEC-MAINTAINER.md")
        finally:
            p.cleanup()
