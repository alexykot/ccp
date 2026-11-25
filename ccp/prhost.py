"""The PR host (ADR-0040, E19; SPEC §4.5, §15.5): the one module that reaches a pull request's host, and the
PR-host interface `ccp pr` serves to workers and the runner. Everything else sees a PR as `PrFacts`, plain
normalised values, never a host's field names or state words. plane.json `pr_host.adapter` names the adapter
(ADR-0040 D5): the GitHub adapter runs `gh` (`CCP_GH_BIN`, else `gh`) and holds the one merge argv; the local
adapter keeps each PR's record in the queue, in `STATES`' words, records a `pr` ledger event for each opening, body
edit and merge (§23.2), and merges with git alone (ADR-0040 D3). `merge.command` in
plane.json still replaces the merge operation under either (SPEC §15.5)."""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ccp import refs
from ccp.config import PR_HOST_DEFAULTS, Config, fill
from ccp.envvars import envvar

STATES = ("open", "merged", "closed")  # a PR's normalised state
BODY_TIMEOUT_S = 60  # how long a body read waits on the host

_GITHUB_STATES = {"OPEN": "open", "MERGED": "merged", "CLOSED": "closed"}
PRS_DIR = "prs"  # ADR-0040 D3: the local adapter's records, QUEUE_ROOT/prs/<n>.json (contracts/pr_record.schema.json)
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
    `merge_commit` is the merge's sha ('' until merged). `body` is the PR's text, set only when the read
    asks for it (`view(..., with_body=True)`)."""
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
         timeout: float | None = None, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(cmd, cwd=cfg.root, capture_output=True, text=True, timeout=timeout, input=stdin,
                              env={**os.environ, **(env or {})})
    except FileNotFoundError as exc:
        raise HostUnavailable(f"{cmd[0]} is not installed") from exc


def _words(r: subprocess.CompletedProcess[str]) -> str:
    return (r.stderr or r.stdout).strip()


class GitHub:
    """ADR-0040 D2: pull requests on GitHub, through `gh`."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def view(self, pr: str, with_body: bool = False) -> PrFacts:
        r = _run(self.cfg, [_gh(), "pr", "view", pr, "--json", _VIEW_FIELDS + (",body" if with_body else "")])
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
            number=number if isinstance(number, int) else (int(pr) if pr.isdigit() else 0),
            state=state,
            head=str(got.get("headRefOid") or ""),
            branch=str(got.get("headRefName") or ""),
            merged_at=str(got["mergedAt"]) if got.get("mergedAt") else None,
            merge_commit=str(merge.get("oid") or "") if isinstance(merge, dict) else "",
            body=str(got.get("body") or "") if with_body else None)

    def body(self, pr: str, timeout: float | None) -> str:
        gh = _gh()
        try:
            r = _run(self.cfg, [gh, "pr", "view", pr, "--json", "body"], timeout=timeout)
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

    def open(self, branch: str, base: str, title: str, body: str) -> int:  # noqa: A003  (the operation's name)
        r = _run(self.cfg, [_gh(), "pr", "create", "--head", branch, "--base", base, "--title", title,
                            "--body-file", "-"], stdin=body)
        if r.returncode != 0:
            raise HostError(f"gh pr create --head {branch}: {_words(r)}", _words(r))
        said = (r.stdout.strip().splitlines() or [""])[-1].rstrip("/").rsplit("/", 1)[-1]
        if not said.isdigit():
            raise HostError(f"gh pr create --head {branch} named no PR number: {r.stdout.strip()!r}")
        return int(said)

    def diff(self, pr: str) -> str:
        r = _run(self.cfg, [_gh(), "pr", "diff", pr])
        if r.returncode != 0:
            raise HostReadFailed(f"gh pr diff {pr}: {_words(r)}", _words(r))
        return r.stdout

    def edit(self, pr: str, body: str) -> None:
        r = _run(self.cfg, [_gh(), "pr", "edit", pr, "--body-file", "-"], stdin=body)
        if r.returncode != 0:
            raise HostError(f"gh pr edit {pr}: {_words(r)}", _words(r))

    def merge(self, pr: str, head: str, task_id: str) -> MergeResult:
        r = _run(self.cfg, [_gh(), "pr", "merge", pr, "--squash", "--match-head-commit", head])
        said = (r.stderr + r.stdout).lower()
        return MergeResult(r.returncode == 0, _words(r), "conflict" in said or "not mergeable" in said)

    def confirm(self, pr: str) -> PrFacts:
        return self.view(pr)

    @staticmethod
    def head_refs(pr: str) -> list[str]:
        """The refs on origin besides the task branch that hold the PR's head: GitHub's `refs/pull/<pr>/head`."""
        return [f"refs/pull/{pr}/head"]


class Local:
    """ADR-0040 D3: the plane keeps each PR's record in the queue (`PRS_DIR`) and reads and merges it with git
    alone, against `origin`."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def _dir(self) -> Path:
        from ccp import queue  # noqa: PLC0415

        return queue.root() / PRS_DIR

    @contextlib.contextmanager
    def _locked(self) -> Iterator[Path]:
        """`prs/.lock`, held by every write of a record, so two writers never give one number twice or lose an edit."""
        import fcntl  # noqa: PLC0415

        d = self._dir()
        d.mkdir(parents=True, exist_ok=True)
        with (d / ".lock").open("a") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield d
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _load(self, pr: str) -> dict[str, Any]:
        if not pr.isdigit():
            raise HostReadFailed(f"PR {pr!r} is not a PR number", "not a PR number")
        path = self._dir() / f"{int(pr)}.json"
        try:
            rec = json.loads(path.read_text())
        except FileNotFoundError:
            raise HostReadFailed(f"no PR #{pr} in {path.parent}", f"no record {path.name}") from None
        except (OSError, ValueError) as exc:
            raise HostError(f"{path} is not a PR record: {exc}") from None
        if not isinstance(rec, dict) or rec.get("state") not in STATES:
            raise HostError(f"{path} names no PR state")
        return rec

    def _save(self, rec: dict[str, Any]) -> None:
        from ccp import queue  # noqa: PLC0415

        queue.write_json(self._dir() / f"{rec['number']}.json", rec)

    def _emit(self, rec: dict[str, Any], op: str, **extra: str) -> None:
        """§23.2: the record's `pr` event, `op` (opened, edited, merged), under the branch's task when it is `task/<id>`."""
        from ccp import queue  # noqa: PLC0415

        branch = str(rec["branch"])
        task_id = branch.removeprefix("task/") if branch.startswith("task/") else ""
        queue.emit(queue.root(), self.cfg, task_id, "pr", op, {"pr": int(rec["number"]), "head": str(rec["head"]), **extra})

    def _merged_at(self, sha: str, cwd: Path | None = None) -> str:
        """The squash commit's time, as a record's `merged_at`: now when git cannot read it."""
        when = self._git("show", "-s", "--format=%ct", sha, cwd=cwd).stdout.strip()
        at = datetime.fromtimestamp(int(when), timezone.utc) if when.isdigit() else datetime.now(timezone.utc)
        return at.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _git(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return _run(self.cfg, ["git", "-C", str(cwd or self.cfg.root), *args])

    def _tip(self, branch: str) -> str:
        """`branch`'s head on origin, fetched now; "" when origin has no such branch."""
        self._git("fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}")
        r = self._git("rev-parse", "-q", "--verify", f"refs/remotes/origin/{branch}^{{commit}}")
        return r.stdout.strip() if r.returncode == 0 else ""

    def _squash_of(self, rec: dict[str, Any]) -> str:
        """The squash commit of the PR on origin/<base>: the one this adapter recorded, or else (a merge made by
        `merge.command`) the commit on the base's first-parent line since the PR's head with the §10.7 squash
        subject, `Task <NNNN>: <title> (#<n>)`; "" when there is none."""
        if rec["merge_commit"]:
            return str(rec["merge_commit"])
        branch, head = str(rec["branch"]), str(rec["head"])
        if not head or not branch.startswith("task/"):
            return ""
        lead = f"Task {refs.ids(self.cfg).task_number(branch.removeprefix('task/'))}: "
        r = self._git("log", "--first-parent", "--format=%H %s", f"{head}..refs/remotes/origin/{rec['base']}")
        for line in r.stdout.splitlines() if r.returncode == 0 else []:
            sha, _, subject = line.partition(" ")
            if subject.startswith(lead) and subject.endswith(f" (#{rec['number']})"):
                return sha
        return ""

    def _refresh(self, rec: dict[str, Any]) -> None:
        """An open record brought up to origin: its head from origin/<branch> (kept when the branch is gone), and
        `merged`, with the merge time, once its squash commit is on origin/<base>."""
        if rec["state"] != "open":
            return
        tip = self._tip(str(rec["branch"]))
        if tip:
            rec["head"] = tip
        self._tip(str(rec["base"]))
        sha = self._squash_of(rec)
        if sha and self._git("merge-base", "--is-ancestor", sha, f"refs/remotes/origin/{rec['base']}").returncode == 0:
            rec.update(state="merged", merge_commit=sha, merged_at=self._merged_at(sha))

    def _read(self, pr: str) -> dict[str, Any]:
        """The record, refreshed from origin and written back when that changed it; the write that first records it
        merged (a merge made by `merge.command`) records its `merged` event."""
        with self._locked():
            rec = self._load(pr)
            before = dict(rec)
            self._refresh(rec)
            if rec != before:
                self._save(rec)
                if before["state"] != "merged" and rec["state"] == "merged":
                    self._emit(rec, "merged", merge_commit=str(rec["merge_commit"]))
        return rec

    @staticmethod
    def _facts(rec: dict[str, Any], with_body: bool = False) -> PrFacts:
        merged = rec["state"] == "merged"
        return PrFacts(number=int(rec["number"]), state=str(rec["state"]), head=str(rec["head"]),
                       branch=str(rec["branch"]), merged_at=rec.get("merged_at") if merged else None,
                       merge_commit=str(rec["merge_commit"]) if merged else "",
                       body=str(rec["body"]) if with_body else None)

    def view(self, pr: str, with_body: bool = False) -> PrFacts:
        return self._facts(self._read(pr), with_body)

    def body(self, pr: str, timeout: float | None) -> str:
        return str(self._load(pr)["body"])

    def open(self, branch: str, base: str, title: str, body: str) -> int:  # noqa: A003  (the operation's name)
        head = self._tip(branch)
        if not head:
            raise HostError(f"{branch} is not on origin: push it, then open its PR")
        from ccp.queue import iso  # noqa: PLC0415

        with self._locked() as d:
            numbers = [int(p.stem) for p in d.glob("*.json") if p.stem.isdigit()]
            for n in numbers:
                rec = self._load(str(n))
                if rec["branch"] == branch and rec["state"] == "open":
                    raise HostError(f"{branch} has an open PR already: #{n}")
            n = max(numbers, default=0) + 1
            rec = {"number": n, "branch": branch, "base": base, "title": title, "body": body, "head": head,
                   "state": "open", "opened_at": iso(), "merged_at": None, "merge_commit": ""}
            self._save(rec)
            self._emit(rec, "opened")
        return n

    def diff(self, pr: str) -> str:
        rec = self._read(pr)
        r = self._git("diff", f"origin/{rec['base']}...{rec['head']}")
        if r.returncode != 0:
            raise HostReadFailed(f"git diff for PR #{pr}: {_words(r)}", _words(r))
        return r.stdout

    def edit(self, pr: str, body: str) -> None:
        with self._locked():
            rec = self._load(pr)
            rec["body"] = body
            self._save(rec)
            self._emit(rec, "edited")

    @contextlib.contextmanager
    def _merge_tree(self, task_id: str, base: str) -> Iterator[Path]:
        """Where the squash is made: close's merge worktree for the task (§10.5), else (a product with no
        `worktrees.dir`) a temporary detached worktree, removed after."""
        from ccp import lifecycle, wt  # noqa: PLC0415

        if wt.merge_path(self.cfg, task_id) is not None:
            yield lifecycle._merge_checkout(self.cfg, task_id, base).root
            return
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "merge"
            r = self._git("worktree", "add", "-q", "--detach", str(path), f"refs/remotes/origin/{base}")
            if r.returncode != 0:
                raise HostError(f"git worktree add {path}: {_words(r)}")
            try:
                yield path
            finally:
                self._git("worktree", "remove", "--force", str(path))

    def merge(self, pr: str, head: str, task_id: str) -> MergeResult:
        from ccp.queue import QueueError, task_meta  # noqa: PLC0415

        rec = self._read(pr)
        n, branch, base = rec["number"], str(rec["branch"]), str(rec["base"])
        if rec["state"] != "open":
            return MergeResult(False, f"PR #{n} is {rec['state']}, not open: nothing merged")
        tip = self._tip(branch)
        if not tip or tip.lower() != head.lower():
            return MergeResult(False, f"origin/{branch} is at {tip[:12] or 'nothing'}, not the given head {head[:12]}: "
                                      "nothing merged")
        try:
            subject = f"Task {refs.ids(self.cfg).task_number(task_id)}: {task_meta(self.cfg, task_id)['title']} (#{n})"
            with self._merge_tree(task_id, base) as where:
                steps = (("checkout", "-q", "--detach", f"refs/remotes/origin/{base}"), ("merge", "--squash", tip),
                         ("commit", "-q", "-m", subject))
                for step in steps:
                    r = self._git(*step, cwd=where)
                    if r.returncode != 0:
                        said = (r.stdout + r.stderr).strip()
                        self._git("reset", "-q", "--hard", cwd=where)
                        return MergeResult(False, f"git {step[0]} for PR #{n}: {said}: nothing merged",
                                           step[0] == "merge" and "conflict" in said.lower())
                sha = self._git("rev-parse", "HEAD", cwd=where).stdout.strip()
                merged_at = self._merged_at(sha, cwd=where)
                r = self._git("push", "-q", "origin", f"HEAD:refs/heads/{base}", cwd=where)
                if r.returncode != 0:
                    return MergeResult(False, f"the push of PR #{n}'s squash {sha[:12]} to {base} was refused (has the "
                                              f"tip moved?): nothing merged; run `ccp tasks close {task_id} --pr {n}` "
                                              f"again: {_words(r)}")
        except HostUnavailable:
            raise
        except (QueueError, HostError) as exc:  # the task's title, or the merge worktree, could not be had
            return MergeResult(False, f"PR #{n}: {exc}: nothing merged")
        with self._locked():
            rec = self._load(pr)
            if rec["state"] == "open":  # else a read that found the squash on the base recorded it first
                rec.update(state="merged", merge_commit=sha, merged_at=merged_at)
                self._save(rec)
                self._emit({**rec, "head": tip}, "merged", merge_commit=sha)
        return MergeResult(True, f"squashed onto {base} as {sha[:12]}")

    def confirm(self, pr: str) -> PrFacts:
        return self._facts(self._read(pr))

    @staticmethod
    def head_refs(pr: str) -> list[str]:
        """None: a local PR's head is on its branch."""
        return []


_ADAPTERS: dict[str, type[GitHub] | type[Local]] = {"github": GitHub, "local": Local}  # by config.PR_HOST_ADAPTERS


def adapter_name(cfg: Config) -> str:
    """ADR-0040 D5: plane.json `pr_host.adapter`, the adapter's name."""
    return str((cfg.pr_host or PR_HOST_DEFAULTS)["adapter"])


def adapter(cfg: Config) -> GitHub | Local:
    """ADR-0040 D5: the adapter plane.json `pr_host.adapter` names."""
    return _ADAPTERS[adapter_name(cfg)](cfg)


def label(cfg: Config) -> str:
    """How a message names the PR host it used: `the PR host (<adapter>)`."""
    return f"the PR host ({adapter_name(cfg)})"


def fetch_commit(cfg: Config, root: Path, sha: str, pr: str | int | None, branch: str) -> bool:
    """Whether `sha` is a commit in the checkout `root`, fetching it when it is not: from `origin`, in order, the
    adapter's own refs for `pr` (none when `pr` is None or empty) and then `branch`, stopping once it is there."""
    def here() -> bool:
        return _run(cfg, ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"]).returncode == 0

    if here():
        return True
    for ref in (adapter(cfg).head_refs(str(pr)) if pr else []) + [branch]:
        if _run(cfg, ["git", "-C", str(root), "fetch", "-q", "origin", ref]).returncode == 0 and here():
            return True
    return False


def view(cfg: Config, pr: str, with_body: bool = False) -> PrFacts:
    """The PR's facts, read from the host, with its body in the same read when `with_body`. Raises
    HostUnavailable when the host's tool is missing, HostReadFailed when the read fails, HostError when it
    names no PR state or no JSON."""
    return adapter(cfg).view(str(pr), with_body)


def body(cfg: Config, pr: str, timeout: float | None = BODY_TIMEOUT_S) -> str:
    """The PR's body text. Raises HostError (HostUnavailable when the host's tool is missing) when the host
    cannot give one; the message names why."""
    return adapter(cfg).body(str(pr), timeout)


def open(cfg: Config, branch: str, base: str, title: str, body: str) -> int:  # noqa: A001  (the operation's name)
    """Open a PR for the pushed `branch` against `base`; its number. Raises HostUnavailable when the host's
    tool is missing, HostError when the host refuses or names no PR number."""
    return adapter(cfg).open(branch, base, title, body)


def diff(cfg: Config, pr: str) -> str:
    """The PR's diff against its base. Raises HostUnavailable when the host's tool is missing,
    HostReadFailed when the read fails."""
    return adapter(cfg).diff(str(pr))


def edit(cfg: Config, pr: str, body: str) -> None:
    """Replace the PR's body. Raises HostUnavailable when the host's tool is missing, HostError when the
    host refuses."""
    adapter(cfg).edit(str(pr), body)


def merge(cfg: Config, pr: str, head: str, task_id: str) -> MergeResult:
    """§15.5: the merge pinned to the verified head: plane.json `merge.command` when set (a template
    naming pr, head_sha, task_id; its child env names the host CLI in CCP_GH_BIN), else the adapter's
    squash merge. Raises HostUnavailable when the host's tool is missing."""
    cmd = (cfg.merge or {}).get("command")
    if cmd:
        r = _run(cfg, ["/bin/sh", "-c", fill(cmd, {"pr": pr, "head_sha": head, "task_id": task_id})],
                 {"CCP_GH_BIN": _gh()})
        said = (r.stderr + r.stdout).lower()
        return MergeResult(r.returncode == 0, _words(r), "conflict" in said or "not mergeable" in said)
    return adapter(cfg).merge(str(pr), head, task_id)


def confirm(cfg: Config, pr: str) -> PrFacts:
    """The PR's facts after a merge was asked for: the caller checks `state` is merged and takes
    `merge_commit`. On GitHub it is the same read as `view`; the local adapter's record is `merged` from its own
    merge, or once a squash commit made by `merge.command` is on origin/<base>."""
    return adapter(cfg).confirm(str(pr))
