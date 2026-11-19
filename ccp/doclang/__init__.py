"""Language packs for the package-doc checks (SPEC §21.4).

`ccp docs check` judges documentation in two layers. The core (ccp/pkgdocs.py) is language-neutral:
a doc per source directory, its title, no planning sections, its size, no dead paths. A language
pack adds what a language's own conventions demand, and is chosen by the product's `language` (§8.1).

A pack declares the source suffixes and directory names it brings to the core, the per-file checks
it runs over `package_docs.docstring_globs`, opt-in per-file checks a product enables by naming
them in `package_docs.rules`, and how it reads a file's code comments, which the core's
delivery-id check searches. It also owns what the plane knows about the language's tests (house rule
E18): how its test runner prints a count and a failure, how a test module is found and what it
imports, and the command that runs named modules; `for_tests` is the one lookup of them. Adding a
language is adding a module here and a line to PACKS; `language: none` turns the package-doc checks off
and knows no test output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

# A per-file check: (path, root-relative path for messages) -> failures.
FileCheck = Callable[[Path, str], "list[str]"]
# A file's comments in the language's own syntax: (line number, comment text) each.
CommentReader = Callable[[Path], "list[tuple[int, str]]"]
# §14.7: the test modules a change touches: (root, changed paths, the files git tracks or would track,
# root-relative) -> test ids, sorted.
AffectedReader = Callable[[Path, "list[str]", "list[str]"], "list[str]"]
# §14.7: how many test modules the pack counts in the suite: (root, the files git tracks or would track).
SuiteSizer = Callable[[Path, "list[str]"], int]


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
    # The language's tests (§14.1, §14.7). `count_re`: the line whose first group is a test count; `summary`:
    # `failed_re`, `skipped_re` and `section_re`, how the runner prints failures, skips and a failing test's
    # section; both empty where the pack knows none. `test_glob`: a test module's file name. `affected`: the
    # reader of the modules a change touches, `suite_size` the counter of the suite's modules, `test_command`
    # the command that runs modules by name; each None where the pack has none.
    count_re: str = ""
    summary: dict[str, Any] = field(default_factory=dict)
    test_glob: str = ""
    affected: AffectedReader | None = None
    suite_size: SuiteSizer | None = None
    test_command: str | None = None


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
        raise KeyError(f"language {name!r} is not one of {', '.join(NAMES)}")
    return PACKS[name]()


def for_tests(cfg: Any) -> Pack:
    """The pack a product's test facts come from (§14.1, §14.7): the one its `language` names (§8.1), output
    patterns, reader, counter and command alike; `none` knows none of them. With no language (the grace
    release, §29.3), or `cfg` None, the pack it was read with before the key was required."""
    from ccp.config import language_name  # noqa: PLC0415
    return get(language_name(cfg))
