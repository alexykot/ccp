"""`ccp tasks check` refuses a refactor whose dod_check re-runs the gate or full lane (SPEC §20.3, §21.1)."""
from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from ccp import cli, tasklog
from tests.helpers import Product

CHECKS = """## dod_checks

- id: `code-01`
  story: As a maintainer, the registry has one owner.
  setup: {setup}
  steps:
{steps01}
  expect: {expect}

- id: `code-02`
  story: As a maintainer, the old copy is gone.
  steps:
{steps02}
  expect: no line.

"""


class RefactorRerunsTheGate(unittest.TestCase):
    def setUp(self):
        self.p = self.product({"lanes": {"gate": ["scripts/gate.sh"]}})

    def tearDown(self):
        self.p.cleanup()

    def product(self, suite, architect=True):
        p = Product({**({"architect": {}} if architect else {}), "suite": suite})
        self.addCleanup(p.cleanup)
        return p

    def task(self, steps01, p=None, tid="0001-r", kind="refactor", status="pending",
             steps02="    1. Run `git grep -n old_registry`.", setup="a checkout.", expect="exit 0."):
        p = p or self.p
        f = p.task(tid, status)
        text = f.read_text()
        if kind == "refactor":
            text = text.replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]')
        start, end = text.index("## dod_checks"), text.index("## Implementation notes")
        f.write_text(text[:start] + CHECKS.format(steps01=steps01, steps02=steps02, setup=setup, expect=expect)
                     + text[end:])
        p.index()

    def gate_errs(self, p=None):
        return [e for e in tasklog.check((p or self.p).cfg) if "`code-0" in e]

    def test_a_refactor_whose_step_runs_the_gate_lane_fails_tasks_check_naming_task_check_and_lane(self):
        self.task("    1. Run `scripts/gate.sh`.")
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["--root", str(self.p.root), "tasks", "check"])
        self.assertEqual(code, 1)
        line = next(x for x in out.getvalue().splitlines() if "`code-0" in x)
        self.assertIn("docs/delivery/tasks/0001-r.md", line)
        self.assertIn("`code-01`", line)
        self.assertIn("`gate`", line)
        self.assertNotIn("`code-02`", out.getvalue())

    def test_a_refactor_that_runs_only_its_own_commands_passes(self):
        self.task("    1. Run `python3 -m unittest tests.test_registry`.")
        self.assertEqual(tasklog.check(self.p.cfg), [])

    def test_the_full_lane_is_refused_too_and_both_are_named_when_one_command_runs_both(self):
        p = self.product({"lanes": {"gate": ["scripts/gate.sh"], "full": ["make", "test"]}})
        self.task("    1. Run `make test`.", p=p)
        errs = self.gate_errs(p)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("`full`", errs[0])
        self.assertNotIn("`gate`", errs[0])
        same = self.product({"lanes": {"gate": ["scripts/gate.sh"], "full": ["scripts/gate.sh"]}})
        self.task("    1. Run `scripts/gate.sh`.", p=same)
        errs = self.gate_errs(same)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("`gate`", errs[0])
        self.assertIn("`full`", errs[0])

    def test_the_lanes_judged_are_those_suite_roles_names(self):
        p = self.product({"lanes": {"verify": ["scripts/verify.sh"], "gate": ["scripts/quick.sh"]},
                          "roles": {"gate": "verify", "full": "all"}})
        self.task("    1. Run `scripts/quick.sh`.", p=p)
        self.assertEqual(self.gate_errs(p), [])
        self.task("    1. Run `scripts/verify.sh`.", p=p)
        errs = self.gate_errs(p)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("`verify`", errs[0])

    def test_the_lane_command_run_as_a_whole_command_in_its_usual_forms(self):
        forms = ("    1. Run `./scripts/gate.sh`.",
                 "    1. Run `CI=1 scripts/gate.sh && git branch --list 'state/*'`.",
                 "    1. Run `git status; scripts/gate.sh`.",
                 "    1. Run `ccp suite run --run r/implement --lane part -- scripts/gate.sh`.",
                 "    1. Change the seed, then run\n       `scripts/gate.sh`.",
                 "    1. Read the notes.\n    2. Run `scripts/gate.sh`.",
                 "    1. Run `env -u QUEUE_ROOT scripts/gate.sh`.",
                 "    1. Run `env CI=1 -u QUEUE_ROOT bash scripts/gate.sh`.",
                 "    1. Run `sh scripts/gate.sh`.",
                 "    1. Run `time scripts/gate.sh`.",
                 "    1. Run `timeout 900 scripts/gate.sh`.",
                 "    1. Run `scripts/gate.sh 2>&1 | tail -3`.",
                 "    1. Run `scripts/gate.sh > out.log`.",
                 "    1. Run `scripts/gate.sh &>out.log`.")
        for form in forms:
            self.task(form)
            self.assertEqual(len(self.gate_errs()), 1, form)

    def test_a_lane_declared_with_its_wrapper_matches_its_own_spelling(self):
        p = self.product({"lanes": {"gate": ["bash", "scripts/gate.sh"]}})
        self.task("    1. Run `bash scripts/gate.sh`.", p=p)
        self.assertEqual(len(self.gate_errs(p)), 1)

    def test_the_lane_argv_inside_another_command_is_not_a_run_of_the_lane(self):
        p = self.product({"lanes": {"full": ["pytest"]}})
        self.task("    1. Run `pytest tests/test_registry.py`.", p=p)
        self.assertEqual(self.gate_errs(p), [])
        self.task("    1. Run `pytest tests/test_registry.py > out.log`.", p=p)
        self.assertEqual(self.gate_errs(p), [])
        for form in ("    1. Run `cat scripts/gate.sh`.", "    1. Run `scripts/gate.sh.bak`.",
                     "    1. Run `timeout scripts/gate.sh`.", "    1. Run `env -u scripts/gate.sh`.",
                     "    1. Run `scripts/gate.sh 2`."):
            self.task(form)
            self.assertEqual(self.gate_errs(), [], form)

    def test_ccp_suite_run_of_the_declared_lane_is_refused_and_one_with_its_own_command_is_not(self):
        for form in ("    1. Run `ccp suite run --run r/implement --lane gate`.",
                     "    1. Run `QUEUE_ROOT=/q bin/ccp suite run --lane=gate --full`."):
            self.task(form)
            self.assertEqual(len(self.gate_errs()), 1, form)
        for form in ("    1. Run `ccp suite run --lane gate -- python3 -m unittest tests.test_registry`.",
                     "    1. Run `ccp suite run --lane part`."):
            self.task(form)
            self.assertEqual(self.gate_errs(), [], form)

    def test_a_staged_lane_is_matched_by_its_ccp_run_not_by_one_stage(self):
        p = self.product({"lanes": {"gate": [{"name": "lint", "cmd": "scripts/lint.sh"},
                                             {"name": "tests", "cmd": "scripts/test.sh"}]}})
        self.task("    1. Run `scripts/lint.sh`.", p=p)
        self.assertEqual(self.gate_errs(p), [])
        self.task("    1. Run `ccp suite run --lane gate`.", p=p)
        self.assertEqual(len(self.gate_errs(p)), 1)

    def test_only_the_steps_are_read(self):
        self.task("    1. Run `git grep -n registry`.", setup="`scripts/gate.sh` passes on the merge base.",
                  expect="like `scripts/gate.sh`, exit 0.")
        self.assertEqual(self.gate_errs(), [])

    def test_a_feature_a_done_or_dropped_refactor_and_a_product_without_lanes_are_not_judged(self):
        self.task("    1. Run `scripts/gate.sh`.", kind="feature")
        self.task("    1. Run `scripts/gate.sh`.", tid="0002-done", status="done")
        self.task("    1. Run `scripts/gate.sh`.", tid="0003-dropped", status="dropped")
        self.assertEqual(self.gate_errs(), [])
        bare = self.product({})
        self.task("    1. Run `scripts/gate.sh`.", p=bare)
        self.assertEqual(self.gate_errs(bare), [])

    def test_without_the_architect_block_kind_is_not_read(self):
        p = self.product({"lanes": {"gate": ["scripts/gate.sh"]}}, architect=False)
        self.task("    1. Run `scripts/gate.sh`.", p=p)
        self.assertEqual(self.gate_errs(p), [])


if __name__ == "__main__":
    unittest.main()
