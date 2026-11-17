"""SPEC §3.6, §29.3: `ccp notify upgrade` records a release's `upgrade` notice for a product, the
`adopt` steps of the release's tasks it has not taken, and records none when there are none; the lead
finds it in `ccp notify pending` and in the orientation."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, notify
from ccp.queue import lib
from tests.test_upgrade import UpgradeFixture

PLANE = Path(__file__).resolve().parents[1]  # this checkout: its plugin gives the orientation


def orientation(root: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("ccp.queue.PLANE", PLANE), redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["--root", str(root), "orientation"])
    return code, out.getvalue(), err.getvalue()


class UpgradeNotice(UpgradeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane_task("0001-old", "done", "Old", "plane.json old.key")
        self.plane_task("0002-cache", "pending", "Cache", "plane.json verify.accept_cache")
        self.plane_task("0003-none", "pending", "Nothing", "none")
        self.plane_task("0004-skip", "pending", "Skip", "plane.json verify.skip_review_after_clean")
        self.before = self.commit("before")
        self.plane_task("0002-cache", "done", "Cache", "plane.json verify.accept_cache")
        self.plane_task("0003-none", "done", "Nothing", "none")
        self.plane_task("0004-skip", "done", "Skip", "plane.json verify.skip_review_after_clean")
        self.release = self.commit("release")

    def notice_rows(self) -> list[dict]:
        return [e for e in lib.load_events(self.q / "observability" / "events.jsonl")
                if e.get("type") == "notify"]

    def test_records_one_pending_notice_naming_the_release_and_each_step_not_taken(self):
        self.product_json(verify={"skip_review_after_clean": True})  # 0004's step is taken
        code, body, err = self.ccp("notify", "upgrade", "--since", self.before)
        self.assertEqual(code, 0, err)
        self.assertTrue(body["recorded"])
        self.assertEqual(body["release"], self.release)
        self.assertEqual([s["task"] for s in body["steps"]], ["0002-cache"])
        code, pending, err = self.ccp("notify", "pending")
        self.assertEqual(code, 0, err)
        [n] = pending["pending"]
        self.assertEqual((n["trigger"], n["id"], n["task"]), ("upgrade", self.release, ""))
        self.assertIn("plane.json verify.accept_cache", n["reason"])
        self.assertIn("0002-cache", n["reason"])
        self.assertNotIn("0004-skip", n["reason"])
        self.assertNotIn("0001-old", n["reason"])  # merged before the release
        self.assertIn(self.release, n["subject"])
        self.assertEqual([(e["op"], e["actor"]) for e in self.notice_rows()], [("pending", "task-runner")])

    def test_a_product_that_took_every_step_gets_no_notice(self):
        self.product_json(verify={"accept_cache": {"max_age_days": 7}, "skip_review_after_clean": True})
        code, body, err = self.ccp("notify", "upgrade", "--since", self.before)
        self.assertEqual(code, 0, err)
        self.assertEqual((body["recorded"], body["steps"]), (False, []))
        self.assertEqual(self.notice_rows(), [])

    def test_a_declined_step_is_left_out(self):
        self.product_json(verify={"skip_review_after_clean": True},
                          upgrade={"declined": {"0002-cache": "not for us"}})
        code, body, err = self.ccp("notify", "upgrade", "--since", self.before)
        self.assertEqual(code, 0, err)
        self.assertFalse(body["recorded"])

    def test_a_release_that_brought_nothing_records_nothing(self):
        self.product_json()
        code, body, err = self.ccp("notify", "upgrade", "--since", self.release)
        self.assertEqual(code, 0, err)
        self.assertFalse(body["recorded"])
        self.assertEqual(self.notice_rows(), [])

    def test_the_notify_command_is_not_run_for_it(self):
        marker = self.q / "sent-by-command"
        self.product_json(notify={"command": f"touch {marker}"})
        code, body, err = self.ccp("notify", "upgrade", "--since", self.before)
        self.assertEqual(code, 0, err)
        self.assertTrue(body["recorded"])
        self.assertFalse(marker.exists())
        self.assertEqual([e["op"] for e in self.notice_rows()], ["pending"])

    def test_the_lead_records_its_send_and_it_is_no_longer_pending(self):
        self.product_json()
        self.assertEqual(self.ccp("notify", "upgrade", "--since", self.before)[0], 0)
        code, _body, err = self.ccp("notify", "sent", "upgrade", "--id", self.release, "--via", "lead")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.ccp("notify", "pending")[1]["pending"], [])

    def test_without_a_queue_it_is_refused(self):
        self.product_json()
        self.env.stop()
        try:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = cli.main(["--root", str(self.product.root), "notify", "upgrade", "--since", self.before])
        finally:
            self.env.start()
        self.assertNotEqual(code, 0)
        self.assertEqual(out.getvalue(), "")


class UpgradeNoticeOrientation(UpgradeFixture, unittest.TestCase):
    def test_orientation_lists_the_pending_notice_with_its_step(self):
        self.plane_task("0002-cache", "pending", "Cache", "plane.json verify.accept_cache")
        before = self.commit("before")
        self.plane_task("0002-cache", "done", "Cache", "plane.json verify.accept_cache")
        release = self.commit("release")
        self.product_json()
        self.assertEqual(self.ccp("notify", "upgrade", "--since", before)[0], 0)
        code, text, err = orientation(self.product.root)
        self.assertEqual(code, 0, err)
        self.assertIn("# CCP — Claude Control Plane", text)
        self.assertIn(f"[demo] upgrade: {release}", text)
        self.assertIn("0002-cache: plane.json verify.accept_cache", text)
        self.assertIn(f"ccp notify sent upgrade --id {release} --via lead", text)
        self.assertLessEqual(len(text), 9500 + 1)

    def test_with_nothing_pending_the_orientation_is_unchanged(self):
        self.product_json()
        code, text, err = orientation(self.product.root)
        self.assertEqual(code, 0, err)
        self.assertIn("# CCP — Claude Control Plane", text)
        self.assertNotIn("[demo] ", text)  # no notice's subject


class UpgradeReason(unittest.TestCase):
    def test_steps_join_on_one_line(self):
        r = notify.upgrade_reason([{"task": "0001-a", "adopt": "plane.json a.b"},
                                   {"task": "0002-b", "adopt": "run  ccp\ndocs regen"}])
        self.assertEqual(r, "0001-a: plane.json a.b; 0002-b: run ccp docs regen")

    def test_steps_past_the_limit_are_counted(self):
        steps = [{"task": f"{i:04d}-t", "adopt": "plane.json " + "k" * 300} for i in range(30)]
        r = notify.upgrade_reason(steps)
        self.assertLessEqual(len(r), notify.NOTE_MAX)
        self.assertNotIn("\n", r)
        kept = r.count(": plane.json ")
        self.assertTrue(r.endswith(f"+{30 - kept} more: ccp upgrade status"), r[-80:])
        self.assertGreater(kept, 0)
        notify.render("demo", "upgrade", "", "abc", r)  # within the one-line limit render takes

    def test_a_record_only_trigger_is_never_fired_or_sent(self):
        with self.assertRaises(ValueError):
            notify.send(None, "upgrade")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            notify.fire(None, None, "upgrade")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
