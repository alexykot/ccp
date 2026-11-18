"""SPEC §29.3, ADR-0041 D2: `ccp upgrade notes` lists the plane's tasks merged since a commit with their
`adopt` steps; `ccp upgrade status` lists the steps a product has not taken."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config
from tests.helpers import TASK, Product

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def task_text(tid: str, status: str, title: str, adopt: str | None) -> str:
    ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
    text = TASK.format(tid=tid, title=title, status=status, deps="", ver=ver)
    if adopt is not None:
        text = text.replace(f"status: {status}", f"status: {status}\nadopt: \"{adopt}\"", 1)
    return text


class UpgradeFixture:
    """A scratch plane (a git repo with a task log, standing in for the checkout `ccp` runs from), a
    scratch product and a scratch queue."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        t = Path(self._tmp.name).resolve()
        self.q = t / "queue"
        self.q.mkdir()
        self.bindings = t / "bindings"
        self.bindings.mkdir()
        self.env = mock.patch.dict(os.environ, {**GIT_ENV, "QUEUE_ROOT": str(self.q), "ACTOR": "task-runner",
                                                "CCP_BINDINGS_DIR": str(self.bindings)})
        self.env.start()
        self.plane = Product()
        self.git("init", "-q", "-b", "main")
        self.plane_patch = mock.patch("ccp.queue.PLANE", self.plane.root)
        self.plane_patch.start()
        self.product = Product()

    def tearDown(self):
        self.plane_patch.stop()
        self.env.stop()
        self.plane.cleanup()
        self.product.cleanup()
        self._tmp.cleanup()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.plane.root), *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def plane_task(self, tid: str, status: str, title: str = "A task", adopt: str | None = None) -> None:
        self.plane.write(f"docs/delivery/tasks/{tid}.md", task_text(tid, status, title, adopt))

    def commit(self, msg: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def ccp(self, *args: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.product.root), *args])
        body = out.getvalue()
        return code, (json.loads(body) if body.strip().startswith("{") else None), err.getvalue()

    def product_json(self, **extra) -> None:
        self.product.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **extra}))

    def proposal(self, pid: str, status: str | None = None, built_task: str | None = None) -> None:
        p = self.q / "plane" / "proposals.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        rows = [{"op": "proposed", "id": pid, "at": "2026-11-01T00:00:00Z", "by": "implementer", "task_id": None,
                 "need": "a knob", "generic": "any product", "workaround": None, "frequency": "per-task"}]
        if status:
            rows.append({"op": "triaged", "id": pid, "at": "2026-11-02T00:00:00Z", "by": "plane-session",
                         "decision": status, "merged_into": None, "reason": "plane task"})
        if built_task:
            rows.append({"op": "built", "id": pid, "at": "2026-11-03T00:00:00Z", "by": "plane-session",
                         "built_task": built_task, "adopt": "x"})
        with p.open("a") as fh:
            fh.writelines(json.dumps(r) + "\n" for r in rows)


class Notes(UpgradeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane_task("0001-old", "done", "Old", "plane.json verify.skip_review")
        self.plane_task("0002-none", "pending", "None step", "none")
        self.plane_task("0003-cache", "pending", "Cache step", "plane.json verify.accept_cache")
        self.plane_task("0004-bare", "pending", "No key")
        self.plane_task("0005-later", "pending", "Still pending", "plane.json x.y")
        self.x = self.commit("X")
        for tid, title, adopt in (("0002-none", "None step", "none"),
                                  ("0003-cache", "Cache step", "plane.json verify.accept_cache"),
                                  ("0004-bare", "No key", None)):
            self.plane_task(tid, "done", title, adopt)
        self.commit("Y")

    def test_lists_the_tasks_done_since_the_commit_with_title_and_step_and_none_when_missing(self):
        code, body, err = self.ccp("upgrade", "notes", "--since", self.x)
        self.assertEqual(code, 0, err)
        self.assertEqual([(t["task"], t["title"], t["adopt"]) for t in body["tasks"]],
                         [("0002-none", "None step", "none"), ("0003-cache", "Cache step", "plane.json verify.accept_cache"),
                          ("0004-bare", "No key", "none")])
        self.assertEqual(body["since"], self.x)

    def test_the_default_since_is_the_plane_checkouts_previous_position(self):
        code, body, err = self.ccp("upgrade", "notes")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["since"], self.x)
        self.assertEqual([t["task"] for t in body["tasks"]], ["0002-none", "0003-cache", "0004-bare"])

    def test_a_since_that_is_not_a_commit_is_refused(self):
        code, body, err = self.ccp("upgrade", "notes", "--since", "no-such-ref")
        self.assertEqual((code, body), (2, None))
        self.assertIn("no-such-ref", err)

    def test_with_no_previous_position_it_asks_for_since(self):
        with tempfile.TemporaryDirectory() as d:
            fresh = Path(d)
            (fresh / "docs/delivery/tasks").mkdir(parents=True)
            (fresh / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "fresh"}))
            subprocess.run(["git", "-C", d, "init", "-q", "-b", "main"], check=True)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "commit", "-q", "-m", "only"], check=True)
            with mock.patch("ccp.queue.PLANE", fresh):
                code, body, err = self.ccp("upgrade", "notes")
        self.assertEqual((code, body), (2, None))
        self.assertIn("--since", err)

    def test_each_task_names_the_proposals_closed_as_built_by_it(self):
        self.proposal("pp-a", "accepted", built_task="0003-cache")
        self.proposal("pp-b", "accepted")
        code, body, err = self.ccp("upgrade", "notes", "--since", self.x)
        self.assertEqual(code, 0, err)
        self.assertEqual({t["task"]: t["proposals"] for t in body["tasks"]},
                         {"0002-none": [], "0003-cache": ["pp-a"], "0004-bare": []})


class Status(UpgradeFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane_task("0001-cache", "done", "Cache", "plane.json verify.accept_cache")
        self.plane_task("0002-clean", "done", "Skip after clean", "plane.json verify.skip_review_after_clean")
        self.plane_task("0003-hand", "done", "By hand", "run the migration by hand")
        self.plane_task("0004-pending", "pending", "Not merged", "plane.json verify.provers")
        self.commit("plane")
        self.product_json(verify={"skip_review_after_clean": True})

    def status(self) -> list[dict]:
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return body["steps"]

    def test_lists_the_untaken_key_and_the_by_hand_step_and_not_the_taken_key(self):
        steps = self.status()
        self.assertEqual([(s["task"], s["check"]) for s in steps],
                         [("0001-cache", "not taken"), ("0003-hand", "check by hand")])
        self.assertIn("verify.accept_cache", steps[0]["change"])
        self.assertEqual(steps[1]["change"], "run the migration by hand")

    def test_a_declined_task_is_left_out(self):
        self.product_json(verify={"skip_review_after_clean": True},
                          upgrade={"declined": {"0001-cache": "our suite has no cache"}})
        self.assertEqual([s["task"] for s in self.status()], ["0003-hand"])

    def test_a_key_the_product_holds_with_any_value_is_taken(self):
        self.product_json(verify={"skip_review_after_clean": False, "accept_cache": None})
        self.assertEqual([s["task"] for s in self.status()], ["0003-hand"])

    def test_a_step_whose_first_word_is_none_asks_nothing(self):
        self.plane_task("0005-quiet", "done", "Quiet", "none: it applies by itself")
        self.plane_task("0006-quiet", "done", "Quiet", "None for products; the plane sets it for itself")
        self.assertEqual([s["task"] for s in self.status()], ["0001-cache", "0003-hand"])

    def test_a_settings_step_is_read_from_the_products_settings(self):
        self.plane_task("0005-ttl", "done", "TTL", '.claude/settings.json subagentPromptCacheTtl 1h')
        self.plane_task("0006-env", "done", "Env", ".claude/settings.json env.CCP_X")
        self.product.write(".claude/settings.json", json.dumps({"subagentPromptCacheTtl": "5m"}))
        steps = {s["task"]: s for s in self.status()}
        self.assertNotIn("0005-ttl", steps)
        self.assertEqual(steps["0006-env"]["check"], "not taken")

    def test_a_settings_step_with_no_settings_file_is_not_taken(self):
        self.plane_task("0005-ttl", "done", "TTL", '.claude/settings.json subagentPromptCacheTtl 1h')
        step = {s["task"]: s for s in self.status()}["0005-ttl"]
        self.assertEqual(step["check"], "not taken")
        self.assertIn("1h", step["change"])

    def test_a_binding_step_is_read_from_the_products_binding_and_by_hand_without_one(self):
        self.plane_task("0005-window", "done", "Window", "binding lead.auto_compact_window")
        self.plane_task("0006-other", "done", "Other", "binding lead.other")
        self.assertEqual({s["task"]: s["check"] for s in self.status()}["0005-window"], "check by hand")
        (self.bindings / "demo.yaml").write_text(
            f"project_id: demo\nproduct_root: {self.product.root.resolve()}\nlead:\n  auto_compact_window: 350000\n")
        checks = {s["task"]: s["check"] for s in self.status()}
        self.assertNotIn("0005-window", checks)
        self.assertEqual(checks["0006-other"], "not taken")

    def test_a_step_naming_settings_is_read_from_the_products_settings(self):
        self.plane_task("0005-ttl", "done", "TTL", "settings subagentPromptCacheTtl 1h, with autoCompactWindow beside it")
        self.assertEqual({s["task"]: s["check"] for s in self.status()}["0005-ttl"], "not taken")
        self.product.write(".claude/settings.json", json.dumps({"subagentPromptCacheTtl": "1h"}))
        self.assertNotIn("0005-ttl", [s["task"] for s in self.status()])

    def test_a_task_recorded_as_taken_is_listed_under_taken_with_its_reason_and_not_as_a_step(self):
        self.product_json(verify={"skip_review_after_clean": True},
                          upgrade={"taken": {"0003-hand": "gate already parallel"},
                                   "declined": {"0001-cache": "our suite has no cache"}})
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["steps"], [])
        self.assertEqual([(t["task"], t["reason"]) for t in body["taken"]], [("0003-hand", "gate already parallel")])

    def test_nothing_is_listed_under_taken_by_default(self):
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["taken"], [])

    def test_the_products_own_proposal_is_named(self):
        self.proposal("pp-mine", "accepted", built_task="0001-cache")
        steps = {s["task"]: s["proposals"] for s in self.status()}
        self.assertEqual(steps, {"0001-cache": ["pp-mine"], "0003-hand": []})


class Required(UpgradeFixture, unittest.TestCase):
    """§5.2, §29.3: a step that starts with `required:` is marked required, any other optional, and the reading
    names the plane checkout's commit; a plane.json block no step names changes nothing."""

    def setUp(self):
        super().setUp()
        self.plane_task("0001-alpha", "done", "Alpha", "required: plane.json alpha.on")
        self.plane_task("0002-beta", "done", "Beta", "plane.json beta.on")
        self.head = self.commit("plane")
        self.product_json()

    def reading(self) -> dict:
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return body

    def test_each_step_is_marked_required_or_optional_and_the_plane_commit_is_named(self):
        body = self.reading()
        self.assertEqual([(s["task"], s["required"], s["check"]) for s in body["steps"]],
                         [("0001-alpha", True, "not taken"), ("0002-beta", False, "not taken")])
        self.assertEqual(body["steps"][0]["change"], "set `alpha.on` in docs/delivery/plane.json")
        self.assertEqual(body["steps"][0]["adopt"], "required: plane.json alpha.on")
        self.assertEqual(body["plane"], self.head)

    def test_a_required_step_the_product_took_is_not_listed(self):
        self.product_json(alpha={"on": True})
        self.assertEqual([s["task"] for s in self.reading()["steps"]], ["0002-beta"])

    def test_a_required_step_it_cannot_check_is_listed_by_hand_without_the_prefix(self):
        self.plane_task("0003-hand", "done", "Hand", "required: run the migration by hand")
        step = {s["task"]: s for s in self.reading()["steps"]}["0003-hand"]
        self.assertEqual((step["required"], step["check"], step["change"]),
                         (True, "check by hand", "run the migration by hand"))

    def test_a_step_of_only_the_prefix_is_listed_by_hand_as_written(self):
        self.plane_task("0004-bare", "done", "Bare", "required:")
        step = {s["task"]: s for s in self.reading()["steps"]}["0004-bare"]
        self.assertEqual((step["required"], step["check"], step["change"]), (True, "check by hand", "required:"))

    def test_a_block_no_step_names_leaves_the_reading_as_it_was(self):
        before = self.reading()
        self.product_json(gamma={"on": True})
        self.assertEqual(self.reading(), before)


class Declined(unittest.TestCase):
    def test_upgrade_declined_maps_a_task_id_to_a_reason(self):
        p = Product({"upgrade": {"declined": {"0001-a": "not for us"}}})
        try:
            self.assertEqual(p.cfg.upgrade["declined"], {"0001-a": "not for us"})
            self.assertEqual(Product().cfg.upgrade["declined"], {})
            for bad in ({"declined": ["0001-a"]}, {"declined": {"0001-a": ""}}, {"declined": {"0001-a": 3}}, []):
                p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "upgrade": bad}))
                with self.assertRaises(config.ConfigError, msg=bad):
                    config.load(p.root)
        finally:
            p.cleanup()

    def test_the_schema_carries_upgrade_declined(self):
        schema = json.loads((Path(__file__).resolve().parents[1] / "contracts/plane_config.schema.json").read_text())
        self.assertIn("declined", schema["properties"]["upgrade"]["properties"])
        self.assertIn("taken", schema["properties"]["upgrade"]["properties"])

    def test_upgrade_taken_maps_a_task_id_to_a_reason(self):
        p = Product({"upgrade": {"taken": {"0001-a": "done by hand"}}})
        try:
            self.assertEqual(p.cfg.upgrade["taken"], {"0001-a": "done by hand"})
            self.assertEqual(Product().cfg.upgrade["taken"], {})
            for bad in ({"taken": ["0001-a"]}, {"taken": {"0001-a": " "}}, {"taken": {"0001-a": None}}):
                p.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "upgrade": bad}))
                with self.assertRaises(config.ConfigError, msg=bad):
                    config.load(p.root)
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
