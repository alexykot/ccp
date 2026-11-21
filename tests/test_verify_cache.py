"""plane.json `verify.accept_cache` (SPEC §15.3): a product's content-keyed test cache stands in for
a rerun in the verifier's gate."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from ccp import config, drill, report, suite, tasklog
from tests.test_suite import PY, SuiteFixture
from tests.test_toolkit import PLANE, ToolkitFixture, git

SECTION = "`verify.accept_cache`"
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
                    {"max_age_days": 3, "review": "yes"}, "on"):
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
        self.assertIn("Be adversarial:", text)
        self.assertNotIn(SECTION, text)
        self.assertNotIn("accept_cache", text)
        self.assertNotIn("cached", text)

    def test_with_it_a_cache_hit_counts_as_run_and_the_gate_is_warm(self):
        self.plane(CACHE)
        text = self.verify_prompt()
        self.assertIn(SECTION, text)
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


class ColdFromTheSuiteRecord(SuiteFixture, CacheFixture, unittest.TestCase):
    """A gate run citing a suite run takes that record's own `cold` (§14.6), so the two never disagree."""

    def setUp(self):
        super().setUp()
        self.verify_prompt()

    def gate(self, script: str, *extra: str) -> str:
        r = self.run_suite("--run", "0002-second/verify", "--lane", "gate", *extra, "--", PY, "-c", script)
        self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
        return self.rows()[-1]["suite_id"]

    def recorded(self, gate_runs: list[dict]) -> list[dict]:
        code, _, out, err = self.record(gate_runs)
        self.assertEqual(code, 0, out + err)
        return json.loads((self.q / "verification/0002-second.json").read_text())["gate"]["runs"]

    def test_a_run_with_nothing_cached_is_cold_and_an_uncounted_cold_ask_is_not(self):
        self.tally()
        counted = self.gate("print('Ran 5 tests in 0.1s'); print('gate: 5 modules ran, 0 cached; 5 tests ran in 0 s')")
        asked = self.gate("print('Ran 5 tests in 0.1s')", "--cold")
        self.assertEqual([(r["cached"], r["cold"]) for r in self.rows() if r["op"] == "ended"], [(0, True), (None, None)])
        runs_ = self.recorded([{"suite_id": counted}, {"suite_id": asked}])
        self.assertIs(runs_[0]["cold"], True)
        self.assertNotIn("cold", runs_[1])

    def test_the_records_cold_decides_not_its_cached_count(self):
        """Rows written by hand: one cold with nothing cached, one that counted nothing cached and is not
        recorded cold, and one recorded cold with no count at all (a `--cold` ask before §14.6 changed)."""
        for sid, end in (("st-said", {"cached": 0, "cold": True}), ("st-unsaid", {"cached": 0, "cold": None}),
                         ("st-asked", {"cold": True})):
            suite._append(self.q, {"op": "started", "suite_id": sid, "at": "2026-10-22T00:00:00Z", "lane": "gate",
                                   "run_id": "0002-second/verify", "task_id": "0002-second", "phase": "verify"})
            suite._append(self.q, {"op": "ended", "suite_id": sid, "at": "2026-10-22T00:01:00Z", "exit_code": 0,
                                   "seconds": 60, "tests": 5, "interrupted": None, **end})
        runs_ = self.recorded([{"suite_id": s} for s in ("st-said", "st-unsaid", "st-asked")]
                              + [{"suite_id": "st-said", "cold": False}])
        self.assertIs(runs_[0]["cold"], True)
        self.assertEqual([("cold" in r) for r in runs_[1:3]], [False, False])  # no count of nothing cached
        self.assertIs(runs_[3]["cold"], False)  # the verifier's own value wins


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
