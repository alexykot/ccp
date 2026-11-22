"""§17.7 skip-ahead and the task-id check of `spec-maintainer-ask.sh`: the task log through the binding."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PLANE_ROOT, Product, binding

ASK = PLANE_ROOT / "scripts" / "spec-maintainer-ask.sh"
QID = "sm-20261122T000000Z-abcd"


class SkipAhead(unittest.TestCase):
    def setUp(self):
        self.prod = Product()
        self.addCleanup(self.prod.cleanup)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)
        (self.q / "project.yaml").write_text(binding(product_root=self.prod.root))
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        self.env = {k: v for k, v in os.environ.items() if k not in ("DURABLE_DOCS", "PROJECT_YAML", "ACTOR")}
        self.env["QUEUE_ROOT"] = str(self.q)
        self.prod.task("0001-a")
        self.prod.task("0002-b", deps=["0001-a"])
        self.prod.task("0003-c", deps=["0002-b"])
        self.prod.task("0004-d")

    def question(self, qid: str, status: str, blocks: list[str]) -> None:
        (self.q / "questions").mkdir(exist_ok=True)
        (self.q / "questions" / f"{qid}.json").write_text(
            json.dumps({"question_id": qid, "status": status, "blocks": blocks, "task_id": blocks[0]}))

    def ask(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(ASK), *argv], capture_output=True, text=True, env=self.env)

    def blocked(self) -> dict:
        r = self.ask("blocked")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_blocked_lists_the_task_log_descendants_of_a_blocked_task(self):
        self.question(QID, "open", ["0001-a"])
        got = self.blocked()
        self.assertEqual(got["blocked"], ["0001-a", "0002-b", "0003-c"])
        self.assertEqual(got["by_question"][QID]["descendants"], ["0002-b", "0003-c"])

    def test_blocked_with_no_readable_plane_json_lists_no_task_log_descendant(self):
        self.prod.write("docs/delivery/plane.json", "{not json")
        self.question(QID, "open", ["0001-a"])
        self.assertEqual(self.blocked()["blocked"], ["0001-a"])

    def test_blocked_unites_the_queue_tasks_with_the_task_log(self):
        (self.q / "tasks").mkdir()
        (self.q / "tasks" / "0005-e.json").write_text(json.dumps({"task_id": "0005-e", "depends_on": ["0003-c"]}))
        self.question(QID, "open", ["0001-a"])
        self.assertEqual(self.blocked()["blocked"], ["0001-a", "0002-b", "0003-c", "0005-e"])

    def test_an_escalated_question_blocks_and_an_answered_one_does_not(self):
        self.question(QID, "escalated", ["0001-a"])
        self.question("sm-20261122T000001Z-abce", "answered", ["0004-d"])
        self.assertEqual(self.blocked()["blocked"], ["0001-a", "0002-b", "0003-c"])

    def raise_for(self, tid: str) -> subprocess.CompletedProcess:
        return self.ask("raise", "--raised-by", "task-runner", "--task-id", tid, "--text", "Which?",
                        "--inconsistency", "task vs SPEC", "--spec-refs", "S1")

    def test_raise_refuses_an_id_at_the_wrong_width(self):
        r = self.raise_for("00001-x")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("00001-x", r.stderr)
        self.assertEqual(list(self.q.glob("questions/*")), [])

    def test_raise_takes_the_id_shape_from_the_product(self):
        plane = json.loads((self.prod.root / "docs/delivery/plane.json").read_text())
        self.prod.write("docs/delivery/plane.json", json.dumps({**plane, "ids": {"task": {"width": 5}}}))
        for f in (self.prod.root / "docs/delivery/tasks").glob("*.md"):
            f.unlink()
        r = self.raise_for("0001-x")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("NNNNN-slug", r.stderr)
        self.assertEqual(list(self.q.glob("questions/*")), [])


if __name__ == "__main__":
    unittest.main()
