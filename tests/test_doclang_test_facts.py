"""The language pack owns what the plane knows about its language's tests (house rule E18): the Python
pack's fields, the one lookup `doclang.for_tests`, and the readers in `ccp suite` and `ccp mutate` that ask it."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, doclang, mutate, suite
from ccp.doclang import python as py_pack
from ccp.queue import QueueError
from tests.helpers import Product

REPO = Path(__file__).resolve().parents[1]


def tests_cfg(language: str | None = None, extra: dict | None = None) -> config.Config:
    """A product's config with `language` (None: it names none, as in the grace release) and `extra`."""
    p = Product({**({"language": language} if language is not None else {}), **(extra or {})}, bare=True)
    cfg = p.cfg
    p.cleanup()
    return cfg


class PythonPack(unittest.TestCase):
    def setUp(self):
        self.pack = doclang.get("python")

    def test_the_pack_holds_unittests_patterns_and_command(self):
        self.assertEqual(self.pack.count_re, r"^Ran (\d+) tests? in ")
        self.assertEqual(self.pack.test_command, "python3 -m unittest")
        self.assertEqual(self.pack.test_glob, "test*.py")
        self.assertEqual(self.pack.unbuilt_re, (r"^(?:SyntaxError|IndentationError|TabError): ",
                                                r"^ImportError: Failed to import test module: "))
        self.assertEqual(sorted(self.pack.summary), ["failed_re", "section_re", "skipped_re"])
        self.assertIsNotNone(self.pack.affected)
        self.assertIsNotNone(self.pack.suite_size)

    def test_the_did_not_build_lines_match_what_unittest_prints_when_a_module_does_not_compile_or_import(self):
        lines = ["SyntaxError: invalid syntax", "IndentationError: unexpected indent", "TabError: inconsistent use",
                 "ImportError: Failed to import test module: test_m"]
        others = ["AssertionError: 3 != 2", "ImportError: cannot import name 'add' from 'calc'", "FAIL: test_a (m.T)"]
        matches = lambda ln: any(re.search(p, ln) for p in self.pack.unbuilt_re)  # noqa: E731
        self.assertEqual([ln for ln in lines + others if matches(ln)], lines)

    def test_the_summary_patterns_read_a_failing_run(self):
        failed = [re.compile(p) for p in self.pack.summary["failed_re"]]
        line = "FAILED (failures=2, errors=3, skipped=4)"
        self.assertEqual([m.group(1) for r in failed if (m := r.search(line))], ["2", "3"])
        self.assertEqual(re.search(self.pack.summary["skipped_re"], line).group(1), "4")
        self.assertIsNotNone(re.search(self.pack.summary["section_re"], "ERROR: test_a (m.T.test_a)"))
        self.assertIsNone(re.search(self.pack.summary["section_re"], "OK"))

    def test_the_none_pack_knows_no_test_facts(self):
        none = doclang.get("none")
        self.assertEqual((none.count_re, none.summary, none.test_glob), ("", {}, ""))
        self.assertEqual((none.affected, none.suite_size, none.test_command), (None, None, None))
        self.assertEqual(none.unbuilt_re, ())

    def test_the_reader_lists_the_test_modules_a_change_touches(self):
        files = ["pkg/__init__.py", "pkg/a.py", "tests/test_a.py", "tests/test_b.py", "tests/helper.py"]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, text in {"pkg/__init__.py": "", "pkg/a.py": "X = 1\n", "tests/test_a.py": "from pkg import a\n",
                              "tests/test_b.py": "import os\n", "tests/helper.py": "from pkg import a\n"}.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text)
            self.assertEqual(self.pack.affected(root, ["pkg/a.py"], files), ["tests.test_a"])
            self.assertEqual(self.pack.suite_size(root, files), 2)


class ForTests(unittest.TestCase):
    def test_a_product_that_names_no_language_gets_the_python_pack_as_before(self):
        pack = doclang.for_tests(tests_cfg())
        self.assertEqual((pack.name, pack.test_command), ("python", "python3 -m unittest"))
        self.assertIs(pack.affected, py_pack.PACK.affected)

    def test_no_config_gets_the_python_pack(self):
        self.assertEqual(doclang.for_tests(None).name, "python")

    def test_a_python_product_gets_the_python_pack(self):
        pack = doclang.for_tests(tests_cfg("python"))
        self.assertEqual((pack.name, pack.count_re, pack.summary), ("python", py_pack.COUNT_RE, py_pack.SUMMARY))

    def test_a_none_product_has_no_reader_command_or_output_patterns(self):
        pack = doclang.for_tests(tests_cfg("none"))
        self.assertEqual((pack.name, pack.affected, pack.suite_size, pack.test_command), ("none", None, None, None))
        self.assertEqual((pack.count_re, pack.summary), ("", {}))


class Readers(unittest.TestCase):
    def test_the_summary_reader_takes_the_packs_patterns_for_what_the_product_leaves_out(self):
        scfg = suite._summary_cfg(tests_cfg("python"))
        self.assertEqual([p.pattern for p in scfg["failed_re"]], py_pack.SUMMARY["failed_re"])
        self.assertEqual([p.pattern for p in scfg["section_re"]], [py_pack.SUMMARY["section_re"]])
        mine = suite._summary_cfg(tests_cfg("python", {"suite": {"summary": {"failed_re": r"(\d+) failed"}}}))
        self.assertEqual([p.pattern for p in mine["failed_re"]], [r"(\d+) failed"])
        self.assertEqual([p.pattern for p in mine["skipped_re"]], [py_pack.SUMMARY["skipped_re"]])

    def test_the_summary_reader_takes_the_pack_chosen_by_the_lookup(self):
        pack = doclang.Pack("fake", (), (), (), summary={"failed_re": "^BAD (\\d+)", "skipped_re": "^SKIP (\\d+)",
                                                         "section_re": "^BROKE: "})
        with mock.patch.object(doclang, "for_tests", return_value=pack):
            scfg = suite._summary_cfg(None)
        self.assertEqual([p.pattern for p in scfg["failed_re"]], ["^BAD (\\d+)"])
        self.assertEqual([p.pattern for p in scfg["section_re"]], ["^BROKE: "])

    def test_the_count_reader_takes_the_packs_pattern_unless_the_product_sets_one(self):
        self.assertEqual([p.pattern for p in suite._count_res(tests_cfg("python"))], [py_pack.COUNT_RE.encode()])
        mine = tests_cfg("python", {"suite": {"count_re": r"^(\d+) passed"}})
        self.assertEqual([p.pattern for p in suite._count_res(mine)], [rb"^(\d+) passed"])
        pack = doclang.Pack("fake", (), (), (), count_re=r"^Counted (\d+)")
        with mock.patch.object(doclang, "for_tests", return_value=pack):
            self.assertEqual([p.pattern for p in suite._count_res(tests_cfg())], [rb"^Counted (\d+)"])

    def test_a_none_product_with_no_map_is_refused_a_reader_and_with_a_map_lists_the_mapped_tests(self):
        p = Product({"language": "none"})
        self.addCleanup(p.cleanup)
        subprocess.run(["git", "-C", str(p.root), "init", "-q", "-b", "main"], check=True)
        with self.assertRaises(QueueError) as cm:
            suite.affected(p.cfg, None, ["a.txt"])
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("python", str(cm.exception))
        self.assertIn("'none' has no test reader", str(cm.exception))
        mapped = Product({"language": "none", "suite": {"affected_map": {"a.*": ["t1"]}}})
        self.addCleanup(mapped.cleanup)
        self.assertEqual(suite.affected(mapped.cfg, None, ["a.txt"]), (["a.txt"], ["t1"]))

    def test_a_language_with_no_runner_is_refused(self):
        with self.assertRaises(QueueError) as cm:
            mutate._run(tests_cfg("none"), Path("."), "x", "t", ["a:b=>c"], [], None, None)
        self.assertEqual(cm.exception.code, 2)
        for named in ("mutate.command", "{test}", "sh {test}"):  # what to set, a whole-script test's form too
            self.assertIn(named, str(cm.exception))
        self.assertNotIn("unittest", str(cm.exception))

    def test_the_mutate_command_and_did_not_build_lines_come_from_the_pack_unless_the_product_sets_them(self):
        py, none = doclang.get("python"), doclang.get("none")
        self.assertEqual(mutate._command({"command": None}, py), "python3 -m unittest {test}")
        self.assertEqual(mutate._command({"command": "sh {test}"}, py), "sh {test}")
        self.assertIsNone(mutate._command({"command": None}, none))
        pats = mutate._unbuilt_patterns
        self.assertEqual([p.pattern for p in pats({"unbuilt_re": None}, py)], list(py_pack.UNBUILT_RE))
        self.assertEqual([p.pattern for p in pats({"unbuilt_re": "^BROKE"}, py)], ["^BROKE"])
        self.assertEqual([p.pattern for p in pats({"unbuilt_re": ["^A", "^B"]}, py)], ["^A", "^B"])
        self.assertEqual(pats({"unbuilt_re": None}, none), [])
        fake = doclang.Pack("fake", (), (), (), test_command="run-one", unbuilt_re=("^NO BUILD",))
        self.assertEqual(mutate._command({}, fake), "run-one {test}")
        self.assertEqual([p.pattern for p in pats({}, fake)], ["^NO BUILD"])


class CoreCheck(unittest.TestCase):
    def test_the_language_pack_check_is_declared(self):
        ids = [c["id"] for c in json.loads((REPO / "docs/delivery/plane.json").read_text())["architect"]["checks"]]
        self.assertIn("E18", ids)


if __name__ == "__main__":
    unittest.main()
