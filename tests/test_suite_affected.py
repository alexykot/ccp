"""ccp suite affected (SPEC §14.7): the test modules a change touches, read by the product's language pack."""
from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli
from tests.helpers import Product


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True).stdout.strip()


class Affected(unittest.TestCase):
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

    def test_a_changed_module_lists_only_the_tests_that_import_it(self):
        self.p.write("pkg/a.py", "X = 3\n")
        self.assertEqual(self.affected(), ["tests.test_a"])

    def test_no_change_prints_nothing_and_exits_0(self):
        code, lines, _ = self.run_cli()
        self.assertEqual((code, lines), (0, []))

    def test_a_change_no_test_depends_on_prints_nothing(self):
        self.p.write("pkg/c.py", "Z = 1\n")
        code, lines, _ = self.run_cli()
        self.assertEqual((code, lines), (0, []))

    def test_since_takes_the_commits_after_the_ref_and_the_uncommitted_change(self):
        base = git(self.p.root, "rev-parse", "HEAD")
        self.p.write("pkg/a.py", "X = 3\n")
        self.commit("change a")
        self.assertEqual(self.affected(), [])  # HEAD, the default, has it already
        self.assertEqual(self.affected("--since", base), ["tests.test_a"])
        self.p.write("pkg/b.py", "Y = 3\n")
        self.assertEqual(self.affected("--since", base), ["tests.test_a", "tests.test_b"])

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

    def test_a_pack_with_no_test_reader_is_refused(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "suite", "affected", "--paths", "pkg/a.py"])
        self.assertEqual(code, 2)
        self.assertIn("'none'", err.getvalue())


if __name__ == "__main__":
    unittest.main()
