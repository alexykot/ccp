"""The PR host (ADR-0040, E19): the one module that reaches a pull request's host. Everything else
sees a PR as `PrFacts`, plain normalised values, never a host's field names or state words. Today
the GitHub adapter is the only one: it runs `gh` (`CCP_GH_BIN`, else `gh`) and holds the one merge
argv; `merge.command` in plane.json still replaces the merge operation (SPEC §15.5)."""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from ccp.config import Config, fill
from ccp.envvars import envvar, for_child

STATES = ("open", "merged", "closed")  # a PR's normalised state
BODY_TIMEOUT_S = 60  # how long a body read waits on the host

_GITHUB_STATES = {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}
_VIEW_FIELDS = "number,state,headRefOid,headRefName,mergeCommit,mergedAt"


class HostError(Exception):
    """The host could not be read or answered badly: a refusal's reason, not a configuration problem.
    `detail` is the host's own words, when it gave any."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(message)
        self.detail = detail


class HostUnavailable(HostError):
    """The host's CLI cannot run here: a configuration problem, not a refusal."""


class HostReadFailed(HostError):
    """The host's CLI ran and exited non-zero reading a PR; `detail` is its own words, possibly none."""


@dataclass(frozen=True)
class PrFacts:
    """A PR as the plane sees it. `state` is one of `STATES`; `head` is the full head sha; `branch` is
    the head branch ('' when the host did not name it); `merged_at` is an ISO-8601 time or None;
    `merge_commit` is the merge's sha ('' until merged). `body` is the PR's text, set only by `body()`."""
    number: int
    state: str
    head: str
    branch: str = ""
    merged_at: str | None = None
    merge_commit: str = ""
    body: str | None = None


@dataclass(frozen=True)
class MergeResult:
    """What a merge attempt answered: `ok`, the host's words (`message`), and whether it refused for a
    conflict with what merged since (`conflict`)."""
    ok: bool
    message: str
    conflict: bool = False


def _gh() -> str:
    return envvar("CCP_GH_BIN") or "gh"


def _run(cfg: Config, cmd: list[str], env: dict[str, str] | None = None,
         timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cfg.root, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, **(env or {})})
    except FileNotFoundError as exc:
        raise HostUnavailable(f"{cmd[0]} is not installed") from exc


def _words(r: subprocess.CompletedProcess[str]) -> str:
    return (r.stderr or r.stdout).strip()


def view(cfg: Config, pr: str) -> PrFacts:
    """The PR's facts, read from the host. Raises HostUnavailable when the CLI is missing, HostReadFailed
    when the read exits non-zero, HostError when it names no PR state or no JSON."""
    r = _run(cfg, [_gh(), "pr", "view", str(pr), "--json", _VIEW_FIELDS])
    if r.returncode != 0:
        raise HostReadFailed(f"gh pr view {pr}: {_words(r)}", _words(r))
    try:
        got = json.loads(r.stdout)
    except ValueError:
        raise HostError(f"gh printed no JSON for PR {pr}") from None
    if not isinstance(got, dict):
        raise HostError(f"gh printed no JSON for PR {pr}")
    state = _GITHUB_STATES.get(str(got.get("state") or ""))
    if state is None:
        raise HostError(f"gh names no state for PR {pr}: {got.get('state')!r}")
    merge: Any = got.get("mergeCommit")
    number = got.get("number")
    return PrFacts(
        number=number if isinstance(number, int) else (int(pr) if str(pr).isdigit() else 0),
        state=state,
        head=str(got.get("headRefOid") or ""),
        branch=str(got.get("headRefName") or ""),
        merged_at=str(got["mergedAt"]) if got.get("mergedAt") else None,
        merge_commit=str(merge.get("oid") or "") if isinstance(merge, dict) else "")


def body(cfg: Config, pr: str, timeout: float | None = BODY_TIMEOUT_S) -> str:
    """The PR's body text. Raises HostError (HostUnavailable when the CLI is missing) when the host cannot
    give one; the message names why."""
    gh = _gh()
    try:
        r = _run(cfg, [gh, "pr", "view", str(pr), "--json", "body"], timeout=timeout)
    except HostUnavailable:
        raise HostUnavailable(f"{gh} could not read PR #{pr} (FileNotFoundError)") from None
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HostError(f"{gh} could not read PR #{pr} ({type(exc).__name__})") from exc
    if r.returncode != 0:
        why = ((r.stderr or r.stdout).strip().splitlines() or ["no output"])[-1]
        raise HostError(f"{gh} pr view {pr} exited {r.returncode}: {why}", why)
    try:
        text = json.loads(r.stdout).get("body")
    except (ValueError, AttributeError):
        text = None
    if not isinstance(text, str):
        raise HostError(f"{gh} pr view {pr} gave no body")
    return text


def merge(cfg: Config, pr: str, head: str, task_id: str) -> MergeResult:
    """§15.5: the merge pinned to the verified head: plane.json `merge.command` when set (a template
    naming pr, head_sha, task_id; its child env names the host CLI in CCP_GH_BIN), else the GitHub
    adapter's squash merge. Raises HostUnavailable when the CLI is missing."""
    cmd = (cfg.merge or {}).get("command")
    if cmd:
        r = _run(cfg, ["/bin/sh", "-c", fill(cmd, {"pr": pr, "head_sha": head, "task_id": task_id})],
                 for_child({"CCP_GH_BIN": _gh()}))
    else:
        r = _run(cfg, [_gh(), "pr", "merge", str(pr), "--squash", "--match-head-commit", head])
    said = (r.stderr + r.stdout).lower()
    return MergeResult(r.returncode == 0, _words(r), "conflict" in said or "not mergeable" in said)


def confirm(cfg: Config, pr: str) -> PrFacts:
    """The PR's facts after a merge was asked for: the caller checks `state` is merged and takes
    `merge_commit`. On GitHub it is the same read as `view`."""
    return view(cfg, pr)
