"""The helpers the review and verify tests share, on mixins that hold no tests.

`ReviewFlow`, `SkipFlow` and `PhaseFlow` mix into a `ToolkitFixture` `TestCase` (`class X(ReviewFlow, ToolkitFixture,
unittest.TestCase)`): they drive a claimed `0002-second` through review, fix and verify rounds, so a module
that needs a round inherits them and never borrows a method off another module's test class."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tests.report_helpers import done_report
from tests.toolkit_fixture import PLANE, ToolkitFixture, git

A, B = "a" * 40, "b" * 40

# The proof command `SkipFlow`'s product declares (`verify.skip_review.proof`): it logs its arguments to
# `$PROOF_LOG` and exits `$PROOF_EXIT`.
PROOF = '#!/bin/sh\necho "$@" >> "$PROOF_LOG"\nsleep "${PROOF_SLEEP:-0}"\nexit "${PROOF_EXIT:-0}"\n'
SKIP_REVIEW_PLANE = {**ToolkitFixture.PLANE_JSON,
                     "verify": {"skip_review": {"paths": ["tests"], "proof": '"$PROOF_BIN" {task_id} {reviewed} {head} {from}'}}}


class ReviewFlow:
    """Review, fix and verdict rounds of a claimed task, and a commit in a worktree."""

    def run_phase(self, phase: str, head: str, lines: str, *extra: str):
        code, body, out, err = self.ccp("prompt", phase, "0002", "--pr", "7", "--head", head, *extra)
        self.assertEqual(code, 0, f"{phase}: {out}{err}")
        code, _, out, err = self.report(body["run_id"], done_report(phase, lines))
        self.assertEqual(code, 0, f"{phase} report: {out}{err}")
        return body["run_id"]

    def review(self, head: str = A):
        return self.run_phase("review", head, "Severity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0")

    def fix(self, head: str = A, to: str = B):
        return self.run_phase("fix", head, f"PR: #7\nHead: {to}")

    def verdict(self, head: str, verdict: str = "approve"):
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head, verdict=verdict)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": verdict == "approve", "evidence": "ran it",
                          "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))

    def verify_round(self, head: str = A, verdict: str = "reject"):
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.verdict(head, verdict)
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(body["run_id"], f"Outcome: done\nVerdict: {verdict}\nHead: {head}\n"
                                                         "## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def commit(self, wt, rel, text, msg):
        (wt / rel).write_text(text)
        git(wt, "add", rel)
        git(wt, "commit", "-q", "-m", msg)
        return git(wt, "rev-parse", "HEAD")


class SkipFlow(ReviewFlow):
    """`ReviewFlow` for a task claimed into `self.wt`, its worktree, with a proof command: `commit`, `fix`
    and `push` here replace `ReviewFlow`'s, which take other arguments, and `on_main`, `reviewed` and `verify` are new.
    A class using it sets `wt` and `log` in `setUp` and `PLANE_JSON = SKIP_REVIEW_PLANE`."""

    def commit(self, rel: str, text: str, wt: Path | None = None) -> str:
        wt = wt or self.wt
        (wt / rel).parent.mkdir(parents=True, exist_ok=True)
        (wt / rel).write_text(text)
        git(wt, "add", rel)
        git(wt, "commit", "-q", "-m", f"change {rel}")
        return git(wt, "rev-parse", "HEAD")

    def on_main(self, files: dict[str, str]) -> None:
        """Another task's merge landing on the integration branch: each `rel: text` of `files` committed in order in
        a detached worktree at `origin/main`, then pushed to `main` once."""
        other = Path(tempfile.mkdtemp(dir=self._tmp.name))
        git(self.main, "worktree", "add", "-q", "--detach", str(other), "origin/main")
        for rel, text in files.items():
            self.commit(rel, text, other)
        git(other, "push", "-q", "origin", "HEAD:main")

    def push(self) -> str:
        git(self.wt, "push", "-q", "-u", "origin", "task/0002-second")
        return git(self.wt, "rev-parse", "HEAD")

    def reviewed(self) -> str:
        self.commit("feature.txt", "built\n")
        self.commit("tests/test_feature.txt", "check it\n")
        head = self.push()
        self.review(head)
        return head

    def fix(self, rel: str = "tests/test_feature.txt", text: str = "check it  # comment fixed\n") -> str:
        reviewed = git(self.wt, "rev-parse", "HEAD")
        self.commit(rel, text)
        head = self.push()
        self.run_phase("fix", reviewed, f"PR: #7\nHead: {head}")
        return head

    def verify(self, head: str, *extra: str):
        return self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head, *extra)


class PhaseFlow(ReviewFlow):
    """`ReviewFlow` with the rounds that move a task through `implemented` and `reviewed` (SPEC §10.1): a claimed
    `0002-second`, an implement round bound to a session and reported done with PR #7 at `A`, and reviews whose
    workers are bound to sessions too. Every run opens a second after the last (`opened_at` has one-second
    resolution); `start` patches the clock and claims the task."""

    IMPLEMENTER_SESSION = "sess-implementer"

    def start(self) -> None:
        from unittest import mock  # noqa: PLC0415
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        for where in ("ccp.runs.iso", "ccp.report.iso"):
            patch = mock.patch(where, side_effect=lambda: next(clock))
            patch.start()
            self.addCleanup(patch.stop)
        self.ccp("tasks", "claim", "0002")

    def bind(self, agent_type: str, agent: str, session: str) -> None:
        from ccp import config, runs  # noqa: PLC0415
        runs.bind(self.q, config.load(self.runner), agent_type, agent, session)

    def implemented(self, head: str = A) -> str:
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.bind("delivery-implementer", "agent-implementer", self.IMPLEMENTER_SESSION)
        code, _, out, err = self.report(body["run_id"], done_report("implement", "PR: #7", f"Head: {head}"))
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def reviewed_as(self, severity: str, head: str = A, session: str = "sess-reviewer") -> str:
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        self.bind("delivery-reviewer", f"agent-{body['run_id']}", session)
        code, _, out, err = self.report(body["run_id"], f"Outcome: done\nSeverity: {severity}\n"
                                                        "## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        return body["run_id"]

    def status(self) -> str:
        return json.loads((self.q / "tasks/0002-second.json").read_text())["status"]

    def review_record(self) -> Path:
        from ccp import report  # noqa: PLC0415
        return report.review_record_path(self.q, "0002-second")


CLEAN = "BLOCKER=0 MAJOR=0 MINOR=0 NIT=0"
MAJOR = "BLOCKER=0 MAJOR=1 MINOR=0 NIT=0"
