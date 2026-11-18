"""Worktrees outside the main checkout (SPEC §12.1): plane.json `worktrees.dir` absolute or a sibling."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, lifecycle, prompt, wt
from tests.helpers import Product
from tests.test_toolkit import PLANE, ToolkitFixture, git

LEGACY_OFF = {"worktree_dir": None, "worktree_links": [".venv"], "post_close": ["touch closed-{nnnn}"]}


class Config(unittest.TestCase):
    """What `worktrees.dir` may be: relative (`..` allowed) or absolute, never empty or the main checkout."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self._other = tempfile.TemporaryDirectory()
        self.addCleanup(self._other.cleanup)

    def load(self, **blocks) -> config.Config:
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **blocks}))
        return config.load(self.p.root)

    def test_a_sibling_or_an_absolute_directory_loads_and_resolves(self):
        sibling = f"../{self.p.root.name}-wt"
        outside = str(Path(self._other.name) / "wt")
        for d, want in ((sibling, (self.p.root.parent / f"{self.p.root.name}-wt").resolve()),
                        (outside, Path(outside).resolve())):
            with self.subTest(d=d):
                cfg = self.load(worktrees={"dir": d})
                self.assertEqual(wt.base_dir(cfg), want)
                self.assertTrue(wt.base_dir(cfg).is_absolute())
                self.assertEqual(prompt.worktree_for(cfg, "impl", "0002"), str(want / "impl-0002"))

    def test_the_legacy_key_may_be_absolute_too(self):
        outside = str(Path(self._other.name) / "wt")
        cfg = self.load(adapter={"worktree_dir": outside})
        self.assertEqual(wt.base_dir(cfg), Path(outside).resolve())

    def test_an_empty_value_or_the_main_checkout_itself_is_refused(self):
        for d in ("", ".", "./", "sub/..", f"../{self.p.root.name}", str(self.p.root)):
            with self.subTest(d=d):
                with self.assertRaises(config.ConfigError) as cm:
                    self.load(worktrees={"dir": d})
                self.assertIn("worktrees.dir must be a path relative to the main checkout (`..` allowed) "
                              "or an absolute path, or null", str(cm.exception))

    def test_a_relative_directory_inside_resolves_under_the_main_checkout(self):
        cfg = self.load(worktrees={"dir": ".rt"})
        self.assertEqual(wt.base_dir(cfg), (self.p.root / ".rt").resolve())


class SiblingFixture(ToolkitFixture):
    """The toolkit product with `worktrees.dir` `../product-wt`, committed so the runner worktree reads it."""

    DIR = "../product-wt"

    def setUp(self):
        super().setUp()
        body = {**self.PLANE_JSON, "adapter": LEGACY_OFF, "worktrees": {"dir": self.DIR, "links": [".venv"]}}
        self.write("docs/delivery/plane.json", json.dumps(body))
        git(self.main, "add", "docs/delivery/plane.json")
        git(self.main, "commit", "-q", "-m", "worktrees outside")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        self.outside = (self.main.parent / "product-wt").resolve()

    def wt(self, *args: str):
        code, parsed, body, err = self.ccp("wt", *args, root=self.main)
        if parsed is None and body.strip().startswith("["):
            parsed = json.loads(body)
        return code, parsed, body, err

    def inside(self, name: str) -> list[Path]:
        """Directories named `name` in the main checkout, git's own admin dir aside."""
        return [p for p in self.main.rglob(name) if p.is_dir() and self.main / ".git" not in p.parents]


class Sibling(SiblingFixture, unittest.TestCase):
    def test_an_impl_worktree_is_made_and_recorded_in_the_sibling_directory(self):
        code, body, out, err = self.wt("create", "--kind", "impl", "--task", "0002")
        self.assertEqual(code, 0, out + err)
        want = self.outside / "impl-0002"
        self.assertEqual(body["path"], str(want))
        self.assertTrue(want.is_dir())
        st = json.loads((self.q / "worktrees" / "impl-0002.json").read_text())
        self.assertEqual(st["path"], str(want))
        code, listed, out, err = self.wt("list", "--task", "0002-second")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([(s["name"], s["path"]) for s in listed], [("impl-0002", str(want))])
        self.assertIn(str(want), git(self.main, "worktree", "list"))
        self.assertEqual(self.inside("impl-0002"), [])

    def test_close_reconciles_in_the_sibling_merge_worktree_and_removes_both(self):
        code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        impl = Path(body["worktree"]["path"])
        self.assertEqual(impl, self.outside / "impl-0002")
        (impl / "feature.txt").write_text("built\n")
        git(impl, "add", "feature.txt")
        git(impl, "commit", "-q", "-m", "Task 0002: build it")
        git(impl, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(impl, "rev-parse", "HEAD")
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "OPEN", "head": head, "origin": str(self.origin),
                                                           "base": "main", "branch": "task/0002-second"}))
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        made: list[Path] = []
        real = lifecycle._merge_checkout

        def spy(cfg, tid, integ):
            rc = real(cfg, tid, integ)
            made.append(rc.root)
            return rc

        with mock.patch.object(lifecycle, "_merge_checkout", spy):
            code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(made, [self.outside / "merge-0002"])
        git(self.main, "fetch", "-q", "origin")
        self.assertTrue(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile 0002"))
        self.assertFalse(impl.exists())
        self.assertFalse((self.outside / "merge-0002").exists())
        self.assertEqual(self.inside("merge-0002") + self.inside("impl-0002"), [])

    def test_an_unrecorded_worktree_git_names_is_still_listed_removed_and_swept(self):
        ver = self.outside / "ver-0002"
        merge = self.outside / "merge-0002"
        git(self.main, "worktree", "add", "-q", "--detach", str(ver), "origin/main")
        git(self.main, "worktree", "add", "-q", "--detach", str(merge), "origin/main")
        listed = {s["name"] for s in self.wt("list")[1]}
        self.assertEqual(listed, {"ver-0002", "merge-0002"})
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "done"}))
        body = self.wt("gc")[1]
        self.assertEqual((body["removed"], body["warnings"]), (["merge-0002"], []))
        self.assertFalse(merge.exists())
        self.assertEqual(wt.remove_task(config.load(self.main), self.q, "0002-second"), [])
        self.assertFalse(ver.exists())


class Unrecorded(SiblingFixture, unittest.TestCase):
    """A directory with no record under the sibling directory: adopted or removed only when git names it."""

    def plain(self, name: str) -> Path:
        d = self.outside / name
        d.mkdir(parents=True)
        (d / "theirs.txt").write_text("another checkout's\n")
        return d

    def assertUntouched(self, d: Path):
        self.assertEqual([p.name for p in d.iterdir()], ["theirs.txt"])
        self.assertEqual((d / "theirs.txt").read_text(), "another checkout's\n")

    def test_create_refuses_a_plain_directory_git_does_not_name_and_writes_nothing(self):
        with mock.patch.dict("os.environ", {"CCP_NO_WORKTREE": "1"}):
            code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        d = self.plain("impl-0002")
        code, _, out, err = self.wt("create", "--kind", "impl", "--task", "0002")
        self.assertEqual(code, 3, out + err)
        self.assertIn(str(d), err)
        self.assertIn("git worktree list", err)
        self.assertFalse((self.q / "worktrees" / "impl-0002.json").exists())
        self.assertUntouched(d)

    def test_remove_refuses_a_plain_directory_git_does_not_name_and_leaves_it(self):
        d = self.plain("rev-0002")
        code, _, out, err = self.wt("remove", "rev-0002")
        self.assertEqual(code, 3, out + err)
        self.assertIn(str(d), err)
        self.assertUntouched(d)

    def test_a_recorded_name_whose_worktree_moved_is_adopted_as_before(self):
        (self.q / "worktrees").mkdir(exist_ok=True)
        (self.q / "worktrees" / "impl-0002.json").write_text(json.dumps(
            {"name": "impl-0002", "kind": "impl", "task_id": "0002-second", "path": str(self.main.parent / "gone")}))
        d = self.plain("impl-0002")
        code, body, out, err = self.wt("create", "--kind", "impl", "--task", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIs(body["adopted"], True)
        self.assertEqual(body["path"], str(d))

    def test_worktrees_git_names_are_still_adopted_and_removed_without_a_record(self):
        impl, rev = self.outside / "impl-0002", self.outside / "rev-0002"
        git(self.main, "worktree", "add", "-q", "-b", "task/0002-second", str(impl), "origin/main")
        git(self.main, "worktree", "add", "-q", "--detach", str(rev), "origin/main")
        code, body, out, err = self.wt("create", "--kind", "impl", "--task", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertIs(body["adopted"], True)
        self.assertEqual(json.loads((self.q / "worktrees" / "impl-0002.json").read_text())["path"], str(impl))
        code, _, out, err = self.wt("remove", "rev-0002")
        self.assertEqual(code, 0, out + err)
        self.assertFalse(rev.exists())


class Shared(ToolkitFixture, unittest.TestCase):
    """An absolute `worktrees.dir` shared with another repository's checkouts: theirs are left alone."""

    def setUp(self):
        super().setUp()
        self.d = Path(self._tmp.name).resolve() / "shared"
        self.d.mkdir()
        body = {**self.PLANE_JSON, "adapter": LEGACY_OFF, "worktrees": {"dir": str(self.d)}}
        self.write("docs/delivery/plane.json", json.dumps(body))
        other = Path(self._tmp.name).resolve() / "other"
        git(other.parent, "init", "-q", "-b", "main", str(other))
        (other / "a.txt").write_text("a\n")
        git(other, "add", "a.txt")
        git(other, "commit", "-q", "-m", "other")
        git(self.d, "clone", "-q", str(other), str(self.d / "impl-0001"))  # a clone: `.git` is a directory
        git(other, "worktree", "add", "-q", "--detach", str(self.d / "merge-0001"), "main")
        (self.d / "rev-0001").mkdir()  # a plain directory
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0001-first.json").write_text(json.dumps({"task_id": "0001-first", "status": "done"}))

    def wt(self, *args: str):
        code, parsed, body, err = self.ccp("wt", *args, root=self.main)
        if parsed is None and body.strip().startswith("["):
            parsed = json.loads(body)
        return code, parsed, body, err

    def test_list_gc_and_a_tasks_cleanup_leave_another_repositorys_directories(self):
        code, listed, out, err = self.wt("list")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(listed, [])
        code, body, out, err = self.wt("gc")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["removed"], [])
        self.assertEqual(wt.remove_task(config.load(self.main), self.q, "0001-first"), [])
        for n in ("impl-0001", "merge-0001", "rev-0001"):
            self.assertTrue((self.d / n).is_dir(), n)
        self.assertTrue((self.d / "impl-0001" / "a.txt").is_file())
        self.assertTrue((self.d / "merge-0001" / "a.txt").is_file())

    def test_remove_refuses_another_repositorys_clone_or_worktree_and_keeps_it(self):
        for n in ("impl-0001", "merge-0001"):
            with self.subTest(n=n):
                code, _, out, err = self.wt("remove", n)
                self.assertEqual(code, 3, out + err)
                self.assertTrue((self.d / n / "a.txt").is_file())


class Inside(ToolkitFixture, unittest.TestCase):
    """Inside the main checkout an unrecorded directory is still taken for the product's, as before."""

    def test_a_plain_unrecorded_directory_under_an_inside_dir_is_listed(self):
        (self.main / ".rt" / "rev-0002").mkdir(parents=True)
        code, _, body, err = self.ccp("wt", "list", root=self.main)
        self.assertEqual(code, 0, body + err)
        names = {s["name"] for s in json.loads(body)}
        self.assertIn("rev-0002", names)

    def test_an_unrecorded_directory_inside_is_still_adopted_and_removed(self):
        self.write("docs/delivery/plane.json",
                   json.dumps({**self.PLANE_JSON, "adapter": LEGACY_OFF, "worktrees": {"dir": ".rt"}}))
        (self.main / ".rt" / "impl-0002").mkdir(parents=True)
        code, body, out, err = self.ccp("wt", "create", "--kind", "impl", "--task", "0002", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertIs(body["adopted"], True)
        git(self.main, "worktree", "add", "-q", "--detach", str(self.main / ".rt" / "rev-0002"), "origin/main")
        code, _, out, err = self.ccp("wt", "remove", "rev-0002", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.main / ".rt" / "rev-0002").exists())


if __name__ == "__main__":
    unittest.main()
