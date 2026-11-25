"""SPEC §16.5, §20.4, §22, §22.5: the runner seat's scope, slot and readiness decisions (`ccp/runnerscope.py`), each
branch on plain values: no fixture repo, no `team.sh`."""
from __future__ import annotations

import unittest

from ccp import runnerscope as rs
from ccp.queue import QueueError


def task(tid, status="pending", rp=None, kind=None):
    return {"task_id": tid, "status": status, "review_point": rp, **({"kind": kind} if kind else {})}


TASKS = [task("0001-a", "pending", "R8"), task("0002-b", "in_progress", "R8"), task("0003-c", "blocked", "R8"),
         task("0004-d", "done", "R8"), task("0005-e", "pending", "R9"), task("0006-f", "pending"),
         task("0007-g", "pending", None, "refactor")]


class Refusal(unittest.TestCase):
    def refused(self, fn, *a):
        with self.assertRaises(QueueError) as cm:
            fn(*a)
        self.assertEqual(cm.exception.code, 2)
        return str(cm.exception)


class TaggedOpen(unittest.TestCase):
    def test_open_tasks_of_the_point_in_task_order(self):
        self.assertEqual(rs.tagged_open(TASKS, "R8"), ["0001-a", "0002-b", "0003-c"])  # 0004-d is done
        self.assertEqual(rs.tagged_open(TASKS, "R9"), ["0005-e"])
        self.assertEqual(rs.tagged_open(TASKS, "R1"), [])


class RespawnScope(unittest.TestCase):
    def test_order_and_filters(self):
        got = rs.respawn_scope(["0001-a"], ["0005-e", "0001", "0002-b", "0003-c"], ["0001-a", "0002-b", "0005-e"])
        self.assertEqual(got, ["0001-a", "0005-e", "0002-b"])  # 0001 is tagged already, 0003-c is not pending
        self.assertEqual(rs.respawn_scope([], ["0002-b"], ["0002-b"]), ["0002-b"])


class ScopeWarnings(unittest.TestCase):
    def test_both_ways(self):
        got = rs.scope_warnings(TASKS, "R8", ["0002-b", "0005-e", "0006-f"])
        self.assertEqual(len(got), 2)
        self.assertIn("2 scope task(s) are not tagged R8: 0005-e, 0006-f", got[0])
        self.assertIn("2 open task(s) tagged R8 are not in the scope: 0001-a, 0003-c", got[1])

    def test_a_refactor_and_an_unknown_entry_are_not_named_and_a_number_names_its_task(self):
        self.assertEqual(rs.scope_warnings(TASKS, "R8", ["0001", "0002-b", "0003-c", "0007-g", "0099-x"]), [])

    def test_only_the_missing_side(self):
        got = rs.scope_warnings(TASKS, "R8", ["0001-a", "0002-b"])
        self.assertEqual(len(got), 1)
        self.assertIn("1 open task(s) tagged R8 are not in the scope: 0003-c", got[0])


class PointScope(Refusal):
    def call(self, entries=("R8",), scope=("0006-f",), review_point=None, scope_given=False, work_point=None,
             work_scope=(), work_refactors=(), problem_given=None, problem_for=None):
        return rs.point_scope(TASKS, list(entries) if entries is not None else None, list(scope), review_point,
                              scope_given, work_point, list(work_scope), list(work_refactors), problem_given,
                              problem_for)

    def test_no_register_names_the_pattern_problem_as_a_warning(self):
        scope, warns = self.call(entries=None, review_point="PM", problem_given="bad", problem_for="bad point")
        self.assertEqual(scope, ["0006-f"])
        self.assertEqual(len(warns), 1)
        self.assertIn("bad point: `ccp tasks close` will not stamp it into the tasks it closes", warns[0])
        # a refusing --review-point is only a warning without a register
        self.assertEqual(self.call(entries=None, problem_for=None), (["0006-f"], []))

    def test_an_unknown_review_point_refuses_before_anything(self):
        msg = self.refused(self.call, ("R8",), ("0006-f",), "R9", False, None, (), (), "R9 is not in the register", None)
        self.assertEqual(msg, "runner spawn --review-point: R9 is not in the register")

    def test_a_given_scope_is_kept_and_warned_about(self):
        scope, warns = self.call(review_point="R8", scope=["0002-b", "0005-e"], scope_given=True)
        self.assertEqual(scope, ["0002-b", "0005-e"])
        self.assertEqual(len(warns), 2)

    def test_a_new_point_takes_its_open_tagged_tasks(self):
        self.assertEqual(self.call(review_point="R8", work_point="R7", work_scope=["0006-f"]),
                         (["0001-a", "0002-b", "0003-c"], []))

    def test_a_respawn_keeps_the_pending_tasks_work_json_holds_but_not_its_refactors(self):
        scope, warns = self.call(review_point="R8", work_point="R8", work_scope=["0006-f", "0007-g", "0004-d"],
                                 work_refactors=["0007-g"])
        self.assertEqual((scope, warns), (["0001-a", "0002-b", "0003-c", "0006-f"], []))  # 0004-d is done

    def test_no_open_tagged_task_refuses(self):
        msg = self.refused(self.call, ("R8",), ("0006-f",), "R1", False, None, (), (), None, None)
        self.assertEqual(msg, "no open task is tagged review_point: R1; tag the point's tasks "
                              "(`ccp review-points tag R1 …`) or pass --scope (SPEC §22)")

    def test_work_json_point_with_a_problem_warns_and_keeps_the_scope(self):
        scope, warns = self.call(work_point="PM", problem_for="review point 'PM' is not R<number>")
        self.assertEqual(scope, ["0006-f"])
        self.assertEqual(len(warns), 1)
        self.assertIn("work.json's review point 'PM' is not R<number>; `ccp tasks close` will not stamp it", warns[0])

    def test_nothing_to_say(self):
        self.assertEqual(self.call(), (["0006-f"], []))


class RefactorScope(unittest.TestCase):
    def test_a_new_point_puts_every_waiting_refactor_on_top(self):
        self.assertEqual(rs.refactor_scope(True, ["0007-g", "0008-h"], ["0006-f"], ["0001-old"], ["0006-f", "0007-g"]),
                         (["0007-g", "0008-h", "0006-f"], ["0007-g", "0008-h"], ["0007-g", "0008-h"]))

    def test_a_respawn_puts_back_the_ones_still_pending_and_not_in_scope(self):
        got = rs.refactor_scope(False, ["0009-new"], ["0007-g", "0008-h", "0006-f"], ["0007-g", "0008-h", "0005-e"],
                                ["0006-f", "0008-h"])
        self.assertEqual(got, (["0007-g", "0006-f", "0008-h"], ["0007-g"], ["0007-g", "0008-h", "0005-e"]))

    def test_no_refactor_log_adds_none(self):
        self.assertEqual(rs.refactor_scope(True, [], None, ["0007-g"], ["0006-f"]), (["0006-f"], [], []))
        self.assertEqual(rs.refactor_scope(False, [], None, ["0007-g"], ["0006-f"]), (["0006-f"], [], ["0007-g"]))
        self.assertEqual(rs.refactor_scope(False, [], None, None, ["0006-f"]), (["0006-f"], [], []))


class Slots(unittest.TestCase):
    def test_slots_of_reads_runners_as_records(self):
        self.assertEqual(rs.slots_of({"runners": {"runner-1": {"bound_name": "x"}, 2: "junk"}}),
                         {"runner-1": {"bound_name": "x"}, "2": {}})
        self.assertEqual(rs.slots_of({"runners": ["runner-1"]}), {})
        self.assertEqual(rs.slots_of({}), {})

    def test_slot_tasks_are_the_in_flight_tasks_the_slot_leases_and_not_done(self):
        states = {"0001-a": {"lease_holder": "runner-1", "status": "in_progress"},
                  "0002-b": {"lease_holder": "runner-2", "status": "in_progress"},
                  "0003-c": {"lease_holder": "runner-1", "status": "done"},
                  "0004-d": "junk"}
        flight = ["0001-a", "0002-b", "0003-c", "0004-d", "0005-unread"]
        self.assertEqual(rs.slot_tasks(flight, states, "runner-1"), ["0001-a"])
        self.assertEqual(rs.slot_tasks(flight, states, "runner-2"), ["0002-b"])
        self.assertEqual(rs.slot_tasks(None, states, "runner-1"), [])


class NewSlots(Refusal):
    def test_a_slot_is_a_respawn_of_a_recorded_one(self):
        self.assertEqual(rs.new_slots(["runner-1", "runner-2"], "runner", "runner-2", None, 2), ["runner-2"])

    def test_a_slot_that_is_none_refuses_naming_the_recorded(self):
        self.assertEqual(self.refused(rs.new_slots, ["runner-2", "runner-1"], "runner", "runner-9", None, 2),
                         "--slot runner-9: no such slot (runner-1, runner-2)")
        self.assertEqual(self.refused(rs.new_slots, [], "runner", "runner-1", None, 2),
                         "--slot runner-1: no such slot (none)")

    def test_count_makes_that_many_unrecorded_slots(self):
        self.assertEqual(rs.new_slots([], "runner", None, 2, 3), ["runner-1", "runner-2"])
        self.assertEqual(rs.new_slots(["runner-1"], "runner", None, 3, 3), ["runner-2", "runner-3"])

    def test_the_default_count_is_the_recorded_slots_else_one(self):
        self.assertEqual(rs.new_slots([], "runner", None, None, 2), ["runner-1"])
        self.assertEqual(rs.new_slots(["runner-2"], "runner", None, None, 2), ["runner-1"])

    def test_a_count_above_the_cap_refuses(self):
        self.assertEqual(self.refused(rs.new_slots, [], "runner", None, 3, 2),
                         "--count 3 is above parallel.max_in_flight 2 (SPEC §16.5)")

    def test_no_slot_left_refuses(self):
        self.assertEqual(self.refused(rs.new_slots, ["runner-1", "runner-2"], "runner", None, 2, 2),
                         "2 slot(s) are recorded already; respawn one with --slot")


class Orphans(Refusal):
    STATES = {"0001-a": {"lease_holder": "runner", "status": "in_progress"},
              "0002-b": {"lease_holder": "runner-1", "status": "in_progress"},
              "0003-c": {"lease_holder": "runner-2", "status": "in_progress"},
              "0004-d": {"lease_holder": "runner", "status": "done"},
              "0005-e": {"status": "in_progress"}, "0006-f": "junk"}

    def test_a_task_held_by_no_slot_refuses_naming_it_and_its_holder(self):
        msg = self.refused(rs.orphans, ["0001-a", "0002-b", "0003-c", "0004-d", "0005-e", "0006-f", "0007-unread"],
                           self.STATES, ["runner-1"], ["runner-2"])
        self.assertTrue(msg.startswith("0001-a (held by runner): held by no runner slot. Drain or stop the single "
                                       "runner first (`team.sh runner stop --drain`)"), msg)

    def test_several_are_named_in_order(self):
        states = {"0001-a": {"lease_holder": "x", "status": "in_progress"},
                  "0002-b": {"lease_holder": "y", "status": "blocked"}}
        self.assertTrue(self.refused(rs.orphans, ["0001-a", "0002-b"], states, [], []).startswith(
            "0001-a (held by x), 0002-b (held by y): held by no runner slot"))

    def test_slots_recorded_or_new_hold_no_orphan(self):
        self.assertIsNone(rs.orphans(["0002-b", "0003-c", "0004-d", "0005-e", "0006-f"], self.STATES,
                                     ["runner-1"], ["runner-2"]))
        self.assertIsNone(rs.orphans(None, self.STATES, [], []))


class ReadinessChecks(unittest.TestCase):
    def by_name(self, checks):
        return {c["check"]: c for c in checks}

    def test_an_unreadable_log_is_the_one_failing_check(self):
        checks = rs.readiness_checks(["0001-a"], [], [], None, None)
        self.assertEqual([(c["check"], c["ok"]) for c in checks], [("task_log", False)])
        self.assertIn("the product's task log does not read", checks[0]["detail"])

    def test_all_clear(self):
        c = self.by_name(rs.readiness_checks(["0001-a", "0002"], ["0001-a", "0002-b"], [], [], None))
        self.assertEqual(list(c), ["scope_tasks_exist", "tasks_check", "closed_points"])
        self.assertTrue(all(x["ok"] for x in c.values()))
        self.assertEqual(c["scope_tasks_exist"]["detail"], "2 scope task(s) in the task log")  # 0002 names 0002-b
        self.assertEqual(c["tasks_check"]["detail"], "`ccp tasks check` is clean")
        self.assertEqual(c["closed_points"]["detail"], "no closed review point holds an undecided follow-up")

    def test_a_scope_entry_missing_from_the_log_is_named(self):
        c = self.by_name(rs.readiness_checks(["0001-a", "0009-z", "0010"], ["0001-a"], [], [], None))
        self.assertEqual((c["scope_tasks_exist"]["ok"], c["scope_tasks_exist"]["detail"]),
                         (False, "not in the task log: 0009-z, 0010"))
        self.assertTrue(c["tasks_check"]["ok"])

    def test_tasks_check_failures_are_counted_and_the_first_five_named(self):
        errs = [f"e{i}" for i in range(7)]
        c = self.by_name(rs.readiness_checks([], [], errs, [], None))["tasks_check"]
        self.assertEqual((c["ok"], c["detail"]), (False, "`ccp tasks check`: 7 failure(s): e0; e1; e2; e3; e4"))

    def test_closed_point_failures_are_counted_and_the_first_five_named(self):
        c = self.by_name(rs.readiness_checks([], [], [], ["p1", "p2"], None))["closed_points"]
        self.assertEqual((c["ok"], c["detail"]), (False, "`ccp tasks check --closed-points`: 2 failure(s): p1; p2"))

    def test_the_runner_worktree_by_state(self):
        def one(state):
            return rs.readiness_checks([], [], [], [], ("/w/runner", state))[-1]
        self.assertEqual(one(rs.WORKTREE), {"check": "runner_worktree", "ok": True, "detail": "/w/runner exists"})
        self.assertEqual(one(rs.ABSENT), {"check": "runner_worktree", "ok": True,
                                          "detail": "/w/runner would be made by the spawn"})
        occupied = one(rs.OCCUPIED)
        self.assertFalse(occupied["ok"])
        self.assertIn("/w/runner exists and is not a working tree of the product", occupied["detail"])

    def test_no_worktree_to_check_adds_none(self):
        self.assertNotIn("runner_worktree", self.by_name(rs.readiness_checks([], [], [], [], None)))
        self.assertEqual([c["check"] for c in rs.readiness_checks([], [], [], None, ("/w", rs.WORKTREE))],
                         ["task_log", "runner_worktree"])


if __name__ == "__main__":
    unittest.main()
