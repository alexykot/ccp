"""The plane's starter house rules (SPEC §20.5): the template names each rule's check, `ccp docs check`
runs the adopted rules' `docs` checks and skips a declined rule's, and the house-rules format's `docs`
check kind (§20.1)."""
from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, docrules, rules
from ccp import init as ccp_init
from tests.helpers import Product

# One planted fault per mechanical starter rule, and the token of the failure each produces.
FAULTS = {
    "refs-resolve": ("docs/PROJECT.md", "See [the flow](SPEC.md#no-such-heading).\n", "rule citations:"),
    "current-docs": ("docs/NOTES.md", "Added by 0012-add-the-thing.\n", "rule no_ids:"),
    "package-maps": ("app/schema.sql", "select 1;\n", "app: no .claude.md"),
}


def starter_product(declined: dict | None = None, **package_docs) -> Product:
    cfg = json.loads(json.dumps(ccp_init.STARTER_CONFIG))
    cfg["package_docs"].update(package_docs)
    cfg["docs"]["starter_rules"]["declined"] = declined or {}
    p = Product(cfg)
    p.write("docs/SPEC.md", "# SPEC\n\n## Flows\n")
    p.write("docs/PROJECT.md", "# PROJECT\n")
    p.task("0012-add-the-thing")          # the current-docs fault names it: only a logged task is an id
    p.index()
    return p


def docs_check(p: Product) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = cli.main(["--root", str(p.root), "docs", "check"])
    return code, out.getvalue()


class Template(unittest.TestCase):
    def test_every_rule_names_its_starter_name_and_check(self):
        text = rules.STARTER_DOC.read_text()
        blocks, errs = rules.rule_blocks(text)
        self.assertEqual(errs, [])
        self.assertTrue(blocks)
        for rid, b in blocks.items():
            self.assertTrue(b["starter"], rid)
            self.assertIn(b["kind"], {"pass", "docs"}, rid)
            if b["kind"] == "docs":
                self.assertTrue(b["keys"], rid)
        self.assertEqual(len(rules.starter_rules()), len(blocks))
        self.assertLessEqual(len(text.splitlines()), config.ARCHITECT_DEFAULTS["rules_max_lines"])

    def test_a_broken_template_is_an_error_not_an_empty_set(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "starter-rules.md"
            bad.write_text("- **E1** x\n  starter: x\n  check: docs — nope\n")
            rules.starter_rules.cache_clear()
            try:
                with mock.patch.object(rules, "STARTER_DOC", bad), self.assertRaises(ValueError):
                    rules.starter_rules()
            finally:
                rules.starter_rules.cache_clear()

    def test_the_template_is_a_valid_rules_doc_once_adopted(self):
        p = starter_product()
        try:
            p.write("docs/ENGINEERING.md", rules.STARTER_DOC.read_text())
            raw = json.loads((p.root / "docs/delivery/plane.json").read_text())
            raw["architect"] = {"rules_doc": "docs/ENGINEERING.md"}
            p.write("docs/delivery/plane.json", json.dumps(raw))
            self.assertEqual(rules.check_doc(p.cfg), [])
        finally:
            p.cleanup()

    def test_each_docs_check_the_template_names_runs(self):
        # Every key a starter rule's `docs` check names is set by the adoption settings, and each
        # mechanical rule's planted fault is reported.
        keys = {k for r in rules.starter_rules().values() for k in r["keys"]}
        p = starter_product()
        try:
            self.assertTrue(all(rules.configured(p.cfg, k) for k in keys))
            self.assertEqual(docs_check(p), (0, "docs: clean\n"))
            for rel, text, _ in FAULTS.values():
                p.write(rel, text)
            code, out = docs_check(p)
            self.assertEqual(code, 1)
            for name, (_, _, token) in FAULTS.items():
                self.assertIn(token, out, name)
            self.assertEqual({n for n, r in rules.starter_rules().items() if r["kind"] == "docs"}, set(FAULTS))
        finally:
            p.cleanup()


class Decline(unittest.TestCase):
    def test_a_declined_rule_does_not_run_and_the_others_do(self):
        for declined in FAULTS:
            with self.subTest(declined=declined):
                p = starter_product({declined: "not for this product"})
                try:
                    for rel, text, _ in FAULTS.values():
                        p.write(rel, text)
                    code, out = docs_check(p)
                    self.assertEqual(code, 1)
                    for name, (_, _, token) in FAULTS.items():
                        (self.assertNotIn if name == declined else self.assertIn)(token, out, name)
                    note = [line for line in out.splitlines() if f"starter rule {declined} " in line]
                    self.assertEqual(len(note), 1)
                    self.assertIn("not for this product", note[0])
                finally:
                    p.cleanup()

    def test_an_adopted_rule_needs_its_check_set_and_declining_it_clears_that(self):
        p = starter_product()
        try:
            raw = json.loads((p.root / "docs/delivery/plane.json").read_text())
            del raw["package_docs"]["rules"]["citations"]
            p.write("docs/delivery/plane.json", json.dumps(raw))
            errs = rules.starter_check(p.cfg)
            self.assertEqual(len(errs), 1)
            self.assertIn("refs-resolve", errs[0])
            self.assertIn("package_docs.rules.citations", errs[0])
            self.assertEqual(docs_check(p)[0], 1)
            raw["docs"]["starter_rules"]["declined"] = {"refs-resolve": "no numbered SPEC"}
            p.write("docs/delivery/plane.json", json.dumps(raw))
            self.assertEqual(rules.starter_check(p.cfg), [])
            self.assertEqual(docs_check(p)[0], 0)
        finally:
            p.cleanup()

    def test_declining_package_maps_drops_a_package_docs_paths_and_ids_but_not_its_rules(self):
        for declined, reported in (({}, True), ({"package-maps": "no package docs"}, False)):
            with self.subTest(declined=declined):
                p = starter_product(declined)
                try:
                    p.write("app/schema.sql", "select 1;\n")
                    p.write("app/.claude.md", "# app\n\nSee `app/gone.sql`; added by 0012-add-the-thing.\n")
                    p.write(*FAULTS["refs-resolve"][:2])
                    code, out = docs_check(p)
                    self.assertEqual(code, 1)
                    self.assertIn(FAULTS["refs-resolve"][2], out)
                    for token in ("`app/gone.sql`, which does not exist", "names delivery id(s) 0012-add-the-thing"):
                        (self.assertIn if reported else self.assertNotIn)(token, out)
                finally:
                    p.cleanup()

    def test_a_declined_judged_rule_is_noted_with_no_check_skipped(self):
        p = starter_product({"one-home": "a single-file product"})
        try:
            notes = rules.starter_notes(p.cfg)
            self.assertEqual(len(notes), 1)
            self.assertIn("one-home", notes[0])
            self.assertEqual(rules.declined_keys(p.cfg), set())
            code, out = docs_check(p)
            self.assertEqual(code, 0)
            self.assertIn("a single-file product", out)
        finally:
            p.cleanup()

    def test_declining_package_maps_with_no_package_docs_block_is_clean(self):
        p = Product({"docs": {"starter_rules": {"declined": {
            "package-maps": "r", "current-docs": "r", "refs-resolve": "r"}}}})
        try:
            self.assertEqual(rules.starter_check(p.cfg), [])
        finally:
            p.cleanup()

    def test_declining_current_docs_drops_the_history_marker_too(self):
        p = starter_product({"current-docs": "we keep no history files"})
        try:
            subprocess.run(["git", "init", "-q"], cwd=p.root, check=True)
            p.write(".gitattributes", "docs/log/** history\n")
            p.write("docs/log/old.md", "old\n")
            subprocess.run(["git", "add", "-A"], cwd=p.root, check=True)
            self.assertEqual(docrules.history_paths(p.cfg), set())
            self.assertEqual(rules.declined_keys(p.cfg),
                             {"package_docs.rules.no_ids", "package_docs.rules.history_attr"})
        finally:
            p.cleanup()
        p = starter_product()
        try:
            subprocess.run(["git", "init", "-q"], cwd=p.root, check=True)
            p.write(".gitattributes", "docs/log/** history\n")
            p.write("docs/log/old.md", "old\n")
            subprocess.run(["git", "add", "-A"], cwd=p.root, check=True)
            self.assertEqual(docrules.history_paths(p.cfg), {"docs/log/old.md"})
        finally:
            p.cleanup()

    def test_a_check_an_adopted_rule_also_names_still_runs(self):
        fake = {"a": {"id": "E1", "kind": "docs", "keys": ["package_docs.rules.citations", "package_docs"]},
                "b": {"id": "E2", "kind": "docs", "keys": ["package_docs"]}}
        p = Product({"package_docs": {"language": "none"}, "docs": {"starter_rules": {"declined": {"a": "r"}}}})
        try:
            with mock.patch.object(rules, "starter_rules", return_value=fake):
                self.assertEqual(rules.declined_keys(p.cfg), {"package_docs.rules.citations"})
        finally:
            p.cleanup()

    def test_without_starter_rules_nothing_is_required_or_skipped(self):
        p = Product()
        p.index()
        try:
            self.assertEqual((rules.starter_check(p.cfg), rules.declined_keys(p.cfg), rules.starter_notes(p.cfg)),
                             ([], set(), []))
            self.assertEqual(docs_check(p), (0, "docs: clean\n"))
        finally:
            p.cleanup()


class Config(unittest.TestCase):
    def test_bad_starter_rules_are_refused(self):
        for bad in ([], {"declined": []}, {"declined": {"refs-resolve": ""}}, {"declined": {"refs-resolve": 3}},
                    {"adopt": True}, {"declined": {"no-such-rule": "why"}}):
            p = Product({"docs": {"starter_rules": bad}})
            try:
                with self.assertRaises(config.ConfigError, msg=bad):
                    config.load(p.root)
            finally:
                p.cleanup()

    def test_good_starter_rules_load(self):
        for good in (None, {}, {"declined": {}}, {"declined": {"one-home": "one repo, one doc"}}):
            p = Product({"docs": {"starter_rules": good}})
            try:
                self.assertEqual(config.load(p.root).docs["starter_rules"], good)
            finally:
                p.cleanup()


class DocsCheckKind(unittest.TestCase):
    RULES = "# Rules\n\n- **E1** Every reference resolves.\n  check: docs — {keys}\n"

    def check_doc(self, keys: str, package_docs: dict | None) -> list[str]:
        cfg = {"architect": {"rules_doc": "docs/ENGINEERING.md"}}
        if package_docs is not None:
            cfg["package_docs"] = package_docs
        p = Product(cfg)
        try:
            p.write("docs/ENGINEERING.md", self.RULES.format(keys=keys))
            return rules.check_doc(p.cfg)
        finally:
            p.cleanup()

    def test_a_docs_check_must_be_set(self):
        cited = {"rules": {"citations": {"globs": ["docs/*.md"], "targets": ["docs/SPEC.md"]}}}
        self.assertEqual(self.check_doc("package_docs, package_docs.rules.citations", cited), [])
        self.assertEqual(self.check_doc("`package_docs`", {}), [])
        unset = self.check_doc("package_docs.rules.citations", {})
        self.assertEqual(len(unset), 1)
        self.assertIn("package_docs.rules.citations", unset[0])
        self.assertEqual(len(self.check_doc("package_docs", None)), 1)

    def test_a_docs_check_names_known_keys(self):
        self.assertEqual(len(self.check_doc("package_docs.rules.nope", {})), 1)
        self.assertIn("no plane.json key", "\n".join(self.check_doc("", {})))

    def test_a_description_after_the_keys_is_not_a_key(self):
        cited = {"rules": {"citations": {"globs": ["docs/*.md"], "targets": ["docs/SPEC.md"]}}}
        self.assertEqual(self.check_doc("package_docs — a map per source directory, its paths exist", {}), [])
        self.assertEqual(self.check_doc("package_docs, `package_docs.rules.citations` — refs — and links", cited), [])
        blocks, errs = rules.rule_blocks(self.RULES.format(keys="package_docs — what it measures"))
        self.assertEqual((blocks["E1"]["kind"], blocks["E1"]["keys"], errs), ("docs", ["package_docs"], []))
        self.assertEqual(len(self.check_doc("package_docs.rules.nope — what it measures", {})), 1)

    def test_other_kinds_parse_as_before(self):
        blocks, errs = rules.rule_blocks("- **E1** x\n  check: command — scripts/x.sh\n- **E2** y\n  check: maybe\n")
        self.assertEqual((blocks["E1"]["kind"], blocks["E1"]["keys"]), ("command", []))
        self.assertEqual(blocks["E2"]["kind"], "?")
        self.assertEqual(len(errs), 1)


if __name__ == "__main__":
    unittest.main()
