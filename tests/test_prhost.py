"""The PR-host module (ADR-0040, E19): the GitHub adapter's `gh` calls and JSON, tested once, here.
Every other module sees a PR as `PrFacts`."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ccp import prhost
from tests.helpers import Product

HEAD = "a" * 40
MERGE = "b" * 40

# A stand-in for gh: logs its argv (and CCP_GH_BIN), prints FAKE_OUT, writes FAKE_ERR, exits FAKE_RC.
FAKE = """#!/bin/sh
echo "$@" >> "$FAKE_LOG"
echo "bin=$CCP_GH_BIN" >> "$FAKE_LOG.env"
printf '%s' "$FAKE_OUT"
printf '%s' "$FAKE_ERR" >&2
exit "${FAKE_RC:-0}"
"""


def gh_json(**fields: object) -> str:
    return json.dumps({"number": 7, "state": "OPEN", "headRefOid": HEAD, "headRefName": "task/0001-a",
                       "mergedAt": None, "mergeCommit": None, **fields})


class HostCase(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self.addCleanup(self.p.cleanup)
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        t = Path(self._t.name)
        self.gh = t / "fake-gh"
        self.gh.write_text(FAKE)
        self.gh.chmod(0o755)
        self.log = t / "log"
        self.say({})

    def say(self, env: dict[str, str]) -> None:
        patch = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(self.gh), "FAKE_LOG": str(self.log),
                                             "FAKE_OUT": "", "FAKE_ERR": "", "FAKE_RC": "0", **env})
        patch.start()
        self.addCleanup(patch.stop)

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def cfg(self, **blocks: object):
        self.p.cleanup()
        self.p = Product(blocks)
        self.addCleanup(self.p.cleanup)
        return self.p.cfg


class View(HostCase):
    def test_a_pr_is_read_as_plain_facts(self):
        self.say({"FAKE_OUT": gh_json()})
        facts = prhost.view(self.p.cfg, "7")
        self.assertEqual(facts, prhost.PrFacts(number=7, state="open", head=HEAD, branch="task/0001-a"))
        self.assertEqual(self.calls(), ["pr view 7 --json number,state,headRefOid,headRefName,mergeCommit,mergedAt"])

    def test_a_merged_pr_carries_its_time_and_merge_commit(self):
        self.say({"FAKE_OUT": gh_json(state="MERGED", mergedAt="2026-10-16T21:33:30Z", mergeCommit={"oid": MERGE})})
        facts = prhost.view(self.p.cfg, "7")
        self.assertEqual((facts.state, facts.merged_at, facts.merge_commit), ("merged", "2026-10-16T21:33:30Z", MERGE))

    def test_every_state_the_host_names_is_one_of_the_normalised_states(self):
        for word, state in (("OPEN", "open"), ("MERGED", "merged"), ("CLOSED", "closed")):
            self.say({"FAKE_OUT": gh_json(state=word)})
            self.assertEqual(prhost.view(self.p.cfg, "7").state, state)
            self.assertIn(state, prhost.STATES)

    def test_facts_the_host_leaves_out_are_empty(self):
        self.say({"FAKE_OUT": json.dumps({"state": "OPEN", "headRefOid": HEAD})})
        facts = prhost.view(self.p.cfg, "9")
        self.assertEqual((facts.number, facts.branch, facts.merged_at, facts.merge_commit), (9, "", None, ""))

    def test_a_state_the_host_does_not_name_is_a_host_error(self):
        for out in (json.dumps({"headRefOid": HEAD}), gh_json(state="DRAFT")):
            self.say({"FAKE_OUT": out})
            with self.assertRaises(prhost.HostError):
                prhost.view(self.p.cfg, "7")

    def test_a_failing_read_is_a_host_error_carrying_the_hosts_words(self):
        self.say({"FAKE_RC": "1", "FAKE_ERR": "no such PR\n"})
        with self.assertRaises(prhost.HostError) as cm:
            prhost.view(self.p.cfg, "7")
        self.assertNotIsInstance(cm.exception, prhost.HostUnavailable)
        self.assertIsInstance(cm.exception, prhost.HostReadFailed)
        self.assertEqual(cm.exception.detail, "no such PR")

    def test_output_that_is_not_a_json_object_is_a_host_error(self):
        for out in ("not json", "[1, 2]"):
            self.say({"FAKE_OUT": out})
            with self.assertRaises(prhost.HostError) as cm:
                prhost.view(self.p.cfg, "7")
            self.assertIn("no JSON for PR 7", str(cm.exception))

    def test_a_missing_binary_is_host_unavailable(self):
        self.say({"CCP_GH_BIN": str(Path(self._t.name) / "no-such-gh")})
        with self.assertRaises(prhost.HostUnavailable) as cm:
            prhost.view(self.p.cfg, "7")
        self.assertIn("is not installed", str(cm.exception))
        self.assertIsInstance(cm.exception, prhost.HostError)


class Body(HostCase):
    def test_the_body_is_read_alone(self):
        self.say({"FAKE_OUT": json.dumps({"body": "Task 0001-a: it."})})
        self.assertEqual(prhost.body(self.p.cfg, "7"), "Task 0001-a: it.")
        self.assertEqual(self.calls(), ["pr view 7 --json body"])

    def test_a_body_the_host_cannot_give_is_a_host_error(self):
        for env in ({"FAKE_RC": "1", "FAKE_ERR": "boom"}, {"FAKE_OUT": "{}"}, {"FAKE_OUT": "nope"}):
            self.say(env)
            with self.assertRaises(prhost.HostError):
                prhost.body(self.p.cfg, "7")

    def test_a_missing_binary_is_host_unavailable(self):
        self.say({"CCP_GH_BIN": str(Path(self._t.name) / "no-such-gh")})
        with self.assertRaises(prhost.HostUnavailable):
            prhost.body(self.p.cfg, "7")


class Merge(HostCase):
    def test_the_default_merge_is_squash_pinned_to_the_head(self):
        r = prhost.merge(self.p.cfg, "12", "abc123", "0002-second")
        self.assertEqual(r, prhost.MergeResult(True, ""))
        self.assertEqual(self.calls(), ["pr merge 12 --squash --match-head-commit abc123"])

    def test_a_refused_merge_says_why_and_names_a_conflict(self):
        self.say({"FAKE_RC": "1", "FAKE_ERR": "head moved"})
        r = prhost.merge(self.p.cfg, "12", "abc123", "0002-second")
        self.assertEqual((r.ok, r.message, r.conflict), (False, "head moved", False))
        for words in ("Pull request has a conflict", "Pull request is not mergeable"):
            self.say({"FAKE_RC": "1", "FAKE_ERR": words})
            self.assertTrue(prhost.merge(self.p.cfg, "12", "abc123", "0002-second").conflict, words)

    def test_merge_command_replaces_the_argv_and_is_a_template(self):
        cfg = self.cfg(merge={"command": "echo {pr} {head_sha} {task_id} '{\"literal\": 1}' > merged.txt"})
        r = prhost.merge(cfg, "12", "abc123", "0002-second")
        self.assertTrue(r.ok)
        self.assertEqual((cfg.root / "merged.txt").read_text().split(),
                         ["12", "abc123", "0002-second", '{"literal":', "1}"])
        self.assertEqual(self.calls(), [])  # the host's own merge did not run

    def test_merge_command_runs_with_the_host_cli_named_in_its_env(self):
        cfg = self.cfg(merge={"command": "echo $CCP_GH_BIN {head_sha} > bin.txt"})
        prhost.merge(cfg, "12", "abc123", "0002-second")
        self.assertEqual((cfg.root / "bin.txt").read_text().split(), [str(self.gh), "abc123"])
        with mock.patch.dict(os.environ):  # the variable unset: the child is told the default CLI
            del os.environ["CCP_GH_BIN"]
            prhost.merge(cfg, "12", "abc123", "0002-second")
        self.assertEqual((cfg.root / "bin.txt").read_text().split(), ["gh", "abc123"])

    def test_a_failing_merge_command_is_a_refused_merge(self):
        cfg = self.cfg(merge={"command": "echo no >&2; exit 3 # {head_sha}"})
        r = prhost.merge(cfg, "12", "abc123", "0002-second")
        self.assertEqual((r.ok, r.message), (False, "no"))

    def test_a_missing_binary_is_host_unavailable(self):
        self.say({"CCP_GH_BIN": str(Path(self._t.name) / "no-such-gh")})
        with self.assertRaises(prhost.HostUnavailable):
            prhost.merge(self.p.cfg, "12", "abc123", "0002-second")


class Confirm(HostCase):
    def test_confirm_gives_the_facts_of_the_merged_pr(self):
        self.say({"FAKE_OUT": gh_json(state="MERGED", mergeCommit={"oid": MERGE})})
        facts = prhost.confirm(self.p.cfg, "7")
        self.assertEqual((facts.state, facts.merge_commit), ("merged", MERGE))
        self.say({"FAKE_OUT": gh_json()})
        self.assertEqual(prhost.confirm(self.p.cfg, "7").state, "open")  # the caller refuses what is not merged


if __name__ == "__main__":
    unittest.main()
