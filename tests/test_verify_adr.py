"""`ccp verify record` runs the in-force ADR check on the PR head before an approve (SPEC §6.7, §15.4)."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import adr, cli
from tests.helpers import TASK, Product
from tests.test_verify import approve

ADR_BODY = "# ADR-0001 — T\n\n## Decision\n\n### D1. First\n\nOne.\n\n### D2. Second\n\nTwo.\n"


class InForceAtVerify(unittest.TestCase):
    strict = True

    def setUp(self):
        self.p = Product({"adr": {"dir": "docs/adr", "strict": self.strict}})
        self.addCleanup(self.p.cleanup)
        self._q = tempfile.TemporaryDirectory()
        self.addCleanup(self._q.cleanup)
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        env.start()
        self.addCleanup(env.stop)
        self.p.write("docs/adr/0001-a.md", adr.emit({"id": "ADR-0001", "title": "T", "status": "accepted",
                                                      "date": "2026-01-01", "decisions": ["D1 not_built", "D2 built"]})
                     + ADR_BODY)
        self.task("0001-a", ["ADR-0001 D1"])
        self.git("init", "-q")
        self.not_flipped = self.commit("the task's change, decision not flipped")

    def task(self, tid: str, refs: list[str]) -> None:
        text = TASK.format(tid=tid, title="A task", status="pending", deps="", ver="*Append-only.*")
        text = text.replace('spec_refs: ["S1"]\n',
                            'spec_refs: ["S1"]\nadr_refs: [' + ", ".join(f'"{r}"' for r in refs) + "]\n")
        self.p.write(f"docs/delivery/tasks/{tid}.md", text)

    def git(self, *a: str) -> str:
        r = subprocess.run(["git", "-C", str(self.p.root), "-c", "user.email=t@t", "-c", "user.name=t",
                            "-c", "commit.gpgsign=false", *a], capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def commit(self, msg: str) -> str:
        self.git("add", "-A", ".")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def record(self, body: dict):
        src = self.q / "in.json"
        src.write_text(json.dumps(body))
        return self.ccp("verify", "record", str(src))

    def written(self) -> Path:
        return self.q / "verification" / "0001-a.json"

    def flip(self) -> str:
        code, out, err = self.ccp("adr", "decide", "1", "D1", "built")
        self.assertEqual(code, 0, out + err)
        return self.commit("flip D1")


class Strict(InForceAtVerify):
    def test_an_approve_of_a_head_with_the_decision_not_flipped_is_refused(self):
        code, _, err = self.record(approve(head_sha=self.not_flipped))
        self.assertEqual(code, 1, err)
        self.assertIn("nothing written", err)
        self.assertIn("ADR-0001 D1", err)
        self.assertIn("`ccp adr decide 1 D1 built`", err)
        self.assertFalse(self.written().exists())

    def test_an_approve_of_a_head_with_the_decision_flipped_is_recorded(self):
        flipped = self.flip()
        code, out, err = self.record(approve(head_sha=flipped))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(self.written().read_text())["head_sha"], flipped)

    def test_the_head_is_judged_not_the_checkout(self):
        flipped = self.flip()
        code, _, err = self.record(approve(head_sha=self.not_flipped))  # checkout says built, the head does not
        self.assertEqual(code, 1, err)
        self.assertIn("ADR-0001 D1", err)
        self.git("checkout", "-q", self.not_flipped)  # checkout says not_built, the head says built
        code, out, err = self.record(approve(head_sha=flipped[:12]))
        self.assertEqual(code, 0, out + err)

    def test_a_reject_is_never_held_back(self):
        code, out, err = self.record(approve(verdict="reject", head_sha=self.not_flipped))
        self.assertEqual(code, 0, out + err)

    def test_a_decision_the_task_does_not_cite_does_not_count(self):
        self.task("0001-a", ["ADR-0001 D2", "ADR-0001"])
        head = self.commit("cite only D2, and the ADR as a whole")
        code, out, err = self.record(approve(head_sha=head))
        self.assertEqual(code, 0, out + err)

    def test_the_task_file_is_read_at_the_head(self):
        self.task("0001-a", ["ADR-0001 D2"])
        cites_d2 = self.commit("the head cites only D2")
        self.task("0001-a", ["ADR-0001 D1"])  # the checkout cites D1, the head does not
        code, out, err = self.record(approve(head_sha=cites_d2))
        self.assertEqual(code, 0, out + err)

    def test_a_head_this_checkout_lacks_is_refused_only_when_a_decision_is_cited(self):
        missing = "c" * 40
        code, _, err = self.record(approve(head_sha=missing))
        self.assertEqual(code, 1, err)
        self.assertIn("not in this checkout", err)
        self.task("0001-a", [])
        code, out, err = self.record(approve(head_sha=missing))
        self.assertEqual(code, 0, out + err)

    def test_a_pr_that_is_not_a_tasks_is_not_judged(self):
        code, out, err = self.record(approve(task="pr-7", head_sha=self.not_flipped))
        self.assertEqual(code, 0, out + err)


class NotStrict(InForceAtVerify):
    strict = False

    def test_without_adr_strict_the_approve_is_recorded(self):
        code, out, err = self.record(approve(head_sha=self.not_flipped))
        self.assertEqual(code, 0, out + err)


del InForceAtVerify

if __name__ == "__main__":
    unittest.main()
