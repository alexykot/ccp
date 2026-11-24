"""The worker report's sections are one table, `report.SECTIONS` (SPEC §13.4): `ccp report` reads a report by it
and `ccp prompt` asks each phase for the sections it carries from it. Each phase's prompt names every section
the table gives that phase, and the lines every report carries.

Run as `python3 -m tests.test_report_sections --dump <dir> --ccp <checkout>/bin/ccp`, the module renders the
prompt of each phase for one fixture task with that checkout's `ccp`, into `<dir>/<phase>.txt`, with run ids,
times, hashes and paths replaced by fixed tokens: two checkouts' dumps are then compared with `diff -r`."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from ccp import report, runs
from tests.helpers import DOWNTIME_FIELD as DOWNTIME, GIT_ENV
from tests.report_helpers import done_report, implement_report, REPORT_HEAD as HEAD
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

# What every report carries, whatever the table says (§13.4): a phase whose prompt lacks one is wrong.
EVERY_REPORT = ("Outcome:", "Prompt:", "Suite:", "## Friction")
DATES = {"GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z"}
# the phases a dump renders: the six, and a resolution review (`ccp prompt review --mode resolution`)
RENDERED = (*runs.PHASES, "resolution")
REPORT_FROM, REPORT_TO = "these lines:\n", "\n2. Send the runner teammate"


def report_part(text: str) -> str:
    """The prompt's account of the report's lines."""
    a = text.index(REPORT_FROM) + len(REPORT_FROM)
    return text[a:text.index(REPORT_TO, a)]


class Prompts(ToolkitFixture, unittest.TestCase):
    """One fixture task, its prompt rendered for each phase. `ccp_bin` runs another checkout's `ccp`."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "report": {"required_fields": [DOWNTIME]}}
    ccp_bin: str | None = None
    SHARED_REPO = False  # the dates below are set before the build, so the first commit's hash is the same in each dump

    def setUp(self):
        dates = mock.patch.dict(os.environ, DATES)  # the same commits, so the same hashes, in each dump
        dates.start()
        self.addCleanup(dates.stop)
        super().setUp()

    def ccp(self, *args: str, stdin: str | None = None, root: Path | None = None):
        if not self.ccp_bin:
            return super().ccp(*args, stdin=stdin, root=root)
        r = subprocess.run([sys.executable, self.ccp_bin, "--root", str(root or self.runner), *args], input=stdin,
                           capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            parsed = json.loads(r.stdout) if r.stdout.strip().startswith("{") else None
        except ValueError:
            parsed = None
        return r.returncode, parsed, r.stdout, r.stderr

    def prompt_text(self, *args: str) -> str:
        code, body, out, err = self.ccp("prompt", *args)
        self.assertEqual(code, 0, out + err)
        return Path(body["prompt_path"]).read_text()

    def render(self, key: str) -> str:
        """The prompt of `key` (a phase, or `resolution`), its task claimed and the history it needs made."""
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        pr = ("--pr", "7")
        if key == "implement":
            return self.prompt_text("implement", "0002", "--base", "abc1234")
        if key == "resolution":
            h1 = self.start()
            self.review(h1)
            return self.prompt_text("review", "0002", *pr, "--head", self.move_tip(), "--mode", "resolution")
        head = self.main_head()
        if key == "fix":
            self.review(head)  # a fix works from a review
        extra = ("--note", "the lead's ruling") if key == "ruling" else ()
        return self.prompt_text(key, "0002", *pr, "--head", head, *extra)

    def main_head(self) -> str:
        return git(self.main, "rev-parse", "HEAD")

    def start(self) -> str:
        """The task branch's head, forked from the integration branch before its tip moves."""
        m = self.main
        self.write("shared.txt", "one\ntwo\nthree\n")
        git(m, "add", "shared.txt")
        git(m, "commit", "-q", "-m", "base")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "-b", "feat")
        self.write("shared.txt", "one\ntask change\nthree\n")
        git(m, "commit", "-q", "-am", "task change")
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return head

    def move_tip(self) -> str:
        """The integration tip moves on the line the task changed; the task branch merges it, and its merge commit
        holds a hand resolution. Returns that merge commit."""
        m = self.main
        self.write("shared.txt", "one\ntip change\nthree\n")
        git(m, "commit", "-q", "-am", "tip change")
        git(m, "push", "-q", "origin", "main")
        git(m, "checkout", "-q", "feat")
        merged = subprocess.run(["git", "-C", str(m), "merge", "-q", "--no-edit", "origin/main"],
                                capture_output=True, text=True, env={**os.environ, **GIT_ENV})
        self.assertEqual(merged.returncode, 1, merged.stdout + merged.stderr)
        self.write("shared.txt", "one\ntask change and tip change\nthree\n")
        git(m, "add", "shared.txt")
        git(m, "commit", "-q", "--no-edit")
        head = git(m, "rev-parse", "HEAD")
        git(m, "checkout", "-q", "main")
        return head

    def review(self, head: str) -> None:
        """A done review of `head` on record, which a fix or a resolution review works from."""
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        text = "Outcome: done\nSeverity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0\n## Spec beyond intent\nnone\n## Friction\nnone\n"
        code, _, out, err = self.report(body["run_id"], text)
        self.assertEqual(code, 0, out + err)

    def check(self, key: str) -> None:
        phase, mode = ("review", "resolution") if key == "resolution" else (key, None)
        part = report_part(self.render(key))
        for s in report.sections_for(phase, mode):
            self.assertIn(s.label, part, f"the {key} prompt does not name {s.name}")
        for label in EVERY_REPORT:
            self.assertIn(label, part, f"the {key} prompt does not name {label}")

    def test_implement(self):
        self.check("implement")

    def test_fix(self):
        self.check("fix")

    def test_merge(self):
        self.check("merge")

    def test_ruling(self):
        self.check("ruling")

    def test_review(self):
        self.check("review")

    def test_verify(self):
        self.check("verify")

    def test_resolution_review(self):
        self.check("resolution")


class Table(unittest.TestCase):
    """The table's own shape: what `parse` reads, the record's fields and what a phase carries."""

    def test_the_record_fields_come_from_the_table(self):
        stored = {k for s in report.SECTIONS for k in s.stored}
        self.assertEqual(set(report.PARSED_KEYS), stored - set(report.SET_APART))
        self.assertEqual(len(report.PARSED_KEYS), len(set(report.PARSED_KEYS)))
        self.assertTrue(set(report.SET_APART) <= stored)
        self.assertEqual(set(report.RETURNED_KEYS), stored | {"suite_runs_recorded", "suite_s_recorded", "corrections"})

    def test_each_phase_carries_what_the_table_gives_it(self):
        for phase in runs.PHASES:
            names = [s.key for s in report.sections_for(phase)]
            for always in ("outcome", "prompt", "suite", "friction"):
                self.assertIn(always, names, phase)
        self.assertEqual([s.key for s in report.sections_for("verify")][1:3], ["head", "verdict"])
        self.assertNotIn("resolution", [s.key for s in report.sections_for("review")])
        self.assertIn("affected", [s.key for s in report.sections_for("review", "resolution")])
        self.assertNotIn("severity", [s.key for s in report.sections_for("verify")])

    def test_parse_asks_a_phase_for_its_required_sections(self):
        got, errs = report.parse("implement", "Outcome: done\n## Friction\nnone\n")
        self.assertEqual(errs, [s.missing for s in report.SECTIONS if s.key in ("head", "pr", "tests")])
        got, errs = report.parse("verify", "Outcome: done\nHead: " + HEAD + "\nVerdict: approve\n## Friction\nnone\n")
        self.assertEqual((errs, got["verdict"], got["friction"]), ([], "approve", []))
        got, errs = report.parse("verify", "Outcome: blocked\n")  # only what is always required, when not done
        self.assertEqual(errs, [s.missing for s in report.SECTIONS if s.key == "friction"])


class Submit(ToolkitFixture, unittest.TestCase):
    """`ccp report` keeps each section where the table says, and refuses a secret in a secret-checked one."""

    def setUp(self):
        super().setUp()
        self.ccp("tasks", "claim", "0002")
        self.assertEqual(self.ccp("prompt", "implement", "0002", "--base", "abc1234")[0], 0)

    def test_the_reply_carries_the_fields_the_table_stores(self):
        code, body, out, err = self.report("0002-second/implement", implement_report("Suite: 12 tests, 3.5 s"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["outcome"], body["pr"], body["head"], body["suite_tests"], body["friction_count"]),
                         ("done", "7", HEAD, 12, 0))
        self.assertTrue(set(body) <= {"ok", "run_id", "report", "warnings", *report.RETURNED_KEYS}, body)

    def test_a_secret_friction_line_is_refused_and_nothing_is_written(self):
        text = done_report("implement", "PR: #7", f"Head: {HEAD}", friction=("- ANTHROPIC_API_KEY=abc123",))
        code, _, out, err = self.report("0002-second/implement", text)
        self.assertEqual(code, 1, out + err)
        self.assertIn("a Friction line looks like it holds a secret", err)
        self.assertFalse((self.q / "progress/0002-second/implement-report.md").exists())


NORMALISE = (
    (re.compile(r"\b\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\b"), "<TIME>"),
    (re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*\d)[0-9a-f]{7,40}(?![0-9A-Za-z])"), "<HASH>"),
    (re.compile(r"Prompt end: \w+"), "Prompt end: <TOKEN>"),
)


def normalised(text: str, paths: dict[str, str]) -> str:
    """`text` with each path in `paths` (longest first), and then times, hashes and the prompt's token, replaced
    by fixed tokens."""
    for path in sorted(paths, key=len, reverse=True):
        text = text.replace(path, paths[path])
    for rx, token in NORMALISE:
        text = rx.sub(token, text)
    return text


def dump(out: Path, ccp_bin: str) -> None:
    """Each phase's prompt, from `ccp_bin`'s `ccp`, normalised, into `out/<phase>.txt`."""
    out.mkdir(parents=True, exist_ok=True)
    checkout = Path(ccp_bin).resolve().parents[1]
    for key in RENDERED:
        case = Prompts("test_implement")
        case.ccp_bin = ccp_bin
        case.setUp()
        try:
            text = case.render(key)
            tmp = Path(case._tmp.name)
            paths = {str(checkout): "<PLANE>", str(tmp): "<TMP>", case._tmp.name: "<TMP>"}
            (out / f"{key}.txt").write_text(normalised(text, paths))
        finally:
            case.tearDown()
            case.doCleanups()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--dump")
    ap.add_argument("--ccp")
    known, rest = ap.parse_known_args()
    if known.dump:
        if not known.ccp:
            sys.exit("--dump needs --ccp <checkout>/bin/ccp")
        dump(Path(known.dump), known.ccp)
    else:
        unittest.main(argv=[sys.argv[0], *rest])
