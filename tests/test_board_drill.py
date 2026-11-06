"""SPEC §28.3: the board's per-task drill-down (ccp/drill.py): the interval maths, the idle
rule, the fallback for tasks before run records, the size bound, escaping, and `ccp board task`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ccp import board, drill
from tests.test_board_quality import HOSTILE, STUB, Base, _hostile

T0 = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc).timestamp()  # in the past: an open task runs to now


def at(s: float) -> str:
    """T0 + s as the RFC3339 the plane writes (with a fraction, as the telemetry does)."""
    return datetime.fromtimestamp(T0 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def at_s(s: float) -> str:
    return datetime.fromtimestamp(T0 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Intervals(unittest.TestCase):
    def test_overlapping_requests_are_a_union_not_a_sum(self):
        self.assertEqual(drill.length(drill.union([(0, 10), (5, 15), (20, 25), (24, 24), (30, 29)])), 20)
        p = drill.partition(0, 30, [(0, 10), (5, 15), (20, 25)], [])
        self.assertEqual((p["model_s"], p["other_s"], p["idle_s"], p["suite_s"]), (20, 10, 0, 0))

    def test_a_suite_counts_where_no_request_is_in_flight(self):
        # model 0-15 (two overlapping), a suite in the model gap 15-60, a suite under a request 70-80 / 75-90
        p = drill.partition(0, 100, [(0, 10), (5, 15), (75, 90)], [(15, 60), (70, 80)])
        self.assertEqual(p["model_s"], 30)
        self.assertEqual(p["suite_s"], 50)       # 45 + the 5 s before the request began
        self.assertEqual(p["suite_all_s"], 55)   # the whole suite union, model or not
        self.assertEqual((p["other_s"], p["idle_s"]), (20, 0))  # 60-70 and 90-100
        self.assertAlmostEqual(p["model_s"] + p["suite_s"] + p["other_s"] + p["idle_s"], p["wall_s"])
        self.assertEqual([k for _, _, k in p["segments"]], ["m", "s", "o", "s", "m", "o"])

    def test_intervals_outside_the_window_are_clipped(self):
        p = drill.partition(10, 20, [(0, 12), (18, 40)], [(-5, 11)])
        self.assertEqual((p["model_s"], p["suite_s"], p["other_s"]), (4, 0, 6))

    def test_a_gap_of_idle_gap_or_more_is_idle_a_shorter_one_other_tools(self):
        gap = drill.IDLE_GAP_S
        p = drill.partition(0, 3 * gap + 30, [(0, 10), (10 + gap - 1, gap + 19), (2 * gap + 19, 2 * gap + 30)], [])
        # 10 → gap+9: one second short of the rule (other); gap+19 → 2gap+19: exactly the rule (idle);
        # the tail after the last request, gap long: idle
        self.assertEqual(p["other_s"], gap - 1)
        self.assertEqual(p["idle_s"], 2 * gap)
        kinds = [k for _, _, k in p["segments"]]
        self.assertEqual(kinds, ["m", "o", "m", "i", "m", "i"])

    def test_no_telemetry_leaves_model_other_and_idle_unknown(self):
        p = drill.partition(0, 100, [], [(10, 40)], telemetry=False)
        self.assertEqual((p["model_s"], p["other_s"], p["idle_s"]), (None, None, None))
        self.assertEqual((p["suite_s"], p["unknown_s"]), (30, 70))

    def test_coarsen_bounds_segments_and_encode_round_trips(self):
        segs = [(i, i + 0.5, "m") for i in range(1000)] + [(i + 0.5, i + 1, "o") for i in range(1000)]
        segs.sort()
        out, coarse = drill.coarsen(segs, 0, 1000)
        self.assertTrue(coarse)
        self.assertLessEqual(len(out), drill.MAX_SEGMENTS)
        self.assertEqual((out[0][0], out[-1][1]), (0, 1000))
        few, coarse = drill.coarsen([(0, 5, "m"), (5, 7, "m"), (7, 9, "s")], 0, 9)
        self.assertEqual((few, coarse), ([(0, 7, "m"), (7, 9, "s")], False))  # neighbours joined, nothing lost
        s = drill.encode(few, 0)
        self.assertEqual(s, "m0+7 s7+2")
        self.assertEqual(drill.decode(s + " x<1+2 m1+"), few)  # junk tokens are skipped


class Fixture(Base):
    """A run of 0002-second with telemetry and suites, in flight."""

    def seed(self, n_requests: int = 3, note: str = "suite runs took long", wait: str = "spec_maintainer"):
        rid = "0002-second/implement"
        d = self.q / "runs" / "0002-second"
        d.mkdir(parents=True)
        (d / "implement.json").write_text(json.dumps({
            "schema_version": 1, "run_id": rid, "task_id": "0002-second", "phase": "implement", "round": 1,
            "seat": "implementer", "agent_type": "delivery-implementer", "expected_model": "claude-opus-5-5",
            "expected_effort": "high", "opened_at": at_s(0), "agent_id": "agent-1", "started_at": at_s(10),
            "stopped_at": at_s(2000), "reported_at": at_s(1990), "outcome": "done"}))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "task_id": "0002-second", "phase": "implementing"}))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks" / "0002-second.json").write_text(json.dumps({
            "task_id": "0002-second", "status": "implementing", "claimed_at": at_s(0), "depends_on": ["0001-first"]}))
        b = self.q / "board"
        b.mkdir(exist_ok=True)
        with (b / "usage-requests.jsonl").open("w") as rq, (b / "usage-spans.jsonl").open("w") as sp:
            # requests every 5 s from 10 s, 3 s each; then nothing from the last one to 2000 s
            for i in range(n_requests):
                a = 10 + 5 * i
                rq.write(json.dumps({"at": at(a + 3), "request_id": f"r{i}", "model": "claude-opus-5-5", "effort": "high",
                                     "query_source": "agent:custom", "input_tokens": 1, "output_tokens": 2,
                                     "cache_read_tokens": 3, "cache_creation_tokens": 4, "cost_usd": 0.01,
                                     "duration_ms": 3000}) + "\n")
                sp.write(json.dumps({"at": at(a), "end": at(a + 3), "request_id": f"r{i}", "agent_id": "agent-1",
                                     "model": "claude-opus-5-5", "effort": "high"}) + "\n")
        with (self.q / "runs" / "_suites.jsonl").open("w") as fh:
            fh.write(json.dumps({"op": "started", "suite_id": "st-1", "at": at_s(100), "lane": "full", "cmd": "unit.sh",
                                 "argc": 0, "run_id": rid, "task_id": "0002-second", "phase": "implement"}) + "\n")
            fh.write(json.dumps({"op": "ended", "suite_id": "st-1", "at": at_s(400), "exit_code": 0, "seconds": 300,
                                 "tests": 12, "interrupted": None}) + "\n")
        ev = self.q / "observability" / "events.jsonl"
        ev.parent.mkdir(exist_ok=True)
        with ev.open("a") as fh:
            for e in ({"type": "lease", "op": "set", "at": at_s(0), "payload": {"holder": "runner"}},
                      {"type": "waiting_on", "op": "set", "at": at_s(500), "payload": {"reason": wait, "detail": "sm-1"}},
                      {"type": "waiting_on", "op": "clear", "at": at_s(800), "payload": {"reason": "spec_resolved", "was": wait}}):
                fh.write(json.dumps({"project_id": "demo", "task_id": "0002-second", "actor": "task-runner", **e}) + "\n")
        self.note(at_s(1990), "implementer", note)
        return rid


class Built(Fixture, unittest.TestCase):
    def test_an_open_task_with_telemetry_is_split_into_model_suite_other_idle_and_runner(self):
        self.seed()
        b, _ = self.build()
        d = b["drill"]["0002-second"]
        self.assertTrue(d["open"])
        self.assertEqual(d["telemetry"], "runs")
        r = d["runs"][0]
        self.assertEqual(r["model_s"], 9)      # three 3 s requests
        self.assertEqual(r["suite_s"], 300)
        self.assertEqual(r["wall_s"], 1990)    # started 10 s to the later of stop and report
        self.assertEqual(r["idle_s"], 1990 - 9 - 300 - r["other_s"])
        self.assertGreater(r["idle_s"], 0)     # 25 → 100 s is a tool; 400 → 2000 s has nothing in flight
        self.assertEqual(r["other_s"], 6 + 75)
        self.assertEqual((r["suites"]["runs"], r["suites"]["by_lane"]["full"]["n"]), (1, 1))
        self.assertEqual((r["requests"], r["tokens"], r["models"], r["efforts"]), (3, 30, ["claude-opus-5-5"], ["high"]))
        # runner: claimed at 0, the run's agent started at 10 s, and the run ended at 2000 s: an open task runs to now
        self.assertAlmostEqual(d["split"]["runner_s"], d["wall_s"] - 1990, delta=0.2)
        self.assertGreater(d["wall_s"], 86400)
        self.assertEqual([(w["on"], w["s"], w["off"]) for w in d["waits"]], [("spec_maintainer", 300, 500)])
        self.assertEqual(d["friction"][0]["text"], "suite runs took long")
        self.assertEqual(drill.decode(r["segments"])[0][2], "m")

    def test_the_segments_of_a_run_are_bounded(self):
        self.seed(n_requests=390)
        b, page = self.build()
        r = b["drill"]["0002-second"]["runs"][0]
        self.assertTrue(r["coarsened"])
        self.assertLessEqual(len(r["segments"].split()), drill.MAX_SEGMENTS)
        self.assertEqual(r["model_s"], 390 * 3)  # totals come from the exact intervals, not the bins
        self.assertLess(len(json.dumps(b["drill"])), 40_000)

    def test_agent_text_in_notes_and_waits_stays_text(self):
        self.seed(note=HOSTILE, wait=HOSTILE)
        b, page = self.build()
        data = page.split("const B = ", 1)[1].split(";\nconst SEATS", 1)[0]
        for bad in ("<", ">", "&"):
            self.assertNotIn(bad, data)
        d = b["drill"]["0002-second"]
        self.assertIn("<!--<script>", d["friction"][0]["text"])
        self.assertIn("<img", d["waits"][0]["on"])
        self.assertEqual(page.count("<script>"), 1)

    def test_ccp_board_task_prints_the_breakdown_and_writes_nothing(self):
        self.seed()
        before = {p: p.stat().st_mtime_ns for p in self.q.rglob("*") if p.is_file()}
        code, _, out, err = self.ccp("board", "task", "0002", root=self.main)
        self.assertEqual(code, 0, err)
        self.assertIn("0002-second  open, implementing", out)
        self.assertIn("split: model 9s, suite 5m", out)
        self.assertIn("implement", out)
        self.assertIn("wait on spec_maintainer: +8m, 5m", out)
        self.assertIn("idle 27m", out)
        self.assertIn("friction", out)
        after = {p: p.stat().st_mtime_ns for p in self.q.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.q / "board" / "board.json").exists())
        code, _, _, err = self.ccp("board", "task", "9999", root=self.main)
        self.assertNotEqual(code, 0)
        self.assertIn("no task 9999", err)
        self.assertEqual(self.ccp("board", "task", root=self.main)[0], 2)

    def test_a_failing_drill_leaves_the_rest_of_the_board(self):
        self.seed()
        orig = drill.collect
        try:
            drill.collect = lambda *a, **k: 1 / 0
            b, _ = self.build()
        finally:
            drill.collect = orig
        self.assertIn("ZeroDivisionError", b["drill"]["_error"])
        self.assertIn("tasks", b)


class OldTask(unittest.TestCase):
    """A task merged before run records: phases from prompt stamps and report file times."""

    def test_phases_suite_lines_and_the_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            tid = "0216-docs-only-gate"
            (q / "prompts" / tid).mkdir(parents=True)
            (q / "progress" / tid).mkdir(parents=True)
            for off, ph in ((0, "implement"), (3600, "review"), (7200, "verify")):
                stamp = datetime.fromtimestamp(T0 + off, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                (q / "prompts" / tid / f"{stamp}_{ph}.json").write_text("{}")
            for ph, end, suite_line in (("implement", 3000, "Suite: 1049 tests, 508 s"), ("review", 4800, "Suite: 1050 tests, 510 s"),
                                        ("fix", 6000, "no suite"), ("verify", 8000, "Suite: 1050 tests, 513 s, mac")):
                f = q / "progress" / tid / f"{ph}-report.md"
                f.write_text(f"Outcome: done\n{suite_line}\n")
                os.utime(f, (T0 + end, T0 + end))
            row = {"task_id": tid, "merged_at": at_s(8600), "wall_s": 8600, "review_rounds": 1, "verify_rounds": 1, "fix_rounds": 1,
                   "implementing_s": 3600, "reviewing_s": 3000, "verifying_s": 1900, "times": "recorded"}
            d = drill.collect(q, [row], {"runs": [], "timeline": {}}, now=T0 + 9000)[tid]
        self.assertEqual(d["note"], drill.NO_RUNS)
        self.assertEqual(d["telemetry"], "none")
        self.assertEqual(d["runs"], [])
        self.assertEqual(d["split"]["unknown_s"], 8600)
        self.assertEqual([(p["phase"], p["off"], p["s"], p["suite_s"]) for p in d["phases"]],
                         [("implement", 0, 3000, 508), ("review", 3600, 1200, 510), ("fix", 4800, 1200, None),
                          ("verify", 7200, 800, 513)])
        self.assertEqual(d["reported_suite_s"], 1531)
        self.assertEqual(d["rounds"], {"review": 1, "verify": 1, "fix": 1})
        self.assertIn("no run telemetry", drill.text(d))


def _queue(tmp: str) -> Path:
    q = Path(tmp)
    (q / "runs").mkdir()
    (q / "tasks").mkdir()
    return q


def _run(q: Path, tid: str, phase: str, start: float, end: float | None, agent: str, **extra) -> str:
    rid = f"{tid}/{phase}"
    d = q / "runs" / tid
    d.mkdir(exist_ok=True)
    rec = {"schema_version": 1, "run_id": rid, "task_id": tid, "phase": phase, "round": 1, "agent_id": agent,
           "opened_at": at_s(start), "started_at": at_s(start), "stopped_at": at_s(end) if end is not None else None,
           "reported_at": at_s(end) if end is not None else None, **extra}
    (d / f"{phase}.json").write_text(json.dumps(rec))
    return rid


def _row(tid: str, wall: float, merged: float) -> dict:
    return {"task_id": tid, "merged_at": at_s(merged), "wall_s": wall, "review_rounds": 1, "verify_rounds": 0, "fix_rounds": 0}


class Guards(unittest.TestCase):
    """Review of #33: one bad row costs at most its own task's drill-down."""

    def test_a_bad_suite_row_and_a_bad_depends_on_leave_every_drill_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = _queue(tmp)
            a = _run(q, "0010-aaa", "implement", 0, 1000, "ag-a")
            _run(q, "0011-bbb", "implement", 2000, 3000, "ag-b")
            _run(q, "0012-ccc", "implement", 4000, 5000, "ag-c")
            with (q / "runs" / "_suites.jsonl").open("w") as fh:
                fh.write(json.dumps({"op": "started", "suite_id": "st-x", "at": at_s(10), "run_id": a, "task_id": "0010-aaa",
                                     "lane": "full"}) + "\n")
                fh.write(json.dumps({"op": "ended", "suite_id": "st-x", "at": at_s(100), "exit_code": "<b>",
                                     "seconds": "not a number", "tests": "<img>"}) + "\n")
            (q / "tasks" / "0011-bbb.json").write_text(json.dumps({"task_id": "0011-bbb", "depends_on": [["a"], {"b": 1}, 7]}))
            (q / "tasks" / "0012-ccc.json").write_text(json.dumps({"task_id": "0012-ccc", "depends_on": "0010-aaa"}))
            rows = [_row("0010-aaa", 1000, 1000), _row("0011-bbb", 1000, 3000), _row("0012-ccc", 1000, 5000)]
            out = drill.collect(q, rows, {"runs": [], "timeline": {}}, now=T0 + 9000)
            self.assertEqual(sorted(out), ["0010-aaa", "0011-bbb", "0012-ccc"])
            for d in out.values():
                self.assertNotIn("_error", d)
            r = out["0010-aaa"]["runs"][0]
            self.assertEqual(r["suite_s"], 90)  # the interval is known from its rows' times
            self.assertEqual(r["suites"]["list"][0]["s"], None)  # the bad seconds, not a crash
            self.assertIsNone(out["0011-bbb"]["queue_wait_s"])
            # and a record that raises costs only its own task
            orig = drill.record

            def flaky(q_, tid, *a, **k):
                if tid == "0011-bbb":
                    raise ValueError("bad row")
                return orig(q_, tid, *a, **k)
            drill.record = flaky
            try:
                out = drill.collect(q, rows, {"runs": [], "timeline": {}}, now=T0 + 9000)
            finally:
                drill.record = orig
            self.assertEqual(out["0011-bbb"], {"task_id": "0011-bbb", "_error": "ValueError: bad row"})
            self.assertIn("split", out["0010-aaa"])
            self.assertIn("split", out["0012-ccc"])
            self.assertIn("failed to build", drill.text(out["0011-bbb"]))


class Overlaps(unittest.TestCase):
    def test_overlapping_runs_count_each_instant_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = _queue(tmp)
            _run(q, "0010-aaa", "implement", 0, 1000, "ag-i")
            _run(q, "0010-aaa", "review", 600, 1400, "ag-r")
            tl = {"0010-aaa/implement": [(T0 + 0, T0 + 1000)], "0010-aaa/review": [(T0 + 600, T0 + 700)]}
            rep = {"runs": [{"run_id": k, "usage": {"requests": 1}, "flags": []} for k in tl], "timeline": tl}
            d = drill.collect(q, [_row("0010-aaa", 2000, 2000)], rep, now=T0 + 9000)["0010-aaa"]
        sp = d["split"]
        self.assertEqual(d["overlap_s"], 400)
        self.assertEqual(sp["model_s"], 1000)  # review's request lies under implement's: once
        self.assertEqual(sp["other_s"], 0)
        # review idles 700-1400 in its own window, but 700-1000 is implement's model time: 400 s idle
        self.assertEqual(d["runs"][1]["idle_s"], 700)
        self.assertEqual((sp["idle_s"], sp["runner_s"]), (400, 600))
        self.assertAlmostEqual(sum(sp.values()), d["wall_s"])

    def test_a_running_run_on_a_merged_task_ends_at_the_merge_and_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = _queue(tmp)
            _run(q, "0010-aaa", "verify", 100, None, "ag-v")
            d = drill.collect(q, [_row("0010-aaa", 1000, 1000)], {"runs": [], "timeline": {}}, now=T0 + 90000)["0010-aaa"]
        r = d["runs"][0]
        self.assertTrue(r["stale_run"])
        self.assertEqual((r["wall_s"], r["end_at"]), (900, at_s(1000)))
        self.assertAlmostEqual(sum(d["split"].values()), d["wall_s"])
        self.assertIn("stale", drill.text(d))


class LiveTail(unittest.TestCase):
    def collect(self, minutes: float, fresh: bool = False):
        with tempfile.TemporaryDirectory() as tmp:
            q = _queue(tmp)
            (q / "tasks" / "0010-aaa.json").write_text(json.dumps({"task_id": "0010-aaa", "status": "implementing",
                                                                  "claimed_at": at_s(0)}))
            _run(q, "0010-aaa", "implement", 0, None, "ag-i")
            tl = {"0010-aaa/implement": [(T0 + 0, T0 + 600)]}  # its last request ended at +10 min
            if fresh:  # another session's request, minutes ago: the receiver is up
                tl["0011-bbb/implement"] = [(T0 + 60 * minutes - 120, T0 + 60 * minutes - 60)]
            rep = {"runs": [{"run_id": "0010-aaa/implement", "usage": {"requests": 1}, "flags": []}], "timeline": tl}
            return drill.collect(q, [], rep, now=T0 + 60 * minutes)["0010-aaa"]

    def test_a_live_runs_tail_is_live_not_idle(self):
        for minutes in (15, 60):
            d = self.collect(minutes)
            r = d["runs"][0]
            self.assertEqual(r["idle_s"], 0, minutes)
            self.assertEqual(r["live_s"], 60 * minutes - 600, minutes)
            self.assertEqual(r["live_since"], at_s(600))
            self.assertEqual(d["split"]["live_s"], 60 * minutes - 600)
            self.assertIn("l", {k for _, _, k in drill.decode(r["segments"])})
            self.assertIn("live, no telemetry since 09:10", drill.text(d))

    def test_a_fresh_receiver_makes_the_tail_idle(self):
        r = self.collect(60, fresh=True)["runs"][0]
        self.assertEqual((r["live_s"], r["idle_s"]), (0, 3000))


class PreTelemetry(unittest.TestCase):
    def test_the_stretch_before_telemetry_is_unmeasured_not_idle(self):
        p = drill.partition(0, 2000, [(1500, 1600)], [], measured_from=1500)
        self.assertEqual((p["unknown_s"], p["idle_s"], p["other_s"]), (1500, 0, 400))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Rendered(Fixture, unittest.TestCase):
    def render(self, b):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        tail = "\nfor (const id of Object.keys(B.drill || {})) out.push(drillHtml(id));\nprocess.stdout.write(out.join(''));"
        r = subprocess.run(["node", "-e", STUB + js + tail], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_every_string_in_the_drill_renders_as_text(self):
        """The page and each drill-down, rendered in node with every board string made hostile."""
        self.seed()
        b = self.build()[0]
        html = self.render(_hostile(b))
        self.assertIn("Friction notes", html)
        self.assertIn("&lt;!--&lt;script&gt;", html)
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)

    def test_the_drill_draws_the_runs_and_the_chart_stacks_the_split(self):
        self.seed()
        b = self.build()[0]
        html = self.render(b)
        self.assertIn('aria-label="Runs of 0002-second on a time axis"', html)
        self.assertIn("var(--s1)", html)  # model segments
        self.assertIn("spec_maintainer", html)
        self.assertIn('data-drill="0"', html)  # the Now panel's task opens it


HASH_STUB = """
const out = [], panel = [];
const el = (id) => ({style: {}, dataset: {}, hidden: true, addEventListener() {}, append(x) { out.push(x); }, setAttribute() {},
  querySelectorAll: () => [], set innerHTML(h) { if (id === "drill") panel.push(h); }, get innerHTML() { return ""; }});
globalThis.document = {createElement: () => { const t = {set innerHTML(h) { this.content = h; }}; return t; },
  getElementById: (id) => el(id), querySelectorAll: () => [], documentElement: el()};
globalThis.localStorage = {getItem: () => null, setItem() {}};
globalThis.matchMedia = () => ({matches: false});
globalThis.innerWidth = 800; globalThis.innerHeight = 800; globalThis.setTimeout = () => 0;
globalThis.history = {replaceState() {}};
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Hash(Fixture, unittest.TestCase):
    """#task=<id> reopens a drill-down after the reload; an injected hash renders nothing raw."""

    def open_with(self, page_js: str, h: str):
        loc = "globalThis.location = {hash: %s, pathname: '/b', search: ''};\n" % json.dumps(h)
        r = subprocess.run(["node", "-e", HASH_STUB + loc + page_js + "\nprocess.stdout.write(JSON.stringify(panel));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_injected_hashes_open_nothing_and_a_real_one_opens_its_drill(self):
        self.seed()
        b = self.build()[0]
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        for h in ("#task=__proto__", "#task=constructor", "#task=toString", "#task=<img src=x onerror=alert(1)>",
                  "#task=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E", "#task=%E0%A4%A", "#task=", "#task=_error"):
            self.assertEqual(self.open_with(js, h), [], h)
        opened = self.open_with(js, "#task=0002-second")
        self.assertEqual(len(opened), 1)
        self.assertIn("Runs of 0002-second on a time axis", opened[0])
        self.assertNotIn("<img", opened[0])


if __name__ == "__main__":
    unittest.main()
