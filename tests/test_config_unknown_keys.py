"""plane.json keys this ccp does not know (SPEC §8.1): loading ignores them, warning on stderr with each
key's dotted path and the file; `ccp docs check` fails on each; a known key's wrong value is still refused."""
from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli, config
from tests.helpers import Product

FUTURE = {"future_block": {}, "verify": {"future_knob": True}}

# One known key at every level the plane reads by key: none of them is unknown.
EVERY_LEVEL = {
    "$schema": "x", "_note": "x", "language": "none",
    "ids": {"task": {"width": 4}, "adr": {"prefix": "ADR-", "width": 4}, "spec": {"prefix": "S"},
            "rule": {"pattern": "E[0-9]+"}, "review_point": {"pattern": "R[1-9][0-9]*"}},
    "task_log": {"kinds": {"feature": {"refs_any": ["spec_refs"], "forbid": []}}, "max_checks": 6},
    "package_docs": {"rules": {"citations": {"globs": ["*.md"], "targets": ["x"], "ignore": []},
                                                   "no_ids": {"globs": ["*.md"], "patterns": []},
                                                   "no_overlap": True}},
    "docs": {"checks": [{"id": "c", "cmd": "true", "timeout_seconds": 5}], "workers": 1,
             "starter_rules": {"declined": {}}},
    "architect": {"checks": [{"id": "E1", "cmd": "true", "timeout_seconds": 5}],
                  "budgets": [{"id": "E2", "glob": "*.py", "max_lines": 9, "cut_line": 8}], "areas": {"code": ["src/**"]}},
    "prompts": {"worker_env": {"X": "{{task_id}}"}, "keep_body": False},
    "reconcile": {"log": {"path": "log.md", "entry": "{task_id}", "before": "^#"}, "hooks": []},
    "auth_check": {"probes": [{"id": "gh", "cmd": "true"}], "timeout_seconds": 5},
    "telemetry": {"design_seat": {"model": "m", "effort": "high"},
                  "windows": {"seven_day": {"kind": "weekly", "stop_pct": 90}}},
    "usage": {"advice": {"context_tokens": 1000}},
    "workers": {"implementer_model": {"small": "sonnet", "refactor": "opus"}},
    "suite": {"lanes": {"full": ["true"], "gate": [{"name": "tests", "cmd": "true"}]},
              "summary": {"tail_lines": 5, "modules_ran_re": r"(\d+) ran"},
              "roles": {"full": "full", "gate": "gate", "part": "part"}},
    "verify": {"accept_cache": {"max_age_days": 7, "cold_tasks": [], "review": False},
               "skip_review": {"paths": ["docs"], "proof": "true"},
               "provers": [{"name": "p", "command": "true", "skips": "review"}]},
    "estimate": {"calibration": {"half_life": 40, "min_pairs": 8, "k": None}},
    "report": {"required_fields": [{"name": "Docs", "values": ["yes", "no"]}]},
    "notify": {"lead": {"tool": "t", "to": "x"}},
    "upgrade": {"declined": {"0001-x": "why"}, "taken": {}},
}


def _load(p: Product) -> tuple[config.Config, str]:
    err = io.StringIO()
    with redirect_stderr(err):
        return config.load(p.root), err.getvalue()


class UnknownKeys(unittest.TestCase):
    def product(self, cfg: dict) -> Product:
        p = Product(cfg)
        self.addCleanup(p.cleanup)
        return p

    def ccp(self, p: Product, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(p.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_a_command_runs_as_it_would_without_them_and_names_them_on_stderr(self):
        p, plain = self.product(FUTURE), self.product({})
        p.task("0001-a")
        plain.task("0001-a")
        code, out, err = self.ccp(p, "tasks", "next")
        self.assertEqual((code, out), self.ccp(plain, "tasks", "next")[:2])
        self.assertIn(str(p.root / config.CONFIG_REL), err)
        for k in ("future_block", "verify.future_knob"):
            self.assertIn(k, err)

    def test_docs_check_fails_naming_each(self):
        p = self.product(FUTURE)
        p.task("0001-a")
        self.assertEqual(self.ccp(p, "tasks", "index")[0], 0)
        code, out, _ = self.ccp(p, "docs", "check")
        self.assertEqual(code, 1)
        for k in ("future_block", "verify.future_knob"):
            self.assertIn(f"unknown key {k}:", out)
        p.write(config.CONFIG_REL, json.dumps({"project_id": "demo"}))
        self.assertEqual(self.ccp(p, "docs", "check")[0], 0)

    def test_a_known_key_of_the_wrong_type_is_still_refused(self):
        p = self.product({"verify": {"skip_review_after_clean": "yes"}})
        code, _, err = self.ccp(p, "tasks", "next")
        self.assertEqual(code, 2)
        self.assertIn("verify.skip_review_after_clean must be true or false", err)

    def test_unknown_keys_at_every_level_are_dropped_and_named(self):
        c, err = _load(self.product({
            "architect": {"checks": [{"id": "E1", "cmd": "true", "shell": True}], "future": 1},
            "verify": {"provers": [{"name": "p", "command": "true", "skips": "review", "x": 1}],
                       "skip_review": {"paths": ["docs"], "proof": "true", "y": 2}},
            "telemetry": {"windows": {"seven_day": {"kind": "weekly", "z": 1}}},
            "suite": {"lanes": {"gate": [{"name": "tests", "cmd": "true", "w": 1}]}},
            "ids": {"task": {"width": 4, "v": 1}},
            "notify": {"lead": {"tool": "t", "to": "x", "u": 1}},
            "usage": {"advice": {"t": 1}}}))
        want = ("architect.checks[0].shell", "architect.future", "verify.provers[0].x", "verify.skip_review.y",
                "telemetry.windows.seven_day.z", "suite.lanes.gate[0].w", "ids.task.v", "notify.lead.u",
                "usage.advice.t")
        self.assertEqual(sorted(c.unknown_keys), sorted(want))
        for k in want:
            self.assertIn(k, err)
        self.assertEqual(c.architect["checks"], [{"id": "E1", "cmd": "true"}])
        self.assertEqual(c.verify["provers"], [{"name": "p", "command": "true", "skips": "review"}])
        self.assertEqual(c.verify["skip_review"], {"paths": ["docs"], "proof": "true"})
        self.assertEqual(c.notify["lead"], {"tool": "t", "to": "x"})
        self.assertEqual(c.suite["lanes"]["gate"], [{"name": "tests", "cmd": "true"}])

    def test_what_remains_is_still_validated(self):
        p = self.product({"notify": {"lead": {"tool": "t", "too": "x"}}})  # a typo for `to`: `to` is missing
        with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
            config.load(p.root)
        self.assertIn("notify.lead", str(cm.exception))

    def test_every_known_key_is_known(self):
        c, err = _load(self.product(EVERY_LEVEL))
        self.assertEqual((c.unknown_keys, err), ((), ""))

    def test_each_key_is_warned_about_once_a_process(self):
        p = self.product(FUTURE)
        first, second = _load(p)[1], _load(p)[1]
        self.assertIn("future_block", first)
        self.assertEqual(second, "")

    def test_the_skip_rules_load_from_a_plane_json_with_a_key_this_ccp_does_not_know(self):
        p = self.product({"verify": {"skip_review_after_clean": True, "future_knob": 1}})
        git = ["git", "-C", str(p.root), "-c", "user.email=t@example.com", "-c", "user.name=t"]
        for argv in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "x"]):
            subprocess.run([*git, *argv], check=True, capture_output=True)
        verify, why = config.skip_rules_at(p.root, "HEAD")
        self.assertEqual((verify["skip_review_after_clean"], why), (True, ""))


if __name__ == "__main__":
    unittest.main()
