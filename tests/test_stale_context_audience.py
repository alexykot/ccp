"""SPEC §21.1, §13.2, §16.5, §22.5: who hears that a brief was measured before commits that changed its paths.
`ccp tasks check` counts such tasks in one warning and `--stale` names them; the implement prompt carries the
task's own line; the spawn and its dry run show the scope's lines to the lead without refusing; and a respawn on
`work.json`'s review point keeps the pending tasks the lead added to the scope."""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import cli, config, tasklog
from tests.helpers import PLANE_ROOT, REVIEW_REGISTER as REGISTER, Product, done_report, tagged_task as _tagged
from tests.review_flow import A, ReviewFlow
from tests.team_hosting_fixture import TeamCase
from tests.toolkit_fixture import ToolkitFixture, git

RERUN = "Re-run the Context's measurements"


def measured(f: Path, sha: str, path: str) -> None:
    """Give the task file `f` the paths [`path`] and a Context measured at `sha`."""
    f.write_text(f.read_text().replace("spec_refs:", f'paths: ["{path}"]\nspec_refs:', 1)
                 .replace("- background", f"- Measured at `{sha}`.", 1))


def commit(root: Path, rel: str, msg: str) -> str:
    """Append a line to `rel` (made when missing) and commit it: the commit's short sha."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((p.read_text() if p.is_file() else "") + "x = 1\n")
    git(root, "add", rel)
    git(root, "commit", "-qm", msg)
    return git(root, "rev-parse", "--short=7", "HEAD")


def warning_lines(out: str) -> list[str]:
    return [ln.removeprefix("  warning: ") for ln in out.splitlines() if ln.startswith("  warning: ")]


class TasksCheck(unittest.TestCase):
    """A git product with two pending tasks measured at a commit before a change to their paths, and a third
    whose Context states a number with no command (another warning)."""

    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        git(self.p.root, "init", "-q", "-b", "main")
        base = commit(self.p.root, "src/a.py", "init")
        for tid in ("0001-a", "0002-b"):
            measured(self.p.task(tid), base, "src/a.py")
        f = self.p.task("0003-c")
        f.write_text(f.read_text().replace("- background", "- 42 sites"))
        self.p.index()
        commit(self.p.root, "src/a.py", "change a")

    def check(self, *flags: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "tasks", "check", *flags])
        return code, out.getvalue(), err.getvalue()

    def test_the_check_counts_the_stale_tasks_in_one_warning_and_names_none(self):
        stale = tasklog.stale(self.p.cfg)
        self.assertEqual(len(stale), 2, stale)
        code, out, err = self.check()
        self.assertEqual(code, 0, out + err)
        warns = warning_lines(out)
        self.assertIn(tasklog.stale_count(2)[0], warns)
        counted = [w for w in warns if "--stale" in w]
        self.assertEqual(len(counted), 1, warns)
        self.assertIn("2", counted[0])
        for line in stale:
            self.assertNotIn(line, warns)
        self.assertTrue(any("Context states a number" in w for w in warns), warns)  # the other warnings stay

    def test_stale_names_each_task_and_no_other_warning(self):
        code, out, err = self.check("--stale")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(warning_lines(out), tasklog.stale(self.p.cfg))
        self.assertEqual(len(warning_lines(out)), 2)

    def test_stale_goes_with_no_other_flag(self):
        for flag in ("--lease", "--closed-points", "--staged"):
            code, _, err = self.check("--stale", flag)
            self.assertEqual(code, 2, flag)
            self.assertIn("--stale", err)

    def test_no_stale_task_gives_no_count(self):
        self.assertEqual(tasklog.stale_count(0), [])
        self.assertEqual(len(tasklog.stale_count(1)), 1)


class ImplementPrompt(ReviewFlow, ToolkitFixture, unittest.TestCase):
    """`ccp prompt implement` carries the task's own stale-Context line; a fix round and a fresh task do not."""

    def setUp(self):
        super().setUp()
        clock = iter(f"2026-10-22T{10 + i // 60:02d}:{i % 60:02d}:00Z" for i in range(600))
        patch = mock.patch("ccp.runs.iso", side_effect=lambda: next(clock))
        patch.start()
        self.addCleanup(patch.stop)

    def make_stale(self) -> None:
        """Measure 0002-second's Context at a commit, then change its path, on origin/main and the runner's checkout."""
        base = commit(self.main, "src/a.py", "add a")
        measured(self.main / "docs/delivery/tasks/0002-second.md", base, "src/a.py")
        git(self.main, "add", "docs/delivery/tasks/0002-second.md")
        git(self.main, "commit", "-qm", "measure 0002")
        commit(self.main, "src/a.py", "change a")
        git(self.main, "push", "-q", "origin", "main")
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")

    def implement(self) -> str:
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.run_id = body["run_id"]
        return Path(body["prompt_path"]).read_text()

    def test_a_stale_tasks_implement_prompt_names_its_line_and_its_fix_prompt_does_not(self):
        self.make_stale()
        cfg = config.load(self.runner)
        meta = next(t for t in tasklog.load(cfg) if t["task_id"] == "0002-second")
        line = tasklog.stale_context(cfg, meta, cfg.rel(meta["_file"]))
        self.assertEqual(len(line), 1, line)
        text = self.implement()
        self.assertIn(line[0], text)
        self.assertIn(RERUN, text)
        code, _, out, err = self.report(self.run_id, done_report("implement", "PR: #7", f"Head: {A}"))
        self.assertEqual(code, 0, out + err)
        self.run_phase("review", A, "Severity: BLOCKER=1 MAJOR=0 MINOR=0 NIT=0")
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", A)
        self.assertEqual(code, 0, out + err)
        fix = Path(body["prompt_path"]).read_text()
        self.assertNotIn(line[0], fix)
        self.assertNotIn(RERUN, fix)
        self.assertNotIn("Context says Measured at", fix)

    def test_a_fresh_tasks_implement_prompt_has_neither(self):
        text = self.implement()
        self.assertNotIn(RERUN, text)
        self.assertNotIn("Context says Measured at", text)


class Spawn(TeamCase):
    """The spawn and its dry run on a scope holding one stale task (0001-a) and one fresh one (0002-b)."""

    def setUp(self):
        super().setUp()
        base = commit(self.prod.root, "src/a.py", "add a")
        measured(self.prod.task("0001-a"), base, "src/a.py")
        self.prod.task("0002-b")
        self.prod.index()
        commit(self.prod.root, "src/a.py", "change a")
        self.stale = tasklog.stale(self.prod.cfg)
        self.assertEqual(len(self.stale), 1, self.stale)

    def test_the_dry_run_lists_the_stale_line_and_is_ready(self):
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual((res["ready"], res["stale"]), (True, self.stale))
        self.assertNotIn("failed", res)
        self.assertIn(f"warning: {self.stale[0]}", err)
        code, res, err = self.team("runner", "spawn", "--dry-run", "--scope", "0002-b")
        self.assertEqual((code, res["stale"]), (0, []), err)
        self.assertNotIn("Context says Measured at", err)

    def test_the_spawn_prints_the_stale_line_as_a_warning_and_spawns(self):
        code, res, err = self.team("runner", "spawn", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertEqual(res["outcome"], "spawn_recorded")
        self.assertIn(f"warning: {self.stale[0]}", err)

    def test_runner_slots_show_it_too(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "parallel": {"max_in_flight": 2}}))
        code, res, err = self.team("runner", "spawn", "--dry-run", "--count", "2", "--scope", "0001-a,0002-b")
        self.assertEqual((code, res["ready"], res["stale"]), (0, True, self.stale), err)
        self.assertIn(f"warning: {self.stale[0]}", err)
        code, res, err = self.team("runner", "spawn", "--count", "2", "--scope", "0001-a,0002-b")
        self.assertEqual(code, 0, err)
        self.assertIn(f"warning: {self.stale[0]}", err)


class Respawn(TeamCase):
    """§22.5: R8 tags 0001-a; the lead adds the untagged 0002-b to the running scope; R10 tags 0003-c."""

    def setUp(self):
        super().setUp()
        self.prod.write("docs/delivery/review-points.yaml", REGISTER)
        _tagged(self.prod, "0001-a", "pending", "R8")
        _tagged(self.prod, "0002-b", "pending")
        _tagged(self.prod, "0003-c", "pending", "R10")
        self.prod.index()

    def spawn_and_add(self) -> None:
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual((code, res["scope"]), (0, ["0001-a"]), err)
        code, res, err = self.team("runner", "scope", "--add", "0002-b")
        self.assertEqual((code, res["scope"]), (0, ["0001-a", "0002-b"]), err)

    def test_a_respawn_on_the_same_point_keeps_the_task_the_lead_added(self):
        self.spawn_and_add()
        code, res, err = self.team("runner", "spawn", "--review-point", "R8", "--dry-run")
        self.assertEqual((code, res["scope"]), (0, ["0001-a", "0002-b"]), err)
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual((code, res["scope"]), (0, ["0001-a", "0002-b"]), err)
        self.assertEqual(json.loads((self.q / "work.json").read_text())["scope"], ["0001-a", "0002-b"])

    def test_a_task_the_lead_added_that_is_done_is_not_kept(self):
        self.spawn_and_add()
        self.prod.task("0002-b", "done")
        self.prod.index()
        code, res, err = self.team("runner", "spawn", "--review-point", "R8", "--dry-run")
        self.assertEqual((code, res["scope"]), (0, ["0001-a"]), err)

    def test_a_respawn_whose_tagged_tasks_are_done_spawns_on_the_added_ones_and_another_point_still_refuses(self):
        self.spawn_and_add()
        _tagged(self.prod, "0001-a", "done", "R8")
        _tagged(self.prod, "0003-c", "done", "R10")
        self.prod.index()
        code, res, err = self.team("runner", "spawn", "--review-point", "R8", "--dry-run")
        self.assertEqual((code, res["scope"]), (0, ["0002-b"]), err)
        code, _, err = self.team("runner", "spawn", "--review-point", "R10", "--dry-run")
        self.assertEqual(code, 2, err)
        self.assertIn("no open task is tagged review_point: R10", err)

    def test_a_new_point_takes_only_its_tagged_tasks(self):
        self.spawn_and_add()
        code, res, err = self.team("runner", "spawn", "--review-point", "R10", "--dry-run")
        self.assertEqual((code, res["scope"]), (0, ["0003-c"]), err)

    def test_the_points_refactors_stay_on_top_and_announced(self):
        self.prod.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", "architect": {"shape_from_task": "0001"}}))
        f = _tagged(self.prod, "0004-tidy", "pending")
        f.write_text(f.read_text().replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E1"]'))
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle", "review_point": "R7"}))
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual((code, res["refactors_added"], res["scope"]), (0, ["0004-tidy"], ["0004-tidy", "0001-a"]), err)
        self.assertEqual(self.team("runner", "scope", "--add", "0002-b")[0], 0)
        code, res, err = self.team("runner", "spawn", "--review-point", "R8")
        self.assertEqual((code, res["refactors_added"], res["scope"]),
                         (0, ["0004-tidy"], ["0004-tidy", "0001-a", "0002-b"]), err)


class RespawnScope(unittest.TestCase):
    """`respawn_scope` on plain values: the tagged tasks, then the kept entries naming a pending task not among them."""

    def test_order_and_filters(self):
        sys.path.insert(0, str(PLANE_ROOT / "scripts" / "observability"))
        import team  # noqa: PLC0415
        got = team.respawn_scope(["0001-a"], ["0005-e", "0001", "0002-b", "0003-c"], ["0001-a", "0002-b", "0005-e"],
                                 tasklog.in_scope)
        self.assertEqual(got, ["0001-a", "0005-e", "0002-b"])  # 0001 is tagged already, 0003-c is not pending
        self.assertEqual(team.respawn_scope([], ["0002-b"], ["0002-b"], tasklog.in_scope), ["0002-b"])


if __name__ == "__main__":
    unittest.main()
