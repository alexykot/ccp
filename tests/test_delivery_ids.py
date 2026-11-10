"""Package docs and code comments name no delivery id (SPEC §21.3), checked by `ccp docs check`."""
from __future__ import annotations

import io
import re
import subprocess
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ccp import cli, config, pkgdocs, refs, tasklog
from tests.helpers import Product

SRC = '"""Does one thing."""\n' + "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"
RULING = "sm-20260925T083400Z-a1b2"
FINDING = "ar-20261001T120000Z-0f3c#F02"


# The tasks the fixtures' docs and comments name: a task id counts only when its task is in the log.
TASKS = ("0003-fixture", "0004-parse", "0005-store", "0007-add-login", "0009-cli", "0012-entry",
         "0042-fix-the-thing")


def log(p: Product, *tids: str) -> Product:
    for tid in tids:
        p.task(tid)
    return p


def product(**pd) -> Product:
    p = log(Product({"package_docs": {"docstring_globs": ["app/**/*.py"], **pd}}), *TASKS)
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
        p = log(Product({"package_docs": {"claude_md_dirs": ["lib"]}}), *TASKS)
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
        p = log(Product({"ids": {"task": {"width": 5}}, "package_docs": {}}), "00012-wide-id", "0012-narrow")
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
        p = log(Product({"package_docs": {"language": "none"}}), *TASKS)
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


class TaskLog(unittest.TestCase):
    """A task id counts only when its task is in the product's task log."""

    def scratch(self, doc: str, **pd) -> Product:
        p = log(Product({"package_docs": {"docstring_globs": ["app/**/*.py"], **pd}}), "0001-setup", "0007-add-login")
        p.write("app/.claude.md", "# app\n\n" + doc)
        p.write("app/main.py", SRC)
        return p

    def test_ordinary_numbers_file_names_and_years_are_not_ids(self):
        doc = "Run chmod 0644 on it.\nMigrations start at 0001-init.sql.\nSee task 2026.\nThe plan 2026-q3-review.\n"
        p = self.scratch(doc)
        try:
            self.assertEqual(pkgdocs.check(p.cfg), [])
            p.write("app/main.py", SRC + "".join(f"y = 1  # {line}\n" for line in doc.splitlines()))
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_ids_of_logged_tasks_and_the_planes_stamp_ids_are_flagged(self):
        p = self.scratch("Added by 0007-add-login.\nSee task 7.\nDone in 0007.\nRuled in sm-20261110T000000Z-abcd.\n"
                         "Per Task: 1.\n")
        try:
            errs = failures(p)
            self.assertRegex(errs, r"app/\.claude\.md:3:.*names delivery id\(s\) 0007-add-login;")
            self.assertRegex(errs, r"app/\.claude\.md:4:.*names delivery id\(s\) task 7;")
            self.assertRegex(errs, r"app/\.claude\.md:5:.*names delivery id\(s\) 0007;")
            self.assertRegex(errs, r"app/\.claude\.md:6:.*names delivery id\(s\) sm-20261110T000000Z-abcd;")
            self.assertRegex(errs, r"app/\.claude\.md:7:.*names delivery id\(s\) Task: 1;")
            self.assertEqual(len(errs.splitlines()), 5, errs)
        finally:
            p.cleanup()

    def test_a_task_not_in_the_log_is_not_an_id(self):
        p = self.scratch("Not 0002-other-thing, task 3, 0008 or task #0042.\n")
        try:
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_a_task_id_followed_by_a_file_extension_is_a_name(self):
        p = self.scratch("The tasks/0007-add-login.md file and 0001-setup.sh.\n")
        try:
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_with_no_task_log_the_stamp_ids_are_still_flagged(self):
        p = Product({"package_docs": {}})
        try:
            p.write("lib/.claude.md", f"# lib\n\nSee 0001-setup, task 1 and 0001.\n{FINDING}\n")
            p.write("lib/q.sql", "select 1;\n" * 10)
            errs = pkgdocs.check(p.cfg)
            self.assertEqual(len(errs), 1, errs)
            self.assertRegex(errs[0], rf"lib/\.claude\.md:4:.*{re.escape(FINDING)}")
        finally:
            p.cleanup()

    def test_the_off_switch_still_turns_real_ids_off(self):
        p = self.scratch("Added by 0007-add-login.\n", no_delivery_ids=False)
        try:
            self.assertEqual(pkgdocs.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_the_no_ids_rule_matches_only_logged_tasks_too(self):
        p = self.scratch("", rules={"no_ids": {"globs": ["docs/*.md"]}})
        try:
            p.write("docs/a.md", "chmod 0644, 0001-init.sql, task 2026, plan 2026-q3-review.\n"
                                  "Added by 0007-add-login, task 7 and 0001.\n")
            self.assertEqual(failures(p), "rule no_ids: docs/a.md:2 carries delivery id(s) 0007-add-login, task 7, "
                                          "0001; ids belong in the task log, not the code")
        finally:
            p.cleanup()

    def test_one_docs_check_reads_the_task_log_once(self):
        p = self.scratch("Added by 0007-add-login.\n", rules={"no_ids": {"globs": ["docs/*.md"]}})
        try:
            p.write("docs/a.md", "task 7\n")
            with mock.patch.object(tasklog, "task_numbers", wraps=tasklog.task_numbers) as read:
                errs = failures(p)
            self.assertEqual(read.call_count, 1)
            self.assertIn("app/.claude.md:3:", errs)
            self.assertIn("rule no_ids: docs/a.md:1", errs)
        finally:
            p.cleanup()


class Patterns(unittest.TestCase):
    def test_the_planes_ids_match_whole(self):
        rx = re.compile("|".join(f"(?:{x})" for x in refs.DEFAULT.delivery_id_patterns(["0042", "0007"])))
        for s in ("0042", "0042-fix-it", "task 42", "Task #0042", "task 07", "Task: 7", "TASK:  0042", RULING,
                  FINDING, "sh-20261001T120000Z-00ff"):
            self.assertEqual([m.group(0) for m in rx.finditer(f"see {s} here")], [s], s)
        self.assertEqual(rx.findall("added in 0042."), ["0042"])
        self.assertEqual(rx.findall("added in 0042-fix-it."), ["0042-fix-it"])
        for s in ("1.0042", "0042.5", "0042.x", "0042-fix-it.md", "2026", "x0042", "sm-2026",
                  "ar-20261001T120000Z-0f3c5", "ADR-0031", "0043", "0043-fix-it", "task 43", "task 420", "task 00042",
                  "task 142"):
            self.assertEqual(rx.findall(f"see {s} here"), [], s)

    def test_no_task_numbers_give_no_task_patterns(self):
        self.assertEqual(refs.DEFAULT.task_mention_patterns([]), ())
        self.assertEqual(refs.DEFAULT.task_mention_patterns(["42", "00042"]), ())   # not at the width
        self.assertEqual(len(refs.DEFAULT.delivery_id_patterns([])), 2)

    def test_a_number_that_is_not_zero_padded_is_never_bare(self):
        rx = re.compile("|".join(f"(?:{x})" for x in refs.DEFAULT.task_mention_patterns(["1234"])))
        self.assertEqual(rx.findall("in 1234, 1234-the-id and task 1234"), ["1234-the-id", "task 1234"])


if __name__ == "__main__":
    unittest.main()
