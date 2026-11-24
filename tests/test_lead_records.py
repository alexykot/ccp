"""SPEC §3.5, §13.4, §17.5, §15.4: the lead's three records (a sign-off, a ruling, a follow-up's outcome) refuse,
through one guard, every caller whose `ACTOR` does not name the lead (unset or unknown included); a sign-off and a
ruling count only when the lead recorded them, and a ruling id is never reused."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccp import config, queue, refs, runs, tasklog
from ccp.queue import QueueError, lib
from tests.helpers import as_actor, as_lead
from tests.report_helpers import MARKED_BLOCK as MARKED, MARKED_CHECK_ID as CHECK, MARKED_TASK_ID as TASK
from tests.toolkit_fixture import ToolkitFixture, git

TASK_FILE = "docs/delivery/tasks/0002-second.md"
RUN = "0001-first/review"


class TheGuard(unittest.TestCase):
    """`queue.lead_actor` on the environment alone."""

    def test_the_lead_s_actor_gives_the_lead(self):
        with as_lead():
            self.assertEqual(queue.lead_actor("a ruling"), lib.LEAD)

    def refusal(self, value: str | None) -> str:
        with as_actor(value), self.assertRaises(QueueError) as cm:
            queue.lead_actor("a ruling")
        self.assertEqual(cm.exception.code, 2, value)
        msg = str(cm.exception)
        self.assertIn("only the lead records a ruling", msg)
        self.assertIn(f"the lead runs it as ACTOR={lib.LEAD} ccp", msg)
        return msg

    def test_another_known_actor_is_refused_with_exit_2(self):
        for value in (lib.RUNNER, lib.VERIFIER, "operator"):
            self.assertIn(f"(ACTOR is {value})", self.refusal(value))

    def test_an_unset_or_empty_actor_is_refused_with_exit_2(self):
        for value in (None, ""):
            self.assertIn("(ACTOR is unset)", self.refusal(value))

    def test_an_unknown_actor_is_refused_with_exit_2(self):
        for value in ("task-lead", "Design-Seat", f"{lib.LEAD} "):
            self.assertIn(f"(ACTOR is {value})", self.refusal(value))


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

    def assert_refused_by_each(self, value: str | None) -> None:
        """Each of the three, run with `ACTOR` at `value`, exits 2 naming how the lead runs it, and writes nothing."""
        before = len(self.events())
        with as_actor(value):
            got = self.records()
        for name, (code, _, out, err) in got.items():
            self.assertEqual(code, 2, f"{name}: {out}{err}")
            self.assertIn("only the lead records", err, name)
            self.assertIn(f"ACTOR={lib.LEAD}", err, name)
        self.assertEqual(self.recorded(), [])
        self.assertEqual(len(self.events()), before)
        self.assertIsNone(runs.load(self.q, RUN)["follow_ups"][0]["outcome"])

    def test_another_seat_s_actor_is_refused_by_each_and_nothing_is_written(self):
        for value in (lib.RUNNER, lib.VERIFIER):
            self.assert_refused_by_each(value)

    def test_with_actor_unset_each_is_refused_and_nothing_is_written(self):
        self.assert_refused_by_each(None)

    def test_an_unknown_actor_is_refused_by_each_and_nothing_is_written(self):
        self.assert_refused_by_each("task-lead")

    def test_the_lead_s_actor_records_each(self):
        with as_lead():
            got = self.records()
        for name, (code, _, out, err) in got.items():
            self.assertEqual(code, 0, f"{name}: {out}{err}")
        self.assertEqual(self.recorded(), [("sign_off", lib.LEAD), ("ruling", lib.LEAD), ("decided", lib.LEAD)])
        self.assertEqual(runs.load(self.q, RUN)["follow_ups"][0]["outcome"]["by"], lib.LEAD)

    def test_a_ruling_is_numbered_past_one_another_actor_recorded(self):
        foreign = f"{TASK}-r1"
        queue.emit(self.q, config.load(self.runner), TASK, "ruling", "recorded",
                   {"id": foreign, "n": 1, "words": "a runner's own ruling"}, lib.RUNNER)
        with as_lead():
            code, body, out, err = self.ccp("tasks", "ruling", "0002", "--words", "hold the count")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["id"], f"{TASK}-r2")
        ids = [e["payload"]["id"] for e in self.events() if (e["type"], e["op"]) == ("ruling", "recorded")]
        self.assertEqual(ids, [foreign, f"{TASK}-r2"])
        self.assertEqual([r["id"] for r in queue.rulings(self.q, TASK)], [f"{TASK}-r2"])


class ASignOffAnotherSeatRecorded(unittest.TestCase):
    """`queue.sign_offs` reads only the `sign_off` `recorded` events the lead recorded: another actor's is no
    sign-off of the operator's."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)

    def ledger(self, actor: str) -> None:
        p = queue.events_path(self.q)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"at": "2026-11-22T10:00:00Z", "project_id": "demo", "task_id": TASK, "actor": actor,
                                 "type": "sign_off", "op": "recorded",
                                 "payload": {"stage": "brief", "by": "op", "words": "signed", "head": "a" * 40}}) + "\n")

    def test_a_sign_off_another_actor_recorded_is_left_out(self):
        self.ledger(lib.RUNNER)
        self.assertNotIn("brief", queue.sign_offs(self.q, TASK))

    def test_a_sign_off_the_lead_recorded_is_read(self):
        self.ledger(lib.LEAD)
        self.assertEqual(queue.sign_offs(self.q, TASK)["brief"]["words"], "signed")


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
        with as_lead():
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
        self.assertIn(f"ACTOR={lib.LEAD} ccp tasks ruling", err)
        self.assertFalse(any(p.name.startswith("verify") for p in (self.q / "runs" / TASK).glob("*.json")))

    def test_the_lead_s_ruling_waives_the_check(self):
        code, _, out, err = self.verify(self.lead_ruling)
        self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
