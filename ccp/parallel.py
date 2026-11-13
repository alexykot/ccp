"""SPEC §16.3: which tasks the runner may hold at once.

A task's paths are the backticked paths in its Scope section's **In:** item. Two tasks run together
only when their paths do not meet, neither touches a product's `parallel.exclusive` entry, and the
account's 5-hour usage is below `parallel.session_ceiling_pct` (a product without
`telemetry.allowance_cmd` reads no usage, so that rule passes). Correctness never rests on these
rules (§16.1): verify and merge run one at a time on the current head. They only decide what to
start together. With `parallel.max_in_flight` 1 (the default) nothing here is consulted.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ccp import tasklog
from ccp.config import Config

EXIT_SLOTS = 7  # §16.3: the runner holds what it can; carry on with it (not "nothing ready", exit 3)

TICK_RE = re.compile(r"`([^`\s]+)`")
# A file extension, not `module.attr` (`entries.close`, `sys.path`): a known suffix, or a file that exists
EXTENSIONS = {"py", "pyi", "md", "json", "jsonl", "sql", "sh", "bash", "zsh", "yml", "yaml", "toml", "txt", "csv",
              "tsv", "ini", "cfg", "conf", "html", "htm", "css", "js", "mjs", "ts", "tsx", "jsx", "go", "rs", "rb",
              "java", "kt", "c", "h", "cc", "cpp", "hpp", "swift", "lock", "xml", "svg", "png", "jpg", "pdf", "env",
              "plist", "service", "tmpl", "j2", "ipynb", "proto", "graphql", "rst", "log", "gitignore", "dockerfile"}
EXT_RE = re.compile(r"\.([A-Za-z0-9]{1,12})$")
ITEM_RE = re.compile(r"^\s*-\s+\*\*")
LINE_RE = re.compile(r":\d+(?:-\d+)?$")  # `src/app/leak.py:146` names the file
GLOB_CHARS = set("*?[")
MARK_RE = re.compile(r"\b(?:new|removed)\b", re.I)  # §5.5: a Scope path the task creates or deletes


def settings(cfg: Config) -> dict[str, Any]:
    return cfg.parallel or {"max_in_flight": 1, "exclusive": [], "session_ceiling_pct": 60}


def enabled(cfg: Config) -> bool:
    return int(settings(cfg)["max_in_flight"]) > 1


def in_item(text: str) -> str:
    """The Scope section's **In:** item, up to the next item (`**Out:**`)."""
    scope = tasklog._section(text, tasklog.SEC_SCOPE) or ""
    out: list[str] = []
    inside = False
    for line in scope.splitlines():
        if ITEM_RE.match(line):
            inside = "**In:**" in line or "**In**:" in line
        if inside:
            out.append(line)
    return "\n".join(out)


def paths(cfg: Config, t: dict[str, Any]) -> list[str]:
    """The paths a task touches (§16.3): its declared `paths:` frontmatter (§5) when it has one;
    else, from the Scope **In:** item, a backticked token that holds a `/`, ends in a file extension,
    or names a file or directory in the product's checkout. Symbols (`coverage`) are not paths."""
    declared = [p.strip().removeprefix("./") for p in tasklog._as_list(t.get("paths")) if p.strip()]
    if declared:
        return list(dict.fromkeys(declared))
    found: list[str] = []
    for tok in TICK_RE.findall(in_item(t.get("_text") or "")):
        tok = LINE_RE.sub("", tok.strip().removeprefix("./").rstrip(",;"))
        if not tok or tok in found:
            continue
        ext = EXT_RE.search(tok)
        if "/" in tok or (ext and ext.group(1).lower() in EXTENSIONS) or (cfg.root / tok).exists():
            found.append(tok)
    return found


def flag(t: dict[str, Any]) -> bool | None:
    """Frontmatter `parallel:` true (changes no file: runs beside anything), false (always alone), or unset."""
    v = t.get("parallel")
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower() if v is not None else ""
    return True if s == "true" else False if s == "false" else None


def _glob_re(g: str) -> re.Pattern[str]:
    out = ""
    i = 0
    while i < len(g):
        if g.startswith("**", i):
            out += ".*"
            i += 2
            if g.startswith("/", i):  # `a/**/b` also matches `a/b`
                out += "/?"
                i += 1
        elif g[i] == "*":
            out += "[^/]*"
            i += 1
        elif g[i] == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(g[i])
            i += 1
    return re.compile(out + "/?$")


def _is_glob(p: str) -> bool:
    return any(c in GLOB_CHARS for c in p)


def _holds(d: str, p: str) -> bool:
    """`d` is a directory (written `d/`, or a plain prefix) that holds `p`."""
    d = d.rstrip("/")
    return bool(d) and p.startswith(d + "/")


def _is_dir(p: str) -> bool:
    """Written as a directory: a trailing `/`, or a last part with no extension."""
    return p.endswith("/") or not EXT_RE.search(p.rstrip("/").rsplit("/", 1)[-1])


def meets(a: str, b: str) -> bool:
    """§16.3: equal; one a directory holding the other; a glob of one matching the other; or a bare
    file name (`.claude.md`) matching the other's last part."""
    a, b = a.strip().removeprefix("./"), b.strip().removeprefix("./")
    if a.rstrip("/") == b.rstrip("/"):
        return True
    for x, y in ((a, b), (b, a)):
        if _is_glob(x):
            if _glob_re(x).match(y.rstrip("/")):
                return True
            stem = x[:min(x.index(c) for c in GLOB_CHARS if c in x)]
            if not _is_glob(y) and y.rstrip("/") and (stem.startswith(y.rstrip("/") + "/")
                                                      or stem.rstrip("/") == y.rstrip("/")
                                                      or (_is_dir(y) and y.startswith(stem))):
                return True  # a directory holding what the glob matches, or one inside its fixed part
            if _is_glob(y) and (stem.startswith(y[:min(y.index(c) for c in GLOB_CHARS if c in y)])
                                or y.startswith(stem)):
                return True  # two globs: overlapping fixed prefixes are taken to meet
            continue
        if _holds(x, y) and not _is_glob(y):
            return True
        if "/" not in x.rstrip("/") and not x.endswith("/") and y.rstrip("/").rsplit("/", 1)[-1] == x:
            return True
    return False


def no_five_hour_limit(sample: dict[str, Any] | None) -> bool:
    """A sample that reads the weekly figure but has no 5-hour one: the account has no 5-hour limit
    (Anthropic dropped it on 2026-10-31; SPEC §16.3 rule 5, §25.1), not a failed read."""
    s = sample or {}
    return s.get("five_hour") is None and s.get("seven_day") is not None


def reads_usage(cfg: Config) -> bool:
    """The product sets `telemetry.allowance_cmd`: rule 5 has a reading to judge (§16.3). Without
    it the plane reads no usage, and the rule passes."""
    return bool((cfg.telemetry or {}).get("allowance_cmd"))


def join_refusal(cfg: Config, cand: dict[str, Any], active: list[dict[str, Any]],
                 sample: dict[str, Any] | None, five_known: bool = True) -> str | None:
    """Why `cand` may not be claimed beside `active` (§16.3 rules 1-5), or None when it may.
    An empty `active` is never refused here: a lone claim is judged as before §16. `sample` is the
    allowance reading (`five_hour`, `seven_day`); `five_known` False skips rule 5 (no fresh sample to
    judge it by; the claim samples), and so does a product with no `telemetry.allowance_cmd`."""
    if not active:
        return None
    s = settings(cfg)
    cid = str(cand.get("task_id"))
    if len(active) >= int(s["max_in_flight"]):
        return f"the runner holds {len(active)} task(s), parallel.max_in_flight is {s['max_in_flight']} (rule 1)"
    group = [cand, *active]
    for t in group:
        tid = str(t.get("task_id"))
        if flag(t) is False:
            return f"{tid} says parallel: false: it runs alone (rule 2)"
        if flag(t) is not True and not paths(cfg, t):
            return f"{tid} names no path in its Scope In: item and does not say parallel: true: it runs alone (rule 2)"
    cpaths = [] if flag(cand) is True else paths(cfg, cand)
    for t in active:
        if flag(t) is True:
            continue
        for p in cpaths:
            for o in paths(cfg, t):
                if meets(p, o):
                    return f"{cid}'s `{p}` meets in-flight {t.get('task_id')}'s `{o}` (rule 3)"
    for t in group:
        if flag(t) is True:
            continue
        for p in paths(cfg, t):
            for x in s["exclusive"]:
                if meets(p, x):
                    return f"{t.get('task_id')}'s `{p}` is exclusive (`{x}`, parallel.exclusive): it runs alone (rule 4)"
    if five_known and reads_usage(cfg) and not no_five_hour_limit(sample):
        ceiling = float(s["session_ceiling_pct"])
        five_hour = (sample or {}).get("five_hour")
        if five_hour is None:
            return "the 5-hour usage is unknown, so no second task is taken (rule 5)"
        if five_hour >= ceiling:
            return f"the 5-hour usage is {five_hour:g}%, at or above parallel.session_ceiling_pct {ceiling:g}% (rule 5)"
    return None


def active_tasks(cfg: Config, q: Path, w: dict[str, Any], tasks: list[dict[str, Any]] | None = None,
                 but: str | None = None) -> list[dict[str, Any]]:
    """The runner's in-flight tasks (work.json `in_flight`) still claimed, as task-file metas. A task
    whose file is gone stands in as an empty record: it has no paths, so nothing joins it (rule 2)."""
    from ccp.queue import load_task_state  # noqa: PLC0415
    tasks = tasks if tasks is not None else tasklog.load(cfg)
    by_id = {str(t.get("task_id")): t for t in tasks}
    out = []
    for tid in [str(x) for x in w.get("in_flight") or []]:
        if tid == but:
            continue
        st = load_task_state(q, tid)
        if st.get("status") == "done" or not st.get("lease_holder"):
            continue
        out.append(by_id.get(tid) or {"task_id": tid, "_text": ""})
    return out


def next_choice(cfg: Config, q: Path | None, sel: dict[str, Any]) -> dict[str, Any]:
    """What `ccp tasks next` returns, for the command and the board alike: `pick`, a (task, why) or
    None, and `slots_full`, None or what to tell the runner (§16.3, exit 7). Without parallel, row 0 of
    the selection, as before §16 (an in-flight task included: the runner resumes it). With it, the
    head of the line is the first ready task not in flight; it is taken only when it may join what
    the runner holds, and nothing behind it is taken instead. Rule 5 is judged on the latest
    allowance sample while it is fresh (15 minutes); the claim samples anew either way."""
    ranked = sel["ranked"]
    if q is None or not enabled(cfg):
        return {"pick": ranked[0] if ranked else None, "slots_full": None}
    import time  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415
    from ccp import usage  # noqa: PLC0415
    from ccp.queue import load_work  # noqa: PLC0415
    rows = [r for r in ranked if str(r[0].get("task_id")) not in sel["in_flight"]]
    active = active_tasks(cfg, q, load_work(q))
    if not active:
        return {"pick": rows[0] if rows else None, "slots_full": None}
    ids = [str(x.get("task_id")) for x in active]
    if not rows:
        return {"pick": None, "slots_full": {"in_flight": ids, "reason": "nothing else is ready"}}
    last = usage._latest(q)
    try:
        fresh = time.time() - datetime.fromisoformat(str(last.get("at")).replace("Z", "+00:00")).timestamp() < 15 * 60
    except ValueError:
        fresh = False
    why = join_refusal(cfg, rows[0][0], active, last, five_known=fresh)
    if why is None:
        return {"pick": rows[0], "slots_full": None}
    return {"pick": None, "slots_full": {"in_flight": ids, "head": str(rows[0][0].get("task_id")), "reason": why}}


def runs_alone(cfg: Config, t: dict[str, Any]) -> bool:
    """§16.3 rules 2 and 4 for one task: it never shares the runner (parallel: false; no path and no
    parallel: true; a path that meets an exclusive entry). The forecast gives it every slot (§16.7)."""
    f = flag(t)
    if f is True:
        return False
    ps = paths(cfg, t)
    return f is False or not ps or any(meets(p, x) for p in ps for x in settings(cfg)["exclusive"])


def missing_paths(cfg: Config, t: dict[str, Any], tasks: list[dict[str, Any]] | None = None) -> list[str]:
    """Scope In: paths (tokens with a `/`; a bare name is often given
    relative to a sibling path) that exist neither in the checkout, nor in a dependency's own Scope In:
    (a file an unmerged dependency makes), nor as new or removed: the word `new` or `removed` within
    the 25 characters after the token and before the next backtick, so a marking applies to the token
    it follows and not to one before it (a removed path is accepted whether or not it still exists).
    Globs are left alone."""
    item = in_item(t.get("_text") or "")
    deps = set(tasklog._as_list(t.get("depends_on")))
    theirs = {p.rstrip("/") for d in tasks or [] if str(d.get("task_id")) in deps for p in paths(cfg, d)}
    out = []
    for m in TICK_RE.finditer(item):
        tok = LINE_RE.sub("", m.group(1).strip().removeprefix("./").rstrip(",;"))
        if not tok or "/" not in tok or _is_glob(tok) or tok in out:
            continue
        after = item[m.end():m.end() + 25].split("`", 1)[0]  # the window stops at the next backticked token
        if (cfg.root / tok.rstrip("/")).exists() or tok.rstrip("/") in theirs or MARK_RE.search(after):
            continue
        out.append(tok)
    return out


def scope_warnings(cfg: Config, tasks: list[dict[str, Any]]) -> list[str]:
    """`ccp tasks check` (§16.3): with parallel on, a not-done task with no path and no `parallel:
    true` only ever runs alone."""
    open_ = [t for t in tasks if t.get("status") not in ("done", "dropped")]
    out = [f"{cfg.rel(t['_file'])}: Scope names {', '.join(f'`{x}`' for x in miss)}, which does not exist and is not "
           "marked new or removed" for t in open_ if (miss := missing_paths(cfg, t, tasks))]
    if not enabled(cfg):
        return out
    return out + [f"{cfg.rel(t['_file'])}: no path in its Scope In: item and no `parallel: true`: "
                  "it will only run alone (SPEC §16.3)" for t in open_ if flag(t) is None and not paths(cfg, t)]
