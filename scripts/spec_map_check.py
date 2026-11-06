#!/usr/bin/env python3
"""Checks for the SPEC restructure (ADR-0033): the old → new map in docs/spec/map/ against the old
SPEC.md and the new part files.

  spec_map_check.py coverage [--spec FILE]   every ##–#### heading of the old SPEC has a map row
  spec_map_check.py part NN [--spec FILE]     a part task's map file is refined and complete:
      (a) every target in the part's range is §N.M and that heading exists in the part file;
      (b) no bare §N target is left in the range;
      (c) every backticked token of the mapped source sections appears in docs/spec/, docs/design/
          or docs/cli/, or is listed under the map file's "Dropped tokens";
      (d) every row marked `operator (obsolete?)` is listed in docs/spec/RULINGS.md.
  spec_map_check.py refs FILE...              every §N[.M…] reference in FILEs names a heading of
      docs/spec/ (for the switch task, after references are rewritten), and every `spec_refs` entry
      of an ADR or task names an existing top-level section (`S<n>`). A record of the restructure
      itself (its map, MAP.md, RULINGS.md, tasks 0001–0008, ADR-0033) names pre-restructure sections
      on purpose: it is skipped when it is on that list **and** carries the marker as a line of its
      own.

Exit 0 when clean, 1 with one line per problem. Run from the repo root.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PARTS = {"01": ("01-model", 1, 9), "02": ("02-delivery", 10, 18), "03": ("03-quality", 19, 22),
         "04": ("04-observability", 23, 28), "05": ("05-operations", 29, 31)}
HEAD_RE = re.compile(r"^(#{2,4}) (.*)$")
NUM_RE = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")
ROW_RE = re.compile(r"^\| (§[^|]+?) \| [^|]* \| ([^|]*) \|")
TICK_RE = re.compile(r"`([^`\n]{2,80})`")
HISTORICAL = "<!-- spec-refs: historical -->"
HISTORICAL_PATHS = re.compile(r"^(docs/spec/map/[^/]+\.md|docs/spec/MAP\.md|docs/spec/RULINGS\.md|"
                              r"docs/delivery/tasks/000[1-8]-[^/]+\.md|docs/adr/0033-[^/]+\.md)$")
SPEC_REFS_RE = re.compile(r"^spec_refs:\s*\[(.*)\]\s*$", re.M)


def historical(path: str, text: str) -> bool:
    return bool(HISTORICAL_PATHS.match(path)) and HISTORICAL in text.splitlines()


def old_sections(spec: Path) -> dict[str, tuple[int, int]]:
    """Old section id (`20.1.5`, `5/Write rules`) → its [start, end) line range in the old SPEC."""
    lines = spec.read_text().splitlines()
    heads, top = [], None
    for i, line in enumerate(lines):
        m = HEAD_RE.match(line)
        if not m:
            continue
        text = m.group(2).strip()
        n = NUM_RE.match(text)
        if n and m.group(1) == "##":
            top = key = n.group(1)
        elif n:
            key = n.group(1)
        else:
            key = f"{top}/{text}"
        heads.append((key, i))
    return {k: (start, heads[j + 1][1] if j + 1 < len(heads) else len(lines))
            for j, (k, start) in enumerate(heads)}


def map_rows(path: Path) -> list[tuple[str, str]]:
    """(old id, targets cell) per table row of a map file."""
    out = []
    for line in path.read_text().splitlines():
        m = ROW_RE.match(line)
        if m and not m.group(1).startswith("Old"):
            out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def coverage(spec: Path) -> list[str]:
    secs = old_sections(spec)
    mapped = set()
    for f in Path("docs/spec/map").glob("*.md"):
        for old, _ in map_rows(f):
            s = old.lstrip("§")
            num, _, rest = s.partition(" — ")
            mapped.add(num)
            if rest:
                mapped.add(f"{num}/{rest}")
    return [f"unmapped old heading: §{k}" for k in secs if k not in mapped and k.split("/")[0] not in mapped]


def part(nn: str, spec: Path) -> list[str]:
    name, lo, hi = PARTS[nn]
    errs = []
    part_text = Path(f"docs/spec/{name}.md").read_text()
    have = set(re.findall(r"^#{2,4} (\d+(?:\.\d+)+)\.?\s", part_text, re.M))
    map_file = Path(f"docs/spec/map/{name}.md")
    rows = map_rows(map_file)
    for old, targets in rows:
        for t in re.findall(r"§(\d+(?:\.\d+)*)", targets):
            n = int(t.split(".")[0])
            if not lo <= n <= hi:
                continue
            if "." not in t:
                errs.append(f"{old}: target §{t} is not refined to §N.M")
            elif t not in have:
                errs.append(f"{old}: target §{t} has no heading in docs/spec/{name}.md")
    # (c) backticked tokens of the source sections
    secs = old_sections(spec)
    lines = spec.read_text().splitlines()
    dropped_line = next((ln for ln in map_file.read_text().splitlines() if ln.startswith("Dropped tokens")), "")
    dropped = set(TICK_RE.findall(dropped_line))
    corpus = "\n".join(p.read_text() for d in ("docs/spec", "docs/design", "docs/cli")
                       for p in Path(d).rglob("*.md") if "map" not in p.parts)
    corpus += Path("docs/cli.md").read_text() if Path("docs/cli.md").exists() else ""
    seen = set()
    for old, targets in rows:
        if all(x.strip().startswith(("dropped", "operator")) for x in targets.split(",")):
            continue
        num, _, rest = old.lstrip("§").partition(" — ")
        rng = secs.get(f"{num}/{rest}") or secs.get(num)
        if not rng:
            continue
        for tok in TICK_RE.findall("\n".join(lines[rng[0]:rng[1]])):
            if tok in seen or tok in dropped:
                continue
            seen.add(tok)
            if tok not in corpus:
                errs.append(f"{old}: `{tok}` appears in no part, design note or command file (or list it under Dropped tokens)")
    # (d) operator rows listed in RULINGS.md
    rulings = Path("docs/spec/RULINGS.md").read_text()
    for old, targets in rows:
        if "operator" in targets and old.split(" — ")[0] not in rulings:
            errs.append(f"{old}: marked operator (obsolete?) but not listed in docs/spec/RULINGS.md")
    return errs


def refs(files: list[str]) -> list[str]:
    have = set()
    for p in Path("docs/spec").glob("0*.md"):
        have |= set(re.findall(r"^#{2,4} (\d+(?:\.\d+)*)\.?\s", p.read_text(), re.M))
    tops = {h.split(".")[0] for h in have}
    errs = []
    for f in files:
        text = Path(f).read_text(errors="replace")
        if f.startswith(("docs/adr/", "docs/delivery/tasks/")):
            m = SPEC_REFS_RE.search(text)
            for s in re.findall(r"S(\d+)", m.group(1)) if m else []:
                if s not in tops:
                    errs.append(f"{f}: spec_refs S{s} names no top-level section of docs/spec/")
        if historical(f, text):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for r in re.findall(r"§(\d+(?:\.\d+)*)", line):
                if r not in have:
                    errs.append(f"{f}:{i}: §{r} names no heading in docs/spec/")
    return errs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mode", choices=("coverage", "part", "refs"))
    ap.add_argument("args", nargs="*")
    ap.add_argument("--spec", default="SPEC.md", help="the old SPEC (default SPEC.md)")
    a = ap.parse_args(argv)
    spec = Path(a.spec)
    if a.mode == "coverage":
        errs = coverage(spec)
    elif a.mode == "part":
        if len(a.args) != 1 or a.args[0] not in PARTS:
            ap.error("part takes one of " + ", ".join(PARTS))
        errs = part(a.args[0], spec)
    else:
        errs = refs(a.args)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
