"""SPEC §26.3 phase B: the estimator seat. The prompt (bounded, notes stripped, plain text), the
strict validation and its one retry, a failure keeping the baseline, the triggers (hash and
dependency, in-flight tasks left out), the auto flag (off by default), the budget cap, the
headless launch (no tools, pinned model, keys stripped), the live-seats row and the board. Every
`claude -p` is mocked (`estimator.call`)."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import estimate, estimator, seats
from tests.helpers import Product
from tests import test_estimate as te
from tests.test_board_drill import Fixture
from tests.test_estimate import body, entry


def answer(**over):
    a = {"complexity": {k: {"rating": "med", "reason": f"{k} is middling"} for k, _, _ in estimator.CRITERIA},
         "rounds": {"review_p50": 1, "fix_risk": 0.3},
         "phases": {"implement": {"p50_min": 20, "p90_min": 40}, "review": {"p50_min": 8, "p90_min": 15},
                    "fix": {"p50_min": 0, "p90_min": 25}, "verify": {"p50_min": 5, "p90_min": 10}},
         "total": {"p50_min": 45, "p90_min": 90}, "tokens": {"p50": 2e7, "p90": 4e7}, "cost_usd": {"p50": 8, "p90": 15},
         "reference_tasks": ["0001-sf-h"], "waits": [], "reasoning": "Close to 0001; baseline kept."}
    a.update(over)
    return a


def result(obj, cost=0.05, text=None):
    return ({"type": "result", "is_error": False, "result": text if text is not None else "```json\n" + json.dumps(obj) + "\n```",
             "total_cost_usd": cost, "duration_ms": 4000, "session_id": "sess-1",
             "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 10, "outputTokens": 700, "cacheReadInputTokens": 0,
                                                  "cacheCreationInputTokens": 9000, "costUSD": cost}}}, "", 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.p.write("docs/delivery/tasks/0005-sf-store.md", body(deps='"0004-sf-dep"', notes="- SECRET-NOTE built half of it"))
        self.p.write("docs/delivery/tasks/0004-sf-dep.md", body("0004-sf-dep"))
        self.p.write("docs/delivery/tasks/0003-sf-old.md", body("0003-sf-old", status="done"))
        self.p.write("src/app/store.py", "x\n" * 12)
        self.q = Path(tempfile.mkdtemp())
        self.hist = [entry(f"000{i}-sf-h", 1000 + i, 600 + 60 * i, areas=["src/app"], tokens=2e7) for i in range(3)]
        self.stub = mock.patch.object(estimate, "history", lambda cfg, q, tasks=None: [dict(h) for h in self.hist])
        self.stub.start()
        self.calls: list[str] = []
        self.answers: list = []

    def tearDown(self):
        self.stub.stop()
        self.p.cleanup()
        shutil.rmtree(self.q, ignore_errors=True)

    def fake(self, cfg, q, prompt, run_id, tid, actor="system"):
        self.calls.append(prompt)
        return self.answers.pop(0)

    def run_(self, ids=None, **kw):
        with mock.patch.object(estimator, "call", self.fake):
            return estimator.run(self.p.cfg, self.q, ids, **kw)


class Prompt(Base):
    def test_the_prompt_is_bounded_plain_text_without_notes(self):
        self.p.write("docs/adr/0031-big.md", "# ADR-0031: Big\n\n## Decision\n\n### D1. First\n\n" + "y" * 5000
                     + "\n\n### D2. Second\n\nshort\n")
        self.p.write("docs/adr/0007-para.md", "# ADR-0007: Para\n\n## Decision\n\nD1. **Para decision.** body one\n\n"
                     "D2. **Other.** body two\n")
        self.p.write("docs/SPEC.md", "# SPEC\n\n## S1 — First rule\n\n" + "s" * 3000 + "\n\n## S2 — Second\n\nshort two\n")
        text = body(deps='"0004-sf-dep"', notes="- SECRET-NOTE").replace("adr_refs: [\"ADR-0031\", \"0007\"]",
                                                                          "adr_refs: [\"0031 D1\", \"0031 D2\", \"0007 D1\"]")
        text = text.replace("## Scope", "{{BASELINE}} literal braces stay\n\n" + "z" * 20000 + "\n\n## Scope")
        self.p.write("docs/delivery/tasks/0005-sf-store.md", text)
        out = io.StringIO()
        with redirect_stdout(out):
            pr = estimator.prompt_for(self.p.cfg, self.q, "0005")
        self.assertNotIn("SECRET-NOTE", pr)
        self.assertNotIn("{{", pr.replace("{{BASELINE}} literal", ""))  # the template's placeholders all filled
        self.assertIn("{{BASELINE}} literal braces stay", pr)        # a task's own text is never expanded
        self.assertIn(f"[... cut at {estimator.B_TASK} characters]", pr)
        self.assertIn("### D1. First", pr)
        self.assertIn(f"[... cut at {estimator.B_ADR} characters]", pr)
        self.assertIn("short", pr)
        self.assertIn("Para decision.", pr)
        self.assertNotIn("body two", pr)                             # only the cited decision
        self.assertIn("## S1 — First rule", pr)
        self.assertIn(f"[... cut at {estimator.B_SPEC} characters]", pr)
        self.assertIn("src/app/store.py: 12 lines", pr)
        self.assertIn("not found (", pr)
        for k, _, _ in estimator.CRITERIA:
            self.assertIn(f"`{k}`", pr)
        self.assertIn('"wall_min"', pr)                              # the reference class carries actuals
        self.assertIn("0002-sf-h", pr)
        self.assertLess(len(pr), 40000)

    def test_the_launch_has_no_tools_pins_sonnet_and_strips_keys(self):
        argv = estimator.argv_for("PROMPT")
        for k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            self.assertEqual(argv[argv.index(k) - 1], "-u")
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertEqual(argv[argv.index("--model") + 1], "claude-sonnet-5-5")
        self.assertEqual(argv[argv.index("--effort") + 1], "medium")
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertNotIn("--allowedTools", argv)
        self.assertIn("--safe-mode", argv)                            # no CLAUDE.md, memory, hooks, plugins
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "local")  # no user settings file
        self.assertNotIn("--bare", argv)                              # it would drop the OAuth login
        self.assertEqual(estimator.pins()["model"], "claude-sonnet-5-5")
        from ccp import architect
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "OTEL_RESOURCE_ATTRIBUTES": "a=b,ccp.seat=old"}):
            env = architect.sm.headless_env("demo", estimator.SEAT)
        self.assertNotIn("ANTHROPIC_API_KEY", env)
        self.assertIn("ccp.seat=estimator", env["OTEL_RESOURCE_ATTRIBUTES"])


    def test_the_child_env_carries_the_user_settings_telemetry_keys(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "settings.json").write_text(json.dumps({"env": {
                "CLAUDE_CODE_ENABLE_TELEMETRY": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
                "OTEL_LOGS_EXPORTER": "otlp", "OTEL_RESOURCE_ATTRIBUTES": "team=x,ccp.seat=wrong",
                "SOME_TOKEN": "secret", "ANTHROPIC_API_KEY": "k"}, "hooks": {"Stop": []}}))
            base = {k: v for k, v in os.environ.items() if not k.startswith(("OTEL_", "CLAUDE_CODE_", "ANTHROPIC_"))}
            with mock.patch.dict(os.environ, {**base, "CCP_USER_SETTINGS": str(d / "settings.json"),
                                              "OTEL_LOGS_EXPORTER": "console", "ANTHROPIC_API_KEY": "k"}, clear=True):
                env = estimator.child_env("demo")
            self.assertEqual(env["CLAUDE_CODE_ENABLE_TELEMETRY"], "1")
            self.assertEqual(env["OTEL_EXPORTER_OTLP_ENDPOINT"], "http://127.0.0.1:4318")
            self.assertEqual(env["OTEL_LOGS_EXPORTER"], "console")       # the shell's own value wins
            self.assertEqual(env["OTEL_RESOURCE_ATTRIBUTES"], "team=x,ccp.project_id=demo,ccp.seat=estimator")
            self.assertNotIn("SOME_TOKEN", env)                          # only telemetry keys are copied
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            with mock.patch.dict(os.environ, {"CCP_USER_SETTINGS": str(d / "missing.json")}):
                self.assertIn("ccp.seat=estimator", estimator.child_env("demo")["OTEL_RESOURCE_ATTRIBUTES"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Validate(unittest.TestCase):
    def test_a_good_answer_passes(self):
        self.assertEqual(estimator.validate(answer(), ["0001-sf-h"]), [])
        self.assertEqual(estimator.validate(answer(reference_tasks=["0001"]), ["0001-sf-h"]), [])

    def test_every_rule_is_checked(self):
        cases = {
            "above": answer(total={"p50_min": 90, "p90_min": 45}),
            "phases.verify is missing": answer(phases={k: v for k, v in answer()["phases"].items() if k != "verify"}),
            "must be positive": answer(phases={**answer()["phases"], "implement": {"p50_min": 0, "p90_min": 5}}),
            "must be numbers": answer(tokens={"p50": "2e7", "p90": 4e7}),
            "complexity.novelty.rating": answer(complexity={**answer()["complexity"], "novelty": {"rating": "huge", "reason": "x"}}),
            "reasoning must be": answer(reasoning="r" * 601),
            "at least one task of the reference class": answer(reference_tasks=["0099-other"]),
            "rounds.fix_risk": answer(rounds={"review_p50": 1, "fix_risk": 1.5}),
            "missing keys": {k: v for k, v in answer().items() if k != "cost_usd"},
            "waits must be": answer(waits="none"),
        }
        for msg, obj in cases.items():
            errs = estimator.validate(obj, ["0001-sf-h"])
            self.assertTrue(any(msg in e for e in errs), (msg, errs))
        self.assertTrue(estimator.validate(answer(total={"p50_min": True, "p90_min": 5}), []))  # a bool is not a number
        self.assertEqual(estimator.validate([1], []), ["the answer is not a JSON object"])
        self.assertEqual(estimator.validate(answer(phases={**answer()["phases"], "fix": {"p50_min": 0, "p90_min": 0}}), []), [])


class Seat(Base):
    def test_a_valid_answer_is_an_agent_row_of_the_estimate_shape(self):
        estimate.estimate_tasks(self.p.cfg, self.q, ["0005"])  # a baseline first
        self.answers = [result(answer())]
        r = self.run_(["0005"])
        self.assertEqual((r["written"], r["tasks"][0]["action"]), (1, "written"))
        row = estimate.latest(estimate.rows(self.q, "0005-sf-store"), "agent")
        self.assertEqual(row["total"], {"p50_s": 2700, "p90_s": 5400})
        self.assertEqual(row["phases"]["fix"], {"p50_s": 0, "p90_s": 1500})
        self.assertEqual(row["inputs"]["method"]["name"], "estimator-seat")
        self.assertEqual(row["inputs"]["reference_tasks"], ["0001-sf-h"])
        self.assertEqual(row["inputs"]["baseline"]["version"], 1)
        self.assertEqual((row["seat"]["attempts"], row["seat"]["cost_usd"]), (1, 0.05))
        self.assertEqual(row["complexity"]["novelty"]["rating"], "med")
        self.assertEqual(row["task_hash"], estimate.task_hash((self.p.root / "docs/delivery/tasks/0005-sf-store.md").read_text()))
        log = estimator.calls(self.q)
        self.assertEqual([x["outcome"] for x in log], ["ok"])
        # it is scored like any row: accuracy reads the agent source
        acc = estimate.accuracy(estimate.all_rows(self.q))
        self.assertIn("agent", acc["sources"])

    def test_an_invalid_answer_is_retried_once_with_its_errors(self):
        self.answers = [result(answer(total={"p50_min": 90, "p90_min": 45}), cost=0.04), result(answer(), cost=0.05)]
        r = self.run_(["0005"])
        self.assertEqual(r["tasks"][0]["action"], "written")
        self.assertEqual(len(self.calls), 2)
        self.assertIn("Your previous answer was rejected", self.calls[1])
        self.assertIn("p50_min 90 is above p90_min 45", self.calls[1])
        row = estimate.latest(estimate.rows(self.q, "0005-sf-store"), "agent")
        self.assertEqual((row["seat"]["attempts"], row["seat"]["cost_usd"]), (2, 0.09))
        self.assertEqual([x["outcome"] for x in estimator.calls(self.q)], ["invalid", "ok"])

    def test_a_second_failure_writes_no_row_and_the_baseline_stands(self):
        estimate.estimate_tasks(self.p.cfg, self.q, ["0005"])
        self.answers = [result(None, text="no json here"), result(answer(reasoning=""))]
        r = self.run_(["0005"])
        self.assertEqual((r["written"], r["failed"], r["tasks"][0]["action"]), (0, 1, "failed"))
        rs = estimate.rows(self.q, "0005-sf-store")
        self.assertIsNone(estimate.latest(rs, "agent"))
        self.assertIsNotNone(estimate.latest(rs, "baseline"))
        self.assertEqual(estimate.board_view(self.q)["tasks"]["0005-sf-store"]["baseline"]["source"], "baseline")
        self.assertEqual([x["outcome"] for x in estimator.calls(self.q)], ["invalid", "invalid"])
        self.assertTrue(list((self.q / "estimator").glob("*.failed.txt")))
        self.assertIsNone(estimator.running(self.q))  # the lock is released

    def test_a_call_that_fails_outright_is_not_retried(self):
        self.answers = [({}, "claude: command not found", 127)]
        r = self.run_(["0005"])
        self.assertEqual((r["tasks"][0]["action"], len(self.calls)), ("failed", 1))
        self.assertIn("claude exited 127", r["tasks"][0]["reason"])

    def test_a_dry_run_calls_nothing_and_writes_nothing(self):
        r = self.run_(None, dry_run=True)
        self.assertEqual({x["action"] for x in r["tasks"]}, {"would estimate"})
        self.assertEqual(self.calls, [])
        self.assertFalse((self.q / "estimates").exists())


class Triggers(Base):
    def test_hash_and_dependency_changes_make_an_estimate_stale(self):
        ids = lambda: {str(t.get("task_id")): why for t, why in estimator.stale(self.p.cfg, self.q)}  # noqa: E731
        self.assertEqual(ids(), {"0004-sf-dep": "no agent estimate yet", "0005-sf-store": "no agent estimate yet"})
        self.answers = [result(answer()), result(answer())]
        self.assertEqual(self.run_(None)["written"], 2)
        self.assertEqual(ids(), {})
        f = self.p.root / "docs/delivery/tasks/0005-sf-store.md"
        f.write_text(f.read_text().replace("SECRET-NOTE", "another note").replace("status: pending", "status: pending"))
        self.assertEqual(ids(), {})  # a note is not a change
        f.write_text(f.read_text().replace("Change `src", "Rework `src"))
        self.assertEqual(ids(), {"0005-sf-store": "the task changed"})
        self.answers = [result(answer())]
        self.run_(None)
        dep = self.p.root / "docs/delivery/tasks/0004-sf-dep.md"
        dep.write_text(dep.read_text().replace("status: pending", "status: done"))
        self.assertEqual(ids(), {"0005-sf-store": "a dependency merged since: 0004-sf-dep"})
        (self.q / "work.json").write_text(json.dumps({"in_flight": ["0005-sf-store"]}))
        self.assertEqual(ids(), {})  # in flight: an estimate now would never be scored
        self.answers = [result(answer())]  # named, it is estimated even in flight
        self.assertEqual(self.run_(["0005"])["tasks"][0]["action"], "written")
        self.assertEqual(self.run_(["0005"])["tasks"][0]["action"], "unchanged")

    def test_auto_is_off_by_default_and_says_nothing(self):
        self.assertIs(self.p.cfg.estimate["auto"], False)
        self.assertEqual(len(estimator.stale(self.p.cfg, self.q)), 2)  # tasks need an estimate all the same
        with mock.patch.object(estimator, "spawn") as sp:
            lines = estimator.notice(self.p.cfg, self.q)
        sp.assert_not_called()
        self.assertEqual(lines, [])

    def test_auto_on_names_the_tasks_that_need_an_estimate(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "estimate": {"auto": True}}))
        with mock.patch.object(estimator, "_linked_worktree", return_value=False):
            lines = estimator.notice(self.p.cfg, self.q)
        self.assertEqual(len(lines), 1)
        self.assertIn("estimates: 2 open task(s) without a current agent estimate (0004, 0005)", lines[0])
        self.assertIn("not started (CCP_NO_ESTIMATOR_SPAWN)", lines[0])

    def test_auto_on_starts_one_detached_batch_and_never_two(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "estimate": {"auto": True}}))
        env = {k: v for k, v in os.environ.items() if k != "CCP_NO_ESTIMATOR_SPAWN"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(estimator, "_linked_worktree", return_value=False), \
                mock.patch.object(estimator, "spawn", return_value={"run_id": "es-x", "log": "/l"}) as sp:
            lines = estimator.notice(self.p.cfg, self.q)
            sp.assert_called_once()
            self.assertIn("started the estimator in the background (es-x", lines[0])
            ok, _ = estimator.lock_take(self.q, "es-y", 600)
            self.assertTrue(ok)
            lines = estimator.notice(self.p.cfg, self.q)
            self.assertIn("already running", lines[0])
            self.assertEqual(sp.call_count, 1)
            estimator.lock_release(self.q, "es-y")
            with mock.patch.object(estimator, "_linked_worktree", return_value=True):
                self.assertIn("linked worktree", estimator.notice(self.p.cfg, self.q)[0])
            self.assertEqual(sp.call_count, 1)

    def test_tasks_check_prints_the_note_and_keeps_its_exit_code(self):
        from ccp import cli
        self.p.index()
        def check():
            o = io.StringIO()
            with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}), redirect_stdout(o), redirect_stderr(io.StringIO()):
                return cli.main(["--root", str(self.p.root), "tasks", "check"]), o.getvalue()
        off_code, out = check()
        self.assertNotIn("estimates:", out)  # estimate.auto is off by default: no note
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "estimate": {"auto": True}}))
        code, out = check()
        self.assertEqual(code, off_code)
        self.assertIn("note: estimates: 2 open task(s)", out)
        with mock.patch.object(estimator, "notice", return_value=[]):
            self.assertEqual(check()[0], code)  # the note never changes the exit code
        with mock.patch.object(estimator, "stale", side_effect=RuntimeError("boom")):
            code2, out = check()
        self.assertEqual(code2, code)
        self.assertIn("the estimator trigger failed (RuntimeError: boom)", out)

    def test_the_budget_cap_defers_the_rest(self):
        self.p.write("docs/delivery/tasks/0006-sf-more.md", body("0006-sf-more"))
        self.answers = [result(answer()), result(answer())]
        r = self.run_(None, max_n=2)
        self.assertEqual(r["written"], 2)
        self.assertEqual([x["action"] for x in r["tasks"]].count("deferred"), 1)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(r["cost_usd"], 0.1)

    def test_a_held_lock_stops_a_second_batch(self):
        ok, _ = estimator.lock_take(self.q, "es-held", 600)
        self.assertTrue(ok)
        r = self.run_(["0005"])
        self.assertEqual((r["ok"], r["outcome"]), (False, "locked"))
        self.assertEqual(self.calls, [])


class Cli(Base):
    def go(self, *a):
        from ccp import cli
        o, e = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)}), mock.patch.object(estimator, "call", self.fake), \
                redirect_stdout(o), redirect_stderr(e):
            c = cli.main(["--root", str(self.p.root), *a])
        return c, o.getvalue(), e.getvalue()

    def test_estimate_without_baseline_runs_the_seat(self):
        self.answers = [result(answer())]
        c, out, err = self.go("tasks", "estimate", "0005")
        self.assertEqual(c, 0, err)
        self.assertIn("agent  v1", out)
        self.assertIn("Close to 0001", out)
        c, out, _ = self.go("tasks", "estimate", "0005", "--print-prompt")
        self.assertEqual(c, 0)
        self.assertIn("## The reference class", out)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.go("tasks", "estimate", "--all", "--max", "0")[0], 2)
        self.answers = [({}, "boom", 1)]
        self.assertEqual(self.go("tasks", "estimate", "0004")[0], 1)


class SeatsAndBoard(Fixture, unittest.TestCase):
    view = te.Page.view
    render = te.Page.render

    def test_a_running_batch_is_a_headless_seat_with_its_pins(self):
        q = Path(tempfile.mkdtemp())
        try:
            ok, body_ = estimator.lock_take(q, "es-run", 600)
            estimator._lock_note(q, body_, "0005-sf-store")
            rows, claimed = seats._headless(q, "claude-team", {"runs": {}, "seats": {}}, 0)
            self.assertIn("estimator", claimed)
            row = [r for r in rows if r["seat"].startswith("estimator")][0]
            self.assertIn("0005-sf-store", row["seat"])
            self.assertEqual((row["expected"]["model"], row["expected"]["effort"]), ("claude-sonnet-5-5", "medium"))
            estimator.lock_release(q, "es-run")
            rows, _ = seats._headless(q, "claude-team", {"runs": {}, "seats": {}}, 0)
            self.assertFalse([r for r in rows if r["seat"].startswith("estimator")])
        finally:
            shutil.rmtree(q, ignore_errors=True)

    def test_the_queue_shows_agent_beside_baseline_and_the_card_shows_spend(self):
        from tests.test_board_quality import HOSTILE
        self.seed()
        b = self.build()[0]
        self.assertEqual(b["estimates"]["estimator"]["calls"], 0)
        v = self.view("0002-second")
        base = v["tasks"]["0002-second"]["baseline"]
        v["tasks"]["0002-second"]["agent"] = {**base, "source": "agent", "total": {"p50_s": 1800, "p90_s": 3600},
                                              "reasoning": "kept the baseline" + HOSTILE,
                                              "complexity": {"novelty": {"rating": "low" + HOSTILE}}}
        v["tasks"]["0002-second"]["agent_scored"] = v["tasks"]["0002-second"]["agent"]
        v["estimator"] = {"calls": 3, "estimates": 2, "failed": 1, "cost_usd": 0.15, "cost_usd_7d": 0.15,
                          "per_estimate_usd": 0.075, "pins": {"model": "claude-sonnet-5-5" + HOSTILE, "effort": "medium"}}
        b["estimates"] = v
        html = self.render(b, "\nout.push(estCell('0002-second')); out.push(estDrill('0002-second'));")
        self.assertIn("30m–1.0h", html)
        self.assertIn("· base", html)
        self.assertIn("10m–20m", html)
        self.assertIn("2 estimate(s) from 3 call(s), 1 failed", html)
        self.assertIn("Estimator: kept the baseline", html)
        self.assertNotIn(HOSTILE, html)
        for raw in ("<script", "<img"):
            self.assertNotIn(raw, html)

    def test_hostile_agent_text_renders_as_text(self):
        bad = ('<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '</script><script>alert(2)//', '<!--')
        self.seed()
        b = self.build()[0]
        v = self.view("0002-second")
        base = v["tasks"]["0002-second"]["baseline"]
        agent = {**base, "source": "agent", "total": {"p50_s": 1800, "p90_s": 3600},
                 "reasoning": " ".join(bad), "waits": list(bad), "refs": list(bad), "tier": bad[1], "model": bad[2],
                 "complexity": {k + bad[i % 4]: {"rating": bad[(i + 1) % 4], "reason": bad[(i + 2) % 4]}
                                for i, (k, _, _) in enumerate(estimator.CRITERIA)}}
        v["tasks"]["0002-second"].update(agent=agent, agent_scored=agent)
        b["estimates"] = v
        html = self.render(b, "\nout.push(estCell('0002-second')); out.push(estDrill('0002-second'));")
        self.assertIn("Estimator: &lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html)
        self.assertIn("&lt;!--", html)
        self.assertIn('title="&lt;/script&gt;&lt;script&gt;alert(2)//"', html)  # a per-criterion reason, as text
        self.assertIn("<b>&lt;img src=x onerror=alert(1)&gt;</b>", html)          # a rating, as text
        for raw in bad + ("<img", "onerror=alert(1)>"):
            self.assertNotIn(raw, html)

    def test_spend_sums_the_calls(self):
        q = Path(tempfile.mkdtemp())
        try:
            for i, (o, c) in enumerate((("invalid", 0.04), ("ok", 0.05), ("invalid", 0.03), ("invalid", 0.03))):
                estimator._log(q, {"at": estimate.iso(), "run_id": "es-1", "task_id": "000" + ("1" if i < 2 else "2"),
                                   "attempt": 1, "outcome": o, "cost_usd": c})
            s = estimator.spend(q)
            self.assertEqual((s["calls"], s["estimates"], s["failed"], s["cost_usd"]), (4, 1, 1, 0.15))
        finally:
            shutil.rmtree(q, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
