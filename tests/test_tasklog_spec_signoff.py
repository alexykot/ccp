"""ccp tasks check (SPEC §3.5): a task whose `paths` name the SPEC carries a `brief` sign-off, or says
`§31.1` in its Scope; otherwise it is warned about, never refused."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from ccp import cli, config, tasklog
from tests.helpers import Product


class SpecEditsAreSignedAtTasking(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def task(self, tid: str, extra: str = "", scope: str = "- **In:** it", status: str = "pending",
             paths: str = '["docs/spec/01-model.md"]'):
        f = self.p.task(tid, status)
        f.write_text(f.read_text().replace('spec_refs: ["S1"]\n', f'spec_refs: ["S1"]\npaths: {paths}\n{extra}')
                     .replace("- **In:** it", scope))
        return f

    def check(self) -> tuple[int, list[str]]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        return code, [line for line in out.getvalue().splitlines() if line.startswith("  warning:")]

    def three(self):
        self.task("0001-a")
        self.task("0002-b", "sign_off: brief\n")
        self.task("0003-c", scope="- **In:** the SPEC text only describes this feature (§31.1)")
        self.p.index()

    def test_only_the_task_with_neither_sign_off_nor_31_1_is_warned_about(self):
        self.three()
        code, ws = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(ws), 1, ws)
        self.assertIn("docs/delivery/tasks/0001-a.md: its paths name the SPEC (docs/spec/01-model.md)", ws[0])

    def test_spec_paths_says_where_the_spec_is(self):
        self.three()
        plane = json.loads((self.p.root / "docs/delivery/plane.json").read_text())
        self.p.write("docs/delivery/plane.json", json.dumps({**plane, "task_log": {"spec_paths": ["spec/"]}}))
        code, ws = self.check()
        self.assertEqual((code, ws), (0, []))

    def test_a_brief_sign_off_among_stages_holds_and_a_build_one_alone_does_not(self):
        self.task("0001-a", "sign_off: [brief, build]\n")
        self.task("0002-b", "sign_off: build\n")
        ws = tasklog.warnings(self.p.cfg)
        self.assertEqual([w.split(":")[0] for w in ws], ["docs/delivery/tasks/0002-b.md"])

    def test_31_1_outside_scope_does_not_count(self):
        f = self.task("0001-a")
        f.write_text(f.read_text().replace("- background", "- only describes its feature (§31.1)"))
        self.assertEqual(len(tasklog.warnings(self.p.cfg)), 1)

    def test_a_done_or_dropped_task_is_not_warned_about(self):
        self.task("0001-a", status="done")
        self.task("0002-b", status="dropped")
        self.assertEqual(tasklog.warnings(self.p.cfg), [])

    def test_the_default_spec_paths_match_a_file_or_a_directory_entry_not_a_lookalike(self):
        self.task("0001-a", paths='["SPEC.md"]')
        self.task("0002-b", paths='["docs/spec/*.md"]')
        self.task("0003-c", paths='["SPEC.md.bak", "docs/specs/x.md", "docs/spec"]')
        self.task("0004-d", paths='["./docs/spec/02-delivery.md"]')
        ws = tasklog.warnings(self.p.cfg)
        self.assertEqual([w.split(":")[0] for w in ws],
                         ["docs/delivery/tasks/0001-a.md", "docs/delivery/tasks/0002-b.md",
                          "docs/delivery/tasks/0004-d.md"])

    def test_the_default_names_what_init_writes_and_the_estimators_spec_dirs(self):
        self.task("0001-a", paths='["docs/SPEC.md"]')
        self.task("0002-b", paths='["spec/a.md"]')
        self.task("0003-c", paths='["docs/other.md"]')
        self.p.index()
        code, ws = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(ws), 2, ws)
        self.assertIn("docs/delivery/tasks/0001-a.md: its paths name the SPEC (docs/SPEC.md)", ws[0])
        self.assertIn("docs/delivery/tasks/0002-b.md: its paths name the SPEC (spec/a.md)", ws[1])

    def test_the_schema_gives_the_default_the_code_applies(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())
        knob = schema["properties"]["task_log"]["properties"]["spec_paths"]
        self.assertEqual(knob["default"], config.TASK_LOG_DEFAULTS["spec_paths"])

    def test_an_entry_without_a_slash_meets_only_the_path_it_equals(self):
        self.p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "task_log": {"spec_paths": ["rules"]}}))
        self.task("0001-a", paths='["rules"]')
        self.task("0002-b", paths='["rules/one.md"]')
        self.task("0003-c", paths='["rulesets/one.md"]')
        self.p.index()
        code, ws = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(len(ws), 1, ws)
        self.assertIn("docs/delivery/tasks/0001-a.md: its paths name the SPEC (rules)", ws[0])

    def test_spec_paths_must_be_relative_paths(self):
        for bad in ("docs/spec/", ["/abs/spec"], ["../spec"], [""], [3]):
            with self.subTest(bad=bad):
                self.p.write("docs/delivery/plane.json",
                             json.dumps({"project_id": "demo", "task_log": {"spec_paths": bad}}))
                with self.assertRaises(config.ConfigError) as cm:
                    config.load(self.p.root)
                self.assertIn("task_log.spec_paths", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
