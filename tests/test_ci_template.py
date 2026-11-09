"""SPEC §15.7, ADR-0034 D12: the optional CI template ships neutral defaults. Its job has no database
service, an empty STORE_TEST_PATTERN and EXPECT_STORE_TESTS "0", and its store-test step checks
nothing at those defaults; a product that names a pattern and sets EXPECT_STORE_TESTS=1 gets the
skip and no-match failures."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

PLANE = Path(__file__).resolve().parents[1]
TEMPLATE = PLANE / "templates/github/workflows/formal-unit-lint.yml"


def _job_lines(text: str) -> list[str]:
    """The lines of the template's single job, from its key to the end of the file."""
    lines = text.splitlines()
    start = lines.index("jobs:")
    return lines[start + 2:]


def _job_env(text: str) -> dict[str, str]:
    """The job-level `env:` mapping (four-space key, six-space entries), values unquoted."""
    out: dict[str, str] = {}
    inside = False
    for ln in _job_lines(text):
        if ln == "    env:":
            inside = True
            continue
        if inside:
            if not ln.startswith("      ") or ln.strip().startswith("-"):
                break
            key, _, value = ln.strip().partition(":")
            out[key] = value.strip().strip('"')
    return out


def _store_check(text: str) -> str:
    """The Python the store-test step runs (its heredoc body)."""
    body = text.split("python3 - <<'PY'\n", 1)[1].split("\n          PY\n", 1)[0]
    return textwrap.dedent(body)


class CITemplateDefaults(unittest.TestCase):
    def setUp(self):
        self.text = TEMPLATE.read_text(encoding="utf-8")

    def test_job_has_no_service_block(self):
        keys = {ln.strip().rstrip(":") for ln in _job_lines(self.text)
                if ln.startswith("    ") and not ln.startswith("     ") and ln.strip().endswith(":")}
        self.assertIn("steps", keys)
        self.assertNotIn("services", keys)

    def test_store_settings_are_neutral(self):
        env = _job_env(self.text)
        self.assertEqual(env.get("STORE_TEST_PATTERN"), "")
        self.assertEqual(env.get("EXPECT_STORE_TESTS"), "0")
        self.assertNotIn("DATABASE_URL", env)


class CITemplateStoreCheck(unittest.TestCase):
    SKIPPED_STORE = "test_store_roundtrip (tests.test_store.T) ... skipped 'no database'\n"
    PASSED_STORE = "test_store_roundtrip (tests.test_store.T) ... ok\n"
    PASSED_OTHER = "test_parse (tests.test_parse.T) ... ok\n"

    def setUp(self):
        self.code = _store_check(TEMPLATE.read_text(encoding="utf-8"))
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _run(self, unit_out: str, pattern: str, expect: str) -> int:
        Path(self.tmp.name, "unit.out").write_text(unit_out, encoding="utf-8")
        env = {**os.environ, "STORE_TEST_PATTERN": pattern, "EXPECT_STORE_TESTS": expect}
        return subprocess.run([sys.executable, "-I", "-c", self.code], cwd=self.tmp.name, env=env,
                              capture_output=True, text=True).returncode

    def test_defaults_pass_even_with_skips(self):
        self.assertEqual(self._run(self.SKIPPED_STORE + self.PASSED_OTHER, "", "0"), 0)

    def test_defaults_pass_with_no_store_tests(self):
        self.assertEqual(self._run(self.PASSED_OTHER, "", "0"), 0)

    def test_expecting_store_tests_without_a_pattern_fails(self):
        self.assertEqual(self._run(self.PASSED_STORE, "", "1"), 1)

    def test_skipped_matching_test_fails(self):
        self.assertEqual(self._run(self.SKIPPED_STORE + self.PASSED_OTHER, "store", "1"), 1)

    def test_no_matching_test_fails_when_expected(self):
        self.assertEqual(self._run(self.PASSED_OTHER, "store", "1"), 1)

    def test_matching_tests_that_ran_pass(self):
        self.assertEqual(self._run(self.PASSED_STORE + self.PASSED_OTHER, "store", "1"), 0)


if __name__ == "__main__":
    unittest.main()
