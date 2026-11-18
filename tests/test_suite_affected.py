"""ccp suite affected (SPEC §14.7): the test modules a change touches, read by the product's language pack, and
on stderr the command that runs them on the part lane."""
from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, suite
from tests.helpers import Product


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True).stdout.strip()


class Scratch:
    """A scratch Python product: tests/test_a.py imports pkg/a.py, tests/test_b.py imports pkg/b.py."""

    def setUp(self, cfg: dict | None = None):
        self.p = Product(cfg)
        self.addCleanup(self.p.cleanup)
        for rel, text in {
            "pkg/__init__.py": "",
            "pkg/a.py": "X = 1\n",
            "pkg/b.py": "Y = 2\n",
            "tests/__init__.py": "",
            "tests/test_a.py": "import unittest\nfrom pkg import a\n",
            "tests/test_b.py": "import unittest\nfrom pkg.b import Y\n",
        }.items():
            self.p.write(rel, text)
        git(self.p.root, "init", "-q", "-b", "main")
        self.commit("init")

    def commit(self, msg: str) -> str:
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", msg)
        return git(self.p.root, "rev-parse", "HEAD")

    def run_cli(self, *args: str) -> tuple[int, list[str], str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "suite", "affected", *args])
        return code, out.getvalue().splitlines(), err.getvalue()

    def affected(self, *args: str) -> list[str]:
        code, lines, err = self.run_cli(*args)
        self.assertEqual(code, 0, err)
        return lines


class Affected(Scratch, unittest.TestCase):
    def test_a_changed_module_lists_only_the_tests_that_import_it(self):
        self.p.write("pkg/a.py", "X = 3\n")
        self.assertEqual(self.affected(), ["tests.test_a"])

    def test_after_the_list_stderr_hands_the_command_that_runs_it_on_the_part_lane(self):
        code, lines, err = self.run_cli("--paths", "pkg/a.py")
        self.assertEqual((code, lines), (0, ["tests.test_a"]))
        self.assertIn("ccp suite run --lane part -- python3 -m unittest tests.test_a\n", err)
        code, lines, err = self.run_cli("--paths", "pkg/a.py", "pkg/b.py")
        self.assertEqual(lines, ["tests.test_a", "tests.test_b"])
        self.assertIn("ccp suite run --lane part -- python3 -m unittest tests.test_a tests.test_b\n", err)

    def test_the_command_names_the_lane_the_product_gives_the_part_role(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "suite": {"roles": {"part": "quick"}}}))
        _, lines, err = self.run_cli("--paths", "pkg/a.py")
        self.assertEqual(lines, ["tests.test_a"])
        self.assertIn("ccp suite run --lane quick -- python3 -m unittest tests.test_a", err)

    def test_a_language_with_no_command_named_gets_no_command_line(self):
        with mock.patch.dict(suite.AFFECTED_COMMANDS, clear=True):
            code, lines, err = self.run_cli("--paths", "pkg/a.py")
        self.assertEqual((code, lines), (0, ["tests.test_a"]))
        self.assertNotIn("ccp suite run", err)

    def test_no_change_prints_nothing_and_exits_0(self):
        code, lines, _ = self.run_cli()
        self.assertEqual((code, lines), (0, []))

    def test_a_change_no_test_depends_on_prints_nothing(self):
        self.p.write("pkg/c.py", "Z = 1\n")
        code, lines, err = self.run_cli()
        self.assertEqual((code, lines), (0, []))
        self.assertNotIn("ccp suite run", err)

    def test_since_takes_the_commits_after_the_ref_and_the_uncommitted_change(self):
        base = git(self.p.root, "rev-parse", "HEAD")
        self.p.write("pkg/a.py", "X = 3\n")
        self.commit("change a")
        self.assertEqual(self.affected(), [])  # HEAD, the default, has it already
        self.assertEqual(self.affected("--since", base), ["tests.test_a"])
        self.p.write("pkg/b.py", "Y = 3\n")
        self.assertEqual(self.affected("--since", base), ["tests.test_a", "tests.test_b"])

    def test_since_takes_a_range_as_the_files_changed_in_it_only(self):
        a = git(self.p.root, "rev-parse", "HEAD")
        self.p.write("pkg/a.py", "X = 3\n")
        b = self.commit("change a")
        self.p.write("pkg/b.py", "Y = 3\n")
        c = self.commit("change b")
        self.p.write("pkg/a.py", "X = 4\n")  # uncommitted: no part of a range
        self.p.write("tests/test_new.py", "import unittest\n")  # untracked: no part of a range either
        code, lines, err = self.run_cli("--since", f"{b}..{c}")
        self.assertEqual((code, lines), (0, ["tests.test_b"]), err)
        self.assertEqual(self.affected("--since", f"{a}..{b}"), ["tests.test_a"])
        self.assertEqual(self.affected("--since", "HEAD~2..HEAD~1"), ["tests.test_a"])
        self.assertEqual(self.affected("--since", f"{a}..{c}"), ["tests.test_a", "tests.test_b"])
        self.assertEqual(self.affected("--since", b), ["tests.test_a", "tests.test_b", "tests.test_new"])

    def test_a_range_with_an_end_git_cannot_read_is_refused(self):
        b = git(self.p.root, "rev-parse", "HEAD")
        for since in (f"{b}..no-such-ref", f"no-such-ref..{b}", f"{b}..-x", f"-x..{b}", f"{b}...{b}"):
            code, lines, err = self.run_cli("--since", since)
            self.assertEqual((code, lines), (2, []), since)
            self.assertIn(repr(since), err)
        self.assertFalse((self.p.root / "x").exists())

    def test_a_dotfile_has_no_extension_so_no_test_matches_it_by_name(self):
        self.p.write(".gitignore", "build/\n")
        self.p.write("tests/test_ignore.py", "IGNORE = ROOT / '.gitignore'\n")
        self.commit("ignore test")
        self.assertEqual(self.affected("--paths", ".gitignore"), [])
        self.p.write("tests/test_cfg.py", "CFG = ROOT / 'setup.cfg'\n")
        self.commit("cfg test")
        self.assertEqual(self.affected("--paths", "setup.cfg"), ["tests.test_cfg"])  # a name with an extension does

    def test_an_untracked_module_counts_and_an_ignored_one_does_not(self):
        self.p.write("tests/test_c.py", "import pkg.c\n")
        self.p.write("pkg/c.py", "Z = 1\n")
        self.assertEqual(self.affected(), ["tests.test_c"])
        self.p.write(".gitignore", "pkg/c.py\ntests/test_c.py\n")
        self.assertEqual(self.affected(), [])

    def test_a_renamed_module_counts_by_its_old_name(self):
        git(self.p.root, "mv", "pkg/a.py", "pkg/renamed.py")
        self.assertEqual(self.affected(), ["tests.test_a"])

    def test_paths_name_the_change_instead_of_git(self):
        self.p.write("pkg/a.py", "X = 3\n")
        self.assertEqual(self.affected("--paths", "pkg/b.py"), ["tests.test_b"])
        self.assertEqual(self.affected("--paths", "./pkg/b.py", str(self.p.root / "pkg/a.py")),
                         ["tests.test_a", "tests.test_b"])

    def test_a_path_outside_the_root_is_refused(self):
        code, lines, _ = self.run_cli("--paths", "/elsewhere/pkg/a.py")
        self.assertEqual((code, lines), (2, []))

    def test_a_ref_git_cannot_read_is_refused(self):
        code, lines, _ = self.run_cli("--since", "no-such-ref")
        self.assertEqual((code, lines), (2, []))

    def test_a_ref_starting_with_a_dash_is_an_unknown_ref_not_an_option(self):
        for args in (("--since", "-x"), ("--since=-x",), ("--since", "--output=x")):
            code, lines, err = self.run_cli(*args)
            self.assertEqual((code, lines), (2, []), args)
            self.assertIn(repr(args[-1].removeprefix("--since=")), err)
        self.assertFalse((self.p.root / "x").exists())  # git never read it as its --output option

    def test_a_name_without_an_extension_or_a_directory_is_no_name_match(self):
        self.p.write("Makefile", "all:\n")
        self.p.write("assets.v2/logo.txt", "x\n")
        self.p.write("tests/test_build.py", "RULES = 'Makefile'\nPKG = 'pkg'\nART = 'assets.v2'\n")
        self.commit("build test")
        for path in ("Makefile", "pkg/", "pkg", "assets.v2", "."):
            self.assertEqual(self.affected("--paths", path), [], path)
        self.p.write("tests/test_doc.py", "DOC = 'guide.md'\n")
        self.commit("doc test")
        self.assertEqual(self.affected("--paths", "docs/guide.md"), ["tests.test_doc"])  # a file's name still counts

    def test_paths_are_normalised_against_the_root(self):
        want = self.affected("--paths", "pkg/a.py")
        self.assertEqual(want, ["tests.test_a"])
        for path in ("./pkg/../pkg/a.py", "pkg/./a.py", "pkg//a.py", "tests/../pkg/a.py"):
            self.assertEqual(self.affected("--paths", path), want, path)
        for path in ("../pkg/a.py", "pkg/../../a.py"):
            code, lines, _ = self.run_cli("--paths", path)
            self.assertEqual((code, lines), (2, []), path)

    def test_since_and_paths_do_not_mix(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as e:
            cli.main(["--root", str(self.p.root), "suite", "affected", "--since", "HEAD", "--paths", "pkg/a.py"])
        self.assertEqual(e.exception.code, 2)

    def test_importing_a_submodule_imports_its_package(self):
        self.p.write("pkg/__init__.py", "VERSION = 2\n")
        self.assertEqual(self.affected(), ["tests.test_a", "tests.test_b"])

    def test_a_package_init_reaches_its_imports_one_level_only(self):
        self.p.write("pkg/sub/__init__.py", "from pkg.sub import inner\n")
        self.p.write("pkg/sub/inner.py", "from pkg.sub.deep import leaf\n")
        self.p.write("pkg/sub/deep/__init__.py", "from pkg.sub.deep import leaf\n")
        self.p.write("pkg/sub/deep/leaf.py", "W = 1\n")
        self.p.write("tests/test_sub.py", "import pkg.sub\n")
        self.commit("sub")
        self.assertEqual(self.affected("--paths", "pkg/sub/inner.py"), ["tests.test_sub"])
        self.assertEqual(self.affected("--paths", "pkg/sub/deep/leaf.py"), [])

    def test_relative_and_function_level_imports_count(self):
        self.p.write("tests/helpers.py", "H = 1\n")
        self.p.write("tests/test_rel.py", "from .helpers import H\n")
        self.p.write("tests/test_late.py", "def test():\n    from pkg import b\n")
        self.commit("more")
        self.assertEqual(self.affected("--paths", "tests/helpers.py"), ["tests.test_rel"])
        self.assertEqual(self.affected("--paths", "pkg/b.py"), ["tests.test_b", "tests.test_late"])

    def test_a_test_that_names_a_changed_file_counts(self):
        self.p.write("tests/test_doc.py", "DOC = ROOT / 'docs' / 'guide.md'\nDATA = 'data.py'\n")
        self.commit("doc test")
        self.assertEqual(self.affected("--paths", "docs/guide.md"), ["tests.test_doc"])
        self.assertEqual(self.affected("--paths", "pkg/a.py"), ["tests.test_a"])  # 'data.py' is not 'a.py'

    def test_a_changed_test_module_lists_itself_and_a_deleted_one_does_not(self):
        self.p.write("tests/test_b.py", "import unittest\n")
        self.assertEqual(self.affected(), ["tests.test_b"])
        (self.p.root / "tests/test_b.py").unlink()
        self.assertEqual(self.affected(), [])

    def test_only_test_modules_are_listed(self):
        self.p.write("tests/helpers.py", "from pkg import a\n")
        self.p.write("tools/check.py", "from pkg import a\n")
        self.commit("not tests")
        self.p.write("pkg/a.py", "X = 3\n")
        self.assertEqual(self.affected(), ["tests.test_a"])

    def test_a_test_that_does_not_parse_is_read_for_names_only(self):
        self.p.write("tests/test_broken.py", "from pkg import a\nif (:\n# a.py\n")
        self.commit("broken")
        self.assertEqual(self.affected("--paths", "pkg/a.py"), ["tests.test_a", "tests.test_broken"])
        self.assertEqual(self.affected("--paths", "pkg/b.py"), ["tests.test_b"])


class Language(unittest.TestCase):
    def setUp(self):
        self.p = Product({"package_docs": {"language": "none"}})
        self.addCleanup(self.p.cleanup)
        git(self.p.root, "init", "-q", "-b", "main")

    def run_cli(self, *args: str) -> tuple[int, list[str], str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "suite", "affected", *args])
        return code, out.getvalue().splitlines(), err.getvalue()

    def test_a_pack_with_no_test_reader_is_refused(self):
        code, _, err = self.run_cli("--paths", "pkg/a.py")
        self.assertEqual(code, 2)
        self.assertIn("'none'", err)
        self.assertIn("suite.affected_map", err)

    def test_a_pack_with_no_reader_reads_the_tests_from_the_products_map_alone(self):
        amap = {"internal/store/*": ["./internal/store/..."], "ops/*.sh": ["ops/test_ops.sh"]}
        self.p.write("docs/delivery/plane.json", json.dumps(
            {"project_id": "demo", "package_docs": {"language": "none"}, "suite": {"affected_map": amap}}))
        code, lines, err = self.run_cli("--paths", "internal/store/db.go", "ops/deploy.sh", "docs/readme.md")
        self.assertEqual((code, lines), (0, ["./internal/store/...", "ops/test_ops.sh"]), err)
        self.assertNotIn("ccp suite run", err)  # no command is named for a language with no reader
        code, lines, err = self.run_cli("--paths", "docs/readme.md")
        self.assertEqual((code, lines), (0, []), err)
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "package_docs": {"language": "none"}}))
        code, lines, err = self.run_cli("--paths", "internal/store/db.go", "ops/deploy.sh", "docs/readme.md")
        self.assertEqual((code, lines), (2, []))
        self.assertIn("suite.affected_map", err)

    def test_a_glob_star_crosses_directories_and_matches_case_exactly(self):
        self.p.write("docs/delivery/plane.json", json.dumps(
            {"project_id": "demo", "package_docs": {"language": "none"},
             "suite": {"affected_map": {"internal/*": ["./internal/..."], "*.SH": ["upper"]}}}))
        code, lines, err = self.run_cli("--paths", "internal/store/deep/db.go", "ops/x.sh")
        self.assertEqual((code, lines), (0, ["./internal/..."]), err)


class AffectedMap(Scratch, unittest.TestCase):
    """The Python product, with a map from shell scripts to a test module the reader cannot see."""

    def setUp(self):
        super().setUp({"suite": {"affected_map": {"scripts/*.sh": ["tests.test_scripts"],
                                                  "pkg/*.py": ["tests.test_a"]}}})

    def test_the_map_adds_to_what_the_reader_finds_sorted_each_once(self):
        code, lines, err = self.run_cli("--paths", "pkg/a.py", "scripts/x.sh")
        self.assertEqual((code, lines), (0, ["tests.test_a", "tests.test_scripts"]), err)
        self.assertIn("-- python3 -m unittest tests.test_a tests.test_scripts\n", err)
        self.assertEqual(self.affected("--paths", "pkg/b.py"), ["tests.test_a", "tests.test_b"])
        self.assertEqual(self.affected("--paths", "scripts/x.sh"), ["tests.test_scripts"])

    def test_a_changed_script_under_git_reaches_the_map(self):
        self.p.write("scripts/x.sh", "echo hi\n")
        self.assertEqual(self.affected(), ["tests.test_scripts"])


class AffectedMapConfig(unittest.TestCase):
    def test_a_map_of_another_shape_fails_the_load_naming_the_key(self):
        for bad in (["scripts/*.sh"], {"scripts/*.sh": "tests.test_scripts"}, {"scripts/*.sh": []},
                    {"scripts/*.sh": [""]}, {"": ["t"]}, {"x": [1]}):
            p = Product({"suite": {"affected_map": bad}})
            try:
                with self.assertRaisesRegex(config.ConfigError, r"suite\.affected_map", msg=bad):
                    p.cfg
            finally:
                p.cleanup()
        p, plain = Product({"suite": {"affected_map": {"a/*": ["t"]}}}), Product()
        self.addCleanup(p.cleanup)
        self.addCleanup(plain.cleanup)
        self.assertEqual(p.cfg.suite["affected_map"], {"a/*": ["t"]})
        self.assertEqual(plain.cfg.suite["affected_map"], {})

    def test_the_schema_lists_the_key(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(schema["properties"]["suite"]["properties"]["affected_map"]["default"], {})


if __name__ == "__main__":
    unittest.main()
