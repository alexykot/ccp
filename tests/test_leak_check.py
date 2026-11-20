"""scripts/leak-check.sh finds the installation's denylist: CCP_LEAK_DENYLIST, then the bindings directory."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORD = "zzleakword" + "qq"  # split: this file is tracked too


class LeakCheckLookup(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ccp-leak-check-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/leak-check.sh", self.repo / "scripts/leak-check.sh")
        (self.repo / "notes.txt").write_text(f"a line with {WORD} in it\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        # PATH holds python3 and the system tools, never the real ccp.
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(shutil.which("python3") or sys.executable)
        self.bindings = self.tmp / "bindings"
        self.bindings.mkdir()

    def denylist(self, directory: Path, pattern: str = WORD) -> Path:
        path = directory / "leak-denylist.txt"
        path.write_text(pattern + "\n")
        return path

    def stub_ccp(self, binding: Path | None, plane: Path) -> None:
        """A `ccp` whose `--root <repo> where` prints a binding (or none) and a plane."""
        import json
        out = json.dumps({"binding": str(binding) if binding else None, "plane": str(plane)})
        stub = self.bin / "ccp"
        stub.write_text(f"#!/bin/sh\n[ \"$1\" = --root ] && [ \"$3\" = where ] && echo '{out}'\n")
        stub.chmod(0o755)

    def run_check(self, **env_set):
        env = {k: v for k, v in os.environ.items() if k not in ("CCP_LEAK_DENYLIST", "CCP_BINDINGS_DIR")}
        env["PATH"] = f"{self.bin}:/usr/bin:/bin"
        env.update(env_set)
        return subprocess.run(["bash", str(self.repo / "scripts/leak-check.sh")], capture_output=True, text=True, env=env)

    def test_bindings_dir_denylist_is_found_and_a_match_fails(self):
        self.denylist(self.bindings)
        r = self.run_check(CCP_BINDINGS_DIR=str(self.bindings))
        self.assertEqual(r.returncode, 1)
        self.assertIn("leak-check: denylist found (bindings dir)", r.stdout)
        self.assertIn("notes.txt:1", r.stderr)
        self.assertNotIn(str(self.bindings), r.stdout + r.stderr)

    def test_bindings_dir_denylist_with_no_match_is_clean(self):
        self.denylist(self.bindings, "zz-no-such-" + "token-qq")
        r = self.run_check(CCP_BINDINGS_DIR=str(self.bindings))
        self.assertEqual(r.returncode, 0)
        self.assertIn("leak-check: denylist found (bindings dir)", r.stdout)
        self.assertIn("leak-check: clean", r.stdout)

    def test_env_denylist_wins_over_the_bindings_dir(self):
        self.denylist(self.bindings)  # would match
        named = self.tmp / "named.txt"
        named.write_text("zz-no-such-" + "token-qq\n")
        r = self.run_check(CCP_BINDINGS_DIR=str(self.bindings), CCP_LEAK_DENYLIST=str(named))
        self.assertEqual(r.returncode, 0)
        self.assertIn("leak-check: denylist found (CCP_LEAK_DENYLIST)", r.stdout)
        self.assertNotIn(str(named), r.stdout + r.stderr)

    def test_a_named_but_missing_env_denylist_exits_2(self):
        r = self.run_check(CCP_LEAK_DENYLIST=str(self.tmp / "missing.txt"), CCP_BINDINGS_DIR=str(self.bindings))
        self.assertEqual(r.returncode, 2)

    def test_bindings_dir_without_a_denylist_checks_nothing_even_if_ccp_names_one(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.denylist(elsewhere)
        self.stub_ccp(elsewhere / "x.yaml", elsewhere)
        r = self.run_check(CCP_BINDINGS_DIR=str(self.bindings))  # empty directory
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing checked", r.stdout)
        self.assertNotIn("leak-check: denylist found", r.stdout)

    def test_ccp_where_binding_directory_is_searched_when_bindings_dir_is_unset(self):
        installation = self.tmp / "installation"
        installation.mkdir()
        self.denylist(installation)
        self.stub_ccp(installation / "p.yaml", self.tmp / "no-plane")
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("leak-check: denylist found (bindings dir)", r.stdout)
        self.assertNotIn(str(installation), r.stdout + r.stderr)

    def test_ccp_where_plane_projects_is_searched_when_it_names_no_binding(self):
        plane = self.tmp / "plane"
        (plane / "projects").mkdir(parents=True)
        self.denylist(plane / "projects")
        self.stub_ccp(None, plane)
        r = self.run_check()
        self.assertEqual(r.returncode, 1)
        self.assertIn("leak-check: denylist found (bindings dir)", r.stdout)

    def test_a_ccp_that_fails_or_prints_junk_falls_through_to_nothing_checked(self):
        stub = self.bin / "ccp"
        for body in ("exit 1", "echo not-json", "echo '{\"plane\": 3}'"):
            stub.write_text(f"#!/bin/sh\n{body}\n")
            stub.chmod(0o755)
            r = self.run_check()
            self.assertEqual(r.returncode, 0, body)
            self.assertIn("nothing checked", r.stdout, body)

    def test_no_denylist_anywhere_passes_with_nothing_checked(self):
        r = self.run_check()  # no ccp on PATH, no variable
        self.assertEqual(r.returncode, 0)
        self.assertIn("leak-check: no denylist found (CCP_LEAK_DENYLIST, the bindings directory): nothing checked", r.stdout)
        r = self.run_check(CCP_BINDINGS_DIR=str(self.bindings))
        self.assertEqual(r.returncode, 0)
        self.assertIn("nothing checked", r.stdout)


if __name__ == "__main__":
    unittest.main()
