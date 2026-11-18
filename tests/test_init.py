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
        self.assertEqual(settings, {**ccp_init.ANCHOR, "subagentPromptCacheTtl": "1h", "autoCompactWindow": 350000})
        self.assertTrue(settings["enabledPlugins"]["ccp@ccp"])
        self.assertIn("ccp", settings["extraKnownMarketplaces"])
        self.assertEqual(settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"], "1")
        self.assertEqual((self.repo / "CLAUDE.md").read_text(), ccp_init.CLAUDE_LINE + "\n")
        self.assertTrue(self.queue.is_dir())
        self.assertFalse((self.queue / "project.yaml").exists())  # §8.3: no copy in the queue
        b = self.binding.read_text()
        for line in ("project_id: demo", "integration_branch: main", "production_branch: main", f"product_root: {self.repo}",
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
        self.assertIn("production_branch: trunk", self.binding.read_text().splitlines())
        cfg = json.loads((self.repo / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"]["lanes"]["gate"], [{"name": "gate", "cmd": "python3 -m unittest discover -s tests"}])

    def test_a_gate_is_one_stage_holding_the_line_as_given(self):
        line = "cd sub && make check 'a  b' | tee out.txt"
        code, res = self.init("--project-id", "demo", "--gate", line)
        self.assertEqual(code, 0, res)
        cfg = json.loads((self.repo / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"], {"lanes": {"gate": [{"name": "gate", "cmd": line}]}})

    def test_a_gate_against_a_kept_plane_json_is_listed_as_not_applied(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        code, res = self.init("--project-id", "demo", "--gate", "make test")
        self.assertEqual(code, 0, res)
        self.assertIn("docs/delivery/plane.json (--gate not applied)", res["kept"])
        self.assertNotIn("suite", json.loads((self.repo / "docs/delivery/plane.json").read_text()))

    def test_starter_rules_are_offered_and_adopted(self):
        code, res = self.init("--project-id", "demo", "--starter-rules")
        self.assertEqual(code, 0, res)
        self.assertIn("docs/ENGINEERING.md", res["written"])
        self.assertEqual((self.repo / "docs/ENGINEERING.md").read_text(),
                         (PLANE / "templates/docs-project/starter-rules.md").read_text())
        cfg = json.loads((self.repo / "docs/delivery/plane.json").read_text())
        self.assertEqual({k: cfg[k] for k in ccp_init.STARTER_CONFIG}, ccp_init.STARTER_CONFIG)
        r = self.ccp("docs", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.init("--project-id", "demo")[1]["written"])

    def test_starter_rules_against_a_kept_plane_json_are_listed_as_not_applied(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.assertFalse((self.repo / "docs/ENGINEERING.md").exists())
        code, res = self.init("--project-id", "demo", "--gate", "make test", "--starter-rules")
        self.assertEqual(code, 0, res)
        self.assertIn("docs/delivery/plane.json (--gate, --starter-rules not applied)", res["kept"])
        self.assertIn("docs/ENGINEERING.md", res["written"])
        self.assertNotIn("docs", json.loads((self.repo / "docs/delivery/plane.json").read_text()))

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
        self.assertEqual(lines, ["# My product", "No trailing newline", "", ccp_init.CLAUDE_LINE])
        self.assertEqual((self.repo / ".gitignore").read_text(), "node_modules/\n.plane-runtime\n")
        self.assertEqual((self.repo / "docs/SPEC.md").read_text(), "# My spec\n")
        self.assertIn("docs/SPEC.md", res["kept"])
        self.assertEqual(res["written"], [])
        self.assertEqual(res["merged"], [])

    def test_the_claude_line_is_its_own_paragraph_after_any_ending(self):
        for before, after in (("# P\nText\n", "# P\nText\n\n"), ("# P\nText\n\n", "# P\nText\n\n"),
                              ("# P\nText\n  ", "# P\nText\n  \n"), ("\n", "\n")):
            (self.repo / "CLAUDE.md").write_text(before)
            self.assertEqual(self.init("--project-id", "demo")[0], 0)
            self.assertEqual((self.repo / "CLAUDE.md").read_text(), after + ccp_init.CLAUDE_LINE + "\n", repr(before))

    def test_an_anchor_key_the_product_set_keeps_its_value(self):
        mine = {"ccp": {"source": {"source": "directory", "path": "/opt/my-ccp"}},
                "other": {"source": {"source": "github", "repo": "x/y"}}}
        text = json.dumps({"extraKnownMarketplaces": mine, "enabledPlugins": {"ccp@ccp": False, "other@x": True},
                           "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "0"},
                           "subagentPromptCacheTtl": "1h", "autoCompactWindow": 350000}, indent=4)
        (self.repo / ".claude/settings.json").write_text(text)
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.assertEqual((self.repo / ".claude/settings.json").read_text(), text)
        self.assertNotIn(".claude/settings.json", res["merged"])

    def test_an_anchor_block_gains_only_the_missing_entries(self):
        mine = {"source": {"source": "directory", "path": "/opt/my-ccp"}}
        (self.repo / ".claude/settings.json").write_text(json.dumps(
            {"extraKnownMarketplaces": {"ccp": mine, "other": {"source": {"source": "github", "repo": "x/y"}}},
             "enabledPlugins": {"ccp@ccp": False}}))
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        settings = json.loads((self.repo / ".claude/settings.json").read_text())
        self.assertEqual(settings["extraKnownMarketplaces"],
                         {"ccp": mine, "other": {"source": {"source": "github", "repo": "x/y"}}})
        self.assertEqual(settings["enabledPlugins"], {"ccp@ccp": False})
        self.assertEqual(settings["env"], ccp_init.ANCHOR["env"])
        self.assertIn(".claude/settings.json", res["merged"])

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


class Adoption(InitCase):
    """§4.5: init records the adoption as a `plane`/`adopted` ledger event, once per adoption."""

    def adopted(self):
        rows = [json.loads(ln) for ln in lib.events_path(self.queue).read_text().splitlines()] \
            if lib.events_path(self.queue).is_file() else []
        return [r for r in rows if (r.get("type"), r.get("op")) == ("plane", "adopted")]

    def test_writing_the_binding_records_one_event_and_a_rerun_none(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        [ev] = self.adopted()
        head = subprocess.run(["git", "-C", str(PLANE), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual((ev["project_id"], ev["task_id"], ev["actor"]), ("demo", "", "operator"))
        self.assertEqual(ev["payload"], {"plane": head, "binding": "written"})
        self.assertEqual(lib.validate_event(ev), [])
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.assertIn("binding", res["kept"])
        self.assertEqual(len(self.adopted()), 1)

    def test_a_kept_binding_on_a_queue_with_no_event_records_one_as_kept(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        ledger = lib.events_path(self.queue)
        older = {"at": "2026-01-01T00:00:00Z", "project_id": "demo", "task_id": "0001-a", "actor": "task-runner",
                 "type": "lease", "op": "set", "payload": {"holder": "r"}}
        ledger.write_text(json.dumps(older) + "\n")  # the queue as it was before the event existed
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        [ev] = self.adopted()
        self.assertEqual(ev["payload"]["binding"], "kept")
        self.assertEqual(json.loads(ledger.read_text().splitlines()[0]), older)
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.assertEqual(len(self.adopted()), 1)

    def test_force_rewriting_the_binding_records_another(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.assertEqual(self.init("--project-id", "demo", "--force")[0], 0)
        self.assertEqual([e["payload"]["binding"] for e in self.adopted()], ["written", "written"])

    def test_the_op_and_its_keys_are_in_the_contract(self):
        schema = json.loads((PLANE / "contracts" / "observability_event.schema.json").read_text())
        self.assertIn("adopted", schema["properties"]["op"]["enum"])
        self.assertEqual(lib.REQUIRED_PAYLOAD[("plane", "adopted")], ("plane", "binding"))
        ev = {"at": "2026-01-01T00:00:00Z", "project_id": "demo", "task_id": "", "actor": "operator", "type": "plane",
              "op": "adopted", "payload": {"plane": "abc"}}
        self.assertIn("payload missing binding", lib.validate_event(ev))


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

    def test_a_gate_that_does_not_split(self):
        err = self.assert_refused_untouched("--project-id", "demo", "--gate", 'echo "x')
        self.assertIn("--gate", err)
        self.assertFalse((self.repo / "docs/delivery/plane.json").exists())
        self.assertFalse(self.binding.exists())

    def test_a_kept_plane_json_that_does_not_load(self):
        (self.repo / "docs/delivery").mkdir(parents=True)
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "demo", "board": {"refresh_minutes": 0}}))
        err = self.assert_refused_untouched("--project-id", "demo")
        self.assertIn("board.refresh_minutes", err)
        self.assertFalse(self.binding.exists())
        self.assertFalse(self.queue.exists())

    def test_a_path_holding_a_hash(self):
        repo = self.repo.parent / "my repo #1"
        repo.mkdir()
        self.git("init", "-q", ".", cwd=repo)
        self.repo = repo
        err = self.assert_refused_untouched("--project-id", "demo")
        self.assertIn("product root", err)
        self.assertFalse(self.binding.exists())
        self.assertFalse(self.queue.exists())
        self.repo = self.repo.parent / "repo"
        err = self.assert_refused_untouched("--project-id", "demo", "--queue-root", str(self.home / "q #2"))
        self.assertIn("queue path", err)
        self.assertFalse(self.binding.exists())
        self.assertFalse((self.home / "q #2").exists())


class GithubOrigin(InitCase):
    """ADR-0040 D7: pull requests need a GitHub origin; init warns, naming the commands, and adopts anyway."""

    def adopt(self):
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.repo / "docs/delivery/plane.json").is_file())
        return json.loads(r.stdout), r.stderr

    def assert_warns(self, res, err):
        self.assertEqual(len(res["warnings"]), 1)
        for text in (res["warnings"][0], err):
            self.assertIn("GitHub", text)
            for command in ("ccp verify merge-ok", "ccp tasks close", "gh pr"):
                self.assertIn(command, text)

    def test_a_local_bare_origin_is_warned_about(self):
        bare = self.repo.parent / "bare.git"
        self.git("init", "-q", "--bare", str(bare))
        self.git("remote", "add", "origin", str(bare))
        self.assert_warns(*self.adopt())

    def test_no_origin_is_warned_about(self):
        res, err = self.adopt()
        self.assert_warns(res, err)
        self.assertIn("no origin", err)

    def test_an_origin_on_another_host_is_named_without_its_credentials(self):
        self.git("remote", "add", "origin", "https://someone:s3cret@git.example.org/team/repo.git")
        res, err = self.adopt()
        self.assert_warns(res, err)
        self.assertIn("git.example.org", err)
        self.assertNotIn("s3cret", err + json.dumps(res))

    def test_an_origin_that_does_not_parse_is_named_and_adopted_as_one_with_no_github_origin(self):
        self.git("remote", "add", "origin", "https://someone:s3cret@[::1")
        res, err = self.adopt()
        self.assert_warns(res, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("https://[::1", res["warnings"][0])
        self.assertNotIn("s3cret", err + json.dumps(res))
        self.assertTrue(self.queue.is_dir())

    def test_a_github_origin_is_not_warned_about(self):
        self.git("remote", "add", "origin", "https://example.invalid/placeholder.git")
        for url in ("https://github.com/team/repo.git", "git@github.com:team/repo.git",
                    "ssh://git@ssh.github.com:443/team/repo.git"):
            with self.subTest(url=url):
                self.git("remote", "set-url", "origin", url)
                res, err = self.adopt()
                self.assertNotIn("warnings", res)
                self.assertNotIn("warning", err)


class EarlierTaskFiles(InitCase):
    """§5.3: adopting a product whose task files have no frontmatter names them and `ccp tasks migrate`."""

    def setUp(self):
        super().setUp()
        self.git("remote", "add", "origin", "https://github.com/team/repo.git")  # no origin warning

    def test_task_files_with_no_frontmatter_are_counted_in_the_warnings(self):
        tasks = self.repo / "docs/delivery/tasks"
        tasks.mkdir(parents=True)
        for n in ("0001-a", "0002-b"):
            (tasks / f"{n}.md").write_text(f"# Task {n[:4]}: old\n\n## Meta\n\n| Field | Value |\n|---|---|\n")
        (tasks / "0003-c.md").write_text("---\ntask_id: 0003-c\n---\n")
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertEqual(len(res["warnings"]), 1, res)
        for text in (res["warnings"][0], r.stderr):
            self.assertIn("2 task file", text)
            self.assertIn("`ccp tasks migrate`", text)

    def test_a_current_task_log_is_not_warned_about(self):
        tasks = self.repo / "docs/delivery/tasks"
        tasks.mkdir(parents=True)
        (tasks / "0001-a.md").write_text("---\ntask_id: 0001-a\n---\n")
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("warnings", json.loads(r.stdout))


class KeptBinding(InitCase):
    """§8.3: a kept binding is checked against the current shape; each missing or obsolete key is a warning
    naming the binding file and the fix, and init still adopts the product."""

    def setUp(self):
        super().setUp()
        self.git("remote", "add", "origin", "https://github.com/team/repo.git")  # no origin warning
        self.bindings.mkdir()

    def keep(self, text: str) -> tuple[dict, str]:
        self.binding.write_text(text)
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertIn("binding", res["kept"])
        self.assertEqual(self.binding.read_text(), text)
        return res, r.stderr

    def named(self, warnings: list[str], key: str) -> str:
        hits = [w for w in warnings if key in w]
        self.assertEqual(len(hits), 1, (key, warnings))
        for part in (str(self.binding), "ccp init --force"):
            self.assertIn(part, hits[0])
        return hits[0]

    def test_an_earlier_generations_binding_is_named_with_what_it_lacks_and_carries(self):
        _, err = self.keep(f"project_id: demo\nintegration_branch: main\nproduct_root: {self.repo}\n"
                           f"durable_docs_path: docs/delivery/\nqueue_root: {self.queue}\n"
                           "seats:\n  runner: x\n  steerer: y\nemail:\n  alert_to: a@example.com\nhosting: claude\n")
        res = json.loads(self.ccp("init", "--project-id", "demo").stdout)
        self.assertIn("lacks", self.named(res["warnings"], "the `runner` block"))
        for key in ("`seats.runner`", "`email`", "`hosting`"):
            self.assertIn("carries", self.named(res["warnings"], key))
        self.assertEqual(len(res["warnings"]), 4, res["warnings"])  # `seats.steerer` is current
        self.assertIn("seats.runner", err)

    def test_retired_unlisted_and_partial_keys_are_named_and_still_read_ones_are_not(self):
        res, _ = self.keep(f"project_id: demo\nintegration_branch: main\nproduct_root: {self.repo}\n"
                           f"queue_root: {self.queue}  # here\nrunner:\n  agent_type: ccp:delivery-runner\n"
                           "cadence:\n  verify_stale_minutes: 5\n  runner: '*/5 * * * *'\ngrok:\n  model: x\n"
                           "architecture_review:\n  enabled: false\nmystery: 1\n"
                           "auth_check:\n  script: auth.sh\nspec_maintainer:\n  kind: team-lead\n")
        w = res["warnings"]
        for key in ("`durable_docs_path`", "`runner.name`"):
            self.assertIn("lacks", self.named(w, key))
        for key in ("`cadence.verify_stale_minutes`", "`grok`", "`architecture_review`", "`mystery`"):
            self.assertIn("carries", self.named(w, key))
        self.assertEqual(len(w), 6, w)
        self.assertFalse([x for x in w if "auth_check" in x or "spec_maintainer" in x or "`queue_root`" in x])

    def test_a_binding_init_wrote_is_not_warned_about(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.assertIn("binding", res["kept"])
        self.assertNotIn("warnings", res)

    def test_force_rewrites_the_binding_without_a_warning(self):
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.repo}\nqueue_root: {self.queue}\nemail:\n  from: x\n")
        code, res = self.init("--project-id", "demo", "--force")
        self.assertEqual(code, 0, res)
        self.assertNotIn("warnings", res)
        self.assertIn("  name: runner", self.binding.read_text().splitlines())


class PathsAgree(InitCase):
    """§9.2: `ccp where` prints the paths `ccp init` prints, from a linked worktree too, each a real path."""

    def test_init_and_where_from_a_worktree_print_the_same_real_paths(self):
        self.git("remote", "add", "origin", "https://github.com/team/repo.git")
        self.git("commit", "-q", "--allow-empty", "-m", "first")
        wt = self.repo.parent / "wt"
        self.git("worktree", "add", "-q", "--detach", str(wt))
        real_q = self.home / "real" / "q"
        real_q.mkdir(parents=True)
        (self.home / "link").symlink_to(self.home / "real")
        self.bindings.mkdir()
        (self.home / "blink").symlink_to(self.bindings)
        binding = self.bindings / "repo.yaml"
        binding.write_text(f"project_id: repo\nintegration_branch: main\nproduct_root: {self.repo}\n"
                           f"durable_docs_path: docs/delivery/\nqueue_root: {self.home / 'link' / 'q'}\n"
                           "runner:\n  agent_type: ccp:delivery-runner\n  name: runner\n")
        env = {"CCP_BINDINGS_DIR": str(self.home / "blink")}
        r = self.ccp("--root", str(wt), "init", **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        res = json.loads(r.stdout)
        self.assertNotIn("warnings", res)
        r = self.ccp("--root", str(wt), "where", CCP_NO_BINDING_QUEUE="0", **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        where = json.loads(r.stdout)
        want = (str(self.repo), str(binding), str(real_q))
        for out in (res, where):
            self.assertEqual((out["product_root"], out["binding"], out["queue_root"]), want, out)


class KeptIndex(InitCase):
    """§4.5: an existing INDEX.yaml is kept, listed as kept, and the README says so."""

    def test_an_existing_index_is_kept_byte_for_byte_and_listed(self):
        index = self.repo / "docs/delivery/INDEX.yaml"
        index.parent.mkdir(parents=True)
        index.write_text("# an earlier generation's index\ntasks: []\n")
        self.git("add", "docs/delivery/INDEX.yaml")
        self.git("commit", "-q", "-m", "index")
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.assertIn("docs/delivery/INDEX.yaml", res["kept"])
        self.assertNotIn("docs/delivery/INDEX.yaml", res["written"])
        self.assertEqual(index.read_text(), "# an earlier generation's index\ntasks: []\n")

    def test_the_readme_says_an_existing_index_is_kept(self):
        readme = (PLANE / "README.md").read_text()
        start = readme.index("### 2. Adopt a product")
        text = " ".join(readme[start:readme.index("\n#", start + 1)].split())
        self.assertIn("`INDEX.yaml` when there is none (an existing one is kept and listed as kept; "
                      "`ccp tasks index` regenerates it)", text)


class GateInStandingDod(InitCase):
    """§4.5, §21.2: init names `--gate` in the standing DoD it writes; docs check warns on the placeholder."""

    DOD = "docs/delivery/standing-dod.md"

    def docs_check(self) -> str:
        r = self.ccp("docs", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_the_gate_given_replaces_the_placeholder_item(self):
        self.assertEqual(self.init("--project-id", "demo", "--gate", "python3 -m unittest")[0], 0)
        lines = (self.repo / self.DOD).read_text().splitlines()
        self.assertNotIn("7. …", lines)
        self.assertIn("7. **The gate is `python3 -m unittest`**, run by the verifier at the PR head (item 5).", lines)
        self.assertNotIn("placeholder", self.docs_check())

    def test_without_a_gate_the_placeholder_stays_and_docs_check_warns(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.assertIn("7. …", (self.repo / self.DOD).read_text().splitlines())
        warned = [x for x in self.docs_check().splitlines() if "warning:" in x and "placeholder" in x]
        self.assertEqual(len(warned), 1, warned)
        self.assertIn(self.DOD, warned[0])

    def test_a_kept_standing_dod_is_untouched_and_force_writes_the_gate(self):
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        before = (self.repo / self.DOD).read_text()
        code, res = self.init("--project-id", "demo", "--gate", "make test")
        self.assertEqual(code, 0, res)
        self.assertIn(self.DOD, res["kept"])
        self.assertEqual((self.repo / self.DOD).read_text(), before)
        code, res = self.init("--project-id", "demo", "--gate", "make test", "--force")
        self.assertEqual(code, 0, res)
        self.assertIn("7. **The gate is `make test`**, run by the verifier at the PR head (item 5).",
                      (self.repo / self.DOD).read_text().splitlines())


class OriginHost(InitCase):
    def host(self, url):
        self.git("remote", "add", "origin", url)
        try:
            return ccp_init.origin_host(self.repo)
        finally:
            self.git("remote", "remove", "origin")

    def test_the_host_of_each_url_form(self):
        self.assertIsNone(ccp_init.origin_host(self.repo))
        for url, host in (("https://GitHub.com/o/r", "github.com"), ("git@github.com:o/r.git", "github.com"),
                          ("github.com:o/r", "github.com"), ("ssh://git@gitlab.example:2222/o/r", "gitlab.example"),
                          ("/srv/git/r.git", ""), ("../r.git", ""), ("file:///srv/git/r.git", ""),
                          ("notgithub.com:o/r", "notgithub.com")):
            with self.subTest(url=url):
                self.assertEqual(self.host(url), host)
        self.assertIsNone(self.host("https://[::1"))  # does not parse: no host
        self.assertTrue(ccp_init.is_github("ssh.github.com"))
        for host in (None, "", "notgithub.com", "github.com.example"):
            self.assertFalse(ccp_init.is_github(host), host)


class OneBinding(InitCase):
    """§8.3: a binding edit reaches every reader; the queue holds no copy."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        self.binding.write_text(self.binding.read_text().replace("name: runner", "name: steward") + "ci: github-actions\n")

    def test_team_sh_spawns_the_name_in_the_binding(self):
        # the spawn makes the runner worktree from origin/main (SPEC §12.1): the repo needs that ref
        bare = Path(self._d.name) / "origin.git"
        self.git("init", "-q", "--bare", "-b", "main", str(bare))
        self.git("remote", "add", "origin", str(bare))
        self.git("add", ".")
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        self.git("push", "-q", "origin", "HEAD:main")
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
