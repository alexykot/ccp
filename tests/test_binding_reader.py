"""The one reader of a product's binding (SPEC §8.3): its parser and its two resolutions."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp.queue import PLANE, lib
from tests.binding_reader_fixture import BindingDir

BINDING = """\
# a comment line, then the scalars
project_id: demo
product_root: '/work/demo'   # quoted, with a trailing comment
queue_root: /work/queue
integration_branch: "main"
runner:
  name: steward
  # an indented comment: not a key
  worktree: /work/demo-runner
  agent_type:
seats:
  lead: opus
ci: github-actions
spec_maintainer:
auth_check:
  script: auth.sh
  extra:
    deep: value
sizes:
  - small
  - large
"""


class ReadBindingTest(unittest.TestCase):
    def test_scalars_are_strings_without_quotes_and_comments(self):
        d = lib.read_binding(BINDING)
        self.assertEqual(d["project_id"], "demo")
        self.assertEqual(d["product_root"], "/work/demo")
        self.assertEqual(d["integration_branch"], "main")
        self.assertEqual(d["ci"], "github-actions")

    def test_a_block_is_a_dict_by_indentation(self):
        d = lib.read_binding(BINDING)
        self.assertEqual(d["runner"]["name"], "steward")
        self.assertEqual(d["runner"]["worktree"], "/work/demo-runner")
        self.assertEqual(d["auth_check"]["extra"], {"deep": "value"})

    def test_a_key_with_no_value_is_an_empty_block(self):
        d = lib.read_binding(BINDING)
        self.assertEqual(d["spec_maintainer"], {})
        self.assertEqual(d["runner"]["agent_type"], {})

    def test_comments_and_list_items_are_not_keys(self):
        d = lib.read_binding(BINDING)
        self.assertEqual(d["sizes"], {})
        self.assertNotIn("an indented comment", d["runner"])
        self.assertEqual(list(d), ["project_id", "product_root", "queue_root", "integration_branch", "runner",
                                   "seats", "ci", "spec_maintainer", "auth_check", "sizes"])

    def test_binding_str_reads_a_path_and_refuses_a_block_or_a_gap(self):
        d = lib.read_binding(BINDING)
        self.assertEqual(lib.binding_str(d, "runner", "name"), "steward")
        self.assertIsNone(lib.binding_str(d, "runner"))
        self.assertIsNone(lib.binding_str(d, "spec_maintainer"))
        self.assertIsNone(lib.binding_str(d, "runner", "missing"))
        self.assertIsNone(lib.binding_str(d, "queue_root", "deeper"))

    def test_block_scalars_keep_the_strings_directly_under_the_block(self):
        self.assertEqual(lib._yaml_block_scalars(BINDING, "auth_check"), {"script": "auth.sh"})
        self.assertEqual(lib._yaml_block_scalars(BINDING, "seats"), {"lead": "opus"})
        self.assertEqual(lib._yaml_block_scalars(BINDING, "nope"), {})


class BindingEntryPointTest(unittest.TestCase):
    """`lib.py binding <file>`: what the release script reads a binding through."""

    def run_entry(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(PLANE / "ccp/lib.py"), *args],
                              capture_output=True, text=True)

    def test_it_prints_the_top_level_scalars_as_json(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "demo.yaml"
            f.write_text(BINDING)
            r = self.run_entry("binding", str(f))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), {"project_id": "demo", "product_root": "/work/demo",
                                                "queue_root": "/work/queue", "integration_branch": "main",
                                                "ci": "github-actions"})

    def test_it_refuses_a_missing_file_and_a_wrong_call(self):
        self.assertEqual(self.run_entry("binding", "/nonexistent/x.yaml").returncode, 1)
        self.assertEqual(self.run_entry().returncode, 2)
        self.assertEqual(self.run_entry("other", "x").returncode, 2)


class ResolutionTest(BindingDir):
    def test_by_queue_finds_the_binding_naming_the_queue(self):
        self.assertEqual(lib.binding_path(self.queue), self.binding)
        self.assertEqual(lib.binding_str(lib.binding_data(self.queue), "integration_branch"), "steward")
        self.assertEqual(lib.binding_str(lib.binding_data(self.queue), "product_root"), str(self.product))

    def test_by_queue_falls_back_to_the_retired_queue_copy_only_without_a_binding(self):
        other = Path(self._d.name) / "legacy"
        other.mkdir()
        self.assertIsNone(lib.binding_path(other))
        self.assertEqual(lib.binding_data(other), {})
        (other / "project.yaml").write_text("integration_branch: old\n")
        self.assertEqual(lib.binding_path(other), other / "project.yaml")
        self.assertEqual(lib.binding_str(lib.binding_data(other), "integration_branch"), "old")

    def test_by_queue_prefers_an_explicit_project_yaml(self):
        explicit = Path(self._d.name) / "explicit.yaml"
        explicit.write_text("integration_branch: chosen\n")
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(explicit)}):
            self.assertEqual(lib.binding_path(self.queue), explicit)
            self.assertEqual(lib.binding_str(lib.binding_data(self.queue), "integration_branch"), "chosen")

    def test_by_product_finds_the_binding_when_the_product_root_is_among_the_roots(self):
        self.assertEqual(lib.product_binding("demo", (self.product,)), self.binding)
        self.assertEqual(lib.product_binding("demo", (Path("/elsewhere"), self.product)), self.binding)

    def test_by_product_gives_a_clone_naming_the_id_nothing(self):
        self.assertIsNone(lib.product_binding("demo", (Path(self._d.name) / "scratch-clone",)))
        self.assertIsNone(lib.product_binding("other", (self.product,)))

    def test_by_product_takes_an_explicit_binding_ahead_of_the_directory_one(self):
        explicit = Path(self._d.name) / "sandbox.yaml"
        explicit.write_text(f"product_root: {self.product}\n")
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(explicit)}):
            self.assertEqual(lib.product_binding("demo", (self.product,)), explicit)
            # an explicit file naming another product falls through to the directory's
            explicit.write_text("product_root: /somewhere/else\n")
            self.assertEqual(lib.product_binding("demo", (self.product,)), self.binding)


class ReadersTest(BindingDir):
    """The modules that read a binding's keys, each through the one parser."""

    def setUp(self):
        super().setUp()
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}   # the checkout\n"
                                f"queue_root: '{self.queue}'\nintegration_branch: dev\n")

    def test_the_integration_branch_is_the_bindings_else_main(self):
        from ccp import queue  # noqa: PLC0415
        self.assertEqual(queue.integration_branch(self.queue), "dev")
        self.binding.write_text(f"queue_root: {self.queue}\n")
        self.assertEqual(queue.integration_branch(self.queue), "main")

    def test_the_same_change_judge_asks_in_the_bindings_product_root_and_branch(self):
        from ccp import runs  # noqa: PLC0415
        with mock.patch("ccp.runs._same_patch", return_value=True) as same:
            self.assertTrue(runs.same_change(self.queue, "aaa", "bbb"))
        self.assertEqual(same.call_args.args[1:], (str(self.product), "aaa", "bbb", "dev"))
        self.binding.write_text(f"queue_root: {self.queue}\n")
        self.assertFalse(runs.same_change(self.queue, "aaa", "bbb"))

    def test_the_receiver_reads_the_binding_for_queue_roots_and_env(self):
        from ccp import otel  # noqa: PLC0415
        self.assertEqual(otel.queue_for("demo", {}), self.queue)
        self.assertEqual(otel.bindings(), [("demo", os.path.realpath(self.product), self.queue)])
        (self.bindings / "file-name.yaml").write_text(f"project_id: named-id\nproduct_root: {self.product}\n"
                                                      f"queue_root: {self.queue}\n")
        self.assertEqual([b[0] for b in otel.bindings()], ["demo", "named-id"])
        self.assertEqual(otel.env_for_project("demo", 4318)["project"]["path"],
                         f"{self.product}/.claude/settings.json")

    def test_the_product_queue_root_is_the_bindings_when_it_is_a_directory(self):
        from types import SimpleNamespace  # noqa: PLC0415
        from ccp import cli  # noqa: PLC0415
        cfg = SimpleNamespace(project_id="demo", root=self.product)
        with mock.patch("ccp.prompt.main_checkout", return_value=self.product):
            self.assertEqual(cli.product_queue_root(cfg), str(self.queue))
            self.assertEqual(cli.product_binding(cfg), self.binding)
            self.assertIsNone(cli.product_binding(SimpleNamespace(project_id="Demo", root=self.product)))
            self.binding.write_text(f"product_root: {self.product}\nqueue_root: {self.queue}/missing\n")
            self.assertIsNone(cli.product_queue_root(cfg))

    def test_the_spec_maintainer_reads_the_project_id_and_product_root(self):
        sys.path.insert(0, str(PLANE / "scripts" / "observability"))
        import spec_maintainer as sm  # noqa: PLC0415
        with mock.patch.dict(os.environ, {"PROJECT_ID": ""}):
            self.assertEqual(sm.project_id(self.queue), "demo")
        self.assertEqual(sm.product_root(self.queue), str(self.product))
        other = Path(self._d.name) / "none"
        self.assertEqual(sm.product_root(other), "")

    def write_plane(self, text: str) -> None:
        (self.product / "docs/delivery").mkdir(parents=True, exist_ok=True)
        (self.product / "docs/delivery/plane.json").write_text(text)

    def test_the_product_config_is_the_loaded_plane_json_at_the_bindings_product_root(self):
        self.write_plane('{"project_id": "demo", "task_log": {"dir": "notes/log"}}')
        cfg = lib.product_config(self.queue)
        self.assertEqual(cfg.root, self.product)
        self.assertEqual(cfg.tasks_dir, self.product / "notes/log/tasks")
        self.write_plane('{"project_id": "demo"}')
        self.assertEqual(lib.product_config(self.queue).tasks_dir, self.product / "docs/delivery/tasks")

    def test_the_product_config_is_none_with_no_product_root_or_no_plane_json(self):
        self.assertIsNone(lib.product_config(self.queue))  # the product has no plane.json
        self.assertIsNone(lib.product_config(self.queue, strict=True))  # a missing file is not a load error
        self.write_plane('{"project_id": "demo"}')
        self.binding.write_text(f"queue_root: {self.queue}\n")
        self.assertIsNone(lib.product_config(self.queue))
        self.assertIsNone(lib.product_config(self.queue, strict=True))

    def test_a_plane_json_that_does_not_load_is_none_unless_strict_which_raises_its_error(self):
        self.write_plane("{not json")
        self.assertIsNone(lib.product_config(self.queue))
        with self.assertRaises(Exception) as caught:
            lib.product_config(self.queue, strict=True)
        self.assertIn("plane.json", str(caught.exception))

    def test_the_product_config_load_prints_nothing_and_leaves_the_warning_to_a_later_load(self):
        from ccp import config  # noqa: PLC0415
        self.write_plane('{"project_id": "demo", "mystery_key": 1}')
        err = io.StringIO()
        with mock.patch.object(config, "_WARNED", set()), contextlib.redirect_stderr(err):
            self.assertIsNotNone(lib.product_config(self.queue))
            self.assertEqual(err.getvalue(), "")
            config.load(self.product)
        self.assertIn("mystery_key", err.getvalue())


class SyncReaderTest(unittest.TestCase):
    """`scripts/sync-product-docs.sh` reads the binding through the same parser."""

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.product = Path(self._d.name).resolve() / "product"
        self.product.mkdir()
        self.yml = Path(self._d.name) / "demo.yaml"

    def sync(self, binding: str) -> subprocess.CompletedProcess:
        self.yml.write_text(f"project_id: demo\nproduct_root: {self.product}\n" + binding)
        return subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo",
                               "--project-yaml", str(self.yml), "--check"], capture_output=True, text=True)

    def test_a_product_that_has_the_maintainer_doc_copy_has_it_reported(self):
        (self.product / "docs" / "delivery").mkdir(parents=True)
        (self.product / "docs" / "delivery" / "SPEC-MAINTAINER.md").write_text(
            "> Managed copy of control-plane `plugin/skills/spec-maintainer/SKILL.md` at abc1234. Edit.\n")
        r = self.sync("")
        self.assertIn("DRIFT docs/delivery/SPEC-MAINTAINER.md: retired", r.stdout, r.stderr)

    def test_without_the_doc_there_is_no_such_copy_whatever_the_binding_holds(self):
        r = self.sync("spec_maintainer:\n  kind: team-lead\n")
        self.assertNotIn("docs/delivery/SPEC-MAINTAINER.md", r.stdout, r.stderr)

    def test_a_binding_for_another_project_id_is_refused(self):
        self.yml.write_text(f"project_id: other\nproduct_root: {self.product}\n")
        r = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo",
                            "--project-yaml", str(self.yml), "--check"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is project_id other, not demo", r.stderr)

    def test_without_a_project_yaml_the_binding_is_found_in_the_bindings_directory(self):
        self.yml.write_text(f"project_id: demo\nproduct_root: {self.product}\n")
        (self.product / "docs" / "delivery").mkdir(parents=True)
        (self.product / "docs" / "delivery" / "CONTROL-PLANE.md").write_text(
            "> Managed copy of control-plane `plugin/orientation.md` at abc1234. Edit.\n")
        env = {**os.environ, "CCP_BINDINGS_DIR": self._d.name}
        r = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo", "--check"],
                           capture_output=True, text=True, env=env)
        self.assertNotIn("no project binding", r.stderr)
        self.assertIn("DRIFT docs/delivery/CONTROL-PLANE.md: retired", r.stdout, r.stderr)
        self.assertEqual(r.returncode, 1, r.stderr)


if __name__ == "__main__":
    unittest.main()
