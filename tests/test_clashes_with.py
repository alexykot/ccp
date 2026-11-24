"""SPEC §5, §16.3: a task may record `clashes_with`, and under `parallel.schedule: clashes`, the default, claim rule 3
and `ccp tasks next` keep apart only tasks that clash, whatever their paths; under `paths`, the field is not read."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr

from ccp import config, parallel, tasklog
from tests.parallel_claims_fixture import task
from tests.toolkit_fixture import ToolkitFixture


def clashing(tid: str, scope_in: str, with_: list[str], extra: str = "") -> str:
    ids = ", ".join(f'"{x}"' for x in with_)
    return task(tid, scope_in, extra=f"clashes_with: [{ids}]\n{extra}")


class Fixture(ToolkitFixture):
    def plane(self, **par):
        self.edit_plane(lambda cfg: cfg.update(parallel=par))

    def task(self, tid: str, scope_in: str, with_: list[str] | None = None, extra: str = ""):
        text = clashing(tid, scope_in, with_, extra) if with_ is not None else task(tid, scope_in, extra=extra)
        self.write(f"docs/delivery/tasks/{tid}.md", text)

    def start(self):
        (self.q / "work.json").write_text(json.dumps({"status": "running"}))
        code, _, out, err = self.ccp("tasks", "claim", "0002", root=self.main)
        self.assertEqual(code, 0, out + err)


class Check(Fixture, unittest.TestCase):
    def test_a_clash_naming_no_task_or_the_task_itself_is_refused(self):
        self.task("0002-second", "`src/a.py`", ["0003-third"])
        self.task("0003-third", "`src/b.py`", ["0099-none"])
        self.task("0004-fourth", "`src/c.py`", ["0004-fourth"])
        tasklog.write_index(config.load(self.main))
        code, _, out, err = self.ccp("tasks", "check", root=self.main)
        self.assertEqual(code, 1, out + err)
        lines = [ln for ln in (out + err).splitlines() if "clashes_with" in ln]
        self.assertEqual(len(lines), 2, out + err)
        self.assertTrue(any("0003-third.md" in ln and "0099-none" in ln for ln in lines), lines)
        self.assertTrue(any("0004-fourth.md" in ln and "which is the task itself" in ln for ln in lines), lines)
        self.assertNotIn("0002-second.md: clashes_with", out + err)
        self.assertNotIn("depends_on `0099-none`", out + err)

    def test_a_missing_dependency_reads_as_before(self):
        self.write("docs/delivery/tasks/0003-third.md",
                   task("0003-third", "`src/b.py`").replace("depends_on: []", 'depends_on: ["0099-none"]'))
        errs = tasklog.check(config.load(self.main))
        self.assertTrue(any("0003-third.md: depends_on `0099-none`, which does not exist" in e for e in errs), errs)


class Schedule(Fixture, unittest.TestCase):
    def load(self, **par):
        self.plane(**par)
        err = io.StringIO()
        with redirect_stderr(err):
            cfg = config.load(self.main)
        return cfg, err.getvalue()

    def test_the_schedule_defaults_to_clashes_and_takes_only_its_two_values(self):
        cfg, err = self.load(max_in_flight=2)
        self.assertEqual(parallel.settings(cfg)["schedule"], "clashes")
        cfg, err = self.load(max_in_flight=2, schedule="paths")
        self.assertEqual(parallel.settings(cfg)["schedule"], "paths")
        self.assertNotIn("schedule", err)
        self.plane(max_in_flight=2, schedule="files")
        with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
            config.load(self.main)
        self.assertIn("parallel.schedule", str(cm.exception))


class Claims(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane(max_in_flight=3, schedule="clashes")
        self.task("0002-second", "`src/app/pool.py`")
        self.task("0003-third", "`src/app/views.py`", ["0002-second"])
        self.task("0004-fourth", "`src/app/pool.py`")
        self.task("0006-sixth", "an operator step, nothing in the repo")
        self.start()

    def claim(self, n):
        return self.ccp("tasks", "claim", n, root=self.main)

    def test_meeting_paths_start_together_and_a_recorded_clash_keeps_apart(self):
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("0003-third clashes with in-flight 0002-second (clashes_with, rule 3)", err)
        code, _, out, err = self.claim("0006")
        self.assertEqual(code, 7, out + err)
        self.assertIn("rule 2", err)

    def test_the_clash_is_symmetric_and_the_naming_task_is_the_one_in_flight(self):
        self.task("0002-second", "`src/app/pool.py`", ["0004-fourth"])  # recorded on the in-flight task
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 7, out + err)
        self.assertIn("0004-fourth clashes with in-flight 0002-second", err)

    def test_parallel_true_does_not_lift_a_recorded_clash(self):
        self.task("0003-third", "`src/app/views.py`", ["0002-second"], extra="parallel: true\n")
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("clashes_with, rule 3", err)

    def test_a_task_with_no_path_still_runs_alone_and_exclusive_paths_still_apply(self):
        self.plane(max_in_flight=3, schedule="clashes", exclusive=["src/app/views.py"])
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("clashes with in-flight 0002-second", err)  # rule 3 speaks first
        self.task("0003-third", "`src/app/views.py`")
        self.task("0002-second", "`src/app/pool.py`, `src/app/views.py`")  # in flight: both meet the entry
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 7, out + err)
        self.assertIn("rule 4", err)

    def test_under_paths_clashes_with_is_not_read(self):
        self.plane(max_in_flight=3, schedule="paths")
        code, _, out, err = self.claim("0003")
        self.assertEqual(code, 0, out + err)  # paths differ, so it joins despite its recorded clash
        code, _, out, err = self.claim("0004")
        self.assertEqual(code, 7, out + err)
        self.assertIn("`src/app/pool.py` meets in-flight 0002-second's `src/app/pool.py` (rule 3)", err)


class Predicate(unittest.TestCase):
    def cfg(self, schedule: str) -> config.Config:
        return config.Config(root=parallel.Path("."), project_id="demo", task_log={}, package_docs=None,
                             parallel={**config.PARALLEL_DEFAULTS, "schedule": schedule})

    def test_a_clash_with_a_task_that_is_done_or_dropped_holds_nothing_back(self):
        a = {"task_id": "0002-a", "status": "pending", "clashes_with": ["0003-b"], "_text": ""}
        for status, held in (("pending", True), ("done", False), ("dropped", False)):
            b = {"task_id": "0003-b", "status": status, "_text": ""}
            self.assertEqual(parallel.kept_apart(self.cfg("clashes"), a, b) is not None, held, status)
            self.assertEqual(parallel.kept_apart(self.cfg("clashes"), b, a) is not None, held, status)

    def test_paths_schedule_returns_the_meeting_paths_and_clashes_the_clash(self):
        a = {"task_id": "0002-a", "paths": ["src/x.py"], "clashes_with": ["0003-b"], "_text": ""}
        b = {"task_id": "0003-b", "paths": ["src/x.py"], "_text": ""}
        self.assertEqual(parallel.kept_apart(self.cfg("paths"), a, b), parallel.Apart("paths", "src/x.py", "src/x.py"))
        self.assertEqual(parallel.kept_apart(self.cfg("clashes"), a, b), parallel.Apart("clash"))
        c = {"task_id": "0004-c", "paths": ["src/x.py"], "_text": ""}
        self.assertIsNone(parallel.kept_apart(self.cfg("clashes"), a, c))


class Next(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plane(max_in_flight=3, schedule="clashes")
        self.task("0002-second", "`src/app/pool.py`")
        self.start()
        self.task("0003-third", "`src/app/views.py`", ["0002-second"])
        self.task("0004-fourth", "`src/app/pool.py`", ["0003-third"])
        self.task("0008-eighth", "`src/app/pool.py`")

    def test_a_clash_is_passed_over_and_a_later_task_never_overtakes_a_clash_behind_it(self):
        code, body, out, err = self.ccp("tasks", "next", "--json", root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(body["task_id"], "0008-eighth")
        self.assertEqual([p["task_id"] for p in body["passed_over"]], ["0003-third", "0004-fourth"])
        self.assertIn("0002-second", body["passed_over"][0]["why"])
        self.assertIn("0004-fourth clashes with passed-over 0003-third", body["passed_over"][1]["why"])


if __name__ == "__main__":
    unittest.main()
