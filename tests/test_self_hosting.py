"""The plane manages its own development (docs/ROADMAP.md): its own task log, ADRs and docs pass the
plane's checks. Read-only against this repo: no queue, no estimator, no denylist."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import binding, PLANE_ROOT

ROOT = PLANE_ROOT


def ccp(*args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "CCP_LEAK_DENYLIST")}
    return subprocess.run([sys.executable, str(ROOT / "bin/ccp"), "--root", str(ROOT), *args],
                          capture_output=True, text=True, env=env, timeout=300)


class SelfHosting(unittest.TestCase):
    def test_the_task_log_is_clean(self):
        r = ccp("tasks", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_adrs_are_clean(self):
        r = ccp("adr", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_docs_are_clean(self):
        r = ccp("docs", "check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


def e4_import_check() -> str:
    """The part of the architect's `E4` command that finds a test module importing another: a shell test that
    passes when it finds none in the test files git tracks."""
    cmd = next(c["cmd"] for c in json.loads((ROOT / "docs/delivery/plane.json").read_text())["architect"]["checks"]
               if c["id"] == "E4")
    parts = [p for p in cmd.split(" && ") if "from tests" in p]
    assert len(parts) == 1, parts
    return parts[0]


class TestModulesImportNoTestModule(unittest.TestCase):
    def check(self, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", e4_import_check()], cwd=cwd, capture_output=True, text=True)

    def run_check(self, cwd: Path) -> int:
        return self.check(cwd).returncode

    def test_no_test_module_of_the_plane_imports_another(self):
        self.assertEqual(self.run_check(ROOT), 0)

    def test_the_check_finds_each_way_to_import_a_test_module(self):
        for line in ("from tests.test_a import X", "from tests import test_a", "import tests.test_a",
                     "from .test_a import X", "def f():\n    from tests.test_a import X", "from . import test_a",
                     "from tests import a, test_a", "from tests import (\n    a,\n    test_a,\n)"):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as d:
                repo = Path(d)
                (repo / "tests").mkdir()
                (repo / "tests" / "test_b.py").write_text(line + "\n")
                subprocess.run(["git", "init", "-q", str(repo)], check=True)
                subprocess.run(["git", "-C", str(repo), "add", "tests"], check=True)
                r = self.check(repo)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("tests/test_b.py:", r.stdout)  # found, not a file it could not read

    def test_the_check_lets_a_test_import_a_fixture_module(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "tests").mkdir()
            (repo / "tests" / "test_b.py").write_text("from tests.a_fixture import X\nfrom tests import helpers\n")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "tests"], check=True)
            self.assertEqual(self.run_check(repo), 0)

    def test_the_check_skips_a_tracked_test_file_it_cannot_read_and_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            (repo / "tests").mkdir()
            (repo / "tests" / "test_a.py").write_text("x = 1\n")
            (repo / "tests" / "test_b.py").write_text("def (\n")
            (repo / "tests" / "test_c.py").write_text("x = 1\n")
            (repo / "tests" / "test_d.py").write_bytes(b"\xff\xfe x")  # not UTF-8
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "tests"], check=True)
            (repo / "tests" / "test_a.py").unlink()  # tracked, gone from the working tree
            r = self.check(repo)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("E4: skipped tests/test_a.py: ", r.stderr)
            self.assertIn("E4: skipped tests/test_b.py: ", r.stderr)
            self.assertIn("E4: skipped tests/test_d.py: ", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            (repo / "tests" / "test_c.py").write_text("from tests import test_x\n")
            r = self.check(repo)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("tests/test_c.py:1", r.stdout)
            self.assertIn("E4: skipped tests/test_a.py: ", r.stderr)
            self.assertIn("E4: skipped tests/test_b.py: ", r.stderr)
            self.assertIn("E4: skipped tests/test_d.py: ", r.stderr)


if __name__ == "__main__":
    unittest.main()


class ReviewFixes(unittest.TestCase):
    """Phase A review: tracked files only, the plane's own usage, quiet hooks, leak-check and gate parsing."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, *a: str, cwd: Path) -> None:
        subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True)

    def test_package_docs_judge_tracked_directories_only(self):
        from ccp import config, pkgdocs
        r = self.tmp / "prod"
        (r / "docs/delivery").mkdir(parents=True)
        (r / "docs/delivery/plane.json").write_text('{"project_id": "p", "language": "python", "package_docs": {}}')
        (r / "pkg").mkdir()
        (r / "pkg/m.py").write_text('"""m."""\n')
        (r / ".pytest_cache/v").mkdir(parents=True)
        (r / ".pytest_cache/v/x.json").write_text("{}")
        (r / "build/lib").mkdir(parents=True)
        (r / "build/lib/n.py").write_text("x = 1\n")
        self.git("init", "-q", cwd=r)
        self.git("add", "docs", "pkg", cwd=r)
        dirs = [str(d.relative_to(r)) for d in pkgdocs.source_dirs(config.load(r))]
        self.assertEqual(dirs, ["pkg"])

    def test_the_planes_own_project_counts_with_the_system_sink(self):
        from unittest import mock
        from ccp import forecast
        b, sink = self.tmp / "bindings", self.tmp / "sink"
        b.mkdir()
        sink.mkdir()
        (sink / "usage-requests-2026-11-05.jsonl").write_text("{}\n")
        prod, plane = self.tmp / "prod", self.tmp / "plane"
        (plane / ".claude-plugin").mkdir(parents=True)
        (plane / ".claude-plugin/marketplace.json").write_text('{"name": "ccp"}')
        (plane / "ccp").mkdir()
        (plane / "ccp/refs.py").write_text("")
        prod.mkdir()
        qs = {}
        for name, root in (("prod", prod), ("plane", plane)):
            q = self.tmp / f"q-{name}"
            (q / "board").mkdir(parents=True)
            (q / "board/usage-requests.jsonl").write_text("{}\n")
            (b / f"{name}.yaml").write_text(binding(project_id=name, product_root=root, queue_root=q))
            qs[name] = q
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(b), "CCP_TELEMETRY_DIR": str(sink)}):
            plane_paths, sink_paths = forecast.telemetry_paths(qs["prod"])
        self.assertEqual(plane_paths, [qs["prod"] / "board/usage-requests.jsonl"])
        self.assertIn(qs["plane"] / "board/usage-requests.jsonl", sink_paths)

    def test_orientation_in_the_planes_own_repo_is_one_line(self):
        def run(root: Path) -> str:
            return subprocess.run(["bash", str(ROOT / "plugin/hooks/orientation.sh")], capture_output=True,
                                  text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)}).stdout
        self.assertIn("Control-plane development session", run(ROOT))
        prod = self.tmp / "prod"
        (prod / "docs/delivery").mkdir(parents=True)
        (prod / "docs/delivery/plane.json").write_text('{"project_id": "p"}')
        out = run(prod)
        self.assertNotIn("Control-plane development session", out)
        self.assertIn("additionalContext", out)

    def test_runner_idle_logs_nothing_where_no_runner_ran(self):
        q = self.tmp / "q"
        q.mkdir()
        r = subprocess.run(["bash", str(ROOT / "plugin/hooks/runner-idle.sh"), "--queue-root", str(q), "--ccp", "ccp"],
                           input='{"teammate_name": "runner"}', capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertFalse((q / "observability").exists())

    def test_leak_check_exit_codes(self):
        def run(env_val: str | None) -> int:
            env = {k: v for k, v in os.environ.items() if k != "CCP_LEAK_DENYLIST"}
            if env_val is not None:
                env["CCP_LEAK_DENYLIST"] = env_val
            return subprocess.run(["bash", str(ROOT / "scripts/leak-check.sh")], capture_output=True, env=env).returncode
        self.assertEqual(run(None), 0)
        self.assertEqual(run(str(self.tmp / "missing")), 2)
        bad = self.tmp / "bad"
        bad.write_text("(\n")
        self.assertEqual(run(str(bad)), 2)
        named = self.tmp / "named"
        named.write_text("(unclosed-" + "denylisted\n")
        env = {**{k: v for k, v in os.environ.items() if k != "CCP_LEAK_DENYLIST"}, "CCP_LEAK_DENYLIST": str(named)}
        r = subprocess.run(["bash", str(ROOT / "scripts/leak-check.sh")], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("denylisted", r.stdout + r.stderr)  # a bad pattern is reported, never printed
        ok = self.tmp / "ok"
        ok.write_text("# comment\n" + "zz-no-such-" + "token-qq\n")  # split: this file is tracked too
        self.assertEqual(run(str(ok)), 0)
        # Perl-compatible patterns: a word boundary and a case-insensitive pattern both bite. The probe
        # runs on a scratch git repository holding a copy of the script, never on this checkout.
        import shutil
        repo = self.tmp / "repo"
        (repo / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/leak-check.sh", repo / "scripts/leak-check.sh")
        (repo / "notes.txt").write_text("LEAKCHECKWORD and LeakCheckCase; leakcheckwords\n")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)

        def probe(pattern: str) -> int:
            lst = self.tmp / "probe-list"
            lst.write_text(pattern + "\n")
            env = {**os.environ, "CCP_LEAK_DENYLIST": str(lst)}
            return subprocess.run(["bash", str(repo / "scripts/leak-check.sh")], capture_output=True,
                                  env=env).returncode
        self.assertEqual(probe(r"\bLEAKCHECKWORD\b"), 1)
        self.assertEqual(probe(r"\bleakcheckword\b"), 0)  # case-sensitive by default; `words` is no word match
        self.assertEqual(probe("(?i)leakcheckcase"), 1)
        # The root LICENSE names its copyright holder by design and is not scanned; the same name
        # anywhere else, a nested LICENSE included, still fails.
        (repo / "LICENSE").write_text("Copyright (c) 2026 HOLDERNAME\n")
        subprocess.run(["git", "-C", str(repo), "add", "LICENSE"], check=True)
        self.assertEqual(probe(r"\bHOLDERNAME\b"), 0)
        (repo / "sub").mkdir()
        (repo / "sub" / "LICENSE").write_text("HOLDERNAME\n")
        subprocess.run(["git", "-C", str(repo), "add", "sub/LICENSE"], check=True)
        self.assertEqual(probe(r"\bHOLDERNAME\b"), 1)
        (repo / "sub" / "LICENSE").unlink()
        subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", "sub/LICENSE"], check=True)
        (repo / "notes.txt").write_text("HOLDERNAME\n")
        subprocess.run(["git", "-C", str(repo), "add", "notes.txt"], check=True)
        self.assertEqual(probe(r"\bHOLDERNAME\b"), 1)

    def test_gate_result_parses_failures_and_the_summary(self):
        import json
        log = self.tmp / "log"
        log.write_text("\n".join([
            "test_a (tests.t.C.test_a) ... skipped 'x' skipped=9",
            "FAIL: test_b (tests.t.C.test_b)",
            "ERROR: setUpClass (tests.t.D)",
            "ERROR: test_c (tests.u.E)",
            "Ran 12 tests in 1.0s", "", "FAILED (failures=1, errors=2, skipped=3)", ""]))
        out = json.loads(subprocess.run([sys.executable, str(ROOT / "scripts/gate_result.py"), str(log), "7"],
                                        capture_output=True, text=True).stdout)
        self.assertEqual(out["tests"], 12)
        self.assertEqual(out["skipped"], 3)
        self.assertEqual([f["id"] for f in out["failures"]], ["tests.t.C.test_b", "tests.t.D.setUpClass", "tests.u.E.test_c"])
        self.assertEqual(out["seconds"], 7)
