"""plane.json `verify.accept_cache` (SPEC §15.3): a product's content-keyed test cache stands in for
a rerun in the verifier's gate."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import config, drill, report, tasklog
from tests.test_toolkit import PLANE, ToolkitFixture, git

ORIGINAL = ("A check you did not run is not a pass: record it as not run, resting on one of the three forms below. "
            "Be adversarial:")
CACHE = {"max_age_days": 3, "cold_tasks": ["*-rollout"]}


class CacheFixture(ToolkitFixture):
    def plane(self, accept_cache=None, commit=True) -> None:
        body = dict(self.PLANE_JSON)
        if accept_cache is not None:
            body["verify"] = {"accept_cache": accept_cache}
        self.write("docs/delivery/plane.json", json.dumps(body))
        if commit:
            git(self.main, "add", "-A")
            git(self.main, "commit", "-q", "-m", "plane.json")
            git(self.main, "push", "-q", "origin", "main")
            git(self.runner, "fetch", "-q", "origin")
            git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def verify_prompt(self) -> str:
        self.ccp("tasks", "claim", "0002")
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        return (self.q / "prompts/0002-second/verify-prompt.md").read_text()

    def record(self, gate_runs: list[dict]):
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", project_id="demo", head_sha="a" * 40)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it",
                          "produced_by": "verifier"}]
        rec["gate"] = {"runs": gate_runs}
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        return self.ccp("verify", "record", str(f))


WARM = {"command": "scripts/gate.sh main", "exit_code": 0, "tests_run": 40, "seconds": 12,
        "ran": 3, "cached": 90, "cold": False}
COLD = {**WARM, "ran": 93, "cached": 0, "cold": True}


class Config(CacheFixture, unittest.TestCase):
    def test_shape_and_refusals(self):
        self.plane(CACHE, commit=False)
        self.assertEqual(config.load(self.main).verify["accept_cache"], {**CACHE, "review": False})
        self.plane({"max_age_days": 3}, commit=False)
        self.assertEqual(config.load(self.main).verify["accept_cache"]["cold_tasks"], [])
        self.plane({**CACHE, "review": True}, commit=False)
        self.assertIs(config.load(self.main).verify["accept_cache"]["review"], True)
        for bad in ({}, {"max_age_days": 0}, {"max_age_days": True}, {"max_age_days": 3, "cold_tasks": "x"},
                    {"max_age_days": 3, "other": 1}, {"max_age_days": 3, "review": "yes"}, "on"):
            self.plane(bad, commit=False)
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load(self.main)
        self.plane(None, commit=False)
        self.assertIsNone(config.load(self.main).verify["accept_cache"])

    def test_the_schema_has_the_block_and_the_gate_counts(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        ac = schema["properties"]["verify"]["properties"]["accept_cache"]["properties"]
        self.assertEqual(set(ac), set(config.ACCEPT_CACHE_DEFAULTS))
        runs = json.loads((PLANE / "contracts/verification.schema.json").read_text())
        item = runs["properties"]["gate"]["properties"]["runs"]["items"]["properties"]
        self.assertTrue({"ran", "cached", "cold", "modules_ran", "modules_cached"} <= set(item))

    def test_tasks_check_takes_gate_cold_only(self):
        p = self.main / "docs/delivery/tasks/0002-second.md"
        text = p.read_text()
        p.write_text(text.replace("status: pending", "status: pending\ngate: cold", 1))
        self.assertEqual([e for e in tasklog.check(config.load(self.main)) if "gate" in e], [])
        p.write_text(text.replace("status: pending", "status: pending\ngate: warm", 1))
        self.assertTrue(any("gate 'warm' is not `cold`" in e for e in tasklog.check(config.load(self.main))))


class Prompt(CacheFixture, unittest.TestCase):
    def test_without_the_setting_the_brief_is_unchanged(self):
        text = self.verify_prompt()
        self.assertIn(ORIGINAL, text)
        self.assertNotIn("accept_cache", text)
        self.assertNotIn("cached", text)

    def test_with_it_a_cache_hit_counts_as_run_and_the_gate_is_warm(self):
        self.plane(CACHE)
        text = self.verify_prompt()
        self.assertNotIn(ORIGINAL, text)
        self.assertIn("counts as run, and as passed", text)
        self.assertIn("An entry more than 3 days old is not a hit", text)
        self.assertIn("Run the gate warm", text)
        self.assertIn("`Suite: <n> tests, <s> s, ran <r>, cached <c>`", text)
        self.assertNotIn("This task's gate is cold", text)

    def test_a_task_marked_cold_gets_a_cold_gate(self):
        p = self.main / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("status: pending", "status: pending\ngate: cold", 1))
        self.plane(CACHE)
        text = self.verify_prompt()
        self.assertIn("This task's gate is cold", text)
        self.assertNotIn("Run the gate warm", text)

    def test_a_cold_tasks_glob_marks_it_too(self):
        from ccp import verify
        self.plane(CACHE, commit=False)
        cfg = config.load(self.main)
        self.assertTrue(verify.cold_gate(cfg, {"task_id": "0290-big-rollout"}))
        self.assertFalse(verify.cold_gate(cfg, {"task_id": "0244-test-cache-rules"}))
        self.plane(None, commit=False)
        self.assertFalse(verify.cold_gate(config.load(self.main), {"task_id": "0290-x-rollout", "gate": "cold"}))


class Record(CacheFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane(CACHE)
        self.verify_prompt()

    def test_an_approve_gives_the_counts(self):
        bare = {k: v for k, v in WARM.items() if k not in ("ran", "cached", "cold")}
        code, _, _, err = self.record([bare])
        self.assertEqual(code, 1)
        self.assertIn("gives ran and cached", err)
        self.assertFalse((self.q / "verification/0002-second.json").exists())
        code, _, out, err = self.record([WARM, {"command": "ccp docs check", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)

    def test_a_gate_run_with_the_pre_contract_names_still_counts(self):
        old = {k: v for k, v in WARM.items() if k not in ("ran", "cached")} | {"modules_ran": 3, "modules_cached": 90}
        code, _, out, err = self.record([old, {"command": "ccp docs check", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)

    def test_a_cold_gate_task_needs_a_cold_run(self):
        p = self.runner / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("status: pending", "status: pending\ngate: cold", 1))
        code, _, _, err = self.record([WARM])
        self.assertEqual(code, 1)
        self.assertIn("gate is cold", err)
        code, _, out, err = self.record([COLD])
        self.assertEqual(code, 0, out + err)

    def test_a_warm_run_beside_a_cold_one_is_accepted_on_a_cold_gate(self):
        p = self.runner / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("status: pending", "status: pending\ngate: cold", 1))
        code, _, out, err = self.record([WARM, COLD])
        self.assertEqual(code, 0, out + err)

    def test_without_the_setting_nothing_changes(self):
        self.plane(None, commit=False)
        p = self.runner / "docs/delivery/plane.json"
        p.write_text((self.main / "docs/delivery/plane.json").read_text())
        code, _, out, err = self.record([{"command": "scripts/unit.sh", "exit_code": 0}])
        self.assertEqual(code, 0, out + err)


class Report(CacheFixture, unittest.TestCase):
    def test_suite_line_counts(self):
        text = "Outcome: done\nVerdict: approve\nHead: abcdef1\nSuite: 40 tests, 12 s, mac, ran 3, cached 90\n## Friction\nnone\n"
        out, errs = report.parse("verify", text, accept_cache=True)
        self.assertEqual((errs, out["suite_ran"], out["suite_cached"]), ([], 3, 90))
        out, errs = report.parse("verify", text.replace(", ran 3, cached 90", ""), accept_cache=True)
        self.assertTrue(any("ran <r>, cached <c>" in e for e in errs))
        self.assertEqual(report.parse("verify", text.replace(", ran 3, cached 90", ""))[1], [])
        self.assertEqual(report.parse("implement", text.replace(", ran 3, cached 90", ""), accept_cache=True)[1][:1],
                         ["no `PR: #<number>` line"])

    def test_a_blank_line_before_the_suite_line_keeps_its_counts(self):
        """`^\\W*` under re.M matched from the blank line above `Suite:`."""
        text = ("Outcome: done\n\nVerdict: approve\n\nHead: abcdef1\n\n- **Suite: 40 tests, 12 s, ran 3, cached 90**\n\n"
                "## Friction\nnone\n")
        out, errs = report.parse("verify", text, accept_cache=True)
        self.assertEqual((errs, out["suite_tests"], out["suite_ran"], out["suite_cached"]), ([], 40, 3, 90))
        self.assertEqual(report.SUITE_ANY_RE.search(text).group(0), "- **Suite: 40 tests, 12 s, ran 3, cached 90**")
        out, _ = report.parse("verify", text.replace("40 tests, 12 s", "unreadable"), accept_cache=True)
        self.assertEqual(out["suite_unparsed"], "- **Suite: unreadable, ran 3, cached 90**")
        bold = text.replace("**Suite: 40 tests, 12 s, ran 3, cached 90**", "**Suite:** 40 tests, 12 s, ran 3, cached 90")
        out, errs = report.parse("verify", bold, accept_cache=True)
        self.assertEqual((errs, out["suite_tests"], out["suite_cached"]), ([], 40, 90))
        self.assertEqual(report.parse("verify", bold.replace("40 tests, 12 s, ran 3, cached 90", "from st-1-a"))[0]["suite_from"],
                         "st-1-a")
        out, errs = report.parse("verify", text.replace("\n", "\r\n"), accept_cache=True)  # CRLF line endings
        self.assertEqual((errs, out["suite_ran"], out["friction"]), ([], 3, []))

    def test_a_warm_suite_line_is_kept_on_the_run_not_in_health(self):
        self.plane(CACHE)
        self.verify_prompt()
        self.assertEqual(self.record([WARM])[0], 0)
        code, body, out, err = self.report("0002-second/verify", f"""\
            Outcome: done
            Verdict: approve
            Head: {'a' * 40}
            Suite: 40 tests, 12 s, ran 3, cached 90

            ## Friction
            none
            """)
        self.assertEqual(code, 0, out + err)
        self.assertEqual((body["suite_ran"], body["suite_cached"]), (3, 90))
        metrics = [json.loads(x) for x in (self.q / "health/metrics.jsonl").read_text().splitlines()]
        # §27.2: no suite record for the run, so the line falls back: warm, out of the cold series
        self.assertEqual({m["metric"] for m in metrics}, {"suite_tests_warm", "suite_seconds_warm"})
        rows = drill._report_suites(self.q, "0002-second")
        self.assertEqual([(r["ran"], r["cached"]) for r in rows], [(3, 90)])


if __name__ == "__main__":
    unittest.main()
