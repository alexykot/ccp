"""The headless docs audit (SPEC §21.7): drift between package docs and the code a rule can't see.

A fresh, read-only `claude -p` session runs the product's managed `docs-audit` skill over every
source directory `ccp docs check` knows about, and returns one report in the §19 finding shape.
Everything after the report is the architecture review's machinery, reused as a second review
*kind*: its lock, prompt audit, prepaid-OAuth launch, report validation, and the task-log owner's
triage under `docs/delivery/REVIEW-TRIAGE.md`. The auditor proposes; it never edits.

Due when the product opted into package docs, nothing is running or awaiting triage, the product
HEAD moved since the last audit, and `docs_audit.every_days` have passed.

When the product's plane.json has an `architect` block, `ccp docs audit` is a thin alias of
`ccp architect` (SPEC §19): the docs lens is part of every architect pass. Without one it runs as
above, with the product's `architect` skill (docs lens) where the sync has replaced `docs-audit`.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from typing import Any

from ccp import pkgdocs
from ccp.config import Config

OBS = Path(__file__).resolve().parent.parent / "scripts" / "observability"
sys.path.insert(0, str(OBS))

import architecture_review as ar  # noqa: E402  (review kinds, lock, validation, triage)
import spec_maintainer as sm  # noqa: E402
from lib import fmt_dt, parse_dt, write_json  # noqa: E402

DA = ar.Kind("docs_audit", "Docs audit", "da", "docs-audit.json", "docs-audit.lock", "docs-audit",
             ("doc-wrong", "doc-missing", "doc-aspirational", "doc-padding", "doc-history"), "ccp docs audit triage")
SKILL = ".claude/skills/docs-audit/SKILL.md"
ARCHITECT_SKILL = ar.ARCHITECT_SKILL


def _root() -> Path:
    q = os.environ.get("QUEUE_ROOT")
    if not q or not Path(q).is_dir():
        raise SystemExit("ccp docs audit: set QUEUE_ROOT to this project's runtime queue (SPEC §21.7)")
    return Path(q)


def due_info(cfg: Config, root: Path) -> dict[str, Any]:
    st = ar.load_state(root, DA)
    last = st.get("last") or {}
    head = ar.git(str(cfg.root), "rev-parse", "HEAD")
    every = int(cfg.docs_audit["every_days"])
    days = round((ar.now_utc() - parse_dt(last["at"])).total_seconds() / 86400, 1) if last.get("at") else None
    pending = [r for r, rec in st["reviews"].items() if rec.get("status") in ("reported", "triage_sent", "triage_failed")]
    running = [r for r, rec in st["reviews"].items() if rec.get("status") == "running"]
    info: dict[str, Any] = {"enabled": cfg.package_docs is not None, "head": head, "last_audit_id": last.get("review_id"),
                            "last_head": last.get("head"), "days_since_last": days, "every_days": every,
                            "pending_triage": pending, "running": running}
    if cfg.package_docs is None:
        info.update(due=False, reason="no package_docs block in docs/delivery/plane.json")
    elif running:
        info.update(due=False, reason=f"audit {running[0]} is running")
    elif pending:
        info.update(due=False, reason=f"audit {pending[0]} awaits triage: run `ccp docs audit triage {pending[0]}`")
    elif not last:
        info.update(due=True, reason="no audit yet")
    elif last.get("head") == head:
        info.update(due=False, reason="nothing committed since the last audit")
    elif days is not None and days < every:
        info.update(due=False, reason=f"{days} of {every} days since the last audit")
    else:
        info.update(due=True, reason=f"{days} days and new commits since {last.get('review_id')}")
    return info


def auditor_prompt(cfg: Config, rid: str, head: str, dirty: bool, architect: bool = False) -> str:
    dirs = [{"dir": str(d.relative_to(cfg.root)), "doc": pkgdocs.doc_for(cfg, d).name}
            for d in pkgdocs.source_dirs(cfg)]
    da = cfg.docs_audit
    if architect:  # the product has the §19 skill: a docs-lens pass under the §21 settings
        head_txt = (f"/architect mode=pass lenses=docs review_id={rid} project_id={cfg.project_id} head={head}\n\n"
                    f"You are the isolated architect for project {cfg.project_id} (control-plane SPEC §19, run "
                    f"through the §21 alias). If the architect skill is not loaded, read {ar.architect_skill(cfg.root)} now and "
                    "follow it exactly. Mode: pass. Lenses: docs. ")
    else:
        head_txt = (f"/docs-audit review_id={rid} project_id={cfg.project_id} head={head}\n\n"
                    f"You are the isolated docs auditor for project {cfg.project_id} (control-plane SPEC §21). "
                    f"If the docs-audit skill is not loaded, read {SKILL} now and follow it exactly. ")
    return (
        head_txt
        + "You are read-only: no edits, no commits, nothing that writes, spends or sends.\n"
        f"Directories to audit (each against its own package doc): {json.dumps(dirs)}\n"
        f"Shape-only directories (read for structure, never quote a value): {json.dumps(da['shape_only_dirs'])}\n"
        f"Private paths (never open, never quote): {json.dumps(da['private_dirs'])}\n"
        + ("The working tree has uncommitted changes from other work: audit the committed state "
           "(`git show HEAD:<path>` for any modified file).\n" if dirty else "")
        + "Finish with the report JSON object as your final message and nothing after it.\n"
    )


def cmd_run(cfg: Config, root: Path, actor: str, force: bool) -> int:
    info = due_info(cfg, root)
    if cfg.package_docs is None:
        return ar.out({"outcome": "disabled", **info}, 3)
    if not force and not info["due"]:
        return ar.out({"outcome": "not_due", **info}, 3)
    if info["running"] or info["pending_triage"]:
        return ar.out({"outcome": "blocked", "reason": info["reason"]}, 3)
    pr, pid, head = str(cfg.root), cfg.project_id, info["head"]
    if not head:
        raise SystemExit(f"ccp docs audit: not a git checkout: {pr}")
    use_architect = (cfg.root / ARCHITECT_SKILL).is_file() or not (cfg.root / SKILL).is_file()  # §9: the plugin's
    if not use_architect and not (cfg.root / SKILL).is_file():
        raise SystemExit(f"ccp docs audit: missing {ARCHITECT_SKILL}: install it with scripts/sync-product-docs.sh {pid} "
                         "and commit (SPEC §19)")
    dirty = bool(ar.git(pr, "status", "--porcelain", "--untracked-files=no"))
    rid = f"{DA.prefix}-{ar.now_utc().strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
    timeout_s = int(cfg.docs_audit["call_timeout_minutes"]) * 60
    ok, cur = ar.lock_take(root, actor, rid, timeout_s + 600, DA)
    if not ok:
        return ar.out({"outcome": "locked", "lock": cur}, 3)
    result: dict[str, Any] = {"review_id": rid, "head": head, "dirty": dirty}
    st = ar.load_state(root, DA)
    try:
        st["reviews"][rid] = {"status": "none", "head": head, "started_at": fmt_dt(ar.now_utc())}
        ar.transition(root, st, rid, "running", actor, DA)
        prompt = auditor_prompt(cfg, rid, head, dirty, use_architect)
        deny = [ar.DENY_TOOLS] + [r for p in cfg.docs_audit["private_dirs"] for r in (f"Read(./{p})", f"Read(./{p}/**)")]
        argv = ["env"]
        for k in sm.STRIP_KEYS:
            argv += ["-u", k]
        argv += [os.environ.get("DA_CLAUDE_BIN") or "claude", "-p", prompt, *ar.HEADLESS_MODEL, *ar.plugin_args(cfg.root),
                 "--output-format", "json", "--allowedTools", ",".join(ar.BASE_READ_TOOLS), "--disallowedTools", ",".join(deny)]
        audit = subprocess.run(
            ["bash", str(OBS / "write-prompt-audit.sh"), "--task-id", DA.audit_task, "--phase", DA.audit_task,
             "--prompt-file", "-", "--argv", json.dumps(argv), "--actor", actor, "--project-id", pid,
             "--worktree", pr, "--git-head", head, "--notes", f"review_id={rid}"],
            input=prompt, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(root)})
        if audit.returncode != 0:
            raise RuntimeError(f"write-prompt-audit failed: {audit.stderr.strip()}")
        ar.emit(root, actor, "launch", {"review_id": rid, "phase": "review",
                                        "prompt_ref": audit.stdout.strip().splitlines()[-1]}, DA)
        env = sm.headless_env(pid, "docs-audit")
        try:
            proc = subprocess.run(argv, cwd=pr, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout_s, env=env)
            code, so, se = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            so = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            code, se = 124, "timeout"
        res = sm.parse_claude_json(so)
        ar.emit(root, actor, "exit", {"review_id": rid, "phase": "review", "exit_code": code}, DA)
        is_quota, qclass, resets = sm.detect_quota(res, so, se)
        if is_quota:
            ar.transition(root, st, rid, "quota_parked", actor, DA)
            return ar.out({**result, "outcome": "quota_parked", "quota_class": qclass, "resets_at": resets}, 1)
        report = ar.last_json_object(str(res.get("result") or ""))
        errs = ar.validate_report(report, rid, pid, DA) if report is not None else ["no JSON report in the final message"]
        if errs:
            (ar.rdir(root) / f"{rid}.failed.txt").write_text((str(res.get("result") or se or ""))[-20000:])
            ar.transition(root, st, rid, "failed", actor, DA)
            return ar.out({**result, "outcome": "failed", "errors": errs}, 1)
        report.update({"schema_version": 1, "review_id": rid, "project_id": pid, "head": head, "base": None})
        write_json(ar.report_path(root, rid), report)
        (ar.rdir(root) / f"{rid}.md").write_text(ar.render_md(report, DA))
        st = ar.load_state(root, DA)
        st["last"] = {"review_id": rid, "at": fmt_dt(ar.now_utc()), "head": head}
        n = len(report["findings"])
        st["reviews"][rid]["findings"] = n
        ar.save_state(root, st, DA)
        if n == 0:
            ar.transition(root, st, rid, "no_findings", actor, DA)
            return ar.out({**result, "outcome": "no_findings", "report": str(ar.report_path(root, rid))})
        ar.transition(root, st, rid, "reported", actor, DA)
        return ar.out({**result, "outcome": "reported", "findings": n, "report": str(ar.report_path(root, rid)),
                       "actions": [{"action": "triage", "cmd": f"ccp docs audit triage {rid}"}]})
    except Exception as exc:  # noqa: BLE001
        st = ar.load_state(root, DA)
        if rid in st.get("reviews", {}):
            ar.transition(root, st, rid, "failed", actor, DA)
        return ar.out({**result, "outcome": "failed", "errors": [str(exc)]}, 1)
    finally:
        ar.lock_release(root, actor, rid, DA)


def main(cfg: Config, a: argparse.Namespace) -> int:
    if cfg.architect is not None:  # §19: the product moved; this command is an alias
        from ccp import architect  # noqa: PLC0415
        print("ccp docs audit: this product has an architect block; running `ccp architect "
              f"{a.action}` (SPEC §19)", file=sys.stderr)
        return architect.main(cfg, argparse.Namespace(
            action=a.action, review_id=a.review_id, force=a.force, actor=a.actor, mode="pass", lens=None,
            adr=None, detach=False, rid=None, scope=None))
    root = _root()
    actor = ar.actor_of(a.actor)
    if a.action == "due":
        info = due_info(cfg, root)
        return ar.out(info, 0 if info["due"] else 3)
    if a.action == "run":
        return cmd_run(cfg, root, actor, a.force)
    if a.action == "triage":
        if not a.review_id:
            raise SystemExit("ccp docs audit triage: give the review id")
        return ar.triage(root, a.review_id, actor, DA)
    st = ar.load_state(root, DA)
    return ar.out({"due": due_info(cfg, root), "last": st.get("last"), "reviews": st.get("reviews")})
