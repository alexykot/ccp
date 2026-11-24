"""`ccp mutate` (SPEC §20.6): a mutant is killed only when the named test fails, and the worktree is
restored after each."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from ccp import config, doclang, mutate, runs
from ccp.queue import QueueError
from tests.helpers import PLANE_ROOT
from tests.git_helpers import git
from tests.toolkit_fixture import ToolkitFixture

sys.path.insert(0, str(PLANE_ROOT / "scripts" / "observability"))
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

    def test_no_command_runs_the_packs_runner(self):
        p = self.mut / "docs/delivery/plane.json"
        body = json.loads(p.read_text())
        del body["mutate"]
        p.write_text(json.dumps(body))
        code, body, _, err = self.mutate("calc.py:a + b=>a - b", "calc.py:a * 2=>a * 3")
        self.assertEqual((code, body["killed"], body["survived"]), (1, 1, 1), err)
        self.assertEqual([r["outcome"] for r in self.rows()], ["killed", "survived"])
        self.assertIn("FAIL: test_add", Path(body["log"]).read_text())
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

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

    def test_each_mutant_prints_one_line_on_stderr(self):
        code, _, out, err = self.mutate("calc.py:a * 2=>a * 3", "calc.py:a + b=>a - b")
        self.assertEqual(code, 1, err)
        self.assertTrue(out.rstrip().endswith("}"))  # the JSON whole on stdout
        self.assertEqual(err.splitlines(), [f"mutant 1: survived ({ADD})", f"mutant 2: killed ({ADD})"])

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


def group_running(pgid: int) -> list[str]:
    """The `ps` rows (pid, stat, command) of the processes of group `pgid` that run: every one but zombies."""
    out = subprocess.run(["ps", "-A", "-o", "pgid=,pid=,stat=,command="], capture_output=True, text=True,
                         check=True).stdout
    rows = (line.split(None, 1) for line in out.splitlines())
    return [r[1] for r in rows if len(r) == 2 and r[0] == str(pgid) and not r[1].split()[1].startswith("Z")]


def group_gone(pgid: int) -> bool:
    """No process of group `pgid` runs: `ps` lists none of it but zombies. A zombie waits for its reaper, which
    under load may be late, and `os.killpg(pgid, 0)` on a group of zombies alone is refused on macOS, so it
    cannot tell them from a running process."""
    return not group_running(pgid)


class GroupGone(unittest.TestCase):
    def test_a_group_whose_only_member_is_an_unreaped_zombie_is_gone(self):
        p = subprocess.Popen(["sleep", "0"], start_new_session=True)
        self.addCleanup(p.wait)
        os.waitid(os.P_PID, p.pid, os.WEXITED | os.WNOWAIT)  # it has exited, and stays unreaped
        self.assertTrue(group_gone(p.pid))

    def test_a_group_running_a_process_is_not_gone(self):
        p = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        self.assertFalse(group_gone(p.pid))

    def test_a_running_group_s_rows_name_each_process_its_state_and_command(self):
        p = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(p.wait)
        self.addCleanup(p.kill)
        [row] = group_running(p.pid)
        pid, stat, command = row.split(None, 2)
        self.assertEqual((pid, command), (str(p.pid), "sleep 30"))
        self.assertNotIn("Z", stat)


class Interrupted(MutateFixture, unittest.TestCase):
    """`ccp mutate` in its own process, sent a SIGTERM while the test command runs."""

    def interrupt(self, sleep_when: str, *mutants: str) -> tuple[int, int]:
        """Send the call a SIGTERM once the command is asleep (it sleeps when `sleep_when`, a shell
        test, holds); its exit code and the sleeping command's process group."""
        pid = Path(self._tmp.name) / "child.pid"
        self.set_mutate(command=f"if {sleep_when}; then echo $$ > {shlex.quote(str(pid))}; exec sleep 60; fi; "
                        + COMMAND)  # exec: no fork follows the pid file
        args = [sys.executable, str(PLANE_ROOT / "bin/ccp"), "--root", str(self.mut), "mutate", "--run", self.run_id,
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
        deadline = time.monotonic() + 30
        while running := group_running(group):
            if time.monotonic() > deadline:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.fail("the test command was left running: " + "; ".join(running))
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

    def test_a_worktree_of_another_task(self):
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("mut", task="0001"))
        self.refused(2, "calc.py:a + b=>a - b", root=self.make_wt("rev", task="0001"))

    def test_a_closed_run(self):
        rec = runs.load(self.q, self.run_id)
        rec["reported_at"] = "2026-11-10T00:00:00Z"
        runs.save(self.q, rec)
        self.refused(2, "calc.py:a + b=>a - b")

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

    def test_a_relative_path_is_read_from_the_current_directory(self):
        f = self.mfile(f"calc.py\n=== old\n{TWO_LINES_OLD}=== new\n{TWO_LINES_NEW}")
        self.assertEqual(mutate.parse_file(self.mut, f.name, f.parent)["old"], TWO_LINES_OLD.encode().rstrip(b"\n"))

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
        # calc.py imports limits, so the test module no longer imports: the pack's lines call it unbuilt
        self.assertEqual((code, self.rows()[0]["outcome"]), (1, "unbuilt"), err)
        self.assertEqual((self.rev / "limits.py").read_text(), "FLOOR = 0\n")
        self.assertEqual(self.tree_of(self.rev), before)

    def test_reverts_come_after_the_mutants(self):
        code, _, _, err = self.mutate("calc.py:a * 2=>a * 3", test=GUARD, root=self.rev, reverts=("calc.py:5-6",))
        self.assertEqual(code, 1, err)
        self.assertEqual([(r["mutant"], r["kind"], r["outcome"]) for r in self.rows()],
                         [(1, "text", "survived"), (2, "revert", "killed")])

    def test_a_revert_that_changes_nothing_or_names_no_file_is_refused(self):
        for spec in ("calc.py:15", "docs/delivery/plane.json", "nope.py", "nope.py:1", "../calc.py", "/etc/hosts",
                     "docs"):
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
    SYNTAX_BREAK = "calc.py:def add(a, b):=>def add(a, b)"  # calc.py no longer compiles: a SyntaxError

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

    def test_with_no_pattern_the_packs_lines_mark_a_syntax_error_and_a_failed_import_unbuilt(self):
        self.set_mutate(unbuilt_re=None)
        code, body, _, err = self.mutate(self.SYNTAX_BREAK, self.IMPORT_BREAK, "calc.py:a + b=>a - b")
        self.assertEqual((code, body["unbuilt"], body["killed"]), (1, 2, 1), err)
        self.assertEqual([r["outcome"] for r in self.rows()], ["unbuilt", "unbuilt", "killed"])
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_syntax_error_the_code_under_test_raises_at_run_time_is_killed(self):
        self.set_mutate(unbuilt_re=None)
        code, body, _, err = self.mutate("calc.py:    return a + b=>    return compile('def f(:', '<string>', 'exec')")
        self.assertEqual((code, body["killed"], body["unbuilt"]), (0, 1, 0), err)
        self.assertIn("SyntaxError", Path(body["log"]).read_text())

    def test_a_syntax_error_in_a_lazily_imported_module_is_unbuilt(self):
        # the new module sorts after calc.py, so the patch does not end on a blank context line the fixture's git strips
        patch = self.patch_file({"calc.py": CALC.replace("    return a + b\n", "    import lazy\n    return a + b\n"),
                                 "lazy.py": "def f(:\n    pass\n"})
        self.set_mutate(unbuilt_re=None)  # after the patch, which holds the worktree's whole diff
        code, body, _, err = self.mutate(str(patch))
        self.assertIsNotNone(body, err)
        self.assertEqual((code, body["unbuilt"], body["killed"]), (1, 1, 0), err)
        self.assertNotIn("Failed to import test module", Path(body["log"]).read_text())  # the test module imported
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_a_config_with_no_mutate_block_runs_on_the_defaults(self):
        cfg = replace(config.load(self.mut), mutate=None)
        body, code = mutate.run(cfg, self.q, self.run_id, [ADD], ["calc.py:a + b=>a - b"], cwd=self.mut)
        self.assertEqual((code, body["killed"]), (0, 1))

    def test_a_pattern_of_its_own_replaces_the_packs(self):
        self.set_mutate(unbuilt_re="^no line says this$")
        code, body, _, err = self.mutate(self.SYNTAX_BREAK)
        self.assertEqual((code, body["killed"], body["unbuilt"]), (0, 1, 0), err)

    def test_a_language_whose_pack_has_no_lines_counts_the_same_mutant_a_kill(self):
        p = self.mut / "docs/delivery/plane.json"
        p.write_text(json.dumps({**json.loads(p.read_text()), "language": "none"}))
        self.set_mutate(unbuilt_re=None)
        code, body, _, err = self.mutate(self.SYNTAX_BREAK)
        self.assertEqual((code, body["killed"], body["unbuilt"]), (0, 1, 0), err)

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


# A test's FAIL section whose assertion message quotes a child program's syntax error in the test's own fixture file
QUOTED_SYNTAX_ERROR = """\
======================================================================
FAIL: test_skips (tests.test_house.Imports.test_skips)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/w/rev-1/tests/test_house.py", line 92, in test_skips
    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
AssertionError: 1 != 0 : E4: skipped tests/test_a.py: [Errno 2] No such file or directory: 'tests/test_a.py'
Traceback (most recent call last):
  File "<string>", line 4, in <module>
  File "/usr/lib/python3/ast.py", line 46, in parse
    return compile(source, filename, mode, flags,
  File "tests/test_b.py", line 1
    def (
        ^
SyntaxError: invalid syntax

----------------------------------------------------------------------
Ran 4 tests in 3.282s

FAILED (failures=1)
"""


class UnbuiltLines(unittest.TestCase):
    """The did-not-build decision on plain values: a pack's source-location line counts only when its `path` group
    names a file the mutant touched."""

    def unbuilt(self, text: str, files: list[str]) -> bool:
        pats = [re.compile(p) for p in doclang.get("python").unbuilt_re]
        return mutate.says_unbuilt(text, pats, files)

    def test_a_frame_counts_only_when_it_names_a_file_the_mutant_touched(self):
        self.assertFalse(self.unbuilt(QUOTED_SYNTAX_ERROR, ["docs/delivery/plane.json"]))
        self.assertTrue(self.unbuilt(QUOTED_SYNTAX_ERROR, ["tests/test_b.py"]))
        frame = '  File "/w/rev-1/ccp/x.py", line 5\n'
        self.assertTrue(self.unbuilt(frame, ["ccp/x.py"]))
        self.assertTrue(self.unbuilt(frame, ["./ccp/x.py"]))
        self.assertTrue(self.unbuilt(frame, ["ccp//x.py"]))
        self.assertFalse(self.unbuilt(frame, ["ccp/y.py", "x.py.bak", "p/x.py"]))
        failed_import = "ImportError: Failed to import test module: tests.test_x\n"
        self.assertTrue(self.unbuilt(failed_import, []))
        self.assertTrue(self.unbuilt(failed_import, ["ccp/y.py"]))


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

    def test_together_a_later_part_finds_its_old_text_in_what_an_earlier_one_wrote(self):
        code, _, _, err = self.mutate("calc.py:a + b=>a ^ b", "calc.py:a ^ b=>a % b", together=True)
        self.assertEqual((code, [r["outcome"] for r in self.rows()]), (0, ["killed"]), err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

    def test_together_two_spellings_of_one_file_are_one_file(self):
        self.refused("calc.py:a + b=>a - b", "./calc.py:return a + b=>return 0")
        patch = self.patch_file({"calc.py": CALC.replace("a * 2", "a * 3")})
        self.assertIn("calc.py", self.refused(str(patch), "./calc.py:a + b=>a - b"))
        code, _, _, err = self.mutate("./calc.py:a + b=>a ^ b", "./calc.py:a ^ b=>a % b", together=True)
        self.assertEqual((code, [(r["files"], r["outcome"]) for r in self.rows()]), (0, [(["calc.py"], "killed")]), err)
        self.assertEqual((self.mut / "calc.py").read_text(), CALC)

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

    def test_several_ranges_put_back_the_hunks_they_hit_and_the_digest_takes_them_as_given(self):
        base = git(self.rev, "merge-base", "HEAD", "origin/main")
        one, other = (mutate.parse_revert(self.rev, spec, base) for spec in ("rep.txt:3,8", "rep.txt:8,3"))
        self.assertEqual((one["content"], other["content"]), (b"a\n\nb\n\nC\nd\ne\n",) * 2)  # C's change stays
        self.assertNotEqual(one["digest"], other["digest"])
        with self.assertRaises(QueueError) as cm:
            mutate.parse_revert(self.rev, "rep.txt:3,9", base)
        self.assertIn("lines 9-9 ", str(cm.exception))  # the range past the file's end

    def test_a_line_outside_every_git_hunk_is_no_change(self):
        code, _, _, err = self.mutate(test=ADD, root=self.rev, reverts=("rep.txt:2",))
        self.assertEqual(code, 2, err)
        self.assertIn("touch no change", err)
        self.assertEqual(self.rows(), [])


class RevertLines(unittest.TestCase):
    """Which changes line ranges put back (lines of the worktree's file, 1-based, inclusive)."""

    BASE = b"a\nb\nc\nd\ne\nf\n"

    def setUp(self):
        env = mock.patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        env.start()
        self.addCleanup(env.stop)

    def test_only_the_changes_the_range_overlaps(self):
        now = b"a\nB\nc\nd\nE\nf\n"
        self.assertEqual(mutate._revert_lines(now, self.BASE, [(2, 2)]), b"a\nb\nc\nd\nE\nf\n")
        self.assertEqual(mutate._revert_lines(now, self.BASE, [(2, 5)]), self.BASE)
        self.assertEqual(mutate._revert_lines(now, self.BASE, [(3, 4)]), now)

    def test_added_lines_are_dropped(self):
        now = b"a\nb\nx\ny\nc\nd\ne\nf\n"
        self.assertEqual(mutate._revert_lines(now, self.BASE, [(4, 4)]), self.BASE)
        self.assertEqual(mutate._revert_lines(b"x\ny\n", b"", [(1, 1)]), b"")

    def test_a_deletion_inside_or_next_to_the_range_is_put_back(self):
        now = b"a\nb\nd\ne\nf\n"  # c deleted, between lines 2 and 3
        for first, last in ((2, 2), (3, 3), (2, 3)):
            self.assertEqual(mutate._revert_lines(now, self.BASE, [(first, last)]), self.BASE, (first, last))
        self.assertEqual(mutate._revert_lines(now, self.BASE, [(4, 5)]), now)

    def test_repeated_lines_follow_gits_hunks(self):
        was, now = b"}\n}\n", b"}\nfoo\n}\n}\n"  # git: foo and a } added after line 1; difflib: before it
        self.assertEqual(mutate._hunks(was, now), [(1, 1, 1, 3)])
        self.assertEqual(mutate._revert_lines(now, was, [(3, 3)]), was)
        self.assertEqual(mutate._revert_lines(now, was, [(1, 1)]), now)

    def test_several_ranges_put_back_each_hunk_one_hits_and_not_the_lines_between(self):
        base = self.BASE + b"g\n"
        now = b"a\nB\nc\nD\ne\nF\ng\n"  # changes at lines 2, 4 and 6
        between = b"a\nb\nc\nD\ne\nf\ng\n"
        for given in ([(2, 2), (6, 6)], [(6, 6), (2, 2)], [(2, 2), (2, 2), (6, 6)], [(1, 2), (2, 3), (6, 7)]):
            self.assertEqual(mutate._revert_lines(now, base, given), between, given)
        self.assertEqual(mutate._revert_lines(now, base, [(2, 6)]), base)  # one range spans the change between
        self.assertEqual(mutate._ranges("rep.txt:2,6", "rep.txt", "2,6", 7), [(2, 2), (6, 6)])
        self.assertEqual(mutate._ranges("rep.txt:6,2-3", "rep.txt", "6,2-3", 7), [(6, 6), (2, 3)])
        for rng, bad in (("2,8", "8-8"), ("2,5-9", "5-9"), ("6-5,2", "6-5")):
            with self.assertRaises(QueueError) as cm:
                mutate._ranges(f"rep.txt:{rng}", "rep.txt", rng, 7)
            self.assertEqual(cm.exception.code, 2)
            self.assertIn(f"lines {bad} ", str(cm.exception))  # the bad range, named
        for rng in ("2,5", "5,2", "2-3,5", "2,,5", "2,", ",5", "0,5", "2-x"):
            self.assertEqual(mutate.RANGES_RE.fullmatch(rng) is not None, rng in ("2,5", "5,2", "2-3,5"), rng)

    def test_a_last_line_without_its_newline(self):
        self.assertEqual(mutate._revert_lines(b"a\nB", b"a\nb\n", [(2, 2)]), b"a\nb\n")
        self.assertEqual(mutate._revert_lines(b"a\nb", b"a\nb\n", [(2, 2)]), b"a\nb\n")


class Ledger(unittest.TestCase):
    def test_a_mutate_event_needs_its_counts(self):
        ev = {"at": "2026-11-11T00:00:00Z", "project_id": "demo", "task_id": "0002-second", "actor": lib.RUNNER,
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
