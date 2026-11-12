"""ADRs (SPEC §6): the plane's ADR format, its checks, its commands and the generated index.

  ccp adr new "<title>"                          the next ADR, from the template, status proposed
  ccp adr status N <status> [--note T]           move an ADR along adr.transitions
  ccp adr supersede OLD NEW [--decisions D2,D4] [--by Dk] [--archive]
                                                 links both ways, statuses and decision states
  ccp adr decide N D3 <state> [--by "ADR-0007 D1"] [--note T]
                                                 one decision's build state
  ccp adr check | index [--stdout] | list [--json] | migrate --markers [--dry-run]

An ADR opens with YAML frontmatter (`id`, `title`, `status`, `date` required; `deciders`,
`supersedes`, `superseded_by`, `amends`, `review_points`, `spec_refs`, `decisions`, `notes`
declared; any other key is a warning). Its decisions are numbered headings, `### D1. Title`; other
styles (a bold bullet, a bold lead, a paragraph) are read for compatibility and warned about, or
refused under `adr.strict`. `decisions:` records each decision's build state as one string per
decision, `D<n> <state>[ by <ADR id>[ D<n>]][ — <note>]`, state one of not_built, built, live,
retired. Links (`supersedes`, `superseded_by`, `amends`) are lists of `<ADR id>[ D<n>]`; the reverse
of each is checked.

The plane takes no YAML dependency: the writer emits a small subset (plain tokens, JSON-quoted
strings, `|-` literal blocks, inline and block lists) and the reader understands that subset plus
hand-written plain and single-quoted scalars. A line it does not understand is a `ccp docs check`
failure, never a silent skip. Commands rewrite only the frontmatter keys they change; every other
line of the file is kept byte for byte.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from ccp import refs, reviewpoints
from ccp.config import ADR_DEFAULTS, Config

FILE_RE = refs.DEFAULT.adr_file_re  # the default; a product may set ids.adr (refs.py)
KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*?))?[ \t]*$")
PLAIN_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
REQUIRED = ("id", "title", "status", "date")
OPTIONAL = ("deciders", "supersedes", "superseded_by", "amends", "review_points", "spec_refs", "decisions", "notes")
LIST_KEYS = ("supersedes", "superseded_by", "amends", "review_points", "spec_refs", "decisions")
LINK_KEYS = ("supersedes", "superseded_by", "amends")
STATES = ("not_built", "built", "live", "retired")
DECISION_RE = re.compile(r"^D(\d+[a-z]?)[ \t]+([a-z_]+)(?:[ \t]+by[ \t]+(.+?))?(?:[ \t]+—[ \t]+(.*))?$")
FENCES = ("```", "~~~")
CANONICAL_RE = re.compile(r"^### D(\d+[a-z]?)\.(?: \S|$)")


class ParseError(ValueError):
    pass


# ---------------------------------------------------------------- the frontmatter subset

def _scalar(v: str) -> str:
    if v.startswith('"'):
        try:
            out = json.loads(v)
        except ValueError:
            raise ParseError(f"cannot read the quoted value {v[:60]!r}") from None
        if not isinstance(out, str):
            raise ParseError(f"not a string: {v[:60]!r}")
        return out
    if v.startswith("'"):
        if len(v) < 2 or not v.endswith("'"):
            raise ParseError(f"unclosed single quote: {v[:60]!r}")
        return v[1:-1].replace("''", "'")
    return re.sub(r"[ \t]+#.*$", "", v)  # a plain scalar may carry a trailing comment


def _inline_list(v: str) -> list[str]:
    """`[a, "b, c", 'd''s']`: each item read as `_scalar` reads a value (a double-quoted item is JSON,
    so `\\"` and `\\\\` unescape exactly as the writer escapes them)."""
    inner = v[1:-1].strip()
    if not inner:
        return []
    items, cur, q, esc = [], "", None, False
    for ch in inner:
        if q == '"' and esc:
            esc = False
        elif q == '"' and ch == "\\":
            esc = True
        elif ch in "\"'" and (q == ch or (q is None and not cur.strip())):
            q = None if q else ch
        elif ch == "," and q is None:
            items.append(cur)
            cur = ""
            continue
        cur += ch
    return [_scalar(i.strip()) for i in items + [cur] if i.strip()]


def split(text: str) -> tuple[str | None, str]:
    """(frontmatter text, the rest) when the file opens with `---`, else (None, text)."""
    if text.startswith("---\r\n"):   # a CRLF file: the frontmatter read with LF, the body kept as is
        end = text.find("\r\n---\r\n", 3)
        if end == -1:
            raise ParseError("frontmatter opens with --- and never closes")
        return text[5:end + 2].replace("\r\n", "\n"), text[end + 7:]
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.endswith("\n---"):
            return text[4:-4], ""
        raise ParseError("frontmatter opens with --- and never closes")
    return text[4:end + 1], text[end + 5:]


def parse(fm: str) -> dict[str, Any]:
    """The frontmatter subset: `k: plain | "json" | 'single' | [a, b] | |- block | (block list)`."""
    out: dict[str, Any] = {}
    lines = fm.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = KEY_RE.match(line)
        if not m:
            raise ParseError(f"line {i + 1} is not `key: value`: {line[:60]!r}")
        k, v = m.group(1), (m.group(2) or "")
        if k in out:
            raise ParseError(f"line {i + 1}: `{k}` appears twice")
        i += 1
        bm = re.match(r"^\|([1-9])?([-+])?$", v)
        if bm:
            block: list[str] = []
            while i < len(lines) and (not lines[i].strip() or lines[i].startswith((" ", "\t"))):
                block.append(lines[i])
                i += 1
            ind = int(bm.group(1)) if bm.group(1) else next(
                (len(b) - len(b.lstrip(" ")) for b in block if b.strip()), 0)
            if ind == 0 and any(b.strip() for b in block):
                raise ParseError(f"`{k}`: a block's lines must be indented")
            body = []
            for b in block:
                if b.strip() and not b.startswith(" " * ind):
                    raise ParseError(f"`{k}`: a block line is indented less than its first line")
                body.append(b[ind:])
            text = "\n".join(body)
            chomp = bm.group(2)
            text = text.rstrip("\n") if chomp == "-" else text if chomp == "+" else text.rstrip("\n") + "\n"
            out[k] = text
        elif v == "":
            items = []
            while i < len(lines) and re.match(r"^\s+- ", lines[i]):
                items.append(_scalar(lines[i].split("- ", 1)[1].strip()))
                i += 1
            out[k] = items if items else ""
        elif v.startswith("[") and v.endswith("]"):
            out[k] = _inline_list(v)
        else:
            out[k] = _scalar(v)
    return out


def _quote(s: str) -> str:
    """A JSON string is a YAML double-quoted scalar; the characters YAML would break or refuse are
    escaped too (JSON leaves U+0085, U+2028, U+2029, DEL and C1 raw)."""
    return UNSAFE_RE.sub(lambda m: f"\\u{ord(m.group(0)):04x}", json.dumps(s, ensure_ascii=False))


def _block_ok(s: str) -> bool:
    """A `|-` block keeps text exactly only when it holds no character YAML escapes, starts and ends
    on text, and has no line of only whitespace (a reader may fold its spaces into indentation).
    Anything else is written quoted, which is exact for every string."""
    if "\n" not in s or "\r" in s or UNSAFE_RE.search(s) or s.startswith("\n") or s.endswith("\n"):
        return False
    return all(ln.strip() or not ln for ln in s.split("\n"))


def _emit_value(k: str, v: Any) -> list[str]:
    if not KEY_RE.match(f"{k}:") or k.lower() in YAML_WORDS or k[0].isdigit():
        raise ValueError(f"not a safe key: {k!r}")
    if isinstance(v, list):
        return _emit_list(k, v)
    s = str(v)
    if _block_ok(s):
        ind = "|2-" if s[:1] in (" ", "\t") else "|-"
        return [f"{k}: {ind}"] + [("  " + x) if x else "" for x in s.split("\n")]
    if k in ("id", "status", "superseded_by") and PLAIN_OK.match(s) and s.lower() not in YAML_WORDS:
        return [f"{k}: {s}"]
    return [f"{k}: {_quote(s)}"]  # `date` too: a bare date is a date to a YAML reader, a string to us


def emit(fields: dict[str, Any]) -> str:
    out = ["---"]
    for k, v in fields.items():
        out += _emit_value(k, v)
    return "\n".join(out + ["---"]) + "\n"


# Keys YAML 1.1 reads as booleans or null (`on: x` is {True: "x"} to PyYAML): never written bare.
YAML_WORDS = {"y", "n", "yes", "no", "on", "off", "true", "false", "null"}
# Characters a YAML reader treats as line breaks or refuses raw: always written escaped.
UNSAFE_RE = re.compile("[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\ufeff]")


def _emit_list(k: str, v: list[str]) -> list[str]:
    """A list: inline when short and plain, else one item per line (decisions, links)."""
    items = [x if PLAIN_OK.match(x) and x.lower() not in YAML_WORDS else _quote(x) for x in map(str, v)]
    inline = f"{k}: [{', '.join(items)}]"
    if k not in ("decisions", "supersedes", "superseded_by", "amends") or (len(inline) <= 100 and len(v) <= 3):
        return [inline]
    return [f"{k}:"] + [f"  - {x}" for x in items]


def set_fields(text: str, updates: dict[str, Any]) -> str:
    """`text` with these frontmatter keys replaced (or appended before the closing `---`), every
    other line kept byte for byte. A value of None removes the key."""
    fm, rest = split(text)
    if fm is None:
        raise ParseError("no YAML frontmatter")
    lines = fm.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    spans: dict[str, tuple[int, int]] = {}
    i = 0
    while i < len(lines):
        m = KEY_RE.match(lines[i])
        if not m:
            i += 1
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].startswith((" ", "\t"))):
            j += 1
        spans[m.group(1)] = (i, j)
        i = j
    for k in sorted((k for k in updates if k in spans), key=lambda k: -spans[k][0]):
        a, b = spans[k]
        lines[a:b] = [] if updates[k] is None else _emit_value(k, updates[k])
    for k, v in updates.items():
        if k not in spans and v is not None:
            lines += _emit_value(k, v)
    nl = "\r\n" if text.startswith("---\r\n") else "\n"
    return f"---{nl}" + nl.join(lines) + f"{nl}---{nl}" + rest


# ---------------------------------------------------------------- decisions in frontmatter and body

def parse_decision(s: Any) -> dict[str, Any] | None:
    """`D2 retired by ADR-0007 D1 — superseded by the queue rework` → {id, state, by, note}."""
    m = DECISION_RE.match(str(s).strip())
    if not m:
        return None
    return {"id": m.group(1), "state": m.group(2), "by": (m.group(3) or "").strip() or None,
            "note": (m.group(4) or "").strip() or None}


def format_decision(d: dict[str, Any]) -> str:
    return f"D{d['id']} {d['state']}" + (f" by {d['by']}" if d.get("by") else "") + (f" — {d['note']}" if d.get("note") else "")


def _dec_key(ident: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([a-z]?)$", ident)
    return (int(m.group(1)), m.group(2)) if m else (10 ** 9, ident)


def body_decisions(body: str) -> list[dict[str, Any]]:
    """The body's decisions in file order, each at the occurrence `decision_block` reads (a heading
    first, else the first marker): {id, line, start, canonical}. Later reuses of an id are not
    decisions (an implementation note or an acceptance list numbered the same way)."""
    head: dict[str, re.Match[str]] = {}
    mark: dict[str, re.Match[str]] = {}
    fenced = False
    pos = 0
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith(FENCES):
            fenced = not fenced
        elif not fenced:
            m = _DEC_ANY.match(line)
            if m:
                ident = next(g for g in m.groups()[1:] if g)
                (head if m.group(1) else mark).setdefault(ident, (pos, line.rstrip("\n")))  # type: ignore[arg-type]
        pos += len(line)
    out = []
    for ident in set(head) | set(mark):
        start, line = head.get(ident) or mark[ident]  # type: ignore[misc]
        out.append({"id": ident, "start": start, "line": line, "canonical": bool(CANONICAL_RE.match(line))})
    return sorted(out, key=lambda d: d["start"])


def canonical_heading_counts(body: str) -> dict[str, int]:
    """How many `### Dn.` headings each id has (outside code fences)."""
    counts: dict[str, int] = {}
    fenced = False
    for line in body.splitlines():
        if line.lstrip().startswith(FENCES):
            fenced = not fenced
        elif not fenced and (m := CANONICAL_RE.match(line)):
            counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return counts


_MARK_PARTS = re.compile(r"^(?:[-*][ \t]+)?(?P<b1>\*\*)?D(?P<id>\d+[a-z]?)(?:[ \t]*\((?P<note>[^)\n]{0,40})\))?"
                         r"[ \t]*(?:[.:]|—|–|-)?[ \t]*(?P<b2>\*\*)?[ \t]*(?:[.:]|—|–)?[ \t]*(?P<rest>.*)$")
_HEAD_PARTS = re.compile(r"^#+[ \t]+D(?P<id>\d+[a-z]?)\b(?:[ \t]*\((?P<note>[^)\n]{0,40})\))?[ \t]*(?:[.:]|—|–|-)?[ \t]*(?P<rest>.*)$")


def _lift(inner: str, after: str) -> bool:
    """A bold run is a title only when it closes on its line and ends a sentence there: its text ends
    in `.` or `:`, or nothing follows it."""
    return inner.rstrip().endswith((".", ":")) or not after.strip()


def canonical_marker(line: str) -> tuple[str, str]:
    """A decision's marker line in the canonical form: (`### Dn. Title`, the text that follows on the
    line, or ""). A title is lifted only from a bold run that closes on the line and ends a sentence
    (`- **D1. Title.** body`, `**D4 — Lead**`); otherwise the heading is `### Dn.` and the line's text
    (bold kept, balanced) follows as the first body line, so no word moves and none is lost."""
    m = _HEAD_PARTS.match(line)
    if m:
        title, body = m.group("rest").replace("**", "").strip(), ""
    else:
        m = _MARK_PARTS.match(line)
        if not m:
            raise ValueError(f"not a decision line: {line[:60]!r}")
        rest = m.group("rest")
        bold_open = bool(m.group("b1")) != bool(m.group("b2"))   # a bold run the marker opened
        title, body = "", rest
        if bold_open:
            i = rest.find("**")
            if i >= 0 and _lift(rest[:i], rest[i + 2:]):
                title, body = rest[:i], rest[i + 2:]
            else:
                body = "**" + rest                # the run continues (on this line or the next): keep it
    title = re.sub(r"[ \t.:]+$", "", title.replace("**", "").strip())
    note = f" ({m.group('note').strip()})" if m.group("note") else ""
    head = f"### D{m.group('id')}." + (f" {title}" if title else "") + note
    return head, body.strip()


def _in_mixed_list(lines: list[str], i: int) -> bool:
    """Whether line i is an item of a bullet list whose other items are not decisions (an amendment's
    list of findings with one decision among them): such a marker is left for a person."""
    ind = len(lines[i]) - len(lines[i].lstrip())
    if not lines[i].lstrip().startswith(("- ", "* ")):
        return False
    j = i - 1
    while j >= 0 and lines[j].strip():
        j -= 1
    k = i + 1
    while k < len(lines) and lines[k].strip():
        k += 1
    for ln in lines[j + 1:k]:
        if len(ln) - len(ln.lstrip()) == ind and ln.lstrip().startswith(("- ", "* ")) and not _DEC_ANY.match(ln):
            return True
    return False


def migrate_markers_text(text: str) -> tuple[str, int, list[str]]:
    """`text` with each decision (at the occurrence `decision_block` reads) in the canonical
    `### Dn. Title` form; the text its marker line also carried follows as a paragraph. A decision
    that is one item of a list of other things is left alone and named. Returns the text, how many
    markers changed, and the decisions left."""
    fm, body = split(text)
    head = text[: len(text) - len(body)]
    lines = body.splitlines(keepends=True)
    starts, pos = {}, 0
    for i, ln in enumerate(lines):
        starts[pos] = i
        pos += len(ln)
    changed, left = 0, []
    for d in sorted(body_decisions(body), key=lambda d: -d["start"]):
        if d["canonical"]:
            continue
        i = starts[d["start"]]
        if _in_mixed_list([ln.rstrip("\r\n") for ln in lines], i):
            left.append(f"D{d['id']}")
            continue
        nl = "\r\n" if lines[i].endswith("\r\n") else "\n"
        heading, rest = canonical_marker(lines[i].rstrip("\r\n"))
        new = [heading + nl] + ([nl, rest + nl] if rest else [])
        if i > 0 and lines[i - 1].strip():
            new = [nl] + new
        lines[i:i + 1] = new
        changed += 1
    return head + "".join(lines), changed, sorted(left, key=lambda x: _dec_key(x[1:]))


# ---------------------------------------------------------------- the product's ADRs

def read(f: Path, errors: str = "strict") -> str:
    """A file's text with its line endings as written (a CRLF ADR stays CRLF)."""
    return f.read_bytes().decode("utf-8", errors=errors)


def write(f: Path, text: str) -> None:
    with open(f, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def adr_dir(cfg: Config, override: str | None = None) -> Path:
    return cfg.root / (override or ((cfg.adr or {}).get("dir")) or "docs/adr")


def files(d: Path, ids: refs.Ids = refs.DEFAULT) -> list[Path]:
    """ADR files under d, subdirectories (an archive) included: `NNNN-slug.md` or `<prefix>NNNN-slug.md`."""
    if not d.is_dir():
        return []
    rx = ids.adr_file_re
    return sorted((f for f in d.rglob("*.md") if rx.match(f.name)),
                  key=lambda f: (int(rx.match(f.name).group(1)), str(f)))


def _as_list(v: Any) -> list[str]:
    return [str(x) for x in v] if isinstance(v, list) else ([] if v in (None, "") else [str(v)])


def _settings(cfg: Config) -> dict[str, Any]:
    return cfg.adr or ADR_DEFAULTS


def load(cfg: Config, override: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Every ADR's frontmatter (with `_path`, `_number`, `_archived`, `_body`, `_decisions`), and what
    is wrong with each file on its own."""
    d = adr_dir(cfg, override)
    out: list[dict[str, Any]] = []
    errs: list[str] = []
    statuses = _settings(cfg).get("statuses") or ADR_DEFAULTS["statuses"]
    register = reviewpoints.load(cfg)[0]
    seen: dict[int, str] = {}
    ids = refs.ids(cfg)
    for f in files(d, ids):
        rel = cfg.rel(f)
        num = int(ids.adr_file_re.match(f.name).group(1))
        if num in seen:
            errs.append(f"{rel}: {ids.adr_id(num)} is also {seen[num]}")
        seen[num] = rel
        try:
            fm, body = split(read(f, errors="replace"))
            if fm is None:
                errs.append(f"{rel}: no YAML frontmatter (SPEC §6.2; `ccp adr new` writes one)")
                continue
            meta = parse(fm)
        except ParseError as e:
            errs.append(f"{rel}: frontmatter: {e}")
            continue
        meta.update(_path=rel, _number=num, _archived=f.parent != d, _body=body, _decisions=body_decisions(body))
        for k in REQUIRED:
            if not str(meta.get(k) or "").strip():
                errs.append(f"{rel}: frontmatter is missing `{k}`")
        if meta.get("id") and meta["id"] != ids.adr_id(num):
            errs.append(f"{rel}: id {meta['id']!r} does not match the file's number ({ids.adr_id(num)})")
        if meta.get("status") and meta["status"] not in statuses:
            errs.append(f"{rel}: status {meta['status']!r} is not one of {', '.join(statuses)} (adr.statuses)")
        if meta.get("date") and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(meta["date"])):
            errs.append(f"{rel}: date {meta['date']!r} is not YYYY-MM-DD")
        if meta.get("status") == "superseded" and not _as_list(meta.get("superseded_by")):
            errs.append(f"{rel}: status superseded needs `superseded_by: {ids.adr_prefix}NNNN`")
        for k in LIST_KEYS:
            if k in meta and k not in LINK_KEYS and not isinstance(meta[k], list) and meta[k] != "":
                errs.append(f"{rel}: `{k}` must be a list")
        for rp in meta.get("review_points") if isinstance(meta.get("review_points"), list) else []:
            if why := reviewpoints.problem(cfg, rp, register):  # §22: the points this ADR is built in
                errs.append(f"{rel}: review_points: {why}")
        out.append(meta)
    return out, errs


def _link(ids: refs.Ids, s: str) -> tuple[int, str | None] | None:
    """`ADR-0007` or `ADR-0007 D2` (or the bare number) → (7, "2"); anything else → None."""
    pre = re.escape(ids.adr_prefix.rstrip("-"))
    m = re.fullmatch(rf"\s*(?:{pre}-?)?0*(\d+)(?:\s+D(\d+[a-z]?))?\s*", str(s), re.I)
    return (int(m.group(1)), m.group(2)) if m else None


def analyse(cfg: Config) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """The ADRs, the errors and the warnings: each file on its own (`load`), then the links between
    ADRs, the decisions, the tasks that cite them and the index. Under `adr.strict` every warning
    here is an error."""
    from ccp import tasklog  # noqa: PLC0415  (tasklog imports this module's readers indirectly)

    adrs, errs = load(cfg)
    warns: list[str] = []
    strict = bool(_settings(cfg).get("strict"))
    soft = errs if strict else warns
    ids = refs.ids(cfg)
    by_num = {m["_number"]: m for m in adrs}

    def dec_ids(m: dict[str, Any]) -> set[str]:
        return {d["id"] for d in m["_decisions"]}

    def resolve(where: str, key: str, s: str) -> tuple[int, str | None] | None:
        ln = _link(ids, s)
        if ln is None:
            errs.append(f"{where}: {key} entry {s!r} is not `{ids.adr_prefix}NNNN` or `{ids.adr_prefix}NNNN Dn`")
            return None
        n, dec = ln
        if n not in by_num:
            errs.append(f"{where}: {key} {s!r} names no ADR")
            return None
        if dec and dec not in dec_ids(by_num[n]):
            errs.append(f"{where}: {key} {s!r}: {by_num[n]['_path']} has no decision D{dec}")
            return None
        return ln

    states: dict[tuple[int, str], dict[str, Any]] = {}
    for m in adrs:
        rel, me = m["_path"], m["_number"]
        unknown = sorted(k for k in m if not k.startswith("_") and k not in REQUIRED + OPTIONAL)
        if unknown:
            warns.append(f"{rel}: undeclared frontmatter key(s): {', '.join(unknown)} (SPEC §6; fold into `notes`)")
        # the body's decisions
        decs = m["_decisions"]
        bad = [d["id"] for d in decs if not d["canonical"]]
        if bad:
            soft.append(f"{rel}: decision(s) {', '.join('D' + x for x in bad)} not written `### Dn. Title` "
                        "(`ccp adr migrate --markers`)")
        dup = sorted(k for k, n in canonical_heading_counts(m["_body"]).items() if n > 1)
        if dup:
            soft.append(f"{rel}: more than one `### Dn.` heading for {', '.join('D' + x for x in dup)}")
        order = [_dec_key(d["id"]) for d in decs]
        if order != sorted(order):
            warns.append(f"{rel}: decisions are not in number order ({', '.join('D' + d['id'] for d in decs)})")
        # recorded decision states
        seen_ids: set[str] = set()
        for s in _as_list(m.get("decisions")):
            d = parse_decision(s)
            if d is None:
                errs.append(f"{rel}: decisions entry {s!r} is not `Dn <state>[ by {ids.adr_prefix}NNNN[ Dn]][ — note]`")
                continue
            if d["state"] not in STATES:
                errs.append(f"{rel}: decisions entry D{d['id']}: state {d['state']!r} is not one of {', '.join(STATES)}")
            if d["id"] in seen_ids:
                errs.append(f"{rel}: decisions lists D{d['id']} twice")
            seen_ids.add(d["id"])
            if d["id"] not in dec_ids(m):
                errs.append(f"{rel}: decisions entry D{d['id']}: the body has no decision D{d['id']}")
            if d["by"]:
                resolve(rel, f"decisions D{d['id']} by", d["by"])
            states[(me, d["id"])] = d
    # review points with no register to check them against (§22.3): a warning, under strict too
    tagged = [ids.adr_id(m["_number"]) for m in adrs if _as_list(m.get("review_points"))]
    if tagged and reviewpoints.load(cfg)[0] is None:
        warns.append(f"no review-point register: {cfg.rel(reviewpoints.path(cfg))}; the review points of "
                     f"{', '.join(tagged)} are unchecked — create it (SPEC §22.3)")

    # links and their reverse: a whole-ADR link is answered only by a whole-ADR link
    def names_whole(other: dict[str, Any], key: str, n: int) -> bool:
        return any(_link(ids, x) == (n, None) for x in _as_list(other.get(key)))

    for m in adrs:
        rel, me = m["_path"], m["_number"]
        mine = ids.adr_id(me)
        for key in LINK_KEYS:
            v = m.get(key)
            if isinstance(v, str) and v and _link(ids, v) is None:  # prose written before links were defined
                soft.append(f"{rel}: `{key}` holds prose, not a list of `{ids.adr_prefix}NNNN[ Dn]`; move the "
                            "prose into `notes` and list the links")
                continue
            for s in _as_list(v):
                ln = resolve(rel, key, s)
                if ln is None:
                    continue
                n, dec = ln
                other = by_num[n]
                if key == "superseded_by" and dec is None and not names_whole(other, "supersedes", me):
                    soft.append(f"{rel}: superseded_by {s!r}, but {other['_path']} does not list {mine} in `supersedes`")
                elif key == "supersedes" and dec is None:
                    if not names_whole(other, "superseded_by", me):
                        soft.append(f"{rel}: supersedes {s!r}, but {other['_path']} does not name {mine} in `superseded_by`")
                    if other.get("status") != "superseded":
                        soft.append(f"{rel}: supersedes {s!r}, whose status is {other.get('status')!r}, not superseded")
                elif key == "supersedes":
                    st = states.get((n, dec))
                    if st is None or st["state"] != "retired":
                        soft.append(f"{rel}: supersedes {s!r}, but {other['_path']} does not record D{dec} as retired")
    # the tasks that cite decisions
    try:
        tasks = tasklog.load(cfg)
    except OSError:
        tasks = []
    for t in tasks:
        tid = t.get("task_id") or t["_file"].stem
        for ref in tasklog._as_list(t.get("adr_refs")):
            r = ids.parse_adr_ref(ref)
            if r is None or r.decision is None:
                continue
            m = by_num.get(r.number)
            if m is None:
                errs.append(f"{tid}: adr_refs {ref!r} names no ADR in {cfg.rel(adr_dir(cfg))}")
                continue
            if r.decision not in dec_ids(m):
                errs.append(f"{tid}: adr_refs {ref!r}: {m['_path']} has no decision D{r.decision}")
                continue
            st = states.get((r.number, r.decision))
            if t.get("status") == "done" and not_in_force(st):
                soft.append(f"{tid}: done, and cites {ids.adr_id(r.number)} D{r.decision}, which {m['_path']} "
                            "records as not_built (`ccp adr decide` it built or live)")
    # the index
    if _settings(cfg).get("index"):
        p = cfg.root / _settings(cfg)["index"]
        if not p.is_file():
            errs.append(f"{cfg.rel(p)}: missing — run `ccp adr index`")
        elif p.read_text() != render_index(cfg, adrs):
            errs.append(f"{cfg.rel(p)}: stale — run `ccp adr index`")
    return adrs, errs, warns


def check(cfg: Config) -> list[str]:
    """`ccp docs check`'s ADR part, with the `adr` block on: the errors of `analyse`."""
    if cfg.adr is None:
        return []
    d = adr_dir(cfg)
    if not d.is_dir():
        return [f"{cfg.rel(d)}: missing (plane.json adr.dir)"]
    return analyse(cfg)[1]


def warnings(cfg: Config) -> list[str]:
    if cfg.adr is None or not adr_dir(cfg).is_dir():
        return []
    return analyse(cfg)[2]


def not_in_force(state: dict[str, Any] | None) -> bool:
    """§6.7 in force: a decision a done task cites must not be recorded `not_built`. One rule for the
    check (`analyse`) and for the verdict (`in_force_at`)."""
    return state is not None and state["state"] == "not_built"


def _at(cfg: Config, head: str, rel: str) -> str | None:
    r = subprocess.run(["git", "-C", str(cfg.root), "show", f"{head}:{rel}"], capture_output=True)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def in_force_at(cfg: Config, task: dict[str, Any], head: str) -> list[str]:
    """§6.7's in-force check run on a task's PR head before its verdict (§15.4): closing the task marks
    it done, so each decision its `adr_refs` cite that the head's ADRs record as `not_built` would fail
    the check on the integration branch. Read from the git objects at `head` in this checkout: the task
    file (the checkout's when the head has none) and the ADR files under `adr.dir`. One line per such
    decision, naming it and the `ccp adr decide` that flips it; nothing without `adr.strict` (the
    check only warns then) or when the task cites no decision. A head this checkout does not hold is
    refused when there is a decision to judge."""
    from ccp import tasklog  # noqa: PLC0415  (as in analyse)

    if cfg.adr is None or not _settings(cfg).get("strict"):
        return []
    ids = refs.ids(cfg)
    tid = str(task.get("task_id") or task["_file"].stem)
    rel = cfg.rel(task["_file"])

    def cited(meta: dict[str, Any]) -> list[tuple[int, str]]:
        out = []
        for ref in tasklog._as_list(meta.get("adr_refs")):
            r = ids.parse_adr_ref(ref)
            if r is not None and r.decision is not None:
                out.append((r.number, r.decision))
        return out

    head = str(head or "").strip()
    resolved = subprocess.run(["git", "-C", str(cfg.root), "rev-parse", "--verify", "-q", f"{head}^{{commit}}"],
                              capture_output=True, text=True) if head else None
    if resolved is None or resolved.returncode != 0:
        if not cited(task):
            return []
        return [f"{tid} cites ADR decisions, and the PR head {head[:12] or '(none)'} is not in this checkout "
                "(git fetch it): the in-force ADR check (SPEC §6.7) runs on the head before an approve"]
    head = resolved.stdout.strip()
    text = _at(cfg, head, rel)
    decisions = cited(tasklog.frontmatter(text.replace("\r\n", "\n")) if text is not None else task)
    if not decisions:
        return []
    d = cfg.rel(adr_dir(cfg))
    listed = subprocess.run(["git", "-C", str(cfg.root), "ls-tree", "-r", "--name-only", head, "--", d],
                            capture_output=True, text=True)
    by_num: dict[int, str] = {}
    for name in sorted(listed.stdout.splitlines()) if listed.returncode == 0 else []:
        m = ids.adr_file_re.match(Path(name).name)
        if m:
            by_num.setdefault(int(m.group(1)), name)
    errs: list[str] = []
    for n, dec in decisions:
        path = by_num.get(n)
        body = _at(cfg, head, path) if path else None
        try:
            fm = split(body)[0] if body is not None else None
            meta = parse(fm) if fm is not None else {}
        except ParseError:
            meta = {}  # `ccp adr check` names an unreadable frontmatter; the gate runs it
        states = {x["id"]: x for x in (parse_decision(s) for s in _as_list(meta.get("decisions"))) if x}
        if not_in_force(states.get(dec)):
            errs.append(f"{tid} cites {ids.adr_id(n)} D{dec}, which {path} records as not_built at the PR head "
                        f"{head[:12]}: closing the task marks it done, and the in-force ADR check (SPEC §6.7, "
                        f"adr.strict) then fails on the integration branch; flip it on the PR head: "
                        f"`ccp adr decide {n} D{dec} built` (or live)")
    return errs


def _cell(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).replace("|", "\\|").strip()


def render_index(cfg: Config, adrs: list[dict[str, Any]] | None = None) -> str:
    """The ADR index (`adr.index`): one row per ADR, from its frontmatter only, so it changes only
    when an ADR does. No date of its own (git has it), as INDEX.yaml."""
    adrs = adrs if adrs is not None else load(cfg)[0]
    idx = cfg.root / _settings(cfg)["index"]
    # §22.4: the review-point column appears once an ADR names its points, so an index written
    # before the field existed stays current.
    rps = any(isinstance(m.get("review_points"), list) and m["review_points"] for m in adrs)
    lines = ["<!-- Generated by `ccp adr index` from each ADR's frontmatter. Do not hand-edit. -->",
             "", "# ADR index", "", "| ADR | Title | Status | Date | Superseded by |" + (" Review points |" if rps else ""),
             "|---|---|---|---|---|" + ("---|" if rps else "")]
    for m in adrs:
        link = Path(os.path.relpath(cfg.root / m["_path"], idx.parent))
        status = _cell(m.get("status")) + (" (archived)" if m.get("_archived") else "")
        pts = m.get("review_points") if isinstance(m.get("review_points"), list) else []
        lines.append(f"| [{_cell(m.get('id'))}]({link.as_posix()}) | {_cell(m.get('title'))} | {status} | "
                     f"{_cell(m.get('date'))} | {_cell(', '.join(_as_list(m.get('superseded_by'))))} |"
                     + (f" {_cell(', '.join(map(str, pts)))} |" if rps else ""))
    return "\n".join(lines) + "\n"


def write_index(cfg: Config) -> str:
    if not cfg.adr or not cfg.adr.get("index"):
        return "(no ADR index: plane.json adr.index is not set)"
    p = cfg.root / cfg.adr["index"]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(render_index(cfg))
    return cfg.rel(p)


def public(m: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in m.items() if not k.startswith("_")} | {"path": m.get("_path"), "archived": m.get("_archived")}
    out["body_decisions"] = [d["id"] for d in m.get("_decisions") or []]
    return out


def built(m: dict[str, Any]) -> tuple[int, int] | None:
    """(built or live, decisions not retired) when the ADR records any state; a body decision with
    no recorded state counts as not built. None when it records none."""
    states = decision_states(m)
    if not any(d["state"] for d in states):
        return None
    standing = [d for d in states if d["state"] != "retired"]
    return sum(d["state"] in ("built", "live") for d in standing), len(standing)


def decision_states(m: dict[str, Any]) -> list[dict[str, Any]]:
    """The recorded states, in the body's order, each body decision once (`state` None when the ADR
    records none for it)."""
    rec = {d["id"]: d for d in (parse_decision(s) for s in _as_list(m.get("decisions"))) if d}
    return [rec.get(d["id"]) or {"id": d["id"], "state": None, "by": None, "note": None} for d in m.get("_decisions") or []]


# ---------------------------------------------------------------- commands

class AdrError(Exception):
    def __init__(self, msg: str, code: int = 2) -> None:
        super().__init__(msg)
        self.code = code


def _find(cfg: Config, arg: str) -> tuple[Path, dict[str, Any]]:
    ids = refs.ids(cfg)
    n = ids.adr_number(arg)
    if n is None and re.fullmatch(r"\d+", str(arg).strip()):
        n = int(arg)
    f = find_file(cfg, n) if n is not None else None
    if f is None:
        raise AdrError(f"no ADR {arg!r} in {cfg.rel(adr_dir(cfg))}")
    text = read(f)
    fm, body = split(text)
    if fm is None:
        raise AdrError(f"{cfg.rel(f)}: no YAML frontmatter")
    meta = parse(fm)
    meta.update(_path=cfg.rel(f), _number=n, _body=body, _decisions=body_decisions(body))
    return f, meta


def _today() -> str:
    return date.today().isoformat()


def _note(meta: dict[str, Any], line: str) -> str:
    old = str(meta.get("notes") or "").rstrip("\n")
    return (old + "\n" if old else "") + f"{_today()}: {line}"


def _slug(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return "-".join(s.split("-")[:8]) or "decision"


TEMPLATE = """---
id: {id}
title: {title_q}
status: proposed
date: "{date}"
deciders: ""
---
# {id} — {title}

## Context

What forces the decision: the problem, the constraints, what was tried.

## Decision

### D1. The first decision

What is decided, and its boundaries.

## Consequences

What follows, good and bad; what this rules out.
"""


def new(cfg: Config, title: str) -> Path:
    if not title.strip():
        raise AdrError("give the ADR a title")
    d = adr_dir(cfg)
    ids = refs.ids(cfg)
    nums = [int(ids.adr_file_re.match(f.name).group(1)) for f in files(d, ids)]
    n = max(nums, default=0) + 1
    tmpl_path = _settings(cfg).get("template")
    tmpl = (cfg.root / tmpl_path).read_text() if tmpl_path else TEMPLATE
    width = ids.adr_width
    f = d / f"{n:0{width}d}-{_slug(title)}.md"
    text = tmpl.format(id=ids.adr_id(n), title=title.strip(), title_q=_quote(title.strip()), date=_today())
    d.mkdir(parents=True, exist_ok=True)
    f.write_text(text)
    _reindex(cfg)
    return f


def _write(f: Path, updates: dict[str, Any]) -> None:
    write(f, set_fields(read(f), updates))


def _reindex(cfg: Config) -> None:
    if cfg.adr and cfg.adr.get("index"):
        write_index(cfg)


def _transition(cfg: Config, meta: dict[str, Any], to: str) -> None:
    statuses = _settings(cfg).get("statuses") or ADR_DEFAULTS["statuses"]
    if to not in statuses:
        raise AdrError(f"{to!r} is not one of {', '.join(statuses)} (adr.statuses)")
    frm = str(meta.get("status") or "")
    allowed = (_settings(cfg).get("transitions") or ADR_DEFAULTS["transitions"]).get(frm, [])
    if to not in allowed:
        raise AdrError(f"{meta['_path']}: {frm or '(none)'} → {to} is not allowed "
                       f"(adr.transitions: {frm or '(none)'} → {', '.join(allowed) or 'nothing'})", 1)


def set_status(cfg: Config, arg: str, to: str, note: str | None = None) -> dict[str, Any]:
    f, meta = _find(cfg, arg)
    if to == "superseded":
        raise AdrError("use `ccp adr supersede OLD NEW`: it links both ADRs")
    _transition(cfg, meta, to)
    upd: dict[str, Any] = {"status": to}
    states = [d for d in (parse_decision(s) for s in _as_list(meta.get("decisions"))) if d]
    if to == "accepted" and meta["_decisions"]:
        have = {d["id"]: d for d in states}
        if any(d["id"] not in have for d in meta["_decisions"]):
            upd["decisions"] = [format_decision(have.get(d["id"]) or {"id": d["id"], "state": "not_built"})
                                for d in meta["_decisions"]]
    if to == "retired":
        have = {d["id"]: d for d in states}
        upd["decisions"] = [format_decision({**have.get(d["id"], {"id": d["id"]}), "state": "retired"})
                            for d in meta["_decisions"]]
    upd["notes"] = _note(meta, f"status {meta.get('status')} → {to}" + (f": {note}" if note else ""))
    _write(f, upd)
    _reindex(cfg)
    return {"path": meta["_path"], "status": to, "decisions": upd.get("decisions")}


def decide(cfg: Config, arg: str, dec: str, state: str, by: str | None = None, note: str | None = None) -> dict[str, Any]:
    f, meta = _find(cfg, arg)
    ident = dec[1:] if dec.upper().startswith("D") else dec
    if ident not in {d["id"] for d in meta["_decisions"]}:
        raise AdrError(f"{meta['_path']} has no decision D{ident}")
    if state not in STATES:
        raise AdrError(f"{state!r} is not one of {', '.join(STATES)}")
    if by:
        ids = refs.ids(cfg)
        ln = _link(ids, by)
        target = find_file(cfg, ln[0]) if ln else None
        if target is None:
            raise AdrError(f"--by {by!r} is not an existing `{ids.adr_prefix}NNNN[ Dn]`")
        if ln[1] and ln[1] not in {d["id"] for d in body_decisions(split(read(target))[1])}:
            raise AdrError(f"--by {by!r}: {cfg.rel(target)} has no decision D{ln[1]}")
    entries = [d for d in (parse_decision(s) for s in _as_list(meta.get("decisions"))) if d]
    have = {d["id"]: d for d in entries}
    have[ident] = {"id": ident, "state": state, "by": by, "note": note}
    order = [d["id"] for d in meta["_decisions"]]
    out = [format_decision(have[i]) for i in order if i in have]
    _write(f, {"decisions": out})
    return {"path": meta["_path"], "decision": f"D{ident}", "state": state}


def supersede(cfg: Config, old: str, new_: str, decisions: list[str] | None = None, by: str | None = None,
              archive: bool = False) -> dict[str, Any]:
    ids = refs.ids(cfg)
    fo, mo = _find(cfg, old)
    fn, mn = _find(cfg, new_)
    if mo["_number"] == mn["_number"]:
        raise AdrError("an ADR cannot supersede itself")
    if archive and decisions:
        raise AdrError("--archive moves a superseded ADR; superseding some of its decisions keeps it in force")
    new_id, old_id = ids.adr_id(mn["_number"]), ids.adr_id(mo["_number"])
    by_ref = f"{new_id} D{by.lstrip('Dd')}" if by else new_id
    if by and by.lstrip("Dd") not in {d["id"] for d in mn["_decisions"]}:
        raise AdrError(f"{mn['_path']} has no decision {by}")
    entries = {d["id"]: d for d in (parse_decision(s) for s in _as_list(mo.get("decisions"))) if d}
    body_ids = [d["id"] for d in mo["_decisions"]]
    if decisions:
        want = [x.strip().lstrip("Dd") for x in decisions if x.strip()]
        missing = [x for x in want if x not in body_ids]
        if missing:
            raise AdrError(f"{mo['_path']} has no decision(s) {', '.join('D' + x for x in missing)}")
        for x in want:
            entries[x] = {**entries.get(x, {"id": x}), "state": "retired", "by": by_ref, "note": entries.get(x, {}).get("note")}
        sup = [f"{old_id} D{x}" for x in want]
        upd_old: dict[str, Any] = {"decisions": [format_decision(entries[i]) for i in body_ids if i in entries],
                                   "notes": _note(mo, f"D{', D'.join(want)} superseded by {by_ref}")}
    else:
        _transition(cfg, mo, "superseded")
        for x in body_ids:
            entries[x] = {**entries.get(x, {"id": x}), "state": "retired", "by": entries.get(x, {}).get("by") or by_ref,
                          "note": entries.get(x, {}).get("note")}
        sup = [old_id]
        upd_old = {"status": "superseded",
                   "superseded_by": list(dict.fromkeys(_as_list(mo.get("superseded_by")) + [new_id])),
                   "notes": _note(mo, f"superseded by {new_id}")}
        if body_ids:
            upd_old["decisions"] = [format_decision(entries[i]) for i in body_ids]
    _write(fo, upd_old)
    _write(fn, {"supersedes": list(dict.fromkeys(_as_list(mn.get("supersedes")) + sup))})
    moved = None
    if archive:
        dest = adr_dir(cfg) / "archive" / fo.name
        if fo.parent != dest.parent:
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "-C", str(cfg.root), "mv", str(fo), str(dest)], capture_output=True, text=True)
            if r.returncode != 0:
                shutil.move(str(fo), str(dest))
            moved = cfg.rel(dest)
    _reindex(cfg)
    return {"old": mo["_path"], "new": mn["_path"], "supersedes": sup, "archived_to": moved}


def migrate_markers(cfg: Config, dry_run: bool = False) -> dict[str, Any]:
    rows = []
    for f in files(adr_dir(cfg), refs.ids(cfg)):
        text = read(f)
        try:
            new_text, n, left = migrate_markers_text(text)
        except (ParseError, ValueError) as e:
            rows.append({"path": cfg.rel(f), "changed": 0, "left": [], "error": str(e)})
            continue
        if n and not dry_run:
            write(f, new_text)
        rows.append({"path": cfg.rel(f), "changed": n, "left": left})
    return {"files": rows, "changed_files": sum(1 for r in rows if r["changed"]),
            "changed_lines": sum(r["changed"] for r in rows), "errors": [r for r in rows if r.get("error")],
            "left": [(r["path"], x) for r in rows for x in r["left"]]}


# ---------------------------------------------------------------- decisions and lookup

# A numbered decision opens a line in one of the styles ADRs use: a heading (`### D1. Title`), a bold
# bullet (`- **D1. Title.** body`), a bold lead (`**D1 — Title**`, `**D1**`) or a plain paragraph
# (`D1. **Title**`), optionally with a bracketed note after the id (`- **D5 (F01). Title.**`). Ids may
# carry a letter suffix (`D2a`).
_DEC_HEAD = r"^(#+)[ \t]+D({id})\b"
_DEC_MARK = r"^(?:[-*][ \t]+)?(?:\*\*)?D({id})(?:[ \t]*\([^)\n]{{0,40}}\))?(?:\*\*)?(?:[ \t]*(?:[.:]|—|–)|\*\*|[ \t]+-[ \t])"
_DEC_ANY = re.compile("|".join(p.format(id=r"\d+[a-z]?") for p in (_DEC_HEAD, _DEC_MARK)), re.M)


def find_file(cfg: Config, n: int) -> Path | None:
    """ADR number `n`'s file: at the top of the binding's `adr.dir` (default docs/adr), then in its
    subdirectories (an archive), else in any `adr/` directory in the product."""
    d = cfg.root / str((cfg.adr or {}).get("dir") or ADR_DEFAULTS["dir"])
    pats = refs.ids(cfg).adr_globs(n)
    places = [(d, ""), (d, "*/**/")] if d.is_dir() else []
    places.append((cfg.root, "**/adr/"))
    for base, prefix in places:
        for pat in pats:
            hits = sorted(p for p in base.glob(prefix + pat) if ".git" not in p.parts)
            if hits:
                return hits[0]
    return None


def decision_block(text: str, dec: str) -> str | None:
    """The text of decision `dec` (`1`, `2a`), in whichever style the ADR writes it: under a heading,
    up to the next heading of its level or higher; otherwise up to the next decision or heading."""
    ident = re.escape(dec)
    m = re.search(_DEC_HEAD.format(id=ident), text, re.M)
    if m:
        level = len(m.group(1))
        nxt = re.search(rf"^#{{1,{level}}}[ \t]", text[m.end():], re.M)
        return text[m.start():m.end() + nxt.start() if nxt else len(text)]
    m = re.search(_DEC_MARK.format(id=ident), text, re.M)
    if not m:
        return None
    end, pos, fenced = len(text), m.end(), False
    for line in text[m.end():].splitlines(keepends=True):
        if pos > m.end() and not fenced and (line.startswith("#") or _DEC_ANY.match(line)):
            end = pos
            break
        if line.lstrip().startswith(FENCES):
            fenced = not fenced
        pos += len(line)
    return text[m.start():end]


def decision_titles(text: str) -> list[str]:
    """Each decision's opening line, markup stripped, in file order; an id listed once (its first
    occurrence, as decision_block reads it), so later sections reusing the ids add nothing."""
    out, seen = [], set()
    for m in _DEC_ANY.finditer(text):
        ident = next(g for g in m.groups()[1:] if g) if m.lastindex else ""
        if ident in seen:
            continue
        seen.add(ident)
        line = text[m.start():text.find("\n", m.start()) if "\n" in text[m.start():] else len(text)]
        out.append(re.sub(r"^(?:#+|[-*])[ \t]+|\*\*", "", line).strip()[:160])
    return out
