"""SPEC §9.3: what the SessionStart hook appends after the orientation, the pending notices and the allowance
warning, is built in `ccp` (`notify.orientation_tail`) and printed by `ccp orientation --tail`."""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, notify
from tests.helpers import Product


def row(i: int, reason: str = "") -> dict:
    return {"trigger": "blocker", "subject": f"[demo] blocker: n{i}", "reason": reason,
            "record": f"ccp notify sent blocker --id n{i} --via lead"}


class OrientationTail(unittest.TestCase):
    def test_no_notice_and_no_warning_is_empty(self):
        self.assertEqual(notify.orientation_tail([], ""), "")

    def test_notices_give_the_heading_and_one_line_each(self):
        text = notify.orientation_tail([row(1, "waiting on reauth"), row(2)], "")
        self.assertTrue(text.startswith("\n\n## Pending notices\n\n"))
        self.assertEqual(text.count("\n- "), 2)
        self.assertIn("- [demo] blocker: n1 — waiting on reauth. Record: `ccp notify sent blocker --id n1 --via lead`\n",
                      text)
        self.assertIn("- [demo] blocker: n2. Record: `ccp notify sent blocker --id n2 --via lead`\n", text)
        self.assertNotIn("more:", text)
        self.assertNotIn("## Warning", text)

    def test_a_long_reason_is_cut(self):
        text = notify.orientation_tail([row(1, "r" * 500 + "TAIL")], "")
        self.assertIn("r" * 500 + "…. Record:", text)
        self.assertNotIn("TAIL", text)

    def test_notices_past_the_cap_end_with_the_more_line(self):
        text = notify.orientation_tail([row(i, "r" * 600) for i in range(10)], "")
        self.assertEqual([f"n{i} " in text for i in range(10)], [True] * 4 + [False] * 6)
        self.assertTrue(text.endswith("- … 6 more: `ccp notify pending`\n"), text[-80:])

    def test_the_warning_is_appended(self):
        self.assertEqual(notify.orientation_tail([], "no usage is read"), "\n\n## Warning\n\nno usage is read\n")
        text = notify.orientation_tail([row(1)], "w" * 700)
        self.assertLess(text.index("## Pending notices"), text.index("## Warning"))
        self.assertTrue(text.endswith("w" * 600 + "\n"))


class OrientationTailCommand(unittest.TestCase):
    """`ccp orientation --tail` reads the queue's pending notices and the allowance status."""

    def setUp(self):
        self.p = Product()
        self._tmp = tempfile.TemporaryDirectory()
        self.q = Path(self._tmp.name) / "queue"
        self.q.mkdir()
        (self.q / "observability").mkdir()
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "CCP_BINDINGS_DIR": self._tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.p.cleanup()
        self._tmp.cleanup()

    def tail(self) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "orientation", "--tail"])
        return code, out.getvalue()

    def test_with_no_allowance_command_it_prints_the_warning_ccp_gives(self):
        code, text = self.tail()
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith("\n\n## Warning\n\n"), text)
        self.assertNotIn("## Pending notices", text)

    def test_a_fired_notice_is_listed(self):
        notify.record_pending(self.q, self.p.cfg, "blocker", ident="n7", reason="reauth")
        code, text = self.tail()
        self.assertEqual(code, 0)
        self.assertIn("## Pending notices", text)
        self.assertIn("n7", text)

    def test_without_a_queue_it_prints_nothing(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": ""}), redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "orientation", "--tail"])
        self.assertEqual((code, out.getvalue()), (1, ""))


if __name__ == "__main__":
    unittest.main()
