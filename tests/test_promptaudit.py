"""SPEC §23.8: `ccp.promptaudit.write`, the one function every prompt audit is written through, run against a scratch
queue: the ref it returns, the body kept only under `prompts.keep_body`, and a writer that fails."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ccp import promptaudit
from ccp.queue import QueueError, lib
from tests.helpers import Product


class Write(unittest.TestCase):
    PROMPT = "Do the task.\nThen report."
    ARGV = ["claude", "-p", PROMPT, "--x"]

    def setUp(self):
        q = tempfile.TemporaryDirectory()
        self.addCleanup(q.cleanup)
        self.q = Path(q.name)

    def audit(self, ref: str) -> dict:
        return json.loads((self.q / ref).read_text())

    def test_the_ref_names_the_audit_written_with_the_fields_given(self):
        ref = promptaudit.write(self.q, None, task_id="t1", phase="estimate", argv=self.ARGV, prompt=self.PROMPT,
                                actor=lib.LEAD, project_id="demo", git_head="abc1234", notes="a note", worktree=None)
        self.assertTrue(ref.startswith("prompts/t1/") and ref.endswith("_estimate.json"), ref)
        audit = self.audit(ref)
        self.assertEqual((audit["task_id"], audit["phase"], audit["actor"], audit["project_id"]),
                         ("t1", "estimate", lib.LEAD, "demo"))
        self.assertEqual((audit["git_head"], audit["notes"]), ("abc1234", "a note"))
        self.assertIsNone(audit["worktree"])  # a field given as None is not passed
        self.assertEqual(audit["prompt_chars"], len(self.PROMPT))

    def test_a_named_prompt_file_is_the_prompt_and_a_field_keeps_its_dashes(self):
        f = self.q / "prompt.txt"
        f.write_text(self.PROMPT)
        ref = promptaudit.write(self.q, None, task_id="t1", phase="implement", argv=["Agent", "x"], prompt_file=f,
                                actor=lib.LEAD, project_id="demo", durable_task_path="docs/delivery/tasks/t1.md", spec_refs='["S1"]')
        audit = self.audit(ref)
        self.assertEqual(audit["prompt_chars"], len(self.PROMPT))
        self.assertEqual((audit["durable_task_path"], audit["spec_refs"]), ("docs/delivery/tasks/t1.md", ["S1"]))
        with self.assertRaises(ValueError):
            promptaudit.write(self.q, None, task_id="t1", phase="implement", argv=[])
        with self.assertRaises(ValueError):
            promptaudit.write(self.q, None, task_id="t1", phase="implement", argv=[], prompt="x", prompt_file=f)

    def test_the_body_is_kept_only_under_the_products_setting(self):
        for prompts, cfg_given, kept in (({}, True, False), ({"keep_body": False}, True, False),
                                         ({"keep_body": True}, True, True), ({"keep_body": True}, False, False)):
            with self.subTest(prompts=prompts, cfg_given=cfg_given):
                p = Product({"prompts": prompts})
                self.addCleanup(p.cleanup)
                ref = promptaudit.write(self.q, p.cfg if cfg_given else None, task_id="t1", phase="estimate",
                                        argv=self.ARGV, prompt=self.PROMPT, actor=lib.LEAD,
                                        project_id="demo")
                audit = self.audit(ref)
                self.assertEqual("prompt_body" in audit, kept)
                self.assertEqual(audit["argv"][2], self.PROMPT if kept else "<prompt>")

    def test_a_writer_that_fails_raises_with_its_message(self):
        with self.assertRaises(QueueError) as ctx:
            promptaudit.write(self.q, None, task_id="t1", phase="estimate", argv=self.ARGV, prompt=self.PROMPT,
                              actor="nobody", project_id="demo")
        self.assertTrue(str(ctx.exception).startswith("write-prompt-audit failed: "), str(ctx.exception))
        self.assertIn("invalid actor", str(ctx.exception))
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual([p for p in self.q.rglob("*") if p.is_file()], [])


if __name__ == "__main__":
    unittest.main()
