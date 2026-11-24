"""SPEC §4.5, §18.5: `ccp init --permissions` prints the runner's and workers' permission block for the
operator to apply and writes nothing; the README's adoption checklist names real `plane.json` keys.
Scratch HOME, bindings, repos and queues."""
from __future__ import annotations

import io
import json
import os
import re
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from ccp import cli, config, init
from tests.init_fixture import InitCase
from tests.helpers import file_tree as tree, PLANE_ROOT

SCHEMA = PLANE_ROOT / "contracts" / "plane_config.schema.json"


def denied(rule: str, cmd: str) -> bool:
    """Claude Code's Bash rule: `Bash(prefix:*)` matches the prefix as a whole word or more; any other
    rule matches the whole command, a `*` standing for any run of characters."""
    body = rule[len("Bash("):-1]
    if body.endswith(":*"):
        return cmd == body[:-2] or cmd.startswith(body[:-2] + " ")
    return re.fullmatch(".*".join(map(re.escape, body.split("*"))), cmd) is not None


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
        team, ask = PLANE_ROOT / "scripts" / "team.sh", PLANE_ROOT / "scripts" / "spec-maintainer-ask.sh"
        for cmd in ("ccp", str(team), str(ask)):
            self.assertIn(f"Bash({cmd}:*)", allow)
            self.assertIn(f"Bash(QUEUE_ROOT={self.queue} {cmd}:*)", allow)
        self.assertTrue(team.is_absolute() and team.is_file() and ask.is_file())
        for verb in ("status", "add", "commit", "push", "merge", "worktree"):
            self.assertIn(f"Bash(git {verb}:*)", allow)
        self.assertIn("Bash(python3 -m unittest discover -s tests:*)", allow)
        self.assertNotIn("Bash(git:*)", allow)
        for cmd in ("git push --force", "git reset --hard", "git clean"):
            self.assertIn(f"Bash({cmd}:*)", block["deny"])
        self.assertFalse(set(allow) & set(block["deny"]))

    def test_a_forced_push_is_denied_wherever_its_flag_is(self):
        self.adopt()
        deny = self.block()["deny"]
        for cmd in ("git push origin main --force", "git push --force origin main", "git push origin -f main",
                    "git push origin main --force-with-lease", "git push -f origin main", "git push origin main -f",
                    "git push origin --force-with-lease main", "git push --force-with-lease"):
            with self.subTest(cmd=cmd):
                self.assertTrue([r for r in deny if denied(r, cmd)], cmd)
        for cmd in ("git push origin main", "git push -u origin task/0001-a", "git push origin main --follow-tags",
                    "git push origin HEAD:main"):
            with self.subTest(cmd=cmd):
                self.assertEqual([r for r in deny if denied(r, cmd)], [], cmd)

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
        self.assertEqual(self.block()["allow"][-1], f"Bash(git {init.GIT_VERBS[-1]}:*)")

    def set_adapter(self, name: str) -> None:
        cfg = self.repo / "docs/delivery/plane.json"
        data = json.loads(cfg.read_text())
        data["pr_host"] = {"adapter": name}
        cfg.write_text(json.dumps(data))

    def test_no_adapter_allows_a_forge_cli(self):
        self.adopt()
        for name in config.PR_HOST_ADAPTERS:
            with self.subTest(adapter=name):
                self.set_adapter(name)
                allow = self.block()["allow"]
                self.assertFalse([e for e in allow if "gh " in e], allow)
                self.assertIn("Bash(ccp:*)", allow)

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
        for args in (("--force",), ("--gate", "make test"), ("--language", "python"), ("--starter-rules",),
                     ("--project-id", "demo")):
            r = self.permissions(*args)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn(f"drop {args[0]}", r.stderr)
            self.assertEqual(r.stdout, "")


class LocalAdapterOrigin(InitCase):
    """ADR-0040 D3, D5: under `pr_host.adapter: local`, init warns only when the product has no origin."""

    def adopt(self) -> tuple[dict, str]:
        self.machine_reads_usage()
        (self.repo / "docs/delivery").mkdir(parents=True)
        (self.repo / "docs/delivery/plane.json").write_text(json.dumps({"project_id": "demo",
                                                                         "pr_host": {"adapter": "local"}}))
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout), r.stderr

    def test_a_bare_origin_is_not_warned_about(self):
        bare = self.repo.parent / "bare.git"
        self.git("init", "-q", "--bare", str(bare))
        self.git("remote", "add", "origin", str(bare))
        res, err = self.adopt()
        self.assertNotIn("warnings", res)
        self.assertNotIn("origin", err)

    def test_no_origin_is_warned_about_naming_the_commands_that_need_one(self):
        res, err = self.adopt()
        self.assertEqual(len(res["warnings"]), 1, res)
        for text in (res["warnings"][0], err):
            self.assertIn("no origin", text)
            for command in ("ccp verify merge-ok", "ccp tasks close"):
                self.assertIn(command, text)
            self.assertNotIn("gh pr", text)


class AppliedBlockDocsCheck(InitCase):
    """§4.3, §4.4: the block `ccp init --permissions` prints, applied to `.claude/settings.json`, draws no
    docs-check warning; any other plane path in the file still does. The fence's own plane path does not
    match the docs check's pattern, so the block is printed for a scratch plane path that does."""

    def setUp(self):
        super().setUp()
        self.plane = self.home.parent / "src" / "control-plane"
        code, res = self.init("--project-id", "demo")
        self.assertEqual(code, 0, res)

    def run_ccp(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch("ccp.init.PLANE", self.plane), mock.patch.dict(os.environ, self.env, clear=True), \
                redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = cli.main(["--root", str(self.repo), *args])
        return code, out.getvalue()

    def apply(self, **extra) -> list[str]:
        """Apply the printed block (and `extra` keys) to the product's settings, commit, and return the block's
        entries that name the plane by a path the docs check matches."""
        code, out = self.run_ccp("init", "--permissions")
        self.assertEqual(code, 0, out)
        block = json.loads(out)
        settings_file = self.repo / ".claude/settings.json"
        settings = json.loads(settings_file.read_text())
        settings.update(block, **extra)
        settings_file.write_text(json.dumps(settings, indent=2))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "permissions")
        return [e for e in block["permissions"]["allow"] if re.search(cli.PLANE_PATH_RE, e)]

    def settings_warnings(self) -> list[str]:
        _, out = self.run_ccp("docs", "check")
        return [line for line in out.splitlines() if "warning:" in line and ".claude/settings.json" in line]

    def test_the_applied_block_draws_no_warning(self):
        named = self.apply()
        self.assertEqual(len(named), 4, named)  # team.sh and spec-maintainer-ask.sh, each bare and behind QUEUE_ROOT=
        self.assertEqual(self.settings_warnings(), [])

    def test_another_plane_path_in_the_settings_is_still_warned_about(self):
        hook = str(self.plane / "plugin" / "hooks" / "runner-idle.sh")
        self.apply(hooks={"Stop": [{"hooks": [{"type": "command", "command": hook}]}]})
        warned = self.settings_warnings()
        self.assertEqual(len(warned), 1, warned)
        self.assertIn("SPEC §4.4", warned[0])

    def test_a_permission_entry_naming_another_plane_path_beside_a_seat_script_is_warned_about(self):
        team, other = self.plane / "scripts" / "team.sh", self.plane / "scripts" / "other.sh"
        self.apply()
        settings_file = self.repo / ".claude/settings.json"
        settings = json.loads(settings_file.read_text())
        settings["permissions"]["allow"].append(f"Bash({team} && {other}:*)")
        settings_file.write_text(json.dumps(settings))
        self.assertEqual(len(self.settings_warnings()), 1)

    def test_a_seat_script_entry_under_deny_draws_no_warning(self):
        named = self.apply()
        settings_file = self.repo / ".claude/settings.json"
        settings = json.loads(settings_file.read_text())
        settings["permissions"]["allow"] = [e for e in settings["permissions"]["allow"] if e not in named]
        settings["permissions"]["deny"] += named
        settings_file.write_text(json.dumps(settings))
        self.assertEqual(self.settings_warnings(), [])

    def test_an_entry_naming_a_file_that_only_starts_with_a_seat_script_name_is_warned_about(self):
        self.apply()
        settings_file = self.repo / ".claude/settings.json"
        before = settings_file.read_text()
        for name in ("team.sh.bak", "team.sh-x"):
            with self.subTest(name=name):
                settings = json.loads(before)
                settings["permissions"]["allow"].append(f"Bash({self.plane / 'scripts' / name}:*)")
                settings_file.write_text(json.dumps(settings))
                self.assertEqual(len(self.settings_warnings()), 1)

    def test_a_settings_file_that_is_not_json_is_warned_about_as_before(self):
        self.apply()
        settings_file = self.repo / ".claude/settings.json"
        settings_file.write_text(settings_file.read_text() + "\n,")
        self.assertEqual(len(self.settings_warnings()), 1)


class AdoptionChecklist(unittest.TestCase):
    """The README's adoption checklist names keys the plane.json contract has."""

    KEYS = ("language", "env", "auth_check.probes", "parallel.exclusive", "merge.behind_tip_ignore", "reconcile.log",
            "notify", "docs.starter_rules", "architect.checks", "verify.accept_cache", "mutate.command", "report.required_fields")

    def keys(self) -> list[str]:
        text = (PLANE_ROOT / "README.md").read_text()
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
        self.assertEqual(keys[0], "language")  # the required key comes first
        schema = json.loads(SCHEMA.read_text())
        for key in keys:
            node = schema
            for part in key.split("."):
                self.assertIn(part, node.get("properties", {}), key)
                node = node["properties"][part]


if __name__ == "__main__":
    unittest.main()
