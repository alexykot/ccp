"""A check that cannot hold as written (SPEC §15.4): `as_written: false`, with `held_instead` and a
`ruling`, written by `ccp verify record`, accepted by `merge-ok`, and read by an older reader."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, verify
from tests.helpers import approve_verdict as approve, held_otherwise, judge_merge_ok as decide, PLANE_ROOT, Product

ROOT = PLANE_ROOT
NEW_KEYS = ("as_written", "held_instead", "ruling")


class NotAsWritten(unittest.TestCase):

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        gates = self.q / "escalations" / "0001-a"
        gates.mkdir(parents=True)
        for n, status, decision in ((1, "closed", "approved"), (2, "open", None)):
            (gates / f"{n}.json").write_text(json.dumps({"task_id": "0001-a", "escalation_id": f"0001-a-{n}",
                                                         "class": "other", "status": status, "decision": decision}))
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def record(self, body: dict):
        src = self.q / "in.json"
        src.write_text(json.dumps(body))
        return self.ccp("verify", "record", str(src))

    def written(self) -> Path:
        return self.q / "verification" / "0001-a.json"

    def merge_ok(self):
        """The merge-ok decision on the record as written, for an open PR at its head."""
        return decide(self.p, self.q, json.loads(self.written().read_text()))

    def test_a_check_held_in_another_form_is_written_and_may_merge(self):
        code, out, err = self.record(approve(checks=[held_otherwise()]))
        self.assertEqual(code, 0, out + err)
        check = json.loads(self.written().read_text())["checks"][0]
        self.assertEqual({k: check[k] for k in NEW_KEYS}, {k: held_otherwise()[k] for k in NEW_KEYS})
        reasons, body = self.merge_ok()
        self.assertEqual(reasons, [])
        self.assertEqual(body["unrun_checks"], [])

    def test_each_copy_without_what_it_needs_is_refused_naming_the_check(self):
        drop = held_otherwise()
        cases = (
            ({k: v for k, v in drop.items() if k != "held_instead"}, "with no held_instead"),
            (held_otherwise(held_instead="  "), "with no held_instead"),
            ({k: v for k, v in drop.items() if k != "ruling"}, "with no ruling"),
            (held_otherwise(ruling="0001-a-9"), "no gate or spec question 0001-a-9 is in the queue"),
            (held_otherwise(ruling="0001-a-2"), "gate 0001-a-2 is not closed and approved"),
            (held_otherwise(ruling="the lead agreed"), "it names no ruling id"),
            (held_otherwise(ran=False, **{"pass": None}, rests_on="0001-a-1"), "on a check not run (ran: false)"),
        )
        for check, needle in cases:
            code, out, err = self.record(approve(checks=[check]))
            self.assertEqual(code, 1, (needle, out + err))
            self.assertIn("checks[0] (check-01): as_written is false", err)
            self.assertIn(needle, err)
            self.assertIn("nothing written", err)
            self.assertFalse(self.written().exists(), needle)

    def test_a_check_not_as_written_is_still_a_pass_or_a_fail(self):
        code, _, err = self.record(approve(checks=[held_otherwise(**{"pass": False})]))
        self.assertEqual(code, 1)
        self.assertIn("an approve with a failed check (check-01)", err)
        code, _, err = self.record(approve(checks=[held_otherwise(**{"pass": None})]))
        self.assertEqual(code, 1)
        self.assertIn("pass is null", err)
        code, out, err = self.record(approve(verdict="reject", checks=[held_otherwise(**{"pass": False})]))
        self.assertEqual(code, 0, out + err)

    def test_not_as_written_lists_each_such_check_in_order(self):
        rec = approve(checks=[held_otherwise(dod_check_id="check-02"),
                              {"dod_check_id": "check-01", "pass": True, "evidence": "ran it"},
                              held_otherwise(ruling="0001-a-1 and sm-0001")])
        self.assertEqual(verify.not_as_written(rec), [
            {"dod_check_id": "check-02", "held_instead": held_otherwise()["held_instead"], "ruling": "0001-a-1"},
            {"dod_check_id": "check-01", "held_instead": held_otherwise()["held_instead"],
             "ruling": "0001-a-1 and sm-0001"}])
        self.assertEqual(verify.not_as_written(approve()), [])
        self.assertEqual(verify.not_as_written("not a record"), [])

    def test_an_older_reader_passes_over_the_new_keys(self):
        code, out, err = self.record(approve(checks=[held_otherwise()]))
        self.assertEqual(code, 0, out + err)
        # The reader before this change: its version, and its contract, which names none of the keys.
        older = json.loads((ROOT / "contracts/verification.schema.json").read_text())
        for k in NEW_KEYS:
            del older["properties"]["checks"]["items"]["properties"][k]
        schema = self.q / "older.schema.json"
        schema.write_text(json.dumps(older))
        with mock.patch.object(verify, "RECORD_VERSION", verify.RECORD_VERSION - 1), \
                mock.patch.object(verify, "SCHEMA", schema):
            self.assertEqual(self.merge_ok()[0], [])
            # The same keys in a record no newer than that reader are refused: its contract is in force.
            rec = json.loads(self.written().read_text())
            self.written().write_text(json.dumps({**rec, "schema_version": verify.RECORD_VERSION}))
            self.assertIn("unexpected key as_written", "\n".join(self.merge_ok()[0]))


if __name__ == "__main__":
    unittest.main()
