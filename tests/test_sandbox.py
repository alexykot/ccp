"""SPEC §29.3, §8.3: `ccp sandbox create` makes a throwaway adopted product whose binding and queue sit
inside it, never in the installation's bindings directory; `ccp sandbox remove` deletes only a sandbox.
Every sandbox is made below the test fence's root (`CCP_SANDBOX_ROOT`, tests/__init__.py)."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLANE = Path(__file__).resolve().parents[1]
CCP = PLANE / "bin" / "ccp"
MARKER = ".ccp-sandbox"
PRODUCT = "product"


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

    def plain(self, name="P"):
        """A product adopted with `ccp init` outside every sandbox: its binding in the stand-in installation,
        its queue beside it. Returns the product root and its queue."""
        root, q = Path(self._out.name).resolve() / name, Path(self._out.name).resolve() / f"{name}-queue"
        root.mkdir()
        self.git(str(root), "init", "-q")
        self.git(str(root), "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "commit.gpgsign=false",
                 "commit", "-q", "--allow-empty", "-m", "first")
        r = self.ccp("--root", str(root), "init", "--project-id", name.lower(), "--queue-root", str(q))
        self.assertEqual(r.returncode, 0, r.stderr)
        return root, q


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

    def test_project_yaml_alone_names_the_binding_and_its_queue(self):
        res = self.create(str(self.base / "S"))
        where = json.loads(self.ccp("where", cwd=res["root"], PROJECT_YAML=res["binding"]).stdout)
        self.assertEqual(where["binding"], res["binding"])
        where = json.loads(self.ccp("where", cwd=res["root"], PROJECT_YAML=res["binding"],
                                    CCP_NO_BINDING_QUEUE="").stdout)
        self.assertEqual((where["binding"], where["queue_root"]), (res["binding"], res["queue_root"]))

    def test_project_yaml_naming_another_products_binding_is_not_taken(self):
        a = self.create(str(self.base / "A"))
        root, _ = self.plain()
        (self.installation / "p.yaml").unlink()  # its own binding is not where ccp looks either
        where = json.loads(self.ccp("where", cwd=root, PROJECT_YAML=a["binding"], CCP_NO_BINDING_QUEUE="").stdout)
        self.assertEqual((where["binding"], where["queue_root"]), (None, None))

    def test_project_yaml_naming_another_sandboxs_binding_is_refused(self):
        a, b = self.create(str(self.base / "A")), self.create(str(self.base / "B"))
        r = self.ccp("where", cwd=b["root"], PROJECT_YAML=a["binding"], CCP_NO_BINDING_QUEUE="")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertIn("PROJECT_YAML", r.stderr)
        self.assertIn(str(self.base / "B"), r.stderr)

    def test_what_init_wrote_is_committed_after_one_first_commit(self):
        res = self.create(str(self.base / "S"))
        self.assertEqual(len(self.git(res["root"], "log", "--format=%H").split()), 2)
        self.assertEqual(self.git(res["root"], "status", "--porcelain"), "")
        self.assertIn("docs/delivery/plane.json", self.git(res["root"], "ls-files").split())
        self.assertTrue((self.base / "S" / MARKER).is_file())

    def test_init_options_pass_through(self):
        res = self.create(str(self.base / "U"), "--", "--gate", "python3 -m unittest")
        cfg = json.loads((Path(res["root"]) / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"]["lanes"]["gate"], [{"name": "gate", "cmd": "python3 -m unittest"}])

    def test_a_chained_gate_runs_as_written(self):
        mark = self.base / "M"
        line = f"cd . && touch {shlex.quote(str(mark))} && python3 -c pass"
        res = self.create(str(self.base / "S"), "--", "--gate", line)
        cfg = json.loads((Path(res["root"]) / "docs/delivery/plane.json").read_text())
        self.assertEqual(cfg["suite"]["lanes"]["gate"], [{"name": "gate", "cmd": line}])
        env = dict(kv.split("=", 1) for kv in res["env"])
        r = self.ccp("suite", "run", "--lane", "gate", cwd=res["root"], **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(mark.is_file())

    def test_without_a_directory_it_makes_a_new_one_below_the_fence(self):
        res = self.create()
        d = Path(res["root"]).parent
        self.assertIn(self.fence, d.parents)
        self.assertTrue((d / MARKER).is_file())

    def test_an_empty_directory_is_used(self):
        (self.base / "E").mkdir()
        res = self.create(str(self.base / "E"))
        self.assertEqual(Path(res["root"]).parent, self.base / "E")


class Sealed(SandboxCase):
    """Inside a sandbox every command, init included, uses the sandbox's binding and queue, exported or not;
    the stand-in installation (`HOME`, `CCP_BINDINGS_DIR`) gets nothing."""

    def setUp(self):
        super().setUp()
        out = Path(self._out.name).resolve()
        self.stand_in, self.home = out / "bindings", out / "home"
        self.stand_in.mkdir()
        self.home.mkdir()
        self.env.update(HOME=str(self.home), CCP_BINDINGS_DIR=str(self.stand_in))
        self.s = self.base / "S"
        self.sb = self.create(str(self.s))
        self.product = str(self.s / PRODUCT)
        pid = json.loads((self.s / PRODUCT / "docs/delivery/plane.json").read_text())["project_id"]
        self.binding = (self.s / "bindings" / f"{pid}.yaml").resolve()

    def untouched(self):
        self.assertEqual(list(self.stand_in.iterdir()), [])
        self.assertFalse((self.home / ".delivery-queue").exists())

    def test_init_and_init_force_stay_inside(self):
        forced = self.ccp("--root", self.product, "init", "--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        again = self.ccp("--root", self.product, "init")
        self.assertEqual(again.returncode, 0, again.stderr)
        for r in (forced, again):
            out = json.loads(r.stdout)
            self.assertEqual((out["binding"], out["queue_root"]), (str(self.binding), str((self.s / "queue").resolve())))
        self.assertIn("binding", json.loads(forced.stdout)["written"])
        self.assertIn("binding", json.loads(again.stdout)["kept"])
        self.untouched()

    def test_init_called_in_process_takes_the_sandbox_s_binding_and_queue(self):
        from unittest import mock
        from ccp import init
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.stand_in), "HOME": str(self.home)}):
            out = init.init(self.s / PRODUCT, None, None, None, None, True)
        self.assertEqual((out["binding"], out["queue_root"]), (str(self.binding), str((self.s / "queue").resolve())))
        self.untouched()

    def test_commands_see_the_sandbox_with_nothing_exported(self):
        self.env.pop("CCP_BINDINGS_DIR")
        for cwd, args in ((None, ("--root", self.product)), (self.product, ())):
            with self.subTest(cwd=cwd):
                r = self.ccp(*args, "where", cwd=cwd)
                self.assertEqual(r.returncode, 0, r.stderr)
                where = json.loads(r.stdout)
                self.assertEqual((where["binding"], where["queue_root"]),
                                 (str(self.binding), str((self.s / "queue").resolve())))
                r = self.ccp(*args, "upgrade", "status", cwd=cwd)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_worktree_of_the_sandbox_product_is_in_the_sandbox(self):
        wt = self.base / "W"
        self.git(self.product, "worktree", "add", "-q", "--detach", str(wt))
        where = json.loads(self.ccp("--root", str(wt), "where").stdout)
        self.assertEqual((where["binding"], where["queue_root"]), (str(self.binding), str((self.s / "queue").resolve())))

    def test_child_processes_inherit_the_sandbox_s_names(self):
        seen = self.base / "seen.json"
        keys = ("CCP_BINDINGS_DIR", "PROJECT_YAML", "QUEUE_ROOT")
        r = self.ccp("--root", self.product, "suite", "run", "--lane", "part", "--full", "--", "python3", "-c",
                     f"import json, os, sys; open(sys.argv[1], 'w').write(json.dumps({{k: os.environ.get(k) for k in {keys!r}}}))",
                     str(seen))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(seen.read_text()), {"CCP_BINDINGS_DIR": str(self.s / "bindings"),
                                                        "PROJECT_YAML": str(self.binding),
                                                        "QUEUE_ROOT": str(self.s / "queue")})

    def test_a_shell_pointing_elsewhere_is_refused(self):
        outside = Path(self._out.name).resolve() / "R"
        outside.mkdir()
        for args, env in ((("where",), {"QUEUE_ROOT": str(outside)}),
                          (("init", "--queue-root", str(outside)), {}),
                          (("init", "--force", "--queue-root", str(outside)), {})):
            with self.subTest(args=args):
                r = self.ccp("--root", self.product, *args, **env)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertIn(str(outside), r.stderr)
                self.assertIn(str(self.s), r.stderr)
                self.assertEqual(list(outside.iterdir()), [])
        self.untouched()

    def test_init_takes_the_sandbox_s_queue_and_no_other_inside_it(self):
        r = self.ccp("--root", self.product, "init", "--queue-root", str(self.s / "queue"))
        self.assertEqual(r.returncode, 0, r.stderr)
        other = self.s / "other-queue"
        r = self.ccp("--root", self.product, "init", "--force", "--queue-root", str(other))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertFalse(other.exists())
        self.untouched()

    def test_values_inside_the_sandbox_are_set_to_its_own(self):
        r = self.ccp("--root", self.product, "where", QUEUE_ROOT=str(self.s / PRODUCT),
                     PROJECT_YAML=str(self.s / MARKER))
        self.assertEqual(r.returncode, 0, r.stderr)
        where = json.loads(r.stdout)
        self.assertEqual((where["binding"], where["queue_root"]), (str(self.binding), str((self.s / "queue").resolve())))

    def test_a_directory_beside_a_linked_marker_is_not_a_sandbox(self):
        from ccp import sandbox
        fake = self.base / "F"
        (fake / PRODUCT).mkdir(parents=True)
        (fake / MARKER).symlink_to(self.s / MARKER)
        self.assertIsNone(sandbox.sandbox_of(fake / PRODUCT))
        self.assertEqual(sandbox.sandbox_of(self.s / PRODUCT), self.s)


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

    def test_init_output_without_a_binding_is_refused_and_leaves_nothing(self):
        for opt in ("-h", "--help"):
            with self.subTest(opt):
                d = self.base / "H"
                r = self.ccp("sandbox", "create", str(d), "--", opt)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
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

    def test_a_sandbox_holding_the_working_directory_is_refused(self):
        s = self.base / "S"
        self.create(str(s))
        for cwd, arg in ((s, "."), (s / PRODUCT, ".."), (s / PRODUCT, str(s))):
            with self.subTest(cwd=cwd.name, arg=arg):
                r = self.ccp("sandbox", "remove", arg, cwd=cwd)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertTrue((s / MARKER).is_file())
                self.assertTrue((s / PRODUCT / "README.md").is_file())

    def test_a_sandbox_named_through_a_dot_dot_path_is_removed(self):
        s = self.base / "S"
        self.create(str(s))
        r = self.ccp("sandbox", "remove", "S/product/..")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(s.exists())

    def test_remove_needs_a_directory_and_no_init_options(self):
        s = self.base / "S"
        self.create(str(s))
        for args in (("sandbox", "remove"), ("sandbox", "remove", str(s), "--", "--force")):
            with self.subTest(args):
                self.assertEqual(self.ccp(*args).returncode, 2)
        self.assertTrue(s.exists())


if __name__ == "__main__":
    unittest.main()
