"""The git runner the tests share. Holds no tests."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tests.helpers import GIT_ENV


def run(cmd, **kw):
    """`cmd` with `GIT_ENV` (and `env`) over `os.environ`, output captured as text: a `CompletedProcess`."""
    return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **GIT_ENV, **kw.pop("env", {})}, **kw)


def git(cwd: Path, *args: str, env: dict[str, str] | None = None, raw: bool = False) -> str:
    """`git -C <cwd> <args>` with `GIT_ENV` and `env` over `os.environ`. A non-zero exit fails the test, naming the
    command and its stderr. Returns stdout stripped, or as written with `raw=True`."""
    r = run(["git", "-C", str(cwd), *args], env=env or {})
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {r.stderr}")
    return r.stdout if raw else r.stdout.strip()


HEALTH_T0 = 1_760_000_000  # 2025-10-09T08:53:20Z


def commit(root: Path, msg: str, at: int, *extra: str) -> None:
    """`git commit -qm <msg> <extra>` in `root`, authored and committed at `at` (epoch seconds, UTC)."""
    stamp = f"@{at} +0000"
    git(root, "commit", "-qm", msg, *extra, env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})
