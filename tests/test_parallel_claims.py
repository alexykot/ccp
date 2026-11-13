"""SPEC §16.3 (step 2 of the parallel-runners build): which tasks the runner may hold at once. Scope paths, the meet rule,
the claim's refusals (exit 7), `next`'s head of line and slots-full exit, and nothing changed while
`parallel.max_in_flight` is 1."""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import cli, config, parallel, plan, tasklog
from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture


def task(tid: str, scope_in: str, status: str = "pending", extra: str = "") -> str:
    text = TASK.format(tid=tid, title=tid[5:].title(), status=status, deps="", ver="*Append-only.*")
    text = text.replace("- **In:** it", f"- **In:** {scope_in}\n- **Out:** `other/thing.py`")
    return text.replace("updated: 2026-09-30\n", f"updated: 2026-09-30\n{extra}") if extra else text


class Meets(unittest.TestCase):
    def test_the_meet_rule(self):
        yes = [("src/app/pool.py", "src/app/pool.py"), ("src/app/", "src/app/pool.py"), ("ops", "ops/x.sh"),
               ("grok/**", "grok/playbooks/run.md"), ("tests/test_*.py", "tests/test_pool.py"),
               (".claude.md", "src/app/.claude.md"), ("a/**/b.py", "a/b.py"), ("grok/**", "grok/*.md"),
               ("db/", "db/**"), ("src/app/", "src/app/**"), ("tests/", "tests/test_*.py"), ("docs/sf", "docs/**/x.md"),
               ("docs/", "docs/sf/*.md")]
        no = [("src/app/pool.py", "src/app/views.py"), ("src/sf", "src/sfx/a.py"), ("tests/test_*.py", "tests/sub/test_a.py"),
              (".claude.md", "src/app/claude.md"), ("db/schema.sql", "db/schema.sql.bak"), ("db/", "src/db/**"),
              ("docs/sf/a.py", "docs/**/x.md")]
        for a, b in yes:
            self.assertTrue(parallel.meets(a, b) and parallel.meets(b, a), (a, b))
        for a, b in no:
            self.assertFalse(parallel.meets(a, b) or parallel.meets(b, a), (a, b))


class ParallelFixture(ToolkitFixture):
    """Six tasks with Scope paths, parallel on at 2, a 5-hour reading the test sets."""

    def setUp(self):
        super().setUp()
        self.reading = Path(self._tmp.name) / "reading.json"
        self.five(10)
        self.plane(max_in_flight=2, exclusive=["db/schema.sql"])
        self.write("Makefile", "all:\n")
        self.write("docs/delivery/tasks/0002-second.md",
                   task("0002-second", "`src/app/pool.py` (`coverage`), `tests/test_pool.py`, `Makefile`"))
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/views.py`, `tests/test_views.py`"))
        self.write("docs/delivery/tasks/0004-fourth.md", task("0004-fourth", "`src/app/pool.py` (the probe rule)"))
        self.write("docs/delivery/tasks/0005-fifth.md", task("0005-fifth", "`db/schema.sql`, `src/db.py`"))
        self.write("docs/delivery/tasks/0006-sixth.md", task("0006-sixth", "an operator step, nothing in the repo"))
        self.write("docs/delivery/tasks/0007-watch.md", task("0007-watch", "a watch", extra="parallel: true\n"))
        (self.q / "work.json").write_text(json.dumps({"status": "running"}))

    def plane(self, **par):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {"allowance_cmd": f"cat '{self.reading}'"}
        cfg["parallel"] = par
        self.write("docs/delivery/plane.json", json.dumps(cfg))

    def five(self, pct):
        self.reading.write_text(json.dumps({"five_hour": {"utilization": pct}, "seven_day": {"utilization": 5}}))

    def claim(self, tid):
        return self.ccp("tasks", "claim", tid, root=self.main)

    def next(self):
        return self.ccp("tasks", "next", root=self.main)

    def work(self):
        return json.loads((self.q / "work.json").read_text())


class Claims(ParallelFixture, unittest.TestCase):
    def test_paths_come_from_the_in_item_only(self):
        cfg = config.load(self.main)
        t = {"_text": (self.main / "docs/delivery/tasks/0002-second.md").read_text()}
        self.assertEqual(parallel.paths(cfg, t), ["src/app/pool.py", "tests/test_pool.py", "Makefile"])
        # module.attr symbols are not paths; a known suffix, a trailing comma inside the ticks, are
        t = {"_text": task("0009-x", "`entries.close`, `sys.path`, `base.VENUES`, `notes.md`, `ops/run.sh,`")}
        self.assertEqual(parallel.paths(cfg, t), ["notes.md", "ops/run.sh"])

    def test_two_tasks_in_unrelated_paths_run_together(self):
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.next()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("0003-third"), out)  # 0002 is in flight, not returned again
        self.assertEqual(self.claim("0003")[0], 0)
        self.assertEqual(self.work()["in_flight"], ["0002-second", "0003-third"])
        code, _, out, _ = self.next()  # two of two: carry on
        self.assertEqual(code, 7, out)
        self.assertIn("slots full", out)
        self.assertIn("rule 1", out)

    def test_meeting_paths_are_refused_and_the_head_of_line_waits(self):
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/pool.py`"))
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("`src/app/pool.py` meets in-flight 0002-second", err)
        self.assertNotIn("0003-third", self.work()["in_flight"])
        self.assertFalse((self.q / "tasks/0003-third.json").exists())  # refused before anything was written
        # next does not skip 0003 for a later task that could join: it waits at the head of the line
        code, body, out, _ = self.ccp("tasks", "next", "--json", root=self.main)
        self.assertEqual(code, 7, out)
        self.assertEqual((body["slots_full"], body["head"], body["in_flight"]), (True, "0003-third", ["0002-second"]))

    def test_exclusive_no_path_and_parallel_false_run_alone(self):
        self.assertEqual(self.claim("0005")[0], 0)  # alone: allowed
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7)
        self.assertIn("is exclusive", err)
        self.ccp("tasks", "release", "0005", "--reason", "t", root=self.main)
        self.assertEqual(self.claim("0003")[0], 0)
        code, _, _, err = self.claim("0006")  # no path, no parallel: true
        self.assertEqual(code, 7)
        self.assertIn("names no path", err)
        self.assertEqual(self.claim("0007")[0], 0, "parallel: true changes no file and runs beside anything")

    def test_the_session_ceiling_and_an_unknown_reading(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.five(60)
        code, _, _, err = self.claim("0003")
        self.assertEqual(code, 7)
        self.assertIn("rule 5", err)
        self.reading.write_text("not json")
        code, _, _, err = self.claim("0003")
        self.assertEqual(code, 7)
        self.assertIn("unknown", err)
        self.five(59)
        self.assertEqual(self.claim("0003")[0], 0)

    def test_no_five_hour_figure_means_no_five_hour_limit(self):
        """§16.3 rule 5: since 2026-10-31 the endpoint gives the weekly figure only."""
        self.reading.write_text(json.dumps({"seven_day": {"utilization": 43}}))
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, _ = self.next()
        self.assertEqual(code, 0, out)  # a fresh weekly-only sample: next offers the second task
        self.assertTrue(out.startswith("0003-third"), out)
        self.assertEqual(self.claim("0003")[0], 0)

    def _allowance_cmd(self, cmd):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["telemetry"] = {"allowance_cmd": cmd} if cmd else {}
        self.write("docs/delivery/plane.json", json.dumps(cfg))

    def test_without_a_usage_command_a_second_task_is_claimed(self):
        self._allowance_cmd(None)
        self.assertEqual(self.claim("0002")[0], 0)
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.work()["in_flight"], ["0002-second", "0003-third"])

    def test_without_a_usage_command_next_offers_a_second_task(self):
        self._allowance_cmd(None)
        self.assertEqual(self.claim("0002")[0], 0)
        board = self.q / "board" / "allowance.jsonl"  # a fresh reading left from before is not judged
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 60))
        board.parent.mkdir(parents=True, exist_ok=True)
        board.write_text(json.dumps({"at": stamp, "five_hour": 80, "seven_day": 5}) + "\n")
        code, _, out, _ = self.next()
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("0003-third"), out)

    def test_a_usage_command_that_prints_nothing_still_refuses(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self._allowance_cmd("true")
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("rule 5", err)

    def test_a_resume_is_never_refused(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.claim("0003")[0], 0)
        self.five(70)  # above the ceiling, below the 5-hour park (§25.4)
        self.assertEqual(self.claim("0002")[0], 0)

    def test_off_by_default(self):
        self.plane()  # no keys: max_in_flight 1
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.claim("0004")[0], 0, "one task at a time is not enforced by claim before §16")
        code, _, out, _ = self.next()
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("0002-second"), out)  # as before: the in-flight task, to resume
        _, _, out, _ = self.ccp("tasks", "check", root=self.main)
        self.assertNotIn("SPEC §16.3", out)

    def test_check_warns_about_tasks_that_will_only_run_alone(self):
        _, _, out, _ = self.ccp("tasks", "check", root=self.main)
        self.assertIn("0006-sixth.md: no path", out)
        self.assertNotIn("0007-watch.md: no path", out)

    def test_next_judges_the_ceiling_on_a_fresh_sample_only(self):
        self.assertEqual(self.claim("0002")[0], 0)
        board = self.q / "board" / "allowance.jsonl"
        stamp = lambda ago: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - ago))  # noqa: E731
        board.write_text(json.dumps({"at": stamp(60), "five_hour": 80, "seven_day": 5}) + "\n")
        code, _, out, _ = self.next()
        self.assertEqual(code, 7, out)
        self.assertIn("rule 5", out)
        board.write_text(json.dumps({"at": stamp(3600), "five_hour": 80, "seven_day": 5}) + "\n")
        code, _, out, _ = self.next()  # stale: next offers it, the claim samples anew
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("0003-third"), out)

    def test_the_board_agrees_with_next(self):
        self.assertEqual(self.claim("0002")[0], 0)
        cfg = config.load(self.main)
        rq = plan.ready_queue(cfg, self.q, tasklog.load(cfg))
        self.assertEqual((rq["next"], rq["slots_full"]), ("0003-third", None))
        self.assertEqual(self.claim("0003")[0], 0)
        rq = plan.ready_queue(cfg, self.q, tasklog.load(cfg))
        self.assertEqual(rq["next"], None)
        self.assertIn("rule 1", rq["slots_full"]["reason"])

    def test_an_overdue_architect_gate_still_wins_over_full_slots(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.assertEqual(self.claim("0003")[0], 0)
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {}}))
        with mock.patch.object(cli, "_architect_gate", return_value=4) as gate:
            self.assertEqual(self.next()[0], 4)
        gate.assert_called_once()

    def test_the_weekly_stop_and_a_stopped_runner_say_more_than_exit_7(self):
        self.assertEqual(self.claim("0002")[0], 0)
        self.write("docs/delivery/tasks/0003-third.md", task("0003-third", "`src/app/pool.py`"))  # would meet
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["telemetry"]["allowance_stop_weekly"] = 4
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        self.assertEqual(self.claim("0003")[0], 5)
        cfg["telemetry"]["allowance_stop_weekly"] = None
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        w = self.work()
        (self.q / "work.json").write_text(json.dumps({**w, "status": "draining"}))
        self.assertEqual(self.claim("0003")[0], 3)

    def test_check_warns_about_a_scope_path_that_does_not_exist(self):
        """A path neither in the checkout nor marked new."""
        self.write("docs/delivery/tasks/0008-eighth.md", task(
            "0008-eighth", "`src/app/gone.py`, tests (`tests/test_fresh.py`, new), `markets.py`, `src/app/*.py`, "
                           "`src/made_by_dep.py`").replace("depends_on: []", 'depends_on: ["0009-ninth"]'))
        self.write("docs/delivery/tasks/0009-ninth.md", task("0009-ninth", "`src/made_by_dep.py` (new)"))
        _, _, out, _ = self.ccp("tasks", "check", root=self.main)
        self.assertIn("0008-eighth.md: Scope names `src/app/gone.py`, which does not exist", out)
        self.assertNotIn("`tests/test_fresh.py`", out)  # marked new, past the comma
        self.assertNotIn("`markets.py`", out)  # a bare name: often relative to a sibling path
        self.assertNotIn("`src/made_by_dep.py`, which", out)  # a dependency makes it

    def test_a_marking_applies_only_to_the_path_it_follows(self):
        self.write("docs/delivery/tasks/0008-eighth.md", task("0008-eighth", "`a/x.py`, `b/y.py` (removed)"))
        self.write("docs/delivery/tasks/0009-ninth.md", task("0009-ninth", "`c/z.py` `d/w.py`, new"))
        _, _, out, _ = self.ccp("tasks", "check", root=self.main)
        self.assertIn("0008-eighth.md: Scope names `a/x.py`, which does not exist", out)
        self.assertNotIn("`b/y.py`", out)
        self.assertIn("0009-ninth.md: Scope names `c/z.py`, which does not exist", out)
        self.assertNotIn("`d/w.py`", out)

    def test_config_is_checked(self):
        for bad, msg in (({"max_in_flight": 5}, "1 to 4"), ({"exclusive": "db"}, "list of paths"),
                         ({"session_ceiling_pct": 0}, "above 0"), ({"slots": 2}, "unknown key")):
            self.plane(**bad)
            with self.assertRaises(config.ConfigError) as cm:
                config.load(self.main)
            self.assertIn(msg, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
