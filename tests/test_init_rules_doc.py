"""SPEC §4.5, §20.1: `ccp init --rules-doc PATH [--adopt]` brings a product's existing house rules in:
it lists each rule with no `check:` line and, with `--adopt`, gives each a `check: pass` line within
the doc's line cap, writing nothing else. Scratch HOME, bindings, repos and queues."""
from __future__ import annotations

import json
from pathlib import Path

from ccp import rules
from tests.test_init import InitCase
from tests.test_init_permissions import tree

RULES = """# Engineering rules

## Architecture

- **E1** The core never imports the adapters.
- **E2** One owner for every count: the registry module
  holds it, and every doc names that owner.

- **E3** Tests check behaviour.
  check: pass

## Tests

- **E4** Tests are deterministic.
"""


class RulesDoc(InitCase):
    def setUp(self):
        super().setUp()
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.doc = self.repo / "docs" / "RULES.md"
        self.doc.write_text(RULES)

    def plane(self, **blocks) -> None:
        p = self.repo / "docs/delivery/plane.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), **blocks}))

    def rules_doc(self, *args):
        r = self.ccp("init", "--rules-doc", "docs/RULES.md", *args)
        return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)

    def test_the_report_lists_the_unchecked_rules_and_writes_nothing(self):
        before = tree(self.repo, self.bindings, self.home)
        code, res = self.rules_doc()
        self.assertEqual(code, 0, res)
        self.assertEqual(tree(self.repo, self.bindings, self.home), before)
        self.assertEqual((res["rules"], res["unchecked"], res["adopted"]), (4, ["E1", "E2", "E4"], []))
        self.assertIn(str(rules.STARTER_DOC), res["starter_rules"])
        self.assertTrue(rules.STARTER_DOC.is_file())
        self.assertIn("architect.rules_doc", res["note"])  # not set yet: nothing checks the doc

    def test_adopt_closes_each_unchecked_rule_and_docs_check_passes(self):
        self.plane(architect={"rules_doc": "docs/RULES.md"})
        r = self.ccp("docs", "check")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("has no `check:`"), 3)
        code, res = self.rules_doc("--adopt")
        self.assertEqual(code, 0, res)
        self.assertEqual((res["unchecked"], res["adopted"]), (["E1", "E2", "E4"], ["E1", "E2", "E4"]))
        self.assertNotIn("note", res)  # architect.rules_doc names this doc
        lines = self.doc.read_text().splitlines()
        self.assertEqual(res["lines"], len(lines))
        self.assertEqual(lines[lines.index("- **E1** The core never imports the adapters.") + 1], "  check: pass")
        self.assertEqual(lines[lines.index("  holds it, and every doc names that owner.") + 1], "  check: pass")
        self.assertEqual(lines[-1], "  check: pass")
        self.assertEqual(self.doc.read_text().count("check: pass"), 4)  # E3 keeps its own, once
        self.assertEqual(rules.parse_rules(self.doc.read_text())[0], dict.fromkeys(("E1", "E2", "E3", "E4"), "pass"))
        r = self.ccp("docs", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        before = self.doc.read_text()
        code, res = self.rules_doc("--adopt")
        self.assertEqual((code, res["unchecked"], res["adopted"]), (0, [], []))
        self.assertEqual(self.doc.read_text(), before)

    def test_adopt_over_the_line_cap_writes_nothing(self):
        n = len(RULES.splitlines())
        self.plane(architect={"rules_doc": "docs/RULES.md", "rules_max_lines": n + 2})
        code, err = self.rules_doc("--adopt")
        self.assertEqual(code, 1)
        self.assertIn(f"rules_max_lines {n + 2}", err)
        self.assertEqual(self.doc.read_text(), RULES)
        self.plane(architect={"rules_doc": "docs/RULES.md", "rules_max_lines": n + 3})
        self.assertEqual(self.rules_doc("--adopt")[0], 0)

    def test_the_product_rule_id_pattern_is_used(self):
        self.doc.write_text("- **R-1** Rule one.\n- **R-2** Rule two.\n  check: pass\n- **E9** Not a rule id here.\n")
        self.plane(ids={"rule": {"pattern": "R-[0-9]+"}})
        code, res = self.rules_doc()
        self.assertEqual(code, 0, res)
        self.assertEqual((res["rules"], res["unchecked"]), (2, ["R-1"]))

    def test_refusals(self):
        before = tree(self.repo, self.bindings, self.home)
        for args in (("--rules-doc", "docs/RULES.md", "--gate", "make test"),
                     ("--rules-doc", "docs/RULES.md", "--permissions"),
                     ("--rules-doc", "docs/RULES.md", "--force", "--adopt"),
                     ("--adopt",),
                     ("--rules-doc", "docs/NONE.md")):
            with self.subTest(args=args):
                r = self.ccp("init", *args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertEqual(tree(self.repo, self.bindings, self.home), before)

    def test_without_a_plane_json_the_defaults_apply(self):
        (self.repo / "docs/delivery/plane.json").unlink()
        code, res = self.rules_doc()
        self.assertEqual(code, 0, res)
        self.assertEqual((res["unchecked"], res["rules_max_lines"]), (["E1", "E2", "E4"], 150))
        self.assertTrue(Path(self.doc).is_file())
