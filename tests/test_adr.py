"""SPEC §6: ADRs — the frontmatter reader and writer, the checks, the commands and the index."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ccp import adr, cli, config, plan, tasklog
from tests.helpers import TASK, Product

try:
    import yaml  # only to cross-check the subset this module writes; the plane never imports it
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]


def fm(**kw) -> str:
    """An ADR file: frontmatter from the keyword arguments, then a body with decisions D1 and D2."""
    body = kw.pop("body", "# {id} — T\n\n## Decision\n\n### D1. First\n\nOne.\n\n### D2. Second\n\nTwo.\n")
    fields = {"title": "T", "status": "accepted", "date": "2026-01-01", **kw}
    return adr.emit(fields) + body.replace("{id}", str(fields.get("id", "")))


class Base(unittest.TestCase):
    cfg_block: dict = {"adr": {"dir": "docs/adr", "index": "docs/adr/INDEX.md"}}

    def setUp(self):
        self.p = Product(self.cfg_block)
        self.addCleanup(self.p.cleanup)

    def write_adr(self, name: str, **kw) -> Path:
        return self.p.write(f"docs/adr/{name}", fm(**kw))

    def task(self, tid: str, status: str, refs: list[str]) -> None:
        text = TASK.format(tid=tid, title="A task", status=status, deps="",
                           ver="- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*")
        text = text.replace('spec_refs: ["S1"]\n', 'spec_refs: ["S1"]\nadr_refs: [' + ", ".join(f'"{r}"' for r in refs) + "]\n")
        self.p.write(f"docs/delivery/tasks/{tid}.md", text)

    def ccp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def analyse(self):
        return adr.analyse(self.p.cfg)

    def index(self):
        adr.write_index(self.p.cfg)


class Frontmatter(Base):
    def test_a_good_set_is_clean_and_the_index_is_kept_current(self):
        self.write_adr("0001-a.md", id="ADR-0001", decisions=["D1 built", "D2 not_built"])
        self.write_adr("0002-b.md", id="ADR-0002")
        self.p.index()
        code, out, _ = self.ccp("docs", "check")
        self.assertIn("docs/adr/INDEX.md: missing — run `ccp adr index`", out)
        self.assertEqual(self.ccp("adr", "index")[0], 0)
        code, out, _ = self.ccp("docs", "check")
        self.assertEqual(code, 0, out)
        self.assertIn("| [ADR-0001](0001-a.md) | T | accepted | 2026-01-01 |", (self.p.root / "docs/adr/INDEX.md").read_text())
        self.write_adr("0002-b.md", id="ADR-0002", title="Pipe | renamed")
        self.assertIn("INDEX.md: stale — run `ccp adr index`", self.ccp("docs", "check")[1])

    def test_bad_frontmatter_is_named(self):
        for name, text in (
                ("0001-a.md", fm(id="ADR-0002")),
                ("0003-c.md", fm(id="ADR-0003", status="pondering")),
                ("0004-d.md", fm(id="ADR-0004", status="superseded")),
                ("0005-e.md", fm(id="ADR-0005", status="superseded", superseded_by="ADR-0099")),
                ("0007-g.md", fm(id="ADR-0007", date="1 Jan")),
                ("0008-h.md", "---\nid: ADR-0008\nthis is not yaml\n---\n# x\n"),
                ("0009-i.md", "# ADR-0009 — no frontmatter\n"),
                ("0010-j.md", fm(id="ADR-0010", decisions=["D1 shipped"])),
                ("0011-k.md", fm(id="ADR-0011", decisions=["D9 built"])),
                ("0012-l.md", fm(id="ADR-0012", decisions=["first is done"])),
                ("0013-m.md", fm(id="ADR-0013", decisions=["D1 built", "D1 live"])),
                ("0014-n.md", fm(id="ADR-0014", spec_refs="S1"))):
            self.p.write(f"docs/adr/{name}", text)
        text = "\n".join(self.analyse()[1])
        for why in ("does not match the file's number", "status 'pondering' is not one of", "needs `superseded_by",
                    "names no ADR", "not YYYY-MM-DD", "is not `key: value`", "no YAML frontmatter",
                    "state 'shipped' is not one of", "the body has no decision D9", "is not `Dn <state>",
                    "lists D1 twice", "`spec_refs` must be a list"):
            self.assertIn(why, text)

    def test_undeclared_keys_warn(self):
        self.write_adr("0001-a.md", id="ADR-0001", in_force="all of it", reasoning="because")
        self.index()
        _, errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.assertIn("undeclared frontmatter key(s): in_force, reasoning", "\n".join(warns))

    def test_review_points_without_a_register_warn_naming_the_adrs(self):
        self.write_adr("0001-a.md", id="ADR-0001", review_points=["R1"])
        self.write_adr("0002-b.md", id="ADR-0002")
        self.write_adr("0003-c.md", id="ADR-0003", review_points=["R1", "R2"])
        self.index()
        want = ("no review-point register: docs/delivery/review-points.yaml; the review points of ADR-0001, "
                "ADR-0003 are unchecked")
        self.p.index()
        for strict in (False, True):
            self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "adr": {
                "dir": "docs/adr", "index": "docs/adr/INDEX.md", "strict": strict}}))
            _, errs, warns = self.analyse()
            self.assertEqual(errs, [], strict)
            self.assertEqual([w for w in warns if "review-point register" in w], [want + " — create it (SPEC §22.3)"])
            code, out, _ = self.ccp("adr", "check")
            self.assertEqual((code, out.count(want)), (0, 1), out)
            code, out, _ = self.ccp("docs", "check")
            self.assertEqual((code, out.count(want)), (0, 1), out)
        self.p.write("docs/delivery/review-points.yaml", "review_points:\n  - id: R1\n    name: first\n"
                                                         "    goal: g\n    status: current\n"
                                                         "  - id: R2\n    name: second\n    goal: g\n"
                                                         "    status: planned\n")
        self.assertNotIn("review-point register", "\n".join(self.analyse()[2]))

    def test_no_review_points_and_no_register_say_nothing_of_a_register(self):
        self.write_adr("0001-a.md", id="ADR-0001")
        self.index()
        self.assertNotIn("review-point register", "\n".join(self.analyse()[2]))

    def test_without_the_block_nothing_is_read(self):
        p = Product()
        self.addCleanup(p.cleanup)
        p.write("docs/adr/0001-x.md", "# ADR-0001 — no frontmatter\n")
        self.assertEqual(adr.check(p.cfg), [])
        self.assertEqual(adr.warnings(p.cfg), [])

    def test_config_refuses_a_bad_block(self):
        for bad in ({"adr": {"dir": ""}}, {"adr": {"index": 3}}, {"adr": {"statuses": []}}, {"adr": {"other": 1}},
                    {"adr": "docs/adr"}, {"adr": {"strict": "yes"}}, {"adr": {"transitions": {"accepted": ["gone"]}}},
                    {"adr": {"transitions": ["accepted"]}}, {"adr": {"template": 3}}):
            self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **bad}))
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.p.root)

    def test_schemas_list_the_block_and_the_frontmatter(self):
        schema = json.loads((ROOT / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["adr"]["properties"]), set(config.ADR_DEFAULTS))
        fmschema = json.loads((ROOT / "contracts/adr.schema.json").read_text())
        self.assertEqual(set(fmschema["required"]), set(adr.REQUIRED))
        self.assertEqual(set(fmschema["properties"]), set(adr.REQUIRED + adr.OPTIONAL))


class Decisions(Base):
    def test_non_canonical_markers_warn_and_fail_under_strict(self):
        body = "# x\n\n## Decision\n\n- **D1. First.** one\n- **D2. Second.** two\n"
        self.write_adr("0001-a.md", id="ADR-0001", body=body)
        self.index()
        _, errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.assertIn("decision(s) D1, D2 not written `### Dn. Title`", "\n".join(warns))
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "adr": {"index": "docs/adr/INDEX.md",
                                                                                          "strict": True}}))
        self.assertIn("not written `### Dn. Title`", "\n".join(self.analyse()[1]))

    def test_duplicate_headings_and_order(self):
        body = "# x\n\n### D2. Two\n\nb\n\n### D1. One\n\na\n\n## Notes\n\n### D1. One again\n"
        self.write_adr("0001-a.md", id="ADR-0001", body=body)
        warns = "\n".join(self.analyse()[2])
        self.assertIn("more than one `### Dn.` heading for D1", warns)
        self.assertIn("decisions are not in number order (D2, D1)", warns)

    def test_a_later_reuse_of_an_id_is_not_a_decision(self):
        body = "# x\n\n### D1. One\n\na\n\n## Implementation notes\n\n- **D1.** notes for one\n"
        self.write_adr("0001-a.md", id="ADR-0001", body=body)
        self.assertEqual([d["id"] for d in adr.body_decisions(body)], ["1"])
        self.assertNotIn("not written", "\n".join(self.analyse()[2]))

    def test_migrate_markers_rewrites_only_the_marker_line(self):
        body = ("# x\n\n## Decision\n\n- **D1. A title.** first body\n  continued\n- **D2.** untitled body\n"
                "D3. **Para.** third\n**D4 — Lead** four\n- **D5 (F01). Noted.** five\n#### D6: Deep\n\nsix\n\n"
                "## Notes\n\n- **D1.** a later note\n")
        f = self.write_adr("0001-a.md", id="ADR-0001", body=body)
        before = {d: adr.decision_block(f.read_text(), d) for d in ("1", "2", "3", "4", "5", "6")}
        code, out, _ = self.ccp("adr", "migrate", "--markers", "--dry-run")
        self.assertIn("would rewrite docs/adr/0001-a.md: 6 decision marker(s)", out)
        self.assertEqual(f.read_text(), fm(id="ADR-0001", body=body))
        self.assertEqual(self.ccp("adr", "migrate", "--markers")[0], 0)
        text = f.read_text()
        for line in ("### D1. A title\n\nfirst body\n  continued", "### D2.\n\nuntitled body", "### D3. Para\n\nthird",
                     "### D4.\n\n**Lead** four", "### D5. Noted (F01)\n\nfive", "### D6. Deep\n"):
            self.assertIn(line, text)
        self.assertIn("- **D1.** a later note", text)        # not the decision: left alone
        for d, old in before.items():
            words = [w.strip(".:()*") for w in old.replace("**", " ").split() if len(w) > 3 and not w.startswith(("D", "#", "-"))]
            new = adr.decision_block(text, d)
            self.assertTrue(all(w in new for w in words), (d, old, new))
        self.assertEqual(self.ccp("adr", "migrate", "--markers")[1].splitlines()[-1], "0 file(s), 0 marker(s) rewritten")
        self.index()
        self.assertNotIn("not written", "\n".join(self.analyse()[2]))


class MigrateKeepsText(Base):
    def words(self, s):
        import re  # noqa: PLC0415
        from collections import Counter  # noqa: PLC0415
        return Counter(re.findall(r"[A-Za-z0-9]+", s))

    def test_titles_only_from_a_bold_run_that_ends_a_sentence(self):
        body = ("# x\n\n## Decision\n\n- **D1. Lifetimes: one and the\n  run record.** more\n"
                "- **D2. The daily job runs the build**, through the queue (always).\n"
                "- **D3. Clean title.**\n")
        f = self.write_adr("0001-a.md", id="ADR-0001", body=body)
        old = {d: adr.decision_block(f.read_text(), d) for d in ("1", "2", "3")}
        adr.migrate_markers(self.p.cfg)
        text = f.read_text()
        self.assertIn("### D1.\n\n**Lifetimes: one and the\n  run record.** more", text)
        self.assertIn("### D2.\n\n**The daily job runs the build**, through the queue (always).", text)
        self.assertIn("### D3. Clean title\n", text)
        for d, before in old.items():
            after = adr.decision_block(text, d)
            self.assertEqual(self.words(before), self.words(after), d)
            self.assertEqual(after.count("**") % 2, 0, after)
            self.assertFalse(any(ln.startswith((",", "(")) for ln in after.splitlines()[1:]), after)

    def test_a_decision_in_a_list_of_other_things_is_left_and_named(self):
        body = ("# x\n\n### D1. One\n\na\n\n## Amendment\n\n- **F01.** a finding\n- **D2. Two.** a new decision\n"
                "- **F03.** another finding\n")
        f = self.write_adr("0001-a.md", id="ADR-0001", body=body)
        code, out, _ = self.ccp("adr", "migrate", "--markers")
        self.assertIn("left      docs/adr/0001-a.md: D2 is one item of a list of other things", out)
        self.assertIn("- **D2. Two.** a new decision", f.read_text())


class Links(Base):
    def test_links_resolve_and_their_reverse_is_checked(self):
        self.write_adr("0001-a.md", id="ADR-0001", status="superseded", superseded_by="ADR-0002")
        self.write_adr("0002-b.md", id="ADR-0002", amends=["ADR-0003 D1"])
        self.write_adr("0003-c.md", id="ADR-0003", supersedes=["ADR-0004 D2"], decisions=["D1 built", "D2 built"])
        self.write_adr("0004-d.md", id="ADR-0004", decisions=["D1 built", "D2 live"])
        self.write_adr("0005-e.md", id="ADR-0005", amends=["ADR-0009", "ADR-0003 D7", "see the old one"])
        self.index()
        _, errs, warns = self.analyse()
        e, w = "\n".join(errs), "\n".join(warns)
        self.assertIn("0005-e.md: amends 'ADR-0009' names no ADR", e)
        self.assertIn("0005-e.md: amends 'ADR-0003 D7': docs/adr/0003-c.md has no decision D7", e)
        self.assertIn("0005-e.md: amends entry 'see the old one' is not `ADR-NNNN`", e)
        self.assertIn("0001-a.md: superseded_by 'ADR-0002', but docs/adr/0002-b.md does not list ADR-0001 in `supersedes`", w)
        self.assertIn("0003-c.md: supersedes 'ADR-0004 D2', but docs/adr/0004-d.md does not record D2 as retired", w)

    def test_prose_in_a_link_key_is_a_warning(self):
        self.write_adr("0001-a.md", id="ADR-0001", amends="ADR-0002 (its store), and the old run rule")
        self.write_adr("0002-b.md", id="ADR-0002")
        self.index()
        _, errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.assertIn("`amends` holds prose", "\n".join(warns))


class ReviewFixes(Base):
    def test_quotes_and_backslashes_survive_repeated_writes(self):
        f = self.write_adr("0001-a.md", id="ADR-0001")
        note = 'said "no" \\ then C:\\path'
        for _ in range(3):
            adr.decide(self.p.cfg, "1", "D1", "built", note=note)
            adr.decide(self.p.cfg, "1", "D2", "live", note='a "quoted" one')
            adr.set_status(self.p.cfg, "1", "retired", note=note) if _ == 2 else None
        meta = adr.parse(adr.split(f.read_text())[0])
        self.assertEqual(adr.parse_decision(meta["decisions"][0])["note"], note)
        self.assertIn(note, meta["notes"])

    def test_built_counts_unrecorded_as_not_built_and_all_retired_is_na(self):
        self.write_adr("0001-a.md", id="ADR-0001", decisions=["D1 built"])
        self.write_adr("0002-b.md", id="ADR-0002", decisions=["D1 retired", "D2 retired"])
        reg = {i["id"]: i for i in plan.adr_register(self.p.cfg, [])["items"]}
        self.assertEqual((reg["ADR-0001"]["built_pct"], reg["ADR-0001"]["built_decisions"],
                          reg["ADR-0001"]["standing_decisions"]), (50, 1, 2))
        self.assertEqual((reg["ADR-0002"]["built_pct"], reg["ADR-0002"]["built_from"]), (None, "decisions"))

    def test_decide_by_needs_a_real_decision_and_archive_refuses_decisions(self):
        self.write_adr("0001-a.md", id="ADR-0001")
        self.write_adr("0002-b.md", id="ADR-0002")
        with self.assertRaises(adr.AdrError):
            adr.decide(self.p.cfg, "1", "D1", "retired", by="ADR-0002 D9")
        adr.decide(self.p.cfg, "1", "D1", "retired", by="ADR-0002 D1")
        with self.assertRaises(adr.AdrError):
            adr.supersede(self.p.cfg, "1", "2", ["D2"], archive=True)

    def test_reverse_links_without_decisions_and_whole_vs_decision(self):
        self.write_adr("0001-a.md", id="ADR-0001", status="superseded", superseded_by="ADR-0002")
        self.write_adr("0002-b.md", id="ADR-0002", supersedes=["ADR-0001 D1", "ADR-0003 D2"])
        self.write_adr("0003-c.md", id="ADR-0003")
        self.index()
        w = "\n".join(self.analyse()[2])
        self.assertIn("0001-a.md: superseded_by 'ADR-0002', but docs/adr/0002-b.md does not list ADR-0001", w)
        self.assertIn("0002-b.md: supersedes 'ADR-0003 D2', but docs/adr/0003-c.md does not record D2 as retired", w)

    def test_crlf_frontmatter_and_tilde_fences(self):
        text = fm(id="ADR-0001", body="# x\n\n### D1. One\n\n~~~\n### D1. not a heading\n- **D3. Fenced.** no\n~~~\n\n### D2. Two\n")
        f = self.p.write("docs/adr/0001-a.md", text.replace("\n", "\r\n"))
        self.index()
        adrs, errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.assertEqual([d["id"] for d in adrs[0]["_decisions"]], ["1", "2"])
        self.assertNotIn("more than one", "\n".join(warns))
        adr.decide(self.p.cfg, "1", "D2", "built")
        self.assertIn(b"\r\ndecisions: [\"D2 built\"]\r\n---\r\n", f.read_bytes())

    def test_accepting_fills_the_decisions_not_yet_recorded(self):
        f = self.write_adr("0001-a.md", id="ADR-0001", status="proposed", decisions=["D2 built"])
        adr.set_status(self.p.cfg, "1", "accepted")
        self.assertEqual(adr.parse(adr.split(f.read_text())[0])["decisions"], ["D1 not_built", "D2 built"])

    def test_the_index_header_names_the_command(self):
        self.write_adr("0001-a.md", id="ADR-0001")
        self.assertIn("Generated by `ccp adr index`", adr.render_index(self.p.cfg))


class Tasks(Base):
    def test_task_refs_must_name_a_real_decision_and_in_force_is_checked(self):
        self.write_adr("0001-a.md", id="ADR-0001", decisions=["D1 not_built", "D2 built"])
        self.task("0001-x", "done", ["0001 D1", "0001 D2"])
        self.task("0002-y", "pending", ["0001 D9", "ADR-0001 D1", "0001 Acceptance tests arms-1"])
        self.task("0003-z", "pending", ["0042 D1"])
        self.index()
        _, errs, warns = self.analyse()
        e, w = "\n".join(errs), "\n".join(warns)
        self.assertIn("0002-y: adr_refs '0001 D9': docs/adr/0001-a.md has no decision D9", e)
        self.assertIn("0003-z: adr_refs '0042 D1' names no ADR", e)
        self.assertNotIn("Acceptance", e)                           # a section anchor is not a decision
        self.assertIn("0001-x: done, and cites ADR-0001 D1, which docs/adr/0001-a.md records as not_built", w)
        self.assertNotIn("D2, which", w)


class Commands(Base):
    def test_new_status_decide_and_list(self):
        self.write_adr("0001-a.md", id="ADR-0001")
        self.index()
        code, out, _ = self.ccp("adr", "new", "Queue", "rework!")
        self.assertEqual(code, 0, out)
        f = self.p.root / "docs/adr/0002-queue-rework.md"
        meta = adr.parse(adr.split(f.read_text())[0])
        self.assertEqual((meta["id"], meta["title"], meta["status"]), ("ADR-0002", "Queue rework!", "proposed"))
        self.assertIn("### D1. ", f.read_text())
        self.assertEqual(self.ccp("adr", "status", "2", "retired")[0], 1)    # proposed → retired is not a move
        code, out, _ = self.ccp("adr", "status", "ADR-0002", "accepted", "--note", "agreed in review")
        self.assertEqual(code, 0, out)
        meta = adr.parse(adr.split(f.read_text())[0])
        self.assertEqual((meta["status"], meta["decisions"]), ("accepted", ["D1 not_built"]))
        self.assertIn("status proposed → accepted: agreed in review", meta["notes"])
        self.assertEqual(self.ccp("adr", "decide", "2", "D1", "built")[0], 0)
        self.assertEqual(adr.parse(adr.split(f.read_text())[0])["decisions"], ["D1 built"])
        self.assertEqual(self.ccp("adr", "decide", "2", "D7", "built")[0], 2)
        self.assertEqual(self.ccp("adr", "status", "2", "superseded")[0], 2)  # supersede links both sides
        code, out, _ = self.ccp("adr", "list")
        self.assertIn("built 1/1", out)
        code, out, _ = self.ccp("adr", "check")
        self.assertEqual(code, 0, out)

    def test_a_command_keeps_every_other_line(self):
        text = fm(id="ADR-0001", in_force="kept\nas written", deciders="the team") + "\ntrailing\n"
        f = self.p.write("docs/adr/0001-a.md", text)
        adr.decide(self.p.cfg, "1", "D2", "live", note="rolled out")
        new = f.read_text()
        self.assertEqual(new.replace('decisions: ["D2 live — rolled out"]\n', ""), text)

    def test_supersede_whole_and_partial(self):
        self.write_adr("0001-a.md", id="ADR-0001", decisions=["D1 built", "D2 built"])
        self.write_adr("0002-b.md", id="ADR-0002")
        self.write_adr("0003-c.md", id="ADR-0003", decisions=["D1 built", "D2 built"])
        self.index()
        code, out, _ = self.ccp("adr", "supersede", "1", "2", "--archive")
        self.assertEqual(code, 0, out)
        old = self.p.root / "docs/adr/archive/0001-a.md"
        self.assertTrue(old.is_file())
        mo = adr.parse(adr.split(old.read_text())[0])
        self.assertEqual((mo["status"], mo["superseded_by"], mo["decisions"]),
                         ("superseded", ["ADR-0002"], ["D1 retired by ADR-0002", "D2 retired by ADR-0002"]))
        self.assertEqual(adr.parse(adr.split((self.p.root / "docs/adr/0002-b.md").read_text())[0])["supersedes"], ["ADR-0001"])
        code, out, _ = self.ccp("adr", "supersede", "3", "2", "--decisions", "D2", "--by", "D1")
        self.assertEqual(code, 0, out)
        mc = adr.parse(adr.split((self.p.root / "docs/adr/0003-c.md").read_text())[0])
        self.assertEqual((mc["status"], mc["decisions"]), ("accepted", ["D1 built", "D2 retired by ADR-0002 D1"]))
        self.assertEqual(adr.parse(adr.split((self.p.root / "docs/adr/0002-b.md").read_text())[0])["supersedes"],
                         ["ADR-0001", "ADR-0003 D2"])
        code, out, _ = self.ccp("adr", "check")
        self.assertEqual(code, 0, out)
        self.assertNotIn("warning", out)

    def test_docs_adr_is_an_alias_and_convert_is_gone(self):
        self.write_adr("0001-a.md", id="ADR-0001")
        self.assertEqual(self.ccp("docs", "adr", "index")[0], 0)
        code, out, _ = self.ccp("docs", "adr", "list", "--json")
        self.assertEqual([a["id"] for a in json.loads(out)["adrs"]], ["ADR-0001"])
        with self.assertRaises(SystemExit):
            self.ccp("docs", "adr", "convert")


class OtherIds(Base):
    cfg_block = {"adr": {"dir": "decisions", "index": None}, "ids": {"adr": {"prefix": "DEC-", "width": 3}}}

    def test_prefix_and_width_follow_ids(self):
        self.p.write("decisions/001-a.md", fm(id="DEC-001", decisions=["D1 not_built", "D2 built"]))
        self.p.write("decisions/002-b.md", fm(id="DEC-002", supersedes=["DEC-001 D2"]))
        self.task("0001-x", "done", ["DEC-001 D1", "001 D2"])
        _, errs, warns = self.analyse()
        self.assertEqual(errs, [])
        self.assertIn("cites DEC-001 D1, which decisions/001-a.md records as not_built", "\n".join(warns))
        self.assertIn("decisions/002-b.md: supersedes 'DEC-001 D2', but decisions/001-a.md does not record D2 as retired",
                      "\n".join(warns))
        f = adr.new(self.p.cfg, "Third one")
        self.assertEqual(f.name, "003-third-one.md")
        self.assertEqual(adr.parse(adr.split(f.read_text())[0])["id"], "DEC-003")


class Board(Base):
    def test_built_comes_from_decisions_when_recorded(self):
        self.write_adr("0001-a.md", id="ADR-0001", decisions=["D1 built", "D2 retired by ADR-0002"])
        self.write_adr("0002-b.md", id="ADR-0002", decisions=["D1 not_built", "D2 live"])
        self.write_adr("0003-c.md", id="ADR-0003")
        self.task("0001-x", "done", ["0003 D1"])
        self.task("0002-y", "pending", ["0003 D2"])
        reg = {i["id"]: i for i in plan.adr_register(self.p.cfg, tasklog.load(self.p.cfg))["items"]}
        self.assertEqual((reg["ADR-0001"]["built_pct"], reg["ADR-0001"]["built_from"]), (100, "decisions"))
        self.assertEqual((reg["ADR-0002"]["built_pct"], reg["ADR-0002"]["built_from"]), (50, "decisions"))
        self.assertEqual((reg["ADR-0003"]["built_pct"], reg["ADR-0003"]["built_from"]), (50, "tasks"))
        self.assertEqual(reg["ADR-0001"]["decisions"], [{"id": "D1", "state": "built", "by": None},
                                                        {"id": "D2", "state": "retired", "by": "ADR-0002"}])


class Subset(unittest.TestCase):
    def test_reader_takes_hand_written_forms(self):
        got = adr.parse("id: ADR-0001  # a comment\ntitle: 'It''s here'\nlist: [a, \"b, c\"]\nblock:\n  - one\n  - \"two\"\n"
                        "text: |\n  line one\n\n  line three\n")
        self.assertEqual(got, {"id": "ADR-0001", "title": "It's here", "list": ["a", "b, c"], "block": ["one", "two"],
                               "text": "line one\n\nline three\n"})

    def test_writer_indents_a_block_that_starts_with_spaces(self):
        f = {"id": "ADR-0001", "x": "  lead\nnext"}
        self.assertEqual(adr.parse(adr.split(adr.emit(f) + "rest")[0]), f)
        self.assertIn("x: |2-", adr.emit(f))

    def test_long_link_and_decision_lists_are_written_one_per_line_and_read_back(self):
        f = {"id": "ADR-0001", "decisions": [f"D{i} built" for i in range(1, 6)], "supersedes": ["ADR-0002 D1"]}
        out = adr.emit(f)
        self.assertIn("decisions:\n  - ", out)
        self.assertEqual(adr.parse(adr.split(out)[0]), f)

    def test_keys_that_read_as_booleans_are_refused_and_controls_escaped(self):
        with self.assertRaises(ValueError):
            adr.emit({"on": "x"})
        v = "a b c\x85d\x7fe\x01f\x9fg﻿h"
        out = adr.emit({"id": "ADR-0001", "x": v, "two": v + "\nsecond line"})
        self.assertFalse(adr.UNSAFE_RE.search(out))
        self.assertEqual(adr.parse(adr.split(out)[0]), {"id": "ADR-0001", "x": v, "two": v + "\nsecond line"})

    @unittest.skipUnless(yaml, "PyYAML is not installed")
    def test_fuzz_values_read_the_same_in_both_readers(self):
        import random  # noqa: PLC0415
        rnd = random.Random(28)
        alphabet = (list("abc XYZ:#-[]{}|>'\",&*!%@`?\\") + ["\n", "\t", "\r", "\x00", "\x1b", "\x7f", "\x85", "\xa0",
                    " ", " ", "﻿", "é", "—", "😀", "  "])
        for _ in range(3000):
            v = "".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, 24)))
            fields = {"id": "ADR-0001", "value": v, "listed": [v.strip() or "x"]}
            front = adr.split(adr.emit(fields))[0]
            self.assertEqual(adr.parse(front)["value"], v, repr(v))
            self.assertEqual(yaml.safe_load(front)["value"], v, repr(v))


if __name__ == "__main__":
    unittest.main()
