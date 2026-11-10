"""The runtime queue as the §10 toolkit sees it: QUEUE_ROOT, the live team, the ledger, `work.json`
and a task's queue file.

Every write here goes through one of these helpers, so each command records what it changed in
`observability/events.jsonl` (the §23 ledger, written through `lib.append_event` and its checks).
The single writers the plane already has stay single: `waiting_on` through `set-waiting-on.sh`,
heartbeats through `heartbeat.sh`. The toolkit calls them rather than writing those fields itself.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ccp.envvars import envvar
from ccp import refs, tasklog
from ccp.config import Config

PLANE = Path(__file__).resolve().parents[1]
OBS = PLANE / "scripts" / "observability"
sys.path.insert(0, str(OBS))
import lib  # noqa: E402

CCP_BIN = PLANE / "bin" / "ccp"
def _main_worktree(repo: Path) -> Path:
    """The clone's main worktree: `repo` itself, or, for a linked worktree (its `.git` is a file
    naming `<main>/.git/worktrees/<name>`), that main one."""
    g = repo / ".git"
    if g.is_file():
        m = re.match(r"gitdir:\s*(.+)", g.read_text().strip())
        if m:
            p = Path(m.group(1))
            p = p if p.is_absolute() else (repo / p).resolve()
            if p.parent.name == "worktrees" and p.parent.parent.name == ".git":
                return p.parent.parent.parent
    return repo


# SPEC §29.2: the run checkout sits beside the clone's main worktree (run-checkout.sh's default).
RUN_CHECKOUT = str(_main_worktree(Path(__file__).resolve().parents[1]).parent / "control-plane-run")


def launchd_prefix() -> str:
    """The reverse-DNS prefix of the plane's launchd labels (`CCP_LAUNCHD_PREFIX`, default `dev.ccp`):
    `<prefix>.control-plane.otel`, `<prefix>.control-plane.board.<project_id>`."""
    p = (envvar("CCP_LAUNCHD_PREFIX") or "dev.ccp").strip().strip(".")
    return p if re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*", p) else "dev.ccp"
# A task leased in one of these phases is with a live runner: sync and the board never take it.
MID_FLIGHT = {
    "leased", "implementing", "implemented", "reviewing", "fixing", "reviewed", "submitted", "verifying", "merging",
}


def run_ccp() -> Path:
    """The `ccp` a launchd agent runs (§29.2): the run checkout's (`CCP_RUN_CHECKOUT`, as
    run-checkout.sh), never whichever checkout ran the install. This checkout's own only where no run
    checkout exists (a cloud clone)."""
    b = Path(envvar("CCP_RUN_CHECKOUT") or RUN_CHECKOUT) / "bin" / "ccp"
    return b if b.is_file() else CCP_BIN


def run_ccp_warning() -> str | None:
    """A named run checkout without `bin/ccp`: the plist falls back to this checkout, say so."""
    named = envvar("CCP_RUN_CHECKOUT")
    if named and not (Path(named) / "bin" / "ccp").is_file():
        return f"CCP_RUN_CHECKOUT={named} has no bin/ccp; the plist runs {CCP_BIN} (SPEC §29.2)"
    if run_ccp() == CCP_BIN and not (Path(RUN_CHECKOUT) / "bin" / "ccp").is_file() and not named:
        return f"no run checkout at {RUN_CHECKOUT}; the plist runs {CCP_BIN} (SPEC §29.2)"
    return None


BOOTOUT_WAIT = 10.0  # seconds for launchd to forget a booted-out service
BOOTSTRAP_BACKOFF = (1, 2, 4)  # retries after "Bootstrap failed: 5: Input/output error"
RUNNING_CHECKS = 5  # one a second, for a KeepAlive agent to reach `state = running`


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _launchd_state(target: str) -> tuple[bool, str | None]:
    r = _launchctl("print", target)
    state = next((ln.strip().split("=", 1)[1].strip() for ln in r.stdout.splitlines()
                  if ln.strip().startswith("state =")), None) if r.returncode == 0 else None
    return r.returncode == 0, state


def launchd_bootout(label: str) -> bool:
    """Boot the agent out and wait (at most BOOTOUT_WAIT) until `launchctl print` no longer finds it.
    A bootstrap sent while launchd still holds the old service fails with error 5 (2026-10-21)."""
    target = f"gui/{os.getuid()}/{label}"
    _launchctl("bootout", target)
    for _ in range(int(BOOTOUT_WAIT * 2)):
        if not _launchd_state(target)[0]:
            return True
        time.sleep(0.5)
    return not _launchd_state(target)[0]


def launchd_reload(label: str, plist: Path, want_running: bool) -> dict[str, Any]:
    """Boot out, then bootstrap `plist`, retrying an EIO (error 5) with backoff, then check the agent
    is loaded (and, for a KeepAlive agent, running). The result says how it went, never raises."""
    dom = f"gui/{os.getuid()}"
    target = f"{dom}/{label}"
    out: dict[str, Any] = {}
    if not launchd_bootout(label):
        out["warnings"] = [f"{target} was still loaded {BOOTOUT_WAIT:.0f}s after bootout; bootstrapping anyway"]
    attempts, err = 0, None
    for delay in (*BOOTSTRAP_BACKOFF, None):
        attempts += 1
        r = _launchctl("bootstrap", dom, str(plist))
        if r.returncode == 0:
            err = None
            break
        err = (r.stderr or r.stdout).strip() or f"launchctl bootstrap exited {r.returncode}"
        eio = r.returncode == 5 or "Input/output error" in err or "failed: 5:" in err
        if delay is None or not eio:
            break
        time.sleep(delay)
    loaded, state = _launchd_state(target)
    for _ in range(RUNNING_CHECKS if want_running and err is None else 0):
        if loaded and state == "running":
            break
        time.sleep(1)
        loaded, state = _launchd_state(target)
    ok = err is None and loaded and (state == "running" or not want_running)
    if err is None and not ok:
        err = (f"bootstrapped, but launchctl print {target} "
               + (f"reports state {state!r}, not running" if loaded else "does not find it"))
    out.update({"ok": ok, "bootstrap_attempts": attempts, "loaded": loaded, "state": state,
                **({"error": err} if err else {})})
    return out
TASK_ID_RE = refs.DEFAULT.task_id_re  # the default; task_meta checks the product's width (refs.py)


class QueueError(Exception):
    """The command cannot act: the message says why, `code` is the exit code."""

    def __init__(self, msg: str, code: int = 2):
        super().__init__(msg)
        self.code = code


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def root() -> Path:
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        raise QueueError("set QUEUE_ROOT to this project's runtime queue")
    return Path(q)


def actor(default: str = "task-runner") -> str:
    a = os.environ.get("ACTOR") or default
    return a if a in lib.ACTORS else default


def binding_text(q: Path) -> str:
    return lib.project_yaml_text(q)


def binding_scalar(q: Path, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*([^#\n]+)", binding_text(q), re.M)
    return m.group(1).strip().strip("'\"") if m else None


def binding_runner_name(q: Path) -> str:
    """The binding's `runner.name` (§8.3), the name the lead asks for at a spawn; `runner` by default."""
    m = re.search(r"^runner:\s*\n(?:[ \t]+.*\n)*?[ \t]+name:\s*(\S+)", binding_text(q) + "\n", re.M)
    return m.group(1).strip("'\"") if m else "runner"


def runner_teammate(q: Path) -> str:
    """§10.2: the live runner teammate's actual name. The harness gives a fresh spawn a suffixed name
    (`runner-2`) while the old teammate still holds the asked-for one; the lead binds the actual name
    into work.json `runner` (`team.sh runner bind`). Else the binding's name."""
    try:
        w = read_json(q / "work.json", {})
    except QueueError:  # a broken work.json must not stop the readers that only want a name
        w = {}
    name = w.get("runner") if isinstance(w, dict) else None
    return str(name) if name else binding_runner_name(q)


def runner_slots(w: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """§16.4: work.json `runners`, slot -> record (`bound_name`, `tasks_done`, `worktree`, ...); {} for
    one runner, which keeps the fields before §16 (`runner`, `runner_tasks_done`)."""
    r = w.get("runners") if isinstance(w, dict) else None
    return {str(k): (v if isinstance(v, dict) else {}) for k, v in r.items()} if isinstance(r, dict) else {}


def holder_teammate(q: Path, task_id: str) -> str:
    """§16.4: the teammate name of the runner that holds `task_id` (its lease's slot, bound name as
    recorded), else the one runner's (`runner_teammate`)."""
    try:
        w = read_json(q / "work.json", {})
        slot = str(read_json(task_state_path(q, task_id), {}).get("lease_holder") or "")
    except QueueError:
        return runner_teammate(q)
    slots = runner_slots(w)
    if slot and slot in slots:
        return str(slots[slot].get("bound_name") or slot)
    if slot and slots:  # a slot the lead removed: its own name, never the single runner's stale one
        return slot
    return runner_teammate(q)


def runner_names(q: Path) -> set[str]:
    """Every name a runner teammate of this queue has had: the binding's, work.json's, and each name a
    `runner` event recorded (spawn, bound). Telemetry from an earlier runner still counts as the runner's."""
    names = {binding_runner_name(q), runner_teammate(q)}
    try:  # §16.7: every slot and every bound name
        for slot, rec in runner_slots(read_json(q / "work.json", {})).items():
            names |= {slot, str(rec.get("bound_name") or slot)}
    except QueueError:
        pass
    p = events_path(q)
    if p.is_file():
        for line in p.read_text().splitlines():
            if '"runner"' not in line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "runner" and isinstance(e.get("payload"), dict) and e["payload"].get("name"):
                names.add(str(e["payload"]["name"]))
    return names


def integration_branch(q: Path) -> str:
    return binding_scalar(q, "integration_branch") or "main"


def emit(q: Path, cfg: Config, task_id: str, typ: str, op: str, payload: dict[str, Any],
         who: str | None = None) -> dict[str, Any]:
    ev = {"at": iso(), "project_id": cfg.project_id, "task_id": task_id or "", "actor": who or actor(),
          "type": typ, "op": op, "payload": payload}
    errs = lib.validate_event(ev)
    if errs:
        raise QueueError("invalid event: " + "; ".join(errs), 1)
    return lib.append_event(q, ev)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """An exclusive flock on `<path>.lock`, held by every append to a shared jsonl record and by the
    sync's merge, which replaces the file atomically: an append is never lost under the replace."""
    import fcntl  # noqa: PLC0415

    lp = path.with_name(path.name + ".lock")
    lp.parent.mkdir(parents=True, exist_ok=True)
    with lp.open("a") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """One row appended under the file's lock (`file_lock`)."""
    with file_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def events_path(q: Path) -> Path:
    """The ledger of this queue: observability/events.jsonl."""
    return lib.events_path(q)


def sign_offs(q: Path, task_id: str) -> dict[str, dict[str, Any]]:
    """§3.5: the task's latest recorded sign-off per stage (`brief`, `build`), from the ledger's
    `sign_off` `recorded` events: the payload (`stage`, `by`, `words`, `head`) with the event's `at`."""
    out: dict[str, dict[str, Any]] = {}
    for ev in lib.load_events(events_path(q)):
        p = ev.get("payload") or {}
        if ev.get("task_id") == task_id and ev.get("type") == "sign_off" and ev.get("op") == "recorded" \
                and isinstance(p, dict) and p.get("stage"):
            out[str(p["stage"])] = {**p, "at": ev.get("at")}
    return out


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        raise QueueError(f"{path} is not valid JSON: fix or remove it", 1) from None


def write_json(path: Path, obj: Any) -> None:
    lib.write_json(path, obj)


def load_work(q: Path) -> dict[str, Any]:
    w = read_json(q / "work.json", {})
    return w if isinstance(w, dict) else {}


def preferred_ids(w: dict[str, Any]) -> list[str]:
    """§10.4: the lead's preference list, in order (work.json `next_tasks`; a `next_task` from before
    the list is a one-entry list)."""
    v = w.get("next_tasks")
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [str(w["next_task"])] if w.get("next_task") else []


def save_work(q: Path, updates: dict[str, Any], drop: tuple[str, ...] = (),
              drop_if: tuple[str, Any] | None = None,
              edit: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Merge `updates` into work.json, keeping every other key; the keys in `drop` are removed, and
    with `drop_if=(key, value)` only while the file read now still has that value (a preference the
    lead changed between the caller's read and this write is kept). `edit` then changes the file as
    read now, in place (the claim takes its task out of the preference list the lead may have reset).
    §16.4: the read and the write hold work.json's lock, the one every writer takes (`set-waiting-on.sh`,
    `team.py`), so two writers at once cannot lose each other's change. Anything computed from the file
    belongs in `edit`, never in `updates` from an earlier read; `edit` must not write work.json itself."""
    with file_lock(q / "work.json"):
        w = load_work(q)
        keep = drop_if is not None and w.get(drop_if[0]) != drop_if[1]
        w.update(updates)
        for k in () if keep else drop:
            w.pop(k, None)
        if edit is not None:
            edit(w)
        w["updated_at"] = iso()
        write_json(q / "work.json", w)
    return w


def task_state_path(q: Path, task_id: str) -> Path:
    return q / "tasks" / f"{task_id}.json"


def load_task_state(q: Path, task_id: str) -> dict[str, Any]:
    t = read_json(task_state_path(q, task_id), {})
    return t if isinstance(t, dict) else {}


def save_task_state(q: Path, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    t = load_task_state(q, task_id)
    t.update(updates)
    t["updated_at"] = iso()
    write_json(task_state_path(q, task_id), t)
    return t


def progress_event(q: Path, task_id: str, frm: str | None, to: str, note: str = "") -> None:
    """`progress/<task_id>.json`'s event list, which `ccp health` reads for start times."""
    p = q / "progress" / f"{task_id}.json"
    prog = read_json(p, None) or {"task_id": task_id, "events": []}
    prog.setdefault("events", []).append({"at": iso(), "from": frm, "to": to, "note": note})
    prog["updated_at"] = iso()
    write_json(p, prog)


def set_marker(q: Path, task_id: str, state: str) -> None:
    """The `queue/<state>/<task_id>` marker the plane's queue scripts keep: one per task."""
    base = q / "queue"
    if base.is_dir():
        for d in base.iterdir():
            if d.is_dir() and d.name != state and (d / task_id).exists():
                (d / task_id).unlink()
    (base / state).mkdir(parents=True, exist_ok=True)
    (base / state / task_id).touch()


def durable_statuses(cfg: Config) -> dict[str, str]:
    """Each task's durable status (§4), by its id (the file name when the frontmatter names none) and
    by NNNN. The board and `ccp tasks sync` both look a queue file up here, by its file name, so a
    divergence the board names is one sync fixes."""
    out: dict[str, str] = {}
    for t in tasklog.load(cfg):
        tid, st = str(t.get("task_id") or t["_file"].stem), str(t.get("status") or "")
        out[tid] = st
        out.setdefault(refs.ids(cfg).task_number(tid), st)
    return out


def task_meta(cfg: Config, task_id: str) -> dict[str, Any]:
    """The task's durable frontmatter, by full id or NNNN. Its id becomes paths and command
    arguments, so it must be the file's own name, in the task-id shape."""
    for t in tasklog.load(cfg):
        if refs.ids(cfg).same_task(t["_file"].stem, task_id):
            tid = str(t.get("task_id") or "")
            if tid != t["_file"].stem or not refs.ids(cfg).task_id_re.match(tid):
                raise QueueError(f"{cfg.rel(t['_file'])}: task_id {tid!r} is not its file name in the "
                                 "NNNN-kebab-slug shape (ccp tasks check)", 2)
            return t
    raise QueueError(f"no task {task_id} in {cfg.rel(cfg.tasks_dir)}")


def phase_move(q: Path, cfg: Config, task_id: str, to: str, note: str = "", who: str | None = None) -> str | None:
    """One phase change: the event, the task's queue file, `progress/`, and `work.json` when it is
    the runner's current task. Returns the phase it left."""
    st = load_task_state(q, task_id)
    frm = st.get("status")
    emit(q, cfg, task_id, "phase", "transition", {"from": frm or "pending", "to": to, **({"note": note} if note else {})}, who)
    save_task_state(q, task_id, {"status": to, "phase_since": iso()})
    progress_event(q, task_id, frm, to, note)
    def current(cur: dict[str, Any]) -> None:
        if cur.get("task_id") == task_id:
            cur.update(phase=to, phase_since=iso())

    if load_work(q).get("task_id") == task_id:
        save_work(q, {}, edit=current)
    return frm


def heartbeat(q: Path, action: str, seat: str = "task-runner", task_id: str = "") -> None:
    """§18.3 through its single writer. A failed heartbeat never fails the command."""
    cmd = [str(OBS / "heartbeat.sh"), seat, "--wake-kind", "manual", "--action", action[:200]]
    if task_id:
        cmd += ["--task-id", task_id]
    subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})


# Plane scripts a queue may still hold a copy of after the plane stopped shipping them.
RETIRED_SCRIPTS = {
    "spec-maintainer-lock.sh": "the headless spec maintainer and its lock were removed, SPEC §17, 2026-11-05",
}


def script_drift(q: Path) -> list[str]:
    """§31.3: files in QUEUE_ROOT/scripts/ that are not the plane's own copy. A file the plane does
    not ship is `unknown`; one it ships with other content is `drifted`; one it used to ship is
    `retired` (the message says to delete it)."""
    d = q / "scripts"
    if not d.is_dir():
        return []
    # The binding's own auth-check script lives in the queue by design (§30, `auth_check.script`).
    sanctioned = set()
    m = re.search(r"^auth_check:\s*\n(?:[ \t]+.*\n)*?[ \t]+script:\s*(\S+)", binding_text(q) + "\n", re.M)
    if m:
        sanctioned.add((q / m.group(1).strip("'\"")).resolve())
    out = []
    for f in sorted(d.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix in (".pyc", ".tmp"):
            continue
        if f.resolve() in sanctioned:
            continue
        rel = f.relative_to(d)
        mine = PLANE / "scripts" / rel
        if str(rel) in RETIRED_SCRIPTS:
            out.append(f"retired: scripts/{rel} is no longer shipped by the plane ({RETIRED_SCRIPTS[str(rel)]}); delete it")
        elif not mine.is_file():
            out.append(f"unknown: scripts/{rel}")
        elif mine.read_bytes() != f.read_bytes():
            out.append(f"drifted: scripts/{rel} differs from the plane's scripts/{rel}")
    return out


def git(cwd: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise QueueError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}", 1)
    return r
