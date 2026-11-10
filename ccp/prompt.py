"""`ccp prompt <phase> <task>` (SPEC §13.2): the worker's prompt, rendered by the plane.

Four parts, in order: the plane template `templates/prompts/<phase>.md`, then `_common.md` (rules for
every worker and the report contract) with the product's fragment (`plane.json` `prompts.fragment`)
and the runner's `--note`. The command writes the prompt beside the run (`prompts/<task>/<phase>[-n]-prompt.md`),
its §23.8 audit (the full text only under `prompts.keep_body`; audits older than
`prompts.audit_keep_days` are pruned), opens the run (§11.1) and moves the task's phase. It prints the Agent call to make:
the agent type and a description that starts with the run's task and phase; the prompt is the
file's text, verbatim. The runner never passes `model` (§2). First it samples the allowance: at the
5-hour park % it parks the task and refuses, exit 6, writing nothing else (§25.4 the session park).
A verify round with no fix round since the task's last verify round needs `--note` with the reason
(§15.6 rule 4): without it the command refuses, exit 4, nothing opened.

Templates use `{{name}}`, `{{#name}}…{{/name}}` (kept when the value is not empty) and
`{{^name}}…{{/name}}` (kept when it is). A name the renderer does not know is an error, so a
template change cannot ship a hole.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp import refs, runs, tasklog, verify
from ccp.config import Config, lane_for
from ccp.queue import (CCP_BIN, OBS, PLANE, QueueError, git, integration_branch, load_task_state, load_work, phase_move,
                       runner_slots,
                       holder_teammate, root, task_meta)

TEMPLATES = PLANE / "templates" / "prompts"
SECTION_RE = re.compile(r"\{\{([#^])(\w+)\}\}(.*?)\{\{/\2\}\}", re.S)
VAR_RE = re.compile(r"\{\{(\w+)\}\}")
AUDIT_RE = re.compile(r"^(\d{8}T\d{6}Z)_.+\.json$")  # §23.8: prompts/<task_id>/<UTC>_<phase>.json
NOTE_MAX = 4000  # §13.2; 500 until 2026-10-22
PHASE_STATUS = {"implement": "implementing", "fix": "fixing", "review": "reviewing", "verify": "verifying"}
REPORT_LINES = {
    "implement": "   - `Outcome: done`, `Outcome: blocked` or `Outcome: failed`.\n"
                 "   - When done: `PR: #<number>` and `Head: <full sha of the PR head>`.\n",
    "review": "   - `Outcome: done`, `Outcome: blocked` or `Outcome: failed`.\n"
              "   - When done: `Severity: BLOCKER=<n> MAJOR=<n> MINOR=<n> NIT=<n>`, the counts of your findings.\n",
    "verify": "   - `Outcome: done`, `Outcome: blocked` or `Outcome: failed`.\n"
              "   - When done: `Verdict: approve` or `Verdict: reject`, and `Head: <full sha you judged>`, the same as in "
              "the record you wrote with `ccp verify record`.\n",
}
REPORT_LINES["fix"] = REPORT_LINES["implement"]
# §14.1: the lane each worker labels its test runs with, by role; the names come from plane.json
# suite.roles (`{full}`, `{gate}`, `{part}` below).
SUITE_LANES = {
    "implement": "`--lane {full}` for the product's full suite, `--lane {part}` for a subset of the tests",
    "review": "`--lane {part}` for the tests you run (`--lane {full}` if you run the whole suite)",
    "verify": "`--lane {gate}` for the formal gate (the product's gate script, which picks its own lanes), "
              "`--lane {part}` for a subset such as a mutation check",
}
SUITE_LANES["fix"] = SUITE_LANES["implement"]


def suite_lanes(cfg: Config, phase: str) -> str:
    from ccp.config import SUITE_ROLES, lane_for  # noqa: PLC0415
    return SUITE_LANES[phase].format(**{r: lane_for(cfg, r) for r in SUITE_ROLES})


def render(template: str, values: dict[str, Any]) -> str:
    names = set(VAR_RE.findall(template)) | {m[1] for m in re.findall(r"\{\{([#^/])(\w+)\}\}", template)}
    unknown = sorted(names - set(values))
    if unknown:
        raise QueueError(f"prompt template names {', '.join(unknown)}, which ccp prompt does not set", 1)

    def section(m: re.Match[str]) -> str:
        kind, name, body = m.groups()
        if name not in values:
            raise QueueError(f"prompt template names {{{{{kind}{name}}}}}, which ccp prompt does not set", 1)
        return body if bool(values[name]) == (kind == "#") else ""

    prev = None
    while prev != template:
        prev, template = template, SECTION_RE.sub(section, template)

    def var(m: re.Match[str]) -> str:
        if m.group(1) not in values:
            raise QueueError(f"prompt template names {{{{{m.group(1)}}}}}, which ccp prompt does not set", 1)
        return str(values[m.group(1)])

    return VAR_RE.sub(var, template)


def ccp_command(cfg: Config) -> str:
    """`ccp` on PATH for a product on the plugin (SPEC §29.4). A product still on managed copies
    keeps the full path its permission allowlist names, until it moves to the plugin (§9)."""
    import shutil  # noqa: PLC0415
    own = (cfg.root / ".claude" / "agents" / "delivery-implementer.md").is_file()
    return "ccp" if shutil.which("ccp") and not own else str(CCP_BIN)


def main_checkout(cfg: Config) -> Path:
    """The main checkout of the product repo: the runner works from a worktree of it (§12.1)."""
    r = git(cfg.root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if r.returncode == 0 and r.stdout.strip():
        return Path(r.stdout.strip()).parent
    return cfg.root


def worktree_for(cfg: Config, prefix: str, nnnn: str) -> str | None:
    d = (cfg.worktrees or {}).get("dir")
    return str(main_checkout(cfg) / d / f"{prefix}-{nnnn}") if d else None


def fragment(cfg: Config) -> tuple[str, str]:
    rel = cfg.prompts["fragment"] if cfg.prompts else None
    if not rel:
        return "", ""
    f = cfg.root / rel
    if not f.is_file():
        raise QueueError(f"plane.json prompts.fragment names {rel}, which does not exist", 2)
    return rel, f.read_text().strip()


def prior_reports(q: Path, task_id: str, phase: str) -> str:
    want = {"fix": ("review", "verify"), "review": ("implement", "fix"), "verify": ("implement", "fix", "review")}[phase] \
        if phase != "implement" else ()
    lines = []
    for rec in runs.all_runs(q, task_id):
        p = runs.report_path(q, rec["run_id"])
        if rec.get("phase") in want and p.is_file():
            lines.append(f"- {rec['run_id']}: {p}")
    if not lines:  # reports written before the toolkit: the §2.5 report files
        d = q / "progress" / task_id
        for f in sorted(d.glob("*-report.md")) if d.is_dir() else []:
            if f.name.split("-", 1)[0] in want:
                lines.append(f"- {f}")
    if phase == "fix" and not lines:
        raise QueueError(f"fix: no review or verify report for {task_id} to fix from", 2)
    return "\n".join(lines) + ("\n" if lines else "")


def read_note(a: Any) -> str | None:
    """The runner's note, from `--note` or `--note-file` (one of them): stripped, at most NOTE_MAX
    characters, refused when it looks like a secret (it is written to the prompt and its audit)."""
    from ccp import health  # noqa: PLC0415

    path = getattr(a, "note_file", None)
    if path and a.note:
        raise QueueError("give --note or --note-file, not both", 2)
    flag = "--note-file" if path else "--note"
    if path:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise QueueError(f"--note-file {path}: {e}", 2) from None
    else:
        raw = a.note or ""
    note = raw.strip() or None
    if note and len(note) > NOTE_MAX:
        raise QueueError(f"{flag} is {len(note)} characters; the limit is {NOTE_MAX}. A longer rule belongs in "
                         "the product fragment or a plane template (SPEC §13.2)", 2)
    if note and health.looks_like_secret(note):
        raise QueueError(f"{flag} looks like it holds a secret; it would be written to the prompt and its audit. "
                         "Name where the value lives instead", 2)
    return note


def worker_env(cfg: Config, q: Path, prompt_file: Path, fields: dict[str, str]) -> tuple[str, str]:
    """§13: `prompts.worker_env` rendered for this run into `<prompt>-env.sh` beside the prompt, as
    `export NAME='value'` lines. Returns the file's path and a one-line list of what it sets, or two
    empty strings when the product names none. A value that looks like a secret is refused: the
    file is the queue's, and the prompt prints the values."""
    import shlex  # noqa: PLC0415
    from ccp import health  # noqa: PLC0415

    spec = (cfg.prompts or {}).get("worker_env") or {}
    if not spec:
        return "", ""
    out = {k: VAR_RE.sub(lambda m: fields[m.group(1)], v) for k, v in spec.items()}
    for k, v in out.items():
        if health.looks_like_secret(v):
            raise QueueError(f"prompts.worker_env.{k} renders to what looks like a secret: name a file that holds "
                             "it instead (SPEC §13)", 2)
    f = prompt_file.with_name(prompt_file.name.replace("-prompt.md", "-env.sh"))
    body = ("# ccp prompt: this run's environment (plane.json prompts.worker_env, SPEC §13)\n"
            + "".join(f"export {k}={shlex.quote(v)}\n" for k, v in out.items()))
    fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner-only: a product may name real values
    with os.fdopen(fd, "w") as fh:
        fh.write(body)
    os.chmod(f, 0o600)
    # shell-quoted, since the prompt has the worker run `. <file> && …`
    return shlex.quote(str(f)), ", ".join(f"`{k}={v}`" for k, v in out.items())


def base_sha(cfg: Config, q: Path) -> str:
    r = git(cfg.root, "rev-parse", "--short", f"origin/{integration_branch(q)}")
    if r.returncode != 0:
        raise QueueError(f"cannot read origin/{integration_branch(q)} here: pass --base", 2)
    return r.stdout.strip()


def audit(q: Path, cfg: Config, task_id: str, phase: str, prompt_file: Path, run_id: str, meta: dict[str, Any],
          worktree: str | None, note: str | None) -> str:
    cmd = [str(OBS / "write-prompt-audit.sh"), "--task-id", task_id, "--phase", phase, "--prompt-file", str(prompt_file),
           "--session-id", run_id, "--project-id", cfg.project_id, "--argv", json.dumps(["Agent", runs.AGENT_TYPE[phase]]),
           "--durable-task-path", cfg.rel(meta["_file"]),
           "--spec-refs", json.dumps(tasklog._as_list(meta.get("spec_refs")))]
    if worktree:
        cmd += ["--worktree", worktree]
    if note:
        cmd += ["--notes", note]
    if (cfg.prompts or {}).get("keep_body"):
        cmd += ["--keep-body"]
    r = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "QUEUE_ROOT": str(q)})
    if r.returncode != 0:
        raise QueueError(f"write-prompt-audit: {(r.stderr or r.stdout).strip()}", 1)
    return r.stdout.strip().splitlines()[-1].strip() if r.stdout.strip() else ""


def prune_audits(q: Path, cfg: Config, now: datetime | None = None) -> int:
    """§23.8: remove prompt audits older than `prompts.audit_keep_days`, by the UTC stamp in their
    name (a copied queue rewrites mtimes). Only audit files go; the rendered prompts and env files
    beside them stay. Returns how many went; null keeps every audit."""
    days = (cfg.prompts or {}).get("audit_keep_days")
    d = q / "prompts"
    if not days or not d.is_dir():
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    gone = 0
    for f in d.rglob("*.json"):
        m = AUDIT_RE.match(f.name)
        if not m or not f.is_file():
            continue
        try:
            at = datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if at < cutoff:
            try:
                f.unlink()
                gone += 1
            except OSError:
                pass
    return gone


def review_gate(q: Path, tid: str, phase: str, a: Any) -> dict[str, str] | None:
    """§15.2: a verify of a head with a fix round after the last review is refused (exit 4), unless the
    runner passes `--allow-unreviewed-fix --reason "<the lead's or the operator's words>"`. Returns the override
    to record on the run (a friction note and a ledger event), or None."""
    allow = bool(getattr(a, "allow_unreviewed_fix", False))
    reason = (getattr(a, "reason", None) or "").strip()
    if phase != "verify":
        if allow:
            raise QueueError("--allow-unreviewed-fix is for `ccp prompt verify` only", 2)
        return None
    if allow and not reason:
        raise QueueError('--allow-unreviewed-fix needs --reason "<the lead\'s or the operator\'s words>"', 2)
    why = runs.unreviewed_fix(q, tid, a.head)
    if why is None:
        return None
    if not allow:
        raise QueueError(f"{why}. Override once, on the lead's or the operator's word: "
                         '--allow-unreviewed-fix --reason "<their words>"', 4)
    from ccp import health  # noqa: PLC0415
    if health.looks_like_secret(reason):
        raise QueueError("--reason looks like it holds a secret; say it without the value", 2)
    return {"reason": reason, "was": why}


def repeat_gate(q: Path, tid: str, phase: str, note: str | None) -> dict[str, str] | None:
    """§15.6 rule 4: a verify round with no fix round since the task's last verify round says why, from
    `--note` (or `--note-file`); without one it is refused (exit 4), nothing opened. Returns what to
    record on the run (`repeat_verify`: the verify run it follows), or None."""
    if phase != "verify":
        return None
    after = verify.repeat_round(q, tid)
    if after is None:
        return None
    if not note:
        raise QueueError(f"{after} reported and no fix round opened since: a verify round with no fix round since "
                         'the last says why (SPEC §15.6 rule 4). Give the reason with --note "<why>"', 4)
    return {"after": after}


def opener(q: Path, tid: str, st: dict[str, Any], holder: str | None) -> str | None:
    """§16.4: the runner slot opening a round of `tid`. Only the slot holding the lease may: `--holder`
    names the caller, and another slot is refused (exit 3). With several slots `--holder` is required;
    with one runner (no slots, or one) the lease holder is the caller, as before."""
    held = str(st.get("lease_holder") or "") or None
    if holder:
        slots = runner_slots(load_work(q))
        if slots and holder not in slots:  # a teammate name: its slot through bound_name
            named = [s for s, rec in slots.items() if str(rec.get("bound_name") or "") == holder]
            if len(named) != 1:
                raise QueueError(f"--holder {holder!r} is no runner slot or bound teammate name: pass your slot "
                                 f"({', '.join(sorted(slots))}), not a teammate name (SPEC §16.4)", 2)
            holder = named[0]
        if holder != held:
            raise QueueError(f"{tid} is held by {held}, not by {holder}: only the slot holding the lease opens its "
                             "rounds. A runner that lost the race for it asks `ccp tasks next` again (SPEC §16.4)", 3)
        return holder
    if len(runner_slots(load_work(q))) > 1:
        raise QueueError("several runner slots: name yours with --holder <your slot> (SPEC §16.4)", 2)
    return held


def build(cfg: Config, a: Any) -> dict[str, Any]:
    q = root()
    phase = a.phase
    meta = task_meta(cfg, a.task)
    tid = str(meta["task_id"])
    nnnn = refs.ids(cfg).task_number(tid)
    note = read_note(a)
    if phase != "implement" and not (a.pr and a.head):
        raise QueueError(f"{phase}: give --pr and --head (the PR and the head this run works on)", 2)
    st = load_task_state(q, tid)
    if not st.get("lease_holder") or st.get("status") == "done":
        raise QueueError(f"{tid} is not claimed (or is done): `ccp tasks claim {tid}` first", 3)
    caller = opener(q, tid, st, getattr(a, "holder", None))
    from ccp import usage  # noqa: PLC0415
    # §25.4 the session park: no run opens at or past the 5-hour park % (exit 6, the task parked)
    # (best effort: only the park refuses; a failed sample or wait write is a warning)
    session_warn = usage.session_step(cfg, q, tid, lambda: usage.sample_allowance(cfg, q, gate=False), f"ccp prompt {phase}")
    override = review_gate(q, tid, phase, a)
    repeat = repeat_gate(q, tid, phase, note)
    runs.check_pending(q, runs.AGENT_TYPE[phase], a.supersede, caller)
    runs.check_running_rounds(q, tid, phase, caller, a.supersede)
    n = runs.next_round(q, tid, phase)
    run_id = runs.make_id(tid, phase, n)
    report = runs.report_path(q, run_id)
    frag_path, frag = fragment(cfg)
    worktree = a.worktree or worktree_for(cfg, "impl", nnnn)
    own = None
    if phase in ("review", "verify"):
        own = worktree_for(cfg, "rev" if phase == "review" else "ver", nnnn)
        if own and n > 1:
            own += f"-{n}"
    prompt_file = q / "prompts" / tid / (f"{phase}-{n}-prompt.md" if n > 1 else f"{phase}-prompt.md")
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    workdir = (worktree if phase in ("implement", "fix") else own) or ""
    env_file, env_list = worker_env(cfg, q, prompt_file, {
        "run_id": run_id, "task_id": tid, "nnnn": nnnn, "phase": phase, "worktree": workdir,
        "main_checkout": str(main_checkout(cfg)), "queue_root": str(q), "project_id": cfg.project_id})
    cited = tasklog._as_list(meta.get("spec_refs")) + tasklog._as_list(meta.get("adr_refs")) \
        + tasklog._as_list(meta.get("rule_refs")) + tasklog._as_list(meta.get("review_refs"))
    values: dict[str, Any] = {
        "project_id": cfg.project_id, "run_id": run_id, "task_id": tid, "nnnn": nnnn,
        "title": meta.get("title") or "", "task_file": cfg.rel(meta["_file"]), "round": n,
        "refactor": tasklog.kind_of(meta) == "refactor", "refs": ", ".join(cited) or "none",
        "worktree": worktree or "(the runner names it)", "own_worktree": own or "",
        "own_worktree_name": Path(own).name if own else "",
        "env_up": bool((cfg.env or {}).get("up") or (cfg.env or {}).get("urls")),
        "worktree_links": ", ".join((cfg.worktrees or {}).get("links") or []),
        "main_checkout": str(main_checkout(cfg)), "integration": integration_branch(q),
        "base": (a.base or (base_sha(cfg, q) if phase == "implement" else "")),
        "pr": a.pr or "", "head": a.head or "",
        "rules_doc": (cfg.architect or {}).get("rules_doc") or "",
        "fragment": frag, "fragment_path": frag_path, "note": note or "",
        "prior_reports": prior_reports(q, tid, phase),
        "queue_root": str(q), "ccp": ccp_command(cfg), "report_path": str(report),
        "runner": holder_teammate(q, tid),  # §10.2, §16.4: the runner that holds this task, as bound
        "report_lines": REPORT_LINES[phase], "suite_lanes": suite_lanes(cfg, phase),
        "part_lane": lane_for(cfg, "part"),  # §14.1: the lane a subset or a mutation run goes through
        "worker_env": env_list, "worker_env_file": env_file,
        # §15.3: the product's content-keyed test cache, when its plane.json accepts the hits
        "accept_cache": bool(verify.cache_rule(cfg)), "cache_max_age_days": (verify.cache_rule(cfg) or {}).get("max_age_days") or "",
        "cold_gate": verify.cold_gate(cfg, meta),
        # §15.3: the reviewer's touched modules through the same cache, when the product says so
        "review_cache": bool((verify.cache_rule(cfg) or {}).get("review")),
        # §15.2: the fail-fast pre-gate names the product's house-rule checks
        "architect_checks": ", ".join(f"`{c['cmd']}`" for c in (cfg.architect or {}).get("checks") or []),
        "budgets": bool((cfg.architect or {}).get("budgets")),  # §20.2: `ccp budgets check` in the gates
    }
    body = render((TEMPLATES / f"{phase}.md").read_text(), values).rstrip() + "\n\n" \
        + render((TEMPLATES / "_common.md").read_text(), values).rstrip() + "\n"
    report.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(body)
    ref = audit(q, cfg, tid, phase, prompt_file, run_id, meta, worktree if phase in ("implement", "fix") else own, note)
    prune_audits(q, cfg)
    warnings: list[str] = list(session_warn)
    rec = runs.open_run(q, cfg, tid, phase, prompt_ref=ref, note=note, supersede=a.supersede, warnings=warnings, by=caller,
                        extra={"pr": a.pr or None, "head": a.head or None,
                               # §14.1: a suite run from inside this worktree binds to the run
                               "worktree": (worktree if phase in ("implement", "fix") else own) or None,
                               **({"allow_unreviewed_fix": override} if override else {}),
                               **({"repeat_verify": repeat} if repeat else {})})
    if rec["run_id"] != run_id:  # a run of this phase was opened between our count and now
        raise QueueError(f"run id moved from {run_id} to {rec['run_id']} while rendering: run ccp prompt again", 1)
    if override:
        from ccp import health  # noqa: PLC0415
        from ccp.queue import emit  # noqa: PLC0415
        msg = f"allow-unreviewed-fix: {override['reason']} (was: {override['was']})"
        health.add_note(q, msg, tid, os.environ.get("ACTOR") or "task-runner", "allow-unreviewed-fix")
        emit(q, cfg, tid, "note", "set", {"message": msg, "source": "allow-unreviewed-fix", "run_id": run_id, **override})
    phase_move(q, cfg, tid, PHASE_STATUS[phase], f"{run_id} opened")
    desc = f"{nnnn} {phase}" + (f" r{n}" if n > 1 else "")
    return {"ok": True, "run_id": run_id, "phase": phase, "round": n, "prompt_path": str(prompt_file),
            "report_path": str(report), "prompt_ref": ref, "env_file": env_file or None, "expected_model": rec["expected_model"],
            "expected_effort": rec["expected_effort"], **({"allow_unreviewed_fix": override} if override else {}),
            **({"repeat_verify": repeat} if repeat else {}),
            **({"warnings": warnings} if warnings else {}),
            "agent_call": {"subagent_type": runs.definition(cfg, runs.AGENT_TYPE[phase])[0], "description": desc,
                           "prompt": f"the text of {prompt_file}, verbatim", "model": "never pass it (SPEC §2)"}}

