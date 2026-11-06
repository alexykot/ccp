"""Build throwaway product checkouts for the `ccp` tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

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


class Product:
    """A temp product root with a plane.json and helpers to add tasks and files."""

    def __init__(self, cfg: dict | None = None):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "docs/delivery/tasks").mkdir(parents=True)
        self.write("docs/delivery/plane.json", json.dumps({"project_id": "demo", **(cfg or {})}))

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
