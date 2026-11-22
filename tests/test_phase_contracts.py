"""The progress and review contracts describe the records the plane writes (SPEC §10.1, §15.1): a progress file
`queue.progress_event` writes and a review record `ccp report` writes each validate against their schema."""
from __future__ import annotations

import json
import unittest

from ccp import queue
from ccp.schema import schema_errors
from tests.review_flow import CLEAN, PhaseFlow
from tests.test_toolkit import PLANE, ToolkitFixture


def schema(name: str) -> dict:
    return json.loads((PLANE / "contracts" / name).read_text())


class Contracts(PhaseFlow, ToolkitFixture, unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.start()

    def test_a_progress_file_progress_event_writes_validates(self):
        queue.progress_event(self.q, "0002-second", None, "leased", "first move")
        queue.progress_event(self.q, "0002-second", "leased", "implementing")
        written = json.loads((self.q / "progress/0002-second.json").read_text())
        self.assertGreaterEqual(len(written["events"]), 3)  # the claim's move, then these two
        self.assertEqual(schema_errors(written, schema("progress.schema.json")), [])

    def test_a_review_record_ccp_report_writes_validates(self):
        qid = "sm-20261022T100000Z-abcd"
        (self.q / "questions").mkdir()
        (self.q / "questions" / f"{qid}.json").write_text(json.dumps(
            {"task_id": "0002-second", "question_id": qid, "class": "spec", "status": "answered"}))
        self.implemented()
        self.reviewed_as(CLEAN)
        written = json.loads(self.review_record().read_text())
        self.assertEqual(written["decisions"], [{"class": "spec", "question_ref": qid}])
        self.assertEqual(schema_errors(written, schema("review.schema.json")), [])


if __name__ == "__main__":
    unittest.main()
