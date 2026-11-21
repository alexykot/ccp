"""Worktrees and environments (SPEC §12.1): `ccp wt`, env hooks, URLs, merge.command, auth probes."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, lifecycle, wt
from tests.test_toolkit import GIT_ENV, PLANE, ToolkitFixture, git


class WtFixture(ToolkitFixture):
    """The toolkit product with plane.json rewritten in the main checkout (ccp runs with --root main)."""

    def plane(self, **blocks) -> None:
        body = {**self.PLANE_JSON, **blocks}
        self.write("docs/delivery/plane.json", json.dumps(body))

    def head(self) -> str:
        return git(self.main, "rev-parse", "origin/main")

    def wt(self, *args: str):
        code, parsed, body, err = self.ccp("wt", *args, root=self.main)
        if parsed is None and body.strip().startswith("["):
            parsed = json.loads(body)
        return code, parsed, body, err


class Create(WtFixture, unittest.TestCase):
    def test_claim_records_the_impl_worktree_at_the_same_path(self):
        code, body, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, err)
        path = self.main / ".plane-runtime" / "impl-0002"
        self.assertEqual(Path(body["worktree"]["path"]), path)
        self.assertTrue((path / ".venv").is_symlink())
        st = json.loads((self.q / "worktrees" / "impl-0002.json").read_text())
        self.assertEqual((st["kind"], st["task_id"], st["branch"], st["state"]), ("impl", "0002-second", "task/0002-second", "created"))

    def test_a_base_directory_inside_the_checkout_is_excluded_when_the_gitignore_lacks_it(self):
        self.write(".gitignore", ".venv/\nclosed-*\n")
        git(self.main, "commit", "-qam", "drop the runtime ignore line")
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        self.assertEqual(git(self.main, "status", "--porcelain"), "")  # .plane-runtime is not untracked
        ex = (self.main / ".git" / "info" / "exclude").read_text().splitlines()
        self.assertEqual(ex.count("/.plane-runtime"), 1)
        self.assertEqual(self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())[0], 0)
        self.assertEqual((self.main / ".git" / "info" / "exclude").read_text().splitlines().count("/.plane-runtime"), 1)

    def test_a_base_directory_outside_the_checkout_is_not_excluded(self):
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        self.plane(worktrees={"dir": str(other / "trees")})
        code, body, _, err = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, err)
        self.assertTrue(Path(body["path"]).is_relative_to(other.resolve()), body["path"])
        ex = self.main / ".git" / "info" / "exclude"
        text = ex.read_text() if ex.is_file() else ""
        self.assertNotIn("/trees", text)
        self.assertNotIn("worktrees directory", text)

    def test_rev_worktree_is_detached_runs_setup_with_fields_and_env(self):
        self.plane(env={"setup": "echo {kind} {seat} {tag} {nnnn} $CCP_WT_NAME > setup.txt"})
        code, body, _, err = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head(), "--name", "rev-0002-2")
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual(p.name, "rev-0002-2")
        self.assertEqual((p / "setup.txt").read_text().split(), ["rev", "rev", "main", "0002", "rev-0002-2"])
        self.assertEqual(git(p, "rev-parse", "HEAD"), self.head())
        self.assertEqual(git(p, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")  # detached
        code, again, _, _ = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head(), "--name", "rev-0002-2")
        self.assertEqual((code, again["created"]), (0, False))

    def test_default_names_count_up_and_mut_has_its_tag(self):
        names = [self.wt("create", "--kind", "mut", "--task", "0002", "--sha", self.head())[1]["name"] for _ in range(2)]
        self.assertEqual(names, ["mut-0002", "mut-0002-2"])
        st = json.loads((self.q / "worktrees" / "mut-0002.json").read_text())
        self.assertEqual((st["seat"], st["tag"]), ("ver", "mut"))

    def test_a_worktrees_round_is_the_number_its_name_ends_in(self):
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        made = [self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())[1] for _ in range(2)]
        made.append(self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "ver-0002-5")[1])
        self.assertEqual([(m["name"], m["round"]) for m in made], [("rev-0002", 1), ("rev-0002-2", 2), ("ver-0002-5", 5)])
        code, listed, _, err = self.wt("list")
        self.assertEqual(code, 0, err)
        self.assertEqual({s["name"]: s["round"] for s in listed},
                         {"impl-0002": 1, "rev-0002": 1, "rev-0002-2": 2, "ver-0002-5": 5})
        st = json.loads((self.q / "worktrees" / "rev-0002-2.json").read_text())
        self.assertEqual(st["round"], 2)  # recorded, not only listed

    def test_a_record_without_a_round_reads_as_round_one(self):
        self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())
        name = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())[1]["name"]
        f = self.q / "worktrees" / f"{name}.json"
        st = json.loads(f.read_text())
        del st["round"]
        f.write_text(json.dumps(st))
        code, listed, _, err = self.wt("list")
        self.assertEqual(code, 0, err)
        self.assertEqual({s["name"]: s["round"] for s in listed}, {"rev-0002": 1, name: 1})
        self.assertEqual(wt.load(self.q, name)["round"], 1)

    def test_the_round_is_read_from_the_names_last_number(self):
        self.assertEqual([wt.round_of(n) for n in ("impl-0002", "rev-0002", "rev-0002-2", "mut-0042-11",
                                                   wt.BASELINE, "")], [1, 1, 2, 11, 1, 1])

    def test_a_symbolic_sha_is_the_callers_own_commit_and_one_naming_none_makes_nothing(self):
        main_head = git(self.main, "rev-parse", "HEAD")
        (self.runner / "B.txt").write_text("b\n")
        git(self.runner, "add", "B.txt")
        git(self.runner, "commit", "-q", "-m", "B, in the caller's checkout only")
        mine = git(self.runner, "rev-parse", "HEAD")
        self.assertNotEqual(mine, main_head)
        for given, name in (("HEAD", "mut-0002"), (mine[:9], "mut-0002-2")):
            code, body, _, err = self.ccp("wt", "create", "--kind", "mut", "--task", "0002", "--sha", given)
            self.assertEqual((code, body and body["name"]), (0, name), err)
            st = json.loads((self.q / "worktrees" / f"{name}.json").read_text())
            self.assertEqual(st["sha"], mine)
            self.assertEqual(git(Path(st["path"]), "rev-parse", "HEAD"), mine)
        before = (sorted(p.name for p in (self.q / "worktrees").iterdir()), sorted(p.name for p in (self.main / ".plane-runtime").iterdir()))
        code, _, _, err = self.ccp("wt", "create", "--kind", "mut", "--task", "0002", "--sha", "nope")
        self.assertEqual(code, 2, err)
        self.assertIn("nope", err)
        self.assertEqual((sorted(p.name for p in (self.q / "worktrees").iterdir()),
                          sorted(p.name for p in (self.main / ".plane-runtime").iterdir())), before)

    def test_a_failed_setup_removes_the_half_made_worktree(self):
        self.plane(env={"setup": "echo no database; exit 3"})
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 1)
        self.assertIn("env.setup for ver-0002 exited 3", err)
        self.assertIn("no database", err)
        self.assertFalse((self.main / ".plane-runtime" / "ver-0002").exists())
        self.assertFalse((self.q / "worktrees" / "ver-0002.json").exists())

    def test_detached_kinds_need_a_sha_and_names_follow_the_kind(self):
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002")[0], 2)
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "rev-0002")[0], 2)

    def test_no_worktrees_dir_refuses(self):
        self.plane(worktrees={"dir": None, "links": []})
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 2)
        self.assertIn("worktrees.dir", err)


class Baseline(WtFixture, unittest.TestCase):
    """The adopting lead's verifier-shaped worktree at the integration tip, which needs no task."""

    def test_it_is_made_at_the_tip_recorded_set_up_and_removed(self):
        self.plane(env={"setup": "echo {kind} {seat} {name} \"[{task_id}]\" > setup.txt",
                        "teardown": "echo $CCP_WT_NAME > {main_checkout}/torn.txt"})
        code, body, _, err = self.wt("create", "--kind", "ver", "--baseline")
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual((p, body["created"]), (self.main / ".plane-runtime" / "ver-baseline", True))
        self.assertEqual(git(p, "rev-parse", "HEAD"), self.head())
        self.assertEqual(git(p, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")  # detached
        self.assertEqual((p / "setup.txt").read_text().split(), ["ver", "ver", "ver-baseline", "[]"])
        st = json.loads((self.q / "worktrees" / "ver-baseline.json").read_text())
        self.assertEqual((st["kind"], st["task_id"], st["nnnn"], st["sha"]), ("ver", "", "", self.head()))
        self.assertEqual([(r["name"], r["exists"]) for r in self.wt("list")[1]], [("ver-baseline", True)])
        self.assertEqual(self.wt("gc")[1]["removed"], [])  # no task to be done: gc keeps it
        code, again, _, err = self.wt("create", "--kind", "ver", "--baseline")
        self.assertEqual((code, again["created"]), (0, False), err)
        code, body, _, err = self.wt("remove", "ver-baseline")
        self.assertEqual((code, body["warnings"]), (0, []), err)
        self.assertFalse(p.exists())
        self.assertFalse((self.q / "worktrees" / "ver-baseline.json").exists())
        self.assertEqual((self.main / "torn.txt").read_text().strip(), "ver-baseline")

    def test_a_moved_tip_refuses_the_old_one(self):
        self.assertEqual(self.wt("create", "--kind", "ver", "--baseline")[0], 0)
        self.write("NEW.md", "x\n")
        git(self.main, "add", "NEW.md")
        git(self.main, "commit", "-q", "-m", "tip moves")
        git(self.main, "push", "-q", "origin", "main")
        code, _, _, err = self.wt("create", "--kind", "ver", "--baseline")
        self.assertEqual(code, 3)
        self.assertIn("ccp wt remove ver-baseline", err)
        self.assertIn("--baseline", err)  # the way back is what --baseline accepts,
        self.assertNotIn("--name", err)   # not the flag it refuses

    def test_gc_and_a_tasks_cleanup_remove_the_tasks_worktrees_and_keep_it(self):
        self.assertEqual(self.wt("create", "--kind", "ver", "--baseline")[0], 0)
        for n in ("0001", "0002"):
            self.assertEqual(self.wt("create", "--kind", "ver", "--task", n, "--sha", self.head())[0], 0)
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "done"}))
        self.assertEqual(self.wt("gc")[1]["removed"], ["ver-0002"])
        self.assertEqual(wt.remove_task(config.load(self.main), self.q, "0001-first"), [])  # close's cleanup
        self.assertFalse((self.main / ".plane-runtime" / "ver-0001").exists())
        self.assertTrue((self.main / ".plane-runtime" / "ver-baseline").is_dir())
        self.assertEqual([r["name"] for r in self.wt("list")[1]], ["ver-baseline"])

    def test_without_baseline_a_ver_worktree_still_needs_a_task(self):
        self.assertEqual(self.wt("create", "--kind", "ver", "--sha", self.head())[0], 2)

    def test_baseline_refuses_a_task_a_sha_a_name_another_kind_or_action(self):
        for args in (("create", "--kind", "ver", "--baseline", "--task", "0002"),
                     ("create", "--kind", "ver", "--baseline", "--sha", self.head()),
                     ("create", "--kind", "ver", "--baseline", "--name", "ver-0002"),
                     ("create", "--kind", "rev", "--baseline"),
                     ("create", "--baseline"),
                     ("list", "--baseline")):
            with self.subTest(args=args):
                self.assertEqual(self.wt(*args)[0], 2)
        self.assertFalse((self.main / ".plane-runtime" / "ver-baseline").exists())

    def test_its_name_is_not_a_task_worktree_name(self):
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "ver-baseline")
        self.assertEqual(code, 2, err)
        self.assertFalse((self.main / ".plane-runtime" / "ver-baseline").exists())

    def test_no_integration_tip_refuses(self):
        (self.q / "project.yaml").write_text("project_id: demo\nintegration_branch: trunk\n")
        code, _, _, err = self.wt("create", "--kind", "ver", "--baseline")
        self.assertEqual(code, 3)
        self.assertIn("origin/trunk", err)


class UpDownUrls(WtFixture, unittest.TestCase):
    URLS = """printf '[{"name": "api", "url": "http://localhost:31%s/"}, {"name": "app", "url": "http://localhost:32%s/"}]' {nnnn} {nnnn}"""

    def made(self, **env) -> str:
        self.plane(env=env)
        code, body, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, err)
        return body["name"]

    def state(self, name: str) -> dict:
        return json.loads((self.q / "worktrees" / f"{name}.json").read_text())

    def test_up_runs_the_hook_and_records_a_dynamic_list_of_urls(self):
        name = self.made(up="touch up.flag", urls=self.URLS)
        code, body, _, err = self.wt("up", name)
        self.assertEqual(code, 0, err)
        self.assertEqual([u["name"] for u in body["urls"]], ["api", "app"])
        self.assertEqual(body["urls"][0]["url"], "http://localhost:310002/")
        self.assertTrue((self.main / ".plane-runtime" / name / "up.flag").exists())
        self.assertEqual(self.state(name)["state"], "up")
        self.assertEqual(self.wt("urls", name)[1], body["urls"])

    def test_a_failed_up_leaves_it_down_and_exits_non_zero(self):
        name = self.made(up="exit 4")
        code, _, _, err = self.wt("up", name)
        self.assertEqual(code, 1)
        self.assertIn("env.up for", err)
        self.assertEqual(self.state(name)["state"], "down")

    def test_up_without_hooks_is_a_no_op_that_marks_it_up(self):
        name = self.made()
        code, body, _, _ = self.wt("up", name)
        self.assertEqual((code, body["hook"], body["urls"]), (0, False, []))

    def test_bad_urls_output_is_refused_and_does_not_fail_up(self):
        for out in ("not json", '{"name": "x"}', '[{"name": "x", "url": "localhost:3000"}]',
                    '[{"name": "a", "url": "http://a/"}, {"name": "a", "url": "http://b/"}]'):
            with self.subTest(out=out):
                name = self.made(urls=f"printf '%s' '{out}'")
                code, _, _, err = self.wt("urls", name)
                self.assertEqual(code, 1, out)
                code, body, _, _ = self.wt("up", name)
                self.assertEqual(code, 0)
                self.assertTrue(body["warnings"])
                self.wt("remove", name)

    def test_down_failure_warns_and_marks_down(self):
        name = self.made(down="exit 5")
        self.wt("up", name)
        code, body, _, err = self.wt("down", name)
        self.assertEqual(code, 0)
        self.assertIn("env.down", err)
        self.assertEqual(self.state(name)["state"], "down")

    def test_remove_stops_tears_down_and_forgets_even_when_hooks_fail(self):
        marker = self.main / "teardown.log"
        name = self.made(down=f"echo down >> {marker}", teardown=f"echo teardown {{tag}} >> {marker}; exit 2")
        self.wt("up", name)
        code, body, _, err = self.wt("remove", name)
        self.assertEqual(code, 0, err)
        self.assertEqual(marker.read_text().split("\n")[:2], ["down", "teardown main"])
        self.assertIn("env.teardown", err)
        self.assertFalse((self.main / ".plane-runtime" / name).exists())
        self.assertFalse((self.q / "worktrees" / f"{name}.json").exists())

    def test_a_hook_that_hangs_is_killed_with_its_children(self):
        self.plane(env={"up": "sleep 30 & sleep 30", "timeout_seconds": 1})
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        t = time.time()
        code, _, _, err = self.wt("up", name)
        self.assertLess(time.time() - t, 10)
        self.assertEqual(code, 1)
        self.assertIn("timed out", err)


class Cleanup(WtFixture, unittest.TestCase):
    def test_remove_task_takes_every_recorded_worktree_and_old_unrecorded_ones(self):
        self.ccp("tasks", "claim", "0002")
        self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        git(self.main, "worktree", "add", "-q", "--detach", str(self.main / ".plane-runtime" / "rev-0002"), self.head())  # pre-§12.1
        listed = {r["name"]: r.get("recorded", True) for r in self.wt("list")[1]}
        self.assertEqual(listed, {"impl-0002": True, "ver-0002": True, "rev-0002": False})
        warnings = wt.remove_task(config.load(self.main), self.q, "0002-second")
        self.assertEqual(warnings, [])
        for n in ("impl-0002", "ver-0002", "rev-0002"):
            self.assertFalse((self.main / ".plane-runtime" / n).exists(), n)
        self.assertEqual(list((self.q / "worktrees").glob("*.json")), [])

    def test_gc_forgets_missing_and_removes_finished_tasks(self):
        self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.wt("create", "--kind", "mac", "--task", "0002", "--sha", self.head())
        git(self.main, "worktree", "remove", "--force", str(self.main / ".plane-runtime" / "mac-0002"))
        body = self.wt("gc")[1]
        self.assertEqual(body["forgot"], ["mac-0002"])
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "dropped"}))
        body = self.wt("gc")[1]
        self.assertEqual(body["removed"], ["ver-0002"])


class LeftoverMergeWorktree(WtFixture, unittest.TestCase):
    """§10.5, §12.1: a `merge-<nnnn>` a failed close left behind is listed, removed with its task's
    worktrees, and removed by gc once its task is done or dropped and leased by no one."""

    def leftover(self, nnnn: str = "0002") -> Path:
        path = self.main / ".plane-runtime" / f"merge-{nnnn}"
        git(self.main, "worktree", "add", "-q", "--detach", str(path), self.head())
        return path

    def task_state(self, **st) -> None:
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({"task_id": "0002-second", **st}))

    def test_list_shows_it_as_a_merge_worktree_for_its_task_too(self):
        path = self.leftover()
        self.leftover("0001")
        want = {"name": "merge-0002", "kind": "merge", "path": str(path), "exists": True, "recorded": False}
        self.assertIn(want, self.wt("list")[1])
        self.assertEqual(self.wt("list", "--task", "0002")[1], [want])

    def test_gc_removes_it_once_its_task_is_done_or_dropped_and_unleased(self):
        for status in ("done", "dropped"):
            with self.subTest(status=status):
                path = self.leftover()
                self.task_state(status=status)
                body = self.wt("gc")[1]
                self.assertEqual((body["removed"], body["warnings"]), (["merge-0002"], []))
                self.assertFalse(path.exists())
                self.assertNotIn("merge-0002", git(self.main, "worktree", "list"))
                self.assertNotIn("merge-0002", [w["name"] for w in self.wt("list")[1]])

    def test_gc_keeps_it_while_its_task_is_leased_and_list_shows_it(self):
        path = self.leftover()
        for status in ("verifying", "done", "dropped"):  # a re-run of its close reuses it
            with self.subTest(status=status):
                self.task_state(status=status, lease_holder="runner")
                self.assertEqual(self.wt("gc")[1]["removed"], [])
                self.assertTrue(path.is_dir())
                self.assertIn("merge-0002", [w["name"] for w in self.wt("list")[1]])

    def test_gc_keeps_it_when_the_queue_holds_no_task_for_it(self):
        path = self.leftover()
        self.assertEqual(self.wt("gc")[1]["removed"], [])
        self.assertTrue(path.is_dir())

    def test_remove_task_removes_it_but_never_the_checkout_it_runs_in(self):
        path = self.leftover()
        cfg = config.load(self.main)
        from dataclasses import replace
        self.assertEqual(wt.remove_task(replace(cfg, root=path), self.q, "0002-second"), [])
        self.assertTrue(path.is_dir())  # close runs its cleanup in its merge worktree and removes it itself
        self.assertEqual(wt.remove_task(cfg, self.q, "0002-second"), [])
        self.assertFalse(path.exists())


class MainCheckout(unittest.TestCase):
    """§12.1: the main checkout is found from `git rev-parse --git-common-dir`, a separate git dir too."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.t = Path(self._tmp.name).resolve()

    def tearDown(self):
        self._tmp.cleanup()

    def repo(self, *init: str) -> Path:
        main = self.t / "main"
        git(self.t, "init", "-q", *init, str(main))
        git(main, "commit", "-q", "--allow-empty", "-m", "x")
        return main

    def test_a_main_checkout_with_a_separate_git_dir_is_its_own_main(self):
        main = self.repo("--separate-git-dir", str(self.t / "gitdir"))
        self.assertEqual(wt.main_of(main), main)
        sub = main / "sub"
        sub.mkdir()
        self.assertEqual(wt.main_of(sub), main)

    def test_a_linked_worktree_finds_the_main_checkout(self):
        main = self.repo()
        git(main, "worktree", "add", "-q", "--detach", str(self.t / "linked"))
        self.assertEqual(wt.main_of(self.t / "linked"), main)
        self.assertEqual(wt.main_of(main), main)

    def test_without_a_repository_it_is_the_checkout_itself(self):
        self.assertEqual(wt.main_of(self.t), self.t)

    def test_a_linked_worktree_of_a_separate_git_dir_finds_the_main_checkout(self):
        main = self.repo("--separate-git-dir", str(self.t / "gitdir"))
        git(main, "worktree", "add", "-q", "--detach", str(main / ".plane-runtime" / "inside"))
        git(main, "worktree", "add", "-q", "--detach", str(self.t / "beside"))
        self.assertEqual(wt.main_of(main / ".plane-runtime" / "inside"), main)  # under the main checkout
        self.assertEqual(wt.main_of(self.t / "beside"), main)  # next to it
        (self.t / "beside" / "sub").mkdir()
        self.assertEqual(wt.main_of(self.t / "beside" / "sub"), main)

    def test_a_linked_worktree_whose_main_checkout_is_nowhere_near_is_itself(self):
        main = self.repo("--separate-git-dir", str(self.t / "gitdir"))
        far = self.t / "a" / "b" / "far"
        git(main, "worktree", "add", "-q", "--detach", str(far))
        (main / ".git").unlink()  # the main checkout's pointer to its git dir is gone
        self.assertEqual(wt.main_of(far), far)


class Config(WtFixture, unittest.TestCase):
    def test_legacy_adapter_keys_fold_into_worktrees(self):
        cfg = config.load(self.main)
        self.assertEqual((cfg.worktrees["dir"], cfg.worktrees["links"]), (".plane-runtime", [".venv"]))
        self.plane(worktrees={"dir": None, "links": []},
                   adapter={"worktree_dir": ".lg", "worktree_links": [".env"], "post_close": []})
        cfg = config.load(self.main)
        self.assertEqual((cfg.worktrees["dir"], cfg.worktrees["links"]), (".lg", [".env"]))
        self.plane(adapter={"worktree_dir": None, "worktree_links": [], "post_close": []},
                   worktrees={"dir": ".wt", "links": [".venv"]})
        self.assertEqual(config.load(self.main).worktrees["dir"], ".wt")

    def test_bad_blocks_are_refused(self):
        for bad in ({"worktrees": {"dir": ".x"}, "adapter": {"worktree_dir": ".plane-runtime"}},  # both the block and the legacy key
                    {"env": {"up": 3}}, {"env": {"timeout_seconds": 0}},
                    {"merge": {"command": "gh pr merge {pr} --squash"}},  # not pinned to the head
                    {"auth_check": {"probes": [{"id": "gh"}]}},
                    {"auth_check": {"probes": [{"id": "a", "cmd": "true"}, {"id": "a", "cmd": "true"}]}}):
            with self.subTest(bad=bad):
                self.plane(**bad)
                with self.assertRaises(config.ConfigError):
                    config.load(self.main)

    def test_behind_tip_ignore_is_a_list_of_paths_relative_to_the_root(self):
        self.assertEqual(config.load(self.main).merge["behind_tip_ignore"], [])  # empty by default
        for bad in ("docs", [""], ["/docs"], ["../docs"], [":!docs"], [3]):
            with self.subTest(bad=bad):
                self.plane(merge={"behind_tip_ignore": bad})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn("merge.behind_tip_ignore", str(cm.exception))
        for every in (".", "./", "./.", "*", "**", "./*"):  # an entry that matches every path, named
            with self.subTest(every=every):
                self.plane(merge={"behind_tip_ignore": ["docs/notes", every]})
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.main)
                self.assertIn(f"merge.behind_tip_ignore: {every!r} matches every path", str(cm.exception))
        self.plane(parallel={"behind_tip_ignore": ["docs"]})  # the setting lives under merge: not read there
        with redirect_stderr(io.StringIO()):
            self.assertEqual(config.load(self.main).merge["behind_tip_ignore"], [])
        self.plane(merge={"behind_tip_ignore": ["docs/notes", "CHANGELOG.md"]})
        cfg = config.load(self.main)
        self.assertEqual((cfg.merge["behind_tip_ignore"], cfg.merge["command"]), (["docs/notes", "CHANGELOG.md"], None))


class MergeAndAuth(WtFixture, unittest.TestCase):
    def test_auth_check_runs_probes_and_claim_refuses_on_a_failure(self):
        self.plane(auth_check={"probes": [{"id": "ok", "cmd": "true"}, {"id": "token", "cmd": "echo expired; exit 1"}]})
        code, body, _, _ = self.ccp("auth", "check", root=self.main)
        self.assertEqual(code, 1)
        self.assertEqual([(p["id"], p["ok"]) for p in body["probes"]], [("ok", True), ("token", False)])
        self.assertTrue((self.q / "auth" / "status.json").is_file())
        code, _, _, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, lifecycle.EXIT_AUTH)
        self.assertIn("token (exit 1)", err)
        self.assertFalse((self.q / "tasks" / "0002-second.json").exists() and
                         json.loads((self.q / "tasks" / "0002-second.json").read_text()).get("lease_holder"))

    def test_no_probes_means_auth_check_is_ok(self):
        code, body, _, _ = self.ccp("auth", "check", root=self.main)
        self.assertEqual((code, body["ok"]), (0, True))



class ReviewFixes(WtFixture, unittest.TestCase):
    """PR review of §12.1: exit code, kept worktrees, heads, missing paths, background up, prune, names."""

    def test_auth_exit_code_differs_from_the_parallel_carry_on_code(self):
        from ccp import parallel
        self.assertNotEqual(lifecycle.EXIT_AUTH, parallel.EXIT_SLOTS)
        self.assertNotIn(lifecycle.EXIT_AUTH, (0, 1, 2, 3, 4, 5, 6, 7, 75))

    def test_drop_and_release_keep_the_worktree(self):
        self.ccp("tasks", "claim", "0002")
        code, body, _, err = self.ccp("tasks", "release", "0002", "--reason", "too early")
        self.assertEqual(code, 0, err)
        self.assertTrue((self.main / ".plane-runtime" / "impl-0002").is_dir())
        self.assertTrue(any("worktree" in w and "kept" in w for w in body["warnings"]))

    def test_gc_spares_a_leased_task(self):
        self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps(
            {"task_id": "0002-second", "status": "dropped", "lease_holder": "runner"}))
        self.assertEqual(self.wt("gc")[1]["removed"], [])

    def test_an_existing_worktree_at_another_head_is_refused(self):
        first = self.head()
        self.write("x.txt", "x")
        git(self.main, "add", "x.txt")
        git(self.main, "commit", "-q", "-m", "x")
        git(self.main, "push", "-q", "origin", "main")
        self.wt("create", "--kind", "ver", "--task", "0002", "--sha", first, "--name", "ver-0002")
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "ver-0002")
        self.assertEqual(code, 3)
        self.assertIn("not " + self.head()[:12], err)
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002", "--sha", first, "--name", "ver-0002")[0], 0)

    def test_teardown_is_skipped_when_the_worktree_is_gone(self):
        marker = self.main / "ran-in-main"
        self.plane(env={"teardown": f"touch {marker}"})
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        git(self.main, "worktree", "remove", "--force", str(self.main / ".plane-runtime" / name))
        code, _, _, err = self.wt("remove", name)
        self.assertEqual(code, 0)
        self.assertIn("were not run", err)
        self.assertFalse(marker.exists())

    def test_up_that_backgrounds_a_server_returns_and_logs(self):
        self.plane(env={"up": "(sleep 20; echo late) & echo started"})
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        t = time.time()
        code, _, _, err = self.wt("up", name)
        self.assertLess(time.time() - t, 10, "up waited for the background server")
        self.assertEqual(code, 0, err)
        self.assertIn("started", (self.q / "worktrees" / f"{name}.up.log").read_text())

    def test_path_fields_are_quoted_and_raw_in_the_environment(self):
        self.plane(env={"setup": 'printf "%s|%s" {worktree} "$CCP_WT_WORKTREE" > fields.txt'})
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        p = self.main / ".plane-runtime" / name
        self.assertEqual((p / "fields.txt").read_text(), f"{p}|{p}")

    def test_create_prunes_a_stale_registration_and_retries_a_taken_name(self):
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        import shutil
        shutil.rmtree(self.main / ".plane-runtime" / name)  # gone from disk, still registered with git
        (self.q / "worktrees" / f"{name}.json").unlink()
        code, body, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, err)
        self.assertEqual(body["name"], name)  # the stale registration was pruned, the name reused

    def test_a_default_name_taken_meanwhile_moves_to_the_next(self):
        import subprocess
        from unittest import mock
        real = wt.git
        calls = {"n": 0}

        def racing(cwd, *args, **kw):
            if args[:2] == ("worktree", "add") and calls["n"] == 0:
                calls["n"] += 1  # another worker made ver-0002 between the name check and the add
                Path(args[-2]).mkdir(parents=True)
                return subprocess.CompletedProcess(args, 128, "", f"fatal: '{args[-2]}' already exists")
            return real(cwd, *args, **kw)

        with mock.patch.object(wt, "git", racing):
            st = wt.create(config.load(self.main), self.q, "0002-second", "ver", self.head())
        self.assertEqual((st["name"], st["round"]), ("ver-0002-2", 2))
        self.assertTrue(Path(st["path"]).is_dir())


OWN_CCP = """\
import json, os, signal, sys
from pathlib import Path
if sys.argv[1:2] == ["hello"]:
    Path(__file__).with_name("ran.json").write_text(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}))
    sys.exit(7)
if sys.argv[1:2] == ["die"]:
    os.kill(os.getpid(), signal.SIGTERM)
sys.exit(2)
"""


class SingleRunnerWorktree(WtFixture, unittest.TestCase):
    """§12.1: the one runner's worktree (derived, §8.3) is made by its spawn or by `ccp tasks worktree`
    without a slot, detached at the integration tip; an existing one that holds no task is moved to the
    tip, and one that holds something is kept as it is, with a warning."""

    def setUp(self):
        super().setUp()
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text()
                                             + f"product_root: {self.main}\n")
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        git(self.main, "worktree", "remove", "--force", str(self.runner))  # the fixture's: the spawn makes its own
        self.solo = self.main / ".plane-runtime" / "runner"  # `worktrees.dir` is the constant; the runner is `runner` in it (§8.3)

    def spawn(self, *extra: str):
        r = subprocess.run(["bash", str(PLANE / "scripts" / "team.sh"), "runner", "spawn", "--scope", "0002-second", *extra],
                           capture_output=True, text=True, env=dict(os.environ))
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith("{") else None), r.stderr

    def detached(self, path: Path) -> bool:
        return subprocess.run(["git", "-C", str(path), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode == 1

    def advance_tip(self) -> str:
        self.write("later.txt", "later\n")
        git(self.main, "add", "later.txt")
        git(self.main, "commit", "-q", "-m", "later")
        git(self.main, "push", "-q", "origin", "main")
        return self.head()

    def made_at_the_old_tip(self) -> str:
        """The runner worktree made by `ccp tasks worktree`, then the tip advanced past it; the old tip."""
        self.assertEqual(self.ccp("tasks", "worktree", root=self.main)[0], 0)
        tip = self.head()
        self.assertNotEqual(self.advance_tip(), tip)
        return tip

    def test_the_spawn_makes_it_at_the_tip_and_a_respawn_moves_it_to_the_new_tip(self):
        self.assertFalse(self.solo.exists())
        tip = self.head()
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"], {"path": str(self.solo), "made": True, "moved": False})
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)
        self.assertTrue(self.detached(self.solo))
        new = self.advance_tip()
        self.assertNotEqual(new, tip)
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"], {"path": str(self.solo), "made": False, "moved": True})
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), new)
        self.assertTrue(self.detached(self.solo))
        self.assertNotIn("left as it is", err)
        code, res, err = self.spawn()  # at the tip already: nothing to move
        self.assertEqual((code, res["runner_worktree"]["moved"]), (0, False), err)

    def test_a_spawn_dry_run_after_the_tip_advances_leaves_it_where_it_was(self):
        tip = self.made_at_the_old_tip()
        code, _, err = self.spawn("--dry-run")
        self.assertEqual(code, 0, err)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

    def test_a_spawn_keeps_one_with_an_untracked_file_and_warns(self):
        tip = self.made_at_the_old_tip()
        (self.solo / "note.txt").write_text("left by a step\n")
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"],
                         {"path": str(self.solo), "made": False, "moved": False, "kept": "has changes"})
        self.assertIn(wt.kept_warning(self.solo, "has changes"), res["warnings"])
        self.assertIn(wt.kept_warning(self.solo, "has changes"), err)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)
        self.assertTrue((self.solo / "note.txt").is_file())

    def test_a_spawn_keeps_one_on_a_branch_and_warns(self):
        tip = self.made_at_the_old_tip()
        git(self.solo, "checkout", "-q", "-b", "side")
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"]["kept"], "on branch side")
        self.assertIn(wt.kept_warning(self.solo, "on branch side"), res["warnings"])
        self.assertEqual((git(self.solo, "rev-parse", "HEAD"), git(self.solo, "symbolic-ref", "--short", "HEAD")),
                         (tip, "side"))

    def test_a_spawn_that_cannot_make_it_warns_and_goes_on(self):
        self.solo.mkdir(parents=True)
        (self.solo / "x").write_text("x")
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual((res["runner_worktree"]["made"], res["actions"][-1]["action"]), (False, "spawn_teammate"))
        self.assertIn("not a working tree", res["runner_worktree"]["error"])
        self.assertIn("runner worktree", err)
        self.assertTrue(any("ccp tasks worktree" in w for w in res["warnings"]))
        self.assertEqual(sorted(p.name for p in self.solo.iterdir()), ["x"])  # the directory is left as it was
        self.assertEqual(json.loads((self.q / "work.json").read_text())["status"], "running")

    def test_tasks_worktree_without_a_slot_makes_the_one_runners_and_moves_it_to_the_new_tip(self):
        code, body, out, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["worktree"], body["made"], body["moved"], body["slot"]), (str(self.solo), True, False, None))
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), self.head())
        self.assertTrue(self.detached(self.solo))
        new = self.advance_tip()
        code, body, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual((code, body["made"], body["moved"]), (0, False, True), err)
        self.assertNotIn("kept", body)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), new)
        self.assertTrue(self.detached(self.solo))

    def test_tasks_worktree_keeps_one_that_holds_something_and_warns_on_stderr(self):
        tip = self.made_at_the_old_tip()
        (self.solo / "note.txt").write_text("left by a step\n")
        code, body, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual((code, body["moved"], body["kept"]), (0, False, "has changes"), err)
        self.assertIn(f"warning: {wt.kept_warning(self.solo, 'has changes')}", err)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)
        (self.solo / "note.txt").unlink()
        git(self.solo, "checkout", "-q", "-b", "side")
        code, body, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual((code, body["kept"]), (0, "on branch side"), err)
        self.assertIn(f"warning: {wt.kept_warning(self.solo, 'on branch side')}", err)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

    def test_a_failed_fetch_or_checkout_keeps_it_with_the_git_error(self):
        tip = self.made_at_the_old_tip()
        path, made, moved, kept = wt.runner_worktree(self.main, str(self.solo), "no-such-branch")
        self.assertEqual((path, made, moved), (self.solo, False, False))
        self.assertTrue(kept and "\n" not in kept, kept)
        git(self.main, "remote", "set-url", "origin", str(self.main / "no-such-origin"))
        _, _, moved, kept = wt.runner_worktree(self.main, str(self.solo), "main")
        self.assertFalse(moved)
        self.assertTrue(kept and "\n" not in kept, kept)
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

    def test_a_status_that_fails_keeps_it_with_the_git_error(self):
        tip = self.made_at_the_old_tip()
        real = wt.git

        def failing_status(cwd, *args, **kw):
            if args[:1] == ("status",):
                return subprocess.CompletedProcess(["git", *args], 128, "", "fatal: index file corrupt\nmore\n")
            return real(cwd, *args, **kw)
        with mock.patch.object(wt, "git", failing_status):
            _, made, moved, kept = wt.runner_worktree(self.main, str(self.solo), "main")
        self.assertEqual((made, moved, kept), (False, False, "fatal: index file corrupt"))
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

    def test_what_an_existing_runner_worktree_holds(self):
        self.assertIsNone(wt.runner_worktree_holds("", ""))
        self.assertEqual(wt.runner_worktree_holds("refs/heads/side", ""), "on branch side")
        self.assertEqual(wt.runner_worktree_holds("refs/heads/side", "?? x\n"), "on branch side")
        self.assertEqual(wt.runner_worktree_holds("", "?? x\n"), "has changes")
        self.assertEqual(wt.runner_worktree_holds("", " M a.txt\n"), "has changes")

    def test_tasks_worktree_without_a_slot_refuses_beside_slots_or_with_no_product_root(self):
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runners": {"runner-1": {"bound_name": "runner-1"}}}))
        code, _, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 2)
        self.assertIn("--runner", err)
        (self.q / "work.json").write_text(json.dumps(w))
        (self.q / "project.yaml").write_text("project_id: demo\nintegration_branch: main\n")
        code, _, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 2)
        self.assertIn("names no product_root", err)
        self.assertFalse(self.solo.exists())


class ExecOwnCcp(WtFixture, unittest.TestCase):
    """`ccp wt exec`: a worktree's own bin/ccp, with a subcommand the installed ccp lacks."""

    def made(self) -> tuple[str, Path]:
        name = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())[1]["name"]
        path = self.main / ".plane-runtime" / name
        (path / "bin").mkdir(exist_ok=True)
        (path / "bin" / "ccp").write_text(OWN_CCP)
        return name, path

    def test_exec_runs_the_named_worktrees_ccp_with_its_arguments_verbatim(self):
        name, path = self.made()
        with self.assertRaises(SystemExit):  # the installed ccp has no such subcommand
            self.ccp("hello")
        code, _, _, err = self.wt("exec", name, "--", "hello", "--print", "--root", "x")
        self.assertEqual(code, 7, err)
        ran = json.loads((path / "bin" / "ran.json").read_text())
        self.assertEqual(ran, {"argv": ["hello", "--print", "--root", "x"], "cwd": str(Path.cwd())})

    def test_exec_without_a_name_runs_this_checkouts_ccp_even_when_its_plane_json_does_not_load(self):
        _, path = self.made()
        (path / "docs" / "delivery" / "plane.json").write_text("{not json")
        code, _, _, err = self.ccp("wt", "exec", "--", "hello", root=path)
        self.assertEqual(code, 7, err)
        self.assertTrue((path / "bin" / "ran.json").is_file())

    def test_print_prints_the_path_and_runs_nothing(self):
        name, path = self.made()
        code, _, body, err = self.wt("exec", name, "--print")
        self.assertEqual((code, body.strip()), (0, str(path / "bin" / "ccp")), err)
        self.assertEqual(self.wt("exec", name, "--print", "--", "hello")[0], 2)
        self.assertFalse((path / "bin" / "ran.json").exists())

    def test_a_timeout_is_refused_and_nothing_runs(self):
        name, path = self.made()
        for value in ("abc", "5"):
            code, _, body, err = self.wt("exec", name, "--timeout", value, "--", "hello")
            self.assertEqual((code, body), (2, ""), err)
            self.assertIn("--timeout", err)
            self.assertNotIn("Traceback", err)
        self.assertEqual(self.wt("exec", name, "--timeout", "abc", "--print")[:3:2], (2, ""))
        self.assertFalse((path / "bin" / "ran.json").exists())

    def test_a_signal_ending_it_is_128_plus_the_signal(self):
        name, _ = self.made()
        self.assertEqual(self.wt("exec", name, "--", "die")[0], 143)

    def test_refusals(self):
        name, path = self.made()
        self.assertEqual(self.wt("exec", "hello")[0], 2)  # arguments not after `--`
        self.assertEqual(self.wt("exec", "rev-0099", "--", "hello")[0], 3)  # not recorded
        (path / "bin" / "ccp").unlink()
        code, _, _, err = self.wt("exec", name, "--", "hello")
        self.assertEqual(code, 3)
        self.assertIn("bin/ccp", err)

    def test_a_name_with_no_queue_root_refuses(self):
        name, path = self.made()
        with mock.patch.dict(os.environ):
            os.environ.pop("QUEUE_ROOT")
            code, _, _, err = self.wt("exec", name, "--", "hello")
        self.assertEqual(code, 2, err)
        self.assertIn("QUEUE_ROOT", err)
        self.assertFalse((path / "bin" / "ran.json").exists())

    def test_no_name_outside_a_git_checkout_refuses(self):
        outside = Path(tempfile.mkdtemp(dir=self._tmp.name))
        here = os.getcwd()
        os.chdir(outside)
        self.addCleanup(os.chdir, here)
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(outside.parent)}), \
                redirect_stdout(out), redirect_stderr(err):
            os.environ.pop("CCP_ROOT", None)
            code = cli.main(["wt", "exec", "--", "hello"])
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("not inside a git checkout", err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_neither_a_name_nor_a_checkout_refuses(self):
        from ccp.queue import QueueError
        with self.assertRaises(QueueError) as cm:
            wt.own_ccp(None)
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("name a worktree or a checkout", str(cm.exception))

    def test_the_reviewer_and_verifier_briefs_say_print_shows_which_ccp_runs(self):
        for seat in ("reviewer", "verifier"):
            text = " ".join((PLANE / "plugin" / "agents" / f"delivery-{seat}.md").read_text().split())
            self.assertIn("`ccp wt exec --print` shows which `ccp` that runs", text, seat)
            self.assertIn("`$CCP_ROOT`", text, seat)


class Shallow(WtFixture, unittest.TestCase):
    """`ccp wt create --shallow`: a depth-1 clone at --sha, for a check that must pass without git history."""

    def setUp(self):
        super().setUp()
        for n in (2, 3):
            self.write(f"c{n}.txt", f"{n}\n")
            git(self.main, "add", f"c{n}.txt")
            git(self.main, "commit", "-q", "-m", f"commit {n}")
        git(self.main, "push", "-q", "origin", "main")

    def shallow(self, sha: str, *extra: str):
        return self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--shallow", *extra)

    def test_it_is_at_the_sha_with_a_history_of_depth_one(self):
        head = self.head()
        self.assertEqual(git(self.main, "rev-list", "--count", head), "3")
        code, body, _, err = self.shallow(head)
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual(git(p, "rev-parse", "HEAD"), head)
        self.assertEqual(git(p, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(git(p, "rev-parse", "--is-shallow-repository"), "true")
        self.assertEqual(git(p, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")  # detached
        self.assertEqual(git(p, "status", "--porcelain"), "")  # the linked .venv is excluded in its own repo
        self.assertTrue((p / ".venv").is_symlink())
        self.assertNotIn(str(p), git(self.main, "worktree", "list"))
        st = json.loads((self.q / "worktrees" / f"{body['name']}.json").read_text())
        self.assertEqual((st["shallow"], st["sha"], st["kind"]), (True, head, "ver"))

    def test_an_older_sha_by_a_short_name_and_setup_runs_there(self):
        self.plane(env={"setup": "git rev-list --count HEAD > depth.txt"})
        older = git(self.main, "rev-parse", "origin/main~1")
        code, body, _, err = self.shallow(older[:10])
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual(git(p, "rev-parse", "HEAD"), older)
        self.assertEqual((p / "depth.txt").read_text().strip(), "1")

    def test_remove_and_close_delete_it(self):
        name = self.shallow(self.head())[1]["name"]
        code, body, _, err = self.wt("remove", name)
        self.assertEqual((code, body["warnings"]), (0, []), err)
        self.assertFalse((self.main / ".plane-runtime" / name).exists())
        self.assertFalse((self.q / "worktrees" / f"{name}.json").exists())
        name = self.shallow(self.head())[1]["name"]
        self.assertEqual(wt.remove_task(config.load(self.main), self.q, "0002-second"), [])
        self.assertFalse((self.main / ".plane-runtime" / name).exists())

    def test_reuse_needs_the_same_depth(self):
        head = self.head()
        name = self.shallow(head)[1]["name"]
        code, again, _, err = self.shallow(head, "--name", name)
        self.assertEqual((code, again["created"]), (0, False), err)
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", head, "--name", name)
        self.assertEqual(code, 3, err)  # a shallow one never stands in for a full one
        full = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", head)[1]["name"]
        code, _, _, err = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", head, "--name", full, "--shallow")
        self.assertEqual(code, 3, err)  # nor a full one for a shallow one
        self.assertIn("full history", err)

    def test_refusals(self):
        head = self.head()
        code, _, _, err = self.wt("create", "--kind", "impl", "--task", "0002", "--shallow")
        self.assertEqual(code, 2, err)
        self.assertFalse((self.main / ".plane-runtime" / "impl-0002").exists())
        code, _, _, err = self.wt("create", "--kind", "base", "--task", "0002", "--sha", head, "--shallow", "--", "true")
        self.assertEqual(code, 125, err)
        self.assertEqual(self.wt("list", "--shallow")[0], 2)
        self.assertEqual(self.wt("create", "--kind", "ver", "--baseline", "--shallow")[0], 2)
        code, _, _, err = self.shallow("f" * 40)
        self.assertEqual(code, 1, err)
        self.assertFalse((self.main / ".plane-runtime" / "ver-0002").exists())
        self.assertEqual(list((self.q / "worktrees").glob("*.json")) if (self.q / "worktrees").is_dir() else [], [])


class ShallowMergeBase(WtFixture, unittest.TestCase):
    """A shallow worktree holds the merge base of its sha and the integration branch, recorded for `ccp mutate --revert`."""

    def shallow(self, sha: str):
        return self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--shallow")

    def test_the_merge_base_is_fetched_into_the_clone_and_recorded(self):
        start = self.head()
        git(self.main, "checkout", "-q", "-b", "task/0002-second")
        self.write("c4.txt", "4\n")
        git(self.main, "add", "c4.txt")
        git(self.main, "commit", "-q", "-m", "the task's change")
        head = git(self.main, "rev-parse", "HEAD")
        git(self.main, "checkout", "-q", "main")
        self.write("c5.txt", "5\n")
        git(self.main, "add", "c5.txt")
        git(self.main, "commit", "-q", "-m", "the integration branch moves on")
        git(self.main, "push", "-q", "origin", "main")
        code, body, _, err = self.shallow(head)
        self.assertEqual(code, 0, err)
        self.assertNotIn("warning", err)
        p = Path(body["path"])
        st = json.loads((self.q / "worktrees" / f"{body['name']}.json").read_text())
        self.assertEqual((st["merge_base"], body["merge_base"]), (start, start))
        self.assertEqual(git(p, "cat-file", "-t", start), "commit")
        self.assertEqual(git(p, "rev-parse", "HEAD"), head)  # still detached at --sha
        self.assertEqual(git(p, "status", "--porcelain"), "")

    def test_no_merge_base_is_a_warning_and_none_is_recorded(self):
        git(self.main, "checkout", "-q", "--orphan", "lone")
        git(self.main, "commit", "-q", "-m", "no shared history")
        lone = git(self.main, "rev-parse", "HEAD")
        git(self.main, "checkout", "-q", "-f", "main")
        code, body, _, err = self.shallow(lone)
        self.assertEqual(code, 0, err)
        self.assertIn("warning: no merge base", err)
        st = json.loads((self.q / "worktrees" / f"{body['name']}.json").read_text())
        self.assertNotIn("merge_base", st)
        self.assertEqual(git(Path(body["path"]), "rev-parse", "HEAD"), lone)


@unittest.skipUnless(shutil.which("git-lfs"), "git-lfs is not on PATH")
class ShallowLfs(WtFixture, unittest.TestCase):
    """A shallow worktree of a git-LFS repository checks its LFS files out from the main checkout's store."""

    BLOB = "the committed content of an LFS file\n"

    def setUp(self):
        super().setUp()
        gc = Path(self._tmp.name) / "lfs-gitconfig"  # the filter, in the test's own global config only
        gc.write_text("")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gc)  # what ccp's git sees; restored with the fixture's environment
        self.lfs_git(".", "lfs", "install", "--skip-repo")
        self.lfs_git(self.main, "lfs", "track", "data/*.bin")
        self.write("data/blob.bin", self.BLOB)
        self.write("data/other.bin", "another LFS file\n")
        self.lfs_git(self.main, "add", ".gitattributes", "data/blob.bin", "data/other.bin")
        self.lfs_git(self.main, "commit", "-q", "-m", "LFS files")
        self.assertIn("version https://git-lfs.github.com/spec/v1", git(self.main, "show", "HEAD:data/blob.bin"))

    def lfs_git(self, cwd, *args: str) -> str:
        """git with the test's global config, which holds the LFS filter (the fixture's `git` reads none)."""
        return subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True,
                              env={**os.environ, **GIT_ENV, "GIT_CONFIG_GLOBAL": os.environ["GIT_CONFIG_GLOBAL"]}).stdout

    def shallow(self):
        return self.wt("create", "--kind", "ver", "--task", "0002", "--sha", git(self.main, "rev-parse", "HEAD"),
                       "--shallow")

    def test_its_lfs_files_hold_their_content_not_pointers(self):
        code, body, _, err = self.shallow()
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual((p / "data/blob.bin").read_text(), self.BLOB)
        self.assertNotIn("version https://git-lfs.github.com/spec/v1", (p / "data/other.bin").read_text())
        self.assertNotIn("still pointers", err)
        self.assertEqual(self.lfs_git(p, "status", "--porcelain"), "")

    def test_a_file_whose_object_the_store_lacks_stays_a_pointer_with_a_warning(self):
        oid = hashlib.sha256(b"another LFS file\n").hexdigest()
        store = Path(git(self.main, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "lfs" / "objects"
        (store / oid[:2] / oid[2:4] / oid).unlink()
        code, body, _, err = self.shallow()
        self.assertEqual(code, 0, err)
        p = Path(body["path"])
        self.assertEqual((p / "data/blob.bin").read_text(), self.BLOB)
        self.assertIn("version https://git-lfs.github.com/spec/v1", (p / "data/other.bin").read_text())
        self.assertIn("1 git-LFS file(s)", err)
        self.assertIn("git lfs fetch", err)


class LfsStore(unittest.TestCase):
    def test_the_store_is_where_lfs_env_puts_the_objects_else_the_git_dirs_lfs(self):
        with tempfile.TemporaryDirectory() as d:
            main = Path(d).resolve()
            subprocess.run(["git", "init", "-q", str(main)], check=True, capture_output=True)
            real = subprocess.run

            def lfs_env(out: str):
                def run(args, *a, **kw):
                    if args[-2:] == ["lfs", "env"]:
                        return subprocess.CompletedProcess(args, 0, out, "")
                    return real(args, *a, **kw)
                return run

            with mock.patch("subprocess.run", side_effect=lfs_env("LocalMediaDir=/s/lfs/objects\n")):
                self.assertEqual(wt._lfs_store(main), Path("/s/lfs"))
            with mock.patch("subprocess.run", side_effect=lfs_env("")):
                self.assertEqual(wt._lfs_store(main), main / ".git" / "lfs")


class OwnHooks(WtFixture, unittest.TestCase):
    """`ccp wt create --own-hooks` (§12.2): the worktree's hooks and their timeout come from its own plane.json."""

    MAIN_ENV = {"setup": "echo main > hook.txt"}

    def setUp(self):
        super().setUp()
        self.plane(env=self.MAIN_ENV)  # the caller's (main checkout's) plane.json, uncommitted

    def commit(self, plane: str) -> str:
        """A commit off the integration tip whose plane.json reads `plane` (a PR's head)."""
        (self.runner / "docs/delivery/plane.json").write_text(plane)
        git(self.runner, "commit", "-q", "-am", "the PR's own hooks")
        return git(self.runner, "rev-parse", "HEAD")

    def own(self, **env) -> str:
        return self.commit(json.dumps({**self.PLANE_JSON, "env": env}))

    def record(self, name: str) -> dict:
        return json.loads((self.q / "worktrees" / f"{name}.json").read_text())

    def test_the_own_hooks_worktree_runs_the_heads_setup_and_another_the_callers(self):
        sha = self.own(setup="echo head > hook.txt")
        code, ver, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")
        self.assertEqual(code, 0, err)
        code, rev, _, err = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", sha)
        self.assertEqual(code, 0, err)
        self.assertEqual((Path(ver["path"]) / "hook.txt").read_text().strip(), "head")
        self.assertEqual((Path(rev["path"]) / "hook.txt").read_text().strip(), "main")
        self.assertIs(self.record(ver["name"]).get("own_hooks"), True)
        self.assertNotIn("own_hooks", self.record(rev["name"]))

    def test_a_head_whose_plane_json_does_not_load_fails_the_create_and_leaves_nothing(self):
        sha = self.commit("{ not json")
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")
        self.assertEqual(code, 1, err)
        self.assertIn(str(self.main / ".plane-runtime" / "ver-0002" / "docs/delivery/plane.json"), err)
        self.assertFalse((self.main / ".plane-runtime" / "ver-0002").exists())
        self.assertFalse((self.q / "worktrees" / "ver-0002.json").exists())

    def test_the_hook_timeout_is_the_worktrees_own(self):
        sha = self.own(setup="sleep 20", timeout_seconds=1)
        t = time.time()
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")
        self.assertLess(time.time() - t, 15)
        self.assertEqual(code, 1, err)
        self.assertIn("exited 124", err)

    def test_up_down_and_teardown_are_the_worktrees_own(self):
        marker = self.main / "torn-down"
        self.plane(env={**self.MAIN_ENV, "up": "exit 9", "down": "exit 9", "teardown": "exit 9"})
        sha = self.own(up="echo head > up.txt", down="echo head > down.txt", teardown=f"echo head > {marker}")
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")[1]["name"]
        p = self.main / ".plane-runtime" / name
        code, _, _, err = self.wt("up", name)
        self.assertEqual(code, 0, err)
        self.assertEqual((p / "up.txt").read_text().strip(), "head")
        code, body, _, err = self.wt("down", name)
        self.assertEqual((code, body["warnings"]), (0, []), err)
        self.assertEqual((p / "down.txt").read_text().strip(), "head")
        code, body, _, err = self.wt("remove", name)
        self.assertEqual((code, body["warnings"]), (0, []), err)
        self.assertEqual(marker.read_text().strip(), "head")

    def test_on_down_and_remove_an_own_plane_json_that_does_not_load_is_a_warning_and_the_hook_skipped(self):
        marker = self.main / "torn-down"
        self.plane(env={**self.MAIN_ENV, "down": f"touch {marker}", "teardown": f"touch {marker}"})
        sha = self.own(setup="true")
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")[1]["name"]
        p = self.main / ".plane-runtime" / name
        (p / "docs/delivery/plane.json").write_text("{ not json")
        code, body, _, err = self.wt("down", name)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.record(name)["state"], "down")
        self.assertTrue(any("plane.json" in w for w in body["warnings"]), body)
        code, body, _, err = self.wt("remove", name)
        self.assertEqual(code, 0, err)
        self.assertTrue(any("plane.json" in w for w in body["warnings"]), body)
        self.assertFalse(p.exists())
        self.assertFalse((self.q / "worktrees" / f"{name}.json").exists())
        self.assertFalse(marker.exists())  # never the caller's hooks in their place

    def test_an_own_hooks_worktree_gone_from_disk_warns_its_hooks_were_not_run(self):
        self.plane(env={})  # the caller declares no hooks; the worktree's own are unknown once it is gone
        sha = self.own(teardown="true")
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")[1]["name"]
        git(self.main, "worktree", "remove", "--force", str(self.main / ".plane-runtime" / name))
        code, _, _, err = self.wt("remove", name)
        self.assertEqual(code, 0, err)
        self.assertIn("were not run", err)

    def test_a_base_run_takes_its_hooks_from_the_merge_base(self):
        head = self.head()  # its merge base is the tip, whose committed plane.json declares no setup
        code, _, out, err = self.ccp("wt", "create", "--kind", "base", "--task", "0002", "--sha", head, "--own-hooks",
                                     "--", "sh", "-c", "test ! -e hook.txt", root=self.main)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("wt", "create", "--kind", "base", "--task", "0002", "--sha", head,
                                     "--", "sh", "-c", "test ! -e hook.txt", root=self.main)
        self.assertEqual(code, 1, out + err)  # without it, the caller's setup wrote hook.txt

    def test_reuse_needs_the_same_hooks_and_the_flag_is_only_for_create(self):
        sha = self.own(setup="true")
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--own-hooks")[0], 0)
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--name", "ver-0002")
        self.assertEqual(code, 3, err)
        self.assertIn("own hooks", err)
        code, body, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", sha, "--name", "ver-0002",
                                     "--own-hooks")
        self.assertEqual((code, body["created"]), (0, False), err)
        self.assertEqual(self.wt("create", "--kind", "rev", "--task", "0002", "--sha", sha, "--name", "rev-0002")[0], 0)
        code, _, _, err = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", sha, "--name", "rev-0002",
                                  "--own-hooks")
        self.assertEqual(code, 3, err)
        self.assertEqual(self.wt("create", "--kind", "ver", "--baseline", "--own-hooks")[0], 2)
        self.assertFalse((self.main / ".plane-runtime" / "ver-baseline").exists())
        self.assertEqual(self.wt("list", "--own-hooks")[0], 2)
        self.assertEqual(self.wt("remove", "ver-0002", "--own-hooks")[0], 2)
        self.assertTrue((self.main / ".plane-runtime" / "ver-0002").is_dir())


if __name__ == "__main__":
    unittest.main()
