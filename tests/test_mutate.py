"""`ccp mutate` (SPEC §20.6): a mutant is killed only when the named test fails, and the worktree is
restored after each."""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, mutate, runs
from tests.test_toolkit import PLANE, ToolkitFixture, git

sys.path.insert(0, str(PLANE / "scripts" / "observability"))
import lib  # noqa: E402

CALC = "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n\n\ndef unused(a):\n    return a * 2\n"
TESTS = """import unittest

from calc import add, sub


class CalcTest(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 1), 2)

    def test_sub(self):
        self.assertEqual(sub(3, 1), 2)
"""
ADD = "test_calc.CalcTest.test_add"
COMMAND = f"{shlex.quote(sys.executable)} -B -m unittest -q {{test}}"


class MutateFixture(ToolkitFixture):
    def setUp(self):
        super().setUp()
        self.write("docs/delivery/plane.json", json.dumps({**self.PLANE_JSON, "mutate": {"command": COMMAND}}))
        self.write("calc.py", CALC)
        self.write("test_calc.py", TESTS)
        git(self.main, "add", "docs/delivery/plane.json", "calc.py", "test_calc.py")
        git(self.main, "commit", "-q", "-m", "calc")
        git(self.main, "push", "-q", "origin", "main")
        self.run_id = runs.open_run(self.q, config.load(self.main), "0002-second", "verify", prompt_ref=None,
                                    note=None, supersede=False)["run_id"]
        self.mut = self.make_wt("mut")

    def make_wt(self, kind: str, task: str = "0002") -> Path:
        head = git(self.main, "rev-parse", "origin/main")
        code, body, _, err = self.ccp("wt", "create", "--kind", kind, "--task", task, "--sha", head, root=self.main)
        self.assertEqual(code, 0, err)
        return Path(body["path"])

    def mutate(self, *mutants: str, test: str = ADD, root: Path | None = None, run: str | None = None):
        args = ["mutate", "--run", run or self.run_id, "--test", test]
        for m in mutants:
            args += ["--mutant", m]
        return self.ccp(*args, root=root or self.mut)

    def rows(self) -> list[dict]:
        return runs.load(self.q, self.run_id).get("mutation", [])

    def patch_file(self, edits: dict[str, str]) -> Path:
        """A patch (outside the worktree) that writes `edits` ({path: text}) over the worktree's tree."""
        for rel, text in edits.items():
            (self.mut / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.mut / rel).write_text(text)
        new = [rel for rel in edits if not git(self.mut, "ls-files", rel)]
        if new:
            git(self.mut, "add", "-N", *new)
        patch = Path(self._tmp.name) / f"m{len(list(Path(self._tmp.name).glob('m*.patch')))}.patch"
        patch.write_text(git(self.mut, "diff") + "\n")
        if new:
            git(self.mut, "reset", "-q", *new)
        for rel in edits:
            if rel in new:
                (self.mut / rel).unlink()
                d = (self.mut / rel).parent
                while d != self.mut and not any(d.iterdir()):
                    d.rmdir()
                    d = d.parent
            else:
                git(self.mut, "checkout", "--", rel)
        return patch

    def tree(self) -> list[str]:
        """Every path in the worktree, directories included (Git's own file aside)."""
        return sorted(str(p.relative_to(self.mut)) for p in self.mut.rglob("*") if p.name != ".git")

    def set_mutate(self, **knobs) -> None:
        """The mutation worktree's own plane.json (ccp reads the checkout it runs in)."""
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        body["mutate"] = {**body["mutate"], **knobs}
        p.write_text(json.dumps(body))


class Outcomes(MutateFixture, unittest.TestCase):
    def test_a_mutant_the_test_catches_is_killed_and_the_file_restored(self):
        code, body, _, err = self.mutate("calc.py:a + b=>a - b")
        self.assertEqual(code, 0, err)
        self.assertEqual((body["killed"], body["survived"]), (1, 0))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        row = self.rows()[0]
        self.assertEqual((row["outcome"], row["test"], row["mutant"], row["kind"], row["files"]),
                         ("killed", ADD, 1, "text", ["calc.py"]))
        self.assertNotEqual(row["exit_code"], 0)
        ev = [e for e in self.events() if (e["type"], e["op"]) == ("run", "recorded")]
        self.assertEqual([(e["payload"]["run_id"], e["payload"]["killed"], e["payload"]["survived"]) for e in ev],
                         [(self.run_id, 1, 0)])
        self.assertIn("FAIL: test_add", Path(body["log"]).read_text())

    def test_a_mutant_the_test_does_not_reach_survives(self):
        code, body, _, err = self.mutate("calc.py:a * 2=>a * 3")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.rows()[0]["outcome"], "survived")
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_mutant_that_breaks_only_another_test_survives(self):
        code, _, _, err = self.mutate("calc.py:return a - b=>return a + b")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.rows()[0]["outcome"], "survived")
        code, _, _, err = self.mutate("calc.py:return a - b=>return a + b", test="test_calc.CalcTest.test_sub")
        self.assertEqual((code, self.rows()[1]["outcome"]), (0, "killed"), err)

    def test_each_mutant_runs_alone_on_the_restored_tree(self):
        code, body, _, err = self.mutate("calc.py:a * 2=>a * 3", "calc.py:a + b=>a - b", "calc.py:a * 2=>a * 4")
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["outcome"]) for r in self.rows()],
                         [(1, "survived"), (2, "killed"), (3, "survived")])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_patch_is_a_mutant(self):
        (self.mut / "calc.py").write_text(CALC.replace("a + b", "a + b + 1"))
        patch = Path(self._tmp.name) / "m.patch"
        patch.write_text(git(self.mut, "diff") + "\n")
        git(self.mut, "checkout", "--", "calc.py")
        code, body, _, err = self.mutate(str(patch))
        self.assertEqual(code, 0, err)
        self.assertEqual((self.rows()[0]["kind"], self.rows()[0]["files"], self.rows()[0]["outcome"]),
                         ("patch", ["calc.py"], "killed"))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_patch_that_adds_a_file_is_undone(self):
        (self.mut / "calc.py").write_text(CALC.replace("a + b", "helper(a, b)") + "from extra import helper\n")
        (self.mut / "extra.py").write_text("def helper(a, b):\n    return a + b\n")
        git(self.mut, "add", "-N", "extra.py")
        patch = Path(self._tmp.name) / "m.patch"
        patch.write_text(git(self.mut, "diff") + "\n")
        git(self.mut, "reset", "-q", "extra.py")
        (self.mut / "extra.py").unlink()
        git(self.mut, "checkout", "--", "calc.py")
        code, body, _, err = self.mutate(str(patch))
        self.assertEqual((code, self.rows()[0]["outcome"]), (1, "survived"), err)
        self.assertEqual(sorted(self.rows()[0]["files"]), ["calc.py", "extra.py"])
        self.assertFalse((self.mut / "extra.py").exists())
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_hang_is_killed_at_the_timeout(self):
        self.set_mutate(timeout_seconds=2)
        code, _, _, err = self.mutate("calc.py:return a + b=>while True: pass")
        self.assertEqual(code, 0, err)
        self.assertEqual((self.rows()[0]["outcome"], self.rows()[0]["timed_out"]), ("killed", True))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_patch_that_adds_a_directory_leaves_none(self):
        before = self.tree()
        patch = self.patch_file({"pkg/sub/extra.py": "X = 1\n", "calc.py": CALC.replace("a + b", "a - b")})
        code, _, _, err = self.mutate(str(patch))
        self.assertEqual((code, self.rows()[0]["outcome"]), (0, "killed"), err)
        self.assertEqual(self.tree(), before)

    def test_the_record_carries_no_mutant_text(self):
        old1, new1, old2, new2 = "OLDTXT-q7v3k", "NEWTXT-m2x8w", "OLDPATCH-h4j9z", "NEWPATCH-c6t1r"
        marked = CALC.replace("a * 2", f"a * 2  # {old1}").replace("a - b", f"a - b  # {old2}")
        (self.mut / "calc.py").write_text(marked)
        git(self.mut, "commit", "-q", "-m", "markers", "calc.py")
        patch = self.patch_file({"calc.py": marked.replace(old2, new2)})
        code, _, _, err = self.mutate(f"calc.py:{old1}=>{new1}", str(patch), "calc.py:a + b=>a + b + 1")
        self.assertEqual((code, len(self.rows())), (1, 3), err)
        self.assertEqual((self.mut / "calc.py").read_text(), marked)
        raw = runs.path(self.q, self.run_id).read_text() + (self.q / "observability/events.jsonl").read_text()
        for text in (old1, new1, old2, new2, "a + b + 1"):
            self.assertNotIn(text, raw)
        self.assertEqual([len(r["digest"]) for r in self.rows()], [12, 12, 12])

    def test_a_sigterm_restores_the_files(self):
        self.set_mutate(command="grep -q KILLME calc.py && kill -TERM $PPID && sleep 5; " + COMMAND)
        code, _, _, err = self.mutate("calc.py:a + b=>a + b  # KILLME")
        self.assertEqual(code, 143, err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertEqual(self.rows(), [])

    def sigterm_inside(self, owner, name: str):
        """Run two mutants with a SIGTERM sent from inside `owner.<name>`, during its first call. A
        SIGTERM the call does not take raises here rather than ending the test process."""
        real, calls = getattr(owner, name), []

        def hit(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                os.kill(os.getpid(), signal.SIGTERM)
            return real(*a, **kw)

        def untaken(_sig, _frame):
            raise AssertionError("the SIGTERM reached past the call")
        old = signal.signal(signal.SIGTERM, untaken)
        try:
            with mock.patch.object(owner, name, hit):
                return self.mutate("calc.py:a + b=>a - b", "calc.py:a * 2=>a * 3")
        finally:
            signal.signal(signal.SIGTERM, old)

    def test_a_sigterm_while_a_mutant_is_recorded_ends_the_call_after_it(self):
        code, _, _, err = self.sigterm_inside(runs, "save")
        self.assertEqual(code, 143, err)
        self.assertEqual([(r["mutant"], r["outcome"]) for r in self.rows()], [(1, "killed")])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertNotIn(("run", "recorded"), [(e["type"], e["op"]) for e in self.events()])

    def test_a_sigterm_during_a_restore_lets_it_finish(self):
        code, _, _, err = self.sigterm_inside(mutate, "_restore")
        self.assertEqual(code, 143, err)
        self.assertEqual(self.rows(), [])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_sigterm_before_the_unmutated_run_runs_nothing(self):
        code, _, _, err = self.sigterm_inside(mutate, "parse")
        self.assertEqual((code, self.rows()), (143, []), err)
        self.assertFalse(mutate.log_path(self.q, self.run_id).exists())


class Interrupted(MutateFixture, unittest.TestCase):
    """`ccp mutate` in its own process, sent a SIGTERM while the test command runs."""

    def interrupt(self, sleep_when: str, *mutants: str) -> tuple[int, int]:
        """Send the call a SIGTERM once the command is asleep (it sleeps when `sleep_when`, a shell
        test, holds); its exit code and the sleeping command's process group."""
        pid = Path(self._tmp.name) / "child.pid"
        self.set_mutate(command=f"if {sleep_when}; then echo $$ > {shlex.quote(str(pid))}; sleep 60; fi; " + COMMAND)
        args = [sys.executable, str(PLANE / "bin/ccp"), "--root", str(self.mut), "mutate", "--run", self.run_id,
                "--test", ADD]
        for m in mutants:
            args += ["--mutant", m]
        p = subprocess.Popen(args, cwd=str(self.mut), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while not (pid.is_file() and pid.read_text().strip()):
                self.assertIsNone(p.poll(), "the call ended before its command slept")
                self.assertLess(time.monotonic(), deadline, "the command never slept")
                time.sleep(0.05)
            group = int(pid.read_text())
            p.send_signal(signal.SIGTERM)
            code = p.wait(timeout=30)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
        return code, group

    def assert_gone(self, group: int) -> None:
        deadline = time.monotonic() + 10
        while True:
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return
            except PermissionError:
                pass
            if time.monotonic() > deadline:
                os.killpg(group, signal.SIGKILL)
                self.fail("the test command was left running")
            time.sleep(0.05)

    def test_during_a_mutant_test(self):
        before = self.tree()
        patch = self.patch_file({"pkg/extra.py": "X = 1\n"})
        code, group = self.interrupt("test -f pkg/extra.py", str(patch))
        self.assert_gone(group)
        self.assertEqual(code, 143)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.rows(), [])

    def test_during_the_unmutated_run(self):
        before = self.tree()
        code, group = self.interrupt("! grep -q MUTANT calc.py", "calc.py:a + b=>a - b  # MUTANT")
        self.assert_gone(group)
        self.assertEqual(code, 143)
        self.assertEqual(self.tree(), before)
        self.assertEqual(self.rows(), [])


class Refusals(MutateFixture, unittest.TestCase):
    def refused(self, code_want: int, *mutants: str, **kw) -> str:
        code, _, _, err = self.mutate(*mutants, **kw)
        self.assertEqual(code, code_want, err)
        self.assertEqual(self.rows(), [])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        return err

    def test_outside_a_mutation_worktree(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("ver"))
        self.refused(2, "calc.py:a + b=>a - b", root=self.main)

    def test_a_mutation_worktree_of_another_task(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("mut", task="0001"))

    def test_old_text_absent_or_ambiguous(self):
        self.refused(2, "calc.py:a / b=>a - b")
        self.refused(2, "calc.py:def =>fed ")
        self.refused(2, "calc.py:a + b=>a - b", "calc.py:nope=>x")  # one bad mutant: none runs

    def test_a_mutant_that_is_no_file_or_leaves_the_worktree(self):
        self.refused(2, "no-such.patch")
        self.refused(2, "../calc.py:a + b=>a - b")
        self.refused(2, "missing.py:a=>b")
        self.refused(2, "/etc/hosts:a=>b")
        self.refused(2, "calc.py=>x")
        self.refused(2, "calc.py:=>x")

    def test_no_test_named(self):
        self.refused(2, "calc.py:a + b=>a - b", test=" ")

    def test_a_closed_run(self):
        rec = runs.load(self.q, self.run_id)
        rec["reported_at"] = "2026-11-10T00:00:00Z"
        runs.save(self.q, rec)
        self.refused(2, "calc.py:a + b=>a - b")

    def test_no_command(self):
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        del body["mutate"]
        p.write_text(json.dumps(body))
        self.refused(2, "calc.py:a + b=>a - b")

    def test_a_test_that_fails_unmutated(self):
        (self.mut / "test_calc.py").write_text(TESTS.replace("add(1, 1), 2", "add(1, 1), 3"))
        self.refused(1, "calc.py:a + b=>a - b")


class Ledger(unittest.TestCase):
    def test_a_mutate_event_needs_its_counts(self):
        ev = {"at": "2026-11-11T00:00:00Z", "project_id": "demo", "task_id": "0002-second", "actor": "task-runner",
              "type": "run", "op": "recorded", "payload": {"run_id": "r", "mutants": 2, "killed": 1, "survived": 1}}
        self.assertEqual(lib.validate_event(ev), [])
        for key in ("run_id", "mutants", "killed", "survived"):
            bad = {**ev, "payload": {k: v for k, v in ev["payload"].items() if k != key}}
            self.assertEqual(lib.validate_event(bad), [f"payload missing {key}"])


class PatchPaths(unittest.TestCase):
    def test_numstat_names_plain_and_renamed_paths(self):
        from ccp import mutate
        out = "1\t1\tcalc.py\x000\t0\t\x00old.py\x00new.py\x00-\t-\tbin.dat\x00"
        self.assertEqual(mutate._numstat_paths(out), ["calc.py", "old.py", "new.py", "bin.dat"])


class MutateConfig(unittest.TestCase):
    def test_the_block_is_checked(self):
        from tests.helpers import Product
        for bad in ({"command": "run-one-test"}, {"command": ""}, {"timeout_seconds": 0}, {"other": 1}):
            p = Product({"mutate": bad})
            try:
                with self.assertRaises(config.ConfigError, msg=bad):
                    p.cfg
            finally:
                p.cleanup()
        p = Product({"mutate": {"command": "t {test}"}})
        try:
            self.assertEqual(p.cfg.mutate, {"command": "t {test}", "timeout_seconds": 600})
        finally:
            p.cleanup()

    def test_the_schema_lists_the_block(self):
        schema = json.loads((PLANE / "contracts/plane_config.schema.json").read_text())
        self.assertEqual(set(schema["properties"]["mutate"]["properties"]), set(config.MUTATE_DEFAULTS))


if __name__ == "__main__":
    unittest.main()
