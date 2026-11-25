"""SPEC §29.3: a release (`run-checkout.sh update`) checks each bound product's integration branch with
the new `ccp` and reports what went stale, writing nothing to the product."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.git_helpers import git, run
from tests.helpers import binding, PLANE_ROOT, RUN_CHECKOUT_SCRIPT as SCRIPT

OLD_CCP = "#!/bin/sh\nexit 0\n"  # the old rules: every check passes
NEW_CCP = f'#!/bin/sh\nexec python3 "{PLANE_ROOT}/bin/ccp" "$@"\n'  # the new rules: this plane's ccp
BAD_ADR = "---\nstatus: bogus\n---\n# An ADR\n"


def snapshot(root: Path) -> dict[str, tuple[int, int]]:
    """Every file under the product, its .git included: size and mtime."""
    out = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            st = os.lstat(os.path.join(dp, f))
            out[os.path.relpath(os.path.join(dp, f), root)] = (st.st_size, st.st_mtime_ns)
    return out


class ReleaseChecksProducts(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.origin, self.seed, self.run_dir = self.d / "origin.git", self.d / "seed", self.d / "run"
        run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)])
        run(["git", "clone", "-q", str(self.origin), str(self.seed)])
        git(self.seed, "checkout", "-q", "-b", "main")
        self.plane_commit(OLD_CCP, "old rules")
        run(["git", "clone", "-q", str(self.origin), str(self.run_dir)])
        (self.run_dir / "projects").mkdir()
        # The run checkout's binding parser, present and untracked as a clean checkout's code is: the
        # release reads each binding through it.
        (self.run_dir / "ccp").mkdir(parents=True)
        shutil.copy(PLANE_ROOT / "ccp/lib.py", self.run_dir / "ccp/lib.py")
        self.env = {"CCP_RUN_CHECKOUT": str(self.run_dir), "CCP_BIN_LINK": str(self.d / "bin/ccp"),
                    "CCP_BINDINGS_DIR": str(self.run_dir / "projects")}

    def tearDown(self):
        self._tmp.cleanup()

    def plane_commit(self, ccp: str, msg: str) -> None:
        (self.seed / "bin").mkdir(exist_ok=True)
        (self.seed / "bin/ccp").write_text(ccp)
        (self.seed / "bin/ccp").chmod(0o755)
        git(self.seed, "add", "bin/ccp")
        git(self.seed, "commit", "-qm", msg)
        git(self.seed, "push", "-q", "origin", "main")

    def product(self, name: str, adr: bool, branch: str = "main") -> Path:
        """A git product that passes this plane's checks on `branch`."""
        root = self.d / name
        (root / "docs/delivery/tasks").mkdir(parents=True)
        (root / "docs/delivery/tasks/.gitkeep").write_text("")  # git keeps no empty task log
        cfg = {"project_id": name, **({"adr": {"dir": "docs/adr"}} if adr else {})}
        (root / "docs/delivery/plane.json").write_text(json.dumps(cfg))
        git(root, "init", "-q", "-b", branch)
        r = run([str(PLANE_ROOT / "bin/ccp"), "--root", str(root), "tasks", "index"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        git(root, "add", "docs")
        git(root, "commit", "-qm", "conforming")
        return root

    def bind(self, name: str, root: Path, branch: str = "main") -> None:
        (self.run_dir / "projects" / f"{name}.yaml").write_text(
            binding(project_id=name, product_root=f"{root}  # the checkout", integration_branch=f"'{branch}'"))

    def update(self) -> subprocess.CompletedProcess:
        r = run([SCRIPT, "update"], env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def product_line(self, out: str, name: str) -> str:
        lines = [x for x in out.splitlines() if x.split(":")[:2] == ["run-checkout", f" product {name}"]
                 or x.startswith(f"run-checkout: product {name} (")]
        self.assertEqual(len(lines), 1, out)
        return lines[0]

    def test_a_tightened_check_names_the_product_and_the_check_and_writes_nothing(self):
        root = self.product("stale", adr=True)
        (root / "docs/adr").mkdir()
        (root / "docs/adr/0001-x.md").write_text(BAD_ADR)  # what the old rules let through
        git(root, "add", "docs/adr")
        git(root, "commit", "-qm", "an adr")
        self.bind("stale", root)
        self.assertTrue(self.product_line(self.update().stdout, "stale").endswith(": clean"))
        self.plane_commit(NEW_CCP, "tightened rules")
        before = snapshot(root)
        r = self.update()
        line = self.product_line(r.stdout, "stale")
        self.assertIn("STALE", line)
        self.assertIn("ccp adr check", line)
        self.assertIn("ccp docs check", line)
        self.assertNotIn("ccp tasks check", line)
        self.assertIn("docs/adr/0001-x.md", r.stdout)  # the failing check's own output follows
        self.assertEqual(snapshot(root), before)

    def test_a_conforming_product_is_reported_clean(self):
        root = self.product("green", adr=False, branch="develop")
        self.bind("green", root, branch="develop")
        # Neither another branch nor the working tree is the integration branch.
        git(root, "checkout", "-q", "-b", "wip")
        (root / "docs/delivery/tasks/0001-broken.md").write_text("not a task\n")
        git(root, "add", "docs")
        git(root, "commit", "-qm", "wip")
        (root / "docs/delivery/INDEX.yaml").write_text("broken: [\n")
        self.plane_commit(NEW_CCP, "new rules")
        r = self.update()
        self.assertTrue(self.product_line(r.stdout, "green").endswith(": clean"), r.stdout)
        self.assertNotIn("STALE", r.stdout)

    def test_the_branch_as_last_fetched_is_checked_before_the_local_one(self):
        root = self.product("fetched", adr=True)
        good = git(root, "rev-parse", "HEAD")
        (root / "docs/adr").mkdir()
        (root / "docs/adr/0001-x.md").write_text(BAD_ADR)
        git(root, "add", "docs/adr")
        git(root, "commit", "-qm", "an adr")
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(root, "reset", "-q", "--hard", good)  # local main is behind what was fetched
        self.bind("fetched", root)
        self.plane_commit(NEW_CCP, "new rules")
        self.assertIn("STALE", self.product_line(self.update().stdout, "fetched"))

    def test_a_binding_without_a_repository_or_its_branch_is_not_checked(self):
        self.bind("gone", self.d / "nowhere")
        self.bind("nobranch", self.product("nobranch", adr=False), branch="release")
        self.plane_commit(NEW_CCP, "new rules")
        r = self.update()
        self.assertIn("not checked", self.product_line(r.stdout, "gone"))
        self.assertIn("not checked", self.product_line(r.stdout, "nobranch"))

    def test_a_product_that_has_not_adopted_ccp_is_not_checked(self):
        root = self.d / "unadopted"
        root.mkdir()
        (root / "README.md").write_text("a product\n")
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "README.md")
        git(root, "commit", "-qm", "no plane.json")
        self.bind("unadopted", root)
        self.plane_commit(NEW_CCP, "new rules")
        r = self.update()
        line = self.product_line(r.stdout, "unadopted")
        self.assertIn("not checked", line)
        self.assertIn("docs/delivery/plane.json", line)
        self.assertNotIn("STALE", r.stdout)
        self.assertNotIn("tell each one's lead", r.stdout)

    def test_a_run_checkout_without_the_binding_parser_checks_no_product(self):
        self.bind("any", self.product("any", adr=False))
        (self.run_dir / "ccp/lib.py").unlink()
        self.plane_commit(NEW_CCP, "new rules")
        r = self.update()
        self.assertIn("ccp/lib.py; bound products not checked", r.stderr)
        self.assertNotIn("product any", r.stdout)

    def test_a_check_that_prints_a_lot_neither_kills_the_update_nor_floods_it(self):
        self.bind("big", self.product("big", adr=False))
        self.bind("later", self.product("later", adr=False))
        self.plane_commit("#!/bin/sh\npython3 -c \"import sys; sys.stdout.write('noise\\n' * 40000)\"\nexit 1\n",
                          "a check that prints 240 KB and fails")
        r = self.update()
        self.assertIn("STALE", self.product_line(r.stdout, "big"))
        self.assertIn("STALE", self.product_line(r.stdout, "later"))  # the products after it are still checked
        self.assertIn("2 product(s) went stale", r.stdout)
        self.assertEqual(r.stdout.count("    noise\n"), 2 * 2 * 20)  # two checks per product, 20 lines each


if __name__ == "__main__":
    unittest.main()
