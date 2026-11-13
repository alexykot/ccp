"""SPEC §16.5 rule 4: with several runners, `ccp tasks close` catches a verified head behind the integration tip
up itself when the merge is clean, the tip's new commits change no file the task's own diff or declared paths
change, the task declares no build sign-off and the product has a gate lane: it merges the tip in, runs the gate
lane on the merge as a recorded run, re-checks the tip, pushes the merge and merges it. Otherwise it refuses
`behind_tip`, naming the condition, with the task branch unchanged."""
from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ccp import config, lifecycle, suite, tasklog, verify
from tests.test_toolkit import FAKE_GH, PLANE, ToolkitFixture, git

# GitHub moves an open PR's head with its branch; a `refuse-merge` file makes the merge fail
FOLLOWING_GH = FAKE_GH.replace("args = sys.argv[1:]\n", '''args = sys.argv[1:]
if pr.get("state") == "OPEN" and pr.get("branch"):
    got = subprocess.run(["git", "ls-remote", pr["origin"], "refs/heads/" + pr["branch"]],
                         capture_output=True, text=True).stdout.split()
    if got:
        pr["head"] = got[0]
if args[:2] == ["pr", "merge"] and os.path.exists(os.path.join(d, "refuse-merge")):
    print("the hosting service refused the merge", file=sys.stderr); sys.exit(1)
''', 1)

PY = shlex.quote(sys.executable)
GATE = (f'if [ -n "$CATCH_UP_GATE_HOOK" ]; then {PY} "$CATCH_UP_GATE_HOOK" || exit 9; fi; '
        f'exec {PY} -m unittest discover -q -s ptests -t .')
SHARED = "".join(f"line {i}\n" for i in range(1, 11))
PATHS = 'paths: ["feature.txt", "ptests/test_feature.py", "shared.txt", "area/"]'


class CatchUp(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "parallel": {"max_in_flight": 2},
                  "suite": {"lanes": {"gate": ["/bin/sh", "-c", GATE]}}}

    def setUp(self):
        super().setUp()
        (self.ghstate.parent / "gh").write_text(FOLLOWING_GH)
        self.write("lib/__init__.py", "")
        self.write("lib/helper.py", "def helper():\n    return 1\n")
        self.write("ptests/__init__.py", "")
        self.write("ptests/test_base.py", "import unittest\n\n\nclass T(unittest.TestCase):\n"
                                          "    def test_it(self):\n        self.assertTrue(True)\n")
        self.write("shared.txt", SHARED)
        self.write("area/x.txt", "x\n")
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "the product's code")
        git(self.main, "push", "-q", "origin", "main")

    # ------------------------------------------------------------------ helpers

    def frontmatter(self, *lines: str) -> None:
        """Add lines to 0002's frontmatter on main, before it is claimed."""
        p = self.main / "docs/delivery/tasks/0002-second.md"
        p.write_text(p.read_text().replace("depends_on:", "\n".join(lines) + "\ndepends_on:", 1))
        tasklog.write_index(config.load(self.main))
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "0002 frontmatter")
        git(self.main, "push", "-q", "origin", "main")

    def plane_json(self, edit) -> None:
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        edit(cfg)
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        git(self.main, "commit", "-qam", "plane.json")
        git(self.main, "push", "-q", "origin", "main")

    def approved(self, paths: bool = True, sign_off: str | None = None, brief_signed: bool = False) -> str:
        """0002 claimed, built (feature.txt, a test importing lib.helper, line 1 of shared.txt), pushed and
        approved: its head. `brief_signed` records the brief sign-off before the claim."""
        self.frontmatter(*([PATHS] if paths else []), *([f"sign_off: {sign_off}"] if sign_off else []))
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        if brief_signed:
            code, _, out, err = self.ccp("tasks", "sign-off", "0002", "--stage", "brief", "--by", "op", "--words", "go")
            self.assertEqual(code, 0, out + err)
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        wt = self.main / ".rt" / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        (wt / "ptests/test_feature.py").write_text(
            "import unittest\n\nfrom lib.helper import helper\n\n\nclass F(unittest.TestCase):\n"
            "    def test_feature(self):\n        self.assertEqual(helper(), 1)\n")
        (wt / "shared.txt").write_text(SHARED.replace("line 1\n", "line one, built\n", 1))
        git(wt, "add", "feature.txt", "ptests/test_feature.py", "shared.txt")
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(wt, "rev-parse", "HEAD")
        (self.ghstate / "pr.json").write_text(json.dumps({"state": "OPEN", "head": head, "origin": str(self.origin),
                                                           "base": "main", "branch": "task/0002-second"}))
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 0, out + err)
        rec = json.loads((PLANE / "contracts/verification.example.json").read_text())
        rec.update(task_id="0002-second", head_sha=head)
        rec.pop("checked_at", None)
        rec["checks"] = [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}]
        f = Path(self._tmp.name) / "verdict.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 0, out + err)
        return head

    def tip(self, change, msg: str = "Task 0009: other code") -> str:
        """Another task merges first: `change(checkout)` edits a checkout of the tip; committed and pushed."""
        with tempfile.TemporaryDirectory() as d:
            c = Path(d) / "c"
            git(Path(d), "clone", "-q", str(self.origin), str(c))
            change(c)
            git(c, "add", "-A")
            git(c, "commit", "-q", "-m", msg)
            git(c, "push", "-q", "origin", "HEAD:main")
            return git(c, "rev-parse", "HEAD")

    @staticmethod
    def put(rel: str, text: str):
        def change(c: Path) -> None:
            (c / rel).parent.mkdir(parents=True, exist_ok=True)
            (c / rel).write_text(text)
        return change

    def close(self, root: Path | None = None):
        return self.ccp("tasks", "close", "0002", "--pr", "7", "--summary", "it is built.", root=root)

    def branch(self) -> str:
        return git(self.main, "ls-remote", str(self.origin), "refs/heads/task/0002-second").split()[0]

    def gate_runs(self) -> list[dict]:
        return [r for r in suite.fold(self.q) if r.get("task_id") == "0002-second" and r.get("lane") == "gate"]

    def record(self) -> dict:
        return json.loads((self.q / "verification/0002-second.json").read_text())

    def refused(self, code, out, err, head, *names):
        self.assertEqual(code, 1, out + err)
        self.assertIn("behind_tip", err)
        self.assertIn("nothing merged", err)
        for n in names:
            self.assertIn(n, err)
        self.assertFalse((self.ghstate / "merge-called").exists())
        self.assertEqual(self.branch(), head)
        self.assertNotIn("catch_up", self.record())

    def gate_hook(self, moves: int) -> None:
        """The gate pushes a disjoint commit to main on each of its first `moves` runs: the tip moves under it."""
        t = Path(self._tmp.name)
        git(t, "clone", "-q", str(self.origin), str(t / "mover"))
        hook = t / "hook.py"
        hook.write_text(f"""import pathlib, subprocess
n = pathlib.Path({str(t / 'moves')!r})
done = int(n.read_text()) if n.exists() else 0
if done < {moves}:
    c = {str(t / 'mover')!r}
    run = lambda *a: subprocess.run(["git", "-C", c, *a], check=True, capture_output=True)
    run("pull", "-q", "origin", "main")
    p = pathlib.Path(c, "other", "moving.txt")
    p.parent.mkdir(exist_ok=True)
    p.write_text(str(done))
    run("add", "-A")
    run("commit", "-q", "-m", "Task 0011: more other code")
    run("push", "-q", "origin", "HEAD:main")
    n.write_text(str(done + 1))
""")
        self.env_hook = mock.patch.dict("os.environ", {"CATCH_UP_GATE_HOOK": str(hook)})
        self.env_hook.start()
        self.addCleanup(self.env_hook.stop)

    # ------------------------------------------------------------------ catching up

    def test_a_disjoint_tip_is_caught_up_gated_and_merged(self):
        head = self.approved()
        tip = self.tip(self.put("other/b.txt", "b\n"))
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])
        cu = self.record()["catch_up"]
        merged = cu["to"]
        self.assertEqual(body["caught_up"], cu)
        self.assertEqual((cu["from"], cu["tip"], cu["merge_tree"]), (head, tip, "clean"))
        self.assertEqual(git(self.main, "rev-list", "--parents", "-n1", merged).split()[1:], [head, tip])
        self.assertIn(f"--match-head-commit {merged}", (self.ghstate / "merge-called").read_text())
        self.assertEqual(json.loads((self.ghstate / "pr.json").read_text())["head"], merged)
        self.assertEqual(cu["tip_files"], ["other/b.txt"])
        self.assertEqual(cu["task_files"], ["feature.txt", "ptests/test_feature.py", "shared.txt"])
        runs = self.gate_runs()
        self.assertEqual([r["suite_id"] for r in runs], [cu["gate_run"]])
        self.assertEqual((runs[0]["state"], runs[0]["phase"]), ("passed", "verify"))
        self.assertEqual(self.record()["schema_version"], verify.RECORD_VERSION)
        git(self.main, "fetch", "-q", "origin")
        squash = body["merge_sha"]
        self.assertEqual(git(self.main, "show", f"{squash}:other/b.txt"), "b")
        self.assertEqual(git(self.main, "show", f"{squash}:feature.txt"), "built")
        self.assertFalse((self.main / ".rt" / "merge-0002").exists())
        caught = [e for e in self.events() if (e["type"], e["op"]) == ("verify", "set")]
        self.assertEqual([e["payload"]["to"] for e in caught], [merged])
        note = git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md")
        self.assertIn(cu["gate_run"], note)  # the Verification notes line names the catch-up's gate run

    def test_a_tip_that_moves_during_the_gate_is_caught_up_again(self):
        self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        self.gate_hook(moves=1)
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        cu = self.record()["catch_up"]
        self.assertEqual(len(self.gate_runs()), 2)
        self.assertEqual(cu["gate_run"], self.gate_runs()[-1]["suite_id"])
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(cu["tip"], git(self.main, "rev-parse", "origin/main~2"))  # the mover's commit; then the squash
        self.assertEqual(cu["tip_files"], ["other/b.txt", "other/moving.txt"])
        self.assertIn(f"--match-head-commit {cu['to']}", (self.ghstate / "merge-called").read_text())

    def test_a_tip_that_keeps_moving_refuses_after_three_catch_ups(self):
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        self.gate_hook(moves=99)
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "tip moved too often")
        self.assertEqual(len(self.gate_runs()), lifecycle.CATCH_UPS)
        self.assertFalse((self.main / ".rt" / "merge-0002").exists())

    # ------------------------------------------------------------------ refusals

    def test_a_tip_changing_a_file_the_task_changes_refuses_naming_overlap(self):
        head = self.approved()
        self.tip(self.put("shared.txt", SHARED.replace("line 10\n", "line ten\n")))  # another hunk: merges clean
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "overlap", "shared.txt")
        self.assertEqual(self.gate_runs(), [])

    def test_a_tip_renaming_a_file_the_task_changes_refuses_naming_overlap(self):
        head = self.approved()
        self.tip(lambda c: git(c, "mv", "shared.txt", "renamed.txt"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "overlap", "shared.txt")

    def test_a_tip_changing_a_declared_path_the_diff_leaves_refuses_naming_overlap(self):
        head = self.approved()
        self.tip(self.put("area/x.txt", "changed\n"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "overlap", "area/x.txt")

    def test_a_task_with_no_declared_paths_refuses_naming_it(self):
        head = self.approved(paths=False)
        self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "no declared paths")

    def test_a_conflicting_tip_refuses_naming_the_conflict(self):
        head = self.approved()
        self.tip(self.put("shared.txt", SHARED.replace("line 1\n", "line one, other\n", 1)))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "conflict", "shared.txt")
        self.assertEqual(self.gate_runs(), [])

    def test_a_red_gate_on_the_merge_refuses_naming_the_gate_run(self):
        head = self.approved()
        self.tip(self.put("lib/helper.py", "def other():\n    return 2\n"))  # A's test imports helper
        code, _, out, err = self.close()
        runs = self.gate_runs()
        self.assertEqual([r["state"] for r in runs], ["failed"])
        self.refused(code, out, err, head, "red gate", runs[0]["suite_id"])
        self.assertFalse((self.main / ".rt" / "merge-0002").exists())

    def test_a_build_sign_off_is_never_carried_across_a_catch_up(self):
        head = self.approved(sign_off="build")
        code, _, out, err = self.ccp("tasks", "sign-off", "0002", "--stage", "build", "--by", "op", "--words", "ship it")
        self.assertEqual(code, 0, out + err)
        self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "build sign-off")

    def test_a_brief_sign_off_is_carried_across_a_catch_up(self):
        head = self.approved(sign_off="brief", brief_signed=True)
        self.tip(self.put("other/b.txt", "b\n"))
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])
        self.assertEqual(self.record()["catch_up"]["from"], head)

    def test_a_product_with_no_gate_lane_refuses_and_never_skips_the_run(self):
        self.plane_json(lambda c: c.pop("suite"))
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "no gate lane")
        self.assertEqual(self.gate_runs(), [])

    def test_a_product_with_no_worktrees_dir_refuses(self):
        head = self.approved()
        self.plane_json(lambda c: c["adapter"].pop("worktree_dir"))  # on the tip: it is what the head lacks
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "no merge worktree")

    def test_a_gate_lane_held_by_another_run_refuses(self):
        self.plane_json(lambda c: c["suite"].update(exclusive_lanes=["gate"]))
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        fd, _ = suite.take_lane(self.q, {"suite_id": "st-held", "pid": os.getpid(), "lane": "gate"})
        self.addCleanup(os.close, fd)
        with mock.patch.object(lifecycle, "CATCH_UP_LANE_WAIT", 0):
            code, _, out, err = self.close()
        self.refused(code, out, err, head, "gate lane busy")

    def test_a_queue_that_keeps_its_records_in_git_refuses(self):
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        git(self.q, "init", "-q")
        git(self.q, "add", "verification")
        git(self.q, "commit", "-q", "-m", "records")
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "in git")

    def test_a_refused_push_refuses_with_the_branch_unchanged(self):
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        hook = self.origin / "hooks" / "pre-receive"
        hook.write_text("#!/bin/sh\nwhile read old new ref; do case $ref in refs/heads/task/*) exit 1;; esac; done\n")
        hook.chmod(0o755)
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "push refused")

    # ------------------------------------------------------------------ after the push

    def test_a_refused_merge_after_the_push_is_closed_by_a_rerun(self):
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        (self.ghstate / "refuse-merge").write_text("")
        code, _, out, err = self.close()
        self.assertEqual(code, 1, out + err)
        merged = self.record()["catch_up"]["to"]
        self.assertEqual(self.branch(), merged)  # pushed: the record covers it
        self.assertIn(f"close's catch-up {merged[:7]}", err)
        (self.ghstate / "refuse-merge").unlink()
        code, _, out, err = self.ccp("verify", "merge-ok", "7", "--task", "0002-second")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads(out)["match_head_commit"], merged)
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        self.assertEqual(json.loads((self.ghstate / "pr.json").read_text())["head"], merged)
        self.assertEqual(self.record()["catch_up"]["from"], head)
        self.assertEqual(len(self.gate_runs()), 1)

    def test_a_failed_reconcile_after_a_caught_up_merge_is_reconciled_by_a_rerun(self):
        self.plane_json(lambda c: c["reconcile"].update(hooks=["exit 3"]))
        self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close(root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(json.loads((self.ghstate / "pr.json").read_text())["state"], "MERGED")
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = []
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        git(self.main, "commit", "-qam", "the hook fixed")
        git(self.main, "pull", "-q", "--rebase", "origin", "main")
        git(self.main, "push", "-q", "origin", "main")
        code, body, out, err = self.close(root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])

    def test_a_verdict_cannot_carry_a_catch_up(self):
        head = self.approved()
        rec = self.record()
        rec.pop("checked_at")
        rec["catch_up"] = {"from": head, "to": head, "tip": head, "gate_run": "st-x", "merge_tree": "clean",
                           "tip_files": [], "task_files": []}
        f = Path(self._tmp.name) / "forged.json"
        f.write_text(json.dumps(rec))
        code, _, out, err = self.ccp("verify", "record", str(f))
        self.assertEqual(code, 1, out + err)
        self.assertIn("catch_up", err)


class MergeOkReadsTheCatchUp(unittest.TestCase):
    """`ccp verify merge-ok` takes a caught-up head only through a catch-up from the approved head whose gate run
    is a passed run of the gate lane bound to the task."""

    H, M = "a" * 40, "b" * 40

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.q = Path(self._tmp.name)
        (self.q / "runs").mkdir()
        self.cfg = SimpleNamespace(suite={"roles": {"gate": "gate"}})
        self.rows = []

    def tearDown(self):
        self._tmp.cleanup()

    def run_(self, sid, task="0002-second", lane="gate", code=0):
        at = "2026-11-13T10:00:00Z"
        self.rows += [{"op": "started", "suite_id": sid, "at": at, "lane": lane, "task_id": task, "run_id": None},
                      {"op": "ended", "suite_id": sid, "at": at, "exit_code": code}]
        (self.q / "runs/_suites.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.rows))

    def why(self, gate_run="st-ok", frm=None, to=None, head=None):
        rec = {"head_sha": self.H, "catch_up": {"from": frm or self.H, "to": to or self.M, "tip": "c" * 40,
                                                "gate_run": gate_run, "merge_tree": "clean", "tip_files": [],
                                                "task_files": []}}
        return verify.catch_up_refusal(self.cfg, self.q, rec, "0002-second", head or self.M)

    def test_a_passed_gate_run_of_the_task_covers_the_catch_up(self):
        self.run_("st-ok")
        self.assertIsNone(self.why())

    def test_every_other_catch_up_is_refused(self):
        self.run_("st-ok")
        self.run_("st-red", code=1)
        self.run_("st-other", task="0003-third")
        self.run_("st-full", lane="full")
        for case, want in ((dict(gate_run="st-none"), "not recorded"), (dict(gate_run="st-red"), "did not pass"),
                           (dict(gate_run="st-other"), "0003-third"), (dict(gate_run="st-full"), "gate lane"),
                           (dict(frm="d" * 40), "approved head"), (dict(head="e" * 40), "not eeeeeee")):
            self.assertIn(want, self.why(**case) or "", case)


if __name__ == "__main__":
    unittest.main()
