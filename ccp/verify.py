"""The verifier's record and the runner's merge gate (SPEC §15.3).

The call syntax is in `docs/cli`; the rules are in §15 and §29.3. This names the functions that hold them.
`record` validates a verdict against `contracts/verification.schema.json` with the plane's own checker
(`ccp/schema.py`, a stdlib subset of JSON Schema, so the plane takes no dependency) and against the rules the
schema cannot hold, then writes `verification/<task_id>.json` (`verification/pr-<n>.json`, task_id `pr-<n>`, for a PR that is not a task's).
It stamps `schema_version` with its own `RECORD_VERSION`, whatever the input said. A reader older than the
record passes over the keys its contract does not know, at any depth, and holds every key it knows to its
contract; a record with no version, or one no newer than the reader, is held to the contract with no extra key,
so a task that adds a field can be verified with the newer `ccp` and merged with the older one on PATH (§29.3).

`merge-ok` and `check` judge a record with one function, `judge`: `check` is `merge-ok` without the PR host's
facts (the PR's state, when the record was recorded). The merge rule it makes mechanical: the PR is open; its
head is the record's `head_sha` (or `catch_up.to`, `catch_up_refusal`: only `ccp tasks close` writes a
`catch_up`, `record_catch_up`); the record is an approve (one head, every check it ran passed, every
`gate.runs` exit 0, which `record` holds an approve to); and it was recorded no earlier than its `checked_at`.

A gate run may name its `ccp suite run` (`suite_id`, §14.1): `record` fills its numbers, and `cold` when that
record says nothing was cached, from the recorded run. Under `verify.accept_cache` it holds an approve to a
gate run that says how many units ran and were cached (`ran`, `cached`; earlier records say `modules_ran`,
`modules_cached`), and on a `cold_gate` task to a cold run. Under `adr.strict` it refuses an approve while an
`adr_refs` decision is `not_built` (§6.7).

`record` refuses an approve whose latest fix round is newer than its last review, or of a head other than the
one that review judged (§15.2), unless the verify run carries the override, the `verify.skip_review` or
`verify.skip_review_after_clean` skip, or a declared prover's `skips: review` that proved that head, each
checked in a clean checkout of the integration branch's tip.

A check's evidence is §15.4's rule: `producer_errors`, `rests_on_errors` and `as_written_errors` (listed by
`not_as_written`); `merge-ok` and `check` still refuse a ruling seat's evidence in an older record. A check marked
`runs_on: operator-machine` (ADR-0045 D3) is held by `marked_refusals` and `marked_errors`. A verdict carries
`spec_beyond_intent` (§3.5; `beyond_intent_errors`, `beyond_intent`). `later` and `deferred` (§15.4) are
`record_later` and its `verification/<task_id>.later.jsonl`, which `merge-ok`, `check` and close never read.
`fill_reason` adds a `repeat_round`'s `--note` to `findings`.

`spec-text` (§15.2) checks a PR's SPEC edits against the passages the operator signed (`signed_passages`,
`spec_text`, `spec_hunks`, `named_hunks`, `searchable`), read from the task file by `tasklog.signed_blocks`. The base defaults to
`origin/<integration branch>`, the head to `HEAD`; it reads the task file from the checkout, fetches nothing and
writes nothing. Exit 0 when every passage is found, 1 naming each that is not, 2 for no passages or an
unusable base or head.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Callable

from ccp import prhost, schema
from ccp.config import Config
from ccp.config import spec_paths as spec_paths_of
from ccp.refs import ANY_TASK_ID, QUESTION_ID

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "verification.schema.json"
# The record's schema version, stamped by `record`. A change that adds a key to the record's
# contract, at any depth, raises it, so an older reader knows the record is newer than itself.
RECORD_VERSION = 6  # 2: `catch_up` (§16.5 rule 4); 3: `spec_beyond_intent` (§3.5); 4: a check's `as_written` (§15.4);
#                     5: `catch_up.sign_off_carried` (§16.5 rule 4); 6: a check's `suite_id` (§15.4)
# Clocks on two machines differ a little; a minute is the slack, not a rounding allowance.
SKEW = timedelta(seconds=60)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _ci(queue: Path) -> bool:
    """The binding opts into CI (`ci: github-actions`, §15.3): only then may a verdict cite `gate.ci_run`."""
    from ccp.queue import lib  # noqa: PLC0415
    return re.match(r"github-actions\b", lib.binding_str(lib.binding_data(queue), "ci") or "") is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def written_by_newer(rec: Any) -> bool:
    """The record says a newer `ccp` wrote it: its `schema_version` is an integer above `RECORD_VERSION`."""
    version = rec.get("schema_version") if isinstance(rec, dict) else None
    return schema.is_type(version, "integer") and version > RECORD_VERSION


def record_errors(rec: Any, now: datetime | None = None) -> list[str]:
    """The schema, then what it cannot say. With `now`, a `checked_at` later than now fails. A record
    whose `schema_version` is newer than this reader's may carry keys its contract does not know."""
    errs = schema.schema_errors(rec, json.loads(SCHEMA.read_text()), newer=written_by_newer(rec))
    if not isinstance(rec, dict):
        return errs
    for i, c in enumerate(rec.get("checks") or []):
        if not isinstance(c, dict):
            continue
        name = f"checks[{i}] ({c.get('dod_check_id')})"
        if c.get("ran", True) is False:
            if c.get("pass") is not None:
                errs.append(f"{name}: a check the verifier did not run is neither a pass nor a fail: pass is null")
            if not c.get("rests_on"):
                errs.append(f"{name}: a check the verifier did not run names what it rests on (rests_on), in one of "
                            "the three forms of §15.4")
        elif c.get("pass") is None:
            errs.append(f"{name}: pass is null, so ran is false and rests_on says what it rests on")
    checked = schema.parse_dt(rec.get("checked_at"))
    if now is not None and checked is not None and checked > now + SKEW:
        errs.append(f"checked_at {rec.get('checked_at')} is later than now ({_iso(now)}): "
                    "it is the clock time the verdict was reached")
    return errs


# §2.3: the seats that rule on a task. Evidence either produced is refused unless it came from an
# operator step the operator approved (an approved `operator` gate of the task, §17.9).
RULING_SEATS = ("lead", "runner")


def _operator_step_refusal(queue: Path, task_id: str, step: str) -> str | None:
    """Why `step` is not an approved operator step of `task_id`, or None when it is: the gate file
    `escalations/<task_id>/<n>.json` (§17.9) names this task and step, is closed, approved and of
    class `operator`."""
    prefix = f"{task_id}-"
    n = step[len(prefix):] if step.startswith(prefix) else ""
    if not n.isdigit() or not SAFE_ID_RE.match(task_id):
        return f"operator_step {step!r} is not a gate of this task ({task_id}-<n>)"
    path = queue / "escalations" / task_id / f"{n}.json"
    try:
        gate = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return f"operator_step {step!r}: no gate file escalations/{task_id}/{n}.json"
    if not isinstance(gate, dict):
        return f"operator_step {step!r}: the gate file is not an object"
    if gate.get("task_id") != task_id or gate.get("escalation_id") != step:
        return (f"operator_step {step!r}: the gate file names task {gate.get('task_id')!r} and step "
                f"{gate.get('escalation_id')!r}, not this task and step")
    if gate.get("class") != "operator":
        return f"operator_step {step!r} is a {gate.get('class')!r} gate, not an operator step"
    if gate.get("status") != "closed" or gate.get("decision") != "approved":
        return f"operator_step {step!r} is not approved (status {gate.get('status')!r}, decision {gate.get('decision')!r})"
    return None


# What a check not run (`ran: false`) may rest on (§15.4): a ruling named by its ids (a gate
# `<task_id>-<n>`, a spec question `sm-…`), a carried verdict `approve at <sha>` (§15.6 rule 3), or,
# for evidence the operator produced, any text.
_GATE_TOKEN = re.compile(rf"(?<![\w-])({ANY_TASK_ID})-([0-9]+)(?![\w-])")
_QUESTION_TOKEN = re.compile(rf"(?<![\w-]){QUESTION_ID}(?![\w-])")
_RULING_TOKEN = re.compile(rf"(?<![\w-])({ANY_TASK_ID})-r([0-9]+)(?![\w-])")  # a lead ruling id (§17.5)
_APPROVE_AT = re.compile(r"approve at ([0-9a-fA-F]{7,40})")
_REST_FORMS = ("a ruling, named by its spec question id (sm-…), gate id (<task_id>-<n>) or lead ruling id "
               "(<task_id>-r<n>), each of which exists, each gate closed and approved and each question answered "
               "resolved; a carried verdict, "
               "`approve at <sha>` (§15.6 rule 3), the sha a commit; or evidence the operator produced "
               "(produced_by: operator)")


def carried_from(rests_on: Any) -> str | None:
    """The sha a check not run carries its verdict from (`rests_on` exactly `approve at <sha>`, §15.6
    rule 3), as written; None for any other `rests_on`."""
    m = _APPROVE_AT.fullmatch(rests_on.strip()) if isinstance(rests_on, str) else None
    return m.group(1) if m else None


def _lead_rulings(queue: Path, task_id: str) -> list[dict[str, Any]]:
    """§17.5: the lead rulings the ledger holds on the task (`queue.rulings`); none when the ledger cannot be read."""
    from ccp.queue import rulings  # noqa: PLC0415
    try:
        return rulings(queue, task_id)
    except (OSError, ValueError):
        return []


def _ruling_refusal(queue: Path, rests_on: str) -> str | None:
    """Why `rests_on` is not a ruling the queue holds, or None when it is: it names at least one gate
    id `<task_id>-<n>`, spec question id `sm-…` or lead ruling id `<task_id>-r<n>`, and every one it names
    exists and was ruled (a lead ruling id: the ledger holds its `ruling` `recorded` event, §17.5; the
    gate file `escalations/<task_id>/<n>.json`, §17.9, is the gate it is cited as, its `escalation_id`
    and `task_id` those of the cited id, of any task, closed and approved; the question file
    `questions/<id>.json` with its answer `questions/<id>.answer.json` at verdict `resolved`, §17.5:
    an answer without its question is no ruling). The ids may sit inside prose; an unknown or unruled one beside a ruled one is refused."""
    missing, misfiled, open_, unanswered = [], [], [], []
    gates = list(_GATE_TOKEN.finditer(rests_on))
    questions = list(_QUESTION_TOKEN.finditer(rests_on))
    lead = list(_RULING_TOKEN.finditer(rests_on))
    if not gates and not questions and not lead:
        return "it names no ruling id"
    recorded = {str(r.get("id")) for t in {m.group(1) for m in lead} for r in _lead_rulings(queue, t)}
    for m in gates:
        try:
            gate = json.loads((queue / "escalations" / m.group(1) / f"{m.group(2)}.json").read_text())
        except (OSError, json.JSONDecodeError):
            missing.append(m.group(0))
            continue
        if isinstance(gate, dict) and (gate.get("task_id") != m.group(1) or gate.get("escalation_id") != m.group(0)):
            misfiled.append(f"{m.group(0)} (its file names task {gate.get('task_id')!r}, "
                            f"gate {gate.get('escalation_id')!r})")
        elif not isinstance(gate, dict) or gate.get("status") != "closed" or gate.get("decision") != "approved":
            open_.append(m.group(0))
    unknown = [m.group(0) for m in lead if m.group(0) not in recorded]
    for m in questions:
        if not (queue / "questions" / f"{m.group(0)}.json").is_file():
            missing.append(m.group(0))
            continue
        try:
            answer = json.loads((queue / "questions" / f"{m.group(0)}.answer.json").read_text())
        except (OSError, json.JSONDecodeError):
            answer = None
        if not isinstance(answer, dict) or answer.get("verdict") != "resolved":
            unanswered.append(m.group(0))
    why = ([f"no gate or spec question {', '.join(missing)} is in the queue"] if missing else []) \
        + ([f"no lead ruling {', '.join(unknown)} is recorded in the ledger (ccp tasks ruling)"] if unknown else []) \
        + ([f"gate {', '.join(misfiled)} is not filed as itself"] if misfiled else []) \
        + ([f"gate {', '.join(open_)} is not closed and approved"] if open_ else []) \
        + ([f"spec question {', '.join(unanswered)} has no answer at verdict resolved"] if unanswered else [])
    return "; ".join(why) or None


def _commit_refusal(root: Path, sha: str) -> str | None:
    """Why `sha` does not resolve to a commit in the product checkout, or None when it does."""
    if _git(root, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}").returncode == 0:
        return None
    return f"{sha} does not resolve to a commit in the product checkout"


def rests_on_errors(root: Path, queue: Path, rec: dict[str, Any]) -> list[str]:
    """§15.4, as `record` writes it: a check not run (`ran: false`) rests on one of three things, and
    anything else is refused, naming the check. A ruling: `rests_on` names spec question, gate or lead ruling ids
    that all exist, each gate closed and approved and each question answered `resolved`
    (`_ruling_refusal`). A carried verdict: `rests_on`
    is exactly `approve at <sha>` (§15.6 rule 3), the sha a commit of the product checkout. Evidence
    the operator produced: `produced_by: operator`, with any `rests_on`. An empty `rests_on` is the
    contract's to refuse."""
    errs: list[str] = []
    for i, c in enumerate(rec.get("checks") or []):
        if not isinstance(c, dict) or c.get("ran", True) is not False or not isinstance(c.get("rests_on"), str) \
                or not c["rests_on"]:
            continue
        text, seat = c["rests_on"], c.get("produced_by")
        ruling = _ruling_refusal(queue, text)
        if ruling is None:
            continue
        name = f"checks[{i}] ({c.get('dod_check_id')}): rests_on {text[:60]!r}"
        if seat == "operator":
            continue
        carried = _APPROVE_AT.fullmatch(text.strip())
        if carried and (bad := _commit_refusal(root, carried.group(1))) is None:
            continue
        detail = bad if carried else ruling
        errs.append(f"{name} is none of the forms a check not run rests on ({detail}): {_REST_FORMS} (§15.4)")
    return errs


def as_written_errors(queue: Path, rec: dict[str, Any]) -> list[str]:
    """§15.4, as `record` writes it: a check marked `as_written: false` is one the verifier ran (never
    `ran: false`), with `held_instead`, what it checked in place of the expectation as written, and
    `ruling`, which names spec question, gate or lead ruling ids that all exist and were ruled (`_ruling_refusal`).
    Each refusal names the check and what is missing."""
    errs: list[str] = []
    for i, c in enumerate(rec.get("checks") or []):
        if not isinstance(c, dict) or c.get("as_written", True) is not False:
            continue
        name = f"checks[{i}] ({c.get('dod_check_id')}): as_written is false"
        if c.get("ran", True) is False:
            errs.append(f"{name} on a check not run (ran: false): not as written is for a check the verifier ran; "
                        "a check not run rests on rests_on (§15.4)")
        if not (isinstance(c.get("held_instead"), str) and c["held_instead"].strip()):
            errs.append(f"{name} with no held_instead: say what the verifier checked in its place (§15.4)")
        ruling = c.get("ruling")
        if not (isinstance(ruling, str) and ruling.strip()):
            errs.append(f"{name} with no ruling: name the spec question (sm-…), gate (<task_id>-<n>) or lead "
                        "ruling (<task_id>-r<n>) ids that let it (§15.4)")
        elif (why := _ruling_refusal(queue, ruling)) is not None:
            errs.append(f"{name} and its ruling {ruling[:60]!r} is not a ruling the queue holds ({why}): it names "
                        "spec question, gate or lead ruling ids that all exist, each gate closed and approved and "
                        "each question answered resolved (§15.4)")
    return errs


def not_as_written(rec: Any) -> list[dict[str, str]]:
    """§15.4: the checks a record marks `as_written: false`, each as its `dod_check_id`, `held_instead` and
    `ruling`, in the record's order: what `ccp tasks close` prints before it merges. [] for a record
    without any, or written before the field."""
    checks = rec.get("checks") if isinstance(rec, dict) else None
    return [{"dod_check_id": str(c.get("dod_check_id")), "held_instead": str(c.get("held_instead") or ""),
             "ruling": str(c.get("ruling") or "")}
            for c in checks or [] if isinstance(c, dict) and c.get("as_written", True) is False]


def producer_errors(queue: Path, rec: dict[str, Any], require: bool = True) -> list[str]:
    """§2.3, §15.4: each check names the seat that produced its evidence (`produced_by`; with
    `require`, a check without one is refused, as `record` writes it, unless a ruling closed it:
    `ran: false` and `rests_on` set, which `rests_on_errors` holds to its forms; a record written
    before the field is read without it), and none was produced by a seat that rules on the task
    unless its `operator_step` names an approved operator gate of the task. A named `operator_step`
    must be one."""
    errs: list[str] = []
    task_id = str(rec.get("task_id") or "")
    for i, c in enumerate(rec.get("checks") or []):
        if not isinstance(c, dict):
            continue
        name = f"checks[{i}] ({c.get('dod_check_id')})"
        seat, step = c.get("produced_by"), c.get("operator_step")
        why = _operator_step_refusal(queue, task_id, step) if isinstance(step, str) and step else None
        if seat is None:
            # A ruling is not evidence: a check the ruling closed (`ran: false`, `rests_on` naming
            # it, ADR-0035 D7) with no evidence under it names no producer.
            ruled = c.get("ran", True) is False and bool(c.get("rests_on"))
            if require and not ruled:
                errs.append(f"{name}: names no produced_by, the seat that produced its evidence (§15.4); only "
                            "a check closed by a ruling (ran: false, rests_on naming it) may leave it out")
            if why:
                errs.append(f"{name}: {why}")
            continue
        if seat in RULING_SEATS and not step:
            errs.append(f"{name}: its evidence was produced by the {seat}, a seat that rules on the task: the seat "
                        "that rules never produces the evidence it rules on (§2.3), unless it is an operator step "
                        "the operator approved (operator_step: the approved gate's id)")
        elif why:
            errs.append(f"{name}: produced by the {seat}: {why}")
    return errs


def _gate_runs(rec: dict[str, Any]) -> list[Any]:
    gate = rec.get("gate")
    return (gate.get("runs") or []) if isinstance(gate, dict) else []


def approve_errors(rec: dict[str, Any]) -> list[str]:
    """Why an `approve` is not one: a check it ran failed, it names no head, or it carries no
    passing gate. Nothing for another verdict."""
    if rec.get("verdict") != "approve":
        return []
    errs = []
    failed = [str(c.get("dod_check_id")) for c in rec.get("checks") or []
              if isinstance(c, dict) and c.get("ran", True) is not False and c.get("pass") is False]
    if failed:
        errs.append(f"an approve with a failed check ({', '.join(failed)}): a check that failed is a reject")
    if not str(rec.get("head_sha") or "").strip():
        errs.append("the record names no head_sha: an approval is of one head")
    runs = _gate_runs(rec)
    if not runs:
        errs.append("the record carries no gate: the verifier's own unit and lint runs at the head (§15.3)")
    for r in runs:
        if isinstance(r, dict) and r.get("exit_code") != 0:
            errs.append(f"gate run {r.get('command')!r} exited {r.get('exit_code')}")
    return errs


# A gate run that names a recorded `ccp suite run` (§14.1) takes these from it, where it does not say them.
GATE_FROM_SUITE = {"exit_code": "exit_code", "tests_run": "tests", "tests_skipped": "skipped", "seconds": "seconds",
                   "ran": "ran", "cached": "cached"}


def gate_counts(r: dict[str, Any]) -> tuple[Any, Any]:
    """A gate run's units ran and cached; a run recorded before the gate-result contract names them
    `modules_ran` and `modules_cached`."""
    return (r["ran"] if "ran" in r else r.get("modules_ran"), r["cached"] if "cached" in r else r.get("modules_cached"))


def _latest_verify(queue: Path, task_id: str) -> str:
    """The task's latest verify run id, or "" when it has none."""
    from ccp import runs  # noqa: PLC0415
    try:
        found = [r for r in runs.all_runs(queue, task_id) if r.get("phase") == "verify"]
    except Exception:  # noqa: BLE001
        return ""
    return str(max(found, key=lambda r: runs.parse_id(str(r["run_id"]))[2])["run_id"]) if found else ""


def fill_gate(queue: Path, rec: dict[str, Any]) -> list[str]:
    """§14.1: each `gate.runs` entry with a `suite_id` is filled from that recorded suite run: its
    exit code, tests, skips, seconds and units ran and cached, and a `command` naming it when the
    entry has none; an entry that does not say `cold` takes the record's `cold` when it is `true` (§14.6:
    the run's own count showed nothing cached) and the entry's `cached` is 0, so the verdict and the suite
    record agree. A number the entry gives itself stays; an exit code that differs from the
    recorded one is refused. The suite run must be recorded, ended, and bound to this task's latest
    verify run: an unbound run, another phase's, or an earlier verify round's (an older head) is refused."""
    gate = rec.get("gate")
    entries = [r for r in (gate.get("runs") or []) if isinstance(r, dict) and r.get("suite_id")] \
        if isinstance(gate, dict) and isinstance(gate.get("runs"), list) else []
    if not entries:
        return []
    from ccp import suite  # noqa: PLC0415
    try:
        rows = {r.get("suite_id"): r for r in suite.fold(queue)}
    except Exception:  # noqa: BLE001
        rows = {}
    errs = []
    latest: str | None = None
    for e in entries:
        sid = str(e["suite_id"])
        row = rows.get(sid)
        if row is None:
            errs.append(f"gate run suite_id {sid}: no such suite run is recorded (ccp suite list)")
            continue
        if row.get("state") not in ("passed", "failed", "interrupted"):
            errs.append(f"gate run suite_id {sid}: that suite run has not ended ({row.get('state')})")
            continue
        bound = str(row.get("run_id") or "")
        if not bound:
            errs.append(f"gate run suite_id {sid}: that suite run is bound to no run; a gate is run with "
                        f"`ccp suite run --run <your verify run>`")
            continue
        if row.get("task_id") != rec.get("task_id") or row.get("phase") != "verify":
            errs.append(f"gate run suite_id {sid}: that suite run is {bound}'s, not a verify run of {rec.get('task_id')}")
            continue
        if latest is None:
            latest = _latest_verify(queue, str(rec.get("task_id") or ""))
        if bound != latest:
            errs.append(f"gate run suite_id {sid}: that suite run is {bound}'s, an earlier verify round; "
                        f"{rec.get('task_id')}'s latest verify run is {latest or 'unknown'}: cite a gate run of it")
            continue
        if "exit_code" in e and e["exit_code"] != row.get("exit_code"):
            errs.append(f"gate run suite_id {sid}: exit_code {e['exit_code']} differs from the recorded {row.get('exit_code')}")
            continue
        for key, src in GATE_FROM_SUITE.items():
            if key not in e and row.get(src) is not None:
                e[key] = row[src]
        if "cold" not in e and row.get("cold") is True and gate_counts(e)[1] == 0:
            e["cold"] = True  # §15.3: the suite record's own `cold` (§14.6), never only the `--cold` ask
        e.setdefault("command", f"ccp suite run --lane {row.get('lane') or '-'} -- {row.get('cmd') or '?'} "
                                f"({row.get('argc', 0)} args)")
    return errs


def cache_rule(cfg: Config) -> dict[str, Any] | None:
    """plane.json `verify.accept_cache`, or None when the product does not accept cache hits."""
    return (cfg.verify or {}).get("accept_cache") or None


def cold_gate(cfg: Config, meta: dict[str, Any]) -> bool:
    """Whether this task's gate runs cold under the product's cache rule: its frontmatter says
    `gate: cold`, or its id matches one of `cold_tasks` (a rollout, say). False without the rule."""
    rule = cache_rule(cfg)
    if not rule:
        return False
    tid = str(meta.get("task_id") or "")
    return str(meta.get("gate") or "").strip().lower() == "cold" or any(fnmatchcase(tid, g) for g in rule["cold_tasks"])


def cache_errors(cfg: Config, rec: dict[str, Any]) -> list[str]:
    """Under `verify.accept_cache`, why an approve's gate does not say what the cache did: no run
    gives its units ran and cached, or a cold-gate task's run was warm. Nothing otherwise."""
    if not cache_rule(cfg) or rec.get("verdict") != "approve":
        return []
    counted = [r for r in _gate_runs(rec) if isinstance(r, dict) and None not in gate_counts(r)]
    if not counted:
        return ["the product accepts its test cache's hits (plane.json verify.accept_cache): the gate run of the "
                "suite gives ran and cached (the gate's result file, or its output's counts, §14.1)"]
    from ccp.queue import QueueError, task_meta  # noqa: PLC0415
    tid = str(rec.get("task_id") or "")
    if tid.startswith("pr-"):
        return []
    try:
        meta = task_meta(cfg, tid)
    except QueueError:
        return []
    cold = [r for r in counted if not gate_counts(r)[1] and r.get("cold") is True]
    if cold_gate(cfg, meta) and not cold:  # a warm run beside a cold one is fine; a cold one is required
        return [f"{tid}'s gate is cold (gate: cold, or verify.accept_cache.cold_tasks): a gate run of the suite "
                "is cold (`cold: true`) with nothing cached"]
    return []


def review_errors(queue: Path, rec: dict[str, Any]) -> list[str]:
    """§15.2, belt and braces to `ccp prompt verify`: an approve of a head with a fix round after the
    task's last review (or commits after the head it judged) is refused, unless the task's open verify
    run carries the override `ccp prompt verify --allow-unreviewed-fix --reason` recorded. Nothing for a
    reject, or for a PR that is not a task's."""
    from ccp import runs  # noqa: PLC0415
    from ccp.queue import QueueError  # noqa: PLC0415

    tid = str(rec.get("task_id") or "")
    if rec.get("verdict") != "approve" or not tid or tid.startswith("pr-"):
        return []
    try:
        why = runs.unreviewed_fix(queue, tid, str(rec.get("head_sha") or "").strip() or None)
        run = runs.latest_open(queue, tid, "verify") if why else None
    except QueueError:
        return []
    if why is None or (run is not None and run.get("allow_unreviewed_fix")):
        return []
    skipped = (run or {}).get("review_skip") or {}
    judged = str(rec.get("head_sha") or "").strip()
    if skipped and heads_match(str(skipped.get("head") or ""), judged):
        return []  # §15.2: this verify run's head is a fix the product's proof (verify.skip_review) or a prover proved
    if skipped.get("reason") == "minor-only" and heads_match(str((run or {}).get("head") or ""), judged):
        return []  # §15.2: this verify run's head is a fix of a clean review's minor findings (skip_review_after_clean)
    return [f"{why}; an approve stands only when `ccp prompt verify --allow-unreviewed-fix --reason` recorded "
            "the override on this verify run, or verify.skip_review proved this head's fix, or a verify.provers prover did, "
            "or verify.skip_review_after_clean took it as a fix of a clean review's minor findings"]


def resolution_errors(queue: Path, rec: dict[str, Any]) -> list[str]:
    """§15.6 rule 3: an approve at the head a contained resolution review judged (it is the task's latest review
    that reported done) leaves none of the checks that review named in `Affected checks` unrun: each is in the
    record and not `ran: false`. Nothing for a reject, or for a PR that is not a task's."""
    from ccp import runs  # noqa: PLC0415
    from ccp.queue import QueueError  # noqa: PLC0415

    tid = str(rec.get("task_id") or "")
    if rec.get("verdict") != "approve" or not tid or tid.startswith("pr-"):
        return []
    try:
        done = [r for r in runs.all_runs(queue, tid) if r.get("phase") == "review" and runs.state(r) == "reported"
                and r.get("outcome") == "done"]
    except QueueError:
        return []
    last = done[-1] if done else None
    if not last or last.get("mode") != "resolution" or last.get("resolution") != "contained" \
            or not heads_match(str(last.get("head") or ""), str(rec.get("head_sha") or "").strip()):
        return []
    got = {str(c.get("dod_check_id")): c for c in rec.get("checks") or [] if isinstance(c, dict)}
    unrun = [i for i in last.get("affected_checks") or [] if i not in got or got[i].get("ran") is False]
    if not unrun:
        return []
    return [f"the resolution review {last['run_id']} named {', '.join(unrun)} in `Affected checks`: an approve at "
            f"{str(rec.get('head_sha'))[:12]} reruns every check it names, and {', '.join(unrun)} "
            f"{'is' if len(unrun) == 1 else 'are'} missing from the record or recorded `ran: false` (SPEC §15.6 rule 3)"]


def adr_errors(cfg: Config, rec: dict[str, Any]) -> list[str]:
    """§6.7 before the verdict (§15.4): an approve of a head on which a decision the task cites is still
    recorded `not_built` is refused under `adr.strict`, since closing the task would turn the integration
    branch red (`adr.in_force_at`). Nothing for a reject, or for a PR that is not a task's."""
    from ccp import adr  # noqa: PLC0415
    from ccp.queue import QueueError, task_meta  # noqa: PLC0415

    tid = str(rec.get("task_id") or "")
    if rec.get("verdict") != "approve" or not tid or tid.startswith("pr-") or cfg.adr is None:
        return []
    try:
        meta = task_meta(cfg, tid)
    except QueueError:
        return []
    return adr.in_force_at(cfg, meta, str(rec.get("head_sha") or ""))


def _run_refusal(sid: Any, cid: str, tid: str, suites: list[dict[str, Any]], head: str | None) -> str | None:
    """§15.4, ADR-0045 D3: why `sid` is not a passed suite run of the lane `cid`, bound to `tid`, recorded at
    `head` (§14.4's `head`; None: at any head, for a pass a verdict carried), or None when it is."""
    if not isinstance(sid, str) or not sid.strip():
        return "it names no suite_id, the runner's passed run of the check"
    row = next((s for s in suites if s.get("suite_id") == sid), None)
    if row is None:
        return f"its suite_id {sid} is not a recorded suite run (ccp suite list)"
    if row.get("lane") != cid or row.get("task_id") != tid:
        return f"its suite run {sid} ran lane {row.get('lane')!r} for {row.get('task_id') or 'no task'}, not lane {cid} for {tid}"
    if row.get("state") != "passed":
        return f"its suite run {sid} did not pass ({row.get('state')})"
    if head is not None and not heads_match(str(row.get("head") or ""), head):
        ran = str(row.get("head") or "")
        return f"its suite run {sid} ran at {ran[:12] or 'no recorded head'}, not at {head[:12]}"
    return None


def _carry_refusal(cid: str, old: str, tid: str, verifies: list[dict[str, Any]], suites: list[dict[str, Any]],
                   steps: set[str]) -> str | None:
    """§15.6 rule 3, ADR-0045 D3: why a marked check may not rest on `approve at <old>`, or None when it may: the
    task's latest verify run that recorded an approve at `old` kept facts for the check (`runs.check_facts`) that
    hold it as a pass with an approved `operator_step` and a passed run of its lane at `old`, or as a carry of
    such a pass (not run, the pass's `operator_step` and `suite_id` kept)."""
    at = [r for r in verifies if r.get("verdict") == "approve" and heads_match(str(r.get("head") or ""), old)]
    if not at:
        return f"no verify run of {tid} recorded an approve at {old[:12]}"
    run = at[-1]
    facts = run.get("checks")
    fact = next((f for f in facts if isinstance(f, dict) and f.get("id") == cid), None) \
        if isinstance(facts, list) else None
    if fact is None:
        return f"the verify run {run.get('run_id')} at {old[:12]} kept no facts for it"
    step = fact.get("operator_step")
    if fact.get("ran", True) is not False and fact.get("pass") is not True:
        return f"the verify run {run.get('run_id')} at {old[:12]} did not hold it as a pass"
    if step not in steps:
        return f"the verify run {run.get('run_id')} at {old[:12]} kept no approved operator_step for it"
    why = _run_refusal(fact.get("suite_id"), cid, tid, suites, old if fact.get("ran", True) is not False else None)
    return f"at {old[:12]}: {why}" if why else None


def marked_errors(rec: dict[str, Any], marked: list[str], suites: list[dict[str, Any]],
                  verifies: list[dict[str, Any]], steps: set[str], rulings: set[str]) -> list[str]:
    """§15.4, §15.6 rule 3, ADR-0045 D3, on plain values: why an approve does not hold each check `marked` `runs_on:
    operator-machine` (its task file's, at the head) to a result, one line per refusal, naming the check. A marked
    check is refused when it is missing from the record; when it was run and names no `operator_step` in `steps`
    (the approved operator gates of the task), whoever produced it, or no `suite_id` of a passed run in `suites`
    (`suite.fold`'s rows) of its lane, bound to the task, at the record's `head_sha`; when it is `ran: false` on a
    `rests_on` that is neither a ruling (`rulings`, the texts `_ruling_refusal` accepts that name more than operator
    gates, `_waiver_texts`) nor a carried verdict, or on any `rests_on` of evidence the operator produced; and
    when it carries `approve at <old>` that the task's verify runs (`verifies`, oldest first) do not hold as a
    pass it may carry (`_carry_refusal`). A failed check is `approve_errors`' to refuse, and a waived one passes."""
    tid, head = str(rec.get("task_id") or ""), str(rec.get("head_sha") or "").strip()
    got: dict[str, dict[str, Any]] = {}
    for c in rec.get("checks") or []:
        if isinstance(c, dict):
            got.setdefault(str(c.get("dod_check_id")), c)
    errs: list[str] = []
    for cid in marked:
        name = f"the check {cid}, marked `runs_on: operator-machine`,"
        c = got.get(cid)
        if c is None:
            errs.append(f"{name} is missing from the record: an approve holds it to its result, a verdict it carries "
                        "or a ruling that waives it (SPEC §15.4)")
            continue
        if c.get("ran", True) is False:
            rests = str(c.get("rests_on") or "").strip()
            old = carried_from(rests)
            if old is not None:
                if (why := _carry_refusal(cid, old, tid, verifies, suites, steps)) is not None:
                    errs.append(f"{name} carries a verdict it may not carry ({why}): run it again at the head "
                                "(SPEC §15.6 rule 3, §15.8)")
            elif c.get("produced_by") == "operator" or rests not in rulings:
                what = "evidence the operator produced, never a ruling" if c.get("produced_by") == "operator" \
                    else "no ruling that waives it"
                errs.append(f"{name} is ran: false on {rests[:60]!r}, {what}: free-text operator evidence is never its "
                            "evidence; it rests on a passed run at the head, a verdict it may carry or a ruling that "
                            "waives it (SPEC §15.4)")
            continue
        if c.get("pass") is False:
            continue
        step = c.get("operator_step")
        if step not in steps:
            errs.append(f"{name} names no approved operator_step: its evidence, whoever produced it, comes from the "
                        "task's approved operator gate or a standing approval (SPEC §15.4)")
        if (why := _run_refusal(c.get("suite_id"), cid, tid, suites, head)) is not None:
            errs.append(f"{name} was run, and {why}: it cites a passed run of its lane, bound to the task, recorded at "
                        f"the record's head {head[:12]} (SPEC §15.4)")
    return errs


def marked_refusals(cfg: Config, queue: Path, rec: dict[str, Any], head: str) -> list[str]:
    """§15.4, ADR-0045 D3: `marked_errors` for an approve of a task, with the checks marked `runs_on:
    operator-machine` read from its task file at `head` (`tasklog.text_at`), never the checkout's, and the facts
    from the queue. A task file the head does not hold here is refused when the checkout's copy marks a check,
    and passes otherwise. Nothing for a reject or a PR that is not a task's."""
    from ccp import runs, suite, tasklog  # noqa: PLC0415

    tid = str(rec.get("task_id") or "")
    if rec.get("verdict") != "approve" or not SAFE_ID_RE.match(tid) or tid.startswith("pr-"):
        return []
    path = cfg.tasks_dir / f"{tid}.md"
    text = tasklog.text_at(cfg, head.strip(), cfg.rel(path)) if head.strip() else None
    if text is None:
        local = path.read_text(errors="replace") if path.is_file() else ""
        mine = [c.id for c in tasklog.checks(local) if c.on_operator_machine]
        return [f"{tid}'s task file in this checkout marks {', '.join(mine)} `runs_on: operator-machine`, and its file "
                f"at the head {head.strip()[:12] or '(none)'} cannot be read here (git fetch the head): the marked "
                "checks are read from the task file at the head (SPEC §15.4)"] if mine else []
    marked = [c.id for c in tasklog.checks(text) if c.on_operator_machine]
    if not marked:
        return []
    try:
        suites = suite.fold(queue)
    except Exception:  # noqa: BLE001
        suites = []
    try:
        verifies = [r for r in runs.all_runs(queue, tid) if r.get("phase") == "verify"]
    except Exception:  # noqa: BLE001
        verifies = []
    named = {str(c.get("operator_step")) for c in rec.get("checks") or [] if isinstance(c, dict) and c.get("operator_step")}
    named |= {str(f.get("operator_step")) for r in verifies for f in r.get("checks") or []
              if isinstance(f, dict) and f.get("operator_step")}
    steps = {s for s in named if _operator_step_refusal(queue, tid, s) is None}
    return marked_errors(rec, marked, suites, verifies, steps, _waiver_texts(queue, rec))


def _waiver_texts(queue: Path, rec: dict[str, Any]) -> set[str]:
    """The `rests_on` texts of `rec`'s checks that may waive a marked check (ADR-0045 D3): a ruling the queue holds
    (`_ruling_refusal`) naming at least one id that is not a gate of class `operator`. An operator gate approves
    running a step, never skipping it, so a text whose only ids are operator gates waives nothing."""
    def waives(text: str) -> bool:
        if _ruling_refusal(queue, text) is not None:
            return False
        if _QUESTION_TOKEN.search(text) or _RULING_TOKEN.search(text):
            return True
        for m in _GATE_TOKEN.finditer(text):
            try:
                gate = json.loads((queue / "escalations" / m.group(1) / f"{m.group(2)}.json").read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(gate, dict) and gate.get("class") != "operator":
                return True
        return False

    return {str(c["rests_on"]).strip() for c in rec.get("checks") or []
            if isinstance(c, dict) and isinstance(c.get("rests_on"), str) and c["rests_on"].strip()
            and waives(c["rests_on"])}


PROOF_TIMEOUT = 600  # seconds a proof (verify.skip_review.proof, a verify.provers command) may take; a timeout proves nothing


def review_provers(found: dict[str, Any]) -> list[dict[str, Any]]:
    """The declared provers of the review in a `verify` block (§15.2, `verify.provers` whose `skips` is
    `review`), in their order."""
    from ccp.config import PROVER_REVIEW  # noqa: PLC0415

    return [p for p in found.get("provers") or [] if p.get("skips") == PROVER_REVIEW]


def review_proof_label(found: dict[str, Any]) -> str:
    """What proves a fix round, for `ccp prompt verify`'s refusal: the settings a `verify` block has on."""
    names = (["verify.skip_review"] if found.get("skip_review") else []) \
        + (["verify.provers"] if review_provers(found) else [])
    return " and ".join(names) or "verify.skip_review"


def skip_review(cfg: Config, queue: Path, task_id: str, head: str, pr: str | None) -> tuple[dict[str, Any] | None, str]:
    """§15.2: may a verify of `head` skip the review of the task's latest fix round? Only with plane.json
    `verify.skip_review` set, or a `verify.provers` entry that skips `review`, both read from plane.json on
    `origin/<integration branch>` once `origin` is fetched (never from the checkout or the head under test,
    so a rule the task adds or changes in its own diff does not apply to it; a failed fetch, or a plane.json
    there that does not load, reads none, and the refusal says so), a fix run (not abandoned; a
    merge or ruling round counts as one, §13.2) opened since the last review that reported done, and that
    review's head on record. The fix diff runs from the reviewed change carried onto the head's
    base on the integration branch (`gitmerge.probe` of the reviewed head and that base, which must merge
    cleanly) to the head, so an integration merge in between is not counted as the fix's. It must touch
    at least one file. `verify.skip_review` proves it when the diff touches only files under `paths` (git
    pathspecs, as `merge.behind_tip_ignore`) and the product's `proof` command exits 0; failing that, each
    review prover in turn proves it when its `command` exits 0. Either command runs in a clean checkout of
    the integration branch's tip, the commit the rules were read at (`suite.clean_checkout`, removed when
    the judgement ends), so nothing the task's diff changes alters its verdict, with `{task_id}`,
    `{reviewed}`, `{head}` and `{from}` (the tree the fix diff starts from) filled in. Returns what to
    record on the verify run (a prover's skip adds its `prover` name and `exit_code`, never its command
    text, §14.4), or None and why not, as "<the settings> does not apply: <why>" or "nothing is skipped:
    <why>" ("" when neither is set or there is no fix to judge).

    The probe needs git 2.38 or later. It reports a conflict; any other failure, such as an older git that
    lacks the option, is named as such, and the review stands either way."""
    from ccp import runs  # noqa: PLC0415
    from ccp.config import skip_rules_at  # noqa: PLC0415
    from ccp.queue import git, integration_branch  # noqa: PLC0415

    integ = integration_branch(queue)
    if git(cfg.root, "fetch", "-q", "origin").returncode != 0:
        return None, f"nothing is skipped: the fetch of origin/{integ} failed, so no skip rule was read"
    at = git(cfg.root, "rev-parse", "--verify", "-q", f"origin/{integ}^{{commit}}")
    tip = at.stdout.strip() if at.returncode == 0 else ""
    found, unread = skip_rules_at(cfg.root, tip, f"origin/{integ}") if tip else ({}, "")
    if unread:  # a plane.json that does not load there sets none
        return None, f"nothing is skipped: {unread}, so it sets no skip rule"
    rule = found.get("skip_review")
    provers = review_provers(found)
    if not rule and not provers:
        return None, ""
    label = review_proof_label(found)
    rs = [r for r in runs.all_runs(queue, task_id) if runs.state(r) != "abandoned"]
    fixes = [r for r in rs if r.get("phase") in runs.REWORK_PHASES]
    reviews = [r for r in rs if r.get("phase") == "review" and runs.state(r) == "reported" and r.get("outcome") == "done"]
    if not fixes or not reviews or str(reviews[-1].get("opened_at") or "") > str(fixes[-1].get("opened_at") or ""):
        return None, ""
    reviewed = str(reviews[-1].get("head") or "").strip()
    if not reviewed:
        return None, ""
    rec, why = _judge_fix(cfg, queue, task_id, reviewed, head, pr, str(fixes[-1]["run_id"]), rule, provers, integ,
                          tip)
    return rec, (f"{label} does not apply: {why}" if why else "")


def _judge_fix(cfg: Config, queue: Path, task_id: str, reviewed: str, head: str, pr: str | None, fix: str,
               rule: dict[str, Any] | None, provers: list[dict[str, Any]],
               integ: str, tip: str) -> tuple[dict[str, Any] | None, str]:
    """`skip_review`'s judgement of the fix diff by the rules read from the integration branch at `tip`,
    their commands run in a clean checkout of `tip`: what to record on the verify run, or None and why
    not."""
    from ccp import gitmerge  # noqa: PLC0415
    from ccp.queue import git  # noqa: PLC0415

    shas = []  # `skip_review` fetched origin
    for sha in (reviewed, head.strip()):
        if not prhost.fetch_commit(cfg, cfg.root, sha, pr, f"task/{task_id}"):
            return None, f"{sha[:12]} could not be fetched"
        r = git(cfg.root, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}")
        if r.returncode != 0:
            return None, f"{sha[:12]} could not be fetched"
        shas.append(r.stdout.strip())
    reviewed, head = shas
    base = git(cfg.root, "merge-base", head, f"origin/{integ}")
    if base.returncode != 0:
        return None, f"the head has no merge base with origin/{integ}"
    tree = gitmerge.probe(cfg.root, reviewed, base.stdout.strip())
    if tree.returncode not in (0, 1):
        return None, gitmerge.old_git_text(tree)
    if tree.returncode != 0 or not tree.tree:
        return None, f"the reviewed head does not merge cleanly onto the head's base on origin/{integ}"
    start = tree.tree
    touched = git(cfg.root, "diff", "--name-only", "--no-renames", start, head)  # a rename names both of its paths
    if touched.returncode != 0:
        return None, "the fix diff could not be read"
    files = [f for f in touched.stdout.split("\n") if f]
    if not files:
        return None, "the fix changes no file of its own"
    values = {"task_id": task_id, "reviewed": reviewed, "head": head, "from": start}
    skipped = {"reviewed": reviewed, "head": head, "fix": fix, "files": len(files)}
    with contextlib.ExitStack() as checkouts:  # the provers' checkout goes, on an error or a signal too
        return _prove_fix(cfg, rule, provers, values, skipped, start, head, tip, checkouts)


def _prove_fix(cfg: Config, rule: dict[str, Any] | None, provers: list[dict[str, Any]], values: dict[str, str],
               skipped: dict[str, Any], start: str, head: str, tip: str,
               checkouts: contextlib.ExitStack) -> tuple[dict[str, Any] | None, str]:
    """Run `verify.skip_review`'s proof (within its paths), then each review prover, in a clean checkout of
    the integration tip `tip`, made on first use and held by `checkouts`: what to record when one exits 0,
    or None and why none did."""
    from ccp import rules  # noqa: PLC0415
    from ccp.config import fill  # noqa: PLC0415
    from ccp.queue import git  # noqa: PLC0415
    from ccp.suite import clean_checkout  # noqa: PLC0415

    why: list[str] = []
    tree: list[Path | None] = []

    def prove(cmd: str) -> tuple[bool, int | None]:
        """(made, exit code) of `cmd` in the checkout; (False, None) when none could be made."""
        if not tree:
            tree.append(checkouts.enter_context(clean_checkout(cfg.root, tip)))
        if tree[0] is None:
            return False, None
        return True, rules.run_command(cfg, fill(cmd, values), PROOF_TIMEOUT, cwd=tree[0])[0]
    no_tree = f"no clean checkout of the integration tip {tip[:12]} could be made, so no proof ran"
    if rule:
        paths = [str(x) for x in rule["paths"]]
        outside = git(cfg.root, "diff", "--name-only", "--no-renames", start, head, "--", ".", *[f":!{x}" for x in paths])
        beyond = [f for f in outside.stdout.split("\n") if f] if outside.returncode == 0 else None
        if beyond is None:
            why.append("the fix diff could not be read")
        elif beyond:
            why.append(f"the fix touches {len(beyond)} file(s) outside verify.skip_review.paths "
                       f"({', '.join(beyond[:5])})")
        else:
            made, code = prove(str(rule["proof"]))
            if not made:
                return None, no_tree
            if code == 0:
                return skipped, ""
            why.append("the proof (verify.skip_review.proof) "
                       + (f"timed out after {PROOF_TIMEOUT}s" if code is None else f"exited {code}"))
    for p in provers:
        made, code = prove(str(p["command"]))
        if not made:
            return None, "; ".join(why + [no_tree])
        if code == 0:
            return {**skipped, "prover": str(p["name"]), "exit_code": 0}, ""
        why.append(f"the prover {p['name']} (verify.provers) "
                   + (f"timed out after {PROOF_TIMEOUT}s" if code is None else f"exited {code}"))
    return None, "; ".join(why)


MINOR_SEVERITIES = ("MINOR", "NIT")  # §15.2: the findings below MAJOR, as the review's Severity line counts them


def skip_after_clean(cfg: Config, queue: Path, task_id: str, head: str) -> tuple[dict[str, Any] | None, str]:
    """§15.2: may a verify of `head` skip the review of a fix round that answers only the minor findings
    of a clean review? Only with plane.json `verify.skip_review_after_clean` on, when the task's latest
    review run that reported done recorded no BLOCKER or MAJOR finding and at least one below them, the
    latest fix run (not abandoned; a merge or ruling round counts as one, §13.2) opened since reported
    `done` with its head, `head` is that head, and no verify run since the review rejected (a reject sends
    the task back to review). A second fix round since the review is judged the same way: only the latest
    counts. Returns what to record on the verify run, `{reason: "minor-only", review_run, reviewed, report,
    findings}`: the review, the head it judged, its report's path and its counts below MAJOR (the plane
    keeps no finding text), or None and why not ("" when the setting is off or there is no fix to judge)."""
    from ccp import runs  # noqa: PLC0415

    if not (cfg.verify or {}).get("skip_review_after_clean"):
        return None, ""
    rs = [r for r in runs.all_runs(queue, task_id) if runs.state(r) != "abandoned"]
    reviews = [r for r in rs if r.get("phase") == "review" and runs.state(r) == "reported" and r.get("outcome") == "done"]
    if not reviews:
        return None, ""
    last = reviews[-1]
    since = str(last.get("opened_at") or "")
    fixes = [r for r in rs if r.get("phase") in runs.REWORK_PHASES and str(r.get("opened_at") or "") >= since]
    if not fixes:
        return None, ""
    sev = last.get("severity")
    if not isinstance(sev, dict):
        return None, f"the last review {last['run_id']} recorded no Severity counts"
    above = {k: int(sev.get(k) or 0) for k in ("BLOCKER", "MAJOR")}
    if any(above.values()):
        return None, (f"the last review {last['run_id']} found " + ", ".join(f"{n} {k}" for k, n in above.items() if n))
    findings = {k: int(sev.get(k) or 0) for k in MINOR_SEVERITIES}
    if not any(findings.values()):
        return None, f"the last review {last['run_id']} found nothing for a fix round to answer"
    rejected = [r for r in rs if r.get("phase") == "verify" and r.get("verdict") == "reject"
                and str(r.get("opened_at") or "") >= since]
    if rejected:
        return None, f"{rejected[-1]['run_id']} rejected since the last review: the task goes back to review"
    fix = fixes[-1]
    fixed = str(fix.get("head") or "").strip()
    if runs.state(fix) != "reported" or not fixed:
        return None, f"{fix['run_id']} has reported no head"
    if fix.get("outcome") != "done":
        return None, f"{fix['run_id']} reported `{fix.get('outcome')}`, not done"
    if not heads_match(fixed, head.strip()):
        return None, f"head {head.strip()[:12]} is not {fixed[:12]}, the head {fix['run_id']} reported"
    return {"reason": "minor-only", "review_run": str(last["run_id"]), "reviewed": str(last.get("head") or ""),
            "report": str(runs.report_path(queue, str(last["run_id"]))), "findings": findings}, ""


def repeat_round(queue: Path, task_id: str) -> str | None:
    """§15.6 rule 4: the task's latest verify run that reported, when no fix run (not abandoned) opened
    since it, a merge or ruling round counting as one (§13.2); None otherwise. A verify run that never reported (abandoned, or still open) was no round.
    A tie (one second) counts the fix as newer: a fix opens only once a report exists to fix from."""
    from ccp import runs  # noqa: PLC0415

    rs = [r for r in runs.all_runs(queue, task_id) if runs.state(r) != "abandoned"]
    done = [r for r in rs if r.get("phase") == "verify" and runs.state(r) == "reported"]
    if not done:
        return None
    last = done[-1]
    since = str(last.get("opened_at") or "")
    if any(r.get("phase") in runs.REWORK_PHASES and str(r.get("opened_at") or "") >= since for r in rs):
        return None
    return str(last["run_id"])


REPEAT_PREFIX = "repeat verify round, no fix round since "  # §15.6 rule 4: how fill_reason's line starts


def fill_reason(queue: Path, rec: dict[str, Any]) -> None:
    """§15.6 rule 4: a verify round opened with no fix round since the last (`repeat_verify` on the
    task's open verify run) says why in the record's `findings`, from the runner's `--note`. The note
    is added unless a finding already gives it: the note itself, or a line the note was added as
    (`REPEAT_PREFIX`, then `: <note>` at its end). A finding that only contains it is not one ("rerun"
    inside "flaky gate, rerun"), nor is another statement that ends `: <note>`. A record with no such
    run is left as it is."""
    from ccp import runs  # noqa: PLC0415
    from ccp.queue import QueueError  # noqa: PLC0415

    tid = str(rec.get("task_id") or "")
    if not tid or tid.startswith("pr-"):
        return
    try:
        run = runs.latest_open(queue, tid, "verify")
    except QueueError:
        return
    note = str((run or {}).get("note") or "").strip()
    repeat = (run or {}).get("repeat_verify")
    if not repeat or not note:
        return
    findings = rec.setdefault("findings", [])
    if not isinstance(findings, list):
        return  # the contract check names it
    if not any(isinstance(f, str) and (f.strip() == note or (f.lstrip().startswith(REPEAT_PREFIX)
                                                             and f.rstrip().endswith(f": {note}")))
               for f in findings):
        findings.append(f"{REPEAT_PREFIX}{repeat.get('after')}: {note}")


def _load(path: Path) -> dict[str, Any] | str:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return f"verification file is not JSON: {exc}"
    if not isinstance(data, dict):
        return "verification file is not an object"
    return data


def heads_match(approved: str, pr_head: str) -> bool:
    """True when the two shas are the same commit. A short sha matches a full one."""
    a, b = approved.lower(), pr_head.lower()
    if len(a) < 7 or len(b) < 7:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def refusal(cfg: Config, queue: Path, task_id: str, pr_head: str) -> str | None:
    """Why the runner must not merge, or None when the verdict covers this PR head. `ccp verify check`: the
    record is read from the queue and judged by `judge` with no PR facts, the PR host never read."""
    path = queue / "verification" / f"{task_id}.json"
    if not path.is_file():
        return f"no verification file for {task_id}"
    loaded = _load(path)
    if isinstance(loaded, str):
        return loaded
    reasons, _ = judge(cfg, queue, loaded, task_id, pr_head.strip())
    return "; ".join(reasons) or None


# §15.4: a key this contract does not know may be one the task's own head adds to it
NEWER_CONTRACT = ("if the task's head carries a newer record contract (contracts/verification.schema.json), record "
                  "with the head's own ccp: run `verify record` from your checkout of the head with the `ccp` your "
                  "prompt names (SPEC §12.1, §15.4)")


def write_record(root: Path, queue: Path, rec: Any, now: datetime) -> tuple[list[str], Path | None]:
    """Validate `rec` and write it to verification/<task_id>.json. Nothing is written on an error. A
    refusal for a key the contract does not know adds a line: a head with a newer contract records with its
    own `ccp` (§15.4)."""
    if isinstance(rec, dict) and "checked_at" not in rec:
        rec = {**rec, "checked_at": _iso(now)}
    if isinstance(rec, dict):
        rec = {**rec, "schema_version": RECORD_VERSION}  # the writer's version, so its own contract holds it
    errs = record_errors(rec, now)
    if isinstance(rec, dict):
        errs += approve_errors(rec)
        errs += producer_errors(queue, rec)
        errs += rests_on_errors(root, queue, rec)
        errs += as_written_errors(queue, rec)
    if isinstance(rec, dict):
        errs += beyond_intent_errors(rec)
    if isinstance(rec, dict) and "catch_up" in rec:
        errs.append("catch_up: only `ccp tasks close` records a catch-up (SPEC §16.5 rule 4); a verdict carries none. "
                    "Remove it.")
    if isinstance(rec, dict) and isinstance(rec.get("gate"), dict) and rec["gate"].get("ci_run") and not _ci(queue):
        errs.append("gate.ci_run: this product's binding has no `ci: github-actions`, so a CI run is not evidence "
                    "(SPEC §15.3: the gate is the verifier's own run, never CI). Remove it.")
    if any(": unexpected key " in e for e in errs):
        errs.append(NEWER_CONTRACT)
    if errs:
        return errs, None
    if not SAFE_ID_RE.match(str(rec["task_id"])):
        return [f"task_id {rec['task_id']!r} is not a file name"], None
    path = queue / "verification" / f"{rec['task_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return [], path


def beyond_intent_errors(rec: dict[str, Any]) -> list[str]:
    """§3.5: a task's verdict says what normative text the PR adds beyond the task's intent:
    `spec_beyond_intent`, a list, empty when none. A verdict on a PR that is not a task's (`pr-<n>`) has no
    brief to judge it against and may leave it out."""
    if str(rec.get("task_id") or "").startswith("pr-") or "spec_beyond_intent" in rec:
        return []
    return ["spec_beyond_intent: missing. List each passage of normative text (SPEC, contract) the PR adds or "
            "changes that the task's brief and the ADRs it cites do not call for, naming its file and section, "
            "or give [] when there is none (SPEC §3.5)"]


def beyond_intent(queue: Path, task_id: str) -> list[str]:
    """§3.5: the passages the task's latest verdict (`verification/<task_id>.json`) lists in
    `spec_beyond_intent`: text beyond the task's intent, which makes a build sign-off due. [] for a record
    without the field (written before it), or with none, or no record at all."""
    rec = _load(queue / "verification" / f"{task_id}.json") if SAFE_ID_RE.match(task_id) else None
    got = rec.get("spec_beyond_intent") if isinstance(rec, dict) else None
    return [str(s).strip() for s in got if isinstance(s, str) and s.strip()] if isinstance(got, list) else []


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)


def recorded_at(queue: Path, path: Path) -> tuple[datetime | None, str]:
    """When the record was recorded, and how. In a git checkout: the commit that last changed it,
    which must hold it as it is. Otherwise (the usual queue): when it was written."""
    top = _git(queue, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc), "written"
    rel = os.path.relpath(path.resolve(), Path(top.stdout.strip()).resolve())
    if _git(queue, "ls-files", "--error-unmatch", "--", rel).returncode != 0 \
            or _git(queue, "status", "--porcelain", "--", rel).stdout.strip():
        return None, f"{rel} is not committed as it stands: commit the record, then merge"
    log = _git(queue, "log", "-1", "--format=%H %cI", "--", rel).stdout.split()
    return datetime.fromisoformat(log[1]), f"commit {log[0][:12]}"


def merge_ok(cfg: Config, queue: Path, pr: str, task_id: str | None) -> tuple[list[str], dict[str, Any]]:
    """Every reason the runner may not merge `pr` now (none means it may), and what was checked. The PR
    is read from the PR host and the record from the queue; `judge` judges them. Raises
    prhost.HostUnavailable when the host's CLI cannot run here."""
    rid = task_id or f"pr-{pr}"
    path = queue / "verification" / f"{rid}.json"
    body: dict[str, Any] = {"pr": pr, "record": f"verification/{rid}.json"}
    try:
        facts = prhost.view(cfg, pr)
    except prhost.HostUnavailable as exc:
        raise prhost.HostUnavailable(f"{exc}: merge-ok reads the PR from {prhost.label(cfg)}") from None
    except prhost.HostReadFailed as exc:
        return [f"could not read PR {pr}: {exc.detail}"], body
    except prhost.HostError as exc:
        return [str(exc)], body
    body["pr_head"] = facts.head
    if not path.is_file():
        return [f"no verification record verification/{rid}.json"
                + ("" if task_id else " (a task PR names its task with --task)")], body
    rec = _load(path)
    if isinstance(rec, str):
        return [rec], body
    reasons, found = judge(cfg, queue, rec, rid, facts.head, facts, recorded_at(queue, path), pr)
    return reasons, {**body, **found}


def judge(cfg: Config, queue: Path, rec: dict[str, Any], rid: str, head: str,
          facts: prhost.PrFacts | None = None, recorded: tuple[datetime | None, str] | None = None,
          pr: str | None = None) -> tuple[list[str], dict[str, Any]]:
    """The one judge of a verification record `rec` for `rid` against `head`, on plain values, for `ccp verify
    merge-ok` and `ccp verify check`: the record's contract, its project and task, the approve rule
    (`approve_errors`: no failed check, a head, a passing gate), its producers, and the head (the record's
    `head_sha`, or the `catch_up` close recorded from it, `catch_up_refusal`). With `facts`, the PR's own: it
    is open (`pr` is how the caller named it, default its number); with `recorded` (`recorded_at`), the record
    was recorded no earlier than its `checked_at`. `check` gives neither. Its reasons (none means the record
    covers `head`) and what it checked; it reads the record's producers and catch-up from `queue`, never the PR
    host."""
    body: dict[str, Any] = {}
    reasons = record_errors(rec)
    if rec.get("project_id") != cfg.project_id:
        reasons.append(f"the record is for project {rec.get('project_id')!r}, not {cfg.project_id}")
    if rec.get("task_id") != rid:
        reasons.append(f"the record's task_id is {rec.get('task_id')!r}, not {rid}")
    if rec.get("verdict") != "approve":
        reasons.append(f"the verdict is {rec.get('verdict')!r}, not approve")
    reasons += approve_errors(rec)
    reasons += producer_errors(queue, rec, require=False)
    reasons += marked_refusals(cfg, queue, rec, head)  # ADR-0045 D3: the marked checks at the head it is given
    recorded_head = str(rec.get("head_sha") or "")
    if recorded_head and not heads_match(recorded_head, head):
        why = catch_up_refusal(cfg, queue, rec, rid, head) if "catch_up" in rec else None
        if "catch_up" in rec and why is None:
            body["catch_up"] = rec["catch_up"]  # §16.5 rule 4: close's own catch-up of the approved head
        else:
            reasons.append(f"the PR head {head[:12]} is not the approved head {recorded_head[:12]} "
                           "(the head differs from head_sha): a push after the verdict needs a new verdict "
                           "(re-verify packet)"
                           + (f"; the record's catch-up does not cover it: {why}" if why else ""))
    body["gate_runs"] = _gate_runs(rec)
    when = None
    if recorded is not None:
        when, how = recorded
        body["recorded"] = how
        if when is None:
            reasons.append(how)
        else:
            body["recorded_at"] = _iso(when)
            checked = schema.parse_dt(rec.get("checked_at"))
            if checked is not None and checked > when + SKEW:
                reasons.append(f"checked_at {rec.get('checked_at')} is after the record was recorded "
                               f"({_iso(when)}): checked_at is the clock time the verdict was reached")
    if facts is not None and facts.state != "open":
        merged = schema.parse_dt(facts.merged_at)
        when_s = f" at {_iso(merged)}" if merged else ""
        order = ""
        if merged and when:
            order = f"; the approval was recorded {'before' if when <= merged else 'after'} it"
        reasons.append(f"PR {pr or facts.number} is {facts.state}{when_s}{order}")
    body["unrun_checks"] = [c.get("dod_check_id") for c in rec.get("checks") or []
                            if isinstance(c, dict) and c.get("ran", True) is False]
    body["head_sha"] = recorded_head
    if not reasons and facts is not None:
        body["match_head_commit"] = facts.head  # the PR's full head, which the approval names
    return reasons, body


def sign_off_carried(queue: Path, task_id: str, signed: str, head: str) -> bool:
    """§3.5, §16.5 rule 4: True when close's own catch-up carried the build sign-off recorded for `signed` to
    `head`: the task's approve record has a `catch_up` that starts at `signed`, ends at `head` and names
    `signed` as `sign_off_carried`. (`merge-ok` has judged the catch-up itself, `catch_up_refusal`.)"""
    rec = _load(queue / "verification" / f"{task_id}.json")
    cu = rec.get("catch_up") if isinstance(rec, dict) else None
    return isinstance(cu, dict) and rec.get("verdict") == "approve" \
        and heads_match(str(cu.get("sign_off_carried") or ""), signed) \
        and heads_match(str(cu.get("from") or ""), signed) and heads_match(str(cu.get("to") or ""), head)


def catch_up_refusal(cfg: Config, queue: Path, rec: dict[str, Any], task_id: str, head: str) -> str | None:
    """§16.5 rule 4: why the record's `catch_up` does not cover `head`, or None when it does: it starts
    from the approved head (`head_sha`), ends at `head`, and its `gate_run` is a recorded `ccp suite run`
    of the product's gate lane (`suite.roles`), bound to this task, that passed."""
    from ccp import suite  # noqa: PLC0415
    from ccp.config import lane_for  # noqa: PLC0415
    cu = rec.get("catch_up")
    if not isinstance(cu, dict):
        return "the record carries no catch-up"
    if not heads_match(str(cu.get("from") or ""), str(rec.get("head_sha") or "")):
        return f"it starts from {str(cu.get('from'))[:12]}, not the approved head"
    if not heads_match(str(cu.get("to") or ""), head):
        return f"it ends at {str(cu.get('to'))[:12]}, not {head[:12]}"
    sid = str(cu.get("gate_run") or "")
    try:
        row = next((r for r in suite.fold(queue) if r.get("suite_id") == sid), None)
    except Exception:  # noqa: BLE001
        row = None
    lane = lane_for(cfg, "gate")
    if row is None:
        return f"its gate run {sid or '(none)'} is not recorded (ccp suite list)"
    if row.get("task_id") != task_id:
        return f"its gate run {sid} is bound to {row.get('task_id') or 'no task'}, not {task_id}"
    if row.get("lane") != lane:
        return f"its gate run {sid} ran lane {row.get('lane')!r}, not the gate lane {lane!r}"
    if row.get("state") != "passed" or row.get("exit_code") != 0:
        return f"its gate run {sid} did not pass ({row.get('state')}, exit {row.get('exit_code')})"
    return None


def record_catch_up(queue: Path, task_id: str, catch_up: dict[str, Any]) -> Path:
    """§16.5 rule 4: `ccp tasks close` adds its catch-up to the task's approve record, stamped with this
    reader's version (the key is version 2's). Raises ValueError, writing nothing, when the record is not
    an approve or the result breaks the contract."""
    path = queue / "verification" / f"{task_id}.json"
    rec = _load(path)
    if isinstance(rec, str):
        raise ValueError(rec)
    if rec.get("verdict") != "approve":
        raise ValueError(f"the verdict is {rec.get('verdict')!r}, not approve")
    was = rec.get("schema_version")
    rec = {**rec, "catch_up": catch_up, "schema_version": max(RECORD_VERSION, was if schema.is_type(was, "integer") else 0)}
    errs = record_errors(rec)
    if errs:
        raise ValueError("; ".join(errs))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return path


def _note_run(cfg: Config, queue: Path, rec: dict[str, Any]) -> str | None:
    """§10.3: the verdict on the task's open verify run, with its per-check facts (`runs.check_facts`, §15.6
    rule 3), and a `verify/recorded` event. The verifier's
    `ccp report` closes the run. A verdict with no open run (a PR that is not a task's, a record
    written before the toolkit) is still recorded; it only has no run to note."""
    from ccp import runs  # noqa: PLC0415
    from ccp.queue import QueueError, emit  # noqa: PLC0415

    try:
        run = runs.latest_open(queue, str(rec["task_id"]), "verify")
        if run is None:
            return None
        earlier = [r for r in runs.all_runs(queue, str(rec["task_id"])) if r.get("run_id") != run["run_id"]]
        # §15.6 rule 3: the verdict's per-check facts, which a later carry of a marked check is judged on
        run.update(verdict=rec["verdict"], head=rec.get("head_sha"), verdict_at=rec.get("checked_at"),
                   checks=runs.check_facts(rec.get("checks"), earlier))
        runs.save(queue, run)
        emit(queue, cfg, str(rec["task_id"]), "verify", "recorded",
             {"run_id": run["run_id"], "verdict": rec["verdict"], "head_sha": rec.get("head_sha") or ""}, "task-verifier")
        return run["run_id"]
    except QueueError as exc:
        print(f"ccp verify record: the verdict is written; noting it on its run failed: {exc}", file=sys.stderr)
        return None


def signed_passages(text: str) -> list[tuple[int, str]]:
    """§3.5, §15.2: `tasklog.signed_blocks` without the file each block names: (line number in the file, passage)."""
    from ccp import tasklog  # noqa: PLC0415
    return [(n, passage) for n, passage, _ in tasklog.signed_blocks(text)]


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def searchable(cfg: Config, path: str) -> bool:
    """§15.2: whether a file a block names may be searched for its passage: a path holding a `/` and no glob
    character (`tasklog._path_like`), not under `tests/`, not under the task log's directory (`cfg.tasks_dir`) and
    not a SPEC file (`spec_paths`)."""
    from ccp import tasklog  # noqa: PLC0415
    p = path.strip().removeprefix("./")
    tasks = cfg.rel(cfg.tasks_dir).rstrip("/") + "/"
    return (tasklog._path_like(p) and not p.startswith("tests/") and not p.startswith(tasks)
            and not tasklog._names_spec(p, spec_paths_of(cfg)))


def _hunks(cfg: Config, base: str, head: str, keep: Callable[[str], bool]) -> dict[str, list[tuple[str, str]]] | None:
    """§15.2: per file whose path `keep` accepts, one text per hunk `git diff <base>...<head>` makes to it:
    the hunk's lines in the file as it is at `head`, extended with the unchanged lines before and after it up to the
    nearest blank line on each side (a hunk's own blank first or last line is that line), joined and
    whitespace-normalised, as (text, mask), the mask `+` under each character of a line the hunk adds and
    `.` elsewhere. A hunk that adds nothing has no text. None when the diff cannot be read (`base` resolves
    to nothing). A file's `+++ ` header is read only between its `diff --git` line and its first `@@` line."""
    from ccp import tasklog  # noqa: PLC0415

    r = subprocess.run(["git", "-C", str(cfg.root), "-c", "core.quotePath=false", "diff", "--no-color",
                        "--no-ext-diff", "--unified=0", f"{base}...{head}"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    ranges: dict[str, list[tuple[int, int]]] = {}
    cur: str | None = None
    header = False
    for line in r.stdout.splitlines():
        if line.startswith("diff --git "):
            cur, header = None, True
        elif header and line.startswith("+++ "):
            path = line[4:]
            cur = path[2:] if path.startswith("b/") else None  # `/dev/null`: a deleted file
            if cur is not None and not keep(cur):
                cur = None
        elif line.startswith("@@"):  # with no context lines, no content line begins `@@`
            header = False
            m = _HUNK_RE.match(line)
            if cur is not None and m and (n := int(m.group(2) or 1)):  # +start,count: 0 adds nothing
                ranges.setdefault(cur, []).append((int(m.group(1)) - 1, n))
    out: dict[str, list[tuple[str, str]]] = {}
    for f, hunks in ranges.items():
        shown = tasklog.text_at(cfg, head, f)
        if shown is None:
            continue
        lines = shown.splitlines()
        for start, n in hunks:
            lo, hi = start, min(start + n, len(lines))
            while lo > 0 and lines[lo].strip() and lines[lo - 1].strip():
                lo -= 1
            while 0 < hi < len(lines) and lines[hi - 1].strip() and lines[hi].strip():
                hi += 1
            words = [(w, start <= k < start + n) for k in range(lo, hi) for w in lines[k].split()]
            text = " ".join(w for w, _ in words)
            mask = ".".join(("+" if added else ".") * len(w) for w, added in words)
            if "+" in mask:
                out.setdefault(f, []).append((text, mask))
    return out


def spec_hunks(cfg: Config, base: str, head: str = "HEAD") -> dict[str, list[tuple[str, str]]] | None:
    """§15.2: `_hunks` of the SPEC files (`spec_paths`)."""
    from ccp import tasklog  # noqa: PLC0415
    spec_paths = spec_paths_of(cfg)
    return _hunks(cfg, base, head, lambda p: tasklog._names_spec(p, spec_paths))


def named_hunks(cfg: Config, base: str, head: str, paths: set[str]) -> dict[str, list[tuple[str, str]]] | None:
    """§15.2: `_hunks` of the given paths, the files signed blocks name, never one `searchable` refuses."""
    return _hunks(cfg, base, head, lambda p: p in paths and searchable(cfg, p))


def _found(passage: str, hunk: tuple[str, str]) -> bool:
    """§15.2: whether `passage` lies within the hunk's text and covers at least one character of a line the
    hunk adds (some occurrence of it, when it occurs more than once)."""
    text, mask = hunk
    at = text.find(passage)
    while at >= 0:
        if "+" in mask[at:at + len(passage)]:
            return True
        at = text.find(passage, at + 1)
    return False


def spec_text(cfg: Config, task: str, base: str | None = None, head: str | None = None) -> tuple[int, dict[str, Any]]:
    """§15.2 `ccp verify spec-text`: whether each passage the task carries for the operator's sign-off
    (`tasklog.signed_blocks`, read from the task file in the checkout) is in the SPEC text `head` (default `HEAD`)
    changes since `base` (`spec_hunks`), or else in the text it changes in the one file the passage's own
    block names (`named_hunks`), each hunk read with the
    unchanged lines around it up to the nearest blank line: a passage is found when it lies within one hunk's
    text and covers a character of a line that hunk adds (`_found`), so one wholly inside unchanged lines is
    not. A passage found in the SPEC is not looked for in its named file. The exit code (0 all found, 1 one
    or more not, 2 no passage, an unknown task, a head that names no commit or a base that does not resolve)
    and the body, whose `found_in` names the file or files each passage was found in."""
    from ccp.queue import QueueError, integration_branch, task_meta  # noqa: PLC0415
    try:
        meta = task_meta(cfg, task)
    except QueueError as e:
        return 2, {"ok": False, "task_id": task, "error": str(e)}
    tid = str(meta["task_id"])
    if base is None:
        q = os.environ.get("QUEUE_ROOT")
        base = f"origin/{integration_branch(Path(q)) if q and Path(q).is_dir() else 'main'}"
    head = head or "HEAD"
    from ccp import tasklog  # noqa: PLC0415
    passages = tasklog.signed_blocks(meta["_text"])
    if not passages:
        return 2, {"ok": False, "task_id": tid, "base": base, "head": head,
                   "error": f"{cfg.rel(meta['_file'])} carries no PROPOSED: block (a `PROPOSED:` marker followed by "
                            "`> ` blockquote lines) in its Scope or in a section whose heading begins `Rule changes`"}
    if subprocess.run(["git", "-C", str(cfg.root), "rev-parse", "--verify", "--quiet", f"{head}^{{commit}}"],
                      capture_output=True, text=True).returncode != 0:
        return 2, {"ok": False, "task_id": tid, "base": base, "head": head,
                   "error": f"--head {head} names no commit in {cfg.root}"}
    added = spec_hunks(cfg, base, head)
    if added is None:
        return 2, {"ok": False, "task_id": tid, "base": base, "head": head,
                   "error": f"git diff {base}...{head} failed: is {base} a ref in {cfg.root}?"}
    rel = cfg.rel(meta["_file"])
    rows = [{"line": f"{rel}:{n}", "passage": text,
             "found_in": [f for f, hunks in sorted(added.items()) if any(_found(text, h) for h in hunks)]}
            for n, text, _ in passages]
    named = {names for (_, _, names), r in zip(passages, rows) if names and not r["found_in"]}
    elsewhere = (named_hunks(cfg, base, head, named) or {}) if named else {}
    for (_, text, names), r in zip(passages, rows):
        if not r["found_in"] and names in elsewhere and any(_found(text, h) for h in elsewhere[names]):
            r["found_in"] = [names]
    missing = [r for r in rows if not r["found_in"]]
    return (1 if missing else 0), {"ok": not missing, "task_id": tid, "base": base, "head": head, "passages": rows,
                                   "missing": [r["line"] for r in missing]}


# §15.4: the result of a check verify could not run, recorded after its task closed.
LATER_SUFFIX = ".later.jsonl"
EVIDENCE_MAX = 500
LATER_STATES = ("open", "passed", "failed")


def later_path(queue: Path, task_id: str) -> Path:
    """`verification/<task_id>.later.jsonl`: the results recorded after close, one row each."""
    return queue / "verification" / f"{task_id}{LATER_SUFFIX}"


def _deferred(c: Any) -> bool:
    """A check recorded not run (`ran: false`) that does not rest on a carried verdict."""
    return isinstance(c, dict) and c.get("ran", True) is False and carried_from(c.get("rests_on")) is None


def deferred_ids(rec: Any) -> list[str]:
    """The ids of the record's checks that may be run after close, in the record's order."""
    checks = rec.get("checks") if isinstance(rec, dict) else None
    out: list[str] = []
    for c in checks if isinstance(checks, list) else []:
        cid = str(c.get("dod_check_id")) if isinstance(c, dict) else ""
        if _deferred(c) and cid not in out:
            out.append(cid)
    return out


def _seats() -> tuple[str, ...]:
    """The seats a check's `produced_by` may name: the verdict record's contract."""
    props = json.loads(SCHEMA.read_text())["properties"]["checks"]["items"]["properties"]
    return tuple(props["produced_by"]["enum"])


def later_errors(status: str | None, rec: Any, check_id: str, evidence: str, seat: str, step: str | None,
                 step_refusal: Callable[[str], str | None], seats: tuple[str, ...]) -> list[str]:
    """Why a result recorded after close is refused (§15.4), an empty list when it is not. `status` is the
    task's queue status, `rec` its verdict record (None when it has none), `step_refusal` why an
    `operator_step` is not an approved operator gate of the task (None when it is)."""
    from ccp import health  # noqa: PLC0415

    errs: list[str] = []
    if status != "done":
        errs.append(f"the task is {status or 'not in the queue'}, not done: a check is recorded here only after "
                    "its task closed")
    if not isinstance(rec, dict):
        errs.append("the task has no verification record (verification/<task_id>.json)")
    else:
        checks = [c for c in rec.get("checks") or [] if isinstance(c, dict)
                  and str(c.get("dod_check_id")) == check_id]
        if not checks:
            errs.append(f"the verification record holds no check {check_id!r}")
        elif not any(_deferred(c) for c in checks):
            c = checks[0]
            why = (f"it rests on a carried verdict ({c.get('rests_on')}), run at an earlier head"
                   if c.get("ran", True) is False else "it was run at verify")
            errs.append(f"check {check_id!r} is not one verify deferred: {why}")
    text = evidence.strip()
    if not text:
        errs.append("--evidence is empty: say what the run showed")
    if "\n" in evidence or "\r" in evidence:
        errs.append("--evidence holds a line break: give one line")
    if len(text) > EVIDENCE_MAX:
        errs.append(f"--evidence is {len(text)} characters; the limit is {EVIDENCE_MAX}")
    if text and health.looks_like_secret(text):
        errs.append("--evidence looks like it holds a secret; say it without the value")
    if seat not in seats:
        errs.append(f"--produced-by {seat!r} is not a seat ({', '.join(seats)})")
    elif seat in RULING_SEATS and not step:
        errs.append(f"the evidence was produced by the {seat}, a seat that rules on the task: name the approved "
                    "operator step it came from (--operator-step <task_id>-<n>, §15.4)")
    if step:
        why = step_refusal(step)
        if why:
            errs.append(f"produced by the {seat}: {why}")
    return errs


def later_rows(queue: Path, task_id: str) -> list[dict[str, Any]]:
    """The results recorded after close, in order; a line that is not a JSON object is passed over."""
    try:
        lines = later_path(queue, task_id).read_text().splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def deferred_states(task_id: str, rec: Any, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Each deferred check of the record, `open` with no row, else `passed` or `failed` by its latest row."""
    latest = {str(r.get("dod_check_id")): r.get("pass") for r in rows}
    return [{"task_id": task_id, "dod_check_id": cid,
             "state": "open" if cid not in latest else ("passed" if latest[cid] is True else "failed")}
            for cid in deferred_ids(rec)]


def _read_record(queue: Path, task_id: str) -> dict[str, Any] | None:
    loaded = _load(queue / "verification" / f"{task_id}.json")
    return loaded if isinstance(loaded, dict) else None


def record_later(queue: Path, task_id: str, check_id: str, passed: bool, evidence: str, seat: str,
                 step: str | None, now: datetime) -> tuple[list[str], dict[str, Any] | None]:
    """`ccp verify later`: append one result to `verification/<task_id>.later.jsonl`, or the refusals and
    nothing written."""
    from ccp import queue as qmod  # noqa: PLC0415

    if not SAFE_ID_RE.match(task_id):
        return [f"task id {task_id!r} is not a file name"], None
    try:
        status = qmod.load_task_state(queue, task_id).get("status")
    except qmod.QueueError as exc:
        return [str(exc)], None
    errs = later_errors(str(status) if status else None, _read_record(queue, task_id), check_id, evidence, seat,
                        step, lambda s: _operator_step_refusal(queue, task_id, s), _seats())
    if errs:
        return errs, None
    row = {"task_id": task_id, "dod_check_id": check_id, "pass": passed, "evidence": evidence.strip(),
           "produced_by": seat, "operator_step": step or None, "at": _iso(now), "by": qmod.actor()}
    qmod.append_jsonl(later_path(queue, task_id), row)
    return [], row


def deferred(queue: Path, task_id: str | None = None) -> list[dict[str, str]]:
    """`ccp verify deferred`: each deferred check of each done task with a verification record."""
    from ccp import queue as qmod  # noqa: PLC0415

    out: list[dict[str, str]] = []
    vdir = queue / "verification"
    for path in sorted(vdir.glob("*.json")) if vdir.is_dir() else []:
        tid = path.stem
        if (task_id and tid != task_id) or not SAFE_ID_RE.match(tid):
            continue
        try:
            done = qmod.load_task_state(queue, tid).get("status") == "done"
        except qmod.QueueError:
            done = False
        if done:
            out += deferred_states(tid, _read_record(queue, tid), later_rows(queue, tid))
    return out


def _full_task_id(cfg: Config, task_id: str) -> str:
    """The task's full id, for its number too; as given when the task log holds no such task."""
    from ccp import queue as qmod  # noqa: PLC0415
    try:
        return str(qmod.task_meta(cfg, task_id).get("task_id") or task_id)
    except qmod.QueueError:
        return task_id


def _later_main(cfg: Config, queue: Path, a: Any) -> int:
    errs, row = record_later(queue, _full_task_id(cfg, a.target), a.check, a.passed, a.evidence, a.produced_by,
                             a.operator_step, _now())
    if errs:
        print("ccp verify later: refused, nothing written", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        return 2
    print(json.dumps({"ok": True, **(row or {})}, indent=2, ensure_ascii=False))
    return 0


def _deferred_main(cfg: Config, queue: Path, a: Any) -> int:
    rows = deferred(queue, _full_task_id(cfg, a.task) if a.task else None)
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    for r in rows:
        print(f"{r['task_id']} {r['dod_check_id']} {r['state']}")
    print(f"{sum(r['state'] == 'open' for r in rows)} open, {sum(r['state'] == 'failed' for r in rows)} failed")
    return 0


def _queue() -> Path | None:
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        print("ccp verify: set QUEUE_ROOT to this project's runtime queue", file=sys.stderr)
        return None
    return Path(q)


def main(cfg: Config, a: Any) -> int:
    """`ccp verify <action>`: the parser gives each action its own arguments and refuses another action's (`ccp.cli`)."""
    if a.action == "spec-text":  # reads the task log and git only: no queue
        code, body = spec_text(cfg, a.target, a.base, a.head)
        if body.get("error"):
            print(f"ccp verify spec-text: {body['error']}", file=sys.stderr)
        for r in body.get("passages") or []:
            if not r["found_in"]:
                print(f"ccp verify spec-text: not found in the SPEC or the file its block names, in the text {body['head']} "
                      f"changes since {body['base']}: the passage at {r['line']}: {r['passage']}", file=sys.stderr)
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return code
    queue = _queue()
    if queue is None:
        return 2
    if a.action == "later":
        return _later_main(cfg, queue, a)
    if a.action == "deferred":
        return _deferred_main(cfg, queue, a)
    if a.action == "record":
        try:
            rec = json.loads(sys.stdin.read() if a.target == "-" else Path(a.target).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ccp verify record: {exc}", file=sys.stderr)
            return 2
        errs = fill_gate(queue, rec) if isinstance(rec, dict) else []
        errs = errs or (cache_errors(cfg, rec) if isinstance(rec, dict) else [])
        errs = errs or (review_errors(queue, rec) if isinstance(rec, dict) else [])
        errs = errs or (resolution_errors(queue, rec) if isinstance(rec, dict) else [])
        errs = errs or (adr_errors(cfg, rec) if isinstance(rec, dict) else [])
        errs = errs or (marked_refusals(cfg, queue, rec, str(rec.get("head_sha") or "")) if isinstance(rec, dict) else [])
        if not errs and isinstance(rec, dict):
            fill_reason(queue, rec)
        if not errs:
            errs, path = write_record(cfg.root, queue, rec, _now())
        if errs:
            print("ccp verify record: refused, nothing written", file=sys.stderr)
            for e in errs:
                print(f"  {e}", file=sys.stderr)
            return 1
        run_id = _note_run(cfg, queue, rec)
        print(json.dumps({"ok": True, "path": str(path), "task_id": rec["task_id"], "verdict": rec["verdict"],
                          "head_sha": rec.get("head_sha"), "run_id": run_id}, indent=2))
        return 0
    if a.action == "merge-ok":
        try:
            reasons, body = merge_ok(cfg, queue, a.target, a.task)
        except prhost.HostUnavailable as exc:
            print(f"ccp verify: {exc}", file=sys.stderr)
            return 2
        body = {"ok": not reasons, **body, **({"reasons": reasons} if reasons else {})}
        for r in reasons:
            print(f"ccp verify merge-ok: {r}", file=sys.stderr)
        print(json.dumps(body, indent=2))
        return 1 if reasons else 0
    if not a.head.strip():
        print("ccp verify: --head is the PR head the runner would merge", file=sys.stderr)
        return 2
    reason = refusal(cfg, queue, a.target, a.head)
    if reason:
        print(f"ccp verify: {reason}", file=sys.stderr)
        print(json.dumps({"ok": False, "task_id": a.target, "reason": reason}, indent=2))
        return 1
    print(json.dumps({"ok": True, "task_id": a.target, "head_sha": a.head}, indent=2))
    return 0
