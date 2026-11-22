"""SPEC §3.6, §29.3: `ccp notify upgrade` records a release's `upgrade` notice for a product, the
`adopt` steps of the release's tasks it has not taken, and records none when there are none; the lead
finds it in `ccp notify pending` and in the orientation."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, notify
from ccp.queue import lib
from tests.helpers import Product
from tests.upgrade_fixture import UpgradeFixture

PLANE = Path(__file__).resolve().parents[1]  # this checkout: its plugin gives the orientation
HOOK = PLANE / "plugin" / "hooks" / "orientation.sh"


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


class OrientationHookNotices(unittest.TestCase):
    """The hook asks the `ccp` beside its plugin (`<plugin>/../bin/ccp`) for `orientation --tail`: here a
    stand-in that prints a fixed answer, or one that hangs."""

    def setUp(self):
        self.p = Product()
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.plugin = tmp / "plugin"
        self.plugin.mkdir()
        (tmp / "bin").mkdir()
        self.fake = tmp / "bin" / "ccp"
        self.answer = tmp / "pending.json"

    def tearDown(self):
        self.p.cleanup()
        self._tmp.cleanup()

    def fake_ccp(self, body: str) -> None:
        self.fake.write_text("#!/bin/sh\n" + body + "\n")
        self.fake.chmod(0o755)

    def run_hook(self) -> tuple[subprocess.CompletedProcess, str]:
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR")}
        env.update(CLAUDE_PROJECT_DIR=str(self.p.root), CLAUDE_PLUGIN_ROOT=str(self.plugin))
        r = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_notices_past_the_cap_are_counted_and_long_reasons_cut(self):
        (self.plugin / "orientation.md").write_text("# Orientation\n" + "o" * 9000 + "\nlast-orientation-line\n")
        rows = [{"trigger": "blocker", "subject": f"[demo] blocker: n{i}",
                 "reason": "r" * 500 + "TAIL" + "r" * 3496,
                 "record": f"ccp notify sent blocker --id n{i} --via lead"} for i in range(10)]
        self.answer.write_text(notify.orientation_tail(rows, ""))
        self.fake_ccp(f'case "$*" in *"orientation --tail"*) cat "{self.answer}" ;; *) exit 1 ;; esac')
        _r, text = self.run_hook()
        self.assertLessEqual(len(text), 9500)
        self.assertTrue(text.startswith("# Orientation"))
        self.assertNotIn("last-orientation-line", text)  # the orientation is cut, not the notices
        notices = text[text.index("## Pending notices"):]
        self.assertEqual([f"n{i}" in notices for i in range(10)], [True] * 4 + [False] * 6)
        self.assertTrue(notices.rstrip("\n").endswith("- … 6 more: `ccp notify pending`"), notices[-80:])
        self.assertNotIn("TAIL", notices)
        self.assertEqual(notices.count("r" * 500 + "…. Record: `ccp notify sent blocker --id n"), 4)

    def test_a_hanging_ccp_drops_the_notices_not_the_orientation(self):
        (self.plugin / "orientation.md").write_text("# Orientation\nmarker-5c1e\n")
        self.fake_ccp("exec sleep 30")
        t0 = time.monotonic()
        _r, text = self.run_hook()
        self.assertLess(time.monotonic() - t0, 8)  # within the harness's 10 s SessionStart limit
        self.assertIn("marker-5c1e", text)
        self.assertNotIn("## Pending notices", text)


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
