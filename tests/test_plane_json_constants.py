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

from ccp import architect, config, prompt, tasklog, usage
from tests.helpers import Product
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
        self.assertEqual((cfg.gate["shell_limit_seconds"], cfg.docs["workers"], cfg.architect["max_days"]), (600, 1, 14))
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
        cfg, err = load({"docs": {"workers": 1}, "review_points": {"file": "docs/delivery/review-points.yaml"}})
        self.assertEqual(cfg.docs["workers"], 1)
        self.assertIn("docs.workers is a constant in code (1) and is set to that value: delete it", err)
        self.assertIn("review_points.file is a constant in code", err)

    def test_an_invalid_value_is_still_refused(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
            load({"architect": {"max_days": 0, "shape_from_task": "0001"}})
        self.assertIn("max_days", str(cm.exception))


class TheUpgradeStatus(UpgradeFixture, unittest.TestCase):
    def test_a_constant_set_to_another_value_is_listed_and_one_set_to_the_constant_is_not(self):
        self.product_json(language="none", gate={"shell_limit_seconds": 99}, docs={"workers": 1},
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


if __name__ == "__main__":
    unittest.main()
