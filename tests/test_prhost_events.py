"""The PR host's ledger events (SPEC §23.2, §4.5; ADR-0040 D3): under the local adapter each opening, body edit and
merge of a PR's record appends one `pr` event, a read that only moves the head appends none, and the GitHub adapter,
which writes nothing to the queue, appends none. A scratch product with a bare origin and a scratch queue."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, prhost
from tests.test_toolkit import ToolkitFixture, git

BRANCH = "task/0002-second"


class PrEvents(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        nogh = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(Path(self._tmp.name) / "no-such-gh")})
        nogh.start()
        self.addCleanup(nogh.stop)

    def pr_events(self) -> list[dict]:
        return [e for e in self.events() if e["type"] == "pr"]

    def new_pr_events(self, since: int) -> list[dict]:
        return self.pr_events()[since:]

    def push(self, name: str) -> str:
        """Commit `name` on the claimed task's branch and push it: the head."""
        wt = self.main / config.WORKTREES_DIR / "impl-0002"
        (wt / name).write_text(f"{name}\n")
        git(wt, "add", name)
        git(wt, "commit", "-q", "-m", f"Task 0002: {name}")
        git(wt, "push", "-q", "-u", "origin", BRANCH)
        return git(wt, "rev-parse", "HEAD")

    def open_by_cli(self) -> None:
        code, _, out, err = self.ccp("pr", "open", "--branch", BRANCH, "--title", "Task 0002: Second",
                                     "--body-file", "-", stdin="Task: 0002-second\n")
        self.assertEqual((code, out.strip()), (0, self.PR), err)

    def test_open_and_edit_each_append_one_event_naming_the_pr_and_its_head(self):
        self.ccp("tasks", "claim", "0002")
        head = self.push("feature.txt")
        self.open_by_cli()
        [opened] = self.pr_events()
        self.assertEqual((opened["op"], opened["task_id"], opened["payload"]), ("opened", "0002-second",
                                                                                 {"pr": 1, "head": head}))
        code, _, out, err = self.ccp("pr", "edit", self.PR, "--body-file", "-", stdin="Task: 0002-second\nmore\n")
        self.assertEqual(code, 0, out + err)
        [edited] = self.new_pr_events(1)
        self.assertEqual((edited["op"], edited["task_id"], edited["payload"]), ("edited", "0002-second",
                                                                                 {"pr": 1, "head": head}))

    def test_a_pr_for_a_branch_that_is_not_a_tasks_has_no_task_id_on_its_event(self):
        git(self.runner, "push", "-q", "origin", "HEAD:refs/heads/other")
        code, _, out, err = self.ccp("pr", "open", "--branch", "other", "--title", "t", "--body-file", "-", stdin="b\n")
        self.assertEqual(code, 0, out + err)
        [opened] = self.pr_events()
        self.assertEqual((opened["op"], opened["task_id"]), ("opened", ""))

    def test_a_view_that_only_moves_the_head_appends_none(self):
        self.ccp("tasks", "claim", "0002")
        self.push("feature.txt")
        self.open_by_cli()
        later = self.push("fix.txt")
        code, _, out, err = self.ccp("pr", "view", self.PR, "--json")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.pr_record()["head"], later)
        self.assertEqual([e["op"] for e in self.pr_events()], ["opened"])

    def test_close_appends_one_merged_event_and_a_later_view_none(self):
        head = self._to_approved_pr()
        before = len(self.pr_events())
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR)
        self.assertEqual(code, 0, out + err)
        merged = self.pr_record()["merge_commit"]
        self.assertTrue(merged)
        [ev] = self.new_pr_events(before)
        self.assertEqual((ev["op"], ev["task_id"], ev["payload"]),
                         ("merged", "0002-second", {"pr": 1, "head": head, "merge_commit": merged}))
        for _ in range(2):
            self.assertEqual(self.ccp("pr", "view", self.PR)[0], 0)
        self.assertEqual(len(self.new_pr_events(before)), 1)

    def test_a_read_that_records_the_merge_before_merges_own_write_leaves_it_the_one_event(self):
        self.ccp("tasks", "claim", "0002")
        head = self.push("feature.txt")
        self.open_by_cli()
        locked, calls = prhost.Local._locked, []

        def racing(host: prhost.Local):
            calls.append(host)
            if len(calls) == 2:  # merge's write after its push: a read gets the lock first and finds the squash
                calls.append(host)
                host._read(self.PR)
            return locked(host)

        with mock.patch.object(prhost.Local, "_locked", racing):
            r = prhost.merge(config.load(self.runner), self.PR, head, "0002-second")
        self.assertTrue(r.ok, r.message)
        self.assertEqual([e["op"] for e in self.pr_events()], ["opened", "merged"])
        self.assertEqual(self.pr_record()["state"], "merged")

    def test_a_merge_made_outside_the_adapter_gets_its_one_event_from_the_view_that_finds_it(self):
        self.ccp("tasks", "claim", "0002")
        head = self.push("feature.txt")
        self.open_by_cli()
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "merge", "-q", "--squash", head)
        git(self.runner, "commit", "-q", "-m", "Task 0002: Second (#1)")  # as a merge.command would make it
        sha = git(self.runner, "rev-parse", "HEAD")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        for _ in range(2):
            code, _, out, err = self.ccp("pr", "view", self.PR)
            self.assertEqual(code, 0, out + err)
        self.assertEqual(self.pr_record()["state"], "merged")
        [ev] = self.new_pr_events(1)
        self.assertEqual((ev["op"], ev["payload"]), ("merged", {"pr": 1, "head": head, "merge_commit": sha}))


FAKE_GH = "#!/bin/sh\necho https://example.test/o/r/pull/5\n"


class GitHubWritesNoEvent(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "pr_host": {"adapter": "github"}}

    def test_open_on_github_appends_no_event(self):
        gh = Path(self._tmp.name) / "fake-gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        with mock.patch.dict(os.environ, {"CCP_GH_BIN": str(gh)}):
            code, _, out, err = self.ccp("pr", "open", "--branch", BRANCH, "--title", "Task 0002: Second",
                                         "--body-file", "-", stdin="Task: 0002-second\n")
        self.assertEqual((code, out.strip()), (0, "5"), err)
        self.assertEqual([e for e in self.events() if e["type"] == "pr"], [])


if __name__ == "__main__":
    unittest.main()
