"""The task-id check of `spec-maintainer-ask.sh` (SPEC §17): the ids are checked against the task directory the
product's config names, with the load's warnings kept off stderr."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import PLANE_ROOT, Product, binding

sys.path.insert(0, str(PLANE_ROOT / "scripts" / "observability"))
from ccp import lib  # noqa: E402
import spec_maintainer as sm  # noqa: E402


class CheckTaskIds(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"DURABLE_DOCS": "/unrelated/path"})
        env.start()
        os.environ.pop("PROJECT_YAML", None)
        self.addCleanup(env.stop)

    def product(self, cfg: dict | None = None) -> Product:
        prod = Product(cfg)
        self.addCleanup(prod.cleanup)
        (self.q / "project.yaml").write_text(binding(product_root=prod.root))
        return prod

    def check(self, ids: list[str]) -> tuple[list[str], str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            return sm.check_task_ids(self.q, ids, "--blocks"), err.getvalue()

    def refused(self, ids: list[str]) -> SystemExit:
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()) as err:
            sm.check_task_ids(self.q, ids, "--blocks")
        self.err = err.getvalue()
        return caught.exception

    def test_a_task_in_the_task_dir_the_config_names_is_accepted_and_an_unknown_one_refused(self):
        prod = self.product({"task_log": {"dir": "notes/log"}})
        (prod.root / "docs/delivery/tasks").rmdir()
        (prod.root / "notes/log/tasks").mkdir(parents=True)
        (prod.root / "notes/log/tasks/0001-a.md").write_text("task\n")
        self.assertEqual(self.check(["0001-a"])[0], ["0001-a"])
        exc = self.refused(["0002-b"])
        self.assertEqual(exc.code, 2)
        self.assertIn("no such task: 0002-b", self.err)
        self.assertIn(str(prod.root / "notes/log/tasks"), self.err)

    def test_a_claimed_task_is_accepted_whatever_the_task_dir_holds(self):
        prod = self.product()
        prod.task("0001-a")
        (self.q / "tasks").mkdir()
        (self.q / "tasks" / "0002-b.json").write_text(json.dumps({"task_id": "0002-b"}))
        self.assertEqual(self.check(["0002-b"])[0], ["0002-b"])

    def test_the_task_dir_in_the_environment_is_not_read(self):
        prod = self.product()
        prod.task("0001-a")
        other = Path(self.q) / "elsewhere"
        other.mkdir()
        (other / "tasks").mkdir()
        (other / "tasks" / "0002-b.md").write_text("task\n")
        with mock.patch.dict(os.environ, {"DURABLE_DOCS": str(other)}):
            self.assertEqual(self.refused(["0002-b"]).code, 2)
            self.assertEqual(self.check(["0001-a"])[0], ["0001-a"])

    def test_no_config_means_no_task_dir_check(self):
        prod = self.product()
        (prod.root / "docs/delivery/plane.json").unlink()
        self.assertEqual(self.check(["0009-z"])[0], ["0009-z"])
        (self.q / "project.yaml").write_text(binding())
        self.assertEqual(self.check(["0009-z"])[0], ["0009-z"])

    def test_an_empty_task_dir_checks_the_shape_alone(self):
        self.product()
        self.assertEqual(self.check(["0009-z"])[0], ["0009-z"])

    def test_a_plane_json_that_makes_the_load_warn_leaves_stderr_empty_no_warning_is_printed(self):
        prod = self.product()
        plane = json.loads((prod.root / "docs/delivery/plane.json").read_text())
        prod.write("docs/delivery/plane.json", json.dumps({**plane, "mystery_key": 1}))
        prod.task("0001-a")
        ids, err = self.check(["0001-a"])
        self.assertEqual(ids, ["0001-a"])
        self.assertEqual(err, "")

    def test_the_spec_maintainer_loads_the_config_through_lib_alone(self):
        self.assertIs(sm.product_config, lib.product_config)
        self.assertIs(sm.product_root, lib.product_root)
        self.assertIs(sm.project_id, lib.project_id)


if __name__ == "__main__":
    unittest.main()
