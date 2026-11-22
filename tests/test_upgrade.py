"""SPEC §29.3, ADR-0041 D2: `ccp upgrade notes` lists the plane's tasks merged since a commit with their
`adopt` steps; `ccp upgrade status` lists the steps a product has not taken."""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, upgrade
from ccp.queue import QueueError
from tests.helpers import binding, PLANE_ROOT, Product
from tests.upgrade_fixture import UpgradeFixture


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
            binding(product_root=self.product.root.resolve(), lead={"auto_compact_window": 350000}))
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


class Record(UpgradeFixture, unittest.TestCase):
    """§29.3: `ccp upgrade decline` and `take` write plane.json `upgrade.declined` and `upgrade.taken`, each
    removing the task from the other; `status` lists the steps it found taken under `detected`."""

    def setUp(self):
        super().setUp()
        self.plane_task("0001-alpha", "done", "Alpha", "plane.json alpha.on")
        self.plane_task("0002-quiet", "done", "Quiet", "none")
        self.plane_task("0003-later", "pending", "Later", "plane.json gamma.on")
        self.commit("plane")
        self.product_json()

    def plane_json(self) -> dict:
        return json.loads((self.product.root / "docs/delivery/plane.json").read_text())

    def reading(self) -> dict:
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return body

    def listed(self, body: dict) -> dict[str, list[str]]:
        return {k: [s["task"] for s in body[k]] for k in ("steps", "taken", "detected")}

    def test_a_declined_step_is_recorded_and_status_lists_it_nowhere(self):
        code, body, err = self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")
        self.assertEqual(code, 0, err)
        self.assertEqual(body, {"ok": True, "task": "0001-alpha", "recorded": "declined", "reason": "not for us"})
        self.assertEqual(self.plane_json()["upgrade"]["declined"], {"0001-alpha": "not for us"})
        config.load(self.product.root)
        self.assertEqual(self.listed(self.reading()), {"steps": [], "taken": [], "detected": []})

    def test_taking_a_declined_step_moves_the_record(self):
        self.assertEqual(self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")[0], 0)
        code, body, err = self.ccp("upgrade", "take", "0001-alpha", "--reason", "done by hand")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["recorded"], "taken")
        upgrade = self.plane_json()["upgrade"]
        self.assertEqual(upgrade["taken"], {"0001-alpha": "done by hand"})
        self.assertNotIn("0001-alpha", upgrade["declined"])
        self.assertEqual([(t["task"], t["reason"]) for t in self.reading()["taken"]], [("0001-alpha", "done by hand")])

    def test_declining_a_taken_step_moves_the_record_back(self):
        self.assertEqual(self.ccp("upgrade", "take", "0001-alpha", "--reason", "done by hand")[0], 0)
        self.assertEqual(self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")[0], 0)
        upgrade = self.plane_json()["upgrade"]
        self.assertEqual((upgrade["declined"], upgrade["taken"]), ({"0001-alpha": "not for us"}, {}))

    def test_the_task_may_be_named_by_its_number(self):
        code, body, err = self.ccp("upgrade", "decline", "0001", "--reason", "not for us")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["task"], "0001-alpha")
        self.assertEqual(self.plane_json()["upgrade"]["declined"], {"0001-alpha": "not for us"})

    def test_a_one_line_file_gains_the_entry_inline_and_keeps_its_keys_in_order(self):
        before = json.dumps({"project_id": "demo", "zeta": {"a": 1}, "alpha": {"off": True}})
        self.product.write("docs/delivery/plane.json", before)
        self.assertEqual(self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")[0], 0)
        self.assertEqual((self.product.root / "docs/delivery/plane.json").read_text(),
                         before[:-1] + ', "upgrade": {"declined": {"0001-alpha": "not for us"}}}')

    def test_take_then_decline_changes_only_the_upgrade_entry_and_keeps_every_other_line(self):
        path = self.product.root / "docs/delivery/plane.json"
        lines = ["{", '  "project_id": "demo",', '  "language": "none",',
                 '  "suite": {"lanes": {"gate": ["true"], "full": ["a", "b"]}, "count_re": null},',
                 '  "adr": {"dir": "docs/adr", "index": null, "strict": false},', '  "architect": false', "}"]
        path.write_bytes(("\n".join(lines) + "\n").encode())
        self.assertEqual(self.ccp("upgrade", "take", "0001-alpha", "--reason", "done by hand")[0], 0)
        kept = [*lines[:-2], lines[-2] + ","]
        after = path.read_text().split("\n")
        self.assertEqual(after[:-3], kept)
        self.assertEqual(after[-2:], ["}", ""])
        self.assertEqual(json.loads("{" + after[-3] + "}"), {"upgrade": {"taken": {"0001-alpha": "done by hand"}}})
        self.assertEqual(self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")[0], 0)
        after = path.read_text().split("\n")
        self.assertEqual(after[:-3], kept)
        self.assertEqual(after[-2:], ["}", ""])
        config.load(self.product.root)
        upgrade = self.plane_json()["upgrade"]
        self.assertEqual((upgrade["taken"], upgrade["declined"]), ({}, {"0001-alpha": "not for us"}))
        self.assertEqual(json.loads("{" + after[-3] + "}"), {"upgrade": upgrade})

    def test_a_file_with_crlf_line_ends_keeps_them(self):
        path = self.product.root / "docs/delivery/plane.json"
        before = b'{\r\n  "project_id": "demo"\r\n}\r\n'
        path.write_bytes(before)
        self.assertEqual(self.ccp("upgrade", "take", "0001-alpha", "--reason", "done by hand")[0], 0)
        entry = b',\r\n  "upgrade": {"taken": {"0001-alpha": "done by hand"}}'
        self.assertEqual(path.read_bytes(), before.replace(b'"demo"', b'"demo"' + entry))

    def test_a_plane_json_the_editor_cannot_change_in_place_is_refused_and_left_as_it_was(self):
        path = self.product.root / "docs/delivery/plane.json"
        before = path.read_bytes()
        with mock.patch("ccp.jsonedit.set_member", side_effect=ValueError("no")):
            code, body, err = self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")
        self.assertEqual((code, body), (2, None))
        self.assertIn("could not be edited in place", err)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_a_bad_record_is_refused_and_nothing_is_written(self):
        path = self.product.root / "docs/delivery/plane.json"
        before = path.read_bytes()
        for args in (("decline", "0001-alpha", "--reason", " "), ("decline", "0001-alpha"),
                     ("decline", "9999-no-such", "--reason", "x"), ("take", "0003-later", "--reason", "x"),
                     ("take", "0002-quiet", "--reason", "x")):
            code, body, err = self.ccp("upgrade", *args)
            self.assertEqual((code, body), (2, None), args)
            self.assertEqual(path.read_bytes(), before, args)
            if args[:2] == ("decline", "0001-alpha"):  # a blank or missing reason is refused as that
                self.assertIn("--reason", err, args)

    def test_a_plane_json_that_would_not_load_after_the_change_is_left_as_it_was(self):
        path = self.product.root / "docs/delivery/plane.json"
        before = path.read_bytes()
        real = config._parse  # noqa: SLF001

        def parse(root, text):  # the file as it is loads; the file with the record does not
            if "not for us" in text:
                raise config.ConfigError("no")
            return real(root, text)
        with mock.patch("ccp.config._parse", side_effect=parse):
            code, body, err = self.ccp("upgrade", "decline", "0001-alpha", "--reason", "not for us")
        self.assertEqual((code, body), (2, None))
        self.assertIn("would not load", err)
        self.assertEqual(path.read_bytes(), before)

    def test_a_plane_json_that_does_not_load_is_refused(self):
        path = self.product.root / "docs/delivery/plane.json"
        path.write_text("{not json")
        code, body, _ = self.ccp("upgrade", "decline", "0001-alpha", "--reason", "x")
        self.assertEqual((code, body), (2, None))
        self.assertEqual(path.read_text(), "{not json")

    def test_a_plane_json_broken_after_the_command_started_is_refused(self):
        cfg = config.load(self.product.root)
        path = self.product.root / "docs/delivery/plane.json"
        path.write_text("{not json")
        with self.assertRaises(QueueError) as ctx:
            upgrade.decline(cfg, argparse.Namespace(task="0001-alpha", reason="x", cmd="decline"))
        self.assertEqual(ctx.exception.code, 2)
        self.assertEqual(path.read_text(), "{not json")

    def test_a_step_found_taken_is_listed_under_detected_and_not_under_taken(self):
        self.product_json(alpha={"on": True})
        body = self.reading()
        self.assertEqual(self.listed(body), {"steps": [], "taken": [], "detected": ["0001-alpha"]})
        self.assertEqual(body["detected"], [{"task": "0001-alpha", "title": "Alpha", "adopt": "plane.json alpha.on"}])


class Change(UpgradeFixture, unittest.TestCase):
    """§29.3: a checkable step's change names the key alone, `to` a one-word value, or the rest as written."""

    def test_each_change_reads_as_written(self):
        self.plane_task("0001-a", "done", "A", "plane.json a.b")
        self.plane_task("0002-c", "done", "C", "plane.json c.d 1h")
        self.plane_task("0003-e", "done", "E", "plane.json e.f with tool and to naming the channel")
        self.commit("plane")
        self.product_json()
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        self.assertEqual([s["change"] for s in body["steps"]],
                         ["set `a.b` in docs/delivery/plane.json", "set `c.d` in docs/delivery/plane.json to 1h",
                          "set `e.f` in docs/delivery/plane.json: with tool and to naming the channel"])


class LanguageStep(UpgradeFixture, unittest.TestCase):
    """§8.1, §29.3: the step that sets `language` proposes the product's own value, or states the choice."""

    def setUp(self):
        super().setUp()
        self.plane_task("0001-lang", "done", "Lang", "required: plane.json language (python, or none)")
        self.commit("plane")

    def change(self, **plane) -> str | None:
        self.product_json(**plane)
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        steps = [s for s in body["steps"] if s["task"] == "0001-lang"]
        return steps[0]["change"] if steps else None

    def test_a_package_docs_block_names_its_language_or_the_old_default(self):
        self.assertIn("to none ", self.change(package_docs={"language": "none"}))
        self.assertIn("to python ", self.change(package_docs={"language": "python"}))
        self.assertIn("to python ", self.change(package_docs={}))

    def test_with_no_package_docs_block_it_states_the_choice_and_proposes_no_value(self):
        change = self.change()
        self.assertIn("(a) python", change)
        self.assertIn("(b) none", change)
        self.assertNotIn(" to ", change.split(";")[0])

    def test_a_product_that_sets_language_has_taken_it(self):
        self.assertIsNone(self.change(language="none"))


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
        schema = json.loads((PLANE_ROOT / "contracts/plane_config.schema.json").read_text())
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
