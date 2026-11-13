"""Worktrees and environments (SPEC §12.1): `ccp wt`, env hooks, URLs, merge.command, auth probes."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, lifecycle, wt
from tests.test_toolkit import PLANE, ToolkitFixture, git


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
        path = self.main / ".rt" / "impl-0002"
        self.assertEqual(Path(body["worktree"]["path"]), path)
        self.assertTrue((path / ".venv").is_symlink())
        st = json.loads((self.q / "worktrees" / "impl-0002.json").read_text())
        self.assertEqual((st["kind"], st["task_id"], st["branch"], st["state"]), ("impl", "0002-second", "task/0002-second", "created"))

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

    def test_a_failed_setup_removes_the_half_made_worktree(self):
        self.plane(env={"setup": "echo no database; exit 3"})
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 1)
        self.assertIn("env.setup for ver-0002 exited 3", err)
        self.assertIn("no database", err)
        self.assertFalse((self.main / ".rt" / "ver-0002").exists())
        self.assertFalse((self.q / "worktrees" / "ver-0002.json").exists())

    def test_detached_kinds_need_a_sha_and_names_follow_the_kind(self):
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002")[0], 2)
        self.assertEqual(self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "rev-0002")[0], 2)

    def test_no_worktrees_dir_refuses(self):
        self.plane(adapter={"worktree_dir": None, "worktree_links": [], "post_close": []})
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
        self.assertEqual((p, body["created"]), (self.main / ".rt" / "ver-baseline", True))
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
        self.assertFalse((self.main / ".rt" / "ver-baseline").exists())

    def test_its_name_is_not_a_task_worktree_name(self):
        code, _, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(), "--name", "ver-baseline")
        self.assertEqual(code, 2, err)
        self.assertFalse((self.main / ".rt" / "ver-baseline").exists())

    def test_no_integration_tip_refuses(self):
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: trunk\n")
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
        self.assertTrue((self.main / ".rt" / name / "up.flag").exists())
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
        self.assertFalse((self.main / ".rt" / name).exists())
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
        git(self.main, "worktree", "add", "-q", "--detach", str(self.main / ".rt" / "rev-0002"), self.head())  # pre-§12.1
        listed = {r["name"]: r.get("recorded", True) for r in self.wt("list")[1]}
        self.assertEqual(listed, {"impl-0002": True, "ver-0002": True, "rev-0002": False})
        warnings = wt.remove_task(config.load(self.main), self.q, "0002-second")
        self.assertEqual(warnings, [])
        for n in ("impl-0002", "ver-0002", "rev-0002"):
            self.assertFalse((self.main / ".rt" / n).exists(), n)
        self.assertEqual(list((self.q / "worktrees").glob("*.json")), [])

    def test_gc_forgets_missing_and_removes_finished_tasks(self):
        self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.wt("create", "--kind", "mac", "--task", "0002", "--sha", self.head())
        git(self.main, "worktree", "remove", "--force", str(self.main / ".rt" / "mac-0002"))
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
        path = self.main / ".rt" / f"merge-{nnnn}"
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


class Config(WtFixture, unittest.TestCase):
    def test_legacy_adapter_keys_fold_into_worktrees(self):
        cfg = config.load(self.main)
        self.assertEqual((cfg.worktrees["dir"], cfg.worktrees["links"]), (".rt", [".venv"]))
        self.plane(adapter={"worktree_dir": None, "worktree_links": [], "post_close": []},
                   worktrees={"dir": ".wt", "links": [".venv"]})
        self.assertEqual(config.load(self.main).worktrees["dir"], ".wt")

    def test_bad_blocks_are_refused(self):
        for bad in ({"worktrees": {"dir": ".x"}},  # with the legacy adapter.worktree_dir .rt
                    {"env": {"up": 3}}, {"env": {"timeout_seconds": 0}},
                    {"merge": {"command": "gh pr merge {pr} --squash"}},  # not pinned to the head
                    {"auth_check": {"probes": [{"id": "gh"}]}},
                    {"auth_check": {"probes": [{"id": "a", "cmd": "true"}, {"id": "a", "cmd": "true"}]}},
                    {"worktrees": {"dir": "/abs"}, "adapter": {"worktree_dir": None, "worktree_links": [], "post_close": []}}):
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
        self.plane(parallel={"behind_tip_ignore": ["docs"]})  # the setting lives under merge
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.main)
        self.assertIn("unknown key", str(cm.exception))
        self.plane(merge={"behind_tip_ignore": ["docs/notes", "CHANGELOG.md"]})
        cfg = config.load(self.main)
        self.assertEqual((cfg.merge["behind_tip_ignore"], cfg.merge["command"]), (["docs/notes", "CHANGELOG.md"], None))


class MergeAndAuth(WtFixture, unittest.TestCase):
    def test_merge_command_is_a_template(self):
        self.plane(merge={"command": "echo {pr} {head_sha} {task_id} '{\"literal\": 1}' > merged.txt"})
        r = lifecycle._merge(config.load(self.main), "12", "abc123", "0002-second")
        self.assertEqual(r.returncode, 0)
        self.assertEqual((self.main / "merged.txt").read_text().split(), ["12", "abc123", "0002-second", '{"literal":', "1}"])

    def test_default_merge_is_gh_pinned_to_the_head(self):
        self.write("gh-log", "")
        fake = self.main / "fake-gh"
        fake.write_text(f"#!/bin/sh\necho \"$@\" > {self.main / 'gh-log'}\n")
        fake.chmod(0o755)
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"CCP_GH_BIN": str(fake)}):
            lifecycle._merge(config.load(self.main), "12", "abc123", "0002-second")
        self.assertEqual((self.main / "gh-log").read_text().split(), ["pr", "merge", "12", "--squash", "--match-head-commit", "abc123"])

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
        self.assertTrue((self.main / ".rt" / "impl-0002").is_dir())
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
        git(self.main, "worktree", "remove", "--force", str(self.main / ".rt" / name))
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
        p = self.main / ".rt" / name
        self.assertEqual((p / "fields.txt").read_text(), f"{p}|{p}")

    def test_create_prunes_a_stale_registration_and_retries_a_taken_name(self):
        name = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())[1]["name"]
        import shutil
        shutil.rmtree(self.main / ".rt" / name)  # gone from disk, still registered with git
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
        self.assertEqual(st["name"], "ver-0002-2")
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
    """§12.1: the one runner's worktree (binding `runner.worktree`) is made by its spawn or by
    `ccp tasks worktree` without a slot, detached at the integration tip; an existing one is left alone."""

    def setUp(self):
        super().setUp()
        (self.q / "project.yaml").write_text((self.q / "project.yaml").read_text()
                                             + f"product_root: {self.main}\nrunner:\n  name: runner\n  worktree: .rt/solo\n")
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        self.solo = self.main / ".rt" / "solo"

    def spawn(self):
        r = subprocess.run(["bash", str(PLANE / "scripts" / "team.sh"), "runner", "spawn", "--scope", "0002-second"],
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

    def test_the_spawn_makes_it_at_the_tip_and_a_respawn_leaves_it_alone(self):
        self.assertFalse(self.solo.exists())
        tip = self.head()
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"], {"path": str(self.solo), "made": True})
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)
        self.assertTrue(self.detached(self.solo))
        self.assertNotEqual(self.advance_tip(), tip)
        code, res, err = self.spawn()
        self.assertEqual(code, 0, err)
        self.assertEqual(res["runner_worktree"], {"path": str(self.solo), "made": False})
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

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

    def test_tasks_worktree_without_a_slot_makes_the_one_runners(self):
        code, body, out, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["worktree"], body["made"], body["slot"]), (str(self.solo), True, None))
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), self.head())
        self.assertTrue(self.detached(self.solo))
        tip = self.head()
        self.advance_tip()
        code, body, _, _ = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual((code, body["made"]), (0, False))
        self.assertEqual(git(self.solo, "rev-parse", "HEAD"), tip)

    def test_tasks_worktree_without_a_slot_refuses_beside_slots_or_with_no_runner_worktree(self):
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runners": {"runner-1": {"bound_name": "runner-1"}}}))
        code, _, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 2)
        self.assertIn("--runner", err)
        (self.q / "work.json").write_text(json.dumps(w))
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\nintegration_branch: main\n")
        code, _, _, err = self.ccp("tasks", "worktree", root=self.main)
        self.assertEqual(code, 2)
        self.assertIn("runner.worktree", err)
        self.assertFalse(self.solo.exists())


class ExecOwnCcp(WtFixture, unittest.TestCase):
    """`ccp wt exec`: a worktree's own bin/ccp, with a subcommand the installed ccp lacks."""

    def made(self) -> tuple[str, Path]:
        name = self.wt("create", "--kind", "rev", "--task", "0002", "--sha", self.head())[1]["name"]
        path = self.main / ".rt" / name
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
        self.assertFalse((self.main / ".rt" / name).exists())
        self.assertFalse((self.q / "worktrees" / f"{name}.json").exists())
        name = self.shallow(self.head())[1]["name"]
        self.assertEqual(wt.remove_task(config.load(self.main), self.q, "0002-second"), [])
        self.assertFalse((self.main / ".rt" / name).exists())

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
        self.assertFalse((self.main / ".rt" / "impl-0002").exists())
        code, _, _, err = self.wt("create", "--kind", "base", "--task", "0002", "--sha", head, "--shallow", "--", "true")
        self.assertEqual(code, 125, err)
        self.assertEqual(self.wt("list", "--shallow")[0], 2)
        self.assertEqual(self.wt("create", "--kind", "ver", "--baseline", "--shallow")[0], 2)
        code, _, _, err = self.shallow("f" * 40)
        self.assertEqual(code, 1, err)
        self.assertFalse((self.main / ".rt" / "ver-0002").exists())
        self.assertEqual(list((self.q / "worktrees").glob("*.json")) if (self.q / "worktrees").is_dir() else [], [])


if __name__ == "__main__":
    unittest.main()
