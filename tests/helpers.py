"""Build throwaway product checkouts for the `ccp` tests."""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from ccp import board, config, otel, prhost, prompt, runs, tasklog, verify
from ccp.queue import lib

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
        from tests.board_drill_fixture import HASH_STUB
        js = (patch or (lambda t: t))(board.PAGE.read_text()).replace("/*__BOARD__*/null", board.embed(b)).split("<script>", 1)[1].split("</script>", 1)[0]
        loc = "globalThis.location = {hash: %s, pathname: '/b', search: ''};\n" % json.dumps(h)
        r = subprocess.run(["node", "-e", HASH_STUB + loc + js + "\nprocess.stdout.write(JSON.stringify({out: out.join(''), panel}));"],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(r.stdout)
        return d["out"], d["panel"]


PLANE_ROOT = Path(__file__).resolve().parents[1]
RUN_CHECKOUT_SCRIPT = str(PLANE_ROOT / "scripts/run-checkout.sh")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


# §3.5, §13.4, §17.5: the environment a test runs `ccp` in as the lead (`queue.lead_actor` guards its records).
LEAD_ENV = {"ACTOR": lib.LEAD}


def as_lead():
    """The environment with `ACTOR` naming the lead (`LEAD_ENV`), as a context manager or decorator."""
    return mock.patch.dict(os.environ, LEAD_ENV)


def git_run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **GIT_ENV, **kw.pop("env", {})}, **kw)


def release_git(cwd: Path, *a: str) -> str:
    r = git_run(["git", *a], cwd=cwd)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def ledger_event(at: str, typ: str, op: str, payload: dict, task_id: str = "") -> dict:
    return {"at": at, "project_id": "demo", "task_id": task_id, "actor": lib.LEAD, "type": typ, "op": op,
            "payload": payload}


def spawn_event(at: str, rp: str, scope: list[str]) -> dict:
    return ledger_event(at, "runner", "spawn", {"name": "runner", "scope": scope, "review_point": rp})


def lease_event(at: str, tid: str) -> dict:
    return ledger_event(at, "lease", "set", {"holder": "runner"}, tid)


def epoch_iso(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def good_then_failed(q: Path, resets_in_s: float) -> dict:
    """The product's samples: a good reading two hours old, weekly at 95% with its reset `resets_in_s` from now,
    then a failed read a minute ago (§25.1: the unknown sample, no figures). Returns the good row."""
    t = time.time()
    resets = epoch_iso(t + resets_in_s)
    good = {"at": epoch_iso(t - 7200), "five_hour": 10, "seven_day": 95, "resets_at": resets, "five_hour_resets_at": None,
            "windows": [{"name": "seven_day", "pct": 95, "resets_at": resets}, {"name": "five_hour", "pct": 10, "resets_at": None}],
            "weekly_window": "seven_day", "session_window": "five_hour"}
    failed = {"at": epoch_iso(t - 60), "five_hour": None, "seven_day": None, "resets_at": None, "five_hour_resets_at": None,
              "windows": [], "failed": True, "exit": 1}
    (q / "board").mkdir(exist_ok=True)
    (q / "board" / "allowance.jsonl").write_text("".join(json.dumps(r) + "\n" for r in (good, failed)))
    return good


def repo_git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout


SUITE_RUN_ID = "0002-second/verify"


def suite_started(sid, lane="gate", at="2026-11-01T10:00:00Z"):
    return {"op": "started", "suite_id": sid, "at": at, "lane": lane, "run_id": SUITE_RUN_ID, "task_id": "0002-second",
            "phase": "verify"}


def suite_ended(sid, seconds, code=0, tests=900, cached=None, stages=None, at="2026-11-01T10:20:00Z"):
    row = {"op": "ended", "suite_id": sid, "at": at, "exit_code": code, "seconds": seconds, "tests": tests,
           "failed": None, "skipped": None, "ran": None, "cached": cached, "interrupted": None}
    if stages is not None:
        row.update(stages=[{"name": n, "seconds": s, "exit_code": 0} for n, s in stages], failed_stage=None)
    return row


HEALTH_T0 = 1_760_000_000  # 2025-10-09T08:53:20Z


def health_git(root, *a, env=None):
    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True, env={**os.environ, **(env or {})}).stdout


def health_commit(root, msg, at, *extra):
    stamp = f"@{at} +0000"
    health_git(root, "commit", "-qm", msg, *extra, env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})


def file_tree(*roots: Path) -> dict[str, bytes]:
    """Every file under `roots` (git's own directory aside) with its bytes, and every directory."""
    out: dict[str, bytes] = {}
    for root in roots:
        for p in root.rglob("*") if root.exists() else []:
            if ".git" not in p.relative_to(root).parts:
                out[str(p)] = p.read_bytes() if p.is_file() else b"<dir>"
    return out


MARKED_CHECK_ID = "mac-01"
MARKED_TASK_ID = "0002-second"
MARKED_BLOCK = f"""- id: `{MARKED_CHECK_ID}`
  story: As the operator, it runs on my machine.
  setup: a checkout of the head.
  runs_on: operator-machine
  steps:
    1. run it
  expect: exit 0

## Implementation notes"""


MIGRATION_FIELD = {"name": "migration", "values": ["required", "not required"]}
DOWNTIME_FIELD = {"name": "downtime", "values": ["yes", "no"]}
REPORT_HEAD = "a" * 40


def implement_report(*lines: str, outcome: str = "done") -> str:
    if outcome == "done":
        return done_report("implement", "PR: #7", f"Head: {REPORT_HEAD}", *lines)
    return "\n".join([f"Outcome: {outcome}", "PR: #7", f"Head: {REPORT_HEAD}", *lines, "## Friction", "none", ""])


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


def api_request(rid, t, model="claude-opus-5-5", effort="high", source="agent:custom", out=100, **more):
    return {"t": T0 + t * 10**9, "event__name": "api_request", "request_id": rid, "model": model, "effort": effort,
            "query_source": source, "input_tokens": 2, "output_tokens": out, "cache_read_tokens": 1000,
            "cache_creation_tokens": 10, "cost_usd": 0.01, "session__id": "s1", **more}


ADVICE_SPANS = {"lead": {}, "runner": {"agent_id": "runner@session-abc"}, "worker": {"agent_id": "a1"}}


def advice_row(rid, who, ctx=None, cost=0.01, written=0, five=0, model="claude-opus-5-5", session="s1",
               at="2027-01-15T08:00:00Z"):
    """One request of `who` (lead, runner or worker) on `model` in `session` at `at`, sending `ctx` context
    tokens (default: the writes and a thousand more), `written` of them cache writes, `five` of those at 5
    minutes."""
    ctx = written + 1000 if ctx is None else ctx
    return ({"request_id": rid, "at": at, "session_id": session, "model": model,
             "effort": "high", "query_source": "repl_main_thread" if who == "lead" else "agent:custom",
             "input_tokens": 1, "output_tokens": 10, "cache_read_tokens": ctx - 1 - written,
             "cache_creation_tokens": written, "cache_creation_5m_tokens": five,
             "cache_creation_1h_tokens": written - five, "cost_usd": cost},
            {"request_id": rid, **ADVICE_SPANS[who]})


HEAD_A = "a" * 40
HEAD_B = "b" * 40


def approve_verdict(task: str = "0001-a", **fields: object) -> dict:
    """A verdict that passes every rule: what the verifier writes for an approve at HEAD_A."""
    return {
        "task_id": task, "project_id": "demo", "verdict": "approve", "head_sha": HEAD_A,
        "checks": [{"dod_check_id": "cmd-01", "pass": True, "evidence": "ran it", "produced_by": "verifier"}],
        "spec_beyond_intent": [],
        "gate": {"runs": [{"command": "scripts/unit.sh", "exit_code": 0, "tests_run": 412,
                           "tests_skipped": 0, "seconds": 88.5},
                          {"command": "scripts/lint.sh", "exit_code": 0}]},
        **fields,
    }


def judge_merge_ok(p: Product, queue: Path, rec: dict, rid: str = "0001-a", recorded: tuple | None = None,
                   pr: str = "7", **facts: object) -> tuple[list[str], dict]:
    """The merge-ok decision on plain values: an open PR at HEAD_A (`facts` override), `rec` recorded just now."""
    got = prhost.PrFacts(**{"number": 7, "state": "open", "head": HEAD_A, **facts})
    return verify.judge(p.cfg, queue, rec, rid, got.head, got, recorded or (datetime.now(timezone.utc), "written"), pr)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def held_otherwise(**fields: object) -> dict:
    """A check the verifier ran that held only in another form, under the approved gate 0001-a-1."""
    return {"dod_check_id": "check-01", "pass": True, "as_written": False,
            "held_instead": "ran the listing at the head in place of the removed flag: exit 0",
            "ruling": "0001-a-1", "evidence": "the expectation names a flag the product no longer has",
            "produced_by": "verifier", **fields}


PROMPT_TEMPLATES = PLANE_ROOT / "templates" / "prompts"


def phase_values(**over) -> dict:
    """Every name the templates use, set to a placeholder, with the given overrides."""
    names = set()
    for f in PROMPT_TEMPLATES.glob("*.md"):
        t = f.read_text()
        names |= set(prompt.VAR_RE.findall(t)) | {m[1] for m in re.findall(r"\{\{([#^/])(\w+)\}\}", t)}
    v = {n: f"<{n}>" for n in names}
    v.update(refactor=False, prior_reports="", note="", worker_env="", rules_doc="", fragment="", main_checkout="/m",
             accept_cache=False, review_cache=False, cold_gate=False, architect_checks="", pregate_lane="", cache_max_age_days="",
             budgets=False, resolution=False, resolved_verify=False, has_affected=False, has_old=False)
    v.update(over)
    return v


def render_phase_values(phase: str, **over) -> str:
    return prompt.render_phase(phase, phase_values(**over))


def with_test_methods(text: str) -> str:
    """The text of a test module a fixture writes, its `t_` methods named `test_`: a fixture module holds no test
    method of its own, so it spells them `def t_x`."""
    return text.replace("def t_", "def test_")
