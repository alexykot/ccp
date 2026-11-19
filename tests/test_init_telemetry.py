"""SPEC §4.5, §24.1, §8.3: `ccp init` tags the product's telemetry and, with the operator's consent recorded once
per machine, writes the user-level keys and installs the receiver and the board timer; `ccp otel env --off` prints
the project-level opt-out; the receiver's port is no longer a plane.json setting. Scratch bindings directory, home and
user settings; the launchd installs and the receiver check are stubbed (no launchd, no real home, no live receiver)."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import config, init, otel, sandbox
from tests.helpers import Product
from tests.test_init import InitCase

NOTICE = "every Claude Code session on this machine"
ROOT = Path(__file__).resolve().parents[1]


def args(**kw):
    base = dict(project_id="demo", queue_root=None, integration_branch=None, gate=None, force=False,
                starter_rules=False, telemetry=None, adopt=False, rules_doc=None, permissions=False)
    return argparse.Namespace(**{**base, **kw})


class Machine(InitCase):
    """Init run in this process, so the install steps and the receiver check can be stubbed."""

    def setUp(self):
        super().setUp()
        self.user = self.home / "user-settings.json"
        self.machine = self.bindings / "machine.json"
        self.err = io.StringIO()
        env = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings), "CCP_USER_SETTINGS": str(self.user),
                                           "HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        self.macos = self.patch(init, "_macos", return_value=True)
        self.otel_install = self.patch(otel, "launchd", return_value={"ok": True, "plist": "o.plist"})
        self.board_install = self.patch(init, "board_launchd", return_value={"ok": True, "plist": "b.plist"})
        self.up = self.patch(otel, "receiver_up", return_value=True)

    def patch(self, target, name, **kw):
        p = mock.patch.object(target, name, **kw)
        m = p.start()
        self.addCleanup(p.stop)
        return m

    def run_init(self, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(self.err):
            code = init.main(str(self.repo), args(queue_root=str(self.queue), **kw))
        self.assertEqual(code, 0, self.err.getvalue())
        return json.loads(out.getvalue())

    def clear_err(self):
        self.err.truncate(0)
        self.err.seek(0)

    def user_env(self):
        return json.loads(self.user.read_text())["env"]

    def assert_nothing_outside_the_product(self):
        self.assertFalse(self.user.exists())
        self.otel_install.assert_not_called()
        self.board_install.assert_not_called()


class Consent(Machine):
    def test_no_consent_and_no_flag_prints_the_notice_and_writes_nothing_outside_the_product(self):
        res = self.run_init()
        err = self.err.getvalue()
        self.assertIn(NOTICE, err)
        self.assertIn("--telemetry on", err)
        self.assertIn("ccp otel env --off", err)
        self.assert_nothing_outside_the_product()
        self.assertFalse(self.machine.exists())
        self.assertIsNone(res["telemetry"]["consent"])
        self.up.assert_not_called()

    def test_on_adds_the_user_keys_without_overwriting_and_installs_after_the_notice(self):
        self.user.write_text(json.dumps({"theme": "dark", "env": {"OTEL_LOGS_EXPORTER": "console", "X": "1"}}))
        seen = []
        self.otel_install.side_effect = lambda *a, **k: (seen.append(self.err.getvalue()), {"ok": True})[1]
        res = self.run_init(telemetry="on")
        env = self.user_env()
        self.assertEqual(env["OTEL_LOGS_EXPORTER"], "console")  # a differing value is kept
        self.assertEqual(env["X"], "1")
        for k, v in otel.env_block(otel.receiver_port()).items():
            if k != "OTEL_LOGS_EXPORTER":
                self.assertEqual(env[k], v)
        self.assertEqual(json.loads(self.user.read_text())["theme"], "dark")
        for k in otel.CONTENT_KEYS:
            self.assertNotIn(k, env)
        self.otel_install.assert_called_once_with("install", otel.receiver_port())
        self.board_install.assert_called_once()
        self.assertEqual(json.loads(self.machine.read_text()), {"telemetry": "on"})
        self.assertEqual(len(seen), 1)  # the notice naming the opt-out was printed before the install
        self.assertIn(NOTICE, seen[0])
        self.assertIn("ccp otel env --off", seen[0])
        self.assertEqual(res["telemetry"]["user_settings"]["differing"], ["OTEL_LOGS_EXPORTER"])
        self.assertIn("OTEL_LOGS_EXPORTER", self.err.getvalue())

    def test_a_later_init_with_no_flag_checks_the_setup_again_without_the_notice(self):
        self.run_init(telemetry="on")
        env = self.user_env()
        del env["OTEL_TRACES_EXPORTER"]
        self.user.write_text(json.dumps({"env": env}))
        self.clear_err()
        self.otel_install.reset_mock()
        self.board_install.reset_mock()
        res = self.run_init()
        self.assertEqual(self.user_env()["OTEL_TRACES_EXPORTER"], "otlp")
        self.otel_install.assert_called_once()
        self.board_install.assert_called_once()
        self.assertEqual(res["telemetry"]["consent"], "on")
        self.assertNotIn(NOTICE, self.err.getvalue())

    def test_off_is_recorded_writes_nothing_outside_the_product_and_is_not_asked_again(self):
        res = self.run_init(telemetry="off")
        self.assertEqual(json.loads(self.machine.read_text()), {"telemetry": "off"})
        self.assert_nothing_outside_the_product()
        self.assertEqual(res["telemetry"]["consent"], "off")
        self.run_init()
        self.assert_nothing_outside_the_product()
        self.assertNotIn("telemetry", self.err.getvalue())

    def test_a_receiver_that_stays_down_gets_the_normal_terminal_command(self):
        self.up.return_value = False
        res = self.run_init(telemetry="on")
        self.assertIn("ccp otel install", self.err.getvalue())
        self.assertIn("normal terminal", self.err.getvalue())
        self.assertFalse(res["telemetry"]["receiver_up"])

    def test_a_live_receiver_prints_no_command(self):
        self.run_init(telemetry="on")
        self.assertNotIn("normal terminal", self.err.getvalue())

    def test_a_flag_replaces_the_recorded_consent(self):
        self.run_init(telemetry="on")
        self.run_init(telemetry="off")
        self.assertEqual(json.loads(self.machine.read_text()), {"telemetry": "off"})
        self.run_init(telemetry="on")
        self.assertEqual(json.loads(self.machine.read_text()), {"telemetry": "on"})

    def test_elsewhere_than_macos_the_commands_are_printed_and_nothing_is_installed(self):
        self.macos.return_value = False
        res = self.run_init(telemetry="on")
        self.otel_install.assert_not_called()
        self.board_install.assert_not_called()
        self.assertIn("ccp otel serve", self.err.getvalue())
        self.assertIn("board build --quiet", self.err.getvalue())
        self.assertIn("only macOS", res["telemetry"]["services"])
        self.assertIn("OTEL_LOGS_EXPORTER", self.user_env())

    def test_a_user_settings_file_that_is_not_an_object_is_reported_and_left_alone(self):
        self.user.write_text("[1]")
        res = self.run_init(telemetry="on")
        self.assertEqual(self.user.read_text(), "[1]")
        self.assertIn("not a JSON object", res["telemetry"]["error"])
        self.otel_install.assert_not_called()

    def test_the_machine_file_keeps_its_other_keys(self):
        self.bindings.mkdir()
        self.machine.write_text(json.dumps({"other": 1}))
        self.run_init(telemetry="on")
        self.assertEqual(json.loads(self.machine.read_text()), {"other": 1, "telemetry": "on"})


class Sandboxed(Machine):
    def setUp(self):
        super().setUp()
        self.d = Path(os.environ["CCP_SANDBOX_ROOT"]) / "telemetry-sandbox"
        self.made = sandbox.create(str(self.d), [])
        self.addCleanup(sandbox.remove, str(self.d))

    def test_init_in_a_sandbox_refuses_on_before_writing_anything(self):
        root = Path(self.made["root"])

        def files():
            return {p: p.stat().st_mtime_ns for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        before = files()
        err = io.StringIO()
        with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.d / "bindings")}), \
                contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = init.main(str(root), args(telemetry="on", project_id=None))
        self.assertEqual(code, 2)
        self.assertIn("sandbox", err.getvalue())
        self.assertEqual(before, files())
        self.assert_nothing_outside_the_product()

    def test_sandbox_create_records_off_in_its_own_machine_file_and_refuses_the_flag(self):
        self.assertEqual(json.loads((self.d / "bindings" / "machine.json").read_text()), {"telemetry": "off"})
        self.assertFalse(self.machine.exists())
        with self.assertRaises(sandbox.SandboxError):
            sandbox.create(str(self.d.with_name("telemetry-sandbox-2")), ["--telemetry", "on"])
        self.assert_nothing_outside_the_product()


class Tag(InitCase):
    def fresh_repo(self):
        """An empty repository and no bindings, so each case starts from a product `init` has never touched."""
        for d in (self.repo, self.bindings):
            shutil.rmtree(d, ignore_errors=True)
        self.repo.mkdir()
        self.git("init", "-q", ".")

    def settings(self):
        return json.loads((self.repo / ".claude" / "settings.json").read_text())

    def test_the_tag_is_written_beside_the_agent_teams_key_whatever_the_consent(self):
        for flag in ((), ("--telemetry", "off")):
            with self.subTest(flag=flag):
                self.fresh_repo()
                code, res = self.init("--project-id", "demo", *flag)
                self.assertEqual(code, 0, res)
                self.assertEqual(self.settings()["env"], {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
                                                          "OTEL_RESOURCE_ATTRIBUTES": "ccp.project_id=demo"})
                self.assertEqual(res["telemetry"]["tag"], "added")

    def test_a_tag_the_product_set_is_never_overwritten(self):
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text(json.dumps({"env": {"OTEL_RESOURCE_ATTRIBUTES": "a=b"}}))
        for flags in ((), ("--force",)):
            code, res = self.init("--project-id", "demo", *flags)
            self.assertEqual(code, 0, res)
            self.assertEqual(self.settings()["env"]["OTEL_RESOURCE_ATTRIBUTES"], "a=b")
            self.assertEqual(res["telemetry"]["tag"], "kept")

    def test_init_without_the_flag_prints_the_notice_on_stderr_and_writes_nothing_outside_the_product(self):
        r = self.ccp("init", "--project-id", "demo")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(NOTICE, r.stderr)
        self.assertIsNone(json.loads(r.stdout)["telemetry"]["consent"])
        self.assertFalse((self.bindings / "machine.json").exists())

    def test_the_flag_takes_on_or_off_only_and_permissions_refuses_it(self):
        self.assertEqual(self.ccp("init", "--telemetry", "maybe").returncode, 2)
        self.assertEqual(self.init("--project-id", "demo")[0], 0)
        r = self.ccp("init", "--permissions", "--telemetry", "off")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--telemetry", r.stderr)


class OptOut(unittest.TestCase):
    def run_otel(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = otel.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_env_off_prints_the_project_block_and_where_it_goes(self):
        code, out, _ = self.run_otel("env", "--off")
        body = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(body["project"]["env"], {"CLAUDE_CODE_ENABLE_TELEMETRY": "0", "OTEL_LOGS_EXPORTER": "none",
                                                  "OTEL_TRACES_EXPORTER": "none"})
        self.assertEqual(body["project"]["path"], "<product>/.claude/settings.json")

    def test_the_off_block_turns_off_exactly_what_the_user_block_turns_on(self):
        on, off = otel.env_block(4318), otel.off_block()
        self.assertEqual({k for k, v in on.items() if v == "otlp"} | {"CLAUDE_CODE_ENABLE_TELEMETRY"}, set(off))
        for k in otel.CONTENT_KEYS:
            self.assertNotIn(k, off)

    def test_env_off_names_a_bound_products_settings_path(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "demo.yaml").write_text("project_id: demo\nproduct_root: /srv/demo\n")
            with mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": d}):
                code, out, _ = self.run_otel("env", "--off", "--project", "demo")
                self.assertEqual((code, json.loads(out)["project"]["path"]), (0, "/srv/demo/.claude/settings.json"))
                self.assertEqual(self.run_otel("env", "--off", "--project", "nope")[0], 2)


class Port(unittest.TestCase):
    def test_a_non_numeric_port_in_the_environment_falls_back_to_the_default(self):
        for bad in ("abc", "43.18", " "):
            with self.subTest(value=bad), mock.patch.dict(os.environ, {"CCP_OTEL_PORT": bad}):
                self.assertEqual(otel.receiver_port(), otel.DEFAULT_PORT)
        with mock.patch.dict(os.environ, {"CCP_OTEL_PORT": "4999"}):
            self.assertEqual(otel.receiver_port(), 4999)

    def test_plane_json_that_still_sets_otel_port_loads_with_the_unknown_key_warning(self):
        p = Product({"telemetry": {"otel_port": 4318}})
        self.addCleanup(p.cleanup)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            cfg = config.load(p.root)
        self.assertEqual(cfg.unknown_keys, ("telemetry.otel_port",))
        self.assertIn("telemetry.otel_port", err.getvalue())
        self.assertNotIn("otel_port", cfg.telemetry)

    def test_the_schema_no_longer_lists_it(self):
        schema = json.loads((ROOT / "contracts/plane_config.schema.json").read_text())
        self.assertNotIn("otel_port", schema["properties"]["telemetry"]["properties"])


class MachineFile(unittest.TestCase):
    def test_the_contract_lists_the_one_key(self):
        schema = json.loads((ROOT / "contracts/machine.schema.json").read_text())
        self.assertEqual(list(schema["properties"]), ["telemetry"])
        self.assertEqual(schema["properties"]["telemetry"]["enum"], ["on", "off"])
        self.assertFalse(schema["additionalProperties"])

    def test_the_file_sits_beside_the_bindings_and_is_not_one(self):
        from ccp.queue import lib  # noqa: PLC0415
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": d}):
            self.assertEqual(lib.machine_path(), Path(d) / "machine.json")
            self.assertEqual(lib.read_machine(), {})
            lib.machine_path().write_text("[]")
            self.assertEqual(lib.read_machine(), {})
            lib.machine_path().write_text('{"telemetry": "on"}')
            self.assertEqual(lib.read_machine(), {"telemetry": "on"})


if __name__ == "__main__":
    unittest.main()
