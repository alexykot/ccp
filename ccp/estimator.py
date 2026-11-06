"""Task estimation, phase B (SPEC §26.3): the estimator seat.

  ccp tasks estimate ID [--force] [--dry-run] [--print-prompt]   one agent estimate
  ccp tasks estimate --all [--max N] [--dry-run] [--detach]       every open task without a current one

A headless `claude -p` on Sonnet at medium effort (`HEADLESS_MODEL`), pinned here like the
architect's, with **no tools** (`--tools ""`): everything it needs is rendered into the prompt
(`templates/prompts/estimate.md`), so a call is one model turn, cheap, and cannot read or write
anything. It runs in an empty temporary directory under `--safe-mode --setting-sources local`
(`ISOLATION`), so no CLAUDE.md, memory, settings file, hook, plugin or MCP server, the user's or a
product's, joins its context. Its environment drops the API keys and carries `ccp.seat=estimator`
(`spec_maintainer.headless_env`) and the user settings' telemetry keys (`child_env`), so its
telemetry is still exported and lands on its own seat.

The prompt holds the task file (notes stripped), bounded excerpts of the ADR decisions and SPEC
sections it cites, the cited files' sizes, phase A's features, the reference class (the baseline's
tasks, with their actual phases, tokens, cost, rounds and findings), the baseline itself, the
calibration (phase D's factors and their sample sizes, ccp/calibrate.py), and the criteria table of the design. The answer is one
JSON object, validated strictly (`validate`); an invalid one is retried once with the errors, and a
second failure is recorded as a failed attempt in `estimator/calls.jsonl`, with no row: the
baseline stands. A valid answer is an `agent` row in `estimates/<task>.jsonl` (the same shape as a
baseline row, plus `complexity`, `waits`, `reasoning` and `seat`).

A task needs an agent estimate when it has none, its hash changed, or a dependency merged since the
last one (`stale`). `ccp tasks check` and `ccp tasks index` (the task-writing flow) notice those;
with `plane.json estimate.auto: true` (default false) they start `--all` detached, one batch at a
time (`estimator.lock`), and return at once. Estimates are advisory: nothing gates on them.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp import estimate as est
from ccp import adr, tasklog
from ccp.refs import ids as _ids
from ccp.refs import number_prefix
from ccp.config import Config
from ccp.queue import PLANE, append_jsonl, iso, read_json

SEAT = "estimator"
# Pinned like architecture_review.HEADLESS_MODEL (operator, 2026-10-22: "Sonnet headless at medium effort").
HEADLESS_MODEL = ["--model", "claude-sonnet-5-5", "--effort", "medium"]
NO_TOOLS = ["--tools", ""]
# No user customisation reaches the seat: --safe-mode turns off CLAUDE.md (user and project), auto-memory,
# skills, plugins, hooks, MCP servers, custom agents and output styles while auth (the OAuth login) and
# model selection work normally; --setting-sources local, in an empty temporary cwd, loads no settings
# file at all (not ~/.claude/settings.json). --bare would be stricter but reads no OAuth login.
ISOLATION = ["--safe-mode", "--setting-sources", "local"]
METHOD = "estimator-seat"
METHOD_V = 1
PROMPT_V = 2                      # 2: phase D's calibration factors replace the accuracy summary
TEMPLATE = PLANE / "templates" / "prompts" / "estimate.md"
LOCK = "estimator.lock"
DIR = "estimator"                 # QUEUE_ROOT/estimator/: calls.jsonl, <run>.log, <run>-<task>.failed.txt
CALL_TIMEOUT_S = 300
MAX_BUDGET_USD = "1.00"           # one call's ceiling (`--max-budget-usd`); a call costs about $0.10-0.30
MAX_DEFAULT = 10                  # `--all`: at most this many calls' worth of tasks per batch
RATINGS = ("low", "med", "high")
# The estimation design's criteria.
CRITERIA = (
    ("suite_runs", "Suite runs needed",
     "Most wall time is test suites. Which modules the change touches, the slow modules among their dependents, "
     "and DoD rehearsal runs decide how many and how long."),
    ("context_size", "Context size",
     "Tokens grow with requests times context: many or large cited files make a large implementer context, which drives cost."),
    ("fix_round_risk", "Fix-round risk",
     "Fixture fan-out and the largest contexts led to fix rounds. One fix round adds about 20-40 min plus a re-review."),
    ("dod_shape", "DoD shape",
     "The number and kind of dod_checks (cmd, story, mutation). Mutation and multi-step checks lengthen verify."),
    ("novelty", "Novelty",
     "Whether a close reference task exists. A new module or ADR means a wide band; a refactor in a known area a narrow one."),
    ("waits", "Waits",
     "Spec questions, gates that need the operator, external dependencies. Calendar time, not agent time: flag them separately."),
)
# Prompt bounds (characters): the prompt stays small whatever the task cites.
B_TASK, B_ADR, B_ADRS, B_SPEC, B_SPECS, B_CITED, B_TITLE, B_CALIB = 12000, 1500, 6000, 1200, 4000, 40, 80, 1500
REASONING_MAX, REASON_MAX = 600, 200


# ------------------------------------------------------------------------------------ pins

def pins() -> dict[str, Any]:
    pick = lambda k: HEADLESS_MODEL[HEADLESS_MODEL.index(k) + 1]  # noqa: E731
    return {"model": pick("--model"), "effort": pick("--effort"),
            "source": "ccp/estimator.py HEADLESS_MODEL (claude -p flags)"}


# ------------------------------------------------------------------------------------ prompt inputs

def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n].rstrip() + f"\n[... cut at {n} characters]"


def _heading_block(text: str, pattern: str) -> str | None:
    """The block under the first heading matching `pattern`, up to the next heading of its level or higher."""
    m = re.search(rf"^(#+)[ \t]+{pattern}.*$", text, re.M)
    if not m:
        return None
    level = len(m.group(1))
    nxt = re.search(rf"^#{{1,{level}}}[ \t]", text[m.end():], re.M)
    return text[m.start():m.end() + nxt.start() if nxt else len(text)]


def adr_excerpts(cfg: Config, refs: list[str]) -> str:
    """Each cited ADR decision (`0035 D1`: its `D1` block), or the ADR's head and its decision titles
    (`0039`), each at most B_ADR characters and all of them at most B_ADRS."""
    out, used, seen = [], 0, set()
    for ref in refs:
        parsed = _ids(cfg).parse_adr_ref(ref)
        n = parsed.number if parsed else None
        dec = parsed.decision if parsed else None
        key = (n, dec)
        if n is None or key in seen:
            continue
        seen.add(key)
        f = adr.find_file(cfg, n)
        if f is None:
            out.append(f"### {ref}: no ADR file found")
            continue
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        if dec:
            block = adr.decision_block(text, dec) or f"(no D{dec} in {f.name})"
        else:
            title = (re.search(r"^# .*$", text, re.M) or [f.name])[0]
            heads = adr.decision_titles(text)
            block = title + ("\nDecisions: " + "; ".join(heads) if heads else "\n" + text[:B_ADR])
        piece = f"### {ref} ({cfg.rel(f)})\n{_clip(block, B_ADR)}"
        if used + len(piece) > B_ADRS:
            out.append(f"[further ADR excerpts left out: the excerpts are capped at {B_ADRS} characters]")
            break
        out.append(piece)
        used += len(piece)
    return "\n\n".join(out) or "None cited."


def _spec_files(cfg: Config) -> list[Path]:
    """The product's SPEC files, in `estimate.spec_paths` order (globs relative to the root, §26.3)."""
    out: list[Path] = []
    for pat in (cfg.estimate or {}).get("spec_paths") or ["docs/SPEC.md", "SPEC.md", "docs/spec/*.md", "spec/*.md"]:
        hits = sorted(cfg.root.glob(pat)) if any(ch in pat for ch in "*?[") else [cfg.root / pat]
        out += [p for p in hits if p.is_file() and p not in out]
    return out


def spec_excerpts(cfg: Config, refs: list[str]) -> str:
    """Each cited SPEC section (`S52`: the heading that starts with it), at most B_SPEC characters
    each and B_SPECS in all."""
    out, used = [], 0
    files = _spec_files(cfg)
    texts = []
    for f in files:
        try:
            texts.append((f, f.read_text(errors="replace")))
        except OSError:
            continue
    for ref in dict.fromkeys(str(r).strip() for r in refs if str(r).strip()):
        block = None
        for f, text in texts:
            block = _heading_block(text, re.escape(ref) + r"\b")
            if block:
                break
        piece = f"### {ref}\n{_clip(block, B_SPEC)}" if block else f"### {ref}: no SPEC heading found"
        if used + len(piece) > B_SPECS:
            out.append(f"[further SPEC excerpts left out: the excerpts are capped at {B_SPECS} characters]")
            break
        out.append(piece)
        used += len(piece)
    return "\n\n".join(out) or "None cited."


def cited_sizes(cfg: Config, text: str) -> str:
    """The cited paths that exist, with their lines, then the ones that do not (often files the task
    creates, sometimes not paths at all), at most B_CITED in all."""
    paths = est.cited(text, cfg)
    lines = est._lines_now(cfg.root, paths)
    there = [f"- {p}: {lines[p]} lines" if p in lines else f"- {p}: a directory" for p in paths
             if p in lines or (cfg.root / p).is_dir()]
    gone = [p for p in paths if p not in lines and not (cfg.root / p).is_dir()]
    rows = there[:B_CITED]
    if len(there) > B_CITED:
        rows.append(f"- [{len(there) - B_CITED} more left out]")
    if gone:
        rows.append(f"- not found ({len(gone)}): " + ", ".join(gone[:15]) + (" ..." if len(gone) > 15 else ""))
    if lines:
        rows.append(f"- in all: {len(lines)} existing files, {sum(lines.values())} lines")
    return "\n".join(rows) or "None."


def _mins(s: Any) -> str:
    return "-" if s is None else f"{float(s) / 60:.0f}"


def reference_class(pool: list[dict[str, Any]], b: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    """The baseline's reference tasks (wall first, then those its tokens came from), at most 8,
    with their actuals: numbers, ids and a short title."""
    by = {h["task_id"]: h for h in pool}
    ids = list(dict.fromkeys([*b.get("reference_tasks", []), *b.get("reference_tasks_tokens", [])]))[:8]
    out = []
    for tid in ids:
        h = by.get(tid)
        if not h:
            continue
        a = h["actual"]
        out.append({"task_id": tid, "title": str(h["task"].get("title") or "")[:B_TITLE],
                    "similarity": round(est.similarity(target, h["features"]), 2),
                    "kind": h["features"].get("kind"), "areas": (h["features"].get("areas") or [])[:6],
                    "cited_lines": h["features"].get("cited_lines"), "dod_checks": h["features"].get("dod_checks"),
                    "wall_min": round(float(a["wall_s"]) / 60), "phases_min": {
                        ph: (None if (v := (a.get("phases") or {}).get(ph)) is None else round(float(v) / 60))
                        for ph in est.PHASES},
                    "tokens": a.get("tokens"), "cost_usd": a.get("cost_usd"), "rounds": a.get("rounds"),
                    "findings": a.get("findings"), "merged_at": a.get("merged_at")})
    return out


def _refs_text(refs: list[dict[str, Any]]) -> str:
    if not refs:
        return "None: no completed task to compare with."
    return "\n".join(json.dumps(r, ensure_ascii=False, separators=(", ", ": ")) for r in refs)


def _baseline_text(b: dict[str, Any]) -> str:
    ph = "; ".join(f"{p} {_mins((v or {}).get('p50_s'))}-{_mins((v or {}).get('p90_s'))}" for p, v in b["phases"].items())
    tk, c = b.get("tokens") or {}, b.get("cost_usd") or {}
    return (f"total {_mins(b['total']['p50_s'])}-{_mins(b['total']['p90_s'])} min (P50-P90); phases (min): {ph}\n"
            f"tokens {tk.get('p50', '-')}-{tk.get('p90', '-')}; cost ${c.get('p50', '-')}-${c.get('p90', '-')}\n"
            f"rounds: review P50 {b['rounds'].get('review_p50')}, fix-round share {b['rounds'].get('fix_risk')}\n"
            f"reference class tier: {b['tier']} ({len(b['reference_tasks'])} of {b['pool']} completed tasks); "
            f"novelty (completed tasks sharing): {json.dumps(b['novelty'])}")


def calibration(q: Path, cfg: Config | None = None) -> str:
    """Phase D: the calibration factors and their sample sizes (ccp/calibrate.py), bounded."""
    from ccp import calibrate  # noqa: PLC0415
    by = est.all_rows(q)
    if not any(est.latest(rs, "actual") for rs in by.values()):
        return "No task has actuals yet."
    return calibrate.prompt_text(calibrate.model(q, cfg, by), B_CALIB)


def _criteria_text() -> str:
    return "\n".join(f"- `{k}` ({name}): {why}" for k, name, why in CRITERIA)


def schema_text() -> str:
    crit = ", ".join(f'"{k}": {{"rating": "low|med|high", "reason": "one line"}}' for k, _, _ in CRITERIA)
    ph = ", ".join(f'"{p}": {{"p50_min": n, "p90_min": n}}' for p in est.PHASES)
    return ("{\n"
            f'  "complexity": {{{crit}}},\n'
            '  "rounds": {"review_p50": n, "fix_risk": 0..1},\n'
            f'  "phases": {{{ph}}},\n'
            '  "total": {"p50_min": n, "p90_min": n},\n'
            '  "tokens": {"p50": n, "p90": n},\n'
            '  "cost_usd": {"p50": n, "p90": n},\n'
            '  "reference_tasks": ["NNNN-..."],\n'
            '  "waits": [],\n'
            '  "reasoning": "at most 600 characters"\n'
            "}")


def render(cfg: Config, q: Path, t: dict[str, Any], feats: dict[str, Any], b: dict[str, Any],
           refs: list[dict[str, Any]]) -> str:
    """The seat's prompt: plain text, every part bounded."""
    text = est.strip_notes(str(t.get("_text") or ""))
    parts = {
        "CRITERIA": _criteria_text(),
        "TASK": _clip(text, B_TASK),
        "FEATURES": json.dumps(feats, ensure_ascii=False),
        "CITED": cited_sizes(cfg, text),
        "ADRS": adr_excerpts(cfg, [str(x) for x in tasklog._as_list(t.get("adr_refs"))]),
        "SPECS": spec_excerpts(cfg, [str(x) for x in tasklog._as_list(t.get("spec_refs"))]),
        "REFERENCES": _refs_text(refs),
        "BASELINE": _baseline_text(b),
        "CALIBRATION": calibration(q, cfg),
        "SCHEMA": schema_text(),
    }
    out = TEMPLATE.read_text()
    # One pass, so a placeholder-looking string inside a task or an excerpt is never expanded.
    return re.sub(r"\{\{([A-Z]+)\}\}", lambda m: parts.get(m.group(1), m.group(0)), out)


# ------------------------------------------------------------------------------------ validation

def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def _band(errs: list[str], name: str, d: Any, lo_key: str, hi_key: str, zero_ok: bool = False,
          cap: float | None = None) -> None:
    if not isinstance(d, dict):
        errs.append(f"{name} must be an object with {lo_key} and {hi_key}")
        return
    a, b = d.get(lo_key), d.get(hi_key)
    if not _num(a) or not _num(b):
        errs.append(f"{name}.{lo_key} and {name}.{hi_key} must be numbers")
        return
    if a < 0 or b < 0 or (not zero_ok and (a <= 0 or b <= 0)):
        errs.append(f"{name}: values must be {'zero or ' if zero_ok else ''}positive")
    if a > b:
        errs.append(f"{name}: {lo_key} {a} is above {hi_key} {b}")
    if cap is not None and b > cap:
        errs.append(f"{name}: {hi_key} {b} is beyond {cap:g}")


def validate(obj: Any, offered: list[str]) -> list[str]:
    """Every rule the answer must meet; [] when it is a valid estimate."""
    if not isinstance(obj, dict):
        return ["the answer is not a JSON object"]
    errs: list[str] = []
    missing = [k for k in ("complexity", "rounds", "phases", "total", "tokens", "cost_usd", "reference_tasks", "reasoning")
               if k not in obj]
    if missing:
        errs.append("missing keys: " + ", ".join(missing))
    cx = obj.get("complexity")
    if "complexity" in obj:
        if not isinstance(cx, dict):
            errs.append("complexity must be an object")
        else:
            for k, _, _ in CRITERIA:
                c = cx.get(k)
                if not isinstance(c, dict) or c.get("rating") not in RATINGS:
                    errs.append(f"complexity.{k}.rating must be one of {', '.join(RATINGS)}")
                elif not isinstance(c.get("reason"), str) or not c["reason"].strip() or len(c["reason"]) > REASON_MAX \
                        or "\n" in c["reason"].strip():
                    errs.append(f"complexity.{k}.reason must be one line of at most {REASON_MAX} characters")
    r = obj.get("rounds")
    if "rounds" in obj:
        if not isinstance(r, dict) or not _num(r.get("review_p50")) or not 1 <= r["review_p50"] <= 10:
            errs.append("rounds.review_p50 must be a number from 1 to 10")
        if not isinstance(r, dict) or not _num(r.get("fix_risk")) or not 0 <= r["fix_risk"] <= 1:
            errs.append("rounds.fix_risk must be a number from 0 to 1")
    ph = obj.get("phases")
    if "phases" in obj:
        if not isinstance(ph, dict):
            errs.append("phases must be an object")
        else:
            for p in est.PHASES:
                if p not in ph:
                    errs.append(f"phases.{p} is missing")
                else:
                    _band(errs, f"phases.{p}", ph[p], "p50_min", "p90_min", zero_ok=p == "fix", cap=7 * 24 * 60)
    if "total" in obj:
        _band(errs, "total", obj["total"], "p50_min", "p90_min", cap=7 * 24 * 60)
    if "tokens" in obj:
        _band(errs, "tokens", obj["tokens"], "p50", "p90", cap=1e9)
    if "cost_usd" in obj:
        _band(errs, "cost_usd", obj["cost_usd"], "p50", "p90", cap=1000)
    rt = obj.get("reference_tasks")
    if "reference_tasks" in obj:
        if not isinstance(rt, list) or not all(isinstance(x, str) for x in rt):
            errs.append("reference_tasks must be a list of task ids")
        elif offered and not [x for x in rt if _match(x, offered)]:
            errs.append("reference_tasks must name at least one task of the reference class")
    rs = obj.get("reasoning")
    if "reasoning" in obj and (not isinstance(rs, str) or not rs.strip() or len(rs) > REASONING_MAX):
        errs.append(f"reasoning must be text of 1 to {REASONING_MAX} characters"
                    + (f" (it has {len(rs)})" if isinstance(rs, str) else ""))
    w = obj.get("waits", [])
    if not isinstance(w, list) or len(w) > 5 or not all(isinstance(x, str) and len(x) <= REASON_MAX for x in w):
        errs.append(f"waits must be a list of at most 5 short strings (each at most {REASON_MAX} characters)")
    return errs


def _match(x: str, offered: list[str]) -> str | None:
    x = x.strip()
    nx = number_prefix(x)
    return next((o for o in offered if o == x or (bool(nx) and number_prefix(o) == nx)), None)


def _secs(m: float) -> int:
    return int(round(float(m) * 60))


def to_row(tid: str, version: int, thash: str, feats: dict[str, Any], b: dict[str, Any], base_row: dict[str, Any] | None,
           ans: dict[str, Any], offered: list[str], deps_done: list[str], seat: dict[str, Any], cfg: Config) -> dict[str, Any]:
    """The `agent` row: the estimate row's shape (seconds, like the baseline), plus the profile."""
    named = list(dict.fromkeys(m for x in ans["reference_tasks"] if (m := _match(x, offered))))
    now = iso()
    p = pins()
    return {"at": now, "as_of": now, "task_id": tid, "source": "agent", "version": version, "task_hash": thash,
            "inputs": {"features": feats, "novelty": b["novelty"], "reference_tasks": named,
                       "reference_tasks_tokens": [], "offered": offered, "deps_done": deps_done,
                       "baseline": {"version": (base_row or {}).get("version"), "total": b["total"],
                                    "tokens": b["tokens"], "cost_usd": b["cost_usd"]},
                       "method": {"name": METHOD, "v": METHOD_V, "prompt_v": PROMPT_V, "model": p["model"],
                                  "effort": p["effort"], "tier": b["tier"], "pool": b["pool"],
                                  "k": int((cfg.estimate or {}).get("k") or est.K_DEFAULT)}},
            "phases": {ph: {"p50_s": _secs(ans["phases"][ph]["p50_min"]), "p90_s": _secs(ans["phases"][ph]["p90_min"])}
                       for ph in est.PHASES},
            "total": {"p50_s": _secs(ans["total"]["p50_min"]), "p90_s": _secs(ans["total"]["p90_min"])},
            "tokens": {"p50": int(round(ans["tokens"]["p50"])), "p90": int(round(ans["tokens"]["p90"]))},
            "cost_usd": {"p50": round(float(ans["cost_usd"]["p50"]), 2), "p90": round(float(ans["cost_usd"]["p90"]), 2)},
            "rounds": {"review_p50": ans["rounds"]["review_p50"], "fix_risk": round(float(ans["rounds"]["fix_risk"]), 2)},
            "complexity": {k: {"rating": ans["complexity"][k]["rating"], "reason": ans["complexity"][k]["reason"].strip()}
                           for k, _, _ in CRITERIA},
            "waits": [str(x) for x in ans.get("waits") or []],
            "reasoning": ans["reasoning"].strip(),
            "notes": f"estimator seat ({p['model']}, {p['effort']}); refs {','.join(number_prefix(x) or x[:4] for x in named)}"[:200],
            "seat": seat}


# ------------------------------------------------------------------------------------ the call

def _sm():
    from ccp import architect  # noqa: PLC0415  (puts scripts/observability on the path)
    return architect.sm, architect.ar


def argv_for(prompt: str) -> list[str]:
    sm, _ = _sm()
    argv = ["env"]
    for k in sm.STRIP_KEYS:
        argv += ["-u", k]
    return argv + [envvar("CCP_ESTIMATOR_CLAUDE_BIN") or "claude", "-p", prompt, *HEADLESS_MODEL, *NO_TOOLS,
                   *ISOLATION, "--strict-mcp-config", "--no-session-persistence", "--max-budget-usd", MAX_BUDGET_USD,
                   "--output-format", "json"]


def child_env(project_id: str) -> dict[str, str]:
    """The seat's environment: `headless_env` (no API keys; `ccp.project_id` and `ccp.seat=estimator`),
    plus the telemetry keys of the user settings' `env` (§24), which the seat no longer loads
    (`ISOLATION`): without them its usage would not be exported. A key the shell already sets wins;
    `OTEL_RESOURCE_ATTRIBUTES` keeps the settings' non-`ccp.` attributes ahead of the seat's."""
    from ccp import otel  # noqa: PLC0415
    sm, _ = _sm()
    env = sm.headless_env(project_id, SEAT)
    try:
        user = json.loads(otel.user_settings_path().read_text()).get("env")
    except (OSError, ValueError, AttributeError):
        user = None
    for k, v in (user.items() if isinstance(user, dict) else []):
        if not otel.TELEMETRY_KEY_RE.match(str(k)) or not isinstance(v, (str, int, float)) or isinstance(v, bool):
            continue
        if k == "OTEL_RESOURCE_ATTRIBUTES":
            extra = [x.strip() for x in str(v).split(",") if x.strip() and not x.strip().startswith("ccp.")]
            mine = [x for x in env[k].split(",") if x]
            env[k] = ",".join(dict.fromkeys([*extra, *mine]))
        elif k not in os.environ:
            env[k] = str(v)
    return env


def call(cfg: Config, q: Path, prompt: str, run_id: str, tid: str, actor: str = "system") -> tuple[dict[str, Any], str, int]:
    """One headless call: (the parsed `--output-format json` result, stderr, exit code). The tests
    replace this function; nothing else here starts a process that costs money."""
    sm, _ = _sm()
    argv = argv_for(prompt)
    audit = subprocess.run(
        ["bash", str(PLANE / "scripts" / "observability" / "write-prompt-audit.sh"), "--task-id", SEAT, "--phase", "estimate",
         "--prompt-file", "-", "--argv", json.dumps(argv[:argv.index("-p") + 1] + ["<prompt>"] + argv[argv.index("-p") + 2:]),
         "--actor", actor, "--project-id", cfg.project_id, "--worktree", str(cfg.root),
         "--notes", f"run_id={run_id} task_id={tid}"],
        input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
    if audit.returncode != 0:
        raise RuntimeError(f"write-prompt-audit failed: {audit.stderr.strip()[:300]}")
    cwd = tempfile.mkdtemp(prefix="ccp-estimator-")  # no product CLAUDE.md, settings or hooks join the context
    try:
        proc = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=CALL_TIMEOUT_S, env=child_env(cfg.project_id))
        code, so, se = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        code, se = 124, "timeout"
    finally:
        shutil.rmtree(cwd, ignore_errors=True)
    return sm.parse_claude_json(so), se, code


def _usage(res: dict[str, Any]) -> dict[str, Any]:
    mu = res.get("modelUsage") if isinstance(res.get("modelUsage"), dict) else {}
    tok = 0
    for v in mu.values():
        if isinstance(v, dict):
            tok += sum(int(v.get(k) or 0) for k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                                    "cacheCreationInputTokens"))
    cost = res.get("total_cost_usd")
    return {"cost_usd": round(float(cost), 4) if _num(cost) else None, "tokens": tok or None,
            "duration_ms": res.get("duration_ms"), "models": sorted(mu), "session_id": res.get("session_id")}


def _retry_prompt(prompt: str, raw: str, errs: list[str]) -> str:
    return (prompt + "\n\n## Your previous answer was rejected\n\n"
            + "\n".join(f"- {e}" for e in errs)
            + "\n\nYour previous answer (cut):\n" + _clip(raw or "(empty)", 3000)
            + "\n\nAnswer again with only the corrected JSON object.\n")


def _log(q: Path, rec: dict[str, Any]) -> None:
    append_jsonl(q / DIR / "calls.jsonl", rec)


def estimate_one(cfg: Config, q: Path, t: dict[str, Any], b: dict[str, Any], pool: list[dict[str, Any]], feats: dict[str, Any],
                 deps_done: list[str], run_id: str, actor: str = "system", dry_run: bool = False) -> dict[str, Any]:
    """One task: render, call, validate (retry once with the errors), write the row. A failure
    writes no row; the attempt is in `estimator/calls.jsonl` and the baseline stands."""
    from ccp import usage  # noqa: PLC0415
    _, ar = _sm()
    tid = str(t.get("task_id"))
    refs = reference_class(pool, b, feats)
    offered = [r["task_id"] for r in refs]
    prompt = render(cfg, q, t, feats, b, refs)
    if dry_run:
        return {"task_id": tid, "action": "would estimate", "prompt_chars": len(prompt), "offered": offered}
    rs = est.rows(q, tid)
    spent: list[dict[str, Any]] = []
    errs: list[str] = []
    raw, text = "", prompt
    for attempt in (1, 2):
        res, se, code = call(cfg, q, text, run_id, tid, actor)
        u = _usage(res)
        spent.append(u)
        usage.record_headless(q, SEAT, f"{run_id}:{tid}:{attempt}", res)
        sm, _ = _sm()
        quota, qclass, resets = sm.detect_quota(res, "", se)
        raw = str(res.get("result") or "")
        if quota:
            errs = [f"quota ({qclass}); resets {resets}"]
            _log(q, {"at": iso(), "run_id": run_id, "task_id": tid, "attempt": attempt, "outcome": "quota", **u,
                     "errors": errs})
            return {"task_id": tid, "action": "failed", "reason": errs[0], "quota": True, "cost_usd": _sum(spent)}
        if code != 0 or res.get("is_error"):
            errs = [f"claude exited {code}" + (f": {se.strip()[:200]}" if se.strip() else "")
                    + (f" ({raw[:200]})" if res.get("is_error") and raw else "")]
        else:
            ans = ar.last_json_object(raw)
            errs = validate(ans, offered) if ans is not None else ["no JSON object in the answer"]
        _log(q, {"at": iso(), "run_id": run_id, "task_id": tid, "attempt": attempt,
                 "outcome": "ok" if not errs else "invalid", **u, "errors": errs[:10]})
        if not errs:
            seat = {"run_id": run_id, "attempts": attempt, "cost_usd": _sum(spent),
                    "tokens": sum(int(x.get("tokens") or 0) for x in spent) or None,
                    "duration_ms": sum(int(x.get("duration_ms") or 0) for x in spent) or None,
                    "models": sorted({m for x in spent for m in x["models"]}), "session_id": u.get("session_id")}
            row = to_row(tid, est._version(rs, "agent"), est.task_hash(str(t.get("_text") or "")), feats, b,
                         est.latest(rs, "baseline"), ans, offered, deps_done, seat, cfg)
            est._append(q, row)
            return {"task_id": tid, "action": "written", "row": row, "cost_usd": seat["cost_usd"], "attempts": attempt}
        if code != 0 and not res:  # the call itself failed: a retry with the errors would not help
            break
        text = _retry_prompt(prompt, raw, errs)
    d = q / DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}-{_ids(cfg).task_number(tid)}.failed.txt").write_text(raw[-20000:])
    return {"task_id": tid, "action": "failed", "reason": "; ".join(errs)[:500], "cost_usd": _sum(spent)}


def _sum(spent: list[dict[str, Any]]) -> float | None:
    vals = [x["cost_usd"] for x in spent if x.get("cost_usd") is not None]
    return round(sum(vals), 4) if vals else None


# ------------------------------------------------------------------------------------ which tasks

def _in_flight(q: Path) -> set[str]:
    w = read_json(q / "work.json", {}) or {}
    return {str(x) for x in (w.get("in_flight") or [])} | ({str(w["task_id"])} if w.get("task_id") else set()) \
        if isinstance(w, dict) else set()


def why_agent(rs: list[dict[str, Any]], thash: str, deps_done: list[str]) -> str | None:
    """Why the task needs a new agent estimate, or None when its latest stands."""
    last = est.latest(rs, "agent")
    if last is None:
        return "no agent estimate yet"
    if last.get("task_hash") != thash:
        return "the task changed"
    new = sorted(set(deps_done) - set((last.get("inputs") or {}).get("deps_done") or []))
    if new:
        return "a dependency merged since: " + ", ".join(new)
    return None


def stale(cfg: Config, q: Path, tasks: list[dict[str, Any]] | None = None) -> list[tuple[dict[str, Any], str]]:
    """Open tasks (not done, dropped or in flight) whose agent estimate is missing or out of date.
    Cheap: the task files and the estimate rows only."""
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    done = {str(t.get("task_id")) for t in tasks if t.get("status") == "done"}
    flying = _in_flight(q)
    out = []
    for t in tasks:
        tid = str(t.get("task_id"))
        if t.get("status") in ("done", "dropped") or tid in flying:
            continue
        deps_done = sorted(d for d in tasklog._as_list(t.get("depends_on")) if d in done)
        why = why_agent(est.rows(q, tid), est.task_hash(str(t.get("_text") or "")), deps_done)
        if why:
            out.append((t, why))
    return out


# ------------------------------------------------------------------------------------ lock

def lock_take(q: Path, run_id: str, ttl_s: int) -> tuple[bool, dict[str, Any] | None]:
    sm, _ = _sm()
    path = q / LOCK
    for _ in range(2):
        body = {"holder": SEAT, "pid": os.getpid(), "host": socket.gethostname(), "since": iso(),
                "ttl_seconds": ttl_s, "review_id": run_id, "task_id": None}
        try:
            fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except FileExistsError:
            cur = read_json(path, {}) or {}
            if sm.lock_is_stale(cur):
                path.unlink(missing_ok=True)
                continue
            return False, cur
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(body) + "\n")
        return True, body
    return False, None


def _lock_note(q: Path, body: dict[str, Any], tid: str) -> None:
    from ccp.queue import write_json  # noqa: PLC0415
    write_json(q / LOCK, {**body, "task_id": tid, "task_since": iso()})


def lock_release(q: Path, run_id: str) -> None:
    cur = read_json(q / LOCK, {}) or {}
    if isinstance(cur, dict) and cur.get("review_id") == run_id and cur.get("pid") in (os.getpid(), str(os.getpid())):
        (q / LOCK).unlink(missing_ok=True)


def running(q: Path) -> dict[str, Any] | None:
    """The batch in progress (its lock, when alive), for the live-seats panel. Read only."""
    cur = read_json(q / LOCK, {}) or {}
    if not isinstance(cur, dict) or not cur.get("review_id"):
        return None
    sm, _ = _sm()
    return None if sm.lock_is_stale(cur) else cur


# ------------------------------------------------------------------------------------ commands

def _new_run_id() -> str:
    return "es-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + os.urandom(2).hex()


def run(cfg: Config, q: Path, ids: list[str] | None, max_n: int = MAX_DEFAULT, dry_run: bool = False,
        force: bool = False, actor: str = "system", run_id: str | None = None) -> dict[str, Any]:
    """Agent estimates for `ids`, or (None) every open task that needs one, at most `max_n` tasks,
    one at a time under `estimator.lock`. A named task is estimated even when in flight; `--all`
    leaves in-flight tasks out (an estimate made after the start is never scored)."""
    from ccp.queue import QueueError  # noqa: PLC0415
    tasks = tasklog.load(cfg)
    done = {str(t.get("task_id")) for t in tasks if t.get("status") == "done"}
    if ids is None:
        todo = stale(cfg, q, tasks)
        if force:
            flying = _in_flight(q)
            todo = [(t, "forced") for t in tasks if t.get("status") not in ("done", "dropped")
                    and str(t.get("task_id")) not in flying]
    else:
        todo = []
        for i in ids:
            t = next((x for x in tasks if _ids(cfg).same_task(x["_file"].stem, i)), None)
            if t is None:
                raise QueueError(f"no task {i} in {cfg.rel(cfg.tasks_dir)}", 2)
            if t.get("status") in ("done", "dropped"):
                todo.append((t, f"skip:{t.get('status')}: an estimate is made before the work"))
                continue
            deps_done = sorted(d for d in tasklog._as_list(t.get("depends_on")) if d in done)
            why = "forced" if force else why_agent(est.rows(q, str(t.get("task_id"))),
                                                   est.task_hash(str(t.get("_text") or "")), deps_done)
            todo.append((t, why or "skip:unchanged: the latest agent estimate stands"))
    out: list[dict[str, Any]] = []
    for t, why in todo:
        if why.startswith("skip:"):
            _, act, reason = why.split(":", 2)
            out.append({"task_id": str(t.get("task_id")), "action": act if act == "unchanged" else "skipped",
                        "reason": reason.strip()})
    work = [(t, why) for t, why in todo if not why.startswith("skip:")]
    over = work[max_n:]
    work = work[:max_n]
    for t, _ in over:
        out.append({"task_id": str(t.get("task_id")), "action": "deferred", "reason": f"over the budget cap (--max {max_n})"})
    if not work:
        return {"ok": True, "dry_run": dry_run, "tasks": out, "written": 0, "cost_usd": 0.0}
    run_id = run_id or _new_run_id()
    lock = None
    if not dry_run:
        ok, cur = lock_take(q, run_id, len(work) * 2 * CALL_TIMEOUT_S + 600)
        if not ok:
            return {"ok": False, "outcome": "locked", "lock": cur, "tasks": out, "written": 0,
                    "reason": f"an estimator batch is running ({(cur or {}).get('review_id')})"}
        lock = cur
    try:
        hist = est.history(cfg, q, tasks)
        pool = est._pool(hist)
        est._featured(cfg, pool)
        k = int((cfg.estimate or {}).get("k") or est.K_DEFAULT)
        for t, why in work:
            tid = str(t.get("task_id"))
            feats = est.features(cfg, t)
            b = est.baseline(feats, [h for h in pool if h["task_id"] != tid], k)
            if b is None:
                out.append({"task_id": tid, "action": "skipped", "reason": "no completed task with a wall time to compare with"})
                continue
            if lock:
                _lock_note(q, lock, tid)
            deps_done = sorted(d for d in tasklog._as_list(t.get("depends_on")) if d in done)
            try:
                r = estimate_one(cfg, q, t, b, pool, feats, deps_done, run_id, actor, dry_run)
            except Exception as exc:  # noqa: BLE001  (one task's failure never stops the batch)
                r = {"task_id": tid, "action": "failed", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}
            r["why"] = why
            out.append(r)
            if r.get("quota"):
                break
    finally:
        if lock:
            lock_release(q, run_id)
    cost = round(sum(float(r.get("cost_usd") or 0) for r in out), 4)
    return {"ok": True, "dry_run": dry_run, "run_id": run_id, "tasks": out, "cost_usd": cost,
            "written": sum(1 for r in out if r["action"] == "written"),
            "failed": sum(1 for r in out if r["action"] == "failed")}


def prompt_for(cfg: Config, q: Path, task_id: str) -> str:
    """`--print-prompt`: the prompt the seat would get for one task; no call."""
    from ccp.queue import QueueError  # noqa: PLC0415
    tasks = tasklog.load(cfg)
    t = next((x for x in tasks if _ids(cfg).same_task(x["_file"].stem, task_id)), None)
    if t is None:
        raise QueueError(f"no task {task_id} in {cfg.rel(cfg.tasks_dir)}", 2)
    pool = est._pool(est.history(cfg, q, tasks))
    est._featured(cfg, pool)
    feats = est.features(cfg, t)
    b = est.baseline(feats, [h for h in pool if h["task_id"] != t.get("task_id")],
                     int((cfg.estimate or {}).get("k") or est.K_DEFAULT))
    if b is None:
        raise QueueError("no completed task with a wall time to compare with", 3)
    return render(cfg, q, t, feats, b, reference_class(pool, b, feats))


# ------------------------------------------------------------------------------------ triggers

def _linked_worktree(root: Path) -> bool:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-dir", "--git-common-dir"], capture_output=True, text=True)
    parts = r.stdout.split()
    return r.returncode == 0 and len(parts) == 2 and Path(root, parts[0]).resolve() != Path(root, parts[1]).resolve()


def spawn(cfg: Config, q: Path, max_n: int = MAX_DEFAULT, actor: str = "system") -> dict[str, Any]:
    """Start `ccp tasks estimate --all` in its own session and return at once (it outlives the caller)."""
    run_id = _new_run_id()
    d = q / DIR
    d.mkdir(parents=True, exist_ok=True)
    log = d / f"{run_id}.log"
    boot = f"import sys; sys.path.insert(0, {str(PLANE)!r}); from ccp.cli import main; sys.exit(main(sys.argv[1:]))"
    with log.open("w") as fh:
        p = subprocess.Popen([sys.executable, "-c", boot, "--root", str(cfg.root), "tasks", "estimate", "--all",
                              "--max", str(max_n), "--run-id", run_id, "--actor", actor, "--json"],
                             stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, cwd=cfg.root,
                             env={**os.environ, "QUEUE_ROOT": str(q)}, start_new_session=True)
    return {"outcome": "started", "run_id": run_id, "pid": p.pid, "log": str(log)}


def notice(cfg: Config, q: Path | None = None) -> list[str]:
    """`ccp tasks check` and `ccp tasks index`: lines about tasks that need an agent estimate and,
    with `estimate.auto`, a detached batch started for them. Never raises, never blocks."""
    try:
        if q is None:
            raw = os.environ.get("QUEUE_ROOT")
            if not raw or not Path(raw).is_dir():
                return []
            q = Path(raw)
        todo = stale(cfg, q)
        if not todo:
            return []
        ids = ", ".join(_ids(cfg).task_number(t.get("task_id")) for t, _ in todo[:12]) + (" ..." if len(todo) > 12 else "")
        head = f"estimates: {len(todo)} open task(s) without a current agent estimate ({ids})"
        if not (cfg.estimate or {}).get("auto"):
            return [head + "; `ccp tasks estimate --all` runs the estimator (estimate.auto is off, SPEC §26.3)"]
        if running(q):
            return [head + "; an estimator batch is already running"]
        if _linked_worktree(cfg.root):
            return [head + "; not started from a linked worktree (the main checkout's task files are the ones estimated)"]
        if envvar("CCP_NO_ESTIMATOR_SPAWN"):
            return [head + "; not started (CCP_NO_ESTIMATOR_SPAWN)"]
        s = spawn(cfg, q)
        return [head + f"; started the estimator in the background ({s['run_id']}, at most {MAX_DEFAULT} task(s); "
                       f"log {s['log']})"]
    except Exception as exc:  # noqa: BLE001
        return [f"estimates: the estimator trigger failed ({type(exc).__name__}: {str(exc)[:160]})"]


# ------------------------------------------------------------------------------------ spend

def calls(q: Path) -> list[dict[str, Any]]:
    p = q / DIR / "calls.jsonl"
    try:
        return est._parse(p.read_text()) if p.is_file() else []
    except OSError:
        return []


def spend(q: Path, days: int = 7) -> dict[str, Any]:
    """The seat's calls and cost (the board's Estimation card), from `estimator/calls.jsonl`."""
    cs = calls(q)
    cut = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cost = lambda xs: round(sum(float(x.get("cost_usd") or 0) for x in xs), 2)  # noqa: E731
    recent = [x for x in cs if str(x.get("at") or "") >= cut]
    tasks_ok = {(x.get("run_id"), x.get("task_id")) for x in cs if x.get("outcome") == "ok"}
    tasks_all = {(x.get("run_id"), x.get("task_id")) for x in cs}
    return {"calls": len(cs), "cost_usd": cost(cs), f"cost_usd_{days}d": cost(recent), "calls_7d": len(recent),
            "estimates": len(tasks_ok), "failed": len(tasks_all - tasks_ok),
            "per_estimate_usd": round(cost(cs) / len(tasks_ok), 3) if tasks_ok else None,
            "last_at": max((str(x.get("at")) for x in cs), default=None), "pins": pins()}


def run_text(body: dict[str, Any]) -> str:
    lines = []
    for r in body.get("tasks") or []:
        extra = f" ${r['cost_usd']:.3f}" if isinstance(r.get("cost_usd"), (int, float)) else ""
        lines.append(f"{r['task_id']}: {r['action']}{extra} ({r.get('reason') or r.get('why') or ''})"
                     + (f"\n  {est.row_text(r['row'])}\n  {r['row']['reasoning']}" if r.get("row") else "")
                     + (f" prompt {r['prompt_chars']} chars, refs {','.join(number_prefix(x) or x[:4] for x in r['offered'])}"
                        if r.get("prompt_chars") else ""))
    if body.get("outcome") in ("locked", "deferred"):
        lines.append(f"{body['outcome']}: {body.get('reason')}")
    lines.append(f"{body.get('written', 0)} agent estimate(s) written, {body.get('failed', 0)} failed, "
                 f"cost ${float(body.get('cost_usd') or 0):.3f}" + (" (dry run: no call made)" if body.get("dry_run") else ""))
    return "\n".join(lines)

