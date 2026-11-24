#!/usr/bin/env python3
"""house_checks.py — the programs of the house rules' command checks (docs/ENGINEERING.md E4, E24), one
subcommand each, that `architect.checks` in docs/delivery/plane.json calls with its figures (SPEC §19.11).
Plane development only: run from the repo's root, it reads the files git tracks there. A file it cannot read
or parse is skipped and named on stderr."""
from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
from typing import Iterator


def tracked(pathspec: str) -> list[str]:
    """The files git tracks under `pathspec`, in the current directory's repo."""
    return subprocess.run(["git", "ls-files", pathspec], capture_output=True, text=True,
                          check=True).stdout.splitlines()


def parsed(files: list[str], rule: str) -> Iterator[tuple[str, ast.Module]]:
    """Each file's syntax tree; a file that cannot be read or parsed is named on stderr and skipped."""
    for f in files:
        try:
            with open(f) as fh:
                tree = ast.parse(fh.read(), f)
        except (OSError, SyntaxError, ValueError) as e:
            print(f"{rule}: skipped {f}: {e}", file=sys.stderr)
            continue
        yield f, tree


def _literal(n: ast.AST) -> str:
    """The literal text of a string argument: a plain string, an f-string's literal parts, or a `+` of them."""
    if isinstance(n, ast.Constant) and isinstance(n.value, str):
        return n.value
    if isinstance(n, ast.JoinedStr):
        return "".join(p.value for p in n.values if isinstance(p, ast.Constant))
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        return _literal(n.left) + _literal(n.right)
    return ""


def _long_assert(n: ast.AST) -> bool:
    """An `assert…` call with a string argument of 40 or more characters."""
    if not isinstance(n, ast.Call):
        return False
    f = n.func
    name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
    return name.startswith("assert") and any(len(_literal(a)) >= 40 for a in n.args + [k.value for k in n.keywords])


def e4_count(maximum: int, files: list[str]) -> int:
    """E4: the long-literal asserts in `files` (none given: the tracked tests/*.py), named when over `maximum`."""
    count = sum(1 for _, t in parsed(files or tracked("tests/*.py"), "E4") for n in ast.walk(t) if _long_assert(n))
    if count > maximum:
        print(f"E4 long-literal asserts: {count} > {maximum}")
        return 1
    return 0


def _imports_test_module(n: ast.AST) -> bool:
    """`import tests.test_x`, `from tests.test_x import …`, `from .test_x import …`, `from tests import test_x`
    or `from . import test_x`."""
    if isinstance(n, ast.Import):
        return any(a.name.startswith("tests.test_") for a in n.names)
    if not isinstance(n, ast.ImportFrom):
        return False
    if (n.module or "").split(".")[-1].startswith("test_"):
        return True
    package = (n.module == "tests" and n.level == 0) or (n.module is None and n.level == 1)
    return package and any(a.name.startswith("test_") for a in n.names)


def e4_imports() -> int:
    """E4: each place a tracked tests/*.py file imports a test module, as `<path>:<line>`."""
    hits = [f"{f}:{n.lineno}" for f, t in parsed(tracked("tests/*.py"), "E4") for n in ast.walk(t)
            if _imports_test_module(n)]
    for h in hits:
        print(h)
    return 1 if hits else 0


def e24(long_max: int, exit_max: int) -> int:
    """E24: the tracked ccp/*.py module docstrings over 30 lines and those stating an exit code, each count
    named when over its figure."""
    docs = [ast.get_docstring(t) or "" for _, t in parsed(tracked("ccp/*.py"), "E24")]
    n = sum(len(d.splitlines()) > 30 for d in docs)
    e = sum(bool(re.search(r"exits? [0-9]", d)) for d in docs)
    bad = [m for m in (f"E24 docstrings over 30 lines: {n} > {long_max}" if n > long_max else "",
                       f"E24 docstrings stating an exit code: {e} > {exit_max}" if e > exit_max else "") if m]
    for m in bad:
        print(m)
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="house_checks.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="check", required=True)
    c = sub.add_parser("e4-count", help="count the long-literal asserts")
    c.add_argument("--max", type=int, required=True, help="the figure the count may reach")
    c.add_argument("files", nargs="*", help="the files to read; none: the tracked tests/*.py")
    sub.add_parser("e4-imports", help="find a test module importing another")
    c = sub.add_parser("e24", help="count the long and the exit-code module docstrings")
    c.add_argument("--long-max", type=int, required=True, help="the figure for docstrings over 30 lines")
    c.add_argument("--exit-max", type=int, required=True, help="the figure for docstrings stating an exit code")
    a = p.parse_args(argv)
    if a.check == "e4-count":
        return e4_count(a.max, a.files)
    if a.check == "e4-imports":
        return e4_imports()
    return e24(a.long_max, a.exit_max)


if __name__ == "__main__":
    sys.exit(main())
