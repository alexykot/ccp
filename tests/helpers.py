"""Build throwaway product checkouts for the `ccp` tests, and the small constants and builders they share.

`Product` is a temp product root with a plane config and helpers to add tasks and files; most modules build on
it. `binding(**keys)` is the text of a binding, `project_id: demo` first, then each key: a test that needs a
binding writes it with this, and only a test of the binding's format or of `ccp init`'s output keeps literal
text. A test names the worktrees directory as `config.WORKTREES_DIR`.

The constants and builders are each named for what they make: `PLANE_ROOT` (the plane checkout, and the only name
a test gives it), `GIT_ENV` (git's identity: a test identity, no global or system config), `LEAD_ENV` and
`as_lead()` (the environment with the lead's `ACTOR`, for a command only the lead may run), `as_actor(value)`
(`ACTOR` set to another value, or unset), `run_clock(case, *where)` (the one run clock: the stamps a test's runs
open and report at, a minute apart from the real time unless the test names its `start`), `file_tree` and the rest.

This module loads no `ccp` module on import, so the fence in `tests/__init__.py` comes first. It imports none of
the four `*_helpers.py` modules, and a test module imports a helper from the module that holds it: an edit to one
concern then marks only its importers affected."""
from __future__ import annotations

import copy
import itertools
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

if TYPE_CHECKING:
    from ccp import config

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
        from ccp import config  # noqa: PLC0415
        return config.load(self.root)

    def index(self) -> None:
        from ccp import tasklog  # noqa: PLC0415
        tasklog.write_index(self.cfg)


PLANE_ROOT = Path(__file__).resolve().parents[1]
RUN_CHECKOUT_SCRIPT = str(PLANE_ROOT / "scripts/run-checkout.sh")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def lead_env() -> dict[str, str]:
    """§3.5, §13.4, §17.5: the environment a test runs `ccp` in as the lead (`queue.lead_actor` guards its
    records). Modules import it as `LEAD_ENV` (module `__getattr__`), read when first named."""
    from ccp.queue import lib  # noqa: PLC0415
    return {"ACTOR": lib.LEAD}


def __getattr__(name: str):
    """PEP 562: `LEAD_ENV` reads the lead's actor id from `ccp` when a module first names it, so importing this
    module loads no `ccp` module."""
    if name == "LEAD_ENV":
        return lead_env()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def as_lead():
    """The environment with `ACTOR` naming the lead (`LEAD_ENV`), as a context manager or decorator."""
    return mock.patch.dict(os.environ, lead_env())


def as_actor(value: str | None):
    """The environment with `ACTOR` set to `value`, or with no `ACTOR` at all for None (the lead's: `as_lead`)."""
    if value is None:
        return mock.patch.dict(os.environ, {k: v for k, v in os.environ.items() if k != "ACTOR"}, clear=True)
    return mock.patch.dict(os.environ, {"ACTOR": value})


def file_tree(*roots: Path) -> dict[str, bytes]:
    """Every file under `roots` (git's own directory aside) with its bytes, and every directory."""
    out: dict[str, bytes] = {}
    for root in roots:
        for p in root.rglob("*") if root.exists() else []:
            if ".git" not in p.relative_to(root).parts:
                out[str(p)] = p.read_bytes() if p.is_file() else b"<dir>"
    return out


MIGRATION_FIELD = {"name": "migration", "values": ["required", "not required"]}
DOWNTIME_FIELD = {"name": "downtime", "values": ["yes", "no"]}
REVIEW_REGISTER = """# The review points (product-owned; SPEC §22)
review_points:
  - id: R7
    name: the earlier team's work, reviewed
    goal: Fold the earlier team's work into tasks.
    status: closed
    opened: 2026-10-20
    closed: 2026-10-22
  - id: R8
    name: pre-beta   # the operator's name
    goal: |-
      After this review point's tasks are done,
      we run the beta test.
    status: current
    opened: "2026-10-22"
  - id: R10
    name: "after the beta test"
    goal: 'What the beta test teaches.'
    status: planned
"""


def tagged_task(p: Product, tid: str, status: str = "pending", rp: str | None = None, deps=None, extra: str = "") -> Path:
    f = p.task(tid, status, deps)
    add = (f"review_point: {rp}\n" if rp else "") + extra
    if add:
        f.write_text(f.read_text().replace("updated: 2026-09-30\n", "updated: 2026-09-30\n" + add))
    return f


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_clock(case, *where: str, start: str | None = None) -> None:
    """Patch each dotted name in `where` (default `ccp.runs.iso`) with one shared clock until `case`'s cleanup.

    Each call returns the next stamp in `iso()`'s form, a minute after the last (`opened_at` has one-second
    resolution, and the gates order runs by it). The first is `start`, else the real UTC time at this call, to the
    minute, so a rule that compares a run's stamp with the real time (a pending run's expiry) sees a run opened now."""
    first = (datetime.fromisoformat(start.replace("Z", "+00:00")) if start
             else datetime.now(timezone.utc).replace(second=0, microsecond=0))
    stamps = ((first + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ") for i in itertools.count())
    for name in where or ("ccp.runs.iso",):
        patch = mock.patch(name, side_effect=lambda: next(stamps))
        patch.start()
        case.addCleanup(patch.stop)
