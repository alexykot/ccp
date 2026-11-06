"""`ccp prompt` (SPEC §13.2, §13): the runner's note up to 4000 characters, `--note-file`, and the
product's `prompts.worker_env` rendered into the run's env file and named in the prompt."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

from ccp import config, prompt as prompt_mod
from tests.test_toolkit import ToolkitFixture, git


class NoteAndEnv(ToolkitFixture, unittest.TestCase):
    def claim(self):
        code, _, out, err = self.ccp("tasks", "claim", "0002")
        self.assertEqual(code, 0, out + err)

    def test_a_long_note_from_a_file_renders_like_note(self):
        self.claim()
        f = Path(self._tmp.name) / "note.md"
        text = "Rulings for this run:\n1. keep the old flag\n2. " + "x" * 3000
        f.write_text(text + "\n")
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note-file", str(f))
        self.assertEqual(code, 0, out + err)
        self.assertIn("Note from the runner for this run: " + text + "\n", Path(body["prompt_path"]).read_text())
        run = json.loads((self.q / "runs/0002-second/implement.json").read_text())
        self.assertEqual(run["note"], text)

    def test_the_cap_both_flags_and_a_secret_are_refused(self):
        self.claim()
        f = Path(self._tmp.name) / "note.md"
        f.write_text("y" * (prompt_mod.NOTE_MAX + 1))
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note-file", str(f))
        self.assertEqual(code, 2)
        self.assertIn(f"--note-file is {prompt_mod.NOTE_MAX + 1} characters; the limit is 4000", err)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note", "y" * 4001)
        self.assertIn("--note is 4001 characters", err)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note", "a", "--note-file", str(f))
        self.assertEqual(code, 2)
        self.assertIn("not both", err)
        f.write_text("use ghp_" + "A" * 36)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note-file", str(f))
        self.assertEqual(code, 2)
        self.assertIn("looks like it holds a secret", err)
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note-file", str(f) + ".missing")
        self.assertEqual(code, 2)
        self.assertFalse((self.q / "runs/0002-second/implement.json").exists())
        code, _, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--note", "z" * 4000)
        self.assertEqual(code, 0, out + err)

    def test_workers_message_the_runner_by_its_bound_name(self):
        """§10.2: after a rotation the runner may be `runner-2`; the briefs follow work.json."""
        self.claim()
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("Send the runner teammate, `runner`, a message", text)
        w = json.loads((self.q / "work.json").read_text())
        (self.q / "work.json").write_text(json.dumps({**w, "runner": "runner-2"}))
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234", "--supersede")
        self.assertEqual(code, 0, out + err)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn("Send it to `runner-2` with SendMessage", text)
        self.assertIn("no messages to anyone except the runner teammate, `runner-2`.", text)
        self.assertIn("Send the runner teammate, `runner-2`, a message", text)
        self.assertNotIn("`runner`", text)

    def test_no_worker_env_no_file_and_no_line(self):
        self.claim()
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        self.assertIsNone(body["env_file"])
        self.assertNotIn("This run's environment", Path(body["prompt_path"]).read_text())

    def _with_env(self, env: dict) -> None:
        pj = dict(self.PLANE_JSON, prompts={"fragment": "docs/delivery/WORKERS.md", "worker_env": env})
        (self.runner / "docs/delivery/plane.json").write_text(json.dumps(pj))

    def test_worker_env_is_rendered_into_a_file_the_prompt_names(self):
        self._with_env({"SCRATCH_ENV": "{{main_checkout}}/.env", "RUN_TAG": "{{nnnn}}-{{phase}} it's {{run_id}}"})
        self.claim()
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        env = Path(body["env_file"])
        self.assertEqual(env.name, "implement-env.sh")
        self.assertEqual(env.parent, Path(body["prompt_path"]).parent)
        text = Path(body["prompt_path"]).read_text()
        self.assertIn(f"This run's environment is in `{env}`: `SCRATCH_ENV={self.main}/.env`", text)
        self.assertIn(f"start every command with `. {env} && `", text)
        r = subprocess.run(["sh", "-c", f'. "{env}" && printf "%s|%s" "$SCRATCH_ENV" "$RUN_TAG"'],
                           capture_output=True, text=True)
        self.assertEqual(r.stdout, f"{self.main}/.env|0002-implement it's 0002-second/implement")

    def test_worker_env_for_a_reviewer_names_its_own_worktree(self):
        self._with_env({"WT": "{{worktree}}"})
        self.claim()
        code, body, out, err = self.ccp("prompt", "review", "0002", "--pr", "7", "--head", "a" * 40)
        self.assertEqual(code, 0, out + err)
        self.assertIn(f"export WT={self.main}/.rt/rev-0002", Path(body["env_file"]).read_text())

    def test_worker_env_config_is_checked(self):
        for env, want in (({"1BAD": "x"}, "not a shell variable name"), ({"A": "{{nope}}"}, "names nope"),
                          ({"A": "a\nb"}, "one-line string"), ([], "must be an object")):
            self._with_env(env)
            with self.assertRaises(config.ConfigError) as cm:
                config.load(self.runner)
            self.assertIn(want, str(cm.exception))

    def test_a_secret_looking_value_is_refused(self):
        self._with_env({"TOKEN": "ghp_" + "B" * 36})
        self.claim()
        code, _, _, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 2)
        self.assertIn("looks like a secret", err)


if __name__ == "__main__":
    unittest.main()
