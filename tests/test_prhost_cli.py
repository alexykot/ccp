"""`ccp pr` (SPEC §15.5, ADR-0040 D1): the PR-host interface as workers and the runner call it, each
call given the PR number, over a stand-in `gh` on `CCP_GH_BIN` that logs its argv and its stdin."""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli
from tests.helpers import Product

HEAD = "a" * 40
MERGE = "b" * 40

# A stand-in for gh: logs each call's argv as one line of [word]s, a body read on stdin (`--body-file -`)
# to FAKE_LOG.stdin, prints FAKE_OUT, writes FAKE_ERR, exits FAKE_RC.
FAKE = """#!/bin/sh
for w in "$@"; do printf '[%s]' "$w" >> "$FAKE_LOG"; done
echo >> "$FAKE_LOG"
case "$*" in *"--body-file -"*) cat > "$FAKE_LOG.stdin" ;; esac
printf '%s' "$FAKE_OUT"
printf '%s' "$FAKE_ERR" >&2
exit "${FAKE_RC:-0}"
"""


def argv(*words: str) -> str:
    return "".join(f"[{w}]" for w in words)


class PrCli(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.p.task("0001-a")
        self.addCleanup(self.p.cleanup)
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.t = Path(t.name)
        self.gh = self.t / "fake-gh"
        self.gh.write_text(FAKE)
        self.gh.chmod(0o755)
        self.log = self.t / "log"
        self.q = self.t / "queue"
        self.q.mkdir()
        (self.q / "project.yaml").write_text("project_id: demo\nintegration_branch: trunk\n")
        self.say({})

    def say(self, env: dict[str, str]) -> None:
        patch = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(self.gh), "FAKE_LOG": str(self.log),
                                             "FAKE_OUT": "", "FAKE_ERR": "", "FAKE_RC": "0",
                                             "QUEUE_ROOT": str(self.q), **env})
        patch.start()
        self.addCleanup(patch.stop)

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def stdin(self) -> str:
        return Path(f"{self.log}.stdin").read_text()

    def ccp(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "pr", *args])
        return code, out.getvalue(), err.getvalue()

    def body_file(self, text: str) -> str:
        f = self.t / "body.md"
        f.write_text(text)
        return str(f)


class Open(PrCli):
    def test_open_creates_the_pr_against_the_integration_branch_and_prints_its_number(self):
        self.say({"FAKE_OUT": "https://example.test/o/r/pull/12\n"})
        code, out, _ = self.ccp("open", "--branch", "task/0001-a", "--title", "Task 0001: a title",
                                "--body-file", self.body_file("Task: 0001-a\n"))
        self.assertEqual((code, out.strip()), (0, "12"))
        self.assertEqual(self.calls(), [argv("pr", "create", "--head", "task/0001-a", "--base", "trunk",
                                             "--title", "Task 0001: a title", "--body-file", "-")])
        self.assertEqual(self.stdin(), "Task: 0001-a\n")

    def test_open_reads_the_number_from_a_url_with_a_trailing_slash(self):
        self.say({"FAKE_OUT": "https://example.test/o/r/pull/12/\n"})
        code, out, _ = self.ccp("open", "--branch", "b", "--title", "t", "--body-file", self.body_file("x"))
        self.assertEqual((code, out.strip()), (0, "12"))

    def test_a_create_that_names_no_pr_number_is_a_host_error(self):
        self.say({"FAKE_OUT": "created\n"})
        code, _, err = self.ccp("open", "--branch", "b", "--title", "t", "--body-file", self.body_file("x"))
        self.assertEqual(code, 1)
        self.assertIn("created", err)

    def test_open_without_a_queue_runs_nothing(self):
        self.say({"QUEUE_ROOT": str(self.t / "no-queue")})
        code, _, err = self.ccp("open", "--branch", "b", "--title", "t", "--body-file", self.body_file("x"))
        self.assertEqual(code, 2)
        self.assertIn("QUEUE_ROOT", err)
        self.assertEqual(self.calls(), [])


class View(PrCli):
    def facts(self, **fields: object) -> str:
        return json.dumps({"number": 7, "state": "MERGED", "headRefOid": HEAD, "headRefName": "task/0001-a",
                           "mergedAt": "2026-11-20T10:00:00Z", "mergeCommit": {"oid": MERGE},
                           "body": "Task: 0001-a", **fields})

    def test_view_json_prints_the_facts_with_the_body_in_one_read(self):
        self.say({"FAKE_OUT": self.facts()})
        code, out, _ = self.ccp("view", "7", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"number": 7, "state": "merged", "head": HEAD, "branch": "task/0001-a",
                                           "merged_at": "2026-11-20T10:00:00Z", "merge_commit": MERGE,
                                           "body": "Task: 0001-a"})
        self.assertEqual(self.calls(), [argv("pr", "view", "7", "--json",
                                             "number,state,headRefOid,headRefName,mergeCommit,mergedAt,body")])

    def test_view_prints_each_fact_on_its_own_line(self):
        self.say({"FAKE_OUT": self.facts(state="OPEN", mergedAt=None, mergeCommit=None)})
        code, out, _ = self.ccp("view", "7")
        self.assertEqual(code, 0)
        self.assertIn(f"head: {HEAD}", out.splitlines())
        self.assertIn("state: open", out.splitlines())
        self.assertIn("Task: 0001-a", out.splitlines())

    def test_a_failing_read_exits_1_with_the_hosts_words(self):
        self.say({"FAKE_RC": "1", "FAKE_ERR": "no such PR"})
        code, out, err = self.ccp("view", "7", "--json")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no such PR", err)


class DiffEditMerge(PrCli):
    def test_diff_prints_the_hosts_diff_as_it_is(self):
        patch = "diff --git a/x b/x\n+one\n"
        self.say({"FAKE_OUT": patch})
        self.assertEqual(self.ccp("diff", "7")[:2], (0, patch))
        self.assertEqual(self.calls(), [argv("pr", "diff", "7")])

    def test_the_pr_number_is_given_to_the_host_without_leading_zeros(self):
        self.ccp("diff", "007")
        self.assertEqual(self.calls(), [argv("pr", "diff", "7")])

    def test_edit_replaces_the_body_from_the_file(self):
        code, _, _ = self.ccp("edit", "7", "--body-file", self.body_file("Task: 0001-a\nnew\n"))
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), [argv("pr", "edit", "7", "--body-file", "-")])
        self.assertEqual(self.stdin(), "Task: 0001-a\nnew\n")

    def test_edit_with_an_unreadable_body_file_is_a_usage_error_and_runs_nothing(self):
        code, _, err = self.ccp("edit", "7", "--body-file", str(self.t / "missing.md"))
        self.assertEqual(code, 2)
        self.assertIn("missing.md", err)
        self.assertEqual(self.calls(), [])

    def test_merge_is_the_squash_pinned_to_the_head(self):
        code, _, _ = self.ccp("merge", "12", "--head", HEAD, "--task", "0001-a")
        self.assertEqual(code, 0)
        self.assertEqual(self.calls(), [argv("pr", "merge", "12", "--squash", "--match-head-commit", HEAD)])

    def test_a_refused_merge_exits_1_with_the_hosts_words(self):
        self.say({"FAKE_RC": "1", "FAKE_ERR": "head moved"})
        code, _, err = self.ccp("merge", "12", "--head", HEAD, "--task", "0001-a")
        self.assertEqual(code, 1)
        self.assertIn("head moved", err)

    def test_merge_command_gets_the_task_and_the_head(self):
        self.p.cleanup()
        self.p = Product({"merge": {"command": f"{self.gh} merged {{pr}} {{head_sha}} {{task_id}}"}})
        self.p.task("0001-a")
        self.assertEqual(self.ccp("merge", "12", "--head", HEAD, "--task", "0001-a")[0], 0)
        self.assertEqual(self.calls(), [argv("merged", "12", HEAD, "0001-a")])

    def test_merge_command_gets_the_full_task_id_for_its_number_and_the_head_case_folded(self):
        self.p.cleanup()
        self.p = Product({"merge": {"command": f"{self.gh} merged {{pr}} {{head_sha}} {{task_id}}"}})
        self.p.task("0001-a")
        self.assertEqual(self.ccp("merge", "12", "--head", HEAD.upper(), "--task", "0001")[0], 0)
        self.assertEqual(self.calls(), [argv("merged", "12", HEAD, "0001-a")])

    def test_merge_for_an_unknown_task_is_a_usage_error_and_runs_nothing(self):
        code, _, err = self.ccp("merge", "12", "--head", HEAD, "--task", "0099")
        self.assertEqual(code, 2)
        self.assertIn("0099", err)
        self.assertEqual(self.calls(), [])


class Refusals(PrCli):
    def test_a_missing_host_binary_exits_1_naming_it(self):
        gone = str(self.t / "no-such-gh")
        self.say({"CCP_GH_BIN": gone})
        body = self.body_file("x")
        for args in (("open", "--branch", "b", "--title", "t", "--body-file", body), ("view", "7"),
                     ("diff", "7"), ("edit", "7", "--body-file", body), ("merge", "7", "--head", HEAD, "--task", "0001")):
            with self.subTest(args[0]):
                code, _, err = self.ccp(*args)
                self.assertEqual(code, 1)
                self.assertIn(gone, err)

    def test_merge_needs_the_full_head_sha(self):
        for head in ("x", HEAD[:12], "task/0001-a", f"{HEAD}; true", "g" * 40):
            with self.subTest(head):
                with self.assertRaises(SystemExit) as cm:
                    self.ccp("merge", "12", "--head", head, "--task", "0001")
                self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.calls(), [])

    def test_a_host_refusal_exits_1_with_the_hosts_words(self):
        self.say({"FAKE_RC": "1", "FAKE_ERR": "host said no", "FAKE_OUT": "https://example.test/o/r/pull/12"})
        body = self.body_file("x")
        for args in (("open", "--branch", "b", "--title", "t", "--body-file", body), ("diff", "7"),
                     ("edit", "7", "--body-file", body)):
            with self.subTest(args[0]):
                code, out, err = self.ccp(*args)
                self.assertEqual((code, out), (1, ""))
                self.assertIn("host said no", err)

    def test_every_call_but_open_needs_the_pr_number(self):
        for args in (("view",), ("view", "task/0001-a"), ("diff", "0"), ("edit", "--body-file", "x"),
                     ("merge", "HEAD", "--head", HEAD, "--task", "0001")):
            with self.subTest(args):
                with self.assertRaises(SystemExit) as cm:
                    self.ccp(*args)
                self.assertEqual(cm.exception.code, 2)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
