"""SPEC §10.4, §10.5, §31.3: no task transition writes a `queue/<state>/` marker any more, so a claim, a
release, a close and a sync leave the queue without a `queue/` directory; an older queue's `queue/`
directory is a top-level entry the plane does not keep, which `ccp plane check --archive` moves aside."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccp import queue
from tests.helpers import TASK
from tests.toolkit_fixture import ToolkitFixture, git

MARKERS = "queue"  # the retired top-level directory of per-task state markers


class NoTransitionWritesAMarker(ToolkitFixture, unittest.TestCase):
    def assertNoMarkers(self):
        self.assertFalse((self.q / MARKERS).exists(), sorted(p.name for p in self.q.iterdir()))

    def test_a_claim_and_a_release_leave_no_marker(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        self.assertNoMarkers()
        code, body, out, err = self.ccp("tasks", "release", "0002", "--reason", "claimed too early")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["released_from"], "leased")
        self.assertNoMarkers()

    def test_a_close_leaves_no_marker(self):
        self._to_approved_pr()
        code, _, out, err = self.ccp("tasks", "close", "0002", "--pr", self.PR, "--summary", "it is built.")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.q / "tasks/0002-second.json").read_text())["status"], "done")
        self.assertNoMarkers()

    def test_a_sync_settles_a_dropped_task_and_leaves_no_marker(self):
        (self.runner / "docs/delivery/tasks/0003-dropped.md").write_text(TASK.format(
            tid="0003-dropped", title="Dropped", status="dropped", deps="", ver="*Append-only.*"))
        (self.q / "tasks").mkdir(exist_ok=True)
        (self.q / "tasks/0003-dropped.json").write_text(json.dumps({"task_id": "0003-dropped", "status": "pending"}))
        code, body, out, err = self.ccp("tasks", "sync")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([c["task_id"] for c in body["changed"]], ["0003-dropped"])
        self.assertNoMarkers()

    def test_an_old_queues_marker_directory_is_archived_as_a_leftover(self):
        old = self.q / MARKERS / "pending" / "0002-second"
        old.parent.mkdir(parents=True)
        old.touch()
        code, body, out, err = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0, out + err)
        self.assertEqual([r["path"] for r in body["archived"]], [f"{MARKERS}/"])
        self.assertNoMarkers()
        day = queue.now().strftime("%Y-%m-%d")
        self.assertTrue((self.q / queue.LEGACY_DIR / day / MARKERS / "pending" / "0002-second").is_file())
        self.assertEqual(git(self.main, "status", "--porcelain"), "")  # the product is untouched


class TheMarkerDirectoryIsNotThePlanes(unittest.TestCase):
    def test_a_queue_holding_only_markers_lists_them_as_its_one_leftover(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d)
            (q / MARKERS / "done").mkdir(parents=True)
            (q / MARKERS / "done" / "0001-x").touch()
            (q / "tasks").mkdir()
            self.assertEqual(queue.leftover_entries(q), [MARKERS])
            self.assertEqual(queue.queue_leftovers(q), [f"unknown: {MARKERS}/"])


if __name__ == "__main__":
    unittest.main()
