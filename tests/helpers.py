"""Build throwaway product checkouts for the `ccp` tests."""
from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from ccp import config, tasklog

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


def without_constant_warnings(text: str | bytes) -> str | bytes:
    """`text`, stderr output, without the lines that warn a constant is set (SPEC §29.3): a fixture that sets
    `worktrees.dir` has the warning on every load, and a test of other output leaves it out."""
    if isinstance(text, bytes):
        return b"".join(x for x in text.splitlines(keepends=True) if b"is a constant in code" not in x)
    return "".join(x for x in text.splitlines(keepends=True) if "is a constant in code" not in x)


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
