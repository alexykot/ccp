"""ccp docs check (SPEC §21.5) and plane.json loading (SPEC §8.1)."""
from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stdout, redirect_stderr

from ccp import cli, config, pkgdocs
from tests.helpers import Product

SRC = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"


class PkgDocsTest(unittest.TestCase):
    def setUp(self):
        self.p = Product({"language": "python",
                          "package_docs": {"docstring_globs": ["app/**/*.py"], "claude_md_dirs": ["app"]}})
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

    def test_off_under_language_none(self):
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

    def test_a_directory_of_documents_only_needs_no_package_doc_unless_listed(self):
        for git in (False, True):
            with self.subTest(git=git):
                q = Product({"language": "python", "package_docs": {"claude_md_dirs": ["listed"]}})
                self.addCleanup(q.cleanup)
                q.write("notes/a.md", "# a\n")
                q.write("notes/deeper/b.md", "# b\n")
                q.write("mixed/x.md", "# x\n")
                q.write("mixed/y.json", "{}\n")
                q.write("lib/y.py", '"""Y."""\n')
                q.write("listed/z.md", "# z\n")
                if git:  # a checkout: the tracked files decide
                    subprocess.run(["git", "init", "-q"], cwd=q.root, check=True)
                    subprocess.run(["git", "add", "--", "notes", "mixed", "lib", "listed"], cwd=q.root, check=True)
                errs = pkgdocs.check(q.cfg)
                self.assertFalse([e for e in errs if e.startswith("notes")], errs)
                for need in ("mixed: no .claude.md", "lib: no .claude.md", "listed: no CLAUDE.md"):
                    self.assertIn(need, "\n".join(errs))

    def test_a_package_doc_in_a_directory_of_documents_only_is_checked(self):
        for git in (False, True):
            with self.subTest(git=git):
                q = Product({"language": "python", "package_docs": {}})
                self.addCleanup(q.cleanup)
                q.write("notes/a.md", "# a\n" + "line\n" * 20)
                q.write("notes/.claude.md", "no title\n\nSee `gone.md`.\n")
                q.write("plain/b.md", "# b\n")
                q.write("bare/.claude.md", "# bare\n\nSee `gone.md`.\n")  # the doc alone, no other file
                if git:  # a checkout: the tracked files decide
                    subprocess.run(["git", "init", "-q"], cwd=q.root, check=True)
                    subprocess.run(["git", "add", "--", "notes", "plain", "bare"], cwd=q.root, check=True)
                errs = "\n".join(pkgdocs.check(q.cfg))
                self.assertIn("notes/.claude.md: must open with a `# ` title", errs)
                self.assertIn("notes/.claude.md: names `gone.md`", errs)
                self.assertIn("bare/.claude.md: names `gone.md`", errs)
                self.assertNotIn("plain", errs)  # no doc, and none needed
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["--root", str(q.root), "docs", "check"]), 1)
                q.write("notes/.claude.md", "# notes\n")
                q.write("bare/.claude.md", "# bare\n")
                self.assertEqual(pkgdocs.check(q.cfg), [])

    def test_a_listed_directorys_package_doc_is_not_its_own_source(self):
        for git in (False, True):
            with self.subTest(git=git):
                q = Product({"language": "python", "package_docs": {"claude_md_dirs": ["listed", "bare"]}})
                self.addCleanup(q.cleanup)
                q.write("listed/CLAUDE.md", "# listed\n" + "line\n" * 9)
                q.write("listed/a.py", '"""A."""\n' + "x = 1\n" * 9)
                q.write("bare/CLAUDE.md", "# bare\n\nSee `gone.py`.\n")  # the doc alone, no other file
                q.write("unlisted/CLAUDE.md", "# unlisted\n" + "line\n" * 20)  # not listed: still a .md file
                if git:  # a checkout: the tracked files decide
                    subprocess.run(["git", "init", "-q"], cwd=q.root, check=True)
                    subprocess.run(["git", "add", "--", "listed", "bare", "unlisted"], cwd=q.root, check=True)
                errs = pkgdocs.check(q.cfg)
                text = "\n".join(errs)
                self.assertIn("listed/CLAUDE.md: 10 lines against 10 of source", text)  # 20 counted before
                self.assertIn("bare/CLAUDE.md: names `gone.py`, which does not exist", text)
                self.assertNotIn("bare/CLAUDE.md: 3 lines against", text)  # no source left: no size check
                self.assertFalse([e for e in errs if e.startswith("unlisted")], errs)  # not judged


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
        self.assertNotIn("statuses", c.task_log)  # a removed key (§29.3)
        self.assertIsNone(c.package_docs)
        p.cleanup()

    def test_an_unknown_key_is_not_read(self):
        p = Product({"task_log": {"maxchecks": 3}})
        with redirect_stderr(io.StringIO()):
            c = config.load(p.root)
        self.assertEqual((c.task_log["max_checks"], c.unknown_keys), (6, ("task_log.maxchecks",)))
        p.cleanup()

    def test_the_retired_docs_audit_block_is_unknown(self):
        p = Product({"docs_audit": {"every_days": 7}})
        with redirect_stderr(io.StringIO()):
            self.assertEqual(config.load(p.root).unknown_keys, ("docs_audit",))
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
