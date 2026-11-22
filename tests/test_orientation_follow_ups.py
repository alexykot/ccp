"""SPEC §9.3, ADR-0044 D4: while any worker follow-up has no outcome, what the SessionStart hook appends after the
orientation (`notify.orientation_tail`, printed by `ccp orientation --tail`) ends with one line giving how many are
open and the command that lists them."""
from __future__ import annotations

import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, notify, refs, runs
from ccp.queue import lib
from tests.helpers import Product

LIST = "`ccp tasks follow-ups --open`"
DROPPED = {"kind": "drop", "reason": "not worth it", "at": "2026-11-21T00:00:00Z", "by": lib.LEAD}


def notice() -> dict:
    return {"trigger": "blocker", "subject": "[demo] blocker: n1", "reason": "",
            "record": "ccp notify sent blocker --id n1 --via lead"}


def record(run_id: str, outcomes: list[dict | None]) -> dict:
    """A reported run record with one follow-up per entry of `outcomes`, numbered from 1."""
    task_id = runs.parse_id(run_id)[0]
    return {"run_id": run_id, "task_id": task_id, "phase": "implement",
            "follow_ups": [{"id": refs.follow_up_id(run_id, n), "text": f"gap {n}", "outcome": o}
                           for n, o in enumerate(outcomes, 1)]}


def last_line(text: str) -> str:
    return text.rstrip("\n").rsplit("\n", 1)[-1]


class OnPlainValues(unittest.TestCase):
    def test_no_line_at_zero(self):
        self.assertEqual(notify.orientation_tail([], "", 0), "")
        self.assertNotIn(LIST, notify.orientation_tail([notice()], "a warning", 0))

    def test_the_line_at_two_comes_after_the_notices(self):
        text = notify.orientation_tail([notice()], "", 2)
        self.assertLess(text.index("## Pending notices"), text.index(LIST))
        self.assertEqual(text.count(LIST), 1)
        self.assertRegex(last_line(text), rf"^2 .*{re.escape(LIST)}$")

    def test_one_open_follow_up_gives_the_line(self):
        text = notify.orientation_tail([], "", 1)
        self.assertEqual(text.count(LIST), 1)
        self.assertRegex(last_line(text), rf"^1 .*{re.escape(LIST)}$")


class TheCommand(unittest.TestCase):
    """`ccp orientation --tail` counts the undecided follow-ups on the queue's run records."""

    def setUp(self):
        self.p = Product()
        self._tmp = tempfile.TemporaryDirectory()
        self.q = Path(self._tmp.name) / "queue"
        (self.q / "observability").mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "CCP_BINDINGS_DIR": self._tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.p.cleanup()
        self._tmp.cleanup()

    def tail(self) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "orientation", "--tail"])
        return code, out.getvalue()

    def test_the_line_counts_the_undecided_follow_ups_after_the_notices(self):
        notify.record_pending(self.q, self.p.cfg, "blocker", ident="n7", reason="reauth")
        runs.save(self.q, record("0001-a/implement", [None, DROPPED]))
        runs.save(self.q, record("0002-b/review", [None]))
        code, text = self.tail()
        self.assertEqual(code, 0)
        self.assertLess(text.index("## Pending notices"), text.index(LIST))
        self.assertRegex(last_line(text), rf"^2 .*{re.escape(LIST)}$")

    def test_no_line_when_every_follow_up_is_decided(self):
        runs.save(self.q, record("0001-a/implement", [DROPPED]))
        code, text = self.tail()
        self.assertEqual(code, 0)
        self.assertNotIn(LIST, text)

    def test_no_line_without_a_queue(self):
        runs.save(self.q, record("0001-a/implement", [None]))
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}):
            code, text = self.tail()
        self.assertEqual((code, text), (1, ""))


if __name__ == "__main__":
    unittest.main()
