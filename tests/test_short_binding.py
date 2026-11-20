"""SPEC §8.3, §29.3: a binding holds where the product and its queue are, its integration branch, and its CI and
notes. The runner's agent, name and worktree are derived, its limits are constants (a value a binding still
sets applies, with a warning), the lead's compaction window is the product's own setting. A binding that still
holds a removed key loads with one warning for each, and `ccp upgrade status` lists them."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest import mock

from ccp import cli, config, lifecycle, upgrade
from ccp.queue import PLANE, lib
from tests.test_binding_reader import BindingDir
from tests.test_sandbox import SandboxCase
from tests.test_team_hosting import HOOK, TeamCase
from tests.test_upgrade import UpgradeFixture

SCHEMA = json.loads((PLANE / "contracts" / "project.schema.json").read_text())
KEPT = ["project_id", "integration_branch", "product_root", "queue_root"]
# The binding `ccp init` wrote before this task: the keys the plane no longer reads, and the runner's.
OLD_INIT = ("project_id: demo\nintegration_branch: main\nproduction_branch: main\nproduct_root: {root}\n"
            "durable_docs_path: docs/delivery/\nqueue_root: {queue}\nrunner:\n  agent_type: ccp:delivery-runner\n"
            "  name: runner\n  worktree: {root}/.plane-runtime/runner\n")
OLD_KEYS = ["production_branch", "durable_docs_path", "runner.agent_type", "runner.name", "runner.worktree"]
# §8.3, ADR-0043: every top-level key the plane removed from the binding.
REMOVED = ("production_branch", "durable_docs_path", "display_name", "adapter", "adapter_config_path", "hosting",
           "grok", "spec_maintainer", "auth_check", "seats", "cadence", "email", "verifier_access",
           "architecture_review")


def warnings_of(fn, *args) -> tuple[Any, str]:
    """What `fn` returns and what it wrote to stderr, with the once-per-process memory cleared first."""
    err = io.StringIO()
    config._WARNED.clear()
    with redirect_stderr(err):
        out = fn(*args)
    return out, err.getvalue()


class Init(SandboxCase):
    def test_a_new_product_gets_a_binding_of_exactly_its_four_keys(self):
        res = self.create(str(self.base / "S"))
        text = Path(res["binding"]).read_text()
        self.assertEqual(list(lib.read_binding(text)), KEPT)
        self.assertEqual(lib.binding_str(lib.read_binding(text), "product_root"), res["root"])
        self.assertEqual(lib.binding_str(lib.read_binding(text), "queue_root"), res["queue_root"])

    def test_a_kept_binding_is_checked_against_the_short_shape(self):
        root, q = self.plain("Short")
        binding = self.installation / "short.yaml"
        self.assertEqual(list(lib.read_binding(binding.read_text())), KEPT)
        r = self.ccp("--root", str(root), "init", "--project-id", "short")
        self.assertEqual([w for w in json.loads(r.stdout).get("warnings", []) if "carries" in w], [])
        binding.write_text(binding.read_text() + OLD_INIT.split("queue_root: {queue}\n")[1])
        body = json.loads(self.ccp("--root", str(root), "init", "--project-id", "short").stdout)
        carried = [w for w in body["warnings"] if "carries" in w]
        self.assertEqual(len(carried), 3, body["warnings"])  # runner.agent_type, runner.name, runner.worktree


class Schema(unittest.TestCase):
    def test_the_required_keys_are_the_short_binding_and_the_removed_ones_are_deprecated_not_dropped(self):
        self.assertEqual(SCHEMA["required"], KEPT[:1] + ["integration_branch", "queue_root", "product_root"])
        props = SCHEMA["properties"]
        for key in REMOVED:
            self.assertIs(props[key].get("deprecated"), True, key)
        for key in (*KEPT, "ci", "notes"):
            self.assertNotIn("deprecated", props[key], key)
        self.assertEqual(sorted(k for k, v in props.items() if v.get("deprecated")), sorted([*REMOVED, "runner", "lead"]))

    def test_an_old_binding_still_validates_and_one_without_durable_docs_path_does(self):
        data = lib.read_binding(OLD_INIT.format(root="/p", queue="/q"))
        self.assertEqual(validation_errors(data), [])
        data.pop("durable_docs_path")
        self.assertEqual(validation_errors(data), [])
        data.pop("product_root")
        self.assertEqual(validation_errors(data), ["product_root is required"])

    def test_the_binding_findings_agree_with_the_schema(self):
        every = {"project_id": "d", "integration_branch": "main", "product_root": "/p", "queue_root": "/q",
                 "ci": "github-actions", "notes": "n", **{k: "x" for k in REMOVED}}
        self.assertEqual(sorted(f["key"] for f in lib.binding_findings(every)), sorted(REMOVED))


def validation_errors(data: dict[str, Any]) -> list[str]:
    """The schema's own rules as far as a binding needs them: its required keys, and no key it does not list
    (`additionalProperties: false`, at the top and one block down)."""
    errs = [f"{k} is required" for k in SCHEMA["required"] if k not in data]
    for key, value in data.items():
        prop = SCHEMA["properties"].get(key)
        if prop is None:
            errs.append(f"{key} is not listed")
        elif isinstance(value, dict) and prop.get("properties") is not None:
            errs += [f"{key}.{k} is not listed" for k in value if k not in prop["properties"]]
    return errs


class OldBinding(BindingDir):
    """A binding as `ccp init` wrote it before this task: it still works, and names each key to delete."""

    def setUp(self):
        super().setUp()
        self.binding.write_text(OLD_INIT.format(root=self.product, queue=self.queue))

    def test_it_loads_with_one_warning_for_each_removed_key(self):
        _, err = warnings_of(lib.binding_data, self.queue)
        lines = err.splitlines()
        self.assertEqual(len(lines), len(OLD_KEYS), err)
        for key in OLD_KEYS:
            self.assertEqual(len([x for x in lines if f"{key} is removed and ignored" in x]), 1, (key, err))
        self.assertTrue(all("SPEC §29.3" in x for x in lines))
        again = io.StringIO()
        with redirect_stderr(again):
            lib.binding_data(self.queue)
        self.assertEqual(again.getvalue(), "")  # once per process

    def test_the_runner_is_the_same_as_before_by_derivation(self):
        sys.path.insert(0, str(PLANE / "scripts" / "observability"))
        import team  # noqa: PLC0415
        rc = team.runner_cfg(self.queue)
        self.assertEqual((rc["name"], rc["agent_type"], rc["worktree"]),
                         ("runner", "ccp:delivery-runner", str(self.product / ".plane-runtime" / "runner")))
        self.assertEqual((lib.RUNNER_NAME, lib.RUNNER_AGENT), ("runner", "ccp:delivery-runner"))
        self.assertEqual(lib.runner_worktree(self.queue), str(self.product / ".plane-runtime" / "runner"))

    def test_the_derived_values_ignore_what_the_binding_names(self):
        self.binding.write_text(OLD_INIT.format(root=self.product, queue=self.queue)
                                .replace("name: runner", "name: steward").replace("ccp:delivery-runner", "x")
                                .replace(f"{self.product}/.plane-runtime/runner", "/elsewhere"))
        sys.path.insert(0, str(PLANE / "scripts" / "observability"))
        import team  # noqa: PLC0415
        from ccp import queue  # noqa: PLC0415
        with redirect_stderr(io.StringIO()):
            rc = team.runner_cfg(self.queue)
            self.assertEqual(queue.runner_teammate(self.queue), "runner")
        self.assertEqual((rc["name"], rc["agent_type"], rc["worktree"]),
                         ("runner", "ccp:delivery-runner", str(self.product / ".plane-runtime" / "runner")))

    def test_the_worktree_is_under_the_products_worktrees_directory(self):
        (self.product / "docs/delivery").mkdir(parents=True)
        (self.product / "docs/delivery/plane.json").write_text('{"project_id": "demo", "worktrees": {"dir": ".rt"}}')
        self.assertEqual(lib.runner_worktree(self.queue), str(self.product / ".rt" / "runner"))
        (self.product / "docs/delivery/plane.json").write_text(
            '{"project_id": "demo", "adapter": {"worktree_dir": "../out"}}')  # the old key, read while it is set
        self.assertEqual(lib.runner_worktree(self.queue), os.path.normpath(self.product / ".." / "out" / "runner"))
        self.binding.write_text(f"project_id: demo\nqueue_root: {self.queue}\n")
        self.assertIsNone(lib.runner_worktree(self.queue))  # no product root: nowhere to derive it from

    def test_the_lead_window_is_named_as_moved(self):
        self.binding.write_text(f"project_id: demo\nqueue_root: {self.queue}\nlead:\n  auto_compact_window: 500000\n")
        _, err = warnings_of(lib.binding_data, self.queue)
        self.assertIn("lead.auto_compact_window moved to the product's .claude/settings.json", err)
        self.assertEqual([(f["key"], f["outcome"]) for f in lib.binding_findings(lib.binding_data(self.queue))],
                         [("lead.auto_compact_window", "moved")])


class Limits(BindingDir):
    """The runner's limits are constants; a value a binding still sets applies, with a warning (§29.3)."""

    def limits(self, runner: str = "") -> tuple[dict, str]:
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}\nqueue_root: {self.queue}\n" + runner)
        return warnings_of(lib.runner_limits, self.queue)

    def test_unset_they_are_the_constants_and_say_nothing(self):
        limits, err = self.limits()
        self.assertEqual((limits, err), ({"after_tasks": 4, "at_context_tokens": None, "idle_limit": 3}, ""))
        self.assertEqual(lifecycle.rotation_knobs(self.queue), (4, None))

    def test_a_value_other_than_the_constant_applies_with_a_warning_naming_both(self):
        limits, err = self.limits("runner:\n  rotate_after_tasks: 2\n  rotate_at_context_tokens: 100000\n"
                                  "  idle_block_limit: 5\n")
        self.assertEqual(limits, {"after_tasks": 2, "at_context_tokens": 100000, "idle_limit": 5})
        self.assertEqual(len(err.splitlines()), 3, err)
        self.assertIn("runner.rotate_after_tasks is a constant in code (4); the value 2 set here still applies", err)
        self.assertIn("runner.rotate_at_context_tokens is a constant in code (None); the value 100000", err)
        self.assertIn("runner.idle_block_limit is a constant in code (3); the value 5", err)
        self.assertEqual(lifecycle.rotation_knobs(self.queue), (2, 100000))

    def test_the_constants_own_value_warns_that_the_key_can_be_deleted(self):
        limits, err = self.limits("runner:\n  rotate_after_tasks: 4\n  rotate_at_context_tokens: null\n")
        self.assertEqual(limits, {"after_tasks": 4, "at_context_tokens": None, "idle_limit": 3})
        self.assertEqual(err.count("set to that value: delete it"), 2, err)

    def test_a_value_that_is_no_limit_is_named_and_the_constant_applies(self):
        limits, err = self.limits("runner:\n  rotate_after_tasks: 0\n  idle_block_limit: null\n  rotate_at_context_tokens: big\n")
        self.assertEqual(limits, {"after_tasks": 4, "at_context_tokens": None, "idle_limit": 3})
        self.assertEqual(err.count("which is no value it takes"), 3, err)

    def test_the_idle_hooks_limit_is_what_ccp_where_reports(self):
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}\nqueue_root: {self.queue}\n"
                                "runner:\n  idle_block_limit: 2\n")
        (self.product / "docs/delivery").mkdir(parents=True)
        (self.product / "docs/delivery/plane.json").write_text('{"project_id": "demo", "language": "none"}')
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.queue)}), redirect_stdout(out), \
                redirect_stderr(io.StringIO()), mock.patch("ccp.prompt.main_checkout", return_value=self.product):
            self.assertEqual(cli.main(["--root", str(self.product), "where"]), 0)
        self.assertEqual(json.loads(out.getvalue())["idle_limit"], 2)


class IdleHook(TeamCase):
    """The plugin's hook takes its limit from `ccp where`: 3, or the value a binding still sets."""

    def hook(self, idle_limit) -> int:
        fake = self.prod.root / "fake-bin"
        fake.mkdir(exist_ok=True)
        where = {"binding": str(self.q / "project.yaml"), "queue_root": str(self.q), "ccp": str(PLANE / "bin" / "ccp")}
        if idle_limit is not None:
            where["idle_limit"] = idle_limit
        (fake / "ccp").write_text(f"#!/bin/sh\necho '{json.dumps(where)}'\n")
        (fake / "ccp").chmod(0o755)
        env = {**self.env, "PATH": f"{fake}:{os.environ['PATH']}", "CLAUDE_PROJECT_DIR": str(self.prod.root)}
        stdin = json.dumps({"hook_event_name": "TeammateIdle", "teammate_name": "runner", "cwd": str(self.prod.root)})
        return subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env, input=stdin).returncode

    def setUp(self):
        super().setUp()
        self.prod.task("0001-a", status="done")
        self.prod.task("0002-b", deps=["0001-a"])
        self.prod.index()
        (self.q / "work.json").write_text(json.dumps({"status": "running", "scope": ["0001-a", "0002-b"],
                                                      "runner_tasks_done": 1, "waiting_on": None}))

    def test_without_a_reported_limit_it_lets_go_after_three_blocks(self):
        self.assertEqual([self.hook(None) for _ in range(4)], [2, 2, 2, 0])

    def test_a_reported_limit_is_the_hooks(self):
        self.assertEqual([self.hook(1) for _ in range(2)], [2, 0])


class Upgrade(UpgradeFixture, unittest.TestCase):
    def binding_step(self, text: str | None) -> dict[str, Any] | None:
        self.product_json(language="none")
        if text is not None:
            (self.bindings / "demo.yaml").write_text(
                f"project_id: demo\nproduct_root: {self.product.root.resolve()}\n" + text)
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return next((s for s in body["steps"] if s["task"] == upgrade.BINDING_STEP), None)

    def test_it_lists_each_removed_key_each_runner_limit_and_the_lead_window(self):
        step = self.binding_step("production_branch: main\nseats:\n  runner: x\nrunner:\n  name: runner\n"
                                 "  rotate_after_tasks: 2\n  rotate_at_context_tokens: null\nlead:\n  auto_compact_window: 1\n")
        self.assertFalse(step["required"])
        listed = {k["key"]: k for k in step["keys"]}
        self.assertEqual(set(listed), {"production_branch", "seats.runner", "runner.name", "runner.rotate_after_tasks",
                                       "runner.rotate_at_context_tokens", "lead.auto_compact_window"})
        self.assertEqual(listed["runner.name"]["outcome"], "removed")
        self.assertEqual((listed["runner.rotate_after_tasks"]["outcome"], listed["runner.rotate_after_tasks"]["constant"],
                          listed["runner.rotate_after_tasks"]["set"]), ("constant", 4, "2"))
        self.assertIn("delete `production_branch`: it is removed", step["change"])
        self.assertIn("delete `runner.rotate_after_tasks`: it is a constant, 4, and yours is '2'", step["change"])
        self.assertIn("delete `runner.rotate_at_context_tokens`: it is a constant, None, which is what yours already is",
                      step["change"])
        self.assertIn("move `lead.auto_compact_window` to the product's .claude/settings.json", step["change"])

    def test_a_short_binding_or_none_has_no_such_step(self):
        self.assertIsNone(self.binding_step(None))
        self.assertIsNone(self.binding_step("ci: github-actions\nnotes: n\n"))


class Readers(BindingDir):
    def test_the_products_binding_warns_once_for_a_removed_key(self):
        from types import SimpleNamespace  # noqa: PLC0415
        self.binding.write_text(f"project_id: demo\nproduct_root: {self.product}\nqueue_root: {self.queue}\nhosting: x\n")
        cfg = SimpleNamespace(project_id="demo", root=self.product)
        with mock.patch("ccp.prompt.main_checkout", return_value=self.product):
            got, err = warnings_of(cli.product_binding, cfg)
            self.assertEqual(got, self.binding)
            self.assertEqual(err.count("hosting is removed and ignored"), 1, err)
            self.assertEqual(warnings_of(cli.product_binding, cfg)[1].count("hosting"), 1)  # a second process

    def test_a_kept_key_is_never_warned_about(self):
        self.binding.write_text(f"project_id: demo\nintegration_branch: main\nproduct_root: {self.product}\n"
                                f"queue_root: {self.queue}\nci: github-actions\nnotes: n\n")
        self.assertEqual(warnings_of(lib.binding_data, self.queue)[1], "")


if __name__ == "__main__":
    unittest.main()
