"""SPEC §20.1 `ccp docs check --only <id>`: one `architect.checks` or `docs.checks` entry, run and judged as
`ccp docs check` runs it, and nothing else; an id it runs no check by exits 2 naming the ids it does."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli
from tests.helpers import Product

HOUSE = [{"id": "E1", "cmd": "echo a > a.out"}, {"id": "E2", "cmd": "echo broken; exit 3"}]
DOCS = [{"id": "D1", "cmd": "echo d > d.out"}, {"id": "D2", "cmd": "echo bad; exit 4"}]


class Only(unittest.TestCase):
    def setUp(self):
        # no INDEX.yaml and no rules doc: the whole command fails on them, a run of one check does not
        self.p = Product({"architect": {"checks": HOUSE}, "docs": {"checks": DOCS}})
        self.addCleanup(self.p.cleanup)

    def docs_check(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "docs", "check", *args])
        return code, out.getvalue(), err.getvalue()

    def ran(self) -> set[str]:
        return {f.stem for f in self.p.root.glob("*.out")}

    def test_only_runs_the_one_check_named_and_nothing_else(self):
        code, out, err = self.docs_check("--only", "E1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.ran(), {"a"})
        self.assertIn("E1", out)
        for other in ("E2", "D1", "D2"):
            self.assertNotIn(other, out)
        code, out, err = self.docs_check("--only", "D1")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.ran(), {"a", "d"})

    def test_a_failing_check_fails_under_the_name_docs_check_gives_it(self):
        for cid, kind in (("E2", "check"), ("D2", "docs check")):
            code, out, _err = self.docs_check("--only", cid)
            self.assertEqual(code, 1, out)
            failing = [ln.strip() for ln in out.splitlines()[1:]]
            self.assertEqual([ln.split(": ", 1)[0] for ln in failing], [f"{kind} {cid}"])
        self.assertEqual(self.ran(), set())

    def test_an_unknown_id_exits_2_naming_the_ids_it_runs(self):
        code, out, err = self.docs_check("--only", "E99")
        self.assertEqual(code, 2, out + err)
        first = err.splitlines()[0]
        for cid in ("E99", "E1", "E2", "D1", "D2"):
            self.assertIn(cid, first)
        self.assertEqual(self.ran(), set())


if __name__ == "__main__":
    unittest.main()
