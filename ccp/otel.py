"""`ccp otel serve` (SPEC §24.2, §24): a local OTLP/HTTP (JSON) receiver for Claude Code's telemetry.

It keeps two kinds of record, and only their numbers and ids, never prompt or response content:

- `claude_code.api_request` log records → `usage-requests.jsonl`: model, effort, `query_source`, the
  four token counts, `cost_usd`, `duration_ms`, `request_id`, `session.id`;
- `claude_code.llm_request` trace spans → `usage-spans.jsonl`: `request_id`, `agent_id` (a worker's
  id, or `<teammate>@session-…`), model, effort, the token counts.

The six keys that turn telemetry on live in the USER settings (`~/.claude/settings.json`, or the
shell; `ccp otel env`), for every Claude Code session on the Mac: Claude Code ignores them in a
project's settings (§24.3). A product's settings carry only `OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=<id>`
(`ccp otel env --project ID`), which Claude Code honours there. Each record is routed, in this order:

1. the resource attribute `ccp.project_id` (the product's settings, or a process env), to that project's queue
   (this plane's binding `projects/<project_id>.yaml`);
2. the record's `session.id` → the session's `cwd` (its transcript under `~/.claude/projects/`) →
   the binding whose `product_root` holds that cwd (a worktree under it, or a git worktree of it);
3. otherwise the system sink (`~/.local/state/control-plane/telemetry/`, daily files, kept
   `KEEP_DAYS`), labelled with the session id and cwd: `ccp usage --system` reads it.

It binds to localhost only. Metrics are accepted and ignored.

  ccp otel serve [--port N]             the receiver (launchd runs it: `ccp otel install`)
  ccp otel env [--port N]               the user-settings `env` block (static, no project)
  ccp otel env --project ID             that, and the product's block (OTEL_RESOURCE_ATTRIBUTES only)
  ccp otel install|uninstall|status     the launchd agent on the Mac; status checks the user settings
"""
from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp.queue import PLANE, launchd_bootout, launchd_reload, run_ccp, run_ccp_warning

DEFAULT_PORT = 4318
MAX_BODY = 16 * 1024 * 1024  # on the wire, and again after gzip
# cache_creation_{5m,1h}_tokens: the cache-write split by lifetime (Claude Code ≥2.1.308), so a seat's
# `experimental.cacheTtl: 1h` (§2) can be seen to take effect.
TTL_SPLIT = ("cache_creation_5m_tokens", "cache_creation_1h_tokens")
NUMERIC = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", *TTL_SPLIT, "cost_usd",
           "duration_ms")
PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
REQUEST_FIELDS = ("model", "effort", "query_source", "agent.name", "request_id", "session.id", "prompt.id",
                  "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens", *TTL_SPLIT, "cost_usd",
                  "duration_ms", "speed")
SPAN_FIELDS = ("request_id", "agent_id", "llm_request.context", "model", "effort", "session.id",
               "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")
def launchd_label() -> str:
    """The receiver's launchd label: `<CCP_LAUNCHD_PREFIX>.control-plane.otel` (default prefix `dev.ccp`)."""
    from ccp.queue import launchd_prefix  # noqa: PLC0415
    return f"{launchd_prefix()}.control-plane.otel"
SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")  # a session id names a file: no path parts
TRANSCRIPT_LINES = 200  # the first records of a transcript carry its cwd
KEEP_DAYS = 90  # system-sink day files older than this are deleted
SEAT_RE = re.compile(r"^[a-z0-9][a-z0-9:-]{0,63}$")  # resource ccp.seat


def _value(v: dict[str, Any]) -> Any:
    if not isinstance(v, dict) or not v:
        return None
    if "intValue" in v:
        try:
            return int(v["intValue"])
        except (TypeError, ValueError):
            return None
    if "doubleValue" in v:
        return v["doubleValue"]
    for k in ("stringValue", "boolValue"):
        if k in v:
            return v[k]
    return None


def attrs(lst: Any) -> dict[str, Any]:
    return {a["key"]: _value(a.get("value") or {}) for a in lst or [] if isinstance(a, dict) and "key" in a}


def _iso(nanos: Any) -> str | None:
    try:
        return datetime.fromtimestamp(int(nanos) / 1e9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (TypeError, ValueError, OSError):
        return None


def _num(v: Any) -> Any:
    """A number, also from a numeric string (some attributes arrive as stringValue); else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        f = float(str(v))
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def _row(a: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    row = {}
    for k in fields:
        v = a.get(k)
        if v is None:
            continue
        row[k.replace(".", "_")] = _num(v) if k in NUMERIC else v
    return row


def bindings_dir() -> Path:
    return Path(envvar("CCP_BINDINGS_DIR") or PLANE / "projects")


def claude_projects_dir() -> Path:
    """Claude Code's transcripts, one folder per cwd (`CCP_CLAUDE_PROJECTS_DIR` for tests)."""
    return Path(envvar("CCP_CLAUDE_PROJECTS_DIR") or Path.home() / ".claude" / "projects")


def telemetry_dir() -> Path:
    """The system sink: outside every product queue and every git checkout (`CCP_TELEMETRY_DIR`)."""
    return Path(envvar("CCP_TELEMETRY_DIR") or Path.home() / ".local" / "state" / "control-plane" / "telemetry")


def user_settings_path() -> Path:
    return Path(envvar("CCP_USER_SETTINGS") or Path.home() / ".claude" / "settings.json")


def _scalar(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*([^#\n]+)", text, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def queue_for(project_id: Any, cache: dict[str, Path | None]) -> Path | None:
    """The project's queue. Only hits are cached: a project bound after the receiver starts is
    found on its next record."""
    pid = str(project_id or "")
    if cache.get(pid) is not None:
        return cache[pid]
    q = None
    if PROJECT_RE.match(pid):
        b = bindings_dir() / f"{pid}.yaml"
        if b.is_file():
            raw = _scalar(b.read_text(), "queue_root")
            path = Path(raw) if raw else None
            q = path if path and path.is_dir() else None
    if q is not None:
        cache[pid] = q
    return q


def is_plane_repo(root: str | Path) -> bool:
    """True when `root` is a checkout of the control plane itself (it manages its own development):
    its marketplace names the `control-plane` plugin and it carries the `ccp` package. Usage there is
    plane development, not product work, and counts with the system sink."""
    r = Path(root)
    try:
        mk = json.loads((r / ".claude-plugin" / "marketplace.json").read_text())
    except (OSError, ValueError):
        return False
    return isinstance(mk, dict) and mk.get("name") == "ccp" and (r / "ccp" / "refs.py").is_file()


def bindings() -> list[tuple[str, str, Path]]:
    """(project_id, realpath of product_root, queue) for each binding that names both."""
    out = []
    d = bindings_dir()
    for b in sorted(d.glob("*.yaml")) if d.is_dir() else []:
        try:
            text = b.read_text()
        except OSError:
            continue
        pid = _scalar(text, "project_id") or b.stem
        root, q = _scalar(text, "product_root"), _scalar(text, "queue_root")
        if PROJECT_RE.match(pid) and root and q and Path(q).is_dir():
            out.append((pid, os.path.realpath(root), Path(q)))
    return out


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _main_checkout(cwd: str) -> str | None:
    """A git worktree's main checkout, read from its `.git` file (`gitdir: <main>/.git/worktrees/<name>`)
    without running git. None for a main checkout or no repo."""
    p = Path(cwd)
    for d in (p, *p.parents):
        g = d / ".git"
        if g.is_dir():
            return None
        if g.is_file():
            try:
                m = re.match(r"gitdir:\s*(.+)", g.read_text().strip())
            except OSError:
                return None
            if not m:
                return None
            gd = Path(os.path.realpath(d / m.group(1).strip()))
            if gd.parent.name == "worktrees" and gd.parent.parent.name == ".git":
                return str(gd.parent.parent.parent)
            return None
    return None


def project_for_cwd(cwd: str, binds: list[tuple[str, str, Path]]) -> tuple[str, Path] | None:
    """The binding whose product_root holds cwd (equal or under it, or cwd is a git worktree of it),
    comparing realpaths. The deepest root wins when roots nest."""
    real = os.path.realpath(cwd)
    cands = [real] + [m for m in (_main_checkout(real),) if m]
    best: tuple[str, Path, str] | None = None
    for pid, root, q in binds:
        if any(_under(c, root) for c in cands) and (best is None or len(root) > len(best[2])):
            best = (pid, q, root)
    return (best[0], best[1]) if best else None


def _first_cwd(f: Path, sid: str) -> str | None:
    try:
        fh = f.open("rb")
    except OSError:
        return None
    with fh:
        for i, line in enumerate(fh):
            if i >= TRANSCRIPT_LINES:
                break
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and isinstance(r.get("cwd"), str) and r["cwd"] \
                    and str(r.get("sessionId") or sid) == sid:
                return r["cwd"]
    return None


def transcript_cwd(session_id: Any, projects: Path | None = None) -> str | None:
    """The cwd a session runs in, from its transcript `<projects>/<slug>/<session_id>.jsonl` (the first
    record that carries `cwd`). The slug is the cwd with `/` and `.` as `-`, but the recorded cwd is
    what counts, so every folder is looked in. Subagents and in-process teammates write
    `<slug>/<lead session>/subagents/agent-*.jsonl` under the lead's `sessionId`, and their telemetry
    carries the lead's `session.id`, so they resolve through the lead's transcript (§24)."""
    sid = str(session_id or "")
    if not SESSION_RE.match(sid):
        return None
    base = projects or claude_projects_dir()
    try:
        dirs = [d for d in base.iterdir() if d.is_dir()]
    except OSError:
        return None
    for d in dirs:
        cwd = _first_cwd(d / f"{sid}.jsonl", sid)
        if cwd:
            return cwd
    return None


def _resource(res: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
    """The resource's project id, and the labels it gives each row: `seat` from `ccp.seat`, which the
    plane's headless launches set (§24)."""
    a = attrs((res or {}).get("attributes"))
    seat = a.get("ccp.seat")
    pid = a.get("ccp.project_id")
    return pid, ({"seat": seat} if isinstance(seat, str) and SEAT_RE.match(seat) else {})


def fold_logs(body: dict[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    out = []
    for rl in body.get("resourceLogs") or []:
        pid, extra = _resource(rl.get("resource"))
        for sl in rl.get("scopeLogs") or []:
            for lr in sl.get("logRecords") or []:
                a = attrs(lr.get("attributes"))
                if a.get("event.name") != "api_request":
                    continue
                row = {"at": _iso(lr.get("timeUnixNano") or lr.get("observedTimeUnixNano")) or a.get("event.timestamp")}
                row.update(_row(a, REQUEST_FIELDS))
                row.update(extra)
                out.append((pid, row))
    return out


def fold_spans(body: dict[str, Any]) -> list[tuple[Any, dict[str, Any]]]:
    out = []
    for rs in body.get("resourceSpans") or []:
        pid, extra = _resource(rs.get("resource"))
        for ss in rs.get("scopeSpans") or []:
            for sp in ss.get("spans") or []:
                if sp.get("name") != "claude_code.llm_request":
                    continue
                a = attrs(sp.get("attributes"))
                row = {"at": _iso(sp.get("startTimeUnixNano")), "end": _iso(sp.get("endTimeUnixNano"))}
                row.update(_row(a, SPAN_FIELDS))
                row.update(extra)
                out.append((pid, row))
    return out


class Sink:
    """Appends folded rows to the queue each routes to (§24.3), or to the system sink.

    A session's cwd is cached once found; a miss is not, since the transcript may not exist at a
    session's first export: it is looked up again once `miss_ttl` seconds pass. Rows of a session
    that has not resolved yet wait in a bounded buffer for up to `hold_s` seconds before they go to
    the system sink, so a late transcript still routes them to their project. A session's route is
    cached per bindings generation."""

    miss_ttl = 10.0
    bindings_ttl = 30.0
    hold_s = 60.0
    max_pending = 5000

    def __init__(self, projects: Path | None = None, system_dir: Path | None = None) -> None:
        self.cache: dict[str, Path | None] = {}
        self.projects = projects
        self.system_dir = system_dir
        self.sessions: dict[str, str] = {}  # session id → cwd (hits only)
        self.misses: dict[str, float] = {}  # session id → when it last missed (monotonic)
        self.routes: dict[str, tuple[int, tuple[str, Path] | None]] = {}  # session id → (generation, hit)
        self.pending: dict[str, list[tuple[float, Any, str, dict[str, Any]]]] = {}  # sid → (since, pid, file, row)
        self._binds: list[tuple[str, str, Path]] | None = None
        self._binds_at = 0.0
        self.gen = 0
        self._pruned: str | None = None
        self.lock = threading.Lock()
        self.written_by = {"project": 0, "system": 0}
        self.routed_by = {"project_id": 0, "session": 0}
        self.unresolved = 0  # rows kept in the system sink whose session gave no cwd
        self.dropped = 0  # rows that could not be written at all
        self.refused = 0  # bodies that were not OTLP JSON (415/400/413)

    @property
    def written(self) -> int:
        return sum(self.written_by.values())

    def session_cwd(self, sid: Any) -> str | None:
        sid = str(sid or "")
        if not sid:
            return None
        if sid in self.sessions:
            return self.sessions[sid]
        t = self.misses.get(sid)
        if t is not None and time.monotonic() - t < self.miss_ttl:
            return None
        cwd = transcript_cwd(sid, self.projects)
        if cwd:
            self.sessions[sid] = cwd
            self.misses.pop(sid, None)
        else:
            if len(self.misses) > 10000:
                self.misses.clear()
            self.misses[sid] = time.monotonic()
        return cwd

    def binds(self) -> list[tuple[str, str, Path]]:
        if self._binds is None or time.monotonic() - self._binds_at >= self.bindings_ttl:
            new = bindings()
            if new != self._binds:
                self.gen += 1
            self._binds, self._binds_at = new, time.monotonic()
        return self._binds

    def session_project(self, sid: str, cwd: str) -> tuple[str, Path] | None:
        binds = self.binds()
        hit = self.routes.get(sid)
        if hit is None or hit[0] != self.gen:
            if len(self.routes) > 10000:
                self.routes.clear()
            hit = (self.gen, project_for_cwd(cwd, binds))
            self.routes[sid] = hit
        return hit[1]

    def route(self, pid: Any, row: dict[str, Any]) -> tuple[Path | None, dict[str, Any]]:
        """(queue or None for the system sink, the labels the row gets)."""
        sid = row.get("session_id")
        if pid:
            q = queue_for(pid, self.cache)
            if q is not None:
                cwd = self.session_cwd(sid)
                return q, {"project_id": str(pid), "routed_by": "project_id", **({"cwd": cwd} if cwd else {})}
        cwd = self.session_cwd(sid)
        if cwd:
            hit = self.session_project(str(sid), cwd)
            if hit:
                return hit[1], {"project_id": hit[0], "routed_by": "session", "cwd": cwd}
        unbound = str(pid) if pid and len(str(pid)) <= 64 and PROJECT_RE.match(str(pid)) else None
        return None, {"cwd": cwd, **({"project_id_unbound": unbound} if unbound else {})}

    def _system_file(self, name: str) -> Path:
        d = self.system_dir or telemetry_dir()
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._pruned != day:
            self._pruned = day
            prune(d, KEEP_DAYS)
        return d / name.replace(".jsonl", f"-{day}.jsonl")

    def _place(self, pid: Any, name: str, row: dict[str, Any], out: dict[tuple[Path, str], list[str]],
               final: bool) -> bool:
        """Route one row into `out`. False when it should wait for its session (not `final`)."""
        q, labels = self.route(pid, row)
        if q is None and not labels.get("cwd") and not final and SESSION_RE.match(str(row.get("session_id") or "")):
            return False
        if q is not None:
            self.routed_by[labels["routed_by"]] += 1
            p, kind = q / "board" / name, "project"
        else:
            if not labels.get("cwd"):
                self.unresolved += 1
            p, kind = self._system_file(name), "system"
        out.setdefault((p, kind), []).append(json.dumps({**labels, **row}))
        return True

    def _retry(self, out: dict[tuple[Path, str], list[str]], flush: bool = False) -> None:
        now = time.monotonic()
        for sid in list(self.pending):
            rows = self.pending[sid]
            old = flush or now - rows[0][0] >= self.hold_s
            if not old and self.session_cwd(sid) is None:
                continue
            del self.pending[sid]
            for _since, pid, name, row in rows:
                self._place(pid, name, row, out, final=True)

    def _emit(self, out: dict[tuple[Path, str], list[str]]) -> int:
        n = 0
        for (p, kind), lines in out.items():
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with p.open("a") as fh:
                    fh.write("".join(x + "\n" for x in lines))
            except OSError as e:
                self.dropped += len(lines)
                print(f"ccp otel: could not write {len(lines)} row(s) to {p}: {e}", file=sys.stderr, flush=True)
                continue
            self.written_by[kind] += len(lines)
            n += len(lines)
        return n

    def _npending(self) -> int:
        return sum(len(v) for v in self.pending.values())

    def write(self, rows: list[tuple[Any, dict[str, Any]]], name: str) -> int:
        out: dict[tuple[Path, str], list[str]] = {}
        with self.lock:
            before = self.unresolved
            self._retry(out)
            now = time.monotonic()
            for pid, row in rows:
                sid = str(row.get("session_id") or "")
                if sid in self.pending or not self._place(pid, name, row, out, final=False):
                    self.pending.setdefault(sid, []).append((now, pid, name, row))
            while self._npending() > self.max_pending:  # bounded: the oldest session goes to the system sink
                sid = min(self.pending, key=lambda s: self.pending[s][0][0])
                for _since, pid, nm, row in self.pending.pop(sid):
                    self._place(pid, nm, row, out, final=True)
            n = self._emit(out)
            self._note(before)
        return n

    def tick(self, flush: bool = False) -> int:
        """Retry waiting sessions; `flush` writes every waiting row now (shutdown)."""
        out: dict[tuple[Path, str], list[str]] = {}
        with self.lock:
            before = self.unresolved
            self._retry(out, flush)
            n = self._emit(out)
            self._note(before)
        return n

    def _note(self, before: int) -> None:
        if self.unresolved != before and any(before < m <= self.unresolved for m in (1, 10, 100, 1000, 10000, 100000)):
            print(f"ccp otel: {self.unresolved} row(s) kept in the system sink with no session cwd",
                  file=sys.stderr, flush=True)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {"ok": True, "written": self.written, "written_by_sink": dict(self.written_by),
                    "routed_by": dict(self.routed_by), "unresolved": self.unresolved, "pending": self._npending(),
                    "dropped": self.dropped, "refused": self.refused, "sessions_known": len(self.sessions),
                    "system_sink": str(self.system_dir or telemetry_dir())}


def prune(d: Path, keep_days: int) -> list[str]:
    """Delete system-sink day files older than keep_days, so the sink cannot grow unbounded."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    gone = []
    for f in d.glob("usage-*-????-??-??.jsonl") if d.is_dir() else []:
        if f.stem[-10:] < cutoff:
            try:
                f.unlink()
                gone.append(f.name)
            except OSError:
                pass
    return gone


def handler(sink: Sink) -> type[http.server.BaseHTTPRequestHandler]:
    class H(http.server.BaseHTTPRequestHandler):
        def _reply(self, code: int, body: dict[str, Any] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body or {}).encode())

        def _chunked(self) -> bytes:
            """A Transfer-Encoding: chunked body, capped at MAX_BODY."""
            out = b""
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    self.rfile.readline()
                    return out
                out += self.rfile.read(size)
                self.rfile.readline()
                if len(out) > MAX_BODY:
                    raise ValueError("chunked body too large")

        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/status"):
                self._reply(200, sink.status())
            else:
                self._reply(404)

        def do_POST(self) -> None:  # noqa: N802
            chunked = "chunked" in str(self.headers.get("Transfer-Encoding") or "").lower()
            try:
                n = int(self.headers.get("Content-Length") or "") if not chunked else 0
            except ValueError:
                n = -1
            if not 0 <= n <= MAX_BODY:
                sink.refused += 1
                self._reply(413 if n > MAX_BODY else 411)
                return
            # Exactly application/json: a browser can POST text/plain cross-origin to 127.0.0.1 without a preflight.
            if str(self.headers.get("Content-Type") or "").split(";")[0].strip().lower() != "application/json":
                # An exporter left on http/protobuf must not look healthy while nothing is kept (docs/design/telemetry.md).
                self.rfile.read(n)
                sink.refused += 1
                self._reply(415, {"error": "send OTLP as http/json (OTEL_EXPORTER_OTLP_PROTOCOL=http/json)"})
                return
            try:
                raw = self._chunked() if chunked else self.rfile.read(n)
                if self.headers.get("Content-Encoding") == "gzip":
                    d = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    raw = d.decompress(raw, MAX_BODY)
                    if d.unconsumed_tail:
                        raise ValueError("body too large after gzip")
                body = json.loads(raw) if raw else {}
            except (OSError, ValueError, zlib.error):
                body = None
            if not isinstance(body, dict):
                sink.refused += 1
                self._reply(400, {"error": "not an OTLP JSON object"})
                return
            if self.path.startswith("/v1/logs"):
                sink.write(fold_logs(body), "usage-requests.jsonl")
            elif self.path.startswith("/v1/traces"):
                sink.write(fold_spans(body), "usage-spans.jsonl")
            self._reply(200)

        def log_message(self, *_a: Any) -> None:
            pass

    return H


def serve(port: int) -> int:
    import signal  # noqa: PLC0415
    sink = Sink()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler(sink))
    stop = threading.Event()

    def ticker() -> None:
        while not stop.wait(5):
            try:
                sink.tick()
            except Exception as exc:  # noqa: BLE001  (a dead ticker would leave held rows waiting for the next POST)
                print(f"ccp otel: tick failed: {exc}", file=sys.stderr, flush=True)
    threading.Thread(target=ticker, daemon=True).start()
    # launchd stops the agent with SIGTERM: shut down cleanly so the waiting rows are written.
    signal.signal(signal.SIGTERM, lambda *_a: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(f"ccp otel: listening on 127.0.0.1:{port}", file=sys.stderr, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        sink.tick(flush=True)
    return 0


def env_block(port: int) -> dict[str, str]:
    """The static `env` the USER settings (`~/.claude/settings.json`, or the shell) carry, for every
    session (§24): the six keys that turn telemetry on. Claude Code ignores them in a project's
    settings (a project may only turn telemetry off) and warns."""
    return {"CLAUDE_CODE_ENABLE_TELEMETRY": "1", "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
            "OTEL_LOGS_EXPORTER": "otlp", "OTEL_TRACES_EXPORTER": "otlp",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
            "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{port}"}


def project_env(project_id: str) -> dict[str, str]:
    """The one telemetry key a product's `.claude/settings.json` carries (§24.3): Claude Code honours
    `OTEL_RESOURCE_ATTRIBUTES` there, and the receiver routes by it ahead of the session's cwd."""
    return {"OTEL_RESOURCE_ATTRIBUTES": f"ccp.project_id={project_id}"}


def env_for_project(project_id: str, port: int) -> dict[str, Any]:
    """`ccp otel env --project ID`: which block goes where. Raises ValueError for an unbound id."""
    from ccp.config import PROJECT_ID_RE  # noqa: PLC0415
    b = bindings_dir() / f"{project_id}.yaml"
    if not PROJECT_ID_RE.match(project_id) or not b.is_file():
        raise ValueError(f"{project_id!r} is not a bound project ({bindings_dir()}/<id>.yaml)")
    root = _scalar(b.read_text(), "product_root")
    return {
        "project": {"path": f"{root or '<product>'}/.claude/settings.json", "env": project_env(project_id)},
        "user": {"path": f"{user_settings_path()} (or the shell)", "env": env_block(port)},
        "note": ("project: only OTEL_RESOURCE_ATTRIBUTES goes in the product's .claude/settings.json env. "
                 "user: the six enabling keys go in the user settings or the shell; remove them from the "
                 "product's settings, where Claude Code ignores them and warns (SPEC §24)"),
    }


TELEMETRY_KEY_RE = re.compile(r"^(CLAUDE_CODE_ENABLE_TELEMETRY|CLAUDE_CODE_ENHANCED_TELEMETRY_BETA|OTEL_.+)$")
PROJECT_KEYS = ("OTEL_RESOURCE_ATTRIBUTES",)  # the telemetry keys a project's settings may carry
# Keys that make Claude Code export prompt text and tool details (arguments, full commands). They stay unset.
CONTENT_KEYS = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_TOOL_DETAILS")


def content_keys_set(env: dict[str, Any] | None) -> list[str]:
    """The CONTENT_KEYS this env sets to anything but empty. Key names only, never values."""
    return sorted(k for k in CONTENT_KEYS if isinstance(env, dict) and str(env.get(k) or "").strip())


def user_settings_check(port: int, shell: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read-only: does the user settings' `env` carry `env_block(port)`, and do it or the shell (`shell`,
    default this process's environment) set a CONTENT_KEYS key? Key names only, never values."""
    p = user_settings_path()
    try:
        env = json.loads(p.read_text()).get("env")
    except (OSError, ValueError, AttributeError):
        env = None
    want = env_block(port)
    content = [f"{k} is set in {where}: Claude Code would export prompt text or tool details; unset it "
               "(the receiver keeps numbers and ids only, SPEC §24)"
               for where, keys in ((str(p), content_keys_set(env)),
                                   ("the environment (the shell, or a Claude Code session's settings env)",
                                    content_keys_set(dict(os.environ) if shell is None else shell)))
               for k in keys]
    if not isinstance(env, dict):
        return {"path": str(p), "ok": False, "missing": sorted(want),
                "warnings": [f"{p} has no env block: add `ccp otel env`'s block there (SPEC §24)", *content]}
    missing = sorted(k for k, v in want.items() if str(env.get(k)) != v)
    warnings = []
    if missing:
        warnings.append(f"{p} env lacks or differs on {', '.join(missing)}: nothing exports (SPEC §24)")
    pinned = re.search(r"\b(c(?:cp|pl)\.project_id)=", str(env.get("OTEL_RESOURCE_ATTRIBUTES") or ""))
    if pinned:
        warnings.append(f"{p} sets {pinned.group(1)} in OTEL_RESOURCE_ATTRIBUTES: every session would land in one "
                        "project; remove it, the id belongs in each product's settings (`ccp otel env --project ID`, SPEC §24)")
    warnings += content
    return {"path": str(p), "ok": not warnings, "missing": missing, **({"warnings": warnings} if warnings else {})}


def product_block_keys(settings: dict[str, Any]) -> list[str]:
    """Enabling telemetry keys in a product's settings `env`, which Claude Code ignores there (§24).
    `OTEL_RESOURCE_ATTRIBUTES` is honoured there and is not one of them."""
    env = settings.get("env") if isinstance(settings, dict) else None
    return sorted(k for k in env if TELEMETRY_KEY_RE.match(str(k)) and k not in PROJECT_KEYS) \
        if isinstance(env, dict) else []


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{launchd_label()}.plist"


def _plist(port: int) -> str:
    from xml.sax.saxutils import escape  # noqa: PLC0415
    log = escape(str(Path.home() / "Library" / "Logs" / "control-plane-otel.log"))
    # §29.2: launchd runs the run checkout's ccp, never whichever checkout ran `install`.
    args = "".join(f"<string>{escape(x)}</string>" for x in (str(run_ccp()), "otel", "serve", "--port", str(port)))
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            f'"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
            f"<key>Label</key><string>{launchd_label()}</string>"
            f"<key>ProgramArguments</key><array>{args}</array>"
            f"<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>"
            f"<key>StandardErrorPath</key><string>{log}</string>"
            f"<key>StandardOutPath</key><string>{log}</string></dict></plist>\n")


def launchd(action: str, port: int) -> dict[str, Any]:
    p = _plist_path()
    dom = f"gui/{os.getuid()}"
    if action == "status":
        r = subprocess.run(["launchctl", "print", f"{dom}/{launchd_label()}"], capture_output=True, text=True)
        live = None
        try:
            import urllib.request  # noqa: PLC0415
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/status", timeout=3) as resp:
                live = json.loads(resp.read())
        except (OSError, ValueError):
            live = None
        user = user_settings_check(port)
        return {"ok": r.returncode == 0 and live is not None, "plist": str(p), "loaded": r.returncode == 0,
                "state": next((ln.strip() for ln in r.stdout.splitlines() if ln.strip().startswith("state =")), None),
                "receiver": live, "user_settings": user,
                "warnings": user.get("warnings") or []}
    if action == "uninstall":
        launchd_bootout(launchd_label())
        p.unlink(missing_ok=True)
        return {"ok": True, "removed": str(p)}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_plist(port))
    r = launchd_reload(launchd_label(), p, want_running=True)  # KeepAlive: the receiver must be up
    warns = (r.pop("warnings", None) or []) + [w for w in [run_ccp_warning()] if w]
    return {**r, "plist": str(p), "port": port, "ccp": str(run_ccp()), **({"warnings": warns} if warns else {})}


def main(argv: list[str]) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(prog="ccp otel")
    ap.add_argument("action", choices=("serve", "env", "install", "uninstall", "status"))
    ap.add_argument("--port", type=int, default=int(envvar("CCP_OTEL_PORT") or DEFAULT_PORT))
    ap.add_argument("--project", help="env: also the product's block, OTEL_RESOURCE_ATTRIBUTES=ccp.project_id=ID")
    a = ap.parse_args(argv)
    if a.action == "serve":
        return serve(a.port)
    if a.action == "env":
        if not a.project:
            print(json.dumps({"env": env_block(a.port), "settings": str(user_settings_path())}, indent=2))
            return 0
        try:
            body = env_for_project(a.project, a.port)
        except ValueError as exc:
            print(f"ccp otel env: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(body, indent=2))
        print(f"ccp otel env: {body['note']}", file=sys.stderr)
        return 0
    body = launchd(a.action, a.port)
    print(json.dumps(body, indent=2))
    for w in body.get("warnings") or []:
        print(f"warning: {w}", file=sys.stderr)
    return 0 if body.get("ok") else 1
