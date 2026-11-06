"""Task kinds (SPEC §20.3) and the shaping check (§19.6): `ccp tasks check` and `ccp tasks next`.
Acceptance checks docs/design/architect.md #3 and #4 are named below."""
from __future__ import annotations

import json
import subprocess
import unittest

from ccp import tasklog
from tests.helpers import Product


def git(root, *a):
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                   capture_output=True)


def front(p: Product, tid: str, old: str, new: str) -> None:
    f = p.root / "docs/delivery/tasks" / f"{tid}.md"
    f.write_text(f.read_text().replace(old, new, 1))


class RefactorKind(unittest.TestCase):
    def setUp(self):
        self.p = Product({"task_log": {"required": ["task_id", "title", "status", "depends_on", "spec_refs",
                                                    "adr_refs", "created", "updated"],
                                       "refs_any": ["spec_refs", "adr_refs"]},
                          "architect": {}})

    def tearDown(self):
        self.p.cleanup()

    def errs(self):
        self.p.index()
        return "\n".join(tasklog.check(self.p.cfg))

    def refactor(self, tid, refs='rule_refs: ["E3"]'):
        self.p.task(tid)
        front(self.p, tid, 'spec_refs: ["S1"]', f"kind: refactor\n{refs}")

    def test_a_refactor_cites_rules_or_findings_not_the_spec(self):
        self.refactor("0001-merge-registries")
        self.assertEqual(self.errs(), "")  # no spec_refs/adr_refs keys needed
        self.refactor("0002-cut-copies", 'review_refs: ["ar-20261014T000000Z-abcd#F03"]')
        self.assertEqual(self.errs(), "")

    def test_a_refactor_citing_the_spec_is_refused(self):
        self.p.task("0001-r")
        front(self.p, "0001-r", 'spec_refs: ["S1"]', 'kind: refactor\nspec_refs: ["S1"]\nadr_refs: ["0031 D1"]\nrule_refs: ["E1"]')
        self.assertIn("a refactor changes no rule, so it cites no spec_refs, adr_refs", self.errs())

    def test_a_refactor_must_cite_something(self):
        self.refactor("0001-r", "rule_refs: []")
        self.assertIn("a refactor cites rule_refs (house-rule ids) or review_refs", self.errs())

    def test_bad_kind_and_bad_rule_id(self):
        self.p.task("0001-a")
        front(self.p, "0001-a", "status: pending", "status: pending\nkind: chore")
        self.refactor("0002-r", 'rule_refs: ["rule-3"]')
        e = self.errs()
        self.assertIn("kind 'chore' is not one of feature, refactor", e)
        self.assertIn("rule_refs entry 'rule-3' is not a house-rule id", e)

    def test_without_the_architect_block_kind_is_not_read(self):
        (self.p.root / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "demo"}))
        self.p.task("0001-a")
        front(self.p, "0001-a", "status: pending", "status: pending\nkind: chore")
        self.assertEqual(self.errs(), "")
        self.refactor("0002-r")  # an ordinary task now: it needs spec refs like any other
        self.assertIn("0002-r.md: cites none of spec_refs", self.errs())
        self.assertNotIn("a refactor", self.errs())

    def test_a_feature_still_needs_its_refs(self):
        self.p.task("0001-a")
        front(self.p, "0001-a", 'spec_refs: ["S1"]', 'spec_refs: []\nadr_refs: []\nrule_refs: ["E1"]')
        self.assertIn("cites none of spec_refs, adr_refs", self.errs())


class RefactorCapacity(unittest.TestCase):
    """`next` and the refactor lane under `refactor_in_scope: true`: in every scope, and ahead of
    features once refactor_every merged."""

    def setUp(self):
        self.p = Product({"architect": {"refactor_every": 4, "refactor_in_scope": True}})
        git(self.p.root, "init", "-q")

    def tearDown(self):
        self.p.cleanup()

    def commit(self, msg):
        self.p.index()
        git(self.p.root, "add", "-A")
        git(self.p.root, "commit", "-qm", msg)

    def done(self, tid, kind=None):
        self.p.task(tid, "done")
        if kind:
            front(self.p, tid, "status: done", f"status: done\nkind: {kind}")
            front(self.p, tid, 'spec_refs: ["S1"]', 'rule_refs: ["E1"]')
        self.commit(f"done {tid}")

    def refactor(self, tid):
        self.p.task(tid)
        front(self.p, tid, 'spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]')

    def test_acceptance_4_refactor_comes_first_after_4_features(self):
        for i in range(1, 9):
            self.p.task(f"{i:04d}-f{i}")
        self.refactor("0009-r")
        self.commit("tasks")
        for i in range(1, 4):
            self.done(f"{i:04d}-f{i}")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0004", "0005"])["task_id"], "0004-f4")  # 3 since none
        self.done("0004-f4")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0005", "0006"])["task_id"], "0009-r")  # features-only scope
        self.done("0009-r", "refactor")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0005", "0006"])["task_id"], "0005-f5")

    def test_merge_order_is_git_order_not_task_order(self):
        for i in range(1, 6):
            self.p.task(f"{i:04d}-f{i}")
        self.refactor("0006-r")
        self.refactor("0007-r2")
        self.commit("tasks")
        self.done("0006-r", "refactor")      # the refactor merged first ...
        for i in range(1, 5):
            self.done(f"{i:04d}-f{i}")       # ... then four features
        self.assertEqual(tasklog.done_order(self.p.cfg),
                         ["0006-r", "0001-f1", "0002-f2", "0003-f3", "0004-f4"])
        self.assertEqual(tasklog.features_since_refactor(self.p.cfg, tasklog.load(self.p.cfg)), 4)
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0005"])["task_id"], "0007-r2")

    def test_reopened_task_leaves_the_order(self):
        self.p.task("0001-a")
        self.p.task("0002-b")
        self.commit("tasks")
        self.done("0001-a")
        self.done("0002-b")
        self.p.task("0001-a")  # back to pending
        self.commit("reopen")
        self.done("0001-a")
        self.assertEqual(tasklog.done_order(self.p.cfg), ["0002-b", "0001-a"])

    def test_without_the_architect_block_a_refactor_is_an_ordinary_task(self):
        (self.p.root / "docs/delivery/plane.json").write_text('{"project_id": "demo"}')
        self.p.task("0001-f1")
        self.refactor("0002-r")
        self.assertEqual(tasklog.next_task(self.p.cfg, ["0001"])["task_id"], "0001-f1")
        self.done("0001-f1")
        self.assertIsNone(tasklog.next_task(self.p.cfg, ["0001"]))  # the refactor is not in this scope


class RefactorDeps(unittest.TestCase):
    """`refactor_in_scope: "deps"` (the default, operator 2026-10-21): a refactor joins a scope only when a
    scope task depends on it; the rest wait for the next review point."""

    def setUp(self):
        self.p = Product({"architect": {"refactor_every": 0}})

    def tearDown(self):
        self.p.cleanup()

    def refactor(self, tid, status="pending"):
        self.p.task(tid, status)
        front(self.p, tid, 'spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]')

    def test_deps_is_the_default(self):
        self.assertEqual(self.p.cfg.architect["refactor_in_scope"], "deps")

    def test_only_a_refactor_a_scope_task_depends_on_joins_the_scope(self):
        self.refactor("0001-r-unrelated")
        self.refactor("0002-r-needed")
        self.p.task("0003-mid", deps=["0002-r-needed"])
        self.p.task("0004-f", deps=["0003-mid"])
        cfg = self.p.cfg
        # transitive: 0004 needs 0003 (outside the scope too), which needs the refactor
        self.assertEqual(tasklog.refactor_reach(cfg, tasklog.load(cfg), ["0004"]), {"0002-r-needed": "0004-f"})
        self.assertEqual(tasklog.next_task(cfg, ["0004"])["task_id"], "0002-r-needed")
        self.assertEqual([t["task_id"] for t in tasklog.waiting_refactors(cfg, ["0004"])], ["0001-r-unrelated"])
        self.refactor("0002-r-needed", "done")
        self.assertIsNone(tasklog.next_task(cfg, ["0004"]))  # 0003 is not a refactor: it never joins

    def test_a_done_or_dropped_scope_task_pulls_nothing_in(self):
        self.refactor("0001-r")
        self.p.task("0002-f", "done", deps=["0001-r"])
        self.assertEqual(tasklog.refactor_reach(self.p.cfg, tasklog.load(self.p.cfg), ["0002"]), {})
        self.assertEqual([t["task_id"] for t in tasklog.waiting_refactors(self.p.cfg, ["0002"])], ["0001-r"])

    def test_a_dropped_task_pulls_nothing_in(self):
        self.refactor("0001-r")
        self.p.task("0002-gone", deps=["0001-r"])
        front(self.p, "0002-gone", "status: pending", "status: dropped")
        self.p.task("0003-f", deps=["0002-gone"])
        self.assertEqual(tasklog.scope_deps(tasklog.load(self.p.cfg), ["0003"]), {})

    def test_the_review_points_refactors_are_taken_first(self):
        self.p.task("0001-f")
        self.refactor("0002-r-blocked")
        front(self.p, "0002-r-blocked", "depends_on: []", 'depends_on: ["0001-f"]')
        self.refactor("0005-r")
        self.refactor("0009-r")
        scope = ["0009-r", "0005-r", "0002-r-blocked", "0001"]
        first = ["0009-r", "0005-r", "0002-r-blocked"]
        # ready ones first, lowest NNNN; 0002 waits on its own dependency like any task
        self.assertEqual(tasklog.next_task(self.p.cfg, scope, first)["task_id"], "0005-r")
        self.assertEqual(tasklog.next_task(self.p.cfg, scope)["task_id"], "0001-f")  # no list: task order

    def test_true_and_false_keep_their_meaning(self):
        self.refactor("0001-r")
        self.p.task("0002-f")
        for mode, want in ((True, "0001-r"), (False, "0002-f")):
            self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"refactor_in_scope": mode}}))
            self.assertEqual(tasklog.next_task(self.p.cfg, ["0002"])["task_id"], want)
        self.assertEqual(tasklog.waiting_refactors(self.p.cfg, ["0002"])[0]["task_id"], "0001-r")  # false: it waits
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"refactor_in_scope": "all"}}))
        with self.assertRaisesRegex(Exception, 'refactor_in_scope must be "deps", true or false'):
            self.p.cfg


class Shaping(unittest.TestCase):
    def setUp(self):
        self.p = Product({"task_log": {"required": ["task_id", "title", "status", "depends_on", "spec_refs",
                                                    "adr_refs", "created", "updated"],
                                       "refs_any": ["spec_refs", "adr_refs"]},
                          "architect": {"shape_adrs": True, "shape_from_task": "0003"}})
        for tid in ("0001-old", "0003-new"):
            self.p.task(tid)
            front(self.p, tid, 'spec_refs: ["S1"]', 'spec_refs: []\nadr_refs: ["0031 D1"]')

    def tearDown(self):
        self.p.cleanup()

    def errs(self):
        self.p.index()
        return "\n".join(tasklog.check(self.p.cfg))

    def test_acceptance_3_unshaped_adr_fails_until_a_record_or_a_waiver(self):
        e = self.errs()
        self.assertIn("0003-new.md: cites ADR-0031 ('0031 D1'), which has no shaping record", e)
        self.assertNotIn("0001-old.md", e)  # before shape_from_task
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "# Architect shape\n\nADR: ADR-0030\n")
        self.assertIn("0003-new.md: cites ADR-0031", self.errs())  # a record naming another ADR
        self.p.write("docs/delivery/reviews/sh-20261014T000001Z-abce.md", "# Architect shape\n\nADR: ADR-0031\n")
        self.assertEqual(self.errs(), "")

    def test_waiver(self):
        front(self.p, "0003-new", "status: pending", "status: pending\nshaping: waived — one-line change, nothing to shape")
        self.assertEqual(self.errs(), "")
        front(self.p, "0003-new", "shaping: waived — one-line change, nothing to shape", "shaping: skipped")
        self.assertIn("a waiver reads `shaping: waived — <reason>`", self.errs())

    def test_only_pending_tasks_and_only_with_the_check_on(self):
        self.p.task("0003-new", "done")
        front(self.p, "0003-new", 'spec_refs: ["S1"]', 'spec_refs: []\nadr_refs: ["0031 D1"]')
        self.assertEqual(self.errs(), "")
        self.p.task("0004-later")
        front(self.p, "0004-later", 'spec_refs: ["S1"]', 'spec_refs: []\nadr_refs: ["ADR-0031"]')
        self.assertIn("0004-later.md: cites ADR-0031", self.errs())
        (self.p.root / "docs/delivery/plane.json").write_text(
            '{"project_id": "demo", "task_log": {"required": ["task_id"], "refs_any": ["spec_refs", "adr_refs"]}}')
        self.assertEqual(self.errs(), "")

    def test_only_entries_that_open_with_an_adr_cite_one(self):
        # A quoted entry with commas stays one entry; its trailing words are not ADRs.
        front(self.p, "0003-new", 'adr_refs: ["0031 D1"]', 'adr_refs: ["0031 D7", "0031 Acceptance tests instr-01, instr-02"]')
        self.assertEqual(tasklog.frontmatter((self.p.root / "docs/delivery/tasks/0003-new.md").read_text())["adr_refs"],
                         ["0031 D7", "0031 Acceptance tests instr-01, instr-02"])
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "ADR: ADR-0031\n")
        self.assertEqual(self.errs(), "")
        self.assertEqual([tasklog.adr_number(r) for r in ("ADR-0031", "adr 7", "docs/adr/0012-x.md", "instr-02", "D4",
                                                          "2026-10-14 ruling")],
                         [31, 7, 12, None, None, None])
        self.assertEqual(tasklog.frontmatter("---\nx: [S12 the operator's call, S13]\n---\n")["x"], ["S12 the operator's call", "S13"])

    def test_an_adr_line_names_only_its_adrs(self):
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "ADR: ADR-0030 (accepted 2026-10-06)\n")
        self.assertEqual(tasklog.shaped_adrs(self.p.cfg), {30})
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "adr: 0031\n")
        self.assertEqual(tasklog.shaped_adrs(self.p.cfg), set())  # only ADR-NNNN tokens count

    def test_a_record_without_an_adr_line_names_any_adr_it_mentions(self):
        self.p.write("docs/delivery/reviews/sh-20261014T000000Z-abcd.md", "# Shape of ADR-0031\n")
        self.assertEqual(self.errs(), "")


if __name__ == "__main__":
    unittest.main()
