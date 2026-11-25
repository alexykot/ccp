"""SPEC §8.3: a binding is found by its project id through one resolver, `lib.binding_for_id`, which honours
`PROJECT_YAML` as the queue's resolver does; `ccp otel` and `scripts/sync-product-docs.sh` read it that way."""
from __future__ import annotations

import io
import json
import os
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from ccp.queue import lib
from tests.binding_reader_fixture import BindingDir
from tests.helpers import PLANE_ROOT


class BindingById(BindingDir):
    def sandbox(self, project_id: str = "demo", product: Path | None = None) -> Path:
        """A binding outside the bindings directory, as a sandbox keeps it."""
        root = product or Path(self._d.name) / "sandbox-product"
        root.mkdir(exist_ok=True)
        yml = Path(self._d.name) / f"sandbox-{project_id}.yaml"
        yml.write_text(f"project_id: {project_id}\nproduct_root: {root}\n")
        return yml

    def test_project_yaml_naming_the_ids_binding_wins(self):
        yml = self.sandbox()
        self.assertEqual(lib.binding_for_id("demo"), self.binding)
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(yml)}):
            self.assertEqual(lib.binding_for_id("demo"), yml)

    def test_the_bindings_directory_defaults_to_projects_beside_the_plane_code(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("CCP_BINDINGS_DIR", None)
            self.assertEqual(lib.bindings_dir(), PLANE_ROOT / "projects")

    def test_project_yaml_naming_another_id_falls_back(self):
        yml = self.sandbox("other")
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(yml)}):
            self.assertEqual(lib.binding_for_id("demo"), self.binding)
            self.assertEqual(lib.binding_for_id("other"), yml)
            self.assertIsNone(lib.binding_for_id("missing"))
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(Path(self._d.name) / "no-such-file.yaml")}):
            self.assertEqual(lib.binding_for_id("demo"), self.binding)

    def test_otel_env_reads_the_binding_project_yaml_names(self):
        yml = self.sandbox()
        sandbox_root = Path(self._d.name) / "sandbox-product"
        with mock.patch.dict(os.environ, {"PROJECT_YAML": str(yml)}):
            for argv in (["otel", "env", "--project", "demo", "--port", "4318"], ["otel", "env", "--off", "--project", "demo"]):
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(argv), 0)
                self.assertEqual(json.loads(out.getvalue())["project"]["path"], f"{sandbox_root}/.claude/settings.json")

    def test_sync_reads_the_binding_project_yaml_names(self):
        yml = self.sandbox()
        sandbox_root = Path(self._d.name) / "sandbox-product"
        (sandbox_root / "docs" / "delivery").mkdir(parents=True)
        (sandbox_root / "docs" / "delivery" / "SPEC-MAINTAINER.md").write_text(
            "> Managed copy of control-plane `plugin/skills/spec-maintainer/SKILL.md` at abc1234. Edit.\n")
        script = PLANE_ROOT / "scripts" / "sync-product-docs.sh"
        env = {**os.environ, "CCP_BINDINGS_DIR": str(self.bindings)}
        env.pop("PROJECT_YAML", None)
        theirs = subprocess.run(["bash", str(script), "demo", "--check"], capture_output=True, text=True, env=env)
        self.assertNotIn("docs/delivery/SPEC-MAINTAINER.md", theirs.stdout, theirs.stderr)
        mine = subprocess.run(["bash", str(script), "demo", "--check"], capture_output=True, text=True,
                              env={**env, "PROJECT_YAML": str(yml)})
        self.assertIn("SPEC-MAINTAINER.md: retired", mine.stdout, mine.stderr)

    def test_sync_refuses_a_project_with_no_binding(self):
        env = {**os.environ, "CCP_BINDINGS_DIR": str(self.bindings)}
        env.pop("PROJECT_YAML", None)
        r = subprocess.run(["bash", str(PLANE_ROOT / "scripts" / "sync-product-docs.sh"), "no-binding", "--check"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("no-binding", r.stderr)


if __name__ == "__main__":
    unittest.main()
