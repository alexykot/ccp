#!/usr/bin/env bash
# runner-idle.sh — SPEC §18.2 TeammateIdle hook. Shipped by the control-plane
# plugin (SPEC §9.1), which calls it with no arguments: it then asks `ccp where` for the queue and
# the plane. A product still on managed copies calls its copy with --queue-root and --ccp.
#
# Keeps the runner teammate working while its scope still has a ready task and nothing waits on
# the lead or the operator. Exit 2 = keep working (stderr is the feedback); exit 0 = let it go idle.
# Any other teammate (among them an earlier runner a rotation replaced: the runner is the name
# work.json `runner` binds, SPEC §10.2), the runner's own subagents, a draining/idle runner, a
# rotation due, or a missing queue: exit 0. A subagent is told apart by the hook input: Claude Code adds `agent_id` and
# `agent_type` when a hook fires inside a subagent, and the runner's subagents share its
# teammate_name. So it acts only when there is no agent_id, or agent_type is the runner's own type.
# For a teammate, Claude Code reports agent_type as the teammate's name (SPEC docs/design/plugin.md), so that counts
# as the runner's own type too; the runner's subagents report their own (plugin-scoped) types.
# Every input's non-secret fields go to observability/runner-idle-inputs.jsonl (bounded), so a
# change in what the harness sends can be seen.
# After `idle_block_limit` consecutive blocks on the same ready set it lets the runner idle, so a
# runner that genuinely cannot proceed reports instead of looping.
# With an `architect` block in the product's plane.json (SPEC §19.6) it also asks `ccp tasks next`:
# a report overdue for triage waits on the lead (let it idle); a pass due tells it to start the pass.
#
# settings.json:
#   {"hooks": {"TeammateIdle": [{"hooks": [{"type": "command", "timeout": 20,
#     "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/runner-idle.sh --queue-root <QUEUE_ROOT> --ccp <PLANE>/bin/ccp"}]}]}}
set -uo pipefail
# The hook's JSON arrives on stdin; the heredoc below takes stdin for the script, so pass it by env.
HOOK_INPUT="$(cat)"
export HOOK_INPUT
exec python3 - "$@" <<'PY'
import datetime, json, os, re, shutil, subprocess, sys
from pathlib import Path

args = sys.argv[1:]
def arg(name, default=None):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default

try:
    hook = json.loads(os.environ.get("HOOK_INPUT") or "{}")
except ValueError:
    sys.exit(0)
root = Path(arg("--queue-root", "") or "/nonexistent")
ccp = arg("--ccp", "ccp")
if not arg("--queue-root"):
    # Plugin mode (SPEC §9): the project's queue and plane come from `ccp where`.
    try:
        on_path = shutil.which("ccp") or "ccp"
        w = subprocess.run([on_path, "--root", os.environ.get("CLAUDE_PROJECT_DIR") or ".", "where"],
                           capture_output=True, text=True, timeout=10)
        where = json.loads(w.stdout) if w.returncode == 0 else {}
    except (OSError, ValueError, subprocess.SubprocessError):
        where = {}
    root = Path(where.get("queue_root") or "/nonexistent")
    ccp = where.get("ccp") or on_path
if not root.is_dir() or not (root / "work.json").is_file():
    sys.exit(0)   # no queue, or no runner has ever run here: nothing to keep working, nothing to log

yml = (root / "project.yaml").read_text() if (root / "project.yaml").is_file() else ""
def block(name):
    out, inside = {}, False
    for line in yml.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = line.split("#", 1)[0].strip() == f"{name}:"
            continue
        if inside and ":" in line:
            k, _, v = line.strip().partition(":")
            v = v.split(" #", 1)[0].strip().strip("'\"")
            if v:
                out[k.strip()] = v
    return out
rc = block("runner")

# Record what the harness sent: whitelisted fields only (no prompts, no transcript contents).
LOG_FIELDS = ("hook_event_name", "teammate_name", "team_name", "agent_id", "agent_type", "session_id",
              "cwd", "permission_mode")
try:
    import datetime
    log_p = root / "observability" / "runner-idle-inputs.jsonl"
    log_p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "keys": sorted(hook), **{k: hook[k] for k in LOG_FIELDS if k in hook}}
    if log_p.is_file() and log_p.stat().st_size > 256 * 1024:
        log_p.write_text("".join(log_p.read_text().splitlines(True)[-200:]))
    with log_p.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")
except (OSError, TypeError, ValueError):
    pass

try:
    work = json.loads((root / "work.json").read_text())
except (OSError, ValueError):
    sys.exit(0)
if not isinstance(work, dict):
    sys.exit(0)
# SPEC §16.4: several runners, one per slot (work.json `runners`): this teammate is the slot whose bound
# name it carries; every other name (an old teammate a rotation replaced) is no runner.
SLOTS = work.get("runners") if isinstance(work.get("runners"), dict) else {}
SLOT = None
if SLOTS:
    SLOT = next((k for k, v in SLOTS.items() if str((v or {}).get("bound_name") or k) == hook.get("teammate_name")), None)
    if SLOT is None or (SLOTS[SLOT] or {}).get("bind_pending"):
        sys.exit(0)  # no slot's runner, or one respawned after a rotation and not yet bound
    RUNNER = str(SLOTS[SLOT].get("bound_name") or SLOT)
else:
    if work.get("runner_bind_pending"):
        sys.exit(0)  # §10.2: respawned after a rotation, not yet bound: which teammate is the runner is unknown
    # §10.2: the live runner is the name the lead bound in work.json (`team.sh runner bind`): after a
    # rotation the harness may have named the fresh one `runner-2` while the old one, still idling under
    # the binding's name, must not be nudged back to work.
    RUNNER = str(work.get("runner") or rc.get("name", "runner"))

def is_runner_itself(h):
    if h.get("teammate_name") != RUNNER:
        return False
    atype = h.get("agent_type")
    if atype:
        own = rc.get("agent_type", "delivery-runner").split(":", 1)[-1]
        return atype.split(":", 1)[-1] in (own, RUNNER, rc.get("name", "runner"))
    return not h.get("agent_id")  # agent_id without agent_type: still a subagent

if not is_runner_itself(hook):
    sys.exit(0)

if work.get("status") != "running":
    sys.exit(0)
# work.json's own waiting_on is the last wait set on any task, so it is not a scope-wide stop:
# readiness is judged per task below (a runner that skipped ahead past a gate must keep going).
# The one exception, SPEC §25.4 the session park: the 5-hour window is the account's, so while any
# task (its queue file, or work.json's) is parked on it until a planned resume still ahead, no task can
# run: let the runner idle, and the lead's session wake resumes it. A park past its planned resume has
# expired (the wake may have been lost with the lead's session): it holds nothing back, so the hook
# nudges the runner on, and its next claim or prompt samples again and lifts or renews the park.
def _when(v):
    try:
        return datetime.datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None
NOW = datetime.datetime.now(datetime.timezone.utc).timestamp()
def session_park(st):
    """'live' (parked, resume ahead or unknown), 'expired', or None (not a 5-hour park)."""
    if not isinstance(st, dict) or st.get("waiting_on") != "quota" or st.get("quota_class") != "session":
        return None
    due = _when(st.get("planned_resume_at"))
    return "expired" if due is not None and due <= NOW else "live"
def _read(f):
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return None
parks = [work] + [_read(f) for f in sorted((root / "tasks").glob("*.json"))]
if any(session_park(st) == "live" for st in parks):
    sys.exit(0)
done = (SLOTS[SLOT] or {}).get("tasks_done") if SLOT else work.get("runner_tasks_done")  # §16.5: per slot
if int(done or 0) >= int(rc.get("rotate_after_tasks", 4)):
    sys.exit(0)  # rotation due: let it idle and report; the lead rotates it (§10.2)
scope = list(work.get("scope") or [])
if not scope:
    sys.exit(0)

cwd = hook.get("cwd") or "."
r = subprocess.run([ccp, "--root", cwd, "tasks", "list", "--json"], cwd=cwd, capture_output=True, text=True)
try:
    tasks = {t["task_id"]: t for t in json.loads(r.stdout)}
except (ValueError, KeyError, TypeError):
    sys.exit(0)

def runtime_wait(tid):
    try:
        st = json.loads((root / "tasks" / f"{tid}.json").read_text())
    except (OSError, ValueError):
        return None
    if session_park(st) == "expired":
        return None  # SPEC §25.4: an expired 5-hour park holds nothing back
    return st.get("waiting_on") if isinstance(st, dict) else None  # any value, old names included, holds it

held = set()  # tasks an open spec question or an undecided gate blocks
for qp in (root / "questions").glob("sm-*.json"):
    if qp.name.endswith(".answer.json"):
        continue
    try:
        q = json.loads(qp.read_text())
    except (OSError, ValueError):
        continue
    if q.get("status") in ("open", "escalated"):
        held.update(q.get("blocks") or [])
for gp in (root / "escalations").glob("*/*.json"):
    try:
        g = json.loads(gp.read_text())
    except (OSError, ValueError):
        continue
    if g.get("to") == "design_seat" and g.get("status") in ("open", "waiting_operator"):
        held.add(g.get("task_id"))

def queue_status(tid):
    st = _read(root / "tasks" / f"{tid}.json")
    return st.get("status") if isinstance(st, dict) else None

# The task files come from the hook's cwd, a runner's worktree that can be
# behind master; the queue is written at once by close and drop, so its done or dropped wins.
settled = {tid for tid in scope if queue_status(tid) in ("done", "dropped")}

def done(tid):  # a dependency is met only by done, as `ccp tasks next` judges it (dropped meets nothing)
    return queue_status(tid) == "done" or tasks.get(tid, {}).get("status") == "done"

ready = []
for tid in scope:
    t = tasks.get(tid)
    if not t or tid in held or tid in settled or runtime_wait(tid):
        continue
    deps = [d.strip() for d in str(t.get("depends_on") or "").split(",") if d.strip() and d.strip() != "-"]
    # a legacy `blocked` reads as pending (SPEC §5.3); a legacy `in_progress` was started, so it is ready
    if t["status"] == "in_progress" or (t["status"] in ("pending", "blocked") and all(done(d) for d in deps)):
        ready.append(tid)

architect_due = None
try:
    pj = json.loads((Path(cwd) / "docs/delivery/plane.json").read_text())
except (OSError, ValueError, TypeError):
    pj = {}
has_architect = isinstance(pj, dict) and "architect" in pj
par = pj.get("parallel") if isinstance(pj, dict) and isinstance(pj.get("parallel"), dict) else {}
try:
    parallel_on = int(par.get("max_in_flight", 1)) > 1
except (TypeError, ValueError):
    parallel_on = False

def worker_open(tid):
    """A worker run of tid opened and not yet reported, abandoned or stopped: the runner waits on it.
    (A stopped run's worker is gone, so the runner does not wait on it, though ccp/runs.py counts it open.)"""
    d = root / "runs" / tid
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        r = _read(f)
        if isinstance(r, dict) and r.get("run_id") and not any(r.get(k) for k in ("abandoned_at", "reported_at", "stopped_at")):
            return True
    return False

n = None
if ready and (parallel_on or has_architect):  # one `ccp tasks next` for both uses (it samples no allowance)
    n = subprocess.run([ccp, "--root", cwd, "tasks", "next", "--scope", ",".join(scope), "--json"], cwd=cwd,
                       capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
if SLOT is not None and ready:
    # SPEC §16.5: a slot's runner holds one task: it is ready unless it waits (or its worker works); a
    # runner holding none is ready for the task `ccp tasks next` hands out now, to claim as its slot.
    def holder(tid):
        st = _read(root / "tasks" / f"{tid}.json")
        return st.get("lease_holder") if isinstance(st, dict) else None
    flight = [str(x) for x in work.get("in_flight") or []]
    mine = [t for t in flight if holder(t) == SLOT]
    if mine:
        ready = [t for t in mine if t in ready and not worker_open(t)]
    else:
        try:
            nxt = json.loads(n.stdout) if n is not None and n.returncode == 0 else None
        except ValueError:
            nxt = None
        claim = [nxt["task_id"]] if isinstance(nxt, dict) and nxt.get("task_id") in ready and nxt["task_id"] not in flight else []
        ready = claim
elif parallel_on and ready:
    # SPEC §16.5: a task the runner holds is ready unless its worker is still working; a task it does
    # not hold is ready only when `ccp tasks next` hands it out now (a free slot it may join).
    flight = {str(x) for x in work.get("in_flight") or []}
    held_ready = [t for t in ready if t in flight and not worker_open(t)]
    try:
        nxt = json.loads(n.stdout) if n.returncode == 0 else None
    except ValueError:
        nxt = None
    new = [nxt["task_id"]] if isinstance(nxt, dict) and nxt.get("task_id") in ready and nxt["task_id"] not in flight else []
    ready = held_ready + new
if n is not None and has_architect and n.returncode == 4:
    try:
        block = json.loads(n.stdout).get("architect") or {}
    except (ValueError, AttributeError):
        block = {}
    if block.get("kind") == "triage":
        ready = []  # the scope waits on the lead's triage
    elif block.get("kind") == "pass":
        architect_due = block.get("blocked")
        ready = ready or ["the architect pass"]  # the pass is work to do even when no task is ready

state_p = root / "observability" / (f"runner-idle-{SLOT}.json" if SLOT else "runner-idle.json")  # §16.5: per slot
try:
    state = json.loads(state_p.read_text())
except (OSError, ValueError):
    state = {}
key = ",".join(ready)
if not ready:
    state = {"key": "", "count": 0}
    code = 0
else:
    count = state.get("count", 0) + 1 if state.get("key") == key else 1
    limit = int(rc.get("idle_block_limit", 3))
    state = {"key": key, "count": count}
    code = 2 if count <= limit else 0
state_p.parent.mkdir(parents=True, exist_ok=True)
state_p.write_text(json.dumps(state) + "\n")
if code == 2 and architect_due:
    print(f"{architect_due}. Run `ccp architect run --detach` (SPEC §19.6), then `ccp tasks next` and carry on "
          f"with {ready[0]}.", file=sys.stderr)
elif code == 2 and SLOT and not [t for t in [str(x) for x in work.get("in_flight") or []]
                                  if (_read(root / "tasks" / f"{t}.json") or {}).get("lease_holder") == SLOT]:
    print(f"A slot is free: claim {ready[0]} as yours (`ccp tasks claim {ready[0]} --holder {SLOT}`) and carry on "
          "with it (SPEC §16.5).", file=sys.stderr)
elif code == 2:
    print(f"Scope not finished: {ready[0]} is ready and nothing waits on the lead or the operator. Carry on with it. "
          "If you cannot proceed, record why (waiting_on, a gate or a question) and report to the lead.", file=sys.stderr)
sys.exit(code)
PY
