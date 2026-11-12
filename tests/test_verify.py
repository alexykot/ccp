"""The verifier's record and the runner's merge gate (SPEC §15.3), and the re-verify packet."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from ccp import cli, verify
from tests.helpers import Product

ROOT = Path(__file__).resolve().parents[1]
HEAD_A = "a" * 40
HEAD_B = "b" * 40


class MergeGate(unittest.TestCase):
    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def binding(self) -> None:
        (self.q / "project.yaml").write_text("project_id: demo\n")

    def verdict(self, task: str, **fields: object) -> None:
        body = {
            "task_id": task, "project_id": "demo", "verdict": "approve",
            "checked_at": "2026-10-16T12:00:00Z",
            "checks": [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it"}],
            **fields,
        }
        d = self.q / "verification"
        d.mkdir(exist_ok=True)
        (d / f"{task}.json").write_text(json.dumps(body))

    def check(self, task: str, head: str):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "check", task, "--head", head])
        return code, out.getvalue(), err.getvalue()

    def test_schema_names_head_sha_and_does_not_require_it_globally(self):
        schema = json.loads((ROOT / "contracts/verification.schema.json").read_text())
        self.assertIn("head_sha", schema["properties"])
        self.assertEqual(schema["properties"]["head_sha"]["pattern"], "^[0-9a-fA-F]{7,40}$")
        self.assertNotIn("head_sha", schema["required"])

    def test_an_approve_matches_and_a_different_head_is_refused(self):
        self.binding()
        self.verdict("0001-a", head_sha=HEAD_A)
        code, out, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 0, out + err)
        self.assertTrue(json.loads(out)["ok"])
        code, out, err = self.check("0001-a", HEAD_B)
        self.assertEqual(code, 1)
        self.assertIn("differs", err)
        self.assertFalse(json.loads(out)["ok"])

    def test_a_non_approve_is_refused(self):
        self.binding()
        self.verdict("0001-a", verdict="reject", head_sha=HEAD_A)
        code, _, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 1)
        self.assertIn("not approve", err)

    def test_a_missing_head_sha_passes_check_and_a_different_one_is_refused(self):
        self.binding()
        self.verdict("0001-a")
        code, out, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 0, out + err)
        self.verdict("0001-a", head_sha=HEAD_A)
        code, _, err = self.check("0001-a", HEAD_B)
        self.assertEqual(code, 1)
        self.assertIn("differs", err)

    def test_a_short_sha_matches_the_full_one(self):
        self.binding()
        self.verdict("0001-a", head_sha=HEAD_A[:7])
        code, out, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 0, out + err)
        self.verdict("0001-a", head_sha=HEAD_A)
        code, out, err = self.check("0001-a", HEAD_A[:7])
        self.assertEqual(code, 0, out + err)

    def test_check_reads_a_newer_record_with_a_key_this_version_does_not_know(self):
        self.binding()
        self.verdict("0001-a", head_sha=HEAD_A, schema_version=verify.RECORD_VERSION + 1, reviewed_at=HEAD_B)
        code, out, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 0, out + err)
        self.verdict("0001-a", head_sha=HEAD_A, schema_version=verify.RECORD_VERSION + 1, verdict="maybe")
        code, _, err = self.check("0001-a", HEAD_A)
        self.assertEqual(code, 1)
        self.assertIn("is not one of approve, reject", err)

    def test_reverify_example_matches_the_schema_and_the_briefs_name_it(self):
        schema = json.loads((ROOT / "contracts/reverify_packet.schema.json").read_text())
        example = json.loads((ROOT / "contracts/reverify_packet.example.json").read_text())
        for key in schema["required"]:
            self.assertIn(key, example)
        for key in schema["properties"]["packet"]["required"]:
            self.assertIn(key, example["packet"])
        self.assertRegex(example["head_sha"], schema["properties"]["head_sha"]["pattern"])
        self.assertEqual(example["kind"], "reverify")
        self.assertEqual(example["reason"], "fix-up")
        self.assertGreaterEqual(len(example["fixups"]), 1)
        verifier = (ROOT / "plugin/agents/delivery-verifier.md").read_text()
        self.assertIn("head_sha", verifier)
        self.assertIn("contracts/reverify_packet.schema.json", verifier)
        self.assertIn("contracts/reverify_packet.example.json", verifier)


# The record contract's keys at each schema version. A version's keys never change once released: a
# key added at any depth goes in under a new version, with verify.RECORD_VERSION raised to it and the
# new version's digest pinned, so an older reader knows the record is newer and passes over the key.
KEYS_AT = {1: frozenset({
    "access_mode", "checked_at", "checks", "checks.dod_check_id", "checks.evidence", "checks.notes",
    "checks.operator_step", "checks.pass", "checks.produced_by", "checks.ran", "checks.rests_on",
    "evidence_pack_path", "findings", "gate", "gate.ci_run", "gate.runs", "gate.runs.cached",
    "gate.runs.cold", "gate.runs.command", "gate.runs.exit_code", "gate.runs.modules_cached",
    "gate.runs.modules_ran", "gate.runs.ran", "gate.runs.seconds", "gate.runs.suite_id",
    "gate.runs.tests_run", "gate.runs.tests_skipped", "head_sha", "merge_requested", "project_id",
    "proof_urls", "proof_urls.local", "proof_urls.verifier", "schema_version", "task_id", "verdict",
    "verifier_seat",
})}
PINNED = {1: "3e6bb65b819a72b59897e56e02c640e9d064894502b01f687fb2024e9216b483"}


def record_keys(schema: dict, at: str = "") -> set:
    """Every key the record's contract names, dotted, at any depth."""
    out = set()
    for k, v in schema.get("properties", {}).items():
        out |= {at + k} | record_keys(v, f"{at}{k}.")
    return out | (record_keys(schema["items"], at) if "items" in schema else set())


def keys_digest(keys) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()


def version_errors(keys: set, version: int, keys_at: dict, pinned: dict) -> list[str]:
    """Why the contract's `keys` at record `version` break the version rule: the versions run 1 to
    `version`, each version's keys match its pinned digest (a released version never changes), and
    the contract's keys are exactly the current version's."""
    errs = []
    if sorted(keys_at) != list(range(1, version + 1)):
        errs.append(f"versions {sorted(keys_at)} do not run 1 to {version}")
    for v, ks in keys_at.items():
        if pinned.get(v) != keys_digest(ks):
            errs.append(f"version {v}'s keys are not the ones pinned for it: a new key raises the version")
    if set(keys) != set(keys_at.get(version, ())):
        errs.append(f"the contract's keys differ from version {version}'s: "
                    f"{sorted(set(keys) ^ set(keys_at.get(version, ())))}")
    return errs


def approve(task: str = "0001-a", **fields: object) -> dict:
    """A verdict that passes every rule: what the verifier writes for an approve at HEAD_A."""
    return {
        "task_id": task, "project_id": "demo", "verdict": "approve", "head_sha": HEAD_A,
        "checks": [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}],
        "gate": {"runs": [{"command": "scripts/unit.sh", "exit_code": 0, "tests_run": 412,
                           "tests_skipped": 0, "seconds": 88.5},
                          {"command": "scripts/lint.sh", "exit_code": 0}]},
        **fields,
    }


class Record(unittest.TestCase):
    """`ccp verify record`: the schema and the rules it cannot hold, before anything is written."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\n")
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def record(self, body: object):
        src = self.q / "in.json"
        src.write_text(json.dumps(body))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "record", str(src)])
        return code, out.getvalue(), err.getvalue()

    def written(self) -> Path:
        return self.q / "verification" / "0001-a.json"

    def test_ci_run_needs_ci_in_the_binding(self):
        rec = approve()
        rec["gate"]["ci_run"] = "https://github.com/x/y/actions/runs/1"
        code, _, err = self.record(rec)
        self.assertNotEqual(code, 0)
        self.assertIn("gate.ci_run", err)
        self.assertFalse(self.written().exists())
        (self.q / "project.yaml").write_text("project_id: demo\nci: github-actions\n")
        code, out, err = self.record(rec)
        self.assertEqual(code, 0, out + err)

    def test_an_invalid_record_is_refused_and_nothing_is_written(self):
        # PROC-23: 9 of 84 record versions failed the contract.
        for bad, needle in (
            (approve(verdict="changes_requested"), "is not one of approve, reject"),
            (approve(base_sha=HEAD_B), "unexpected key base_sha"),
            (approve(findings=[{"text": "x"}]), "record.findings[0]"),
            (approve(checks=[{"dod_check_id": "cmd-01", "pass": True}]), "missing evidence"),
            (approve(head_sha=None), "is not string"),
        ):
            code, _, err = self.record(bad)
            self.assertEqual(code, 1, err)
            self.assertIn(needle, err)
            self.assertIn("nothing written", err)
            self.assertFalse(self.written().exists())

    def test_checked_at_is_stamped_when_absent_and_never_later_than_now(self):
        code, out, err = self.record(approve())
        self.assertEqual(code, 0, err)
        rec = json.loads(self.written().read_text())
        stamped = datetime.fromisoformat(rec["checked_at"].replace("Z", "+00:00"))
        self.assertLess(abs((datetime.now(timezone.utc) - stamped).total_seconds()), 5)
        later = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        code, _, err = self.record(approve(checked_at=later))
        self.assertEqual(code, 1)
        self.assertIn("is later than now", err)

    def test_a_check_not_run_is_neither_a_pass_nor_a_fail(self):
        unrun = {"dod_check_id": "data-01", "ran": False, "pass": None, "rests_on": "the operator's paste, 15:49",
                 "evidence": "not run by the verifier: the live store is the Mac's", "produced_by": "operator"}
        code, _, err = self.record(approve(checks=[unrun]))
        self.assertEqual(code, 0, err)
        code, _, err = self.record(approve(checks=[{**unrun, "pass": True}]))
        self.assertEqual(code, 1)
        self.assertIn("neither a pass nor a fail", err)
        code, _, err = self.record(approve(checks=[{k: v for k, v in unrun.items() if k != "rests_on"}]))
        self.assertIn("rests_on", err)
        code, _, err = self.record(approve(checks=[{**unrun, "ran": True}]))
        self.assertIn("pass is null", err)

    def test_a_check_with_no_producer_still_has_its_operator_step_checked(self):
        gates = self.q / "escalations" / "0001-a"
        gates.mkdir(parents=True)
        (gates / "1.json").write_text(json.dumps({"task_id": "0001-a", "escalation_id": "0001-a-1", "class": "other",
                                                  "status": "closed", "decision": "approved"}))
        ruled = {"dod_check_id": "data-01", "ran": False, "pass": None, "rests_on": "0001-a-1",
                 "evidence": "closed by the lead's ruling"}
        code, _, err = self.record(approve(checks=[ruled]))
        self.assertEqual(code, 0, err)
        self.written().unlink()
        for step, needle in (("0001-a-9", "no gate file"), ("0001-a-1", "not an operator step")):
            code, _, err = self.record(approve(checks=[{**ruled, "operator_step": step}]))
            self.assertEqual(code, 1, step)
            self.assertIn(f"checks[0] (data-01): operator_step {step!r}", err)
            self.assertIn(needle, err)
            self.assertFalse(self.written().exists())

    def test_an_approve_with_a_failed_check_is_refused(self):
        code, _, err = self.record(approve(checks=[{"dod_check_id": "cmd-01", "pass": False, "evidence": "exit 1",
                                                    "produced_by": "verifier"}]))
        self.assertEqual(code, 1)
        self.assertIn("an approve with a failed check (cmd-01)", err)
        code, _, err = self.record(approve(verdict="reject",
                                           checks=[{"dod_check_id": "cmd-01", "pass": False, "evidence": "exit 1",
                                                     "produced_by": "verifier"}]))
        self.assertEqual(code, 0, err)

    def test_a_record_may_carry_every_access_mode_a_binding_declares(self):
        # S4: a binding saying verifier_access.mode local-cli, which the record contract refused.
        binding = json.loads((ROOT / "contracts/project.schema.json").read_text())
        for mode in binding["properties"]["verifier_access"]["properties"]["mode"]["enum"]:
            code, _, err = self.record(approve(access_mode=mode))
            self.assertEqual(code, 0, (mode, err))

    def test_record_refuses_the_approve_merge_ok_would_refuse(self):
        # S5: an approve with no head or gate was written, then refused at merge time.
        for drop, needle in (("head_sha", "names no head_sha"), ("gate", "carries no gate")):
            body = approve()
            del body[drop]
            code, _, err = self.record(body)
            self.assertEqual(code, 1, drop)
            self.assertIn(needle, err)
        reject = approve(verdict="reject")
        del reject["head_sha"], reject["gate"]
        code, _, err = self.record(reject)
        self.assertEqual(code, 0, err)

    def test_the_example_record_passes_and_the_verifier_brief_names_it(self):
        example = json.loads((ROOT / "contracts/verification.example.json").read_text())
        self.assertEqual(example["schema_version"], verify.RECORD_VERSION)
        code, _, err = self.record({**example, "task_id": "0001-a", "project_id": "demo"})
        self.assertEqual(code, 0, err)
        self.assertIn("contracts/verification.example.json",
                      (ROOT / "plugin/agents/delivery-verifier.md").read_text())

    def test_record_stamps_its_own_version_and_holds_the_record_to_its_own_contract(self):
        code, _, err = self.record(approve(schema_version=verify.RECORD_VERSION + 5))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.written().read_text())["schema_version"], verify.RECORD_VERSION)
        self.written().unlink()
        # A record claiming a newer version is still written under this one: an unknown key is refused.
        code, _, err = self.record(approve(schema_version=verify.RECORD_VERSION + 1, reviewed_at=HEAD_B))
        self.assertEqual(code, 1)
        self.assertIn("unexpected key reviewed_at", err)
        self.assertFalse(self.written().exists())

    def test_a_key_added_to_the_record_raises_its_version(self):
        schema = json.loads((ROOT / "contracts/verification.schema.json").read_text())
        self.assertEqual(version_errors(record_keys(schema), verify.RECORD_VERSION, KEYS_AT, PINNED), [])

    def test_the_version_rule_refuses_a_key_added_without_a_raise(self):
        schema = json.loads((ROOT / "contracts/verification.schema.json").read_text())
        schema["properties"]["checks"]["items"]["properties"]["reviewed_at"] = {"type": "string"}
        added = record_keys(schema)
        # Added to the schema alone, or to the current version's keys as well: either is refused.
        self.assertTrue(version_errors(added, 1, KEYS_AT, PINNED))
        self.assertTrue(version_errors(added, 1, {1: added}, PINNED))
        # Raised: a new version holding the key, pinned, with RECORD_VERSION at it.
        at2 = {**KEYS_AT, 2: added}
        pinned2 = {**PINNED, 2: keys_digest(added)}
        self.assertEqual(version_errors(added, 2, at2, pinned2), [])
        self.assertTrue(version_errors(added, 1, at2, pinned2))
        self.assertTrue(version_errors(added, 2, at2, PINNED))

    def test_an_approve_needs_head_sha_and_the_validator_fails_closed_on_an_unknown_keyword(self):
        body = approve()
        del body["head_sha"]
        code, _, err = self.record(body)
        self.assertEqual(code, 1)
        self.assertIn("names no head_sha", err)
        self.assertEqual(verify.schema_errors(1, {"oneOf": []}),
                         ["record: the schema uses oneOf, which ccp verify cannot check"])


class MergeOk(unittest.TestCase):
    """`ccp verify merge-ok`: a committed approval at the PR's head (PROC-12)."""

    def setUp(self):
        self.p = Product()
        self._q = tempfile.TemporaryDirectory()
        self.q = Path(self._q.name)
        (self.q / "project.yaml").write_text("project_id: demo\nhosting: claude-team\n")
        self.pr = {"number": 7, "state": "OPEN", "headRefOid": HEAD_A, "mergedAt": None}
        gh = self.q / "fake-gh"
        gh.write_text("#!/bin/sh\ncat \"$(dirname \"$0\")/pr.json\"\n")
        gh.chmod(0o755)
        self.env = mock.patch.dict(os.environ, {"QUEUE_ROOT": str(self.q), "CCP_GH_BIN": str(gh)})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.p.cleanup()
        self._q.cleanup()

    def put(self, rec: dict, name: str = "0001-a") -> Path:
        d = self.q / "verification"
        d.mkdir(exist_ok=True)
        path = d / f"{name}.json"
        path.write_text(json.dumps(rec))
        return path

    def ok(self, *extra: str):
        (self.q / "pr.json").write_text(json.dumps(self.pr))
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(self.p.root), "verify", "merge-ok", "7", *extra])
        return code, json.loads(out.getvalue()) if out.getvalue() else {}, err.getvalue()

    def test_an_approval_at_the_open_head_with_its_gate_may_merge(self):
        self.put(approve(checked_at=now_iso()))
        code, body, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertTrue(body["ok"])
        self.assertEqual((body["head_sha"], body["recorded"], body["unrun_checks"]), (HEAD_A, "written", []))
        self.assertEqual([r["command"] for r in body["gate_runs"]], ["scripts/unit.sh", "scripts/lint.sh"])
        # A short approved sha still merges on the PR's full head (gh needs a full OID).
        self.put(approve(head_sha=HEAD_A[:7], checked_at=now_iso()))
        code, body, err = self.ok("--task", "0001-a")
        self.assertEqual((code, body["match_head_commit"]), (0, HEAD_A), err)

    def test_each_reason_not_to_merge_is_named(self):
        cases = (
            ({"headRefOid": HEAD_B}, {}, "is not the approved head"),
            ({}, {"gate": None}, "carries no gate"),
            ({}, {"gate": {"runs": [{"command": "scripts/lint.sh", "exit_code": 1}]}},
             "gate run 'scripts/lint.sh' exited 1"),
            ({}, {"verdict": "reject"}, "the verdict is 'reject', not approve"),
            ({}, {"head_sha": None}, "names no head_sha"),
            ({}, {"project_id": "other"}, "not demo"),
            ({}, {"task_id": "0009-z"}, "the record's task_id is '0009-z', not 0001-a"),
            ({}, {"checks": [{"dod_check_id": "cmd-01", "pass": False, "evidence": "exit 1"}]},
             "an approve with a failed check (cmd-01)"),
            ({"state": "MERGED", "mergedAt": "2026-10-16T21:33:30Z"}, {},
             "PR 7 is merged at 2026-10-16T21:33:30Z; the approval was recorded after it"),
        )
        for pr, rec, needle in cases:
            self.pr = {"number": 7, "state": "OPEN", "headRefOid": HEAD_A, "mergedAt": None, **pr}
            body = {k: v for k, v in approve(checked_at=now_iso(), **rec).items() if v is not None}
            self.put(body)
            code, out, err = self.ok("--task", "0001-a")
            self.assertEqual(code, 1, (needle, err))
            self.assertIn(needle, err)
            self.assertFalse(out["ok"])

    def test_a_pr_without_a_task_reads_its_pr_record(self):
        code, _, err = self.ok()
        self.assertEqual(code, 1)
        self.assertIn("no verification record verification/pr-7.json", err)
        self.put(approve(task="pr-7", checked_at=now_iso()), name="pr-7")
        code, _, err = self.ok()
        self.assertEqual(code, 0, err)

    def test_in_a_git_checkout_the_record_must_be_committed_after_its_checked_at(self):
        def git(*a: str) -> subprocess.CompletedProcess:
            return subprocess.run(["git", "-C", str(self.q), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                                  check=True, capture_output=True, text=True)
        git("init", "-q")
        self.put(approve(checked_at=now_iso()))
        code, _, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 1)
        self.assertIn("is not committed as it stands", err)
        # S9: a committed reject overwritten by an approve that is not committed.
        self.put(approve(verdict="reject", checked_at=now_iso()))
        git("add", "verification/0001-a.json")
        git("commit", "-qm", "reject")
        self.put(approve(checked_at=now_iso()))
        code, _, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 1)
        self.assertIn("is not committed as it stands", err)
        git("add", "verification/0001-a.json")
        git("commit", "-qm", "verdict")
        code, body, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertTrue(body["recorded"].startswith("commit "))
        # A rounded-up checked_at, later than the commit that recorded it (pr-158: 18:18:12 vs 18:20:00).
        later = (datetime.now(timezone.utc) + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.put(approve(checked_at=later))
        git("commit", "-qam", "verdict, rounded")
        code, _, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 1)
        self.assertIn("is after the record was recorded", err)

    def newer(self, **fields: object) -> dict:
        """An approve written by a newer version, carrying a key at each depth this contract lacks."""
        rec = approve(checked_at=now_iso(), schema_version=verify.RECORD_VERSION + 1, reviewed_at=HEAD_B, **fields)
        rec["checks"][0]["seat_run"] = "r-1"
        rec["gate"]["runs"][0]["lane"] = "gate"
        rec["gate"]["shard"] = 1
        return rec

    def test_a_record_from_a_newer_version_with_keys_this_one_does_not_know_may_merge(self):
        self.put(self.newer())
        code, body, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 0, err)
        self.assertEqual(body["match_head_commit"], HEAD_A)
        # The same keys from a version no newer than this one, or from a record with none, are refused.
        for version in (verify.RECORD_VERSION, None):
            rec = self.newer()
            if version is None:
                del rec["schema_version"]
            else:
                rec["schema_version"] = version
            self.put(rec)
            code, _, err = self.ok("--task", "0001-a")
            self.assertEqual(code, 1, version)
            for key in ("reviewed_at", "checks[0]: unexpected key seat_run", "gate.runs[0]: unexpected key lane",
                        "record.gate: unexpected key shard"):
                self.assertIn(key, err)

    def test_a_newer_record_still_holds_every_key_this_version_knows(self):
        cases = (
            ({"verdict": "approved"}, "is not one of approve, reject"),
            ({"head_sha": "not-a-sha"}, "does not match"),
            ({"checks": [{"dod_check_id": "cmd-01", "pass": "yes", "evidence": "ran it", "produced_by": "verifier"}]},
             "record.checks[0].pass"),
            ({"checks": [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}],
              "gate": {"runs": [{"command": "scripts/unit.sh", "exit_code": "0"}]}}, "record.gate.runs[0].exit_code"),
            ({"checks": [{"dod_check_id": "cmd-01", "pass": True, "produced_by": "verifier"}]}, "missing evidence"),
        )
        for fields, needle in cases:
            self.put(self.newer(**fields))
            code, _, err = self.ok("--task", "0001-a")
            self.assertEqual(code, 1, (needle, err))
            self.assertIn(needle, err)
        # A version that is not an integer is a bad value, and the record is held to this contract.
        rec = self.newer()
        rec["schema_version"] = str(verify.RECORD_VERSION + 1)
        self.put(rec)
        code, _, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 1)
        self.assertIn("record.schema_version", err)
        self.assertIn("unexpected key reviewed_at", err)

    def test_no_gh_is_a_configuration_error(self):
        with mock.patch.dict(os.environ, {"CCP_GH_BIN": str(self.q / "no-such-gh")}):
            code, _, err = self.ok("--task", "0001-a")
        self.assertEqual(code, 2)
        self.assertIn("is not installed", err)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


if __name__ == "__main__":
    unittest.main()
