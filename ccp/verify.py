"""The verifier's record and the runner's merge gate (SPEC §15.3).

  ccp verify record FILE|-              validate a verdict, then write verification/<task_id>.json
  ccp verify merge-ok PR [--task ID]    may the runner merge this PR now? (exit 0 only if so)
  ccp verify check TASK_ID --head SHA   the record covers this head (the adapter path, no `gh`)

A record is validated against `contracts/verification.schema.json` itself (a stdlib subset of
JSON Schema, so the plane takes no dependency) and against the rules the schema cannot hold:
a check the verifier did not run is neither a pass nor a fail, `checked_at` is the clock time
the verdict was reached.

A record carries the schema version of the `ccp` that wrote it (`schema_version`; `record` stamps
`RECORD_VERSION`, whatever the input said). A reader older than the record, its own
`RECORD_VERSION` lower, passes over keys its contract does not know, at any depth, and still holds
every key it knows to its contract; a record with no version, or one no newer than the reader, is
held to the contract with no extra key. So a task that adds a field to the record can be verified
with the newer `ccp` on its PR head and merged and closed with the older one on PATH (§15.4, §29.3).

An approve is one head, every check it ran passed, and the formal gate the verifier ran
(`gate.runs`, every exit 0). `record` holds an approve to that, so a verdict it writes is one
`merge-ok` accepts.

`merge-ok` is the merge rule made mechanical: the PR is open; its head is the record's
`head_sha`; the record is such an approve; and it was recorded (committed, when the queue is a git
checkout; written, otherwise) no earlier than its `checked_at`. A verdict at another head, one recorded after the merge, or one relayed
in a message is not an approval. A PR that is not a task's is approved in
`verification/pr-<n>.json`, whose `task_id` is `pr-<n>`.

A product whose plane.json sets `verify.accept_cache` lets its content-keyed test cache stand in
for a rerun: a unit the verifier's own gate run reports as a hit on identical inputs counts as
run. `record` then holds an approve to a gate run that says how many units ran and how many were
cached (`ran`, `cached`; a record written earlier says `modules_ran`, `modules_cached`), and, on a
task whose gate is cold (`cold_gate`), to a cold run with nothing cached.

A gate run may name the `ccp suite run` that ran it (`suite_id`, §14.1): `record` fills its exit
code, tests, skips, seconds and units ran and cached from that recorded run (the gate's result
file, or the output's counts), and marks a run with nothing cached `cold`, so the verifier types none
of them.

`record` also refuses an approve of a task whose latest fix round is newer than its last review, or
of a head other than the one that review judged (§15.2, the runner brief's step 7), unless the open
verify run carries the override `ccp prompt verify --allow-unreviewed-fix` recorded, or the skip
`skip_review` proved for that head: a product with `verify.skip_review` lets a fix whose diff touches only
the declared paths, and that the product's proof command passes, go to verify with no new review, and a
declared prover of the review (`verify.provers`, `skips: review`) whose command exits 0 on the fix diff
does the same, its name and exit recorded on the verify run (no command text). A
product with `verify.skip_review_after_clean` lets the fix round after a clean review (no BLOCKER or MAJOR
finding) go to verify with no new review, the skip recorded as `minor-only` at the verify run's head; the
verifier confirms the fix answers only that review's findings (`skip_after_clean`).

Under `adr.strict`, `record` also refuses an approve of a head on which a decision the task's `adr_refs`
cite is still recorded `not_built` (§6.7's in-force check, run before the verdict rather than only once
close has marked the task done), naming the decision and the `ccp adr decide` that flips it.

Each check names the seat that produced its evidence (`produced_by`, §2.3, §15.4). `record` refuses
a check without one (a check a ruling closed, `ran: false` with `rests_on`, may leave it out), and
evidence produced by a seat that rules on the task (the lead, the runner) unless its `operator_step`
names an approved `operator` gate of the task (§17.9); `merge-ok` and `check` read a record written
before the field, and still refuse a ruling seat's evidence.

A check not run (`ran: false`) rests on one of three things, and `record` refuses anything else
(`rests_on_errors`): a ruling, named by spec question (`sm-…`) or gate (`<task_id>-<n>`) ids that all
exist (a gate's file is the gate it is cited as, its `escalation_id` and `task_id` those of the cited
id; a question has its question file as well as its answer), each gate closed and approved and each
question answered `resolved`; a carried verdict, `approve at <sha>` (§15.6 rule 3), the sha a commit
of the product checkout; or evidence the operator produced (`produced_by: operator`), with any text. `merge-ok` and `check` do not apply it, so a record
written before the rule is still read.

A verify round opened with no fix round since the last (§15.6 rule 4, `repeat_round`) carries the
runner's `--note` as its reason; `record` adds that reason to the record's `findings` when no finding
gives it yet, as its whole text or as the line it adds (`fill_reason`).

A record may carry `catch_up` (§16.5 rule 4), which only `ccp tasks close` writes (`record_catch_up`;
`record` refuses a verdict that carries one): close merged the integration tip into the approved head
itself, ran the gate lane on the result and pushed it as the task branch's new head. `merge-ok` accepts
that head, `catch_up.to`, in place of `head_sha` only when `catch_up.from` is `head_sha` and its
`gate_run` is a passed `ccp suite run` of the product's gate lane bound to the task (`catch_up_refusal`).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp.config import Config
from ccp.refs import ANY_TASK_ID, QUESTION_ID

SCHEMA = Path(__file__).resolve().parents[1] / "contracts" / "verification.schema.json"
# The record's schema version, stamped by `record`. A change that adds a key to the record's
# contract, at any depth, raises it, so an older reader knows the record is newer than itself.
RECORD_VERSION = 2  # 2: `catch_up` (§16.5 rule 4)
# Clocks on two machines differ a little; a minute is the slack, not a rounding allowance.
SKEW = timedelta(seconds=60)
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
# Keywords that only describe; every other keyword must be one `schema_errors` enforces.
_ANNOTATIONS = {"$schema", "$id", "title", "description", "default"}


def _ci(queue: Path) -> bool:
    """The binding opts into CI (`ci: github-actions`, §15.3): only then may a verdict cite `gate.ci_run`."""
    from ccp.queue import binding_text  # noqa: PLC0415
    text = binding_text(queue)
    return re.search(r"^ci:\s*['\"]?github-actions\b", text, re.M) is not None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is(value: Any, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[typ])


def schema_errors(value: Any, schema: dict[str, Any], at: str = "record", newer: bool = False) -> list[str]:
    """Where `value` breaks `schema`. Only the keywords the plane's contracts use are known; an
    unknown one is an error, so a contract change cannot silently weaken this check. With `newer`
    (a record written by a newer version) a key the schema does not name is passed over; every key
    it names is still checked."""
    unknown = set(schema) - _ANNOTATIONS - {"type", "enum", "required", "properties", "additionalProperties",
                                            "items", "minItems", "minLength", "minimum", "pattern", "format"}
    if unknown:
        return [f"{at}: the schema uses {', '.join(sorted(unknown))}, which ccp verify cannot check"]
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(_is(value, t) for t in types):
            return [f"{at}: {json.dumps(value)[:60]} is not {' or '.join(types)}"]
    errs: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{at}: {json.dumps(value)[:60]} is not one of {', '.join(map(str, schema['enum']))}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{at}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{at}: {value!r} does not match {schema['pattern']}")
        if schema.get("format") == "date-time" and _parse_dt(value) is None:
            errs.append(f"{at}: {value!r} is not an RFC 3339 date-time")
    if "minimum" in schema and _is(value, "number") and value < schema["minimum"]:
        errs.append(f"{at}: {value} is below {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{at}: fewer than {schema['minItems']} item(s)")
        for i, item in enumerate(value):
            errs += schema_errors(item, schema.get("items", {}), f"{at}[{i}]", newer)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{at}: missing {k}")
        for k, v in value.items():
            if k in props:
                errs += schema_errors(v, props[k], f"{at}.{k}", newer)
            elif schema.get("additionalProperties") is False and not newer:
                errs.append(f"{at}: unexpected key {k}")
    return errs


def written_by_newer(rec: Any) -> bool:
    """The record says a newer `ccp` wrote it: its `schema_version` is an integer above `RECORD_VERSION`."""
    version = rec.get("schema_version") if isinstance(rec, dict) else None
    return _is(version, "integer") and version > RECORD_VERSION


def record_errors(rec: Any, now: datetime | None = None) -> list[str]:
    """The schema, then what it cannot say. With `now`, a `checked_at` later than now fails. A record
    whose `schema_version` is newer than this reader's may carry keys its contract does not know."""
    errs = schema_errors(rec, json.loads(SCHEMA.read_text()), newer=written_by_newer(rec))
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
    checked = _parse_dt(rec.get("checked_at"))
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
_APPROVE_AT = re.compile(r"approve at ([0-9a-fA-F]{7,40})")
_REST_FORMS = ("a ruling, named by its spec question id (sm-…) or gate id (<task_id>-<n>), each of which exists, "
               "each gate closed and approved and each question answered resolved; a carried verdict, "
               "`approve at <sha>` (§15.6 rule 3), the sha a commit; or evidence the operator produced "
               "(produced_by: operator)")


def _ruling_refusal(queue: Path, rests_on: str) -> str | None:
    """Why `rests_on` is not a ruling the queue holds, or None when it is: it names at least one gate
    id `<task_id>-<n>` or spec question id `sm-…`, and every one it names exists and was ruled (the
    gate file `escalations/<task_id>/<n>.json`, §17.9, is the gate it is cited as, its `escalation_id`
    and `task_id` those of the cited id, of any task, closed and approved; the question file
    `questions/<id>.json` with its answer `questions/<id>.answer.json` at verdict `resolved`, §17.5:
    an answer without its question is no ruling). The ids may sit inside prose; an unknown or unruled one beside a ruled one is refused."""
    missing, misfiled, open_, unanswered = [], [], [], []
    gates = list(_GATE_TOKEN.finditer(rests_on))
    questions = list(_QUESTION_TOKEN.finditer(rests_on))
    if not gates and not questions:
        return "it names no ruling id"
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
    anything else is refused, naming the check. A ruling: `rests_on` names spec question or gate ids
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
    entry has none; a recorded run with nothing cached (`cached` 0) is marked `cold: true` when the
    entry does not say `cold`. A number the entry gives itself stays; an exit code that differs from the
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
        if "cold" not in e and row.get("cached") == 0 and gate_counts(e)[1] == 0:
            e["cold"] = True  # §15.3: a recorded run with nothing cached is a cold run
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
    base on the integration branch (`git merge-tree` of the reviewed head and that base, which must merge
    cleanly) to the head, so an integration merge in between is not counted as the fix's. It must touch
    at least one file. `verify.skip_review` proves it when the diff touches only files under `paths` (git
    pathspecs, as `merge.behind_tip_ignore`) and the product's `proof` command exits 0; failing that, each
    review prover in turn proves it when its `command` exits 0. Either command runs in the product root
    with `{task_id}`, `{reviewed}`, `{head}` and `{from}` (the tree the fix diff starts from) filled in.
    Neither runs when the task's diff (the head's merge base with the integration branch to the head)
    touches a file its command names, or plane.json (`config.prover_touched`): it is refused,
    `prover_touched`. Returns what to record on the verify run (a prover's skip adds its `prover` name and
    `exit_code`, never its command text, §14.4; `refused_provers` names each refused one), or None and why
    not, as "<the settings> does not apply: <why>" or "nothing is skipped: <why>" ("" when neither is set or
    there is no fix to judge).

    `git merge-tree --write-tree` needs git 2.38 or later. It exits 1 on a conflict; any other failure,
    such as an older git that lacks the option, is named as such, and the review stands either way."""
    from ccp import runs  # noqa: PLC0415
    from ccp.config import skip_rules_at  # noqa: PLC0415
    from ccp.queue import git, integration_branch  # noqa: PLC0415

    integ = integration_branch(queue)
    if git(cfg.root, "fetch", "-q", "origin").returncode != 0:
        return None, f"nothing is skipped: the fetch of origin/{integ} failed, so no skip rule was read"
    found, unread = skip_rules_at(cfg.root, f"origin/{integ}")
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
    rec, why = _judge_fix(cfg, queue, task_id, reviewed, head, pr, str(fixes[-1]["run_id"]), rule, provers, integ)
    return rec, (f"{label} does not apply: {why}" if why else "")


def _judge_fix(cfg: Config, queue: Path, task_id: str, reviewed: str, head: str, pr: str | None, fix: str,
               rule: dict[str, Any] | None, provers: list[dict[str, Any]],
               integ: str) -> tuple[dict[str, Any] | None, str]:
    """`skip_review`'s judgement of the fix diff by the rules read from the integration branch: what to
    record on the verify run, or None and why not."""
    from ccp import rules  # noqa: PLC0415
    from ccp.config import PROVER_TOUCHED, fill, prover_touched  # noqa: PLC0415
    from ccp.queue import git  # noqa: PLC0415

    shas = []  # `skip_review` fetched origin
    for sha in (reviewed, head.strip()):
        if git(cfg.root, "cat-file", "-e", f"{sha}^{{commit}}").returncode != 0:
            for ref in ([f"refs/pull/{pr}/head"] if pr else []) + [f"task/{task_id}"]:
                if git(cfg.root, "fetch", "-q", "origin", ref).returncode == 0 \
                        and git(cfg.root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0:
                    break
        r = git(cfg.root, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}")
        if r.returncode != 0:
            return None, f"{sha[:12]} could not be fetched"
        shas.append(r.stdout.strip())
    reviewed, head = shas
    base = git(cfg.root, "merge-base", head, f"origin/{integ}")
    if base.returncode != 0:
        return None, f"the head has no merge base with origin/{integ}"
    tree = git(cfg.root, "merge-tree", "--write-tree", "--no-messages", reviewed, base.stdout.strip())
    if tree.returncode not in (0, 1):
        return None, (f"`git merge-tree --write-tree` failed (exit {tree.returncode}); it needs git 2.38 or later")
    if tree.returncode != 0 or not tree.stdout.split():
        return None, f"the reviewed head does not merge cleanly onto the head's base on origin/{integ}"
    start = tree.stdout.split()[0]
    task = git(cfg.root, "diff", "--name-only", "--no-renames", base.stdout.strip(), head)
    if task.returncode != 0:
        return None, "the task's diff could not be read"
    task_files = [f for f in task.stdout.split("\n") if f]
    touched = git(cfg.root, "diff", "--name-only", "--no-renames", start, head)  # a rename names both of its paths
    if touched.returncode != 0:
        return None, "the fix diff could not be read"
    files = [f for f in touched.stdout.split("\n") if f]
    if not files:
        return None, "the fix changes no file of its own"
    values = {"task_id": task_id, "reviewed": reviewed, "head": head, "from": start}
    skipped = {"reviewed": reviewed, "head": head, "fix": fix, "files": len(files)}
    why: list[str] = []
    refused: list[dict[str, str]] = []

    def touches(name: str, cmd: str, what: str) -> bool:
        """Refuse a prover whose files the task's diff touches: the task could grant itself the skip."""
        hit = prover_touched(cmd, task_files, cfg.root)
        if hit:
            refused.append({"prover": name, "reason": PROVER_TOUCHED})
            why.append(f"{what} is refused, {PROVER_TOUCHED}: the task's diff touches {', '.join(hit[:5])}")
        return bool(hit)
    if rule:
        paths = [str(x) for x in rule["paths"]]
        outside = git(cfg.root, "diff", "--name-only", "--no-renames", start, head, "--", ".", *[f":!{x}" for x in paths])
        beyond = [f for f in outside.stdout.split("\n") if f] if outside.returncode == 0 else None
        if beyond is None:
            why.append("the fix diff could not be read")
        elif beyond:
            why.append(f"the fix touches {len(beyond)} file(s) outside verify.skip_review.paths "
                       f"({', '.join(beyond[:5])})")
        elif not touches("verify.skip_review", str(rule["proof"]), "the proof (verify.skip_review.proof)"):
            code, _ = rules.run_command(cfg, fill(str(rule["proof"]), values), PROOF_TIMEOUT)
            if code == 0:
                return skipped, ""  # tried first: nothing refused before it
            why.append("the proof (verify.skip_review.proof) "
                       + (f"timed out after {PROOF_TIMEOUT}s" if code is None else f"exited {code}"))
    for p in provers:
        if touches(str(p["name"]), str(p["command"]), f"the prover {p['name']} (verify.provers)"):
            continue
        code, _ = rules.run_command(cfg, fill(str(p["command"]), values), PROOF_TIMEOUT)
        if code == 0:
            return {**skipped, "prover": str(p["name"]), "exit_code": 0,
                    **({"refused_provers": refused} if refused else {})}, ""
        why.append(f"the prover {p['name']} (verify.provers) "
                   + (f"timed out after {PROOF_TIMEOUT}s" if code is None else f"exited {code}"))
    return None, "; ".join(why)


MINOR_SEVERITIES = ("MINOR", "NIT")  # §15.2: the findings below MAJOR, as the review's Severity line counts them


def skip_after_clean(cfg: Config, queue: Path, task_id: str, head: str) -> tuple[dict[str, Any] | None, str]:
    """§15.2: may a verify of `head` skip the review of a fix round that answers only the minor findings
    of a clean review? Only with plane.json `verify.skip_review_after_clean` on, when the task's latest
    review run that reported done recorded no BLOCKER or MAJOR finding and at least one below them, a fix
    run (not abandoned; a merge or ruling round counts as one, §13.2) opened since and reported its head,
    `head` is that head, and no verify run since the review rejected (a reject sends the task back to
    review). Returns what to record on the verify run, `{reason: "minor-only", review_run, reviewed, report,
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


def refusal(queue: Path, task_id: str, pr_head: str) -> str | None:
    """Why the runner must not merge, or None when the verdict covers this PR head."""
    path = queue / "verification" / f"{task_id}.json"
    if not path.is_file():
        return f"no verification file for {task_id}"
    loaded = _load(path)
    if isinstance(loaded, str):
        return loaded
    errs = record_errors(loaded) + producer_errors(queue, loaded, require=False)
    if errs:
        return "the verification record is not valid: " + "; ".join(errs)
    if loaded.get("verdict") != "approve":
        return f"verdict is {loaded.get('verdict')!r}, not approve"
    recorded = loaded.get("head_sha")
    if not isinstance(recorded, str) or not recorded.strip():
        return None
    if not heads_match(recorded.strip(), pr_head.strip()):
        return f"PR head {pr_head} differs from head_sha {recorded}"
    return None


def write_record(root: Path, queue: Path, rec: Any, now: datetime) -> tuple[list[str], Path | None]:
    """Validate `rec` and write it to verification/<task_id>.json. Nothing is written on an error."""
    if isinstance(rec, dict) and "checked_at" not in rec:
        rec = {**rec, "checked_at": _iso(now)}
    if isinstance(rec, dict):
        rec = {**rec, "schema_version": RECORD_VERSION}  # the writer's version, so its own contract holds it
    errs = record_errors(rec, now)
    if isinstance(rec, dict):
        errs += approve_errors(rec)
        errs += producer_errors(queue, rec)
        errs += rests_on_errors(root, queue, rec)
    if isinstance(rec, dict) and "catch_up" in rec:
        errs.append("catch_up: only `ccp tasks close` records a catch-up (SPEC §16.5 rule 4); a verdict carries none. "
                    "Remove it.")
    if isinstance(rec, dict) and isinstance(rec.get("gate"), dict) and rec["gate"].get("ci_run") and not _ci(queue):
        errs.append("gate.ci_run: this product's binding has no `ci: github-actions`, so a CI run is not evidence "
                    "(SPEC §15.3: the gate is the verifier's own run, never CI). Remove it.")
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


class NoGh(Exception):
    """`gh` cannot run here: a configuration problem, not a refusal."""


def _pr_facts(root: Path, pr: str) -> dict[str, Any] | str:
    gh = envvar("CCP_GH_BIN") or "gh"
    try:
        proc = subprocess.run([gh, "pr", "view", pr, "--json", "number,state,headRefOid,mergedAt"],
                              cwd=root, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise NoGh(f"{gh} is not installed: merge-ok reads the PR with gh") from exc
    if proc.returncode != 0:
        return f"could not read PR {pr}: {(proc.stderr or proc.stdout).strip()}"
    try:
        facts = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return f"gh printed no JSON for PR {pr}: {exc}"
    return facts if isinstance(facts, dict) else f"gh printed no object for PR {pr}"


def merge_ok(cfg: Config, queue: Path, pr: str, task_id: str | None) -> tuple[list[str], dict[str, Any]]:
    """Every reason the runner may not merge `pr` now (none means it may), and what was checked."""
    rid = task_id or f"pr-{pr}"
    path = queue / "verification" / f"{rid}.json"
    body: dict[str, Any] = {"pr": pr, "record": f"verification/{rid}.json"}
    facts = _pr_facts(cfg.root, pr)
    if isinstance(facts, str):
        return [facts], body
    head = str(facts.get("headRefOid") or "")
    body["pr_head"] = head
    if not path.is_file():
        return [f"no verification record verification/{rid}.json"
                + ("" if task_id else " (a task PR names its task with --task)")], body
    rec = _load(path)
    if isinstance(rec, str):
        return [rec], body
    reasons = record_errors(rec)
    if rec.get("project_id") != cfg.project_id:
        reasons.append(f"the record is for project {rec.get('project_id')!r}, not {cfg.project_id}")
    if rec.get("task_id") != rid:
        reasons.append(f"the record's task_id is {rec.get('task_id')!r}, not {rid}")
    if rec.get("verdict") != "approve":
        reasons.append(f"the verdict is {rec.get('verdict')!r}, not approve")
    reasons += approve_errors(rec)
    reasons += producer_errors(queue, rec, require=False)
    recorded_head = str(rec.get("head_sha") or "")
    if recorded_head and not heads_match(recorded_head, head):
        why = catch_up_refusal(cfg, queue, rec, rid, head) if "catch_up" in rec else None
        if "catch_up" in rec and why is None:
            body["catch_up"] = rec["catch_up"]  # §16.5 rule 4: close's own catch-up of the approved head
        else:
            reasons.append(f"the PR head {head[:12]} is not the approved head {recorded_head[:12]}: "
                           "a push after the verdict needs a new verdict (re-verify packet)"
                           + (f"; the record's catch-up does not cover it: {why}" if why else ""))
    body["gate_runs"] = _gate_runs(rec)
    when, how = recorded_at(queue, path)
    body["recorded"] = how
    if when is None:
        reasons.append(how)
    else:
        body["recorded_at"] = _iso(when)
        checked = _parse_dt(rec.get("checked_at"))
        if checked is not None and checked > when + SKEW:
            reasons.append(f"checked_at {rec.get('checked_at')} is after the record was recorded "
                           f"({_iso(when)}): checked_at is the clock time the verdict was reached")
    state = str(facts.get("state") or "")
    if state != "OPEN":
        merged = _parse_dt(facts.get("mergedAt"))
        when_s = f" at {_iso(merged)}" if merged else ""
        order = ""
        if merged and when:
            order = f"; the approval was recorded {'before' if when <= merged else 'after'} it"
        reasons.append(f"PR {pr} is {state.lower() or 'not open'}{when_s}{order}")
    body["unrun_checks"] = [c.get("dod_check_id") for c in rec.get("checks") or []
                            if isinstance(c, dict) and c.get("ran", True) is False]
    body["head_sha"] = recorded_head
    if not reasons:
        body["match_head_commit"] = head  # the PR's full head, which the approval names
    return reasons, body


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
    rec = {**rec, "catch_up": catch_up, "schema_version": max(RECORD_VERSION, was if _is(was, "integer") else 0)}
    errs = record_errors(rec)
    if errs:
        raise ValueError("; ".join(errs))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return path


def _note_run(cfg: Config, queue: Path, rec: dict[str, Any]) -> str | None:
    """§10.3: the verdict on the task's open verify run, and a `verify/recorded` event. The verifier's
    `ccp report` closes the run. A verdict with no open run (a PR that is not a task's, a record
    written before the toolkit) is still recorded; it only has no run to note."""
    from ccp import runs  # noqa: PLC0415
    from ccp.queue import QueueError, emit  # noqa: PLC0415

    try:
        run = runs.latest_open(queue, str(rec["task_id"]), "verify")
        if run is None:
            return None
        run.update(verdict=rec["verdict"], head=rec.get("head_sha"), verdict_at=rec.get("checked_at"))
        runs.save(queue, run)
        emit(queue, cfg, str(rec["task_id"]), "verify", "recorded",
             {"run_id": run["run_id"], "verdict": rec["verdict"], "head_sha": rec.get("head_sha") or ""}, "task-verifier")
        return run["run_id"]
    except QueueError as exc:
        print(f"ccp verify record: the verdict is written; noting it on its run failed: {exc}", file=sys.stderr)
        return None


def _queue() -> Path | None:
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        print("ccp verify: set QUEUE_ROOT to this project's runtime queue", file=sys.stderr)
        return None
    return Path(q)


def main(cfg: Config, a: Any) -> int:
    queue = _queue()
    if queue is None:
        return 2
    if a.action == "record":
        try:
            rec = json.loads(sys.stdin.read() if a.target == "-" else Path(a.target).read_text())
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ccp verify record: {exc}", file=sys.stderr)
            return 2
        errs = fill_gate(queue, rec) if isinstance(rec, dict) else []
        errs = errs or (cache_errors(cfg, rec) if isinstance(rec, dict) else [])
        errs = errs or (review_errors(queue, rec) if isinstance(rec, dict) else [])
        errs = errs or (adr_errors(cfg, rec) if isinstance(rec, dict) else [])
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
        if not str(a.target or "").isdigit():
            print("ccp verify merge-ok: give the PR number", file=sys.stderr)
            return 2
        try:
            reasons, body = merge_ok(cfg, queue, a.target, a.task)
        except NoGh as exc:
            print(f"ccp verify: {exc}", file=sys.stderr)
            return 2
        body = {"ok": not reasons, **body, **({"reasons": reasons} if reasons else {})}
        for r in reasons:
            print(f"ccp verify merge-ok: {r}", file=sys.stderr)
        print(json.dumps(body, indent=2))
        return 1 if reasons else 0
    if not str(a.head or "").strip():
        print("ccp verify: --head is the PR head the runner would merge", file=sys.stderr)
        return 2
    reason = refusal(queue, a.target, a.head)
    if reason:
        print(f"ccp verify: {reason}", file=sys.stderr)
        print(json.dumps({"ok": False, "task_id": a.target, "reason": reason}, indent=2))
        return 1
    print(json.dumps({"ok": True, "task_id": a.target, "head_sha": a.head}, indent=2))
    return 0
