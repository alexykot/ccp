"""Worktrees and environments (SPEC §12.1): `ccp wt create|remove|list|up|down|urls|gc|exec`.

The plane owns every worktree a task needs: the implementer's (`impl`, on `task/<id>`), the
reviewer's and verifier's (`rev`, `ver`, detached at the head they judge), a mutation copy (`mut`) and
a machine check (`mac`), and a throwaway at the merge base of a head and the integration branch
(`base`), made by `ccp wt create --kind base … -- COMMAND` only to run that command and removed again.
Each is named `<kind>-<nnnn>[-<n>]` under `worktrees.dir` in the main
checkout, gets `worktrees.links` linked in, and is recorded in `QUEUE_ROOT/worktrees/<name>.json`,
so close, drop, release and gc remove exactly what was made. A runner's own merge worktree
(`runner_worktree`, binding `runner.worktree`) is made here too, detached at the integration tip,
by `ccp tasks worktree` and the single runner's spawn; it is not a task's, so it is not recorded.

What a product needs beyond a git worktree (a database branch, a local stack) is a hook in plane.json
`env`: `setup` and `teardown` run when a worktree is made and removed, `up` and `down` start and stop
what it serves, and `urls` prints the URLs it serves as a JSON list of `{name, url}`, as many as the
product has. Each hook is a shell command template run in the worktree with a timeout; its fields
are also in the environment as `CCP_WT_<FIELD>`, and `ccp suite run` gives a lane's stages run in the
worktree the same variables (§14.2).

`ccp wt exec [NAME] -- ARGS` runs a worktree's own `bin/ccp`, so a change that adds a subcommand can
be tried before the installed `ccp` has it; `--print` prints that path instead.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ccp import refs
from ccp.envvars import for_child
from ccp.config import WT_FIELDS, Config, fill
from ccp.queue import QueueError, git, integration_branch, iso, load_task_state, read_json, write_json

KINDS: dict[str, tuple[str, str]] = {  # kind -> (default seat, default tag)
    "impl": ("impl", "main"), "rev": ("rev", "main"), "ver": ("ver", "main"),
    "mut": ("ver", "mut"), "mac": ("ver", "mac"), "base": ("ver", "base"),
}
NAME_RE = re.compile(r"^(impl|rev|ver|mut|mac|base)-[0-9]+(?:-[0-9]+)?$")
URL_RE = re.compile(r"^[a-z][a-z0-9+.-]*://\S+$")
OUT_CAP = 20000


# ---------------------------------------------------------------- paths and state

def main_checkout(cfg: Config) -> Path:
    from ccp.prompt import main_checkout as mc  # noqa: PLC0415

    return mc(cfg)


def base_dir(cfg: Config) -> Path | None:
    d = (cfg.worktrees or {}).get("dir")
    return main_checkout(cfg) / d if d else None


def state_dir(q: Path) -> Path:
    return q / "worktrees"


def state_path(q: Path, name: str) -> Path:
    return state_dir(q) / f"{name}.json"


def load(q: Path, name: str) -> dict[str, Any] | None:
    s = read_json(state_path(q, name), None)
    return s if isinstance(s, dict) else None


def save(q: Path, st: dict[str, Any]) -> None:
    state_dir(q).mkdir(parents=True, exist_ok=True)
    write_json(state_path(q, st["name"]), st)


def records(q: Path) -> list[dict[str, Any]]:
    d = state_dir(q)
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        s = read_json(f, None)
        if isinstance(s, dict) and s.get("name"):
            out.append(s)
    return out


def _queue_root() -> Path:
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        raise QueueError("set QUEUE_ROOT to this project's runtime queue (SPEC §12.2)", 2)
    return Path(q)


# ---------------------------------------------------------------- hooks

def context(cfg: Config, st: dict[str, Any]) -> dict[str, str]:
    return {"task_id": st["task_id"], "nnnn": st["nnnn"], "kind": st["kind"], "seat": st["seat"],
            "tag": st["tag"], "worktree": st["path"], "main_checkout": str(main_checkout(cfg)), "name": st["name"]}


def env_fields(cfg: Config, st: dict[str, Any]) -> dict[str, str]:
    """The worktree's fields as the environment gives them, raw: `CCP_WT_<FIELD>` (§12.2)."""
    return for_child({f"CCP_WT_{k.upper()}": v for k, v in context(cfg, st).items()})


def recorded_at(q: Path, root: Path) -> dict[str, Any] | None:
    """The record of the worktree `ccp wt` made at `root`, or None when it made none there."""
    here = root.resolve()
    for st in records(q):
        try:
            if st.get("path") and Path(str(st["path"])).resolve() == here:
                return st
        except (OSError, ValueError):
            continue
    return None


def run_cmd(line: str, cwd: Path, timeout: int, extra_env: dict[str, str] | None = None,
            log: Path | None = None, no_stdin: bool = False) -> tuple[int, str]:
    """Run a shell command in its own process group; on timeout the whole group is killed. Returns the
    exit code (124 on timeout) and the last OUT_CAP characters of its combined output.

    With `log`, output goes to that file, not a pipe, and the call returns when the shell exits: a
    service the command started in the background keeps running (and writing to the log) without
    holding the call open. With `log` or `no_stdin`, the command reads an empty stdin, not the caller's."""
    env = {**os.environ, **(extra_env or {})}
    if log is None:
        p = subprocess.Popen(["/bin/sh", "-c", line], cwd=str(cwd), env=env, stdout=subprocess.PIPE,
                             stdin=subprocess.DEVNULL if no_stdin else None,
                             stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
        try:
            out, _ = p.communicate(timeout=timeout)
            return p.returncode, (out or "")[-OUT_CAP:]
        except subprocess.TimeoutExpired:
            _killpg(p.pid)
            out, _ = p.communicate()
            return 124, ((out or "")[-OUT_CAP:] + f"\n(timed out after {timeout} s)").strip()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as f:
        f.write(f"\n--- {iso()} {line}\n".encode())
        f.flush()
        start = f.tell()
        p = subprocess.Popen(["/bin/sh", "-c", line], cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                             stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _killpg(p.pid)
            p.wait()
            code = 124
    with log.open("rb") as f:
        f.seek(start)
        out = f.read().decode(errors="replace")[-OUT_CAP:]
    if code == 124:
        out = (out + f"\n(timed out after {timeout} s)").strip()
    return code, out


def _killpg(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass


PATH_FIELDS = ("worktree", "main_checkout", "name")


def hook(cfg: Config, q: Path, name: str, st: dict[str, Any]) -> tuple[int, str] | None:
    """Run env.<name> in the worktree `st`; None when the product declares no such hook. The path
    fields are shell-quoted in the template (in the environment, `"$CCP_WT_WORKTREE"` and the rest are
    the raw values). Output goes to `QUEUE_ROOT/worktrees/<name>.<hook>.log`."""
    cmd = (cfg.env or {}).get(name)
    if not cmd:
        return None
    ctx = context(cfg, st)
    line = fill(cmd, {k: shlex.quote(v) if k in PATH_FIELDS else v for k, v in ctx.items()})
    return run_cmd(line, Path(st["path"]), int((cfg.env or {}).get("timeout_seconds") or 600),
                   env_fields(cfg, st), state_dir(q) / f"{st['name']}.{name}.log")


def parse_urls(out: str) -> list[dict[str, str]]:
    """env.urls output: a JSON list of {name, url}; any length. Raises ValueError when it is not."""
    try:
        data = json.loads(out.strip() or "[]")
    except ValueError as e:
        raise ValueError(f"env.urls did not print JSON ({e})") from None
    if not isinstance(data, list):
        raise ValueError("env.urls must print a JSON list of {name, url}")
    urls, seen = [], set()
    for i, u in enumerate(data):
        if not isinstance(u, dict) or not isinstance(u.get("name"), str) or not u["name"].strip() \
                or not isinstance(u.get("url"), str) or not URL_RE.match(u["url"]):
            raise ValueError(f"env.urls entry {i} is not {{name, url}} with a URL like http://host:port/path")
        if u["name"] in seen:
            raise ValueError(f"env.urls names {u['name']!r} twice")
        seen.add(u["name"])
        urls.append({"name": u["name"].strip(), "url": u["url"]})
    return urls


# ---------------------------------------------------------------- create / remove

def _exclude(main: Path, links: list[str]) -> None:
    """A linked path is a symlink in the worktree, which a `dir/` ignore pattern does not match: name
    it in the repository's info/exclude, so a worker's commit cannot pick it up."""
    r = git(main, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if r.returncode != 0 or not links:
        return
    ex = Path(r.stdout.strip()) / "info" / "exclude"
    have = ex.read_text().splitlines() if ex.is_file() else []
    want = [f"/{x.strip('/')}" for x in links if f"/{x.strip('/')}" not in have]
    if want:
        ex.parent.mkdir(parents=True, exist_ok=True)
        ex.write_text("\n".join(have + ["# control-plane: worktree links (SPEC §12.1)", *want]) + "\n")


def _link(cfg: Config, main: Path, path: Path) -> None:
    links = list((cfg.worktrees or {}).get("links") or [])
    _exclude(main, links)
    for link in links:
        src, dst = main / link, path / link
        if src.exists() and not dst.exists():
            dst.symlink_to(src)


def _free_name(cfg: Config, q: Path, kind: str, nnnn: str) -> str:
    base = base_dir(cfg)
    name, n = f"{kind}-{nnnn}", 1
    while load(q, name) or (base and (base / name).exists()):
        n += 1
        name = f"{kind}-{nnnn}-{n}"
    return name


def create(cfg: Config, q: Path, task_id: str, kind: str, sha: str | None = None, name: str | None = None,
           seat: str | None = None, tag: str | None = None) -> dict[str, Any]:
    """Make (or adopt) the worktree; run env.setup when it is new. A failed setup removes it again."""
    if kind not in KINDS:
        raise QueueError(f"--kind must be one of {', '.join(KINDS)}", 2)
    base = base_dir(cfg)
    if base is None:
        raise QueueError("plane.json names no worktrees.dir: this product has no plane-made worktrees (§12.1)", 2)
    nnnn = refs.ids(cfg).task_number(task_id)
    explicit = name is not None or kind == "impl"  # a default name may move on a race; a given one never
    if kind == "impl":
        name = name or f"impl-{nnnn}"
    else:
        if not sha:
            raise QueueError(f"--sha is required for a {kind} worktree: it is detached at the head it judges", 2)
        name = name or _free_name(cfg, q, kind, nnnn)
    if not NAME_RE.match(name) or not name.startswith(f"{kind}-"):
        raise QueueError(f"worktree name {name!r} is not {kind}-<nnnn>[-<n>]", 2)
    main = main_checkout(cfg)
    path = base / name
    st = load(q, name)
    if kind == "base" and (st or path.exists()):  # it is removed after its command: never one it did not make
        raise QueueError(f"worktree {name} exists: a base worktree is always made fresh; give another --name", 3)
    if st and Path(st["path"]).is_dir():
        _same_head(path, name, sha)
        return {**st, "created": False}
    d_seat, d_tag = KINDS[kind]
    st = {"name": name, "kind": kind, "task_id": task_id, "nnnn": nnnn, "seat": seat or d_seat, "tag": tag or d_tag,
          "path": str(path), "sha": sha, "branch": f"task/{task_id}" if kind == "impl" else None,
          "created_at": iso(), "state": "created", "urls": []}
    if path.is_dir():  # made before §12.1 recorded worktrees: adopt it, setup already happened
        _same_head(path, name, sha)
        st["adopted"] = True
        save(q, st)
        return {**st, "created": False}
    git(main, "fetch", "-q", "origin")
    git(main, "worktree", "prune")
    if kind == "impl":
        branch = st["branch"]
        st["base"] = f"origin/{integration_branch(q)}"
        exists = git(main, "rev-parse", "--verify", "-q", f"refs/heads/{branch}").returncode == 0
        args = ["worktree", "add", "-q", str(path), branch] if exists else \
            ["worktree", "add", "-q", "-b", branch, str(path), st["base"]]
    else:
        args = ["worktree", "add", "-q", "--detach", str(path), sha]
    r = git(main, *args)
    tries = 0
    while r.returncode != 0 and not explicit and tries < 5 and "already exists" in r.stderr:
        tries += 1  # another worker took the name meanwhile: the next free one
        name = _free_name(cfg, q, kind, nnnn)
        path = base / name
        st.update(name=name, path=str(path))
        args[-2] = str(path)
        r = git(main, *args)
    if r.returncode != 0:
        raise QueueError(f"git worktree add {name}: {r.stderr.strip()}", 1)
    _link(cfg, main, path)
    res = hook(cfg, q, "setup", st)
    if res and res[0] != 0:
        git(main, "worktree", "remove", "--force", str(path))
        raise QueueError(f"env.setup for {name} exited {res[0]}; the worktree is removed again:\n{res[1].strip()}", 1)
    save(q, st)
    return {**st, "created": True}


def _same_head(path: Path, name: str, sha: str | None) -> None:
    """An existing worktree is reused only at the head asked for: never silently at another."""
    if not sha:
        return
    head = git(path, "rev-parse", "HEAD").stdout.strip()
    want = git(path, "rev-parse", "--verify", "-q", f"{sha}^{{commit}}").stdout.strip() or sha
    if head and head != want:
        raise QueueError(f"worktree {name} exists at {head[:12]}, not {sha[:12]}: remove it (`ccp wt remove {name}`) "
                         "or give another --name", 3)


def remove(cfg: Config, q: Path, name: str) -> list[str]:
    """Stop (env.down, when up), tear down (env.teardown), remove the worktree, forget it. Failures
    are warnings: a worktree is removed even when its hooks fail."""
    st = load(q, name)
    warnings: list[str] = []
    base = base_dir(cfg)
    if st is None:
        if not base or not (base / name).is_dir():
            raise QueueError(f"no worktree {name} recorded in {state_dir(q)} or under worktrees.dir", 3)
        st = {"name": name, "path": str(base / name), "state": "created"}
    if st.get("task_id") and not Path(st["path"]).is_dir():
        if (cfg.env or {}).get("teardown") or (st.get("state") == "up" and (cfg.env or {}).get("down")):
            warnings.append(f"{st['path']} is gone: env.down and env.teardown for {name} were not run "
                            "(they run only in the worktree)")
    elif st.get("task_id"):
        if st.get("state") == "up" and (res := hook(cfg, q, "down", st)) and res[0] != 0:
            warnings.append(f"env.down for {name} exited {res[0]}: {res[1].strip()[-300:]}")
        if (res := hook(cfg, q, "teardown", st)) and res[0] != 0:
            warnings.append(f"env.teardown for {name} exited {res[0]}: {res[1].strip()[-300:]}")
    if Path(st["path"]).is_dir():
        r = git(main_checkout(cfg), "worktree", "remove", "--force", st["path"])
        if r.returncode != 0:
            warnings.append(f"worktree {st['path']}: {r.stderr.strip()}")
    state_path(q, name).unlink(missing_ok=True)
    return warnings


def remove_task(cfg: Config, q: Path, task_id: str) -> list[str]:
    """Every worktree recorded for the task, then any made before worktrees were recorded
    (`impl-`, `rev-`, `ver-` with its number) as a fallback."""
    warnings: list[str] = []
    for st in records(q):
        if st.get("task_id") == task_id:
            warnings += remove(cfg, q, st["name"])
    base = base_dir(cfg)
    if base and base.is_dir():
        nnnn = refs.ids(cfg).task_number(task_id)
        old = sorted(base.glob(f"impl-{nnnn}")) + sorted(base.glob(f"rev-{nnnn}*")) + sorted(base.glob(f"ver-{nnnn}*"))
        for wt in old:
            if wt.is_dir():
                r = git(main_checkout(cfg), "worktree", "remove", "--force", str(wt))
                if r.returncode != 0:
                    warnings.append(f"worktree {wt}: {r.stderr.strip()}")
    return warnings


# ---------------------------------------------------------------- a command on the merge base

def merge_base(cfg: Config, q: Path, head: str) -> str:
    """The merge base of `head` and `origin/<integration>`, after a fetch. Exit 3 when there is none."""
    main = main_checkout(cfg)
    git(main, "fetch", "-q", "origin")
    ref = f"origin/{integration_branch(q)}"
    r = git(main, "merge-base", f"{head}^{{commit}}", ref)
    if r.returncode != 0 or not r.stdout.strip():
        raise QueueError(f"no merge base of {head[:12]} and {ref}: the head is not fetched, "
                         "or it shares no history with the integration branch", 3)
    return r.stdout.strip()


def run_on_base(cfg: Config, q: Path, task_id: str, head: str, command: list[str], name: str | None = None,
                seat: str | None = None, tag: str | None = None) -> dict[str, Any]:
    """A `base` worktree (§12.1): made detached at the merge base of `head` and the integration branch,
    `command` run there (argv, no shell) with its output passed through as it comes, then removed
    again whatever the command did. Returns the result; its `exit` is the command's exit code (127
    when it cannot be found, 126 when it cannot run, 128 + N when signal N ended it)."""
    if not command:
        raise QueueError("a base worktree runs a command: give it after `--`", 2)
    if not head:
        raise QueueError("--sha is required for a base worktree: the head whose merge base it checks out", 2)
    sha = merge_base(cfg, q, head)
    st = {k: v for k, v in create(cfg, q, task_id, "base", sha, name, seat, tag).items() if k != "created"}
    st["head"] = head
    save(q, st)
    path = Path(st["path"])
    started = time.monotonic()
    warnings: list[str] = []
    try:
        try:
            p = subprocess.Popen(command, cwd=str(path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 stdin=subprocess.DEVNULL, text=True, errors="replace")
        except OSError as e:
            print(f"ccp wt create: {command[0]}: {e}", file=sys.stderr)
            code = 127 if isinstance(e, FileNotFoundError) else 126
        else:
            assert p.stdout is not None
            for line in p.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
            p.wait()
            code = p.returncode if p.returncode >= 0 else 128 - p.returncode
    finally:
        warnings += remove(cfg, q, st["name"])
    return {"ok": code == 0, "name": st["name"], "task_id": task_id, "head": head, "merge_base": sha,
            "integration": f"origin/{integration_branch(q)}", "exit": code,
            "seconds": round(time.monotonic() - started, 1), "removed": not path.exists(), "warnings": warnings}


# ---------------------------------------------------------------- a runner's own worktree

def main_of(checkout: Path) -> Path:
    """The main checkout of the repository `checkout` belongs to (itself when git cannot say)."""
    r = git(checkout, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(r.stdout.strip()).parent if r.returncode == 0 and r.stdout.strip() else checkout


def runner_worktree(main: Path, path: str, integ: str) -> tuple[Path, bool]:
    """§12.1: a runner's own merge worktree at `path` (relative to the main checkout `main`), made
    detached at `origin/<integ>` when it is missing and left alone when it exists. Returns (path, made).
    Not recorded under `worktrees/`: it belongs to a runner, not to a task. A non-empty directory there
    that is no working tree refuses (exit 2); a failed `git worktree add` exits 1."""
    wt = Path(path) if Path(path).is_absolute() else main / path
    if (wt / ".git").exists() and git(wt, "rev-parse", "--is-inside-work-tree").stdout.strip() == "true":
        return wt, False
    if wt.exists() and any(wt.iterdir()):
        raise QueueError(f"{wt} exists and is not a working tree of the product: move it away first", 2)
    git(main, "worktree", "prune")  # a worktree removed by hand still registered blocks the add
    git(main, "fetch", "-q", "origin")
    git(main, "worktree", "add", "-q", "--detach", str(wt), f"origin/{integ}", check=True)
    return wt, True


# ---------------------------------------------------------------- up / down / urls

def _need(q: Path, name: str) -> dict[str, Any]:
    st = load(q, name)
    if not st:
        raise QueueError(f"no worktree {name} recorded: make it with `ccp wt create` (§12.1)", 3)
    if not Path(st["path"]).is_dir():
        raise QueueError(f"worktree {name} is recorded but {st['path']} is gone: `ccp wt gc` forgets it", 3)
    return st


def urls(cfg: Config, q: Path, name: str, st: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Run env.urls and record what it prints; without the hook, the recorded list (empty)."""
    st = st or _need(q, name)
    res = hook(cfg, q, "urls", st)
    if res is None:
        return list(st.get("urls") or [])
    if res[0] != 0:
        raise QueueError(f"env.urls for {name} exited {res[0]}:\n{res[1].strip()}", 1)
    try:
        got = parse_urls(res[1])
    except ValueError as e:
        raise QueueError(str(e), 1) from None
    st["urls"] = got
    save(q, st)
    return got


def up(cfg: Config, q: Path, name: str) -> dict[str, Any]:
    st = _need(q, name)
    res = hook(cfg, q, "up", st)
    if res and res[0] != 0:
        st.update(state="down", urls=[])
        save(q, st)
        raise QueueError(f"env.up for {name} exited {res[0]}; it is down:\n{res[1].strip()}", 1)
    st.update(state="up", up_at=iso())
    save(q, st)
    warnings = []
    try:
        got = urls(cfg, q, name, st)
    except QueueError as e:
        got, warnings = [], [f"up, but its URLs are not recorded: {e}"]
    return {"ok": True, "name": name, "state": "up", "hook": res is not None, "urls": got, "warnings": warnings}


def down(cfg: Config, q: Path, name: str) -> dict[str, Any]:
    st = _need(q, name)
    res = hook(cfg, q, "down", st)
    warnings = [f"env.down for {name} exited {res[0]}: {res[1].strip()[-300:]}"] if res and res[0] != 0 else []
    st.update(state="down", urls=[])
    save(q, st)
    return {"ok": True, "name": name, "state": "down", "hook": res is not None, "warnings": warnings}


# ---------------------------------------------------------------- list / gc

def listing(cfg: Config, q: Path, task_id: str | None = None) -> list[dict[str, Any]]:
    recs = [s for s in records(q) if not task_id or s.get("task_id") == task_id]
    out = [{**s, "exists": Path(s["path"]).is_dir()} for s in recs]
    base = base_dir(cfg)
    known = {s["name"] for s in recs}
    if base and base.is_dir() and not task_id:
        for p in sorted(base.iterdir()):
            if p.is_dir() and NAME_RE.match(p.name) and p.name not in known:
                out.append({"name": p.name, "path": str(p), "exists": True, "recorded": False})
    return out


def gc(cfg: Config, q: Path) -> dict[str, Any]:
    """Prune git's worktree list; forget records whose worktree is gone; remove the worktrees of tasks
    that are done or dropped in the queue and leased by no one (drop and release keep them, §12.1)."""
    forgot, removed, warnings = [], [], []
    git(main_checkout(cfg), "worktree", "prune")
    for st in records(q):
        if not Path(st["path"]).is_dir():
            state_path(q, st["name"]).unlink(missing_ok=True)
            forgot.append(st["name"])
            continue
        tq = load_task_state(q, st.get("task_id") or "")
        if str(tq.get("status") or "") in ("done", "dropped") and not tq.get("lease_holder"):
            warnings += remove(cfg, q, st["name"])
            removed.append(st["name"])
    return {"ok": True, "forgot": forgot, "removed": removed, "warnings": warnings}


# ---------------------------------------------------------------- the worktree's own ccp

def own_ccp(root: Path | None, name: str | None = None) -> Path:
    """The `bin/ccp` of worktree NAME (recorded in QUEUE_ROOT), else of `root`, the checkout this `ccp`
    resolved (--root, $CCP_ROOT, or the working directory's git toplevel). Exit 2 for a NAME that is
    not a worktree name, 3 when the worktree is not recorded or carries no `bin/ccp`."""
    if name is not None:
        if not NAME_RE.match(name):
            raise QueueError(f"{name!r} is not a worktree name: usage `ccp wt exec [NAME] -- ARGS` "
                             "(the arguments go after `--`)", 2)
        path = Path(_need(_queue_root(), name)["path"])
    elif root is not None:
        path = root
    else:
        raise QueueError("name a worktree or a checkout", 2)
    exe = path / "bin" / "ccp"
    if not exe.is_file():
        raise QueueError(f"{path} has no bin/ccp: it is not a checkout of the plane", 3)
    return exe


def exec_ccp(exe: Path, args: list[str]) -> int:
    """Run `exe` with `args`, in the caller's working directory and environment, its output the caller's.
    Returns its exit code (128 + N when signal N ended it)."""
    code = subprocess.call([sys.executable, str(exe), *args])
    return code if code >= 0 else 128 - code


# ---------------------------------------------------------------- auth probes (§30)

def auth_check(cfg: Config, q: Path | None) -> dict[str, Any]:
    """Run plane.json auth_check.probes (each a command; exit 0 = ok). Writes QUEUE_ROOT/auth/status.json."""
    au = cfg.auth_check or {}
    results = []
    for p in au.get("probes") or []:
        code, out = run_cmd(p["cmd"], cfg.root, int(au.get("timeout_seconds") or 60))
        from ccp.queue import lib  # noqa: PLC0415
        detail = out.strip()[-300:]
        if lib.looks_like_secret(detail):  # §30: never store a credential, even one a probe printed
            detail = "(output withheld: it looks like a credential)"
        results.append({"id": p["id"], "ok": code == 0, "exit": code, "detail": detail})
    body = {"ok": all(r["ok"] for r in results), "checked_at": iso(), "probes": results}
    if q is not None and results:
        (q / "auth").mkdir(parents=True, exist_ok=True)
        write_json(q / "auth" / "status.json", body)
    return body


__all__ = ["KINDS", "WT_FIELDS", "auth_check", "create", "down", "exec_ccp", "gc", "listing", "merge_base", "own_ccp",
           "remove", "remove_task", "run_on_base", "up", "urls"]
