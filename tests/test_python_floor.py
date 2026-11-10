"""The declared Python floor is what runs the plane (SPEC §29.2). launchd starts the telemetry receiver
and the board through `bin/ccp`, whose `#!/usr/bin/env python3` finds the system python3 on launchd's
PATH: 3.9 on macOS. Below 3.10 an annotation is evaluated at definition time, so a PEP 604 union
(`int | str`) in one crashes the import unless the module postpones annotations with
`from __future__ import annotations`. The guard reads the syntax tree, so no spelling of the union
escapes it, and names each module and line."""
import ast
import pathlib
import re
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "ccp"


def declared_floor(pyproject: pathlib.Path = ROOT / "pyproject.toml") -> tuple[int, int]:
    """`requires-python = ">=X.Y"` as (X, Y)."""
    m = re.search(r'^requires-python\s*=\s*">=\s*(\d+)\.(\d+)', pyproject.read_text(), re.M)
    if not m:
        raise AssertionError(f"{pyproject} declares no `requires-python = \">=X.Y\"`")
    return int(m.group(1)), int(m.group(2))


def _postpones_annotations(tree: ast.Module) -> bool:
    return any(isinstance(n, ast.ImportFrom) and n.module == "__future__"
               and any(a.name == "annotations" for a in n.names) for n in tree.body)


def _annotations(tree: ast.AST):
    for n in ast.walk(tree):
        if isinstance(n, ast.arg) and n.annotation is not None:
            yield n.annotation
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns is not None:
            yield n.returns
        elif isinstance(n, ast.AnnAssign):
            yield n.annotation


def unpostponed_unions(path: pathlib.Path, base: pathlib.Path) -> list[str]:
    """`<module>:<line>` for each `|` inside an annotation of a module without the future import."""
    tree = ast.parse(path.read_text(), filename=str(path))
    if _postpones_annotations(tree):
        return []
    rel = path.relative_to(base).as_posix()
    lines = sorted({b.lineno for ann in _annotations(tree) for b in ast.walk(ann)
                    if isinstance(b, ast.BinOp) and isinstance(b.op, ast.BitOr)})
    return [f"{rel}:{ln}" for ln in lines]


def guard(pkg: pathlib.Path, floor: tuple[int, int]) -> list[str]:
    """Every annotation union under `pkg` that the floor interpreter cannot import."""
    if floor >= (3, 10):
        return []
    return [hit for p in sorted(pkg.rglob("*.py")) for hit in unpostponed_unions(p, pkg.parent)]


class TheGuardCatchesUnionAnnotations(unittest.TestCase):
    def _scan(self, source: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "scratch"
            pkg.mkdir()
            (pkg / "mod.py").write_text(source)
            return guard(pkg, (3, 9))

    def test_a_union_in_a_parameter_is_named_by_module_and_line(self):
        self.assertEqual(self._scan("import os\n\n\ndef f(x: int | str):\n    return x\n"),
                         ["scratch/mod.py:4"])

    def test_every_annotation_site_is_read(self):
        source = ("from typing import Optional\n"
                  "X: int | None = None\n"
                  "class C:\n"
                  "    y: 'str' | None = None\n"
                  "def f(*a: int | str, k: Optional[int | str] = None, **kw: bytes | None) -> int | None:\n"
                  "    z: list[int | str] = []\n"
                  "async def g(\n"
                  "    q: dict[str, int | None],\n"
                  ") -> None:\n"
                  "    pass\n")
        self.assertEqual(self._scan(source), [f"scratch/mod.py:{n}" for n in (2, 4, 5, 6, 8)])

    def test_postponed_annotations_pass(self):
        self.assertEqual(self._scan('"""Doc."""\nfrom __future__ import annotations\n\n'
                                    "def f(x: int | str) -> int | None:\n    return None\n"), [])

    def test_a_union_outside_an_annotation_passes(self):
        self.assertEqual(self._scan("FLAGS = 1 | 2\n\ndef f(x: int = 1 | 2) -> int:\n    return x | 4\n"), [])

    def test_a_floor_of_3_10_needs_no_postponing(self):
        with tempfile.TemporaryDirectory() as d:
            pkg = pathlib.Path(d) / "scratch"
            pkg.mkdir()
            (pkg / "mod.py").write_text("def f(x: int | str):\n    return x\n")
            self.assertEqual(guard(pkg, (3, 10)), [])
            self.assertEqual(guard(pkg, (3, 9)), ["scratch/mod.py:1"])


class EveryModuleImportsOnTheDeclaredFloor(unittest.TestCase):
    def test_the_package_postpones_every_union_annotation(self):
        hits = guard(PKG, declared_floor())
        self.assertEqual(hits, [], "add `from __future__ import annotations` to these modules: "
                         + ", ".join(hits))

    def test_the_readme_declares_the_same_floor(self):
        m = re.search(r"Python (\d+)\.(\d+) or newer", (ROOT / "README.md").read_text())
        self.assertIsNotNone(m, "README.md names no Python floor")
        self.assertEqual((int(m.group(1)), int(m.group(2))), declared_floor())

    def test_the_floor_is_read_from_requires_python(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "pyproject.toml"
            p.write_text('[project]\nname = "x"\nrequires-python = ">=3.9"\n')
            self.assertEqual(declared_floor(p), (3, 9))
            p.write_text('[project]\nname = "x"\n')
            with self.assertRaises(AssertionError):
                declared_floor(p)


if __name__ == "__main__":
    unittest.main()
