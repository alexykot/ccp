"""`ccp tasks submit` (SPEC §15.1): formal-submit, the standing DoD's local checklist the runner runs after
the review that clears the PR head and before `ccp prompt verify`. It is not the gate: it runs no test of its own
(the review skips' proof and provers run as `ccp prompt verify` runs them) and writes nothing but the task's move to
`submitted` (§10.1), and `ccp prompt verify` neither runs it nor requires it.

The PR and its head are the ones the task's latest done implement or rework round reported (§13.4). Whether the
review record's review covers that head is judged by the rules `ccp prompt verify` applies (§15.2). A failed item
is refused, exit 4, naming each, with nothing moved. `unit_lint` is the verifier's own run: submit only says
whether the round that reported the head recorded a passed `ccp suite run` on the full or gate lane. A task that is
not mid-flight, or is already past `submitted`, is refused, exit 3, with nothing moved.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from ccp import report, runs
from ccp.config import Config, lane_for
from ccp.queue import MID_FLIGHT, QueueError, load_task_state, phase_move, read_json, root, task_meta

# The standing DoD's `formal_submit` items submit judges, in the order it names a failure (dod/standing.yaml);
# its fourth, `unit_lint`, is reported, never judged.
ITEMS = ("pr_exists", "review_artifact_present", "no_open_spec_escalation")

# §10.1: the phases a task is submitted from, mid-flight and not past `submitted`.
SUBMITTABLE = MID_FLIGHT - {"verifying", "merging"}


class Facts(NamedTuple):
    """What the checklist judges, read from the queue: the PR and head the task's latest done change round
    reported, the review record (None when there is none), the task's latest done review (run id and verdict),
    why that review does not cover the head by `ccp prompt verify`'s rules (None when it does), and the open spec
    questions and escalations that list the task."""
    pr: int | None
    head: str | None
    record: dict[str, Any] | None
    latest_review: str | None
    latest_clean: bool
    uncovered: str | None
    open_refs: list[str]


def failures(task_id: str, f: Facts) -> list[str]:
    """§15.1: each failed item, as `<item>: <why>`, in `ITEMS` order; empty when the task may be submitted."""
    out = []
    if f.pr is None:
        out.append(f"pr_exists: no implement or rework round of {task_id} reported done with a PR")
    if gaps := _review_gaps(task_id, f):
        out.append("review_artifact_present: " + "; ".join(gaps))
    if f.open_refs:
        out.append(f"no_open_spec_escalation: open, listing {task_id}: {', '.join(f.open_refs)}")
    return out


def phase_refusal(task_id: str, status: str | None) -> str | None:
    """§10.1: why a task in `status` is not submitted (closed, released, verifying or merging); None when it may be."""
    if status in SUBMITTABLE:
        return None
    return f"{task_id} is {status or 'pending'}: only a task mid-flight and not past `submitted` is submitted"


def _review_gaps(task_id: str, f: Facts) -> list[str]:
    rec = f.record
    path = f"{report.REVIEW_DIR}/{task_id}.json"
    if rec is None:
        return [f"no review record {path}: a review that reports clean writes it"]
    gaps = []
    if f.latest_review != rec.get("review_run_id"):
        gaps.append(f"{path} records review {rec.get('review_run_id')}, not the latest done review "
                    f"{f.latest_review or '(none)'}")
    if f.latest_review and not f.latest_clean:
        gaps.append(f"the latest done review {f.latest_review} found a BLOCKER or MAJOR")
    if f.pr is not None and report.pr_number(rec.get("pr")) != f.pr:
        gaps.append(f"{path} records PR {rec.get('pr')}, not PR {f.pr}")
    if f.head is None:
        gaps.append("no round reported a head for the review to cover")
    elif f.uncovered:
        gaps.append(f.uncovered)
    return gaps


def _latest_change(q: Path, task_id: str) -> dict[str, Any] | None:
    done = [r for r in runs.all_runs(q, task_id) if r.get("phase") in runs.CHANGE_PHASES
            and runs.state(r) == "reported" and r.get("outcome") == "done" and r.get("head")]
    return done[-1] if done else None


def _latest_review(q: Path, task_id: str) -> dict[str, Any] | None:
    done = [r for r in runs.all_runs(q, task_id) if r.get("phase") == "review" and runs.state(r) == "reported"
            and r.get("outcome") == "done"]
    return done[-1] if done else None


def coverage(cfg: Config, q: Path, task_id: str, head: str, pr: int | None) -> str | None:
    """§15.2: why the task's latest done review does not cover `head`, by `ccp prompt verify`'s rules: a fix round
    newer than it or a head it did not judge (`runs.unreviewed_fix`), unless `verify.skip_review`, a review prover or
    `verify.skip_review_after_clean` takes the fix; None when it covers."""
    from ccp import verify  # noqa: PLC0415
    why = runs.unreviewed_fix(q, task_id, head)
    if why is None:
        return None
    skipped, unproven = verify.skip_review(cfg, q, task_id, head, str(pr) if pr else None)
    if skipped:
        return None
    skipped, unclean = verify.skip_after_clean(cfg, q, task_id, head)
    if skipped:
        return None
    return why + (f" ({unproven})" if unproven else "") \
        + (f" (verify.skip_review_after_clean does not apply: {unclean})" if unclean else "")


def open_refs(q: Path, task_id: str) -> list[str]:
    """§17.3, §17.9: the open spec questions whose `task_id` or `blocks` name the task, as the spec maintainer counts
    them (`open_questions`: open, or escalated to the operator), and the open escalations of class `spec` of the
    task, by id."""
    from ccp.queue import lib, open_questions  # noqa: PLC0415
    out = [str(qq.get("question_id")) for qq in open_questions(q)
           if qq.get("task_id") == task_id or task_id in (qq.get("blocks") or [])]
    ed = q / "escalations"
    for f in sorted(ed.rglob("*.json")) if ed.is_dir() else []:
        g = _read(f)
        if (g.get("task_id") or f.parent.name) == task_id and g.get("class") == "spec" \
                and g.get("status") in lib.OPEN_GATE_STATUSES:
            out.append(str(g.get("escalation_id") or f"{f.parent.name}-{f.stem}"))
    return out


def _read(f: Path) -> dict[str, Any]:
    try:
        v = read_json(f, {})
    except QueueError:
        return {}
    return v if isinstance(v, dict) else {}


def unit_lint(cfg: Config, q: Path, run: dict[str, Any] | None) -> dict[str, Any]:
    """§15.1: the passed `ccp suite run` on the full or gate lane the round that reported the head recorded, as
    `{run_id, head, suite_id}` (`suite_id` None when there is none). Reported, never judged."""
    from ccp import suite  # noqa: PLC0415
    rid = str((run or {}).get("run_id") or "") or None
    lanes = {lane_for(cfg, r) for r in report.AUTO_ROLES}
    try:
        rows = suite.fold(q)
    except Exception:  # noqa: BLE001  (a damaged suites file: nothing recorded to report)
        rows = []
    passed = [r for r in rows if rid and r.get("run_id") == rid and r.get("lane") in lanes and r.get("state") == "passed"]
    return {"run_id": rid, "head": (run or {}).get("head"), "suite_id": passed[-1].get("suite_id") if passed else None}


def submit(cfg: Config, task: str) -> dict[str, Any]:
    q = root()
    tid = str(task_meta(cfg, task)["task_id"])
    st = load_task_state(q, tid)
    if why := phase_refusal(tid, st.get("status")):
        raise QueueError(f"formal-submit refused, nothing moved (SPEC §15.1): {why}", 3)
    last = _latest_change(q, tid)
    pr = report.pr_number((last or {}).get("pr")) or report.pr_number(st.get("pr"))
    head = str(last["head"]) if last else None
    record = _read(report.review_record_path(q, tid)) or None
    latest = _latest_review(q, tid)
    clean = latest is not None and report.review_verdict("review", latest) == "clean"
    facts = Facts(pr, head, record, str(latest["run_id"]) if latest else None, clean, None, open_refs(q, tid))
    if record is not None and head is not None and not _review_gaps(tid, facts):  # only then judge the head (git)
        facts = facts._replace(uncovered=coverage(cfg, q, tid, head, pr))
    failed = failures(tid, facts)
    if failed:
        raise QueueError("formal-submit refused, nothing moved (SPEC §15.1):\n  " + "\n  ".join(failed), 4)
    lint = unit_lint(cfg, q, last)
    warnings = [] if lint["suite_id"] else [
        f"unit_lint: {lint['run_id']} recorded no passed `ccp suite run` on the full or gate lane at {str(head)[:12]}; "
        "not judged here: the verifier's own run is the gate (SPEC §15.1)"]
    frm = phase_move(q, cfg, tid, "submitted", "ccp tasks submit")
    return {"ok": True, "task_id": tid, "from": frm, "to": "submitted", "pr": pr, "head": head,
            "review_record": f"{report.REVIEW_DIR}/{tid}.json", "review_run_id": record["review_run_id"] if record else None,
            "unit_lint": lint, **({"warnings": warnings} if warnings else {})}
