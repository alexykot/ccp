"""The canonical task file (SPEC §5): its schema, statuses, kinds, declared paths and sections."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from ccp import parallel, tasklog
from tests.helpers import Product

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "contracts/task_file.schema.json").read_text())


def front(p: Product, tid: str, old: str, new: str) -> None:
    f = p.root / "docs/delivery/tasks" / f"{tid}.md"
    f.write_text(f.read_text().replace(old, new, 1))


class Schema(unittest.TestCase):
    def test_statuses_are_the_canonical_three_plus_the_legacy_reads(self):
        self.assertEqual(SCHEMA["properties"]["status"]["enum"],
                         [*tasklog.STATUSES, *tasklog.LEGACY_STATUSES])

    def test_runtime_keys_are_refused(self):
        refused = {k for alt in SCHEMA["not"]["anyOf"] for k in alt["required"]}
        self.assertEqual(refused, set(tasklog.RUNTIME_KEYS))

    def test_the_template_frontmatter_is_covered(self):
        tmpl = (ROOT / "templates/docs-delivery/TEMPLATE-task.md").read_text()
        head = tmpl.split("\n---\n", 1)[0]
        keys = set(re.findall(r"^#?\s*([a-z_]+):", head, re.M)) - {"task_id"}  # commented examples too
        keys |= {"task_id"}
        missing = {k for k in keys if k not in SCHEMA["properties"]} - {"http", "https"}
        self.assertEqual(missing, set())

    def test_the_template_carries_the_canonical_sections_in_order(self):
        tmpl = (ROOT / "templates/docs-delivery/TEMPLATE-task.md").read_text()
        heads = re.findall(r"^## (.+)$", tmpl, re.M)
        self.assertEqual(heads, list(tasklog.SECTIONS))


class Statuses(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def test_legacy_in_flight_statuses_read_as_pending_with_a_warning(self):
        self.p.task("0001-a", status="in_progress")
        self.p.task("0002-b", status="blocked")
        self.p.index()
        self.assertEqual(tasklog.check(self.p.cfg), [])
        warns = "\n".join(tasklog.warnings(self.p.cfg))
        self.assertIn("0001-a.md: status 'in_progress' is an in-flight state", warns)
        self.assertIn("0002-b.md: status 'blocked'", warns)
        self.assertEqual(tasklog.canonical_status("in_progress"), "pending")
        self.assertEqual(tasklog.canonical_status("done"), "done")

    def test_any_other_status_fails(self):
        self.p.task("0001-a", status="claimed")
        self.p.index()
        self.assertIn("status 'claimed' is not one of pending, done, dropped", "\n".join(tasklog.check(self.p.cfg)))

    def test_a_configured_statuses_list_is_not_read(self):
        p = Product({"task_log": {"statuses": ["pending", "in_progress", "wip", "done", "dropped"]}})
        try:
            p.task("0001-a", status="wip")
            p.index()
            self.assertIn("status 'wip' is not one of", "\n".join(tasklog.check(p.cfg)))
        finally:
            p.cleanup()


class Sections(unittest.TestCase):
    def test_the_canonical_context_heading_and_the_old_one_both_read(self):
        p = Product()
        try:
            p.task("0001-old")  # the helper writes `Context (not verified)`
            new = p.task("0002-new")
            new.write_text(new.read_text().replace("## Context (not verified)", "## Context (not checked)"))
            p.index()
            self.assertEqual(tasklog.check(p.cfg), [])
            self.assertEqual(tasklog._section(new.read_text(), tasklog.SEC_CONTEXT).strip(), "- background")
            self.assertEqual(tasklog._section(new.read_text(), "Context (not verified)").strip(), "- background")
        finally:
            p.cleanup()

    def test_a_product_may_require_an_extra_section(self):
        p = Product({"task_log": {"sections": [*tasklog.SECTIONS, "Rollout"]}})
        try:
            p.task("0001-a")
            p.index()
            self.assertIn("missing section `## Rollout`", "\n".join(tasklog.check(p.cfg)))
        finally:
            p.cleanup()


class Kinds(unittest.TestCase):
    def test_a_configured_kind_sets_its_own_refs(self):
        p = Product({"architect": {}, "task_log": {"kinds": {
            "feature": {}, "refactor": {"refs_any": ["rule_refs", "review_refs"], "forbid": ["spec_refs", "adr_refs"]},
            "chore": {"refs_any": ["review_refs"], "forbid": ["spec_refs"]}}}})
        try:
            p.task("0001-c")
            front(p, "0001-c", 'spec_refs: ["S1"]', "kind: chore")
            p.index()
            errs = "\n".join(tasklog.check(p.cfg))
            self.assertIn("a chore cites review_refs (finding ids)", errs)
            self.assertNotIn("missing `spec_refs`", errs)  # forbidden for a chore, so not required
            front(p, "0001-c", "kind: chore", 'kind: chore\nreview_refs: ["ar-20261014T000000Z-abcd#F01"]')
            self.assertEqual(tasklog.check(p.cfg), [])
            self.assertEqual(tasklog.kind_refs(p.cfg, "chore"), ["review_refs"])
            self.assertEqual(tasklog.kind_refs(p.cfg, "feature"), ["spec_refs"])
        finally:
            p.cleanup()

    def test_a_bad_kinds_block_is_refused(self):
        from ccp import config
        p = Product({"task_log": {"kinds": {"refactor": {"needs": ["x"]}}}})
        try:
            with self.assertRaises(config.ConfigError):
                _ = p.cfg
        finally:
            p.cleanup()


class DeclaredPaths(unittest.TestCase):
    def test_paths_frontmatter_wins_over_the_scope_in_item(self):
        p = Product()
        try:
            f = p.task("0001-a")
            f.write_text(f.read_text().replace("- **In:** it", "- **In:** `src/guessed.py`"))
            t = next(x for x in tasklog.load(p.cfg) if x["task_id"] == "0001-a")
            self.assertEqual(parallel.paths(p.cfg, t), ["src/guessed.py"])
            front(p, "0001-a", "created:", 'paths: ["src/declared/", "./tests/test_x.py"]\ncreated:')
            t = next(x for x in tasklog.load(p.cfg) if x["task_id"] == "0001-a")
            self.assertEqual(parallel.paths(p.cfg, t), ["src/declared/", "tests/test_x.py"])
        finally:
            p.cleanup()


class ReviewsDir(unittest.TestCase):
    def test_shaping_records_are_read_from_the_configured_dir(self):
        p = Product({"task_log": {"reviews_dir": "records"}, "architect": {"shape_adrs": True, "shape_from_task": "0001"}})
        try:
            p.write("docs/delivery/records/sh-20261020T000000Z-abcd.md", "ADR: ADR-0031\n")
            self.assertEqual(tasklog.shaped_adrs(p.cfg), {31})
            self.assertEqual(p.cfg.reviews_dir, p.root / "docs/delivery/records")
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()


class ReviewFixes(unittest.TestCase):
    """#91 review: a legacy status reads as pending everywhere; kinds merge per kind; paths are checked."""

    def test_a_legacy_status_is_pending_for_every_reader(self):
        p = Product()
        try:
            p.task("0001-a", status="in_progress")
            p.task("0002-b", status="blocked")
            p.task("0003-c", deps=["0002-b"])
            p.index()
            self.assertEqual({t["status"] for t in tasklog.load(p.cfg)}, {"pending"})
            ranked = [t["task_id"] for t, _ in tasklog.ranked(p.cfg)]
            self.assertIn("0001-a", ranked)
            self.assertIn("0002-b", ranked)
            self.assertNotIn("0003-c", ranked)      # waits for 0002-b like any pending dependency
        finally:
            p.cleanup()

    def test_naming_one_kind_keeps_the_default_feature_kind(self):
        p = Product({"architect": {}, "task_log": {"kinds": {"refactor": {"refs_any": ["rule_refs"]}}}})
        try:
            self.assertIn("feature", p.cfg.task_log["kinds"])
            p.task("0001-a")
            p.index()
            self.assertNotIn("is not one of", "\n".join(tasklog.check(p.cfg)))
        finally:
            p.cleanup()

    def test_paths_must_be_an_inline_list_of_relative_paths(self):
        for value, ok in (("[src/a.py, docs/*.md]", True), ("src/a.py, src/b.py", False), ("", False),
                          ("[/etc/x]", False), ("[../out/a.py]", False)):
            p = Product()
            try:
                p.task("0001-a")
                front(p, "0001-a", "status: pending", f"status: pending\npaths: {value}")
                p.index()
                errs = [e for e in tasklog.check(p.cfg) if "paths" in e]
                self.assertEqual(not errs, ok, (value, errs))
            finally:
                p.cleanup()
