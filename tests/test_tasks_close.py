"""`ccp tasks close` reconciles in a worktree of its own (SPEC §10.5): the checkout it runs from, the
product's main checkout included, keeps its branch, HEAD and index."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

if __name__ == "__main__":  # run as a script: the checkout's root is the import root, and the tests' fence comes first
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import tests  # noqa: F401

from ccp import lifecycle, prhost  # noqa: E402
from tests.test_toolkit import PLANE, ToolkitFixture, git  # noqa: E402


class CloseKeepsTheCaller(ToolkitFixture, unittest.TestCase):

    def _state(self, checkout):
        return (git(checkout, "rev-parse", "HEAD"), git(checkout, "symbolic-ref", "-q", "--short", "HEAD")
                if checkout == self.main else None, git(checkout, "status", "--porcelain"))

    def test_close_from_the_main_checkout_leaves_it_on_its_branch_at_its_head(self):
        self._to_approved_pr()
        before = self._state(self.main)
        self.assertEqual(before[1:], ("main", ""))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(self.main), before)
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), body["reconcile_sha"])
        self.assertTrue(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile 0002"))
        self.assertIn("status: done", git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md"))
        self.assertFalse((self.main / ".plane-runtime" / "merge-0002").exists())

    def test_close_from_the_runner_worktree_ends_it_at_the_reconcile_and_leaves_the_main_checkout(self):
        self._to_approved_pr()
        main_before = self._state(self.main)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self._state(self.runner), (body["reconcile_sha"], None, ""))
        self.assertEqual(self._state(self.main), main_before)
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(git(self.main, "rev-parse", "origin/main"), body["reconcile_sha"])
        self.assertNotIn("merge-0002", git(self.main, "worktree", "list"))

    def test_a_failed_reconcile_is_discarded_by_the_rerun_in_the_merge_worktree(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["touch hook-ran && exit 3"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a failing hook")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        git(self.main, "pull", "-q", "origin", "main")
        self._to_approved_pr()
        before = self._state(self.main)
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self._state(self.main), before)
        merge_wt = self.main / ".plane-runtime" / "merge-0002"
        self.assertTrue((merge_wt / "hook-ran").exists())  # the half-done reconcile is in close's own worktree
        cfg["reconcile"]["hooks"] = []
        (self.main / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.main, "commit", "-qam", "the hook fixed")
        git(self.main, "pull", "-q", "--rebase", "origin", "main")
        git(self.main, "push", "-q", "origin", "main")
        before = self._state(self.main)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])
        self.assertEqual(self._state(self.main), before)
        self.assertEqual(body["committed"].count("hook-ran"), 0)
        self.assertFalse(merge_wt.exists())

    def test_a_rerun_after_a_failed_reconcile_takes_the_pr_number_as_it_was_given(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["test -f hook-ok"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a hook that fails first")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        git(self.main, "pull", "-q", "origin", "main")
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        cfg["reconcile"]["hooks"] = []
        (self.main / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.main, "commit", "-qam", "the hook fixed")
        git(self.main, "pull", "-q", "--rebase", "origin", "main")
        git(self.main, "push", "-q", "origin", "main")
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "07", root=self.main)  # the host reads 07 as 7
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])

    def test_a_merge_the_host_has_not_completed_names_the_hosts_own_state_word(self):
        head = self._to_approved_pr()
        queued = prhost.PrFacts(number=7, state="open", head=head)
        with mock.patch.object(prhost, "confirm", return_value=queued):
            code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertIn("exited 0 but the PR is OPEN (a merge queue or auto-merge?)", err)

    def test_a_detached_main_checkout_keeps_its_head_too(self):
        self._to_approved_pr()
        git(self.main, "checkout", "-q", "--detach")
        before = (git(self.main, "rev-parse", "HEAD"), git(self.main, "status", "--porcelain"))
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((git(self.main, "rev-parse", "HEAD"), git(self.main, "status", "--porcelain")), before)
        self.assertNotEqual(before[0], body["reconcile_sha"])

    def test_a_merge_worktree_path_taken_by_something_else_stops_the_reconcile_and_touches_nothing(self):
        self._to_approved_pr()
        (self.main / ".plane-runtime" / "merge-0002").mkdir(parents=True)
        (self.main / ".plane-runtime" / "merge-0002" / "keep.txt").write_text("not ours\n")
        before = self._state(self.main)
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertIn("merge-0002", err)
        self.assertEqual(self._state(self.main), before)
        self.assertEqual((self.main / ".plane-runtime" / "merge-0002" / "keep.txt").read_text(), "not ours\n")
        self.assertFalse(git(self.main, "log", "-1", "--format=%s", "origin/main").startswith("Reconcile"))

    def test_without_a_worktrees_dir_the_reconcile_is_made_in_the_checkout_close_runs_from(self):
        cwd = self.main.parent / "hook-cwd"
        self._to_approved_pr()
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["worktrees"]["dir"] = None  # the one way to have none: a value other than the constant
        cfg["reconcile"]["hooks"] = [f"pwd -P > {cwd}"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "no worktrees dir")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(cwd.read_text().strip(), str(self.runner.resolve()))
        self.assertEqual(git(self.runner, "rev-parse", "HEAD"), body["reconcile_sha"])

    def test_the_reconcile_hooks_run_in_the_merge_worktree(self):
        cwd = self.main.parent / "hook-cwd"
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = [f"pwd -P > {cwd}"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a hook that notes its directory")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(cwd.read_text().strip(), str((self.main / ".plane-runtime" / "merge-0002").resolve()))

    def test_the_reconcile_hooks_see_the_worktrees_links_paths(self):
        seen = self.main.parent / "hook-seen"
        self.write(".venv/marker", "linked in\n")  # a worktrees.links path: untracked, in the main checkout only
        cfg = json.loads((self.runner / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = [f"cat .venv/marker > {seen}"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a hook that reads a linked path")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(seen.read_text(), "linked in\n")
        self.assertNotIn(".venv", body["committed"])


    def test_a_failed_close_leaves_a_merge_worktree_that_wt_list_shows_and_gc_keeps_while_leased(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = ["exit 3"]
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(self.runner, "commit", "-qam", "a failing hook")
        git(self.runner, "push", "-q", "origin", "HEAD:main")
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1, out + err)
        merge_wt = self.main / ".plane-runtime" / "merge-0002"
        code, _, out, err = self.ccp("wt", "list", "--task", "0002")
        self.assertEqual(code, 0, err)
        listed = {r["name"]: r for r in json.loads(out)}
        self.assertEqual((listed["merge-0002"]["kind"], listed["merge-0002"]["path"]), ("merge", str(merge_wt)))
        code, body, out, err = self.ccp("wt", "gc")
        self.assertEqual(code, 0, err)
        self.assertNotIn("merge-0002", body["removed"])  # the task is still leased: a re-run of close reuses it
        self.assertTrue(merge_wt.is_dir())

class PrReadRefusals(unittest.TestCase):
    """close and drop read the PR through the PR host: a host that cannot answer is a refusal (exit 1), a host
    CLI that cannot run here a configuration problem (exit 2)."""

    def test_a_host_error_is_a_refusal_and_an_unavailable_host_a_configuration_error(self):
        from ccp.queue import QueueError  # noqa: PLC0415
        for exc, code in ((prhost.HostError("gh pr view 7: boom"), 1),
                          (prhost.HostUnavailable("gh is not installed"), 2)):
            with mock.patch.object(prhost, "view", side_effect=exc), self.assertRaises(QueueError) as cm:
                lifecycle._pr_state(mock.Mock(), "7")
            self.assertEqual((cm.exception.code, str(cm.exception)), (code, str(exc)))


class CloseListsChecksNotAsWritten(ToolkitFixture, unittest.TestCase):
    """SPEC §15.4: close prints each check verified not as written before it merges, and merges."""

    def _merge_seeing_stderr(self):
        seen, real = [], prhost.merge

        def merge(*a):
            seen.append(sys.stderr.getvalue())  # what close had printed when it merged
            return real(*a)
        return seen, mock.patch.object(prhost, "merge", side_effect=merge)

    def test_close_lists_each_check_not_as_written_before_the_merge_and_merges(self):
        head = self._to_approved_pr()
        gates = self.q / "escalations" / "0002-second"
        gates.mkdir(parents=True)
        (gates / "1.json").write_text(json.dumps({"task_id": "0002-second", "escalation_id": "0002-second-1",
                                                  "class": "other", "status": "closed", "decision": "approved"}))
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "check-01", "pass": True, "as_written": False,
                          "held_instead": "ran the listing in place of the removed flag", "ruling": "0002-second-1",
                          "evidence": "the flag the expectation names is gone", "produced_by": "verifier"},
                         {"dod_check_id": "check-02", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict-not-as-written.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        seen, patch = self._merge_seeing_stderr()
        with patch:
            code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        line = "check-01: held instead: ran the listing in place of the removed flag; ruling: 0002-second-1"
        self.assertEqual(len(seen), 1)
        self.assertIn(line, seen[0])
        self.assertNotIn("check-02:", seen[0])
        self.assertTrue(body["merged_now"])
        self.assertEqual(json.loads((self.ghstate / "pr.json").read_text())["state"], "MERGED")

    def test_close_prints_no_list_when_every_check_held_as_written(self):
        self._to_approved_pr()
        seen, patch = self._merge_seeing_stderr()
        with patch:
            code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(seen), 1)
        self.assertNotIn("not as written", err)



class CloseNamesCarriedChecks(ToolkitFixture, unittest.TestCase):
    """§15.6 rule 3: the Verification notes line close writes names the checks a verify round carried from
    an earlier approval, with that approval's sha."""

    def test_the_verification_line_names_the_checks_carried_from_an_earlier_approval(self):
        head = self._to_approved_pr()
        earlier = git(self.main / ".plane-runtime" / "impl-0002", "rev-parse", "HEAD~1")
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": cid, "ran": False, "pass": None, "rests_on": f"approve at {earlier}",
                          "evidence": "the PR's own files are unchanged since that approve", "produced_by": "verifier"}
                         for cid in ("c-01", "c-02")]
        f = Path(self._tmp.name) / "verdict-carried.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        git(self.main, "fetch", "-q", "origin")
        notes = git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md").split("## Verification notes")[1]
        line = next(ln for ln in notes.splitlines() if "APPROVE" in ln)
        self.assertIn(f"Carried from {earlier}: c-01, c-02.", line)
        self.assertNotIn("Passed: none", line)
        self.assertNotIn("Not run by the verifier", line)

    def test_passed_carried_and_otherwise_unrun_checks_each_keep_their_own_part_of_the_line(self):
        a, b = "a" * 40, "b" * 7
        (self.q / "verification").mkdir(exist_ok=True)
        (self.q / "verification" / "0002-second.json").write_text(json.dumps({"checks": [
            {"dod_check_id": "c-01", "pass": True},
            {"dod_check_id": "c-02", "ran": False, "pass": None, "rests_on": f"approve at {a}"},
            {"dod_check_id": "c-03", "ran": False, "pass": None, "rests_on": f"approve at {b}"},
            {"dod_check_id": "c-04", "ran": False, "pass": None, "rests_on": "the operator's live run"},
            {"dod_check_id": "c-05", "ran": False, "pass": None, "rests_on": f"approve at {a}"}]}))
        line = lifecycle._verification_note(self.q, "0002-second", "7", "c" * 40, "d" * 40, "2026-11-17")
        self.assertIn(f"Passed: c-01. Carried from {a}: c-02, c-05. Carried from {b}: c-03. "
                      "Not run by the verifier: c-04.", line)


class CloseReadsAMalformedRunnerCount(ToolkitFixture, unittest.TestCase):
    """§10.2 step 4: a runner's `tasks_done` that is no whole number reads as 0 at close, as claim reads it."""

    def work(self, **fields) -> None:
        p = self.q / "work.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), **fields}))

    def test_one_runner_s_count(self):
        self._to_approved_pr()
        self.work(runner_tasks_done="x")
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Traceback", err)
        self.assertIn("runner_tasks_done", err)  # the warning claim gives too
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner_tasks_done"], 1)

    def test_a_slot_s_count(self):
        self._to_approved_pr()
        slot = json.loads((self.q / "tasks" / "0002-second.json").read_text())["lease_holder"]
        self.work(runners={slot: {"bound_name": slot, "tasks_done": "x"}})
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runners"][slot]["tasks_done"], 1)


if __name__ == "__main__":
    unittest.main()
