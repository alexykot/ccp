"""SPEC §2.4, §24.5: a run pinned to a model alias (plane.json `workers.implementer_model`) is judged
against the full ids telemetry reports: an alias matches any full id of its family, a full id only
itself. The usage fold (the pin check and the window join) and the board's live seats both read it."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccp import config, models, runs, seats, usage
from tests.test_board_seats import Base, req as seat_req
from tests import test_usage
from tests.test_usage import req

SONNET, OPUS = "claude-sonnet-5-5", "claude-opus-5-5"


class Matches(unittest.TestCase):
    def test_a_full_id_matches_only_an_equal_id(self):
        self.assertTrue(models.matches(SONNET, SONNET))
        for other in ("claude-sonnet-5-4", "claude-sonnet-5-5[1m]", OPUS, "sonnet"):
            self.assertFalse(models.matches(other, SONNET), other)

    def test_an_alias_matches_its_family_and_no_other(self):
        for alias, full in (("sonnet", SONNET), ("opus", OPUS), ("haiku", "claude-haiku-4-5"),
                            ("fable", "claude-fable-5-1")):
            self.assertTrue(models.matches(full, alias), (full, alias))
            self.assertTrue(models.matches(f"{full}[1m]", alias), (full, alias))
        self.assertTrue(models.matches("sonnet", "sonnet"))
        for other in (OPUS, "claude-haiku-4-5", "claude-fable-5-1", "claude-sonnetx-5-5", "sonnet-5-5", ""):
            self.assertFalse(models.matches(other, "sonnet"), other)

    def test_an_unknown_alias_matches_nothing(self):
        for full in (SONNET, OPUS, "claude-mystery-5-5"):
            self.assertFalse(models.matches(full, "mystery"), full)


class UsageFold(unittest.TestCase):
    """Two implement runs pinned to `sonnet`: one observed on a full Sonnet id (through the window
    join, no span), one on a full Opus id (through its span)."""
    mkrun, write, rows = test_usage.Fold.mkrun, test_usage.Fold.write, test_usage.Fold.rows

    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.q = Path(self._d.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        (self.q / "board").mkdir()
        self.mkrun("0001-a/implement", "implementer", "sonnet", "high", agent="a1", start=0, stop=100)
        self.mkrun("0002-b/implement", "implementer", "sonnet", "high", agent="b1", start=200, stop=300)

    def test_the_sonnet_run_is_on_pin_and_windowed_and_the_opus_run_is_flagged(self):
        self.write("usage-requests.jsonl", self.rows(req("x1", 50, model=SONNET), req("y1", 250, model=OPUS)))
        self.write("usage-spans.jsonl", [{"request_id": "y1", "agent_id": "b1"}])
        r = usage.fold(self.q)
        by = {x["run_id"]: x for x in r["runs"]}
        a, b = by["0001-a/implement"], by["0002-b/implement"]
        self.assertEqual((a["usage"]["requests"], a["flags"]), (1, []))
        self.assertEqual((b["usage"]["requests"], b["flags"]), (1, [f"model {OPUS}, pinned sonnet"]))
        self.assertEqual((r["how"]["window"], r["how"]["span"], r["how"]["none"]), (1, 1, 0))

    def test_a_request_of_another_family_is_not_windowed_to_an_alias_run(self):
        self.write("usage-requests.jsonl", self.rows(req("x1", 50, model=OPUS)))
        r = usage.fold(self.q)
        self.assertEqual((r["how"]["window"], r["how"]["none"]), (0, 1))

    def test_a_lead_expected_on_an_alias_is_not_advised_on_its_family(self):
        self.write("usage-requests.jsonl", self.rows(req("l1", 40, model=f"{OPUS}[1m]", effort="xhigh",
                                                        source="repl_main_thread")))
        self.assertEqual(usage.fold(self.q, design_seat={"model": "opus", "effort": "xhigh"})["advice"], [])
        self.assertEqual(len(usage.fold(self.q, design_seat={"model": "sonnet", "effort": "xhigh"})["advice"]), 1)


class BoardSeats(Base, unittest.TestCase):
    def test_the_sonnet_run_is_on_pin_and_the_opus_run_is_a_mismatch(self):
        rid = self.open_implement()
        cfg = config.load(self.main)
        runs.bind(self.q, cfg, "delivery-implementer", "agent-1", "sess-1")
        p = next((self.q / "runs" / rid.split("/")[0]).glob("implement*.json"))
        rec = json.loads(p.read_text())
        p.write_text(json.dumps({**rec, "expected_model": "sonnet"}))
        other = {**rec, "expected_model": "sonnet", "run_id": f"{rid}-b", "agent_id": "agent-2"}
        (p.parent / f"{p.stem}-b.json").write_text(json.dumps(other))
        self.requests(seat_req("r1", 3, SONNET, "high"), seat_req("r2", 2, OPUS, "high"),
                      spans=[{"request_id": "r1", "agent_id": "agent-1"}, {"request_id": "r2", "agent_id": "agent-2"}])
        r = self.rows(self.build())
        on, off = r[f"implementer {rid}"], r[f"implementer {rid}-b"]
        self.assertEqual((on["observed"]["model"], on["mismatch"]), (SONNET, []))
        self.assertEqual((off["observed"]["model"], off["mismatch"]), (OPUS, [f"model {OPUS}, pinned sonnet"]))
        code, body, out, err = self.ccp("usage", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        flags = {x["run_id"]: x["flags"] for x in body["runs"]}
        self.assertEqual((flags[rid], flags[f"{rid}-b"]), ([], [f"model {OPUS}, pinned sonnet"]))

    def test_a_lead_expected_on_an_alias_is_compared_without_its_suffix(self):
        self.assertEqual(seats.mismatch({"model": "opus"}, {"model": f"{OPUS}[1m]"}, prefix=True), [])
        self.assertEqual(seats.mismatch({"model": "sonnet"}, {"model": f"{OPUS}[1m]"}, prefix=True),
                         [f"model {OPUS}[1m], pinned sonnet"])


if __name__ == "__main__":
    unittest.main()
