"""The reports, verdicts and marked-check text the tests share. Holds no tests.

`done_report(phase, *lines)` is the text of a done report of a phase that `ccp report` accepts, with the section
the phase needs when done: a test that files a done report for something else writes it with this. The rest:
`implement_report`, `approve_verdict`, `judge_merge_ok`, `held_otherwise`, `HEAD_A`, `HEAD_B` and the marked-check
text (`MARKED_CHECK_ID`, `MARKED_TASK_ID`, `MARKED_BLOCK`)."""
from __future__ import annotations

from datetime import datetime, timezone

from tests.helpers import Product


# What a done report of each phase carries besides `Outcome:`, its own lines and `## Friction` (SPEC §13.4): a
# review's `## Spec beyond intent`, and a round that pushes a head its `## Tests for new behaviour`.
def done_sections() -> dict[str, tuple[str, str]]:
    from ccp import runs  # noqa: PLC0415
    return {"review": ("## Spec beyond intent", "none"),
            **{p: ("## Tests for new behaviour", "none: the fixture's round adds no behaviour") for p in runs.CHANGE_PHASES}}


def done_report(phase: str, *lines: str, friction: tuple[str, ...] = ("none",)) -> str:
    """A report of `phase` with `Outcome: done` for `ccp report`: `lines` (a round's `PR:` and `Head:`, a review's
    `Severity:`, a `Suite:` line, a `## Follow-ups` section), the section the phase needs when done, and
    `## Friction` with the lines `friction`."""
    return "\n".join(["Outcome: done", *lines, *done_sections().get(phase, ()), "## Friction", *friction, ""])


MARKED_CHECK_ID = "mac-01"
MARKED_TASK_ID = "0002-second"
MARKED_BLOCK = f"""- id: `{MARKED_CHECK_ID}`
  story: As the operator, it runs on my machine.
  setup: a checkout of the head.
  runs_on: operator-machine
  steps:
    1. run it
  expect: exit 0

## Implementation notes"""


REPORT_HEAD = "a" * 40


def implement_report(*lines: str, outcome: str = "done") -> str:
    if outcome == "done":
        return done_report("implement", "PR: #7", f"Head: {REPORT_HEAD}", *lines)
    return "\n".join([f"Outcome: {outcome}", "PR: #7", f"Head: {REPORT_HEAD}", *lines, "## Friction", "none", ""])


HEAD_A = "a" * 40
HEAD_B = "b" * 40


def approve_verdict(task: str = "0001-a", **fields: object) -> dict:
    """A verdict that passes every rule: what the verifier writes for an approve at HEAD_A."""
    return {
        "task_id": task, "project_id": "demo", "verdict": "approve", "head_sha": HEAD_A,
        "checks": [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}],
        "spec_beyond_intent": [],
        "gate": {"runs": [{"command": "scripts/unit.sh", "exit_code": 0, "tests_run": 412,
                           "tests_skipped": 0, "seconds": 88.5},
                          {"command": "scripts/lint.sh", "exit_code": 0}]},
        **fields,
    }


def judge_merge_ok(p: Product, queue: Path, rec: dict, rid: str = "0001-a", recorded: tuple | None = None,
                   pr: str = "7", **facts: object) -> tuple[list[str], dict]:
    """The merge-ok decision on plain values: an open PR at HEAD_A (`facts` override), `rec` recorded just now."""
    from ccp import prhost, verify  # noqa: PLC0415
    got = prhost.PrFacts(**{"number": 7, "state": "open", "head": HEAD_A, **facts})
    return verify.judge(p.cfg, queue, rec, rid, got.head, got, recorded or (datetime.now(timezone.utc), "written"), pr)


def held_otherwise(**fields: object) -> dict:
    """A check the verifier ran that held only in another form, under the approved gate 0001-a-1."""
    return {"dod_check_id": "check-01", "pass": True, "as_written": False,
            "held_instead": "ran the listing at the head in place of the removed flag: exit 0",
            "ruling": "0001-a-1", "evidence": "the expectation names a flag the product no longer has",
            "produced_by": "verifier", **fields}
