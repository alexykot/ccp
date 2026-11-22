"""The Python pack for the package-doc checks (SPEC §21).

Python documents a module with its docstring, so each `.py` file under `package_docs.docstring_globs`
must carry one. Opt-in (`package_docs.rules.no_call_bullets: true`): the docstring says what the
module does rather than list its functions as backticked call bullets (`- `foo()` …`), which go
stale with every rename and repeat the code. The core's delivery-id check reads the file's `#`
comments through this pack; strings, docstrings included, are not comments.

The pack also owns what the plane knows about Python's tests (house rule E18): how unittest prints its
counts and failures, the `test*.py` modules, the reader of the ones a change touches (`affected`) and the
command that runs named modules.
"""
from __future__ import annotations

import ast
import fnmatch
import io
import re
import tokenize
from pathlib import Path

from ccp.doclang import Pack

# A docstring line that is a bullet naming a call: `- `name(...)`` or `* `mod.name()``.
CALL_BULLET_RE = re.compile(r"^\s*[-*]\s+`[\w.]+\([^`]*\)`", re.M)


def _docstring(path: Path) -> tuple[str | None, str | None]:
    """(docstring, parse error)."""
    try:
        mod = ast.parse(path.read_text())
    except SyntaxError as e:
        return None, str(e)
    return ast.get_docstring(mod), None


def has_docstring(path: Path, rel: str) -> list[str]:
    doc, err = _docstring(path)
    if err is not None:
        return [f"{rel}: does not parse ({err})"]
    if not doc:
        return [f"{rel}: no module docstring (say what it does and which rules it enforces)"]
    return []


def no_call_bullets(path: Path, rel: str) -> list[str]:
    doc, err = _docstring(path)
    if err is not None or not doc:
        return []
    n = len(CALL_BULLET_RE.findall(doc))
    return [f"{rel}: module docstring lists {n} function(s) as backticked call bullets; say what the "
            "module does, not its API"] if n else []


def comments(path: Path) -> list[tuple[int, str]]:
    """The file's `#` comments, (line, text); docstrings and other strings are code, not comments. A
    file that does not tokenize gives none: the docstring check reports that it does not parse."""
    try:
        toks = tokenize.generate_tokens(io.StringIO(path.read_text(errors="replace")).readline)
        return [(t.start[0], t.string) for t in toks if t.type == tokenize.COMMENT]
    except (tokenize.TokenError, SyntaxError):
        return []


# --------------------------------------------------------------------------------------- the tests

TEST_GLOB = "test*.py"  # the test modules: unittest's default discovery pattern
# The line whose first group is a test count, summed (§14.3): unittest's "Ran N tests in Xs".
COUNT_RE = r"^Ran (\d+) tests? in "
# The patterns of `suite.summary` a product leaves out (§14.1): unittest's failure and error counts, its
# skip count, and the line after a `====` rule that starts a failing test's section.
SUMMARY = {
    "failed_re": [r"^FAILED \(.*\bfailures=(\d+)", r"^FAILED \(.*\berrors=(\d+)"],
    "skipped_re": r"^(?:OK|FAILED) \(.*\bskipped=(\d+)",
    "section_re": r"^(?:FAIL|ERROR|UNEXPECTED SUCCESS): ",
}
TEST_COMMAND = "python3 -m unittest"  # runs test modules, or one test, by dotted name
# The lines that say the code did not build or import (§20.6): a module with a syntax error, and a test module
# unittest could not import.
UNBUILT_RE = (r"^(?:SyntaxError|IndentationError|TabError): ", r"^ImportError: Failed to import test module: ")


def _py_module(rel: str) -> str | None:
    """The dotted module a root-relative `.py` path is (`pkg/__init__.py` is `pkg`), or None."""
    if not rel.endswith(".py"):
        return None
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts and all(p.isidentifier() for p in parts) else None


def _py_imports(text: str, module: str, is_pkg: bool) -> set[str]:
    """Every module a file's import statements name, wherever they sit (a function's too): `import a.b`
    gives a.b, `from a import b` gives a and a.b (b may be a submodule), a relative import is resolved
    against the file's own package. Each one's parent packages are added: importing a.b runs a."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    own = module.split(".") if is_pkg else module.split(".")[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(own):
                    continue
                parts = own[:len(own) - (node.level - 1)] + (node.module.split(".") if node.module else [])
            else:
                parts = node.module.split(".") if node.module else []
            base = ".".join(parts)
            if base:
                names.add(base)
            names.update(f"{base}.{a.name}" if base else a.name for a in node.names if a.name != "*")
    return {".".join(n.split(".")[:i]) for n in names for i in range(1, n.count(".") + 2)}


def _read(p: Path) -> str | None:
    try:
        return p.read_text(errors="replace") if p.is_file() and not p.is_symlink() else None
    except OSError:
        return None


def _test_files(files: list[str]) -> list[tuple[str, str]]:
    """(root-relative path, dotted module) of each `test*.py` file among `files` (what git tracks or would
    track), in their order."""
    return [(rel, mod) for rel in files if (mod := _py_module(rel))
            and fnmatch.fnmatchcase(rel.rsplit("/", 1)[-1], TEST_GLOB)]


def suite_size(root: Path, files: list[str]) -> int:
    """§14.7: how many test modules the pack counts in the suite: the ones the reader walks (a file
    deleted in the working tree or not a regular file is no module)."""
    return sum(1 for rel, _ in _test_files(files) if _read(root / rel) is not None)


def affected(root: Path, changed: list[str], files: list[str]) -> list[str]:
    """The test modules a change touches (`files`: what git tracks or would track): each `test*.py` file git tracks or would track that changed itself, imports a
    changed module directly or through one package level (a package it imports whose `__init__.py`
    imports it), or names a changed file's name in its text: a name with an extension, never a directory's
    (an extension-less name such as `Makefile`, or `pkg`, would match nearly every test)."""
    changed_mods = {m for m in map(_py_module, changed) if m}
    packages = {m: rel for rel in files if rel.endswith("/__init__.py") and (m := _py_module(rel))}
    init_imports: dict[str, set[str]] = {}

    def through(pkg: str) -> set[str]:
        if pkg not in init_imports:
            init_imports[pkg] = _py_imports(_read(root / packages[pkg]) or "", pkg, True)
        return init_imports[pkg]

    names = {Path(c).name for c in changed if Path(c).suffix and not (root / c).is_dir()}  # a file's name only
    name_re = re.compile("|".join(rf"(?<![\w.-]){re.escape(n)}(?![\w-])" for n in sorted(names))) if names else None
    out, touched = set(), set(changed)
    for rel, mod in _test_files(files):
        text = _read(root / rel)
        if text is None:  # deleted in the working tree, or not a regular file
            continue
        if rel in touched:
            out.add(mod)
            continue
        direct = _py_imports(text, mod, False)
        reached = direct.union(*(through(p) for p in direct if p in packages))
        if reached & changed_mods or (name_re is not None and name_re.search(text)):
            out.add(mod)
    return sorted(out)


PACK = Pack(
    name="python",
    source_suffixes=(".py",),
    exempt_dirs=("__pycache__", ".venv"),
    file_suffixes=(".py",),
    file_checks=(has_docstring,),
    optional_checks={"no_call_bullets": no_call_bullets},
    file_skip_dirs=("__pycache__",),
    comments=comments,
    count_re=COUNT_RE,
    summary=SUMMARY,
    test_glob=TEST_GLOB,
    affected=affected,
    suite_size=suite_size,
    test_command=TEST_COMMAND,
    unbuilt_re=UNBUILT_RE,
)
