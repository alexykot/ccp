"""SPEC §16.7 (step 5 of the parallel-runners build): what parallel work records and shows. `peak_in_flight` on each task
held, `undeclared_paths` at close, the forecast's slots (one slot is the model before §16, exactly),
gaps from serial history only, and the board's list of every task in flight."""
from __future__ import annotations

import json
import unittest

from ccp import board, config, forecast, lifecycle, tasklog
from tests import test_parallel_claims
from tests.test_parallel_claims import task
from tests.test_toolkit import git

NOW = 1_800_000_000.0


class Slots(unittest.TestCase):
    def run_(self, slots=1, alone=None, order=("a", "b", "c", "d")):
        dur = {t: forecast.lognormal(3600, 5400) for t in order}
        r = forecast.simulate(list(order), {}, dur, {}, [0.0], NOW, {}, trials=300, targets={"all": list(order)},
                              slots=slots, alone=alone)
        return sorted(r["targets"]["all"]["end"])

    def test_one_slot_is_the_model_before(self):
        dur = {t: forecast.lognormal(3600, 5400) for t in "abcd"}
        before = forecast.simulate(list("abcd"), {}, dur, {}, [0.0], NOW, {}, trials=300, targets={"all": list("abcd")})
        self.assertEqual(sorted(before["targets"]["all"]["end"]), self.run_(1))
        self.assertEqual(self.run_(1), self.run_(1, alone={"a", "b"}))  # alone means nothing with one slot

    def test_two_slots_finish_sooner_and_a_lone_task_takes_both(self):
        one, two = self.run_(1), self.run_(2)
        median = lambda xs: xs[len(xs) // 2]  # noqa: E731
        self.assertLess(median(two) - NOW, 0.75 * (median(one) - NOW))
        self.assertGreater(median(self.run_(2, alone={"a", "b", "c", "d"})), median(two))
        self.assertEqual(self.run_(2, alone=set("abcd")), one)  # all alone: serial again

    def test_a_lone_task_in_flight_holds_every_slot(self):
        dur = {t: forecast.lognormal(3600, 5400) for t in "ab"}
        run = lambda alone: sorted(forecast.simulate(  # noqa: E731
            ["a", "b"], {}, dur, {}, [0.0], NOW, {"a": 600.0}, trials=300, targets={"b": ["b"]}, slots=2,
            alone=alone)["targets"]["b"]["end"])
        self.assertGreater(run({"a"})[150], run(set())[150])


class Apart(unittest.TestCase):
    """§16.7: the forecast starts a task after every task ahead of it that rule 3 keeps it from running beside."""

    def ends(self, apart, slots=2, target=("a", "b", "c", "d"), gaps=(0.0,)):
        order = list("abcd")
        dur = {t: forecast.lognormal(3600, 5400) for t in order}
        r = forecast.simulate(order, {}, dur, {}, list(gaps), NOW, {}, trials=300, targets={"all": order, "ab": list(target)},
                              slots=slots, apart=apart)
        return r["targets"]

    def test_none_and_empty_are_the_model_before(self):
        order = list("abcd")
        dur = {t: forecast.lognormal(3600, 5400) for t in order}
        before = forecast.simulate(order, {}, dur, {}, [0.0], NOW, {}, trials=300, targets={"all": order}, slots=2)
        self.assertEqual(self.ends(None)["all"], before["targets"]["all"])
        self.assertEqual(self.ends({})["all"], before["targets"]["all"])

    def test_a_pair_kept_apart_runs_one_after_the_other(self):
        median = lambda xs: sorted(xs)[len(xs) // 2]  # noqa: E731
        free = self.ends(None, target=("a", "b"))["ab"]["end"]
        held = self.ends({"b": {"a"}}, target=("a", "b"))["ab"]["end"]
        self.assertGreater(median(held), median(free))
        self.assertTrue(all(h >= f for h, f in zip(held, free)))

    def test_every_task_kept_apart_from_every_earlier_one_is_the_one_slot_run(self):
        every = {"b": {"a"}, "c": {"a", "b"}, "d": {"a", "b", "c"}}
        self.assertEqual(self.ends(every)["all"]["end"], self.ends(None, slots=1)["all"]["end"])

    def test_a_task_kept_apart_from_a_later_one_or_an_unknown_one_waits_for_nothing(self):
        self.assertEqual(self.ends({"a": {"d"}, "b": {"zz"}})["all"], self.ends(None)["all"])


class Records(test_parallel_claims.ParallelFixture, unittest.TestCase):
    def state(self, tid):
        return json.loads((self.q / f"tasks/{tid}.json").read_text())

    def test_each_held_task_records_the_most_held_at_once(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.state("0002-second")["peak_in_flight"], 1)
        self.assertEqual(self.claim("0003")[0], 0)
        self.assertEqual((self.state("0002-second")["peak_in_flight"], self.state("0003-third")["peak_in_flight"]), (2, 2))
        self.ccp("tasks", "release", "0003", "--reason", "t", root=self.main)
        self.assertEqual(self.claim("0007")[0], 0)
        self.assertEqual(self.state("0002-second")["peak_in_flight"], 2)  # the most, not the latest
        w = self.work()  # a stale id in in_flight (no lease any more) does not count
        (self.q / "work.json").write_text(json.dumps({**w, "in_flight": w["in_flight"] + ["0099-gone"]}))
        self.ccp("tasks", "release", "0007", "--reason", "t", root=self.main)
        self.assertEqual(self.claim("0007")[0], 0)
        self.assertEqual(self.state("0007-watch")["peak_in_flight"], 2)

    def test_undeclared_paths_are_the_merges_files_its_scope_missed(self):
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "the fixture's tasks")
        for rel in ("src/app/pool.py", "src/app/reads.py", "tests/test_pool.py", "tests/sf_fixtures.py"):
            self.write(rel, "x\n")
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "a merge")
        sha = git(self.main, "rev-parse", "HEAD").strip()
        cfg = config.load(self.main)
        meta = next(t for t in tasklog.load(cfg) if t["task_id"] == "0002-second")
        self.assertEqual(sorted(lifecycle._undeclared(cfg, meta, sha)), ["src/app/reads.py", "tests/sf_fixtures.py"])
        f = self.main / "docs/delivery/tasks/0002-second.md"  # the task's own file rides along: never undeclared
        f.write_text(f.read_text() + "\n- 2026-10-28 note\n")
        git(self.main, "commit", "-q", "-am", "with its task file")
        sha = git(self.main, "rev-parse", "HEAD").strip()
        self.assertEqual(lifecycle._undeclared(config.load(self.main), meta, sha), [])
        self.plane()  # parallel off: nothing is recorded
        self.assertIsNone(lifecycle._undeclared(config.load(self.main), meta, sha))

    def test_gaps_are_measured_where_a_task_starts_alone_but_every_merge_moves_the_frontier(self):
        (self.q / "tasks").mkdir(exist_ok=True)
        for tid, peak in (("000a-a", 1), ("000b-b", 2), ("000c-c", 2), ("000d-d", 1)):
            (self.q / f"tasks/{tid}.json").write_text(json.dumps({"peak_in_flight": peak}))
        h = 3600.0
        iso = lambda x: forecast.iso(NOW + x)  # noqa: E731
        drill = {"000a-a": {"start_at": iso(0), "merged_at": iso(1 * h)},
                 "000b-b": {"start_at": iso(1 * h + 60), "merged_at": iso(3 * h)},
                 "000c-c": {"start_at": iso(1 * h + 90), "merged_at": iso(2.9 * h)},
                 "000d-d": {"start_at": iso(3 * h + 180), "merged_at": iso(4 * h)}}
        tp = forecast.throughput(forecast.windows(drill, forecast._held_alone(self.q, drill)))
        self.assertEqual((tp["gaps"], tp["stops"]), ([180.0], 0))  # D after C's and B's merges, not after A's

    def test_the_board_lists_every_task_in_flight(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.claim("0003")[0], 0)
        fl = board._flight(self.q, self.work())
        self.assertEqual([(f["task_id"], f["phase"], f["peak_in_flight"]) for f in fl],
                         [("0002-second", "leased", 2), ("0003-third", "leased", 2)])
        self.assertTrue(all(f["since"] for f in fl))

    def throughput(self, third_extra="", **par):
        """`ccp forecast --backlog --json` with two pending tasks whose declared paths meet."""
        self.plane(max_in_flight=2, **par)
        self.write("docs/delivery/tasks/0002-second.md", task("0002-second", "`src/app/pool.py`"))
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/pool.py`", extra=third_extra))
        for tid in ("0004-fourth", "0005-fifth", "0006-sixth", "0007-watch"):
            self.write(f"docs/delivery/tasks/{tid}.md", task(tid, "`other/x.py`", status="dropped"))
        (self.q / "estimates").mkdir(exist_ok=True)
        for tid in ("0002-second", "0003-third"):
            (self.q / "estimates" / f"{tid}.jsonl").write_text(json.dumps({
                "at": "2026-10-22T10:00:00Z", "task_id": tid, "version": 1, "source": "baseline",
                "total": {"p50_s": 600, "p90_s": 900}, "tokens": None, "cost_usd": None}) + "\n")
        code, body, out, err = self.ccp("forecast", "--backlog", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["order"], ["0002-second", "0003-third"])
        return body

    def test_the_forecast_reads_rule_3_through_the_claims_predicate_under_either_schedule(self):
        hours = {}
        for par, extra, schedule, pairs in (({}, "", "paths", 1),
                                            ({"schedule": "clashes"}, "", "clashes", 0),
                                            ({"schedule": "clashes"}, "clashes_with: [0002-second]\n", "clashes", 1)):
            body = self.throughput(extra, **par)
            tp = body["throughput"]
            self.assertEqual((tp["schedule"], tp["apart_pairs"], tp["slots"]), (schedule, pairs, 2))
            self.assertNotIn("paths meet", tp["text"])
            self.assertIn(f"{pairs} pair(s) of tasks kept apart", tp["text"])
            self.assertIn(f"parallel.schedule {schedule}", tp["text"])
            hours[(schedule, pairs)] = body["backlog"]["hours"]
        # the dates the lead reads: the pair kept apart runs one after the other, the free pair side by side
        self.assertGreater(hours[("paths", 1)]["p50"], hours[("clashes", 0)]["p50"])
        self.assertEqual(hours[("paths", 1)], hours[("clashes", 1)])

    def test_one_slot_has_no_pairs_to_report(self):
        self.plane(max_in_flight=1)
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/pool.py`"))
        (self.q / "estimates").mkdir(exist_ok=True)
        (self.q / "estimates" / "0002-second.jsonl").write_text(json.dumps({
            "at": "2026-10-22T10:00:00Z", "task_id": "0002-second", "version": 1, "source": "baseline",
            "total": {"p50_s": 600, "p90_s": 900}, "tokens": None, "cost_usd": None}) + "\n")
        code, body, out, err = self.ccp("forecast", "--backlog", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("apart_pairs", body["throughput"])


if __name__ == "__main__":
    unittest.main()
