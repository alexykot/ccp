"""The plane's one reading of git's merge analysis (house rule E14): does merging two commits conflict, and
in which files; a head's own change, by patch id; how a merge commit's recorded resolution differs from git's
own. Callers: §15.2 (the review skip, `verify.skip_review`), §16.5 rule 4 (close's catch-up of a head behind
the integration tip) and §13 (the integration-merge rule, `runs.same_change`). Every git call goes through
`ccp.queue.git`, looked up when it is called, except `own_patch_id`, which uses its caller's runner. Standard
library only; the refusal texts that name a git subcommand are made here."""
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

STAGE_RE = re.compile(r"^(\d{6}) ([0-9a-f]{40,64}) ([123])\t(.+)$", re.S)  # a conflicted file's stage, in -z output


@dataclass(frozen=True)
class Probe:
    """One merge probe: `tree` (the merge's tree, with conflict markers in the conflicted files; "" when git
    gave none), `conflicts` (each conflicted path to its stages: 1 base, absent when both sides added the file;
    2 ours; 3 theirs; each as (mode, blob)), `returncode` (0 clean, 1 conflicted), `failed` (git could not run
    the merge at all: an exit other than 0 or 1, or no tree) and `detail` (git's own message, cut for a refusal)."""
    tree: str
    conflicts: dict[str, dict[int, tuple[str, str]]] = field(default_factory=dict)
    returncode: int = 0
    failed: bool = False
    detail: str = ""


def probe(root: Path, ours: str, theirs: str) -> Probe:
    """`git merge-tree --write-tree -z --no-messages` of `ours` and `theirs`: writes the merge's objects,
    touches no working tree. It needs git 2.38 or later."""
    from ccp import queue  # noqa: PLC0415
    r = queue.git(root, "merge-tree", "--write-tree", "-z", "--no-messages", ours, theirs)
    tree, *rest = r.stdout.split("\0")
    tree = tree.strip()
    conflicts: dict[str, dict[int, tuple[str, str]]] = {}
    for x in rest:
        if m := STAGE_RE.match(x):
            conflicts.setdefault(m.group(4), {})[int(m.group(3))] = (m.group(1), m.group(2))
    return Probe(tree, conflicts, r.returncode, r.returncode not in (0, 1) or not tree,
                 (r.stderr or r.stdout).strip()[:200])


def cannot_merge_text(p: Probe, ours: str, integ: str) -> str:
    """Close's refusal when git could not run the merge of the head `ours` and the tip of `integ`."""
    return f"conflict: git merge-tree could not merge {ours[:7]} and origin/{integ}: {p.detail}"


def conflict_text(ours: str, integ: str, files: list[str], why: str = "") -> str:
    """Close's refusal when the head `ours` and the tip of `integ` conflict, naming up to five of `files`."""
    return (f"conflict: git merge-tree of {ours[:7]} and origin/{integ} conflicts"
            + (f" in {', '.join(files[:5])}" if files else "") + why)


def old_git_text(p: Probe) -> str:
    """The review skip's reason when git exited other than 0 or 1 (an older git lacks the option)."""
    return f"`git merge-tree --write-tree` failed (exit {p.returncode}); it needs git 2.38 or later"


def own_patch_id(root: Path | str, sha: str, base_ref: str, run: Callable[..., subprocess.CompletedProcess[str]],
                 *, exclude: Sequence[str] = (), empty: str | None = None) -> str | None:
    """The patch id (`git patch-id --stable`) of the diff from the merge base of `sha` and `base_ref` to `sha`:
    the change `sha` carries of its own. None when it cannot be read or the diff is empty (a head `base_ref`
    already holds). Never fetches. `run(root, *git_args, data=None)` is the caller's git runner, so the caller
    keeps its environment and timeout (a timeout it raises passes through). `exclude` leaves those files out of
    the diff (literal pathspecs); `empty` is what an empty diff returns instead of None (a diff whose every
    file is left out is empty)."""
    mb = run(root, "merge-base", sha, base_ref)
    if mb.returncode != 0:
        return None
    spec = ["--", ".", *(f":(exclude,literal){f}" for f in exclude)] if exclude else []
    d = run(root, "diff", "--binary", mb.stdout.strip(), sha, *spec)
    if d.returncode != 0:
        return None
    if empty is not None and not d.stdout.strip():
        return empty
    pid = run(root, "patch-id", "--stable", data=d.stdout)
    if pid.returncode != 0 or not pid.stdout.split():
        return None
    return str(pid.stdout.split()[0])


def remerge_diff(root: Path, merge: str) -> str:
    """The text of `git show --remerge-diff` of the merge commit `merge`: how its recorded resolution differs
    from git's automatic merge of its parents; empty for a clean merge. Raises QueueError when git fails."""
    from ccp import queue  # noqa: PLC0415
    out: Any = queue.git(root, "show", "--remerge-diff", "--format=", merge, check=True).stdout
    return str(out)
