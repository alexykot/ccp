"""SPEC §22.4: the review-point register (names, goals, strict R<n> ids), tasks and ADRs
attached at planning time, the tag and migrate tools, the spawn from tagged tasks, and the board's
review-point cards, filters and Now line."""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import adr, backfill, board, cli, plan, reviewpoints, tasklog
from tests.helpers import TASK, Product
from tests.test_backfill import GIT_ENV, claim, ev, spawn
from tests.test_board_quality import HOSTILE, STUB, Base, _hostile
from tests.test_team_hosting import TeamCase

REGISTER = """# The review points (product-owned; SPEC §22)
review_points:
  - id: R7
    name: the earlier team's work, reviewed
    goal: Fold the earlier team's work into tasks.
    status: closed
    opened: 2026-10-20
    closed: 2026-10-22
  - id: R8
    name: pre-beta   # the operator's name
    goal: |-
      After this review point's tasks are done,
      we run the beta test.
    status: current
    opened: "2026-10-22"
  - id: R10
    name: "after the beta test"
    goal: 'What the beta test teaches.'
    status: planned
"""


def _git_init(root: Path) -> None:
    for c in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(root), *c], check=True, capture_output=True, env={**os.environ, **GIT_ENV})


def _tagged(p: Product, tid: str, status: str = "pending", rp: str | None = None, deps=None, extra: str = "") -> Path:
    f = p.task(tid, status, deps)
    add = (f"review_point: {rp}\n" if rp else "") + extra
    if add:
        f.write_text(f.read_text().replace("updated: 2026-09-30\n", "updated: 2026-09-30\n" + add))
    return f


class Register(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)

    def reg(self, text: str):
        self.p.write("docs/delivery/review-points.yaml", text)
        return reviewpoints.load(self.p.cfg)

    def test_reads_the_register(self):
        entries, errs = self.reg(REGISTER)
        self.assertEqual(errs, [])
        by = {e["id"]: reviewpoints.public(e) for e in entries}
        self.assertEqual(by["R8"], {"id": "R8", "name": "pre-beta", "goal": "After this review point's tasks are done,\nwe run the beta test.",
                                    "status": "current", "opened": "2026-10-22", "closed": None})
        self.assertEqual((by["R10"]["name"], by["R10"]["goal"]), ("after the beta test", "What the beta test teaches."))
        self.assertEqual(reviewpoints.current(entries)["id"], "R8")
        # a top-level list, with no `review_points:` key, reads the same; CRLF too
        entries2, errs2 = self.reg(REGISTER.split("review_points:\n", 1)[1].replace("\n  ", "\n").lstrip().replace("\n", "\r\n"))
        self.assertEqual((errs2, [e["id"] for e in entries2]), ([], ["R7", "R8", "R10"]))
        self.assertEqual(self.reg("review_points: []\n"), ([], []))

    def test_no_register_keeps_the_pattern_rule(self):
        self.assertEqual(reviewpoints.load(self.p.cfg), (None, []))
        self.assertIsNone(reviewpoints.problem(self.p.cfg, "R99"))
        self.assertIsNone(reviewpoints.problem(self.p.cfg, "R0"))  # the default pattern, ^R[0-9]+$
        for bad in ("PM", "r1", "", None, 8):
            self.assertIn("does not match task_log.review_point_pattern", reviewpoints.problem(self.p.cfg, bad), bad)
        self.assertEqual(reviewpoints.notes(self.p.cfg), [])  # no task uses a review point: nothing to say
        _tagged(self.p, "0001-a", "pending", "R1")
        self.assertEqual(reviewpoints.notes(self.p.cfg), ["no review-point register: docs/delivery/review-points.yaml; "
                                                          "review points are unchecked — create it (SPEC §22.1)"])
        # with the register the rule is strict, and a pattern in plane.json is ignored with a warning
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "task_log": {"review_point_pattern": "^(R[0-9]+|PM)$"}}))
        self.assertIsNone(reviewpoints.problem(self.p.cfg, "PM"))
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        self.assertIn("is not R<number>", reviewpoints.problem(self.p.cfg, "PM"))
        self.assertIn("is not R<number>", reviewpoints.problem(self.p.cfg, "R0"))
        self.assertIn("review_point_pattern is ignored", reviewpoints.notes(self.p.cfg)[0])

    def test_validation(self):
        _, errs = self.reg("""review_points:
  - id: R0
    name: x
    goal: g
    status: planned
  - id: PM
    name: pre-beta
    goal: g
    status: current
  - id: R2
    name: a name far longer than forty characters, which is a sentence
    goal: ""
    status: current
    opened: 2026-13-01
    closed: 2026-10-01
    owner: me
  - id: R2
    name: ""
    goal: g
    status: open
  - id: R3
    name: three
    goal: g
    status: closed
    opened: 2026-10-05
    closed: 2026-10-01
""")
        text = "\n".join(errs)
        for why in ("id 'R0' is not R<number>", "id 'PM' is not R<number>", "name is 60 characters", "R2 has no goal",
                    "opened '2026-13-01' is not a date", "has a closed date but its status is 'current'",
                    "unknown key(s) owner", "id R2 is also at line", "R2 has no name", "status 'open' is not one of",
                    "R3 closes before it opens", "2 review points are current (PM, R2)"):
            self.assertIn(why, text)
        _, errs = self.reg("review_points:\n  - id: R1\n    name: \"unclosed\n")
        self.assertTrue(errs and "item at line 2" in errs[0], errs)
        _, errs = self.reg("points:\n  - id: R1\n")
        self.assertIn("is not a list item", errs[0])

    def test_tasks_check_and_docs_check_refuse_unknown_points(self):
        self.reg(REGISTER)
        _tagged(self.p, "0001-a", "done", "R7")
        _tagged(self.p, "0002-b", "pending", "R8")
        _tagged(self.p, "0003-c", "pending", "R9")
        _tagged(self.p, "0004-d", "pending", "PM")
        self.p.index()
        errs = [e for e in tasklog.check(self.p.cfg) if "review point" in e]
        self.assertEqual(len(errs), 2, errs)
        self.assertIn("0003-c.md: review point R9 is not in the register docs/delivery/review-points.yaml", errs[0])
        self.assertIn("0004-d.md: review point 'PM' is not R<number>", errs[1])
        self.p.write("docs/delivery/review-points.yaml", REGISTER + "  - id: R1\n    name: x\n")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.p.root), "docs", "check"])
        self.assertEqual(code, 1)
        self.assertIn("R1 has no goal", out.getvalue())

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_wi_shaped_product_without_a_register_checks_as_before(self):
        """Merging this is a live release: a product with `PM` tasks, its widened pattern and no register
        gets the same exit codes as before, and one warning naming the missing register."""
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "task_log": {"review_point_pattern": "^(R[0-9]+|PM)$"}}))
        _tagged(self.p, "0001-a", "done", "R7")
        _tagged(self.p, "0002-b", "done", "PM")
        _tagged(self.p, "0003-c", "pending")
        self.p.index()
        for cmd in (("tasks", "check"), ("docs", "check")):
            code, out, err = self.run_cli(*cmd)
            self.assertEqual(code, 0, out + err)
            self.assertEqual((out + err).count("no review-point register: docs/delivery/review-points.yaml; review points "
                                               "are unchecked — create it (SPEC §22.1)"), 1, cmd)
        # the same product with the default pattern fails on PM exactly as before
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))
        code, out, _ = self.run_cli("tasks", "check")
        self.assertEqual(code, 1)
        self.assertIn("0002-b.md: review_point 'PM' does not match task_log.review_point_pattern (^R[0-9]+$, SPEC §22)", out)

    def test_with_the_register_a_pattern_key_is_ignored_and_warned(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "task_log": {"review_point_pattern": "^(R[0-9]+|PM)$"}}))
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.p, "0001-a", "done", "PM")
        self.p.index()
        code, out, _ = self.run_cli("tasks", "check")
        self.assertEqual(code, 1)
        self.assertIn("review point 'PM' is not R<number>", out)
        self.assertIn("warning: docs/delivery/plane.json: task_log.review_point_pattern is ignored", out)

    def test_a_custom_register_path(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "review_points": {"file": "docs/RP.yaml"}}))
        self.p.write("docs/RP.yaml", REGISTER)
        self.assertEqual(reviewpoints.known(reviewpoints.load(self.p.cfg)[0]), {"R7", "R8", "R10"})


class Adrs(unittest.TestCase):
    def setUp(self):
        self.p = Product({"adr": {"index": "docs/adr/INDEX.md"}})
        self.addCleanup(self.p.cleanup)
        self.p.write("docs/adr/0001-a.md", "---\nid: ADR-0001\ntitle: A\nstatus: accepted\ndate: 2026-10-01\n---\n# ADR-0001 — A\n")

    def test_the_field_is_validated_against_the_register_and_the_index_gains_a_column(self):
        adr.write_index(self.p.cfg)
        plain = (self.p.root / "docs/adr/INDEX.md").read_text()
        self.assertNotIn("Review points", plain)  # an index written before the field stays current
        self.assertEqual(adr.check(self.p.cfg), [])
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        self.p.write("docs/adr/0002-b.md", "---\nid: ADR-0002\ntitle: B\nstatus: accepted\ndate: 2026-10-02\n"
                                           "review_points: [R8, R10]\n---\n# ADR-0002 — B\n")
        self.p.write("docs/adr/0003-c.md", "---\nid: ADR-0003\ntitle: C\nstatus: accepted\ndate: 2026-10-02\n"
                                           "review_points:\n  - R9\n  - PM\n---\n# ADR-0003 — C\n")
        self.p.write("docs/adr/0004-d.md", "---\nid: ADR-0004\ntitle: D\nstatus: accepted\ndate: 2026-10-02\n"
                                           "review_points: R8\n---\n# ADR-0004 — D\n")
        errs = adr.check(self.p.cfg)
        self.assertTrue(any("0003-c.md: review_points: review point R9 is not in the register" in e for e in errs), errs)
        self.assertTrue(any("0003-c.md: review_points: review point 'PM' is not R<number>" in e for e in errs), errs)
        self.assertTrue(any("0004-d.md: `review_points` must be a list" in e for e in errs), errs)
        idx = adr.render_index(self.p.cfg)
        self.assertIn("| Superseded by | Review points |", idx)
        self.assertIn("|  | R8, R10 |", idx)

    def test_built_per_point_on_the_register(self):
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        self.p.write("docs/adr/0002-b.md", "---\nid: ADR-0002\ntitle: B\nstatus: accepted\ndate: 2026-10-02\n"
                                           "review_points: [R8]\n---\n# ADR-0002 — B\n")
        _tagged(self.p, "0001-a", "done", "R7", extra='adr_refs: ["0002"]\n')
        _tagged(self.p, "0002-b", "done", "R8", extra='adr_refs: ["0002"]\n')
        _tagged(self.p, "0003-c", "pending", "R8", extra='adr_refs: ["0002"]\n')
        _tagged(self.p, "0004-d", "pending", "R8", extra='adr_refs: ["0001"]\n')
        q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, q)
        P = plan.collect(self.p.cfg, q, {"review_point": "R8", "scope": ["0003", "0004"]}, today="2026-10-22")
        by = {i["id"]: i for i in P["adrs"]["items"]}
        self.assertEqual(by["ADR-0002"]["review_points"], ["R8"])
        self.assertEqual(by["ADR-0002"]["by_point"], {"R7": {"tasks": 1, "done": 1, "built_pct": 100},
                                                      "R8": {"tasks": 2, "done": 1, "built_pct": 50}})
        self.assertEqual(by["ADR-0002"]["built_pct"], 67)
        r8 = next(g for g in P["review_points"] if g["id"] == "R8")
        self.assertEqual([(a["id"], a["named"], a["point"]) for a in r8["adrs"]],
                         [("ADR-0001", False, {"tasks": 1, "done": 0, "built_pct": 0}),
                          ("ADR-0002", True, {"tasks": 2, "done": 1, "built_pct": 50})])


class Summary(unittest.TestCase):
    """plan.collect's review points with a register: number order, the register's fields, current."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q)

    def collect(self, **work):
        return plan.collect(self.p.cfg, self.q, {"status": "running", **work}, today="2026-10-22")

    def test_number_order_register_fields_and_open_counts(self):
        self.p.write("docs/delivery/review-points.yaml", REGISTER.replace("R10", "R9"))
        _tagged(self.p, "0001-a", "done", "R7")
        _tagged(self.p, "0002-b", "blocked", "R8")
        _tagged(self.p, "0003-c", "pending", "R8")
        _tagged(self.p, "0004-d", "dropped", "R8")
        _tagged(self.p, "0005-e", "pending")
        P = self.collect(review_point="R8", scope=["0002", "0003", "0005"])
        rp = P["review_points"]
        self.assertEqual([g["id"] for g in rp], ["R7", "R8", "R9"])
        r8 = rp[1]
        self.assertEqual({k: r8[k] for k in ("name", "status", "opened", "current", "runner", "tasks", "done", "remaining",
                                            "dropped", "unstamped", "open", "open_ids")},
                         {"name": "pre-beta", "status": "current", "opened": "2026-10-22", "current": True, "runner": True,
                          "tasks": 3, "done": 0, "remaining": 3, "dropped": 1, "unstamped": 1,
                          "open": {"pending": 3, "in_progress": 0, "blocked": 0}, "open_ids": ["0002-b", "0003-c", "0005-e"]})
        self.assertEqual((rp[2]["tasks"], rp[2]["status"], rp[2]["current"]), (0, "planned", False))
        self.assertEqual(P["register"], {"path": "docs/delivery/review-points.yaml", "exists": True, "errors": [],
                                         "current": "R8", "runner": "R8", "mismatch": None})
        self.assertIn("review point R8 pre-beta 0/3", plan.status_lines(P)[0])
        ready = {r["task_id"]: r["review_point"] for r in P["ready"]["items"]}
        self.assertEqual(ready, {"0002-b": "R8", "0003-c": "R8", "0005-e": None})  # legacy blocked reads as pending (§5.3)

    def test_without_a_register_points_sort_by_number_and_legacy_names_last(self):
        for i, rp in enumerate(("R10", "R9", "PM", "R2"), 1):
            _tagged(self.p, f"000{i}-t", "done", rp)
        P = self.collect(review_point="PM")
        self.assertEqual([g["id"] for g in P["review_points"]], ["R2", "R9", "R10", "PM"])
        self.assertEqual([g["id"] for g in P["review_points"] if g["current"]], ["PM"])
        self.assertFalse(P["register"]["exists"])

    def test_a_runner_off_the_register_is_reported(self):
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        self.assertIn("the runner works on R7; the register's current point is R8",
                      self.collect(review_point="R7")["register"]["mismatch"])
        self.assertIn("review point 'PM' is not R<number>", self.collect(review_point="PM")["register"]["mismatch"])


class Tools(unittest.TestCase):
    """`ccp review-points tag` and `migrate`: working tree only, bytes kept, the queue through its writers."""

    def setUp(self):
        self.p = Product({"reconcile": {"log": {"path": "docs/LOG.md",
                                                "entry": "**{date} (runner, {review_point}):** `{nnnn}` done: {summary}."}}})
        self.addCleanup(self.p.cleanup)
        self.p.write("docs/LOG.md", "# Log\n\n**2026-10-22 (runner, PM):** `0001` done: x.\n")
        self.p.write("docs/delivery/review-points.yaml", REGISTER)
        self.a = _tagged(self.p, "0001-a", "done", "PM")
        self.b = _tagged(self.p, "0002-b", "done")
        self.b.write_text(self.b.read_text().replace("updated: 2026-09-30\n", "updated: 2026-09-30\nreview_point: 'PM'   # pre-beta\n"))
        self.b.write_bytes(self.b.read_bytes().replace(b"\n", b"\r\n"))
        self.c = _tagged(self.p, "0003-c", "pending")
        self.d = _tagged(self.p, "0004-d", "pending")
        self.p.index()
        _git_init(self.p.root)
        self.q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.q)
        (self.q / "observability").mkdir()
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\n")
        (self.q / "work.json").write_text(json.dumps({"status": "running", "review_point": "PM", "scope": ["0003-c", "0004-d"]}))
        (self.q / "observability" / "events.jsonl").write_text(json.dumps(spawn("2026-10-22T10:00:00Z", "PM", ["0003-c"])) + "\n")
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(self.q), "ACTOR": "design-seat"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def rp(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "review-points", *args])
        return code, out.getvalue(), err.getvalue()

    def snapshot(self):
        return {f: f.read_bytes() for f in (self.a, self.b, self.c, self.d)} | {"work": (self.q / "work.json").read_bytes(),
                                                                               "events": (self.q / "observability/events.jsonl").read_bytes()}

    def test_migrate_dry_run_writes_nothing_and_lists_what_it_would_touch(self):
        before = self.snapshot()
        code, out, err = self.rp("migrate", "--from", "PM", "--to", "R8", "--dry-run", "--json")
        self.assertEqual(code, 0, err)
        body = json.loads(out)
        self.assertEqual([r["task_id"] for r in body["tasks"]], ["0001-a", "0002-b"])
        self.assertEqual(body["queue"]["work_json"], {"review_point": "PM", "change": True})
        self.assertEqual(body["queue"]["ledger"]["events"], 1)
        self.assertEqual(body["product_log"], {"path": "docs/LOG.md", "tasks": 1})
        self.assertEqual((body["written"], body["dry_run"]), ([], True))
        self.assertEqual(self.snapshot(), before)
        code, out, _ = self.rp("migrate", "--from", "PM", "--to", "R8", "--dry-run")
        self.assertIn("2 task file(s) carry review_point: PM -> R8: 0001, 0002", out)
        self.assertIn("work.json review_point PM -> R8", out)
        self.assertIn("Dry run: nothing written.", out)

    def test_migrate_rewrites_keeps_bytes_moves_the_queue_and_is_idempotent(self):
        before = self.snapshot()
        code, out, err = self.rp("migrate", "--from", "PM", "--to", "R8")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.a.read_bytes(), before[self.a].replace(b"review_point: PM\n", b"review_point: R8\n"))
        self.assertEqual(self.b.read_bytes(), before[self.b].replace(b"review_point: 'PM'   # pre-beta\r\n",
                                                                    b"review_point: 'R8'   # pre-beta\r\n"))
        self.assertEqual((self.c.read_bytes(), self.d.read_bytes()), (before[self.c], before[self.d]))
        self.assertEqual(json.loads((self.q / "work.json").read_text())["review_point"], "R8")
        last = json.loads((self.q / "observability/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual((last["type"], last["op"], last["payload"]["from"], last["payload"]["to"]), ("runner", "set", "PM", "R8"))
        self.assertIn("commit them as one change", out)
        self.assertIn("docs/delivery/tasks/0001-a.md docs/delivery/tasks/0002-b.md", out)
        self.assertEqual([e for e in tasklog.check(self.p.cfg) if "review point" in e], [])
        # the ledger's PM spawn reads as R8 now (the backfill's runners)
        events = backfill._events(self.q)
        self.assertEqual(reviewpoints.renames(events), {"PM": "R8"})
        after = self.snapshot()
        code, out, err = self.rp("migrate", "--from", "PM", "--to", "R8")
        self.assertEqual(code, 0, err)
        self.assertIn("No task file to change.", out)
        self.assertEqual(self.snapshot(), after)  # no second rename event either

    def test_migrate_refusals(self):
        before = self.snapshot()
        for args, why in ((("--from", "PM", "--to", "R9"), "R9 is not in the register"),
                          (("--from", "PM", "--to", "PM2"), "is not R<number>"),
                          (("--from", "R8", "--to", "R8"), "the same"),
                          (("--from", "a b", "--to", "R8"), "not a review-point token")):
            code, _, err = self.rp("migrate", *args)
            self.assertEqual(code, 2, args)
            self.assertIn(why, err)
        _tagged(self.p, "0005-e", "pending", "R8")
        code, _, err = self.rp("migrate", "--from", "PM", "--to", "R8")
        self.assertEqual(code, 2)
        self.assertIn("1 task(s) already carry R8 (0005-e)", err)
        self.assertEqual(self.snapshot(), before)
        self.a.write_text(self.a.read_text() + "\nhand edit\n")
        code, _, err = self.rp("migrate", "--from", "PM", "--to", "R8", "--merge")
        self.assertEqual(code, 2)
        self.assertIn("uncommitted changes", err)
        (self.p.root / "docs/delivery/review-points.yaml").unlink()
        code, _, err = self.rp("migrate", "--from", "PM", "--to", "R8")
        self.assertIn("there is no review-point register", err)


    def test_tag_attaches_tasks_at_planning_time(self):
        before = self.snapshot()
        code, out, err = self.rp("tag", "R8", "--from-work", "--dry-run")
        self.assertEqual(code, 0, err)
        self.assertIn("tag      0003-c", out)
        self.assertEqual(self.snapshot(), before)
        code, out, err = self.rp("tag", "R8", "0003", "0004-d")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.c.read_bytes(), before[self.c].replace(b"updated: 2026-09-30\n---\n",
                                                                    b"updated: 2026-09-30\nreview_point: R8\n---\n"))
        self.assertEqual(tasklog.frontmatter(self.d.read_text())["review_point"], "R8")
        code, out, _ = self.rp("tag", "R8", "0003")
        self.assertIn("already  0003-c", out)
        for args, why in ((("R8", "0001"), "on another review point already: 0001-a (PM)"), (("R9", "0003"), "not in the register"),
                          (("R8", "0099"), "no task 0099"), (("R8",), "name the tasks")):
            code, _, err = self.rp("tag", *args)
            self.assertEqual(code, 2, args)
            self.assertIn(why, err)

    def test_list_and_show(self):
        self.rp("migrate", "--from", "PM", "--to", "R8")
        code, out, err = self.rp("list")
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("  R7 "), lines)
        self.assertTrue(lines[1].startswith("* R8    pre-beta"), lines)
        # the runner's scope (0003, 0004) counts toward its point until the tasks are tagged
        self.assertIn("2/4 done, 2 pending  opened 2026-10-22  (runner)", lines[1])
        code, out, _ = self.rp("show", "R8", "--json")
        g = json.loads(out)
        self.assertEqual((g["name"], g["done"], g["ids"]), ("pre-beta", 2, ["0001-a", "0002-b", "0003-c", "0004-d"]))
        code, out, _ = self.rp("show", "R8")
        self.assertIn("we run the beta test.", out)
        self.assertEqual(self.rp("show", "R42")[0], 2)
        body = json.loads(self.rp("list", "--json")[1])
        self.assertEqual([g["id"] for g in body["review_points"]], ["R7", "R8", "R10"])


class Spawn(TeamCase):
    """`team.sh runner spawn --review-point R` (§22): strict ids, the register, scope from tagged tasks."""

    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.prod, "0001-a", "done", "R8")
        _tagged(self.prod, "0002-b", "pending", "R8")
        _tagged(self.prod, "0003-c", "blocked", "R8", deps=["0002-b"])
        _tagged(self.prod, "0004-d", "pending")
        _tagged(self.prod, "0005-e", "pending", "R7")

    def test_without_scope_the_point_takes_its_open_tagged_tasks(self):
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["scope"], ["0002-b", "0003-c"])
        self.assertNotIn("warnings", res)
        w = json.loads((self.q / "work.json").read_text())
        self.assertEqual((w["scope"], w["review_point"]), (["0002-b", "0003-c"], "R8"))
        self.assertIn("Scope: 0002-b, 0003-c (review point R8)", res["actions"][0]["prompt"])

    def test_with_scope_warns_both_ways(self):
        code, res, err = self.team("runner", "spawn", "--scope", "0002-b,0004-d,0005-e", "--review-point", "R8")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["scope"], ["0002-b", "0004-d", "0005-e"])
        self.assertIn("2 scope task(s) are not tagged R8: 0004-d, 0005-e", res["warnings"][0])
        self.assertIn("1 open task(s) tagged R8 are not in the scope: 0003-c", res["warnings"][1])
        self.assertIn("warning: 2 scope task(s)", err)

    def test_refusals_write_nothing(self):
        before = (self.q / "work.json").read_text()
        for rp, why in (("R9", "R9 is not in the register"), ("PM", "is not R<number>"), ("R10", "no open task is tagged")):
            code, _, err = self.team("runner", "spawn", "--review-point", rp)
            self.assertEqual(code, 2, rp)
            self.assertIn(why, err)
        self.assertEqual((self.q / "work.json").read_text(), before)
        self.assertEqual([e for e in self.events() if e["type"] == "runner"], [])

    def test_a_respawn_on_a_legacy_point_warns(self):
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle", "review_point": "PM",
                                                      "scope": ["0002-b"]}))
        code, res, err = self.team("runner", "spawn")
        self.assertEqual(code, 0, err)
        self.assertIn("work.json's review point 'PM' is not R<number>", res["warnings"][0])


class SpawnNoRegister(TeamCase):
    def test_without_a_register_spawn_behaves_as_before_and_names_the_register(self):
        _tagged(self.prod, "0001-a", "pending", "R8")
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a", "--review-point", "PM")
        self.assertEqual(code, 0, err)  # warned, not refused
        self.assertIn("review point 'PM' does not match task_log.review_point_pattern", res["warnings"][0])
        self.assertEqual(err.count("no review-point register"), 1)
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")  # no tagged scope without a register
        self.assertEqual((code, res["scope"]), (0, ["0001-a"]), err)  # work.json's scope, as before


class BackfillRenamed(unittest.TestCase):
    def test_a_renamed_point_reads_as_its_new_name_in_the_ledger_and_the_log(self):
        p = Product({"reconcile": {"log": {"path": "docs/LOG.md", "entry": "**{date} (runner, {review_point}):** `{nnnn}` done."}}})
        self.addCleanup(p.cleanup)
        p.write("docs/delivery/review-points.yaml", REGISTER)
        p.write("docs/LOG.md", "**2026-10-22 (runner, PM):** `0002` done.\n")
        p.task("0001-a", status="done")
        p.task("0002-b", status="done")
        q = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, q)
        (q / "observability").mkdir()
        evs = [spawn("2026-10-22T00:00:00Z", "PM", ["0001-a"]), claim("2026-10-22T01:00:00Z", "0001-a"),
               ev("2026-10-22T09:00:00Z", "runner", "set", {"field": "review_point", "from": "PM", "to": "R8"})]
        (q / "observability" / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in evs))
        rows = {r["task_id"]: r for r in backfill.plan(p.cfg, q)["tasks"]}
        self.assertEqual((rows["0001-a"]["review_point"], rows["0001-a"]["action"]), ("R8", "stamp"))
        self.assertEqual((rows["0002-b"]["review_point"], rows["0002-b"]["how"]), ("R8", "log"))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class Rendered(Base, unittest.TestCase):
    def render(self, b):
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        r = subprocess.run(["node", "-e", STUB + js + "\nprocess.stdout.write(out.join(''));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def seed(self):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "adr": {}}))
        self.write("docs/adr/0004-y.md", "---\nid: ADR-0004\ntitle: \"u\"\nstatus: accepted\ndate: 2026-09-02\n"
                                         "review_points: [R8]\n---\n# ADR-0004 — u\n")
        self.write("docs/delivery/review-points.yaml", REGISTER)
        f = self.main / "docs/delivery/tasks/0002-second.md"
        f.write_text(f.read_text().replace("updated: 2026-09-30\n", 'updated: 2026-09-30\nreview_point: R8\nadr_refs: ["0004"]\n'))
        (self.q / "work.json").write_text(json.dumps({"status": "running", "review_point": "R8", "scope": ["0002"],
                                                      "in_flight": []}))
        return self.build()[0]

    def test_cards_order_now_line_and_filters(self):
        b = self.seed()
        p = b["plan"]
        self.assertEqual((p["errors"], p["register"]["errors"], p["register"]["current"]), ({}, [], "R8"))
        html = self.render(b)
        queue = html.split('id="pane-queue"', 1)[1].split('id="pane-health"', 1)[0]
        head = html.split('<div class="pane grid"', 1)[0]
        self.assertIn("running · R8 · pre-beta · scope 1", head)  # the Now line
        self.assertIn("Current review point: R8 · pre-beta", queue)
        self.assertIn("we run the beta test.", queue)
        self.assertIn("ADRs it builds", queue)
        self.assertIn('<select data-rpf="tasks">', queue)
        self.assertIn('<option value="current">Current (R8)</option>', queue)
        self.assertIn('<tr data-rp="R8">', queue)
        # the Review points card, newest number first, the current one marked
        card = queue.split("<h2>Review points</h2>", 1)[1]
        self.assertLess(card.index("<b>R10</b>"), card.index("<b>R8</b>"))
        self.assertLess(card.index("<b>R8</b>"), card.index("<b>R7</b>"))
        backlog = html.split('id="pane-backlog"', 1)[1].split('id="pane-queue"', 1)[0]
        self.assertIn('<select data-rpf="adrs">', backlog)
        self.assertIn('data-rp="R8"', backlog)

    def test_without_a_register_the_card_stands_and_a_banner_suggests_one(self):
        b = self.build()[0]
        self.assertFalse(b["plan"]["register"]["exists"])
        html = self.render(b)
        self.assertIn("No review-point register", html)
        self.assertIn("<h2>Review points</h2>", html)

    def test_every_review_point_string_renders_as_text(self):
        b = self.seed()
        b["plan"]["register"]["errors"] = ["bad line"]
        b["plan"]["register"]["mismatch"] = "the runner works on R7"
        html = self.render(_hostile(b))
        for t in ("Current review point", "Review-point register", "Review points", "&lt;!--&lt;script&gt;"):
            self.assertIn(t, html)
        for raw in ("<!--", "<script", "<img", "</script"):
            self.assertNotIn(raw, html)

    def test_the_filter_hides_rows_of_other_points(self):
        b = self.seed()
        js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        harness = """
const rows = [{a: {"data-rp": "R8"}, hidden: false}, {a: {"data-rp": "R7 R8"}, hidden: false}, {a: {"data-rp": ""}, hidden: false},
              {a: {"data-rp": "R7"}, hidden: false}];
rows.forEach((r) => { r.getAttribute = (k) => r.a[k]; });
document.querySelectorAll = (q) => q.includes("data-rpf-rows") ? rows : [];
const res = {};
for (const v of ["all", "current", "R7", "none"]) { applyRpf("tasks", v); res[v] = rows.map((r) => r.hidden); }
process.stdout.write(JSON.stringify(res));
"""
        r = subprocess.run(["node", "-e", STUB + js + harness], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout[r.stdout.index('{"all"'):])  # the page's own output comes first
        self.assertEqual(got, {"all": [False, False, False, False], "current": [False, False, True, True],
                               "R7": [True, False, True, False], "none": [True, True, False, True]})


if __name__ == "__main__":
    unittest.main()
