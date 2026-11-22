"""SPEC §3.5, §13.4, §17.5, §15.4: the lead's three records (a sign-off, a ruling, a follow-up's outcome) refuse a
caller whose `ACTOR` names another seat, through one guard, and a ruling counts only when the lead recorded it."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from ccp import config, queue, refs, runs, tasklog
from ccp.queue import QueueError, lib
from tests.test_marked_checks_loop import CHECK, MARKED, TASK
from tests.test_toolkit import ToolkitFixture, git

TASK_FILE = "docs/delivery/tasks/0002-second.md"
RUN = "0001-first/review"


def as_actor(value: str | None):
    """The environment with `ACTOR` set to `value`, or with no `ACTOR` at all for None."""
    if value is None:
        return mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ACTOR"}, clear=True)
    return mock.patch.dict(os.environ, {"ACTOR": value})


class TheGuard(unittest.TestCase):
    """`queue.lead_actor` on the environment alone."""

    def test_the_lead_or_no_actor_gives_the_lead(self):
        for value in (None, lib.LEAD):
            with as_actor(value):
                self.assertEqual(queue.lead_actor("a ruling"), lib.LEAD, value)

    def test_another_known_actor_is_refused_with_exit_2(self):
        for value in (lib.RUNNER, "task-verifier", "operator"):
            with as_actor(value), self.assertRaises(QueueError) as cm:
                queue.lead_actor("a ruling")
            self.assertEqual(cm.exception.code, 2)
            self.assertIn("only the lead records a ruling", str(cm.exception))
            self.assertIn(value, str(cm.exception))


class TheThreeRecords(ToolkitFixture, unittest.TestCase):
    """`ccp tasks sign-off`, `tasks ruling` and `tasks follow-up` against a git product and a queue."""

    def setUp(self):
        super().setUp()
        p = self.main / TASK_FILE  # 0002 declares a brief sign-off, so one is due
        p.write_text(p.read_text().replace("depends_on:", "sign_off: brief\ndepends_on:", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", TASK_FILE, "docs/delivery/INDEX.yaml")
        git(self.main, "commit", "-q", "-m", "0002 needs a sign-off")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        runs.save(self.q, {"run_id": RUN, "task_id": "0001-first", "phase": "review",
                           "follow_ups": [{"id": refs.follow_up_id(RUN, 1), "text": "a gap", "outcome": None}]})

    def records(self) -> dict[str, tuple]:
        """Each of the three commands, run once: the name of its event, and what `ccp` returned."""
        return {"sign_off": self.ccp("tasks", "sign-off", "0002", "--by", "op", "--words", "signed"),
                "ruling": self.ccp("tasks", "ruling", "0002", "--words", "hold the count"),
                "decided": self.ccp("tasks", "follow-up", refs.follow_up_id(RUN, 1), "--drop", "not worth it")}

    def recorded(self) -> list[tuple[str, str]]:
        """The (event op or type, actor) of each record the three commands write."""
        return [(e["type"] if e["type"] != "run" else e["op"], e["actor"]) for e in self.events()
                if (e["type"], e["op"]) in (("sign_off", "recorded"), ("ruling", "recorded"), ("run", "decided"))]

    def test_another_seat_s_actor_is_refused_by_each_and_nothing_is_written(self):
        for value in (lib.RUNNER, "task-verifier"):
            with as_actor(value):
                got = self.records()
            for name, (code, _, out, err) in got.items():
                self.assertEqual(code, 2, f"{name}: {out}{err}")
                self.assertIn("only the lead records", err, name)
            self.assertEqual(self.recorded(), [])
            self.assertIsNone(runs.load(self.q, RUN)["follow_ups"][0]["outcome"])

    def test_with_no_actor_each_records_as_the_lead(self):
        with as_actor(None):
            got = self.records()
        for name, (code, _, out, err) in got.items():
            self.assertEqual(code, 0, f"{name}: {out}{err}")
        self.assertEqual(self.recorded(), [("sign_off", lib.LEAD), ("ruling", lib.LEAD), ("decided", lib.LEAD)])
        self.assertEqual(runs.load(self.q, RUN)["follow_ups"][0]["outcome"]["by"], lib.LEAD)

    def test_the_lead_s_actor_records_each(self):
        with as_actor(lib.LEAD):
            got = self.records()
        for name, (code, _, out, err) in got.items():
            self.assertEqual(code, 0, f"{name}: {out}{err}")
        self.assertEqual(self.recorded(), [("sign_off", lib.LEAD), ("ruling", lib.LEAD), ("decided", lib.LEAD)])


class ARulingAnotherSeatRecorded(ToolkitFixture, unittest.TestCase):
    """A `ruling` `recorded` event another actor wrote in the ledger is no lead ruling: the reader leaves it out and
    a `--waived` naming it is refused, while the lead's own ruling waives the same check."""

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        task = self.runner / TASK_FILE  # the claimed task gets a check marked `runs_on: operator-machine`
        task.write_text(task.read_text().replace("## Implementation notes", MARKED, 1))
        m = self.main
        git(m, "checkout", "-q", "-b", "feat")
        self.write("feature.txt", "built\n")
        git(m, "add", "feature.txt")
        git(m, "commit", "-q", "-m", "build it")
        self.head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        with as_actor(lib.LEAD):
            code, body, out, err = self.ccp("tasks", "ruling", "0002", "--words", "the operator waives the live check")
        self.assertEqual(code, 0, out + err)
        self.lead_ruling = body["id"]
        self.foreign = f"{TASK}-r2"
        queue.emit(self.q, config.load(self.runner), TASK, "ruling", "recorded",
                   {"id": self.foreign, "n": 2, "words": "a runner's own ruling"}, lib.RUNNER)

    def verify(self, ruling: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", self.head, "--waived", f"{CHECK}={ruling}")

    def test_the_reader_keeps_only_the_lead_s_ruling(self):
        self.assertIn((self.foreign, lib.RUNNER), [(e["payload"].get("id"), e["actor"]) for e in self.events()])
        self.assertEqual([r["id"] for r in queue.rulings(self.q, TASK)], [self.lead_ruling])

    def test_a_waiver_naming_it_is_refused_and_opens_nothing(self):
        code, _, out, err = self.verify(self.foreign)
        self.assertNotEqual(code, 0, out + err)
        self.assertIn(self.foreign, err)
        self.assertFalse(any(p.name.startswith("verify") for p in (self.q / "runs" / TASK).glob("*.json")))

    def test_the_lead_s_ruling_waives_the_check(self):
        code, _, out, err = self.verify(self.lead_ruling)
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
