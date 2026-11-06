"""SPEC §28.3 priority 4, §28.3: the board's Quality section (architect passes and triage, house
rules and budgets, friction notes), its daily counters, and that agent-written text stays text."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from ccp import board, quality
from tests.helpers import TASK
from tests.test_toolkit import ToolkitFixture, git

RULES = """# Engineering

## Budgets

- **E1** Source files stay short.
  check: budget
- **E2** One registry.
  check: pass
- **E3** The import boundary holds.
  check: command
"""
HOSTILE = "x <!--<script> y </script><img src=x onerror=alert(1)> &amp;"


class Base(ToolkitFixture):
    def arch_on(self, **extra):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {
            "rules_doc": "docs/ENGINEERING.md", "every_n_tasks": 4, "notes_due": 3,
            "budgets": [{"id": "E1", "glob": "src/*.py", "max_lines": 3}],
            "checks": [{"id": "E3", "cmd": "false"}], **extra}}))
        self.write("docs/ENGINEERING.md", RULES)
        self.write("src/small.py", "a = 1\n")
        self.write("src/big.py", "a = 1\n" * 5)
        self.write("docs/delivery/tasks/0003-tidy.md", TASK.format(tid="0003-tidy", title="Tidy the registry", status="pending",
                                                                  deps="", ver="*Append-only.*")
                   .replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E2"]'))
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "architect on")

    def a_pass(self, rid="ar-20261020T100000Z-abcd", status="triaged", **rec):
        st = {"schema_version": 1, "reviews": {rid: {"mode": "pass", "status": status, "started_at": "2026-10-20T10:00:00Z",
                                                     "findings": 3, "rule_changes": 1, "done": ["0001-first"],
                                                     "tasks_created": ["0003-tidy", "0001-first"], **rec}},
              "last": {"review_id": rid, "started_at": "2026-10-20T10:00:00Z", "done": ["0001-first"]}}
        (self.q / "architect.json").write_text(json.dumps(st))
        (self.q / "reviews").mkdir(exist_ok=True)
        (self.q / "reviews" / f"{rid}.json").write_text(json.dumps({"findings": [
            {"id": "F01", "severity": "high", "category": "duplication"},
            {"id": "F02", "severity": "low", "category": "test-cost"},
            {"id": "F03", "severity": "low", "category": "test-cost"}]}))
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "dispositions": [{"finding": "F01", "disposition": "task"}, {"finding": "F02", "disposition": "task"},
                             {"finding": "F03", "disposition": "defer"}],
            "rule_changes": [{"rule": "E2", "action": "amend", "disposition": "applied", "reason": "r"}]}))
        return rid

    def note(self, at, by, text, task="0002-second", source="worker"):
        p = self.q / "health" / "notes.jsonl"
        p.parent.mkdir(exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps({"at": at, "task_id": task, "by": by, "source": source, "text": text}) + "\n")

    def build(self):
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text()), Path(body["page"]).read_text()


class Quality(Base, unittest.TestCase):

    def test_without_the_architect_block_only_friction_shows(self):
        self.note("2026-10-20T09:00:00Z", "implementer", "a fact in three places")
        b, page = self.build()
        q = b["quality"]
        self.assertIsNone(q["architect"])
        self.assertIsNone(q["rules"])
        self.assertEqual((q["friction"]["total"], q["friction"]["by_seat"]), (1, {"implementer": 1}))
        self.assertIn("function quality(", page)

    def test_passes_triage_and_the_tasks_triage_filed(self):
        self.arch_on()
        self.a_pass()
        b, _ = self.build()
        a = b["quality"]["architect"]
        p = a["passes"][0]
        self.assertEqual((p["status"], p["findings"], p["severity"]), ("triaged", 3, {"high": 1, "low": 2}))
        self.assertEqual(p["dispositions"], {"task": 2, "defer": 1})
        self.assertEqual(a["rule_dispositions_total"], {"applied": 1})
        self.assertEqual(a["severity_total"], {"high": 1, "low": 2})
        self.assertEqual([(t["task_id"], t["status"], t["kind"]) for t in p["tasks_created"]],
                         [("0003-tidy", "pending", "refactor"), ("0001-first", "done", "feature")])
        self.assertEqual((a["filed"]["total"], [t["task_id"] for t in a["filed"]["open"]]), (2, ["0003-tidy"]))
        self.assertEqual(a["filed"]["open"][0]["title"], "Tidy the registry")
        self.assertEqual((a["done_since_last"], a["settings"]["every_n_tasks"], a["due"]), (0, 4, True))
        self.assertIn("budget check fails: E1: src/big.py has 5 lines > 3", a["reason"])  # §19.6 #4
        self.assertEqual(a["last"]["review_id"], "ar-20261020T100000Z-abcd")
        status = self.ccp("board", "status", root=self.main)[2]
        self.assertIn("architect last pass ar-20261020T100000Z-abcd, 0/4 tasks and 0/3 notes since; pass due: budget", status)
        self.assertIn("architect tasks open 1 of 2 filed", status)

    def test_an_awaiting_report_shows_and_the_board_never_reaps_or_writes_architect_state(self):
        self.arch_on()
        rid = self.a_pass(status="running", started_at="2026-10-01T00:00:00Z")  # lock gone long ago: dead
        before = (self.q / "architect.json").read_text()
        b, _ = self.build()
        self.assertEqual((self.q / "architect.json").read_text(), before)  # no reap, no `seen` written
        self.assertEqual(b["quality"]["architect"]["running"], [rid])
        self.a_pass(status="reported")
        b, _ = self.build()
        self.assertEqual([w["review_id"] for w in b["quality"]["architect"]["awaiting_triage"]], [rid])
        self.assertEqual(b["quality"]["architect"]["dispositions_total"], {})  # only triaged passes count
        self.assertIn(f"architect {rid} awaits triage", self.ccp("board", "status", root=self.main)[2])

    def test_house_rules_budgets_measured_and_checks_named_not_run(self):
        self.arch_on()
        b, _ = self.build()
        r = b["quality"]["rules"]
        self.assertEqual((r["rules"], r["lines"], r["by_check"]), (3, len(RULES.splitlines()), {"budget": 1, "pass": 1, "command": 1}))
        self.assertEqual(r["checks"], ["E3"])  # named; `false` would fail if it ran
        self.assertEqual(r["doc_errors"], [])
        self.assertEqual(r["budgets"], [{"id": "E1", "target": "src/*.py", "measure": "max_lines", "limit": 3, "files": 2,
                                         "missing": 0, "over": 1, "max": 5, "max_path": "src/big.py",
                                         "missing_paths": []}])
        self.assertEqual(r["budgets_over"], 1)
        self.assertIn("house rules: 1 budget(s) over (E1 src/big.py 5>3)", self.ccp("board", "status", root=self.main)[2])

    def test_friction_counts_by_day_seat_and_source_latest_first(self):
        self.arch_on()
        self.note("2026-10-19T09:00:00Z", "implementer", "before the pass")
        self.note("2026-10-20T11:00:00Z", "reviewer", "after the pass")
        self.note("2026-10-20T12:00:00Z", None, "overdue: " + "long " * 100, task=None, source="allow-overdue")
        self.a_pass()
        f = self.build()[0]["quality"]["friction"]
        self.assertEqual((f["total"], f["since_last_pass"], f["notes_due"]), (3, 2, 3))
        self.assertEqual(f["by_seat"], {"implementer": 1, "reviewer": 1, "unknown": 1})
        self.assertEqual(f["by_source"], {"worker": 2, "allow-overdue": 1})
        self.assertEqual([n["text"][:9] for n in f["recent"]], ["overdue: ", "after the", "before th"])
        self.assertLessEqual(len(f["recent"][0]["text"]), quality.TEXT)
        self.assertEqual(sum(f["per_week"].values()), 3)
        self.assertEqual(len(f["per_day"]), quality.DAYS)

    def test_daily_counters_reach_history_and_the_trend(self):
        self.arch_on()
        self.note("2026-10-20T09:00:00Z", "verifier", "n")
        h = self.q / "board" / "history"
        h.mkdir(parents=True)
        (h / "2026-10-01.json").write_text(json.dumps({"date": "2026-10-01", "quality": {"friction_total": 0, "budgets_over": 0}}))
        (h / "2026-10-02.json").write_text(json.dumps({"date": "2026-10-02"}))  # before quality counters: skipped
        b, _ = self.build()
        hist = b["quality"]["history"]
        self.assertEqual([x["date"] for x in hist], ["2026-10-01", b["generated_at"][:10]])
        self.assertEqual((hist[-1]["friction_total"], hist[-1]["budgets_over"]), (1, 1))
        snap = json.loads((h / f"{b['generated_at'][:10]}.json").read_text())
        self.assertEqual(snap["quality"]["friction_total"], 1)
        self.assertEqual(snap["quality"]["passes"], 0)

    def test_agent_text_in_notes_titles_and_errors_cannot_break_the_page(self):
        self.arch_on()
        t = self.main / "docs/delivery/tasks/0003-tidy.md"
        t.write_text(t.read_text().replace("title: Tidy the registry", f"title: {HOSTILE}"))
        self.note("2026-10-20T11:00:00Z", "reviewer", HOSTILE, task="0002-</script>")
        self.a_pass(status="failed", error=HOSTILE, due_reason=HOSTILE)
        b, page = self.build()
        data = page.split("const B = ", 1)[1].split(";\nconst SEATS", 1)[0]
        for bad in ("<", ">", "&"):
            self.assertNotIn(bad, data)
        q = b["quality"]
        self.assertIn("<!--<script>", q["friction"]["recent"][0]["text"])  # kept as text in board.json
        self.assertIn("<!--<script>", q["architect"]["passes"][0]["error"])
        self.assertIn("<!--<script>", q["architect"]["filed"]["open"][0]["title"])
        self.assertEqual(page.count("<script>"), 1)  # the page's own, and nothing a note opened
        # The page renders every agent string through esc(): no raw interpolation of these fields.
        js = page.split("function quality(", 1)[1].split("function render()", 1)[0]
        for field in ("n.text", "p.error", "t.title", "p.due_reason", "n.task_id"):
            self.assertNotIn("${" + field + "}", js, field)
            self.assertNotIn("${" + field + " ||", js, field)

    def test_a_bad_architect_state_fails_that_section_only_and_keeps_the_days_counters(self):
        self.arch_on()
        self.a_pass()
        self.note("2026-10-20T11:00:00Z", "reviewer", "n")
        b, _ = self.build()
        self.assertEqual(b["quality"]["history"][-1]["passes"], 1)
        (self.q / "architect.json").write_text("{not json")
        b, page = self.build()
        q = b["quality"]
        self.assertIsNone(q["architect"])
        self.assertIn("architect", q["errors"])
        self.assertEqual((q["rules"]["budgets_over"], q["friction"]["total"]), (1, 1))  # the others still build
        day = b["generated_at"][:10]
        snap = json.loads((self.q / "board/history" / f"{day}.json").read_text())["quality"]
        self.assertEqual((snap["passes"], snap["friction_total"]), (1, 1))  # the earlier good value stands
        self.assertEqual(q["history"][-1]["passes"], 1)
        self.assertIn("quality architect failed:", self.ccp("board", "status", root=self.main)[2])
        self.assertIn("section failed", page)

    def test_a_bad_record_or_triage_file_is_counted_not_fatal(self):
        self.arch_on()
        rid = self.a_pass()
        st = json.loads((self.q / "architect.json").read_text())
        st["reviews"]["ar-20261019T100000Z-dead"] = "not a record"
        (self.q / "architect.json").write_text(json.dumps(st))
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({"dispositions": 7, "rule_changes": "x"}))
        a = self.build()[0]["quality"]["architect"]
        self.assertEqual(a["unreadable"], 1)
        self.assertEqual(([p["review_id"] for p in a["passes"]], a["passes"][0]["dispositions"]), ([rid], {}))
        self.assertIn("architect 1 pass record(s) unreadable", self.ccp("board", "status", root=self.main)[2])

    def test_non_utf8_notes_fail_friction_only(self):
        self.arch_on()
        (self.q / "health").mkdir(exist_ok=True)
        (self.q / "health" / "notes.jsonl").write_bytes(b'{"text": "\xff\xfe"}\n\xff\xfe\n')
        q = self.build()[0]["quality"]
        self.assertIsNone(q["friction"])
        self.assertIn("friction", q["errors"])
        self.assertIsNotNone(q["rules"])

    def test_severity_totals_count_triaged_passes_only(self):
        self.arch_on()
        self.a_pass(status="reported")
        a = self.build()[0]["quality"]["architect"]
        self.assertEqual(a["passes"][0]["severity"], {"high": 1, "low": 2})
        self.assertEqual(a["severity_total"], {})

    def test_the_review_point_scope_is_the_one_ccp_architect_due_uses(self):
        self.arch_on(budgets=[])
        (self.main / "docs/delivery/tasks/0003-tidy.md").unlink()
        (self.q / "work.json").write_text(json.dumps({"status": "idle", "scope": ["0001-first"]}))
        self.assertNotIn("review point", self.build()[0]["quality"]["architect"]["reason"])
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-first"]}))
        self.assertIn("review point closes", self.build()[0]["quality"]["architect"]["reason"])

    def test_status_names_a_missing_budget_file(self):
        self.arch_on(budgets=[{"id": "E1", "path": "docs/GONE.md", "max_bytes": 10}])
        r = self.build()[0]["quality"]["rules"]
        self.assertEqual((r["budgets_over"], r["budgets"][0]["missing_paths"]), (1, ["docs/GONE.md"]))
        self.assertIn("E1 docs/GONE.md missing", self.ccp("board", "status", root=self.main)[2])


def _hostile(v, key=None):
    """Every string gets the hostile suffix (a prefix would break slices and ids); count maps (all
    values numbers) get hostile keys too, since the page prints those keys."""
    if isinstance(v, str):
        return v + HOSTILE
    if isinstance(v, list):
        return [_hostile(x) for x in v]
    if isinstance(v, dict):
        counts = bool(v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values())
        return {(k + HOSTILE if counts else k): _hostile(x, k) for k, x in v.items()}
    return v


STUB = """
const out = [];
const el = () => ({style: {}, dataset: {}, addEventListener() {}, append(x) { out.push(x); }, setAttribute() {}});
globalThis.document = {createElement: () => { const t = {set innerHTML(h) { this.content = h; }}; return t; },
  getElementById: () => el(), querySelectorAll: () => [], documentElement: el()};
globalThis.localStorage = {getItem: () => null, setItem() {}};
globalThis.matchMedia = () => ({matches: false});
globalThis.innerWidth = 800; globalThis.innerHeight = 800;
globalThis.setTimeout = () => 0;
"""


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Rendered(Base, unittest.TestCase):
    def test_every_string_in_the_board_renders_as_text(self):
        """Render the whole page in node with every board string made hostile: any interpolation
        that skips esc(), under any name, puts a raw tag into the HTML."""
        self.arch_on()
        self.a_pass()
        self.note("2026-10-20T11:00:00Z", "reviewer", "n")
        b = self.build()[0]
        h = _hostile(b)
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(h)).split("<script>", 1)[1].split("</script>", 1)[0]
        r = subprocess.run(["node", "-e", STUB + js + "\nprocess.stdout.write(out.join(''));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        html = r.stdout
        self.assertIn("Architect passes and triage", html)
        self.assertIn("&lt;!--&lt;script&gt;", html)  # the hostile text is there, escaped
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)

    def test_a_section_error_renders_as_text(self):
        self.arch_on()
        (self.q / "architect.json").write_text("{not json")
        b = self.build()[0]
        b["quality"]["errors"]["architect"] = HOSTILE
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        html = subprocess.run(["node", "-e", STUB + js + "\nprocess.stdout.write(out.join(''));"],
                              capture_output=True, text=True, timeout=60).stdout
        self.assertIn("Architect section failed", html)
        self.assertNotIn("No architect block", html)
        self.assertNotIn("<img", html)


if __name__ == "__main__":
    unittest.main()
