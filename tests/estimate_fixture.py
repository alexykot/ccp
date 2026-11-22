"""The estimates tests' task body and history entries, and the estimates tab of the board page under node. A
fixture module: it holds no tests."""
from __future__ import annotations

import json
import subprocess

from ccp import board, estimate
from tests.board_drill_fixture import HASH_STUB
from tests.board_quality_fixture import HOSTILE


BODY = """---
task_id: {tid}
title: A task
status: {status}
kind: {kind}
depends_on: [{deps}]
spec_refs: ["S1", "S2"]
adr_refs: ["ADR-0031", "0007"]
rule_refs: ["E8"]
created: 2026-10-01
updated: 2026-10-01
---

# Task: {tid}

## Intent

Change `src/app/store.py` and `src/app/record.py`; add `ops/new_tool.py`. See `https://x/y` and `-flag`.

## Scope

- **In:** `docs/delivery/WORKERS.md`

## dod_checks

- id: `code-01`
  story: It works.
  steps:
    1. run it, then a mutation of the guard
  expect: exit 0

- id: `code-02`
  story: It still works.
  expect: exit 0

- id: `docs-01`
  expect: one match

## Implementation notes

{notes}

## Verification notes

*Append-only.*
"""


def body(tid="0005-sf-store", status="pending", kind="feature", deps="", notes="*Append-only, newest last.*"):
    return BODY.format(tid=tid, status=status, kind=kind, deps=deps, notes=notes)


def entry(tid, merged, wall, kind="feature", fam=None, areas=(), adrs=(), tokens=None, phases=None, fix=0, start=None,
          **feat):
    """A history entry as `estimate.history` returns it, with its features already read."""
    f = {"kind": kind, "family": fam if fam is not None else estimate.family(tid), "areas": list(areas), "adrs": list(adrs),
         "cited_lines": 100, "dod_checks": 3, "text_chars": 2000, "deps": 0, **feat}
    return {"task_id": tid, "merged_at": float(merged), "start": float(start if start is not None else merged - wall),
            "excluded": False, "rev": None, "features": f,
            "task": {"task_id": tid, "_text": body(tid), "depends_on": [], "status": "done"},
            "actual": {"wall_s": wall, "phases": phases or {"implement": wall / 2, "review": wall / 4, "fix": 0, "verify": wall / 4},
                       "tokens": tokens, "cost_usd": tokens / 1e6 if tokens else None,
                       "rounds": {"review": 1, "fix": fix, "verify": 1},
                       "merged_at": estimate.iso_ep(float(merged)), "start_at": estimate.iso_ep(float(merged - wall))}}


class EstimatePage:
    """The estimates tab of the board page, under node: `view` builds the estimates block, `render` runs the page's
    script over a build. A mixin before a `TestCase` (it asserts)."""

    def view(self, tid):
        h = HOSTILE
        est = {"source": "baseline" + h, "at": "2026-10-20T09:00:00Z" + h, "version": 1, "tier": "similar" + h,
               "refs": ["0001-first" + h], "backfill": True, "total": {"p50_s": 600, "p90_s": 1200},
               "tokens": {"p50": 1e6, "p90": 2e6}, "cost_usd": {"p50": 1.5, "p90": 3},
               "phases": {"implement": {"p50_s": 300, "p90_s": 600}, "review": None}, "rounds": {"review_p50": 1}}
        acc = {"actuals": 3, "sources": {"baseline": {"wall": {"n": 3, "share_p50": 0.5, "share_p90": 0.9, "median_ratio": "1.1" + h},
                                                      "tokens": {"n": 0}}, "agent": {}},
               "bias": {"baseline": {"kind" + h: {"feature" + h: {"n": 2, "share_p50": 0.5, "share_p90": 1, "median_ratio": 1}}}}}
        return {"tasks": {tid: {"baseline": est, "agent": None, "baseline_scored": est,
                                "actual": {"wall_s": 1500, "phases": {"implement": 700}, "phases_from": "spans" + h,
                                           "tokens": 2e6, "cost_usd": 2.5}}}, "accuracy": acc}

    def render(self, b, tail):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: '#tab=quality', pathname: '/b', search: ''};\n"
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + tail + "\nprocess.stdout.write(JSON.stringify(out.join('')));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)
