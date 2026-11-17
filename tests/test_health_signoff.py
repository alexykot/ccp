"""ccp health (SPEC §27.1): per review point, how long verified work waited on an operator sign-off or a
merge gate, from its latest approving verdict."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ccp import cli, health
from tests.helpers import Product
from tests.test_health import T0, commit, git

MIN = 60


def at(off: int) -> str:
    return datetime.fromtimestamp(T0 + off, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(off: int, tid: str, typ: str, op: str, **payload) -> dict:
    return {"at": at(off), "task_id": tid, "type": typ, "op": op, "payload": payload}


class SignOffWait(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.ids = ("0001-signed", "0002-gated", "0003-nowait", "0004-unpointed", "0005-later")
        for tid in self.ids:
            f = self.p.task(tid, "done")
            if tid != "0004-unpointed":
                point = "R2" if tid == "0005-later" else "R1"
                f.write_text(f.read_text().replace('spec_refs: ["S1"]\n', f'spec_refs: ["S1"]\nreview_point: {point}\n'))
        git(self.p.root, "init", "-q", "-b", "main")
        git(self.p.root, "add", "-A")
        commit(self.p.root, "init", T0)
        for i, tid in enumerate(self.ids, 1):
            self.p.write(f"app/{i}.py", "x\n")
            git(self.p.root, "add", "-A")
            commit(self.p.root, f"Task {tid[:4]}: it (#{i})", T0 + 40000 + i)
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "observability").mkdir()
        (self.q / "verification").mkdir()

    def tearDown(self):
        self.p.cleanup()
        self._q.cleanup()

    def ledger(self, *events: dict) -> None:
        (self.q / "observability" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))

    def three_in_r1(self) -> list[dict]:
        return [
            # 0001: approved, then a build sign-off 60 minutes later; a brief sign-off before is no end
            ev(0, "0001-signed", "sign_off", "recorded", stage="brief"),
            ev(1000, "0001-signed", "verify", "recorded", verdict="approve"),
            ev(1000 + 60 * MIN, "0001-signed", "sign_off", "recorded", stage="build"),
            # 0002: approved, then a merge gate decided 180 minutes later; another class of gate is no end
            ev(2000, "0002-gated", "verify", "recorded", verdict="approve"),
            ev(2100, "0002-gated", "gate", "opened", escalation_id="0002-gated-1", **{"class": "spend"}),
            ev(2200, "0002-gated", "gate", "decided", escalation_id="0002-gated-1", decided_by="design_seat"),
            ev(2300, "0002-gated", "gate", "opened", escalation_id="0002-gated-2", **{"class": "merge"}),
            ev(2000 + 180 * MIN, "0002-gated", "gate", "decided", escalation_id="0002-gated-2", decided_by="design_seat"),
            # 0003: approved, then a standing merge approval: it waited on no one
            ev(3000, "0003-nowait", "verify", "recorded", verdict="approve"),
            ev(3001, "0003-nowait", "gate", "opened", escalation_id="0003-nowait-1", standing=True, **{"class": "merge"}),
            ev(3001, "0003-nowait", "gate", "decided", escalation_id="0003-nowait-1", decided_by="standing"),
            # 0004: waited, but names no review point
            ev(4000, "0004-unpointed", "verify", "recorded", verdict="approve"),
            ev(4000 + 30 * MIN, "0004-unpointed", "sign_off", "recorded", stage="build"),
        ]

    def run_cli(self, *args: str) -> str:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()), mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}):
            self.assertEqual(cli.main(["--root", str(self.p.root), "health", *args]), 0)
        return out.getvalue()

    def test_per_review_point_tasks_median_and_longest_in_json_and_text(self):
        self.ledger(*self.three_in_r1())
        w = json.loads(self.run_cli("--json"))["sign_off_wait"]
        self.assertEqual(list(w), ["R1"])
        self.assertEqual([(t["task_id"], t["wait_s"], t["on"]) for t in w["R1"]["tasks"]],
                         [("0001-signed", 60 * MIN, "sign_off"), ("0002-gated", 180 * MIN, "merge_gate")])
        self.assertEqual((w["R1"]["median_s"], w["R1"]["longest_s"]), (120 * MIN, 180 * MIN))
        self.assertIn("Sign-off wait R1: 2 task(s) waited after their approve, median 120 min, longest 180 min",
                      self.run_cli())

    def test_the_wait_runs_from_the_latest_approve_to_the_first_end_after_it(self):
        self.ledger(
            ev(0, "0001-signed", "verify", "recorded", verdict="approve"),
            ev(600, "0001-signed", "sign_off", "recorded", stage="build"),  # before the latest approve
            ev(1000, "0001-signed", "verify", "recorded", verdict="reject"),
            ev(2000, "0001-signed", "verify", "recorded", verdict="approve"),
            ev(2000 + 20 * MIN, "0001-signed", "sign_off", "recorded", stage="build"),
            ev(2000 + 50 * MIN, "0001-signed", "sign_off", "recorded", stage="build"),
            # 0005: its approve is only on the verification record; it lands in R2
            ev(5000 + 10 * MIN, "0005-later", "sign_off", "recorded", stage="build"),
        )
        (self.q / "verification" / "0005-later.json").write_text(
            json.dumps({"task_id": "0005-later", "verdict": "approve", "checked_at": at(5000)}))
        w = health.collect(self.p.cfg, self.q)["sign_off_wait"]
        self.assertEqual(list(w), ["R1", "R2"])
        self.assertEqual([(t["task_id"], t["wait_s"]) for t in w["R1"]["tasks"]], [("0001-signed", 20 * MIN)])
        self.assertEqual([(t["task_id"], t["wait_s"]) for t in w["R2"]["tasks"]], [("0005-later", 10 * MIN)])

    def test_since_keeps_only_the_tasks_merged_in_the_window(self):
        self.ledger(*self.three_in_r1())
        late = datetime.fromtimestamp(T0 + 40002, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        w = health.collect(self.p.cfg, self.q, late)["sign_off_wait"]
        self.assertEqual([t["task_id"] for t in w["R1"]["tasks"]], ["0002-gated"])

    def test_no_queue_no_wait(self):
        self.assertIsNone(health.collect(self.p.cfg, None)["sign_off_wait"])


if __name__ == "__main__":
    unittest.main()
