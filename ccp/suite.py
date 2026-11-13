"""`ccp suite run|list|affected` (SPEC §10, §14.1, §14.7): workers run their tests through `ccp`, which
records how long each run took, and ask it which test modules a change touches.

  ccp suite run [--lane NAME] [--run RUN_ID | --task ID [--phase P]] [--full | --summary] [--log PATH]
                [-- COMMAND …]
  ccp suite list [--task ID]
  ccp suite affected [--since REF | --paths PATH …]

`run` wraps the command. It runs in the foreground, from the current directory, with stdin
inherited, and `ccp` exits with the command's exit code (128 + N when a signal N ended it).
SIGINT and SIGTERM sent to `ccp` reach the command's process group; a watchdog in that group ends
it if `ccp` itself dies.

Summary mode, the default without a terminal on stdin (`--summary` forces it): the command's
stdout and stderr both go to one log file, in the order the command wrote them (`--log`, else
next to the run's record in the queue, else a temp file). `ccp` prints a start line naming the
log, and when the command ends, a summary: on a failure the failing tests' sections (unittest's
FAIL:/ERROR: blocks) and the log's last lines, capped with the tail cut from its front so the end
always shows; always every `show_re` line; then one line with the exit code, lane, seconds, tests,
failures, skips and modules ran and cached, and the log's path. A log that cannot be opened
streams the run as --full does, with a warning. Options that do not parse run the command
unrecorded, in the mode a terminal decides.

`--full`, the default with a terminal on stdin: the output is
copied to `ccp`'s own, byte for byte, as it arrives (one pipe when stdout and stderr are the same
file, so their order is kept), at most DRAIN_SECONDS after the command exits.

The gate-result contract (§14.3): the command's environment carries CCP_SUITE_RESULT, a path the
command may write a JSON result to (contracts/suite_result.schema.json: tests, ran, cached,
cached_tests, skipped, failed, failures, seconds). When it does, its numbers are the record's. When
it does not, each line is matched against the product's `suite.count_re` (default: unittest's
`Ran N tests in`) and `suite.summary`'s patterns (defaults: unittest's failures and skips only). The
numbers are summed, and nothing else of the output, or of the result file, is kept in the records:
failure ids are shown in the summary, never recorded. The command's environment is the caller's,
unchanged, plus CCP_SUITE_ID and CCP_SUITE_RESULT: `bin/ccp` sets no variable, and a QUEUE_ROOT
`ccp` finds from the binding when the caller set none stays `ccp`'s own. A lane's stages run in a
worktree `ccp wt` made also get that worktree's `CCP_WT_<FIELD>` variables, the ones its env hooks
get (§12.2), and its task as `CCP_TASK_ID` and `CCP_NNNN`; a command after `--` gets none. A
`ccp suite run` inside it records nothing and writes no log: it becomes its command, so the outer run
captures the output.

`--lane NAME` labels the run. A lane plane.json `suite.exclusive_lanes` names (a run with no lane counts as
the `full` role's lane, `suite.roles`) runs one at a time in the queue (SPEC §16.6): a run that finds it held exits 75 at once,
naming the holder and its usual duration, runs nothing, and counts `lane_busy` on its run. A run
that records nothing (no QUEUE_ROOT, recording off) takes no lock: recording never blocks tests.
Without `-- COMMAND`, it runs what `plane.json` `suite.lanes` names for that lane, from the
checkout's root: an argv, run as one stage named after the lane, or an ordered list of `{name, cmd}`
stages (§14.2), each run by the shell, in order, timed, until one exits non-zero. The gate role's staged
lane ends with the plane's doc checks as the stage `plane-docs`. Such a run records `stages` (name,
seconds, exit code of each that ran) and `failed_stage` on its `ended` row and event. A signal between
stages stops the run before the next starts: it exits 128 + N and names that stage. Every `ended` row
and event says whether the run was `cold` (§14.6: its own `cached` count was 0; null without one).
On the gate role's staged lane, a run that is recorded and names its task runs a stage's declared provers
(plane.json `verify.provers`) before it starts: the first whose command exits 0 on the task's diff, from
the head's merge base with the integration branch to HEAD in a clean checkout, skips the stage, and the
`ended` row and its event record it in `proven_skips` (stage, prover name, exit code: no command text,
§14.4; the command is looked up in plane.json by the name).

The record is `QUEUE_ROOT/runs/_suites.jsonl`, append-only: a `started` row when the command
starts and an `ended` row when it ends, sharing a `suite_id`. The `ended` row also goes into the
ledger as `suite/recorded`. A row holds numbers, ids, short labels and the log's path only: the
lane, the output mode, the command's basename and its argument count, never its arguments or its
output. The run it belongs to is `--run`, else the latest open run of `--task` (and `--phase`),
else the one running worker run whose worktree holds the current directory. A `started` row with
no end is `killed` once its run has stopped or reported, or after KILLED_AFTER_S.

`affected` prints the test modules a change touches, for the `part` lane, and runs nothing (§14.7). The
change is `--paths`, else what `git diff REF` (default HEAD) names against the working tree plus the
untracked files. The product's language pack reads them: for Python, a `test*.py` module that changed,
imports a changed module directly or through one package's `__init__.py`, or names a changed file.

Recording never stands between a worker and its tests. With a command after `--`, it runs and its
exit code is returned whatever else fails: no QUEUE_ROOT, no checkout, an unreadable plane.json, a bad option, a failed write. `ccp` prints one
`ccp suite:` warning on stderr and records nothing, or nothing more.
"""
from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from ccp.envvars import envvar, for_child
from ccp import runs
from ccp.config import PLANE_DOCS_STAGE, SUITE_LANE_RE, Config, fill, lane_for, lane_stages
from ccp.queue import QueueError, emit, iso, root

DEFAULT_COUNT_RE = r"^Ran (\d+) tests? in "
LINE_MAX = 8192  # a partial line longer than this is dropped from the count scan, never from the output


def path(q: Path) -> Path:
    return q / "runs" / "_suites.jsonl"


BUSY_EXIT = 75  # SPEC §16.6: an exclusive lane is held by another run; run it again later (EX_TEMPFAIL)


def _exclusive(cfg: Config | None, lane: str | None) -> bool:
    """§16.6: this run's lane is one of plane.json `suite.exclusive_lanes` (a run with no lane counts as the
    `full` role's lane, `suite.roles`)."""
    return (lane or lane_for(cfg, "full")) in ((cfg.suite or {}).get("exclusive_lanes") or []) if cfg is not None else False


def take_lane(q: Path, holder: dict[str, Any]) -> tuple[int | None, dict[str, Any]]:
    """§16.6: the queue's exclusive-lane lock, without waiting: (its fd, held until this process ends,
    and `holder` written beside it) or (None, the holder's record). An flock dies with its process, so
    a crashed holder's lock is free again at once."""
    import fcntl  # noqa: PLC0415
    d = q / "locks"
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(d / "suite-exclusive.lock", os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        try:
            return None, json.loads((d / "suite-exclusive.json").read_text())
        except (OSError, ValueError):
            return None, {}
    try:  # the last holder's record: one whose process is gone left the lane to us (its flock died with it)
        was = json.loads((d / "suite-exclusive.json").read_text())
        pid = int(was.get("pid") or 0)
        if pid and pid != os.getpid():
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                holder["took_over"] = was.get("suite_id")
            except OSError:
                pass
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    tmp = d / f".suite-exclusive.{os.getpid()}.tmp"  # replaced whole: a reader never sees half a record
    tmp.write_text(json.dumps(holder) + "\n")
    os.replace(tmp, d / "suite-exclusive.json")
    return fd, holder


def release_lane(q: Path, suite_id: str) -> None:
    """Remove the holder's record when it is this run's (the flock itself goes with the process)."""
    p = q / "locks" / "suite-exclusive.json"
    try:
        if json.loads(p.read_text()).get("suite_id") == suite_id:
            p.unlink()
    except (OSError, ValueError, AttributeError):
        pass


def usual_seconds(q: Path, lane: str | None, default: str = "full") -> float | None:
    """The median of this lane's last ten passing runs, from the suite records (a failed or cut-off run
    says little about how long the holder will take)."""
    started: dict[str, str | None] = {}
    secs: list[float] = []
    try:
        for line in path(q).read_text().splitlines():
            r = json.loads(line)
            if r.get("op") == "started":
                started[r.get("suite_id")] = r.get("lane")
            elif r.get("op") == "ended" and (started.get(r.get("suite_id")) or default) == (lane or default) \
                    and r.get("exit_code") == 0 and isinstance(r.get("seconds"), (int, float)):
                secs.append(float(r["seconds"]))
    except (OSError, ValueError):
        return None
    last = sorted(secs[-10:])
    return last[len(last) // 2] if last else None


def _append(q: Path, row: dict[str, Any]) -> None:
    p = path(q)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row) + "\n")


# ----------------------------------------------------------------------------------------- run


class _Warn:
    """At most one `ccp suite:` warning per command: the tests' own output is what matters."""

    def __init__(self) -> None:
        self.said = False

    def __call__(self, msg: str) -> None:
        if not self.said:
            self.said = True
            print(f"ccp suite: {msg}", file=sys.stderr, flush=True)


class _Counter:
    """Scans one stream's lines for the count pattern, and for the summary's other numbers, as
    they pass. Keeps no output."""

    def __init__(self, pattern: re.Pattern[bytes], fields: dict[str, list[re.Pattern[bytes]]] | None = None) -> None:
        self.pattern = pattern
        self.fields = fields or {}
        self.partial = b""
        self.skip = False  # the rest of an over-long line: never matched
        self.total: int | None = None
        self.sums: dict[str, int] = {}

    def feed(self, chunk: bytes) -> None:
        data = self.partial + chunk
        *lines, self.partial = data.split(b"\n")
        for ln in lines:
            if self.skip:
                self.skip = False
                continue
            self._line(ln)
        if len(self.partial) > LINE_MAX:
            self.partial = b""
            self.skip = True

    def close(self) -> None:
        if self.partial and not self.skip:
            self._line(self.partial)
        self.partial = b""

    def _line(self, ln: bytes) -> None:
        ln = ln.rstrip(b"\r")
        m = self.pattern.search(ln)
        if m:
            try:
                self.total = (self.total or 0) + int(m.group(1))
            except (IndexError, ValueError):
                pass
        for name, pats in self.fields.items():
            for pat in pats:
                f = pat.search(ln)
                if f:
                    try:
                        self.sums[name] = self.sums.get(name, 0) + int(f.group(1))
                    except (IndexError, ValueError):
                        pass


def _pump(src: Any, fd: int, counter: _Counter) -> None:
    """Copy a pipe to fd as it arrives. A closed reader (`| head`) stops the copy, not the drain."""
    out_ok = True
    while True:
        try:
            chunk = os.read(src.fileno(), 65536)
        except OSError:
            break
        if not chunk:
            break
        if out_ok:
            try:
                view = memoryview(chunk)
                while view:
                    n = os.write(fd, view)
                    view = view[n:]
            except OSError:
                out_ok = False
        try:
            counter.feed(chunk)
        except Exception:  # noqa: BLE001  (counting never costs the output)
            pass
    try:
        counter.close()
    except Exception:  # noqa: BLE001
        pass


def resolve_argv(cfg: Config | None, lane: str | None, command: list[str] | None) -> list[str]:
    """The argv to run, for a single-command run. A command after `--` always runs, whatever else is wrong."""
    stages = resolve_stages(cfg, lane, command)
    return stages[0]["argv"]


def self_argv() -> list[str]:
    """This `ccp` itself, as a command: its `bin/ccp` under this interpreter, else `python -m ccp`."""
    exe = Path(__file__).resolve().parent.parent / "bin" / "ccp"
    return [sys.executable, str(exe)] if exe.is_file() else [sys.executable, "-m", "ccp"]


def plane_docs_argv(cfg: Config) -> list[str]:
    """The built-in stage's command (§14.2): this `ccp`'s own `docs check`, in the product root."""
    return [*self_argv(), "--root", str(cfg.root), "docs", "check"]


def resolve_stages(cfg: Config | None, lane: str | None, command: list[str] | None) -> list[dict[str, Any]]:
    """The stages to run, in order (§14.2): `[{name, argv}]`. A command after `--` is one unnamed stage;
    a lane's argv is one stage named after the lane; a staged lane is its `{name, cmd}` stages, each run
    by the shell, and the gate role's ends with the plane's doc checks (`plane-docs`)."""
    if command:
        return [{"name": None, "argv": list(command)}]
    if lane is None:
        raise QueueError("give the command after `--` (ccp suite run --lane full -- scripts/gate.sh), "
                         "or a --lane that plane.json suite.lanes names", 2)
    lanes = (cfg.suite or {}).get("lanes") if cfg else None
    if not lanes or lane not in lanes:
        known = ", ".join(sorted(lanes or {})) or "none"
        raise QueueError(f"plane.json suite.lanes names no lane {lane!r} (lanes: {known}): give the command after `--`", 2)
    declared = lane_stages(lanes[lane])
    if declared is None:
        return [{"name": lane, "argv": list(lanes[lane])}]
    out = [{"name": st["name"], "argv": ["/bin/sh", "-c", st["cmd"]], "staged": True} for st in declared]
    if cfg is not None and lane == lane_for(cfg, "gate"):
        out.append({"name": PLANE_DOCS_STAGE, "argv": plane_docs_argv(cfg), "staged": True})
    return out


def _usage_problem(a: Any) -> str | None:
    if a.lane is not None and not SUITE_LANE_RE.match(a.lane):
        return f"--lane {a.lane!r}: a lane is a short label (lowercase letters, digits, . _ -)"
    if a.phase is not None and a.phase not in runs.PHASES:
        return f"--phase {a.phase!r}: one of {', '.join(runs.PHASES)}"
    return None


def _count_re(cfg: Config | None) -> re.Pattern[bytes]:
    pat = ((cfg.suite or {}).get("count_re") if cfg else None) or DEFAULT_COUNT_RE
    return re.compile(pat.encode())


# ------------------------------------------------------------------------------ summary mode

SUMMARY_FIELDS = ("failed", "skipped", "ran", "cached", "cached_tests")
# Record fields the counters had before the gate-result contract, read as their new names.
LEGACY_FIELDS = {"modules_ran": "ran", "modules_cached": "cached"}
SHOW_MAX = 20  # `show_re` lines kept, at most
SHOW_LINE_MAX = 2000  # a shown line longer than this is cut
RULE_EQ = re.compile(r"^={20,}\s*$")
RULE_DASH = re.compile(r"^-{20,}\s*$")


def _summary_cfg(cfg: Config | None) -> dict[str, Any]:
    """plane.json `suite.summary` over its defaults, the patterns compiled. A pattern that does not
    compile keeps its default (config.load refuses one; this guards a run without a checked config)."""
    from ccp.config import SUITE_SUMMARY_ALIASES, SUITE_SUMMARY_DEFAULTS  # noqa: PLC0415
    raw = ((cfg.suite or {}).get("summary") if cfg else None) or {}
    given = {SUITE_SUMMARY_ALIASES[k]: v for k, v in raw.items() if k in SUITE_SUMMARY_ALIASES}
    given.update({k: v for k, v in raw.items() if k not in SUITE_SUMMARY_ALIASES})  # a new name wins
    out: dict[str, Any] = {}
    for k, default in SUITE_SUMMARY_DEFAULTS.items():
        v = given.get(k, default)
        if k in ("tail_lines", "max_chars"):
            out[k] = v if isinstance(v, int) and not isinstance(v, bool) else default
            continue
        try:
            out[k] = [re.compile(x) for x in (v if isinstance(v, list) else [v])]
        except (re.error, TypeError):
            out[k] = [re.compile(x) for x in (default if isinstance(default, list) else [default])]
    return out


def _field_patterns(scfg: dict[str, Any]) -> dict[str, list[re.Pattern[bytes]]]:
    return {f: [re.compile(p.pattern.encode()) for p in scfg[f"{f}_re"]] for f in SUMMARY_FIELDS}


def _cut(line: str) -> str:
    return line if len(line) <= SHOW_LINE_MAX else line[:SHOW_LINE_MAX] + f" …[{len(line) - SHOW_LINE_MAX} chars cut]"


def _lines(fh: Any) -> Any:
    """The log's lines, decoded, without their ends. An over-long line is read in pieces, so a log
    of any size reads in bounded memory; only its first piece is kept as the line."""
    while True:
        raw = fh.readline(LINE_MAX)
        if not raw:
            return
        if not raw.endswith(b"\n"):
            while True:  # the rest of an over-long line
                more = fh.readline(LINE_MAX)
                if not more or more.endswith(b"\n"):
                    break
        yield raw.rstrip(b"\n").rstrip(b"\r").decode("utf-8", "replace")


def digest(log: Path, scfg: dict[str, Any], count_re: re.Pattern[bytes]) -> dict[str, Any]:
    """What summary mode shows of a finished run's log: the failing tests' sections (a `====` rule,
    a `section_re` line, and everything to the next `====` rule or the `----` rule before a count
    line), the `show_re` lines, and the last `tail_lines` lines. Bounded: past `max_chars` of
    sections, the rest are counted, not kept."""
    count = re.compile(count_re.pattern.decode("utf-8", "replace"))
    section_res, show_res = scfg["section_re"], scfg["show_re"]
    budget = scfg["max_chars"]
    sections: list[tuple[int, int, list[str]]] = []
    dropped = dropped_chars = 0
    kept = 0
    show: list[tuple[int, str]] = []
    tail: list[tuple[int, str]] = []
    cur: list[str] | None = None
    cur_start = 0
    cur_chars = 0
    prev_eq: str | None = None
    held_dash: str | None = None
    n = -1

    def close(end: int) -> None:
        nonlocal cur, kept, dropped, dropped_chars
        if cur is not None:
            if kept + cur_chars <= budget * 3 // 4:
                sections.append((cur_start, end, cur))
                kept += cur_chars
            elif not sections:  # the first failure, too long to show whole: its start, cut
                cur.append(f"…[this section is {cur_chars} chars: the rest is in the log]")
                sections.append((cur_start, end, cur))
                kept = budget
            else:
                dropped += 1
                dropped_chars += cur_chars
        cur = None

    with log.open("rb") as fh:
        for n, line in enumerate(_lines(fh)):
            if cur is not None:
                if held_dash is not None:
                    if count.search(line):
                        close(n - 2)
                    else:
                        cur.append(held_dash)
                        cur_chars += len(held_dash) + 1
                    held_dash = None
                if cur is not None:
                    if RULE_EQ.match(line):
                        close(n - 1)
                    elif RULE_DASH.match(line) and len(cur) > 2:
                        held_dash = _cut(line)
                    else:
                        c = _cut(line)
                        if kept + cur_chars + len(c) <= budget * 3 // 4:
                            cur.append(c)
                        cur_chars += len(c) + 1
            if cur is None and prev_eq is not None and any(r.search(line) for r in section_res):
                cur, cur_start = [prev_eq, _cut(line)], n - 1
                cur_chars = len(prev_eq) + len(line) + 2
            prev_eq = _cut(line) if RULE_EQ.match(line) else None
            if len(show) < SHOW_MAX and any(r.search(line) for r in show_res):
                show.append((n, _cut(line)))
            tail.append((n, _cut(line)))
            if len(tail) > scfg["tail_lines"]:
                del tail[0]
    if held_dash is not None and cur is not None:
        cur.append(held_dash)
    close(n)
    if not scfg["tail_lines"]:
        tail = []
    return {"sections": sections, "dropped": dropped, "dropped_chars": dropped_chars, "show": show,
            "tail": tail, "lines": n + 1}


def _fmt_count(v: Any, word: str) -> str | None:
    return None if v is None else f"{v} {word}"


def summary_line(suite_id: str, code: int, lane: str | None, seconds: float, tests: int | None,
                 fields: dict[str, int | None], sig_name: str | None) -> str:
    """The one line summary mode always ends with."""
    verdict = f"interrupted ({sig_name})" if sig_name else ("passed" if code == 0 else "FAILED")
    secs = f"{seconds:.0f}" if seconds >= 10 else f"{seconds:.1f}"
    head = f"ccp suite: {suite_id}: {verdict}, exit {code}" + (f", lane {lane}" if lane else "") + f", {secs} s"
    counts = [x for x in (_fmt_count(tests, "tests"), _fmt_count(fields.get("failed"), "failed"),
                          _fmt_count(fields.get("skipped"), "skipped")) if x]
    out = head + "; " + (", ".join(counts) if counts else "no test count found")
    if fields.get("ran") is not None or fields.get("cached") is not None:
        out += f"; ran {fields.get('ran', 0) or 0}, cached {fields.get('cached', 0) or 0}"
    if fields.get("cached_tests") is not None:
        out += f"; {fields['cached_tests']} tests behind the cached results"
    return out


def stages_line(suite_id: str, done: list[dict[str, Any]], not_run: list[str],
                proven: list[dict[str, Any]] | None = None) -> str:
    """A staged lane's line (§14.2): each stage that ran, its result and seconds, the stages a prover
    skipped and which prover, then those not run."""
    parts = [f"{d['name']} {'passed' if d['exit_code'] == 0 else 'FAILED (exit ' + str(d['exit_code']) + ')'} "
             f"{d['seconds']:.1f} s" for d in done]
    skipped = [f"{x['stage']} (prover {x['prover']})" for x in proven or []]
    return (f"ccp suite: {suite_id}: stages: {', '.join(parts) or 'none ran'}"
            + (f"; skipped: {', '.join(skipped)}" if skipped else "")
            + (f"; not run: {', '.join(not_run)}" if not_run else ""))


def _sum(vals: list[Any]) -> int | None:
    """The sum of the counters given, or None when none is."""
    got = [v for v in vals if v is not None]
    return sum(got) if got else None


def _stage_mark(fd: int | None, text: str) -> None:
    """A staged lane's start and end lines for a stage: into the log, or on stderr when streaming."""
    try:
        data = text.encode("utf-8", "replace")
        target = fd if fd is not None else 2
        while data:
            data = data[os.write(target, data):]
    except OSError:
        pass


def _fit_tail(lines: list[str], budget: int) -> tuple[list[str], int]:
    """The last lines that fit in budget chars, cut from the front: the log's end always survives.
    How many lines were dropped."""
    out: list[str] = []
    used = 0
    for ln in reversed(lines):
        if used + len(ln) + 1 > budget:
            if not out:  # the last line alone is too long: its end
                keep = max(0, budget - 40)
                out.append(f"…[{len(ln) - keep} chars cut] " + ln[len(ln) - keep:] if keep < len(ln) else ln)
            break
        out.append(ln)
        used += len(ln) + 1
    return list(reversed(out)), len(lines) - len(out)


def render_summary(suite_id: str, log: Path, code: int, lane: str | None, seconds: float, tests: int | None,
                   fields: dict[str, int | None], sig_name: str | None, dig: dict[str, Any] | None,
                   max_chars: int, stage_text: str | None = None) -> str:
    """Summary mode's closing text. Always: every `show_re` line, then the result line and the
    log's path, last. On a failure, before them: the failing tests' sections, then the log's last
    lines not inside a shown section. The budget (max_chars) goes to the sections first, less a
    reserve for the tail, and the tail is cut from its front, so the log's last lines (the final
    error) always survive. A log no longer than `tail_lines` is shown whole instead."""
    failed = code != 0 or bool(fields.get("failed"))
    show = [ln for _i, ln in (dig or {}).get("show", [])] if dig is not None else []
    show_text = "\n".join(["ccp suite: from the log:", *show]) if show else ""
    parts: list[str] = []
    if dig is not None and failed:
        if dig["lines"] == 0:
            parts.append("ccp suite: the command printed nothing")
        elif dig["lines"] <= len(dig["tail"]):  # the whole log fits in the tail: show it all
            budget = max(0, max_chars - len(show_text))
            body, dropped = _fit_tail([ln for _i, ln in dig["tail"]], budget)
            parts.append(f"ccp suite: the whole log ({dig['lines']} line(s)"
                         + (f", the first {dropped} not shown" if dropped else "") + "):")
            parts.extend(body)
        else:
            full_tail = [ln for _i, ln in dig["tail"]]
            reserve = min(sum(len(x) + 1 for x in full_tail), max_chars // 4)
            budget = max(0, max_chars - len(show_text) - reserve)
            chosen: list[tuple[int, int, list[str]]] = []
            used = 0
            for sec in dig["sections"]:
                size = sum(len(x) + 1 for x in sec[2])
                if used + size > budget:
                    break
                chosen.append(sec)
                used += size
            if not chosen and dig["sections"]:  # the first one alone is over: its start, cut to fit
                s0, e0, b0 = dig["sections"][0]
                cut, size = [], 0
                for x in b0:
                    if size + len(x) + 1 > budget - 80:
                        break
                    cut.append(x)
                    size += len(x) + 1
                chosen.append((s0, e0, [*cut, "…[this section is cut to fit: the rest is in the log]"]))
            not_shown = len(dig["sections"]) - len(chosen) + dig["dropped"]
            if chosen:
                more = f", {not_shown} more not shown" if not_shown else ""
                parts.append(f"ccp suite: failing tests' sections ({len(chosen)}{more}):")
                for _s, _e, body in chosen:
                    parts.extend(body)
            elif not_shown:
                parts.append(f"ccp suite: {not_shown} failing tests' sections, too long to show; see the log")
            upto = max((e for _s, e, _b in chosen), default=-1)
            tail = [ln for i, ln in dig["tail"] if i > upto]
            if tail:
                left = max(0, max_chars - len(show_text) - sum(len(x) + 1 for x in parts))
                body, dropped = _fit_tail(tail, max(left, reserve))
                parts.append(f"ccp suite: the log's last {len(body)} line(s) of {dig['lines']}"
                             + (f" ({dropped} more cut to fit)" if dropped else "") + ":")
                parts.extend(body)
    if show_text:
        parts.append(show_text)
    if stage_text:
        parts.append(stage_text)
    end = summary_line(suite_id, code, lane, seconds, tests, fields, sig_name)
    where = f"ccp suite: full log: {log} (read it with grep -n or sed -n; never cat it whole)" if failed \
        else f"ccp suite: log: {log}"
    return "".join(p + "\n" for p in parts) + end + "\n" + where + "\n"


def log_path(q: Path | None, started: dict[str, Any] | None, suite_id: str, given: str | None) -> Path:
    """Where summary mode writes the command's output: --log, else next to the run's record
    (QUEUE_ROOT/runs/<task>/<phase>[-n]-suite-<id>.log), else the queue's runs/_suite-logs/ for an
    unbound run, else a temp file (no queue to write to), in CCP_SUITE_LOG_DIR when that is set."""
    if given:
        return Path(given).expanduser().resolve()
    if q is not None and started is not None:
        rid = started.get("run_id")
        if rid:
            rec = runs.path(q, rid)
            return rec.with_name(f"{rec.stem}-suite-{suite_id}.log")
        return q / "runs" / "_suite-logs" / f"{suite_id}.log"
    import tempfile  # noqa: PLC0415
    base = envvar("CCP_SUITE_LOG_DIR") or tempfile.gettempdir()  # the tests' fence names their own
    return Path(base) / f"ccp-suite-{suite_id}.log"


LOG_KEEP_DAYS = 14
PRUNE_MAX = 5000  # files looked at per run, at most: pruning stays cheap on any queue


def prune_logs(q: Path, keep_days: int, now: float | None = None) -> int:
    """Remove summary-mode logs older than keep_days from the queue: `runs/<task>/*-suite-st-*.log`
    and `runs/_suite-logs/st-*.log`, nothing else, no symlink. Never raises; how many it removed."""
    cutoff = (time.time() if now is None else now) - keep_days * 86400
    removed = seen = 0
    try:
        base = q / "runs"
        real = base.resolve()
        paths = [*base.glob("*/*-suite-st-*.log"), *(base / "_suite-logs").glob("st-*.log")]
    except OSError:
        return 0
    for f in paths:
        seen += 1
        if seen > PRUNE_MAX:
            break
        try:
            if f.is_symlink() or not f.is_file() or any(d.is_symlink() for d in f.parents if base in d.parents) \
                    or real not in f.resolve().parents:
                continue
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def _keep_days(cfg: Config | None) -> int:
    v = (cfg.suite or {}).get("log_keep_days") if cfg else None
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else LOG_KEEP_DAYS


def _open_log(p: Path) -> int:
    p.parent.mkdir(parents=True, exist_ok=True)
    return os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)


def _say(text: str) -> None:
    """Summary mode's own lines, on stdout. A closed reader never stops the run."""
    try:
        data = text.encode("utf-8", "replace")
        while data:
            data = data[os.write(1, data):]
    except OSError:
        pass


def _mode(a: Any) -> str:
    """`full` (stream everything, as before) or `summary`. --full and --summary choose; without
    either, a terminal on stdin (someone at a prompt) gets full, anything else summary."""
    out = getattr(a, "output", None)
    if out in ("full", "summary"):
        return out
    try:
        return "full" if os.isatty(0) else "summary"
    except OSError:
        return "summary"


def _inside(cwd: Path, worktree: Any) -> bool:
    if not worktree:
        return False
    try:
        w = Path(str(worktree)).resolve()
        return cwd == w or w in cwd.parents
    except (OSError, ValueError):
        return False


def _bind(cfg: Config | None, q: Path, a: Any, warn: _Warn) -> dict[str, Any]:
    """The run this suite run belongs to: --run, else --task [--phase]'s latest open run, else the
    one running worker run whose worktree holds the current directory. What is known of it, when
    nothing binds."""
    out: dict[str, Any] = {"run_id": None, "task_id": None, "phase": a.phase or None, "round": None,
                           "seat": None, "bound_by": None}
    rec = None
    if a.run:
        task, phase, _n = runs.parse_id(a.run)
        out.update(task_id=task, phase=phase)
        try:
            rec = runs.load(q, a.run)
            out["bound_by"] = "run"
        except QueueError:
            warn(f"no run {a.run} in the queue: recorded against its task, unbound")
    elif a.task:
        tid = a.task
        if cfg is not None and not runs.RUN_ID_RE.match(f"{tid}/implement"):
            from ccp.queue import task_meta  # noqa: PLC0415
            tid = str(task_meta(cfg, a.task)["task_id"])
        out["task_id"] = tid
        if a.phase:
            rec = runs.latest_open(q, tid, a.phase)
        else:
            rec = next((r for r in reversed(runs.all_runs(q, tid))
                        if runs.state(r) in ("pending", "running", "stopped")), None)
        out["bound_by"] = "task" if rec else None
    else:
        cwd = Path.cwd().resolve()
        live = [r for r in runs.all_runs(q) if runs.state(r) == "running" and _inside(cwd, r.get("worktree"))]
        if len(live) == 1:
            rec, out["bound_by"] = live[0], "worktree"
    if rec:
        out.update(run_id=rec["run_id"], task_id=rec.get("task_id"), phase=rec.get("phase"),
                   round=rec.get("round"), seat=rec.get("seat"))
    return out


def _actor_for(seat: str | None) -> str:
    return "task-verifier" if seat == "verifier" else "task-runner"


# The watchdog: it sits in the command's process group, ignores the signals ccp forwards, and waits
# on a pipe only ccp writes. EOF without the "done" byte means ccp died (SIGKILL, a harness killing
# ccp's group): it ends the command's group, which would otherwise run on unwatched.
WATCHDOG = r"""
import os, signal, sys, time
for s in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(s, signal.SIG_IGN)
try:
    done = os.read(0, 1)
except OSError:
    done = b""
if done != b"x":
    pg = os.getpgrp()
    for sig, pause in ((signal.SIGTERM, 2.0), (signal.SIGKILL, 0)):
        try:
            os.killpg(pg, sig)
        except OSError:
            break
        time.sleep(pause)
"""
DRAIN_SECONDS = 2.0  # after the command exits, how long its output may still arrive (a background child holds the pipe)


def _flush() -> None:
    for f in (sys.stdout, sys.stderr):
        try:
            if f is not None:
                f.flush()
        except Exception:  # noqa: BLE001  (a closed or missing stream never stops the run)
            pass


def _reopen_closed_std_fds() -> None:
    """A closed fd 1 or 2 is reopened on /dev/null, so no pipe the run makes can land on it."""
    for fd in (1, 2):
        try:
            os.fstat(fd)
        except OSError:
            try:
                nul = os.open(os.devnull, os.O_WRONLY)
                if nul != fd:
                    os.dup2(nul, fd)
                    os.close(nul)
            except OSError:
                pass


def _group(pgid: int) -> dict[str, Any]:
    """Popen arguments that put the process in group pgid (0: its own). `process_group` is 3.11+."""
    if sys.version_info >= (3, 11):
        return {"process_group": pgid}
    return {"preexec_fn": lambda: os.setpgid(0, pgid)}


def _passthrough(argv: list[str], env: dict[str, str] | None = None) -> int:
    """A nested `ccp suite run` (CCP_SUITE_ID set): become the command, in the caller's
    environment, and record nothing."""
    try:
        _flush()
        os.execvpe(argv[0], argv, dict(os.environ) if env is None else env)
    except OSError as e:
        print(f"ccp suite: {argv[0]}: {e.strerror or e}", file=sys.stderr)
        return 127 if isinstance(e, FileNotFoundError) else 126
    return 0  # not reached


def _same_file(a: int, b: int) -> bool:
    try:
        sa, sb = os.fstat(a), os.fstat(b)
        return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)
    except OSError:
        return False


def _run_stage(argv: list[str], env: dict[str, str], log_fd: int | None, merged: bool, own_group: bool,
               counters: list[_Counter], current: dict[str, Any]) -> tuple[int, float]:
    """Run one stage's command to its end: (its return code, as Popen gives it, and its seconds). Its
    output goes to the log, or is copied through and counted as it arrives. A command that cannot
    start returns 127 (not found) or 126 and says why."""
    t0 = time.monotonic()
    if log_fd is not None:  # the file itself, both streams: the order is the command's own
        pipes: dict[str, Any] = {"stdout": log_fd, "stderr": subprocess.STDOUT, "env": env}
    else:
        pipes = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT if merged else subprocess.PIPE, "env": env}
    try:
        try:
            proc = subprocess.Popen(argv, **pipes, **(_group(0) if own_group else {}))
        except TypeError:  # no process-group support here: the command still runs, in ccp's group
            own_group = False
            proc = subprocess.Popen(argv, **pipes)
    except OSError as e:
        print(f"ccp suite: {argv[0]}: {e.strerror or e}", file=sys.stderr)
        return (127 if isinstance(e, FileNotFoundError) else 126), time.monotonic() - t0
    current.update(proc=proc, group=own_group)
    dog_w = None
    if own_group:
        try:
            r_fd, dog_w = os.pipe()
            subprocess.Popen([sys.executable, "-I", "-c", WATCHDOG], stdin=r_fd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True, **_group(proc.pid))
            os.close(r_fd)
        except Exception:  # noqa: BLE001  (no watchdog: the run goes on)
            dog_w = None
    pumps = []
    if log_fd is None:
        pumps.append(threading.Thread(target=_pump, args=(proc.stdout, 1, counters[0]), daemon=True))
        if not merged:
            pumps.append(threading.Thread(target=_pump, args=(proc.stderr, 2, counters[1]), daemon=True))
    try:
        for t in pumps:
            t.start()
        while True:
            try:
                rc = proc.wait()
                break
            except InterruptedError:
                continue
        # A background child of the command may hold the pipe open: give its output a moment, then go.
        deadline = time.monotonic() + DRAIN_SECONDS
        for t in pumps:
            t.join(max(0.0, deadline - time.monotonic()))
    finally:
        current.clear()
        if dog_w is not None:
            try:
                os.write(dog_w, b"x")  # ccp ends normally: the watchdog leaves the group alone
                os.close(dog_w)
            except OSError:
                pass
    return rc, time.monotonic() - t0


def worktree_env(cfg: Config | None, command: list[str] | None, warn: _Warn) -> dict[str, str]:
    """The `CCP_WT_<FIELD>` variables a lane's stages get when the checkout is a worktree `ccp wt` made
    (§14.2): the ones its env hooks get (§12.2), and its task as `CCP_TASK_ID` and `CCP_NNNN`. Nothing
    for a command after `--`, outside such a worktree, or without a queue to look in; a lookup that
    fails is a warning, never the run's problem."""
    q = os.environ.get("QUEUE_ROOT")
    if cfg is None or command or not q or not Path(q).is_dir():
        return {}
    try:
        from ccp import wt  # noqa: PLC0415

        st = wt.recorded_at(Path(q), cfg.root)
        if not st:
            return {}
        return {**wt.env_fields(cfg, st), **for_child({"CCP_TASK_ID": st["task_id"], "CCP_NNNN": st["nnnn"]})}
    except Exception as e:  # noqa: BLE001
        warn(f"the worktree's CCP_WT_* fields were not found ({type(e).__name__}): the stages run without them")
        return {}


PROVER_TIMEOUT = 600  # seconds a gate stage's prover (verify.provers) may take; a timeout proves nothing


def stage_provers(cfg: Config | None, lane: str | None, command: list[str] | None,
                  stages: list[dict[str, Any]], started: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """The declared provers of each stage this run may skip (§14.2, plane.json `verify.provers`): only for
    the gate role's staged lane, on a run that is recorded and names its task, so a skip is always on the
    record. {} otherwise."""
    from ccp.config import PROVER_REVIEW  # noqa: PLC0415

    if cfg is None or command or not lane or lane != lane_for(cfg, "gate") or not stages[0].get("staged") \
            or started is None or not started.get("task_id"):
        return {}
    names = {st["name"] for st in stages if st["name"] != PLANE_DOCS_STAGE}
    out: dict[str, list[dict[str, Any]]] = {}
    for pr in (cfg.verify or {}).get("provers") or []:
        if pr.get("skips") != PROVER_REVIEW and pr.get("skips") in names:
            out.setdefault(str(pr["skips"]), []).append(pr)
    return out


def task_diff(cfg: Config, q: Path) -> tuple[dict[str, str] | None, str]:
    """The task's diff a gate stage's prover judges (§14.2): `{from, head}`, from the head's merge base
    with the integration branch (`origin/<branch>`) to the checkout's HEAD, or None and why it cannot be
    judged: no HEAD, no merge base, or uncommitted changes (the stages would test what the diff leaves
    out)."""
    from ccp.queue import git, integration_branch  # noqa: PLC0415

    integ = integration_branch(q)
    head = git(cfg.root, "rev-parse", "--verify", "-q", "HEAD^{commit}")
    if head.returncode != 0:
        return None, "the checkout has no HEAD"
    base = git(cfg.root, "merge-base", "HEAD", f"origin/{integ}")
    if base.returncode != 0:
        return None, f"the head has no merge base with origin/{integ}"
    dirty = git(cfg.root, "status", "--porcelain")
    if dirty.returncode != 0 or dirty.stdout.strip():
        return None, "the checkout has uncommitted changes"
    return {"from": base.stdout.strip(), "head": head.stdout.strip()}, ""


def _prove(cmd: str, cwd: Path, env: dict[str, str], current: dict[str, Any]) -> int | None:
    """Run one prover's command (`/bin/sh -c`, its output discarded) to its end: its exit code, or None
    after PROVER_TIMEOUT, when its process group is killed. A signal sent to `ccp` reaches it."""
    try:
        proc = subprocess.Popen(["/bin/sh", "-c", cmd], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return 126
    current.update(proc=proc, group=True)
    try:
        rc = proc.wait(timeout=PROVER_TIMEOUT)
        return 128 - rc if rc < 0 else rc
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
        return None
    finally:
        current.clear()


def _passthrough_stages(stages: list[dict[str, Any]], env: dict[str, str] | None = None) -> int:
    """A nested `ccp suite run` of a staged lane: run the stages in order in the caller's environment,
    stop at the first that fails, and record nothing."""
    code = 0
    for stage in stages:
        _flush()
        try:
            rc = subprocess.call(stage["argv"], env=dict(os.environ) if env is None else env)
        except OSError as e:
            print(f"ccp suite: {stage['argv'][0]}: {e.strerror or e}", file=sys.stderr)
            return 127 if isinstance(e, FileNotFoundError) else 126
        code = 128 - rc if rc < 0 else rc
        if code != 0:
            break
    return code


def run(cfg: Config | None, a: Any, command: list[str] | None, warn: _Warn | None = None, record: bool = True,
        caller_env: dict[str, str] | None = None) -> int:
    warn = warn or _Warn()
    problem = _usage_problem(a)
    if problem and not command:
        print(f"ccp suite: {problem}", file=sys.stderr)
        return 2
    try:
        stages = resolve_stages(cfg, a.lane, command)
    except QueueError as e:
        print(f"ccp suite: {e}", file=sys.stderr)
        return e.code
    argv = stages[0]["argv"]
    mode = _mode(a)
    log_arg = getattr(a, "log", None)
    if log_arg:
        log_arg = str(Path(log_arg).expanduser().absolute())  # from the caller's directory, before a lane's chdir
    if cfg is not None and not command and a.lane:
        os.chdir(cfg.root)  # a named lane runs from the checkout's root, as a product script expects
    _reopen_closed_std_fds()
    wt_env = worktree_env(cfg, command, warn)
    if envvar("CCP_SUITE_ID"):
        inner = {**(os.environ if caller_env is None else caller_env), **wt_env} if wt_env else caller_env
        if len(stages) > 1:
            return _passthrough_stages(stages, inner)  # the outer `ccp suite run` records this time
        return _passthrough(argv, inner)  # the outer `ccp suite run` records this time
    if problem:
        warn(f"{problem}: running the command without recording it")
        record = False
    # 1. what to record against, never at the cost of the run
    q: Path | None = None
    started: dict[str, Any] | None = None
    suite_id = f"st-{iso().replace('-', '').replace(':', '')}-{secrets.token_hex(3)}"
    try:
        if not record:
            pass
        elif not os.environ.get("QUEUE_ROOT"):
            warn("QUEUE_ROOT is not set: running the tests without recording them")
        else:
            q = root()
            bound = _bind(cfg, q, a, warn)
            started = {"op": "started", "suite_id": suite_id, "at": iso(), "lane": a.lane,
                       **({"cmd": "stages", "argc": len(stages)} if stages[0].get("staged") else
                          {"cmd": Path(argv[0]).name[:64], "argc": len(argv) - 1}), "output": mode, **bound}
    except Exception as e:  # noqa: BLE001  (recording never blocks the tests)
        warn(f"not recorded ({str(e).splitlines()[0][:200] if str(e) else type(e).__name__}): running the tests anyway")
        q = started = None
    lane_fd: int | None = None
    if q is not None and started is not None and _exclusive(cfg, a.lane):
        # §16.6: one exclusive-lane run at a time in this queue; a held lane answers at once, or after
        # `--wait SECONDS` at most, the wait recorded apart from the run's time
        mine = {"suite_id": suite_id, "pid": os.getpid(), "at": started["at"], "lane": a.lane or lane_for(cfg, "full"),
                "run_id": started.get("run_id"), "task_id": started.get("task_id")}
        wait = max(0, int(getattr(a, "wait", None) or 0))
        t_wait = time.monotonic()
        try:
            lane_fd, holder = take_lane(q, mine)
            told = False
            while lane_fd is None and time.monotonic() - t_wait < wait:
                mine["at"] = iso()  # a holder's record dates from when it took the lane
                if not told:
                    print(f"ccp suite: lane {a.lane or 'full'} is held by {holder.get('suite_id') or 'another run'}; "
                          f"waiting up to {wait} s (--wait)", file=sys.stderr)
                    told = True
                time.sleep(min(2.0, max(0.1, wait - (time.monotonic() - t_wait))))
                lane_fd, holder = take_lane(q, mine)
            if lane_fd is not None and lane_fd >= 0 and time.monotonic() - t_wait >= 0.5:
                started["wait_s"] = round(time.monotonic() - t_wait, 1)
                started["at"] = iso()  # the run starts now; the wait is wait_s
        except OSError as e:  # the lock never stands between a worker and its tests
            warn(f"the exclusive lane could not be locked ({e}): running without it")
            lane_fd, holder = -1, {}
        if holder.get("took_over"):
            warn(f"lane {a.lane or 'full'}: its last holder {holder['took_over']} ended without releasing it; taken over")
        if lane_fd is None:
            usual = usual_seconds(q, holder.get("lane"), lane_for(cfg, "full"))
            try:
                _append(q, {"op": "busy", "suite_id": suite_id, "at": iso(), "lane": a.lane or lane_for(cfg, "full"),
                            "run_id": started.get("run_id"), "task_id": started.get("task_id"),
                            "held_by": holder.get("suite_id"),
                            **({"waited_s": round(time.monotonic() - t_wait, 1)} if wait else {})})
                # §16.6: counted on the run, for the parallel-work measures (§16.7). Unlocked: the worker that owns
                # the run is the one waiting in this shell, so nothing else writes it now
                if started.get("run_id"):
                    rec = runs.load(q, started["run_id"])
                    rec["lane_busy"] = int(rec.get("lane_busy") or 0) + 1
                    runs.save(q, rec)
            except Exception:  # noqa: BLE001  (a record that fails never changes the answer)
                pass
            print(f"ccp suite: busy: lane {a.lane or 'full'} is exclusive (plane.json suite.exclusive_lanes, SPEC §16.6) "
                  f"and held by {holder.get('suite_id') or 'another run'}"
                  + (f" (task {holder['task_id']})" if holder.get("task_id") else "")
                  + (f" since {holder['at']}" if holder.get("at") else "")
                  + (f"; its usual run is {usual:.0f} s" if usual is not None else "")
                  + f". Nothing ran. Do other work, then run it again, or wait for it with `--wait SECONDS` "
                  f"(exit {BUSY_EXIT}).", file=sys.stderr)
            return BUSY_EXIT
    if q is not None and started is not None:
        try:
            _append(q, started)
        except Exception as e:  # noqa: BLE001
            warn(f"not recorded ({str(e).splitlines()[0][:200] if str(e) else type(e).__name__}): running the tests anyway")
            q = started = None
    if q is not None:
        try:  # opportunistic, bounded, never the run's problem
            prune_logs(q, _keep_days(cfg))
        except Exception:  # noqa: BLE001
            pass
    # 2. the run itself
    try:
        pattern = _count_re(cfg)
    except re.error:
        pattern = re.compile(DEFAULT_COUNT_RE.encode())
    scfg = _summary_cfg(cfg)
    fpats = _field_patterns(scfg)
    # Summary mode (§14.3, 2026-10-22): the output goes to a log file, and ccp prints a start line,
    # then the counts and, on a failure, the failing sections. A log that cannot be opened is a
    # warning: the run streams as --full does.
    log: Path | None = None
    log_fd: int | None = None
    if mode == "summary":
        try:
            log = log_path(q, started, suite_id, log_arg)
            log_fd = _open_log(log)
        except Exception as e:  # noqa: BLE001  (never stands between a worker and its tests)
            warn(f"no log file ({str(e).splitlines()[0][:200] if str(e) else type(e).__name__}): streaming the output")
            log = log_fd = None
    t0 = time.monotonic()
    got: list[int] = []
    _flush()
    if log is not None:
        _say(f"ccp suite: {suite_id}: the output goes to {log}; a summary follows when it ends (--full streams it)\n")
    # Its own process group, so a signal reaches every process of the suite (a script's children
    # too), except under a terminal, where the command must stay in the foreground group.
    own_group = not os.isatty(0)
    merged = _same_file(1, 2)  # one destination: one pipe, so the interleaving is kept
    current: dict[str, Any] = {}  # the stage's process, for the signal handler

    def forward(sig: int, _frame: Any) -> None:
        got.append(sig)
        proc = current.get("proc")
        if proc is None:
            return
        try:
            os.killpg(proc.pid, sig) if current.get("group") else proc.send_signal(sig)
        except OSError:
            pass
    old = {}
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            old[s] = signal.signal(s, forward)
        except (ValueError, OSError):  # not the main thread
            pass
    counters = [_Counter(pattern, fpats), _Counter(pattern, fpats)]
    staged = bool(stages[0].get("staged"))
    done: list[dict[str, Any]] = []  # §14.2: each stage that ran: name, seconds, exit code
    results: list[tuple[dict[str, Any] | None, str | None]] = []
    code, rc = 0, 0
    cut: int | None = None  # §14.2: the stage a signal kept from starting
    provers = stage_provers(cfg, a.lane, command, stages, started)
    proven: list[dict[str, Any]] = []  # §14.2: each stage a prover skipped: stage, prover name, exit code
    diff: tuple[dict[str, str] | None, str] | None = None
    reached = 0  # the stages run or skipped so far
    try:
        for i, stage in enumerate(stages):
            if got:
                cut = i
                break  # interrupted: no later stage starts
            if stage["name"] in provers and cfg is not None and q is not None:
                if diff is None:
                    diff = task_diff(cfg, q)
                    if diff[0] is None:
                        _stage_mark(log_fd, f"ccp suite: no prover runs: {diff[1]}\n")
                skip = None
                for pr in provers[stage["name"]] if diff[0] is not None else []:
                    cmd = fill(str(pr["command"]), {"task_id": str(started["task_id"]), **diff[0]})
                    pcode = _prove(cmd, cfg.root, {**(os.environ if caller_env is None else caller_env), **wt_env},
                                   current)
                    _stage_mark(log_fd, f"ccp suite: stage {stage['name']}: prover {pr['name']} "
                                        + ("timed out\n" if pcode is None else f"exit {pcode}\n"))
                    if got or pcode == 0:
                        skip = None if got else {"stage": stage["name"], "prover": str(pr["name"]), "exit_code": 0}
                        break
                if got:
                    cut = i
                    break  # interrupted while proving: the stage does not start
                if skip:
                    proven.append(skip)
                    reached = i + 1
                    _stage_mark(log_fd, f"ccp suite: stage {stage['name']}: skipped, prover {skip['prover']} exit 0\n")
                    continue
            if staged:
                _stage_mark(log_fd, f"ccp suite: stage {stage['name']}: started\n")
            # The caller's environment, the worktree's fields for a lane's stages, and CCP_SUITE_ID, nothing
            # else (§14.2): outside a `ccp wt` worktree, a test cache that hashes the environment finds the
            # same entries from a plain shell and from `ccp suite run`. Each stage writes its own result file.
            result_path = Path(tempfile.gettempdir()) / f"ccp-suite-result-{suite_id}{f'-{i}' if i else ''}.json"
            env = {**(os.environ if caller_env is None else caller_env), **wt_env,
                   **for_child({"CCP_SUITE_ID": suite_id, "CCP_SUITE_RESULT": str(result_path)})}
            rc, s_secs = _run_stage(stage["argv"], env, log_fd, merged, own_group, counters, current)
            code = 128 - rc if rc < 0 else rc
            results.append(read_result(result_path))
            if stage["name"] is not None:
                done.append({"name": stage["name"], "seconds": round(s_secs, 3), "exit_code": code})
            if staged:
                _stage_mark(log_fd, f"ccp suite: stage {stage['name']}: exit {code}, {s_secs:.1f} s\n")
            reached = i + 1
            if code != 0:
                break
    finally:
        for s, h in old.items():
            try:
                signal.signal(s, h)
            except (ValueError, OSError):
                pass
        if log_fd is not None:
            os.close(log_fd)
    seconds = time.monotonic() - t0
    sig = got[0] if got else (-rc if rc < 0 else None)
    failed_stage = done[-1]["name"] if done and code != 0 else None
    if cut is not None:
        # A signal between stages (§14.2): the run never passes with a stage unrun. It exits as if
        # the signal had ended a command, and names the first stage not run.
        code = 128 + got[0]
        failed_stage = stages[cut]["name"]
    not_run = [st["name"] for st in stages[reached:]] if staged else []
    dig = None
    if log is not None:
        try:  # the counts and the failure's text, from the log; reading it never costs the exit code
            with log.open("rb") as fh:
                while chunk := fh.read(65536):
                    counters[0].feed(chunk)
            counters[0].close()
            dig = digest(log, scfg, pattern)
        except Exception as e:  # noqa: BLE001
            warn(f"could not read the log back ({type(e).__name__}): see {log}")
    totals = [c.total for c in counters if c.total is not None]
    tests = sum(totals) if totals else None
    fields: dict[str, int | None] = {}
    for f in SUMMARY_FIELDS:
        vals = [c.sums[f] for c in counters if f in c.sums]
        fields[f] = sum(vals) if vals else None
    source = "output"
    valid = [r for r, _p in results if r is not None]
    problem = next((p for _r, p in results if p), None)
    failures: list[str] = []
    if valid:  # §14.3: the gate's own result is authoritative: every counter is its (summed over the stages)
        source = "result"
        tests = _sum([r.get("tests") for r in valid])
        per = []
        for r in valid:
            one = {f: r.get(f) for f in SUMMARY_FIELDS}
            if "failed" not in r and isinstance(r.get("failures"), list):
                one["failed"] = len(r["failures"])
            per.append(one)
        fields = {f: _sum([x[f] for x in per]) for f in SUMMARY_FIELDS}
        failures = [str(x.get("id")) for r in valid for x in r.get("failures") or []
                    if isinstance(x, dict) and x.get("id")]
    if tests is None and fields.get("ran") == 0 and fields.get("cached"):
        tests = 0  # every unit was a cache hit: no test ran, and that is a count (§14.5)
    stage_text = stages_line(suite_id, done, not_run, proven) if staged else None
    if log is not None:
        _say(render_summary(suite_id, log, code, a.lane, seconds, tests, fields, _sig_name(sig), dig,
                            scfg["max_chars"], stage_text))
    elif stage_text:
        _say(stage_text + "\n")
    if problem:  # its own line, never swallowed by the one-warning limit; also on the record
        _say(f"ccp suite: {suite_id}: the gate's result file was not used ({problem}); "
             + ("the other stages' results stand\n" if valid else "the output's counts stand\n"))
    if failures:
        shown = failures[:SHOW_MAX]
        _say(f"ccp suite: {suite_id}: failing (from the gate's result): {', '.join(_cut(x) for x in shown)}"
             + (f" and {len(failures) - len(shown)} more" if len(failures) > len(shown) else "") + "\n")
    _finish(cfg, q, started, warn, code, seconds, tests, sig, fields, log, source, problem,
            done if stages[0]["name"] is not None else None, failed_stage, proven)
    if lane_fd is not None and lane_fd >= 0 and q is not None:
        release_lane(q, suite_id)  # a normal end: the next holder is not told this one died
    return code


RESULT_INTS = ("tests", "ran", "cached", "cached_tests", "skipped", "failed")
RESULT_MAX = 1_000_000  # bytes read from a result file, at most


def read_result(p: Path) -> tuple[dict[str, Any] | None, str | None]:
    """The gate's result file (CCP_SUITE_RESULT, contracts/suite_result.schema.json), removed once
    read: (its numbers, None), (None, None) when the gate wrote none, or (None, why) when it is not a
    result. Only the counters and the failure ids are taken; anything else in it is ignored."""
    if not os.path.lexists(p):
        return None, None
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            data = os.read(fd, RESULT_MAX + 1)
        finally:
            os.close(fd)
        if len(data) > RESULT_MAX:
            return None, "larger than 1 MB"
        obj = json.loads(data.decode("utf-8", "replace"))
    except OSError as e:
        return None, f"unreadable ({'a symlink' if os.path.islink(p) else type(e).__name__})"
    except ValueError as e:
        return None, f"not JSON ({type(e).__name__})"
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass
    if not isinstance(obj, dict):
        return None, "not a JSON object"
    out: dict[str, Any] = {}
    for k in RESULT_INTS:
        if k in obj:
            v = obj[k]
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                return None, f"`{k}` is not a non-negative integer"
            out[k] = v
    if "seconds" in obj and (isinstance(obj["seconds"], bool) or not isinstance(obj["seconds"], (int, float))):
        return None, "`seconds` is not a number"
    if "failures" in obj:
        if not isinstance(obj["failures"], list):
            return None, "`failures` is not a list"
        out["failures"] = [x for x in obj["failures"] if isinstance(x, dict)][:1000]
    if "tests" not in out and "ran" not in out and "cached" not in out:
        return None, "it gives none of tests, ran or cached"
    return out, None


def _sig_name(sig: int | None) -> str | None:
    try:
        return signal.Signals(sig).name if sig else None
    except ValueError:
        return f"signal {sig}"


def run_cold(cached: Any) -> bool | None:
    """Whether a run was cold, from its own count (§14.6): nothing cached is cold, any unit cached is
    warm; with no `cached` count the run cannot tell (None), and §27.2's cache start decides."""
    if isinstance(cached, bool) or not isinstance(cached, int):
        return None
    return cached == 0


def _finish(cfg: Config | None, q: Path | None, started: dict[str, Any] | None, warn: _Warn, code: int,
            seconds: float, tests: int | None, sig: int | None, fields: dict[str, int | None] | None = None,
            log: Path | None = None, source: str = "output", problem: str | None = None,
            stages: list[dict[str, Any]] | None = None, failed_stage: str | None = None,
            proven: list[dict[str, Any]] | None = None) -> None:
    if q is None or started is None:
        return
    name = _sig_name(sig)
    nums = {f: (fields or {}).get(f) for f in SUMMARY_FIELDS}
    cold = run_cold(nums.get("cached"))
    row = {"op": "ended", "suite_id": started["suite_id"], "at": iso(), "exit_code": code,
           "seconds": round(seconds, 3), "tests": tests, **nums, "cold": cold, "counts_from": source,
           **({"result_problem": problem[:80]} if problem else {}),
           "log": str(log) if log else None, "interrupted": name,
           **({"stages": stages, "failed_stage": failed_stage} if stages is not None else {}),
           **({"proven_skips": proven} if proven else {})}
    try:
        _append(q, row)
        if cfg is not None:
            emit(q, cfg, started.get("task_id") or "", "suite", "recorded",
                 {"suite_id": started["suite_id"], "run_id": started.get("run_id"), "phase": started.get("phase"),
                  "lane": started.get("lane"), "exit_code": code, "seconds": row["seconds"], "tests": tests, **nums,
                  "cold": cold, "counts_from": source, "interrupted": name,
                  **({"stages": stages, "failed_stage": failed_stage} if stages is not None else {}),
                  **({"proven_skips": proven} if proven else {})},
                 _actor_for(started.get("seat")))
    except Exception as e:  # noqa: BLE001
        warn(f"the run's end was not recorded ({str(e).splitlines()[0][:200] if str(e) else type(e).__name__})")
        return
    try:
        if cfg is not None:
            from ccp import board  # noqa: PLC0415
            board.refresh(cfg)
    except Exception:  # noqa: BLE001  (never the run's problem)
        pass


def main_run(a: Any, command: list[str] | None) -> int:
    """`ccp suite run`, before and without a usable plane.json: anything that goes wrong finding the
    product or its config stops a lane lookup and the recording, never a command given after `--`."""
    warn = _Warn()
    caller_env = dict(os.environ)  # before ccp sets anything for itself
    cfg = None
    try:
        from ccp import cli, config  # noqa: PLC0415
        cfg = config.load(config.find_root(a.root))
    except Exception as e:  # noqa: BLE001  (no git, unreadable or non-UTF-8 plane.json, …)
        if not command:
            print(f"ccp: {e}", file=sys.stderr)
            return 2
        warn(f"{str(e).splitlines()[0][:200] if str(e) else type(e).__name__}: running the tests without recording them")
    if cfg is not None and not os.environ.get("QUEUE_ROOT") and envvar("CCP_NO_BINDING_QUEUE") != "1":
        try:
            if q := cli.binding_queue_root(cfg):
                os.environ["QUEUE_ROOT"] = q
        except Exception:  # noqa: BLE001
            pass
    return run(cfg, a, command, warn, record=cfg is not None,  # no config, no project id: nothing to record
               caller_env=caller_env)


def unparsed(command: list[str]) -> int:
    """`ccp suite run … -- COMMAND` whose options did not parse (argparse said why): the command
    still runs, unrecorded, in the mode a terminal decides (summary mode logs to a temp file)."""
    print("ccp suite: the options above did not parse: running the command without recording it",
          file=sys.stderr, flush=True)
    a = type("A", (), {"lane": None, "phase": None, "run": None, "task": None, "root": None, "output": None,
                       "log": None})()
    return run(None, a, command, _Warn(), record=False)


# ---------------------------------------------------------------------------------------- read


KILLED_AFTER_S = 30 * 60  # an open row this old, or whose run has since stopped or reported, was killed


def _epoch(at: Any) -> float | None:
    from datetime import datetime  # noqa: PLC0415
    try:
        return datetime.fromisoformat(str(at).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def fold(q: Path, now: float | None = None) -> list[dict[str, Any]]:
    """Every suite run, oldest first: its started row with its end. One with no end is `open` while
    it may still be going, and `killed` once its run has stopped or reported since it started, or
    it is older than KILLED_AFTER_S. A killed run's seconds run to its run's stop or report when
    that is known (`seconds_estimated`), else they are unknown (None)."""
    out: dict[str, dict[str, Any]] = {}
    p = path(q)
    for line in p.read_text(errors="replace").splitlines() if p.is_file() else []:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("suite_id"), str):
            continue
        sid = row["suite_id"]
        if row.get("op") == "started":
            out[sid] = {k: v for k, v in row.items() if k not in ("op", "at")} | {"started_at": row.get("at"), "state": "open"}
        elif row.get("op") == "ended" and sid in out:
            st = out[sid]
            st.update(ended_at=row.get("at"), exit_code=row.get("exit_code"), seconds=row.get("seconds"),
                      tests=row.get("tests"), interrupted=row.get("interrupted"),
                      **{k: row.get(k) for k in (*SUMMARY_FIELDS, "log", "counts_from", "cold", "stages",
                                                  "failed_stage") if k in row})
            for old, new in LEGACY_FIELDS.items():  # a row written before the gate-result contract
                if old in row and new not in row:
                    st[new] = row[old]
            st["state"] = "interrupted" if row.get("interrupted") else ("passed" if row.get("exit_code") == 0 else "failed")
    now = time.time() if now is None else now
    recs: dict[str, dict[str, Any] | None] = {}
    for st in out.values():
        if st["state"] != "open":
            continue
        t0 = _epoch(st.get("started_at"))
        rid = st.get("run_id")
        if rid and rid not in recs:
            try:
                recs[rid] = runs.load(q, rid)
            except Exception:  # noqa: BLE001
                recs[rid] = None
        rec = recs.get(rid) if rid else None
        ends = sorted(e for e in (_epoch((rec or {}).get(k)) for k in ("stopped_at", "reported_at", "abandoned_at"))
                      if e is not None and t0 is not None and e >= t0)
        if ends or (t0 is not None and now - t0 > KILLED_AFTER_S):
            st["state"] = "killed"
            st["seconds"] = round(ends[0] - t0, 3) if ends else None
            st["seconds_estimated"] = True
    return list(out.values())


def _acc(acc: dict[str, Any], s: dict[str, Any]) -> None:
    acc["suite_runs"] += 1
    if s.get("state") == "killed":
        acc["suite_killed"] += 1
    try:
        acc["suite_s"] = round(acc["suite_s"] + float(s.get("seconds") or 0), 3)
    except (TypeError, ValueError):
        pass


def _blank() -> dict[str, Any]:
    return {"suite_s": 0.0, "suite_runs": 0, "suite_killed": 0}


def totals(suites: list[dict[str, Any]], task_id: str | None = None) -> dict[str, Any]:
    """Seconds and counts of finished suite runs, killed ones included (`suite_killed`; their time
    when known): per run, per task and per task's phase. A run still open counts in no total."""
    by_run: dict[str, dict[str, Any]] = {}
    by_task: dict[str, dict[str, Any]] = {}
    for s in suites:
        if s.get("state") == "open" or (task_id and s.get("task_id") != task_id):
            continue
        if s.get("run_id"):
            _acc(by_run.setdefault(s["run_id"], _blank()), s)
        if s.get("task_id"):
            t = by_task.setdefault(s["task_id"], {**_blank(), "phases": {}})
            _acc(t, s)
            _acc(t["phases"].setdefault(s.get("phase") or "unbound", _blank()), s)
    return {"by_run": by_run, "by_task": by_task}


def safe_totals(q: Path, task_id: str | None = None) -> dict[str, Any]:
    """totals(fold(q)), or none at all: a damaged suites file never breaks the board or `ccp usage`."""
    try:
        return totals(fold(q), task_id)
    except Exception:  # noqa: BLE001
        return {"by_run": {}, "by_task": {}}


def listing(cfg: Config, a: Any) -> dict[str, Any]:
    q = root()
    tid = None
    if a.task:
        from ccp.queue import task_meta  # noqa: PLC0415
        tid = str(task_meta(cfg, a.task)["task_id"])
    rows = [s for s in fold(q) if not tid or s.get("task_id") == tid]
    t = totals(rows, tid)
    return {"ok": True, "task_id": tid, "suites": rows, "by_run": t["by_run"],
            "by_task": t["by_task"]}


def attach(q: Path, report: dict[str, Any], task_id: str | None) -> dict[str, Any]:
    """`ccp usage`: each run row gains its suite seconds and runs; a task's report, its totals."""
    t = safe_totals(q, task_id)
    for r in report.get("runs") or []:
        r["suite"] = t["by_run"].get(r["run_id"], _blank())
    if task_id is not None:
        report["suite_total"] = t["by_task"].get(task_id, {**_blank(), "phases": {}})
    return report


def recorded_for(q: Path, run_id: str) -> dict[str, Any]:
    """The ended suite runs recorded against one run (`ccp report`'s cross-check)."""
    return totals(fold(q))["by_run"].get(run_id, _blank())


def table(report: dict[str, Any]) -> str:
    """`ccp usage`'s suite lines: time in recorded test runs, per run and for the task."""
    def killed(v: dict[str, Any]) -> str:
        return f", {v['suite_killed']} killed" if v.get("suite_killed") else ""
    lines = [f"suite {r['run_id']}: {r['suite']['suite_runs']} run(s), {r['suite']['suite_s']:.0f} s{killed(r['suite'])}"
             for r in report.get("runs") or [] if (r.get("suite") or {}).get("suite_runs")]
    tt = report.get("suite_total")
    if tt is not None and tt["suite_runs"]:
        by = ", ".join(f"{p} {v['suite_s']:.0f} s in {v['suite_runs']}" for p, v in sorted(tt["phases"].items()))
        lines.append(f"task {report.get('task_id')}: {tt['suite_runs']} suite run(s){killed(tt)}, {tt['suite_s']:.0f} s ({by})")
    elif tt is not None:
        lines.append(f"task {report.get('task_id')}: no suite runs recorded (ccp suite run)")
    return "\n".join(lines)


# §14.7: the test modules a change touches, for choosing the `part` lane. Nothing is run or recorded.
TEST_FILE_GLOB = "test*.py"  # the Python pack's test modules: unittest's default discovery pattern


def _git_lines(root: Path, *args: str) -> list[str]:
    """`git -C root <args>`'s output lines; a QueueError (exit 2) naming git's complaint when it fails."""
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise QueueError(f"git {args[0]} failed: {(r.stderr.strip().splitlines() or ['no output'])[-1]}", 2)
    return [ln for ln in r.stdout.splitlines() if ln.strip()]


def changed_paths(root: Path, since: str | None, given: list[str] | None) -> list[str]:
    """`--paths` as given (relative to the root), else what `git diff <since>` names against the working
    tree (renames as both paths) plus the untracked files git does not ignore; `since` defaults to HEAD."""
    if given:
        out = []
        for p in given:
            path = Path(p)
            if path.is_absolute():
                try:
                    path = path.resolve().relative_to(root.resolve())
                except ValueError:
                    raise QueueError(f"--paths {p}: not under the product root {root}", 2) from None
            out.append(path.as_posix().removeprefix("./"))
        return sorted(set(out))
    diff = _git_lines(root, "diff", "--name-only", "--no-renames", "--relative", since or "HEAD", "--")
    return sorted(set(diff) | set(_git_lines(root, "ls-files", "--others", "--exclude-standard")))


def _py_module(rel: str) -> str | None:
    """The dotted module a root-relative `.py` path is (`pkg/__init__.py` is `pkg`), or None."""
    if not rel.endswith(".py"):
        return None
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts and all(p.isidentifier() for p in parts) else None


def _py_imports(text: str, module: str, is_pkg: bool) -> set[str]:
    """Every module a file's import statements name, wherever they sit (a function's too): `import a.b`
    gives a.b, `from a import b` gives a and a.b (b may be a submodule), a relative import is resolved
    against the file's own package. Each one's parent packages are added: importing a.b runs a."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    own = module.split(".") if is_pkg else module.split(".")[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(own):
                    continue
                parts = own[:len(own) - (node.level - 1)] + (node.module.split(".") if node.module else [])
            else:
                parts = node.module.split(".") if node.module else []
            base = ".".join(parts)
            if base:
                names.add(base)
            names.update(f"{base}.{a.name}" if base else a.name for a in node.names if a.name != "*")
    return {".".join(n.split(".")[:i]) for n in names for i in range(1, n.count(".") + 2)}


def _read(p: Path) -> str | None:
    try:
        return p.read_text(errors="replace") if p.is_file() and not p.is_symlink() else None
    except OSError:
        return None


def _python_affected(root: Path, changed: list[str]) -> list[str]:
    """The Python pack: each `test*.py` file git tracks or would track that changed itself, imports a
    changed module directly or through one package level (a package it imports whose `__init__.py`
    imports it), or names a changed file's name in its text."""
    files = _git_lines(root, "ls-files", "--cached", "--others", "--exclude-standard")
    changed_mods = {m for m in map(_py_module, changed) if m}
    packages = {m: rel for rel in files if rel.endswith("/__init__.py") and (m := _py_module(rel))}
    init_imports: dict[str, set[str]] = {}

    def through(pkg: str) -> set[str]:
        if pkg not in init_imports:
            init_imports[pkg] = _py_imports(_read(root / packages[pkg]) or "", pkg, True)
        return init_imports[pkg]

    names = {Path(c).name for c in changed}
    name_re = re.compile("|".join(rf"(?<![\w.-]){re.escape(n)}(?![\w-])" for n in sorted(names))) if names else None
    out, touched = set(), set(changed)
    for rel in files:
        mod = _py_module(rel)
        if not mod or not fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], TEST_FILE_GLOB):
            continue
        text = _read(root / rel)
        if text is None:  # deleted in the working tree, or not a regular file
            continue
        if rel in touched:
            out.add(mod)
            continue
        direct = _py_imports(text, mod, False)
        reached = direct.union(*(through(p) for p in direct if p in packages))
        if reached & changed_mods or (name_re is not None and name_re.search(text)):
            out.add(mod)
    return sorted(out)


AFFECTED_READERS = {"python": _python_affected}


def affected(cfg: Config, since: str | None, paths: list[str] | None) -> tuple[list[str], list[str]]:
    """(the changed paths, the test modules they touch), read by the product's language pack
    (`package_docs.language`; its default when the block is absent)."""
    from ccp.config import PACKAGE_DOCS_DEFAULTS  # noqa: PLC0415
    lang = (cfg.package_docs or PACKAGE_DOCS_DEFAULTS)["language"]
    reader = AFFECTED_READERS.get(lang)
    if reader is None:
        raise QueueError(f"package_docs.language {lang!r} has no test reader; one of: "
                         f"{', '.join(sorted(AFFECTED_READERS))}", 2)
    changed = changed_paths(cfg.root, since, paths)
    return changed, (reader(cfg.root, changed) if changed else [])


def main_affected(cfg: Config, a: Any) -> int:
    """`ccp suite affected`: the test modules, one per line; a note on stderr when there are none."""
    try:
        changed, mods = affected(cfg, a.since, a.paths)
    except QueueError as e:
        print(f"ccp suite affected: {e}", file=sys.stderr)
        return e.code
    for m in mods:
        print(m)
    if not mods:
        print(f"ccp suite affected: no test module depends on the {len(changed)} changed path(s)", file=sys.stderr)
    return 0
