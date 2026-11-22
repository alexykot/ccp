"""SPEC §22.2, ADR-0044 D3: a review point the register records closed while a follow-up of one of its tasks is
undecided fails `ccp tasks check --closed-points` and the spawn's readiness check, never plain `ccp tasks check`.

Run as `python3 -m tests.test_followups_closed_point --seed <queue> <task_id>` it writes one run record of that task
with an undecided follow-up into the queue, and runs no test.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, followups, refs, runs
from ccp.queue import lib
from tests.helpers import Product, binding
from tests.test_review_points import REGISTER, _tagged
from tests.test_team_hosting import TeamCase


def seed(q: Path, task_id: str, decided: bool = False) -> str:
    """Write `<task_id>/implement`'s run record into queue `q` with one follow-up, undecided unless `decided`: its
    id."""
    run_id = f"{task_id}/implement"
    fid = refs.follow_up_id(run_id, 1)
    outcome = {"kind": "drop", "reason": "not worth it", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD} \
        if decided else None
    runs.save(q, {"run_id": run_id, "task_id": task_id, "phase": "implement",
                  "follow_ups": [{"id": fid, "text": "a test gap out of scope", "outcome": outcome}]})
    return fid


def run_record(task_id: str, outcome: dict | None = None) -> dict:
    run_id = f"{task_id}/review"
    return {"run_id": run_id, "task_id": task_id,
            "follow_ups": [{"id": refs.follow_up_id(run_id, 1), "text": "later", "outcome": outcome}]}


DECIDED = {"kind": "task", "ref": "0009-z", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD}
POINTS = [{"id": "R1", "status": "closed"}, {"id": "R2", "status": "current"}, {"id": "R3", "status": "planned"}]


class OnPlainValues(unittest.TestCase):

    def test_a_closed_point_with_an_undecided_follow_up_names_the_point_the_follow_up_and_the_command(self):
        errs = followups.closed_point_errors(POINTS, {"R1": ["0001-a", "0002-b"]},
                                             [run_record("0001-a"), run_record("0002-b", DECIDED)])
        self.assertEqual(len(errs), 1)
        fid = refs.follow_up_id("0001-a/review", 1)
        for token in ("R1", fid, f"ccp tasks follow-up {fid}"):
            self.assertIn(token, errs[0])

    def test_every_closed_point_is_checked_not_only_the_first(self):
        points = [{"id": "R1", "status": "closed"}, {"id": "R2", "status": "closed"}]
        errs = followups.closed_point_errors(points, {"R1": ["0001-a"], "R2": ["0002-b"]}, [run_record("0002-b")])
        self.assertEqual(len(errs), 1)
        self.assertIn("review point R2", errs[0])

    def test_a_closed_point_with_every_follow_up_decided_passes(self):
        self.assertEqual(followups.closed_point_errors(POINTS, {"R1": ["0001-a"]}, [run_record("0001-a", DECIDED)]), [])

    def test_an_open_point_with_an_undecided_follow_up_passes(self):
        self.assertEqual(followups.closed_point_errors(
            POINTS, {"R2": ["0001-a"], "R3": ["0002-b"]}, [run_record("0001-a"), run_record("0002-b")]), [])

    def test_a_task_of_no_closed_point_and_no_register_pass(self):
        self.assertEqual(followups.closed_point_errors(POINTS, {"R1": ["0002-b"]}, [run_record("0001-a")]), [])
        self.assertEqual(followups.closed_point_errors(None, {"R1": ["0001-a"]}, [run_record("0001-a")]), [])


class TheTasksCheck(unittest.TestCase):
    """`ccp tasks check` with and without `--closed-points`, on a temp product whose register records R7 closed."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.p, "0001-a", "done", "R7")
        _tagged(self.p, "0002-b", "pending", "R8")
        self.p.index()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)
        (self.q / "project.yaml").write_text(binding(product_root=self.p.root))
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "ACTOR": lib.LEAD})
        env.start()
        self.addCleanup(env.stop)

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_closed_points_fails_on_an_undecided_follow_up_then_passes_once_it_is_decided(self):
        fid = seed(self.q, "0001-a")
        code, out, err = self.ccp("tasks", "check", "--closed-points")
        self.assertEqual(code, 1, out + err)
        self.assertIn(fid, out)
        self.assertEqual(self.ccp("tasks", "follow-up", fid, "--drop", "covered elsewhere")[0], 0)
        code, out, err = self.ccp("tasks", "check", "--closed-points")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("tasks: clean"), out)

    def test_an_undecided_follow_up_of_an_open_points_task_does_not_fail(self):
        seed(self.q, "0002-b")
        code, out, err = self.ccp("tasks", "check", "--closed-points")
        self.assertEqual(code, 0, out + err)

    def test_plain_tasks_check_is_not_held_by_an_undecided_follow_up(self):
        seed(self.q, "0001-a")
        code, out, err = self.ccp("tasks", "check")
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.startswith("tasks: clean"), out)

    def test_without_a_queue_closed_points_notes_it_read_none_and_passes(self):
        seed(self.q, "0001-a")
        with mock.patch.dict(os.environ):
            del os.environ["QUEUE_ROOT"]
            code, out, err = self.ccp("tasks", "check", "--closed-points")
        self.assertEqual(code, 0, out + err)
        self.assertIn("note: --closed-points read no queue", out)

    def test_an_unreadable_run_record_is_named(self):
        bad = self.q / "runs" / "0001-a" / "implement.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{not json")
        code, out, err = self.ccp("tasks", "check", "--closed-points")
        self.assertEqual(code, 1, out + err)
        self.assertIn(str(bad), err)

    def test_closed_points_with_lease_is_refused(self):
        code, _, err = self.ccp("tasks", "check", "--closed-points", "--lease")
        self.assertEqual(code, 2)
        self.assertIn("--closed-points", err)


class TheSpawnReadiness(TeamCase):
    """`team.sh runner spawn --dry-run` names a closed point holding an undecided follow-up as not ready."""

    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.prod, "0001-a", "done", "R7")
        _tagged(self.prod, "0002-b", "pending", "R8")
        self.prod.index()

    def check(self, res: dict) -> dict:
        return next(c for c in res["checks"] if c["check"] == "closed_points")

    def test_an_undecided_follow_up_of_a_closed_point_is_not_ready_until_it_is_decided(self):
        fid = seed(self.q, "0001-a")
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0002-b")
        self.assertEqual(code, 1, err)
        self.assertEqual(res["failed"], ["closed_points"])
        self.assertIn(fid, self.check(res)["detail"])
        seed(self.q, "0001-a", decided=True)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0002-b")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.check(res)["ok"])

    def test_an_unreadable_run_record_is_not_ready(self):
        bad = self.q / "runs" / "0001-a" / "implement.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("{not json")
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0002-b")
        self.assertEqual(code, 1, err)
        self.assertEqual(res["failed"], ["closed_points"])
        self.assertIn(str(bad), self.check(res)["detail"])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--seed"] and len(sys.argv) == 4:
        print(seed(Path(sys.argv[2]), sys.argv[3]))
    else:
        unittest.main()
