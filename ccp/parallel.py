"""SPEC §16.3: which tasks the runner may hold at once.

A task's paths are the backticked paths in its Scope section's **In:** item. Which pairs rule 3 keeps
apart depends on `parallel.schedule`. Under `paths`, two tasks run together only when their
paths do not meet (unless both are covered by a `parallel.shared` entry, a file tasks only append lines
to). Under `clashes` (the default), they run together unless one names the other in `clashes_with` (§5), whatever their
paths; paths then only feed rules 2 and 4. Either way neither touches a product's `parallel.exclusive` entry, and the
account's 5-hour usage is below the session ceiling, a constant (a machine without
`allowance_cmd` reads no usage, so that rule passes). Correctness never rests on these
rules (§16.1): verify and merge run one at a time on the current head. They only decide what to
start together. With `parallel.max_in_flight` 1 nothing here is consulted.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ccp import tasklog, usage
from ccp.config import PARALLEL_DEFAULTS, Config

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
    return cfg.parallel or copy.deepcopy(PARALLEL_DEFAULTS)


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


def covered(p: str, entries: list[str]) -> bool:
    """§16.2, §16.3 rule 3: `p` lies wholly within a `parallel.shared` entry: equal to it, under an entry
    that is a directory, matched by an entry that is a glob, or ending in an entry that is a bare file name.
    A glob `p` is covered only by an equal entry or a directory holding it; a directory `p` never by a file
    or file glob (it holds other files)."""
    p = p.strip().removeprefix("./")
    for x in (e.strip().removeprefix("./") for e in entries):
        if p.rstrip("/") == x.rstrip("/"):
            return True
        if not _is_glob(x) and _is_dir(x) and _holds(x, p):
            return True
        if _is_glob(p) or _is_dir(p):
            continue
        if _is_glob(x) and _glob_re(x).match(p):
            return True
        if not _is_glob(x) and "/" not in x and p.rsplit("/", 1)[-1] == x:
            return True
    return False


def no_five_hour_limit(sample: dict[str, Any] | None) -> bool:
    """A sample that reads the weekly figure but has no 5-hour one: the account has no 5-hour limit
    (Anthropic dropped it on 2026-10-31; SPEC §16.3 rule 5, §25.1), not a failed read."""
    s = sample or {}
    return s.get("five_hour") is None and s.get("seven_day") is not None


def reads_usage(cfg: Config) -> bool:
    """The machine sets `allowance_cmd`: rule 5 has a reading to judge (§16.3). Without
    it the plane reads no usage, and the rule passes."""
    return usage.usage_read(cfg)


def paths_meet(cfg: Config, a: dict[str, Any], b: dict[str, Any]) -> tuple[str, str] | None:
    """§16.3 rule 3 between two tasks: the first path of `a` that meets a path of `b`, with that path,
    unless both are covered by a `parallel.shared` entry; a task saying `parallel: true` meets nothing."""
    if flag(a) is True or flag(b) is True:
        return None
    shared = settings(cfg).get("shared") or []
    for p in paths(cfg, a):
        for o in paths(cfg, b):
            if meets(p, o) and not (covered(p, shared) and covered(o, shared)):
                return p, o
    return None


@dataclass(frozen=True)
class Apart:
    """Why two tasks may not run together (§16.3 rule 3): `kind` is `paths` (`a_path` of the first meets
    `b_path` of the second) or `clash` (one names the other in `clashes_with`; no paths)."""
    kind: str
    a_path: str = ""
    b_path: str = ""


def clashes(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """§5: either task names the other in `clashes_with` (the relation is symmetric). A task that is done
    or dropped holds nothing back."""
    if a.get("status") in ("done", "dropped") or b.get("status") in ("done", "dropped"):
        return False
    return (str(b.get("task_id")) in map(str, tasklog._as_list(a.get("clashes_with")))
            or str(a.get("task_id")) in map(str, tasklog._as_list(b.get("clashes_with"))))


def kept_apart(cfg: Config, a: dict[str, Any], b: dict[str, Any]) -> Apart | None:
    """Whether tasks `a` and `b` may not run together (§16.3 rule 3): the reason, or None when they may.
    The one pairwise predicate: rule 3 and `next`'s passed-over walk both ask it. Under `parallel.schedule`
    `paths` it is `paths_meet`; under `clashes` it is the recorded clash, whatever the paths, and
    `parallel: true` does not lift it."""
    if settings(cfg).get("schedule", "paths") == "clashes":
        return Apart("clash") if clashes(a, b) else None
    met = paths_meet(cfg, a, b)
    return Apart("paths", met[0], met[1]) if met is not None else None


def join_refusal(cfg: Config, cand: dict[str, Any], active: list[dict[str, Any]],
                 sample: dict[str, Any] | None, five_known: bool = True, rule3: bool = True) -> str | None:
    """Why `cand` may not be claimed beside `active` (§16.3 rules 1-5), or None when it may.
    An empty `active` is never refused here: a lone claim is judged as before §16. `sample` is the
    reading in force (`five_hour`, `seven_day`; §25.1), None when there is none, which refuses rule 5;
    `five_known` False skips rule 5 (`next` with no reading in force: the claim reads), and so does a
    machine with no `allowance_cmd`.
    `rule3` False skips the path rule (`next` asks whether rule 3 alone keeps a task out)."""
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
    for t in active if rule3 else []:
        if (met := kept_apart(cfg, cand, t)) is not None:
            if met.kind == "clash":
                return f"{cid} clashes with in-flight {t.get('task_id')} (clashes_with, rule 3)"
            return f"{cid}'s `{met.a_path}` meets in-flight {t.get('task_id')}'s `{met.b_path}` (rule 3)"
    for t in group:
        if flag(t) is True:
            continue
        for p in paths(cfg, t):
            for x in s["exclusive"]:
                if meets(p, x):
                    return f"{t.get('task_id')}'s `{p}` is exclusive (`{x}`, parallel.exclusive): it runs alone (rule 4)"
    if five_known and reads_usage(cfg) and not no_five_hour_limit(sample):
        ceiling = float(usage.account(cfg)["ceiling_pct"])
        if sample is None:
            return (f"no good usage reading in the last {usage.IN_FORCE_S // 60} minutes, so no second task is "
                    "taken (rule 5)")
        five_hour = sample.get("five_hour")
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
    None, `slots_full`, None or what to tell the runner (§16.3, exit 7), and `passed_over`, the
    `{task_id, why}` of each task passed over. Without parallel, row 0 of the selection, as before §16
    (an in-flight task included: the runner resumes it). With tasks in flight, the ready tasks not in
    flight are walked in rank order: the first that may join what the runner holds and that rule 3 would
    not keep from joining a task passed over is taken. A task that rule 3 alone keeps out, or that rule 3
    would keep from joining a passed-over task, is passed over: it waits only for the tasks rule 3 keeps
    it from (its paths meet, or under `parallel.schedule: clashes` it clashes with).
    A task any other rule keeps out ends the walk with none (head of line); `slots_full` names the first
    ready task as `head`, with its refusal. Rule 5 is judged on the reading in force (§25.1: the latest
    good sample no older than `usage.IN_FORCE_S`); with none it is not judged here, and the claim reads."""
    ranked = sel["ranked"]
    if q is None or not enabled(cfg):
        return {"pick": ranked[0] if ranked else None, "slots_full": None, "passed_over": []}
    from ccp import usage  # noqa: PLC0415
    from ccp.queue import load_work  # noqa: PLC0415
    rows = [r for r in ranked if str(r[0].get("task_id")) not in sel["in_flight"]]
    active = active_tasks(cfg, q, load_work(q))
    if not active:
        return {"pick": rows[0] if rows else None, "slots_full": None, "passed_over": []}
    ids = [str(x.get("task_id")) for x in active]
    if not rows:
        return {"pick": None, "slots_full": {"in_flight": ids, "reason": "nothing else is ready", "passed_over": []},
                "passed_over": []}
    last = usage.in_force(q, usage.now())  # a failed sample is never in force, so never makes the slots full
    fresh = last is not None
    passed: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []  # the passed-over tasks themselves
    head_why = None
    for n, row in enumerate(rows):
        t, tid = row[0], str(row[0].get("task_id"))
        why = join_refusal(cfg, t, active, last, five_known=fresh)
        if n == 0:
            head_why = why
        if why is not None and join_refusal(cfg, t, active, last, five_known=fresh, rule3=False) is not None:
            break  # rules 1, 2, 4 or 5: the line waits here
        behind = next(((o, met) for o in held if (met := kept_apart(cfg, t, o)) is not None), None)
        if why is None and behind is None:
            return {"pick": row, "slots_full": None, "passed_over": passed}
        if why is None and behind is not None:
            o, met = behind
            why = (f"{tid} clashes with passed-over {o.get('task_id')}" if met.kind == "clash" else
                   f"{tid}'s `{met.a_path}` meets passed-over {o.get('task_id')}'s `{met.b_path}`")
        passed.append({"task_id": tid, "why": why})
        held.append(t)
    return {"pick": None, "passed_over": passed,
            "slots_full": {"in_flight": ids, "head": str(rows[0][0].get("task_id")), "reason": head_why,
                           "passed_over": passed}}


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
