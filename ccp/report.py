"""`ccp report <run_id> FILE` (SPEC §10): a worker submits its report, and the run closes.

The report is the worker's own words plus a few lines `ccp` reads:

- `Outcome: done|blocked|failed`, always;
- implement and fix, when done: `PR: #<n>` and `Head: <sha>`;
- review, when done: `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>`;
- verify, when done: `Verdict: approve|reject` and `Head: <sha>`;
- `Suite: <n> tests, <s> s`, when the worker ran the full suite; it may end `ran <r>, cached <c>`
  (or `<r> modules ran, <c> cached`),
  the units that ran and those a product's content-keyed test cache reported as hits. A
  verify report on a product whose plane.json sets `verify.accept_cache` must give them (§15.3).
  `Suite: from <suite_id>` takes them from that recorded `ccp suite run` of this run, and a report
  with no `Suite:` line gets them from the run's latest `full` or `gate` lane run when it passed
  (after a failed one, a warning and nothing filled; a failed run's numbers never reach `ccp health`
  from the record) (§14.1);
- a `## Friction` section: `- ` lines, or `none`.

A report that lacks one is refused with what is missing, and nothing is written. An accepted one
is stored at the run's report path, its friction lines are recorded for `ccp health` (what the
runner used to copy by hand, §27.2), and the run is closed. The `Suite:` line's numbers are kept on
the run: they are the worker's statement. What `ccp health` gets, for a report whose outcome is done
(a verify: approve), is the run's recorded `ccp suite` runs, each filed under its kind (cold, warm, part, unverified; `health.file_suites`); only a run with
no suite record falls back to the line. A `Suite:` line with no `ccp suite run` recorded against the
run is a warning, never a refusal (§14.1).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from ccp import health, runs
from ccp.config import Config, lane_for
from ccp.queue import QueueError, emit, iso, root

# The line patterns lead with `[^\w\n]*` (a bullet, bold markers), not `\W*`: under re.M `\W` also
# matches a newline, so a blank line above `Suite:` began the match there and lost the line's counts.
# `Suite:` may be bold to the colon (`**Suite:** 40 tests, …`), and a report may have CRLF line endings.
OUTCOME_RE = re.compile(r"^[^\w\n]*Outcome:\W*(done|blocked|failed)\b", re.I | re.M)
PR_RE = re.compile(r"^[^\w\n]*PR:\W*#?(\d+)\b", re.I | re.M)
HEAD_RE = re.compile(r"^[^\w\n]*Head:\W*([0-9a-f]{7,40})\b", re.I | re.M)
VERDICT_RE = re.compile(r"^[^\w\n]*Verdict:\W*(approve|reject)\b", re.I | re.M)
SEVERITY_RE = re.compile(r"^[^\w\n]*Severity:(.*)$", re.I | re.M)
SEV_PART_RE = re.compile(r"\b(BLOCKER|MAJOR|MINOR|NIT)\s*=\s*(\d+)", re.I)
SUITE_RE = re.compile(r"^[^\w\n]*Suite:[\s*_]*(\d+)\s*tests?\s*,\s*(\d+(?:\.\d+)?)\s*s\b", re.I | re.M)
# `ran 3, cached 90` (§14.1), or the older wording `57 modules ran, 3 cached`
SUITE_CACHE_RE = re.compile(r"\bran\s+(\d+)\s*,\s*cached\s+(\d+)\b|\b(\d+)\s+modules?\s+ran\s*,\s*(\d+)\s+cached\b", re.I)
SUITE_FROM_RE = re.compile(r"^[^\w\n]*Suite:[\s*_]*from\s+(st-[A-Za-z0-9-]+)", re.I | re.M)
SUITE_ANY_RE = re.compile(r"^[^\w\n]*Suite:.*$", re.I | re.M)
AUTO_ROLES = ("full", "gate")  # a report with no Suite: line takes its run's latest of these roles' lanes (§14.1)
FRICTION_RE = re.compile(r"^##\s+Friction[ \t]*\r?$", re.M)


def cache_counts(line: str) -> tuple[int, int] | None:
    """A `Suite:` line's units (ran, cached), in either wording; None when it gives none."""
    c = SUITE_CACHE_RE.search(line)
    if not c:
        return None
    ran, cached = (c.group(1), c.group(2)) if c.group(1) is not None else (c.group(3), c.group(4))
    return int(ran), int(cached)


def friction(text: str) -> list[str] | None:
    """The Friction section's lines; None when the section is missing or says nothing usable."""
    m = FRICTION_RE.search(text)
    if not m:
        return None
    nxt = re.search(r"^#{1,2}\s", text[m.end():], re.M)
    body = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    lines = [raw for raw in body.splitlines() if raw.strip()]
    if len(lines) == 1 and re.sub(r"^[-*]\s+", "", lines[0].strip()).rstrip(".").strip().lower() == "none":
        return []
    items: list[str] = []
    for raw in lines:
        ln = raw.strip()
        if ln[:2] in ("- ", "* ") and ln[2:].strip():
            items.append(ln[2:].strip())
        elif raw[:1] in (" ", "\t") and items:  # a wrapped bullet: its continuation line
            items[-1] += " " + ln
        else:
            return None
    if any(re.sub(r"[.\s]+$", "", i).lower() == "none" for i in items):
        return None  # "none" beside real items is a contradiction, not a note
    return items or None


NO_CACHE_COUNTS = ("the `Suite:` line gives no `ran <r>, cached <c>`: this product accepts its test cache's hits "
                   "(plane.json verify.accept_cache), so say how many units ran and how many were cached")


def _from_suite(row: dict[str, Any]) -> dict[str, Any]:
    """A report's suite numbers from a recorded `ccp suite run`."""
    sec = float(row.get("seconds") or 0)
    out: dict[str, Any] = {"suite_tests": int(row["tests"]), "suite_seconds": round(sec) if sec >= 10 else round(sec, 1)}
    if row.get("ran") is not None and row.get("cached") is not None:  # suite.fold maps a pre-contract row's names
        out["suite_ran"], out["suite_cached"] = int(row["ran"]), int(row["cached"])
    return out


def fill_suite(q: Path, run_id: str, phase: str, parsed: dict[str, Any], accept_cache: bool,
               auto_lanes: tuple[str, ...] = AUTO_ROLES) -> tuple[list[str], list[str]]:
    """§14.1: `Suite: from <suite_id>` takes the numbers from that recorded run, which must be this
    run's and have ended with a test count. With no `Suite:` line at all, the run's latest ended
    `full` or `gate` lane run with a count fills it in (`suite_filled: auto`), only when it passed:
    after a failed one, nothing is filled and a warning says so. A hand-written line stays as
    written. Errors (a refusal) and warnings."""
    from ccp import suite  # noqa: PLC0415
    sid = parsed.get("suite_from")
    if sid is None and "suite_tests" in parsed:
        return [], []
    if "suite_unparsed" in parsed:  # the worker's line stays as written; nothing is filled over it
        return [], [f"the report's `{parsed['suite_unparsed']}` line is neither `Suite: <n> tests, <s> s` nor "
                    "`Suite: from <suite_id>`: no suite numbers were recorded from it"]
    try:
        rows = suite.fold(q)
    except Exception:  # noqa: BLE001  (a damaged suites file: nothing to fill from)
        rows = []
    ended = [r for r in rows if r.get("state") in ("passed", "failed", "interrupted")]
    if sid is not None:
        row = next((r for r in rows if r.get("suite_id") == sid), None)
        if row is None:
            return [f"`Suite: from {sid}`: no suite run {sid} is recorded (ccp suite list)"], []
        if row.get("run_id") != run_id:
            return [f"`Suite: from {sid}`: that suite run is recorded against {row.get('run_id') or 'no run'}, "
                    f"not {run_id}"], []
        if row not in ended or row.get("tests") is None:
            return [f"`Suite: from {sid}`: that suite run has not ended with a test count; "
                    "write `Suite: <n> tests, <s> s`"], []
        got = _from_suite(row)
        if phase == "verify" and accept_cache and "suite_ran" not in got:
            return [NO_CACHE_COUNTS + f" (suite run {sid} recorded none)"], []
        parsed.update(got, suite_filled="from", suite_passed=row.get("state") == "passed")
        return [], []
    mine = [r for r in ended if r.get("run_id") == run_id and r.get("lane") in auto_lanes and r.get("tests") is not None]
    if not mine:
        return [], []
    last = mine[-1]
    if last.get("state") != "passed":
        return [], [f"no `Suite:` line, and this run's latest {last.get('lane')} suite run ({last['suite_id']}) "
                    f"{last.get('state')} with exit {last.get('exit_code')}: nothing was filled in; write "
                    f"`Suite: <n> tests, <s> s` or `Suite: from <suite_id>`"]
    got = _from_suite(last)
    if not (phase == "verify" and accept_cache and "suite_ran" not in got):
        parsed.update(got, suite_from=last["suite_id"], suite_filled="auto", suite_passed=True)
    return [], []


def parse(phase: str, text: str, accept_cache: bool = False) -> tuple[dict[str, Any], list[str]]:
    errs: list[str] = []
    out: dict[str, Any] = {}
    m = OUTCOME_RE.search(text)
    if not m:
        errs.append("no `Outcome: done|blocked|failed` line")
    else:
        out["outcome"] = m.group(1).lower()
    done = out.get("outcome") == "done"
    if phase in ("implement", "fix", "verify"):
        h = HEAD_RE.search(text)
        if h:
            out["head"] = h.group(1)
        elif done:
            errs.append("no `Head: <sha>` line")
    if phase in ("implement", "fix"):
        p = PR_RE.search(text)
        if p:
            out["pr"] = p.group(1)
        elif done:
            errs.append("no `PR: #<number>` line")
    if phase == "verify":
        v = VERDICT_RE.search(text)
        if v:
            out["verdict"] = v.group(1).lower()
        elif done:
            errs.append("no `Verdict: approve|reject` line")
    if phase == "review":
        s = SEVERITY_RE.search(text)
        parts = {k.upper(): int(v) for k, v in SEV_PART_RE.findall(s.group(1))} if s else {}
        if set(parts) == {"BLOCKER", "MAJOR", "MINOR", "NIT"}:
            out["severity"] = parts
        elif done:
            errs.append("no `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>` line with all four counts")
    s = SUITE_RE.search(text)
    if s:
        out["suite_tests"] = int(s.group(1))
        sec = float(s.group(2))
        out["suite_seconds"] = int(sec) if sec.is_integer() else sec
        line = text[s.start():].split("\n", 1)[0]
        c = cache_counts(line)
        if c:
            out["suite_ran"], out["suite_cached"] = c
        elif phase == "verify" and accept_cache:
            errs.append(NO_CACHE_COUNTS)
    elif f := SUITE_FROM_RE.search(text):
        out["suite_from"] = f.group(1)
    elif u := SUITE_ANY_RE.search(text):
        out["suite_unparsed"] = u.group(0).strip()[:200]
    fr = friction(text)
    if fr is None:
        errs.append("no `## Friction` section of `- ` lines, or the single line `none`")
    else:
        out["friction"] = fr
    return out, errs


def submit(cfg: Config, run_id: str, file: str) -> dict[str, Any]:
    q = root()
    rec = runs.load(q, run_id)
    state = runs.state(rec)
    if state in ("reported", "abandoned"):
        raise QueueError(f"{run_id} is already {state}: a new launch needs a new run (ccp prompt)", 1)
    src = Path(file)
    if not src.is_file():
        raise QueueError(f"{file}: no such report file", 2)
    text = src.read_text()
    from ccp.verify import cache_rule  # noqa: PLC0415
    parsed, errs = parse(rec["phase"], text, accept_cache=bool(cache_rule(cfg)))
    fill_errs, fill_warnings = fill_suite(q, run_id, rec["phase"], parsed, bool(cache_rule(cfg)),
                                          tuple(lane_for(cfg, r) for r in AUTO_ROLES))
    errs += fill_errs
    if errs:
        raise QueueError("report refused, nothing written:\n  " + "\n  ".join(errs), 1)
    if parsed.get("friction") and any(health.looks_like_secret(f) for f in parsed["friction"]):
        raise QueueError("report refused: a Friction line looks like it holds a secret; say it without the value", 1)
    if rec["phase"] == "verify" and rec.get("verdict") and parsed.get("outcome") == "done":
        from ccp.verify import heads_match  # noqa: PLC0415
        if parsed.get("verdict") != rec["verdict"] or not heads_match(str(parsed.get("head") or ""), str(rec.get("head") or "")):
            raise QueueError(f"report refused, nothing written: it says {parsed.get('verdict')} at "
                             f"{str(parsed.get('head'))[:12]}, the recorded verdict is {rec['verdict']} at "
                             f"{str(rec.get('head'))[:12]} (ccp verify record)", 1)
    dest = runs.report_path(q, run_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    tid = rec["task_id"]
    # §27.2: the run's recorded suite runs, each under its kind; the line only when none is recorded.
    # Only a finished piece of work counts: outcome done, and for a verify, approve.
    if parsed.get("outcome") == "done" and parsed.get("verdict") != "reject":
        line = SUITE_ANY_RE.search(text)
        health.file_suites(cfg, q, run_id, tid, parsed, line.group(0) if line else None)
    for line in parsed.get("friction") or []:
        health.add_note(q, line, tid, rec["seat"], "worker")
    warnings = list(fill_warnings)
    try:
        from ccp import suite  # noqa: PLC0415
        got = suite.recorded_for(q, run_id)
        rec.update(suite_runs_recorded=got["suite_runs"], suite_s_recorded=got["suite_s"])
        if "suite_tests" in parsed and not got["suite_runs"]:
            warnings.append(f"the report has a Suite: line, but no suite run is recorded for {run_id}: run every "
                            f"suite through `ccp suite run --run {run_id} --lane <name> -- <command>` (SPEC §14.1)")
    except Exception:  # noqa: BLE001  (a cross-check never refuses a report)
        pass
    rec.update(reported_at=iso(), outcome=parsed["outcome"], report=str(dest),
               friction_count=len(parsed.get("friction") or []),
               **{k: parsed[k] for k in ("pr", "head", "verdict", "severity", "suite_tests", "suite_seconds", "suite_ran",
                                         "suite_cached", "suite_from", "suite_filled") if k in parsed})
    runs.save(q, rec)
    emit(q, cfg, tid, "run", "reported", {"run_id": run_id, "outcome": rec["outcome"]},
         _actor_for(rec["seat"]))
    if rec["phase"] == "review" and "severity" in parsed:
        verdict = "changes" if parsed["severity"]["BLOCKER"] or parsed["severity"]["MAJOR"] else "clean"
        emit(q, cfg, tid, "review", "recorded", {"run_id": run_id, "verdict": verdict, "severity": parsed["severity"]},
             _actor_for(rec["seat"]))
    return {"ok": True, "run_id": run_id, "report": str(dest), **{k: v for k, v in rec.items() if k in (
        "outcome", "pr", "head", "verdict", "severity", "suite_tests", "suite_seconds", "suite_ran", "suite_cached",
        "suite_from", "suite_filled", "friction_count",
        "suite_runs_recorded", "suite_s_recorded")}, **({"warnings": warnings} if warnings else {})}


def _actor_for(seat: str) -> str:
    # The ledger's actors are seats; the verifier has its own id, the other workers act for the runner (§23.7).
    return "task-verifier" if seat == "verifier" else "task-runner"
