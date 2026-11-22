"""The parser, `ccp.cli.build_parser()`, is the one source of the command surface; this is the one test that holds
the hand-written call syntax in `docs/cli/*.md` to it: every command and long flag the parser defines is written
down, and every `ccp` command and flag the docs name is one the parser defines. No module docstring holds call
syntax of its own: the docs are the one place it is written."""
from __future__ import annotations

import argparse
import ast
import re
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from ccp import cli
from tests.helpers import PLANE_ROOT

ROOT = PLANE_ROOT
DOCS = ROOT / "docs" / "cli"
USAGE_LINE = re.compile(r"^\s*ccp [a-z]")
# A backticked `ccp` span holding call syntax: a `<placeholder>`, a `[flag]`, a `|` alternation or an upper-case
# metavariable. A bare command name is not call syntax.
CALL_SYNTAX = re.compile(r"^\s*`ccp [^`]*(?:[<\[|]|\b[A-Z][A-Z_]+\b)")
# A command that parses its own words past the parser's first (`ccp.cli.main` hands it the rest): its name is
# held, its own subcommands and flags are `ccp otel -h`'s.
DELEGATED = ("otel",)

SPAN = re.compile(r"`([^`]+)`")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z0-9-]*")
WORDS = re.compile(r"(?<![\w./<-])ccp((?: +[a-z][a-z0-9-]*(?:\|[a-z][a-z0-9-]*)*)+)")


@dataclass
class Node:
    """One parser: its long flags, its subcommands and, for a command that takes its subcommand as a first
    `action` word, those words."""
    flags: set[str] = field(default_factory=set)
    subs: dict[str, "Node"] = field(default_factory=dict)
    actions: tuple[str, ...] = ()
    default_action: str | None = None


def node_of(parser: argparse.ArgumentParser) -> Node:
    node = Node()
    for a in parser._actions:  # noqa: SLF001  (argparse keeps no public list of a parser's arguments)
        if isinstance(a, argparse._SubParsersAction):  # noqa: SLF001
            node.subs = {name: node_of(p) for name, p in a.choices.items()}
        elif a.option_strings:
            if a.help != argparse.SUPPRESS:
                node.flags |= {o for o in a.option_strings if o.startswith("--") and o != "--help"}
        elif a.dest == "action" and a.choices:
            node.actions, node.default_action = tuple(a.choices), a.default
    return node


def units(text: str) -> list[list[str]]:
    """The doc's code, grouped as it is read together: a table row, a line of a fenced block, or a paragraph."""
    out: list[list[str]] = []
    block: list[str] = []
    fenced = False
    for line in [*text.splitlines(), ""]:
        if line.startswith("```"):
            fenced = not fenced
        elif fenced:
            out.append([line])
        elif line.startswith("|"):
            out.append(SPAN.findall(line.replace("\\|", "|")))
        elif line.strip():
            block += SPAN.findall(line)
        elif block:
            out.append(block)
            block = []
    return [u for u in out if u]


def paths_in(root: Node, code: str, problems: list[str]) -> list[tuple[str, ...]]:
    """The commands (as words, an action included) the `ccp ...` in `code` names; a word the parser does not
    define goes to `problems`."""
    found: list[tuple[str, ...]] = []
    for m in WORDS.finditer(code):
        paths: list[tuple[str, ...]] = [()]
        for alts in (w.split("|") for w in m.group(1).split()):
            nxt: list[tuple[str, ...]] = []
            for path in paths:
                node = at(root, path)
                if node.subs:
                    wanted = node.subs
                elif node.actions and path[-1:] and path[-1] not in node.actions:
                    wanted = {a: None for a in node.actions}
                else:
                    nxt.append(path)  # a leaf: what follows is an argument
                    continue
                for alt in alts:
                    if alt in wanted:
                        nxt.append((*path, alt))
                    elif node.subs or not node.default_action:
                        problems.append(f"`ccp {' '.join((*path, alt))}`: the parser has no such command")
            paths = nxt
        found += paths
    return found


def at(root: Node, path: tuple[str, ...]) -> Node:
    node = root
    for word in path:
        if word not in node.subs:
            break  # an action word: the same parser
        node = node.subs[word]
    return node


def leaves(root: Node, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], Node]]:
    if not root.subs:
        return [(path, root)]
    return [leaf for name, sub in root.subs.items() for leaf in leaves(sub, (*path, name))]


def delegates(paths: list[tuple[str, ...]]) -> bool:
    """Whether one of `paths` is a delegated command, whose own flags are its own."""
    return any(not p[:1] or p[0] in DELEGATED for p in paths)


def problems_of(docs: Path) -> list[str]:
    root = node_of(cli.build_parser())
    problems: list[str] = []
    named: set[tuple[str, ...]] = set()
    credited: dict[tuple[str, ...], set[str]] = {}
    every_flag: set[str] = set()
    for f in sorted(docs.glob("*.md")):
        for unit in units(f.read_text()):
            spans = [(FLAG.findall(code), paths_in(root, code, problems)) for code in unit]
            flags = {fl for fls, _ in spans for fl in fls}
            every_flag |= flags
            here = [p for _, ps in spans for p in ps]
            named |= set(here)
            nodes = [at(root, p) for p in here] if not delegates(here) else []
            allowed = root.flags | {"--help"}
            for fls, ps in spans:
                if not ps:  # a span that names no command is read against its unit's, unless one of them is delegated
                    if delegates(here):
                        continue
                    for p in here:
                        credited.setdefault(strip_action(root, p), set()).update(fls)
                    for fl in sorted(set(fls) - allowed - {fl for n in nodes for fl in n.flags}) if nodes else []:
                        problems.append(f"{f.name}: `{fl}` is no flag of {' / '.join('`ccp ' + ' '.join(p) + '`' for p in here)}")
                    continue
                if delegates(ps):
                    continue
                for p in ps:  # a span that names commands holds its flags to each of them, and credits only them
                    credited.setdefault(strip_action(root, p), set()).update(fls)
                    for fl in sorted(set(fls) - allowed - at(root, p).flags):
                        problems.append(f"{f.name}: `{fl}` is no flag of `ccp {' '.join(p)}`")
    for path, node in leaves(root):
        shown = " ".join(path)
        if not node.actions:
            if path not in named:
                problems.append(f"docs/cli names no `ccp {shown}`")
        else:
            for a in node.actions:
                if (*path, a) not in named and not (a == node.default_action and path in named):
                    problems.append(f"docs/cli names no `ccp {shown} {a}`")
        if path[0] not in DELEGATED:
            for fl in sorted(node.flags - credited.get(path, set())):
                problems.append(f"docs/cli gives `ccp {shown}` no `{fl}`")
    for fl in sorted(root.flags - every_flag):
        problems.append(f"docs/cli names no global `{fl}`")
    return problems


def strip_action(root: Node, path: tuple[str, ...]) -> tuple[str, ...]:
    node = at(root, path)
    return path[:-1] if node.actions and path[-1:] and path[-1] in node.actions else path


def module_docstrings() -> list[tuple[Path, str]]:
    """Each ccp module's docstring, as written."""
    paths = sorted([*(ROOT / "ccp").glob("*.py"), *(ROOT / "ccp" / "doclang").glob("*.py")])
    return [(p, ast.get_docstring(ast.parse(p.read_text()), clean=False) or "") for p in paths]


class CliReference(unittest.TestCase):
    def test_the_docs_hold_the_parsers_commands_and_flags_and_no_others(self):
        self.assertEqual(problems_of(DOCS), [])

    def test_no_module_docstring_carries_a_usage_line(self):
        found = []
        for path, doc in module_docstrings():
            found += [f"{path.relative_to(ROOT)}: {l.strip()}" for l in doc.splitlines() if USAGE_LINE.match(l)]
        self.assertEqual(found, [])

    def test_no_module_docstring_opens_with_call_syntax(self):
        found = [f"{path.relative_to(ROOT)}: {doc.splitlines()[0]}" for path, doc in module_docstrings()
                 if doc.splitlines() and CALL_SYNTAX.match(doc.splitlines()[0])]
        self.assertEqual(found, [])

    def copy_with(self, old: str, new: str) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        for f in DOCS.glob("*.md"):
            text = f.read_text()
            (d / f.name).write_text(text.replace(old, new) if old in text else text)
        self.assertTrue(any(old in f.read_text() for f in DOCS.glob("*.md")), old)
        return d

    def test_a_flag_the_docs_leave_out_is_found(self):
        d = self.copy_with(" [--allow-overdue REASON]", "")
        self.assertEqual(problems_of(d), ["docs/cli gives `ccp tasks next` no `--allow-overdue`"])

    def test_a_flag_the_parser_does_not_define_is_found(self):
        d = self.copy_with("`ccp tasks index [--stdout]` | lead", "`ccp tasks index [--stdout] [--no-such-flag]` | lead")
        self.assertEqual(problems_of(d), ["02-delivery.md: `--no-such-flag` is no flag of `ccp tasks index`"])

    def test_a_joined_row_giving_an_action_its_siblings_flags_is_found(self):
        d = self.copy_with("`ccp adr index [--stdout]` | regenerate the ADR index | §6.6 |\n| `ccp adr list [--json] [--dir DIR]` | every ADR's frontmatter |",
                           "`ccp adr index\\|list [--stdout] [--json] [--dir DIR]` | the ADR index, or every ADR's frontmatter |")
        self.assertEqual(sorted(problems_of(d)), [
            "01-model.md: `--dir` is no flag of `ccp adr index`",
            "01-model.md: `--json` is no flag of `ccp adr index`",
            "01-model.md: `--stdout` is no flag of `ccp adr list`",
        ])

    def test_a_flag_left_out_of_one_span_is_not_credited_from_its_siblings(self):
        d = self.copy_with("`ccp tasks resume <id> [--detail …]`", "`ccp tasks resume <id>`")
        self.assertEqual(problems_of(d), ["docs/cli gives `ccp tasks resume` no `--detail`"])

    def test_a_row_with_a_delegated_span_is_still_checked_in_its_other_spans(self):
        d = self.copy_with("`ccp tasks index [--stdout]` | lead",
                           "`ccp otel serve [--port N]` / `ccp tasks index [--stdout] [--no-such-flag]` | lead")
        self.assertEqual(problems_of(d), ["02-delivery.md: `--no-such-flag` is no flag of `ccp tasks index`"])

    def test_a_command_the_parser_does_not_define_is_found(self):
        d = self.copy_with("`ccp tasks sync [--dry-run]` | lead", "`ccp tasks sync [--dry-run]` | lead\n| `ccp tasks no-such [--json]` | lead")
        self.assertEqual(problems_of(d), ["`ccp tasks no-such`: the parser has no such command"])

    def test_a_command_the_docs_leave_out_is_found(self):
        d = self.copy_with("`ccp where`", "`ccp were`")
        self.assertIn("docs/cli names no `ccp where`", problems_of(d))


if __name__ == "__main__":
    unittest.main()
