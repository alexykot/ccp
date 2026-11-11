"""Worktrees and environments (SPEC §12.1): `ccp wt`, env hooks, URLs, merge.command, auth probes."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from ccp import config, lifecycle, wt
from tests.test_toolkit import ToolkitFixture, git


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


if __name__ == "__main__":
    unittest.main()
