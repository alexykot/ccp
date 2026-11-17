"""`ccp prompt env <worktree>` (SPEC §13.3): the `prompts.worker_env` lines a worktree's workers would get,
rendered from its record, with no run opened and nothing written."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.test_toolkit import ToolkitFixture, git

ENV = {"TAG": "{{nnnn}}-{{seat}}-{{kind}}", "WT": "{{worktree}}", "RUN": "{{run_id}}|{{phase}}|{{task_id}}",
       "Q": "{{queue_root}}", "MAIN": "{{main_checkout}}/x y", "P": "{{project_id}}"}
A = "a" * 40


class PromptEnv(ToolkitFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.with_env(ENV)
        sha = git(self.main, "rev-parse", "origin/main")
        code, body, out, err = self.ccp("wt", "create", "--kind", "rev", "--task", "0002", "--sha", sha,
                                        "--seat", "probe", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.rev = Path(body["path"])

    def with_env(self, env: dict) -> None:
        pj = dict(self.PLANE_JSON, prompts={"worker_env": env})
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(pj))

    def queue_files(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.q)): p.read_bytes() for p in sorted(self.q.rglob("*")) if p.is_file()}

    def values(self, text: str) -> list[str]:
        """What the printed lines set, read back by the shell."""
        r = subprocess.run(["sh", "-c", text + 'printf "%s\\n" "$TAG" "$WT" "$RUN" "$Q" "$MAIN" "$P"'],
                           capture_output=True, text=True, check=True)
        return r.stdout.splitlines()

    def test_it_prints_the_rendered_lines_with_that_worktrees_values_and_writes_nothing(self):
        before = self.queue_files()
        code, _, out, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.queue_files(), before)  # no run, no prompt audit, no event, no board
        self.assertTrue(all(ln.startswith("export ") for ln in out.splitlines()), out)
        self.assertEqual(self.values(out), ["0002-probe-rev", str(self.rev), "<run_id>|<phase>|0002-second",
                                            str(self.q), f"{self.main}/x y", self.PLANE_JSON["project_id"]])

    def test_it_starts_no_board_rebuild(self):
        with mock.patch("ccp.board.refresh") as refresh:
            code, _, _, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual(code, 0, err)
        refresh.assert_not_called()

    def test_the_worktree_may_be_named_by_its_record(self):
        by_path = self.ccp("prompt", "env", str(self.rev))
        by_name = self.ccp("prompt", "env", self.rev.name)
        self.assertEqual((by_name[0], by_name[2]), (0, by_path[2]), by_name[3])

    def test_with_a_run_bound_there_it_matches_the_env_file_ccp_prompt_writes(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        written = [ln + "\n" for ln in Path(body["env_file"]).read_text().splitlines() if ln.startswith("export ")]
        code, _, out, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "".join(written))
        self.assertIn("0002-second/review|review|0002-second", out)

    def test_a_reported_run_is_not_the_worktrees_run(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        rec_path = self.q / "runs/0002-second/review.json"
        rec = json.loads(rec_path.read_text())
        rec_path.write_text(json.dumps({**rec, "reported_at": "2026-01-01T00:00:00Z"}))
        code, _, out, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual(code, 0, err)
        self.assertIn("<run_id>|<phase>|0002-second", self.values(out)[2])

    def test_a_worktree_with_no_record_is_refused(self):
        for where in (str(self.main), str(Path(self._tmp.name) / "nowhere"), "rev-0009", "../rev-0002"):
            before = self.queue_files()
            code, _, out, err = self.ccp("prompt", "env", where)
            self.assertEqual((code, out), (2, ""), (where, err))
            self.assertEqual(self.queue_files(), before)

    def test_a_product_with_no_worker_env_prints_nothing(self):
        self.with_env({})
        code, _, out, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual((code, out), (0, ""), err)
        self.assertIn("worker_env", err)

    def test_a_value_that_looks_like_a_secret_is_refused(self):
        self.with_env({"TOKEN": "ghp_" + "A" * 36})
        code, _, out, err = self.ccp("prompt", "env", str(self.rev))
        self.assertEqual((code, out), (2, ""), err)
        self.assertIn("secret", err)


if __name__ == "__main__":
    unittest.main()
