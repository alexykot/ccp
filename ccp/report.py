"""`ccp report <run_id> FILE` (SPEC §10): a worker submits its report, and the run closes.

The report is the worker's own words plus a few lines `ccp` reads:

- `Outcome: done|blocked|failed`, always;
- implement, fix, merge and ruling, when done: `PR: #<n>` and `Head: <sha>`;
- review, when done: `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>`, and a `## Spec beyond intent`
  section (§3.5): a `- ` line for each passage of normative text the PR adds or changes that the task's
  brief and its ADRs do not call for, or the single line `none`; the run keeps only their count
  (`spec_beyond_intent`);
- a review with `mode: resolution` (a resolution review of a conflicted integration merge, §13.2), when done:
  `Resolution: contained` or `Resolution: beyond <why>`, and `Affected checks: <id>, <id>` (or `none`), each id one
  of the task file's dod_check ids; a report missing either line, or naming an unknown id, is refused
  (exit 1, nothing written), and the run keeps `resolution` and `affected_checks`;
- verify, when done: `Verdict: approve|reject` and `Head: <sha>`;
- `Suite: <n> tests, <s> s`, when the worker ran the full suite; it may end `ran <r>, cached <c>`
  (or `<r> modules ran, <c> cached`),
  the units that ran and those a product's content-keyed test cache reported as hits. A
  verify report on a product whose plane.json sets `verify.accept_cache` must give them (§15.3).
  `Suite: from <suite_id>` takes them from that recorded `ccp suite run` of this run, and a report
  with no `Suite:` line gets them from the run's latest `full` or `gate` lane run when it passed
  (after a failed one, a warning and nothing filled; a failed run's numbers never reach `ccp health`
  from the record) (§14.1);
- a `## Friction` section: `- ` lines, or `none`;
- `Prompt: <token>`, always, the token on the last line of the run's prompt (`Prompt end: <token>`, §13.2).
  A report with none, or with another token, is refused (exit 2) naming the run's: the prompt the worker
  read was probably cut. A run opened before the token (none recorded on it) is not held to it;
- implement, fix, merge and ruling, when done, with a `Head:`: the plane computes the round's integration merges
  from git and keeps them on the run (`integration_merges`, `before_review`; `round_merges`, §11.1, §27.1); a
  round it cannot measure keeps none, and the report is never refused for it;
- implement, fix, merge and ruling, when done: each verdict the product declares in plane.json
  `report.required_fields`, as `<name>: <value>` with one of its declared values, on one line (§13.4). They are
  kept on the run (`fields`) and shown in the review prompt; whether a verdict is right is not judged.

A report that lacks one is refused with what is missing, and nothing is written. An accepted one
is stored at the run's report path, its friction lines are recorded for `ccp health` (what the
runner used to copy by hand, §27.2), and the run is closed. The `Suite:` line's numbers are kept on
the run: they are the worker's statement. What `ccp health` gets, for a report whose outcome is done
(a verify: approve), is the run's recorded `ccp suite` runs, each filed under its kind (cold, warm, part, unverified; `health.file_suites`); only a run with
no suite record falls back to the line. A `Suite:` line with no `ccp suite run` recorded against the
run is a warning, never a refusal (§14.1).

A run already reported takes a corrected report while no later run of its task has opened (§13.4,
`runs.opened_after`): nothing has acted on it yet. The correction is checked like a first report; the
stored one is kept beside it as `<stem>.superseded-<k>.md`, the run's `corrections` gets `{at, superseded}`,
its report fields are the corrected report's, and the `run reported` event (`corrected: true`) and a
review's `review recorded` event are written again. Its friction lines and suite filing are not recorded
again: those are the first submission's.
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
BEYOND_RE = re.compile(r"^##\s+(?:Spec beyond intent|spec_beyond_intent)[ \t]*\r?$", re.I | re.M)  # §3.5
FIELD_PHASES = runs.CHANGE_PHASES  # §13.4: the rounds that push a head (PR, Head) and state the declared verdicts
RESOLUTION_RE = re.compile(r"^[^\w\n]*Resolution[ \t*_]*:[ \t*_`]*(.*?)[ \t]*\r?$", re.I | re.M)  # §13.4
AFFECTED_RE = re.compile(r"^[^\w\n]*Affected checks[ \t*_]*:[ \t*_`]*(.*?)[ \t]*\r?$", re.I | re.M)  # §13.4
PROMPT_RE = re.compile(r"^[^\w\n]*Prompt[*_]*:[\s*_`]*([0-9A-Za-z]+)", re.M)  # §13.4: the prompt's token, repeated


def prompt_error(q: Path, rec: dict[str, Any], text: str) -> str | None:
    """§13.4: why a report does not repeat its run's prompt token (`Prompt: <token>`), naming the token
    and where the prompt's last line carries it; None when it does, or when the run records no token
    (opened before the token was)."""
    want = str(rec.get("prompt_token") or "")
    if not want:
        return None
    m = PROMPT_RE.search(text)
    if m and m.group(1).lower() == want.lower():
        return None
    from ccp.prompt import prompt_path  # noqa: PLC0415
    prompt = prompt_path(q, rec["run_id"])
    said = f"says `Prompt: {m.group(1)}`" if m else "has no `Prompt: <token>` line"
    return (f"report refused, nothing written: it {said}; this run's prompt ends `Prompt end: {want}` ({prompt}), "
            f"so the report says `Prompt: {want}`. The prompt you read was probably cut before its end: tell the "
            "runner, which launches you again with the prompt file (SPEC §13.4)")


def fields(text: str, declared: list[dict[str, Any]]) -> tuple[dict[str, str], list[str]]:
    """§13.4: each declared verdict's line, `<name>: <value>` (the name without regard to case, bold
    or a bullet allowed), its value one of the declared values (the longest that fits, then the
    line's end or a non-word character, so a reason may follow). The values found, by declared name
    and spelling, and an error naming the field, its line and its allowed values for each missing or
    other one. A value followed by `|` is the prompt's `a|b` template pasted, not a verdict, and is
    refused, as is a value followed by `/`, `,` or the word `or` and then another of the field's declared
    values (the template in another spelling: `a or b`, `a / b`, `a, b`, and the longer forms such as
    `a, b or c`); a reason after a comma or a slash is not one, even one that starts with another declared
    value (`yes, no downtime needed`). So is a field stated on more than one line, naming each line."""
    got: dict[str, str] = {}
    errs: list[str] = []
    for f in declared:
        name, values = f["name"], list(f["values"])
        allowed = ", ".join(f"`{v}`" for v in values)
        ms = list(re.finditer(rf"^[^\w\n]*{re.escape(name)}[ \t*_]*:[ \t*_`]*(.*?)[ \t]*\r?$", text, re.I | re.M))
        if not ms:
            errs.append(f"no `{name}: <value>` line: this product requires it on every implementer report, "
                        f"one of {allowed} (plane.json report.required_fields)")
            continue
        if len(ms) > 1:
            where = ", ".join(f"line {_line_no(text, m)} (`{m.group(1)[:80]}`)" for m in ms)
            errs.append(f"`{name}:` is stated on {len(ms)} lines, {where}; state it once "
                        "(plane.json report.required_fields)")
            continue
        m = ms[0]
        said = m.group(1)
        hit = next((v for v in sorted(values, key=len, reverse=True)
                    if said.lower().startswith(v.lower()) and not re.match(r"\w", said[len(v):len(v) + 1])), None)
        if hit is not None and _template(said[len(hit):], [v for v in values if v.lower() != hit.lower()]):
            hit = None  # the template's alternatives, `a|b` or another spelling, pasted as they stand
        if hit is None:
            errs.append(f"`{name}:` on line {_line_no(text, m)} says `{said[:80]}`; the allowed values are "
                        f"{allowed}, exactly one (plane.json report.required_fields)")
        else:
            got[name] = hit
    return got, errs


ALT_RE = re.compile(r"[ \t*_`]*(?:/|,|or\b)[ \t*_`]*", re.I)  # `a / b`, `a, b`, `a or b`: the template respelled


def _template(rest: str, others: list[str]) -> bool:
    """§13.4: is `rest`, what follows a declared value on its field's line, the rest of the template
    pasted rather than a reason: a `|`, or a `/`, `,` or `or` followed by another declared value (`others`)
    that ends there or at a non-word character, and so on for a longer template (`a, b or c`), with no
    words after the last value? Words there make it a reason that starts with another declared value
    (`yes, no downtime needed`); a `|` between the values makes it the template whatever follows."""
    if rest.lstrip(" \t*_`").startswith("|"):
        return True
    joined = False
    while (m := ALT_RE.match(rest) or PIPE_RE.match(rest)) and (v := _value_at(rest[m.end():], others)):
        if "|" in m.group(0):
            return True
        rest, joined = rest[m.end() + len(v):], True
    return joined and not re.search(r"\w", rest)


PIPE_RE = re.compile(r"[ \t*_`]*\|[ \t*_`]*")  # `a | b`: the template's own joint, between later values too


def _value_at(tail: str, values: list[str]) -> str | None:
    """The longest of `values` that `tail` starts with, ending there or at a non-word character."""
    return next((v for v in sorted(values, key=len, reverse=True)
                 if tail.lower().startswith(v.lower()) and not re.match(r"\w", tail[len(v):len(v) + 1])), None)


def _line_no(text: str, m: re.Match[str]) -> int:
    """The 1-based line of the report a field's match starts on."""
    return text.count("\n", 0, m.start(1)) + 1


def cache_counts(line: str) -> tuple[int, int] | None:
    """A `Suite:` line's units (ran, cached), in either wording; None when it gives none."""
    c = SUITE_CACHE_RE.search(line)
    if not c:
        return None
    ran, cached = (c.group(1), c.group(2)) if c.group(1) is not None else (c.group(3), c.group(4))
    return int(ran), int(cached)


def friction(text: str, heading: re.Pattern[str] = FRICTION_RE) -> list[str] | None:
    """The Friction section's lines (or another section of the same shape, `heading`: `- ` lines, or the
    single line `none`); None when the section is missing or says nothing usable."""
    m = heading.search(text)
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


def resolution_lines(text: str, checks: list[str] | None) -> tuple[dict[str, Any], list[str]]:
    """§13.4: a resolution review's `Resolution:` (`contained`, or `beyond` and why) and `Affected checks:` (dod_check
    ids, comma-separated, or `none`) lines. The values found (`resolution`, `affected_checks`) and an error for each
    line missing, stated twice, or unreadable, or an id that is not in `checks` (the task file's, when given)."""
    out: dict[str, Any] = {}
    errs: list[str] = []
    ms = list(RESOLUTION_RE.finditer(text))
    if not ms:
        errs.append("no `Resolution: contained` or `Resolution: beyond <why>` line: a resolution review says whether the "
                    "resolution stays within the conflict hunks")
    elif len(ms) > 1:
        errs.append(f"`Resolution:` is stated on {len(ms)} lines, "
                    + ", ".join(f"line {_line_no(text, m)} (`{m.group(1)[:80]}`)" for m in ms) + "; state it once")
    else:
        said = ms[0].group(1)
        m = re.match(r"(contained|beyond)\b(.*)$", said, re.I)
        if not m or re.match(r"[ \t*_`]*\|", m.group(2)):  # a `|` right after the value: the prompt's template pasted
            errs.append(f"`Resolution:` on line {_line_no(text, ms[0])} says `{said[:80]}`; it is `contained`, or "
                        "`beyond <why>`, exactly one")
        else:
            out["resolution"] = m.group(1).lower()
    am = list(AFFECTED_RE.finditer(text))
    if not am:
        errs.append("no `Affected checks: <id>, <id>` or `Affected checks: none` line: a resolution review names the "
                    "task's dod_checks the resolution can affect")
    elif len(am) > 1:
        errs.append(f"`Affected checks:` is stated on {len(am)} lines, "
                    + ", ".join(f"line {_line_no(text, m)} (`{m.group(1)[:80]}`)" for m in am) + "; state it once")
    else:
        said = am[0].group(1)
        if re.sub(r"[\s`*_.]", "", said).lower() == "none":
            out["affected_checks"] = []
        else:
            ids = list(dict.fromkeys(t for t in (x.strip("`*_.") for x in re.split(r"[,\s]+", said)) if t))
            unknown = [i for i in ids if checks is not None and i not in checks]
            if not ids:
                errs.append(f"`Affected checks:` on line {_line_no(text, am[0])} is empty: name the task's dod_check ids, "
                            "or `none`")
            elif unknown:
                errs.append(f"`Affected checks:` names {', '.join(f'`{i}`' for i in unknown)}, which "
                            f"{'is' if len(unknown) == 1 else 'are'} not a dod_check of the task "
                            f"({', '.join(checks or []) or 'it has none'})")
            else:
                out["affected_checks"] = ids
    return out, errs


def parse(phase: str, text: str, accept_cache: bool = False,
          declared: list[dict[str, Any]] | None = None, mode: str | None = None,
          checks: list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    errs: list[str] = []
    out: dict[str, Any] = {}
    m = OUTCOME_RE.search(text)
    if not m:
        errs.append("no `Outcome: done|blocked|failed` line")
    else:
        out["outcome"] = m.group(1).lower()
    done = out.get("outcome") == "done"
    if phase in (*FIELD_PHASES, "verify"):
        h = HEAD_RE.search(text)
        if h:
            out["head"] = h.group(1)
        elif done:
            errs.append("no `Head: <sha>` line")
    if phase in FIELD_PHASES:
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
        beyond = friction(text, BEYOND_RE)
        if beyond is not None:
            out["spec_beyond_intent"] = len(beyond)
        elif done:
            errs.append("no `## Spec beyond intent` section: a `- ` line for each passage of normative text (SPEC, "
                        "contract) the PR adds or changes that the task's brief and its ADRs do not call for, or the "
                        "single line `none` (SPEC §3.5)")
    if phase == "review" and mode == "resolution" and done:
        got, rerrs = resolution_lines(text, checks)
        out.update(got)
        errs += rerrs
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
    if phase in FIELD_PHASES and done and declared:
        out["fields"], ferrs = fields(text, declared)
        errs += ferrs
    fr = friction(text)
    if fr is None:
        errs.append("no `## Friction` section of `- ` lines, or the single line `none`")
    else:
        out["friction"] = fr
    return out, errs


# The run record's fields a report's lines give (§13.4); a correction replaces them all.
PARSED_KEYS = ("pr", "head", "verdict", "severity", "spec_beyond_intent", "suite_tests", "suite_seconds", "suite_ran",
               "suite_cached", "suite_from", "suite_filled", "fields", "resolution", "affected_checks")


# The run record's fields the plane computes at submit (§11.1); a correction computes them again.
COMPUTED_KEYS = ("integration_merges", "before_review")


def before_review(runs_of_task: list[dict[str, Any]], rec: dict[str, Any]) -> bool:
    """§11.1: whether the round `rec` opened before its task's first review run that reported done (a tie in
    `opened_at`, one second's resolution, counts the round as after, as `runs.unreviewed_fix` does). A task with
    no such review yet has every round before review."""
    first = next((r for r in runs_of_task if r.get("phase") == "review" and runs.state(r) == "reported"
                  and r.get("outcome") == "done"), None)
    return first is None or str(rec.get("opened_at") or "") < str(first.get("opened_at") or "")


def round_merges(cfg: Config, q: Path, rec: dict[str, Any], head: str) -> list[dict[str, Any]] | None:
    """§11.1, §27.1: the integration merges of a done change round that reported `head`: the merge commits on the
    head's first-parent line in `<the task's previous done change round's reported head>..<head>` (for its first
    such round, `origin/<integration>..<head>`) whose second parent is an ancestor of `origin/<integration>`, each
    as `{sha, conflicted, files}` (the count of conflicted files, never their names), oldest first. Whether one
    conflicted is `gitmerge.probe` of its first and second parents: the merge git would make on its own, so a
    recorded resolution does not hide it. Nothing is fetched. An empty list: none found. None: it could not be
    measured (no product checkout, a head, a previous head or the integration tip not in the object store, a git
    call that failed, a probe git could not run), so the run records none (never a refusal)."""
    from ccp import gitmerge, queue  # noqa: PLC0415
    repo = cfg.root
    if not repo.is_dir():
        return None

    def rev(ref: str) -> str | None:
        r = queue.git(repo, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None

    integ = rev(f"origin/{queue.integration_branch(q)}")
    tip = rev(head)
    if integ is None or tip is None:
        return None
    rs = [r for r in runs.all_runs(q, str(rec["task_id"])) if runs.state(r) != "abandoned"]
    prior = [r for r in rs if r.get("run_id") != rec.get("run_id") and r.get("phase") in runs.CHANGE_PHASES
             and runs.state(r) == "reported" and r.get("outcome") == "done" and r.get("head")
             and str(r.get("opened_at") or "") <= str(rec.get("opened_at") or "")]
    base = rev(str(prior[-1]["head"])) if prior else integ
    if base is None:
        return None
    found = queue.git(repo, "rev-list", "--merges", "--first-parent", "--topo-order", "--reverse", f"{base}..{tip}")
    if found.returncode != 0:
        return None
    out: list[dict[str, Any]] = []
    for sha in found.stdout.split():
        ids = queue.git(repo, "rev-list", "--parents", "-n", "1", sha).stdout.split()
        if len(ids) < 3:
            return None
        anc = queue.git(repo, "merge-base", "--is-ancestor", ids[2], integ)
        if anc.returncode == 1:
            continue  # a merge of something else (not the integration branch)
        if anc.returncode != 0:
            return None
        p = gitmerge.probe(repo, ids[1], ids[2])
        if p.failed:
            return None
        out.append({"sha": sha, "conflicted": p.returncode == 1, "files": len(p.conflicts)})
    return out


def _supersede(src: Path, dest: Path) -> Path | None:
    """§13.4: keep the stored report `dest` beside it as `<stem>.superseded-<k>.md`, `k` the first free
    from 1, before a correction replaces it. None when there is nothing earlier to keep: the corrected
    file is the stored one, edited in place, or no report is stored."""
    if not dest.is_file() or src.resolve() == dest.resolve():
        return None
    k = 1
    while (kept := dest.with_name(f"{dest.stem}.superseded-{k}{dest.suffix}")).exists():
        k += 1
    shutil.copyfile(dest, kept)
    return kept


def submit(cfg: Config, run_id: str, file: str) -> dict[str, Any]:
    q = root()
    rec = runs.load(q, run_id)
    state = runs.state(rec)
    if state == "abandoned":
        raise QueueError(f"{run_id} is already {state}: a new launch needs a new run (ccp prompt)", 1)
    correcting = state == "reported"  # §13.4: a correction, while nothing has acted on the report
    if correcting and (later := runs.opened_after(q, rec)):
        raise QueueError(f"{run_id} is already reported, and a later run of its task, {later['run_id']}, has opened "
                         "since: the runner may have acted on the report, so it is not corrected (SPEC §13.4). "
                         "Tell the runner what changed", 1)
    src = Path(file)
    if not src.is_file():
        raise QueueError(f"{file}: no such report file", 2)
    text = src.read_text()
    cut = prompt_error(q, rec, text)
    if cut:
        raise QueueError(cut, 2)
    from ccp.verify import cache_rule  # noqa: PLC0415
    checks = None
    if rec["phase"] == "review" and rec.get("mode") == "resolution":  # §13.4: ids are checked against the task file's
        from ccp.queue import task_meta  # noqa: PLC0415
        checks = [str(c) for c in task_meta(cfg, str(rec["task_id"])).get("_checks") or []]
    parsed, errs = parse(rec["phase"], text, accept_cache=bool(cache_rule(cfg)),
                         declared=(cfg.report or {}).get("required_fields") or [], mode=rec.get("mode"), checks=checks)
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
    warnings = list(fill_warnings)
    if correcting:
        superseded = _supersede(src, dest)
        if superseded is None:
            warnings.append(f"the corrected report is the stored one ({dest}), edited in place: the earlier report "
                            "was overwritten before this correction, so none is kept as superseded")
        rec["corrections"] = [*(rec.get("corrections") or []),
                              {"at": iso(), "superseded": str(superseded) if superseded else None}]
        for k in COMPUTED_KEYS:  # computed again below, from the corrected head
            rec.pop(k, None)
        for k in PARSED_KEYS:  # the run's figures are the corrected report's, none left from the earlier one
            if not (rec["phase"] == "verify" and k in ("verdict", "head")):  # those are `ccp verify record`'s
                rec.pop(k, None)
    if src.resolve() != dest.resolve():
        shutil.copyfile(src, dest)
    tid = rec["task_id"]
    # §27.2: the run's recorded suite runs, each under its kind; the line only when none is recorded.
    # Only a finished piece of work counts: outcome done, and for a verify, approve. A correction files
    # nothing again: the suite filing and the friction lines are the first submission's (§13.4).
    if not correcting and parsed.get("outcome") == "done" and parsed.get("verdict") != "reject":
        line = SUITE_ANY_RE.search(text)
        health.file_suites(cfg, q, run_id, tid, parsed, line.group(0) if line else None)
    for line in [] if correcting else parsed.get("friction") or []:
        health.add_note(q, line, tid, rec["seat"], "worker")
    try:
        from ccp import suite  # noqa: PLC0415
        got = suite.recorded_for(q, run_id)
        rec.update(suite_runs_recorded=got["suite_runs"], suite_s_recorded=got["suite_s"])
        if "suite_tests" in parsed and not got["suite_runs"]:
            warnings.append(f"the report has a Suite: line, but no suite run is recorded for {run_id}: run every "
                            f"suite through `ccp suite run --run {run_id} --lane <name> -- <command>` (SPEC §14.1)")
    except Exception:  # noqa: BLE001  (a cross-check never refuses a report)
        pass
    if not correcting:  # a correction keeps the time the run closed: its figures change, not its timing
        rec["reported_at"] = iso()
    if rec["phase"] in FIELD_PHASES and parsed.get("outcome") == "done" and parsed.get("head"):
        rec["before_review"] = before_review(runs.all_runs(q, tid), rec)  # §11.1, §27.1
        try:  # a failed measurement records none: health counts the round unmeasured, the report is not refused
            merges = round_merges(cfg, q, rec, str(parsed["head"]))
        except Exception:  # noqa: BLE001
            merges = None
        if merges is not None:
            rec["integration_merges"] = merges
    rec.update(outcome=parsed["outcome"], report=str(dest), friction_count=len(parsed.get("friction") or []),
               **{k: parsed[k] for k in PARSED_KEYS if k in parsed})
    runs.save(q, rec)
    emit(q, cfg, tid, "run", "reported",
         {"run_id": run_id, "outcome": rec["outcome"], **({"corrected": True} if correcting else {})}, _actor_for(rec["seat"]))
    if rec["phase"] == "review" and "severity" in parsed:
        verdict = "changes" if parsed["severity"]["BLOCKER"] or parsed["severity"]["MAJOR"] else "clean"
        emit(q, cfg, tid, "review", "recorded", {"run_id": run_id, "verdict": verdict, "severity": parsed["severity"]},
             _actor_for(rec["seat"]))
    return {"ok": True, "run_id": run_id, "report": str(dest), **{k: v for k, v in rec.items() if k in (
        "outcome", "pr", "head", "verdict", "severity", "spec_beyond_intent", "suite_tests", "suite_seconds",
        "suite_ran", "suite_cached", "resolution", "affected_checks",
        "suite_from", "suite_filled", "friction_count", "fields",
        "suite_runs_recorded", "suite_s_recorded", "corrections")}, **({"warnings": warnings} if warnings else {})}


def _actor_for(seat: str) -> str:
    # The ledger's actors are seats; the verifier has its own id, the other workers act for the runner (§23.7).
    return "task-verifier" if seat == "verifier" else "task-runner"
