"""Language packs for the package-doc checks (SPEC §21.4).

`ccp docs check` judges documentation in two layers. The core (ccp/pkgdocs.py) is language-neutral:
a doc per source directory, its title, no planning sections, its size, no dead paths. A language
pack adds what a language's own conventions demand, and is chosen by `package_docs.language`.

A pack declares the source suffixes and directory names it brings to the core, the per-file checks
it runs over `package_docs.docstring_globs`, opt-in per-file checks a product enables by naming
them in `package_docs.rules`, and how it reads a file's code comments, which the core's
delivery-id check searches. Adding a language is adding a module here and a
line to PACKS; `language: none` runs the core alone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# A per-file check: (path, root-relative path for messages) -> failures.
FileCheck = Callable[[Path, str], "list[str]"]
# A file's comments in the language's own syntax: (line number, comment text) each.
CommentReader = Callable[[Path], "list[tuple[int, str]]"]


@dataclass(frozen=True)
class Pack:
    name: str
    source_suffixes: tuple[str, ...]
    exempt_dirs: tuple[str, ...]
    file_suffixes: tuple[str, ...]          # files under docstring_globs the file checks read
    file_checks: tuple[FileCheck, ...] = field(default_factory=tuple)
    # Opt-in per-file checks, run when package_docs.rules names them (true).
    optional_checks: dict[str, FileCheck] = field(default_factory=dict)
    # Directory names whose files the per-file checks skip, whatever exempt_dirs says.
    file_skip_dirs: tuple[str, ...] = ()
    # Reads a file's code comments, for the delivery-id check (§21.3); None: the pack reads none.
    comments: CommentReader | None = None


def _python() -> Pack:
    from ccp.doclang import python  # noqa: PLC0415
    return python.PACK


NONE = Pack("none", (), (), ())
# Name -> loader, so a pack's imports are paid only when it is chosen.
PACKS: dict[str, Callable[[], Pack]] = {"python": _python, "none": lambda: NONE}
NAMES = tuple(sorted(PACKS))


def get(name: str) -> Pack:
    """The pack called `name`; a KeyError names the packs there are."""
    if name not in PACKS:
        raise KeyError(f"package_docs.language {name!r} is not one of {', '.join(NAMES)}")
    return PACKS[name]()
