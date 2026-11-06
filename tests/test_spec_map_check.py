"""scripts/spec_map_check.py: the SPEC restructure's map checks (ADR-0033)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "spec_map_check.py"


def run(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True)


class OnTheRepo(unittest.TestCase):
    def test_coverage_is_clean(self):
        r = run("coverage")
        self.assertEqual(r.returncode, 0, r.stdout)


class OnAFixture(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "docs/spec/map").mkdir(parents=True)
        (self.d / "docs/design").mkdir(parents=True)
        (self.d / "docs/cli").mkdir(parents=True)
        (self.d / "SPEC.md").write_text("# SPEC\n\n## 1. Purpose\n\nUse `alpha`.\n\n### 1.1 Detail\n\nAnd `beta`.\n\n## 2. Gone\n\nOld.\n")
        (self.d / "docs/spec/RULINGS.md").write_text("| Old § | Rule |\n|---|---|\n")
        for n in ("02-delivery", "03-quality", "04-observability", "05-operations"):
            (self.d / f"docs/spec/{n}.md").write_text("# part\n")
            (self.d / f"docs/spec/map/{n}.md").write_text("# map\n")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def write_part(self, part: str, rows: str) -> None:
        (self.d / "docs/spec/01-model.md").write_text(part)
        (self.d / "docs/spec/map/01-model.md").write_text("# map\n\nDropped tokens: none.\n\n| Old | Title | Targets | Note |\n|---|---|---|---|\n" + rows)
        (self.d / "docs/spec/map/dropped.md").write_text("| Old | Title | Targets | Note |\n|---|---|---|---|\n| §4 | Gone | dropped (history) |  |\n")

    def test_coverage_finds_an_unmapped_heading(self):
        self.write_part("# I\n", "| §1 | Purpose | §1 |  |\n")
        r = run("coverage", cwd=self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("§1.1", r.stdout)

    def test_part_requires_refined_targets_headings_and_tokens(self):
        self.write_part("# I\n\n## 1. Purpose\n\n### 1.1 Use\n\nUse `alpha`.\n",
                        "| §1 | Purpose | §1.1 |  |\n| §1.1 | Detail | §1 |  |\n")
        r = run("part", "01", cwd=self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("§1.1: target §1 is not refined", r.stdout)
        self.assertIn("`beta` appears in no part", r.stdout)

    def test_a_complete_part_is_clean(self):
        self.write_part("# I\n\n## 1. Purpose\n\n### 1.1 Use\n\nUse `alpha` and `beta`.\n",
                        "| §1 | Purpose | §1.1 |  |\n| §1.1 | Detail | §1.1 |  |\n")
        self.assertEqual(run("part", "01", cwd=self.d).returncode, 0)

    def test_an_operator_row_must_be_in_rulings(self):
        self.write_part("# I\n\n## 1. Purpose\n\n### 1.1 Use\n\nUse `alpha` and `beta`.\n",
                        "| §1 | Purpose | §1.1, operator (obsolete?) |  |\n| §1.1 | Detail | §1.1 |  |\n")
        r = run("part", "01", cwd=self.d)
        self.assertIn("not listed in docs/spec/RULINGS.md", r.stdout)

    def test_refs_finds_a_reference_to_no_heading(self):
        self.write_part("# I\n\n## 1. Purpose\n\n### 1.1 Use\n", "")
        (self.d / "x.md").write_text("see §1.1 and §15.1\n")
        r = run("refs", "x.md", cwd=self.d)
        self.assertEqual(r.returncode, 1)
        self.assertIn("§15.1", r.stdout)
        self.assertNotIn("§1 names", r.stdout)


if __name__ == "__main__":
    unittest.main()
