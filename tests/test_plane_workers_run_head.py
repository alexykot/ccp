"""The plane's own workers run the head they change (SPEC §12.1, §29.2): a product whose checkout carries
its own `bin/ccp` renders a worker prompt's `ccp` as `ccp wt exec --`, and a `ccp wt exec` child gives no
checkout warning, while a plain run off `main` still does."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import cli, prompt, wt
from ccp.queue import CCP_BIN
from tests.helpers import GIT_ENV
from tests.report_helpers import done_report, REPORT_HEAD as HEAD
from tests.toolkit_fixture import ToolkitFixture

WT_EXEC = "wt exec --"


def product(root: Path, own_ccp: bool, managed: bool = False) -> SimpleNamespace:
    if own_ccp:
        (root / "bin").mkdir(parents=True, exist_ok=True)
        (root / "bin" / "ccp").write_text("")
    if managed:
        (root / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "agents" / "delivery-implementer.md").write_text("")
    return SimpleNamespace(root=root)


class CcpCommand(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def render(self, on_path: bool) -> str:
        with mock.patch("shutil.which", return_value="/usr/local/bin/ccp" if on_path else None):
            return prompt.ccp_command(self.cfg)

    def test_a_product_without_its_own_bin_ccp_gets_ccp_on_path(self):
        self.cfg = product(self.root, own_ccp=False)
        self.assertEqual(self.render(on_path=True), "ccp")

    def test_a_checkout_with_its_own_bin_ccp_gets_wt_exec(self):
        self.cfg = product(self.root, own_ccp=True)
        self.assertEqual(self.render(on_path=True), f"ccp {WT_EXEC}")

    def test_without_ccp_on_path_wt_exec_goes_through_the_plane_path(self):
        self.cfg = product(self.root, own_ccp=True)
        self.assertEqual(self.render(on_path=False), f"{CCP_BIN} {WT_EXEC}")
        self.cfg = product(Path(self._tmp.name) / "other", own_ccp=False)
        self.assertEqual(self.render(on_path=False), str(CCP_BIN))

    def test_managed_copies_keep_the_plane_path_and_still_run_the_head(self):
        self.cfg = product(self.root, own_ccp=True, managed=True)
        self.assertEqual(self.render(on_path=True), f"{CCP_BIN} {WT_EXEC}")


CHILD = """\
import os, sys
from pathlib import Path
Path(sys.argv[1]).write_text(repr(os.environ.get(sys.argv[2])))
"""


class ExecChild(unittest.TestCase):
    def test_the_child_gets_the_marker_and_the_caller_keeps_its_environment(self):
        with tempfile.TemporaryDirectory() as d:
            exe, out = Path(d) / "ccp", Path(d) / "env.txt"
            exe.write_text(CHILD)
            env = {k: v for k, v in os.environ.items() if k != wt.EXEC_CHILD}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(wt.exec_ccp(exe, [str(out), wt.EXEC_CHILD]), 0)
                self.assertNotIn(wt.EXEC_CHILD, os.environ)
            self.assertNotIn(out.read_text(), ("None", "''"))  # set, and not empty: `envvar` reads empty as unset


def off_main_repo(d: Path) -> Path:
    repo = d / "plane"
    repo.mkdir()
    for args in (["init", "-q", "-b", "topic"], ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True,
                       env={**os.environ, **GIT_ENV})
    return repo


class CheckoutWarningInAChild(unittest.TestCase):
    def test_a_wt_exec_child_gives_no_warning_and_a_plain_run_off_main_does(self):
        with tempfile.TemporaryDirectory() as d:
            repo = off_main_repo(Path(d))
            env = {k: v for k, v in os.environ.items() if k != wt.EXEC_CHILD}
            with mock.patch("ccp.queue.PLANE", repo), mock.patch.dict(os.environ, {**env, "CCP_DEV": "0"}, clear=True):
                self.assertIn("not main", cli.checkout_warning() or "")
                os.environ[wt.EXEC_CHILD] = "1"
                self.assertIsNone(cli.checkout_warning())


class RenderedPrompt(ToolkitFixture, unittest.TestCase):
    """The verify prompt of a product whose checkout carries `bin/ccp` names the head's `ccp`."""

    def verify_prompt(self) -> str:
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", HEAD)
        self.assertEqual(code, 0, out + err)
        return Path(body["prompt_path"]).read_text()

    def test_a_checkout_with_its_own_bin_ccp_renders_wt_exec(self):
        (self.runner / "bin").mkdir()
        (self.runner / "bin" / "ccp").write_text("")
        text = self.verify_prompt()
        self.assertIn(f"{WT_EXEC} verify record <file>", text)
        self.assertIn(f"{WT_EXEC} <args>", text)
        self.assertIn(f"{WT_EXEC} mutate --run", text)

    def test_a_product_without_one_renders_no_wt_exec(self):
        self.assertNotIn(WT_EXEC, self.verify_prompt())


# A command line a worker runs against the queue, naming `ccp` without going through the head's (SPEC §12.1).
RUN_LINE = re.compile(r"QUEUE_ROOT=\S+ \S*ccp (?!wt exec -- )\S+")


class EveryPhaseRunsTheHead(ToolkitFixture, unittest.TestCase):
    """Each worker prompt of a product whose checkout carries `bin/ccp` names the head's `ccp` for the
    commands the worker runs: the shared rules (suite runs, mutation runs, the report) and the phase's own."""

    def open(self, phase: str, *args: str, report: tuple[str, ...]) -> tuple[str, str]:
        code, body, out, err = self.ccp("prompt", phase, "0002", *args)
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        code, _, out, err = self.report(body["run_id"], done_report(phase, *report))
        self.assertEqual(code, 0, out + err)
        return body["run_id"], text

    def prompts(self) -> dict:
        (self.runner / "bin").mkdir()
        (self.runner / "bin" / "ccp").write_text("")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        pr = ("--pr", "7", "--head", HEAD)
        return {"implement": self.open("implement", "--base", "abc1234", report=("PR: #7", f"Head: {HEAD}")),
                "review": self.open("review", *pr, report=("Severity: BLOCKER=1 MAJOR=0 MINOR=0 NIT=0",)),
                "fix": self.open("fix", *pr, report=("PR: #7", f"Head: {HEAD}"))}

    def test_the_commands_a_worker_runs_are_the_rendered_ccp(self):
        texts = self.prompts()
        self.assertIn(f"{WT_EXEC} <args>", texts["review"][1])  # review's rule for checks by hand
        for phase, (run_id, text) in texts.items():
            self.assertIn(f"{WT_EXEC} suite run --run", text, phase)
            self.assertIn(f"{WT_EXEC} suite run` and `", text, phase)
            self.assertIn(f"{WT_EXEC} mutate` the Bash tool's full limit", text, phase)
            self.assertIn(f"{WT_EXEC} mutate --run", text, phase)
            self.assertIn(f"{WT_EXEC} report {run_id} ", text, phase)
            self.assertIn(f"{WT_EXEC} report` again with that file", text, phase)
            self.assertEqual([m.group(0) for m in RUN_LINE.finditer(text)], [], phase)

    def test_the_report_fallback_needs_no_root_flag(self):
        _, text = self.prompts()["review"]
        self.assertIn("if it is already gone, run `report` from ", text)
        self.assertNotIn("before `report`", text)


if __name__ == "__main__":
    unittest.main()
