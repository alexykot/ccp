"""SPEC §28.3 priority 5, §22.10: review points stamped at close, the board's Plan and backlog
section (task fields, ADR register, review points, ready queue, dependency graph, burn-up), and that
task and ADR text renders as text."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ccp import board, plan, tasklog
from tests.helpers import TASK, Product
from tests.test_board_quality import HOSTILE, STUB, Base, _hostile
from tests.test_toolkit import git


def _task(p: Product, tid: str, status: str = "pending", deps: list[str] | None = None, extra: str = "",
          created: str = "2026-09-30", title: str = "A task") -> None:
    text = TASK.format(tid=tid, title=title, status=status, deps=", ".join(f'"{d}"' for d in deps or []),
                       ver="- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*")
    text = text.replace("created: 2026-09-30", f"created: {created}")
    if extra:
        text = text.replace("updated: 2026-09-30\n", f"updated: 2026-09-30\n{extra}\n")
    p.write(f"docs/delivery/tasks/{tid}.md", text)


class Stamp(Base, unittest.TestCase):
    """`ccp tasks close` writes work.json's review point into the task file it closes (§22.1)."""

    def work(self, **kw):
        w = json.loads((self.q / "work.json").read_text()) if (self.q / "work.json").is_file() else {}
        (self.q / "work.json").write_text(json.dumps({**w, **kw}))

    def close(self):
        self._to_approved_pr()
        code, body, out, err = self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "built.")
        self.assertEqual(code, 0, out + err)
        git(self.main, "fetch", "-q", "origin")
        return body, git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md")

    def test_close_stamps_the_runners_review_point(self):
        self.work(review_point="R7")
        body, task = self.close()
        head = task.split("\n---\n", 1)[0]
        self.assertIn("\nreview_point: R7", head)
        self.assertEqual(body["review_point_stamped"], "R7")
        self.assertEqual(tasklog.frontmatter(task)["review_point"], "R7")
        git(self.main, "checkout", "-q", "--detach", "origin/main")
        self.assertEqual(tasklog.check(self.cfg_main()), [])

    def test_a_review_point_already_set_is_kept(self):
        f = self.main / "docs/delivery/tasks/0002-second.md"
        f.write_text(f.read_text().replace("updated: 2026-09-30\n", "updated: 2026-09-30\nreview_point: R6\n"))
        from ccp import config  # noqa: PLC0415
        tasklog.write_index(config.load(self.main))
        git(self.main, "commit", "-qam", "R6")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        self.work(review_point="R7")
        body, task = self.close()
        self.assertIsNone(body["review_point_stamped"])
        self.assertIn("review_point: R6", task)
        self.assertNotIn("R7", task.split("\n---\n", 1)[0])

    def test_a_review_point_outside_the_pattern_is_not_stamped_and_says_so(self):
        self.work(review_point="PM")
        body, task = self.close()
        self.assertNotIn("review_point", task.split("\n---\n", 1)[0])
        self.assertTrue(any("does not match task_log.review_point_pattern" in w for w in body["warnings"]), body)

    def test_a_crlf_task_file_is_stamped_and_stays_crlf(self):
        f = self.main / "docs/delivery/tasks/0002-second.md"
        f.write_bytes(f.read_bytes().replace(b"\n", b"\r\n"))
        git(self.main, "-c", "core.autocrlf=false", "commit", "-qam", "crlf")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        self.work(review_point="R7")
        body, _ = self.close()
        raw = subprocess.run(["git", "-C", str(self.main), "show", "origin/main:docs/delivery/tasks/0002-second.md"],
                             capture_output=True).stdout
        self.assertEqual(body["review_point_stamped"], "R7")
        self.assertIn(b"\r\nreview_point: R7\r\n---\r\n", raw)
        self.assertIn(b"status: done\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))  # no bare LF crept in

    def test_no_frontmatter_end_warns_instead_of_skipping_silently(self):
        from ccp import lifecycle  # noqa: PLC0415
        p = Path(self._tmp.name) / "odd.md"
        p.write_text("status: pending\n\n## Verification notes\n\n*Append-only.*\n")
        self.assertFalse(lifecycle._task_file_done(p, "- note", "2026-10-22", "R7"))
        self.assertTrue(lifecycle._task_file_done(p, "- note", "2026-10-22", None))

    def test_no_review_point_no_stamp(self):
        body, task = self.close()
        self.assertIsNone(body["review_point_stamped"])
        self.assertNotIn("review_point", task.split("\n---\n", 1)[0])

    def cfg_main(self):
        from ccp import config  # noqa: PLC0415
        return config.load(self.main)


class Check(unittest.TestCase):
    def test_tasks_check_holds_review_point_to_the_pattern(self):
        p = Product({"task_log": {"review_point_pattern": "^(R[0-9]+|PM)$"}})
        self.addCleanup(p.cleanup)
        _task(p, "0001-a", extra="review_point: PM")
        _task(p, "0002-b", extra="review_point: R3")
        _task(p, "0003-c", extra="review_point: X9")
        p.index()
        errs = tasklog.check(p.cfg)
        self.assertEqual([e for e in errs if "review_point" in e],
                         ["docs/delivery/tasks/0003-c.md: review_point 'X9' does not match task_log.review_point_pattern "
                          "(^(R[0-9]+|PM)$, SPEC §22)"])


class Plan(unittest.TestCase):
    """plan.collect against a product without git and a hand-made queue."""

    def setUp(self):
        self.p = Product({"architect": {"refactor_every": 2}, "task_log": {"refs_any": ["spec_refs", "adr_refs"]}})
        self.addCleanup(self.p.cleanup)
        self._q = tempfile.TemporaryDirectory()
        self.addCleanup(self._q.cleanup)
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\n")
        (self.q / "tasks").mkdir()
        _task(self.p, "0001-base", "done", extra='adr_refs: ["0007 D1"]\nreview_point: R1', created="2026-09-28")
        _task(self.p, "0002-feat", "done", ["0001-base"], extra='adr_refs: ["ADR-0007"]\nreview_point: R1',
              created="2026-09-29")
        _task(self.p, "0003-next", "pending", ["0002-feat"], extra='adr_refs: ["0007 D2", "0008"]\nreview_point: R2')
        _task(self.p, "0004-later", "pending", ["0003-next"], extra="review_point: R2")
        _task(self.p, "0005-free", "pending")
        _task(self.p, "0006-gone", "dropped", extra='adr_refs: ["0007 D3"]')
        self.p.write("docs/delivery/tasks/0007-tidy.md", TASK.format(tid="0007-tidy", title="Tidy", status="pending", deps="",
                                                                     ver="*Append-only.*")
                     .replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E2"]'))
        (self.q / "tasks" / "0002-feat.json").write_text(json.dumps(
            {"status": "done", "pr": "12", "merge_sha": "abcdef1234567890", "merged_at": "2026-10-01T10:00:00Z"}))

    def work(self, **kw):
        w = {"status": "running", "hosting": "claude-team", **kw}
        (self.q / "work.json").write_text(json.dumps(w))
        return w

    def collect(self, **kw):
        return plan.collect(self.p.cfg, self.q, self.work(**kw), today="2026-10-03")

    def test_task_rows_carry_the_board_fields(self):
        P = self.collect()
        self.assertEqual(P["errors"], {})
        r = {t["task_id"]: t for t in P["tasks"]}
        self.assertEqual({k: r["0002-feat"][k] for k in ("kind", "adr_refs", "spec_refs", "review_point", "pr", "merge_sha",
                                                        "done_at")},
                         {"kind": "feature", "adr_refs": ["ADR-0007"], "spec_refs": ["S1"], "review_point": "R1", "pr": "12",
                          "merge_sha": "abcdef123456", "done_at": "2026-10-01T10:00:00Z"})
        self.assertEqual(r["0001-base"]["done_at"], "2026-09-30")  # no close record, no git: the file's updated date
        self.assertEqual(r["0001-base"]["pr"], None)
        self.assertEqual(r["0007-tidy"]["kind"], "refactor")
        self.assertEqual(r["0003-next"]["depends_on"], ["0002-feat"])
        self.assertEqual(r["0002-feat"]["depends_on"], [])  # a closed task's are in INDEX.yaml
        self.assertEqual(P["counts"], {"done": 2, "pending": 4, "dropped": 1})

    def test_adr_register_without_the_block_counts_citing_tasks(self):
        a = self.collect()["adrs"]
        self.assertFalse(a["enabled"])
        by = {i["id"]: i for i in a["items"]}
        self.assertEqual((by["ADR-0007"]["tasks"], by["ADR-0007"]["done"], by["ADR-0007"]["built_pct"]), (3, 2, 67))
        self.assertEqual(by["ADR-0007"]["open"], ["0003-next"])
        self.assertEqual(by["ADR-0008"]["built_pct"], 0)

    def test_adr_register_with_the_block_reads_frontmatter(self):
        cfg = json.loads((self.p.root / "docs/delivery/plane.json").read_text())
        self.p.write("docs/delivery/plane.json", json.dumps({**cfg, "adr": {}}))
        self.p.write("docs/adr/0007-x.md", "---\nid: ADR-0007\ntitle: \"Seven\"\nstatus: accepted\ndate: 2026-09-01\n"
                                           "in_force: |-\n  all\n  of it\n---\n# ADR-0007 — Seven\n")
        self.p.write("docs/adr/0006-y.md", "---\nid: ADR-0006\ntitle: Six\nstatus: superseded\nsuperseded_by: ADR-0007\n"
                                           "date: 2026-08-01\n---\n# ADR-0006 — Six\n")
        a = self.collect()["adrs"]
        by = {i["id"]: i for i in a["items"]}
        self.assertEqual(a["errors"], [])
        self.assertEqual((by["ADR-0007"]["title"], by["ADR-0007"]["in_force"], by["ADR-0007"]["supersedes"]),
                         ("Seven", "all of it", ["ADR-0006"]))
        self.assertEqual((by["ADR-0006"]["superseded_by"], by["ADR-0006"]["built_pct"]), ("ADR-0007", None))
        self.assertIsNone(by["ADR-0008"]["title"])  # cited, with no file

    def test_review_points_group_by_the_field_and_the_current_scope(self):
        rp = self.collect(review_point="R2", scope=["0003", "0004", "0005"])["review_points"]
        by = {g["id"]: g for g in rp}
        self.assertEqual({k: by["R1"][k] for k in ("tasks", "done", "remaining", "current", "first_done_at", "last_done_at")},
                         {"tasks": 2, "done": 2, "remaining": 0, "current": False, "first_done_at": "2026-09-30",
                          "last_done_at": "2026-10-01T10:00:00Z"})
        self.assertEqual({k: by["R2"][k] for k in ("tasks", "done", "remaining", "current", "unstamped")},
                         {"tasks": 3, "done": 0, "remaining": 3, "current": True, "unstamped": 1})
        self.assertEqual([g["id"] for g in rp], ["R1", "R2"])

    def next_cmd(self):
        """What `ccp tasks next --json` returns for this queue."""
        import io  # noqa: PLC0415
        import os  # noqa: PLC0415
        from contextlib import redirect_stderr, redirect_stdout  # noqa: PLC0415
        from unittest import mock  # noqa: PLC0415
        from ccp import cli  # noqa: PLC0415
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), \
                mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}), \
                mock.patch("ccp.cli._architect_gate", return_value=None):
            cli.main(["--root", str(self.p.root), "tasks", "next", "--json"])
        body = json.loads(out.getvalue())
        return body and body["task_id"]

    def test_ready_queue_is_the_selection_next_runs_nothing_in_flight(self):
        # Two features merged since any refactor and refactor_every 2: the ready refactor comes first.
        P = self.collect()
        ids = [r["task_id"] for r in P["ready"]["items"]]
        self.assertEqual(ids, ["0007-tidy", "0003-next", "0005-free"])
        self.assertEqual(P["ready"]["next"], self.next_cmd())
        self.assertEqual(P["ready"]["next"], str(tasklog.next_task(self.p.cfg)["task_id"]))
        self.assertIn("refactor, due after 2 feature merges", P["ready"]["items"][0]["why"])
        self.assertFalse(any(r["in_flight"] for r in P["ready"]["items"]))

    def test_ready_queue_with_a_task_in_flight(self):
        # The refactor is claimed, its file still pending: `next` returns it (a resume), and so does the board.
        P = self.collect(in_flight=["0007-tidy"], task_id="0007-tidy")
        self.assertEqual((P["ready"]["next"], self.next_cmd()), ("0007-tidy", "0007-tidy"))
        self.assertEqual(P["ready"]["in_flight"], ["0007-tidy"])
        self.assertEqual([(r["task_id"], r["in_flight"]) for r in P["ready"]["items"]],
                         [("0007-tidy", True), ("0003-next", False), ("0005-free", False)])
        self.assertIn("next pick 0007-tidy, in flight", plan.status_lines(P)[0])
        # A task in flight that is not ready is still listed as in flight.
        P = self.collect(in_flight=["0004-later"])
        self.assertEqual((P["ready"]["next"], P["ready"]["in_flight"]), (self.next_cmd(), ["0004-later"]))

    def test_ready_queue_preference_and_scope(self):
        P = self.collect(next_task="0005-free", next_task_reason="unblocks the demo")
        self.assertEqual([r["task_id"] for r in P["ready"]["items"]], ["0005-free", "0007-tidy", "0003-next"])
        self.assertEqual(self.next_cmd(), "0005-free")
        self.assertIn("unblocks the demo", P["ready"]["items"][0]["why"])
        # A scope narrows it; a preference outside it is reported, not taken.
        P = self.collect(scope=["0005"], next_task="0003-next")
        self.assertEqual([r["task_id"] for r in P["ready"]["items"]], ["0005-free"])
        self.assertEqual((P["ready"]["next"], self.next_cmd()), ("0005-free", "0005-free"))
        self.assertEqual(P["ready"]["preferred"], [{"task_id": "0003-next", "state": "out of scope"}])  # a legacy next_task

    def test_graph_and_burnup(self):
        P = self.collect(scope=["0003", "0004"])
        g = P["graph"]
        nodes = {n["id"]: n for n in g["nodes"]}
        self.assertEqual(set(nodes), {"0003-next", "0004-later", "0005-free", "0007-tidy"})
        self.assertEqual(g["edges"], [["0003-next", "0004-later"]])
        self.assertEqual((nodes["0003-next"]["depth"], nodes["0004-later"]["depth"]), (0, 1))
        self.assertEqual((nodes["0003-next"]["ready"], nodes["0004-later"]["ready"], nodes["0003-next"]["done_deps"]),
                         (True, False, 1))
        self.assertFalse(nodes["0005-free"]["in_scope"])
        b = P["burnup"]
        self.assertEqual(b[0], {"date": "2026-09-28", "total": 1, "done": 0})
        self.assertEqual(b[-1], {"date": "2026-10-03", "total": 6, "done": 2})
        self.assertEqual(len(b), 6)

    def test_a_failing_part_leaves_its_error_and_the_rest(self):
        from unittest import mock  # noqa: PLC0415
        with mock.patch.object(plan, "burnup", side_effect=RuntimeError("boom")):
            P = self.collect()
        self.assertEqual(P["errors"], {"burnup": "RuntimeError: boom"})
        self.assertTrue(P["ready"]["items"])
        self.assertTrue(plan.status_lines(P)[-1].startswith("plan burnup failed"))


class Built(Base, unittest.TestCase):
    """The section through `ccp board build`, with git's merges."""

    def test_board_json_has_the_plan_and_status_a_line(self):
        b = self.build()[0]
        p = b["plan"]
        self.assertEqual(p["errors"], {})
        self.assertEqual([r["task_id"] for r in p["ready"]["items"]], ["0002-second"])
        code, _, out, _ = self.ccp("board", "status", root=self.main)
        self.assertIn("plan: 1/2 tasks done, 1 ready (next pick 0002-second)", out)

    def test_git_merges_give_pr_and_sha(self):
        self.write("docs/delivery/tasks/0001-first.md", (self.main / "docs/delivery/tasks/0001-first.md").read_text())
        git(self.main, "commit", "-q", "--allow-empty", "-m", "Task 0001: first (#5)")
        b = self.build()[0]
        r = {t["task_id"]: t for t in b["plan"]["tasks"]}
        self.assertEqual(r["0001-first"]["pr"], "5")
        self.assertEqual(len(r["0001-first"]["merge_sha"]), 12)
        self.assertTrue(r["0001-first"]["done_at"].endswith("Z"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Rendered(Base, unittest.TestCase):
    def render(self, b):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        r = subprocess.run(["node", "-e", STUB + js + "\nprocess.stdout.write(out.join(''));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_every_plan_string_renders_as_text(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "adr": {}}))
        self.write("docs/adr/0003-x.md", "---\nid: ADR-0003\ntitle: \"t\"\nstatus: superseded\nsuperseded_by: ADR-0004\n"
                                         "date: 2026-09-01\nin_force: \"none\"\n---\n# ADR-0003 — t\n")
        self.write("docs/adr/0004-y.md", "---\nid: ADR-0004\ntitle: \"u\"\nstatus: accepted\ndate: 2026-09-02\n---\n# ADR-0004 — u\n")
        self.write("docs/adr/0005-z.md", "no frontmatter\n")
        (self.q / "work.json").write_text(json.dumps({"status": "running", "review_point": "R7", "scope": ["0002"],
                                                      "next_task": "0002-second", "in_flight": []}))
        b = self.build()[0]
        p = b["plan"]
        self.assertTrue(p["adrs"]["errors"] and p["review_points"] and p["ready"]["items"] and p["graph"]["nodes"])
        p["ready"]["in_flight"] = ["0009-x"]
        p["ready"]["items"].append(dict(p["ready"]["items"][0], in_flight=True))
        p["ready"]["preferred"] = [{"task_id": "0009-x", "state": "waiting on 0001"}]
        p["errors"] = {"burnup": "x"}
        html = self.render(_hostile(b))
        for title in ('id="pane-backlog"', 'id="pane-queue"', "ADR register", "Review points", "Ready queue", "Dependency graph, open tasks",
                      "Burn-up", "Task board", "Burn-up section failed"):
            self.assertIn(title, html)
        self.assertIn("&lt;!--&lt;script&gt;", html)
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)

    def test_a_renderer_that_throws_shows_its_banner_and_the_rest_renders(self):
        b = self.build()[0]
        b["plan"]["tasks"] = 5  # not a list: plan() throws inside
        b["plan"]["graph"] = {"nodes": 7}
        html = self.render(b)
        self.assertIn("Plan section failed", html)
        self.assertIn("Plane health", html)
        self.assertIn("Quality", html)

    def test_an_empty_plan_renders(self):
        b = self.build()[0]
        b["plan"] = {"errors": {"plan": HOSTILE}}
        html = self.render(b)
        self.assertIn("Plan section failed", html)
        self.assertNotIn("<img", html)


if __name__ == "__main__":
    unittest.main()
