"""The product's language, a required top-level plane.json key (SPEC §8.1): it is validated, the old
`package_docs.language` is read in its place while it is unset, the package-doc checks (§21.3, §21.4), the
reading of test output (§14.1) and `ccp suite affected` (§14.7) follow it, and a command that needs it warns
during the grace release (§29.3) and refuses after it."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, doclang, pkgdocs, suite
from tests.helpers import Product

CCP = Path(__file__).resolve().parents[1] / "bin" / "ccp"


def product(plane: dict) -> Product:
    """A git product whose plane.json is `plane` (only `project_id` besides), with a source directory that
    carries no package doc, committed."""
    p = Product(plane, bare=True)
    p.write("src/a.py", "x = 1\n")
    p.write("src/b.sql", "select 1;\n")
    p.write("CLAUDE.md", "# demo\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "init")):
        subprocess.run(["git", "-C", str(p.root), "-c", "user.email=t@t", "-c", "user.name=t", *args],
                       check=True, capture_output=True)
    p.index()
    return p


def load(p: Product) -> tuple[config.Config, str]:
    err = io.StringIO()
    with redirect_stderr(err):
        config._WARNED.clear()
        return config.load(p.root), err.getvalue()


class Key(unittest.TestCase):
    def cfg(self, plane: dict) -> tuple[config.Config, str]:
        p = Product(plane, bare=True)
        self.addCleanup(p.cleanup)
        return load(p)

    def test_each_pack_and_none_load_and_unset_is_none(self):
        for lang in doclang.NAMES:
            self.assertEqual(self.cfg({"language": lang})[0].language, lang)
        cfg, err = self.cfg({})
        self.assertIsNone(cfg.language)
        self.assertEqual(err, "")

    def test_any_other_value_is_refused_listing_the_packs(self):
        for bad in ("cobol", "", None, 1, ["python"]):
            p = Product({"language": bad}, bare=True)
            self.addCleanup(p.cleanup)
            with self.assertRaisesRegex(config.ConfigError, r"language .* is not one of none, python", msg=bad):
                p.cfg
        self.assertIn("language", config.REQUIRED_KEYS)

    def test_the_old_place_is_read_while_the_key_is_unset_with_a_warning_naming_the_move(self):
        cfg, err = self.cfg({"package_docs": {"language": "none"}})
        self.assertEqual(cfg.language, "none")
        self.assertIn("package_docs.language", err)
        self.assertIn("`language`", err)

    def test_the_key_wins_over_the_old_place_which_is_ignored_with_a_warning(self):
        cfg, err = self.cfg({"language": "python", "package_docs": {"language": "none"}})
        self.assertEqual(cfg.language, "python")
        self.assertIn("package_docs.language is ignored", err)
        self.assertTrue(config.package_docs_on(cfg))

    def test_a_pack_loads_the_package_doc_settings_without_a_block_and_none_loads_none(self):
        python, _ = self.cfg({"language": "python"})
        self.assertEqual(python.package_docs["doc_name"], config.PACKAGE_DOCS_DEFAULTS["doc_name"])
        self.assertTrue(config.package_docs_on(python))
        none, _ = self.cfg({"language": "none"})
        self.assertIsNone(none.package_docs)
        self.assertFalse(config.package_docs_on(none))
        ruled, _ = self.cfg({"language": "none", "package_docs": {"rules": {"no_overlap": True}}})
        self.assertTrue(ruled.package_docs["rules"]["no_overlap"])  # the generic rules run whatever the language
        self.assertFalse(config.package_docs_on(ruled))

    def test_unset_turns_the_checks_on_only_with_a_block_as_before(self):
        self.assertFalse(config.package_docs_on(self.cfg({})[0]))
        block, _ = self.cfg({"package_docs": {}})
        self.assertTrue(config.package_docs_on(block))
        self.assertEqual(pkgdocs.pack(block).name, config.GRACE_LANGUAGE)


class DocsCheck(unittest.TestCase):
    def run_check(self, plane: dict) -> tuple[int, str, str]:
        p = product(plane)
        self.addCleanup(p.cleanup)
        out, err = io.StringIO(), io.StringIO()
        config._LANGUAGE_WARNED.clear()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(p.root), "docs", "check"])
        return code, out.getvalue(), err.getvalue()

    def test_unset_warns_naming_the_key_and_runs_as_before(self):
        code, out, err = self.run_check({})
        self.assertEqual(code, 0, out + err)
        self.assertIn("`language`", err)

    def test_unset_after_the_grace_release_is_refused_naming_the_key(self):
        with mock.patch.object(config, "REQUIRED_KEYS_GRACE", False):
            code, out, err = self.run_check({})
        self.assertEqual(code, 2, out + err)
        self.assertIn("`language`", err)
        self.assertEqual(out, "")

    def test_a_pack_runs_the_package_doc_checks_with_no_block(self):
        code, out, err = self.run_check({"language": "python"})
        self.assertEqual(code, 1, out + err)
        self.assertIn("src: no .claude.md", out)
        self.assertNotIn("unknown key", out + err)
        self.assertNotIn("`language`", err)

    def test_none_turns_them_off_and_the_old_place_still_works_with_a_warning(self):
        code, out, err = self.run_check({"language": "none"})
        self.assertEqual((code, err), (0, ""), out)
        code, out, err = self.run_check({"package_docs": {"language": "none"}})
        self.assertEqual(code, 0, out + err)
        self.assertIn("package_docs.language", err)


class Affected(unittest.TestCase):
    def run_affected(self, plane: dict) -> tuple[int, str, str]:
        p = product(plane)
        self.addCleanup(p.cleanup)
        out, err = io.StringIO(), io.StringIO()
        config._LANGUAGE_WARNED.clear()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(p.root), "suite", "affected", "--paths", "src/a.py"])
        return code, out.getvalue(), err.getvalue()

    def test_unset_warns_and_reads_with_the_python_pack_as_before(self):
        code, out, err = self.run_affected({})
        self.assertEqual(code, 0, err)
        self.assertIn("`language`", err)
        self.assertIn("no test module depends", err)

    def test_unset_after_the_grace_release_is_refused(self):
        with mock.patch.object(config, "REQUIRED_KEYS_GRACE", False):
            code, out, err = self.run_affected({})
        self.assertEqual((code, out), (2, ""))
        self.assertIn("`language`", err)

    def test_the_language_picks_the_reader(self):
        self.assertEqual(self.run_affected({"language": "python"})[0], 0)
        code, _, err = self.run_affected({"language": "none"})
        self.assertEqual(code, 2)
        self.assertIn("suite.affected_map", err)


class TestOutput(unittest.TestCase):
    """§14.1: the count and summary defaults are the pack's; with `none` only the product's patterns count."""

    def cfg(self, plane: dict) -> config.Config:
        p = Product(plane, bare=True)
        self.addCleanup(p.cleanup)
        return load(p)[0]

    def test_none_has_no_default_patterns_and_a_pack_its_own(self):
        none = self.cfg({"language": "none"})
        self.assertEqual(suite._count_res(none), [])
        scfg = suite._summary_cfg(none)
        self.assertEqual((scfg["failed_re"], scfg["skipped_re"], scfg["section_re"]), ([], [], []))
        mine = self.cfg({"language": "none", "suite": {"count_re": r"^(\d+) passed",
                                                       "summary": {"failed_re": r"(\d+) failed"}}})
        self.assertEqual([p.pattern for p in suite._count_res(mine)], [rb"^(\d+) passed"])
        self.assertEqual([p.pattern for p in suite._summary_cfg(mine)["failed_re"]], [r"(\d+) failed"])
        python = self.cfg({"language": "python"})
        self.assertEqual([p.pattern for p in suite._count_res(python)], [doclang.get("python").count_re.encode()])

    def run_suite(self, plane: dict) -> subprocess.CompletedProcess[str]:
        p = product(plane)
        self.addCleanup(p.cleanup)
        return subprocess.run([str(CCP), "--root", str(p.root), "suite", "run", "--summary", "--", sys.executable,
                               "-c", "print('Ran 5 tests in 0.1s')"], cwd=p.root, capture_output=True, text=True,
                              timeout=60)

    def test_a_none_products_unittest_line_is_not_counted_and_a_python_products_is(self):
        none = self.run_suite({"language": "none"})
        self.assertEqual(none.returncode, 0, none.stderr)
        self.assertIn("no test count found", none.stdout)
        python = self.run_suite({"language": "python"})
        self.assertEqual(python.returncode, 0, python.stderr)
        self.assertIn("; 5 tests", python.stdout)
        self.assertNotIn("`language`", python.stderr)

    def test_unset_warns_and_reads_as_before(self):
        r = self.run_suite({})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("`language`", r.stderr)
        self.assertIn("; 5 tests", r.stdout)

    def test_unset_after_the_grace_release_is_refused_and_runs_nothing(self):
        p = product({})
        self.addCleanup(p.cleanup)
        ran = p.root / "ran"
        err = io.StringIO()
        with mock.patch.object(config, "REQUIRED_KEYS_GRACE", False), redirect_stderr(err), \
                redirect_stdout(io.StringIO()):
            code = cli.main(["--root", str(p.root), "suite", "run", "--summary", "--", "touch", str(ran)])
        self.assertEqual(code, 2, err.getvalue())
        self.assertIn("`language`", err.getvalue())
        self.assertFalse(ran.exists())



class ArchitectDocsLens(unittest.TestCase):
    def test_the_docs_lens_lists_the_directories_only_where_the_checks_run(self):
        import tempfile  # noqa: PLC0415
        from ccp import architect  # noqa: PLC0415
        for lang, listed in (("none", False), ("python", True)):
            with self.subTest(language=lang):
                p = Product({"language": lang, "package_docs": {}, "architect": {}})
                self.addCleanup(p.cleanup)
                p.write("src/a.py", "x = 1\n")
                q = tempfile.TemporaryDirectory()
                self.addCleanup(q.cleanup)
                text = architect.prompt_for(p.cfg, Path(q.name), "ar-x", "pass", ["docs"], "abc", None, False,
                                            None, "due", None)
                self.assertEqual('"dir": "src"' in text, listed)


if __name__ == "__main__":
    unittest.main()
