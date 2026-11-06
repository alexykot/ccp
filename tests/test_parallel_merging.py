"""SPEC §16.5 rules 4, 5 and 7 (step 7 of the parallel-runners build): a task merges only from a verified head that contains
the integration tip, the task log's bookkeeping aside; a reconcile that collides with another runner's
is rebuilt on the fresh tip; a freed slot names the idle runners."""
from __future__ import annotations

import json
import unittest
from unittest import mock

from ccp import lifecycle
from tests.test_toolkit import ToolkitFixture, git


class Merging(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "parallel": {"max_in_flight": 2}}  # §16.5 rule 4 is several runners'

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
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg.pop("parallel")
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        git(self.main, "commit", "-qam", "one runner")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        self._to_approved_pr()
        self.push_to_main("docs/notes.md", "a lead's note\n", "the lead's doc commit")
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
