"""The Python pack for the package-doc checks (SPEC §21).

Python documents a module with its docstring, so each `.py` file under `package_docs.docstring_globs`
must carry one. Opt-in (`package_docs.rules.no_call_bullets: true`): the docstring says what the
module does rather than list its functions as backticked call bullets (`- `foo()` …`), which go
stale with every rename and repeat the code.
"""
from __future__ import annotations

import ast
import re
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


PACK = Pack(
    name="python",
    source_suffixes=(".py",),
    exempt_dirs=("__pycache__", ".venv"),
    file_suffixes=(".py",),
    file_checks=(has_docstring,),
    optional_checks={"no_call_bullets": no_call_bullets},
    file_skip_dirs=("__pycache__",),
)
