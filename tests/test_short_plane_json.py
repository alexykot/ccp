"""A plane.json key that is not the product's to decide has one outcome (`config.KEY_OUTCOMES`, SPEC §29.3,
ADR-0043 D9), and one loader applies it: a removed key is ignored with a warning, a merged key is read at its
new place (and at its old one, with a warning, while the new is unset), a constant keeps a value the product sets
other than the constant, with a warning, until the product deletes the key. `ccp upgrade status` lists each key a
product still sets."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr
from typing import Any
from unittest import mock

from ccp import config, estimator, tasklog
from tests.helpers import PLANE_ROOT, Product
from tests.upgrade_fixture import UpgradeFixture

SCHEMA = json.loads((PLANE_ROOT / "contracts/plane_config.schema.json").read_text())
MACHINE_SCHEMA = json.loads((PLANE_ROOT / "contracts/machine.schema.json").read_text())

# A test-only constant: a real key (so the loader knows it), registered here as the constant it is not in the plane.
CONSTANT_KEY = "board.refresh_minutes"
TEST_CONSTANT = {CONSTANT_KEY: config.Outcome(config.CONSTANT, value=config.BOARD_DEFAULTS["refresh_minutes"])}


def load(plane: dict[str, Any], *, bare: bool = True) -> tuple[config.Config, str]:
    """The config of a temp product whose plane.json is `plane`, and what loading it wrote to stderr."""
    p = Product(plane, bare=bare)
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            config._WARNED.clear()
            return config.load(p.root), err.getvalue()
    finally:
        p.cleanup()


class Removed(unittest.TestCase):
    def test_task_log_statuses_is_ignored_with_a_warning(self):
        cfg, err = load({"task_log": {"statuses": ["pending", "done", "dropped", "extra"]}})
        self.assertNotIn("statuses", cfg.task_log)
        self.assertIn("task_log.statuses is removed and ignored", err)
        self.assertEqual(cfg.unknown_keys, ())

    def test_the_old_suite_summary_names_are_ignored_with_a_warning_each(self):
        cfg, err = load({"suite": {"summary": {"modules_ran_re": r"(\d+) ran", "modules_cached_re": r"(\d+) hit",
                                               "failed_re": r"(\d+) bad"}}})
        self.assertEqual(cfg.suite["summary"], {"failed_re": r"(\d+) bad"})
        self.assertIn("suite.summary.modules_ran_re is removed and ignored: its name is `ran_re`", err)
        self.assertIn("suite.summary.modules_cached_re is removed and ignored: its name is `cached_re`", err)

    def test_the_warning_shows_in_the_checks_too(self):
        cfg, _ = load({"task_log": {"statuses": []}})
        self.assertTrue(any("task_log.statuses is removed" in w for w in config.config_warnings(cfg)))
        self.assertTrue(any("task_log.statuses is removed" in w for w in tasklog.warnings(cfg)))

    def test_a_product_that_sets_none_hears_nothing(self):
        cfg, err = load({"language": "none"})
        self.assertEqual((err, cfg.key_notes), ("", ()))


class MergedSpecPaths(unittest.TestCase):
    def test_the_top_level_key_is_read_and_the_default_names_the_usual_places(self):
        cfg, err = load({"spec_paths": ["spec/"]})
        self.assertEqual((config.spec_paths(cfg), err), (["spec/"], ""))
        self.assertEqual(config.spec_paths(load({})[0]), ["docs/SPEC.md", "SPEC.md", "docs/spec/", "spec/"])

    def test_each_old_place_is_read_while_the_new_is_unset_with_a_warning_naming_it(self):
        for old in ("task_log", "estimate"):
            with self.subTest(old=old):
                cfg, err = load({old: {"spec_paths": ["design/"]}})
                self.assertEqual(config.spec_paths(cfg), ["design/"])
                self.assertIn(f"{old}.spec_paths has moved to spec_paths", err)
                self.assertNotIn("spec_paths", cfg.task_log if old == "task_log" else cfg.estimate)

    def test_the_new_place_wins_when_both_are_set_and_the_old_one_is_ignored_with_a_warning(self):
        cfg, err = load({"spec_paths": ["new/"], "task_log": {"spec_paths": ["old/"]},
                         "estimate": {"spec_paths": ["older/"]}})
        self.assertEqual(config.spec_paths(cfg), ["new/"])
        self.assertIn("task_log.spec_paths is ignored: spec_paths is set", err)
        self.assertIn("estimate.spec_paths is ignored: spec_paths is set", err)

    def test_a_value_is_checked_wherever_it_was_set_and_the_error_names_the_key_the_product_wrote(self):
        for plane, key in (({"spec_paths": "SPEC.md"}, "spec_paths"),
                           ({"task_log": {"spec_paths": ["../x"]}}, "task_log.spec_paths"),
                           ({"estimate": {"spec_paths": [3]}}, "estimate.spec_paths")):
            with self.subTest(plane=plane):
                with self.assertRaisesRegex(config.ConfigError, f"{key.replace('.', '[.]')} must be a list"), \
                        redirect_stderr(io.StringIO()):
                    load(plane)

    def test_an_old_estimate_glob_moves_as_its_directory_with_a_warning_saying_so(self):
        cfg, err = load({"estimate": {"spec_paths": ["docs/spec/*.md", "SPEC.md", "x/*/*.md"]}})
        self.assertEqual(config.spec_paths(cfg), ["docs/spec/", "SPEC.md", "x/*/*.md"])
        self.assertIn("docs/spec/*.md read as docs/spec/", err)
        self.assertNotIn("x/*/*.md read as", err)
        cfg, err = load({"task_log": {"spec_paths": ["a/*.md"]}})
        self.assertEqual(config.spec_paths(cfg), ["a/*.md"])
        self.assertNotIn("read as", err)

    def test_the_estimator_reads_a_directory_as_its_markdown_files(self):
        p = Product({"spec_paths": ["design/", "RULES.md"]}, bare=True)
        self.addCleanup(p.cleanup)
        for rel in ("design/a.md", "design/b.txt", "RULES.md", "docs/SPEC.md"):
            p.write(rel, "# x\n")
        got = [f.relative_to(p.root).as_posix() for f in estimator._spec_files(p.cfg)]  # noqa: SLF001
        self.assertEqual(got, ["design/a.md", "RULES.md"])


class MergedWorktrees(unittest.TestCase):
    def test_the_old_keys_are_read_while_the_new_are_unset_with_a_warning_naming_them(self):
        cfg, err = load({"adapter": {"worktree_dir": ".lg", "worktree_links": [".env"]}})
        self.assertEqual((cfg.worktrees["dir"], cfg.worktrees["links"]), (".lg", [".env"]))
        self.assertIn("adapter.worktree_dir has moved to worktrees.dir", err)
        self.assertIn("adapter.worktree_links has moved to worktrees.links", err)

    def test_the_new_keys_win_when_they_say_the_same_and_the_old_ones_are_ignored_with_a_warning(self):
        cfg, err = load({"adapter": {"worktree_dir": config.WORKTREES_DIR, "worktree_links": [".env"]},
                         "worktrees": {"dir": config.WORKTREES_DIR, "links": [".env"]}})
        self.assertEqual((cfg.worktrees["dir"], cfg.worktrees["links"]), (config.WORKTREES_DIR, [".env"]))
        self.assertIn("adapter.worktree_dir is ignored: worktrees.dir is set", err)
        self.assertIn("adapter.worktree_links is ignored: worktrees.links is set", err)

    def test_both_places_set_to_different_values_is_an_error(self):
        for plane in ({"adapter": {"worktree_dir": ".a"}, "worktrees": {"dir": ".b"}},
                      {"adapter": {"worktree_links": [".a"]}, "worktrees": {"links": [".b"]}}):
            with self.subTest(plane=plane):
                with self.assertRaisesRegex(config.ConfigError, "not both"), redirect_stderr(io.StringIO()):
                    load(plane)

    def test_an_empty_old_key_is_no_value(self):
        cfg, err = load({"adapter": {"worktree_dir": None, "worktree_links": []}, "worktrees": {"dir": ".wt"}})
        self.assertEqual(cfg.worktrees["dir"], ".wt")
        self.assertIn("adapter.worktree_dir is empty and ignored", err)


class MergedPostClose(unittest.TestCase):
    def test_it_is_still_read_in_place_with_a_warning_that_it_moves_to_the_hooks(self):
        cfg, err = load({"adapter": {"post_close": ["touch closed-{nnnn}"]}})
        self.assertEqual(cfg.adapter["post_close"], ["touch closed-{nnnn}"])
        self.assertEqual(cfg.reconcile["hooks"], [])
        self.assertIn("adapter.post_close moves to reconcile.hooks", err)
        self.assertIn("$TASK_ID", err)

    def test_an_empty_list_is_no_value_and_warns_of_nothing_to_move(self):
        cfg, err = load({"adapter": {"post_close": []}})
        self.assertEqual(cfg.adapter["post_close"], [])
        self.assertIn("adapter.post_close is empty and ignored", err)
        self.assertNotIn("moves to reconcile.hooks", err)


class MergedReviewPointPattern(unittest.TestCase):
    def test_it_is_the_ids_pattern_with_a_warning_naming_the_new_key(self):
        cfg, err = load({"task_log": {"review_point_pattern": "^Q[0-9]+$"}})
        self.assertEqual(cfg.ids.review_point_pattern, "^Q[0-9]+$")
        self.assertIn("ids.review_point.pattern", err)
        self.assertTrue(cfg.ids.is_review_point("Q7"))
        self.assertFalse(cfg.ids.is_review_point("R7"))

    def test_without_it_the_one_default_holds(self):
        cfg, err = load({})
        self.assertEqual((cfg.ids.review_point_pattern, err), ("R[1-9][0-9]*", ""))

    def test_the_new_place_wins_when_both_are_set(self):
        cfg, err = load({"task_log": {"review_point_pattern": "^Q[0-9]+$"},
                         "ids": {"review_point": {"pattern": "P[0-9]+"}}})
        self.assertEqual(cfg.ids.review_point_pattern, "P[0-9]+")
        self.assertIn("task_log.review_point_pattern is ignored: ids.review_point.pattern is set", err)

    def test_it_is_checked_as_a_regular_expression_and_the_error_names_the_key_the_product_wrote(self):
        with self.assertRaisesRegex(config.ConfigError, "task_log.review_point_pattern is not a regular expression"), \
                redirect_stderr(io.StringIO()):
            load({"task_log": {"review_point_pattern": "("}})

    def test_with_a_register_it_is_ignored_with_a_warning(self):
        p = Product({"task_log": {"review_point_pattern": "^Q[0-9]+$"}}, bare=True)
        self.addCleanup(p.cleanup)
        p.write("docs/delivery/review-points.yaml", "review_points: []\n")
        err = io.StringIO()
        with redirect_stderr(err):
            config._WARNED.clear()
            cfg = config.load(p.root)
        self.assertEqual(cfg.ids.review_point_pattern, "R[1-9][0-9]*")
        self.assertIn("task_log.review_point_pattern is ignored: the review-point register", err.getvalue())


class Constants(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.dict(config.KEY_OUTCOMES, TEST_CONSTANT)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_value_other_than_the_constant_applies_with_one_warning_naming_both(self):
        cfg, err = load({"board": {"refresh_minutes": 9}})
        self.assertEqual(cfg.board["refresh_minutes"], 9)
        self.assertEqual(err.count(CONSTANT_KEY), 1, err)
        self.assertIn("a constant in code (5)", err)
        self.assertIn("9", err)
        self.assertEqual(sum(CONSTANT_KEY in n for n in cfg.key_notes), 1)

    def test_the_constants_own_value_warns_that_the_key_can_be_deleted(self):
        cfg, err = load({"board": {"refresh_minutes": 5}})
        self.assertEqual(cfg.board["refresh_minutes"], 5)
        self.assertIn(f"{CONSTANT_KEY} is a constant in code (5) and is set to that value: delete it", err)

    def test_unset_it_is_the_constant_and_says_nothing(self):
        cfg, err = load({"board": {}})
        self.assertEqual((cfg.board["refresh_minutes"], err), (5, ""))
        self.assertEqual(config.constant_override(CONSTANT_KEY), 5)

    def test_the_value_is_still_checked(self):
        with self.assertRaisesRegex(config.ConfigError, "board.refresh_minutes must be an integer"), \
                redirect_stderr(io.StringIO()):
            load({"board": {"refresh_minutes": "often"}})

    def test_any_reader_gets_the_value_to_use_and_the_warning_in_the_notes_it_passes(self):
        notes: list[str] = []
        self.assertEqual(config.constant_override(CONSTANT_KEY, 9, notes=notes, where="the binding"), 9)
        self.assertEqual(config.constant_override(CONSTANT_KEY, 9, notes=notes, where="the binding"), 9)
        self.assertEqual(config.constant_override(CONSTANT_KEY, 5, notes=notes, where="the binding"), 5)
        self.assertEqual(len(notes), 2)  # one per distinct warning: the same one is not repeated
        self.assertTrue(all(n.startswith("the binding: ") for n in notes))

    def test_without_notes_the_warning_goes_to_stderr_once_per_place(self):
        err = io.StringIO()
        with redirect_stderr(err):
            config._WARNED.clear()
            for _ in range(3):
                config.constant_override(CONSTANT_KEY, 9, where="the binding")
            config.constant_override(CONSTANT_KEY, 9, where="another")
        self.assertEqual(err.getvalue().count(CONSTANT_KEY), 2)

    def test_a_key_that_is_no_constant_is_refused(self):
        with self.assertRaises(KeyError):
            config.constant_override("task_log.statuses", [])
        with self.assertRaises(KeyError):
            config.constant_override("no.such.key")


class Registry(unittest.TestCase):
    def schema_prop(self, key: str) -> dict[str, Any]:
        node: Any = {"properties": SCHEMA["properties"]}
        for part in key.split("."):
            self.assertIn(part, node["properties"], f"the schema does not list {key}")
            node = node["properties"][part]
        return node

    def test_every_key_has_one_outcome_and_the_schema_marks_it_deprecated_with_that_outcome(self):
        words = {config.REMOVED: "Removed", config.MERGED: "Merged into", config.CONSTANT: "Constant"}
        for key, o in config.KEY_OUTCOMES.items():
            with self.subTest(key=key):
                self.assertIn(o.kind, words)
                prop = self.schema_prop(key)
                self.assertIs(prop.get("deprecated"), True)
                self.assertTrue(prop["description"].startswith(words[o.kind]), prop["description"])
                if o.kind == config.MERGED:
                    self.assertIn(f"`{o.into}`", prop["description"])
                    self.assertTrue(o.into)
                    if o.machine:  # it moves to the machine file's key (`machine.json <key>`)
                        self.assertIn(o.into.split()[1], MACHINE_SCHEMA["properties"])
                    else:
                        self.schema_prop(o.into)  # it moves to a key that exists

    def test_every_deprecated_key_in_the_schema_has_an_outcome(self):
        # Two keys carry their own mechanism, for as long as it lasts: the language's old place (§8.1), and the
        # per-arm implementer models, whose task removes them.
        own = {"package_docs.language", "workers.implementer_model"}
        found: list[str] = []

        def walk(props: dict[str, Any], path: str) -> None:
            for name, prop in props.items():
                if prop.get("deprecated"):
                    found.append(f"{path}{name}")
                if isinstance(prop.get("properties"), dict):
                    walk(prop["properties"], f"{path}{name}.")

        walk(SCHEMA["properties"], "")
        self.assertEqual(sorted(set(found) - own), sorted(config.KEY_OUTCOMES))

    def test_a_removed_or_merged_key_has_no_default_and_a_constant_is_its_default(self):
        for key, o in config.KEY_OUTCOMES.items():
            *path, name = key.split(".")
            node: Any = config.BLOCK_DEFAULTS
            for part in path:
                node = config.SUITE_SUMMARY_DEFAULTS if part == "summary" else node[part]
            with self.subTest(key=key):
                if o.kind == config.CONSTANT:
                    self.assertEqual(node[name], o.value)
                elif not o.in_place:
                    self.assertNotIn(name, node)

    def test_the_loader_knows_each_old_key_so_none_is_reported_unknown(self):
        cfg, err = load({"task_log": {"statuses": [], "spec_paths": ["a"], "review_point_pattern": "R1"},
                         "estimate": {"spec_paths": ["b"]},
                         "adapter": {"worktree_dir": None, "worktree_links": [], "post_close": []},
                         "suite": {"summary": {"modules_ran_re": "(1)", "modules_cached_re": "(2)"}}})
        self.assertEqual(cfg.unknown_keys, ())
        self.assertNotIn("unknown key", err)

    def test_the_schema_has_the_key_that_took_the_spec_paths(self):
        self.assertEqual(self.schema_prop("spec_paths")["default"], list(config.SPEC_PATHS_DEFAULT))
        self.assertIn("spec_paths", config.PLANE_KEYS)


class UpgradeStatus(UpgradeFixture, unittest.TestCase):
    def keys_step(self, **plane) -> dict[str, Any] | None:
        self.product_json(language="none", **plane)
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return next((s for s in body["steps"] if s["task"] == "plane.json keys"), None)

    def test_it_lists_each_removed_and_merged_key_with_its_replacement(self):
        step = self.keys_step(task_log={"statuses": [], "spec_paths": ["spec/"], "review_point_pattern": "Q1"},
                              estimate={"spec_paths": ["spec/"]},
                              adapter={"worktree_dir": config.WORKTREES_DIR, "worktree_links": [".venv"], "post_close": ["true"]},
                              suite={"summary": {"modules_ran_re": "(1)"}})
        self.assertFalse(step["required"])
        listed = {k["key"]: k for k in step["keys"]}
        self.assertEqual(set(listed), {"task_log.statuses", "task_log.spec_paths", "task_log.review_point_pattern",
                                       "estimate.spec_paths", "adapter.worktree_dir", "adapter.worktree_links",
                                       "adapter.post_close", "suite.summary.modules_ran_re"})
        self.assertEqual(listed["task_log.statuses"]["outcome"], "removed")
        self.assertEqual((listed["task_log.spec_paths"]["outcome"], listed["task_log.spec_paths"]["replacement"]),
                         ("merged", "spec_paths"))
        self.assertEqual(listed["adapter.worktree_dir"]["replacement"], "worktrees.dir")
        self.assertEqual(listed["adapter.post_close"]["replacement"], "reconcile.hooks")
        self.assertEqual(listed["task_log.review_point_pattern"]["replacement"], "ids.review_point.pattern")
        self.assertIn("move `task_log.spec_paths` to `spec_paths`", step["change"])
        self.assertIn("delete `task_log.statuses`", step["change"])

    def test_a_product_that_sets_none_has_no_such_step(self):
        self.assertIsNone(self.keys_step(spec_paths=["spec/"], worktrees={"dir": config.WORKTREES_DIR}))

    def test_a_constant_is_listed_only_when_it_is_set_to_another_value(self):
        with mock.patch.dict(config.KEY_OUTCOMES, TEST_CONSTANT):
            step = self.keys_step(board={"refresh_minutes": 9})
            (found,) = step["keys"]
            self.assertEqual((found["key"], found["outcome"], found["constant"], found["set"]),
                             (CONSTANT_KEY, "constant", 5, 9))
            self.assertIn("file a plane proposal to keep the key", step["change"])
            self.assertIsNone(self.keys_step(board={"refresh_minutes": 5}))
            self.assertIsNone(self.keys_step(board={}))


if __name__ == "__main__":
    unittest.main()
