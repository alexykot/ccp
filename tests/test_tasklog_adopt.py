"""SPEC §5.2, ADR-0041 D1: a task's `adopt` key, one step or `none` (the default when missing), and the
warning on a task that adds a knob a product sets and names no step."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from ccp import cli, tasklog
from tests.helpers import PLANE_ROOT, Product, TASK


def text(tid: str, status: str = "pending", extra: str = "") -> str:
    ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
    body = TASK.format(tid=tid, title="A task", status=status, deps="", ver=ver)
    return body.replace(f"status: {status}", f"status: {status}\n{extra}", 1) if extra else body


class Adopt(unittest.TestCase):
    def setUp(self):
        self.p = Product()

    def tearDown(self):
        self.p.cleanup()

    def task(self, tid: str, status: str = "pending", extra: str = "") -> None:
        self.p.write(f"docs/delivery/tasks/{tid}.md", text(tid, status, extra))

    def warns(self) -> list[str]:
        return [w for w in tasklog.warnings(self.p.cfg) if "adopt" in w]

    def test_the_step_is_read_and_a_missing_key_reads_as_none(self):
        self.task("0001-a", extra='adopt: "plane.json verify.accept_cache"')
        self.task("0002-b")
        steps = {t["task_id"]: tasklog.adopt_step(t) for t in tasklog.load(self.p.cfg)}
        self.assertEqual(steps, {"0001-a": "plane.json verify.accept_cache", "0002-b": "none"})

    def test_a_list_or_an_empty_value_is_refused(self):
        self.task("0001-a", extra="adopt: [a, b]")
        self.task("0002-b", extra="adopt:")
        self.task("0003-c", extra="adopt: none")
        self.p.index()
        errs = "\n".join(tasklog.check(self.p.cfg))
        self.assertIn("0001-a.md: adopt", errs)
        self.assertIn("0002-b.md: adopt", errs)
        self.assertNotIn("0003-c", errs)

    def test_tasks_check_warns_once_on_a_pending_knob_task_with_no_adopt_and_exits_0(self):
        self.task("0001-knob", extra='paths: ["contracts/plane_config.schema.json", "ccp/x.py"]')
        self.p.index()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        lines = [x for x in (out.getvalue() + err.getvalue()).splitlines() if "adopt" in x]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("0001-knob", lines[0])
        self.assertIn("`adopt:`", lines[0])

    def test_no_warning_with_a_step_on_a_done_task_or_without_a_knob_path(self):
        self.task("0001-a", extra='paths: ["contracts/plane_config.schema.json"]\nadopt: none')
        self.task("0002-b", "done", extra='paths: ["contracts/plane_config.schema.json"]')
        self.task("0003-c", "dropped", extra='paths: ["templates/claude-settings.json"]')
        self.task("0004-d", extra='paths: ["contracts/task_file.schema.json", "templates/prompts/x.md"]')
        self.assertEqual(self.warns(), [])

    def test_a_settings_template_or_a_glob_over_the_schema_warns(self):
        self.task("0001-a", extra='paths: ["templates/claude/settings.json"]')
        self.task("0002-b", extra='paths: ["contracts/*.json"]')
        warned = "\n".join(self.warns())
        self.assertIn("0001-a.md", warned)
        self.assertIn("0002-b.md", warned)

    def test_tasks_check_warns_once_on_a_none_value_that_names_a_plane_json_key_and_exits_0(self):
        self.task("0001-hidden", extra='adopt: "none: off by default; plane.json verify.accept_cache turns it on"')
        self.task("0002-quiet", extra='adopt: "none: the advice appears by itself"')
        self.p.index()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        lines = [x for x in (out.getvalue() + err.getvalue()).splitlines() if "adopt" in x]
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("0001-hidden", lines[0])
        self.assertIn("verify.accept_cache", lines[0])

    def test_a_none_value_naming_a_binding_or_settings_key_warns_on_a_done_task_too(self):
        self.task("0001-a", "done", extra='adopt: "none: binding runner.rotate_at_context_tokens turns it on"')
        self.task("0002-b", extra='adopt: "none; set subagentPromptCacheTtl by hand"')
        self.task("0003-c", extra='adopt: "none: binding lead.auto_compact_window"')
        warned = self.warns()
        self.assertEqual(len(warned), 3, warned)
        self.assertIn("runner.rotate_at_context_tokens", warned[0])
        self.assertIn("subagentPromptCacheTtl", warned[1])
        self.assertIn("lead.auto_compact_window", warned[2])

    def test_no_hidden_step_warning_for_a_step_a_path_a_dropped_task_or_an_undotted_block_name(self):
        self.task("0001-a", extra='adopt: "plane.json verify.accept_cache true"')
        self.task("0002-b", extra='adopt: "none: see ccp/upgrade.py and docs/delivery/plane.json"')
        self.task("0003-c", "dropped", extra='adopt: "none: plane.json verify.accept_cache"')
        self.task("0004-d", extra='adopt: "none: the verify step and the runner change by themselves"')
        self.assertEqual(self.warns(), [])

    def test_asks_nothing_reads_the_first_word(self):
        for step, nothing in (("none", True), ("None: it applies by itself", True), ("none; later", True),
                              ("plane.json none", False), ("nonetheless set x", False), ("", False)):
            self.assertEqual(tasklog.asks_nothing(step), nothing, step)

    def test_a_required_prefix_marks_the_step_and_is_read_past(self):
        for step, want in (("required: plane.json alpha.on", (True, "plane.json alpha.on")),
                           ("Required:plane.json alpha.on", (True, "plane.json alpha.on")),
                           ("plane.json beta.on", (False, "plane.json beta.on")),
                           ("required plane.json x.y", (False, "required plane.json x.y")),
                           ("none", (False, "none"))):
            self.assertEqual(tasklog.adopt_required(step), want, step)
        self.assertTrue(tasklog.asks_nothing("required: none"))

    def test_the_step_keeps_its_required_prefix(self):
        self.task("0001-a", extra='adopt: "required: plane.json verify.accept_cache"')
        self.assertEqual(tasklog.adopt_step(tasklog.load(self.p.cfg)[0]), "required: plane.json verify.accept_cache")

    def test_a_required_none_value_naming_a_key_warns_as_a_hidden_step(self):
        self.task("0001-a", extra='adopt: "required: none: plane.json verify.accept_cache turns it on"')
        warned = self.warns()
        self.assertEqual(len(warned), 1, warned)
        self.assertIn("verify.accept_cache", warned[0])

    def test_the_task_file_schema_carries_adopt(self):
        schema = json.loads((PLANE_ROOT / "contracts/task_file.schema.json").read_text())
        self.assertEqual(schema["properties"]["adopt"]["type"], "string")


if __name__ == "__main__":
    unittest.main()
