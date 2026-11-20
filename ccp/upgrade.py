"""What a plane release asks of a product (SPEC §29.3, ADR-0041 D2).

  ccp upgrade notes [--since COMMIT]   the plane's tasks merged since COMMIT, each with its `adopt` step
  ccp upgrade status                   the `adopt` steps this product has not taken
  ccp upgrade decline|take TASK --reason R   record a task's step as declined or taken in plane.json

Both read the plane's own task log, in the plane checkout `ccp` runs from (normally the run checkout):
a task is merged when its file says `done`, and merged since COMMIT when its file there did not. The
default COMMIT is the plane checkout's previous release: the newest commit in its HEAD reflog that is
not HEAD.

A step is read by its form only: `<file> <key.path> [value]`, where the file is `plane.json`
(`docs/delivery/plane.json`), `binding` (the product's binding) or `settings` (`.claude/settings.json`).
Such a step is taken when the product's file holds the key, whatever its value. A step whose first word
is `none` asks nothing. Any other step, and one whose file cannot be read, is listed as "check by hand".
A step that starts with `required:` is one the product must take, and is read without that prefix; any
other is optional. `status` names the plane checkout's HEAD commit it read, so two readings compare.
The step that sets plane.json `language` (§8.1) gets the product's own change: with a `package_docs` block,
the block's language (`python` where the block relied on the old default) as the value to set; without
one, the choice between a language pack and `none`, with what each costs. It proposes no value silently.
The step that names plane.json `suite.lanes.gate` is taken when the product has a gate lane by the rule
claim and next apply (`config.gate_lane_missing`, §14.1): the lane `suite.roles` gives the gate role,
with a command that is not the placeholder.
The step that names plane.json `architect.shape_from_task` (§19.11) is taken when plane.json records it or
sets `"architect": false`; until then it proposes the product's next task number as the adoption point, or
`"architect": false`.
plane.json `upgrade.declined` leaves a task's step out; `upgrade.taken` leaves out a step the product took
in a way the command cannot see, and lists it under `taken` with its reason. A step the command checked and
found taken is listed under `detected`. `decline` and `take` write those two objects, each removing the task
from the other; they rewrite plane.json and commit nothing.
The proposals a task answers are those the plane session closed as built by it (`ccp plane built`).
`status` ends with one more step, `plane.json keys`, when plane.json sets a key the plane removed, merged or
made a constant (`config.KEY_OUTCOMES`, §29.3): it lists each such key with its outcome (a removed key to
delete, a merged key and the key it moves to, a constant set to a value other than the constant). It is no
task's step, so it is never declined or taken: the product deletes or moves the keys.
It ends with one more, `binding keys`, when the product's binding sets a key the plane removed, or a runner
limit (`lib.binding_findings`, §8.3): a removed key to delete, a limit set (a constant), the lead's
compaction window (it moves to the product's own settings).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ccp import config, refs, tasklog
from ccp.config import Config
from ccp.queue import QueueError, lib

TAKEN, NOT_TAKEN, BY_HAND = "taken", "not taken", "check by hand"
KEY_RE = re.compile(r"^[A-Za-z_$][\w$-]*(?:\.[A-Za-z_$][\w$-]*)*$")
# The files a step may name, as the step writes them, and the kind of file each is.
STEP_FILES = {"plane.json": "plane.json", config.CONFIG_REL: "plane.json", "binding": "binding",
              "settings": "settings", ".claude/settings.json": "settings", "machine.json": "machine"}
SHOWN = {"plane.json": config.CONFIG_REL, "binding": "the binding", "settings": ".claude/settings.json",
         "machine": "the machine file (machine.json beside the bindings)"}


def _plane_root() -> Path:
    from ccp import queue  # noqa: PLC0415  (read at call time: the tests point it at a scratch plane)
    return queue.PLANE


def _plane_cfg() -> Config:
    root = _plane_root()
    try:
        return config.load(root)
    except config.ConfigError as e:
        raise QueueError(f"the plane checkout {root} has no readable task log: {e}", 2) from e


def merged_tasks(cfg: Config | None = None) -> list[dict[str, Any]]:
    """The plane's tasks whose file says `done`, in task-log order."""
    return [t for t in tasklog.load(cfg or _plane_cfg()) if t.get("status") == "done"]


def merged_task(task_id: str) -> dict[str, Any] | None:
    """The plane's merged task `task_id`, or None when there is none."""
    return next((t for t in merged_tasks() if t.get("task_id") == task_id), None)


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def previous_release(root: Path) -> str | None:
    """The plane checkout's previous release: the newest commit in its HEAD reflog other than HEAD."""
    head = _git(root, "rev-parse", "HEAD")
    for sha in (_git(root, "reflog", "--format=%H", "HEAD") or "").split():
        if sha != head:
            return sha
    return None


def _proposals_by_task() -> dict[str, list[str]]:
    """Built task id -> the proposals in this queue closed as built by it; {} without a queue."""
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        return {}
    from ccp import plane  # noqa: PLC0415
    out: dict[str, list[str]] = {}
    for p in plane.proposals(Path(q)).values():
        if p.get("status") == "built" and p.get("built_task"):
            out.setdefault(str(p["built_task"]), []).append(str(p["id"]))
    return out


def notes(_cfg: Config, a: Any) -> dict[str, Any]:
    """§29.3: the plane's tasks merged since `--since`, each with its title, `adopt` step and the proposals
    it answers."""
    pcfg = _plane_cfg()
    since = a.since or previous_release(pcfg.root)
    if not since:
        raise QueueError(f"the plane checkout {pcfg.root} has no previous release in its reflog: give --since COMMIT", 2)
    sha = _git(pcfg.root, "rev-parse", "--verify", "-q", f"{since}^{{commit}}")
    if not sha:
        raise QueueError(f"--since {since}: not a commit in the plane checkout {pcfg.root}", 2)
    done = merged_tasks(pcfg)
    before = tasklog.statuses_at(pcfg, sha, [str(t["task_id"]) for t in done])
    answers = _proposals_by_task()
    tasks = [{"task": t["task_id"], "title": t.get("title"), "adopt": tasklog.adopt_step(t),
              "proposals": answers.get(str(t["task_id"]), [])}
             for t in done if before.get(str(t["task_id"])) != "done"]
    return {"ok": True, "since": sha, "head": _git(pcfg.root, "rev-parse", "HEAD"), "tasks": tasks}


def parse_step(step: str) -> tuple[str, str, str] | None:
    """A step this command can check, as (file kind, key path, the value it names or ""); None otherwise.
    A `required:` prefix is read past."""
    words = tasklog.adopt_required(step.strip())[1].split(None, 2)
    if len(words) < 2 or words[0] not in STEP_FILES or not KEY_RE.match(words[1]):
        return None
    return STEP_FILES[words[0]], words[1], words[2].strip() if len(words) > 2 else ""


def _has(data: Any, key: str) -> bool:
    for part in key.split("."):
        if not isinstance(data, dict) or part not in data:
            return False
        data = data[part]
    return True


def _json_file(p: Path) -> dict[str, Any] | None:
    """A JSON object file; {} when it is absent (it holds no key), None when it does not read."""
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _sources(cfg: Config) -> dict[str, dict[str, Any] | None]:
    """The product's three files and the machine file (§8.3) as the steps read them; None for one that cannot be read."""
    from ccp.cli import product_binding  # noqa: PLC0415
    b = product_binding(cfg)
    try:
        binding = lib.read_binding(b.read_text()) if b else None
    except OSError:
        binding = None
    return {"plane.json": _json_file(cfg.root / config.CONFIG_REL), "binding": binding,
            "settings": _json_file(cfg.root / ".claude" / "settings.json"),
            "machine": _json_file(lib.machine_path())}


def _change(kind: str, key: str, value: str) -> str:
    """The change a checkable step asks for: the key alone, `to <value>` for a one-word value, and the rest
    of the step as written after a colon when it is more than one word."""
    where = f"set `{key}` in {SHOWN[kind]}"
    if not value:
        return where
    return f"{where} to {value}" if len(value.split()) == 1 else f"{where}: {value}"


def language_change(plane: dict[str, Any]) -> str:
    """§29.3: the change the `language` step (§8.1) asks of a product whose plane.json is `plane`: with a
    `package_docs` block, its language (`python` where it named none, the old default) as the value to set;
    without one, the choice between `python` and `none`, each with what it costs."""
    where = f"set `language` in {config.CONFIG_REL}"
    block = plane.get("package_docs")
    if isinstance(block, dict):
        old = block.get("language")
        why = ("the package_docs block's language, which moves there: delete package_docs.language" if old
               else "the old default your package_docs block relied on")
        return f"{where} to {old or config.GRACE_LANGUAGE} ({why})"
    return (f"{where}; this product has no package_docs block, so choose: (a) python: the test output is read and "
            "`ccp suite affected` works with the Python pack, and it also turns on the package-doc checks, which "
            "this product has never run: write the package docs first (every source directory's CLAUDE.md, "
            "SPEC §21.3), or the gate's plane-docs stage fails; (b) none: no package-doc checks, but then give "
            "suite.affected_map and your own suite.count_re and suite.summary patterns, or `ccp suite affected` "
            "exits 2 and the run's tests are not counted")


ADOPTION_KEY = ("plane.json", "architect.shape_from_task")
KEYS_STEP = "plane.json keys"  # the step that lists the product's removed, merged and constant keys; no task's
BINDING_STEP = "binding keys"  # the same for the binding's: removed keys, runner limits; no task's


def adoption_change(cfg: Config) -> str:
    """§19.11: the change the adoption-point step asks of this product: its next task number as the point (no
    task before it is judged and no pass is owed at once), or `"architect": false` to keep the seat off."""
    where = f"set `architect.shape_from_task` in {config.CONFIG_REL}"
    return (f"{where} to {tasklog.next_number(cfg)}, the next task number: the architect judges no task before it "
            f"and no pass is owed at once; or set `\"architect\": false` in {config.CONFIG_REL} to keep the seat off")


def key_change(found: dict[str, Any]) -> str:
    """§29.3: the change one key of the `plane.json keys` step asks: delete a removed key, move a merged one
    to its replacement, delete a constant (or file a plane proposal to keep it)."""
    key, why = found["key"], config.KEY_OUTCOMES[found["key"]].why
    if found["outcome"] == config.REMOVED:
        return f"delete `{key}`: it is removed" + (f" ({why})" if why else "")
    if found["outcome"] == config.MERGED:
        return f"move `{key}` to `{found['replacement']}`" + (f" ({why})" if why else "")
    return (f"delete `{key}`: it is a constant, {found['constant']!r}, and yours is {found['set']!r}; or file a "
            "plane proposal to keep the key")


def keys_step(plane: dict[str, Any] | None) -> dict[str, Any] | None:
    """§29.3: the `plane.json keys` step for a product whose plane.json is `plane`, or None when it sets no key
    with an outcome to act on."""
    found = [{k: v for k, v in f.items() if k != "note"} for f in config.key_outcomes_set(plane)]
    if not found:
        return None
    for f in found:
        f["change"] = key_change(f)
    return {"task": KEYS_STEP, "title": "plane.json keys the plane removed, merged or made constants",
            "adopt": KEYS_STEP, "required": False, "check": NOT_TAKEN,
            "change": "; ".join(f["change"] for f in found), "proposals": [], "keys": found}


def binding_change(found: dict[str, Any]) -> str:
    """§8.3: the change one key of the `binding keys` step asks: delete a removed key, or a runner limit (a
    constant now: or file a plane proposal to keep it), and move the lead's window to the product's settings."""
    key = found["key"]
    if found["outcome"] == "removed":
        return f"delete `{key}`: it is removed" + (f" ({found['why']})" if found["why"] else "")
    if found["outcome"] == "moved":
        return f"move `{key}` to {found['replacement']}, then delete it"
    if not found["differs"]:
        return f"delete `{key}`: it is a constant, {found['constant']!r}, which is what yours already is"
    return (f"delete `{key}`: it is a constant, {found['constant']!r}, and yours is {found['set']!r}; or file a "
            "plane proposal to keep the key")


def binding_step(binding: dict[str, Any] | None) -> dict[str, Any] | None:
    """§8.3: the `binding keys` step for a product whose binding is `binding` (`lib.read_binding`), or None when
    it sets no key the plane removed, no runner limit and no lead window."""
    found = lib.binding_findings(binding or {})
    if not found:
        return None
    for f in found:
        f["change"] = binding_change(f)
    return {"task": BINDING_STEP, "title": "binding keys the plane removed or made constants",
            "adopt": BINDING_STEP, "required": False, "check": NOT_TAKEN,
            "change": "; ".join(f["change"] for f in found), "proposals": [], "keys": found}


def status(cfg: Config, _a: Any) -> dict[str, Any]:
    """§29.3: each `adopt` step of a merged plane task that this product has not taken, with the task, whether
    it is required, the product's own proposal for it and the change to make, and the plane checkout's HEAD
    commit it read (`plane`). A declined task's step is left out; a step the product recorded as taken
    (`upgrade.taken`) is too, and is listed under `taken` with its reason; a step the command checked and
    found taken is listed under `detected`. Then `plane.json keys`, the keys the product sets that the plane
    removed, merged or made constants (`keys_step`), and `binding keys`, those of its binding (`binding_step`)."""
    declined = (cfg.upgrade or {}).get("declined") or {}
    recorded = (cfg.upgrade or {}).get("taken") or {}
    sources = _sources(cfg)
    mine = _proposals_by_task()
    steps: list[dict[str, Any]] = []
    taken: list[dict[str, Any]] = []
    detected: list[dict[str, Any]] = []
    for t in merged_tasks():
        tid, step = str(t["task_id"]), tasklog.adopt_step(t)
        if tasklog.asks_nothing(step) or tid in declined:
            continue
        if tid in recorded:
            taken.append({"task": tid, "title": t.get("title"), "adopt": step, "reason": recorded[tid]})
            continue
        required, bare = tasklog.adopt_required(step)
        parsed = parse_step(step)
        if parsed and sources[parsed[0]] is not None:
            if parsed[:2] == ("plane.json", "suite.lanes.gate"):  # §14.1: taken when the gate role has a lane
                found = config.gate_lane_missing(cfg) is None
            elif parsed[:2] == ADOPTION_KEY:  # §19.11: taken when the point is recorded or the seat is off
                found = _has(sources[parsed[0]], parsed[1]) or (sources[parsed[0]] or {}).get("architect") is False
            else:
                found = _has(sources[parsed[0]], parsed[1])
            if found:
                detected.append({"task": tid, "title": t.get("title"), "adopt": step})
                continue
            check, change = NOT_TAKEN, _change(*parsed)
            if parsed[:2] == ("plane.json", "language"):  # §8.1: the product's own value, or its choice
                change = language_change(sources["plane.json"] or {})
            elif parsed[:2] == ADOPTION_KEY:
                change = adoption_change(cfg)
        else:
            check, change = BY_HAND, bare or step  # a step of only the prefix is shown as written
        steps.append({"task": tid, "title": t.get("title"), "adopt": step, "required": required, "check": check,
                      "change": change, "proposals": mine.get(tid, [])})
    if keys := keys_step(sources["plane.json"]):
        steps.append(keys)
    if keys := binding_step(sources["binding"]):
        steps.append(keys)
    return {"ok": True, "plane": _git(_plane_root(), "rev-parse", "HEAD"), "steps": steps, "taken": taken,
            "detected": detected}


def _record(cfg: Config, a: Any, key: str, other: str) -> dict[str, Any]:
    """Set plane.json `upgrade.<key>.<task id>` to the reason and remove the id from `upgrade.<other>`.
    Refused (exit 2, nothing written): a blank reason, a task that is not a merged plane task or whose step
    asks nothing, and a plane.json that does not load before or would not load after the change."""
    reason = a.reason or ""
    if not reason.strip():
        raise QueueError(f"{a.cmd}: give the reason with --reason", 2)
    pcfg = _plane_cfg()
    ids = refs.ids(pcfg)
    hits = [t for t in merged_tasks(pcfg) if ids.same_task(t["task_id"], a.task)]
    if len(hits) != 1:
        raise QueueError(f"{a.cmd}: {a.task} is not a merged plane task in the plane checkout {pcfg.root}", 2)
    tid = str(hits[0]["task_id"])
    if tasklog.asks_nothing(tasklog.adopt_step(hits[0])):
        raise QueueError(f"{a.cmd}: {tid}'s adopt step asks nothing: there is nothing to record", 2)
    path = cfg.root / config.CONFIG_REL
    try:
        config.load(cfg.root)
        data = json.loads(path.read_text())
    except (config.ConfigError, OSError, ValueError) as e:
        raise QueueError(f"{a.cmd}: {config.CONFIG_REL} does not load: {e}", 2) from e
    upgrade = data.setdefault("upgrade", {})
    if not isinstance(upgrade, dict) or not isinstance(upgrade.setdefault(key, {}), dict):
        raise QueueError(f"{a.cmd}: {config.CONFIG_REL} `upgrade.{key}` is not an object", 2)
    upgrade[key][tid] = reason
    if isinstance(upgrade.get(other), dict):
        upgrade[other].pop(tid, None)
    try:
        config._parse(cfg.root, json.dumps(data))  # noqa: SLF001  (the file as it would be, checked as `load` does)
    except config.ConfigError as e:
        raise QueueError(f"{a.cmd}: {config.CONFIG_REL} would not load after the change: {e}", 2) from e
    from ccp import queue  # noqa: PLC0415
    queue.write_json(path, data)
    return {"ok": True, "task": tid, "recorded": key, "reason": reason}


def decline(cfg: Config, a: Any) -> dict[str, Any]:
    """§29.3: record task `a.task`'s step as declined (`upgrade.declined`), with `a.reason`."""
    return _record(cfg, a, "declined", "taken")


def take(cfg: Config, a: Any) -> dict[str, Any]:
    """§29.3: record task `a.task`'s step as taken (`upgrade.taken`), with `a.reason`."""
    return _record(cfg, a, "taken", "declined")
