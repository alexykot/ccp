"""A SPEC ref resolved to its section (SPEC §7.2): the one resolver `ccp spec show` prints and the estimator quotes
(§26.3). The section is found by the fence-aware heading finder (`mdsection`, house rule E22)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from ccp import config, mdsection
from ccp.config import Config
from ccp.refs import ids


def files(cfg: Config) -> list[Path]:
    """The product's SPEC files, in `spec_paths` order (§3.5; globs relative to the root, a directory read as its
    `*.md`, §26.3)."""
    out: list[Path] = []
    for pat in (f"{p}*.md" if p.endswith("/") else p for p in config.spec_paths(cfg)):
        hits = sorted(cfg.root.glob(pat)) if any(ch in pat for ch in "*?[") else [cfg.root / pat]
        out += [p for p in hits if p.is_file() and p not in out]
    return out


def number(ref: str, prefix: str) -> str:
    """The ref's number: `ref` without a leading `§` or `prefix`."""
    ref = ref.strip()
    if ref.startswith("§"):
        return ref[1:].strip()
    return ref[len(prefix):] if prefix and ref.startswith(prefix) else ref


def heading_pattern(ref: str, prefix: str) -> str:
    """The heading text a ref's section starts with: its number, with or without `prefix`, then `.`, a blank or the
    line's end."""
    p = rf"(?:{re.escape(prefix)})?" if prefix else ""
    return rf"{p}{re.escape(number(ref, prefix))}(?=[. \t]|\r?$)"


def resolve(texts: list[str], ref: str, prefix: str) -> str | None:
    """The section a SPEC ref (`S13`, `§10.6`, `10.6`) names: the `mdsection.heading_block` of the first heading
    whose text starts with its number (`heading_pattern`), in the first of `texts` that has one; None when none has.
    The one resolver of a SPEC ref (§7.2)."""
    if not number(ref, prefix):
        return None
    pattern = heading_pattern(ref, prefix)
    for text in texts:
        if (block := mdsection.heading_block(text, pattern)) is not None:
            return block
    return None


def texts(cfg: Config) -> list[str]:
    """The SPEC files' texts, in `spec_paths` order; a file that cannot be read is left out."""
    out = []
    for f in files(cfg):
        try:
            out.append(f.read_text(errors="replace"))
        except OSError:
            continue
    return out


def show(cfg: Config, refs: list[str]) -> int:
    """`ccp spec show`: each ref's section printed in the order given; a ref no heading carries is named on stderr,
    and then the exit is 1. A reader that stops early (`| head`) ends the output quietly."""
    all_texts, prefix, code, blocks = texts(cfg), ids(cfg).spec_prefix, 0, []
    for ref in refs:
        block = resolve(all_texts, ref, prefix)
        if block is None:
            print(f"ccp spec show: no SPEC heading carries `{ref}` (SPEC §7.2)", file=sys.stderr)
            code = 1
        else:
            blocks.append(block.rstrip("\n"))
    if blocks:
        try:
            sys.stdout.write("\n\n".join(blocks) + "\n")
            sys.stdout.flush()
        except BrokenPipeError:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return code
