"""SPEC §29.3, §8.3: `ccp sandbox create` makes a throwaway adopted product whose binding and queue sit
inside it, never in the installation's bindings directory; `ccp sandbox remove` deletes only a sandbox.
Every sandbox is made below the test fence's root (`CCP_SANDBOX_ROOT`, tests/__init__.py)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLANE = Path(__file__).resolve().parents[1]
CCP = PLANE / "bin" / "ccp"
MARKER = ".ccp-sandbox"


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.fence = Path(os.environ["CCP_SANDBOX_ROOT"]).resolve()
        self.base = Path(tempfile.mkdtemp(dir=self.fence)).resolve()
        self._out = tempfile.TemporaryDirectory()  # outside the fence's root
        self.installation = Path(self._out.name).resolve() / "projects"
        self.installation.mkdir()
        (self.installation / "live.yaml").write_text("project_id: live\nqueue_root: /nonexistent/live-queue\n")
        self.env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        self.env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        CCP_BINDINGS_DIR=str(self.installation))

    def tearDown(self):
        self._out.cleanup()
        shutil.rmtree(self.base, ignore_errors=True)

    def ccp(self, *args, cwd=None, **env):
        return subprocess.run([str(CCP), *args], cwd=cwd or self.base, capture_output=True, text=True,
                              env={**self.env, **env})

    def create(self, *args):
        r = self.ccp("sandbox", "create", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def git(self, root, *args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=True,
                              env=self.env).stdout

    def listing(self):
        return {p.name: p.read_text() for p in self.installation.iterdir()}


class Create(SandboxCase):
    def test_an_adopted_product_in_one_command(self):
        s = self.base / "S"
        before = self.listing()
        res = self.create(str(s))
        self.assertEqual(set(res), {"root", "binding", "queue_root", "env"})
        for key in ("root", "binding", "queue_root"):
            self.assertIn(s, Path(res[key]).parents, key)
        self.assertTrue((Path(res["root"]) / "docs/delivery/plane.json").is_file())
        self.assertTrue(Path(res["binding"]).is_file())
        self.assertTrue(Path(res["queue_root"]).is_dir())
        self.assertEqual(self.listing(), before)  # the installation's bindings are untouched
        env = dict(line.split("=", 1) for line in res["env"])
        self.assertEqual(env, {"PROJECT_YAML": res["binding"], "QUEUE_ROOT": res["queue_root"]})
        for cmd in (("tasks", "check"), ("upgrade", "status")):
            r = self.ccp(*cmd, cwd=res["root"], **env)
            self.assertEqual(r.returncode, 0, (cmd, r.stderr))
        where = json.loads(self.ccp("where", cwd=res["root"], **env).stdout)
        self.assertEqual(where["binding"], res["binding"])

    def test_what_init_wrote_is_committed_after_one_first_commit(self):
        res = self.create(str(self.base / "S"))
        self.assertEqual(len(self.git(res["root"], "log", "--format=%H").split()), 2)
        self.assertEqual(self.git(res["root"], "status", "--porcelain"), "")
        self.assertIn("docs/delivery/plane.json", self.git(res["root"], "ls-files").split())
        self.assertTrue((self.base / "S" / MARKER).is_file())

    def test_init_options_pass_through(self):
        res = self.create(str(self.base / "U"), "--", "--gate", "python3 -m unittest")
        cfg = json.loads((Path(res["root"]) / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"]["lanes"]["gate"], ["python3", "-m", "unittest"])

    def test_without_a_directory_it_makes_a_new_one_below_the_fence(self):
        res = self.create()
        d = Path(res["root"]).parent
        self.assertIn(self.fence, d.parents)
        self.assertTrue((d / MARKER).is_file())

    def test_an_empty_directory_is_used(self):
        (self.base / "E").mkdir()
        res = self.create(str(self.base / "E"))
        self.assertEqual(Path(res["root"]).parent, self.base / "E")


class Refusals(SandboxCase):
    def test_outside_the_fence_nothing_is_made(self):
        out = Path(self._out.name).resolve() / "S"
        r = self.ccp("sandbox", "create", str(out))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(out.exists())

    def test_a_directory_with_content_is_refused(self):
        d = self.base / "N"
        d.mkdir()
        (d / "keep.txt").write_text("x")
        r = self.ccp("sandbox", "create", str(d))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual([p.name for p in d.iterdir()], ["keep.txt"])

    def test_init_options_that_would_move_the_queue_or_adopt_nothing_are_refused(self):
        for opt in ("--queue-root", "--queue-root=/tmp/q", "--permissions", "--rules-doc", "--adopt", "--root"):
            with self.subTest(opt):
                d = self.base / "R"
                r = self.ccp("sandbox", "create", str(d), "--", opt, *([] if "=" in opt else ["x"]))
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertFalse(d.exists())

    def test_a_failed_init_leaves_nothing(self):
        for made in (False, True):
            with self.subTest(existing_empty_dir=made):
                d = self.base / f"F{int(made)}"
                if made:
                    d.mkdir()
                r = self.ccp("sandbox", "create", str(d), "--", "--project-id", "Not_An_Id")
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn("ccp init", r.stderr)
                self.assertEqual(list(d.iterdir()) if made else d.exists(), [] if made else False)
        self.assertEqual(self.listing(), {"live.yaml": "project_id: live\nqueue_root: /nonexistent/live-queue\n"})


class Remove(SandboxCase):
    def test_remove_deletes_a_sandbox_and_refuses_any_other_directory(self):
        s = self.base / "S"
        self.create(str(s))
        t = self.base / "T"
        t.mkdir()
        (t / "keep.txt").write_text("x")
        r = self.ccp("sandbox", "remove", str(t))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertTrue((t / "keep.txt").is_file())
        r = self.ccp("sandbox", "remove", str(s))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(s.exists())

    def test_a_link_to_a_sandbox_or_to_a_marker_is_refused(self):
        s = self.base / "S"
        self.create(str(s))
        link = self.base / "L"
        link.symlink_to(s)
        fake = self.base / "M"
        fake.mkdir()
        (fake / MARKER).symlink_to(s / MARKER)
        for d in (link, fake):
            with self.subTest(d.name):
                r = self.ccp("sandbox", "remove", str(d))
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertTrue(d.exists())
        self.assertTrue((s / MARKER).is_file())

    def test_remove_needs_a_directory_and_no_init_options(self):
        s = self.base / "S"
        self.create(str(s))
        for args in (("sandbox", "remove"), ("sandbox", "remove", str(s), "--", "--force")):
            with self.subTest(args):
                self.assertEqual(self.ccp(*args).returncode, 2)
        self.assertTrue(s.exists())


if __name__ == "__main__":
    unittest.main()
