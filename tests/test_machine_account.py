"""SPEC §8.3, §25: the account is the machine's. The allowance command and the weekly stop live in the machine
file beside the bindings, one for every product on the machine; the weekly stop is 90% unless set; the session
park, wake and ceiling numbers and the usage windows are constants; and with no allowance command the plane says
that no usage is read and nothing bounds spend."""
from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from ccp import board, config, notify, parallel, usage
from ccp.queue import lib
from tests.helpers import GIT_ENV, PLANE_ROOT, Product
from tests.board_drill_fixture import HASH_STUB, Fixture
from tests.upgrade_fixture import UpgradeFixture

HOOK = PLANE_ROOT / "plugin" / "hooks" / "orientation.sh"
CCP = PLANE_ROOT / "bin" / "ccp"
MACHINE_SCHEMA = json.loads((PLANE_ROOT / "contracts/machine.schema.json").read_text())


class MachineCase(unittest.TestCase):
    """A fenced machine file: `CCP_BINDINGS_DIR` is a temp directory this test writes `machine.json` into."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.bindings = Path(self._dir.name)
        patch = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": str(self.bindings)})
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self._dir.cleanup)
        self.products: list[Product] = []

    def machine(self, **keys) -> None:
        (self.bindings / "machine.json").write_text(json.dumps(keys))

    def product(self, plane: dict | None = None) -> Product:
        p = Product(plane, bare=True)
        self.products.append(p)
        self.addCleanup(p.cleanup)
        return p

    def load(self, plane: dict | None = None) -> tuple[config.Config, str]:
        """The product's config, and what loading it wrote to stderr."""
        p = self.product(plane)
        err = io.StringIO()
        with redirect_stderr(err):
            config._WARNED.clear()
            return config.load(p.root), err.getvalue()


class TheMachinesAccount(MachineCase):
    def test_nothing_set_reads_no_usage_and_stops_the_week_at_90(self):
        cfg, err = self.load()
        a = usage.account(cfg)
        self.assertIsNone(a["allowance_cmd"])
        self.assertEqual(a["stop_weekly"], 90)
        self.assertEqual(usage.window_rules(cfg)["seven_day"]["stop_pct"], 90)
        self.assertFalse(usage.usage_read(cfg))
        self.assertEqual(err, "")

    def test_the_machines_command_and_stop_serve_every_product(self):
        self.machine(allowance_cmd="cat /dev/null", allowance_stop_weekly=75)
        for _ in range(2):
            cfg, err = self.load()
            a = usage.account(cfg)
            self.assertEqual((a["allowance_cmd"], a["stop_weekly"]), ("cat /dev/null", 75))
            self.assertEqual(usage.window_rules(cfg)["seven_day"]["stop_pct"], 75)
            self.assertTrue(usage.usage_read(cfg))
            self.assertTrue(parallel.reads_usage(cfg))
            self.assertEqual(err, "")

    def test_the_checkpoint_in_force_is_the_machines_stop_without_a_decision(self):
        cfg, _ = self.load()
        with tempfile.TemporaryDirectory() as q:
            self.assertEqual(usage.checkpoint(cfg, Path(q), None), 90)
            self.machine(allowance_stop_weekly=60)
            self.assertEqual(usage.checkpoint(cfg, Path(q), None), 60)

    def test_a_bad_machine_value_is_ignored_with_a_warning_naming_the_file(self):
        self.machine(allowance_cmd="  ", allowance_stop_weekly=140)
        err = io.StringIO()
        with redirect_stderr(err):
            config._WARNED.clear()
            got = config.machine_account()
        self.assertEqual(got, {})
        self.assertIn("allowance_cmd must be a command", err.getvalue())
        self.assertIn("allowance_stop_weekly must be a percentage", err.getvalue())
        self.assertIn(str(lib.machine_path()), err.getvalue())

    def test_the_schema_default_is_the_codes(self):
        props = MACHINE_SCHEMA["properties"]
        self.assertEqual(props["allowance_stop_weekly"]["default"], config.ALLOWANCE_STOP_WEEKLY_DEFAULT)
        self.assertEqual(set(props) - {"telemetry"}, set(config.MACHINE_ACCOUNT_KEYS))


class TheOldPlace(MachineCase):
    OLD = {"telemetry": {"allowance_cmd": "echo old", "allowance_stop_weekly": 80}}

    def test_a_product_value_is_honoured_while_the_machine_file_lacks_it_with_a_warning_naming_the_move(self):
        cfg, err = self.load(self.OLD)
        a = usage.account(cfg)
        self.assertEqual((a["allowance_cmd"], a["stop_weekly"]), ("echo old", 80))
        for key in ("telemetry.allowance_cmd", "telemetry.allowance_stop_weekly"):
            self.assertEqual(sum(f"{key} has moved to" in x for x in err.splitlines()), 1, err)
        self.assertIn("allowance_cmd in the machine file", err)

    def test_the_machines_value_wins_and_the_warning_says_the_products_is_ignored(self):
        self.machine(allowance_cmd="echo machine", allowance_stop_weekly=70)
        cfg, err = self.load(self.OLD)
        a = usage.account(cfg)
        self.assertEqual((a["allowance_cmd"], a["stop_weekly"]), ("echo machine", 70))
        for key in ("telemetry.allowance_cmd", "telemetry.allowance_stop_weekly"):
            self.assertEqual(sum(f"{key} is ignored" in x for x in err.splitlines()), 1, err)

    def test_one_key_in_the_machine_file_leaves_the_other_to_the_product(self):
        self.machine(allowance_stop_weekly=70)
        cfg, err = self.load(self.OLD)
        a = usage.account(cfg)
        self.assertEqual((a["allowance_cmd"], a["stop_weekly"]), ("echo old", 70))
        self.assertIn("telemetry.allowance_cmd has moved to", err)
        self.assertIn("telemetry.allowance_stop_weekly is ignored", err)

    def test_an_empty_product_value_is_no_value_and_warns_of_nothing(self):
        cfg, err = self.load({"telemetry": {"allowance_cmd": None, "allowance_stop_weekly": None}})
        self.assertEqual((usage.account(cfg)["allowance_cmd"], usage.account(cfg)["stop_weekly"]), (None, 90))
        self.assertNotIn("moved", err)
        self.assertIn("is empty and ignored", err)

    def test_the_old_value_is_still_checked(self):
        p = self.product({"telemetry": {"allowance_stop_weekly": 140}})
        with redirect_stderr(io.StringIO()), self.assertRaises(config.ConfigError) as cm:
            config.load(p.root)
        self.assertIn("telemetry.allowance_stop_weekly", str(cm.exception))


class TheConstants(MachineCase):
    CASES = (("telemetry", "session_park_pct", 90, 95), ("telemetry", "session_wake_arm_pct", 40, 50),
             ("telemetry", "session_wake_margin_s", 60, 180), ("parallel", "session_ceiling_pct", 50, 60),
             ("telemetry", "windows", {"hour": {"kind": "session", "park_pct": 80}}, None))

    def test_each_is_a_constant_in_the_registry_at_todays_value(self):
        for block, key, _, default in self.CASES:
            with self.subTest(key=key):
                o = config.KEY_OUTCOMES[f"{block}.{key}"]
                self.assertEqual((o.kind, o.value), (config.CONSTANT, default))
                self.assertEqual(config.constant_override(f"{block}.{key}"), default)

    def test_unset_each_is_the_constant_and_says_nothing(self):
        cfg, err = self.load()
        a = usage.account(cfg)
        self.assertEqual((a["park_pct"], a["wake_arm_pct"], a["wake_margin_s"], a["ceiling_pct"]), (95, 50, 180, 60))
        self.assertEqual(set(a["windows"]), {"seven_day", "five_hour"})
        self.assertEqual(err, "")

    def test_a_value_other_than_the_constant_applies_with_one_warning_naming_the_constant(self):
        for block, key, value, default in self.CASES:
            with self.subTest(key=key):
                cfg, err = self.load({block: {key: value}})
                self.assertEqual(getattr(cfg, block)[key], value)
                lines = [x for x in err.splitlines() if f"{block}.{key} " in x]
                self.assertEqual(len(lines), 1, err)
                self.assertIn(f"a constant in code ({default!r})", lines[0])

    def test_a_product_park_of_90_parks_at_90_with_the_warning_naming_95(self):
        cfg, err = self.load({"telemetry": {"session_park_pct": 90}})
        self.assertEqual(usage.account(cfg)["park_pct"], 90.0)
        self.assertEqual(usage.window_rules(cfg)["five_hour"]["park_pct"], 90.0)
        self.assertIn("a constant in code (95)", err)

    def test_the_constants_own_value_says_the_key_can_be_deleted(self):
        cfg, err = self.load({"telemetry": {"session_park_pct": 95}, "parallel": {"session_ceiling_pct": 60}})
        self.assertEqual((usage.account(cfg)["park_pct"], usage.account(cfg)["ceiling_pct"]), (95, 60))
        self.assertEqual(err.count("delete it"), 2, err)

    def test_the_upgrade_listing_names_each_constant_set_to_another_value(self):
        found = config.key_outcomes_set({"telemetry": {"session_park_pct": 90, "session_wake_arm_pct": 50},
                                         "parallel": {"session_ceiling_pct": 70}})
        self.assertEqual({f["key"]: (f["constant"], f["set"]) for f in found},
                         {"telemetry.session_park_pct": (95, 90), "parallel.session_ceiling_pct": (60, 70)})


class UnreadUsage(MachineCase):
    def test_the_warning_names_the_key_and_the_machine_file(self):
        text = usage.unread_warning()
        self.assertIn("allowance_cmd", text)
        self.assertIn(str(lib.machine_path()), text)

    def test_status_carries_it_only_without_a_command(self):
        cfg, _ = self.load()
        with tempfile.TemporaryDirectory() as q:
            st = usage.status(cfg, Path(q), sample=False)
            self.assertIs(st["usage_read"], False)
            self.assertEqual(st["warning"], usage.unread_warning())
            self.machine(allowance_cmd="cat /dev/null")
            st = usage.status(cfg, Path(q), sample=False)
            self.assertIs(st["usage_read"], True)
            self.assertNotIn("warning", st)


class TheBoard(Fixture, MachineCase):
    def setUp(self):
        MachineCase.setUp(self)
        Fixture.setUp(self)

    def tearDown(self):
        Fixture.tearDown(self)

    def test_the_json_says_usage_is_not_read_and_the_status_line_says_unread(self):
        self.seed()
        b = self.build()[0]
        self.assertIs(b["usage"]["usage_read"], False)
        self.assertIn("usage unread", board.status_text(b).splitlines())

    def test_with_a_command_the_json_says_it_is_read_and_the_status_says_nothing(self):
        self.machine(allowance_cmd="cat /dev/null")
        self.seed()
        b = self.build()[0]
        self.assertIs(b["usage"]["usage_read"], True)
        self.assertNotIn("usage unread", board.status_text(b))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_page_shows_usage_unread_in_the_weekly_tile_only_when_it_is(self):
        self.seed()
        b = self.build()[0]
        for read, shown in ((False, True), (True, False)):
            b["usage"]["usage_read"] = read
            js = board.PAGE.read_text().replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1] \
                .split("</script>", 1)[0]
            loc = "globalThis.location = {hash: '', pathname: '/b', search: ''};\n"
            r = subprocess.run(["node", "-e", HASH_STUB + loc + js + "\nprocess.stdout.write(out.join(''));"],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual("usage unread" in r.stdout, shown)


class InitWarns(MachineCase):
    def init(self) -> dict:
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        repo = t / "repo"
        repo.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        env.update(GIT_ENV, HOME=str(t / "home"))
        (t / "home").mkdir()
        subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True, env=env)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/team/repo.git"], cwd=repo, check=True,
                       env=env)
        r = subprocess.run([str(CCP), "init", "--project-id", "demo", "--language", "none"], cwd=repo,
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {**json.loads(r.stdout), "stderr": r.stderr}

    def test_without_a_command_init_warns_in_its_result_and_on_stderr_naming_the_key(self):
        out = self.init()
        mine = [w for w in out["warnings"] if "allowance_cmd" in w]
        self.assertEqual(len(mine), 1, out["warnings"])
        self.assertIn(str(lib.machine_path()), mine[0])
        self.assertIn(mine[0], out["stderr"])

    def test_with_a_command_it_says_nothing_about_usage(self):
        self.machine(allowance_cmd="cat /dev/null")
        out = self.init()
        self.assertNotIn("warnings", out)
        self.assertNotIn("allowance_cmd", out["stderr"])


class SessionStartCheck(MachineCase):
    """The orientation hook appends the warning `ccp orientation --tail` gives from the allowance status."""

    def hook(self, status: dict | None) -> str:
        t = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, t, True)
        (t / "plugin").mkdir()
        (t / "plugin" / "orientation.md").write_text("# Orientation\nmarker-1c9e\n")
        (t / "bin").mkdir()
        fake = t / "bin" / "ccp"
        fake.write_text("#!/bin/sh\ncat \"$STATUS_FILE\"\n" if status is not None else "#!/bin/sh\nexit 1\n")  # `orientation --tail`
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        (t / "status.json").write_text(notify.orientation_tail([], (status or {}).get("warning") or ""))
        p = self.product()
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
        env.update(CLAUDE_PROJECT_DIR=str(p.root), CLAUDE_PLUGIN_ROOT=str(t / "plugin"), STATUS_FILE=str(t / "status.json"))
        r = subprocess.run(["bash", str(HOOK)], capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_the_warning_ccp_gives_is_added_to_the_orientation(self):
        text = self.hook({"usage_read": False, "warning": "no usage is read: marker-warn-77"})
        self.assertIn("marker-1c9e", text)
        self.assertEqual(text.count("marker-warn-77"), 1)

    def test_with_usage_read_the_orientation_carries_no_warning(self):
        text = self.hook({"usage_read": True})
        self.assertIn("marker-1c9e", text)
        self.assertNotIn("## Warning", text)

    def test_a_ccp_that_cannot_answer_drops_the_warning_never_the_orientation(self):
        text = self.hook(None)
        self.assertIn("marker-1c9e", text)
        self.assertNotIn("## Warning", text)


class UpgradeStatus(UpgradeFixture, unittest.TestCase):
    """`ccp upgrade status` lists the move to the machine file, and checks the step against that file."""
    STEP = "machine.json allowance_cmd (move the command into the machine file)"

    def status(self) -> dict:
        code, body, err = self.ccp("upgrade", "status")
        self.assertEqual(code, 0, err)
        return body

    def test_the_old_keys_are_listed_as_moving_to_the_machine_file_and_the_constants_as_deletable(self):
        self.product_json(language="none", telemetry={"allowance_cmd": "x", "allowance_stop_weekly": 80,
                                                       "session_park_pct": 90, "session_wake_arm_pct": 50})
        step = next(s for s in self.status()["steps"] if s["task"] == "plane.json keys")
        listed = {k["key"]: k for k in step["keys"]}
        self.assertEqual(set(listed), {"telemetry.allowance_cmd", "telemetry.allowance_stop_weekly",
                                       "telemetry.session_park_pct"})
        self.assertEqual(listed["telemetry.allowance_cmd"]["replacement"], "machine.json allowance_cmd")
        self.assertEqual(listed["telemetry.allowance_stop_weekly"]["outcome"], "merged")
        self.assertEqual((listed["telemetry.session_park_pct"]["constant"], listed["telemetry.session_park_pct"]["set"]),
                         (95, 90))
        self.assertIn("move `telemetry.allowance_cmd` to `machine.json allowance_cmd`", step["change"])

    def test_the_step_is_taken_once_the_machine_file_holds_the_command(self):
        self.plane_task("0001-account", "done", "Account", self.STEP)
        self.commit("plane")
        self.product_json(language="none")
        steps = self.status()["steps"]
        self.assertEqual([s["task"] for s in steps], ["0001-account"])
        self.assertEqual(steps[0]["check"], "not taken")
        (self.bindings / "machine.json").write_text(json.dumps({"allowance_cmd": "x"}))
        body = self.status()
        self.assertEqual(([s["task"] for s in body["steps"]], [s["task"] for s in body["detected"]]),
                         ([], ["0001-account"]))


if __name__ == "__main__":
    unittest.main()
