"""The local PR host adapter (ADR-0040 D3, D5; SPEC §4.5): plane.json `pr_host.adapter: local` keeps each PR's
record in the queue and opens, reads, merges and confirms it with git alone, on a scratch product with a bare
origin and a scratch queue; no `gh` can run."""
from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ccp import config, prhost
from tests.toolkit_fixture import PLANE, ToolkitFixture, git

PR_SCHEMA = json.loads((PLANE / "contracts" / "pr_record.schema.json").read_text())
BRANCH = "task/0002-second"


class LocalHost(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        nogh = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(Path(self._tmp.name) / "no-such-gh")})
        nogh.start()
        self.addCleanup(nogh.stop)
        self.wt = self.main / config.WORKTREES_DIR / "impl-0002"

    def cfg(self) -> config.Config:
        return config.load(self.runner)

    def push_work(self, name: str = "feature.txt", text: str = "built\n") -> str:
        """Claim 0002 (once), commit `name` on its branch, push it: the head."""
        if not self.wt.exists():
            self.ccp("tasks", "claim", "0002")
        (self.wt / name).write_text(text)
        git(self.wt, "add", name)
        git(self.wt, "commit", "-q", "-m", f"Task 0002: {name}")
        git(self.wt, "push", "-q", "-u", "origin", BRANCH)
        return git(self.wt, "rev-parse", "HEAD")

    def open_pr(self, body: str = "Task: 0002-second\n") -> tuple[int, str, str]:
        code, _, out, err = self.ccp("pr", "open", "--branch", BRANCH, "--title", "Task 0002: second",
                                     "--body-file", "-", stdin=body)
        return code, out, err

    def record(self, n: int) -> dict:
        return json.loads((self.q / prhost.PRS_DIR / f"{n}.json").read_text())

    def origin_tip(self) -> str:
        return git(self.main, "ls-remote", str(self.origin), "refs/heads/main").split()[0]

    def approve(self, pr: str, head: str) -> None:
        self.ccp("prompt", "verify", "0002", "--pr", pr, "--head", head)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)

    def test_a_task_pr_opens_reads_is_edited_merged_and_confirmed_with_git_alone(self):
        head = self.push_work()
        code, out, err = self.open_pr()
        self.assertEqual((code, out.strip()), (0, "1"), err)
        rec = self.record(1)
        self.assertEqual(set(rec), set(PR_SCHEMA["required"]))
        self.assertEqual((rec["branch"], rec["base"], rec["head"], rec["state"]), (BRANCH, "main", head, "open"))

        code, _, out, err = self.ccp("pr", "view", "1", "--json")
        self.assertEqual(code, 0, err)
        facts = json.loads(out)
        self.assertEqual((facts["number"], facts["state"], facts["head"], facts["branch"]), (1, "open", head, BRANCH))
        self.assertEqual(facts["body"], "Task: 0002-second\n")

        code, _, out, err = self.ccp("pr", "diff", "1")
        self.assertEqual(code, 0, err)
        self.assertIn("+++ b/feature.txt", out)

        code, _, out, err = self.ccp("pr", "edit", "1", "--body-file", "-", stdin="Task: 0002-second\nrepaired\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.record(1)["body"], "Task: 0002-second\nrepaired\n")

        self.approve("1", head)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "1")
        self.assertEqual(code, 0, out + err)
        rec = self.record(1)
        self.assertEqual(rec["state"], "merged")
        self.assertTrue(rec["merged_at"])
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main~1"), rec["merge_commit"])
        self.assertEqual(git(self.main, "log", "-1", "--format=%s", rec["merge_commit"]), "Task 0002: Second (#1)")
        self.assertEqual(git(self.main, "show", f"{rec['merge_commit']}:feature.txt"), "built")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), body["reconcile_sha"])
        self.assertEqual(prhost.confirm(self.cfg(), "1").merge_commit, rec["merge_commit"])

    def test_view_reads_the_head_a_later_push_gave_the_branch_and_saves_it(self):
        self.push_work()
        self.open_pr()
        later = self.push_work("fix.txt")  # a fix round's push after the PR opened
        code, _, out, err = self.ccp("pr", "view", "1", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["head"], later)
        self.assertEqual(self.record(1)["head"], later)

    def test_merge_records_its_own_squash_commit_as_merged_at_its_time(self):
        head = self.push_work()
        self.open_pr()
        r = prhost.merge(self.cfg(), "1", head, "0002-second")
        self.assertTrue(r.ok, r.message)
        rec = self.record(1)  # read straight from the queue: no view or confirm has run since the merge
        tip = self.origin_tip()
        self.assertEqual((rec["merge_commit"], rec["state"]), (tip, "merged"))
        when = int(git(self.main, "show", "-s", "--format=%ct", tip))
        self.assertEqual(rec["merged_at"], datetime.fromtimestamp(when, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    def test_merge_refuses_a_head_that_is_not_the_branchs_and_records_nothing(self):
        first = self.push_work()
        self.open_pr()
        self.push_work("more.txt")  # the branch moved on after the head was verified
        tip = self.origin_tip()
        r = prhost.merge(self.cfg(), "1", first, "0002-second")
        self.assertFalse(r.ok)
        self.assertIn(first[:12], r.message)
        self.assertEqual(self.origin_tip(), tip)
        rec = self.record(1)
        self.assertEqual((rec["state"], rec["merge_commit"]), ("open", ""))

    def test_open_refuses_a_second_record_for_one_branch(self):
        self.push_work()
        self.assertEqual(self.open_pr()[0], 0)
        code, _, err = self.open_pr()
        self.assertEqual(code, 1)
        self.assertIn("#1", err)
        self.assertEqual(sorted(p.name for p in (self.q / prhost.PRS_DIR).glob("*.json")), ["1.json"])

    def test_open_refuses_a_branch_that_is_not_on_origin(self):
        self.ccp("tasks", "claim", "0002")
        code, _, err = self.open_pr()
        self.assertEqual(code, 1)
        self.assertIn(BRANCH, err)
        self.assertEqual(list((self.q / prhost.PRS_DIR).glob("*.json")), [])

    def test_numbers_follow_the_highest_held(self):
        self.push_work()
        prs = self.q / prhost.PRS_DIR
        prs.mkdir(parents=True, exist_ok=True)
        (prs / "41.json").write_text(json.dumps({**self.record_like(41), "branch": "task/0001-first",
                                                 "state": "merged"}))
        code, out, err = self.open_pr()
        self.assertEqual((code, out.strip()), (0, "42"), err)

    def record_like(self, n: int) -> dict:
        return {"number": n, "branch": BRANCH, "base": "main", "title": "t", "body": "", "head": "",
                "state": "open", "opened_at": "2026-01-01T00:00:00Z", "merged_at": None, "merge_commit": ""}

    def test_a_refused_push_names_the_rerun_of_close_and_records_nothing_merged(self):
        head = self.push_work()
        self.open_pr()
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do [ \"$ref\" = refs/heads/main ] && exit 1; done\nexit 0\n")
        hook.chmod(0o755)
        tip = self.origin_tip()
        r = prhost.merge(self.cfg(), "1", head, "0002-second")
        self.assertFalse(r.ok)
        self.assertFalse(r.conflict)
        self.assertIn("ccp tasks close 0002-second --pr 1", r.message)
        self.assertEqual(self.origin_tip(), tip)
        self.assertEqual(self.record(1)["merge_commit"], "")
        self.assertEqual(prhost.confirm(self.cfg(), "1").state, "open")

    def test_a_squash_that_conflicts_with_the_tip_is_a_conflict(self):
        head = self.push_work()
        self.open_pr()
        (self.runner / "feature.txt").write_text("other\n")
        git(self.runner, "add", "feature.txt")
        git(self.runner, "commit", "-q", "-m", "something else")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        r = prhost.merge(self.cfg(), "1", head, "0002-second")
        self.assertFalse(r.ok)
        self.assertTrue(r.conflict)
        self.assertEqual(self.record(1)["state"], "open")

    def test_a_merge_made_by_a_merge_command_is_confirmed_by_its_squash_subject(self):
        head = self.push_work()
        self.open_pr()
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "merge", "-q", "--squash", head)
        git(self.runner, "commit", "-q", "-m", "Task 0002: Second (#1)")
        sha = git(self.runner, "rev-parse", "HEAD")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        facts = prhost.confirm(self.cfg(), "1")
        self.assertEqual((facts.state, facts.merge_commit), ("merged", sha))
        self.assertTrue(facts.merged_at)

    def test_a_record_in_the_old_uppercase_words_is_refused_naming_its_file(self):
        prs = self.q / prhost.PRS_DIR
        prs.mkdir(parents=True, exist_ok=True)
        (prs / "1.json").write_text(json.dumps({**self.record_like(1), "state": "OPEN"}))
        code, _, out, err = self.ccp("pr", "view", "1")
        self.assertNotEqual(code, 0, out)
        self.assertIn("1.json", err)
        self.assertEqual(json.loads((prs / "1.json").read_text())["state"], "OPEN")

    def test_view_keeps_the_head_it_saw_when_the_branch_is_gone_and_refuses_an_unknown_pr(self):
        head = self.push_work()
        self.open_pr()
        git(self.wt, "push", "-q", "origin", f":{BRANCH}")
        self.assertEqual(prhost.view(self.cfg(), "1").head, head)
        with self.assertRaises(prhost.HostReadFailed):
            prhost.view(self.cfg(), "2")


class LocalHostWithoutWorktrees(ToolkitFixture, unittest.TestCase):
    """A product whose plane.json sets `worktrees.dir: null` has no merge worktree: the squash is made in a
    temporary one."""
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "pr_host": {"adapter": "local"},
                  "worktrees": {"dir": None, "links": [".venv"]}}

    def setUp(self):
        super().setUp()
        nogh = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(Path(self._tmp.name) / "no-such-gh")})
        nogh.start()
        self.addCleanup(nogh.stop)

    def worktrees(self) -> list[str]:
        return [line for line in git(self.main, "worktree", "list", "--porcelain").splitlines()
                if line.startswith("worktree ")]

    def test_merge_squashes_in_a_temporary_worktree_and_removes_it(self):
        work = Path(self._tmp.name) / "work"
        git(self.main, "worktree", "add", "-q", "-b", BRANCH, str(work), "origin/main")
        (work / "feature.txt").write_text("built\n")
        git(work, "add", "feature.txt")
        git(work, "commit", "-q", "-m", "Task 0002: feature.txt")
        git(work, "push", "-q", "-u", "origin", BRANCH)
        head = git(work, "rev-parse", "HEAD")
        cfg = config.load(self.runner)
        self.assertIsNone(cfg.worktrees["dir"])
        self.assertEqual(prhost.open(cfg, BRANCH, "main", "Task 0002: second", "Task: 0002-second\n"), 1)
        before, runner_head = self.worktrees(), git(self.runner, "rev-parse", "HEAD")

        r = prhost.merge(cfg, "1", head, "0002-second")
        self.assertTrue(r.ok, r.message)
        tip = git(self.main, "ls-remote", str(self.origin), "refs/heads/main").split()[0]
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "log", "-1", "--format=%s", tip), "Task 0002: Second (#1)")
        self.assertEqual(git(self.main, "show", f"{tip}:feature.txt"), "built")
        self.assertEqual(self.worktrees(), before)
        self.assertEqual(git(self.runner, "rev-parse", "HEAD"), runner_head)
        self.assertEqual(prhost.confirm(cfg, "1").merge_commit, tip)


class Selection(unittest.TestCase):
    def test_the_adapter_named_is_the_one_returned_and_github_is_the_default(self):
        self.assertEqual(set(prhost._ADAPTERS), set(config.PR_HOST_ADAPTERS))
        base = config.Config(root=Path("."), project_id="demo", task_log={}, package_docs=None)
        self.assertIsInstance(prhost.adapter(base), prhost.GitHub)
        for name, cls in (("github", prhost.GitHub), ("local", prhost.Local)):
            from dataclasses import replace
            self.assertIsInstance(prhost.adapter(replace(base, pr_host={"adapter": name})), cls)


class UnknownAdapter(ToolkitFixture, unittest.TestCase):
    def test_an_unknown_adapter_is_refused_naming_the_two(self):
        self.write("docs/delivery/plane.json", json.dumps({**self.PLANE_JSON, "pr_host": {"adapter": "forge"}}))
        with self.assertRaises(config.ConfigError) as cm:
            config.load(self.main)
        for word in ("pr_host.adapter", "github", "local", "forge"):
            self.assertIn(word, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
