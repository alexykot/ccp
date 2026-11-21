"""SPEC §16.5 rule 4: with several runners, `ccp tasks close` catches a verified head behind the integration tip
up itself when the merge is clean, the tip's new commits change no file the task's own diff or declared paths
change (with a build sign-off due, none the task's own diff changes, a parallel.shared path included, and the
catch-up carries the sign-off) and the product has a gate lane: it merges the tip in, runs the gate lane on the
merge as a recorded run, re-checks the tip, pushes the merge and merges it. Otherwise it refuses `behind_tip`,
naming the condition, with the task branch unchanged. Under `parallel.schedule: clashes` the file condition is the
task's own patch unchanged by the merge (`git patch-id --stable`), declared paths or none.

This module runs close end to end, one test for each path through it: caught up, gated and merged; a refusal
that names what it found; a red gate; the tip moving during the gate; the gate's environment; a rerun that closes
what a failed push, merge or reconcile left. Each decision branch is tested on plain values in
`tests.test_catch_up_decision`."""
from __future__ import annotations

import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
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


def product_test(cls: str, name: str, body: str, imports: str = "") -> str:
    """The text of a test module of the product's own suite (the gate's `ptests`): one test in one class."""
    return f"import unittest\n\n{imports}\n\n\nclass {cls}(unittest.TestCase):\n    def {name}(self):\n        {body}\n"


README = "# Package a\n\nIntro.\n\n## Files\n- `one.py`: one\n- `two.py`: two\n"
PATHS = 'paths: ["feature.txt", "ptests/test_feature.py", "shared.txt", "area/"]'


class CatchUp(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "parallel": {"max_in_flight": 2, "schedule": "paths"},
                  "suite": {"lanes": {"gate": ["/bin/sh", "-c", GATE]}}}

    def setUp(self):
        super().setUp()
        (self.ghstate.parent / "gh").write_text(FOLLOWING_GH)
        self.write("lib/__init__.py", "")
        self.write("lib/helper.py", "def helper():\n    return 1\n")
        self.write("ptests/__init__.py", "")
        self.write("ptests/test_base.py", product_test("T", "test_it", "self.assertTrue(True)"))
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

    def shared_readme(self) -> None:
        """docs/a/README.md on main, covered by plane.json parallel.shared."""
        self.write("docs/a/README.md", README)
        git(self.main, "add", "docs")
        git(self.main, "commit", "-q", "-m", "a package doc")
        git(self.main, "push", "-q", "origin", "main")
        self.plane_json(lambda c: c["parallel"].update(shared=["docs/*/README.md"]))

    def approved(self, sign_off: str | None = None, paths: bool = True, extra: dict[str, str] | None = None) -> str:
        """0002 claimed, built (feature.txt, a test importing lib.helper, line 1 of shared.txt, and each `extra`
        file with its text), pushed and approved: its head. `paths=False` declares none."""
        self.frontmatter(*([PATHS] if paths else []), *([f"sign_off: {sign_off}"] if sign_off else []))
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        wt = self.main / config.WORKTREES_DIR / "impl-0002"
        (wt / "feature.txt").write_text("built\n")
        (wt / "ptests/test_feature.py").write_text(
            product_test("F", "test_feature", "self.assertEqual(helper(), 1)", "from lib.helper import helper"))
        (wt / "shared.txt").write_text(SHARED.replace("line 1\n", "line one, built\n", 1))
        for rel, text in (extra or {}).items():
            (wt / rel).write_text(text)
        git(wt, "add", "feature.txt", "ptests/test_feature.py", "shared.txt", *(extra or {}))
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
        self.assertNotIn("sign_off_carried", cu)  # no build sign-off was due: none is carried
        git(self.main, "fetch", "-q", "origin")
        squash = body["merge_sha"]
        self.assertEqual(git(self.main, "show", f"{squash}:other/b.txt"), "b")
        self.assertEqual(git(self.main, "show", f"{squash}:feature.txt"), "built")
        self.assertFalse((self.main / config.WORKTREES_DIR / "merge-0002").exists())
        caught = [e for e in self.events() if (e["type"], e["op"]) == ("verify", "set")]
        self.assertEqual([e["payload"]["to"] for e in caught], [merged])
        self.assertNotIn("sign_off_carried", caught[0]["payload"])
        note = git(self.main, "show", "origin/main:docs/delivery/tasks/0002-second.md")
        self.assertIn(cu["gate_run"], note)  # the Verification notes line names the catch-up's gate run

    def gate_env(self) -> Path:
        """The gate lane appends what its stages see (the merge worktree's CCP_WT_* fields, the task, and the
        product's `worker_env` variable SCRATCH) to a file, one line a run; that file. None of it is in close's
        environment."""
        seen = Path(self._tmp.name) / "gate-env.txt"
        show = ('printf "%s|%s|%s|%s|%s|%s|%s\\n" "$CCP_WT_WORKTREE" "$CCP_WT_KIND" "$CCP_WT_NAME" "$CCP_TASK_ID" '
                f'"$CCP_NNNN" "$CCP_WT_SEAT" "$SCRATCH" >> {shlex.quote(str(seen))}; ')

        def edit(c):
            c["suite"]["lanes"]["gate"] = ["/bin/sh", "-c", show + GATE]
            c.setdefault("prompts", {})["worker_env"] = {"SCRATCH": "{{kind}}_{{nnnn}}"}
        self.plane_json(edit)
        return seen

    def close_bare(self):
        """close, with no CCP_WT_*, task or SCRATCH variable of the caller's reaching the gate."""
        with mock.patch.dict(os.environ):
            for k in [k for k in os.environ if k.startswith("CCP_WT_") or k in ("CCP_TASK_ID", "CCP_NNNN", "SCRATCH")]:
                del os.environ[k]
            return self.close()

    def seen(self, f: Path) -> tuple[list[str], str]:
        """The one line the gate wrote, its worktree resolved; the merge worktree it names, resolved."""
        lines = f.read_text().splitlines()
        self.assertEqual(len(lines), 1, lines)
        got = lines[0].split("|")
        return [str(Path(got[0]).resolve()), *got[1:]], str((self.main / config.WORKTREES_DIR / "merge-0002").resolve())

    def test_the_gate_runs_with_the_merge_worktree_s_environment_and_worker_env(self):
        seen = self.gate_env()
        self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        code, body, out, err = self.close_bare()
        self.assertEqual(code, 0, out + err)
        self.assertTrue(body["merged_now"])
        self.assertEqual([r["state"] for r in self.gate_runs()], ["passed"])
        got, merge_wt = self.seen(seen)
        self.assertEqual(got, [merge_wt, "merge", "merge-0002", "0002-second", "0002", "impl", "merge_0002"])

    def test_under_clashes_a_union_in_a_shared_path_is_caught_up_again_when_the_tip_moves_during_the_gate(self):
        self.shared_readme()
        self.plane_json(lambda c: c["parallel"].update(schedule="clashes"))  # the product default: the patch test alone
        head = self.approved(paths=False, extra={"docs/a/README.md": README + "- `task.py`: the task's\n"})
        self.tip(self.put("docs/a/README.md", README + "- `tip.py`: the tip's\n"))
        self.gate_hook(moves=1)
        code, body, out, err = self.close()
        self.assertEqual(code, 0, out + err)
        cu = self.record()["catch_up"]
        self.assertEqual(len(self.gate_runs()), 2)
        self.assertEqual(cu["gate_run"], self.gate_runs()[-1]["suite_id"])
        git(self.main, "fetch", "-q", "origin")
        self.assertEqual(cu["from"], head)
        self.assertEqual(cu["tip"], git(self.main, "rev-parse", "origin/main~2"))  # the mover's commit; then the squash
        self.assertEqual(cu["merge_tree"], "union")
        self.assertEqual(cu["tip_files"], ["docs/a/README.md", "other/moving.txt"])
        self.assertIn(f"--match-head-commit {cu['to']}", (self.ghstate / "merge-called").read_text())
        self.assertEqual(git(self.main, "show", f"{body['merge_sha']}:docs/a/README.md") + "\n",
                         README + "- `tip.py`: the tip's\n- `task.py`: the task's\n")

    def test_a_tip_that_keeps_moving_refuses_after_three_catch_ups(self):
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        self.gate_hook(moves=99)
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "tip moved too often")
        self.assertEqual(len(self.gate_runs()), lifecycle.CATCH_UPS)
        self.assertFalse((self.main / config.WORKTREES_DIR / "merge-0002").exists())

    # ------------------------------------------------------------------ refusals

    def test_a_tip_changing_a_file_the_task_changes_refuses_naming_overlap(self):
        head = self.approved()
        self.tip(self.put("shared.txt", SHARED.replace("line 10\n", "line ten\n")))  # another hunk: merges clean
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "overlap", "shared.txt")
        self.assertEqual(self.gate_runs(), [])

    def test_a_red_gate_on_the_merge_refuses_naming_the_gate_run(self):
        head = self.approved()
        self.tip(self.put("lib/helper.py", "def other():\n    return 2\n"))  # A's test imports helper
        code, _, out, err = self.close()
        runs = self.gate_runs()
        self.assertEqual([r["state"] for r in runs], ["failed"])
        self.refused(code, out, err, head, "red gate", runs[0]["suite_id"])
        self.assertFalse((self.main / config.WORKTREES_DIR / "merge-0002").exists())

    def sign_build(self) -> None:
        code, _, out, err = self.ccp("tasks", "sign-off", "0002", "--stage", "build", "--by", "op", "--words", "ship it")
        self.assertEqual(code, 0, out + err)

    def sign_offs_recorded(self) -> list[dict]:
        return [e for e in self.events() if (e["type"], e["op"]) == ("sign_off", "recorded")]

    def test_a_rerun_after_the_carried_merge_holds_the_sign_off(self):
        self.plane_json(lambda c: c["reconcile"].update(hooks=["exit 3"]))
        head = self.approved(sign_off="build")
        self.sign_build()
        tip = self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close(root=self.main)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(json.loads((self.ghstate / "pr.json").read_text())["state"], "MERGED")
        cu = self.record()["catch_up"]
        self.assertEqual((cu["from"], cu["tip"], cu["sign_off_carried"]), (head, tip, head))
        caught = [e for e in self.events() if (e["type"], e["op"]) == ("verify", "set")]
        self.assertEqual([e["payload"]["sign_off_carried"] for e in caught], [head])
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        cfg["reconcile"]["hooks"] = []
        self.write("docs/delivery/plane.json", json.dumps(cfg))
        git(self.main, "commit", "-qam", "the hook fixed")
        git(self.main, "pull", "-q", "--rebase", "origin", "main")
        git(self.main, "push", "-q", "origin", "main")
        code, body, out, err = self.close(root=self.main)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("is stale", err)
        self.assertFalse(body["merged_now"])
        self.assertTrue(body["reconciled_now"])
        self.assertEqual(len(self.sign_offs_recorded()), 1)  # no new sign-off was recorded

    def test_a_product_with_no_gate_lane_refuses_and_never_skips_the_run(self):
        self.plane_json(lambda c: c.pop("suite"))
        head = self.approved()
        self.tip(self.put("other/b.txt", "b\n"))
        code, _, out, err = self.close()
        self.refused(code, out, err, head, "no gate lane")
        self.assertEqual(self.gate_runs(), [])

    def test_a_product_with_no_worktrees_dir_refuses(self):
        head = self.approved()
        self.plane_json(lambda c: c["worktrees"].update(dir=None))  # on the tip: it is what the head lacks
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


if __name__ == "__main__":
    unittest.main()
