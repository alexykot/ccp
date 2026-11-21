"""`ccp mutate` (SPEC §20.6): a mutant is killed only when the named test fails, and the worktree is
restored after each."""
from __future__ import annotations

import hashlib
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
from ccp.queue import QueueError
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
GUARDED = "from limits import FLOOR\n\n\n" + CALC.replace(
    "def add(a, b):\n    return a + b\n",
    "def add(a, b):\n    if a < FLOOR or b < FLOOR:\n        raise ValueError('add takes no negatives')\n"
    "    return a + b\n")
GUARD_TESTS = TESTS + """
    def test_add_refuses_negatives(self):
        with self.assertRaises(ValueError):
            add(-1, 1)
"""
GUARD = "test_calc.CalcTest.test_add_refuses_negatives"
COMMAND = f"{shlex.quote(sys.executable)} -B -m unittest -q {{test}}"


class MutateFixture(ToolkitFixture):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "language": "python"}  # a Python product, its tests unittest's

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

    def make_wt(self, kind: str, task: str = "0002", sha: str | None = None) -> Path:
        head = sha or git(self.main, "rev-parse", "origin/main")
        code, body, _, err = self.ccp("wt", "create", "--kind", kind, "--task", task, "--sha", head, root=self.main)
        self.assertEqual(code, 0, err)
        return Path(body["path"])

    def mutate(self, *mutants: str, test: str = ADD, root: Path | None = None, run: str | None = None,
               reverts: tuple[str, ...] = (), files: tuple[Path, ...] = (), together: bool = False):
        args = ["mutate", "--run", run or self.run_id, "--test", test] + (["--together"] if together else [])
        for m in mutants:
            args += ["--mutant", m]
        for f in files:
            args += ["--mutant-file", str(f)]
        for r in reverts:
            args += ["--revert", r]
        return self.ccp(*args, root=root or self.mut)

    def task_commit(self, files: dict[str, str]) -> str:
        """A commit of the task's change, on its branch off main (not merged): its sha."""
        git(self.main, "checkout", "-q", "-b", "task/0002-second")
        for rel, text in files.items():
            self.write(rel, text)
        git(self.main, "add", *files)
        git(self.main, "commit", "-q", "-m", "the task's change")
        sha = git(self.main, "rev-parse", "HEAD")
        git(self.main, "checkout", "-q", "main")
        return sha

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

    def test_a_method_id_runs_that_method_alone(self):
        code, body, _, err = self.mutate("calc.py:a + b=>a - b", test=ADD)
        self.assertEqual((code, self.rows()[0]["outcome"]), (0, "killed"), err)
        log = Path(body["log"]).read_text()
        self.assertEqual(log.count("Ran 1 test in"), 2)
        self.assertNotIn("Ran 2 tests", log)

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

    def sigterm_inside(self, owner, name: str,
                       mutants: tuple[str, ...] = ("calc.py:a + b=>a - b", "calc.py:a * 2=>a * 3")):
        """Run `mutants` (two by default) with a SIGTERM sent from inside `owner.<name>`, during its first
        call. A SIGTERM the call does not take raises here rather than ending the test process."""
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
                return self.mutate(*mutants)
        finally:
            signal.signal(signal.SIGTERM, old)

    def test_a_sigterm_while_a_mutant_is_recorded_ends_the_call_after_it(self):
        code, _, _, err = self.sigterm_inside(runs, "save")
        self.assertEqual(code, 143, err)
        self.assertEqual([(r["mutant"], r["outcome"]) for r in self.rows()], [(1, "killed")])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertNotIn(("run", "recorded"), [(e["type"], e["op"]) for e in self.events()])

    def test_a_sigterm_while_the_only_mutant_is_recorded_emits_no_event(self):
        code, _, _, err = self.sigterm_inside(runs, "save", ("calc.py:a + b=>a - b",))
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


class NoStaleBytecode(MutateFixture, unittest.TestCase):
    """A same-size mutant restored within the second must leave no bytecode a later run takes for the source:
    Python trusts a `__pycache__` entry whose recorded source mtime (whole seconds) and size still match."""

    PY = shlex.quote(sys.executable)

    def command(self, line: str) -> None:
        p = self.mut / "docs/delivery/plane.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), "mutate": {"command": line}}))

    def cached(self) -> list[str]:
        d = self.mut / "__pycache__"
        return sorted(f.name for f in d.glob("calc.*.pyc")) if d.is_dir() else []

    def test_a_restored_file_keeps_no_compiled_entry_and_the_next_run_reads_the_source(self):
        # the command compiles calc.py itself, as a product's runner may, whatever the environment says
        self.command(f"{self.PY} -m py_compile calc.py && {self.PY} -m unittest -q {{test}}")
        code, body, _, err = self.mutate("calc.py:a + b=>a - b")  # the same size as the source
        self.assertEqual((code, body and body["killed"]), (0, 1), err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertEqual(self.cached(), [])
        r = subprocess.run([sys.executable, "-m", "unittest", "-q", ADD], cwd=self.mut, capture_output=True,
                           text=True, timeout=120, env={k: v for k, v in os.environ.items()
                                                       if k != "PYTHONDONTWRITEBYTECODE"})
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_a_compiled_entry_from_another_source_never_runs_in_place_of_the_mutant(self):
        # an unchecked hash-based entry, compiled from the source as it was: Python imports it whatever the source
        import importlib.util  # noqa: PLC0415
        import py_compile  # noqa: PLC0415
        src = self.mut / "calc.py"
        py_compile.compile(str(src), cfile=importlib.util.cache_from_source(str(src)), doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
        self.assertEqual(len(self.cached()), 1)
        code, body, _, err = self.mutate("calc.py:a + b=>a - b")
        self.assertEqual((code, body and body["killed"]), (0, 1), err)
        self.assertEqual(self.rows()[0]["outcome"], "killed")
        self.assertEqual(src.read_text(), CALC)
        self.assertEqual(self.cached(), [])

    def test_every_run_writes_no_bytecode(self):
        self.command(f'[ "$PYTHONDONTWRITEBYTECODE" = 1 ] && {self.PY} -m unittest -q {{test}}')
        with mock.patch.dict(os.environ):
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
            code, body, _, err = self.mutate("calc.py:a + b=>a - b")
        self.assertEqual((code, body and body["killed"]), (0, 1), err)  # the unmutated run passed too
        self.assertEqual(self.cached(), [])


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

    def test_outside_an_impl_mut_rev_or_ver_worktree(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("mac"))
        self.refused(2, "calc.py:a + b=>a - b", root=self.main)

    def test_a_reviewer_or_verifier_worktree(self):
        for kind in ("rev", "ver"):
            root = self.make_wt(kind)
            code, body, _, err = self.mutate("calc.py:a + b=>a - b", root=root)
            self.assertEqual((code, body["worktree"]), (0, root.name), err)
            self.assertEqual((root / "calc.py").read_text(), CALC)
        self.assertEqual([(r["outcome"], r["worktree"]) for r in self.rows()],
                         [("killed", "rev-0002"), ("killed", "ver-0002")])

    def test_neither_a_mutant_nor_a_revert(self):
        self.refused(2)

    def test_a_worktree_of_another_task(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("mut", task="0001"))
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("rev", task="0001"))

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
        err = self.refused(2, "calc.py:a + b=>a - b")
        for named in ("mutate.command", "{test}", "sh {test}"):  # what to set, a whole-script test's form too
            self.assertIn(named, err)

    def test_a_test_that_fails_unmutated(self):
        (self.mut / "test_calc.py").write_text(TESTS.replace("add(1, 1), 2", "add(1, 1), 3"))
        self.refused(1, "calc.py:a + b=>a - b")


TWO_LINES_OLD = "def add(a, b):\n    return a + b\n"
TWO_LINES_NEW = "def add(a, b):\n    return b - a\n"


class MutantFiles(MutateFixture, unittest.TestCase):
    """`--mutant-file`: the target's path, then `=== old`, the old text, `=== new` and the new text."""

    def mfile(self, text: str) -> Path:
        f = Path(self._tmp.name) / f"mutant{len(list(Path(self._tmp.name).glob('mutant*')))}.txt"
        f.write_text(text)
        return f

    def test_a_mutant_spanning_two_lines_is_killed_and_the_file_restored(self):
        f = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}")
        code, body, _, err = self.mutate(files=(f,))
        self.assertEqual(code, 0, err)
        self.assertEqual((body["killed"], body["survived"]), (1, 0))
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        row = self.rows()[0]
        self.assertEqual((row["outcome"], row["kind"], row["files"]), ("killed", "text", ["calc.py"]))
        self.assertNotIn("return b - a", json.dumps(self.rows()))  # the record carries no mutant text

    def test_each_text_is_exactly_the_bytes_between_its_markers(self):
        f = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}")
        m = mutate.parse_file(self.mut, str(f), self.mut)
        self.assertEqual((m["old"], m["new"], m["files"]), (TWO_LINES_OLD.encode(), TWO_LINES_NEW.encode(), ["calc.py"]))
        same = mutate.parse(self.mut, f"calc.py:{TWO_LINES_OLD}=>{TWO_LINES_NEW}", self.mut)
        self.assertEqual(m["digest"], same["digest"])  # the same substitution as the inline form
        gone = mutate.parse_file(self.mut, str(self.mfile("calc.py\n=== old\n" + TWO_LINES_OLD + "=== new\n")), self.mut)
        self.assertEqual(gone["new"], b"")  # an empty new text deletes the old

    def test_a_relative_path_is_read_from_the_current_directory(self):
        f = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}")
        self.assertEqual(mutate.parse_file(self.mut, f.name, f.parent)["old"], TWO_LINES_OLD.encode())

    def test_mutant_files_come_after_the_mutants_and_before_the_reverts(self):
        f = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}")
        code, _, _, err = self.mutate("calc.py:a * 2=>a * 3", files=(f,))
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["outcome"]) for r in self.rows()], [(1, "survived"), (2, "killed")])
        head = self.task_commit({"calc.py": GUARDED, "test_calc.py": GUARD_TESTS, "limits.py": "FLOOR = 0\n"})
        rev = self.make_wt("rev", sha=head)
        guard = self.mfile("calc.py\n=== old\n    if a < FLOOR or b < FLOOR:\n"
                           "        raise ValueError('add takes no negatives')\n=== new\n")
        code, _, _, err = self.mutate("calc.py:a * 2=>a * 3", test=GUARD, root=rev, reverts=("calc.py:5-6",),
                                      files=(guard,))
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["kind"], r["outcome"]) for r in self.rows()[2:]],
                         [(1, "text", "survived"), (2, "text", "killed"), (3, "revert", "killed")])
        self.assertEqual((rev / "calc.py").read_text(), GUARDED)

    def test_a_part_missing_is_refused_and_nothing_runs(self):
        for text in (f"calc.py\n=== old\n{TWO_LINES_OLD}",  # no `=== new`
                     f"calc.py\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}",  # no `=== old`
                     f"\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}",  # no file
                     f"=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}",  # no file, the marker first
                     f"calc.py\n=== old\n=== new\n{TWO_LINES_NEW}",  # no old text
                     f"calc.py\n=== new\n{TWO_LINES_NEW}=== old\n{TWO_LINES_OLD}",  # the markers swapped
                     ""):
            code, _, _, err = self.mutate(files=(self.mfile(text),))
            self.assertEqual(code, 2, (text, err))
            self.assertEqual(self.rows(), [])
            self.assertEqual((self.mut / "calc.py").read_text(), CALC)
            self.assertNotIn("Ran ", err)

    def test_old_text_absent_a_missing_target_or_no_such_file_is_refused(self):
        for f in (self.mfile("calc.py\n=== old\nreturn a / b\n=== new\nx\n"),
                  self.mfile(f"missing.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}"),
                  self.mfile(f"../calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}"),
                  Path(self._tmp.name) / "no-such-mutant.txt"):
            code, _, _, err = self.mutate(files=(f,))
            self.assertEqual(code, 2, (f, err))
            self.assertEqual(self.rows(), [])


class Reverts(MutateFixture, unittest.TestCase):
    """`--revert`: the merge base's version of a file, or of the changes a line range touches."""

    def setUp(self):
        super().setUp()
        self.head = self.task_commit({"calc.py": GUARDED, "test_calc.py": GUARD_TESTS, "limits.py": "FLOOR = 0\n"})
        self.rev = self.make_wt("rev", sha=self.head)

    def test_a_reverted_guard_is_killed_and_the_tree_restored(self):
        before = self.tree_of(self.rev)
        code, body, _, err = self.mutate(test=GUARD, root=self.rev, reverts=("calc.py:5-6",))
        self.assertEqual(code, 0, err)
        self.assertEqual(body["merge_base"], git(self.main, "rev-parse", "origin/main"))
        row = self.rows()[0]
        self.assertEqual((row["kind"], row["files"], row["outcome"], row["worktree"]),
                         ("revert", ["calc.py"], "killed", "rev-0002"))
        self.assertEqual(len(row["digest"]), 12)
        self.assertIn("FAIL: test_add_refuses_negatives", Path(body["log"]).read_text())
        self.assertEqual((self.rev / "calc.py").read_text(), GUARDED)
        self.assertEqual(self.tree_of(self.rev), before)

    def test_a_whole_file_from_a_verifier_worktree(self):
        ver = self.make_wt("ver", sha=self.head)
        code, _, _, err = self.mutate(test=GUARD, root=ver, reverts=("calc.py",))
        self.assertEqual((code, self.rows()[0]["outcome"]), (0, "killed"), err)
        self.assertEqual((ver / "calc.py").read_text(), GUARDED)

    def test_a_file_the_change_added_is_removed_for_the_run(self):
        before = self.tree_of(self.rev)
        code, _, _, err = self.mutate(test=ADD, root=self.rev, reverts=("limits.py",))
        self.assertEqual((code, self.rows()[0]["outcome"]), (0, "killed"), err)
        self.assertEqual((self.rev / "limits.py").read_text(), "FLOOR = 0\n")
        self.assertEqual(self.tree_of(self.rev), before)

    def test_reverts_come_after_the_mutants(self):
        code, _, _, err = self.mutate("calc.py:a * 2=>a * 3", test=GUARD, root=self.rev, reverts=("calc.py:5-6",))
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["kind"], r["outcome"]) for r in self.rows()],
                         [(1, "text", "survived"), (2, "revert", "killed")])

    def test_a_revert_that_changes_nothing_or_names_no_file_is_refused(self):
        for spec in ("calc.py:15", "calc.py:5-99", "calc.py:6-5", "docs/delivery/plane.json", "nope.py",
                     "nope.py:1", "../calc.py", "/etc/hosts", "docs"):
            code, _, _, err = self.mutate(test=GUARD, root=self.rev, reverts=(spec,))
            self.assertEqual(code, 2, (spec, err))
            self.assertEqual(self.rows(), [], spec)
            self.assertEqual((self.rev / "calc.py").read_text(), GUARDED, spec)
        self.assertFalse(mutate.log_path(self.q, self.run_id).exists())

    def tree_of(self, root: Path) -> list[str]:
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.name != ".git")


def capture(root: Path, files: tuple[str, ...]) -> Path:
    """Point the worktree's `mutate.command` at one that first appends what each of `files` holds (or
    `<absent>`) to a capture file, then runs the test: what each run saw."""
    cap = root.parent / f"{root.name}-seen.txt"
    dump = "; ".join(f"{{ cat {f} 2>/dev/null || printf '<absent>'; }} >> {shlex.quote(str(cap))}; "
                     f"printf '<<F>>' >> {shlex.quote(str(cap))}" for f in files)
    p = root / "docs/delivery/plane.json"
    body = json.loads(p.read_text())
    body["mutate"] = {"command": f"{dump}; printf '<<RUN>>' >> {shlex.quote(str(cap))}; {COMMAND}"}
    p.write_text(json.dumps(body))
    return cap


def seen(cap: Path) -> list[list[str]]:
    """Per run (the unmutated one first), what each captured file held."""
    return [run.split("<<F>>")[:-1] for run in cap.read_text().split("<<RUN>>")[:-1]]


class FromTheImplementersWorktree(MutateFixture, unittest.TestCase):
    """The implementer runs `ccp mutate` from its own `impl` worktree, on its task branch."""

    def test_a_revert_runs_there_and_puts_back_the_base_of_that_hunk(self):
        self.task_commit({"calc.py": GUARDED, "test_calc.py": GUARD_TESTS, "limits.py": "FLOOR = 0\n"})
        code, body, _, err = self.ccp("wt", "create", "--kind", "impl", "--task", "0002", root=self.main)
        self.assertEqual(code, 0, err)
        impl = Path(body["path"])
        cap = capture(impl, ("calc.py",))
        code, body, _, err = self.mutate(test=GUARD, root=impl, reverts=("calc.py:5",))
        self.assertEqual((code, body["worktree"]), (0, "impl-0002"), err)
        self.assertEqual(seen(cap), [[GUARDED], ["from limits import FLOOR\n\n\n" + CALC]])
        self.assertEqual([(r["kind"], r["outcome"], r["worktree"]) for r in self.rows()],
                         [("revert", "killed", "impl-0002")])
        self.assertEqual((impl / "calc.py").read_text(), GUARDED)


class Unbuilt(MutateFixture, unittest.TestCase):
    """plane.json `mutate.unbuilt_re`: a mutant whose failing run says the code did not build or import is
    `unbuilt`, never a kill."""

    IMPORT_BREAK = "calc.py:def add(a, b):=>def plus(a, b):"  # `from calc import add` fails: an ImportError

    def setUp(self):
        super().setUp()
        self.write("docs/delivery/plane.json", json.dumps(
            {**self.PLANE_JSON, "mutate": {"command": COMMAND, "unbuilt_re": "Failed to import test module"}}))
        git(self.main, "commit", "-q", "-am", "unbuilt_re")
        git(self.main, "push", "-q", "origin", "main")
        self.impl_run = runs.open_run(self.q, config.load(self.main), "0002-second", "implement", prompt_ref=None,
                                      note=None, supersede=False)["run_id"]
        code, body, _, err = self.ccp("wt", "create", "--kind", "impl", "--task", "0002", root=self.main)
        self.assertEqual(code, 0, err)
        self.impl = Path(body["path"])

    def test_a_mutant_that_stops_the_import_is_unbuilt_and_one_the_test_catches_is_killed(self):
        code, body, _, err = self.mutate(self.IMPORT_BREAK, "calc.py:a + b=>a - b", root=self.impl, run=self.impl_run)
        self.assertEqual(code, 1, err)
        rows = runs.load(self.q, self.impl_run)["mutation"]
        self.assertEqual([(r["mutant"], r["outcome"]) for r in rows], [(1, "unbuilt"), (2, "killed")])
        self.assertTrue(all(r["exit_code"] != 0 for r in rows))
        self.assertEqual((body["killed"], body["unbuilt"], body["survived"]), (1, 1, 0))
        self.assertEqual((self.impl / "calc.py").read_bytes(), CALC.encode())
        ev = [e["payload"] for e in self.events() if (e["type"], e["op"]) == ("run", "recorded")]
        self.assertEqual([(e["mutants"], e["killed"], e["unbuilt"], e["survived"]) for e in ev], [(2, 1, 1, 0)])

    def test_with_no_pattern_the_same_mutant_is_a_kill(self):
        self.set_mutate(unbuilt_re=None)
        code, body, _, err = self.mutate(self.IMPORT_BREAK)
        self.assertEqual((code, body["killed"], body["unbuilt"], body["survived"]), (0, 1, 0, 0), err)
        self.assertEqual(self.rows()[0]["outcome"], "killed")

    def test_a_list_of_patterns_any_of_which_marks_a_syntax_error_unbuilt(self):
        self.set_mutate(unbuilt_re=["Failed to import test module", "^SyntaxError: "])
        code, body, _, err = self.mutate("calc.py:def add(a, b):=>def add(a, b)")
        self.assertEqual((code, body["unbuilt"], body["killed"]), (1, 1, 0), err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_run_that_passes_survives_whatever_it_prints(self):
        self.set_mutate(unbuilt_re=r"^Ran \d+ test")  # unittest prints it on a pass too
        code, body, _, err = self.mutate("calc.py:a * 2=>a * 3")
        self.assertEqual((code, body["survived"], body["unbuilt"], body["killed"]), (1, 1, 0, 0), err)
        self.assertEqual(self.rows()[0]["outcome"], "survived")


class RevertInAShallowWorktree(MutateFixture, unittest.TestCase):
    """A verifier whose worktree is a depth-1 clone reverts against the merge base `ccp wt create` recorded."""

    def shallow(self, sha: str) -> tuple[Path, dict]:
        code, body, _, err = self.ccp("wt", "create", "--kind", "ver", "--task", "0002", "--sha", sha, "--shallow",
                                      root=self.main)
        self.assertEqual(code, 0, err)
        return Path(body["path"]), json.loads((self.q / "worktrees" / f"{body['name']}.json").read_text())

    def test_the_recorded_merge_base_is_what_the_revert_puts_back(self):
        start = git(self.main, "rev-parse", "origin/main")
        head = self.task_commit({"calc.py": CALC.replace("a * 2", "a * 3"),
                                 "test_calc.py": TESTS + "\n    def test_unused(self):\n"
                                                         "        from calc import unused\n"
                                                         "        self.assertEqual(unused(1), 3)\n"})
        git(self.main, "push", "-q", "origin", "task/0002-second")
        self.write("later.txt", "the integration branch moves on\n")
        git(self.main, "add", "later.txt")
        git(self.main, "commit", "-q", "-m", "later")
        git(self.main, "push", "-q", "origin", "main")
        ver, st = self.shallow(head)
        self.assertEqual(git(ver, "rev-parse", "--is-shallow-repository"), "true")
        self.assertEqual(st["merge_base"], start)
        code, body, _, err = self.mutate(test="test_calc.CalcTest.test_unused", root=ver, reverts=("calc.py",))
        self.assertEqual(code, 0, err)
        self.assertEqual((body["merge_base"], self.rows()[0]["outcome"], self.rows()[0]["kind"]),
                         (start, "killed", "revert"))
        self.assertEqual((ver / "calc.py").read_text(), CALC.replace("a * 2", "a * 3"))

    def test_with_no_merge_base_recorded_a_revert_is_refused(self):
        git(self.main, "checkout", "-q", "--orphan", "lone")
        git(self.main, "commit", "-q", "-m", "no shared history")
        lone = git(self.main, "rev-parse", "HEAD")
        git(self.main, "checkout", "-q", "-f", "main")
        ver, st = self.shallow(lone)
        self.assertNotIn("merge_base", st)
        code, _, _, err = self.mutate(test=ADD, root=ver, reverts=("calc.py",))
        self.assertEqual(code, 2, err)
        self.assertIn("no merge base", err)
        self.assertEqual(self.rows(), [])


BACKUP = "def add(a, b):\n    return a + b\n"
EITHER_TESTS = """import unittest

import backup
import calc


class EitherTest(unittest.TestCase):
    def test_one_adds(self):
        self.assertTrue(calc.add(1, 1) == 2 or backup.add(1, 1) == 2)
"""
EITHER = "test_either.EitherTest.test_one_adds"
STEPS = 'def run(log):\n    log.append("open")\n    log.append("write")\n    log.append("close")\n    return log\n'
STEPS_TESTS = """import unittest

from steps import run


class StepsTest(unittest.TestCase):
    def test_order(self):
        self.assertEqual(run([]), ["open", "write", "close"])
"""
ORDER = "test_steps.StepsTest.test_order"


class Together(MutateFixture, unittest.TestCase):
    """`--together`: the mutants given, applied as one mutant."""

    def mfile(self, rel: str, old: str, new: str) -> Path:
        f = Path(self._tmp.name) / f"part{len(list(Path(self._tmp.name).glob('part*')))}.txt"
        f.write_text(f"{rel}\n=== old\n{old}=== new\n{new}")
        return f

    def refused(self, *mutants: str, **kw) -> str:
        code, _, _, err = self.mutate(*mutants, together=True, **kw)
        self.assertEqual(code, 2, err)
        self.assertEqual(self.rows(), [])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertFalse(mutate.log_path(self.q, self.run_id).exists())  # not even the unmutated run
        return err

    def test_together_two_files_each_surviving_alone_are_killed(self):
        (self.mut / "backup.py").write_text(BACKUP)
        (self.mut / "test_either.py").write_text(EITHER_TESTS)
        both = ("calc.py:a + b=>a - b", "backup.py:a + b=>a - b")
        code, _, _, err = self.mutate(*both, test=EITHER)
        self.assertEqual((code, [r["outcome"] for r in self.rows()]), (1, ["survived", "survived"]), err)
        code, _, _, err = self.mutate(*both, test=EITHER, together=True)
        self.assertEqual(code, 0, err)
        self.assertEqual([(r["mutant"], r["kind"], r["outcome"]) for r in self.rows()[2:]], [(1, "together", "killed")])
        self.assertEqual(((self.mut / "calc.py").read_text(), (self.mut / "backup.py").read_text()), (CALC, BACKUP))

    def test_together_a_moved_step_is_killed_and_the_file_restored(self):
        (self.mut / "steps.py").write_text(STEPS)
        (self.mut / "test_steps.py").write_text(STEPS_TESTS)
        cut = self.mfile("steps.py", '    log.append("open")\n', "")
        put = self.mfile("steps.py", '    log.append("close")\n', '    log.append("close")\n    log.append("open")\n')
        code, _, _, err = self.mutate(test=ORDER, files=(cut, put), together=True)
        self.assertEqual(code, 0, err)
        row = self.rows()[0]
        self.assertEqual((row["kind"], row["parts"], row["files"], row["outcome"]),
                         ("together", ["text", "text"], ["steps.py"], "killed"))
        self.assertEqual((self.mut / "steps.py").read_bytes(), STEPS.encode())

    def test_together_the_row_holds_its_parts_kinds_the_union_of_files_and_a_digest(self):
        patch = self.patch_file({"extra.py": "X = 1\n"})
        part = self.mfile("calc.py", "    return a * 2\n", "    return a * 3\n")
        code, _, _, err = self.mutate("calc.py:a + b=>a - b", str(patch), files=(part,), together=True)
        self.assertEqual(code, 0, err)
        rows = self.rows()
        self.assertEqual([(r["mutant"], r["kind"], r["parts"], r["files"], r["outcome"]) for r in rows],
                         [(1, "together", ["text", "patch", "text"], ["calc.py", "extra.py"], "killed")])
        digests = [mutate.parse(self.mut, "calc.py:a + b=>a - b", self.mut)["digest"],
                   mutate.parse(self.mut, str(patch), self.mut)["digest"],
                   mutate.parse_file(self.mut, str(part), self.mut)["digest"]]
        want = hashlib.sha256("\0".join(digests).encode()).hexdigest()[:12]
        self.assertEqual((len(rows[0]["digest"]), rows[0]["digest"]), (12, want))
        self.assertNotIn("a * 3", runs.path(self.q, self.run_id).read_text())  # never a part's text
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertFalse((self.mut / "extra.py").exists())

    def test_together_a_patch_and_a_substitution_on_one_file_are_refused(self):
        patch = self.patch_file({"calc.py": CALC.replace("a * 2", "a * 3")})
        self.assertIn("calc.py", self.refused("calc.py:a + b=>a - b", str(patch)))

    def test_together_a_substitution_whose_old_text_an_earlier_one_removed_is_refused(self):
        self.refused("calc.py:a + b=>a - b", "calc.py:return a + b=>return 0")

    def test_together_with_one_mutant_is_refused(self):
        self.refused("calc.py:a + b=>a - b")

    def test_together_a_part_that_does_not_apply_restores_the_tree_and_refuses(self):
        patch = self.patch_file({"extra.py": "X = 1\n"})
        real = mutate.git

        def failing(root, *args, **kw):
            if args[:1] == ("apply",) and not args[1].startswith("-"):
                return subprocess.CompletedProcess(args, 1, "", "error: refused here")
            return real(root, *args, **kw)
        before = self.tree()
        with mock.patch.object(mutate, "git", failing):
            code, _, _, err = self.mutate("calc.py:a + b=>a - b", str(patch), together=True)
        self.assertEqual(code, 2, err)
        self.assertEqual(self.rows(), [])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)
        self.assertEqual(self.tree(), before)


class TogetherParts(unittest.TestCase):
    """`mutate.together` on plain parts: the order checks, the union of files and the digest."""

    @staticmethod
    def sub(rel: str, old: bytes, new: bytes) -> dict:
        return {"kind": "text", "files": [rel], "old": old, "new": new, "label": f"mutant {old!r}",
                "digest": hashlib.sha1(old + new).hexdigest()[:12]}

    def test_together_an_old_text_only_an_earlier_part_makes_is_found(self):
        texts = {"a.py": b"x = 1\n"}
        parts = [self.sub("a.py", b"x = 1", b"y = 1"), {"kind": "patch", "files": ["c.py", "b.py"], "digest": "p" * 12},
                 self.sub("a.py", b"y = 1", b"y = 2")]
        m = mutate.together(parts, texts)
        self.assertEqual((m["kind"], m["parts"], m["files"]),
                         ("together", ["text", "patch", "text"], ["a.py", "c.py", "b.py"]))
        self.assertEqual(m["digest"], hashlib.sha256("\0".join(p["digest"] for p in parts).encode()).hexdigest()[:12])
        with self.assertRaises(QueueError) as cm:
            mutate.together([self.sub("a.py", b"x = 1", b"y = 1"), self.sub("a.py", b"x = 1", b"z")], texts)
        self.assertEqual(cm.exception.code, 2)


LIB_SH = 'greet() {\n    echo "hello $1"\n}\n'
SCRIPT_TEST = '. ./lib.sh\n[ "$(greet world)" = "hello world" ] || exit 1\n'


class WholeScriptTests(ToolkitFixture, unittest.TestCase):
    """A product whose tests are whole scripts runs one script per test: `sh {test}`, the script as --test."""

    def setUp(self):
        super().setUp()
        self.write("docs/delivery/plane.json", json.dumps({**self.PLANE_JSON, "mutate": {"command": "sh {test}"}}))
        self.write("lib.sh", LIB_SH)
        self.write("tests/t.sh", SCRIPT_TEST)
        git(self.main, "add", "docs/delivery/plane.json", "lib.sh", "tests/t.sh")
        git(self.main, "commit", "-q", "-m", "a script-tested product")
        git(self.main, "push", "-q", "origin", "main")
        self.run_id = runs.open_run(self.q, config.load(self.main), "0002-second", "implement", prompt_ref=None,
                                    note=None, supersede=False)["run_id"]
        code, body, _, err = self.ccp("wt", "create", "--kind", "impl", "--task", "0002", root=self.main)
        self.assertEqual(code, 0, err)
        self.impl = Path(body["path"])

    def test_a_script_test_kills_a_mutant_and_the_source_is_restored(self):
        code, body, _, err = self.ccp("mutate", "--run", self.run_id, "--test", "tests/t.sh",
                                      "--mutant", "lib.sh:hello $1=>bye $1", root=self.impl)
        self.assertEqual(code, 0, err)
        rows = runs.load(self.q, self.run_id).get("mutation", [])
        self.assertEqual([(r["test"], r["outcome"], r["worktree"]) for r in rows],
                         [("tests/t.sh", "killed", "impl-0002")])
        self.assertEqual((self.impl / "lib.sh").read_bytes(), LIB_SH.encode())

    def test_a_mutant_the_script_does_not_read_survives(self):
        code, _, _, err = self.ccp("mutate", "--run", self.run_id, "--test", "tests/t.sh",
                                   "--mutant", "tests/t.sh:|| exit 1=>|| exit 0", "--mutant", "lib.sh:greet()=>greet ()",
                                   root=self.impl)
        self.assertEqual(code, 1, err)
        self.assertEqual([r["outcome"] for r in runs.load(self.q, self.run_id).get("mutation", [])],
                         ["survived", "survived"])


# A change git and difflib place differently: git puts the inserted blank line after NEW, difflib
# before it, so line 4 is in git's hunk and line 2 in difflib's alone.
REP_BASE = "a\n\nb\n\nc\nd\ne\n"
REP_NOW = "a\n\nNEW\n\nb\n\nC\nd\n"


class RevertsAsGitShows(MutateFixture, unittest.TestCase):
    """A revert puts back exactly the hunk `git diff -U0` shows, and a file the change deleted whole."""

    def setUp(self):
        super().setUp()
        self.write("rep.txt", REP_BASE)
        self.write("gone.py", "GONE = 1\n")
        git(self.main, "add", "rep.txt", "gone.py")
        git(self.main, "commit", "-q", "-m", "files the task changes")
        git(self.main, "push", "-q", "origin", "main")
        git(self.main, "checkout", "-q", "-b", "task/0002-second")
        self.write("rep.txt", REP_NOW)
        git(self.main, "rm", "-q", "gone.py")
        git(self.main, "add", "rep.txt")
        git(self.main, "commit", "-q", "-m", "the task's change")
        self.head = git(self.main, "rev-parse", "HEAD")
        git(self.main, "checkout", "-q", "main")
        self.rev = self.make_wt("rev", sha=self.head)

    def git_hunks(self) -> list[tuple[int, int, int, int]]:
        """The hunks git shows for rep.txt from the merge base, as 0-based (i1, i2, j1, j2) spans."""
        out = git(self.rev, "diff", "-U0", "origin/main", "--", "rep.txt")
        spans = []
        for m in mutate.HUNK_RE.finditer(out.encode()):
            s1, n1, s2, n2 = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
            spans.append((s1 - 1 if n1 else s1, (s1 - 1 if n1 else s1) + n1, s2 - 1 if n2 else s2,
                          (s2 - 1 if n2 else s2) + n2))
        return spans

    def test_each_hunk_alone_and_the_deleted_file_whole(self):
        hunks = self.git_hunks()
        self.assertEqual(hunks, [(2, 2, 2, 4), (4, 5, 6, 7), (6, 7, 8, 8)])  # the insertion, C, e deleted
        was, now = REP_BASE.splitlines(keepends=True), REP_NOW.splitlines(keepends=True)
        reverts, want = [], []
        for i1, i2, j1, j2 in hunks:  # every line of the hunk, and for a deletion the line it follows
            for line in range(j1 + 1, j2 + 1) if j2 > j1 else (j1,):
                reverts.append(f"rep.txt:{line}")
                want.append("".join(now[:j1] + was[i1:i2] + now[j2:]))
        cap = capture(self.rev, ("rep.txt", "gone.py"))
        code, _, _, err = self.mutate(test=ADD, root=self.rev, reverts=(*reverts, "gone.py"))
        self.assertEqual(code, 1, err)  # the test reads neither file: every mutant survives
        runs_seen = seen(cap)
        self.assertEqual(runs_seen[0], [REP_NOW, "<absent>"])
        self.assertEqual([r[0] for r in runs_seen[1:-1]], want)
        self.assertEqual(runs_seen[-1], [REP_NOW, "GONE = 1\n"])
        self.assertEqual((self.rev / "rep.txt").read_text(), REP_NOW)
        self.assertFalse((self.rev / "gone.py").exists())

    def test_a_line_outside_every_git_hunk_is_no_change(self):
        code, _, _, err = self.mutate(test=ADD, root=self.rev, reverts=("rep.txt:2",))
        self.assertEqual(code, 2, err)
        self.assertIn("touch no change", err)
        self.assertEqual(self.rows(), [])


class RevertLines(unittest.TestCase):
    """Which changes a line range puts back (lines of the worktree's file, 1-based, inclusive)."""

    BASE = b"a\nb\nc\nd\ne\nf\n"

    def setUp(self):
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)

    def test_only_the_changes_the_range_overlaps(self):
        now = b"a\nB\nc\nd\nE\nf\n"
        self.assertEqual(mutate._revert_lines(now, self.BASE, 2, 2), b"a\nb\nc\nd\nE\nf\n")
        self.assertEqual(mutate._revert_lines(now, self.BASE, 2, 5), self.BASE)
        self.assertEqual(mutate._revert_lines(now, self.BASE, 3, 4), now)

    def test_added_lines_are_dropped(self):
        now = b"a\nb\nx\ny\nc\nd\ne\nf\n"
        self.assertEqual(mutate._revert_lines(now, self.BASE, 4, 4), self.BASE)
        self.assertEqual(mutate._revert_lines(b"x\ny\n", b"", 1, 1), b"")

    def test_a_deletion_inside_or_next_to_the_range_is_put_back(self):
        now = b"a\nb\nd\ne\nf\n"  # c deleted, between lines 2 and 3
        for first, last in ((2, 2), (3, 3), (2, 3)):
            self.assertEqual(mutate._revert_lines(now, self.BASE, first, last), self.BASE, (first, last))
        self.assertEqual(mutate._revert_lines(now, self.BASE, 4, 5), now)

    def test_repeated_lines_follow_gits_hunks(self):
        was, now = b"}\n}\n", b"}\nfoo\n}\n}\n"  # git: foo and a } added after line 1; difflib: before it
        self.assertEqual(mutate._hunks(was, now), [(1, 1, 1, 3)])
        self.assertEqual(mutate._revert_lines(now, was, 3, 3), was)
        self.assertEqual(mutate._revert_lines(now, was, 1, 1), now)

    def test_a_last_line_without_its_newline(self):
        self.assertEqual(mutate._revert_lines(b"a\nB", b"a\nb\n", 2, 2), b"a\nb\n")
        self.assertEqual(mutate._revert_lines(b"a\nb", b"a\nb\n", 2, 2), b"a\nb\n")


class Ledger(unittest.TestCase):
    def test_a_mutate_event_needs_its_counts(self):
        ev = {"at": "2026-11-11T00:00:00Z", "project_id": "demo", "task_id": "0002-second", "actor": "task-runner",
              "type": "run", "op": "recorded",
              "payload": {"run_id": "r", "mutants": 3, "killed": 1, "unbuilt": 1, "survived": 1}}
        self.assertEqual(lib.validate_event(ev), [])
        for key in ("run_id", "mutants", "killed", "unbuilt", "survived"):
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
        for bad in ({"command": "run-one-test"}, {"command": ""}, {"timeout_seconds": 0}, {"unbuilt_re": ""},
                    {"unbuilt_re": []}, {"unbuilt_re": "("}, {"unbuilt_re": ["ok", 1]}, {"unbuilt_re": 3}):
            p = Product({"mutate": bad})
            try:
                with self.assertRaisesRegex(config.ConfigError, rf"mutate\.{next(iter(bad))}\b", msg=bad):
                    p.cfg
            finally:
                p.cleanup()
        p = Product({"mutate": {"command": "t {test}"}})
        try:
            self.assertEqual(p.cfg.mutate, {"command": "t {test}", "timeout_seconds": 600, "unbuilt_re": None})
        finally:
            p.cleanup()


if __name__ == "__main__":
    unittest.main()
