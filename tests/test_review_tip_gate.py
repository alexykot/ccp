"""SPEC §15.2: `ccp prompt review` refuses (exit 4, nothing opened) a head behind the integration tip only when
merging the tip into it would conflict in a file outside the task log and `merge.behind_tip_ignore`; a head
behind by a clean merge is reviewed, and a tip or head that cannot be fetched is a warning. SPEC §13.2: the
implement and fix prompts end with the catch-up merge, before the suite."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from ccp import gitmerge
from tests.test_toolkit import ToolkitFixture, git


class ReviewTipGate(ToolkitFixture, unittest.TestCase):
    PLANE_JSON = {**ToolkitFixture.PLANE_JSON, "merge": {"behind_tip_ignore": ["docs/notes"]}}

    def push_to_main(self, files: dict[str, str], msg: str = "tip commit") -> None:
        git(self.runner, "fetch", "-q", "origin")
        git(self.runner, "checkout", "-q", "--detach", "origin/main")
        for rel, text in files.items():
            p = self.runner / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            git(self.runner, "add", rel)
        git(self.runner, "commit", "-q", "-m", msg)
        git(self.runner, "push", "-q", "origin", "HEAD:main")

    def pushed_head(self, files: dict[str, str] | None = None) -> str:
        """Claim 0002, commit `files` (default: feature.txt) on its branch and push it: the PR head."""
        self.ccp("tasks", "claim", "0002")
        wt = self.main / ".rt" / "impl-0002"
        for rel, text in (files or {"feature.txt": "built\n"}).items():
            (wt / rel).parent.mkdir(parents=True, exist_ok=True)
            (wt / rel).write_text(text)
            git(wt, "add", rel)
        git(wt, "commit", "-q", "-m", "Task 0002: build it")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        return git(wt, "rev-parse", "HEAD")

    def review(self, head: str):
        return self.ccp("prompt", "review", "0002", "--pr", "7", "--head", head)

    def opened(self) -> bool:
        return (self.q / "runs/0002-second/review.json").exists()

    def test_a_head_whose_merge_of_the_tip_would_conflict_is_refused_before_anything_opens(self):
        head = self.pushed_head()
        self.push_to_main({"feature.txt": "someone else's\n"})
        code, _, out, err = self.review(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("feature.txt", err)
        self.assertIn(f"ccp prompt merge 0002-second --pr 7 --head {head[:7]}", err)
        self.assertFalse(self.opened())
        self.assertEqual(list(self.q.glob("prompts/0002-second/review*")), [])

    def test_the_refusal_names_five_files_then_a_count(self):
        names = [f"f{i}.txt" for i in range(7)]
        head = self.pushed_head({n: "mine\n" for n in names})
        self.push_to_main({n: "theirs\n" for n in names})
        code, _, out, err = self.review(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn(", ".join(names[:5]), err)
        self.assertNotIn(names[5], err)
        self.assertIn("and 2 more", err)

    def test_a_head_behind_by_a_clean_merge_is_reviewed(self):
        head = self.pushed_head()
        self.push_to_main({"other.py": "x = 1\n"})
        code, body, out, err = self.review(head)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.opened())
        self.assertFalse(any("behind_tip" in w for w in body.get("warnings", [])), body)

    def test_a_conflict_only_in_the_task_file_is_reviewed(self):
        task = "docs/delivery/tasks/0002-second.md"
        self.ccp("tasks", "claim", "0002")
        wt = self.main / ".rt" / "impl-0002"
        (wt / task).write_text((wt / task).read_text().replace("title: Second", "title: Second, mine"))
        git(wt, "commit", "-qam", "Task 0002: retitle")
        git(wt, "push", "-q", "-u", "origin", "task/0002-second")
        head = git(wt, "rev-parse", "HEAD")
        # the tip also carries other code, so the head is behind it: only then is the merge judged
        self.push_to_main({task: (self.runner / task).read_text().replace("title: Second", "title: Second, theirs"),
                           "other.py": "x = 1\n"})
        code, body, out, err = self.review(head)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.opened())
        self.assertFalse(any("behind_tip" in w for w in body.get("warnings", [])), body)

    def test_a_conflict_only_under_a_declared_path_is_reviewed(self):
        head = self.pushed_head({"docs/notes/today.md": "mine\n"})
        self.push_to_main({"docs/notes/today.md": "theirs\n", "other.py": "x = 1\n"})  # other.py: behind, so judged
        code, _, out, err = self.review(head)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(self.opened())

    def test_a_conflict_beside_a_declared_path_is_still_refused(self):
        head = self.pushed_head({"docs/notes/today.md": "mine\n", "docs/notesmore.md": "mine\n"})
        self.push_to_main({"docs/notes/today.md": "theirs\n", "docs/notesmore.md": "theirs\n"})
        code, _, out, err = self.review(head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("docs/notesmore.md", err)
        self.assertNotIn("docs/notes/today.md", err)

    def test_a_head_not_behind_the_tip_is_reviewed(self):
        head = self.pushed_head()
        code, body, out, err = self.review(head)
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("warnings", body)

    def test_a_head_that_cannot_be_fetched_opens_the_review_with_a_warning(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.review("abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(body["warnings"]), 1, body)
        self.assertTrue(body["warnings"][0].startswith("behind_tip not checked"), body)
        self.assertTrue(self.opened())

    def test_a_merge_git_cannot_run_is_a_warning_and_the_review_opens(self):
        head = self.pushed_head()
        self.push_to_main({"feature.txt": "someone else's\n"})
        with mock.patch("ccp.gitmerge.probe", return_value=gitmerge.Probe("", returncode=129, failed=True)):
            code, body, out, err = self.review(head)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(body["warnings"]), 1, body)
        self.assertTrue(body["warnings"][0].startswith("behind_tip not checked"), body)
        self.assertIn("git 2.38", body["warnings"][0])
        self.assertTrue(self.opened())

    def test_a_verify_of_a_head_behind_by_a_clean_merge_is_still_refused(self):
        head = self.pushed_head()
        self.push_to_main({"other.py": "x = 1\n"})
        code, _, out, err = self.ccp("prompt", "verify", "0002", "--pr", "7", "--head", head)
        self.assertEqual(code, 4, out + err)
        self.assertIn("behind_tip", err)

    def test_the_implement_and_fix_prompts_catch_up_before_the_suite(self):
        self.ccp("tasks", "claim", "0002")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertLess(text.index("is binding"), text.index("git merge origin/main"))
        self.assertLess(text.index("git merge origin/main"), text.index("ccp suite run --lane"))
        self.assertEqual(text.count("git merge origin/main"), 1)
        code, body, out, err = self.review("abc1234")
        self.assertEqual(code, 0, out + err)
        code, _, out, err = self.report(
            "0002-second/review",
            "Outcome: done\nSeverity: BLOCKER=0 MAJOR=1 MINOR=0 NIT=0\n## Spec beyond intent\nnone\n## Friction\nnone\n")
        self.assertEqual(code, 0, out + err)
        code, body, out, err = self.ccp("prompt", "fix", "0002", "--pr", "7", "--head", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertLess(text.index("Fix what these found"), text.index("git merge origin/main"))
        self.assertLess(text.index("git merge origin/main"), text.index("ccp suite run --lane"))
        self.assertEqual(text.count("git merge origin/main"), 1)


if __name__ == "__main__":
    unittest.main()
