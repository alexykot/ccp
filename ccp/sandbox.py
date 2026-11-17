"""`ccp sandbox`: a throwaway adopted product for end-to-end checks, fenced from real queues (SPEC §29.3).

`create [DIR] [-- <ccp init options>]` makes, under DIR (default a new temporary directory), a git
repository with one commit (`product/`), runs `ccp init` there with the options given, with the
binding written to `bindings/` and the queue to `queue/` inside DIR (never the installation's
bindings directory, §8.3), commits what init wrote, writes the marker file `.ccp-sandbox`, and prints
JSON: `root`, `binding`, `queue_root` and `env`, the `PROJECT_YAML` and `QUEUE_ROOT` lines that point
`ccp` at it. `remove DIR` removes a directory holding the marker and refuses (exit 2) any other, and
one that holds the working directory.

DIR must not exist, or be an empty directory. `--queue-root` and init's flags that adopt nothing
(`--permissions`, `--rules-doc`, `--adopt`) are refused: the sandbox places the queue itself. On a
failure, what create made is removed again. Under the test fence (`tests/__init__.py`), which sets
`CCP_SANDBOX_ROOT`, create works only below that directory.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from ccp.envvars import envvar
from ccp.queue import CCP_BIN

MARKER = ".ccp-sandbox"
PRODUCT, BINDINGS, QUEUE = "product", "bindings", "queue"
# Init flags a sandbox does not pass on: it places the queue itself, and these adopt nothing.
REFUSED = ("--queue-root", "--permissions", "--rules-doc", "--adopt", "--root")
GIT_ID = ("-c", "user.name=ccp sandbox", "-c", "user.email=ccp-sandbox@localhost", "-c", "commit.gpgsign=false")


class SandboxError(Exception):
    def __init__(self, message: str, code: int = 2):
        super().__init__(message)
        self.code = code


def fence_root() -> Path | None:
    """The test fence's temporary root (`CCP_SANDBOX_ROOT`), None outside the fence."""
    v = envvar("CCP_SANDBOX_ROOT")
    return Path(v).resolve() if v else None


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _refused(opts: list[str]) -> list[str]:
    return [o for o in opts if o.split("=", 1)[0] in REFUSED]


def _git(root: Path, *args: str) -> None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SandboxError(f"ccp sandbox: git {args[0]} failed: {r.stderr.strip()}", 1)


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "--all", ".")  # the sandbox's own repository: everything in it is the sandbox's
    _git(root, *GIT_ID, "commit", "-q", "--no-verify", "--allow-empty", "-m", message)


def _target(dir_arg: str | None) -> tuple[Path, bool]:
    """The sandbox directory, resolved, and whether create makes it. Refuses (exit 2) one that is not
    empty, or, under the test fence, one outside its root."""
    fence = fence_root()
    if dir_arg is None:
        if fence is not None:
            fence.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="ccp-sandbox-", dir=str(fence) if fence else None)).resolve(), True
    d = Path(dir_arg).expanduser().resolve()
    if fence is not None and not _under(d, fence):
        raise SandboxError(f"ccp sandbox: {d} is outside the test fence's root {fence}; make it below that")
    if d.exists() and (not d.is_dir() or any(d.iterdir())):
        raise SandboxError(f"ccp sandbox: {d} exists and is not an empty directory; name a new one")
    made = not d.exists()
    d.mkdir(parents=True, exist_ok=True)
    return d, made


def create(dir_arg: str | None, init_opts: list[str]) -> dict[str, Any]:
    """Make the sandbox; returns `root`, `binding`, `queue_root` and `env`. Raises SandboxError; what it
    made by then is removed."""
    bad = _refused(init_opts)
    if bad:
        raise SandboxError(f"ccp sandbox: {', '.join(bad)} is not passed to init: the sandbox places its "
                           "queue and binding itself")
    d, made = _target(dir_arg)
    try:
        return _build(d, init_opts)
    except BaseException:
        if made:
            shutil.rmtree(d, ignore_errors=True)
        else:
            for p in d.iterdir():
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
        raise


def _build(d: Path, init_opts: list[str]) -> dict[str, Any]:
    root, bindings, queue = d / PRODUCT, d / BINDINGS, d / QUEUE
    root.mkdir()
    bindings.mkdir()
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")
    (root / "README.md").write_text("A throwaway product made by `ccp sandbox create`.\n")
    _commit(root, "Sandbox product")
    # §8.3: init writes the binding here, never in the installation's bindings directory.
    env = {**os.environ, "CCP_BINDINGS_DIR": str(bindings)}
    r = subprocess.run([sys.executable, str(CCP_BIN), "--root", str(root), "init", *init_opts,
                        "--queue-root", str(queue)], capture_output=True, text=True, env=env)
    if r.stderr:
        sys.stderr.write(r.stderr)
    if r.returncode != 0:
        raise SandboxError("ccp sandbox: ccp init failed (above); nothing kept", r.returncode)
    try:  # init exits 0 without a binding for an option such as `-h`
        binding = Path(json.loads(r.stdout)["binding"])
    except (ValueError, KeyError, TypeError):
        sys.stderr.write(r.stdout)
        raise SandboxError("ccp sandbox: ccp init printed no binding (above); nothing kept") from None
    _commit(root, "Adopt with ccp init")
    out = {"root": str(root), "binding": str(binding), "queue_root": str(queue),
           "env": [f"PROJECT_YAML={shlex.quote(str(binding))}", f"QUEUE_ROOT={shlex.quote(str(queue))}"]}
    (d / MARKER).write_text(json.dumps(out, indent=2) + "\n")
    return out


def remove(dir_arg: str) -> Path:
    """Remove a sandbox: a directory (not a link) holding the marker file, and not holding the working
    directory. Raises SandboxError (exit 2), removing nothing, for any other path."""
    d = Path(dir_arg).expanduser()
    if d.is_symlink() or not d.is_dir():
        raise SandboxError(f"ccp sandbox: {d} is not a directory; nothing removed")
    marker = d / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise SandboxError(f"ccp sandbox: {d} holds no {MARKER} marker, so it is not a sandbox; nothing removed")
    gone = d.resolve()
    if _under(Path.cwd().resolve(), gone):
        raise SandboxError(f"ccp sandbox: {gone} holds the working directory; run remove from outside it. "
                           "Nothing removed")
    shutil.rmtree(gone)
    return gone


def main(a: Any, init_opts: list[str]) -> int:
    try:
        if a.action == "create":
            print(json.dumps(create(a.dir, init_opts), indent=2))
            return 0
        if init_opts:
            raise SandboxError("ccp sandbox remove: takes no init options")
        if not a.dir:
            raise SandboxError("ccp sandbox remove: name the sandbox directory")
        print(json.dumps({"removed": str(remove(a.dir))}))
        return 0
    except SandboxError as e:
        print(str(e), file=sys.stderr)
        return e.code
