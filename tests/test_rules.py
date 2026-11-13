"""House rules (SPEC §20.1) in `ccp docs check`, and the `architect` block's validation (§8.1).
Acceptance check docs/design/architect.md #5 is named below."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, rules
from tests.helpers import Product

RULES = """# Engineering rules

> Header prose that mentions a `check:` is not a rule.

## Architecture

- **E1** The core never imports the paused code.
  check: command
- **E2** Each concept has one registry.
  check: pass

## Budgets

- **E7** No source file over 5 lines.
  check: budget
"""


class RulesDoc(unittest.TestCase):
    def setUp(self):
        self.p = Product({"architect": {"rules_doc": "docs/ENGINEERING.md", "rules_max_lines": 20,
                                        "checks": [{"id": "E1", "cmd": "true"}],
                                        "budgets": [{"id": "E7", "glob": "app/**/*.py", "max_lines": 5}]}})
        self.p.write("docs/ENGINEERING.md", RULES)
        self.p.write("app/a.py", "x = 1\n")
        self.p.task("0001-a")
        self.p.index()

    def tearDown(self):
        self.p.cleanup()

    def docs_check(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "docs", "check"])
        return code, out.getvalue()

    def test_clean(self):
        self.assertEqual(self.docs_check(), (0, "docs: clean\n"))

    def test_acceptance_5_too_long_or_unchecked_rule_fails_docs_check(self):
        self.p.write("docs/ENGINEERING.md", RULES + "\n" * 20)
        code, out = self.docs_check()
        self.assertEqual(code, 1)
        self.assertIn("docs/ENGINEERING.md: 35 lines, over rules_max_lines 20", out)
        self.p.write("docs/ENGINEERING.md", RULES + "- **E9** Tests check behaviour, not wording.\n")
        code, out = self.docs_check()
        self.assertEqual(code, 1)
        self.assertIn("rule E9 has no `check:`", out)

    def test_prose_that_mentions_rules_or_checks_is_not_a_rule(self):
        self.p.write("docs/ENGINEERING.md", RULES.replace(
            "- **E2** Each concept has one registry.\n",
            "- **E2** Each concept has one registry, as the type check: mypy shows, and\n"
            "  E1, above, keeps the imports apart.\n"))
        self.assertEqual(rules.check_doc(self.p.cfg), [])

    def test_checks_and_budgets_must_match_rules(self):
        self.p.write("docs/ENGINEERING.md", RULES.replace("check: command", "check: budget").replace("check: pass", "check: maybe"))
        e = "\n".join(rules.check_doc(self.p.cfg))
        self.assertIn("rule E1 is checked by a budget, but architect.budgets has no E1", e)
        self.assertIn("rule E2: check 'maybe' is not pass, budget, command or docs", e)
        self.p.write("docs/ENGINEERING.md", RULES.replace("- **E1** The core never imports the paused code.\n  check: command\n", ""))
        self.assertIn("architect.checks: E1 names no rule in docs/ENGINEERING.md", "\n".join(rules.check_doc(self.p.cfg)))

    def test_missing_rules_doc_fails(self):
        (self.p.root / "docs/ENGINEERING.md").unlink()
        self.assertIn("docs/ENGINEERING.md: missing", "\n".join(rules.check(self.p.cfg)))

    def test_a_failing_command_check_fails_docs_check(self):
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["checks"] = [{"id": "E1", "cmd": "echo boom; exit 3"}]
        p.write_text(json.dumps(c))
        code, out = self.docs_check()
        self.assertEqual(code, 1)
        self.assertIn("check E1: `echo boom; exit 3` exited 3: boom", out)

    def test_a_check_never_sees_the_planes_pythonpath(self):
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["checks"] = [{"id": "E1", "cmd": 'case ":$PYTHONPATH:" in *":%s:"*) exit 7;; esac' % rules.PLANE}]
        p.write_text(json.dumps(c))
        with mock.patch.dict(os.environ, {"PYTHONPATH": f"{rules.PLANE}{os.pathsep}/elsewhere"}):
            self.assertEqual(self.docs_check(), (0, "docs: clean\n"))
            self.assertEqual(rules.product_env()["PYTHONPATH"], "/elsewhere")

    def test_a_budget_breach_makes_a_pass_due_and_never_fails_docs_check(self):
        self.p.write("app/sub/big.py", "x = 1\n" * 9)
        self.assertEqual(self.docs_check(), (0, "docs: clean\n"))
        self.assertEqual(rules.budget_failures(self.p.cfg), ["E7: app/sub/big.py has 9 lines > 5"])
        with tempfile.TemporaryDirectory() as q, mock.patch.dict(os.environ, {"QUEUE_ROOT": q}):
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = cli.main(["--root", str(self.p.root), "architect", "due"])
            info = json.loads(out.getvalue())
            self.assertEqual((code, info["due"]), (0, True))
            self.assertIn("budget check fails: E7: app/sub/big.py has 9 lines > 5", info["reason"])
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                cli.main(["--root", str(self.p.root), "health", "--json"])
            self.assertEqual(json.loads(out.getvalue())["budget_failures"], ["E7: app/sub/big.py has 9 lines > 5"])

    def test_budgets_judge_tracked_files_only(self):
        g = ["git", "-C", str(self.p.root)]
        subprocess.run([*g, "init", "-q"], check=True)
        subprocess.run([*g, "add", "app/a.py"], check=True)
        self.p.write("app/untracked.py", "x = 1\n" * 9)
        self.assertEqual(rules.budget_failures(self.p.cfg), [])

    def _repo(self):
        g = ["git", "-C", str(self.p.root), "-c", "user.name=t", "-c", "user.email=t@t"]
        run = lambda *a: subprocess.run([*g, *a], check=True, capture_output=True)  # noqa: E731
        self.p.write("app/old.py", "x = 1\n" * 9)  # over its budget before the change
        run("init", "-q", "-b", "main")
        run("add", "-A")
        run("commit", "-qm", "base")
        run("checkout", "-qb", "task/0002")
        return run

    def budgets(self, base="main"):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "budgets", "check", "--base", base])
        return code, out.getvalue(), err.getvalue()

    def test_a_change_fails_only_on_files_it_grew_over_their_budget(self):
        """§20: crossed or grown while over fails; touched and not grown warns."""
        run = self._repo()
        self.assertEqual(self.budgets()[:2], (0, "budgets: ok (0 file(s) touched since " +
                                              rules.budget_check(self.p.cfg, "main")["merge_base"][:12] + ")\n"))
        self.p.write("app/old.py", "y = 2\n" * 9)  # touched, same size: a warning
        code, out, _ = self.budgets()
        self.assertEqual(code, 0, out)
        self.assertIn("warning: E7: app/old.py is 9 lines, over its budget of 5, and this change did not grow it (was 9)", out)
        self.p.write("app/a.py", "x = 1\n" * 7)  # crossed, committed
        run("commit", "-qam", "grow a")
        self.p.write("app/old.py", "x = 1\n" * 10)  # grew while over, not committed
        self.p.write("app/new.py", "x = 1\n" * 6)  # a new, untracked file
        r = rules.budget_check(self.p.cfg, "main")
        self.assertEqual([(f["path"], f["size"], f["was"]) for f in r["failures"]],
                         [("app/a.py", 7, 1), ("app/new.py", 6, None), ("app/old.py", 10, 9)])
        self.assertEqual(r["warnings"], [])
        code, out, _ = self.budgets()
        self.assertEqual(code, 1)
        self.assertIn("budgets: E7: app/a.py is 7 lines, over its budget of 5 (was 1 at the merge base): split it or cut it", out)
        self.assertIn("app/new.py is 6 lines, over its budget of 5 (a new file)", out)
        self.assertTrue(out.rstrip().endswith("budgets: FAIL (3 file(s) touched since " + r["merge_base"][:12] + ")"), out)

    def test_a_file_at_or_above_its_cut_line_warns_and_one_over_the_limit_still_fails(self):
        """§20.2: a cut line below the limit warns, naming the file, its size, the cut line and the limit."""
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["budgets"] = [{"id": "E7", "glob": "app/**/*.py", "max_lines": 100, "cut_line": 90},
                                     {"id": "E7", "path": "docs/ENGINEERING.md", "max_bytes": 2000, "cut_line": 10}]
        p.write_text(json.dumps(c))
        self._repo()
        self.p.write("app/near.py", "x = 1\n" * 95)
        self.p.write("app/edge.py", "x = 1\n" * 90)
        self.p.write("app/full.py", "x = 1\n" * 100)
        self.p.write("app/below.py", "x = 1\n" * 89)
        self.p.write("docs/ENGINEERING.md", RULES + "\n")
        code, out, _ = self.budgets()
        self.assertEqual(code, 0, out)
        self.assertIn("warning: E7: app/near.py is 95 lines, at or above its cut line of 90 (limit 100)", out)
        self.assertIn("app/edge.py is 90 lines, at or above its cut line of 90 (limit 100)", out)
        self.assertIn("app/full.py is 100 lines, at or above its cut line of 90 (limit 100)", out)
        self.assertIn(f"docs/ENGINEERING.md is {len(RULES) + 1} bytes, at or above its cut line of 10 (limit 2000)", out)
        self.assertNotIn("app/below.py", out)
        r = rules.budget_check(self.p.cfg, "main")
        self.assertEqual(sorted((w["path"], w["size"], w["cut_line"], w["limit"]) for w in r["warnings"]),
                         [("app/edge.py", 90, 90, 100), ("app/full.py", 100, 90, 100), ("app/near.py", 95, 90, 100),
                          ("docs/ENGINEERING.md", len(RULES) + 1, 10, 2000)])
        self.p.write("app/near.py", "x = 1\n" * 101)  # over the limit: judged as without a cut line
        code, out, _ = self.budgets()
        self.assertEqual(code, 1, out)
        self.assertIn("budgets: E7: app/near.py is 101 lines, over its budget of 100 (a new file): split it or cut it", out)
        self.assertNotIn("app/near.py is 101 lines, at or above its cut line", out)

    def test_the_integration_branch_moving_on_is_not_the_change(self):
        run = self._repo()
        run("checkout", "-q", "main")
        self.p.write("app/up.py", "x = 1\n" * 9)  # another task's growth, merged to main
        run("add", "app/up.py")
        run("commit", "-qm", "upstream")
        run("checkout", "-q", "task/0002")
        self.assertEqual(self.budgets()[0], 0)  # not rebased: main's commit is not in this tree
        self.p.write("app/a.py", "x = 2\n")
        run("commit", "-qam", "small")
        run("rebase", "-q", "main")  # rebased: judged from main's tip, so up.py is not this change's
        r = rules.budget_check(self.p.cfg, "main")
        self.assertEqual((r["touched"], r["failures"], r["warnings"]), (1, [], []))

    def test_a_rename_keeps_its_size_and_a_path_budget_is_normalised(self):
        run = self._repo()
        run("mv", "app/old.py", "app/moved.py")  # over its budget, moved, not grown: a warning
        run("commit", "-qm", "move")
        r = rules.budget_check(self.p.cfg, "main")
        self.assertEqual(([f["path"] for f in r["failures"]], [(w["path"], w["was"]) for w in r["warnings"]]),
                         ([], [("app/moved.py", 9)]))
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["budgets"].append({"id": "E7", "path": "./docs/ENGINEERING.md", "max_bytes": 10})
        p.write_text(json.dumps(c))
        self.p.write("docs/ENGINEERING.md", RULES + "\n")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "budgets", "check", "--base", "main", "--json"])
        body = json.loads(out.getvalue())  # JSON only
        self.assertEqual(code, 1)
        self.assertEqual([(f["path"], f["measure"], f["was"]) for f in body["failures"]],
                         [("docs/ENGINEERING.md", "max_bytes", len(RULES))])

    def test_a_product_root_below_the_git_toplevel(self):
        top = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(top)]))
        sub = top / "prod"
        subprocess.run(["cp", "-R", str(self.p.root), str(sub)], check=True)
        (sub / "app/old.py").write_text("x = 1\n" * 9)
        g = ["git", "-C", str(top), "-c", "user.name=t", "-c", "user.email=t@t"]
        for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-qm", "base"), ("checkout", "-qb", "t")):
            subprocess.run([*g, *args], check=True, capture_output=True)
        (sub / "app/old.py").write_text("x = 1\n" * 10)
        subprocess.run([*g, "commit", "-qam", "grow"], check=True, capture_output=True)
        (sub / "app/new.py").write_text("x = 1\n" * 6)
        r = rules.budget_check(config.load(sub), "main")
        self.assertEqual([(f["path"], f["was"]) for f in r["failures"]], [("app/new.py", None), ("app/old.py", 9)])

    def test_no_budgets_or_no_base(self):
        run = self._repo()
        self.assertEqual(self.budgets("nope")[0], 2)
        self.assertIn("no merge base of HEAD and 'nope'", self.budgets("nope")[2])
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["budgets"] = []
        p.write_text(json.dumps(c))
        self.p.write("app/a.py", "x = 1\n" * 9)
        self.assertEqual(self.budgets()[:2], (0, "budgets: ok (no architect.budgets in plane.json)\n"))

    def test_max_bytes_on_a_named_doc(self):
        p = self.p.root / "docs/delivery/plane.json"
        c = json.loads(p.read_text())
        c["architect"]["budgets"].append({"id": "E7", "path": "docs/ENGINEERING.md", "max_bytes": 10})
        p.write_text(json.dumps(c))
        self.assertTrue(any("docs/ENGINEERING.md is" in f and "bytes > 10" in f for f in rules.budget_failures(self.p.cfg)))

    def test_glob(self):
        r = rules.glob_re("src/**/*.py")
        self.assertTrue(r.match("src/a.py") and r.match("src/x/y/a.py"))
        self.assertFalse(r.match("wix/a.py") or r.match("src/a.pyc"))
        self.assertTrue(rules.glob_re("**/*.md").match("README.md"))
        self.assertFalse(rules.glob_re("docs/*.md").match("docs/a/b.md"))


class ArchitectConfig(unittest.TestCase):
    def load(self, block):
        p = Product({"architect": block})
        try:
            return config.load(p.root)
        finally:
            p.cleanup()

    def test_defaults(self):
        a = self.load({}).architect
        self.assertEqual((a["every_n_tasks"], a["grace_tasks"], a["triage_grace_tasks"], a["refactor_every"]), (4, 1, 2, 4))
        p = Product()
        self.assertIsNone(p.cfg.architect)
        p.cleanup()

    def test_refused(self):
        for block, needle in (
                ({"every_n_task": 4}, "unknown key(s) in `architect`: every_n_task"),
                ({"every_n_tasks": "4"}, "every_n_tasks must be an integer >= 1"),
                ({"shape_adrs": True}, "shape_adrs needs shape_from_task"),
                ({"shape_from_task": "next"}, "shape_from_task must be a task number"),
                ({"budgets": [{"id": "E7", "glob": "*.py"}]}, "needs one of glob or path, and max_lines or max_bytes"),
                ({"budgets": [{"id": "7", "glob": "*.py", "max_lines": 1}]}, "is not a house-rule id"),
                ({"budgets": [{"id": "E7", "glob": ["*.py"], "max_lines": 1}]}, "must be a path or glob"),
                ({"budgets": [{"id": "E7", "glob": "*.py", "max_lines": 9, "max_bytes": 900, "cut_line": 8}]},
                 "cut_line needs exactly one of max_lines or max_bytes"),
                ({"budgets": [{"id": "E7", "glob": "*.py", "max_lines": 9, "cut_line": 9}]},
                 "cut_line must be an integer >= 1 and below the limit (9)"),
                ({"budgets": [{"id": "E7", "glob": "*.py", "max_bytes": 9, "cut_line": 0}]}, "cut_line must be an integer"),
                ({"budgets": [{"id": "E7", "glob": "*.py", "max_lines": 9, "cut_line": "8"}]}, "cut_line must be an integer"),
                ({"budgets": [{"id": "E7", "glob": "*.py", "max_lines": 9, "cut_line": True}]}, "cut_line must be an integer"),
                ({"checks": [{"id": "E1", "cmd": "x", "shell": True}]}, "unknown key(s) shell"),
                ({"areas": {"code": "src/**"}}, "areas must map an area name to a list of globs")):
            with self.subTest(block=block):
                with self.assertRaisesRegex(config.ConfigError, needle.replace("(", r"\(").replace(")", r"\)")):
                    self.load(block)

    def test_a_cut_line_below_its_limit_loads(self):
        b = {"id": "E7", "glob": "*.py", "max_lines": 9, "cut_line": 8}
        self.assertEqual(self.load({"budgets": [b]}).architect["budgets"], [b])

    def test_checks_that_select_the_same_tests_are_refused(self):
        for cmds, shared in (
                (["python3 -m unittest tests.test_a", "python3 -m unittest tests.test_a"], "tests.test_a"),
                (["python3 -m unittest tests.test_a", "pytest tests/test_a.py::Case"], "tests.test_a.Case"),
                (["python3 tests/test_a.py", "python3 -m unittest tests.test_a.Case.test_one"],
                 "tests.test_a.Case.test_one")):
            with self.subTest(cmds=cmds):
                with self.assertRaises(config.ConfigError) as cm:
                    self.load({"checks": [{"id": "E1", "cmd": cmds[0]}, {"id": "E2", "cmd": cmds[1]}]})
                self.assertRegex(str(cm.exception), rf"\bE1\b.*\bE2\b.*\b{re.escape(shared)}(?![\w.])")

    def test_an_overlapping_config_fails_docs_check(self):
        p = Product({"architect": {"checks": [{"id": "E1", "cmd": "python3 -m unittest tests.test_a"},
                                              {"id": "E2", "cmd": "python3 -m unittest tests.test_a"}]}})
        try:
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = cli.main(["--root", str(p.root), "docs", "check"])
            self.assertEqual(code, 2)
            self.assertRegex(err.getvalue(), r"\bE1\b.*\bE2\b.*\btests\.test_a(?![\w.])")
        finally:
            p.cleanup()

    def test_checks_that_select_different_tests_load(self):
        for cmds in (["python3 -m unittest tests.test_a", "python3 -m unittest tests.test_b"],
                     ["python3 -m unittest tests.test_a.One", "pytest tests/test_a.py::Two"],
                     ["python3 -m unittest tests.test_a", "python3 -m unittest tests.test_ab"],
                     ["python3 -m unittest discover -s tests", "true"]):
            with self.subTest(cmds=cmds):
                a = self.load({"checks": [{"id": "E1", "cmd": cmds[0]}, {"id": "E2", "cmd": cmds[1]}]}).architect
                self.assertEqual([c["id"] for c in a["checks"]], ["E1", "E2"])

    def test_example_binding_from_the_spec_loads(self):
        a = self.load({"rules_doc": "docs/ENGINEERING.md", "rules_max_lines": 150, "every_n_tasks": 4, "max_days": 14,
                       "notes_due": 3, "drift_ratio": 1.5, "grace_tasks": 1, "triage_grace_tasks": 2,
                       "shape_adrs": True, "shape_from_task": "0133", "refactor_every": 4, "refactor_in_scope": True,
                       "call_timeout_minutes": 45, "max_new_tasks": 5, "probes": ["app -h"],
                       "checks": [{"id": "E3", "cmd": "true"}], "budgets": [{"id": "E7", "glob": "src/**/*.py", "max_lines": 800}],
                       "areas": {"code": ["src/**"], "tests": ["tests/**"], "docs": ["docs/**", "**/*.md"]},
                       "private_dirs": [".env", "reference"]}).architect
        self.assertEqual(a["shape_from_task"], "0133")



class TemplatesAndContracts(unittest.TestCase):
    """The house-rules template parses as `ccp docs check` reads it, and the contracts describe what
    the code accepts."""

    PLANE = Path(__file__).resolve().parent.parent

    def test_engineering_template_parses(self):
        text = (self.PLANE / "templates/docs-project/ENGINEERING.md").read_text()
        found, errs = rules.parse_rules(text)
        self.assertEqual(errs, [])
        self.assertTrue(found and all(found.values()), found)
        self.assertLessEqual(len(text.splitlines()), config.ARCHITECT_DEFAULTS["rules_max_lines"])

    def test_plane_config_schema_has_every_architect_key(self):
        schema = json.loads((self.PLANE / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["architect"]["properties"]), set(config.ARCHITECT_DEFAULTS))

    def test_report_schema_categories_are_the_lenses(self):
        from ccp import architect
        schema = json.loads((self.PLANE / "contracts/architect_report.schema.json").read_text())
        items = schema["properties"]["findings"]["items"]["properties"]
        self.assertEqual(items["category"]["enum"], list(architect.ARCH.categories))
        self.assertEqual(schema["properties"]["lenses"]["items"]["enum"], list(architect.LENSES))


if __name__ == "__main__":
    unittest.main()
