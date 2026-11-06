"""SPEC §28.3 Now, §2, §28.3: the board's live seats, their pinned model and effort (from the
definitions in effect, the run records, telemetry.design_seat and the headless flags) against
what the telemetry fold observed, and that agent-written text stays text."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ccp import board, config, runs, seats, usage
from tests.test_board_quality import HOSTILE, STUB, _hostile
from tests.test_toolkit import ToolkitFixture


def at(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class Base(ToolkitFixture):
    def design_seat(self, model="claude-opus-5-5", effort="xhigh"):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "telemetry": {"design_seat": {"model": model, "effort": effort}}}))

    def requests(self, *rows, spans=()):
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        (b / "usage-requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        if spans:
            (b / "usage-spans.jsonl").write_text("".join(json.dumps(s) + "\n" for s in spans))

    def build(self):
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text())

    def rows(self, b):
        return {r["seat"]: r for r in b["now"]["seats"]["rows"]}

    def open_implement(self):
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        return "0002-second/implement"


def req(rid, minutes_ago, model, effort, out=100, **extra):
    return {"request_id": rid, "at": at(minutes_ago), "model": model, "effort": effort, "input_tokens": 10,
            "output_tokens": out, "cache_read_tokens": 0, "cache_creation_tokens": 0, "cost_usd": 0.01, **extra}


class Expected(Base, unittest.TestCase):
    def test_the_product_copy_wins_over_the_plugin(self):
        f = self.main / ".claude/agents/delivery-implementer.md"
        f.write_text(f.read_text().replace("effort: high", "effort: max"))
        cfg = config.load(self.main)
        imp = seats.definition_pins(cfg, "delivery-implementer")
        self.assertEqual((imp["model"], imp["effort"]), ("claude-opus-5-5", "max"))
        self.assertIn(".claude/agents/delivery-implementer.md (product copy)", imp["source"])
        # no product copy of the runner: the plugin's definition, read from the real file
        run = seats.definition_pins(cfg, "ccp:delivery-runner")
        self.assertEqual((run["model"], run["effort"]), ("claude-sonnet-5-5", "high"))
        self.assertEqual(run["source"], "plane:plugin/agents/delivery-runner.md (plugin)")

    def test_an_unknown_agent_type(self):
        self.assertEqual(seats.definition_pins(config.load(self.main), ""),
                         {"model": None, "effort": None, "source": "unknown agent type"})

    def test_a_seat_quiet_for_two_hours_is_flagged(self):
        (self.q / "observability").mkdir(exist_ok=True)
        (self.q / "observability" / "events.jsonl").write_text(json.dumps(
            {"at": at(185), "actor": "design-seat", "type": "gate", "op": "decided"}) + "\n")
        r = self.rows(self.build())
        self.assertEqual(r["design seat"]["stale"], "quiet 3 h")
        _, _, out, _ = self.ccp("board", "status", root=self.main)
        self.assertIn("STALE: quiet 3 h", out)

    def test_usage_json_leaves_out_the_board_rows(self):
        self.requests(req("r1", 2, "claude-opus-5-5", "high"))
        code, body, out, err = self.ccp("usage", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("recent", body)

    def test_headless_pins_are_the_claude_p_flags(self):
        from ccp import architect
        h = seats.headless_pins()
        self.assertEqual(["--model", h["model"], "--effort", h["effort"]], list(architect.ar.HEADLESS_MODEL))

    def test_rows_for_the_lead_runner_and_an_open_run_without_telemetry(self):
        self.design_seat()
        rid = self.open_implement()
        r = self.rows(self.build())
        self.assertEqual(list(r), ["design seat", "runner", f"implementer {rid}"])
        lead, runner, run = r["design seat"], r["runner"], r[f"implementer {rid}"]
        self.assertEqual((lead["expected"]["model"], lead["expected"]["effort"], lead["expected"]["advisory"]),
                         ("claude-opus-5-5", "xhigh", True))
        self.assertEqual((runner["expected"]["model"], runner["expected"]["effort"]), ("claude-sonnet-5-5", "high"))
        self.assertEqual((run["expected"]["model"], run["expected"]["effort"]), ("claude-opus-5-5", "high"))
        self.assertIn("run record", run["expected"]["source"])
        self.assertEqual(run["status"], "pending · implement")
        for x in r.values():  # never a fake value
            self.assertEqual((x["observed"], x["observed_note"], x["mismatch"], x["team"]),
                             (None, "no telemetry yet", [], "claude-team"))
        _, _, out, _ = self.ccp("board", "status", root=self.main)
        self.assertIn("observed no telemetry yet", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("seat ")), 3)

    def test_the_runner_row_names_the_bound_runner(self):
        """§10.2: after a rotation the row shows the name work.json binds."""
        w = json.loads((self.q / "work.json").read_text()) if (self.q / "work.json").is_file() else {}
        (self.q / "work.json").write_text(json.dumps({**w, "runner": "runner-2"}))
        self.assertIn("runner (runner-2)", self.rows(self.build()))

    def test_a_row_per_runner_slot_with_the_task_it_holds(self):
        """§16.7: several runners: one row per slot, its bound name and its task; telemetry on the first."""
        self.ccp("tasks", "claim", "0002")
        st = json.loads((self.q / "tasks/0002-second.json").read_text())
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": "runner-2"}))
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "status": "running", "runners": {
            "runner-1": {"bound_name": "runner-1"}, "runner-2": {"bound_name": "runner-2-x"}}}))
        b = self.build()
        r = self.rows(b)
        self.assertIn("runner runner-1", r)
        self.assertIn("runner runner-2 (runner-2-x)", r)
        self.assertEqual(r["runner runner-1"]["status"], "running · no task")
        self.assertTrue(r["runner runner-2 (runner-2-x)"]["status"].startswith("running · 0002-second"))
        self.assertNotIn("runner", r)
        self.assertEqual([f["holder"] for f in b["now"]["flight"]], ["runner-2"])
        self.assertIn("on the runner runner-1 row", r["runner runner-2 (runner-2-x)"]["observed_note"])
        # a task held by no slot (the single runner's, left over) is named, not lost
        (self.q / "tasks/0002-second.json").write_text(json.dumps({**st, "lease_holder": "runner"}))
        notes = self.rows(self.build())["runner runner-2 (runner-2-x)"]["notes"]
        self.assertTrue(any("held by no runner slot: 0002-second" in n for n in notes), notes)

    def test_a_running_architect_pass_is_a_headless_row_and_is_not_reaped(self):
        st = {"schema_version": 1, "reviews": {"ar-20261021T100000Z-abcd": {
            "mode": "pass", "status": "running", "started_at": at(5)}}}
        (self.q / "architect.json").write_text(json.dumps(st))
        r = self.rows(self.build())["architect pass ar-20261021T100000Z-abcd"]
        self.assertEqual((r["kind"], r["status"], r["expected"]["model"], r["expected"]["effort"]),
                         ("headless", "running", "claude-opus-5-5", "high"))
        self.assertEqual(json.loads((self.q / "architect.json").read_text()), st)
        self.assertEqual(r["stale"], "lock gone")  # no lock, past the reaper's grace: shown, not reaped
        import os, socket
        (self.q / "architect.lock").write_text(json.dumps({"holder": "task-runner", "pid": os.getpid(), "host": socket.gethostname(),
                                                           "since": at(5), "ttl_seconds": 3600, "review_id": "ar-20261021T100000Z-abcd"}))
        self.assertIsNone(self.rows(self.build())["architect pass ar-20261021T100000Z-abcd"]["stale"])
        # its telemetry seat (the `ccp.seat` tag of §24) is its observed value, and not a row of its own
        t = at(1)
        fake = {"total": {"requests": 2}, "recent": {"runs": {}, "seats": {
            "architect-pass": [{"at": t, "model": "claude-opus-5-5", "effort": "high", "tokens": 10}],
            "spec-maintainer": [{"at": t, "model": "claude-opus-5-5", "effort": "xhigh", "tokens": 10}]}}}
        got = {r["seat"]: r for r in seats.collect(config.load(self.main), self.q, fake, {})["rows"]}
        a = got["architect pass ar-20261021T100000Z-abcd"]
        self.assertEqual((a["observed"]["model"], a["observed"]["effort"], a["mismatch"]), ("claude-opus-5-5", "high", []))
        self.assertNotIn("architect-pass", got)
        self.assertEqual(got["spec-maintainer"]["expected"]["source"], "not pinned by the plane")
        self.assertIn("keeps its own model and effort", got["spec-maintainer"]["notes"][0])


class Observed(Base, unittest.TestCase):
    def test_a_known_headless_session_is_not_the_lead_and_an_interactive_sdk_call_is(self):
        """An architect pass's `claude -p` calls folded onto the design seat. A session
        the plane launched (headless-usage.jsonl names it) is set aside on the lead's row; a call
        from any other session stays the lead's, whatever its query_source."""
        self.design_seat()
        (self.q / "board").mkdir(exist_ok=True)
        (self.q / "board" / "headless-usage.jsonl").write_text(json.dumps(
            {"at": at(1), "kind": "architect-pass", "review_id": "ar-x", "models": {}, "session_id": "S-pass"}) + "\n")
        mine = req("r3", 2, "claude-opus-5-5[1m]", "xhigh", query_source="sdk", session_id="S-lead", cwd=str(self.main))
        self.requests(req("r1", 5, "claude-opus-5-5", "high", query_source="sdk", session_id="S-pass"),
                      req("r2", 1, "claude-opus-5-5", "high", query_source="sdk", session_id="S-pass"), mine)
        b = self.build()
        lead = self.rows(b)["design seat"]
        self.assertEqual((lead["observed"]["model"], lead["observed"]["effort"], lead["observed"]["at"], lead["mismatch"]),
                         ("claude-opus-5-5[1m]", "xhigh", mine["at"], []))
        self.assertEqual(b["usage"]["seats"]["architect-pass"]["requests"], 2)  # the fold placed them (§24)
        # a fold that still put that session's rows on the lead (or the runner): the table sets them aside
        t = at(1)
        fake = {"total": {"requests": 3}, "headless": [{"session_id": "S-pass"}], "recent": {"runs": {}, "seats": {
            "design-seat": [{"at": t, "model": "claude-opus-5-5", "effort": "high", "tokens": 9, "session_id": "S-pass"},
                            {"at": t, "model": "claude-opus-5-5", "effort": "high", "tokens": 9, "session_id": "S-pass"},
                            {"at": mine["at"], "model": "claude-opus-5-5", "effort": "xhigh", "tokens": 9, "session_id": "S-lead"}]}}}
        lead = {r["seat"]: r for r in seats.collect(config.load(self.main), self.q, fake, {})["rows"]}["design seat"]
        self.assertEqual((lead["observed"]["effort"], lead["notes"]), ("xhigh", ["2 request(s) of headless sessions set aside"]))

    def test_the_fold_keeps_untagged_headless_calls_off_the_design_seat(self):
        """Pre-§24 architect rows in a product's records: `sdk`, no tag, no headless session, no cwd. They are the
        fold's `headless-untagged` seat, so Tokens by seat, the advice and the table agree."""
        self.design_seat()
        placed = req("r3", 1, "claude-opus-5-5", "xhigh", query_source="sdk", session_id="S-lead", cwd=str(self.main))
        self.requests(req("r1", 5, "claude-opus-5-5", "high", query_source="sdk", session_id="S-old"),
                      req("r2", 4, "claude-opus-5-5", "high", query_source="sdk", session_id="S-old"), placed)
        rep = usage.fold(self.q, None, {"model": "claude-opus-5-5", "effort": "xhigh"})
        self.assertEqual((rep["seats"][usage.UNTAGGED]["requests"], rep["seats"]["design-seat"]["requests"]), (2, 1))
        self.assertEqual((rep["how"]["untagged"], rep["advice"]), (2, []))
        b = self.build()
        self.assertEqual(b["usage"]["advice"], [])
        self.assertIn(usage.UNTAGGED, b["usage"]["seats"])
        lead = self.rows(b)["design seat"]
        self.assertEqual((lead["observed"]["effort"], lead["mismatch"]), ("xhigh", []))
        self.assertIn("2 untagged headless request(s) set aside (seat headless-untagged)", lead["notes"][0])
        _, _, out, _ = self.ccp("board", "status", root=self.main)
        self.assertNotIn("advice: the design seat", out)

    def test_untagged_headless_requests_are_a_note_not_a_pass(self):
        """The fold's `headless-untagged` seat: a running pass never adopts it; the lead's row says it."""
        st = {"schema_version": 1, "reviews": {"ar-1": {"mode": "pass", "status": "running", "started_at": at(10)}}}
        (self.q / "architect.json").write_text(json.dumps(st))
        t = at(1)
        fake = {"total": {"requests": 1}, "headless": [], "recent": {"runs": {}, "seats": {
            seats.UNTAGGED: [{"at": t, "model": "claude-opus-5-5", "effort": "high", "tokens": 5, "query_source": "sdk"}],
            "other-sessions": [{"at": t, "model": "claude-opus-5-5", "effort": "high", "tokens": 5}]}}}
        got = {r["seat"]: r for r in seats.collect(config.load(self.main), self.q, fake, {})["rows"]}
        self.assertIsNone(got["architect pass ar-1"]["observed"])
        self.assertEqual(got["design seat"]["notes"],
                         [f"1 untagged headless request(s) set aside (seat headless-untagged), latest {t}"])
        self.assertEqual(set(got), {"design seat", "runner", "architect pass ar-1"})  # no other-sessions row

    def test_from_a_fake_fold_the_main_model_and_latest_effort(self):
        helper = at(2)
        o = seats.observed([
            {"at": at(50), "model": "claude-opus-5-5", "effort": "low", "tokens": 9000},  # outside the 30 min window
            {"at": at(10), "model": "claude-opus-5-5", "effort": "xhigh", "tokens": 5000},
            {"at": helper, "model": "claude-haiku-4-5", "effort": None, "tokens": 300},  # a helper call
            {"at": at(4), "model": "claude-opus-5-5", "effort": "high", "tokens": 4000}])
        self.assertEqual((o["model"], o["effort"], o["at"], o["requests"], o["other_models"]),
                         ("claude-opus-5-5", "high", helper, 3, ["claude-haiku-4-5"]))
        self.assertIsNone(seats.observed([]))

    def test_mismatch(self):
        exp = {"model": "claude-sonnet-5-5", "effort": "high"}
        self.assertEqual(seats.mismatch(exp, {"model": "claude-sonnet-5-5", "effort": "high"}), [])
        self.assertEqual(seats.mismatch(exp, {"model": "claude-opus-5-5[1m]", "effort": "xhigh"}),
                         ["model claude-opus-5-5[1m], pinned claude-sonnet-5-5", "effort xhigh, pinned high"])
        self.assertEqual(seats.mismatch({"model": "claude-opus-5-5"}, {"model": "claude-opus-5-5[1m]"}, prefix=True), [])
        self.assertEqual(seats.mismatch({"model": "claude-opus-5-5[1m]"}, {"model": "claude-opus-5-5"}, prefix=True), [])
        self.assertEqual(seats.mismatch({"model": "claude-opus-5"}, {"model": "claude-opus-5-5"}, prefix=True),
                         ["model claude-opus-5-5, pinned claude-opus-5"])
        self.assertEqual(seats.mismatch(exp, None), [])

    def test_a_run_and_the_lead_from_the_telemetry_fold(self):
        self.design_seat()
        rid = self.open_implement()
        cfg = config.load(self.main)
        runs.bind(self.q, cfg, "delivery-implementer", "agent-1", "sess-1")
        r1 = req("r1", 3, "claude-sonnet-5-5", "high")
        self.requests(r1, req("r2", 1, "claude-opus-5-5[1m]", "high"),
                      spans=[{"request_id": "r1", "agent_id": "agent-1"}, {"request_id": "r2"}])
        b = self.build()
        r = self.rows(b)
        run, lead = r[f"implementer {rid}"], r["design seat"]
        self.assertEqual((run["observed"]["model"], run["observed"]["effort"]), ("claude-sonnet-5-5", "high"))
        self.assertEqual(run["mismatch"], ["model claude-sonnet-5-5, pinned claude-opus-5-5"])
        self.assertEqual(run["status"], "running · implement")
        self.assertEqual(run["last_activity"], {"at": r1["at"], "source": "telemetry"})
        self.assertEqual((lead["observed"]["model"], lead["status"]), ("claude-opus-5-5[1m]", "active"))
        self.assertEqual(lead["mismatch"], ["effort high, pinned xhigh"])  # the suffix is not a difference for the lead
        self.assertEqual(r["runner"]["observed_note"], "no telemetry yet")
        _, _, out, _ = self.ccp("board", "status", root=self.main)
        self.assertIn("[MISMATCH model claude-sonnet-5-5, pinned claude-opus-5-5]", out)
        self.assertIn("[ADVICE effort high, pinned xhigh]", out)

    def test_another_active_telemetry_seat_gets_a_row(self):
        self.requests(req("r1", 2, "claude-opus-5-5", "high"),
                      spans=[{"request_id": "r1", "agent_id": "probe@session-d7058efc"}])
        r = self.rows(self.build())
        self.assertEqual((r["teammate:probe"]["observed"]["model"], r["teammate:probe"]["expected"]["source"]),
                         ("claude-opus-5-5", "not pinned by the plane"))

    def test_a_build_writes_only_under_board(self):
        self.open_implement()
        self.requests(req("r1", 2, "claude-opus-5-5", "high"))

        def tree():
            return {str(p.relative_to(self.q)): p.read_bytes() for p in self.q.rglob("*")
                    if p.is_file() and p.relative_to(self.q).parts[0] != "board"}
        before = tree()
        self.build()
        self.assertEqual(tree(), before)


def render(b) -> str:
    js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
    r = subprocess.run(["node", "-e", STUB + js + "\nprocess.stdout.write(out.join(''));"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Rendered(Base, unittest.TestCase):
    def test_every_seat_string_renders_as_text(self):
        self.design_seat()
        self.open_implement()
        runs.bind(self.q, config.load(self.main), "delivery-implementer", "agent-1", "sess-1")
        self.requests(req("r1", 3, "claude-sonnet-5-5", "high"), spans=[{"request_id": "r1", "agent_id": "agent-1"}])
        b = self.build()
        b["now"]["seats"] = _hostile(b["now"]["seats"])
        html = render(b)
        self.assertIn("<h2>Seats</h2>", html)
        self.assertIn("&lt;!--&lt;script&gt;", html)
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)

    def test_a_seats_failure_renders_as_text(self):
        b = self.build()
        b["now"]["seats"] = {"error": HOSTILE, "rows": []}
        html = render(b)
        self.assertIn("Seats failed", html)
        self.assertNotIn("<img", html)


if __name__ == "__main__":
    unittest.main()
