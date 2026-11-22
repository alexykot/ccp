"""The quality tab's base fixture (an architect-on product), its hostile text and page stubs. A fixture module: it
holds no tests."""
from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import TASK
from tests.toolkit_fixture import ToolkitFixture, git


RULES = """# Engineering

## Budgets

- **E1** Source files stay short.
  check: budget
- **E2** One registry.
  check: pass
- **E3** The import boundary holds.
  check: command
"""
HOSTILE = "x <!--<script> y </script><img src=x onerror=alert(1)> &amp;"


class Base(ToolkitFixture):
    def arch_on(self, **extra):
        cfg = json.loads((self.main / "docs/delivery/plane.json").read_text())
        self.write("docs/delivery/plane.json", json.dumps({**cfg, "architect": {
            "shape_from_task": "0001", "rules_doc": "docs/ENGINEERING.md", "every_n_tasks": 4, "notes_due": 3,
            "budgets": [{"id": "E1", "glob": "src/*.py", "max_lines": 3}],
            "checks": [{"id": "E3", "cmd": "false"}], **extra}}))
        self.write("docs/ENGINEERING.md", RULES)
        self.write("src/small.py", "a = 1\n")
        self.write("src/big.py", "a = 1\n" * 5)
        self.write("docs/delivery/tasks/0003-tidy.md", TASK.format(tid="0003-tidy", title="Tidy the registry", status="pending",
                                                                  deps="", ver="*Append-only.*")
                   .replace('spec_refs: ["S1"]', 'kind: refactor\nrule_refs: ["E2"]'))
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "architect on")

    def a_pass(self, rid="ar-20261020T100000Z-abcd", status="triaged", **rec):
        st = {"schema_version": 1, "reviews": {rid: {"mode": "pass", "status": status, "started_at": "2026-10-20T10:00:00Z",
                                                     "findings": 3, "rule_changes": 1, "done": ["0001-first"],
                                                     "tasks_created": ["0003-tidy", "0001-first"], **rec}},
              "last": {"review_id": rid, "started_at": "2026-10-20T10:00:00Z", "done": ["0001-first"]}}
        (self.q / "architect.json").write_text(json.dumps(st))
        (self.q / "reviews").mkdir(exist_ok=True)
        (self.q / "reviews" / f"{rid}.json").write_text(json.dumps({"findings": [
            {"id": "F01", "severity": "high", "category": "duplication"},
            {"id": "F02", "severity": "low", "category": "test-cost"},
            {"id": "F03", "severity": "low", "category": "test-cost"}]}))
        (self.q / "reviews" / f"{rid}.triage.json").write_text(json.dumps({
            "dispositions": [{"finding": "F01", "disposition": "task"}, {"finding": "F02", "disposition": "task"},
                             {"finding": "F03", "disposition": "defer"}],
            "rule_changes": [{"rule": "E2", "action": "amend", "disposition": "applied", "reason": "r"}]}))
        return rid

    def note(self, at, by, text, task="0002-second", source="worker"):
        p = self.q / "health" / "notes.jsonl"
        p.parent.mkdir(exist_ok=True)
        with p.open("a") as fh:
            fh.write(json.dumps({"at": at, "task_id": task, "by": by, "source": source, "text": text}) + "\n")

    def build(self):
        code, body, out, err = self.ccp("board", "build", root=self.main)
        self.assertEqual(code, 0, out + err)
        return json.loads(Path(body["board"]).read_text()), Path(body["page"]).read_text()


def _hostile(v, key=None):
    """Every string gets the hostile suffix (a prefix would break slices and ids); count maps (all
    values numbers) get hostile keys too, since the page prints those keys."""
    if isinstance(v, str):
        return v + HOSTILE
    if isinstance(v, list):
        return [_hostile(x) for x in v]
    if isinstance(v, dict):
        counts = bool(v) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values())
        return {(k + HOSTILE if counts else k): _hostile(x, k) for k, x in v.items()}
    return v


STUB = """
const out = [];
const el = () => ({style: {}, dataset: {}, addEventListener() {}, append(x) { out.push(x); }, setAttribute() {}});
globalThis.document = {createElement: () => { const t = {set innerHTML(h) { this.content = h; }}; return t; },
  getElementById: () => el(), querySelectorAll: () => [], documentElement: el()};
globalThis.localStorage = {getItem: () => null, setItem() {}};
globalThis.matchMedia = () => ({matches: false});
globalThis.innerWidth = 800; globalThis.innerHeight = 800;
globalThis.setTimeout = () => 0;
"""
