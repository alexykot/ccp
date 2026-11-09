"""The prompt audit (SPEC §23.8): ids, refs, the prompt's hash and length by default; the full text
only under `prompts.keep_body`; audits older than `prompts.audit_keep_days` pruned by `ccp prompt`."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import config, estimator, health
from ccp import prompt as prompt_mod
from ccp.queue import OBS
from tests.helpers import Product
from tests.test_toolkit import ToolkitFixture


def stamp(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y%m%dT%H%M%SZ")


class PromptAudit(ToolkitFixture, unittest.TestCase):
    def plane(self, **prompts) -> None:
        pj = dict(self.PLANE_JSON, prompts={**self.PLANE_JSON["prompts"], **prompts})
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(pj))

    def render(self) -> tuple[dict, dict, str]:
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        audit = json.loads((self.q / body["prompt_ref"]).read_text())
        return body, audit, Path(body["prompt_path"]).read_text()

    def old_audits(self) -> dict[str, Path]:
        d = self.q / "prompts" / "0001-first"
        d.mkdir(parents=True, exist_ok=True)
        out = {"old": d / f"{stamp(30)}_implement.json", "recent": d / f"{stamp(2)}_review.json",
               "rendered": d / "implement-prompt.md", "other": d / "notes.json"}
        for f in out.values():
            f.write_text(json.dumps({"prompt_sha256": "0" * 64}))
            old = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
            os.utime(f, (old, old))
        return out

    def test_a_default_product_audit_has_the_hash_and_no_text(self):
        body, audit, text = self.render()
        self.assertNotIn("prompt_body", audit)
        self.assertEqual(audit["prompt_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(audit["prompt_chars"], len(text))
        self.assertEqual((audit["task_id"], audit["session_id"]), ("0002-second", body["run_id"]))
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(run["prompt_ref"], body["prompt_ref"])  # the run binds without the text

    def test_opting_in_keeps_the_text_and_old_audits_are_pruned(self):
        self.plane(keep_body=True, audit_keep_days=7)
        files = self.old_audits()
        _, audit, text = self.render()
        self.assertEqual(audit["prompt_body"], text)
        self.assertEqual(audit["prompt_sha256"], hashlib.sha256(text.encode()).hexdigest())
        self.assertFalse(files["old"].exists())
        for k in ("recent", "rendered", "other"):  # inside the age, by name; not audits
            self.assertTrue(files[k].exists(), k)

    def test_without_a_retention_age_every_audit_is_kept(self):
        files = self.old_audits()
        self.render()
        self.assertTrue(files["old"].exists())

    def test_the_audit_matches_its_schema(self):
        schema = json.loads((OBS.parent.parent / "contracts/prompt_audit.schema.json").read_text())
        self.plane(keep_body=True)
        _, audit, _ = self.render()
        self.assertLessEqual(set(audit), set(schema["properties"]))
        self.assertLessEqual(set(schema["required"]), set(audit))
        self.assertNotIn("prompt_body", schema["required"])

    def test_the_knobs_are_checked(self):
        for prompts, want in (({"keep_body": "yes"}, "prompts.keep_body must be true or false"),
                              ({"audit_keep_days": 0}, "prompts.audit_keep_days must be an integer >= 1"),
                              ({"audit_keep_days": True}, "prompts.audit_keep_days must be an integer >= 1"),
                              ({"audit_keep_days": "7"}, "prompts.audit_keep_days must be an integer >= 1")):
            self.plane(**prompts)
            with self.assertRaises(config.ConfigError) as cm:
                config.load(self.runner)
            self.assertIn(want, str(cm.exception))
        self.plane(keep_body=False, audit_keep_days=None)
        self.assertEqual(config.load(self.runner).prompts["audit_keep_days"], None)
        self.assertIs(config.load(self.main).prompts["keep_body"], False)

    def test_the_config_schema_names_the_knobs(self):
        schema = json.loads((OBS.parent.parent / "contracts/plane_config.schema.json").read_text())
        self.assertLessEqual(set(config.PROMPTS_DEFAULTS), set(schema["properties"]["prompts"]["properties"]))


class Pruning(unittest.TestCase):
    def test_age_is_read_from_the_name_and_only_audits_go(self):
        p = Product({"prompts": {"audit_keep_days": 3}})
        self.addCleanup(p.cleanup)
        with tempfile.TemporaryDirectory() as qd:
            q = Path(qd)
            now = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
            d = q / "prompts" / "_runner"
            d.mkdir(parents=True)
            keep = d / "20261107T120000Z_runner-spawn.json"
            gone = d / "20261106T115959Z_runner-spawn.json"
            odd = d / "20261399T000000Z_bad.json"  # not a date: left alone
            for f in (keep, gone, odd):
                f.write_text("{}")
            self.assertEqual(prompt_mod.prune_audits(q, p.cfg, now), 1)
            self.assertEqual(sorted(x.name for x in d.iterdir()), sorted([keep.name, odd.name]))
            self.assertEqual(prompt_mod.prune_audits(q / "missing", p.cfg, now), 0)
        p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo"}))
        self.assertEqual(prompt_mod.prune_audits(Path("/nonexistent"), p.cfg, now), 0)


class Writer(unittest.TestCase):
    PROMPT = "Do the task.\nThen report."

    def write(self, *extra: str) -> dict:
        with tempfile.TemporaryDirectory() as qd:
            r = subprocess.run(
                ["bash", str(OBS / "write-prompt-audit.sh"), "--task-id", "t1", "--phase", "estimate", "--prompt-file", "-",
                 "--project-id", "demo", "--argv", json.dumps(["claude", "-p", self.PROMPT, "--x"]), *extra],
                input=self.PROMPT, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": qd})
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads((Path(qd) / r.stdout.strip().splitlines()[-1]).read_text())

    def test_without_keep_body_the_argv_prompt_is_replaced(self):
        audit = self.write()
        self.assertNotIn("prompt_body", audit)
        self.assertEqual(audit["argv"], ["claude", "-p", "<prompt>", "--x"])
        self.assertEqual(audit["prompt_chars"], len(self.PROMPT))
        self.assertNotIn("Then report", json.dumps(audit))

    def test_keep_body_keeps_the_text_and_the_argv(self):
        audit = self.write("--keep-body")
        self.assertEqual(audit["prompt_body"], self.PROMPT)
        self.assertEqual(audit["argv"], ["claude", "-p", self.PROMPT, "--x"])


class HealthSizes(unittest.TestCase):
    def test_prompt_sizes_come_from_the_length_without_a_body(self):
        with tempfile.TemporaryDirectory() as qd:
            q = Path(qd)
            pd = q / "prompts" / "0003-t3"
            pd.mkdir(parents=True)
            (pd / "20251009T094000Z_implement.json").write_text(json.dumps({"prompt_chars": 250}))
            (pd / "20251009T095000Z_review.json").write_text(json.dumps({"prompt_body": "x" * 40}))  # from before
            r = health._task_queue(q, "0003-t3", {})
        self.assertEqual((r["prompts"], r["prompt_chars"], r["implement_prompt_chars"]), (2, 290, 250))


class EstimatorAudit(unittest.TestCase):
    def call(self, prompts: dict) -> dict:
        p = Product({"prompts": prompts})
        self.addCleanup(p.cleanup)
        with tempfile.TemporaryDirectory() as qd:
            stub = Path(qd) / "claude-stub"
            stub.write_text("#!/bin/sh\necho '{}'\n")
            stub.chmod(0o755)
            q = Path(qd) / "queue"
            q.mkdir()
            with mock.patch.dict(os.environ, {"CCP_ESTIMATOR_CLAUDE_BIN": str(stub)}):
                estimator.call(p.cfg, q, "Estimate this task.", "r1", "0003-t3")
            return json.loads(next((q / "prompts").rglob("*_estimate.json")).read_text())

    def test_the_estimator_audit_follows_keep_body(self):
        self.assertNotIn("prompt_body", self.call({}))
        self.assertEqual(self.call({"keep_body": True})["prompt_body"], "Estimate this task.")


if __name__ == "__main__":
    unittest.main()
