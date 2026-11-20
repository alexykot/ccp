"""The operator's sign-off (SPEC §3.5, §10.5): the task field, `ccp tasks sign-off` and its ledger record,
the claim that refuses a missing brief-time one, and the close that refuses a missing or stale one."""
from __future__ import annotations

import json
import os
import subprocess
import time
import unittest
from pathlib import Path
from unittest import mock

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
        wt = self.main / ".plane-runtime" / "impl-0002"
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

    def test_close_refuses_a_declared_brief_sign_off_that_is_not_recorded(self):
        self._to_approved_pr()  # claimed before the task declared its sign-offs
        self.declare("[brief, build]")
        code, _, out, err = self.sign("--stage", "build")
        self.assertEqual(code, 0, out + err)
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("no brief sign-off", err)
        self.assertNotIn("build sign-off", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_a_malformed_sign_off_value_refuses_the_close(self):
        self._to_approved_pr()
        self.declare("true")
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("ccp tasks check", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    # ------------------------------------------------------------------ claim

    def test_a_missing_brief_sign_off_refuses_the_claim(self):
        self.declare("brief")
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3)
        self.assertIn("no brief sign-off", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.assertFalse((self.main / ".plane-runtime" / "impl-0002").exists())
        code, body, out, err = self.sign()
        self.assertEqual(code, 0, out + err)
        task_commit = git(self.main, "log", "-1", "--format=%H", "--", TASK_FILE)
        self.assertEqual(body["sign_off"]["head"], task_commit)  # the commit of the text signed
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)

    def test_a_brief_sign_off_is_stale_once_the_task_file_changes(self):
        self.declare("brief")
        self.assertEqual(self.sign()[0], 0)
        p = self.main / TASK_FILE
        p.write_text(p.read_text().replace("title: Second", "title: Second, reworded", 1))
        git(self.main, "commit", "-q", "-am", "0002 reworded")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3)
        self.assertIn("stale", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.assertEqual(self.sign()[0], 0)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_brief_sign_off_at_a_later_commit_covers_the_text(self):
        self.declare("brief")
        self.write("other.txt", "not the task file\n")
        git(self.main, "add", "other.txt")
        git(self.main, "commit", "-q", "-m", "an unrelated change")
        later = git(self.main, "rev-parse", "HEAD")
        self.assertNotEqual(later, git(self.main, "log", "-1", "--format=%H", "--", TASK_FILE))
        self.assertEqual(self.sign("--head", later)[0], 0)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_brief_sign_off_on_a_task_file_with_no_commit_refuses_the_claim(self):
        rel = "docs/delivery/tasks/0003-third.md"
        text = (self.main / TASK_FILE).read_text().replace("0002-second", "0003-third").replace("title: Second", "title: Third")
        (self.runner / rel).write_text(text.replace("depends_on:", "sign_off: brief\ndepends_on:", 1))  # never committed
        tip = git(self.runner, "rev-parse", "HEAD")
        code, _, out, err = self.ccp("tasks", "sign-off", "0003", "--by", "op", "--words", "signed", "--head", tip)
        self.assertEqual(code, 0, out + err)
        code, _, _, err = self.ccp("tasks", "claim", "0003")
        self.assertEqual(code, 3)
        self.assertIn("has no commit", err)
        self.assertFalse((self.q / "tasks/0003-third.json").exists())

    def test_a_brief_sign_off_whose_head_is_not_a_sha_refuses_the_claim(self):
        from ccp.queue import emit
        self.declare("brief")
        emit(self.q, config.load(self.runner), "0002-second", "sign_off", "recorded",
             {"stage": "brief", "by": "op", "words": "signed", "head": "origin/main"})  # a ref, though it holds the text
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3, err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())

    def test_a_brief_sign_off_on_a_head_not_in_the_checkout_refuses_the_claim(self):
        self.declare("brief")
        self.assertEqual(self.sign("--head", "b" * 40)[0], 0)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3, err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.assertFalse((self.main / ".plane-runtime" / "impl-0002").exists())

    def test_a_malformed_sign_off_value_refuses_the_claim(self):
        self.declare("brief, build")
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3)
        self.assertIn("ccp tasks check", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())
        self.assertFalse((self.main / ".plane-runtime" / "impl-0002").exists())

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

    # ------------------------------------------------------------------ a sign-off given before it was recorded

    def test_a_past_sign_off_carries_its_date_and_the_task_files_commit_and_holds_the_claim(self):
        self.declare("brief")
        code, body, out, err = self.ccp("tasks", "sign-off", "0002", "--by", "operator", "--words", "approved",
                                        "--at", "2026-01-01")
        self.assertEqual(code, 0, out + err)
        task_commit = git(self.main, "log", "-1", "--format=%H", "--", TASK_FILE)
        (ev,) = self.recorded()
        self.assertEqual(ev["payload"], {"stage": "brief", "by": "operator", "words": "approved",
                                         "head": task_commit, "signed_at": "2026-01-01"})
        self.assertEqual(body["sign_off"]["signed_at"], "2026-01-01")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_past_sign_off_from_a_named_commit_covers_the_text_it_contains(self):
        self.declare("brief")
        self.write("other.txt", "not the task file\n")
        git(self.main, "add", "other.txt")
        git(self.main, "commit", "-q", "-m", "an unrelated change")
        later = git(self.main, "rev-parse", "HEAD")
        code, body, out, err = self.sign("--at", "2026-01-01", "--from", later)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["sign_off"]["head"], later)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_past_sign_off_from_a_commit_before_the_text_changed_is_stale(self):
        before = git(self.main, "rev-parse", "HEAD")
        self.declare("brief")
        self.assertEqual(self.sign("--at", "2026-01-01", "--from", before)[0], 0)
        code, _, _, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 3)
        self.assertIn("stale", err)
        self.assertFalse((self.q / "tasks/0002-second.json").exists())

    def test_a_past_build_sign_off_is_judged_at_the_head_it_merges(self):
        self.declare("build")
        self.assertEqual(self.sign("--at", "2026-01-01", "--from", "a" * 40)[0], 0)
        self._to_approved_pr()
        code, _, _, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        self.assertFalse((self.ghstate / "merge-called").exists())

    def test_a_time_with_its_offset_is_kept_in_utc(self):
        self.declare("brief")
        code, body, out, err = self.sign("--at", "2026-01-01T09:30:00+02:00")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["sign_off"]["signed_at"], "2026-01-01T07:30:00Z")
        self.assertEqual(self.recorded()[0]["payload"]["signed_at"], "2026-01-01T07:30:00Z")

    def test_sign_off_refuses_a_date_it_cannot_read_or_one_still_to_come(self):
        from datetime import date, datetime, timedelta, timezone
        self.declare("brief")
        soon = datetime.now(timezone.utc) + timedelta(hours=2)
        for at, why in (("yesterday", "not a date"), ("2026-13-01", "not a date"),
                        ("2026-01-01T09:30:00", "not a date"), ("", "not a date"),
                        ((date.today() + timedelta(days=2)).isoformat(), "in the future"),
                        (soon.strftime("%Y-%m-%dT%H:%M:%SZ"), "in the future")):
            code, _, _, err = self.sign("--at", at)
            self.assertEqual(code, 2, at)
            self.assertIn(why, err, at)
        self.assertEqual(self.recorded(), [])

    def test_a_date_is_judged_against_todays_utc_date_whatever_the_local_zone(self):
        from datetime import datetime, timedelta, timezone
        self.declare("brief")
        utc = datetime.now(timezone.utc)
        if (utc.hour, utc.minute) >= (23, 58):
            self.skipTest("the UTC date may turn while it runs")
        # a zone whose local date is behind the UTC date (UTC-12, before noon UTC), else ahead of it (UTC+14)
        self.addCleanup(time.tzset)  # back to the real zone once TZ is restored
        with mock.patch.dict(os.environ, {"TZ": "XXX12" if utc.hour < 12 else "XXX-14"}):
            time.tzset()
            self.assertNotEqual(datetime.now().date(), utc.date())  # the local date is another day
            today, tomorrow = utc.date().isoformat(), (utc.date() + timedelta(days=1)).isoformat()
            code, _, out, err = self.sign("--at", tomorrow)
            self.assertEqual(code, 2, out + err)
            self.assertIn("in the future", err)
            code, body, out, err = self.sign("--at", today)
            self.assertEqual(code, 0, out + err)
            self.assertEqual(body["sign_off"]["signed_at"], today)

    # ------------------------------------------------------------------ next

    def two_ready(self) -> None:
        """0001 pending with an unsigned `brief` sign-off and 0002 with none, both ready, on the runner's tip."""
        first = self.main / "docs/delivery/tasks/0001-first.md"
        first.write_text(first.read_text().replace("status: done", "status: pending", 1)
                         .replace("depends_on:", "sign_off: brief\ndepends_on:", 1))
        second = self.main / TASK_FILE
        second.write_text(second.read_text().replace('depends_on: ["0001-first"]', "depends_on: []", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "docs/delivery/tasks/0001-first.md", TASK_FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-q", "-m", "two ready tasks")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def next_id(self, *extra: str) -> tuple[int, str, str]:
        code, _, out, err = self.ccp("tasks", "next", *extra)
        return code, out.split()[0] if out.strip() else "", err

    def test_next_passes_over_a_task_awaiting_its_brief_sign_off(self):
        self.two_ready()
        code, tid, err = self.next_id()
        self.assertEqual((code, tid), (0, "0002-second"), err)
        self.assertIn("passed over 0001-first: no brief sign-off on record", err)
        code, _, out, err = self.ccp("tasks", "sign-off", "0001", "--by", "op", "--words", "signed")
        self.assertEqual(code, 0, out + err)
        code, tid, err = self.next_id()
        self.assertEqual((code, tid), (0, "0001-first"), err)
        self.assertNotIn("passed over", err)

    def test_with_only_an_unsigned_task_ready_nothing_is_ready(self):
        self.two_ready()
        self.assertEqual(self.ccp("tasks", "hold", "0002", "--reason", "later")[0], 0)
        code, tid, err = self.next_id()
        self.assertEqual(code, 3, err)
        self.assertIn("passed over 0001-first: no brief sign-off", err)

    def test_an_empty_next_says_on_stdout_that_a_task_waits_on_its_sign_off(self):
        self.declare("brief")  # 0002, the only pending task
        code, _, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(out.strip(), "nothing ready: 1 waits on a brief sign-off (stderr names it)")
        self.assertIn("passed over 0002-second: no brief sign-off", err)

    def test_an_empty_next_counts_the_unsigned_and_the_held(self):
        self.two_ready()
        self.assertEqual(self.ccp("tasks", "hold", "0002", "--reason", "later")[0], 0)
        code, _, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(out.strip(), "nothing ready: 1 waits on a brief sign-off, 1 held (stderr names them)")

    def test_an_empty_next_with_nothing_passed_over_says_blocked_or_done(self):
        self.declare("brief")
        self.assertEqual(self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed")[0], 0)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        code, _, out, err = self.ccp("tasks", "next", "--scope", "0001")
        self.assertEqual(code, 3, out + err)
        self.assertEqual(out.strip(), "nothing ready in scope: every pending task is blocked on a dependency, "
                                      "or all are done")

    def test_a_preferred_unsigned_task_is_passed_over_and_explained(self):
        self.two_ready()
        self.assertEqual(self.ccp("tasks", "prefer", "0001")[0], 0)
        code, tid, err = self.next_id("--explain")
        self.assertEqual((code, tid), (0, "0002-second"), err)
        self.assertIn("preferred 0001-first awaits its brief sign-off: passed over", err)
        self.assertIn("1 unsigned", err)
        self.assertRegex(err, r"sign +0001-first")

    def test_the_board_s_ready_queue_agrees(self):
        from ccp import plan, selection  # noqa: PLC0415
        self.two_ready()
        cfg = config.load(self.runner)
        sel = selection.pick(cfg, self.q)
        self.assertEqual(sel["unsigned"], ["0001-first"])
        self.assertEqual([str(t["task_id"]) for t, _ in sel["ranked"]], ["0002-second"])
        self.assertEqual(plan.ready_queue(cfg, self.q, selection.current(cfg, self.q))["next"], "0002-second")

    def test_a_leased_task_is_not_passed_over_for_its_sign_off(self):
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)  # claimed before it declared a sign-off
        self.declare("brief")
        code, tid, err = self.next_id()
        self.assertEqual((code, tid), (0, "0002-second"), err)  # its claim resumes it
        self.assertNotIn("passed over", err)

    def three_pending(self) -> None:
        """Three ready tasks declaring a brief sign-off: 0001 signed before its file changed again (stale), 0002
        whose value is misspelt (malformed), 0003 signed at its text (current); the runner on the tip."""
        first = self.main / "docs/delivery/tasks/0001-first.md"
        first.write_text(first.read_text().replace("status: done", "status: pending", 1)
                         .replace("depends_on:", "sign_off: brief\ndepends_on:", 1))
        second = self.main / TASK_FILE
        second.write_text(second.read_text().replace('depends_on: ["0001-first"]', "sign_off: breif\ndepends_on: []", 1))
        self.write("docs/delivery/tasks/0003-third.md", second.read_text().replace("0002-second", "0003-third")
                   .replace("title: Second", "title: Third").replace("sign_off: breif", "sign_off: brief"))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "docs/delivery/tasks/0001-first.md", TASK_FILE, "docs/delivery/tasks/0003-third.md",
            "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-q", "-m", "three tasks")
        for tid in ("0001", "0003"):
            code, _, out, err = self.ccp("tasks", "sign-off", tid, "--by", "op", "--words", "signed", root=self.main)
            self.assertEqual(code, 0, out + err)
        first.write_text(first.read_text().replace("title: First", "title: First, reworded", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "commit", "-q", "-am", "0001 reworded after its signing")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def test_next_passes_over_a_stale_or_malformed_sign_off_naming_which(self):
        self.three_pending()
        code, tid, err = self.next_id()
        self.assertEqual((code, tid), (0, "0003-third"), err)
        self.assertIn("passed over 0001-first: stale brief sign-off: 0001-first's brief sign-off is stale", err)
        self.assertIn("ccp tasks sign-off 0001-first --stage brief", err)
        self.assertIn("passed over 0002-second: malformed sign_off: sign_off 'breif'", err)
        self.assertIn("ccp tasks check", err)
        for tid in ("0001", "0002"):  # what next passed over, claim refuses
            self.assertEqual(self.ccp("tasks", "claim", tid)[0], 3)

    def test_next_explains_each_kind_and_a_preferred_one(self):
        self.three_pending()
        self.assertEqual(self.ccp("tasks", "prefer", "0002", "0001")[0], 0)
        code, tid, err = self.next_id("--explain")
        self.assertEqual((code, tid), (0, "0003-third"), err)
        self.assertIn("preferred 0002-second has a malformed sign_off value: passed over (malformed sign_off", err)
        self.assertIn("preferred 0001-first awaits its brief sign-off again: passed over (stale brief sign-off", err)
        self.assertIn("2 unsigned", err)
        self.assertRegex(err, r"sign +0001-first .* awaits its sign-off: stale")
        self.assertRegex(err, r"sign +0002-second .* awaits its sign-off: malformed")

    def test_with_the_current_one_done_nothing_is_offered(self):
        self.three_pending()
        third = self.main / "docs/delivery/tasks/0003-third.md"
        third.write_text(third.read_text().replace("status: pending", "status: done", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "commit", "-q", "-am", "0003 done")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, out, err = self.ccp("tasks", "next")
        self.assertEqual(code, 3, out + err)
        self.assertTrue(out.startswith("nothing ready"), out)
        self.assertIn("passed over 0001-first: stale", err)
        self.assertIn("passed over 0002-second: malformed", err)

    def test_a_signed_task_whose_sign_off_holds_is_not_passed_over(self):
        self.three_pending()
        self.assertEqual(self.ccp("tasks", "sign-off", "0001", "--by", "op", "--words", "again")[0], 0)
        code, tid, err = self.next_id()
        self.assertEqual((code, tid), (0, "0001-first"), err)
        self.assertNotIn("passed over 0001", err)

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
