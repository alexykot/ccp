"""`ccp tasks migrate`: an earlier plane generation's task files, converted in place (SPEC §5.3).

An earlier generation wrote a task file with no frontmatter: a `# Task NNNN: <title>` heading, a
`## Meta` table (`| Field | Value |` rows `ID`, `Status`, `Depends on`, `Created`), a `## Refs` table
(`| Kind | Ref |` rows such as `SPEC` and `ADR`), then free sections, its title in the old
`INDEX.yaml` (`- id:` / `title:` entries). A second shape writes its keys and values in backticks: a
Meta table with rows `task_id`, `status`, `depends_on` (a `["<id>", …]` list) and `created`, and a
Refs table (`| Field | Value |`) whose `spec_refs` row lists backticked `<path>#<anchor>` links into the
SPEC, under a heading with a note after it (`## Refs (…)`). A task file is never deleted (§5.1), so
such a file is converted where it is, never archived.

The frontmatter comes from those tables: `task_id` the file stem; `title` from the `INDEX.yaml`
committed at HEAD, else the heading without its `Task NNNN:` prefix, else the slug; `status` `done` or
`dropped` by the old status's word; `depends_on` the `Depends on` (or `depends_on`) row's ids (a bare
number names the one file holding it); `spec_refs` from the Refs rows keyed `SPEC` or `spec_refs`, each
value split into its backticked items (else on commas): each `§N`, `§N.M` or `SN` as the product's spec
ref for section N, and a `<path>#<anchor>` whose path names a SPEC file (`spec_paths`) kept as
written, deduplicated in order; `created` and `updated` the `Created` date; `adopt: "none"`.
The whole old text is kept verbatim, in a fenced block, under `## Context (not checked)`; the other
sections say the record was converted and not re-verified (one dod_check, `legacy-01`, and one
verification note). Table keys are matched case-insensitively; a table's heading may carry a note after
its name.

An open task (any other old status) is converted only with `drop_open`, as `dropped` with a note. A
file it cannot convert, or whose converted text `ccp tasks check` would fail, is named with the reason
and left byte for byte; a file with no SPEC section names the Refs heading it read (or none) and each
of its rows. A file that already has frontmatter is left alone without a line of its own.
"""
from __future__ import annotations

import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ccp import mdsection, refs, tasklog
from ccp.config import Config
from ccp.config import spec_paths as spec_paths_of

DONE_WORDS = ("done", "complete", "completed")
DROPPED_WORDS = ("dropped", "cancelled", "canceled", "superseded", "abandoned")
DROP_NOTE = "dropped at migration: rewrite it as a new task if it is still wanted"
HEADING_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.M)
TASK_PREFIX_RE = re.compile(r"^Task[ \t]+\d+[ \t]*[:—–-][ \t]*", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")
INDEX_ENTRY_RE = re.compile(r"^[ \t]*-[ \t]+id:[ \t]*(.+?)[ \t]*$")
INDEX_TITLE_RE = re.compile(r"^[ \t]*title:[ \t]*(.+?)[ \t]*$")
BACKTICKED_RE = re.compile(r"`([^`]+)`")
SPEC_LINK_RE = re.compile(r"^([^\s#]+)#\S+$")
REFS_KEYS = ("spec", "spec_refs")


def _cell(v: str) -> str:
    return v.strip().strip("`*_").strip()


def _head_text(name: str) -> str:
    """A `## <name>` heading's text (any case), with or without a note after a space."""
    return rf"(?i:{re.escape(name)})(?:[ \t][^\n]*)?$"


def heading(text: str, name: str) -> re.Match[str] | None:
    """The first `## <name>` heading line outside a fenced block (`_head_text`)."""
    return re.search(rf"^##[ \t]+{_head_text(name)}", mdsection.unfence(text), re.M)


def table(text: str, name: str, raw: bool = False) -> list[tuple[str, str]] | None:
    """The `(key, value)` rows of the two-column table under `## <name>` (`_head_text`), its header and
    separator rows left out; None when there is no such heading or it holds no row. Each key is lowercased
    without its backticks or emphasis; each value too, or with `raw` only trimmed."""
    span = mdsection.heading_span(text, _head_text(name), level=2)
    if not span:
        return None
    body = text[span[1]:span[2]]
    rows = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(SEPARATOR_CELL_RE.match(c) for c in cells if c):
            if rows:
                rows.pop()  # the row above a separator is the header
            continue
        if len(cells) >= 2:
            value = "|".join(cells[1:])
            rows.append((_cell(cells[0]).lower(), value.strip() if raw else _cell(value)))
    return rows or None


def index_titles(cfg: Config) -> dict[str, str]:
    """Titles by id from the `INDEX.yaml` committed at HEAD, read loosely (`- id:` then `title:`)."""
    r = subprocess.run(["git", "-C", str(cfg.root), "show", f"HEAD:./{cfg.rel(cfg.index_path)}"],
                       capture_output=True, text=True)
    out: dict[str, str] = {}
    if r.returncode != 0:
        return out
    cur = None
    for line in r.stdout.splitlines():
        if m := INDEX_ENTRY_RE.match(line):
            cur = m.group(1).strip("'\"")
        elif cur and (m := INDEX_TITLE_RE.match(line)):
            out.setdefault(cur, m.group(1).strip("'\""))
    return out


def spec_refs(cfg: Config, values: list[str]) -> list[str]:
    """The spec refs `values` name, in order, deduplicated. Each value is split into its backticked items
    when it has any, else on commas; in each item a `§N`, `§N.M` or `SN` (or the product's prefix) is the
    product's ref for section N, and an item `<path>#<anchor>` whose path names a SPEC file
    (`spec_paths`) is kept as written."""
    ids = refs.ids(cfg)
    prefixes = "|".join(re.escape(p) for p in dict.fromkeys(("S", ids.spec_prefix)))
    ref_re = re.compile(rf"(?:§[ \t]*|(?<![\w/-])(?:{prefixes}))(\d{{1,3}})(?:\.\d+)*(?![\w/-])")
    spec_paths = spec_paths_of(cfg)
    found = []
    for v in values:
        for item in BACKTICKED_RE.findall(v) or v.split(","):
            item = item.strip().strip("*").strip()
            if (m := SPEC_LINK_RE.match(item)) and tasklog._names_spec(m.group(1), spec_paths):
                found.append(item)
            else:
                found += [ids.spec_ref(int(r.group(1))) for r in ref_re.finditer(item)]
    return list(dict.fromkeys(found))


def _depends(cfg: Config, value: str) -> tuple[list[str], str | None]:
    """The ids a `Depends on` value names (a `["<id>", …]` list as its ids), each resolved to a task file, or
    why one has no file."""
    ids = refs.ids(cfg)
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):  # a `["<id>", …]` list
        value = value[1:-1]
    words = [w.strip("`*_ \"'") for w in re.split(r"[,\s]+", value)]
    out = []
    for w in words:
        if not w or w in ("-", "—", "–", "none"):
            continue
        if (cfg.tasks_dir / f"{w}.md").is_file():
            out.append(w)
            continue
        held = [f.stem for f in sorted(cfg.tasks_dir.glob("*.md"))
                if w.isdigit() and len(w) == ids.task_width and ids.task_number(f.stem) == w
                and ids.task_file_re.match(f.name)]
        if len(held) != 1:
            return [], f"Depends on names {w}, which has no task file"
        out.append(held[0])
    return list(dict.fromkeys(out)), None


def _quote(v: str) -> str:
    """A frontmatter scalar `tasklog.frontmatter` reads back as `v`."""
    if not (" #" in v or v[:1] in "\"'[" or v != v.strip()):
        return v
    return f'"{v}"' if '"' not in v else f"'{v}'"


def _fence(text: str) -> str:
    runs = [len(m.group(1)) for m in re.finditer(r"^[ \t]*(~{3,})", text, re.M)]
    return "~" * max(3, max(runs, default=0) + 1)


def render(cfg: Config, tid: str, meta: dict[str, Any], old: str, today: str) -> str:
    """The converted file: frontmatter, the canonical sections, the old text verbatim under Context."""
    fence = _fence(old)
    kept = old if old.endswith("\n") else old + "\n"
    lst = lambda xs: "[" + ", ".join(f'"{x}"' for x in xs) + "]"  # noqa: E731
    notes = [f"- {today} — converted by ccp tasks migrate from an earlier plane generation's "
             f"{meta['old_status']} record; not re-verified under this plane."]
    if meta["dropped_open"]:
        notes.append(f"- {today} — {DROP_NOTE}.")
    return (f"---\ntask_id: {tid}\ntitle: {_quote(meta['title'])}\nstatus: {meta['status']}\n"
            f"depends_on: {lst(meta['depends_on'])}\nspec_refs: {lst(meta['spec_refs'])}\n"
            f"created: {meta['created']}\nupdated: {meta['created']}\nadopt: \"none\"\n---\n\n"
            f"# Task: {tid}\n\n"
            f"## {tasklog.SEC_INTENT}\n\n"
            "Converted from an earlier plane generation's task record; the original text is under Context.\n\n"
            f"## {tasklog.SEC_CONTEXT}\n\n{fence}\n{kept}{fence}\n\n"
            f"## {tasklog.SEC_SCOPE}\n\n- **In:** see Context.\n- **Out:** nothing recorded.\n\n"
            f"## {tasklog.SEC_CHECKS}\n\n- id: `legacy-01`\n  story: the record converted.\n"
            "  expect: the original text is under Context.\n\n"
            f"## {tasklog.SEC_IMPL}\n\n*Append-only, newest last.*\n\n"
            f"## {tasklog.SEC_VERIFY}\n\n" + "\n".join(notes) + "\n")


def _refs_read(text: str, rows: list[tuple[str, str]]) -> str:
    """What was read for the Refs table: its heading line (or none) and each row's key with its value."""
    m = heading(text, "Refs")
    if not m:
        return " (no Refs heading)"
    read = "; ".join(f"{k} = {v}" for k, v in rows) or "no rows"
    return f" ({m.group(0).strip()}: {read})"


def convert(cfg: Config, f: Path, titles: dict[str, str], drop_open: bool) -> tuple[dict[str, Any] | None, str | None]:
    """What the old file `f` converts to, or why it cannot be converted."""
    ids = refs.ids(cfg)
    if not ids.task_file_re.match(f.name):
        return None, "its name is not NNNN-kebab-slug.md"
    text = f.read_text()
    meta_rows = table(text, "Meta")
    if meta_rows is None:
        return None, "no Meta table"
    row = {}
    for k, v in meta_rows:
        row.setdefault(k, v)
    if "status" not in row:
        return None, "no Status row in its Meta table"
    old_status = row["status"]
    word = old_status.lower()
    status, dropped_open = ("done", False) if word in DONE_WORDS else ("dropped", False) if word in DROPPED_WORDS \
        else ("dropped", True)
    if dropped_open and not drop_open:
        return None, (f"an open task (Status: {old_status or 'empty'}): rewrite it as a new task, or pass "
                      "--drop-open to convert it as dropped")
    ref_rows = table(text, "Refs", raw=True) or []
    specs = spec_refs(cfg, [v for k, v in ref_rows if k in REFS_KEYS])
    if not specs:
        return None, "no SPEC section in its Refs table" + _refs_read(text, ref_rows)
    created = row.get("created", "")
    if not DATE_RE.match(created):
        return None, f"Created {created!r} is not YYYY-MM-DD"
    try:
        date.fromisoformat(created)
    except ValueError:
        return None, f"Created {created!r} is not YYYY-MM-DD"
    deps, why = _depends(cfg, row.get("depends on", row.get("depends_on", "")))
    if why:
        return None, why
    title = titles.get(f.stem) or titles.get(ids.task_number(f.stem))
    if not title and (h := HEADING_RE.search(text)):
        title = TASK_PREFIX_RE.sub("", h.group(1)).strip()
    if not title:
        title = ids.task_file_re.match(f.name).group(2).replace("-", " ")
    return {"title": title, "status": status, "old_status": old_status, "dropped_open": dropped_open,
            "depends_on": deps, "spec_refs": specs, "created": created}, None


def check_failures(cfg: Config, rendered: dict[Path, str]) -> dict[Path, list[str]]:
    """`ccp tasks check`'s failures for each rendered file, with the log read as if they were written."""
    errs = tasklog.check(cfg, rendered)
    out = {}
    for f in rendered:
        prefix = f"{cfg.rel(f)}: "
        if mine := [e[len(prefix):] for e in errs if e.startswith(prefix)]:
            out[f] = mine
    return out


def migrate(cfg: Config, dry_run: bool = False, drop_open: bool = False) -> dict[str, Any]:
    """Convert each task file with no frontmatter (none written with `dry_run`). Returns `files`, one row per
    such file (`path`, `result`: converted or cannot, `reason`), and `current`, how many already had one.
    A converted file `ccp tasks check` would fail is not written; one that depends on it is checked again
    without it."""
    titles = index_titles(cfg)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows: dict[Path, dict[str, Any]] = {}
    rendered: dict[Path, str] = {}
    current = 0
    for f in sorted(cfg.tasks_dir.glob("*.md")):
        old = f.read_text()
        if tasklog.has_frontmatter(old):
            current += 1
            continue
        meta, why = convert(cfg, f, titles, drop_open)
        if meta is None:
            rows[f] = {"path": cfg.rel(f), "result": "cannot convert", "reason": why}
            continue
        rendered[f] = render(cfg, f.stem, meta, old, today)
        rows[f] = {"path": cfg.rel(f), "result": "converted", "status": meta["status"]}
    while rendered and (failed := check_failures(cfg, rendered)):
        for f, errs in failed.items():
            del rendered[f]
            rows[f] = {"path": cfg.rel(f), "result": "cannot convert",
                       "reason": "converted, it would fail `ccp tasks check`: " + "; ".join(errs)}
    if not dry_run:
        for f, text in rendered.items():
            f.write_text(text)
    return {"files": list(rows.values()), "current": current}
