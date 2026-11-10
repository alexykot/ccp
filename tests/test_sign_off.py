"""The operator's sign-off (SPEC §3.5, §10.5): the task field, `ccp tasks sign-off` and its ledger record,
the claim that refuses a missing brief-time one, and the close that refuses a missing or stale one."""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path

from ccp import config, tasklog
from tests.test_toolkit import PLANE, ToolkitFixture, git

TASK_FILE = "docs/delivery/tasks/0002-second.md"


class SignOff(ToolkitFixture, unittest.TestCase):
    def declare(self, value: str) -> None:
        """Give 0002 a `sign_off:` line, commit and push it, and bring the runner worktree to the new tip."""
        p = self.main / TASK_FILE
        p.write_text(p.read_text().replace("depends_on:", f"sign_off: {value}\ndepends_on:", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", TASK_FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-q", "-m", "0002 needs a sign-off")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def sign(self, *extra: str):
        return self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed as written", *extra)

    def recorded(self) -> list[dict]:
        return [e for e in self.events() if (e["type"], e["op"]) == ("sign_off", "recorded")]

    def verify_at(self, head: str, name: str) -> None:
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / name
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)

    # ------------------------------------------------------------------ close

    def test_close_refuses_a_task_with_no_sign_off_and_merges_nothing(self):
        self.declare("build")
        self._to_approved_pr()
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("no build sign-off", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_a_sign_off_on_an_old_head_is_stale_until_signed_again(self):
        self.declare("build")
        head_a = self._to_approved_pr()
        code, body, out, err = self.sign()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["sign_off"]["head"], head_a)  # the verified head, by default
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built again\n")
        git(wt, "commit", "-q", "-am", "Task 0002: fix it")
        git(wt, "push", "-q", "origin", "task/0002-second")
        head_b = git(wt, "rev-parse", "HEAD")
        pr = json.loads((self.ghstate / "pr.json").read_text())
        (self.ghstate / "pr.json").write_text(json.dumps({**pr, "head": head_b}))
        self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head_b, "--note", "the new head")
        self.verify_at(head_b, "verdict-b.json")
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        self.assertFalse((self.ghstate / "merge-called").exists())
        code, body, out, err = self.sign()
        self.assertEqual((code, body["sign_off"]["head"]), (0, head_b), out + err)
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["head"], head_b)

    def test_a_close_after_a_merge_by_hand_waits_for_the_sign_off(self):
        self.declare("build")
        head = self._to_approved_pr()
        time.sleep(1.2)  # the approval is recorded before the merge, to the second
        subprocess.run([os.environ["CCP_GH_BIN"], "pr", "merge", "7", "--squash", "--match-head-commit", head], check=True)
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("close refused", err)
        self.assertNotIn("status: done", git(self.main, "show", f"origin/main:{TASK_FILE}"))

    def test_a_brief_sign_off_lets_the_task_close_without_a_new_one(self):
        self.declare("brief")
        self.assertEqual(self.sign()[0], 0)
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)

    # ------------------------------------------------------------------ claim

    def test_a_missing_brief_sign_off_refuses_the_claim(self):
        self.declare("brief")
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3)
        self.assertIn("no brief sign-off", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.assertFalse((self.main / ".rt" / "impl-0002").exists())
        code, body, out, err = self.sign()
        self.assertEqual(code, 0, out + err)
        task_commit = git(self.main, "log", "-1", "--format=%H", "--", TASK_FILE)
        self.assertEqual(body["sign_off"]["head"], task_commit)  # the commit of the text signed
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)

    def test_a_build_sign_off_does_not_hold_back_the_claim(self):
        self.declare("build")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    # ------------------------------------------------------------------ the command and its record

    def test_the_record_holds_stage_who_words_and_head_in_the_ledger(self):
        self.declare("[brief, build]")
        code, body, out, err = self.sign("--stage", "build", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        (ev,) = self.recorded()
        self.assertEqual(ev["task_id"], "0002-second")
        self.assertEqual(ev["payload"], {"stage": "build", "by": "op", "words": "signed as written", "head": "a" * 40})
        self.assertEqual(body["sign_off"]["at"], ev["at"])

    def test_sign_off_refuses_what_it_cannot_record(self):
        code, _, _, err = self.sign()
        self.assertEqual(code, 2)
        self.assertIn("declares no sign_off", err)
        self.declare("[brief, build]")
        self.assertEqual(self.sign()[0], 2)  # both declared: which one
        self.assertEqual(self.sign("--stage", "build")[0], 2)  # nothing verified, no --head
        self.assertEqual(self.sign("--stage", "brief", "--head", "not-a-sha")[0], 2)
        self.assertEqual(self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", " ", "--stage", "brief")[0], 2)
        self.assertEqual(self.recorded(), [])

    def test_sign_off_refuses_a_stage_the_task_does_not_declare(self):
        self.declare("brief")
        code, _, _, err = self.sign("--stage", "build", "--head", "a" * 40)
        self.assertEqual(code, 2)
        self.assertEqual(self.recorded(), [])

    def test_a_later_record_of_a_stage_replaces_the_earlier(self):
        from ccp.queue import sign_offs
        self.declare("build")
        self.sign("--head", "a" * 40)
        self.sign("--head", "b" * 40)
        self.assertEqual(sign_offs(self.q, "0002-second")["build"]["head"], "b" * 40)

    # ------------------------------------------------------------------ the task field

    def test_tasks_check_reads_the_field(self):
        self.declare("[brief, build]")
        self.assertEqual([e for e in tasklog.check(config.load(self.main)) if "sign_off" in e], [])
        p = self.main / TASK_FILE
        p.write_text(p.read_text().replace("sign_off: [brief, build]", "sign_off: later", 1))
        errs = [e for e in tasklog.check(config.load(self.main)) if "sign_off" in e]
        self.assertEqual(len(errs), 1, errs)


if __name__ == "__main__":
    unittest.main()
