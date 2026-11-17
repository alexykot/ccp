"""The plane's gate test cache (SPEC §15.3, plane.json `verify.accept_cache`): scripts/gate.sh serves a
module from the cache when nothing it can read changed since it passed, reruns what a change can affect,
records only passes, honours the entry age and the cold option (GATE_COLD), never writes to git, and
reports the modules ran and cached in its result file, which `ccp suite run` records."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_gate_parallel import MORE, OK, GateFixture, ROOT, SCRIPTS
from tests.test_suite_stages import StagedFixture

# A test module that imports another test module (a shared helper), as many of the plane's do.
HELPER = """
import unittest
VALUE = {value}
class H(unittest.TestCase):
    def test_h(self): self.assertTrue(True)
"""
USER = """
import unittest
from tests.test_helper import VALUE
class U(unittest.TestCase):
    def test_u(self): self.assertEqual(VALUE, 1)
"""

# A test module that passes but leaves a `state/x` branch behind in the repository it runs in.
LEAK = """
import subprocess, unittest
class L(unittest.TestCase):
    def test_leak(self):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "branch", "state/x"], check=True,
                       capture_output=True)
"""
# Importers of the helper by the package's own forms, which name it with no `tests.` prefix.
FROM_PKG = """
import unittest
from {pkg} import test_helper
class U(unittest.TestCase):
    def test_u(self): self.assertEqual(test_helper.VALUE, 1)
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout


class CacheFixture(GateFixture):
    def setUp(self):
        super().setUp()
        self.cache = Path(self._tmp.name) / "cache"
        (self.repo / ".gitignore").write_text("__pycache__/\n")  # as the plane's own repo has it
        (self.repo / "src.py").write_text("X = 1\n")
        self.module("test_ok", OK)
        self.module("test_more", MORE.format(lhs=3))

    def commit(self) -> None:
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-q", "-m", "c")

    def cgate(self, cold: str | None = None, **env: str | None) -> tuple[subprocess.CompletedProcess[str], dict]:
        r = self.gate(GATE_CACHE_DIR=str(self.cache), GATE_COLD=cold, **env)
        return r, self.read()

    def mods(self, r: subprocess.CompletedProcess[str], state: str) -> set[str]:
        return {ln.split()[2].rstrip(":") for ln in r.stdout.splitlines()
                if ln.startswith("gate module ") and ln.split()[3].startswith(state)}


class ARepeatRunIsServedFromTheCache(CacheFixture):
    def test_the_second_run_at_unchanged_inputs_runs_nothing_and_passes(self):
        self.commit()
        r1, res1 = self.cgate()
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertEqual((res1["ran"], res1["cached"], res1["cached_tests"], res1["tests"]), (2, 0, 0, 5))
        r2, res2 = self.cgate()
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual((res2["ran"], res2["cached"], res2["cached_tests"], res2["tests"], res2["failed"]),
                         (0, 2, 5, 0, 0))
        self.assertNotIn("modules", res2)
        self.assertEqual(self.mods(r2, "cached"), {"tests.test_ok", "tests.test_more"})

    def test_computing_the_key_leaves_the_index_the_stash_and_the_status_as_they_were(self):
        self.commit()
        (self.repo / "src.py").write_text("X = 2\n")  # an unstaged edit
        (self.repo / "new.py").write_text("Y = 1\n")  # an untracked file
        index = Path(git(self.repo, "rev-parse", "--git-path", "index").strip())
        index = index if index.is_absolute() else self.repo / index
        before = (git(self.repo, "status", "--porcelain"), git(self.repo, "stash", "list"), index.read_bytes(),
                  git(self.repo, "count-objects"))
        for _ in range(2):
            r, _res = self.cgate()
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((git(self.repo, "status", "--porcelain"), git(self.repo, "stash", "list"),
                          index.read_bytes(), git(self.repo, "count-objects")), before)

    def test_an_entry_records_the_key_the_pass_its_tests_seconds_and_time(self):
        self.commit()
        self.cgate()
        entries = [json.loads(p.read_text()) for p in self.cache.glob("*.json")]
        self.assertEqual(len(entries), 2)
        for e in entries:
            self.assertEqual(set(e), {"key", "passed", "tests", "seconds", "at"})
            self.assertTrue(e["passed"])
        self.assertEqual(sorted(e["tests"] for e in entries), [2, 3])


class AChangeRerunsWhatItCanAffect(CacheFixture):
    def warm(self) -> None:
        self.commit()
        r, res = self.cgate()
        self.assertEqual((r.returncode, res["cached"]), (0, 0), r.stdout + r.stderr)

    def test_editing_one_test_module_reruns_only_it(self):
        self.warm()
        p = self.repo / "tests" / "test_more.py"
        p.write_text(p.read_text() + "# a comment\n")
        r, res = self.cgate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.mods(r, "ok"), self.mods(r, "cached")), ({"tests.test_more"}, {"tests.test_ok"}))
        self.assertEqual((res["ran"], res["cached"]), (1, 1))

    def test_an_uncommitted_source_edit_reruns_every_module(self):
        self.warm()
        (self.repo / "src.py").write_text("X = 1  # a comment\n")
        r, res = self.cgate()
        self.assertEqual((r.returncode, res["cached"], res["ran"]), (0, 0, 2), r.stdout + r.stderr)

    def test_the_key_is_the_content_whether_staged_committed_or_in_the_working_tree(self):
        self.warm()
        (self.repo / "src.py").write_text("X = 1  # a comment\n")
        self.cgate()  # the edit's own run records it
        for step in (("add", "src.py"), ("commit", "-q", "-m", "x")):
            with self.subTest(step=step[0]):
                git(self.repo, *step)
                r, res = self.cgate()
                self.assertEqual((res["cached"], res["ran"]), (2, 0), r.stdout + r.stderr)
        (self.repo / "src.py").write_text("X = 1\n")  # back to the warmed content, uncommitted
        r, res = self.cgate()
        self.assertEqual((res["cached"], res["ran"]), (2, 0), r.stdout + r.stderr)

    def test_an_untracked_file_or_a_deleted_one_reruns_every_module(self):
        self.warm()
        (self.repo / "added.py").write_text("Z = 1\n")
        r, res = self.cgate()
        self.assertEqual(res["cached"], 0, r.stdout)
        (self.repo / "added.py").unlink()
        r, res = self.cgate()
        self.assertEqual(res["cached"], 2, r.stdout)  # back to the warmed inputs
        (self.repo / "src.py").unlink()
        r, res = self.cgate()
        self.assertEqual(res["cached"], 0, r.stdout)

    def test_a_test_module_another_imports_is_everyones_input(self):
        self.module("test_helper", HELPER.format(value=1))
        self.module("test_user", USER)
        self.warm()
        p = self.repo / "tests" / "test_helper.py"
        p.write_text(HELPER.format(value=22))  # another size, so no stale bytecode stands in for it
        r, res = self.cgate()
        self.assertEqual(r.returncode, 1, r.stdout)  # the importer reran and saw the change
        self.assertIn("FAIL: test_u (tests.test_user.U.test_u)", r.stdout)
        self.assertEqual(res["cached"], 0)

    def test_a_failed_module_is_not_recorded_and_runs_again(self):
        self.module("test_more", MORE.format(lhs=4))
        self.commit()
        r, res = self.cgate()
        self.assertEqual(r.returncode, 1)
        r, res = self.cgate()
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual((self.mods(r, "cached"), self.mods(r, "FAILED")), ({"tests.test_ok"}, {"tests.test_more"}))

    def helper_by_package(self, pkg: str) -> None:
        self.module("test_helper", HELPER.format(value=1))
        self.module("test_user", FROM_PKG.format(pkg=pkg))
        self.warm()
        self.module("test_helper", HELPER.format(value=22))  # another size, so no stale bytecode stands in
        r, res = self.cgate()
        self.assertEqual(r.returncode, 1, r.stdout)  # the importer reran and saw the change
        self.assertIn("FAIL: test_u (tests.test_user.U.test_u)", r.stdout)
        self.assertEqual(res["cached"], 0)

    def test_a_helper_named_by_from_tests_import_is_everyones_input(self):
        self.helper_by_package("tests")

    def test_a_helper_named_by_from_dot_import_is_everyones_input(self):
        self.helper_by_package(".")

    def test_a_module_that_leaves_a_state_branch_is_never_served_from_the_cache(self):
        self.module("test_leak", LEAK)
        self.commit()
        for run in (1, 2):
            with self.subTest(run=run):
                r, _res = self.cgate()
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("state/x", r.stderr)
                self.assertIn("tests.test_leak", self.mods(r, "ok"))  # run, never served from the cache
                self.assertEqual(self.mods(r, "cached"), set())
                git(self.repo, "branch", "-D", "state/x")
        r, _res = self.cgate()  # nothing recorded while the branch was left: every module runs again
        self.assertEqual(self.mods(r, "cached"), set(), r.stdout)

    def test_an_untracked_nested_repository_is_hashed_into_the_key(self):
        self.warm()
        nested = self.repo / "tests" / "tmpdir"
        nested.mkdir()
        (nested / "x.txt").write_text("one\n")
        subprocess.run(["git", "init", "-q", str(nested)], check=True)  # git lists it whole: tests/tmpdir/
        for content, cached in (("one\n", 0), ("one\n", 2), ("two\n", 0), ("two\n", 2)):
            with self.subTest(content=content, cached=cached):
                (nested / "x.txt").write_text(content)
                r, res = self.cgate()
                self.assertEqual((r.returncode, res["cached"], res["ran"]), (0, cached, 2 - cached), r.stdout)
                self.assertNotIn("no test cache", r.stdout)  # gate.sh tees both streams

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_an_unreadable_untracked_file_turns_the_cache_off_and_is_named(self):
        self.warm()
        f = self.repo / "secret.txt"
        f.write_text("x\n")
        f.chmod(0)
        self.addCleanup(f.chmod, 0o644)
        r, res = self.cgate()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no test cache this run", r.stdout)  # gate.sh tees both streams
        self.assertIn("secret.txt", r.stdout)  # the file is named
        self.assertEqual((res["cached"], res["ran"]), (0, 2))

    def test_an_entry_not_marked_passed_or_with_another_key_is_no_hit(self):
        self.warm()
        for change in ({"passed": False}, {"key": "x"}):
            with self.subTest(change=change):
                for p in self.cache.glob("*.json"):
                    p.write_text(json.dumps({**json.loads(p.read_text()), **change}))
                r, res = self.cgate()
                self.assertEqual((res["cached"], res["ran"]), (0, 2), r.stdout)


class TheAgeTheColdOptionAndTheDirectory(CacheFixture):
    def test_an_entry_older_than_max_age_days_is_no_hit(self):
        (self.repo / "docs" / "delivery").mkdir(parents=True)
        (self.repo / "docs" / "delivery" / "plane.json").write_text(
            json.dumps({"verify": {"accept_cache": {"max_age_days": 2}}}))
        self.commit()
        self.cgate()
        old = [p for p in self.cache.glob("*.json")][0]
        old.write_text(json.dumps({**json.loads(old.read_text()), "at": "2020-01-01T00:00:00Z"}))
        r, res = self.cgate()
        self.assertEqual((res["cached"], res["ran"]), (1, 1), r.stdout)

    def test_the_cold_option_reads_and_writes_no_cache(self):
        self.commit()
        self.cgate()
        before = {p.name: p.read_text() for p in self.cache.glob("*")}
        r, res = self.cgate(cold="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((res["cached"], res["ran"], res["tests"]), (0, 2, 5))
        self.assertEqual({p.name: p.read_text() for p in self.cache.glob("*")}, before)
        empty = Path(self._tmp.name) / "empty-cache"
        self.cache = empty
        self.cgate(cold="yes")
        self.assertFalse(empty.exists())
        r, res = self.cgate(cold="0")  # 0 is not cold
        self.assertEqual(res["cached"], 0)
        self.assertTrue(any(empty.glob("*.json")))

    def test_a_cache_directory_inside_the_repository_is_refused(self):
        self.commit()
        self.cache = self.repo / "cache"
        r, _res = self.cgate()
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("GATE_CACHE_DIR", r.stdout)
        self.assertFalse(self.cache.exists())

    def test_the_default_directory_is_per_repository_under_the_home_cache_and_worktrees_share_it(self):
        self.commit()
        home = Path(self._tmp.name) / "home"
        r = self.gate(GATE_CACHE_DIR=None, HOME=str(home))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        dirs = list((home / ".cache" / "ccp-gate").iterdir())
        self.assertEqual(len(dirs), 1)
        self.assertEqual(len(list(dirs[0].glob("*.json"))), 2)
        wt = Path(self._tmp.name) / "wt"
        git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        self.repo = wt
        r = self.gate(GATE_CACHE_DIR=None, HOME=str(home))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.mods(r, "cached")), 2, r.stdout)
        self.assertEqual(list((home / ".cache" / "ccp-gate").iterdir()), dirs)

    def test_a_checkout_git_cannot_read_runs_every_module_with_no_cache(self):
        with tempfile.TemporaryDirectory() as d:
            plain = Path(d) / "plain"
            (plain / "scripts").mkdir(parents=True)
            (plain / "tests").mkdir()
            for s in SCRIPTS:
                (plain / "scripts" / s).write_text((ROOT / "scripts" / s).read_text())
            (plain / "tests" / "__init__.py").write_text("")
            (plain / "tests" / "test_ok.py").write_text(OK)
            self.repo = plain
            r = self.gate("1", GATE_CACHE_DIR=str(self.cache), GIT_CEILING_DIRECTORIES=d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no test cache this run", r.stdout)  # gate.sh tees both streams
        self.assertEqual((self.read()["ran"], self.read()["cached"]), (1, 0))
        self.assertFalse(self.cache.exists())


class TheResultCountsCachedModules(unittest.TestCase):
    def parse(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log"
            log.write_text(text)
            return json.loads(subprocess.run([sys.executable, str(ROOT / "scripts/gate_result.py"), str(log), "3"],
                                             capture_output=True, text=True, check=True).stdout)

    def test_cached_modules_are_counted_apart_from_those_that_ran(self):
        out = self.parse("\n".join([
            "gate module tests.test_c: cached, 2.00 s, 7 tests",
            "Ran 4 tests in 0.1s", "", "OK", "gate module tests.test_a: ok, 1.25 s, 4 tests", ""]))
        self.assertEqual((out["tests"], out["ran"], out["cached"], out["cached_tests"], out["failed"]), (4, 1, 1, 7, 0))
        self.assertEqual([m["name"] for m in out["modules"]], ["tests.test_a"])

    def test_an_all_cached_log_has_no_tests_run_and_no_modules(self):
        out = self.parse("gate module tests.test_c: cached, 2.00 s, 7 tests\n")
        self.assertEqual((out["tests"], out["ran"], out["cached"], out["cached_tests"]), (0, 0, 1, 7))
        self.assertNotIn("modules", out)


class TheRunRecordsRanCachedAndCold(StagedFixture, unittest.TestCase):
    def test_a_warm_run_is_recorded_warm_and_a_cold_one_cold(self):
        repo = Path(self._tmp.name) / "gate-repo"
        (repo / "scripts").mkdir(parents=True)
        (repo / "tests").mkdir()
        for s in SCRIPTS:
            (repo / "scripts" / s).write_text((ROOT / "scripts" / s).read_text())
        (repo / "tests" / "__init__.py").write_text("")
        (repo / "tests" / "test_ok.py").write_text(OK)
        (repo / ".gitignore").write_text("__pycache__/\n")
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "c")
        self.lanes({"fast": ["bash", str(repo / "scripts" / "gate.sh")]})
        env = {"GATE_CACHE_DIR": str(Path(self._tmp.name) / "gate-cache"), "GATE_WORKERS": "1"}
        rows = []
        for cold in (None, None, "1"):
            r = self.run_suite("--lane", "fast", env={**env, **({"GATE_COLD": cold} if cold else {})},
                               unset=() if cold else ("GATE_COLD",))
            self.assertEqual(r.returncode, 0, r.stdout.decode() + r.stderr.decode())
            rows.append(self.ended())
        self.assertEqual([(x["ran"], x["cached"], x["cold"]) for x in rows], [(1, 0, True), (0, 1, False), (1, 0, True)])
        self.assertEqual(rows[1]["cached_tests"], 2)


if __name__ == "__main__":
    unittest.main()
