"""Only the PR-host adapter names a forge's CLI (ADR-0040 D1, D6; SPEC §18.5): the worker prompts and the
agent briefs reach the PR host through `ccp pr`, no plane module outside the adapter names `gh` or reads its
override, and each rendered prompt carries its `ccp` command's `pr` operation. Read-only against this repo's
templates, briefs and code."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from ccp import config, prompt
from tests.helpers import REPORT_HEAD as HEAD
from tests.toolkit_fixture import ToolkitFixture

ROOT = Path(__file__).resolve().parents[1]
FORGE_CLI = re.compile(r"(?<![\w-])gh (?:pr|api)\b")
ADAPTER_MODULES = {"ccp/prhost.py"}  # the adapter


def forge_lines(paths: list[Path]) -> list[str]:
    """Each `path:line` among `paths` that names a forge's CLI."""
    return [f"{p.relative_to(ROOT)}:{n}" for p in paths
            for n, line in enumerate(p.read_text().splitlines(), 1) if FORGE_CLI.search(line)]


def forge_literals(path: Path) -> list[str]:
    """Each `path:line` of `path` holding the string literal `gh` or naming the CLI override."""
    tree = ast.parse(path.read_text(), str(path))
    return [f"{path.relative_to(ROOT)}:{node.lineno}" for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and (node.value == "gh" or "CCP_GH_BIN" in node.value)]


class NoForgeCli(unittest.TestCase):
    def test_no_prompt_or_agent_brief_names_a_forge_cli(self):
        paths = sorted((ROOT / "templates/prompts").glob("*.md")) + sorted((ROOT / "plugin/agents").glob("*.md"))
        self.assertTrue(paths)
        self.assertEqual(forge_lines(paths), [])

    def test_no_module_outside_the_adapter_names_the_forge_cli(self):
        modules = [p for p in sorted((ROOT / "ccp").rglob("*.py"))
                   if str(p.relative_to(ROOT)) not in ADAPTER_MODULES]
        self.assertTrue(modules)
        self.assertEqual([hit for p in modules for hit in forge_literals(p)], [])


class RenderedPrompts(ToolkitFixture, unittest.TestCase):
    def test_each_worker_prompt_reaches_the_pr_host_through_ccp_pr(self):
        self.ccp("tasks", "claim", "0002")
        ccp = prompt.ccp_command(config.load(self.runner))
        for args, ops in ((("implement", "0002", "--base", "abc1234"), ("open",)),
                          (("review", "0002", "--pr", "7", "--head", HEAD), ("diff",)),
                          (("verify", "0002", "--pr", "7", "--head", HEAD), ("diff", "view"))):
            code, body, out, err = self.ccp("prompt", *args)
            self.assertEqual(code, 0, out + err)
            text = Path(body["prompt_path"]).read_text()
            for op in ops:
                self.assertIn(f"{ccp} pr {op} ", text, f"{args[0]}: {op}")
            self.assertEqual(FORGE_CLI.findall(text), [], args[0])


if __name__ == "__main__":
    unittest.main()
