"""ccp docs check (SPEC §21.5) and plane.json loading (SPEC §8.1)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout, redirect_stderr

from ccp import cli, config, pkgdocs
from tests.helpers import Product

SRC = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"


class PkgDocsTest(unittest.TestCase):
    def setUp(self):
        self.p = Product({"package_docs": {"docstring_globs": ["app/**/*.py"], "claude_md_dirs": ["app"]}})
        self.p.write("app/CLAUDE.md", "# app\n\nThe app.\n")
        self.p.write("app/main.py", '"""Main."""\n' + SRC)
        self.p.write("app/sub/.claude.md", "# sub\n\nSee `app/main.py`.\n")
        self.p.write("app/sub/util.py", '"""Util."""\n' + SRC)

    def tearDown(self):
        self.p.cleanup()

    def errs(self):
        return pkgdocs.check(self.p.cfg)

    def test_clean(self):
        self.assertEqual(self.errs(), [])

    def test_off_without_block(self):
        q = Product()
        q.write("lib/x.py", "x = 1\n")
        self.assertEqual(pkgdocs.check(q.cfg), [])
        q.cleanup()

    def test_rules(self):
        self.p.write("lib/y.py", '"""Y."""\n')                                   # 1 coverage
        self.p.write("app/sub/.claude.md", "sub\n\n## Roadmap\n\n`gone.py`\n")    # 2, 3, 5
        self.p.write("app/sub/nodoc.py", "x = 1\n")                               # 6 docstring
        self.p.write("app/CLAUDE.md", "# app\n" + "line\n" * 100)                 # 4 size
        errs = "\n".join(self.errs())
        for needle in ("lib: no .claude.md", "must open with a `# ` title", "aspirational section",
                       "names `gone.py`, which does not exist", "app/sub/nodoc.py: no module docstring",
                       "app/CLAUDE.md: 101 lines against"):
            self.assertIn(needle, errs)

    def test_exempt_dirs(self):
        self.p.write("docs/notes.md", "x\n")
        self.p.write("app/__pycache__/x.py", "x\n")
        self.assertEqual(self.errs(), [])


class ConfigTest(unittest.TestCase):
    def test_absent_plane_json_is_not_adopted(self):
        p = Product()
        (p.root / "docs/delivery/plane.json").unlink()
        with self.assertRaisesRegex(config.ConfigError, "has not adopted ccp"):
            config.load(p.root)
        p.cleanup()

    def test_defaults_and_overrides(self):
        p = Product({"task_log": {"max_checks": 3}})
        c = p.cfg
        self.assertEqual(c.task_log["max_checks"], 3)
        self.assertEqual(c.task_log["statuses"][-1], "dropped")
        self.assertIsNone(c.package_docs)
        p.cleanup()

    def test_unknown_keys_refused(self):
        p = Product({"task_log": {"maxchecks": 3}})
        with self.assertRaisesRegex(config.ConfigError, "unknown key"):
            config.load(p.root)
        p.cleanup()

    def test_the_retired_docs_audit_block_is_refused(self):
        p = Product({"docs_audit": {"every_days": 7}})
        with self.assertRaisesRegex(config.ConfigError, "unknown top-level key.*docs_audit"):
            config.load(p.root)
        p.cleanup()

    def test_cli_exit_codes(self):
        p = Product()
        p.task("0001-a")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(cli.main(["--root", str(p.root), "tasks", "check"]), 1)
            self.assertEqual(cli.main(["--root", str(p.root), "tasks", "index"]), 0)
            self.assertEqual(cli.main(["--root", str(p.root), "docs", "check"]), 0)
            self.assertEqual(cli.main(["--root", str(p.root), "tasks", "next"]), 0)
            (p.root / "docs/delivery/plane.json").unlink()
            self.assertEqual(cli.main(["--root", str(p.root), "tasks", "list"]), 2)
        self.assertIn("0001-a", out.getvalue())
        p.cleanup()


if __name__ == "__main__":
    unittest.main()
