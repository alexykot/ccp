"""Build throwaway product checkouts for the `ccp` tests."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ccp import board, config, otel, runs, tasklog

TASK = """---
task_id: {tid}
title: {title}
status: {status}   # pending | done
depends_on: [{deps}]
spec_refs: ["S1"]
created: 2026-09-30
updated: 2026-09-30
---

# Task: {tid}

## Intent

Something true for the user.

## Context (not verified)

- background

## Scope

- **In:** it

## dod_checks

- id: `cmd-01`
  story: As an operator, I run it.
  steps:
    1. run
  expect: exit 0

## Implementation notes

*Append-only, newest last.*

## Verification notes

{ver}
"""


# The settings the shared fixtures' tests rely on, named so a change of a default shows here: no language
# (so no package-doc checks and no test-output patterns of a pack), the architect seat off (it is on without a
# block, SPEC §19.11: a test of the seat gives its own `architect` block), a gate lane that passes and one task
# in flight under the `paths` schedule.
BASE_PLANE: dict = {
    "project_id": "demo",
    "language": "none",
    "architect": False,
    "suite": {"lanes": {"gate": ["true"]}},
    "parallel": {"max_in_flight": 1, "schedule": "paths"},
}


def machine_file(case, **keys) -> Path:
    """SPEC §8.3: the machine file of a fenced bindings directory (`CCP_BINDINGS_DIR`, a temp directory the test
    case removes) holding `keys`, written over what an earlier call in the same case wrote. Returns its path."""
    d = getattr(case, "_machine_dir", None)
    if d is None:
        tmp = tempfile.TemporaryDirectory()
        patch = mock.patch.dict(os.environ, {"CCP_BINDINGS_DIR": tmp.name})
        patch.start()
        case.addCleanup(tmp.cleanup)
        case.addCleanup(patch.stop)
        case._machine_dir = d = Path(tmp.name)
    path = d / "machine.json"
    path.write_text(json.dumps({k: v for k, v in keys.items() if v is not None}))
    return path


def binding(**keys) -> str:
    """SPEC §8.3: the text of a binding (`projects/<id>.yaml`, or a queue's `project.yaml`): `project_id: demo`
    first, then each of `keys` in the order given as `key: value`; a dict value is a block, indented two spaces;
    `None` leaves a key out (`project_id=None`: no id). For a test that needs a binding, not one of the binding
    reader's or `ccp init`'s own format."""
    lines: list[str] = []

    def put(items: dict, indent: str) -> None:
        for k, v in items.items():
            if isinstance(v, dict):
                lines.append(f"{indent}{k}:")
                put(v, indent + "  ")
            elif v is not None:
                lines.append(f"{indent}{k}: {v}")
    put({"project_id": "demo", **keys}, "")
    return "\n".join(lines) + "\n"


def merged_plane(cfg: dict | None = None) -> dict:
    """BASE_PLANE with `cfg` over it, block by block: a block `cfg` gives replaces the base's block."""
    return {**copy.deepcopy(BASE_PLANE), **copy.deepcopy(cfg or {})}


class Product:
    """A temp product root with a plane.json and helpers to add tasks and files.

    `cfg` goes over BASE_PLANE block by block; `bare=True` writes only `project_id` and `cfg`, for a test
    whose subject is a missing block."""

    def __init__(self, cfg: dict | None = None, bare: bool = False):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs/delivery/tasks").mkdir(parents=True)
        plane = {"project_id": "demo", **(cfg or {})} if bare else merged_plane(cfg)
        self.write("docs/delivery/plane.json", json.dumps(plane))

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, text: str) -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def task(self, tid: str, status: str = "pending", deps: list[str] | None = None,
             title: str = "A task", ver: str | None = None, body: str | None = None) -> Path:
        if ver is None:
            ver = "- 2026-09-30 — `cmd-01` pass — ran it" if status == "done" else "*Append-only.*"
        text = body if body is not None else TASK.format(
            tid=tid, title=title, status=status, deps=", ".join(f'"{d}"' for d in deps or []), ver=ver)
        return self.write(f"docs/delivery/tasks/{tid}.md", text)

    @property
    def cfg(self) -> config.Config:
        return config.load(self.root)

    def index(self) -> None:
        tasklog.write_index(self.cfg)


# What a done report of each phase carries besides `Outcome:`, its own lines and `## Friction` (SPEC §13.4): a
# review's `## Spec beyond intent`, and a round that pushes a head its `## Tests for new behaviour`.
DONE_SECTIONS = {"review": ("## Spec beyond intent", "none"),
                 **{p: ("## Tests for new behaviour", "none: the fixture's round adds no behaviour")
                    for p in runs.CHANGE_PHASES}}


def done_report(phase: str, *lines: str, friction: tuple[str, ...] = ("none",)) -> str:
    """A report of `phase` with `Outcome: done` for `ccp report`: `lines` (a round's `PR:` and `Head:`, a review's
    `Severity:`, a `Suite:` line, a `## Follow-ups` section), the section the phase needs when done, and
    `## Friction` with the lines `friction`."""
    return "\n".join(["Outcome: done", *lines, *DONE_SECTIONS.get(phase, ()), "## Friction", *friction, ""])


T0 = 1_800_000_000 * 10**9  # 2027-01-15, in nanoseconds: the epoch the usage tests' times count from


class FoldRuns:
    """Mixin for a `TestCase` whose `self.q` is a temp queue: `mkrun` writes a run record (`start` and `stop`
    seconds from `T0`), `write` appends rows to a board file and `rows` makes usage-request rows (a `t` in
    seconds from `T0`)."""

    def mkrun(self, rid, seat, model, effort, agent, start, stop):
        f = lambda s: datetime.fromtimestamp(T0 / 1e9 + s, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        task, phase = rid.split("/")
        p = self.q / "runs" / task / f"{phase}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"run_id": rid, "task_id": task, "phase": phase, "seat": seat, "agent_type": f"delivery-{seat}",
                                 "expected_model": model, "expected_effort": effort, "agent_id": agent,
                                 "opened_at": f(start), "started_at": f(start), "stopped_at": f(stop)}))

    def write(self, name, rows):
        with (self.q / "board" / name).open("a") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    def rows(self, *rs):
        out = []
        for r in rs:
            r = dict(r)
            t = r.pop("t")
            out.append({k.replace("__", "_"): v for k, v in r.items()} | {"at": otel._iso(t)})
        return out


class BoardPage:
    """Mixin for a `TestCase`: `page` runs the board page's script under node against a built board and
    returns the html it wrote and the drill panels it opened."""

    def page(self, b, h: str = "", patch=None):
        from tests.test_board_drill import HASH_STUB  # noqa: PLC0415 (test_board_drill imports this module)
        js = (patch or (lambda t: t))(board.PAGE.read_text()).replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: %s, pathname: '/b', search: ''};\n" % json.dumps(h)
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + "\nprocess.stdout.write(JSON.stringify({out: out.join(''), panel}));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        return d["out"], d["panel"]
