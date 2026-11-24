"""`ccp report` (SPEC §10, §13.4): a worker submits its report, and the run closes.

The report is the worker's own words plus the lines and sections `ccp` reads. `SECTIONS` holds each of them: the
phases that carry it, when it is required, where it lands in the run's record, and the line the prompt asks for
it in (§13.4). The rules are in the SPEC: the report's lines, its corrections and its follow-ups (§13.4, ADR-0044
D1), the prompt's token (§13.2), the `Suite:` line and the suite runs it cites or is filled from (§14.1, §14.4),
the suite filing and friction notes for `ccp health` (§27.2), the round's integration merges (§11.1, §27.1), the
phase it moves the task to (§10.1) and the review record (§15.1).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Callable, NamedTuple

from ccp import followups, health, refs, runs
from ccp.config import WHOLE_SUITE_ROLES, Config, lane_for
from ccp.queue import QueueError, emit, iso, phase_move, read_json, root, seat_actor, write_json

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
FRICTION_RE = re.compile(r"^##\s+Friction[ \t]*\r?$", re.M)
FOLLOW_UPS_RE = re.compile(r"^##\s+Follow-ups[ \t]*\r?$", re.I | re.M)  # §13.4, ADR-0044 D1
FOLLOW_UPS_NEAR_RE = re.compile(r"^#+\s*follow.?ups\b", re.I | re.M)  # a heading `ccp report` does not read as it
BEYOND_RE = re.compile(r"^##\s+(?:Spec beyond intent|spec_beyond_intent)[ \t]*\r?$", re.I | re.M)  # §3.5
TESTS_RE = re.compile(r"^##\s+Tests for new behaviour[ \t]*\r?$", re.I | re.M)  # §13.4, §13.5
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


def friction(text: str, heading: re.Pattern[str] = FRICTION_RE, why: bool = False) -> list[str] | None:
    """The Friction section's lines (or another section of the same shape, `heading`: `- ` lines, or the
    single line `none`, which with `why` is a single line beginning `none` followed by why); None when the
    section is missing or says nothing usable."""
    m = heading.search(text)
    if not m:
        return None
    nxt = re.search(r"^#{1,2}\s", text[m.end():], re.M)
    body = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    lines = [raw for raw in body.splitlines() if raw.strip()]
    single = re.sub(r"^[-*]\s+", "", lines[0].strip()) if len(lines) == 1 else ""
    if single.rstrip(".").strip().lower() == "none" and not why:
        return []
    if why and re.match(r"none\b\W*\w", single, re.I):
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


def follow_ups(text: str) -> tuple[list[str], str | None]:
    """§13.4, ADR-0044 D1: the `## Follow-ups` section's lines, each a `- ` item (a wrapped item's indented
    continuation joins it), or the single line `none`; a missing or empty section reads as `none`. The lines,
    and None; or an error naming the first line that is neither, or a `none` beside items."""
    m = FOLLOW_UPS_RE.search(text)
    if not m:
        return [], None
    nxt = re.search(r"^#{1,2}\s", text[m.end():], re.M)
    body = text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]
    lines = [raw.rstrip("\r") for raw in body.splitlines() if raw.strip()]
    if len(lines) == 1 and re.sub(r"^-\s+", "", lines[0].strip()).rstrip(".").strip().lower() == "none":
        return [], None
    items: list[str] = []
    for raw in lines:
        ln = raw.strip()
        if ln[:2] == "- " and ln[2:].strip():
            items.append(ln[2:].strip())
        elif raw[:1] in (" ", "\t") and items:  # a wrapped item: its continuation line
            items[-1] += " " + ln
        else:
            return [], (f"the `## Follow-ups` section's line `{ln[:80]}` is neither a `- ` item nor the single line "
                        "`none`: write one `- ` line per follow-up, or `none` (SPEC §13.4)")
    if any(re.sub(r"[.\s]+$", "", i).lower() == "none" for i in items):
        return [], ("the `## Follow-ups` section says `none` beside follow-ups: write one `- ` line per follow-up, "
                    "or the single line `none` (SPEC §13.4)")
    return items, None


NO_CACHE_COUNTS = ("the `Suite:` line gives no `ran <r>, cached <c>`: this product accepts its test cache's hits "
                   "(plane.json verify.accept_cache), so say how many units ran and how many were cached")


def _from_suite(row: dict[str, Any]) -> dict[str, Any]:
    """A report's suite numbers from a recorded `ccp suite run`."""
    sec = float(row.get("seconds") or 0)
    out: dict[str, Any] = {"suite_tests": int(row["tests"]), "suite_seconds": round(sec) if sec >= 10 else round(sec, 1)}
    if row.get("ran") is not None and row.get("cached") is not None:  # suite.fold maps a pre-contract row's names
        out["suite_ran"], out["suite_cached"] = int(row["ran"]), int(row["cached"])
    return out


def judge_suite(rows: list[dict[str, Any]], run_id: str, phase: str, parsed: dict[str, Any], accept_cache: bool,
                auto_lanes: tuple[str, ...] = WHOLE_SUITE_ROLES
                ) -> tuple[list[str], list[str], dict[str, Any]]:
    """§14.1: what the report's suite line takes from the folded suite `rows` (`suite.fold`); reads and
    writes nothing. `Suite: from <suite_id>` takes the numbers from that recorded run, which must be this
    run's and have ended with a test count. With no `Suite:` line at all, the run's latest ended
    `full` or `gate` lane run with a count fills it in (`suite_filled: auto`), only when it passed:
    after a failed one, nothing is filled and a warning says so. A hand-written line stays as
    written. Errors (a refusal), warnings, and the fields to set on `parsed`."""
    sid = parsed.get("suite_from")
    if sid is None and "suite_tests" in parsed:
        return [], [], {}
    if "suite_unparsed" in parsed:  # the worker's line stays as written; nothing is filled over it
        return [], [f"the report's `{parsed['suite_unparsed']}` line is neither `Suite: <n> tests, <s> s` nor "
                    "`Suite: from <suite_id>`: no suite numbers were recorded from it"], {}
    ended = [r for r in rows if r.get("state") in ("passed", "failed", "interrupted")]
    if sid is not None:
        row = next((r for r in rows if r.get("suite_id") == sid), None)
        if row is None:
            return [f"`Suite: from {sid}`: no suite run {sid} is recorded (ccp suite list)"], [], {}
        if row.get("run_id") != run_id:
            return [f"`Suite: from {sid}`: that suite run is recorded against {row.get('run_id') or 'no run'}, "
                    f"not {run_id}"], [], {}
        if row not in ended or row.get("tests") is None:
            return [f"`Suite: from {sid}`: that suite run has not ended with a test count; "
                    "write `Suite: <n> tests, <s> s`"], [], {}
        got = _from_suite(row)
        if phase == "verify" and accept_cache and "suite_ran" not in got:
            return [NO_CACHE_COUNTS + f" (suite run {sid} recorded none)"], [], {}
        return [], [], {**got, "suite_filled": "from", "suite_passed": row.get("state") == "passed"}
    mine = [r for r in ended if r.get("run_id") == run_id and r.get("lane") in auto_lanes and r.get("tests") is not None]
    if not mine:
        return [], [], {}
    last = mine[-1]
    if last.get("state") != "passed":
        return [], [f"no `Suite:` line, and this run's latest {last.get('lane')} suite run ({last['suite_id']}) "
                    f"{last.get('state')} with exit {last.get('exit_code')}: nothing was filled in; write "
                    f"`Suite: <n> tests, <s> s` or `Suite: from <suite_id>`"], {}
    got = _from_suite(last)
    if phase == "verify" and accept_cache and "suite_ran" not in got:
        return [], [], {}
    return [], [], {**got, "suite_from": last["suite_id"], "suite_filled": "auto", "suite_passed": True}


def fill_suite(q: Path, run_id: str, phase: str, parsed: dict[str, Any], accept_cache: bool,
               auto_lanes: tuple[str, ...] = WHOLE_SUITE_ROLES) -> tuple[list[str], list[str]]:
    """§14.1: the report's suite line, filled on `parsed` from the queue's recorded suite runs as `judge_suite`
    decides. Errors (a refusal) and warnings."""
    from ccp import suite  # noqa: PLC0415
    try:
        rows = suite.fold(q)
    except Exception:  # noqa: BLE001  (a damaged suites file: nothing to fill from)
        rows = []
    errors, warnings, update = judge_suite(rows, run_id, phase, parsed, accept_cache, auto_lanes)
    parsed.update(update)
    return errors, warnings


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
        elif m.group(1).lower() == "beyond" and not re.search(r"[^\W_]", m.group(2)):  # punctuation and markup alone
            errs.append("`Resolution: beyond` needs its reason: `Resolution: beyond <why>`")
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


class Ctx(NamedTuple):
    """What a section's reader knows besides the text: the round's phase and mode, whether its outcome is
    done, and the checks that need the product's settings and the task file."""
    phase: str
    mode: str | None
    done: bool
    accept_cache: bool
    declared: list[dict[str, Any]]
    checks: list[str] | None


Read = Callable[[str, Ctx], tuple[dict[str, Any], list[str]]]


class Section(NamedTuple):
    """One section or line of a worker's report (§13.4): what `parse` reads, what the prompt asks for, and where
    it lands. `keys` are the names `parse` returns for it; `stored` the run record's fields they become
    (`friction` becomes `friction_count`, its lines filed as health notes). `required` is `always`, `done` (when
    the outcome is done) or `no`: a missing one is refused with `missing`. `read` is None for a line `submit`
    checks before `parse` (`Prompt:`) or reads itself (`Affected checks:`, by `_read_resolution`). A section with
    a `mode` is carried by that review mode only. `prompt` is the line the prompt asks for it in (`{runner}` and
    `{each}` filled in), or None where another section's line names it."""
    key: str
    name: str
    label: str
    phases: tuple[str, ...]
    required: str
    secret: bool
    keys: tuple[str, ...]
    stored: tuple[str, ...]
    read: Read | None
    missing: str
    prompt: str | None
    mode: str | None = None


def _line(key: str, rx: re.Pattern[str], lower: bool = False) -> Read:
    def read(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
        m = rx.search(text)
        return ({key: m.group(1).lower() if lower else m.group(1)} if m else {}), []
    return read


def _read_severity(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    s = SEVERITY_RE.search(text)
    parts = {k.upper(): int(v) for k, v in SEV_PART_RE.findall(s.group(1))} if s else {}
    return ({"severity": parts} if set(parts) == {"BLOCKER", "MAJOR", "MINOR", "NIT"} else {}), []


def _read_beyond(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    beyond = friction(text, BEYOND_RE)
    return ({"spec_beyond_intent": len(beyond)} if beyond is not None else {}), []


def _read_tests(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    tests = friction(text, TESTS_RE, why=True)
    return ({"tests_for_new_behaviour": tests} if tests is not None else {}), []


def _read_resolution(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    """`Resolution:` and `Affected checks:` are read together by `resolution_lines`, a done resolution review's."""
    return resolution_lines(text, c.checks) if c.done else ({}, [])


def _read_suite(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    out: dict[str, Any] = {}
    errs: list[str] = []
    s = SUITE_RE.search(text)
    if s:
        out["suite_tests"] = int(s.group(1))
        sec = float(s.group(2))
        out["suite_seconds"] = int(sec) if sec.is_integer() else sec
        line = text[s.start():].split("\n", 1)[0]
        n = cache_counts(line)
        if n:
            out["suite_ran"], out["suite_cached"] = n
        elif c.phase == "verify" and c.accept_cache:
            errs.append(NO_CACHE_COUNTS)
    elif f := SUITE_FROM_RE.search(text):
        out["suite_from"] = f.group(1)
    elif u := SUITE_ANY_RE.search(text):
        out["suite_unparsed"] = u.group(0).strip()[:200]
    return out, errs


def _read_fields(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    if not (c.done and c.declared):
        return {}, []
    got, errs = fields(text, c.declared)
    return {"fields": got}, errs


def _read_friction(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    fr = friction(text)
    return ({"friction": fr} if fr is not None else {}), []


def _read_follow_ups(text: str, c: Ctx) -> tuple[dict[str, Any], list[str]]:
    items, err = follow_ups(text)
    return ({}, [err]) if err else ({"follow_ups": items}, [])


_ALL = runs.PHASES
_SAME = "   - `Outcome: done`, `Outcome: blocked` or `Outcome: failed`.\n"

# The report's sections, in the order `parse` reads them and the prompt asks for them (the worker's report is
# checked and asked for from this one table). A section is added here, with its reader.
SECTIONS: tuple[Section, ...] = (
    Section("outcome", "Outcome", "Outcome:", _ALL, "always", False, ("outcome",), ("outcome",),
            _line("outcome", OUTCOME_RE, lower=True), "no `Outcome: done|blocked|failed` line", _SAME),
    Section("head", "Head", "Head:", (*FIELD_PHASES, "verify"), "done", False, ("head",), ("head",),
            _line("head", HEAD_RE), "no `Head: <sha>` line", None),
    Section("pr", "PR", "PR:", FIELD_PHASES, "done", False, ("pr",), ("pr",), _line("pr", PR_RE),
            "no `PR: #<number>` line",
            "   - When done: `PR: #<number>` and `Head: <full sha of the PR head>`.\n"),
    Section("verdict", "Verdict", "Verdict:", ("verify",), "done", False, ("verdict",), ("verdict",),
            _line("verdict", VERDICT_RE, lower=True), "no `Verdict: approve|reject` line",
            "   - When done: `Verdict: approve` or `Verdict: reject`, and `Head: <full sha you judged>`, the same as in "
            "the record you wrote with `ccp verify record`.\n"),
    Section("severity", "Severity", "Severity:", ("review",), "done", False, ("severity",), ("severity",),
            _read_severity, "no `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>` line with all four counts",
            "   - When done: `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>`, the counts of your findings.\n"),
    Section("beyond", "Spec beyond intent", "## Spec beyond intent", ("review",), "done", False,
            ("spec_beyond_intent",), ("spec_beyond_intent",), _read_beyond,
            "no `## Spec beyond intent` section: a `- ` line for each passage of normative text (SPEC, contract) the PR "
            "adds or changes that the task's brief and its ADRs do not call for, or the single line `none` (SPEC §3.5)",
            "   - When done: a `## Spec beyond intent` section, a `- ` line for each passage of normative text "
            "beyond the task's intent, or the single line `none` (SPEC §3.5).\n"),
    Section("resolution", "Resolution", "Resolution:", ("review",), "no", False, ("resolution",), ("resolution",),
            _read_resolution, "",
            "   - When done: `Resolution: contained` (the resolution changes nothing of the task's own beyond the "
            "conflict hunks) or `Resolution: beyond <why>`.\n", mode="resolution"),
    Section("affected", "Affected checks", "Affected checks:", ("review",), "no", False, ("affected_checks",),
            ("affected_checks",), None, "",
            "   - When done: `Affected checks: <id>, <id>`, the task's dod_check ids the resolution can affect, "
            "or `Affected checks: none`.\n", mode="resolution"),
    Section("fields", "Declared verdicts", "report.required_fields", FIELD_PHASES, "no", False,
            ("fields",), ("fields",), _read_fields, "",
            "   - When done, a line for each verdict this product requires (plane.json `report.required_fields`), "
            "with one of the values shown: {each}.\n"),
    Section("tests", "Tests for new behaviour", "## Tests for new behaviour", FIELD_PHASES, "done", False,
            ("tests_for_new_behaviour",), (), _read_tests,
            "no `## Tests for new behaviour` section of `- ` lines, one for each behaviour the round's "
            "commits add or change, with the test that fails without it, or a single line beginning `none` followed "
            "by why (SPEC §13.4, §13.5)",
            "   - When done: a `## Tests for new behaviour` section, a `- ` line for each branch, field, refusal or "
            "behaviour your commits add or change, with the test that fails without it, or a single line beginning "
            "`none` followed by why (`none: the merge adds no behaviour`). `ccp report` refuses a done report "
            "without it.\n"),
    Section("prompt", "Prompt", "Prompt:", _ALL, "no", False, (), (), None, "",
            "   - `Prompt: <token>`, the token on this prompt's last line (`Prompt end: <token>`), copied exactly. "
            "`ccp report` refuses a report without it. If this prompt has no such last line, it reached you cut: tell "
            "the runner, `{runner}`, before you do anything else.\n"),
    Section("suite", "Suite", "Suite:", _ALL, "no", False,
            ("suite_tests", "suite_seconds", "suite_ran", "suite_cached", "suite_from"),
            ("suite_tests", "suite_seconds", "suite_ran", "suite_cached", "suite_from", "suite_filled"),
            _read_suite, "",
            "   - `Suite: <n> tests, <s> s`: the size and wall time of your last full test run (leave it out if you ran "
            "none). Or write `Suite: from <suite_id>`, the id in that run's summary, and `ccp report` copies the numbers "
            "from the record. Without a `Suite:` line, it takes them from this run's latest `full` or `gate` lane run "
            "if that run passed. `ccp report` warns when no `ccp suite run` is recorded for this run.\n"),
    Section("friction", "Friction", "## Friction", _ALL, "always", True, ("friction",), ("friction_count",),
            _read_friction, "no `## Friction` section of `- ` lines, or the single line `none`",
            "   - A `## Friction` section: one `- ` line per thing that cost you work the task did not need (a fact "
            "changed in many places, a test that pinned wording, a doc that did not help, a rule that forced extra "
            "work, a tool you needed and did not have), or the single line `none`. Facts, not complaints; never a "
            "reason to do less.\n"),
    Section("follow_ups", "Follow-ups", "## Follow-ups", _ALL, "no", True, ("follow_ups",), ("follow_ups",),
            _read_follow_ups, "",
            "   - A `## Follow-ups` section: one `- ` line per piece of work you found that is not yours to do here (a "
            "deferred finding, a test gap out of scope, a step for a later task, rule text the task does not carry), "
            "or the single line `none`; a missing section reads as `none`. `ccp report` keeps each line on the run "
            "for the lead to decide. Out-of-scope work goes there, never only in notes or prose.\n"),
)


def sections_for(phase: str, mode: str | None = None) -> list[Section]:
    """The sections a report of `phase` (a review's `mode`) carries, in table order."""
    return [s for s in SECTIONS if phase in s.phases and (s.mode is None or s.mode == mode)]


def parse(phase: str, text: str, accept_cache: bool = False,
          declared: list[dict[str, Any]] | None = None, mode: str | None = None,
          checks: list[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """The values a report gives (by `Section.keys`) and what it lacks: each section of `SECTIONS` that `phase`
    carries is read, and a required one it does not give is an error with the section's `missing` text."""
    errs: list[str] = []
    out: dict[str, Any] = {}
    for s in sections_for(phase, mode):
        if s.read is None:
            continue
        c = Ctx(phase, mode, out.get("outcome") == "done", accept_cache, declared or [], checks)
        got, serrs = s.read(text, c)
        out.update(got)
        errs += serrs
        if s.required != "no" and s.keys[0] not in got and (s.required == "always" or c.done):
            errs.append(s.missing)
    return out, errs


# The run record's fields a report's lines give (§13.4), from the table (`outcome` and `friction_count` are
# set apart by `submit`); a correction replaces those its phase's report can give (`phase_keys`).
SET_APART = ("outcome", "friction_count")
PARSED_KEYS = tuple(dict.fromkeys(k for s in SECTIONS for k in s.stored if k not in SET_APART))


def phase_keys(phase: str, mode: str | None = None) -> tuple[str, ...]:
    """The `PARSED_KEYS` a report of `phase` (a review's `mode`) can give: those a correction replaces. Any other
    (a review's `head` and `pr`) keeps the value the run was opened with."""
    own = {k for s in sections_for(phase, mode) for k in s.stored}
    return tuple(k for k in PARSED_KEYS if k in own)


# The run record's fields the plane computes at submit (§11.1); a correction computes them again.
COMPUTED_KEYS = ("integration_merges", "before_review")

# What `submit` returns of the record: the table's fields, the ones set apart, and what submit itself records.
RETURNED_KEYS = (*SET_APART, *PARSED_KEYS, "suite_runs_recorded", "suite_s_recorded", "corrections")


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
    such round, `origin/<integration>..<head>`) whose second parent is an ancestor of `origin/<integration>`,
    leaving out every commit already on `origin/<integration>` (a branch rebuilt on a newer tip does not count the
    tip's own merges), each as `{sha, conflicted, files}` (the count of conflicted files, never their names), oldest
    first. Whether one conflicted is `gitmerge.probe` of its first and second parents: the merge git would make on
    its own, so a recorded resolution does not hide it. Nothing is fetched. An empty list: none found. None: it could
    not be measured (no product checkout, a head, a previous head or the integration tip not in the object store, a
    git call that failed, a probe git could not run), so the run records none (never a refusal)."""
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
    found = queue.git(repo, "rev-list", "--merges", "--first-parent", "--topo-order", "--reverse", f"{base}..{tip}",
                      f"^{integ}")
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
    """Check, store and record the report of `run_id` (§13.4). A correction appends `{at, superseded}` to the run's
    `corrections`; the `run reported` event (`corrected: true`) and a review's `review recorded` event are written
    again, as is the review record of a review corrected to clean, while a review corrected away from clean leaves
    the record as it is (`ccp tasks submit` asks that the record's review be the latest done review and clean); the
    phase move, like the friction lines and the suite filing, is the first submission's."""
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
                                          tuple(lane_for(cfg, r) for r in WHOLE_SUITE_ROLES))
    errs += fill_errs
    if errs:
        raise QueueError("report refused, nothing written:\n  " + "\n  ".join(errs), 1)
    for s in SECTIONS:  # a section the table marks secret-checked is refused when a line looks like a secret
        if s.secret and any(health.looks_like_secret(v) for v in parsed.get(s.keys[0]) or []):
            raise QueueError(f"report refused: a {s.name} line looks like it holds a secret; say it without the value", 1)
    if rec["phase"] == "verify" and rec.get("verdict") and parsed.get("outcome") == "done":
        if parsed.get("verdict") != rec["verdict"] or not runs.heads_match(str(parsed.get("head") or ""), str(rec.get("head") or "")):
            raise QueueError(f"report refused, nothing written: it says {parsed.get('verdict')} at "
                             f"{str(parsed.get('head'))[:12]}, the recorded verdict is {rec['verdict']} at "
                             f"{str(rec.get('head'))[:12]} (ccp verify record)", 1)
    dest = runs.report_path(q, run_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    warnings = list(fill_warnings)
    earlier = rec.get("follow_ups") if isinstance(rec.get("follow_ups"), list) else []
    parsed["follow_ups"] = [{"id": refs.follow_up_id(run_id, n), "text": t, "outcome": None}
                            for n, t in enumerate(parsed.get("follow_ups") or [], 1)]  # §13.4, ADR-0044 D1
    if not FOLLOW_UPS_RE.search(text) and (near := FOLLOW_UPS_NEAR_RE.search(text)):
        warnings.append(f"the heading `{near.group(0)[:40]}` is not read as the follow-ups: only `## Follow-ups` is, "
                        "so none are stored; correct the report to keep them (SPEC §13.4)")
    if correcting:
        parsed["follow_ups"], dropped = followups.carry(earlier, parsed["follow_ups"])
        warnings += [f"follow-up {fu.get('id')} (`{str(fu.get('text') or '')[:80]}`) had the outcome "
                     f"{followups.outcome_word(fu.get('outcome'))}; the corrected report has no line with its text, "
                     "so that outcome is dropped (SPEC §13.4)" for fu in dropped]
        superseded = _supersede(src, dest)
        if superseded is None:
            warnings.append(f"the corrected report is the stored one ({dest}), edited in place: the earlier report "
                            "was overwritten before this correction, so none is kept as superseded")
        rec["corrections"] = [*(rec.get("corrections") or []),
                              {"at": iso(), "superseded": str(superseded) if superseded else None}]
        for k in COMPUTED_KEYS:  # computed again below, from the corrected head
            rec.pop(k, None)
        for k in phase_keys(rec["phase"], rec.get("mode")):  # the corrected report's, none left from the earlier one
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
         {"run_id": run_id, "outcome": rec["outcome"], **({"corrected": True} if correcting else {})}, seat_actor(rec["seat"]))
    verdict = review_verdict(rec["phase"], parsed)
    if verdict is not None:
        if verdict == "clean" and parsed.get("outcome") == "done":  # §15.1: the task's review record
            write_review_record(cfg, q, rec)
        emit(q, cfg, tid, "review", "recorded", {"run_id": run_id, "verdict": verdict, "severity": parsed["severity"]},
             seat_actor(rec["seat"]))
    to = None if correcting else phase_after(rec["phase"], parsed)  # §10.1, §13.4: a correction moves nothing again
    if to is not None:
        phase_move(q, cfg, tid, to, f"{run_id} reported", seat_actor(rec["seat"]))
    return {"ok": True, "run_id": run_id, "report": str(dest), **{k: v for k, v in rec.items() if k in RETURNED_KEYS},
            **({"warnings": warnings} if warnings else {})}


def review_verdict(phase: str, parsed: dict[str, Any]) -> str | None:
    """§15.2: a review report's verdict, `changes` when it counts a BLOCKER or MAJOR finding, else `clean`; None for a
    report of another phase or one with no `Severity:` counts."""
    sev = parsed.get("severity") if phase == "review" else None
    if not isinstance(sev, dict):
        return None
    return "changes" if sev.get("BLOCKER") or sev.get("MAJOR") else "clean"


def phase_after(phase: str, parsed: dict[str, Any]) -> str | None:
    """§10.1: the phase a first report moves its task to: `implemented` for an implement round done with a head,
    `reviewed` for a review done and clean; None for any other (a rework round, a verify, an outcome not done)."""
    if parsed.get("outcome") != "done":
        return None
    if phase == "implement" and parsed.get("head"):
        return "implemented"
    if review_verdict(phase, parsed) == "clean":
        return "reviewed"
    return None


REVIEW_DIR = "review"  # §15.1: QUEUE_ROOT/review/<task_id>.json, the task's review record


def review_record_path(q: Path, task_id: str) -> Path:
    """§15.1: the task's review record, one per task, replaced by each clean review."""
    return q / REVIEW_DIR / f"{task_id}.json"


def pr_number(value: Any) -> int | None:
    """A PR number as a run records it (`7`, `#7`), or None when it is none."""
    s = str(value or "").strip().lstrip("#")
    return int(s) if s.isdigit() and int(s) > 0 else None


def review_record(project_id: str, review: dict[str, Any], rs: list[dict[str, Any]], questions: list[str],
                  at: str) -> dict[str, Any]:
    """§15.1: the review record of the clean review `review` (its run record, reported), from the task's runs `rs`
    (in opened order) and the ids of the spec questions the task raised: the PR the review judged (else the PR the
    latest done change round reported), the head it judged, the implement or rework round that first reported that
    PR and its session (`mk_pr_*`), the rework rounds reported since that one and before the review
    (`safe_fixes_applied`), the questions as `decisions`, the review's report path and `at`. Ids, numbers, paths
    and times only (house rule E5)."""
    live = [r for r in rs if runs.state(r) != "abandoned"]
    done = [r for r in live if r.get("phase") in runs.CHANGE_PHASES and runs.state(r) == "reported"
            and r.get("outcome") == "done" and pr_number(r.get("pr"))]
    pr = pr_number(review.get("pr")) or (pr_number(done[-1].get("pr")) if done else None)
    first = next((r for r in done if pr_number(r.get("pr")) == pr), None)
    since = str((first or {}).get("reported_at") or "")
    before = str(review.get("opened_at") or "")
    fixes = [str(r["run_id"]) for r in live if r.get("phase") in runs.REWORK_PHASES and runs.state(r) == "reported"
             and since <= str(r.get("reported_at") or "") <= before]
    return {"task_id": str(review["task_id"]), "project_id": project_id, "pr": pr,
            "head": str(review.get("head") or "") or None,
            "mk_pr_run_id": str(first["run_id"]) if first else None,
            "mk_pr_session_id": (first or {}).get("session_id") or None,
            "review_run_id": str(review["run_id"]), "review_session_id": review.get("session_id") or None,
            "safe_fixes_applied": fixes,
            "decisions": [{"class": "spec", "question_ref": ref} for ref in questions],
            "review_artifact_path": str(review.get("report") or "") or None, "reviewed_at": at}


def raised_questions(q: Path, task_id: str) -> list[str]:
    """§17.3: the ids of the spec questions the task raised (`questions/sm-*.json` whose `task_id` is it), in id
    order, answered or not."""
    d = q / "questions"
    out = []
    for f in sorted(d.glob("sm-*.json")) if d.is_dir() else []:
        if f.name.endswith(".answer.json"):
            continue
        try:
            qq = read_json(f, {})
        except QueueError:
            continue
        if isinstance(qq, dict) and qq.get("task_id") == task_id:
            out.append(str(qq.get("question_id") or f.stem))
    return out


def write_review_record(cfg: Config, q: Path, review: dict[str, Any]) -> str:
    """§15.1: write the task's review record for the clean review `review`, replacing an earlier one; its path
    relative to QUEUE_ROOT."""
    tid = str(review["task_id"])
    rec = review_record(cfg.project_id, review, runs.all_runs(q, tid), raised_questions(q, tid), iso())
    write_json(review_record_path(q, tid), rec)
    return f"{REVIEW_DIR}/{tid}.json"
