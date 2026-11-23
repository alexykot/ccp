"""ccp/refs.py: ids and references parsed in one place, with the product's `ids` patterns (SPEC §7)."""
from __future__ import annotations

import json
import unittest

from ccp import adr, config, estimator, refs, reviewpoints, rules, tasklog
from tests.helpers import Product

D = refs.DEFAULT


class Defaults(unittest.TestCase):
    def test_task_ids(self):
        self.assertEqual(D.task_file_re.match("0042-sf-store.md").groups(), ("0042", "sf-store"))
        self.assertIsNone(D.task_file_re.match("042-sf.md"))
        self.assertTrue(D.task_id_re.match("0042-sf-store"))
        self.assertEqual(D.task_number("0042-sf-store"), "0042")
        self.assertEqual(D.format_task_number(43), "0043")
        self.assertTrue(D.same_task("0042-sf-store", "0042"))
        self.assertTrue(D.same_task("0042-sf-store", "0042-sf-store"))
        self.assertFalse(D.same_task("0042-sf-store", "0043"))
        self.assertEqual(D.family("0042-sf-store"), "sf")
        self.assertEqual(D.family("0042"), "")

    def test_a_merge_subject_and_a_task_branch_name_the_task_number(self):
        for subject, n in (("Task 0042: sf store", "0042"), ("0042 sf store (#7)", None), ("TASK  0042-sf", None),
                           ("Task 0042 takes a follow-up (#9)", None), ("00421 too wide", None),
                           ("Reconcile 0042", None)):
            m = D.task_merge_subject_re.match(subject)
            self.assertEqual(m.group(1) if m else None, n, subject)
        for text, n in (("Merge branch 'task/0042-sf-store'", "0042"), ("origin/task/0042-sf", "0042"),
                        ("task/0042 no slug", None), ("subtask/0042-sf", None)):
            m = D.task_branch_re.search(text)
            self.assertEqual(m.group(1) if m else None, n, text)

    def test_adr_refs(self):
        for ref, n in (("0031 D2", 31), ("ADR-0007", 7), ("adr-7", 7), ("see docs/adr/0012-x.md", 12),
                       ("0031-x", 31), ("2026-10-01", None), ("nothing", None)):
            self.assertEqual(D.adr_number(ref), n, ref)
        self.assertEqual(D.parse_adr_ref("0030 D2a"), refs.AdrRef(30, "2a", None, "0030 D2a"))
        r = D.parse_adr_ref("0028 Acceptance tests arms-12")
        self.assertEqual((r.number, r.decision, r.section), (28, None, "Acceptance tests arms-12"))
        self.assertIsNone(D.parse_adr_ref("2026-10-01"))
        self.assertEqual(D.adr_id(7), "ADR-0007")
        self.assertEqual(D.adr_canonical("31"), "ADR-0031")
        self.assertEqual(D.adr_canonical("none"), "none")
        self.assertEqual(D.adr_file_re.match("ADR-0003-x.md").group(1), "0003")
        self.assertEqual(D.adr_globs(3), ("0003-*.md", "ADR-0003*.md", "0003.md"))
        self.assertEqual([int(m) for m in D.adr_mention_re.findall("ADR-0031 and ADR 7, not 0099")], [31, 7])

    def test_adr_link_accepts_the_whole_link_forms(self):
        for ref, want in (("ADR-0007", (7, None)), ("adr-7", (7, None)), ("0007", (7, None)), ("7", (7, None)),
                          ("ADR-0007 D2", (7, "2")), ("0031 D2a", (31, "2a")), ("  ADR-0007   D2  ", (7, "2")),
                          (7, (7, None))):
            self.assertEqual(D.adr_link(ref), want, ref)
        self.assertEqual(refs.Ids(adr_prefix="DEC-").adr_link("DEC-007 D1"), (7, "1"))

    def test_adr_link_refuses_anything_else(self):
        for ref in ("", "nothing", "2026-10-01", "0031-x", "ADR-0007 D", "ADR-0007 Acceptance", "ADR-0007 D2 and more",
                    "docs/adr/0012-x.md", "see ADR-0007", "ADR 0007", "ADR-0007, ADR-0008"):
            self.assertIsNone(D.adr_link(ref), ref)

    def test_parse_adr_ref_reads_a_whole_link_and_a_loose_ref_as_the_base_did(self):
        self.assertEqual(D.parse_adr_ref("ADR-0007 D2"), refs.AdrRef(7, "2", None, "ADR-0007 D2"))
        self.assertEqual(D.parse_adr_ref("ADR-0007"), refs.AdrRef(7, None, None, "ADR-0007"))
        self.assertEqual(D.parse_adr_ref("0040 D2 and more").decision, "2")  # not a whole link: the loose reading

    def test_parse_adr_ref_cites_only_a_capital_d_and_a_lower_case_suffix(self):
        # `adr_link` reads `0040 d2` and `0040 D2A` as decisions; a ref cites only `D2` / `D2a`, the rest is a section
        for raw, want in (("0040 d2", refs.AdrRef(40, None, "d2", "0040 d2")),
                          ("ADR-0040 d3", refs.AdrRef(40, None, "d3", "ADR-0040 d3")),
                          ("0040 D2A", refs.AdrRef(40, None, "D2A", "0040 D2A")),
                          ("0040 D2a", refs.AdrRef(40, "2a", None, "0040 D2a"))):
            self.assertEqual(D.parse_adr_ref(raw), want, raw)
            self.assertIsNotNone(D.adr_link(raw), raw)

    def test_parse_adr_ref_keeps_the_first_capital_d_for_a_prefix_ending_in_d(self):
        # `adr_link` reads `D0040 D2` with prefix `D-` as ADR 40, decision 2; a ref has always cited its first `D<n>`
        r = refs.Ids(adr_prefix="D-").parse_adr_ref("D0040 D2")
        self.assertEqual((r.number, r.decision, r.section), (40, "0040", None))
        self.assertEqual(refs.Ids(adr_prefix="D-").adr_link("D0040 D2"), (40, "2"))
        self.assertEqual(refs.Ids(adr_prefix="D-").parse_adr_ref("D-0040 D2").decision, "2")

    def test_spec_rule_review_point(self):
        self.assertEqual(D.spec_ref_re.search("see S3–S5 here").groups(), ("3", "5"))
        self.assertEqual(D.spec_ref(12), "S12")
        self.assertTrue(D.is_rule_id("E31"))
        self.assertFalse(D.is_rule_id("E31x"))
        self.assertTrue(D.is_review_point("R8"))
        self.assertFalse(D.is_review_point("R0"))
        self.assertEqual(D.review_point_number("R12"), 12)
        self.assertIsNone(D.review_point_number("PM"))
        self.assertEqual(refs.number_prefix("0042-x"), "0042")
        self.assertEqual(refs.number_prefix("x"), "")

    def test_defaults_match_what_the_modules_always_used(self):
        self.assertEqual(tasklog.NAME_RE.pattern, r"^(\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
        self.assertEqual(adr.FILE_RE.match("0001-x.md").group(1), "0001")
        self.assertEqual(reviewpoints.ID_RE.pattern, r"^(?:R[1-9][0-9]*)$")
        self.assertEqual(config.RULE_ID_RE.pattern, r"^(?:E[0-9]+)$")


class Validate(unittest.TestCase):
    def test_good_and_absent(self):
        self.assertEqual(refs.validate(None), [])
        self.assertEqual(refs.validate({"task": {"width": 5}, "adr": {"prefix": "DEC-", "width": 3},
                                        "rule": {"pattern": "H\\d+"}}), [])

    def test_bad(self):
        self.assertTrue(refs.validate([]))
        self.assertTrue(refs.validate({"nope": {}}))
        self.assertTrue(refs.validate({"task": {"width": 0}}))
        self.assertTrue(refs.validate({"task": {"width": True}}))
        self.assertTrue(refs.validate({"adr": {"prefix": "1x"}}))
        self.assertTrue(refs.validate({"rule": {"pattern": "("}}))
        self.assertTrue(refs.validate({"spec": {"other": 1}}))

    def test_config_refuses_a_bad_block_and_keeps_a_good_one(self):
        p = Product({"ids": {"task": {"width": 0}}})
        try:
            with self.assertRaises(config.ConfigError):
                p.cfg
        finally:
            p.cleanup()
        p = Product({"ids": {"task": {"width": 5}}})
        try:
            self.assertEqual(refs.ids(p.cfg).task_width, 5)
        finally:
            p.cleanup()
        p = Product()
        try:
            self.assertIs(refs.ids(p.cfg), refs.DEFAULT)
        finally:
            p.cleanup()


class NonDefaultIds(unittest.TestCase):
    """A product with 5-digit tasks, `DEC-` ADRs of 3 digits and `H<n>` house rules."""

    IDS = {"task": {"width": 5}, "adr": {"prefix": "DEC-", "width": 3}, "rule": {"pattern": "H[0-9]+"}}

    def setUp(self):
        self.p = Product({"ids": self.IDS, "adr": {"dir": "docs/decisions", "index": None},
                          "worktrees": {"dir": config.WORKTREES_DIR}})
        self.p.task("00001-first")
        self.p.task("00002-second", deps=["00001-first"])
        self.p.write("docs/decisions/007-pick.md",
                     "---\nid: DEC-007\ntitle: Pick\nstatus: accepted\ndate: 2026-11-01\n---\n\n# DEC-007 — Pick\n\n"
                     "## Decision\n\n### D1. The pick\n\nbody one\n")
        self.p.index()

    def tearDown(self):
        self.p.cleanup()

    def test_tasks_check_reads_the_width(self):
        self.assertEqual(tasklog.check(self.p.cfg), [])
        self.assertEqual(tasklog.next_number(self.p.cfg), "00003")
        self.p.task("0003-short")
        self.assertTrue(any("0003-short" in e for e in tasklog.check(self.p.cfg)))

    def test_merge_subject_and_branch_patterns_read_the_width(self):
        ids = refs.ids(self.p.cfg)
        self.assertEqual(ids.task_merge_subject_re.match("Task 00042: x").group(1), "00042")
        self.assertIsNone(ids.task_merge_subject_re.match("Task 0042: x"))
        self.assertEqual(ids.task_branch_re.search("task/00042-x").group(1), "00042")
        self.assertIsNone(ids.task_branch_re.search("task/0042-x"))

    def test_adr_check_and_refs_use_the_prefix_and_width(self):
        adrs, errs = adr.load(self.p.cfg)
        self.assertEqual(errs, [])
        self.assertEqual([a["id"] for a in adrs], ["DEC-007"])
        self.assertEqual(tasklog.adr_number("DEC-007 D1", self.p.cfg), 7)
        self.p.write("docs/decisions/008-bad.md",
                     "---\nid: ADR-0008\ntitle: Bad\nstatus: accepted\ndate: 2026-11-01\n---\n")
        self.assertTrue(any("DEC-008" in e for e in adr.load(self.p.cfg)[1]))

    def test_estimator_excerpt_finds_the_decision(self):
        out = estimator.adr_excerpts(self.p.cfg, ["007 D1", "DEC-007"])
        self.assertIn("body one", out)
        self.assertIn("Decisions: D1. The pick", out)

    def test_worktree_and_hook_names_use_the_number(self):
        cfg = self.p.cfg
        self.assertEqual(refs.ids(cfg).task_number("00002-second"), "00002")
        from ccp import prompt
        self.assertTrue(str(prompt.worktree_for(cfg, "rev", refs.ids(cfg).task_number("00002-second"))).endswith(f"{config.WORKTREES_DIR}/rev-00002"))

    def test_house_rules_use_the_pattern(self):
        parsed, errs = rules.parse_rules("- **H1** one\n  check: pass\n- **E2** not a rule here\n", refs.ids(self.p.cfg))
        self.assertEqual(list(parsed), ["H1"])

    def test_plane_json_rule_ids_follow_the_pattern(self):
        arch = {"rules_doc": "docs/ENGINEERING.md", "checks": [{"id": "H1", "cmd": "true"}]}
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "ids": self.IDS, "architect": arch}))
        self.assertEqual(self.p.cfg.architect["checks"][0]["id"], "H1")
        arch["checks"][0]["id"] = "E1"
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "ids": self.IDS, "architect": arch}))
        with self.assertRaises(config.ConfigError):
            self.p.cfg


if __name__ == "__main__":
    unittest.main()


class ReviewFixes(unittest.TestCase):
    """#89 review: consumers the first pass missed follow the configured ids."""

    def test_an_adr_prefix_that_reads_as_a_decision_is_refused(self):
        self.assertTrue(refs.validate({"adr": {"prefix": "D-"}}))
        self.assertTrue(refs.validate({"adr": {"prefix": "D"}}))
        self.assertEqual(refs.validate({"adr": {"prefix": "DEC-"}}), [])

    def test_review_point_summary_orders_by_the_configured_pattern(self):
        from ccp import reviewpoints
        ids = refs.Ids(review_point_pattern=r"RP-[0-9]+")
        rows = [{"task_id": f"000{i}-x", "status": "pending", "review_point": rp, "done_at": None}
                for i, rp in enumerate(["RP-10", "RP-2"])]
        got = [g["id"] for g in reviewpoints.summary(rows, {}, None, None, ids)]
        self.assertEqual(got, ["RP-2", "RP-10"])

    def test_estimator_reference_match_works_at_any_width(self):
        from ccp import estimator
        self.assertEqual(estimator._match("042", ["042-a", "043-b"]), "042-a")
        self.assertEqual(estimator._match("0042", ["0042-a"]), "0042-a")
        self.assertIsNone(estimator._match("42", ["0042-a"]))
