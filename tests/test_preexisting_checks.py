"""A failure already on the integration branch, in a fixture repo: `ccp docs check` and `ccp tasks check` on a
task branch report it under the pre-existing heading and pass, and still fail on what the branch brings in
(SPEC §21.2)."""
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

from ccp import cli, config, queue
from tests.helpers import Product, binding

RULES = "# Rules\n\n## Words\n\n- **E1** No forbidden word.\n  check: command\n"
GREP = "! git grep -nE 'FORBID[D]EN' -- ."
HEADING = "pre-existing on main at"


class Repo:
    """A Product made a git repository on `main`, with `origin/main` at its tip."""

    def make(self, cfg: dict) -> Product:
        p = Product(cfg)
        self.addCleanup(p.cleanup)
        self.p = p
        p.write("docs/ENGINEERING.md", RULES)
        p.write("app/clean.md", "fine\n")
        p.task("0001-a")
        p.index()
        self.git("init", "-q", "-b", "main")
        self.commit("start")
        return p

    def git(self, *args: str) -> str:
        r = subprocess.run(["git", "-C", str(self.p.root), "-c", "user.name=t", "-c", "user.email=t@example.com",
                            *args], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def commit(self, msg: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def publish(self) -> None:
        self.git("update-ref", "refs/remotes/origin/main", "main")

    def ccp(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), *args])
        self.assertEqual(self.git("worktree", "list", "--porcelain").count("worktree "), 1)
        return code, out.getvalue()

    def preexisting(self, out: str) -> list[str]:
        """The lines under the heading."""
        lines = out.splitlines()
        at = next((i for i, ln in enumerate(lines) if ln.strip().startswith(HEADING)), None)
        return [] if at is None else [ln.strip() for ln in lines[at + 1:] if ln.startswith("    ")]


class DocsCheck(Repo, unittest.TestCase):
    def setUp(self):
        self.make({"architect": {"rules_doc": "docs/ENGINEERING.md", "checks": [{"id": "E1", "cmd": GREP}]}})
        self.p.write("app/old.md", "FORBIDDEN\n")
        self.commit("a hit on main")
        self.publish()

    def test_a_hit_on_main_in_a_file_the_branch_does_not_touch_passes_under_the_heading(self):
        self.git("checkout", "-q", "-b", "task")
        self.p.write("app/other.md", "mine\n")
        self.commit("work")
        code, out = self.ccp("docs", "check")
        self.assertEqual(code, 0, out)
        self.assertEqual([ln.split(":")[0] for ln in self.preexisting(out)], ["check E1"])

    def test_a_hit_the_branch_adds_in_a_file_it_changes_fails(self):
        self.git("checkout", "-q", "-b", "task")
        self.p.write("app/other.md", "FORBIDDEN too\n")
        self.commit("work")
        code, out = self.ccp("docs", "check")
        self.assertEqual(code, 1)
        self.assertEqual(self.preexisting(out), [])

    def test_a_branch_adding_a_non_ascii_file_to_the_checker_leaves_the_hit_failing(self):
        self.git("config", "core.quotepath", "true")
        self.p.write("ccp/__init__.py", "")
        self.commit("the repository holds its ccp")
        self.publish()
        self.git("checkout", "-q", "-b", "task")
        self.p.write("ccp/caf\u00e9.py", "")
        self.commit("work")
        code, out = self.ccp("docs", "check")
        self.assertEqual(code, 1)
        self.assertEqual(self.preexisting(out), [])

    def test_on_the_integration_branch_itself_the_hit_fails(self):
        code, out = self.ccp("docs", "check")
        self.assertEqual(code, 1)
        self.assertNotIn(HEADING, out)


class BaseRun(Repo, unittest.TestCase):
    def test_the_base_run_reads_the_bases_config_and_sees_no_queue(self):
        marks = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(marks)]))
        env_check = {"id": "env", "cmd": f'echo "${{QUEUE_ROOT:-unset}}" >> {marks}/queue; exit 1'}
        p = self.make({"docs": {"checks": [env_check]}})
        self.publish()
        self.git("checkout", "-q", "-b", "task")
        added = {"id": "added", "cmd": f"echo ran >> {marks}/added; exit 1"}
        plane = json.loads((p.root / config.CONFIG_REL).read_text())
        plane["docs"]["checks"].append(added)
        p.write(config.CONFIG_REL, json.dumps(plane))
        self.commit("add a check")
        q = Path(tempfile.mkdtemp())
        self.addCleanup(q.rmdir)
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(q)}):
            self.assertEqual(self.ccp("docs", "check")[0], 1)
        self.assertEqual((marks / "added").read_text().split(), ["ran"])
        self.assertEqual((marks / "queue").read_text().split(), [str(q), "unset"])

    def echoed(self, var: str, bindings: Path, env: dict, queue_root: Path | None = None) -> list[str]:
        """What a docs check that echoes `$<var>` and fails saw at `HEAD` and then at the base, on a task
        branch, with the running `ccp`'s bindings directory `bindings`, `env` over the environment, and,
        with `queue_root`, the product's binding there naming that queue."""
        marks = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(marks)]))
        echo = {"id": "echo", "cmd": f'echo "${{{var}:-unset}}" >> {marks}/seen; exit 1'}
        p = self.make({"docs": {"checks": [echo]}})
        if queue_root is not None:
            (bindings / "demo.yaml").write_text(binding(product_root=p.root, queue_root=queue_root))
        self.publish()
        self.git("checkout", "-q", "-b", "task")
        p.write("app/other.md", "mine\n")
        self.commit("work")
        with mock.patch.object(queue.lib, "bindings_dir", return_value=bindings), \
                mock.patch.dict(os.environ, env):
            self.assertEqual(self.ccp("docs", "check")[0], 1)
        return (marks / "seen").read_text().split()

    def test_the_base_run_gets_the_bindings_directory_the_head_run_resolved(self):
        bindings = Path(tempfile.mkdtemp())
        self.addCleanup(bindings.rmdir)
        self.assertNotEqual(os.environ["CCP_BINDINGS_DIR"], str(bindings))
        self.assertEqual(self.echoed("CCP_BINDINGS_DIR", bindings, {}),
                         [os.environ["CCP_BINDINGS_DIR"], str(bindings)])

    def test_the_base_run_takes_no_queue_from_the_products_binding(self):
        bindings, q = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(bindings), str(q)]))
        seen = self.echoed("QUEUE_ROOT", bindings, {"CCP_NO_BINDING_QUEUE": ""}, q)
        self.assertEqual(seen, [str(q), "unset"])

    def test_a_leak_style_list_outside_git_is_read_at_both_through_the_bindings_dir(self):
        bindings = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(bindings)]))
        (bindings / "deny.txt").write_text("SECRETWORD\n")
        leaks = {"id": "leaks", "cmd": '! git grep -n -f "$CCP_BINDINGS_DIR/deny.txt" -- .'}
        p = self.make({"docs": {"checks": [leaks]}})
        p.write("app/old.md", "a SECRETWORD here\n")
        self.commit("a hit on main")
        self.publish()
        self.git("checkout", "-q", "-b", "task")
        p.write("app/other.md", "mine\n")
        self.commit("work")
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(bindings)}):
            code, out = self.ccp("docs", "check")
        self.assertEqual(code, 0, out)
        self.assertEqual([ln.split(":")[0] for ln in self.preexisting(out)], ["docs check leaks"])


class TasksCheck(Repo, unittest.TestCase):
    def setUp(self):
        self.make({})
        self.git("checkout", "-q", "-b", "task")
        self.p.write("app/other.md", "mine\n")
        self.commit("work")
        self.git("checkout", "-q", "main")
        self.p.task("0002-b", deps=["0009-missing"])
        self.p.index()
        self.commit("a broken task on main")
        self.publish()
        self.git("checkout", "-q", "task")
        self.git("merge", "-q", "--no-edit", "main")

    def test_tasks_check_passes_on_a_task_file_failure_merged_from_main(self):
        code, out = self.ccp("tasks", "check")
        self.assertEqual(code, 0, out)
        self.assertEqual([ln.split(":")[0] for ln in self.preexisting(out)], ["docs/delivery/tasks/0002-b.md"])

    def test_tasks_check_fails_on_a_task_file_the_branch_adds(self):
        self.p.task("0003-c", deps=["0008-missing"])
        self.p.index()
        self.commit("my broken task")
        code, out = self.ccp("tasks", "check")
        self.assertEqual(code, 1)
        self.assertIn("0003-c.md", out.split(HEADING)[0])


if __name__ == "__main__":
    unittest.main()
