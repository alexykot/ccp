"""Package docs and code comments name no delivery id (SPEC §21.3), checked by `ccp docs check`."""
from __future__ import annotations

import io
import re
import subprocess
import unittest
from contextlib import redirect_stdout

from ccp import cli, config, pkgdocs, refs
from tests.helpers import Product

SRC = '"""Does one thing."""\n' + "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"
RULING = "sm-20260925T083400Z-a1b2"
FINDING = "ar-20261001T120000Z-0f3c#F02"


def product(**pd) -> Product:
    p = Product({"package_docs": {"docstring_globs": ["app/**/*.py"], **pd}})
    p.write("app/.claude.md", "# app\n\nThe app's entry point.\n")
    p.write("app/main.py", SRC)
    return p


def failures(p: Product) -> str:
    return "\n".join(pkgdocs.check(p.cfg))


class PackageDocs(unittest.TestCase):
    def test_a_clean_product_passes(self):
        p = product()
        try:
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_a_task_number_in_a_package_doc_is_reported_with_file_and_line(self):
        p = product()
        try:
            p.write("app/.claude.md", "# app\n\nThe entry point, added in 0012\n")
            errs = pkgdocs.check(p.cfg)
            self.assertEqual(len(errs), 1, errs)
            self.assertTrue(errs[0].startswith("app/.claude.md:3:"), errs)
            self.assertIn("0012", errs[0])
        finally:
            p.cleanup()

    def test_task_ids_findings_and_rulings_in_a_package_doc(self):
        p = product()
        try:
            p.write("app/.claude.md", f"# app\n\nSee 0042-fix-the-thing and task 7.\n{FINDING}\n{RULING}\n")
            errs = failures(p)
            self.assertRegex(errs, r"app/\.claude\.md:3:.*0042-fix-the-thing, task 7")
            self.assertRegex(errs, rf"app/\.claude\.md:4:.*{re.escape(FINDING)}")
            self.assertRegex(errs, rf"app/\.claude\.md:5:.*{RULING}")
        finally:
            p.cleanup()

    def test_numbers_that_are_not_ids_pass(self):
        p = product()
        try:
            p.write("app/.claude.md", "# app\n\nVersion 1.0042, year 2026, ports 8080, ADR-0031, S21.\n")
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_a_claude_md_package_doc_is_checked(self):
        p = Product({"package_docs": {"claude_md_dirs": ["lib"]}})
        try:
            p.write("lib/CLAUDE.md", "# lib\n\nBuilt by task #3.\n")
            p.write("lib/q.sql", "select 1;\n" * 10)
            self.assertRegex(failures(p), r"lib/CLAUDE\.md:3:.*task #3")
        finally:
            p.cleanup()

    def test_the_root_brief_is_not_a_package_doc(self):
        p = product()
        try:
            p.write("CLAUDE.md", "# brief\n\nSee 0012.\n")
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_the_task_width_comes_from_the_ids_block(self):
        p = Product({"ids": {"task": {"width": 5}}, "package_docs": {}})
        try:
            p.write("lib/.claude.md", "# lib\n\n00012 and 00012-wide-id, not 0012.\n")
            p.write("lib/q.sql", "select 1;\n" * 10)
            errs = failures(p)
            self.assertIn("00012, 00012-wide-id", errs)
            self.assertNotIn("0012;", errs)
        finally:
            p.cleanup()


class CodeComments(unittest.TestCase):
    def test_a_ruling_id_in_a_comment_is_reported(self):
        p = product()
        try:
            p.write("app/main.py", SRC + f"y = 2  # as ruled in {RULING}\n")
            errs = pkgdocs.check(p.cfg)
            self.assertEqual(len(errs), 1, errs)
            self.assertTrue(errs[0].startswith("app/main.py:42:"), errs)
            self.assertIn(RULING, errs[0])
        finally:
            p.cleanup()

    def test_the_knob_turns_the_check_off(self):
        p = product(no_delivery_ids=False)
        try:
            p.write("app/main.py", SRC + f"y = 2  # as ruled in {RULING}\n")
            p.write("app/.claude.md", "# app\n\nAdded in 0012.\n")
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_strings_and_docstrings_are_not_comments(self):
        p = product()
        try:
            p.write("app/main.py", f'"""Parses ids like 0042-fix-the-thing."""\nX = "{RULING}"  # a plain comment\n' + SRC)
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_only_files_under_docstring_globs_are_read(self):
        p = product()
        try:
            p.write("tests/.claude.md", "# tests\n")
            p.write("tests/test_x.py", "x = 1  # fixture task 0003\n" * 10)
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_a_file_that_does_not_tokenize_reports_only_its_parse_failure(self):
        p = product()
        try:
            p.write("app/bad.py", '"""Bad."""\nx = (  # task 4\n')
            errs = pkgdocs.check(p.cfg)
            self.assertEqual(len(errs), 1, errs)
            self.assertIn("app/bad.py: does not parse", errs[0])
        finally:
            p.cleanup()

    def test_language_none_reads_no_comments_but_checks_package_docs(self):
        p = Product({"package_docs": {"language": "none"}})
        try:
            p.write("lib/.claude.md", "# lib\n\nAdded in 0012.\n")
            p.write("lib/q.sql", "-- task 4\n" + "select 1;\n" * 10)
            errs = pkgdocs.check(p.cfg)
            self.assertEqual(len(errs), 1, errs)
            self.assertTrue(errs[0].startswith("lib/.claude.md:3:"), errs)
        finally:
            p.cleanup()

    def test_product_patterns_are_checked_beside_the_planes(self):
        p = product(delivery_id_patterns=[r"\bRUL-\d+\b"])
        try:
            p.write("app/main.py", SRC + "y = 2  # RUL-7\nz = 3  # task 9\n")
            errs = failures(p)
            self.assertRegex(errs, r"app/main\.py:42:.*RUL-7")
            self.assertRegex(errs, r"app/main\.py:43:.*task 9")
        finally:
            p.cleanup()

    def test_history_paths_are_skipped(self):
        p = product(rules={"history_attr": "history"})
        try:
            subprocess.run(["git", "init", "-q"], cwd=p.root, check=True)
            p.write(".gitattributes", "app/old.py history\n")
            p.write("app/old.py", SRC + "y = 2  # task 4\n")
            p.write("app/new.py", SRC + "y = 2  # task 5\n")
            subprocess.run(["git", "add", "-A"], cwd=p.root, check=True)
            errs = failures(p)
            self.assertNotIn("app/old.py", errs)
            self.assertIn("app/new.py:42:", errs)
        finally:
            p.cleanup()


class Command(unittest.TestCase):
    def test_docs_check_fails_and_names_the_file_line_and_id(self):
        p = product()
        try:
            p.write("app/.claude.md", "# app\n\nAdded in 0012.\n")
            p.index()
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["--root", str(p.root), "docs", "check"]), 1)
            self.assertRegex(out.getvalue(), r"app/\.claude\.md:3:.*0012")
        finally:
            p.cleanup()


class Config(unittest.TestCase):
    def test_defaults(self):
        p = Product({"package_docs": {}})
        try:
            self.assertIs(p.cfg.package_docs["no_delivery_ids"], True)
            self.assertEqual(p.cfg.package_docs["delivery_id_patterns"], [])
        finally:
            p.cleanup()

    def test_bad_values_are_refused(self):
        for pd in ({"no_delivery_ids": "no"}, {"delivery_id_patterns": "RUL-1"},
                   {"delivery_id_patterns": [""]}, {"delivery_id_patterns": ["("]}):
            p = Product({"package_docs": pd})
            try:
                with self.assertRaises(config.ConfigError, msg=pd):
                    p.cfg
            finally:
                p.cleanup()


class Patterns(unittest.TestCase):
    def test_the_planes_ids_match_whole(self):
        rx = re.compile("|".join(f"(?:{x})" for x in refs.DEFAULT.delivery_id_patterns))
        for s in ("0042", "0042-fix-it", "task 42", "Task #0042", RULING, FINDING, "sh-20261001T120000Z-00ff"):
            self.assertEqual([m.group(0) for m in rx.finditer(f"see {s} here")], [s], s)
        self.assertEqual(rx.findall("added in 0042."), ["0042"])
        for s in ("1.0042", "0042.5", "0042.x", "2026", "x0042", "sm-2026", "ar-20261001T120000Z-0f3c5", "ADR-0031"):
            self.assertEqual(rx.findall(f"see {s} here"), [], s)


if __name__ == "__main__":
    unittest.main()
