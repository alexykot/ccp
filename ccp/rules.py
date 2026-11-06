"""House rules, checked (SPEC §20.1): the rules doc's shape, the product's checks, and the budgets.

The rules doc (`architect.rules_doc`) is product-owned and short: at most `rules_max_lines` lines,
because every implementer reads it. Each rule opens a list item with its id, `- **E<n>** …`, and
carries a `check:` line saying how it is enforced:

  check: pass      the architect judges it on its next pass
  check: budget    an `architect.budgets` entry with the same id (measured by `ccp architect due`)
  check: command   an `architect.checks` entry with the same id, run here (exit 0 = pass)

A rule with no check, a check naming a missing entry, or an entry naming no rule is a failure:
a rule nobody checks is one more page every implementer reads for nothing. The doc's shape and the
product's checks run inside `ccp docs check`, so the verifier gates on them (§21.8). Budgets do not:
they are diagnostics, measured by `ccp architect due` (a failing budget makes a pass due, §19.6) and
`ccp health`, so one file growing never fails an unrelated task's verifier. Budgets are measured over
tracked files (`git ls-files`), so a checkout's untracked clutter never counts.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

from ccp import refs
from ccp.config import Config

def rule_re(ids: refs.Ids = refs.DEFAULT) -> re.Pattern[str]:
    """A house rule's opening line, `- **E7** …` (group 1 the id, by the product's ids.rule pattern)."""
    return re.compile(rf"^\s*[-*]\s+\*\*({ids.rule_pattern})\*\*")


RULE_RE = rule_re()
CHECK_LINE_RE = re.compile(r"^\s*`?check\s*:\s*`?([a-z]+)", re.I)
CHECK_KINDS = {"pass": "pass", "budget": "budget", "command": "command", "cmd": "command"}


def glob_re(glob: str) -> re.Pattern[str]:
    """A root-relative glob as a regex over `/`-separated paths: `**/` is any number of
    directories (none included), `*` stays inside one name."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif glob[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out + r"\Z")


def tracked_files(root: Path) -> list[str]:
    """Paths under the root that git tracks; every file outside git."""
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, text=True)
    if r.returncode == 0:
        return [p for p in r.stdout.split("\0") if p and (root / p).is_file()]
    return [str(p.relative_to(root)) for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts]


def parse_rules(text: str, ids: refs.Ids = refs.DEFAULT) -> tuple[dict[str, str | None], list[str]]:
    """{rule id: its check kind (None when it has no `check:`)}, and the parse failures."""
    rules: dict[str, str | None] = {}
    errs: list[str] = []
    cur = None
    rx = rule_re(ids)
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            cur = None
            continue
        m = rx.match(line)
        if m:
            cur = m.group(1)
            if cur in rules:
                errs.append(f"rule {cur} is defined twice")
            rules[cur] = None
        if cur:
            c = CHECK_LINE_RE.search(line)
            if c and rules[cur] is None:
                kind = CHECK_KINDS.get(c.group(1).lower())
                if kind is None:
                    errs.append(f"rule {cur}: check {c.group(1)!r} is not pass, budget or command")
                rules[cur] = kind or "?"
    return rules, errs


def check_doc(cfg: Config) -> list[str]:
    """The rules doc's own shape: present, short, every rule checked by something that exists."""
    a = cfg.architect
    if not a or not a["rules_doc"]:
        return []
    doc = cfg.root / a["rules_doc"]
    rel = a["rules_doc"]
    if not doc.is_file():
        return [f"{rel}: missing (architect.rules_doc; template: control-plane templates/docs-project/ENGINEERING.md)"]
    text = doc.read_text()
    errs: list[str] = []
    n = len(text.splitlines())
    if n > a["rules_max_lines"]:
        errs.append(f"{rel}: {n} lines, over rules_max_lines {a['rules_max_lines']} — every implementer reads it")
    rules, perrs = parse_rules(text, refs.ids(cfg))
    errs += [f"{rel}: {e}" for e in perrs]
    budgets = {b["id"] for b in a["budgets"]}
    checks = {c["id"] for c in a["checks"]}
    for rid, kind in rules.items():
        if kind is None:
            errs.append(f"{rel}: rule {rid} has no `check:` (pass, budget or command)")
        elif kind == "budget" and rid not in budgets:
            errs.append(f"{rel}: rule {rid} is checked by a budget, but architect.budgets has no {rid}")
        elif kind == "command" and rid not in checks:
            errs.append(f"{rel}: rule {rid} is checked by a command, but architect.checks has no {rid}")
    for what, ids in (("budgets", budgets), ("checks", checks)):
        for rid in sorted(ids - set(rules)):
            errs.append(f"architect.{what}: {rid} names no rule in {rel}")
    return errs


def budget_failures(cfg: Config) -> list[str]:
    """Each file over its budget, as `E<n>: <path> <measure> > <limit>`."""
    a = cfg.architect
    if not a or not a["budgets"]:
        return []
    files = tracked_files(cfg.root)
    out: list[str] = []
    for b in a["budgets"]:
        paths = [b["path"]] if "path" in b else [p for p in files if glob_re(b["glob"]).match(p)]
        for p in paths:
            f = cfg.root / p
            if not f.is_file():
                out.append(f"{b['id']}: {p} is missing")
                continue
            if "max_lines" in b:
                n = len(f.read_text(errors="ignore").splitlines())
                if n > b["max_lines"]:
                    out.append(f"{b['id']}: {p} has {n} lines > {b['max_lines']}")
            if "max_bytes" in b:
                n = f.stat().st_size
                if n > b["max_bytes"]:
                    out.append(f"{b['id']}: {p} is {n} bytes > {b['max_bytes']}")
    return out


def _measure(data: bytes, measure: str) -> int:
    return len(data.decode(errors="ignore").splitlines()) if measure == "max_lines" else len(data)


def budget_check(cfg: Config, base: str) -> dict[str, Any]:
    """§20.2 `ccp budgets check --base REF`: the budgets, judged on the files this change touches. The
    change is the working tree (commits, edits, new files) against the merge base of HEAD and `base`, so
    a branch rebased onto a newer integration tip is judged on its own diff. A touched file over its
    budget fails when the change grew it (it crossed the budget, or grew while over); one over its
    budget that the change did not grow only warns. Files the change does not touch are not judged."""
    a = cfg.architect
    out: dict[str, Any] = {"base": base, "merge_base": None, "touched": 0, "failures": [], "warnings": []}
    if not a or not a["budgets"]:
        return {**out, "note": "no architect.budgets in plane.json"}
    git = lambda *args: subprocess.run(["git", "-C", str(cfg.root), *args], capture_output=True)  # noqa: E731
    mb = git("merge-base", "HEAD", base)
    if mb.returncode != 0:
        shallow = git("rev-parse", "--is-shallow-repository").stdout.decode().strip() == "true"
        raise ValueError(f"no merge base of HEAD and {base!r}: "
                         + ("this clone is shallow: `git fetch --unshallow`" if shallow else
                            "fetch it, or name the integration branch (`--base origin/<branch>`)"))
    sha = mb.stdout.decode().strip()
    out["merge_base"] = sha
    # paths relative to the product root, which need not be git's toplevel; a rename keeps its old size
    fields = git("diff", "--relative", "-M", "--name-status", "-z", sha).stdout.decode(errors="surrogateescape").split("\0")
    origin: dict[str, str] = {}
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i]
        if status[:1] in ("R", "C"):
            origin[fields[i + 2]] = fields[i + 1]
            i += 3
        else:
            origin[fields[i + 1]] = fields[i + 1]
            i += 2
    for p in git("ls-files", "--others", "--exclude-standard", "-z").stdout.decode(errors="surrogateescape").split("\0"):
        if p:
            origin.setdefault(p, p)
    touched = sorted(p for p in origin if (cfg.root / p).is_file())
    out["touched"] = len(touched)
    for b in a["budgets"]:
        paths = [p for p in touched if p == PurePosixPath(b["path"]).as_posix()] if "path" in b else \
            [p for p in touched if glob_re(b["glob"]).match(p)]
        for p in paths:
            now_data = (cfg.root / p).read_bytes()
            # the old version through the same filters (eol, LFS smudge) the checked-out file went through
            shown = git("cat-file", "--filters", f"{sha}:./{origin[p]}")
            was_data = shown.stdout if shown.returncode == 0 else None
            for measure in ("max_lines", "max_bytes"):
                if measure not in b:
                    continue
                now, limit = _measure(now_data, measure), b[measure]
                if now <= limit:
                    continue
                was = _measure(was_data, measure) if was_data is not None else None
                unit = "lines" if measure == "max_lines" else "bytes"
                row = {"id": b["id"], "path": p, "measure": measure, "size": now, "limit": limit, "was": was}
                if was is None or now > was:
                    row["text"] = (f"{b['id']}: {p} is {now} {unit}, over its budget of {limit} "
                                   + ("(a new file)" if was is None else f"(was {was} at the merge base)") + ": split it or cut it")
                    out["failures"].append(row)
                else:
                    row["text"] = (f"{b['id']}: {p} is {now} {unit}, over its budget of {limit}, and this change "
                                   f"did not grow it (was {was}): not a failure")
                    out["warnings"].append(row)
    return out


def budget_status(cfg: Config) -> list[dict[str, Any]]:
    """Each budget's current state, for the board (§28.3 Quality): one row per entry and measure,
    with the files it covers, the largest of them, and how many are over. `budget_failures` stays
    the trigger's own list."""
    a = cfg.architect
    if not a or not a["budgets"]:
        return []
    files = tracked_files(cfg.root)
    out: list[dict[str, Any]] = []
    for b in a["budgets"]:
        paths = [b["path"]] if "path" in b else [p for p in files if glob_re(b["glob"]).match(p)]
        for measure in ("max_lines", "max_bytes"):
            if measure not in b:
                continue
            row: dict[str, Any] = {"id": b["id"], "target": b.get("path") or b.get("glob"), "measure": measure,
                                   "limit": b[measure], "files": 0, "missing": 0, "over": 0, "max": None,
                                   "max_path": None, "missing_paths": []}
            for p in paths:
                f = cfg.root / p
                if not f.is_file():
                    row["missing"] += 1
                    row["missing_paths"] = (row["missing_paths"] + [p])[:5]
                    continue
                n = len(f.read_text(errors="ignore").splitlines()) if measure == "max_lines" else f.stat().st_size
                row["files"] += 1
                row["over"] += n > b[measure]
                if row["max"] is None or n > row["max"]:
                    row["max"], row["max_path"] = n, p
            out.append(row)
    return out


PLANE = Path(__file__).resolve().parents[1]


def product_env() -> dict[str, str]:
    """The environment a product command runs in. `bin/ccp` no longer puts the plane on PYTHONPATH
    (§14), but a caller may have, and that entry must not reach the product, where the plane's
    own packages (`tests`) would shadow the product's."""
    env = dict(os.environ)
    keep = [p for p in env.get("PYTHONPATH", "").split(os.pathsep)
            if p and Path(p).resolve() != PLANE]
    if keep:
        env["PYTHONPATH"] = os.pathsep.join(keep)
    else:
        env.pop("PYTHONPATH", None)
    return env


def check_failures(cfg: Config) -> list[str]:
    """Run each house-rule check (`architect.checks`) in the root; a non-zero exit (or a timeout) is
    a failure."""
    return run_checks(cfg, (cfg.architect or {}).get("checks") or [])


def run_checks(cfg: Config, checks: list[dict[str, Any]]) -> list[str]:
    """Run product check commands (`{id, cmd, timeout_seconds?}`) in the root, as `architect.checks`
    and `docs.checks` both are: exit 0 passes; a non-zero exit or a timeout is a failure."""
    out: list[str] = []
    for c in checks:
        code, text = run_command(cfg, c["cmd"], c.get("timeout_seconds", 600))
        if code is None:
            out.append(f"{c['id']}: `{c['cmd']}` timed out after {c.get('timeout_seconds', 600)}s")
        elif code != 0:
            tail = " | ".join(text.strip().splitlines()[-3:])
            out.append(f"{c['id']}: `{c['cmd']}` exited {code}" + (f": {tail}" if tail else ""))
    return out


OUTPUT_CAP = 20_000  # characters of a check's output kept (its tail)


def run_command(cfg: Config, cmd: str, timeout: int) -> tuple[int | None, str]:
    """(exit code, the tail of stdout+stderr) of `cmd` in the root; (None, …) after a timeout, when
    the command's whole process group is killed, so no grandchild keeps running."""
    p = subprocess.Popen(cmd, shell=True, cwd=cfg.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         env=product_env(), start_new_session=True)
    try:
        raw, _ = p.communicate(timeout=timeout)
        code: int | None = p.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raw, _ = p.communicate()
        code = None
    return code, (raw or b"").decode(errors="replace")[-OUTPUT_CAP:]


def check(cfg: Config) -> list[str]:
    """What §20 puts in the verifier's gate: the rules doc's shape and the product's checks. Not
    the budgets (see the module doc). [] when the architect block is absent."""
    if cfg.architect is None:
        return []
    return check_doc(cfg) + [f"check {e}" for e in check_failures(cfg)]


def summary(cfg: Config) -> dict[str, Any]:
    """For the architect's prompt: where the rules are and how big they are."""
    a = cfg.architect or {}
    doc = a.get("rules_doc")
    p = cfg.root / doc if doc else None
    rules = parse_rules(p.read_text(), refs.ids(cfg))[0] if p and p.is_file() else {}
    return {"rules_doc": doc, "present": bool(p and p.is_file()), "rules": len(rules),
            "lines": len(p.read_text().splitlines()) if p and p.is_file() else 0,
            "rules_max_lines": a.get("rules_max_lines")}
