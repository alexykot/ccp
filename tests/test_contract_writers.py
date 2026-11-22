"""`contracts/` holds what the plane writes and reads: a record its writer writes validates against its
schema, and where a seat or a machine command writes it, an example record validates and is accepted by the
reader. The checker is `ccp.schema.schema_errors`."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ccp import architect, usage, verify, wt
from ccp.schema import schema_errors
from tests.helpers import Product, binding
from tests.test_toolkit import PLANE
from tests.test_wt import WtFixture

sys.path.insert(0, str(PLANE / "scripts/observability"))
import spec_maintainer  # noqa: E402


def contract(name: str) -> dict:
    return json.loads((PLANE / "contracts" / name).read_text())


class WorktreeContract(WtFixture, unittest.TestCase):
    def test_every_record_ccp_wt_create_writes_validates(self):
        head = self.head()
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        for args in (("--kind", "rev", "--task", "0002", "--sha", head),
                     ("--kind", "ver", "--task", "0002", "--sha", head),
                     ("--kind", "mut", "--task", "0002", "--sha", head),
                     ("--kind", "mac", "--task", "0002", "--sha", head),
                     ("--kind", "rev", "--task", "0002", "--sha", head, "--shallow", "--name", "rev-0002-2"),
                     ("--kind", "ver", "--baseline")):
            code, _, _, err = self.wt("create", *args)
            self.assertEqual(code, 0, err)
        written = sorted((self.q / "worktrees").glob("*.json"))
        self.assertGreaterEqual(len(written), 7)  # the claim's impl worktree, then those six
        schema = contract("worktree.schema.json")
        for f in written:
            self.assertEqual(schema_errors(json.loads(f.read_text()), schema), [], f.name)

    def test_the_base_record_validates_while_its_command_runs(self):
        # a base worktree is removed with its command, so the record is read from inside the command
        code, _, out, err = self.wt("create", "--kind", "base", "--task", "0002", "--sha", self.head(), "--",
                                    "sh", "-c", f'cat "{self.q}"/worktrees/base-*.json')
        self.assertEqual(code, 0, out + err)
        record, _ = json.JSONDecoder().raw_decode(out[out.index("{"):])  # the command's output, then ccp's result
        self.assertEqual(record["kind"], "base")
        self.assertIn("head", record)
        self.assertEqual(schema_errors(record, contract("worktree.schema.json")), [])

    def test_the_record_validates_after_ccp_wt_up_and_down(self):
        urls = """printf '[{"name": "api", "url": "http://localhost:31%s/"}, {"name": "app", "url": "http://localhost:32%s/"}]' {nnnn} {nnnn}"""
        schema = contract("worktree.schema.json")

        def record(name: str) -> dict:
            rec = json.loads((self.q / "worktrees" / f"{name}.json").read_text())
            self.assertEqual(schema_errors(rec, schema), [], name)
            return rec

        self.plane(env={"up": "touch up.flag", "down": "true", "urls": urls})
        code, made, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head())
        self.assertEqual(code, 0, err)
        name = made["name"]
        code, _, _, err = self.wt("up", name)
        self.assertEqual(code, 0, err)
        up = record(name)
        self.assertEqual(up["state"], "up")
        self.assertIn("up_at", up)
        self.assertEqual(len(up["urls"]), 2)
        code, _, _, err = self.wt("down", name)
        self.assertEqual(code, 0, err)
        down = record(name)
        self.assertEqual((down["state"], down["urls"]), ("down", []))
        self.plane(env={"up": "exit 4"})
        code, made, _, err = self.wt("create", "--kind", "ver", "--task", "0002", "--sha", self.head(),
                                     "--name", "ver-0002-2")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.wt("up", made["name"])[0], 1)
        self.assertEqual(record(made["name"])["state"], "down")

    def test_the_kind_enum_is_the_kinds_ccp_wt_creates(self):
        self.assertEqual(contract("worktree.schema.json")["properties"]["kind"]["enum"], list(wt.KINDS))


class QueueWriters(unittest.TestCase):
    """The spec-maintainer script and the team script write into a queue; each record validates."""

    def setUp(self):
        self.prod = Product()
        self.addCleanup(self.prod.cleanup)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.q = Path(tmp.name)
        (self.q / "project.yaml").write_text(binding(product_root=self.prod.root))
        (self.q / "work.json").write_text(json.dumps({"project_id": "demo", "status": "idle"}))
        (self.q / "tasks").mkdir()
        (self.q / "tasks/0001-a.json").write_text(json.dumps({"task_id": "0001-a", "waiting_on": None}))
        self.env = {**os.environ, "QUEUE_ROOT": str(self.q)}
        self.env.pop("PROJECT_YAML", None)

    def script(self, name: str, *argv: str) -> dict:
        r = subprocess.run(["bash", str(PLANE / "scripts" / name), *argv], capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_a_question_the_spec_maintainer_writer_writes_validates(self):
        qid = self.script("spec-maintainer-ask.sh", "raise", "--raised-by", "task-runner", "--task-id", "0001-a",
                          "--text", "Which?", "--inconsistency", "task vs SPEC", "--spec-refs", "S1",
                          "--tried", "read both")["question_id"]
        written = json.loads((self.q / "questions" / f"{qid}.json").read_text())
        self.assertEqual(written["status"], "open")
        self.assertEqual(schema_errors(written, contract("question.schema.json")), [])

    def test_a_question_the_writer_sent_to_the_lead_validates(self):
        qid = self.script("spec-maintainer-ask.sh", "raise", "--raised-by", "task-verifier", "--task-id", "0001-a",
                          "--text", "Which?", "--inconsistency", "x", "--spec-refs", "S1,S2", "--tried", "y",
                          "--blocks", "0001-a")["question_id"]
        self.script("spec-maintainer-ask.sh", "process", qid)
        written = json.loads((self.q / "questions" / f"{qid}.json").read_text())
        self.assertIn("lead_messaged_at", written)
        self.assertEqual(schema_errors(written, contract("question.schema.json")), [])

    def test_a_gate_the_team_script_writes_validates_open_and_decided(self):
        eid = self.script("team.sh", "gate", "open", "--task-id", "0001-a", "--class", "operator",
                          "--brief", "db init")["escalation_id"]
        path = self.q / "escalations" / "0001-a" / "1.json"
        schema = contract("escalation.schema.json")
        self.assertEqual(schema_errors(json.loads(path.read_text()), schema), [])
        self.script("team.sh", "gate", "decide", eid, "--decision", "approved", "--resolution", "ok",
                    "--authority", "SPEC §17.9")
        decided = json.loads(path.read_text())
        self.assertEqual(decided["decision"], "approved")
        self.assertEqual(schema_errors(decided, schema), [])


class Examples(unittest.TestCase):
    def test_the_escalation_example_validates_and_the_verify_read_finds_it_approved(self):
        rec = contract("escalation.example.json")
        self.assertEqual(schema_errors(rec, contract("escalation.schema.json")), [])
        with tempfile.TemporaryDirectory() as d:
            q = Path(d)
            (q / "escalations" / rec["task_id"]).mkdir(parents=True)
            (q / "escalations" / rec["task_id"] / "1.json").write_text(json.dumps(rec))
            self.assertIsNone(verify._operator_step_refusal(q, rec["task_id"], rec["escalation_id"]))

    def test_the_allowance_example_validates_and_the_reader_parses_its_windows(self):
        rec = contract("allowance.example.json")
        self.assertEqual(schema_errors(rec, contract("allowance.schema.json")), [])
        wins, ok, code, retry = usage._run(f"cat '{PLANE / 'contracts/allowance.example.json'}'")
        self.assertEqual((ok, code, retry), (True, 0, 60))
        self.assertEqual([(w["name"], w["pct"]) for w in wins],
                         [(w["name"], w["pct"]) for w in rec["windows"]])

    def test_the_legacy_and_the_retry_only_readings_validate_and_a_malformed_one_does_not(self):
        schema = contract("allowance.schema.json")
        self.assertEqual(schema_errors({"five_hour": {"utilization": 3, "resets_at": "2026-01-05T14:00:00Z"},
                                        "retry_after_s": 5}, schema), [])
        self.assertEqual(schema_errors({"retry_after_s": 30}, schema), [])
        self.assertTrue(schema_errors({"windows": [{"pct": 3}]}, schema))
        self.assertTrue(schema_errors({"five_hour": 3}, schema))
        self.assertTrue(schema_errors({"retry_after_s": 30, "windows": 1}, schema))

    def test_the_question_answer_example_validates_and_the_spec_maintainer_accepts_it(self):
        rec = contract("question_answer.example.json")
        self.assertEqual(schema_errors(rec, contract("question_answer.schema.json")), [])
        self.assertEqual(spec_maintainer.validate_answer(rec, rec["question_id"]), [])

    def test_the_triage_example_validates_and_validate_triage_returns_no_errors_for_it(self):
        rec = contract("architecture_review_triage.example.json")
        self.assertEqual(schema_errors(rec, contract("architecture_review_triage.schema.json")), [])
        self.assertEqual(architect.ar.validate_triage(rec, rec["review_id"]), [])


class Checker(unittest.TestCase):
    """The keywords the live contracts use beyond the verdict's: each one holds a value to it."""

    def test_const_holds_a_value_and_its_type(self):
        self.assertEqual(schema_errors(1, {"const": 1}), [])
        self.assertTrue(schema_errors(2, {"const": 1}))
        self.assertTrue(schema_errors(True, {"const": 1}))
        self.assertEqual(schema_errors(1.0, {"const": 1}), [])  # one number, as JSON Schema reads it
        self.assertTrue(schema_errors("1", {"const": 1}))

    def test_allof_anyof_oneof_and_not_combine_sub_schemas(self):
        a, b = {"required": ["a"]}, {"required": ["b"]}
        self.assertEqual(schema_errors({"a": 1, "b": 1}, {"allOf": [a, b]}), [])
        self.assertEqual(schema_errors({"a": 1}, {"allOf": [a, b]}), ["record: missing b"])
        self.assertEqual(schema_errors({"a": 1}, {"anyOf": [a, b]}), [])
        self.assertTrue(schema_errors({}, {"anyOf": [a, b]}))
        self.assertEqual(schema_errors({"a": 1}, {"oneOf": [a, b]}), [])
        self.assertTrue(schema_errors({"a": 1, "b": 1}, {"oneOf": [a, b]}))  # two hold
        self.assertTrue(schema_errors({}, {"oneOf": [a, b]}))  # none holds
        self.assertEqual(schema_errors({}, {"not": a}), [])
        self.assertTrue(schema_errors({"a": 1}, {"not": a}))

    def test_if_then_holds_the_then_only_when_the_if_holds(self):
        schema = {"if": {"properties": {"k": {"const": "x"}}, "required": ["k"]}, "then": {"required": ["y"]}}
        self.assertEqual(schema_errors({"k": "z"}, schema), [])
        self.assertEqual(schema_errors({"k": "x", "y": 1}, schema), [])
        self.assertEqual(schema_errors({"k": "x"}, schema), ["record: missing y"])

    def test_not_and_if_are_judged_strictly_whatever_newer_says(self):
        closed = {"properties": {"a": {}}, "additionalProperties": False}
        # `newer` passes over a key a schema does not name, which would make `closed` match {"a", "z"}
        self.assertEqual(schema_errors({"a": 1, "z": 1}, {"not": closed}, newer=True), [])
        self.assertTrue(schema_errors({"a": 1}, {"not": closed}, newer=True))
        schema = {"if": closed, "then": {"required": ["b"]}}
        self.assertEqual(schema_errors({"a": 1, "z": 1}, schema, newer=True), [])
        self.assertEqual(schema_errors({"a": 1}, schema, newer=True), ["record: missing b"])

    def test_max_properties_and_a_schema_for_the_other_keys(self):
        self.assertTrue(schema_errors({"a": 1, "b": 2}, {"maxProperties": 1}))
        self.assertEqual(schema_errors({"a": 1}, {"maxProperties": 1}), [])
        schema = {"properties": {"n": {"type": "integer"}}, "additionalProperties": {"type": "string"}}
        self.assertEqual(schema_errors({"n": 1, "o": "s"}, schema), [])
        self.assertEqual(schema_errors({"n": 1, "o": 2}, schema), ["record.o: 2 is not string"])

    def test_a_keyword_it_does_not_know_inside_a_sub_schema_is_never_read_as_a_mismatch(self):
        for key in ("anyOf", "oneOf"):
            self.assertEqual(schema_errors(1, {key: [{"dependentRequired": {}}, {"type": "integer"}]}),
                             ["record: the schema uses dependentRequired, which ccp verify cannot check"])
        self.assertEqual(schema_errors(1, {"not": {"dependentRequired": {}}}),
                         ["record: the schema uses dependentRequired, which ccp verify cannot check"])
        self.assertEqual(schema_errors(1, {"if": {"dependentRequired": {}}, "then": {}}),
                         ["record: the schema uses dependentRequired, which ccp verify cannot check"])


if __name__ == "__main__":
    unittest.main()
