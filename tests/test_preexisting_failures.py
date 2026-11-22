"""Which failures of `ccp docs check` and `ccp tasks check` are already on the integration branch (SPEC §21.2),
decided on plain values."""
from __future__ import annotations

import unittest

from ccp import baseline
from ccp.baseline import Failure
from ccp.rules import OUTPUT_CAP

ROOT, BASE_ROOT = "/work/product", "/tmp/ccp-base-run-x/tree"
ROOTS = [(BASE_ROOT, ROOT)]
RULE = "docs/delivery/tasks/0001-a.md: depends_on `0009-x`, which does not exist"


def check(output: str, cmd: str = "scripts/hits.sh", key: str = "check E3", timed_out: bool = False) -> Failure:
    return Failure(f"{key}: `{cmd}` exited 1", key, cmd, output, timed_out)


class RuleLines(unittest.TestCase):
    def test_a_rule_line_printed_at_both_is_preexisting(self):
        self.assertEqual(baseline.split([Failure(RULE)], [Failure(RULE)], ["app/x.py"]), ([], [RULE]))

    def test_a_rule_line_at_both_naming_a_changed_path_fails(self):
        changed = ["docs/delivery/tasks/0001-a.md"]
        self.assertEqual(baseline.split([Failure(RULE)], [Failure(RULE)], changed), ([RULE], []))

    def test_a_rule_line_only_at_head_fails(self):
        other = Failure("docs/delivery/tasks/0002-b.md: missing title")
        self.assertEqual(baseline.split([Failure(RULE), other], [Failure(RULE)], []), ([other.line], [RULE]))


class CommandChecks(unittest.TestCase):
    def test_a_check_failing_at_both_with_every_head_line_in_the_base_output_is_preexisting(self):
        head = check(f"{ROOT}/a.md:3: hit\nb.md:1: hit\n")
        base = check(f"{BASE_ROOT}/a.md:3: hit\nb.md:1: hit\nc.md:9: hit\n")
        self.assertEqual(baseline.split([head], [base], [], roots=ROOTS), ([], [head.line]))

    def test_a_head_line_the_base_lacks_fails(self):
        head = check("a.md:3: hit\nnew.md:1: hit\n")
        self.assertEqual(baseline.split([head], [check("a.md:3: hit\n")], []), ([head.line], []))

    def test_without_root_normalisation_the_base_line_differs(self):
        head = check(f"{ROOT}/a.md:3: hit\n")
        self.assertEqual(baseline.split([head], [check(f"{BASE_ROOT}/a.md:3: hit\n")], []), ([head.line], []))

    def test_an_empty_head_output_fails(self):
        head = check("  \n")
        self.assertEqual(baseline.split([head], [check("a.md:3: hit\n")], []), ([head.line], []))

    def test_an_output_at_the_cap_fails_at_either_side(self):
        full = "a.md:3: hit\n" + "x" * OUTPUT_CAP
        self.assertEqual(baseline.split([check(full)], [check(full)], [])[1], [])
        head = check("a.md:3: hit\n")
        self.assertEqual(baseline.split([head], [check(full)], []), ([head.line], []))

    def test_a_check_passing_at_the_base_fails(self):
        head = check("a.md:3: hit\n")
        other = check("a.md:3: hit\n", key="docs check leaks")
        self.assertEqual(baseline.split([head], [other], []), ([head.line], []))

    def test_a_timed_out_check_fails(self):
        head = check("a.md:3: hit\n", timed_out=True)
        self.assertEqual(baseline.split([head], [check("a.md:3: hit\n")], []), ([head.line], []))


class CheckerChanged(unittest.TestCase):
    def setUp(self):
        self.head, self.base = [check("a.md:3: hit\n"), Failure(RULE)], [check("a.md:3: hit\n"), Failure(RULE)]

    def test_a_change_under_ccp_or_bin_makes_every_failure_count_where_the_repo_holds_ccp(self):
        for path in ("ccp/docs.py", "bin/ccp"):
            with self.subTest(path=path):
                self.assertEqual(baseline.split(self.head, self.base, [path], holds_ccp=True)[1], [])
                self.assertEqual(len(baseline.split(self.head, self.base, [path], holds_ccp=False)[1]), 2)

    def test_a_file_the_checks_command_names_makes_that_check_count(self):
        failing, pre = baseline.split(self.head, self.base, ["scripts/hits.sh"])
        self.assertEqual((failing, pre), ([self.head[0].line], [RULE]))
        quoted = [check("a.md:3: hit\n", cmd="bash './scripts/hits.sh' --all")]
        self.assertEqual(baseline.split(quoted, quoted, ["scripts/hits.sh"])[1], [])


class NoBase(unittest.TestCase):
    def test_no_base_or_a_base_equal_to_head_leaves_every_failure_failing(self):
        self.assertFalse(baseline.comparable(None, "abc"))
        self.assertFalse(baseline.comparable("abc", "abc"))
        self.assertTrue(baseline.comparable("abc", "def"))
        self.assertEqual(baseline.split([Failure(RULE)], None, []), ([RULE], []))


class Names(unittest.TestCase):
    def test_a_path_is_named_only_whole(self):
        self.assertTrue(baseline.names("a/b.md:3: x", "a/b.md"))
        self.assertTrue(baseline.names("see `a/b.md`.", "a/b.md"))
        self.assertFalse(baseline.names("a/b.md.bak:3: x", "a/b.md"))
        self.assertFalse(baseline.names("xa/b.md: x", "a/b.md"))
        self.assertFalse(baseline.names("'a/b.md'", "a/b.md"))
        self.assertTrue(baseline.names("grep -f 'a/b.md'", "a/b.md", command=True))


if __name__ == "__main__":
    unittest.main()
