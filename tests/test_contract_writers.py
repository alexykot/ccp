"""`contracts/` holds what the plane writes and reads: a record its writer writes validates against its
schema, and where a seat or a machine command writes it, an example record validates and is accepted by the
reader. The checker is `ccp.schema.schema_errors`."""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from ccp import adr, architect, cli, config, schema, tasklog, usage, verify, wt
from ccp.queue import lib
from ccp.schema import schema_errors
from tests.helpers import Product, binding
from tests.test_architect import FINDING, Harness
from tests.test_toolkit import PLANE, ToolkitFixture, git
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

    def test_the_task_file_example_validates_and_ccp_tasks_check_accepts_it(self):
        text = (PLANE / "contracts/task_file.example.md").read_text()
        fm = tasklog.frontmatter(text)
        self.assertEqual(schema_errors(fm, contract("task_file.schema.json")), [])
        self.assertEqual(fm["status"], "pending")
        prod = Product()
        self.addCleanup(prod.cleanup)
        prod.write(f"docs/delivery/tasks/{fm['task_id']}.md", text)
        prod.index()
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(prod.root), "tasks", "check"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())


class InitContracts(unittest.TestCase):
    def test_the_plane_json_binding_and_machine_file_ccp_init_writes_validate(self):
        ccp = [str(PLANE / "bin/ccp")]
        env = {k: v for k, v in os.environ.items() if k not in ("QUEUE_ROOT", "PROJECT_YAML")}
        made = subprocess.run([*ccp, "sandbox", "create", "--", "--project-id", "demo", "--language", "python"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(made.returncode, 0, made.stderr)
        sandbox = json.loads(made.stdout)
        self.addCleanup(subprocess.run, [*ccp, "sandbox", "remove", str(Path(sandbox["root"]).parent)],
                        capture_output=True, env=env)
        product = Path(sandbox["root"])
        binding_path = Path(sandbox["binding"])
        plane_json = json.loads((product / "docs/delivery/plane.json").read_text())
        self.assertEqual(plane_json["project_id"], "demo")
        self.assertEqual(schema_errors(plane_json, contract("plane_config.schema.json")), [])
        record = lib.read_binding(binding_path.read_text())
        self.assertEqual(record["project_id"], "demo")
        self.assertEqual(schema_errors(record, contract("project.schema.json")), [])
        machine = json.loads((binding_path.parent / "machine.json").read_text())
        self.assertEqual(schema_errors(machine, contract("machine.schema.json")), [])


class QueueRecordContracts(ToolkitFixture, unittest.TestCase):
    def test_the_pr_record_prompt_audit_and_events_a_claimed_task_writes_validate(self):
        nogh = mock.patch.dict(os.environ, {"CCP_GH_BIN": str(Path(self._tmp.name) / "no-such-gh")})
        nogh.start()
        self.addCleanup(nogh.stop)
        self.assertEqual(self.ccp("tasks", "claim", "0002")[0], 0)
        wt_dir = self.main / config.WORKTREES_DIR / "impl-0002"
        (wt_dir / "feature.txt").write_text("built\n")
        git(wt_dir, "add", "feature.txt")
        git(wt_dir, "commit", "-q", "-m", "Task 0002: build it")
        git(wt_dir, "push", "-q", "-u", "origin", "task/0002-second")
        code, _, out, err = self.ccp("pr", "open", "--branch", "task/0002-second", "--title", "Task 0002: Second",
                                     "--body-file", "-", stdin="Task: 0002-second\n")
        self.assertEqual((code, out.strip()), (0, "1"), err)
        self.assertEqual(schema_errors(self.pr_record("1"), contract("pr_record.schema.json")), [])
        code, body, out, err = self.ccp("prompt", "implement", "0002", "--base", "abc1234")
        self.assertEqual(code, 0, out + err)
        audit = json.loads((self.q / body["prompt_ref"]).read_text())
        self.assertEqual(schema_errors(audit, contract("prompt_audit.schema.json")), [])
        schema_ = contract("observability_event.schema.json")
        events = (self.q / "observability" / "events.jsonl").read_text().splitlines()
        self.assertGreaterEqual(len(events), 2)
        for line in events:
            self.assertEqual(schema_errors(json.loads(line), schema_), [], line)


class ReportContracts(Harness):
    def test_the_report_ccp_architect_run_writes_validates(self):
        self.stub_report([FINDING], rule_changes=[{"rule": "E9", "action": "add", "text": "One registry.",
                                                   "check": "command"}])
        code, res, err = self.dpj("architect", "run", "--force")
        self.assertEqual(res["outcome"], "reported", err)
        written = json.loads(Path(res["report"]).read_text())
        self.assertEqual(len(written["findings"]), 1)
        self.assertEqual(schema_errors(written, contract("architect_report.schema.json")), [])


class GateResultContract(unittest.TestCase):
    def test_the_result_gate_result_py_writes_validates(self):
        log = "\n".join([
            "FAIL: test_x (tests.test_a.A.test_x)", "Ran 3 tests in 0.1s", "FAILED (failures=1, skipped=1)",
            "gate module tests.test_a: FAILED (failures=1), 1.5 s, 3 tests", "gate module tests.test_b: cached, 0.0 s, 2 tests",
            "gate module tests.test_c: ok, 2.0 s, 4 tests", ""])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "gate.log"
            f.write_text(log)
            r = subprocess.run([sys.executable, str(PLANE / "scripts/gate_result.py"), str(f), "7"],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        result = json.loads(r.stdout)
        self.assertEqual((result["failed"], result["skipped"], result["cached"], result["seconds"]), (1, 1, 1, 7))
        self.assertEqual(schema_errors(result, contract("suite_result.schema.json")), [])


class FrontmatterContracts(unittest.TestCase):
    def test_the_frontmatter_ccp_adr_new_writes_validates(self):
        prod = Product()
        self.addCleanup(prod.cleanup)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--root", str(prod.root), "adr", "new", "A decision"])
        self.assertEqual(code, 0, out.getvalue() + err.getvalue())
        files = sorted(prod.root.glob("docs/adr/*.md"))
        self.assertEqual(len(files), 1, out.getvalue())
        block, _ = adr.split(files[0].read_text())
        fm = adr.parse(block)
        self.assertEqual(fm["title"], "A decision")
        self.assertEqual(schema_errors(fm, contract("adr.schema.json")), [])


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

    def test_defs_and_a_local_ref(self):
        schema_ = {"$defs": {"n": {"type": "integer", "minimum": 1}, "o": {"properties": {"k": {"$ref": "#/$defs/n"}}}},
                   "properties": {"a": {"$ref": "#/$defs/n"}, "b": {"$ref": "#/$defs/o"}, "c": {"type": "array",
                                  "items": {"$ref": "#/$defs/n"}}}}
        self.assertEqual(schema_errors({"a": 1, "b": {"k": 2}, "c": [1, 2]}, schema_), [])
        self.assertEqual(schema_errors({"a": "x"}, schema_), ["record.a: \"x\" is not integer"])
        self.assertEqual(schema_errors({"a": 0}, schema_), ["record.a: 0 is below 1"])
        self.assertEqual(schema_errors({"b": {"k": 0}}, schema_), ["record.b.k: 0 is below 1"])
        self.assertEqual(schema_errors({"c": [1, 0]}, schema_), ["record.c[1]: 0 is below 1"])
        # the $ref's sibling keywords are checked too, and `$defs` is never judged as a schema of the record
        self.assertEqual(schema_errors(5, {"$defs": {"n": {"type": "integer"}}, "$ref": "#/$defs/n", "maximum": 3}),
                         ["record: 5 is above 3"])
        self.assertEqual(schema_errors(1, {"$defs": {"x": {"dependentRequired": {}}}, "type": "integer"}), [])
        # a combined sub-schema reaches the root's `$defs` too
        self.assertTrue(schema_errors("x", {"$defs": {"n": {"type": "integer"}}, "anyOf": [{"$ref": "#/$defs/n"}]}))
        for ref in ("other.json#/$defs/n", "#/properties/a", "#/$defs/missing"):
            self.assertEqual(schema_errors(1, {"$defs": {"n": {}}, "$ref": ref}),
                             [f"record: the schema's $ref {json.dumps(ref)} is not a local #/$defs/<name>, {schema._UNCHECKABLE}"],
                             ref)
        self.assertEqual(schema_errors(1, {"$ref": "#/$defs/n"})[0][:8], "record: ")
        # an explicit root is the schema the ref resolves in
        self.assertEqual(schema_errors(0, {"$ref": "#/$defs/n"}, root={"$defs": {"n": {"minimum": 1}}}),
                         ["record: 0 is below 1"])

    def test_max_items_and_unique_items(self):
        self.assertEqual(schema_errors([1, 2], {"maxItems": 2}), [])
        self.assertEqual(schema_errors([1, 2, 3], {"maxItems": 2}), ["record: more than 2 item(s)"])
        self.assertEqual(schema_errors([1, 2, "1", True], {"uniqueItems": True}), [])  # equal only by value and kind
        self.assertEqual(schema_errors([1, 2, 1.0], {"uniqueItems": True}), ["record: items are not unique"])
        self.assertEqual(schema_errors(["a", "b", "a"], {"uniqueItems": True}), ["record: items are not unique"])
        self.assertEqual(schema_errors([{"a": 1}, {"a": 1}], {"uniqueItems": True}), ["record: items are not unique"])
        self.assertEqual(schema_errors(["a", "a"], {"uniqueItems": False}), [])
        self.assertEqual(schema_errors(["a", "a"], {}), [])

    def test_maximum_and_exclusive_minimum(self):
        self.assertEqual(schema_errors(100, {"maximum": 100}), [])
        self.assertEqual(schema_errors(100.5, {"maximum": 100}), ["record: 100.5 is above 100"])
        self.assertEqual(schema_errors(0.1, {"exclusiveMinimum": 0}), [])
        self.assertEqual(schema_errors(0, {"exclusiveMinimum": 0}), ["record: 0 is not above 0"])
        self.assertEqual(schema_errors(-1, {"exclusiveMinimum": 0}), ["record: -1 is not above 0"])
        self.assertEqual(schema_errors("x", {"maximum": 1, "exclusiveMinimum": 5}), [])  # a number keyword holds a number only
        self.assertEqual(schema_errors(True, {"maximum": 0}), [])  # a boolean is not a number

    def test_property_names_holds_each_key(self):
        schema_ = {"propertyNames": {"pattern": "^[a-z]+$"}, "additionalProperties": {"type": "integer"}}
        self.assertEqual(schema_errors({"ab": 1, "cd": 2}, schema_), [])
        self.assertEqual(schema_errors({"ab": 1, "B1": 2}, schema_),
                         ["record.B1: 'B1' does not match ^[a-z]+$"])
        self.assertEqual(schema_errors("x", {"propertyNames": {"maxLength": 1}}), [])
        self.assertEqual(schema_errors({}, schema_), [])

    def test_deprecated_only_describes(self):
        self.assertEqual(schema_errors(1, {"type": "integer", "deprecated": True}), [])
        self.assertEqual(schema_errors("x", {"type": "integer", "deprecated": True}), ["record: \"x\" is not integer"])

    def test_every_contract_uses_only_keywords_the_checker_knows(self):
        known = schema._ANNOTATIONS | schema._KEYWORDS
        maps = ("properties", "$defs")
        singles = ("items", "additionalProperties", "propertyNames", "not", "if", "then")
        lists = ("allOf", "anyOf", "oneOf")
        unknown: list[str] = []

        def walk(node, where: str, name: str) -> None:
            if not isinstance(node, dict):
                return
            unknown.extend(f"{name} {where}: {k}" for k in sorted(set(node) - known))
            for key in maps:
                for k, sub in (node.get(key) if isinstance(node.get(key), dict) else {}).items():
                    walk(sub, f"{where}/{key}/{k}", name)
            for key in singles:
                walk(node.get(key), f"{where}/{key}", name)
            for key in lists:
                for i, sub in enumerate(node.get(key) or []):
                    walk(sub, f"{where}/{key}/{i}", name)

        files = sorted((PLANE / "contracts").glob("*.schema.json"))
        self.assertGreaterEqual(len(files), 20)
        for f in files:
            walk(json.loads(f.read_text()), "#", f.name)
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
