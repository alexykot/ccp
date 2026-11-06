"""Doc checks per language (SPEC §21): the core, the language packs, docs.checks and the opt-in rules."""
from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stdout

from ccp import cli, config, docrules, doclang, pkgdocs
from tests.helpers import Product

SRC = "\n".join(f"x{i} = {i}" for i in range(40)) + "\n"


class Languages(unittest.TestCase):
    def test_none_runs_the_core_only(self):
        p = Product({"package_docs": {"language": "none", "docstring_globs": ["app/**/*.py"]}})
        try:
            p.write("app/.claude.md", "# app\n")
            p.write("app/main.py", SRC)                      # no docstring: no pack, no rule
            p.write("app/data.sql", "select 1;\n" * 10)
            self.assertEqual(pkgdocs.check(p.cfg), [])
            self.assertNotIn(".py", pkgdocs.suffixes(p.cfg))  # .py is the Python pack's
            p.write("lib/q.sql", "select 1;\n")                # the core still judges coverage
            self.assertIn("lib: no .claude.md", "\n".join(pkgdocs.check(p.cfg)))
        finally:
            p.cleanup()

    def test_python_pack_docstrings_and_opt_in_call_bullets(self):
        p = Product({"package_docs": {"docstring_globs": ["app/**/*.py"], "rules": {"no_call_bullets": True}}})
        try:
            p.write("app/.claude.md", "# app\n")
            p.write("app/ok.py", '"""Does one thing."""\n' + SRC)
            p.write("app/none.py", SRC)
            p.write("app/api.py", '"""The API.\n\n- `load(path)`: reads\n- `save()`: writes\n"""\n' + SRC)
            p.write("app/bad.py", "def (:\n")
            errs = "\n".join(pkgdocs.check(p.cfg))
            self.assertIn("app/none.py: no module docstring", errs)
            self.assertIn("app/api.py: module docstring lists 2 function(s)", errs)
            self.assertIn("app/bad.py: does not parse", errs)
            self.assertNotIn("app/ok.py", errs)
            self.assertIn(".py", pkgdocs.suffixes(p.cfg))
            self.assertIn("__pycache__", pkgdocs.exempt_dirs(p.cfg))
        finally:
            p.cleanup()

    def test_defaults_equal_the_old_checks(self):
        # No call-bullet rule unless named; files under .venv are still read, __pycache__ is not.
        p = Product({"package_docs": {"docstring_globs": ["**/*.py"]}})
        try:
            p.write("app/.claude.md", "# app\n")
            p.write("app/api.py", '"""The API.\n\n- `load(path)`: reads\n"""\n' + SRC)
            p.write(".venv/lib/x.py", SRC)
            p.write("app/__pycache__/y.py", SRC)
            errs = "\n".join(pkgdocs.check(p.cfg))
            self.assertNotIn("call bullets", errs)
            self.assertIn(".venv/lib/x.py: no module docstring", errs)
            self.assertNotIn("__pycache__", errs)
        finally:
            p.cleanup()

    def test_language_none_with_docstring_globs_warns(self):
        p = Product({"package_docs": {"language": "none", "docstring_globs": ["app/*.py"]}})
        try:
            self.assertIn("language is none", "\n".join(pkgdocs.notes(p.cfg)))
        finally:
            p.cleanup()

    def test_an_unknown_language_is_a_config_error_naming_the_packs(self):
        p = Product()
        try:
            (p.root / "docs/delivery/plane.json").write_text('{"project_id": "demo", "package_docs": {"language": "cobol"}}')
            with self.assertRaisesRegex(config.ConfigError, r"'cobol' is not one of none, python"):
                config.load(p.root)
        finally:
            p.cleanup()
        self.assertEqual(doclang.NAMES, ("none", "python"))

    def test_explicit_suffixes_replace_core_and_pack(self):
        p = Product({"package_docs": {"source_suffixes": [".go"], "path_ref_suffixes": [".go"]}})
        try:
            self.assertEqual(pkgdocs.suffixes(p.cfg), {".go"})
            p.write("svc/.claude.md", "# svc\n\nSee `svc/gone.go` and `svc/old.py`.\n")
            p.write("svc/main.go", "package main\n" * 10)
            errs = "\n".join(pkgdocs.check(p.cfg))
            self.assertIn("names `svc/gone.go`", errs)
            self.assertNotIn("old.py", errs)                  # .py is no longer a path suffix here
        finally:
            p.cleanup()


class DocsChecks(unittest.TestCase):
    def test_docs_checks_run_in_docs_check_without_a_rule_id(self):
        p = Product({"docs": {"checks": [{"id": "links", "cmd": "true"}, {"id": "spell", "cmd": "echo bad; exit 3"}]}})
        try:
            p.index()
            out = io.StringIO()
            with redirect_stdout(out):
                code = cli.cmd_docs_check(p.cfg, None)
            self.assertEqual(code, 1)
            self.assertIn("docs check spell: `echo bad; exit 3` exited 3: bad", out.getvalue())
            self.assertNotIn("check links", out.getvalue())
        finally:
            p.cleanup()

    def test_bad_docs_checks_are_refused(self):
        for bad in ([{"id": "a"}], [{"id": "a", "cmd": "x"}, {"id": "a", "cmd": "y"}], [{"cmd": "x"}],
                    [{"id": "a", "cmd": "x", "extra": 1}]):
            p = Product()
            try:
                (p.root / "docs/delivery/plane.json").write_text(
                    __import__("json").dumps({"project_id": "demo", "docs": {"checks": bad}}))
                with self.assertRaises(config.ConfigError):
                    config.load(p.root)
            finally:
                p.cleanup()


class Rules(unittest.TestCase):
    def product(self, rules, **extra):
        return Product({"package_docs": {"language": "none", "rules": rules}, **extra})

    def test_citations_spec_refs_and_heading_links(self):
        p = self.product({"citations": {"globs": ["src/**/*.md", "src/**/*.py"], "targets": ["docs/SPEC.md"]}})
        try:
            p.write("docs/SPEC.md", "# Spec\n\n## S1 — One\n\n## S2 — Two\n\n### S2.4 Sub\n\n## Deploy steps\n\n"
                    "## Deploy steps\n\n```\n## S9 not a heading\n```\n")
            p.write("src/.claude.md", "# src\n\nPer S1–S2, S2.4 and S2.7. See [d](../docs/SPEC.md#deploy-steps-1).\n")
            p.write("src/a.py", "# S2\nx = 1\n")
            self.assertEqual(docrules.check(p.cfg), [])
            p.write("src/a.py", "# S2 and S7, S5–S3\n```\nS8 in a fence\n```\n")
            p.write("src/.claude.md", "# src\n\nSee [x](../docs/SPEC.md#gone), [y](../docs/NOPE.md#a), S9.\n")
            errs = "\n".join(docrules.check(p.cfg))
            self.assertIn("src/a.py:1 cites S7", errs)
            self.assertIn("src/a.py:1 cites the reversed range S5–S3", errs)
            self.assertNotIn("S8", errs)
            self.assertIn("src/.claude.md:3 cites S9", errs)       # a fenced heading is not a heading
            self.assertIn("a heading ../docs/SPEC.md does not have", errs)
            self.assertIn("../docs/NOPE.md does not exist", errs)
        finally:
            p.cleanup()

    def test_citations_are_refs_not_words(self):
        p = self.product({"citations": {"globs": ["src/*.py"], "targets": ["docs/SPEC.md"],
                                        "ignore": [r"\bAWS\b"]}})
        try:
            p.write("docs/SPEC.md", "# Spec\n\n## S1 One\n")
            p.write("src/a.py", "S3-bucket, s3://x, MS3, path/S4, and on AWS S5 too\n")
            self.assertEqual(docrules.check(p.cfg), [])
        finally:
            p.cleanup()

    def test_slugs_follow_github(self):
        self.assertEqual(docrules.slugs(["Deploy steps", "Deploy steps", "Use `ccp` [now](x.md)!", "A_b-c"]),
                         {"deploy-steps", "deploy-steps-1", "use-ccp-now", "a_b-c"})

    def test_citations_follow_the_configured_spec_prefix(self):
        p = self.product({"citations": {"globs": ["src/*.py"], "targets": ["docs/SPEC.md"]}},
                         ids={"spec": {"prefix": "SEC"}})
        try:
            p.write("docs/SPEC.md", "# Spec\n\n## SEC4 Rules\n")
            p.write("src/a.py", "# SEC4, SEC5, and S9 is not a ref here\n")
            errs = "\n".join(docrules.check(p.cfg))
            self.assertEqual(errs.count("cites SEC5"), 1)
            self.assertNotIn("S9", errs)
        finally:
            p.cleanup()

    def test_no_ids_default_and_custom_patterns(self):
        p = self.product({"no_ids": {"globs": ["src/*.py", "tests/*.py"]}})
        try:
            p.write("src/a.py", "import os  # noqa: F401\nx = 1  # see 0042-fix-the-thing\n"
                                "# task 42, then 0123; 2026 and 1.0042 are not ids\n")
            p.write("tests/test_b.py", "def test_ok():\n    pass\n")
            errs = "\n".join(docrules.check(p.cfg))
            self.assertNotIn("F401", errs)                 # finding ids are the product's own patterns
            self.assertIn("src/a.py:2 carries delivery id(s) 0042-fix-the-thing", errs)
            self.assertIn("src/a.py:3 carries delivery id(s) task 42, 0123;", errs)
            self.assertNotIn("2026", errs)
            self.assertNotIn("test_b.py", errs)
        finally:
            p.cleanup()
        p = self.product({"no_ids": {"globs": ["src/*.py"], "patterns": [r"\bTKT-\d+\b", r"(?<!noqa: )\bF\d{2}\b"]}})
        try:
            p.write("src/a.py", "x = 1  # TKT-12, F07, 0042-fix-the-thing  # noqa: F40\n")
            errs = "\n".join(docrules.check(p.cfg))
            self.assertIn("delivery id(s) TKT-12, F07;", errs)
        finally:
            p.cleanup()

    def test_history_paths_are_skipped_and_listed(self):
        p = self.product({"no_ids": {"globs": ["**/*.md"]}, "history_attr": "history"})
        try:
            subprocess.run(["git", "init", "-q"], cwd=p.root, check=True)
            p.write(".gitattributes", "docs/log/** history\n")
            p.write("docs/log/2026.md", "merged 0042-fix-the-thing\n")
            p.write("src/notes.md", "do 0043-another-thing\n")
            subprocess.run(["git", "add", "-A"], cwd=p.root, check=True)
            self.assertEqual(docrules.history_paths(p.cfg), {"docs/log/2026.md"})
            errs = "\n".join(docrules.check(p.cfg))
            self.assertIn("src/notes.md", errs)
            self.assertNotIn("docs/log/2026.md", errs)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.cmd_docs_history_paths(p.cfg, type("A", (), {"attr": None})()), 0)
            self.assertEqual(out.getvalue().split(), ["docs/log/2026.md"])
        finally:
            p.cleanup()

    def test_no_overlap(self):
        p = self.product({"no_overlap": True}, docs={"checks": [
            {"id": "a", "cmd": "python3 -m unittest tests.test_x"},
            {"id": "b", "cmd": "python3  -m unittest   tests.test_x"},
            {"id": "c", "cmd": "python3 tests/test_y.py && echo ok"},
            {"id": "d", "cmd": "pytest tests/test_y.py::Case"},
            {"id": "e", "cmd": "python3 -m unittest tests.test_z"},
            {"id": "f", "cmd": "python3 -m unittest tests.test_z.Case.test_one"}]})
        try:
            errs = "\n".join(docrules.check(p.cfg))
            self.assertIn("docs check a and docs check b run the same command", errs)
            self.assertIn("docs check c and docs check d both run tests.test_y", errs)
            self.assertIn("docs check e and docs check f both run tests.test_z", errs)
        finally:
            p.cleanup()

    def test_rules_are_off_until_named_and_validated(self):
        p = Product({"package_docs": {}})
        try:
            self.assertEqual(docrules.check(p.cfg), [])
        finally:
            p.cleanup()
        for bad in ({"citations": {"globs": ["x"]}}, {"no_ids": {"patterns": []}}, {"history_attr": ""},
                    {"no_overlap": "yes"}, {"spelling": True}, {"no_ids": {"globs": ["x"], "patterns": ["("]}},
                    {"citations": {"globs": ["x"], "targets": ["y"], "ignore": ["["]}}, {"no_call_bullets": 1}):
            p = Product()
            try:
                (p.root / "docs/delivery/plane.json").write_text(
                    __import__("json").dumps({"project_id": "demo", "package_docs": {"rules": bad}}))
                with self.assertRaises(config.ConfigError, msg=bad):
                    config.load(p.root)
            finally:
                p.cleanup()


if __name__ == "__main__":
    unittest.main()


class Runner(unittest.TestCase):
    def test_a_timeout_kills_the_process_group_and_output_is_capped(self):
        import time
        from ccp import rules
        p = Product()
        try:
            marker = p.root / "late"
            start = time.time()
            errs = rules.run_checks(p.cfg, [{"id": "slow", "cmd": f"(sleep 3; touch {marker}) & sleep 30",
                                            "timeout_seconds": 1}])
            self.assertLess(time.time() - start, 10)
            self.assertIn("slow: `", errs[0])
            self.assertIn("timed out after 1s", errs[0])
            time.sleep(3.5)
            self.assertFalse(marker.exists())                 # the background child died with the group
            code, text = rules.run_command(p.cfg, "python3 -c \"print('x' * 50000); raise SystemExit(2)\"", 30)
            self.assertEqual(code, 2)
            self.assertLessEqual(len(text), rules.OUTPUT_CAP)
        finally:
            p.cleanup()
