"""The one reader of a product's binding (SPEC §8.3): its parser and its two resolutions."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp.queue import PLANE, lib

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


class ResolutionTest(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        base = Path(self._d.name).resolve()
        self.bindings = base / "bindings"
        self.bindings.mkdir()
        self.queue = base / "queue"
        self.queue.mkdir()
        self.product = base / "product"
        self.product.mkdir()
        self.binding = self.bindings / "demo.yaml"
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}\nqueue_root: {self.queue}\n"
                                "runner:\n  name: steward\n")
        env = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings)})
        env.start()
        self.addCleanup(env.stop)
        for k in ("PROJECT_YAML", "PLANE_PROJECT_YAML"):
            os.environ.pop(k, None)

    def test_by_queue_finds_the_binding_naming_the_queue(self):
        self.assertEqual(lib.binding_path(self.queue), self.binding)
        self.assertEqual(lib.binding_runner_name(self.queue), "steward")
        self.assertEqual(lib.binding_str(lib.binding_data(self.queue), "product_root"), str(self.product))

    def test_by_queue_falls_back_to_the_retired_queue_copy_only_without_a_binding(self):
        other = Path(self._d.name) / "legacy"
        other.mkdir()
        self.assertIsNone(lib.binding_path(other))
        self.assertEqual(lib.binding_data(other), {})
        (other / "project.yaml").write_text("runner:\n  name: old\n")
        self.assertEqual(lib.binding_path(other), other / "project.yaml")
        self.assertEqual(lib.binding_runner_name(other), "old")

    def test_by_queue_prefers_an_explicit_project_yaml(self):
        explicit = Path(self._d.name) / "explicit.yaml"
        explicit.write_text("runner:\n  name: chosen\n")
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(explicit)}):
            self.assertEqual(lib.binding_path(self.queue), explicit)
            self.assertEqual(lib.binding_runner_name(self.queue), "chosen")

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

    def test_a_spec_maintainer_block_adds_its_managed_copy(self):
        r = self.sync("spec_maintainer:\n  kind: team-lead\n")
        self.assertIn("docs/delivery/SPEC-MAINTAINER.md", r.stdout, r.stderr)
        self.assertNotIn("claude-session", r.stdout)

    def test_an_empty_spec_maintainer_block_counts_as_declared(self):
        self.assertIn("docs/delivery/SPEC-MAINTAINER.md", self.sync("spec_maintainer:\n").stdout)

    def test_without_the_block_there_is_no_such_copy(self):
        self.assertNotIn("docs/delivery/SPEC-MAINTAINER.md", self.sync("runner:\n  name: r\n").stdout)

    def test_the_removed_claude_session_kind_gets_a_note(self):
        r = self.sync("spec_maintainer:\n  kind: claude-session   # old\n")
        self.assertIn("spec_maintainer.kind claude-session was removed", r.stdout, r.stderr)

    def test_a_binding_for_another_project_id_is_refused(self):
        self.yml.write_text(f"project_id: other\nproduct_root: {self.product}\n")
        r = subprocess.run(["bash", str(PLANE / "scripts" / "sync-product-docs.sh"), "demo",
                            "--project-yaml", str(self.yml), "--check"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is project_id other, not demo", r.stderr)


if __name__ == "__main__":
    unittest.main()
