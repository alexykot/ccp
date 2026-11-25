"""SPEC §10.4, §10.5, §31.3: an older queue's `queue/<state>/` marker directory is a top-level entry the
plane does not keep: `ccp plane check --archive` moves it aside, and a queue holding only markers lists it
as its one leftover."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ccp import queue
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

MARKERS = "queue"  # the retired top-level directory of per-task state markers


class AnOldMarkerDirectoryIsArchived(ToolkitFixture, unittest.TestCase):
    def assertNoMarkers(self):
        self.assertFalse((self.q / MARKERS).exists(), sorted(p.name for p in self.q.iterdir()))

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
