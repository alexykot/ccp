"""SPEC §16.5 rules 4, 5 and 7 (step 7 of the parallel-runners build): a task merges only from a verified head that contains
the integration tip, the task log's bookkeeping and the product's declared paths aside, and a verifier
is not launched on a head that lacks it; a reconcile that collides with another runner's is rebuilt on
the fresh tip; a freed slot names the idle runners."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from ccp import lifecycle
from tests.test_toolkit import ToolkitFixture, git


class Merging(ToolkitFixture, unittest.TestCase):
    # §16.5 rule 4: close checks it with several runners, verify with any number; commits only under
    # docs/notes/ do not make a head behind the tip
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "parallel": {"max_in_flight": 2},
                  "merge": {"behind_tip_ignore": ["docs/notes"]}}

    def push_to_main(self, rel: str, text: str, msg: str) -> None:
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        p = self.runner / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        git(self.runner, "add", rel)
        git(self.runner, "commit", "-q", "-m", msg)
        git(self.runner, "push", "-q", "origin", "HEAD:main")

    def close(self):
        return self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "it is built.")

    def pushed_head(self) -> str:
        """Claim 0002, commit its work on its branch and push it, unverified: the PR head."""
        self.ccp("tasks", "claim", "0002")
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        git(wt, "add", "feature.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        return git(wt, "rev-parse", "HEAD")

    def verify(self, head: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)

    def one_runner(self) -> None:
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg.pop("parallel")
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        git(self.main, "commit", "-qam", "one runner")
        git(self.main, "push", "-q", "origin", "HEAD:main")

    def test_another_tasks_code_since_the_verify_refuses_the_merge(self):
        self._to_approved_pr()
        self.push_to_main("other.py", "x = 1\n", "Task 0009: other code")
        code, _, out, err = self.close()
        self.assertEqual(code, 1, out + err)
        self.assertIn("behind_tip", err)
        self.assertIn("nothing merged", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_another_tasks_bookkeeping_alone_does_not_hold_it_back(self):
        self._to_approved_pr()
        log = (self.main / "docs/LOG.md").read_text()
        self.push_to_main("docs/LOG.md", log.replace("# Log\n\n", "# Log\n\n**2026-10-28 (runner):** `0009` done.\n\n"),
                          "Reconcile 0009: done")
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])

    def test_a_commit_only_under_a_declared_path_keeps_the_verified_head(self):
        self._to_approved_pr()
        self.push_to_main("docs/notes/today.md", "a lead's note\n", "the lead's doc commit")
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])

    def test_a_commit_that_also_touches_an_undeclared_path_still_refuses(self):
        self._to_approved_pr()
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        for rel in ("docs/notes/today.md", "docs/notesmore.md"):  # a sibling sharing the prefix is not under it
            (self.runner / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.runner / rel).write_text("x\n")
        git(self.runner, "add", "docs")
        git(self.runner, "commit", "-q", "-m", "a note and more")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        code, _, out, err = self.close()
        self.assertEqual(code, 1, out + err)
        self.assertIn("behind_tip", err)
        self.assertIn("`ccp prompt merge 0002-second", err)  # the round that catches up (SPEC §13.2)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_a_tip_that_cannot_be_fetched_refuses_the_merge(self):
        self._to_approved_pr()
        git(self.runner, "remote", "set-url", "origin", str(self.main.parent / "gone.git"))
        code, _, out, err = self.close()
        self.assertEqual(code, 1, out + err)
        self.assertIn("could not be fetched", err)
        self.assertIn("nothing merged", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_verify_refuses_a_head_behind_the_tip(self):
        head = self.pushed_head()
        self.push_to_main("other.py", "x = 1\n", "Task 0009: other code")
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("behind_tip", err)
        self.assertIn("Merge the tip in first", err)
        self.assertIn("`ccp prompt merge 0002-second", err)  # the round that catches up (SPEC §13.2)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened

    def test_verify_launches_on_a_head_behind_only_by_declared_paths_and_the_task_log(self):
        head = self.pushed_head()
        self.push_to_main("docs/notes/today.md", "a lead's note\n", "the lead's doc commit")
        log = (self.main / "docs/LOG.md").read_text()
        self.push_to_main("docs/LOG.md", log.replace("# Log\n\n", "# Log\n\n**2026-10-28 (runner):** `0009` done.\n\n"),
                          "Reconcile 0009: done")
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["run_id"], "0002-second/verify")
        self.assertNotIn("warnings", body)

    def test_verify_warns_and_launches_when_the_head_cannot_be_fetched(self):
        self.pushed_head()
        code, body, out, err = self.verify("c" * 40)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("behind_tip not checked" in w for w in body["warnings"]), body)

    def test_verify_warns_and_launches_when_the_tip_cannot_be_fetched(self):
        head = self.pushed_head()
        git(self.runner, "remote", "set-url", "origin", str(self.main.parent / "gone.git"))
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("behind_tip not checked: origin/main" in w and "close checks it" in w
                            for w in body["warnings"]), body)

    def test_one_runner_close_still_merges_a_verified_head_behind_the_tip(self):
        self.one_runner()
        self._to_approved_pr()
        self.push_to_main("other.py", "x = 1\n", "Task 0009: other code")
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])

    def test_one_runner_verify_refuses_a_head_behind_the_tip(self):
        self.one_runner()
        head = self.pushed_head()
        self.push_to_main("other.py", "x = 1\n", "Task 0009: other code")
        code, _, out, err = self.verify(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("behind_tip", err)
        self.assertIn("Merge the tip in first", err)
        self.assertFalse((self.q / "runs/0002-second/verify.json").exists())  # nothing opened

    def test_one_runner_verify_launches_on_a_head_behind_only_by_declared_paths(self):
        self.one_runner()
        head = self.pushed_head()
        self.push_to_main("docs/notes/today.md", "a lead's note\n", "the lead's doc commit")
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("warnings", body)

    def test_one_runner_verify_warning_does_not_promise_a_close_check(self):
        self.one_runner()
        head = self.pushed_head()
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")  # the runner reads the one-runner config
        git(self.runner, "remote", "set-url", "origin", str(self.main.parent / "gone.git"))
        code, body, out, err = self.verify(head)
        self.assertEqual(code, 0, out + err)
        warns = [w for w in body["warnings"] if "behind_tip not checked: origin/main" in w]
        self.assertTrue(warns, body)
        self.assertFalse(any("close checks it" in w for w in warns), body)

    def test_a_reconcile_that_collides_is_rebuilt_on_the_fresh_tip(self):
        self._to_approved_pr()
        real, calls = lifecycle._push, []

        def another_runner_reconciles_first(cfg, integ):
            calls.append(1)
            if len(calls) == 1:  # meanwhile another runner lands its LOG entry at the same place
                w = self.main / ".rt" / "other"
                git(self.main, "worktree", "add", "-q", "--detach", str(w), "origin/main")
                git(w, "fetch", "-q", "origin")
                git(w, "checkout", "-q", "--detach", "origin/main")
                lp = w / "docs/LOG.md"
                lp.write_text(lp.read_text().replace("# Log\n\n", "# Log\n\n**2026-10-28 (runner):** `0009` done.\n\n"))
                git(w, "commit", "-qam", "Reconcile 0009: done")
                git(w, "push", "-q", "origin", "HEAD:main")
            return real(cfg, integ)

        with mock.patch.object(lifecycle, "_push", side_effect=another_runner_reconciles_first):
            code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(calls), 2)  # rebuilt once
        git(self.main, "fetch", "-q", "origin")
        log = git(self.main, "show", "origin/main:docs/LOG.md")
        self.assertIn("`0009` done.", log)
        self.assertIn("`0002` done: it is built.", log)
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))

    def test_a_close_names_the_idle_runners(self):
        self._to_approved_pr()
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": "runner-1"}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runners": {"runner-1": {}, "runner-2": {"bound_name": "r2"}}}))
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["idle_runners"], ["r2"])  # not runner-1, the closer: it goes on itself

    def test_one_runner_merges_as_before(self):
        self.one_runner()
        self._to_approved_pr()
        self.push_to_main("docs/notes.md", "a lead's note\n", "the lead's doc commit")
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
