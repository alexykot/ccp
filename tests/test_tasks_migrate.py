"""SPEC §5.3: `ccp tasks migrate` converts an earlier plane generation's task files in place, and what it
cannot convert is named and left alone. A scratch product adopted with `ccp init`."""
from __future__ import annotations

import json
import subprocess
import unittest

from ccp import config, taskmigrate, tasklog
from tests.test_init import InitCase

TASKS = "docs/delivery/tasks"

OLD_INDEX = """tasks:
  - id: 0001-ledger-store
    title: Store the ledger
  - id: 0002-export-ledger
    title: Export the ledger as CSV
"""


def old_task(n: str, title: str, meta: dict[str, str] | None, specs: str | None = "§4",
             extra: str = "") -> str:
    """An earlier generation's task file: heading, Meta table, Refs table, free sections."""
    text = f"# Task {n}: {title}\n\n"
    if meta is not None:
        text += "## Meta\n\n| Field | Value |\n|---|---|\n" + "".join(f"| {k} | {v} |\n" for k, v in meta.items()) + "\n"
    if specs is not None:
        text += f"## Refs\n\n| Kind | Ref |\n|---|---|\n| SPEC | {specs} |\n| ADR | 0012 |\n\n"
    return text + extra


GOAL = "## Goal\n\nWrite the ledger out as CSV, one row per entry.\n| a stray | pipe row |\n"
FIXTURE = {
    "0001-ledger-store.md": old_task("0001", "Store", {"ID": "0001", "Status": "done", "Depends on": "-",
                                                       "Created": "2025-03-01"}, "§4.2, §6"),
    "0002-export-ledger.md": old_task("0002", "Export", {"ID": "0002", "Status": "completed",
                                                         "Depends on": "0001-ledger-store",
                                                         "Created": "2025-03-02"}, "§4", GOAL),
}


class Migrate(InitCase):
    def setUp(self):
        super().setUp()
        self.git("remote", "add", "origin", "https://github.com/team/repo.git")

    def adopt(self, files: dict[str, str]) -> None:
        tasks = self.repo / TASKS
        tasks.mkdir(parents=True)
        (self.repo / "docs/delivery/INDEX.yaml").write_text(OLD_INDEX)
        for name, text in files.items():
            (tasks / name).write_text(text)
        self.git("add", "docs")
        self.git("commit", "-qm", "the old task log")
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)
        self.git("add", "docs", ".gitignore", ".claude", "CLAUDE.md")
        self.git("commit", "-qm", "adopt")

    def read(self, name: str) -> str:
        return (self.repo / TASKS / name).read_text()

    def test_a_done_history_converts_and_the_checks_pass(self):
        self.adopt(FIXTURE)
        for args in (("tasks", "migrate"), ("tasks", "check"), ("docs", "check")):
            r = self.ccp(*args)
            self.assertEqual(r.returncode, 0, f"{args}: {r.stdout}{r.stderr}")
        text = self.read("0002-export-ledger.md")
        for line in ("title: Export the ledger as CSV", "status: done", 'depends_on: ["0001-ledger-store"]',
                     'spec_refs: ["S4"]', "created: 2025-03-02", "updated: 2025-03-02", 'adopt: "none"'):
            self.assertIn(line, text.splitlines())
        context = text.split("## Context (not checked)\n", 1)[1].split("\n## Scope\n", 1)[0]
        self.assertIn(FIXTURE["0002-export-ledger.md"], context)
        verify = tasklog._section(text, tasklog.SEC_VERIFY)
        notes = [ln for ln in verify.splitlines() if ln.startswith("- ")]
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("ccp tasks migrate", notes[0])
        self.assertIn("completed", notes[0])
        self.assertIn('spec_refs: ["S4", "S6"]', self.read("0001-ledger-store.md").splitlines())
        rows = {t["task_id"]: t for t in json.loads(self.ccp("tasks", "list", "--json").stdout)}
        self.assertEqual(rows["0001-ledger-store"]["title"], "Store the ledger")
        index = (self.repo / "docs/delivery/INDEX.yaml").read_text()
        self.assertIn("    title: Export the ledger as CSV\n", index)

    def test_what_cannot_be_converted_is_named_and_left_alone(self):
        open_task = old_task("0003", "Retry", {"Status": "in progress", "Created": "2025-03-03"})
        notes = "# Task 0004: Notes\n\nNo table here.\n"
        self.adopt({**FIXTURE, "0003-retry-export.md": open_task, "0004-notes.md": notes})
        dry = self.ccp("tasks", "migrate", "--dry-run")
        self.assertEqual(dry.returncode, 1, dry.stdout + dry.stderr)
        self.assertEqual(subprocess.run(["git", "status", "--porcelain"], cwd=self.repo, capture_output=True,
                                        text=True).stdout, "")
        run = self.ccp("tasks", "migrate")
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        files = lambda out: [ln for ln in out.splitlines() if ln.startswith(TASKS)]  # noqa: E731
        self.assertEqual(files(dry.stdout), files(run.stdout))
        lines = {ln.split(":", 1)[0]: ln for ln in files(run.stdout)}
        self.assertIn("cannot convert: an open task", lines[f"{TASKS}/0003-retry-export.md"])
        self.assertIn("cannot convert: no Meta table", lines[f"{TASKS}/0004-notes.md"])
        for n in ("0001-ledger-store.md", "0002-export-ledger.md"):
            self.assertIn("converted", lines[f"{TASKS}/{n}"])
            self.assertTrue(tasklog.has_frontmatter(self.read(n)))
        self.assertEqual(self.read("0003-retry-export.md"), open_task)
        self.assertEqual(self.read("0004-notes.md"), notes)

        again = self.ccp("tasks", "migrate", "--drop-open")
        self.assertEqual(again.returncode, 1, again.stdout + again.stderr)
        self.assertEqual([ln.split(":", 1)[0] for ln in files(again.stdout)],
                         [f"{TASKS}/0003-retry-export.md", f"{TASKS}/0004-notes.md"])
        self.assertIn("cannot convert: no Meta table", again.stdout)
        text = self.read("0003-retry-export.md")
        self.assertIn("status: dropped", text.splitlines())
        self.assertIn(taskmigrate.DROP_NOTE, tasklog._section(text, tasklog.SEC_VERIFY))
        self.assertEqual(self.read("0004-notes.md"), notes)

    def test_a_converted_file_the_checks_would_fail_is_not_written(self):
        # The kept old text comes first in the file, so its own `## dod_checks` and `## Verification notes`
        # are the sections the checks read: here no check, two soft words and an empty notes section.
        own = ("## dod_checks\n\n- The export should handle errors gracefully.\n\n"
               "## Verification notes\n\n")
        clash = old_task("0003", "Own checks", {"Status": "done", "Created": "2025-03-03"}, extra=own)
        after = old_task("0004", "After", {"Status": "done", "Depends on": "0003-own-checks",
                                           "Created": "2025-03-04"})
        self.adopt({**FIXTURE, "0003-own-checks.md": clash, "0004-after.md": after})
        run = self.ccp("tasks", "migrate")
        self.assertEqual(run.returncode, 1, run.stdout + run.stderr)
        lines = {ln.split(":", 1)[0]: ln for ln in run.stdout.splitlines() if ln.startswith(TASKS)}
        self.assertIn("cannot convert: converted, it would fail `ccp tasks check`: no dod_checks",
                      lines[f"{TASKS}/0003-own-checks.md"])
        self.assertIn("soft language 'should'", lines[f"{TASKS}/0003-own-checks.md"])
        self.assertIn("status is done with no verification notes", lines[f"{TASKS}/0003-own-checks.md"])
        self.assertIn("cannot convert: converted, it would fail `ccp tasks check`: depends_on `0003-own-checks`",
                      lines[f"{TASKS}/0004-after.md"])
        self.assertEqual(self.read("0003-own-checks.md"), clash)
        self.assertEqual(self.read("0004-after.md"), after)
        for n in ("0001-ledger-store.md", "0002-export-ledger.md"):
            self.assertIn("converted (done)", lines[f"{TASKS}/{n}"])
        check = self.ccp("tasks", "check")
        self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
        failing = sorted({ln.strip().split(":", 1)[0] for ln in check.stdout.splitlines() if TASKS in ln})
        self.assertEqual(failing, [f"{TASKS}/0003-own-checks.md", f"{TASKS}/0004-after.md"], check.stdout)
        self.assertNotIn("dod_checks", check.stdout)


class Convert(unittest.TestCase):
    """The rulings one by one, on a temp product (no init needed)."""

    def setUp(self):
        from tests.helpers import Product
        self.p = Product()
        self.addCleanup(self.p.cleanup)

    def rows(self, **kw):
        return {r["path"].rsplit("/", 1)[-1]: r for r in taskmigrate.migrate(config.load(self.p.root), **kw)["files"]}

    def meta(self, **over: str) -> dict[str, str]:
        return {"Status": "done", "Created": "2025-03-01", **over}

    def test_each_reason_a_file_cannot_be_converted(self):
        cases = {
            "notes.md": (old_task("0009", "x", self.meta()), "its name is not NNNN-kebab-slug.md"),
            "0001-no-status.md": (old_task("0001", "x", {"Created": "2025-03-01"}), "no Status row"),
            "0002-no-spec.md": (old_task("0002", "x", self.meta(), specs="none"), "no SPEC section"),
            "0003-no-refs.md": (old_task("0003", "x", self.meta(), specs=None), "no SPEC section"),
            "0004-bad-date.md": (old_task("0004", "x", self.meta(Created="1 March 2025")), "is not YYYY-MM-DD"),
            "0005-no-date.md": (old_task("0005", "x", {"Status": "done"}), "is not YYYY-MM-DD"),
            "0006-bad-dep.md": (old_task("0006", "x", self.meta(**{"Depends on": "0099-gone"})),
                                "Depends on names 0099-gone, which has no task file"),
            "0007-open.md": (old_task("0007", "x", self.meta(Status="todo")), "an open task (Status: todo)"),
        }
        for name, (text, _) in cases.items():
            self.p.write(f"{TASKS}/{name}", text)
        rows = self.rows()
        for name, (text, why) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(rows[name]["result"], "cannot convert")
                self.assertIn(why, rows[name]["reason"])
                self.assertEqual((self.p.root / TASKS / name).read_text(), text)

    def test_statuses_map_and_a_current_file_is_left_alone_without_a_row(self):
        words = {"done": "done", "Complete": "done", "COMPLETED": "done", "dropped": "dropped",
                 "Cancelled": "dropped", "canceled": "dropped", "superseded": "dropped", "abandoned": "dropped"}
        for i, word in enumerate(words, 1):
            self.p.write(f"{TASKS}/{i:04d}-t.md", old_task(f"{i:04d}", "x", self.meta(Status=word)))
        current = self.p.task("0020-current")
        before = current.read_text()
        rows = self.rows()
        self.assertNotIn("0020-current.md", rows)
        self.assertEqual(current.read_text(), before)
        for i, (word, status) in enumerate(words.items(), 1):
            with self.subTest(word=word):
                self.assertEqual(rows[f"{i:04d}-t.md"]["result"], "converted")
                fm = tasklog.frontmatter((self.p.root / TASKS / f"{i:04d}-t.md").read_text())
                self.assertEqual(fm["status"], status)

    def test_a_dry_run_writes_nothing(self):
        text = old_task("0001", "x", self.meta())
        self.p.write(f"{TASKS}/0001-a.md", text)
        self.assertEqual(self.rows(dry_run=True)["0001-a.md"]["result"], "converted")
        self.assertEqual((self.p.root / TASKS / "0001-a.md").read_text(), text)

    def test_title_falls_back_to_the_heading_then_the_slug_outside_an_index(self):
        self.p.write(f"{TASKS}/0001-a-b.md", old_task("0001", "Do the thing # now", self.meta()))
        self.p.write(f"{TASKS}/0002-c-d.md", old_task("0002", "", self.meta()).replace("# Task 0002: \n", ""))
        self.rows()
        load = lambda n: tasklog.frontmatter((self.p.root / TASKS / n).read_text())  # noqa: E731
        self.assertEqual(load("0001-a-b.md")["title"], "Do the thing # now")
        self.assertEqual(load("0002-c-d.md")["title"], "c d")

    def test_spec_refs_read_each_form_and_keep_their_order(self):
        cfg = config.load(self.p.root)
        self.assertEqual(taskmigrate.spec_refs(cfg, ["§6.1, S4", "§ 6 and S12.3; MS3 S3-bucket"]), ["S6", "S4", "S12"])

    def test_keys_match_in_any_case_and_a_bare_number_names_its_file(self):
        self.p.write(f"{TASKS}/0001-a.md", old_task("0001", "x", self.meta()))
        self.p.write(f"{TASKS}/0002-b.md", old_task("0002", "x", {"STATUS": "Done", "created": "2025-03-02",
                                                                  "DEPENDS ON": "`0001`"}))
        rows = self.rows()
        self.assertEqual(rows["0002-b.md"]["result"], "converted", rows)
        fm = tasklog.frontmatter((self.p.root / TASKS / "0002-b.md").read_text())
        self.assertEqual(fm["depends_on"], ["0001-a"])

    def test_old_text_with_its_own_fences_stays_inside_the_kept_block(self):
        body = "## Notes\n\n~~~\nquoted\n~~~\n\n```\ncode\n```\n"
        self.p.write(f"{TASKS}/0001-a.md", old_task("0001", "x", self.meta(), extra=body))
        self.rows()
        self.p.index()
        self.assertEqual(tasklog.check(self.p.cfg), [])
        text = (self.p.root / TASKS / "0001-a.md").read_text()
        self.assertIn("\n~~~~\n# Task 0001: x\n", text)
        self.assertIn(body + "~~~~\n", text)


if __name__ == "__main__":
    unittest.main()
