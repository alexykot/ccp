"""Opt-in generic documentation rules for `ccp docs check` (SPEC §21.6).

Each rule is off until `package_docs.rules` names it, and each is language-neutral:

- `citations: {globs, targets, ignore?}`: every SPEC ref in a file under `globs` names a heading of
  a `targets` doc, and every markdown link to a doc heading (`[x](path.md#anchor)`) names a heading
  that exists. Fenced code is skipped on both sides.
- `no_ids: {globs, patterns?}`: files under `globs` carry no delivery ids. By default these are task
  ids (`NNNN-slug`), zero-padded task numbers and `task NNNN`, at the product's task width; any
  other id (findings, tickets) is the product's own `patterns`.
- `history_attr: <name>`: tracked paths carrying that git attribute are history and are skipped
  by the rules above; `ccp docs history-paths` lists them for a product's own absence checks.
- `no_overlap: true`: no two check commands (`architect.checks`, `docs.checks`) run the same
  command or the same test module.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ccp import refs
from ccp.config import Config

FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+\.md)#([^)\s]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
# A test module, from a path (`tests/test_x.py`, `tests/test_x.py::Case`) or a dotted name
# (`tests.test_x`, `tests.test_x.Case.test_y`): the module part is what two checks must not share.
TEST_PATH_RE = re.compile(r"\b(tests?/[\w/.-]*?\w)\.py\b")
TEST_DOTTED_RE = re.compile(r"(?<![\w/.])(tests?(?:\.[A-Za-z_]\w*)+)")


def _rules(cfg: Config) -> dict:
    return (cfg.package_docs or {}).get("rules") or {}


def history_paths(cfg: Config, attr: str | None = None) -> set[str]:
    """Tracked paths (untracked files are not history) whose git attribute `attr` (default
    `rules.history_attr`) is set. Empty outside a git repo, without the rule, or when git fails."""
    attr = attr or _rules(cfg).get("history_attr")
    if not attr:
        return set()
    ls = subprocess.run(["git", "-C", str(cfg.root), "ls-files", "-z"], capture_output=True)
    if ls.returncode != 0 or not ls.stdout:
        return set()
    r = subprocess.run(["git", "-C", str(cfg.root), "check-attr", "-z", attr, "--stdin"],
                       input=ls.stdout, capture_output=True)
    if r.returncode != 0:
        return set()
    parts = r.stdout.decode(errors="replace").split("\0")
    return {parts[i] for i in range(0, len(parts) - 2, 3) if parts[i + 2] not in ("unspecified", "unset")}


def _files(cfg: Config, globs: list[str], skip: set[str]) -> list[Path]:
    out, seen = [], set()
    for g in globs:
        for f in sorted(cfg.root.glob(g)):
            rel = cfg.rel(f)
            if f.is_file() and f not in seen and rel not in skip and ".git" not in f.parts:
                seen.add(f)
                out.append(f)
    return out


def unfenced(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every line outside fenced code blocks."""
    out, fence = [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = FENCE_RE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
            continue
        if fence is None:
            out.append((n, line))
    return out


def headings(text: str) -> list[str]:
    return [m.group(1) for _, line in unfenced(text) if (m := HEADING_RE.match(line))]


def slugs(heads: list[str]) -> set[str]:
    """Anchors as GitHub renders them: link text kept and URL dropped, inline code unwrapped,
    lowercased, punctuation other than `-` and `_` removed, spaces to `-`, and a repeated heading
    numbered `-1`, `-2`, …"""
    out: set[str] = set()
    count: dict[str, int] = {}
    for h in heads:
        s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", h)
        s = s.replace("`", "").strip().lower()
        s = re.sub(r"[^\w\- ]", "", s).replace(" ", "-")
        n = count.get(s, 0)
        count[s] = n + 1
        out.add(s if n == 0 else f"{s}-{n}")
    return out


def _cite_re(prefix: str) -> re.Pattern[str]:
    """A SPEC ref as a citation, not a word: `S12`, `S12.3`, `S3–S5`, standing alone (no letter,
    digit, `-` or `/` touching it)."""
    p = re.escape(prefix)
    one = rf"{p}(\d{{1,3}})((?:\.\d+)*)"
    return re.compile(rf"(?<![\w/-]){one}(?:\s*(?:–|—|-|to)\s*{one})?(?![\w/-])")


def citations(cfg: Config, rule: dict, skip: set[str]) -> list[str]:
    ids = refs.ids(cfg)
    p = re.escape(ids.spec_prefix)
    target_heads: set[str] = set()
    for t in rule["targets"]:
        tp = cfg.root / t
        if not tp.is_file():
            return [f"rule citations: target {t} does not exist"]
        for h in headings(tp.read_text(errors="replace")):
            m = re.match(rf"{p}(\d{{1,3}}(?:\.\d+)*)\b", h)
            if m:
                target_heads.add(m.group(1))
    ignore = [re.compile(x) for x in rule.get("ignore") or []]
    cite = _cite_re(ids.spec_prefix)
    errs: list[str] = []
    for f in _files(cfg, rule["globs"], skip):
        rel = cfg.rel(f)
        for n, line in unfenced(f.read_text(errors="replace")):
            if any(rx.search(line) for rx in ignore):
                continue
            for m in cite.finditer(line):
                lo, lo_sub, hi, hi_sub = int(m.group(1)), m.group(2), m.group(3), m.group(4)
                if hi is not None and int(hi) < lo:
                    errs.append(f"rule citations: {rel}:{n} cites the reversed range {m.group(0)}")
                    continue
                want = [f"{lo}{lo_sub}"] if hi is None else (
                    [f"{lo}{lo_sub}", f"{hi}{hi_sub}"] if int(hi) - lo > 200 else
                    [f"{lo}{lo_sub}", *map(str, range(lo + 1, int(hi))), f"{hi}{hi_sub}"])
                for w in dict.fromkeys(want):
                    # A subsection cites its own heading if the doc has one, else its section's.
                    if w not in target_heads and w.split(".")[0] not in target_heads:
                        errs.append(f"rule citations: {rel}:{n} cites {ids.spec_prefix}{w}, which no heading in "
                                    f"{', '.join(rule['targets'])} carries")
        for n, line in unfenced(f.read_text(errors="replace")):
            for path, anchor in LINK_RE.findall(line):
                if "://" in path:
                    continue
                target = (f.parent / path) if not path.startswith("/") else cfg.root / path.lstrip("/")
                if not target.is_file():
                    errs.append(f"rule citations: {rel}:{n} links {path}#{anchor}, and {path} does not exist")
                elif anchor.lower() not in slugs(headings(target.read_text(errors="replace"))):
                    errs.append(f"rule citations: {rel}:{n} links {path}#{anchor}, a heading {path} does not have")
    return errs


def no_ids(cfg: Config, rule: dict, skip: set[str]) -> list[str]:
    w = refs.ids(cfg).task_width
    pats = rule.get("patterns") or [
        rf"(?<![\w-])\d{{{w}}}-[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?![\w-])",   # a task id: 0042-fix-the-thing
        rf"(?<![\w.-])0\d{{{w - 1}}}(?![\w.-])",                            # a zero-padded task number: 0042
        rf"(?i:\btask\s+#?)\d{{1,{w}}}\b",                                  # task 42, task #0042
    ]
    rx = re.compile("|".join(f"(?:{x})" for x in pats))
    errs = []
    for f in _files(cfg, rule["globs"], skip):
        for n, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            hits = list(dict.fromkeys(m.group(0) for m in rx.finditer(line)))
            if hits:
                errs.append(f"rule no_ids: {cfg.rel(f)}:{n} carries delivery id(s) {', '.join(hits)}; "
                            "ids belong in the task log, not the code")
    return errs


def test_modules(cmd: str) -> set[str]:
    """The test modules a check command runs, as dotted names (`tests.test_x`)."""
    out = {m.replace("/", ".") for m in TEST_PATH_RE.findall(cmd)}
    for d in TEST_DOTTED_RE.findall(cmd):
        mod = []
        for part in d.split("."):
            if mod and (part[:1].isupper() or (len(mod) > 1 and part.startswith("test_"))):
                break                      # a class or a method inside the module
            mod.append(part)
        out.add(".".join(mod))
    return out


def no_overlap(cfg: Config) -> list[str]:
    checks = [*(("check", c) for c in (cfg.architect or {}).get("checks") or []),
              *(("docs check", c) for c in cfg.docs["checks"])]
    errs, cmds, mods = [], {}, {}
    for kind, c in checks:
        label = f"{kind} {c['id']}"
        norm = " ".join(c["cmd"].split())
        if norm in cmds:
            errs.append(f"rule no_overlap: {cmds[norm]} and {label} run the same command")
        cmds.setdefault(norm, label)
        for m in sorted(test_modules(c["cmd"])):
            if m in mods and mods[m] != label:
                errs.append(f"rule no_overlap: {mods[m]} and {label} both run {m}")
            mods.setdefault(m, label)
    return errs


def check(cfg: Config) -> list[str]:
    """The opted-in rules' failures; [] when none is configured."""
    r = _rules(cfg)
    if not r:
        return []
    skip = history_paths(cfg)
    errs: list[str] = []
    if r.get("citations"):
        errs += citations(cfg, r["citations"], skip)
    if r.get("no_ids"):
        errs += no_ids(cfg, r["no_ids"], skip)
    if r.get("no_overlap"):
        errs += no_overlap(cfg)
    return errs
