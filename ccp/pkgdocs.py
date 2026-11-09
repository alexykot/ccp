"""Package-doc coverage and drift, checked mechanically (SPEC §21).

Coverage rot is invisible: nothing points at the doc that was never written. So where a product
opts in (a `package_docs` block in `plane.json`), the rule is mechanical rather than a judgement.
The language-neutral core: every directory holding source carries a package doc, the doc opens
with a title, names no file that is gone, plans nothing, and stays shorter than a fraction of its
source. The language pack (`package_docs.language`, ccp/doclang) adds its source suffixes and
directory names, and its per-file checks over `docstring_globs` (Python: a module docstring that
says what the module does). Opt-in generic rules are ccp/docrules.py. Staleness a rule cannot see
is the architect's docs lens instead (`ccp architect`, §21.7).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ccp import doclang
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


def pack_check(cfg: Config) -> list[str]:
    """Rule 6: the language pack's per-file checks over `docstring_globs`."""
    p = pack(cfg)
    rules = cfg.package_docs.get("rules") or {}
    checks = [*p.file_checks, *(fc for name, fc in p.optional_checks.items() if rules.get(name))]
    if not checks:
        return []
    errs: list[str] = []
    seen: set[Path] = set()
    for g in cfg.package_docs["docstring_globs"]:
        for f in sorted(cfg.root.glob(g)):
            if f in seen or not f.is_file() or f.suffix not in p.file_suffixes:
                continue
            if any(part in p.file_skip_dirs for part in f.parts):
                continue
            seen.add(f)
            rel = cfg.rel(f)
            for fc in checks:
                out = fc(f, rel)
                errs.extend(out)
                if out and "does not parse" in out[0]:
                    break
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
    from ccp import docrules  # noqa: PLC0415
    return core_check(cfg) + pack_check(cfg) + docrules.check(cfg)
