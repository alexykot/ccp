"""SPEC §28: the board's read model, the page, the status summary, and the rebuild after each
state change (debounced, detached, never the command's problem)."""
from __future__ import annotations

import argparse
import fcntl
import io
import json
import os
import re
import time
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from ccp import board, cli
from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture
import unittest


class Board(ToolkitFixture, unittest.TestCase):
    def test_build_writes_the_model_the_page_and_a_daily_snapshot(self):
        self.ccp("tasks", "claim", "0002")
        self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        b = json.loads(Path(body["board"]).read_text())
        for k in ("now", "usage", "runs", "tasks", "trend", "health", "blockers", "plane"):
            self.assertIn(k, b)
        self.assertEqual(b["now"]["work"]["task_id"], "0002-second")
        self.assertEqual([r["run_id"] for r in b["now"]["open_runs"]], ["0002-second/implement"])
        page = Path(body["page"]).read_text()
        self.assertIn('"project_id": "demo"', page)
        self.assertNotIn("/*__BOARD__*/null", page)
        self.assertIn('http-equiv="refresh"', page)
        self.assertTrue(list((self.q / "board/history").glob("*.json")))

    def test_status_exits_1_on_a_blocker(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, _ = self.ccp("board", "status")
        self.assertEqual(code, 0, out)
        self.ccp("tasks", "wait", "0002", "design_seat", "--detail", "x")
        code, _, out, _ = self.ccp("board", "status")
        self.assertEqual(code, 1)
        self.assertIn("BLOCKER waiting: 0002-second on design_seat", out)

    def test_close_asks_for_a_rebuild_and_the_drain_shows_the_merge(self):
        self._to_approved_pr()
        with mock.patch("ccp.board.refresh") as r:
            code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(r.call_count, 1)
        (self.q / "board").mkdir(exist_ok=True)
        (self.q / "board" / board.DIRTY).touch()
        code, _, out, err = self.ccp("board", "build", "--quiet", "--drain")
        self.assertEqual((code, out), (0, ""), err)
        b = json.loads((self.q / "board/board.json").read_text())
        self.assertIn("0002-second", [t["task_id"] for t in b["tasks"]])  # the merge, from git
        self.assertFalse((self.q / "board" / board.DIRTY).exists())

    def test_close_writes_the_merge_record_when_the_queue_already_says_done(self):
        self._to_approved_pr()
        t = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**t, "status": "done"}))
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", "7")
        self.assertEqual(code, 0, out + err)
        t = json.loads((self.q / "tasks/0002-second.json").read_text())
        self.assertTrue(t["merge_sha"] and t["reconcile_sha"] and t["merged_at"])
        self.assertIsNone(t["lease_holder"])
        self.assertEqual(json.loads((self.q / "work.json").read_text())["runner_tasks_done"], 1)

    def test_refactors_waiting_outside_the_scope_and_the_oldest_age(self):
        b = json.loads(Path(self.ccp("board", "build")[1]["board"]).read_text())
        self.assertIsNone(b["now"]["refactors_waiting"])  # no architect block: kind is not read (§20)
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {}}))
        for tid, created in (("0003-old", "2026-09-01"), ("0004-new", "2026-10-01")):
            self.write(f"docs/delivery/tasks/{tid}.md", TASK.format(tid=tid, title="Tidy", status="pending", deps="", ver="*Append-only.*")
                       .replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]').replace("created: 2026-09-30", f"created: {created}"))
        (self.q / "work.json").write_text(json.dumps({"status": "idle", "scope": ["0002-second"], "review_point": "R7"}))
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        rw = json.loads(Path(body["board"]).read_text())["now"]["refactors_waiting"]
        self.assertEqual((rw["count"], rw["ids"], rw["oldest_task_id"], rw["mode"]), (2, ["0003-old", "0004-new"], "0003-old", "deps"))
        self.assertGreater(rw["oldest_age_days"], 40)
        self.assertIn("refactors waiting 2 outside the scope, oldest 0003-old", self.ccp("board", "status", root=self.main)[2])
        self.assertIn("Refactors waiting", Path(body["page"]).read_text())
        (self.q / "work.json").write_text(json.dumps({"status": "idle"}))  # no scope: every pending refactor waits
        rw = json.loads(Path(self.ccp("board", "build", root=self.main)[1]["board"]).read_text())["now"]["refactors_waiting"]
        self.assertEqual(rw["ids"], ["0003-old", "0004-new"])

    def test_the_page_has_no_external_resources(self):
        page = (Path(__file__).resolve().parents[1] / "ccp/board_page.html").read_text()
        self.assertFalse(re.search(r'<(script|link)[^>]+(src|href)="https?:', page))


class Refresh(ToolkitFixture, unittest.TestCase):
    """§28.3: each §10.6 state change rebuilds the board in the background."""

    def setUp(self):
        super().setUp()
        self.fence = mock.patch.dict(os.environ, {"CCP_NO_BOARD_REFRESH": "0"})
        self.fence.start()

    def tearDown(self):
        self.fence.stop()
        super().tearDown()

    def test_each_state_change_asks_for_one_rebuild_and_reads_do_not(self):
        with mock.patch("ccp.board.refresh") as r:
            def step(*args, fires=True, code=0):
                n = r.call_count
                got, body, out, err = self.ccp(*args)
                self.assertEqual(got, code, out + err)
                self.assertEqual(r.call_count - n, 1 if fires else 0, args)
                return body
            step("tasks", "claim", "0002")
            step("tasks", "phase", "0002", "implementing", "--note", "x")
            step("tasks", "wait", "0002", "design_seat", "--detail", "x")
            step("tasks", "resume", "0002", "answered")
            step("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
            n = r.call_count
            code, _, out, err = self.report("0002-second/review", "Outcome: done\nSeverity: BLOCKER=0 MAJOR=0 MINOR=0 NIT=0\n"
                                                                   "## Friction\nnone\n")
            self.assertEqual((code, r.call_count - n), (0, 1), out + err)
            pid = step("plane", "propose", "--need", "a command that frees per-task resources", "--generic", "every product with per-task resources needs them freed")["id"]
            step("plane", "triage", pid, "--accept", "--reason", "plane task")
            step("plane", "list", fires=False)
            step("tasks", "list", fires=False)
            step("tasks", "check", fires=False)
            step("board", "build", "--quiet", fires=False)
            step("tasks", "claim", "9999", fires=False, code=2)  # a refusal changed nothing

    def test_the_trigger_table_covers_the_other_state_changes(self):
        cfg = mock.Mock()
        with mock.patch("ccp.board.refresh") as r:
            for group, sub, fires in (("verify", "record", True), ("allowance", "continue", True),
                                      ("architect", "run", True), ("architect", "triage", True),
                                      ("plane", "triage", True), ("agent", "start", True), ("agent", "stop", True),
                                      ("health", "note", True),
                                      ("health", "record", True), ("verify", "merge-ok", False),
                                      ("verify", "check", False), ("allowance", "status", False),
                                      ("architect", "due", False), ("architect", "status", False),
                                      ("health", "show", False), ("usage", None, False)):
                n = r.call_count
                cli.refresh_board(cfg, argparse.Namespace(group=group, action=sub), 0)
                self.assertEqual(r.call_count - n, int(fires), (group, sub))
            for ns, fires in ((dict(group="docs", cmd="audit", action="run"), True),
                              (dict(group="docs", cmd="audit", action="triage"), True),
                              (dict(group="docs", cmd="audit", action="due"), False),
                              (dict(group="docs", cmd="check"), False),
                              (dict(group="tasks", cmd="next"), False),
                              (dict(group="tasks", cmd="next", board_dirty=True), True),
                              (dict(group="allowance", action="status", board_dirty=True), True)):
                n = r.call_count
                cli.refresh_board(cfg, argparse.Namespace(**ns), 0)
                self.assertEqual(r.call_count - n, int(fires), ns)
            n = r.call_count
            cli.refresh_board(cfg, argparse.Namespace(group="architect", action="run"), 1)
            self.assertEqual(r.call_count, n)  # a failed run is not a state change to show
            with mock.patch.object(r, "side_effect", RuntimeError("boom")):
                cli.refresh_board(cfg, argparse.Namespace(group="agent", action="stop"), 0)  # never raises

    def test_a_second_trigger_during_a_build_coalesces_into_one_more_build(self):
        cfg = self.ccp_cfg()
        builds = []

        def fake_build(c, q):
            builds.append(1)
            if len(builds) == 1:  # three commands land while the first build runs
                for _ in range(3):
                    self.assertFalse(board.refresh(cfg))
            return {}
        with mock.patch("ccp.board._spawn") as spawn, mock.patch("ccp.board.build", side_effect=fake_build), \
                mock.patch("ccp.board.write"):
            self.assertTrue(board.refresh(cfg))
            self.assertEqual(spawn.call_count, 1)
            self.assertEqual(board.drain(cfg, self.q), 0)
            self.assertEqual(spawn.call_count, 1)  # the running build took the marks; nothing new started
        self.assertEqual(len(builds), 2)
        self.assertFalse((self.q / "board" / board.DIRTY).exists())

    def test_a_held_lock_means_mark_only_and_a_second_drainer_steps_aside(self):
        cfg = self.ccp_cfg()
        (self.q / "board").mkdir()
        with (self.q / "board" / board.LOCK).open("a") as fh, mock.patch("ccp.board._spawn") as spawn, \
                mock.patch("ccp.board.build") as build:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(board.refresh(cfg))
            self.assertEqual(board.drain(cfg, self.q), 0)
            spawn.assert_not_called()
            build.assert_not_called()
        self.assertTrue((self.q / "board" / board.DIRTY).exists())  # the holder builds once more

    def test_a_failing_spawn_never_changes_the_command(self):
        with mock.patch("ccp.board._spawn", side_effect=OSError("no fork")) as spawn:
            code, body, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual((code, body["ok"], body["task_id"]), (0, True, "0002-second"))
        self.assertNotIn("board", err)
        self.assertNotIn("Traceback", err)
        with mock.patch("ccp.board.refresh", side_effect=RuntimeError("boom")):
            code, body, out, err = self.ccp("tasks", "phase", "0002", "implementing")
        self.assertEqual((code, body["ok"]), (0, True), err)
        self.assertNotIn("boom", err)

    def test_the_spawn_is_detached_pinned_to_this_plane_and_logs_its_stderr(self):
        (self.q / "board").mkdir()
        log = self.q / "board" / board.LOG
        log.write_text("x" * (board.LOG_MAX + 1))
        with mock.patch("subprocess.Popen") as popen:
            board._spawn(self.ccp_cfg(), self.q)
        args, kw = popen.call_args
        self.assertIn(f"sys.path.insert(0, {str(board.PLANE)!r})", args[0][2])
        self.assertEqual(args[0][args[0].index("--root") + 1], str(self.runner))
        self.assertEqual(args[0][-4:], ["board", "build", "--quiet", "--drain"])
        self.assertEqual((kw["cwd"], kw["start_new_session"], kw["env"]["QUEUE_ROOT"]), (self.runner, True, str(self.q)))
        self.assertEqual((kw["stdin"], kw["stdout"]), (board.subprocess.DEVNULL, board.subprocess.DEVNULL))
        self.assertEqual(kw["stderr"].name, str(log))
        self.assertEqual(log.stat().st_size, 0)  # past LOG_MAX it starts again

    def test_a_failed_build_is_logged_shown_by_status_and_cleared_by_the_next(self):
        cfg = self.ccp_cfg()
        (self.q / "board").mkdir()
        (self.q / "board" / board.DIRTY).touch()
        err = io.StringIO()
        with mock.patch("ccp.board.build", side_effect=RuntimeError("git is gone")), redirect_stderr(err):
            self.assertEqual(board.drain(cfg, self.q), 1)
        self.assertIn("RuntimeError: git is gone", err.getvalue())
        self.assertEqual(board.last_failure(self.q)["error"], "RuntimeError: git is gone")
        code, _, out, _ = self.ccp("board", "status")
        self.assertIn("last rebuild failed: ", out)
        self.assertIn("RuntimeError: git is gone (see board/.build.log)", out)
        self.assertEqual(self.ccp("board", "build", "--quiet")[0], 0)
        self.assertIsNone(board.last_failure(self.q))
        self.assertNotIn("last rebuild failed", self.ccp("board", "status")[2])

    def test_a_mark_set_as_the_drainer_lets_go_is_built_too(self):
        cfg = self.ccp_cfg()
        (self.q / "board").mkdir()
        (self.q / "board" / board.DIRTY).touch()
        real, late = fcntl.flock, []

        def flock(fh, op):
            if op == fcntl.LOCK_UN and not late:  # a command lands between the last look and the release
                late.append(1)
                (self.q / "board" / board.DIRTY).touch()
            return real(fh, op)
        with mock.patch("ccp.board.fcntl.flock", side_effect=flock), mock.patch("ccp.board.build", return_value={}) \
                as build, mock.patch("ccp.board.write"):
            self.assertEqual(board.drain(cfg, self.q), 0)
        self.assertEqual(build.call_count, 2)
        self.assertFalse((self.q / "board" / board.DIRTY).exists())

    def test_a_real_spawn_brings_the_board_up_to_date(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        d, deadline = self.q / "board", time.time() + 10
        while time.time() < deadline:
            b = json.loads((d / "board.json").read_text()) if (d / "board.json").is_file() else {}
            if (b.get("now") or {}).get("work", {}).get("task_id") == "0002-second" and not (d / board.DIRTY).exists() \
                    and not board._held(d / board.LOCK):
                break
            time.sleep(0.1)
        else:
            self.fail(f"the board did not catch up: {(d / board.LOG).read_text() if (d / board.LOG).is_file() else ''}")
        time.sleep(0.3)  # the drainer's last look and exit, before the temp dir goes
        self.assertIsNone(board.last_failure(self.q))

    def test_skipped_without_a_queue_or_a_board_dir(self):
        cfg = self.ccp_cfg()
        with mock.patch("ccp.board._spawn") as spawn:
            with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
                self.assertFalse(board.refresh(cfg))
            (self.q / "board").write_text("a file, not a dir")
            self.assertFalse(board.refresh(cfg))
            (self.q / "board").unlink()
            with mock.patch.dict(os.environ, {"CCP_NO_BOARD_REFRESH": "1"}):
                self.assertFalse(board.refresh(cfg))
            spawn.assert_not_called()

    def ccp_cfg(self):
        from ccp import config  # noqa: PLC0415
        return config.load(self.runner)


class QueueFollowsTheLog(ToolkitFixture, unittest.TestCase):
    """A task dropped in its task file on 2026-10-20, its queue file pending and waiting on an operator step."""

    def setUp(self):
        super().setUp()
        (self.runner / "docs/delivery/tasks/0003-dropped.md").write_text(TASK.format(
            tid="0003-dropped", title="Dropped", status="dropped", deps="", ver="*Append-only.*"))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks/0003-dropped.json").write_text(json.dumps({
            "task_id": "0003-dropped", "project_id": "demo", "status": "pending", "waiting_on": "operator_step",
            "waiting_on_since": "2026-10-18T05:40:01Z", "lease_holder": None}))
        (self.q / "queue/pending").mkdir(parents=True)
        (self.q / "queue/pending/0003-dropped").touch()
        g = self.q / "escalations/0003-dropped/1.json"
        g.parent.mkdir(parents=True)
        g.write_text(json.dumps({"escalation_id": "0003-dropped-1", "task_id": "0003-dropped", "status": "open",
                                 "class": "operator", "brief": "run it on the Mac"}))
        (self.q / "questions").mkdir()
        (self.q / "questions/sm-1.json").write_text(json.dumps({"question_id": "sm-1", "task_id": "0003", "status": "open"}))

    def test_the_board_lists_a_dropped_tasks_wait_gate_and_question_as_divergence_not_blockers(self):
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        b = json.loads(Path(body["board"]).read_text())
        self.assertEqual(b["blockers"], [])
        self.assertEqual((b["now"]["waits"], b["now"]["gates"], b["now"]["questions"]), ([], [], []))
        div = b["health"]["divergence"]
        self.assertIn("0003-dropped: dropped in its task file, pending in the queue, waiting on operator_step (ccp tasks sync)", div)
        self.assertIn("gate 0003-dropped-1 open: 0003-dropped is dropped in its task file", div)
        self.assertIn("question sm-1 open: 0003 is dropped in its task file", div)
        self.assertIn("warning: 3 queue file(s), gate(s) or question(s) diverge from the task log", err)  # not a failure
        self.assertIn("warning:   0003-dropped: dropped in its task file", err)
        code, _, out, _ = self.ccp("board", "status")
        self.assertEqual(code, 0, out)
        self.assertIn("divergence: 0003-dropped", out)

    def test_a_task_done_in_both_is_not_divergence(self):
        (self.q / "tasks/0004-done.json").write_text(json.dumps({"task_id": "0004-done", "status": "done",
                                                                 "waiting_on": None, "lease_holder": None}))
        (self.runner / "docs/delivery/tasks/0004-done.md").write_text(TASK.format(
            tid="0004-done", title="Done", status="done", deps="", ver="*Append-only.*"))
        (self.q / "tasks/0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "done"}))
        div = json.loads(Path(self.ccp("board", "build")[1]["board"]).read_text())["health"]["divergence"]
        self.assertFalse([x for x in div if x.startswith("0004-done")], div)
        self.assertIn("0002-second: done in the queue, pending in its task file", div)

    def test_a_pending_task_still_blocks(self):
        (self.q / "tasks/0002-second.json").write_text(json.dumps({"task_id": "0002-second", "status": "pending",
                                                                   "waiting_on": "operator_step"}))
        b = json.loads(Path(self.ccp("board", "build")[1]["board"]).read_text())
        self.assertEqual(b["blockers"], ["waiting: 0002-second on operator_step"])

    def test_sync_makes_the_queue_follow_the_log_once(self):
        self.ccp("tasks", "claim", "0002")
        before = json.loads((self.q / "work.json").read_text())
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["changed"], [{"task_id": "0003-dropped", "durable_status": "dropped", "changed": [
            "cleared waiting_on operator_step", "status pending -> dropped", "marker queue/dropped/"]}])
        t = json.loads((self.q / "tasks/0003-dropped.json").read_text())
        self.assertEqual((t["status"], t["waiting_on"], t["waiting_on_since"]), ("dropped", None, None))
        self.assertTrue((self.q / "queue/dropped/0003-dropped").exists())
        self.assertFalse((self.q / "queue/pending/0003-dropped").exists())
        mine = [e for e in self.events() if e["task_id"] == "0003-dropped"]
        self.assertEqual([(e["type"], e["op"]) for e in mine],
                         [("waiting_on", "clear"), ("durable", "reconcile"), ("phase", "transition")])
        self.assertEqual(mine[0]["payload"], {"reason": "dropped_in_log", "was": "operator_step"})
        self.assertEqual(mine[1]["payload"]["new"], "dropped")
        w = json.loads((self.q / "work.json").read_text())  # the runner's own task is untouched
        self.assertEqual((w["task_id"], w["lease"]), (before["task_id"], before["lease"]))
        self.ccp("board", "build", "--quiet")
        b = json.loads((self.q / "board/board.json").read_text())
        self.assertEqual(b["health"]["divergence"], ["gate 0003-dropped-1 open: 0003-dropped is dropped in its task file",
                                                     "question sm-1 open: 0003 is dropped in its task file"])
        n = len(self.events())
        code, body, _, _ = self.ccp("tasks", "sync")
        self.assertEqual((code, body["changed"], len(self.events())), (0, [], n))

    def test_the_board_warns_in_one_line_and_five_examples(self):
        for n in range(4, 12):
            tid = f"{n:04d}-gone"
            (self.runner / f"docs/delivery/tasks/{tid}.md").write_text(TASK.format(
                tid=tid, title="Gone", status="dropped", deps="", ver="*Append-only.*"))
            (self.q / f"tasks/{tid}.json").write_text(json.dumps({"task_id": tid, "status": "pending"}))
        _, _, _, err = self.ccp("board", "build")
        lines = err.strip().splitlines()
        self.assertTrue(lines[0].startswith("warning: 11 queue file(s)"), err)
        self.assertEqual(len(lines), 6)
        _, _, out, _ = self.ccp("board", "status")
        self.assertEqual(out.count("divergence: "), 11)

    def test_sync_skips_a_task_leased_mid_flight(self):
        """A close between its push and its queue update, or a live runner's task the log dropped."""
        self.ccp("tasks", "claim", "0002")
        (self.runner / "docs/delivery/tasks/0002-second.md").write_text(TASK.format(
            tid="0002-second", title="Second", status="done", deps='"0001-first"', ver="- 2026-10-21 — `cmd-01` pass"))
        self.ccp("tasks", "phase", "0002", "merging")
        before = (self.q / "tasks/0002-second.json").read_text()
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([r["task_id"] for r in body["changed"]], ["0003-dropped"])
        self.assertEqual([r["task_id"] for r in body["skipped"]], ["0002-second"])
        self.assertIn("leased by runner and merging in the queue: mid-flight", body["skipped"][0]["reason"])
        self.assertEqual((self.q / "tasks/0002-second.json").read_text(), before)
        self.ccp("board", "build", "--quiet")
        b = json.loads((self.q / "board/board.json").read_text())
        self.assertIn("0002-second: done in its task file, merging in the queue, leased by runner "
                      "(close it: sync skips a task leased mid-flight)", b["health"]["divergence"])

    def test_sync_clears_a_stale_lease_that_is_not_mid_flight(self):
        t = json.loads((self.q / "tasks/0003-dropped.json").read_text())
        (self.q / "tasks/0003-dropped.json").write_text(json.dumps({**t, "lease_holder": "runner"}))
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertIn("cleared the lease of runner", body["changed"][0]["changed"])
        self.assertIsNone(json.loads((self.q / "tasks/0003-dropped.json").read_text())["lease_holder"])
        self.assertIn(("lease", "clear"), self.ops())

    def test_sync_hands_work_json_to_the_live_task_wi_shape(self):
        """work.json's task_id is the stale dropped task, its in_flight and lease another, live one."""
        self.ccp("tasks", "claim", "0002")
        w = json.loads((self.q / "work.json").read_text())
        lease = w["lease"]
        (self.q / "work.json").write_text(json.dumps({**w, "task_id": "0003-dropped", "waiting_on": "operator_step",
                                                      "phase": "pending"}))
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["task_id"], w["lease"], w["in_flight"], w["phase"], w["waiting_on"]),
                         ("0002-second", lease, ["0002-second"], "leased", None))
        self.assertIsNotNone(w["phase_since"])

    def test_sync_leaves_a_work_level_quota_wait_alone(self):
        wait = {"task_id": None, "status": "idle", "waiting_on": "quota", "waiting_on_since": "2026-10-21T10:00:00Z",
                "planned_resume_at": "2026-10-21T15:00:00Z", "resets_at": "2026-10-21T15:00:00Z", "quota_class": "session"}
        (self.q / "work.json").write_text(json.dumps(wait))
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(body["changed"]), 1)
        self.assertEqual(json.loads((self.q / "work.json").read_text()), wait)

    def test_dry_run_writes_nothing(self):
        files = {p: p.read_bytes() for p in self.q.rglob("*") if p.is_file()}
        code, body, out, err = self.ccp("tasks", "sync", "--dry-run")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["dry_run"])
        self.assertEqual(body["changed"][0]["changed"], ["cleared waiting_on operator_step", "status pending -> dropped",
                                                         "marker queue/dropped/"])
        self.assertEqual({p: p.read_bytes() for p in self.q.rglob("*") if p.is_file()}, files)

    def test_sync_asks_for_a_rebuild_only_when_it_wrote(self):
        with mock.patch.dict(os.environ, {"CCP_NO_BOARD_REFRESH": "0"}), mock.patch("ccp.board.refresh") as r:
            self.ccp("tasks", "sync", "--dry-run")
            self.assertEqual(r.call_count, 0)
            self.ccp("tasks", "sync")
            self.assertEqual(r.call_count, 1)
            self.ccp("tasks", "sync")  # nothing left to change
            self.assertEqual(r.call_count, 1)


class Hostile(ToolkitFixture, unittest.TestCase):
    def test_agent_text_cannot_break_the_page_and_gates_keep_their_ids(self):
        self.ccp("tasks", "claim", "0002")
        g = self.q / "escalations/0002-second/1.json"
        g.parent.mkdir(parents=True)
        g.write_text(json.dumps({"escalation_id": "0002-second-1", "task_id": "0002-second", "status": "open",
                                 "class": "operator", "brief": "x <!--<script> y </script><img src=x onerror=alert(1)> &amp;"}))
        code, body, out, err = self.ccp("board", "build")
        self.assertEqual(code, 0, out + err)
        page = Path(body["page"]).read_text()
        data = page.split("const B = ", 1)[1].split(";\nconst SEATS", 1)[0]
        for bad in ("<", ">", "&"):
            self.assertNotIn(bad, data)
        b = json.loads(Path(body["board"]).read_text())
        self.assertEqual(b["now"]["gates"][0]["id"], "0002-second-1")
        self.assertIn("gate 0002-second-1 (operator) open", b["blockers"])
