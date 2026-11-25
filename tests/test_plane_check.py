"""SPEC §31.3: `ccp plane check` names every queue entry the plane does not write (the scripts that are
not the plane's copy, and the top-level entries it does not keep), `--archive` moves them all to
QUEUE_ROOT/_legacy/<UTC date>/ without deleting or overwriting anything, and `ccp init` on such a queue
warns and moves nothing. Every product is a sandbox below the test fence's root (tests/__init__.py)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ccp import queue
from tests.helpers import PLANE_ROOT

CCP = PLANE_ROOT / "bin" / "ccp"


# Every top-level name the plane writes or still reads in a queue, as a file or a directory.
OWNED = ("_legacy", "architect.json", "architect.json.lock", "architect.lock", "auth", "board", "docs-audit.json",
         "docs-audit.lock", "durable", "escalations", "estimates", "estimator", "estimator.lock", "health", "locks",
         "observability", "plane", "progress", "project.yaml", "prompts", "questions",
         "review", "reviews", "runs", "tasks", "verification", "work.json", "work.json.lock",
         "worktrees")


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.fence = Path(os.environ["CCP_SANDBOX_ROOT"]).resolve()
        self.base = Path(tempfile.mkdtemp(dir=self.fence)).resolve()
        self.env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML", "PLANE_PROJECT_YAML")}
        self.env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        r = subprocess.run([str(CCP), "sandbox", "create", str(self.base / "S")], capture_output=True, text=True,
                           env=self.env, cwd=self.base)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.sb = json.loads(r.stdout)
        self.root, self.q = Path(self.sb["root"]), Path(self.sb["queue_root"])
        self.env.update(dict(line.split("=", 1) for line in self.sb["env"]))

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)

    def ccp(self, *args, **env):
        r = subprocess.run([str(CCP), *args], cwd=self.root, capture_output=True, text=True, env={**self.env, **env})
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {}), r.stderr

    def put(self, rel: str, text: str) -> Path:
        p = self.q / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def leftovers(self) -> dict[str, str]:
        """The four entries of an earlier generation's queue: two at the root, two scripts."""
        files = {"run-task.sh": "#!/bin/sh\necho old\n", "old-briefs/0001.md": "an old brief\n",
                 "scripts/queue/claim.sh": "#!/bin/sh\nclaim\n",
                 "scripts/gate.sh": (PLANE_ROOT / "scripts/gate.sh").read_text() + "echo extra\n"}
        for rel, text in files.items():
            self.put(rel, text)
        return files


class Listing(SandboxCase):
    def test_every_leftover_is_named_and_no_plane_entry_is(self):
        self.leftovers()
        for name in OWNED:
            if "." in name:
                self.put(name, "{}\n")
            else:
                self.put(f"{name}/x.json", "{}\n")
        code, body, err = self.ccp("plane", "check")
        self.assertEqual(code, 1, err)
        self.assertEqual(body["root"], ["unknown: old-briefs/", "unknown: run-task.sh"])
        self.assertEqual(sorted(" ".join(s.split()[:2]) for s in body["scripts"]),
                         ["drifted: scripts/gate.sh", "unknown: scripts/queue/claim.sh"])
        self.assertFalse(body["ok"])

    def test_a_clean_queue_passes_with_both_lists_empty(self):
        code, body, err = self.ccp("plane", "check")
        self.assertEqual((code, body["scripts"], body["root"]), (0, [], []), err)

    def test_a_root_leftover_alone_fails_the_check(self):
        self.put("work.json.bak", "{}\n")
        code, body, _ = self.ccp("plane", "check")
        self.assertEqual((code, body["scripts"], body["root"]), (1, [], ["unknown: work.json.bak"]))

    def test_an_atomic_writes_temporary_file_is_not_a_leftover(self):
        self.put("work.json.tmp", "{}\n")
        self.assertEqual(queue.queue_leftovers(self.q), [])

    def test_finders_metadata_file_is_neither_listed_nor_moved(self):
        files = [self.put(rel, "") for rel in (".DS_Store", "scripts/.DS_Store", "scripts/queue/.DS_Store")]
        for args in (("plane", "check"), ("plane", "check", "--archive")):
            with self.subTest(args=args):
                code, body, err = self.ccp(*args)
                self.assertEqual((code, body["scripts"], body["root"]), (0, [], []), err)
                self.assertTrue(all(f.is_file() for f in files))
                self.assertFalse((self.q / "_legacy").exists())

    def test_a_script_the_binding_still_names_as_its_auth_check_is_a_leftover_like_any_other(self):
        # SPEC §29.3: the binding's `auth_check` is removed, so it keeps nothing in the queue.
        with open(self.sb["binding"], "a") as fh:
            fh.write("auth_check:\n  script: auth-check.sh\n")
        self.put("auth-check.sh", "#!/bin/sh\n")
        code, body, _ = self.ccp("plane", "check")
        self.assertEqual((code, body["root"]), (1, ["unknown: auth-check.sh"]))


class Archive(SandboxCase):
    def events(self) -> list[dict]:
        ledger = self.q / "observability" / "events.jsonl"
        return [json.loads(line) for line in ledger.read_text().splitlines()] if ledger.is_file() else []

    def test_an_archive_is_one_ledger_event_with_counts_and_no_path(self):
        self.put("old.txt", "old\n")
        self.put("results/0001.json", "{}\n")
        code, _, err = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0, err)
        ev = self.events()[-1]
        self.assertEqual((ev["type"], ev["op"]), ("plane", "archived"))
        self.assertEqual(ev["payload"], {"day": utc_day(), "archived": 2, "not_moved": 0})

    def test_an_archive_that_moved_nothing_records_what_it_could_not_move(self):
        self.put("run-task.sh", "old\n")
        self.put(f"_legacy/{utc_day()}", "a file where the day's directory would go\n")
        before = len(self.events())
        self.assertEqual(self.ccp("plane", "check", "--archive")[0], 1)
        rows = self.events()[before:]
        self.assertEqual([(ev["op"], ev["payload"]) for ev in rows],
                         [("archived", {"day": utc_day(), "archived": 0, "not_moved": 1})])

    def test_a_clean_queues_archive_writes_no_event(self):
        before = self.events()
        code, body, err = self.ccp("plane", "check", "--archive")
        self.assertEqual((code, body["archived"], body["not_moved"]), (0, [], []), err)
        self.assertEqual(self.events(), before)

    def test_the_archived_event_and_its_keys_are_in_the_contract(self):
        lib = queue.lib
        ev = {"at": "2026-01-01T00:00:00Z", "project_id": "demo", "task_id": "", "actor": "operator", "type": "plane",
              "op": "archived", "payload": {"day": "2026-01-01", "archived": 1, "not_moved": 0}}
        self.assertEqual(lib.validate_event(ev), [])
        for key in ("day", "archived", "not_moved"):
            payload = {k: v for k, v in ev["payload"].items() if k != key}
            self.assertIn(f"payload missing {key}", lib.validate_event({**ev, "payload": payload}))

    def test_one_command_archives_every_leftover_and_loses_nothing(self):
        files = self.leftovers()
        code, body, err = self.ccp("plane", "check", "--archive")
        day = utc_day()
        self.assertEqual(code, 0, err)
        self.assertEqual(sorted(r["path"] for r in body["archived"]),
                         ["old-briefs/", "run-task.sh", "scripts/gate.sh", "scripts/queue/claim.sh"])
        for r in body["archived"]:
            self.assertEqual(r["target"], f"_legacy/{day}/{r['path']}")
        self.assertEqual(body["not_moved"], [])
        for rel, text in files.items():
            self.assertFalse((self.q / rel).exists(), rel)
            self.assertEqual((self.q / "_legacy" / day / rel).read_text(), text, rel)
        code, body, _ = self.ccp("plane", "check")
        self.assertEqual((code, body["scripts"], body["root"]), (0, [], []))

    def test_an_archive_never_overwrites_an_earlier_one(self):
        self.leftovers()
        self.assertEqual(self.ccp("plane", "check", "--archive")[0], 0)
        self.put("run-task.sh", "#!/bin/sh\necho newer\n")
        code, body, _ = self.ccp("plane", "check", "--archive")
        target = f"_legacy/{utc_day()}/run-task.sh"
        self.assertEqual(code, 1)
        self.assertEqual([r["path"] for r in body["not_moved"]], ["run-task.sh"])
        self.assertIn(target, body["not_moved"][0]["reason"])
        self.assertEqual(body["archived"], [])
        self.assertEqual((self.q / "run-task.sh").read_text(), "#!/bin/sh\necho newer\n")
        self.assertEqual((self.q / target).read_text(), "#!/bin/sh\necho old\n")
        self.assertEqual(body["root"], ["unknown: run-task.sh"])

    def test_an_entry_that_cannot_be_moved_stays_and_is_named(self):
        self.put("run-task.sh", "old\n")
        self.put(f"_legacy/{utc_day()}", "a file where the day's directory would go\n")
        code, body, _ = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 1)
        self.assertEqual([r["path"] for r in body["not_moved"]], ["run-task.sh"])
        self.assertTrue((self.q / "run-task.sh").is_file())

    def test_the_retired_docs_sync_stamp_is_a_leftover_that_is_archived(self):
        stamp = "product-docs" + "-check.json"  # joined: the name is retired from every plane file but this one's data
        self.put(stamp, "{}\n")
        code, body, _ = self.ccp("plane", "check")
        self.assertEqual((code, body["root"]), (1, [f"unknown: {stamp}"]))
        code, body, _ = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0)
        self.assertEqual([r["path"] for r in body["archived"]], [stamp])
        self.assertFalse((self.q / stamp).exists())

    def test_a_retired_script_is_archived(self):
        self.put("scripts/spec-maintainer-lock.sh", "#!/bin/sh\n")
        code, body, _ = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0)
        self.assertEqual([r["path"] for r in body["archived"]], ["scripts/spec-maintainer-lock.sh"])

    def test_a_clean_copy_stays_and_the_script_a_binding_names_as_its_auth_check_is_archived(self):
        with open(self.sb["binding"], "a") as fh:
            fh.write("auth_check:\n  script: scripts/auth-check.sh\n")
        auth = self.put("scripts/auth-check.sh", "#!/bin/sh\nexit 0\n")
        gate = self.put("scripts/gate.sh", (PLANE_ROOT / "scripts/gate.sh").read_text())
        code, body, err = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0, err)
        self.assertEqual((body["scripts"], body["root"], [r["path"] for r in body["archived"]], body["not_moved"]),
                         ([], [], ["scripts/auth-check.sh"], []))
        self.assertFalse(auth.exists())
        self.assertTrue(gate.is_file())

    def test_a_directory_holding_the_script_a_binding_names_as_its_auth_check_is_archived_whole(self):
        with open(self.sb["binding"], "a") as fh:
            fh.write("auth_check:\n  script: tools/auth/check.sh\n")
        auth = self.put("tools/auth/check.sh", "#!/bin/sh\nexit 0\n")
        self.put("run-task.sh", "#!/bin/sh\n")
        code, body, err = self.ccp("plane", "check", "--archive")
        self.assertEqual(code, 0, err)
        self.assertEqual([r["path"] for r in body["archived"]], ["run-task.sh", "tools/"])
        self.assertEqual((body["root"], body["not_moved"]), ([], []))
        self.assertFalse(auth.exists())
        self.assertEqual((self.q / "_legacy" / utc_day() / "tools/auth/check.sh").read_text(), "#!/bin/sh\nexit 0\n")

    def test_the_archive_date_is_utc_whatever_the_local_zone(self):
        # Between them, these two zones put the local date off the UTC date at every hour of the day.
        for tz in ("Etc/GMT+12", "Pacific/Kiritimati"):
            with self.subTest(tz=tz):
                self.put("run-task.sh", tz)
                before = utc_day()
                code, body, _ = self.ccp("plane", "check", "--archive", TZ=tz)
                after = utc_day()
                self.assertEqual(code, 0)
                day = body["archived"][0]["target"].split("/")[1]
                self.assertIn(day, {before, after})
                shutil.rmtree(self.q / "_legacy")


class Init(SandboxCase):
    def test_init_on_a_queue_with_leftovers_warns_and_moves_nothing(self):
        self.put("run-task.sh", "#!/bin/sh\n")
        env = {k: v for k, v in self.env.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML")}
        r = subprocess.run([str(CCP), "init"], cwd=self.root, capture_output=True, text=True,
                           env={**env, "CCP_BINDINGS_DIR": str(self.base / "S" / "bindings")})
        self.assertEqual(r.returncode, 0, r.stderr)
        warnings = [w for w in json.loads(r.stdout).get("warnings", []) if "ccp plane check --archive" in w]
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0].startswith("1 "), warnings[0])
        self.assertTrue((self.q / "run-task.sh").is_file())
        self.assertFalse((self.q / "_legacy").exists())

    def test_init_on_a_clean_queue_does_not_warn_of_leftovers(self):
        env = {k: v for k, v in self.env.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML")}
        r = subprocess.run([str(CCP), "init"], cwd=self.root, capture_output=True, text=True,
                           env={**env, "CCP_BINDINGS_DIR": str(self.base / "S" / "bindings")})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse([w for w in json.loads(r.stdout).get("warnings", []) if "plane check" in w])


if __name__ == "__main__":
    unittest.main()
