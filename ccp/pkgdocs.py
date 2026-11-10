"""Package-doc coverage and drift, checked mechanically (SPEC §21).

Coverage rot is invisible: nothing points at the doc that was never written. So where a product
opts in (a `package_docs` block in `plane.json`), the rule is mechanical rather than a judgement.
The language-neutral core: every directory holding source carries a package doc, the doc opens
with a title, names no file that is gone, plans nothing, and stays shorter than a fraction of its
source. The language pack (`package_docs.language`, ccp/doclang) adds its source suffixes and
directory names, and its per-file checks over `docstring_globs` (Python: a module docstring that
says what the module does). Package docs and code comments name no delivery id (a task in the task
log, an architect finding, a spec question's ruling, or the product's own patterns): a package doc is
a map of what exists, and the task log is the record. Opt-in generic rules are ccp/docrules.py.
Staleness a rule cannot see is the architect's docs lens instead (`ccp architect`, §21.7).
"""
from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

from ccp import doclang, refs
from ccp.config import Config

# The core's own source suffixes and directory names; a language pack adds its own (ccp/doclang).
CORE_SUFFIXES = (".sql", ".json", ".md")
CORE_EXEMPT = (".git", ".idea", ".claude", "docs", "node_modules")


def pack(cfg: Config) -> doclang.Pack:
    return doclang.get(cfg.package_docs["language"])


def suffixes(cfg: Config) -> set[str]:
    given = cfg.package_docs["source_suffixes"]
    return set(given) if given is not None else {*CORE_SUFFIXES, *pack(cfg).source_suffixes}


def exempt_dirs(cfg: Config) -> set[str]:
    given = cfg.package_docs["exempt_dirs"]
    return set(given) if given is not None else {*CORE_EXEMPT, *pack(cfg).exempt_dirs}


def _ref_re(cfg: Config) -> re.Pattern[str]:
    exts = "|".join(re.escape(s.lstrip(".")) for s in cfg.package_docs["path_ref_suffixes"])
    return re.compile(rf"`([\w./-]+\.(?:{exts}))`")


def _exempt(cfg: Config, rel: Path, ex: set[str] | None = None) -> bool:
    ex = exempt_dirs(cfg) if ex is None else ex
    return any(part in ex for part in rel.parts) or str(rel) in ex


def _tracked_files(root: Path) -> list[Path] | None:
    """The files git tracks under `root`, or None when `root` is not in a git checkout."""
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", "."],
                           capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    return [root / Path(n.decode("utf-8", "surrogateescape")) for n in r.stdout.split(b"\0") if n]


def source_dirs(cfg: Config) -> list[Path]:
    """Directories below the product root that hold source the product owns. The root itself is
    not judged: its CLAUDE.md is the project brief, which names things in other repos."""
    pd = cfg.package_docs
    sfx, ex = suffixes(cfg), exempt_dirs(cfg)
    tracked = _tracked_files(cfg.root)
    if tracked is not None:   # a git checkout: only what is versioned (no caches, builds or scratch)
        dirs = {f.parent for f in tracked
                if f.suffix in sfx and f.name != pd["doc_name"] and not f.name.startswith(".")}
        return sorted(d for d in dirs if d != cfg.root and not _exempt(cfg, d.relative_to(cfg.root), ex))
    out = []
    for d in sorted(p for p in cfg.root.rglob("*") if p.is_dir()):
        rel = d.relative_to(cfg.root)
        if _exempt(cfg, rel, ex):
            continue
        if any(f.is_file() and f.suffix in sfx and f.name != pd["doc_name"]
               and not f.name.startswith(".") for f in d.iterdir()):
            out.append(d)
    return out


def doc_for(cfg: Config, d: Path) -> Path:
    rel = str(d.relative_to(cfg.root))
    return d / ("CLAUDE.md" if rel in cfg.package_docs["claude_md_dirs"] else cfg.package_docs["doc_name"])


def _source_lines(cfg: Config, d: Path) -> int:
    pd, sfx = cfg.package_docs, suffixes(cfg)
    return sum(len(f.read_text(errors="ignore").splitlines()) for f in d.iterdir()
               if f.is_file() and f.suffix in sfx and f.name != pd["doc_name"])


def core_check(cfg: Config) -> list[str]:
    """The language-neutral rules, 1–5."""
    pd = cfg.package_docs
    banned = re.compile(r"^#{1,4} .*\b(" + "|".join(re.escape(w) for w in pd["banned_headings"]) + r")\b",
                        re.I | re.M) if pd["banned_headings"] else None
    ref_re = _ref_re(cfg)
    errs: list[str] = []
    for d in source_dirs(cfg):
        rel = str(d.relative_to(cfg.root))
        doc = doc_for(cfg, d)
        # 1. coverage
        if not doc.exists():
            errs.append(f"{rel}: no {doc.name} (every source directory carries one)")
            continue
        text = doc.read_text()
        drel = cfg.rel(doc)
        # 2. template: opens with a title
        if not text.lstrip().startswith("# "):
            errs.append(f"{drel}: must open with a `# ` title")
        # 3. document what exists, not what is planned
        if banned:
            for m in banned.finditer(text):
                errs.append(f"{drel}: aspirational section {m.group(0)!r} — plans belong in the design record")
        # 4. proportionality
        src = _source_lines(cfg, d)
        n = len(text.splitlines())
        if src and n > pd["size_ratio"] * src:
            errs.append(f"{drel}: {n} lines against {src} of source — a map, not a transcript")
        # 5. no dead paths
        for ref in ref_re.findall(text):
            if ref in {pd["doc_name"], "CLAUDE.md"}:
                continue
            if not any(c.exists() for c in (cfg.root / ref, d / ref)):
                errs.append(f"{drel}: names `{ref}`, which does not exist")
    return errs


def _pack_files(cfg: Config) -> list[Path]:
    """The files under `docstring_globs` the language pack reads, once each, in glob order."""
    p = pack(cfg)
    out: list[Path] = []
    seen: set[Path] = set()
    for g in cfg.package_docs["docstring_globs"]:
        for f in sorted(cfg.root.glob(g)):
            if f in seen or not f.is_file() or f.suffix not in p.file_suffixes:
                continue
            if any(part in p.file_skip_dirs for part in f.parts):
                continue
            seen.add(f)
            out.append(f)
    return out


def pack_check(cfg: Config) -> list[str]:
    """Rule 6: the language pack's per-file checks over `docstring_globs`."""
    p = pack(cfg)
    rules = cfg.package_docs.get("rules") or {}
    checks = [*p.file_checks, *(fc for name, fc in p.optional_checks.items() if rules.get(name))]
    if not checks:
        return []
    errs: list[str] = []
    for f in _pack_files(cfg):
        rel = cfg.rel(f)
        for fc in checks:
            out = fc(f, rel)
            errs.extend(out)
            if out and "does not parse" in out[0]:
                break
    return errs


def delivery_id_re(cfg: Config, numbers: Iterable[str]) -> re.Pattern[str]:
    """The plane's delivery ids at the product's widths (refs), a task only when its number is one of
    `numbers` (the task log's), and the product's own patterns."""
    pats = (*refs.ids(cfg).delivery_id_patterns(numbers), *cfg.package_docs["delivery_id_patterns"])
    return re.compile("|".join(f"(?:{x})" for x in pats))


def ids_check(cfg: Config, numbers: Iterable[str] | None = None) -> list[str]:
    """Rule 7: no task, finding or ruling id in a package doc (a map of what exists, not a record of
    what a task did) or in a code comment of a file under `docstring_globs`, read by the language
    pack. A task counts only when it is in the task log (`numbers`, read here when not given). Off
    with `no_delivery_ids: false`; history paths (§21.6) are skipped."""
    pd = cfg.package_docs
    if not pd["no_delivery_ids"]:
        return []
    from ccp import docrules, tasklog  # noqa: PLC0415
    numbers = tasklog.task_numbers(cfg) if numbers is None else numbers
    rx, skip = delivery_id_re(cfg, numbers), docrules.history_paths(cfg)
    lines: list[tuple[str, int, str, str]] = []
    for d in source_dirs(cfg):
        doc = doc_for(cfg, d)
        if doc.is_file() and cfg.rel(doc) not in skip:
            lines += [(cfg.rel(doc), n, t, "package doc") for n, t in enumerate(doc.read_text(errors="replace").splitlines(), 1)]
    read = pack(cfg).comments
    for f in _pack_files(cfg) if read else []:
        if cfg.rel(f) not in skip:
            lines += [(cfg.rel(f), n, t, "comment") for n, t in read(f)]
    errs = []
    for rel, n, text, where in lines:
        hits = list(dict.fromkeys(m.group(0) for m in rx.finditer(text)))
        if hits:
            errs.append(f"{rel}:{n}: {where} names delivery id(s) {', '.join(hits)}; "
                        "ids belong in the task log, not the code or its map")
    return errs


def notes(cfg: Config) -> list[str]:
    """Warnings, not failures: configuration that does nothing."""
    pd = cfg.package_docs
    if pd is not None and pd["language"] == "none" and pd["docstring_globs"]:
        return ["package_docs.docstring_globs is set but language is none: no per-file checks run"]
    return []


def check(cfg: Config) -> list[str]:
    """Every package-doc rule, plus the opted-in generic rules. Returns the failures; [] when the
    product has not opted in."""
    if cfg.package_docs is None:
        return []
    from ccp import docrules, rules, tasklog  # noqa: PLC0415
    numbers = tasklog.task_numbers(cfg)   # once per run: both id checks match tasks against it
    # A declined starter rule naming `package_docs` turns the package-doc rules off (§20.5).
    own = ([] if "package_docs" in rules.declined_keys(cfg)
           else core_check(cfg) + pack_check(cfg) + ids_check(cfg, numbers))
    return own + docrules.check(cfg, numbers)
