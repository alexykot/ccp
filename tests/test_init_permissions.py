"""SPEC §4.5, §18.5: `ccp init --permissions` prints the runner's and workers' permission block for the
operator to apply and writes nothing; the README's adoption checklist names real `plane.json` keys.
Scratch HOME, bindings, repos and queues."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.test_init import PLANE, InitCase

SCHEMA = PLANE / "contracts" / "plane_config.schema.json"


def tree(*roots: Path) -> dict[str, bytes]:
    """Every file under `roots` (git's own directory aside) with its bytes, and every directory."""
    out: dict[str, bytes] = {}
    for root in roots:
        for p in root.rglob("*") if root.exists() else []:
            if ".git" not in p.relative_to(root).parts:
                out[str(p)] = p.read_bytes() if p.is_file() else b"<dir>"
    return out


class Permissions(InitCase):
    def adopt(self, *args):
        code, res = self.init("--project-id", "demo", *args)
        self.assertEqual(code, 0, res)

    def permissions(self, *args):
        before = tree(self.repo, self.bindings, self.home)
        r = self.ccp("init", "--permissions", *args)
        self.assertEqual(tree(self.repo, self.bindings, self.home), before)
        return r

    def block(self) -> dict:
        r = self.permissions()
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(list(out), ["permissions"])
        self.assertEqual(set(out["permissions"]), {"allow", "deny"})
        return out["permissions"]

    def test_an_adopted_product_gets_the_allow_and_deny_lists_and_nothing_changes(self):
        self.adopt("--gate", "python3 -m unittest discover -s tests")
        block = self.block()
        allow = block["allow"]
        team, ask = PLANE / "scripts" / "team.sh", PLANE / "scripts" / "spec-maintainer-ask.sh"
        for cmd in ("ccp", str(team), str(ask)):
            self.assertIn(f"Bash({cmd}:*)", allow)
            self.assertIn(f"Bash(QUEUE_ROOT={self.queue} {cmd}:*)", allow)
        self.assertTrue(team.is_absolute() and team.is_file() and ask.is_file())
        for verb in ("status", "add", "commit", "push", "merge", "worktree"):
            self.assertIn(f"Bash(git {verb}:*)", allow)
        self.assertIn("Bash(gh pr:*)", allow)
        self.assertIn("Bash(python3 -m unittest discover -s tests:*)", allow)
        self.assertNotIn("Bash(git:*)", allow)
        for cmd in ("git push --force", "git reset --hard", "git clean"):
            self.assertIn(f"Bash({cmd}:*)", block["deny"])
        self.assertFalse(set(allow) & set(block["deny"]))

    def test_a_staged_gate_lane_allows_each_stage_command(self):
        self.adopt()
        cfg = self.repo / "docs/delivery/plane.json"
        data = json.loads(cfg.read_text())
        data["suite"] = {"lanes": {"gate": [{"name": "lint", "cmd": "scripts/lint.sh --all"},
                                            {"name": "tests", "cmd": "scripts/test.sh"}],
                                   "full": ["scripts/full.sh"]}}
        cfg.write_text(json.dumps(data))
        allow = self.block()["allow"]
        self.assertIn("Bash(scripts/lint.sh --all:*)", allow)
        self.assertIn("Bash(scripts/test.sh:*)", allow)
        self.assertNotIn("Bash(scripts/full.sh:*)", allow)

    def test_without_a_gate_lane_no_lane_command_is_allowed(self):
        self.adopt()
        self.assertEqual(self.block()["allow"][-1], "Bash(gh pr:*)")

    def test_a_queue_path_with_a_space_is_quoted_as_a_shell_would_run_it(self):
        self.adopt("--queue-root", str(self.home / "my queue"))
        self.assertIn(f"Bash(QUEUE_ROOT='{self.home / 'my queue'}' ccp:*)", self.block()["allow"])

    def test_before_adoption_it_is_refused(self):
        r = self.permissions()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertIn("`ccp init`", r.stderr)  # the step that fixes it

    def test_a_product_without_its_binding_is_refused(self):
        (self.repo / "docs/delivery").mkdir(parents=True)
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "demo"}))
        r = self.permissions()
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertEqual(r.stdout, "")
        self.assertIn("`ccp init`", r.stderr)  # the step that fixes it

    def test_a_writing_flag_is_refused(self):
        self.adopt()
        for args in (("--force",), ("--gate", "make test"), ("--starter-rules",), ("--project-id", "demo")):
            r = self.permissions(*args)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn(f"drop {args[0]}", r.stderr)
            self.assertEqual(r.stdout, "")


class AdoptionChecklist(unittest.TestCase):
    """The README's adoption checklist names keys the plane.json contract has."""

    KEYS = ("env", "telemetry.allowance_cmd", "telemetry.allowance_stop_weekly", "auth_check.probes",
            "parallel.exclusive", "merge.behind_tip_ignore", "reconcile.log", "notify", "docs.starter_rules",
            "architect.checks", "verify.accept_cache", "mutate.command", "report.required_fields")

    def keys(self) -> list[str]:
        text = (PLANE / "README.md").read_text()
        start = text.index("#### Adoption checklist")
        section = text[start:text.index("\n#", start + 1)]
        out = []
        for row in re.findall(r"^\| `.*$", section, re.M):
            cell = row.split("|")[1]
            head, _, sub = cell.partition("(")
            names = re.findall(r"`([^`]+)`", head)
            out += names + [f"{names[0]}.{s}" for s in re.findall(r"`([^`]+)`", sub)]
        return out

    def test_it_names_the_keys_a_product_may_need_and_each_is_in_the_contract(self):
        keys = self.keys()
        self.assertTrue(set(self.KEYS) <= set(keys), set(self.KEYS) - set(keys))
        schema = json.loads(SCHEMA.read_text())
        for key in keys:
            node = schema
            for part in key.split("."):
                self.assertIn(part, node.get("properties", {}), key)
                node = node["properties"][part]


if __name__ == "__main__":
    unittest.main()
