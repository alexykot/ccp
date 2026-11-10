"""The durable task log: validation, ordering and the generated index (SPEC §4, §10, §20).

One task per file, `docs/delivery/tasks/NNNN-kebab-slug.md`, never deleted, never renumbered;
filesystem sort is execution order. What the plane used to leave to discipline, this module
enforces: metadata is YAML frontmatter (a parser can read it), `INDEX.yaml` is generated from the
files rather than written beside them (it cannot drift), and `check()` is the gate the Verifier
runs before any task's own `dod_checks`.

A task file is never deleted and carries no runtime state: `check()` refuses runtime keys in
frontmatter, a task file that git or the committed INDEX knew and that is gone, and a number
reused by another task (a renamed task says `renamed_from: <old id>`), and
`warnings()` names a later task cited as a prerequisite in prose, where `depends_on` cannot
reach it (supersede instead).

A task has a kind (§20): `feature` (the default) or `refactor`. A refactor changes no rule, so it
cites house rules or review findings (`rule_refs`, `review_refs`) instead of the spec. With the
`architect` block on, refactors get reserved capacity in `next_task`; by default a refactor joins a
scope only when a task in it depends on the refactor (`refactor_in_scope: "deps"`), and the rest wait
for the top of the next review point's scope. New tasks citing an ADR need its shaping record (`reviews/sh-*.md`) or a waiver.

A task carries `review_point` (§22.1, §22): the review point whose scope it belongs to, set by the
task-log owner when scoping. With the review-point register (`ccp/reviewpoints.py`, which this check
also validates) it is `R<n>` and one of the register's ids; without it, it matches
`task_log.review_point_pattern`, as before the register. `ccp tasks close`
stamps work.json's point into a task that carries none, as a fallback.

The product-specific values live in `plane.json`.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import functools

from ccp import refs, reviewpoints
from ccp.config import Config

NAME_RE = refs.DEFAULT.task_file_re  # the default; checks use refs.ids(cfg).task_file_re

# ---------------------------------------------------------------- the canonical task file (SPEC §5.1)
# The format is the plane's. These names are what ccp reads and writes; a product does not rename them.
SEC_INTENT = "Intent"
SEC_CONTEXT = "Context (not checked)"
SEC_SCOPE = "Scope"
SEC_CHECKS = "dod_checks"
SEC_IMPL = "Implementation notes"
SEC_VERIFY = "Verification notes"
SECTIONS = (SEC_INTENT, SEC_CONTEXT, SEC_SCOPE, SEC_CHECKS, SEC_IMPL, SEC_VERIFY)
# An older name a section is still found under (the plane's template once said "not verified").
SECTION_ALIASES = {SEC_CONTEXT: ("Context (not verified)",)}
# Written during the work, not by the task's writer: left out of estimates (§26.3).
NOTES_SECTIONS = (SEC_IMPL, SEC_VERIFY)
# A dod_check opens `- id: `kind-NN``: a lowercase kind and a number.
CHECK_RE = re.compile(r"^- id: `([a-z]+-\d+)`[ \t]*(?:#.*)?$", re.M)
# The statuses a task file carries: knowledge and outcomes. Who is working on a task, and in which
# phase, is runtime state in the queue (§4).
STATUSES = ("pending", "done", "dropped")
TERMINAL = ("done", "dropped")
# Older files may still carry an in-flight status. It reads as its canonical state, with a warning.
LEGACY_STATUSES = {"in_progress": "pending", "blocked": "pending"}
KINDS = ("feature", "refactor")
# §3.5: the operator sign-offs a task may declare (`sign_off:`): `brief`, on text known when the task is
# written, recorded before the claim; `build`, on text the build finds, recorded after verify for the PR head.
SIGN_OFF_STAGES = ("brief", "build")
REFACTOR_REFS = ("rule_refs", "review_refs")  # the default refactor rule (task_log.kinds)
WAIVER_RE = re.compile(r"^waived\s*[—–:-]+\s*\S")
ADR_LINE_RE = re.compile(r"^\W*adr\W*:(.*)$", re.I | re.M)
# Runtime state (SPEC §4, contracts/task.schema.json) lives in the queue, never in a task file.
RUNTIME_KEYS = ("waiting_on", "waiting_on_since", "lease", "lease_holder", "lease_expires_at",
                "session_id", "claude_session_id", "ports", "planned_resume_at", "quota_class",
                "implementation_started_at")
# §10 task_log.dry_run: a step that runs a backticked command, and the writer's record of running it.
# A numbered step (`1.` or `1)`) with "run `…`" anywhere in it, the command wrapped onto the next line too.
RUN_STEP_RE = re.compile(r"^[ \t]*\d+[.)][ \t]+(?:[^\n]*?\b)?run[ \t]*\n?[ \t]*`", re.I | re.M)
# Each record says something: what the run printed, or why it cannot run yet (not the template's `<why>`).
DRY_RUN_RE = re.compile(r"^[ \t]*dry run \(`?[0-9a-f]{7,40}`?\):[ \t]*(?:\n[ \t]*)?\S", re.I | re.M)
DRY_RUN_NA_RE = re.compile(r"^[ \t]*dry run:[ \t]*n/a[ \t]*[—–-]+[ \t]*(?:\n[ \t]*)?(?!<[^>\n]*>[ \t]*$)\S", re.I | re.M)
DRY_RUN_LINE_RE = re.compile(r"^[ \t]*dry run\b.*$", re.I | re.M)
INDEX_ID_RE = re.compile(r"^  - id: (\S+)$", re.M)
# §5: the plane template's placeholders. One left in a task file not yet done or dropped is a copy
# not filled in. A placeholder inside a code span or a fenced block is quoted, not left, so it is not read.
PLACEHOLDERS = ("NNNN-kebab-slug", "YYYY-MM-DD", "As a <role>", "<preconditions",
                "<concrete, observable result>", "One line, imperative")
# A fence closes on a line of only its own character, at least as many as opened it; a code span
# stays on one line, so one stray backtick cannot quote the lines after it.
FENCE_RE = re.compile(r"^[ \t]*(?P<f>(?P<c>[`~])(?P=c){2,})[^\n]*\n.*?^[ \t]*(?P=f)(?P=c)*[ \t]*$", re.M | re.S)
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)")
# §5.2: what an empty ref list that includes spec_refs is told to do.
SPEC_REFS_HINT = " — list the SPEC sections this task answers to in `spec_refs` and cite them in its text (§5.2)"


@functools.lru_cache(maxsize=8)
def prose_dep_re(width: int) -> re.Pattern[str]:
    """A prerequisite named in prose: "gated on 0197", "blocked by `0197`", "waits for task 0197"."""
    return re.compile(
        r"\b(?:gated on|gated by|blocked on|blocked by|waits? (?:for|on)|waiting (?:for|on)|depends on|"
        rf"dependent on|requires|prerequisite|until|after|once)\s+(?:task\s+)?`?(\d{{{width}}})(?![-/.:]?\d)", re.I)


PROSE_DEP_RE = prose_dep_re(refs.DEFAULT.task_width)


def _strip_comment(v: str) -> str:
    """Drop a trailing ` # comment` outside quotes (the templates annotate their fields)."""
    q = None
    for i, ch in enumerate(v):
        if ch in "\"'" and q in (None, ch):
            q = None if q else ch
        elif ch == "#" and q is None and (i == 0 or v[i - 1] in " \t"):
            return v[:i].rstrip()
    return v


def _split_list(inner: str) -> list[str]:
    """`a, "b, c"` → ["a", "b, c"]: commas inside quotes stay in their item."""
    items, cur, q = [], "", None
    for ch in inner:
        if ch in "\"'" and (q == ch or (q is None and not cur.strip())):  # a quote opens only an item
            q = None if q else ch
        elif ch == "," and q is None:
            items.append(cur)
            cur = ""
            continue
        cur += ch
    return [i.strip().strip('"').strip("'") for i in items + [cur] if i.strip()]


def adr_number(ref: str, cfg: Config | None = None) -> int | None:
    """The ADR an `adr_refs` entry cites, or None when it cites none (refs.Ids.adr_number)."""
    return refs.ids(cfg).adr_number(ref)


def frontmatter(text: str) -> dict[str, Any]:
    """Frontmatter as scalars and flat inline lists. Deliberately tiny: the fields are fixed, and
    the plane takes no YAML dependency."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    out: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = _strip_comment(v.strip())
        if v.startswith("[") and v.endswith("]"):
            out[k.strip()] = _split_list(v[1:-1].strip())
        else:
            out[k.strip()] = v.strip('"').strip("'")
    return out


def canonical_status(status: Any) -> Any:
    """A task file's status as the canonical vocabulary reads it: a legacy in-flight value
    (`in_progress`, `blocked`) is `pending`; anything else is returned as given."""
    return LEGACY_STATUSES.get(str(status), status) if isinstance(status, str) else status


def _section(text: str, name: str) -> str | None:
    """The body under `## <name>` (or an older name for that section), up to the next `## `
    heading; None when the heading is absent."""
    names = [name, *SECTION_ALIASES.get(name, ())]
    names += [k for k, olds in SECTION_ALIASES.items() if name in olds]
    m = None
    for n in names:
        m = re.search(rf"^## {re.escape(n)}[ \t]*$", text, re.M)
        if m:
            break
    if not m:
        return None
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():]


def load(cfg: Config) -> list[dict[str, Any]]:
    """Every task, in filesystem order, which is execution order."""
    out = []
    for f in sorted(cfg.tasks_dir.glob("*.md")):
        text = f.read_text()
        meta = frontmatter(text)
        if meta.get("status") in LEGACY_STATUSES:   # §5: read as its canonical state everywhere
            meta["_legacy_status"] = meta["status"]
            meta["status"] = canonical_status(meta["status"])
        meta["_file"] = f
        meta["_text"] = text
        meta["_checks"] = CHECK_RE.findall(_section(text, SEC_CHECKS) or "")
        out.append(meta)
    return out


def _as_list(v: Any) -> list[str]:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def sign_off_stages(t: dict[str, Any]) -> list[str]:
    """§3.5: the sign-offs the task declares (`sign_off: brief`, `build` or both), in that order."""
    want = {str(x).strip().lower() for x in _as_list(t.get("sign_off"))}
    return [s for s in SIGN_OFF_STAGES if s in want]


def kind_of(t: dict[str, Any]) -> str:
    return str(t.get("kind") or "feature")


def _number(tid: Any, cfg: Config | None = None) -> int | None:
    m = refs.ids(cfg).task_number_re.match(str(tid or ""))
    return int(m.group(1)) if m else None


def shaped_adrs(cfg: Config) -> set[int]:
    """ADR numbers that have a shaping record: the `ADR-NNNN` tokens on a `reviews/sh-*.md`'s `ADR:`
    lines (`ADR: ADR-0031 (accepted 2026-10-06)` names ADR 31 only), or anywhere in a record that has
    no such line. A bare number never counts."""
    out: set[int] = set()
    for f in sorted(cfg.reviews_dir.glob("sh-*.md")):
        text = f.read_text(errors="ignore")
        lines = ADR_LINE_RE.findall(text)
        out.update(int(n) for n in refs.ids(cfg).adr_mention_re.findall("\n".join(lines) if lines else text))
    return out


REF_LABELS = {"rule_refs": "rule_refs (house-rule ids)", "review_refs": "review_refs (finding ids)"}


def kind_refs(cfg: Config, kind: str) -> list[str]:
    """The ref lists a task of `kind` must cite one of: the kind's own `refs_any`, else the task
    log's (`task_log.kinds`, §20)."""
    rule = (cfg.task_log.get("kinds") or {}).get(kind) or {}
    own = rule.get("refs_any")
    return list(own) if own else list(cfg.task_log["refs_any"])


def kind_forbids(cfg: Config, kind: str) -> list[str]:
    """The ref lists a task of `kind` must leave empty: the kind's `forbid`, plus, for a kind with
    its own `refs_any`, the task log's `refs_any` lists it does not share."""
    rule = (cfg.task_log.get("kinds") or {}).get(kind) or {}
    own = rule.get("refs_any")
    extra = [k for k in cfg.task_log["refs_any"] if own and k not in own]
    return list(dict.fromkeys([*(rule.get("forbid") or []), *extra]))


def _check_kind(cfg: Config, t: dict[str, Any], rel: str) -> list[str]:
    """§20, §5: a task's kind sets which refs it cites (`task_log.kinds`). By default a refactor
    changes no rule: it cites house rules or findings, never the spec or an ADR."""
    kind = kind_of(t)
    kinds = cfg.task_log.get("kinds") or {}
    if kind not in kinds:
        return [f"{rel}: kind {kind!r} is not one of {', '.join(kinds)}"]
    errs = []
    cited = [k for k in kind_forbids(cfg, kind) if _as_list(t.get(k))]
    if cited:
        why = "changes no rule, so it " if kind == "refactor" else ""
        hint = " (a change to behaviour or stored data is a feature task)" if kind == "refactor" else ""
        errs.append(f"{rel}: a {kind} {why}cites no {', '.join(cited)}{hint}")
    if not (kinds.get(kind) or {}).get("refs_any"):
        return errs
    need = kind_refs(cfg, kind)
    if not any(_as_list(t.get(k)) for k in need):
        errs.append(f"{rel}: a {kind} cites " + " or ".join(REF_LABELS.get(k, k) for k in need) + _spec_hint(need))
    for r in _as_list(t.get("rule_refs")) if "rule_refs" in need else []:
        if not refs.ids(cfg).is_rule_id(r):
            errs.append(f"{rel}: rule_refs entry {r!r} is not a house-rule id ({refs.ids(cfg).rule_shape})")
    return errs


def _check_dry_runs(t: dict[str, Any], rel: str) -> list[str]:
    """§10 task_log.dry_run: each check of a task not yet done (or dropped) that has a step running a
    backticked command carries its writer's `dry run (<sha>):` line, or `dry run: n/a — <reason>`. Only
    that the line is there is checked; reading its output against `expect` stays the writer's."""
    if t.get("status") in TERMINAL:
        return []
    body = _section(t["_text"], SEC_CHECKS) or ""
    heads = list(CHECK_RE.finditer(body))
    errs = []
    for i, m in enumerate(heads):
        block = body[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(body)]
        if RUN_STEP_RE.search(block) and not (DRY_RUN_RE.search(block) or DRY_RUN_NA_RE.search(block)):
            errs.append(f"{rel}: dod_check `{m.group(1)}` runs a command but records no `dry run (<commit>):` "
                        "line from its writer's run, nor `dry run: n/a — <reason>` (task_log.dry_run, WRITING-tasks.md)")
    return errs


def _blank(m: re.Match[str]) -> str:
    """The matched text as spaces, its line breaks kept, so line numbers still count."""
    return re.sub(r"[^\n]", " ", m.group(0))


def _check_placeholders(t: dict[str, Any], rel: str) -> list[str]:
    """§5: a task not yet done or dropped that still holds a template placeholder is a copy not
    filled in. Names each placeholder and its line; quoted ones (code spans, fenced blocks) pass."""
    if t.get("status") in TERMINAL:
        return []
    text = CODE_SPAN_RE.sub(_blank, FENCE_RE.sub(_blank, t["_text"]))
    return [f"{rel}:{n}: template placeholder {ph!r} is still there — write the task's own text in its place "
            "(§5), or put it in backticks if you mean the text itself"
            for n, line in enumerate(text.split("\n"), 1) for ph in PLACEHOLDERS if ph in line]


def _spec_hint(lists: list[str]) -> str:
    """The hint for a task that cites none of `lists`, when spec_refs is one of them."""
    return SPEC_REFS_HINT if "spec_refs" in lists else ""


def _check_shaping(cfg: Config, t: dict[str, Any], rel: str, shaped: set[int]) -> list[str]:
    """§19.6: with shape_adrs on, a pending task from shape_from_task on that cites an ADR needs the
    ADR's shaping record, or `shaping: waived — <reason>`."""
    a = cfg.architect
    if not a or not a["shape_adrs"] or t.get("status") != "pending":
        return []
    n, start = _number(t.get("task_id"), cfg), _number(a["shape_from_task"], cfg)
    if n is None or start is None or n < start:
        return []
    waiver = str(t.get("shaping") or "")
    if waiver:
        return [] if WAIVER_RE.match(waiver) else \
            [f"{rel}: shaping {waiver!r}: a waiver reads `shaping: waived — <reason>`"]
    errs, named = [], set()
    for ref in _as_list(t.get("adr_refs")):
        n = adr_number(ref, cfg)
        if n is not None and n not in shaped and n not in named:
            named.add(n)
            errs.append(f"{rel}: cites {refs.ids(cfg).adr_id(n)} ({ref!r}), which has no shaping record "
                        f"({cfg.rel(cfg.reviews_dir)}/sh-*.md): run "
                        "`ccp architect run --mode shape --adr <id>` first, or add `shaping: waived — <reason>`")
    return errs


def _git(cfg: Config, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(cfg.root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def missing_task_files(cfg: Config) -> list[str]:
    """Task files that are gone, and numbers reused. A task file is never deleted and its NNNN is
    never reused (SPEC §4); a task that is no longer wanted is `dropped`.

    A file is gone when an id in the committed INDEX.yaml (or, outside git, the one on disk), or a
    task file git history deleted, has no file now. Its NNNN then either has no file, or another
    file holds it. That file is the same task under an amended id (a new slug, §17.4) only when its
    frontmatter says so: `renamed_from: <old id>`. Any other file holding the number is a reused
    number. A deleted path that is not a task file name (`NNNN-kebab-slug.md`) is not a task."""
    ids = refs.ids(cfg)
    holders: dict[str, tuple[str, list[str]]] = {}
    for f in cfg.tasks_dir.glob("*.md"):
        if m := ids.task_file_re.match(f.name):
            holders[m.group(1)] = (f.stem, _as_list(frontmatter(f.read_text()).get("renamed_from")))
    present = {tid for tid, _ in holders.values()}
    gone: dict[str, str] = {}
    committed = _git(cfg, "show", f"HEAD:./{cfg.rel(cfg.index_path)}")
    if committed is None and cfg.index_path.is_file():
        committed = cfg.index_path.read_text()
    for tid in INDEX_ID_RE.findall(committed or ""):
        if ids.task_file_re.match(f"{tid}.md") and tid not in present:
            gone.setdefault(tid, "listed in INDEX.yaml")
    log = _git(cfg, "log", "--no-renames", "--diff-filter=D", "--name-only", "--format=%x01%h",
               "--", cfg.rel(cfg.tasks_dir)) or ""
    sha = ""
    for line in log.splitlines():
        if line.startswith("\x01"):
            sha = line[1:]
        elif ids.task_file_re.match(Path(line).name) and Path(line).stem not in present:
            gone.setdefault(Path(line).stem, f"deleted in {sha}")
    out = []
    for tid, why in sorted(gone.items()):
        holder = holders.get(ids.task_number(tid))
        if holder is None:
            out.append(f"{tid}: its task file is gone ({why}). A task file is never deleted: restore it "
                       "with `status: dropped` and a note naming what replaced it")
        elif tid not in holder[1]:
            out.append(f"{tid}: its task file is gone ({why}) and its number now belongs to {holder[0]}. "
                       f"A number is never reused: restore {tid} with `status: dropped` and give {holder[0]} "
                       f"the next free number. If {holder[0]} is {tid} under an amended id, its frontmatter "
                       f"says `renamed_from: {tid}`")
    return out


def warnings(cfg: Config) -> list[str]:
    """What `check` reports without failing: a task not yet done that names a later task as a
    prerequisite in prose. `depends_on` cannot point forward (filesystem sort is execution
    order), so the waiting task is superseded by a new one that sorts after its prerequisite."""
    tasks = load(cfg)
    ids = refs.ids(cfg)
    later = {m.group(1): t.get("task_id") for t in tasks if (m := ids.task_file_re.match(t["_file"].name))}
    from ccp.config import config_warnings  # noqa: PLC0415
    out = config_warnings(cfg) + [f"{cfg.rel(t['_file'])}: status {t['_legacy_status']!r} is an in-flight state, which lives in the queue, "
           f"not the task file (§5): it reads as {t['status']!r}; write that"
           for t in tasks if t.get("_legacy_status")]
    for t in tasks:
        own = _number(t.get("task_id"), cfg)
        if own is None or t.get("status") in TERMINAL:
            continue
        body = t["_text"].split("\n---\n", 1)[-1]
        for m in prose_dep_re(ids.task_width).finditer(body):
            if m.group(1) in later and int(m.group(1)) > own:
                out.append(f"{cfg.rel(t['_file'])}: {m.group(0)!r} names {later[m.group(1)]}, which runs later, "
                           "as a prerequisite in prose, where nothing enforces it. Supersede this task with a "
                           "new one that sorts after it and lists it in depends_on (WRITING-tasks.md)")
    return out


def check(cfg: Config) -> list[str]:
    """Everything the structure promises, enforced. Returns the failures."""
    tl = cfg.task_log
    soft_re = re.compile(r"\b(" + "|".join(re.escape(w) for w in tl["soft_words"]) + r")\b", re.I) \
        if tl["soft_words"] else None
    errs: list[str] = []
    if not cfg.tasks_dir.is_dir():
        return [f"{cfg.rel(cfg.tasks_dir)}: missing — the task log lives here"]
    tasks = load(cfg)
    shaped = shaped_adrs(cfg) if cfg.architect and cfg.architect["shape_adrs"] else set()
    register, reg_errs = reviewpoints.load(cfg)  # §22: the review-point register, when the product keeps one
    errs += reg_errs
    seen: dict[str, str] = {}
    ids = {t.get("task_id") for t in tasks}
    for t in tasks:
        f: Path = t["_file"]
        rel = cfg.rel(f)
        m = refs.ids(cfg).task_file_re.match(f.name)
        if not m:
            errs.append(f"{rel}: filename must be NNNN-kebab-slug.md")
            continue
        nnnn = m.group(1)
        if nnnn in seen:
            errs.append(f"{rel}: NNNN {nnnn} already used by {seen[nnnn]} — never reuse")
        seen[nnnn] = f.name
        # Kinds exist only with the architect block; without it `kind:` is not read (§19).
        own_refs = cfg.architect is not None and bool(((tl.get("kinds") or {}).get(kind_of(t)) or {}).get("refs_any"))
        for k in tl["required"]:
            # A kind with its own refs (a refactor) may leave out the ones it is not allowed to fill (§20).
            own = ((tl.get("kinds") or {}).get(kind_of(t)) or {}).get("refs_any") or []
            if k not in t and not (own_refs and k in tl["refs_any"] and k not in own):
                errs.append(f"{rel}: frontmatter is missing `{k}`")
        if "paths" in t:   # §5: an inline list of repo-relative paths or globs
            ps = t["paths"]
            if not isinstance(ps, list) or not ps:
                errs.append(f"{rel}: paths must be a non-empty inline list, e.g. paths: [src/a.py, docs/*.md]")
            else:
                bad = [p for p in ps if str(p).startswith("/") or ".." in str(p).split("/") or "," in str(p)]
                if bad:
                    errs.append(f"{rel}: paths must be relative to the repo, without '..': {', '.join(map(str, bad))}")
        if t.get("task_id") != f.stem:
            errs.append(f"{rel}: task_id {t.get('task_id')!r} does not match the filename")
        for k in RUNTIME_KEYS:
            if k in t:
                errs.append(f"{rel}: frontmatter carries `{k}`, which is runtime state (SPEC §4): "
                            "it lives in the queue, never in the task file")
        if t.get("status") not in STATUSES and t.get("status") not in LEGACY_STATUSES:
            errs.append(f"{rel}: status {t.get('status')!r} is not one of {', '.join(STATUSES)}")
        if "review_point" in t:  # §22, §22.4: set when scoping; `ccp tasks close` stamps it otherwise
            rp = t["review_point"]
            if register is None:  # no register: the rule before it, unchanged (§22)
                if not isinstance(rp, str) or not re.match(tl["review_point_pattern"], rp):
                    errs.append(f"{rel}: review_point {rp!r} does not match task_log.review_point_pattern "
                                f"({tl['review_point_pattern']}, SPEC §22)")
            elif why := reviewpoints.problem(cfg, rp, register):
                errs.append(f"{rel}: {why}")
        for dep in _as_list(t.get("depends_on")):
            if dep not in ids:
                errs.append(f"{rel}: depends_on `{dep}`, which does not exist")
            elif dep >= str(t.get("task_id", "")):
                errs.append(f"{rel}: depends_on `{dep}`, which runs later — "
                            "dependencies must precede (filesystem sort is execution order)")
        if not own_refs and tl["refs_any"] and not any(_as_list(t.get(k)) for k in tl["refs_any"]):
            errs.append(f"{rel}: cites none of {', '.join(tl['refs_any'])}" + _spec_hint(tl["refs_any"]))
        if cfg.architect is not None:
            errs += _check_kind(cfg, t, rel)
        if "sign_off" in t:  # §3.5: brief, build or both
            so = [str(x).strip().lower() for x in _as_list(t["sign_off"])]
            if not so or any(x not in SIGN_OFF_STAGES for x in so):
                errs.append(f"{rel}: sign_off {t['sign_off']!r} names no stage, or one that is not "
                            f"{' or '.join(SIGN_OFF_STAGES)} (SPEC §3.5)")
        if "gate" in t and str(t.get("gate") or "").strip().lower() != "cold":
            errs.append(f"{rel}: gate {t.get('gate')!r} is not `cold`, the one value it takes (§15.3)")
        errs += _check_shaping(cfg, t, rel, shaped)
        errs += _check_placeholders(t, rel)
        for s in tl["sections"]:  # the canonical six by default; a product may require more
            if _section(t["_text"], s) is None:
                errs.append(f"{rel}: missing section `## {s}`")
        checks = t["_checks"]
        if not checks:
            errs.append(f"{rel}: no dod_checks — a task with nothing to verify is not a task")
        if len(checks) > tl["max_checks"]:
            errs.append(f"{rel}: {len(checks)} dod_checks — more than {tl['max_checks']} means this is "
                        "more than one task (WRITING-tasks.md)")
        if len(set(checks)) != len(checks):
            errs.append(f"{rel}: duplicate dod_check ids")
        if tl["dry_run"]:
            errs += _check_dry_runs(t, rel)
        if soft_re:
            # a dry run line quotes what a command printed, so its words are not the check's own (§21)
            for mm in soft_re.finditer(DRY_RUN_LINE_RE.sub("", _section(t["_text"], SEC_CHECKS) or "")):
                errs.append(f"{rel}: soft language {mm.group(0)!r} in a check — "
                            "if it cannot fail, it is not a check")
        if t.get("status") == "done":
            ver = _section(t["_text"], SEC_VERIFY) or ""
            if not re.search(r"^- ", ver, re.M):
                errs.append(f"{rel}: status is done with no verification notes")
    errs += missing_task_files(cfg)
    if not cfg.task_log.get("index", True):
        return errs  # SPEC §5.7: the product keeps no index
    idx = cfg.rel(cfg.index_path)
    if not cfg.index_path.exists():
        errs.append(f"{idx}: missing — run `ccp tasks index`")
    elif cfg.index_path.read_text() != render_index(cfg, tasks):
        errs.append(f"{idx}: stale — run `ccp tasks index`")
    return errs


def render_index(cfg: Config, tasks: list[dict[str, Any]] | None = None) -> str:
    """INDEX.yaml. Its format is frozen (SPEC §5.7): these five fields per task, nothing added.
    New task fields go to the board (`board.json`, §28.3)."""
    tasks = tasks if tasks is not None else load(cfg)
    # No generated-on date: it would make the index "stale" every midnight and force a rewrite
    # that changes nothing. Git records when it was written.
    lines = ["# Generated by `ccp tasks index` — do not hand-edit.",
             "# One task per file under tasks/. Never delete, never renumber.",
             f"project_id: {cfg.project_id}",
             "tasks:"]
    for t in tasks:
        lines += [f"  - id: {t.get('task_id')}",
                  f"    status: {t.get('status')}",
                  f"    title: {t.get('title')}",
                  f"    depends_on: [{', '.join(_as_list(t.get('depends_on')))}]",
                  f"    path: tasks/{t['_file'].name}"]
    return "\n".join(lines) + "\n"


def write_index(cfg: Config) -> str:
    """Write INDEX.yaml, or nothing when the product keeps none (SPEC §5.7)."""
    if not cfg.task_log.get("index", True):
        return "(no index: task_log.index is false)"
    cfg.index_path.write_text(render_index(cfg))
    return cfg.rel(cfg.index_path)


def in_scope(tid: str, scope: list[str] | None) -> bool:
    """A scope entry names a whole task id or its NNNN; no scope means every task."""
    return not scope or any(tid == s or tid.split("-", 1)[0] == s for s in scope)


def done_order(cfg: Config, tasks: list[dict[str, Any]] | None = None) -> list[str]:
    """Every `done` task, in the order its file's status became `done` in git history (one
    `git log -G` over the task directory). Tasks done only in the working tree, or outside git,
    come last in NNNN order."""
    tasks = tasks if tasks is not None else load(cfg)
    done = {t.get("task_id") for t in tasks if t.get("status") == "done"}
    order: list[str] = []
    r = subprocess.run(["git", "-C", str(cfg.root), "log", "--reverse", "--format=%x01%H", "-p", "-U0",
                        "--no-color", "--no-ext-diff", "-G^status:", "--", cfg.rel(cfg.tasks_dir)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        per_file: dict[str, list[bool]] = {}

        def flush() -> None:
            for tid, (minus, plus) in per_file.items():
                if plus and not minus and tid not in order:
                    order.append(tid)
                elif minus and not plus and tid in order:
                    order.remove(tid)  # reopened: it re-enters when it is done again
            per_file.clear()

        cur = None
        for line in r.stdout.splitlines():
            if line.startswith("\x01"):
                flush()
            elif line.startswith("+++ "):
                cur = Path(line[6:]).stem if line.startswith("+++ b/") else None
            elif cur and (line.startswith("+status:") or line.startswith("-status:")):
                if _strip_comment(line[8:].strip()).strip("'\"") == "done":
                    per_file.setdefault(cur, [False, False])[0 if line[0] == "-" else 1] = True
        flush()
    order = [t for t in order if t in done]
    return order + sorted(done - set(order))


def features_since_refactor(cfg: Config, tasks: list[dict[str, Any]]) -> int:
    """Feature tasks merged since the last refactor merged (all of them, if none has)."""
    kinds = {t.get("task_id"): kind_of(t) for t in tasks}
    n = 0
    for tid in done_order(cfg, tasks):
        n = 0 if kinds.get(tid) == "refactor" else n + 1
    return n


def scope_deps(tasks: list[dict[str, Any]], scope: list[str] | None) -> dict[str, str]:
    """Every task an open (not done, not dropped) task in the scope depends on, directly or
    transitively, outside the scope, mapped to the scope task that needs it (the lowest NNNN). The
    walk stops at a dropped task: a dropped dependency never makes its own dependencies needed."""
    deps = {str(t.get("task_id")): _as_list(t.get("depends_on")) for t in tasks}
    dropped = {str(t.get("task_id")) for t in tasks if t.get("status") == "dropped"}
    need: dict[str, str] = {}
    for t in tasks:
        tid = str(t.get("task_id"))
        if not scope or not in_scope(tid, scope) or t.get("status") in ("done", "dropped"):
            continue
        stack = list(deps.get(tid, []))
        while stack:
            d = stack.pop()
            if d in need or in_scope(d, scope) or d in dropped:
                continue
            need[d] = tid
            stack += deps.get(d, [])
    return need


def refactor_reach(cfg: Config, tasks: list[dict[str, Any]], scope: list[str] | None) -> dict[str, str]:
    """§20: the refactors outside the scope that `next` widens it to, each with the reason:
    every refactor under `refactor_in_scope: true`, the ones a scope task depends on under "deps",
    none under false or without the architect block."""
    a = cfg.architect
    mode = a["refactor_in_scope"] if a else False
    if not scope or mode is False:
        return {}
    need = scope_deps(tasks, scope) if mode == "deps" else {}
    return {str(t.get("task_id")): need.get(str(t.get("task_id")), "")
            for t in tasks if kind_of(t) == "refactor" and not in_scope(str(t.get("task_id")), scope)
            and (mode is True or str(t.get("task_id")) in need)}


def waiting_refactors(cfg: Config, scope: list[str] | None,
                      tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """§20.4: outstanding (pending, ready or not) refactors that the scope neither names nor reaches,
    in task order. Under "deps" these go to the top of the next review point's scope (§10.2)."""
    if cfg.architect is None or not scope:
        return []
    tasks = tasks if tasks is not None else load(cfg)
    reach = refactor_reach(cfg, tasks, scope)
    return [t for t in tasks if kind_of(t) == "refactor" and t.get("status") == "pending"
            and not in_scope(str(t.get("task_id")), scope) and str(t.get("task_id")) not in reach]


def preferred(cfg: Config, tid: str, scope: list[str] | None,
              tasks: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, str]:
    """§10.4: one entry of the lead's preference list (work.json `next_tasks`, `ccp tasks prefer`), and its state:
    "ready" (pending, every dependency done, in the scope or reached by it), "waiting on <ids>",
    or why it is ignored ("unknown", "done", "dropped", "<status>", "out of scope")."""
    tasks = tasks if tasks is not None else load(cfg)
    t = next((x for x in tasks if str(x.get("task_id")) == tid or x["_file"].stem == tid), None)
    if t is None:
        return None, "unknown"
    if t.get("status") != "pending":
        return t, str(t.get("status") or "no status")
    if not in_scope(tid, scope) and tid not in refactor_reach(cfg, tasks, scope):
        return t, "out of scope"
    done = {x.get("task_id") for x in tasks if x.get("status") == "done"}
    waits = [d for d in _as_list(t.get("depends_on")) if d not in done]
    return t, ("waiting on " + ", ".join(waits)) if waits else "ready"


def ranked(cfg: Config, scope: list[str] | None = None, first: list[str] | None = None,
           prefer: list[tuple[dict[str, Any], str]] | None = None,
           tasks: list[dict[str, Any]] | None = None,
           review_point: str | None = None, since: int | None = None) -> list[tuple[dict[str, Any], str]]:
    """The one selection `ccp tasks next` and the board share (§10.3, §20.3): every ready task, each
    with why it comes where it does, in the order `next` would return them if each merged in turn
    and nothing else became ready. Row 0 is `next`'s pick now.

    Ready: pending, every dependency done (dependencies need not be in scope), in the scope or
    reached by it (`refactor_reach`: all refactors under `refactor_in_scope: true`, the ones a scope
    task depends on under "deps"). The order: `prefer` (the lead's preference list, each with its why:
    the ready ones, in the lead's order); then `first` (work.json's `review_point_refactors`), lowest NNNN first; then a
    ready refactor whenever `refactor_every` features have merged since the last refactor; then
    lowest NNNN."""
    tasks = tasks if tasks is not None else load(cfg)
    done = {t.get("task_id") for t in tasks if t.get("status") == "done"}
    a = cfg.architect
    reach = refactor_reach(cfg, tasks, scope)
    ready = [t for t in tasks
             if (in_scope(str(t.get("task_id")), scope) or str(t.get("task_id")) in reach)
             and t.get("status") == "pending" and all(d in done for d in _as_list(t.get("depends_on")))]
    out: list[tuple[dict[str, Any], str]] = []
    for p in prefer or []:
        if p[0] in ready:
            ready.remove(p[0])
            out.append(p)
    every = a["refactor_every"] if a else 0
    # git's count is only needed when a ready refactor could jump the queue (it is one `git log`)
    since = (since if since is not None else features_since_refactor(cfg, tasks)) \
        if every and any(kind_of(t) == "refactor" for t in ready) else 0
    for p, _ in out:
        since = 0 if kind_of(p) == "refactor" else since + 1
    while ready:
        firsts = [t for t in ready if str(t.get("task_id")) in (first or [])]
        refactors = [t for t in ready if kind_of(t) == "refactor"]
        if firsts:
            pick = firsts[0]
            why = (f"a refactor waiting from an earlier cycle, taken first at review point {review_point or '?'} "
                   "(work.json review_point_refactors, SPEC §20)")
        elif every and refactors and ready[0] is not refactors[0] and since >= every:
            pick, why = refactors[0], f"a refactor, due after {every} feature merge{'' if every == 1 else 's'} since the last (SPEC §20)"
        else:
            pick = ready[0]
            tid = str(pick.get("task_id"))
            need = reach.get(tid) if scope and not in_scope(tid, scope) else None
            why = (f"outside the given scope: a refactor that in-scope task {need} depends on "
                   '(plane.json architect.refactor_in_scope: "deps", SPEC §20.4)' if need else
                   "outside the given scope: a refactor, and refactors belong to every scope "
                   "(plane.json architect.refactor_in_scope: true, SPEC §20.4)"
                   if scope and not in_scope(tid, scope) else "")
        ready.remove(pick)
        since = 0 if kind_of(pick) == "refactor" else since + 1
        out.append((pick, why))
    return out


def next_task(cfg: Config, scope: list[str] | None = None,
              first: list[str] | None = None) -> dict[str, Any] | None:
    """`ranked`'s first row without a preference: what `ccp tasks next` picks by the plane's own order."""
    r = ranked(cfg, scope, first)
    return r[0][0] if r else None


def task_numbers(cfg: Config) -> frozenset[str]:
    """The numbers of the tasks in the task log (its `NNNN-slug.md` files), as written (`0042`)."""
    ids = refs.ids(cfg)
    if not cfg.tasks_dir.is_dir():
        return frozenset()
    return frozenset(m.group(1) for f in cfg.tasks_dir.glob("*.md") if (m := ids.task_file_re.match(f.name)))


def next_number(cfg: Config) -> str:
    """The next free NNNN, for a seat or tool filing a new task."""
    ids = refs.ids(cfg)
    nums = [int(m.group(1)) for f in cfg.tasks_dir.glob("*.md") if (m := ids.task_file_re.match(f.name))]
    return ids.format_task_number(max(nums, default=0) + 1)
