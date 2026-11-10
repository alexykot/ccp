"""SPEC §4.3, §8.3: `ccp init` adopts a product in one command, and every reader of the binding goes
through one resolver, so an edit to it reaches them all. Scratch HOME, bindings, repos and queues."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLANE = Path(__file__).resolve().parents[1]
CCP = PLANE / "bin" / "ccp"
TEAM = PLANE / "scripts" / "team.sh"
HOOK = PLANE / "plugin" / "hooks" / "runner-idle.sh"
sys.path.insert(0, str(PLANE / "scripts" / "observability"))
import lib  # noqa: E402

from ccp import init as ccp_init  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
FOOTPRINT = ("docs/PROJECT.md", "docs/SPEC.md", "docs/delivery/plane.json", "docs/delivery/TEMPLATE-task.md",
             "docs/delivery/WRITING-tasks.md", "docs/delivery/standing-dod.md", "docs/delivery/INDEX.yaml")


class InitCase(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        base = Path(self._d.name).resolve()
        self.home, self.bindings, self.repo = base / "home", base / "bindings", base / "repo"
        self.home.mkdir()
        self.repo.mkdir()
        self.git("init", "-q", ".")
        self.env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        self.env.update(GIT_ENV, HOME=str(self.home), CCP_BINDINGS_DIR=str(self.bindings))

    def tearDown(self):
        self._d.cleanup()

    def git(self, *args, cwd=None):
        subprocess.run(["git", *args], cwd=cwd or self.repo, check=True, capture_output=True, env={**os.environ, **GIT_ENV})

    def ccp(self, *args, cwd=None, **env):
        return subprocess.run([str(CCP), *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              env={**self.env, **env})

    def init(self, *args, cwd=None):
        r = self.ccp("init", *args, cwd=cwd)
        return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)

    @property
    def binding(self) -> Path:
        return self.bindings / "demo.yaml"

    @property
    def queue(self) -> Path:
        return self.home / ".delivery-queue" / "demo"


class Adopt(InitCase):
    def test_an_empty_repository_is_adopted_in_one_command(self):
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        for rel in FOOTPRINT:
            self.assertTrue((self.repo / rel).is_file(), rel)
        self.assertEqual((self.repo / "docs/PROJECT.md").read_text(), (PLANE / "templates/docs-project/PROJECT.md").read_text())
        self.assertEqual(json.loads((self.repo / "docs/delivery/plane.json").read_text()),
                         {"project_id": "demo", "worktrees": {"dir": ".plane-runtime"}})
        self.assertIn(".plane-runtime/", (self.repo / ".gitignore").read_text().splitlines())
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings, ccp_init.ANCHOR)
        self.assertTrue(settings["enabledPlugins"]["ccp@ccp"])
        self.assertIn("ccp", settings["extraKnownMarketplaces"])
        self.assertEqual(settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"], "1")
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), ccp_init.CLAUDE_LINE + "\n")
        self.assertTrue(self.queue.is_dir())
        self.assertFalse((self.queue / "project.yaml").exists())  # §8.3: no copy in the queue
        b = self.binding.read_text()
        for line in ("project_id: demo", "integration_branch: main", f"product_root: {self.repo}",
                     "durable_docs_path: docs/delivery/", f"queue_root: {self.queue}", "  name: runner"):
            self.assertIn(line, b.splitlines())
        self.assertEqual((res["binding"], res["queue_root"]), (str(self.binding), str(self.queue)))

        for check in (("tasks", "check"), ("docs", "check")):
            r = self.ccp(*check)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        where = json.loads(self.ccp("where", CCP_NO_BINDING_QUEUE="0").stdout)
        self.assertEqual((where["binding"], where["queue_root"]), (str(self.binding), str(self.queue)))

    def test_flags_set_the_queue_branch_and_gate(self):
        q = self.home / "elsewhere" / "q"
        code, res = self.init("--project-id", "demo", "--queue-root", str(q), "--integration-branch", "trunk",
                              "--gate", "python3 -m unittest discover -s tests")
        self.assertEqual(code, 0, res)
        self.assertTrue(q.is_dir())
        self.assertIn(f"queue_root: {q}", self.binding.read_text().splitlines())
        self.assertIn("integration_branch: trunk", self.binding.read_text().splitlines())
        cfg = json.loads((self.repo / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"]["lanes"]["gate"], ["python3", "-m", "unittest", "discover", "-s", "tests"])

    def test_the_id_defaults_to_plane_json_then_the_directory(self):
        code, res = self.init()
        self.assertEqual((code, res["project_id"]), (0, "repo"))
        code, res = self.init()
        self.assertEqual((code, res["project_id"]), (0, "repo"))  # now from plane.json
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "other"}))
        code, res = self.init()
        self.assertEqual((code, res["project_id"]), (0, "other"))

    def test_a_bad_id_is_refused(self):
        code, err = self.init("--project-id", "Not_An_Id")
        self.assertEqual(code, 2)
        self.assertFalse((self.repo / "docs").exists())

    def test_from_a_worktree_the_binding_names_the_main_checkout(self):
        self.git("commit", "-q", "--allow-empty", "-m", "first")
        wt = self.repo.parent / "wt"
        self.git("worktree", "add", "-q", "--detach", str(wt))
        code, res = self.init("--project-id", "demo", cwd=wt)
        self.assertEqual(code, 0, res)
        self.assertIn(f"product_root: {self.repo}", self.binding.read_text().splitlines())
        self.assertTrue((wt / "docs/delivery/plane.json").is_file())


class OneSource(unittest.TestCase):
    """SPEC §4.3 and the README quote the anchor and the CLAUDE.md line exactly as init writes them."""

    def assert_quotes(self, text: str):
        blocks = [b for b in re.findall(r"```json\n(.*?)```", text, re.S) if '"extraKnownMarketplaces"' in b]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(json.loads("{" + blocks[0] + "}"), ccp_init.ANCHOR)
        self.assertIn(f'"{ccp_init.CLAUDE_LINE}"', " ".join(text.split()))

    def section(self, path: str, heading: str) -> str:
        text = (PLANE / path).read_text()
        start = text.index(heading)
        return text[start:text.index("\n#", start + len(heading))]

    def test_spec_4_3_quotes_what_init_writes(self):
        self.assert_quotes(self.section("docs/spec/01-model.md", "### 4.3 What a product holds"))

    def test_the_readme_quotes_what_init_writes(self):
        self.assert_quotes(self.section("README.md", "### 2. Adopt a product"))


class NoClobber(InitCase):
    def setUp(self):
        super().setUp()
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ccp:*)"]}, "env": {"MINE": "x"}, "enabledPlugins": {"other@x": True}}))
        (self.repo / "CLAUDE.md").write_text("# My product\nNo trailing newline")
        (self.repo / ".gitignore").write_text("node_modules/\n.plane-runtime\n")

    def test_twice_keeps_other_keys_one_claude_line_and_existing_docs(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        (self.repo / "docs/SPEC.md").write_text("# My spec\n")
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["permissions"], {"allow": ["Bash(ccp:*)"]})
        self.assertEqual(settings["env"], {"MINE": "x", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"})
        self.assertEqual(settings["enabledPlugins"], {"other@x": True, "ccp@ccp": True})
        lines = (self.repo / "CLAUDE.md").read_text().splitlines()
        self.assertEqual(lines[:2], ["# My product", "No trailing newline"])
        self.assertEqual(len(lines), 3)
        self.assertEqual((self.repo / ".gitignore").read_text(), "node_modules/\n.plane-runtime\n")
        self.assertEqual((self.repo / "docs/SPEC.md").read_text(), "# My spec\n")
        self.assertIn("docs/SPEC.md", res["kept"])
        self.assertEqual(res["written"], [])
        self.assertEqual(res["merged"], [])

    def test_force_overwrites_the_files_init_writes(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        (self.repo / "docs/SPEC.md").write_text("# My spec\n")
        self.binding.write_text(self.binding.read_text().replace("name: runner", "name: steward"))
        code, res = self.init("--project-id", "demo", "--force")
        self.assertEqual(code, 0, res)
        self.assertEqual((self.repo / "docs/SPEC.md").read_text(), (PLANE / "templates/docs-project/SPEC.md").read_text())
        self.assertIn("  name: runner", self.binding.read_text().splitlines())
        self.assertEqual(json.loads((self.repo / ".claude/settings.json").read_text())["env"]["MINE"], "x")

    def test_a_rerun_keeps_an_edited_binding(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.binding.write_text(self.binding.read_text().replace("name: runner", "name: steward"))
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.assertIn("binding", res["kept"])
        self.assertIn("  name: steward", self.binding.read_text().splitlines())


class Refusals(InitCase):
    def assert_refused_untouched(self, *args):
        before = sorted(p.relative_to(self.repo) for p in self.repo.rglob("*") if ".git" not in p.parts)
        code, err = self.init(*args)
        self.assertEqual(code, 2, err)
        self.assertEqual(sorted(p.relative_to(self.repo) for p in self.repo.rglob("*") if ".git" not in p.parts), before)
        return err

    def test_a_plane_json_for_another_project(self):
        (self.repo / "docs/delivery").mkdir(parents=True)
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "other"}))
        self.assert_refused_untouched("--project-id", "demo")
        self.assertFalse(self.binding.exists())
        self.assertEqual(self.init("--project-id", "demo", "--force")[0], 0)
        self.assertEqual(json.loads((self.repo / "docs/delivery/plane.json").read_text())["project_id"], "demo")

    def test_a_binding_for_another_product(self):
        self.bindings.mkdir()
        self.binding.write_text("project_id: demo\nproduct_root: /elsewhere\nqueue_root: /elsewhere/q\n")
        self.assert_refused_untouched("--project-id", "demo")
        self.assertIn("/elsewhere", self.binding.read_text())

    def test_a_kept_binding_naming_another_queue(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.assert_refused_untouched("--project-id", "demo", "--queue-root", str(self.home / "other"))
        self.assertFalse((self.home / "other").exists())

    def test_settings_that_are_not_a_json_object(self):
        (self.repo / ".claude").mkdir()
        for text in ("{not json", "[]", '{"env": []}'):
            (self.repo / ".claude/settings.json").write_text(text)
            self.assert_refused_untouched("--project-id", "demo")
            self.assertEqual((self.repo / ".claude/settings.json").read_text(), text)


class OneBinding(InitCase):
    """§8.3: a binding edit reaches every reader; the queue holds no copy."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.binding.write_text(self.binding.read_text().replace("name: runner", "name: steward") + "ci: github-actions\n")

    def test_team_sh_spawns_the_name_in_the_binding(self):
        r = subprocess.run(["bash", str(TEAM), "runner", "spawn", "--scope", "0001-a"], capture_output=True,
                           text=True, env={**self.env, "QUEUE_ROOT": str(self.queue)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["actions"][0]["name"], "steward")

    def test_the_resolver_prefers_the_binding_to_a_stale_queue_copy(self):
        (self.queue / "project.yaml").write_text("project_id: demo\nrunner:\n  name: old\n")
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings)}):
            os.environ.pop("PROJECT_YAML", None)
            self.assertEqual(lib.binding_path(self.queue), self.binding)
            self.assertEqual(lib.resolve_durable_docs_dir(self.queue), self.repo / "docs/delivery")
            from ccp import queue, verify  # noqa: PLC0415
            self.assertEqual(queue.binding_runner_name(self.queue), "steward")
            self.assertTrue(verify._ci(self.queue))

    def test_without_a_binding_the_queue_copy_still_reads(self):
        other = Path(self._d.name) / "legacy-q"
        other.mkdir()
        self.assertIsNone(lib.binding_path(other))
        (other / "project.yaml").write_text("project_id: legacy\n")
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings)}):
            os.environ.pop("PROJECT_YAML", None)
            self.assertEqual(lib.binding_path(other), other / "project.yaml")
            explicit = Path(self._d.name) / "explicit.yaml"
            explicit.write_text("project_id: x\n")
            with mock.patch.dict(os.environ, {"PROJECT_YAML": str(explicit)}):
                self.assertEqual(lib.binding_path(self.queue), explicit)

    def test_the_idle_hook_reads_the_binding_ccp_where_names(self):
        tid = "0001-hello-delivery-log"
        (self.queue / "work.json").write_text(json.dumps({"status": "running", "scope": [tid], "waiting_on": None}))
        (self.repo / f"docs/delivery/tasks/{tid}.md").write_text(
            (PLANE / f"templates/docs-delivery/example-tasks/{tid}.md").read_text().replace("status: done", "status: pending"))
        self.assertEqual(self.ccp("tasks", "index").returncode, 0)
        fake = Path(self._d.name) / "bin"
        fake.mkdir()
        where = json.dumps({"binding": str(self.binding), "queue_root": str(self.queue), "ccp": str(CCP)})
        (fake / "ccp").write_text(f"#!/bin/sh\necho '{where}'\n")
        (fake / "ccp").chmod(0o755)
        env = {**self.env, "PATH": f"{fake}:{os.environ['PATH']}", "CLAUDE_PROJECT_DIR": str(self.repo)}

        def hook(name):
            stdin = json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": name, "cwd": str(self.repo)})
            return subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, input=stdin).returncode
        self.assertEqual(hook("runner"), 0)   # not the binding's runner any more
        self.assertEqual(hook("steward"), 2)  # the binding's name: kept working on its ready task


if __name__ == "__main__":
    unittest.main()
