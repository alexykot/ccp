"""ADR-0043 D9, SPEC §29.3: the tuning keys a product would not change are constants in code (a value a product
still sets applies, with a warning, until it deletes the key), and four defaults changed so a product works
without setting them: estimates start by themselves, ADRs are shaped from the adoption point, the product's
`docs/delivery/WORKERS.md` is the prompt fragment, and the lead's expected model follows `models.lead`."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

from ccp import architect, board, config, drill, estimate, forecast, health, init, prompt, tasklog, usage, wt
from tests.helpers import Product
from tests.test_board_seats import Base, req
from tests.test_toolkit import ToolkitFixture
from tests.test_upgrade import UpgradeFixture
from tests.test_usage_advice import row

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())

# Every key that became a constant, by block: the keys a product would not change.
CONSTANTS = {
    "task_log": ("dir", "required", "refs_any", "sections", "kinds", "reviews_dir", "max_checks", "soft_words",
                 "index", "dry_run"),
    "package_docs": ("doc_name", "size_ratio", "banned_headings", "path_ref_suffixes", "no_delivery_ids"),
    "docs": ("workers",),
    "architect": ("rules_max_lines", "max_days", "notes_due", "drift_ratio", "grace_tasks", "triage_grace_tasks",
                  "refactor_in_scope", "call_timeout_minutes", "max_new_tasks"),
    "prompts": ("keep_body", "audit_keep_days"),
    "worktrees": ("dir",),
    "env": ("timeout_seconds",),
    "auth_check": ("timeout_seconds",),
    "board": ("refresh_minutes",),
    "gate": ("shell_limit_seconds", "cut_line_seconds"),
    "health": ("small_task_lines", "slowest_modules", "suite_trend_runs"),
    "usage.advice": ("cache_5m_share", "context_tokens", "coordination_share", "window_hours"),
    "workers": ("small_estimate_minutes",),
    "suite.summary": ("ran_re", "cached_re", "cached_tests_re", "tail_lines", "max_chars"),
    "suite": ("log_keep_days", "roles"),
    "adr": ("statuses", "transitions"),
    "review_points": ("file",),
    "estimate": ("k", "path_suffixes", "calibration"),
    "mutate": ("timeout_seconds",),
    "notify": ("timeout_seconds",),
    "telemetry": ("design_seat",),
}
# The default each of these keys had before it became a constant (read from the code at the merge base): a constant
# moves the value into code and must not change it.
WAS = {
    "task_log.dir": "docs/delivery",
    "task_log.required": ["task_id", "title", "status", "depends_on", "spec_refs", "created", "updated"],
    "task_log.refs_any": ["spec_refs"],
    "task_log.sections": ["Intent", "Context (not checked)", "Scope", "dod_checks", "Implementation notes",
                          "Verification notes"],
    "task_log.kinds": {"feature": {}, "refactor": {"refs_any": ["rule_refs", "review_refs"],
                                                   "forbid": ["spec_refs", "adr_refs"]}},
    "task_log.reviews_dir": "reviews", "task_log.max_checks": 6,
    "task_log.soft_words": ["should", "may", "might", "as appropriate", "gracefully", "robust", "robustly"],
    "task_log.index": True, "task_log.dry_run": False,
    "package_docs.doc_name": ".claude.md", "package_docs.size_ratio": 0.5,
    "package_docs.banned_headings": ["future", "planned", "next steps", "roadmap", "todo"],
    "package_docs.path_ref_suffixes": [".py", ".sql", ".json", ".md", ".sh"], "package_docs.no_delivery_ids": True,
    "docs.workers": None,  # was 1: ADR-0043 D9 names this constant, as many workers as there are checks
    "architect.rules_max_lines": 150, "architect.max_days": 14, "architect.notes_due": 3,
    "architect.drift_ratio": 1.5, "architect.grace_tasks": 1, "architect.triage_grace_tasks": 2,
    "architect.refactor_in_scope": "deps", "architect.call_timeout_minutes": 45, "architect.max_new_tasks": 5,
    "prompts.keep_body": False, "prompts.audit_keep_days": None,
    "worktrees.dir": ".plane-runtime",  # was null: ADR-0043 D9 names this default, and init wrote it
    "env.timeout_seconds": 600, "auth_check.timeout_seconds": 60, "board.refresh_minutes": 5,
    "gate.shell_limit_seconds": 600, "gate.cut_line_seconds": None,
    "health.small_task_lines": 100, "health.slowest_modules": 5, "health.suite_trend_runs": 10,
    "usage.advice.cache_5m_share": 0.5, "usage.advice.context_tokens": 300000,
    "usage.advice.coordination_share": 0.4, "usage.advice.window_hours": 0,
    "workers.small_estimate_minutes": 30,
    "suite.summary.ran_re": [], "suite.summary.cached_re": [], "suite.summary.cached_tests_re": [],
    "suite.summary.tail_lines": 40, "suite.summary.max_chars": 40000,
    "suite.log_keep_days": 14, "suite.roles": {"full": "full", "gate": "gate", "part": "part"},
    "adr.statuses": ["proposed", "accepted", "in-progress", "implemented", "rejected", "superseded", "withdrawn",
                     "retired"],
    "adr.transitions": {"proposed": ["accepted", "rejected", "withdrawn"], "accepted": ["superseded", "retired"],
                        "in-progress": ["accepted", "superseded", "retired"],
                        "implemented": ["superseded", "retired"]},
    "review_points.file": "docs/delivery/review-points.yaml",
    "estimate.k": 6, "estimate.path_suffixes": None, "estimate.calibration": {"half_life": 40, "min_pairs": 8, "k": None},
    "mutate.timeout_seconds": 600, "notify.timeout_seconds": 30,
    "telemetry.design_seat": None,  # the lead's expected model is `models.lead` now (`config.design_seat`)
}
KEPT = (("adr", "strict"), ("verify", "skip_review_after_clean"), ("estimate", "auto"), ("architect", "shape_adrs"),
        ("prompts", "fragment"), ("suite", "lanes"))


def load(plane: dict[str, Any], files: dict[str, str] | None = None) -> tuple[config.Config, str]:
    """The config of a temp product whose plane.json is `plane`, and what loading it wrote to stderr."""
    p = Product({"project_id": "demo", "language": "none", **plane}, bare=True)
    try:
        for rel, text in (files or {}).items():
            p.write(rel, text)
        err = io.StringIO()
        with redirect_stderr(err):
            config._WARNED.clear()
            return config.load(p.root), err.getvalue()
    finally:
        p.cleanup()


def schema_prop(key: str) -> dict[str, Any]:
    node: Any = {"properties": SCHEMA["properties"]}
    for part in key.split("."):
        node = node["properties"][part]
    return node


class TheConstants(unittest.TestCase):
    def keys(self):
        return [f"{block}.{key}" for block, ks in CONSTANTS.items() for key in ks]

    def test_each_key_is_a_constant_in_the_registry_and_deprecated_in_the_schema(self):
        for key in self.keys():
            with self.subTest(key=key):
                self.assertEqual(config.KEY_OUTCOMES[key].kind, config.CONSTANT)
                prop = schema_prop(key)
                self.assertIs(prop.get("deprecated"), True)
                self.assertTrue(prop["description"].startswith("Constant"), prop["description"])

    def test_no_other_key_is_a_constant_but_the_account_knobs(self):
        account = {"telemetry.session_park_pct", "telemetry.session_wake_arm_pct", "telemetry.session_wake_margin_s",
                   "telemetry.windows", "parallel.session_ceiling_pct"}
        got = {k for k, o in config.KEY_OUTCOMES.items() if o.kind == config.CONSTANT}
        self.assertEqual(got - account, set(self.keys()))

    def test_the_settings_a_product_keeps_are_no_constants(self):
        for block, key in KEPT:
            with self.subTest(key=f"{block}.{key}"):
                self.assertNotIn(f"{block}.{key}", config.KEY_OUTCOMES)
                self.assertIsNot(schema_prop(f"{block}.{key}").get("deprecated"), True)

    def test_a_constant_is_the_default_the_key_had(self):
        self.assertEqual(set(WAS), set(self.keys()))
        for key, was in WAS.items():
            with self.subTest(key=key):
                self.assertEqual(config.KEY_OUTCOMES[key].value, was)
        for key in self.keys():
            o = config.KEY_OUTCOMES[key]
            *path, name = key.split(".")
            node: Any = config.BLOCK_DEFAULTS
            for part in path:
                node = config.SUITE_SUMMARY_DEFAULTS if part == "summary" else node[part]
            with self.subTest(key=key):
                self.assertEqual(o.value, node[name])

    def test_unset_a_product_hears_nothing_and_the_blocks_hold_the_constants(self):
        cfg, err = load({})
        self.assertEqual((err, cfg.key_notes), ("", ()))
        self.assertEqual((cfg.gate["shell_limit_seconds"], cfg.docs["workers"], cfg.architect["max_days"]),
                         (600, None, 14))
        self.assertEqual(cfg.task_log["dir"], "docs/delivery")

    def test_a_value_other_than_the_constant_applies_with_one_warning_naming_the_key_and_the_constant(self):
        cfg, err = load({"gate": {"shell_limit_seconds": 99}})
        self.assertEqual(cfg.gate["shell_limit_seconds"], 99)
        self.assertEqual(err.count("gate.shell_limit_seconds"), 1, err)
        self.assertIn("is a constant in code (600)", err)
        self.assertIn("the value 99 set here still applies", err)

    def test_a_nested_constant_applies_with_a_warning_too(self):
        cfg, err = load({"usage": {"advice": {"window_hours": 6}}, "suite": {"summary": {"tail_lines": 5},
                                                                             "roles": {"gate": "g"}}})
        self.assertEqual((cfg.usage["advice"]["window_hours"], cfg.suite["summary"]["tail_lines"]), (6, 5))
        self.assertEqual(cfg.suite["roles"]["gate"], "g")
        for key in ("usage.advice.window_hours", "suite.summary.tail_lines", "suite.roles"):
            self.assertIn(f"{key} is a constant in code", err)

    def test_a_value_equal_to_the_constant_warns_that_the_key_can_go(self):
        cfg, err = load({"architect": {"max_days": 14},
                         "review_points": {"file": "docs/delivery/review-points.yaml"}})
        self.assertEqual(cfg.architect["max_days"], 14)
        self.assertIn("architect.max_days is a constant in code (14) and is set to that value: delete it", err)
        self.assertIn("review_points.file is a constant in code", err)

    def test_an_invalid_value_is_still_refused(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
            load({"architect": {"max_days": 0, "shape_from_task": "0001"}})
        self.assertIn("max_days", str(cm.exception))


class TheUpgradeStatus(UpgradeFixture, unittest.TestCase):
    def test_a_constant_set_to_another_value_is_listed_and_one_set_to_the_constant_is_not(self):
        self.product_json(language="none", gate={"shell_limit_seconds": 99}, architect={"max_days": 14},
                          telemetry={"design_seat": {"model": "sonnet"}})
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        step = next(s for s in body["steps"] if s["task"] == "plane.json keys")
        listed = {k["key"]: k for k in step["keys"]}
        self.assertEqual(set(listed), {"gate.shell_limit_seconds", "telemetry.design_seat"})
        self.assertEqual((listed["gate.shell_limit_seconds"]["constant"], listed["gate.shell_limit_seconds"]["set"]),
                         (600, 99))
        self.assertEqual(listed["gate.shell_limit_seconds"]["outcome"], "constant")
        self.assertIn("delete `gate.shell_limit_seconds`", step["change"])


    def test_a_constant_in_words_is_named_in_words(self):
        self.product_json(language="none", docs={"workers": 2})
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        step = next(s for s in body["steps"] if s["task"] == "plane.json keys")
        self.assertIn(f"delete `docs.workers`: it is a constant, {config.KEY_OUTCOMES['docs.workers'].shown}, and "
                      "yours is 2;", step["change"])
        self.assertNotIn("constant, None", step["change"])


class TheNewDefaults(unittest.TestCase):
    ADR = {"adr": {}}

    def test_the_four_defaults_hold_for_a_product_that_sets_none_of_them(self):
        cfg, err = load({**self.ADR, "models": {"lead": "opus"}}, {"docs/delivery/WORKERS.md": "rules\n"})
        self.assertEqual(err, "")
        self.assertEqual((cfg.estimate["auto"], cfg.prompts["fragment"], cfg.architect["shape_adrs"],
                          config.design_seat(cfg)["model"]),
                         (True, "docs/delivery/WORKERS.md", True, "opus"))

    def test_estimates_start_by_themselves_and_a_product_may_turn_that_off(self):
        self.assertIs(load({})[0].estimate["auto"], True)
        self.assertIs(load({"estimate": {"auto": False}})[0].estimate["auto"], False)
        self.assertIs(config.ESTIMATE_DEFAULTS["auto"], True)
        self.assertIs(schema_prop("estimate.auto")["default"], True)

    def test_adrs_are_shaped_whenever_the_product_has_an_adr_block(self):
        self.assertIs(load(self.ADR)[0].architect["shape_adrs"], True)
        self.assertIs(load({"adr": {"dir": "docs/adr"}, "architect": {"shape_from_task": "0001"}})[0]
                      .architect["shape_adrs"], True)
        self.assertIs(load({})[0].architect["shape_adrs"], False)

    def test_a_product_that_sets_shape_adrs_keeps_its_value(self):
        self.assertIs(load({**self.ADR, "architect": {"shape_adrs": False}})[0].architect["shape_adrs"], False)
        self.assertIs(load({"architect": {"shape_adrs": True}})[0].architect["shape_adrs"], True)

    def test_shape_adrs_with_no_adoption_point_loads_and_does_not_shape(self):
        for plane in (self.ADR, {**self.ADR, "architect": {"shape_adrs": True}}):
            with self.subTest(plane=plane):
                p = Product({"project_id": "demo", "language": "none", "suite": {"lanes": {"gate": ["true"]}}, **plane},
                            bare=True)
                self.addCleanup(p.cleanup)
                p.write("docs/delivery/tasks/0001-a.md", p.task("0001-a").read_text().replace(
                    'spec_refs: ["S1"]', 'spec_refs: ["S1"]\nadr_refs: ["0001 D1"]'))
                cfg = p.cfg
                self.assertIs(cfg.architect["shape_adrs"], True)
                self.assertIsNone(config.adoption_point(cfg))
                self.assertEqual(architect.shape_due(cfg, tasklog.load(cfg)), [])
                self.assertEqual([e for e in tasklog.check(cfg) if "shaping" in e], [])

    def test_from_the_adoption_point_an_unshaped_adr_is_still_refused(self):
        p = Product({"project_id": "demo", "language": "none", "adr": {}, "architect": {"shape_from_task": "0001"}},
                    bare=True)
        self.addCleanup(p.cleanup)
        p.write("docs/delivery/tasks/0001-a.md", p.task("0001-a").read_text().replace(
            'spec_refs: ["S1"]', 'spec_refs: ["S1"]\nadr_refs: ["0001 D1"]'))
        errs = tasklog.check(p.cfg)
        self.assertTrue(any("has no shaping record" in e for e in errs), errs)

    def test_the_products_workers_file_is_the_fragment_when_it_exists(self):
        p = Product({"project_id": "demo", "language": "none"}, bare=True)
        self.addCleanup(p.cleanup)
        p.write("docs/delivery/WORKERS.md", "the rules\n")
        self.assertEqual(p.cfg.prompts["fragment"], "docs/delivery/WORKERS.md")
        self.assertEqual(prompt.fragment(p.cfg), ("docs/delivery/WORKERS.md", "the rules"))
        self.assertIsNone(load({})[0].prompts["fragment"])
        self.assertEqual(prompt.fragment(load({})[0]), ("", ""))

    def test_a_fragment_the_product_names_wins_over_the_workers_file(self):
        cfg, _ = load({"prompts": {"fragment": "docs/RULES.md"}}, {"docs/delivery/WORKERS.md": "w\n"})
        self.assertEqual(cfg.prompts["fragment"], "docs/RULES.md")

    def test_the_leads_expected_model_follows_models_lead(self):
        for lead, want in ((None, "opus"), ("sonnet", "sonnet"), ("fable", "fable")):
            with self.subTest(lead=lead):
                cfg, _ = load({"models": {"lead": lead}} if lead else {})
                self.assertEqual(config.design_seat(cfg), {"model": want, "effort": None})

    def test_a_design_seat_the_product_still_sets_applies_with_a_warning(self):
        cfg, err = load({"telemetry": {"design_seat": {"model": "sonnet", "effort": "high"}},
                         "models": {"lead": "opus"}})
        self.assertEqual(config.design_seat(cfg), {"model": "sonnet", "effort": "high"})
        self.assertIn("telemetry.design_seat is a constant in code", err)

    def test_the_advice_compares_the_lead_with_models_lead(self):
        with tempfile.TemporaryDirectory() as d:
            q = Path(d)
            (q / "board").mkdir()
            req, span = row("l1", "lead", model="claude-opus-5-5")
            (q / "board" / "usage-requests.jsonl").write_text(json.dumps(req) + "\n")
            (q / "board" / "usage-spans.jsonl").write_text(json.dumps(span) + "\n")
            for lead, ran_on_it in (("opus", True), ("sonnet", False)):
                with self.subTest(lead=lead):
                    cfg, _ = load({"models": {"lead": lead}})
                    advice = usage.fold(q, None, config.design_seat(cfg))["advice"]
                    self.assertEqual(any("the design seat ran on" in x for x in advice), not ran_on_it, advice)


class TheWorktreesDirectory(unittest.TestCase):
    """`worktrees.dir` is a constant at `.plane-runtime` (ADR-0043 D9): a product that names nothing has its
    worktrees there, and `ccp init` writes no key for it."""

    def product(self, **plane):
        p = Product({"project_id": "demo", "language": "none", **plane}, bare=True)
        self.addCleanup(p.cleanup)
        return p

    def test_unset_the_worktrees_go_under_the_constant_with_no_warning(self):
        cfg, err = load({})
        self.assertEqual((cfg.worktrees["dir"], err), (".plane-runtime", ""))
        cfg = self.product().cfg
        self.assertEqual(wt.base_dir(cfg), (cfg.root / ".plane-runtime").resolve())

    def test_a_product_that_still_sets_the_constant_value_loads_with_no_warning(self):
        cfg, err = load({"worktrees": {"dir": ".plane-runtime"}})
        self.assertEqual((cfg.worktrees["dir"], err), (".plane-runtime", ""))
        self.assertEqual(config.key_outcomes_set({"worktrees": {"dir": ".plane-runtime"}}), [])
        cfg, err = load({"worktrees": {"dir": ".other"}})
        self.assertEqual(cfg.worktrees["dir"], ".other")
        self.assertIn("worktrees.dir is a constant in code ('.plane-runtime'); the value '.other' set here still applies", err)

    def test_only_that_key_is_quiet_at_its_own_value(self):
        self.assertEqual([k for k, o in config.KEY_OUTCOMES.items() if o.quiet_equal], ["worktrees.dir"])

    def test_a_different_value_applies_with_a_warning_and_null_is_no_worktrees(self):
        cfg, err = load({"worktrees": {"dir": "../trees"}})
        self.assertEqual(cfg.worktrees["dir"], "../trees")
        self.assertIn("worktrees.dir is a constant in code ('.plane-runtime'); the value '../trees' set here still applies", err)
        cfg, err = load({"worktrees": {"dir": None}})
        self.assertIsNone(cfg.worktrees["dir"])
        self.assertIn("worktrees.dir is a constant in code", err)
        self.assertIsNone(wt.base_dir(self.product(worktrees={"dir": None}).cfg))

    def test_init_writes_no_key_for_it_and_ignores_the_constants_directory(self):
        self.assertNotIn("worktrees", json.loads(init.plane_json_text("demo", "scripts/gate.sh", True, "python", "0001")))
        self.assertEqual(init.WORKTREES_DIR, config.WORKTREES_DIR)
        self.assertEqual(config.WORKTREES_DIR, ".plane-runtime")
        self.assertEqual(schema_prop("worktrees.dir")["default"], ".plane-runtime")


class TheLeadsExpectedModelReaders(Base, ToolkitFixture, unittest.TestCase):
    """A product with no `telemetry.design_seat` and `models.lead` on an alias other than the default, whose lead ran
    on opus: each reader of the lead's expected model reads `models.lead` (`config.design_seat`)."""

    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "models": {"lead": "sonnet"}}

    def setUp(self):
        super().setUp()
        self.requests(req("r1", 1, "claude-opus-5-5", "high"), spans=[{"request_id": "r1"}])

    def spy(self, *call):
        """What each `usage.fold` the call makes was given as the design seat."""
        with mock.patch.object(usage, "fold", wraps=usage.fold) as fold:
            call[0](*call[1:])
        self.assertTrue(fold.call_args_list)
        return [c.args[2] for c in fold.call_args_list]

    def test_the_seats_row_expects_models_lead_and_says_where_from(self):
        self.assertIsNone(config.load(self.main).telemetry["design_seat"])
        lead = self.rows(self.build())["design seat"]
        self.assertEqual(lead["expected"]["model"], "sonnet")
        self.assertEqual(lead["expected"]["source"], "docs/delivery/plane.json models.lead (advisory, §24.5)")
        self.assertEqual(lead["observed"]["model"], "claude-opus-5-5")
        self.assertTrue(any(m.startswith("model ") for m in lead["mismatch"]), lead["mismatch"])

    def test_the_board_advises_that_the_operator_expects_models_lead(self):
        advice = self.build()["usage"]["advice"]
        self.assertTrue(any("the design seat ran on claude-opus-5-5; the operator expects sonnet" in x for x in advice),
                        advice)

    def test_ccp_usage_advises_that_the_operator_expects_models_lead(self):
        code, body, out, err = self.ccp("usage", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(any("the design seat ran on claude-opus-5-5; the operator expects sonnet" in x
                            for x in body["advice"]), body["advice"])

    def test_the_task_view_the_estimator_and_the_forecast_fold_the_usage_against_models_lead(self):
        cfg = config.load(self.main)
        want = {"model": "sonnet", "effort": None}
        self.assertEqual(self.spy(board.task_text, cfg, self.q, "0001"), [want])
        with mock.patch.object(health, "collect", return_value={"tasks": [{"task_id": "0001-first"}]}), \
                mock.patch.object(drill, "collect", return_value={}):  # a merged task to fold the usage for
            self.assertEqual(self.spy(estimate._live, cfg, self.q), [want])
        self.assertEqual(self.spy(forecast.run, cfg, self.q), [want])


if __name__ == "__main__":
    unittest.main()
