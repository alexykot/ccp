"""`ccp prompt <phase> <task>` (SPEC §13.2): the worker's prompt, rendered by the plane.

Four parts, in order: the plane template `templates/prompts/<phase>.md`, then `_common.md` (rules for
every worker and the report contract) with the product's fragment (`plane.json` `prompts.fragment`)
and the runner's `--note`. The command writes the prompt beside the run (`prompts/<task>/<phase>[-n]-prompt.md`),
its §23.8 audit (the full text only under `prompts.keep_body`; audits older than
`prompts.audit_keep_days` are pruned), opens the run (§11.1) and moves the task's phase. The prompt's
last line is `Prompt end: <token>`, the token a short hash of the run id and the text above it, kept on
the run (`prompt_token`): the worker's report repeats it as `Prompt: <token>`, so `ccp report` can tell
a prompt that reached the worker cut (§13.4). It prints the Agent call to make:
the agent type, a description that starts with the run's task and phase, and the prompt: a pointer to
the file, never its text retyped, and, when the role's model for this round (plane.json `models`, else the
plane's default; the implementer's per task) is not the agent definition's, its alias (`model`, §2.4; the run
expects it); otherwise the call carries no `model` and the runner passes none. For an implement round with no
estimate for the task, it warns that the small choice cannot
apply. Once its refusal gates pass, it takes an allowance reading (§25.1; a refused prompt reads nothing): at
the 5-hour park % it parks the task and refuses, exit 6, writing nothing else (§25.4 the session park).
Besides implement, fix, review and verify, a merge round only merges the integration tip into the task
branch and a ruling round only applies a lead's ruling (its `--note`); review and verify treat their heads
as a fix round's (§13.2). A verify of a fix round that no review has seen is refused, exit 4, nothing
opened, unless the product's `verify.skip_review` or a review prover (`verify.provers`) proves the fix, its
`verify.skip_review_after_clean` takes
it as the fix of a clean review's minor findings (the verify prompt lists them), or the lead's word
overrides it (§15.2).
A review of a PR whose body does not contain the task id is refused, exit 2, nothing opened: the runner
repairs the body first (§15.2); a body `gh` cannot read is a warning on the run, not a refusal.
A verify round with no fix round since the task's last verify round needs `--note` with the reason
(§15.6 rule 4): without it the command refuses, exit 4, nothing opened. A verify of a head that lacks the
integration tip, beyond the task log and `merge.behind_tip_ignore`, refuses the same way, with one runner
or several: merge the tip in first (§16.5 rule 4). A review of a head behind the tip refuses the same way
only when merging the tip into it would conflict beyond the task log and `merge.behind_tip_ignore` (§15.2);
a head behind by a clean merge is reviewed.
`ccp prompt review --mode resolution` reviews the resolution of a conflicted integration merge in place of a
full review (§13.2): refused, exit 2, nothing opened, without a done review, over a round that is not a merge
round, for a head that is not a merge commit or whose resolution is empty; any other phase refuses `--mode`.
The verify that follows a contained resolution review lists the checks it names to rerun (§15.6 rule 3).

`ccp prompt env <worktree>` renders the product's `prompts.worker_env` for a worktree `ccp wt` recorded and
prints the `export` lines its workers would get, opening no run and writing nothing (§13.3).

Templates use `{{name}}`, `{{#name}}…{{/name}}` (kept when the value is not empty) and
`{{^name}}…{{/name}}` (kept when it is). A name the renderer does not know is an error, so a
template change cannot ship a hole.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ccp import models, prhost, refs, report, runs, tasklog, verify
from ccp.config import Config, lane_for
from ccp.queue import (CCP_BIN, OBS, PLANE, QueueError, git, integration_branch, load_task_state, load_work, phase_move,
                       runner_slots,
                       holder_teammate, root, task_meta)

TEMPLATES = PLANE / "templates" / "prompts"
SECTION_RE = re.compile(r"\{\{([#^])(\w+)\}\}(.*?)\{\{/\2\}\}", re.S)
VAR_RE = re.compile(r"\{\{(\w+)\}\}")
AUDIT_RE = re.compile(r"^(\d{8}T\d{6}Z)_.+\.json$")  # §23.8: prompts/<task_id>/<UTC>_<phase>.json
NOTE_MAX = 4000  # §13.2; 500 until 2026-10-22
PROMPT_END = "Prompt end: "  # §13.2: the rendered prompt's last line, before its token
# §13.2: a merge or ruling round reworks the open PR, as a fix round does
PHASE_STATUS = {"implement": "implementing", "fix": "fixing", "merge": "fixing", "ruling": "fixing",
                "review": "reviewing", "verify": "verifying"}
# §14.1: the lane each worker labels its test runs with, by role; the names come from plane.json
# suite.roles (`{full}`, `{gate}`, `{part}` below). A role whose lane plane.json `suite.lanes` declares is
# written as that lane with nothing after `--` (`{<role>_for}` and `{<role>_as}` fill in the form).
SUITE_LANES = {
    "implement": "{full}{full_for}the product's full suite{full_as}, {part}{part_for}a subset of the tests{part_as}",
    "review": "{part}{part_for}the tests you run{part_as} ({full} if you run the whole suite)",
    "verify": "{gate}{gate_for}the formal gate (the product's gate script, which picks its own lanes){gate_as}, "
              "{part}{part_for}a subset such as a mutation check{part_as}",
}
SUITE_LANES.update({p: SUITE_LANES["implement"] for p in runs.REWORK_PHASES})


def task_estimate_s(q: Path, tid: str) -> float | None:
    """§26: the task's estimated wall time, its latest agent estimate's total P50, else its latest baseline's
    (the stored bands, uncalibrated); None with neither."""
    from ccp import estimate  # noqa: PLC0415
    rs = estimate.rows(q, tid)
    for src in ("agent", "baseline"):
        p50 = ((estimate.latest(rs, src) or {}).get("total") or {}).get("p50_s")
        if isinstance(p50, (int, float)) and not isinstance(p50, bool) and p50 >= 0:
            return float(p50)
    return None


def worker_model(cfg: Config, q: Path, phase: str, meta: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    """§2.4: the model a round of `phase` pins, the alias its Agent call carries (None when the definition's
    model is the role's), and warnings. The implementer's rounds (implement, fix, merge, ruling) take
    `models.implementer_refactor` for a task of that kind, else `models.implementer_small` when its estimate is
    at most `workers.small_estimate_minutes`, else `models.implementer`. The implement round warns when the
    task has no estimate and the small model differs from the implementer's, so the small choice cannot
    apply, and when the deprecated `workers.implementer_model` is set."""
    warns: list[str] = []
    est = None
    if runs.SEAT[phase] == "implementer" and tasklog.kind_of(meta) != "refactor":
        est = task_estimate_s(q, str(meta["task_id"]))
    if phase == "implement":
        small, plain = models.model_for(cfg, "implementer_small"), models.model_for(cfg, "implementer")
        if est is None and tasklog.kind_of(meta) != "refactor" and small != plain:
            warns.append(f"models.implementer_small: the small choice cannot apply to {meta['task_id']}: it has no "
                         f"estimate (ccp tasks estimate), so its implementer takes the model {plain} (SPEC §2.4)")
        if (cfg.workers or {}).get("implementer_model"):
            warns.append("workers.implementer_model is deprecated: move its small and refactor aliases to "
                         "models.implementer_small and models.implementer_refactor (SPEC §2.4)")
    model, alias = runs.worker_model(cfg, phase, meta, est)
    return model, alias, warns


def report_lines(cfg: Config, phase: str, mode: str | None = None, *, runner: str) -> str:
    """The report contract's lines for `phase`, rendered from `report.SECTIONS` (§13.4): each section the phase
    carries (a resolution review's `Resolution:` and `Affected checks:` for `mode`), and, for a round that
    pushes a head, a line naming each verdict the product declares in plane.json `report.required_fields` with
    its allowed values, when it declares any. `runner` is the teammate the worker tells when its prompt was cut."""
    declared = (cfg.report or {}).get("required_fields") or []
    each = "; ".join(f"`{f['name']}: " + "|".join(f["values"]) + "`" for f in declared)
    return "".join(s.prompt.format(runner=runner, each=each) for s in report.sections_for(phase, mode)
                   if s.prompt and (declared or s.key != "fields"))


def reported_verdicts(cfg: Config, q: Path, task_id: str) -> tuple[str, dict[str, str]]:
    """§13.4: the declared verdicts as the task's latest done implement, fix, merge or ruling report
    states them, by declared name ("not stated" for one its report predates), and that run's id; ("", {})
    when the product declares none or no such report is in. Latest is by `reported_at`; reports in the
    same second go by when their run opened, then (opened in the same second too) a later round after an
    implement, then the higher round."""
    declared = (cfg.report or {}).get("required_fields") or []
    done = [r for r in runs.all_runs(q, task_id) if r.get("phase") in runs.CHANGE_PHASES
            and runs.state(r) == "reported" and r.get("outcome") == "done"]
    if not declared or not done:
        return "", {}
    last = max(done, key=lambda r: (str(r.get("reported_at") or ""), str(r.get("opened_at") or ""),
                                    r.get("phase") != "implement", runs.parse_id(r["run_id"])[2]))
    got = last.get("fields") or {}
    return last["run_id"], {f["name"]: got.get(f["name"], "not stated") for f in declared}


def prompt_token(run_id: str, body: str) -> str:
    """§13.2: the token on a rendered prompt's last line, `Prompt end: <token>`: a short hash of the run
    id and the prompt text above it, so it differs between runs and between renderings."""
    return hashlib.sha256(f"{run_id}\n{body}".encode()).hexdigest()[:12]


def prompt_path(q: Path, run_id: str) -> Path:
    """Where `ccp prompt` writes a run's rendered prompt: `prompts/<task_id>/<phase>[-n]-prompt.md`."""
    task, phase, n = runs.parse_id(run_id)
    return q / "prompts" / task / (f"{phase}-{n}-prompt.md" if n > 1 else f"{phase}-prompt.md")


def pointer(prompt_file: Path) -> str:
    """§13.2: the Agent call's prompt, a pointer to the rendered file, never its text retyped."""
    return f"Your full instructions are in {prompt_file}. Read that file in full first and follow it exactly."


def suite_lanes(cfg: Config, phase: str) -> str:
    """§14.1: the phase's lanes, by role. A lane plane.json `suite.lanes` declares (an argv or stages) runs
    as `--lane <lane>` with nothing after `--`, so the worker runs what the product declares; a lane it does
    not declare takes the command after `--`."""
    from ccp.config import SUITE_ROLES, lane_for  # noqa: PLC0415
    declared = (cfg.suite or {}).get("lanes") or {}
    v: dict[str, str] = {}
    for r in SUITE_ROLES:
        lane = lane_for(cfg, r)
        own = isinstance(declared, dict) and lane in declared
        v[r] = f"`--lane {lane}`" + (" with nothing after `--`" if own else "")
        v[f"{r}_for"], v[f"{r}_as"] = (": ", ", as plane.json gives it") if own else (" for ", "")
    return SUITE_LANES[phase].format(**v)


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
    """The main checkout of the product repo: the runner works from a worktree of it (§12.1, `wt.main_of`)."""
    from ccp import wt  # noqa: PLC0415

    return wt.main_checkout(cfg)


def worktree_for(cfg: Config, prefix: str, nnnn: str) -> str | None:
    """The task's `<prefix>-<nnnn>` worktree under `worktrees.dir`, resolved against the main checkout
    (§12.1, as `wt.base_dir`); None when the product names no `worktrees.dir`."""
    d = (cfg.worktrees or {}).get("dir")
    return str((main_checkout(cfg) / d).resolve() / f"{prefix}-{nnnn}") if d else None


def fragment(cfg: Config) -> tuple[str, str]:
    rel = cfg.prompts["fragment"] if cfg.prompts else None
    if not rel:
        return "", ""
    f = cfg.root / rel
    if not f.is_file():
        raise QueueError(f"plane.json prompts.fragment names {rel}, which does not exist", 2)
    return rel, f.read_text().strip()


def prior_reports(q: Path, task_id: str, phase: str) -> str:
    # §13.2: a merge or ruling round works from the tip or the runner's note, not from findings
    want = {"fix": ("review", "verify"), "review": runs.CHANGE_PHASES,
            "verify": (*runs.CHANGE_PHASES, "review")}.get(phase, ())
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


def env_values(cfg: Config, fields: dict[str, str]) -> dict[str, str]:
    """§13.3: `prompts.worker_env` rendered with these fields, {} when the product names none. A value that
    looks like a secret is refused: the env file is the queue's, and the prompt prints the values."""
    from ccp import health  # noqa: PLC0415

    spec = (cfg.prompts or {}).get("worker_env") or {}
    out = {k: VAR_RE.sub(lambda m: fields[m.group(1)], v) for k, v in spec.items()}
    for k, v in out.items():
        if health.looks_like_secret(v):
            raise QueueError(f"prompts.worker_env.{k} renders to what looks like a secret: name a file that holds "
                             "it instead (SPEC §13)", 2)
    return out


def export_lines(values: dict[str, str]) -> str:
    """The env file's lines: `export NAME='value'`, the value shell-quoted (§13.3)."""
    import shlex  # noqa: PLC0415
    return "".join(f"export {k}={shlex.quote(v)}\n" for k, v in values.items())


def env_lines(cfg: Config, worktree: str) -> str:
    """`ccp prompt env <worktree>` (§13.3): the `worker_env` lines the workers of that worktree would get,
    rendered from its record (its path, or its name, as `ccp wt` recorded it), opening no run and writing
    nothing. `run_id` and `phase` are the open run bound to it when there is one, else stay `<run_id>`
    and `<phase>`. An empty string when the product names no `worker_env`; a worktree with no record
    is refused (exit 2)."""
    from ccp import wt  # noqa: PLC0415

    q = root()
    st = wt.recorded_at(q, Path(worktree)) if Path(worktree).exists() else None
    if st is None and worktree and "/" not in worktree and not worktree.startswith("."):
        st = wt.load(q, worktree)
    if not st or not st.get("path"):
        raise QueueError(f"{worktree}: no worktree `ccp wt` made is recorded there in this queue (SPEC §12.1)", 2)
    if not (cfg.prompts or {}).get("worker_env"):
        return ""
    here = Path(str(st["path"])).resolve()
    bound = None
    for rec in reversed(runs.all_runs(q, st.get("task_id") or None) if st.get("task_id") else []):
        try:
            same = bool(rec.get("worktree")) and Path(str(rec["worktree"])).resolve() == here
        except (OSError, ValueError):
            same = False
        if same and runs.state(rec) in runs.OPEN:
            bound = rec
            break
    kind = str(st.get("kind") or "")
    return export_lines(env_values(cfg, {
        "run_id": str(bound["run_id"]) if bound else "<run_id>",
        "phase": str(bound.get("phase") or "<phase>") if bound else "<phase>",
        "task_id": str(st.get("task_id") or ""), "nnnn": str(st.get("nnnn") or ""), "worktree": str(st["path"]),
        "kind": kind, "seat": str(st.get("seat") or (wt.KINDS[kind][0] if kind in wt.KINDS else "")),
        "round": str(st["round"]),
        "main_checkout": str(main_checkout(cfg)), "queue_root": str(q), "project_id": cfg.project_id}))


def worker_env(cfg: Config, q: Path, prompt_file: Path, fields: dict[str, str]) -> tuple[str, str]:
    """§13: `prompts.worker_env` rendered for this run into `<prompt>-env.sh` beside the prompt, as
    `export NAME='value'` lines. Returns the file's path and a one-line list of what it sets, or two
    empty strings when the product names none. A value that looks like a secret is refused: the
    file is the queue's, and the prompt prints the values."""
    import shlex  # noqa: PLC0415

    out = env_values(cfg, fields)
    if not out:
        return "", ""
    f = prompt_file.with_name(prompt_file.name.replace("-prompt.md", "-env.sh"))
    body = ("# ccp prompt: this run's environment (plane.json prompts.worker_env, SPEC §13)\n" + export_lines(out))
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


def review_gate(cfg: Config, q: Path, tid: str, phase: str,
                a: Any) -> tuple[dict[str, str] | None, dict[str, Any] | None]:
    """§15.2: a verify of a head with a fix round after the last review is refused (exit 4), unless the
    product's `verify.skip_review` or a review prover proves the fix, its `verify.skip_review_after_clean` takes it as a fix of
    a clean review's minor findings, or the runner passes `--allow-unreviewed-fix --reason "<the
    lead's or the operator's words>"`. The override, when given, is taken and recorded as is, and no proof
    runs. Returns what to record on the run: the override (a friction note and a ledger event) and the
    proven skip, each None when it does not apply."""
    allow = bool(getattr(a, "allow_unreviewed_fix", False))
    reason = (getattr(a, "reason", None) or "").strip()
    if phase != "verify":
        if allow:
            raise QueueError("--allow-unreviewed-fix is for `ccp prompt verify` only", 2)
        return None, None
    if allow and not reason:
        raise QueueError('--allow-unreviewed-fix needs --reason "<the lead\'s or the operator\'s words>"', 2)
    why = runs.unreviewed_fix(q, tid, a.head)
    if why is None:
        return None, None
    if not allow:
        skipped, unproven = verify.skip_review(cfg, q, tid, a.head, a.pr)
        if skipped:
            return None, skipped
        skipped, unclean = verify.skip_after_clean(cfg, q, tid, a.head)
        if skipped:
            return None, skipped
        no_skip = f" ({unproven})" if unproven else ""  # §15.2: names the settings, read from the integration branch
        no_skip += f" (verify.skip_review_after_clean does not apply: {unclean})" if unclean else ""
        raise QueueError(f"{why}{no_skip}. Override once, on the lead's or the operator's word: "
                         '--allow-unreviewed-fix --reason "<their words>"', 4)
    from ccp import health  # noqa: PLC0415
    if health.looks_like_secret(reason):
        raise QueueError("--reason looks like it holds a secret; say it without the value", 2)
    return {"reason": reason, "was": why}, None


def minor_only(q: Path, skipped: dict[str, Any] | None) -> dict[str, Any]:
    """§15.2: the verify prompt's view of a `minor-only` review skip (`verify.skip_review_after_clean`): the
    clean review it follows, the head that review judged, its report, and its findings below MAJOR. Empty
    values when this verify follows no such skip."""
    if not skipped or skipped.get("reason") != "minor-only":
        return {"minor_only": False, "minor_review_run": "", "minor_reviewed": "", "minor_review_report": "",
                "minor_findings": ""}
    return {"minor_only": True, "minor_review_run": str(skipped["review_run"]),
            "minor_reviewed": str(skipped["reviewed"]), "minor_review_report": str(skipped["report"]),
            "minor_findings": ", ".join(f"{k}={n}" for k, n in skipped["findings"].items())}


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


def tip_gate(cfg: Config, q: Path, tid: str, phase: str, a: Any) -> list[str]:
    """§16.5 rule 4: a verify of a head behind the integration tip (the task log and
    `merge.behind_tip_ignore` aside) is refused (exit 4), nothing opened, with one runner or several
    (ADR-0035 D2). §15.2: a review of a head behind the tip is refused the same way only when merging the tip
    into it would conflict in a file outside the task log and `merge.behind_tip_ignore` (`gitmerge.probe`); a
    head behind by a clean merge is reviewed. A tip or head that cannot be fetched to judge is a warning,
    returned to record on the run; with several runners close still checks."""
    from ccp import gitmerge, lifecycle, parallel  # noqa: PLC0415
    if phase not in ("review", "verify"):
        return []
    integ = integration_branch(q)
    rule = "SPEC §15.2" if phase == "review" else "SPEC §16.5 rule 4"
    try:
        behind = lifecycle.behind_tip(cfg, a.pr, tid, a.head, integ)
    except lifecycle.Unjudged as exc:
        what = f"origin/{integ}" if exc.what == "tip" else f"the head {a.head[:7]}"
        # close checks only with several runners, and only a verify's head
        close = "; close checks it" if phase == "verify" and parallel.enabled(cfg) else ""
        return [f"behind_tip not checked: {what} could not be fetched ({rule}){close}"]
    if not behind:
        return []
    merge_in = (f"`ccp prompt merge {tid} --pr {a.pr} --head {a.head[:7]}` has the implementer merge "
                f"origin/{integ} into task/{tid} (a plain push, never a rebase)")
    if phase == "review":
        p = gitmerge.probe(cfg.root, a.head, f"origin/{integ}")
        if p.failed:
            return [f"behind_tip not checked: {gitmerge.old_git_text(p)} ({rule})"]
        skip = [x.strip().removeprefix("./").rstrip("/") for x in
                lifecycle.task_log_paths(cfg) + [str(x) for x in ((cfg.merge or {}).get("behind_tip_ignore") or [])]]
        files = sorted(f for f in p.conflicts if not any(f == x or f.startswith(x + "/") for x in skip))
        if not files:
            return []
        raise QueueError(f"behind_tip: merging origin/{integ} into the head {a.head[:7]} would conflict in "
                         f"{', '.join(files[:5])}" + (f" and {len(files) - 5} more" if len(files) > 5 else "")
                         + f". Merge the tip in first: {merge_in}, then review the new head (SPEC §15.2)", 4)
    raise QueueError(f"behind_tip: the head {a.head[:7]} lacks {len(behind)} commit(s) on origin/{integ} that change "
                     f"more than the task log and merge.behind_tip_ignore ({', '.join(behind[:5])}). Merge the "
                     f"tip in first: {merge_in}, then verify the new head (SPEC §13.2, §16.5 rule 4)", 4)


def resolution_gate(cfg: Config, q: Path, tid: str, phase: str, a: Any) -> bool:
    """§13.2: `--mode resolution` opens a resolution review of a conflicted integration merge. True for it,
    False with no `--mode`. Refused (exit 2, nothing opened): any phase but review; a task with no review that
    reported `done`; a latest such review that is a resolution review judged `beyond` (a full review is due,
    §15.2); a round since the latest such review that is not a merge round; a head that is not a merge
    commit (two parents or more); a head whose remerge diff (`gitmerge.remerge_diff`) is empty, a clean merge."""
    mode = getattr(a, "mode", None)
    if not mode:
        return False
    if phase != "review":
        raise QueueError(f"--mode {mode} is for `ccp prompt review` only, not {phase} (SPEC §13.2)", 2)
    from ccp import gitmerge  # noqa: PLC0415
    rs = [r for r in runs.all_runs(q, tid) if runs.state(r) != "abandoned"]
    done = [r for r in rs if r.get("phase") == "review" and runs.state(r) == "reported" and r.get("outcome") == "done"]
    if not done:
        raise QueueError(f"{tid} has no review that reported done: a resolution review never stands in for the "
                         "first review; run `ccp prompt review` in full (SPEC §13.2)", 2)
    last = done[-1]
    if runs.is_resolution_beyond(last):  # §15.2: a beyond resolution is not a review of the head; a full one is due
        raise QueueError(f"{last['run_id']}: the resolution review judged it beyond the conflict hunks: run a full "
                         "`ccp prompt review` (SPEC §13.2, §15.2)", 2)
    since = [r for r in rs if r.get("phase") in runs.REWORK_PHASES
             and str(last.get("opened_at") or "") <= str(r.get("opened_at") or "")]
    other = next((r for r in since if r.get("phase") != "merge"), None)
    if other:
        raise QueueError(f"{other['phase']} round {other['run_id']} is newer than the last review {last['run_id']}: a "
                         "resolution review covers merge rounds only; run `ccp prompt review` in full (SPEC §13.2)", 2)
    head = str(a.head).strip()
    if git(cfg.root, "cat-file", "-e", f"{head}^{{commit}}").returncode != 0:  # not here: the PR's ref, then the branch
        for ref in ([f"refs/pull/{a.pr}/head"] if a.pr else []) + [f"task/{tid}"]:
            if git(cfg.root, "fetch", "-q", "origin", ref).returncode == 0 \
                    and git(cfg.root, "cat-file", "-e", f"{head}^{{commit}}").returncode == 0:
                break
        else:
            raise QueueError(f"the head {head[:12]} could not be read here or fetched from origin (SPEC §13.2)", 2)
    parents = git(cfg.root, "rev-list", "--parents", "-n", "1", head).stdout.split()[1:]
    if len(parents) < 2:
        raise QueueError(f"the head {head[:12]} is not a merge commit (it has {len(parents)} parent(s)): a resolution "
                         "review judges the merge round's head (SPEC §13.2)", 2)
    if not gitmerge.remerge_diff(cfg.root, head).strip():
        raise QueueError(f"no conflict was resolved: a clean merge needs no resolution review (the head {head[:12]} "
                         "has an empty remerge diff; SPEC §13.2)", 2)
    return True


def resolution_verify(q: Path, tid: str, phase: str, head: str) -> dict[str, Any]:
    """§15.6 rule 3: the verify prompt's view of a contained resolution review: set when the task's latest
    review that reported `done` is a resolution review that judged `head` and found the resolution `contained`.
    The checks it names to rerun, and the head of the task's latest approve (`old`) the other checks rest
    on; with no approve yet, every check runs."""
    none: dict[str, Any] = {"resolved_verify": False, "resolution_run": "", "has_affected": False,
                            "affected_checks": "", "has_old": False, "old_approve": ""}
    if phase != "verify":
        return none
    rs = [r for r in runs.all_runs(q, tid) if runs.state(r) != "abandoned"]
    done = [r for r in rs if r.get("phase") == "review" and runs.state(r) == "reported" and r.get("outcome") == "done"]
    last = done[-1] if done else None
    if not last or last.get("mode") != "resolution" or last.get("resolution") != "contained" \
            or not verify.heads_match(str(last.get("head") or ""), head):
        return none
    affected = [str(x) for x in last.get("affected_checks") or []]
    approves = [r for r in runs.all_runs(q, tid) if r.get("phase") == "verify" and r.get("verdict") == "approve"
                and r.get("head")]
    old = str(approves[-1]["head"]) if approves else ""
    return {"resolved_verify": True, "resolution_run": str(last["run_id"]), "has_affected": bool(affected),
            "affected_checks": ", ".join(affected), "has_old": bool(old), "old_approve": old}


def body_gate(cfg: Config, tid: str, phase: str, pr: str) -> list[str]:
    """§15.2: a review of a PR whose body does not contain the task id is refused (exit 2), naming the
    task and the PR, before anything is opened: the runner repairs the body first. The body is read from
    the PR host (`prhost.body`); one that cannot be read is a warning, returned to record on the run, and
    the review opens."""
    if phase != "review":
        return []
    try:
        body = prhost.body(cfg, str(pr))
    except prhost.HostError as exc:
        return [f"the PR body was not checked for {tid} (SPEC §15.2): {exc}"]
    if tid not in body:
        raise QueueError(f"PR #{pr}'s body does not contain the task id {tid}: it may hold another task's body. "
                         f"Repair it (`gh pr edit {pr} --body-file <file>`, naming {tid}), then run "
                         f"`ccp prompt review {tid}` again (SPEC §15.2)", 2)
    return []


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


def rules_doc_for(cfg: Config) -> str:
    """The house rules doc a worker is told to read (§19.11): the architect's `rules_doc` while the file exists.
    The default names a file a product may not have yet, and a worker is never sent to read one that is absent."""
    rel = (cfg.architect or {}).get("rules_doc") or ""
    return rel if rel and (cfg.root / rel).is_file() else ""


def build(cfg: Config, a: Any) -> dict[str, Any]:
    q = root()
    phase = a.phase
    meta = task_meta(cfg, a.task)
    tid = str(meta["task_id"])
    nnnn = refs.ids(cfg).task_number(tid)
    note = read_note(a)
    if phase != "implement" and not (a.pr and a.head):
        raise QueueError(f"{phase}: give --pr and --head (the PR and the head this run works on)", 2)
    if phase == "ruling" and not note:  # §13.2: the ruling the round applies reaches the worker as the note
        raise QueueError("ruling: give the lead's ruling with --note or --note-file (SPEC §13.2)", 2)
    st = load_task_state(q, tid)
    if not st.get("lease_holder") or st.get("status") == "done":
        raise QueueError(f"{tid} is not claimed (or is done): `ccp tasks claim {tid}` first", 3)
    caller = opener(q, tid, st, getattr(a, "holder", None))
    resolution = resolution_gate(cfg, q, tid, phase, a)
    override, skipped = review_gate(cfg, q, tid, phase, a)
    repeat = repeat_gate(q, tid, phase, note)
    tip_warn = tip_gate(cfg, q, tid, phase, a)
    body_warn = body_gate(cfg, tid, phase, a.pr)
    runs.check_pending(q, runs.AGENT_TYPE[phase], a.supersede, caller)
    runs.check_running_rounds(q, tid, phase, caller, a.supersede)
    from ccp import usage  # noqa: PLC0415
    # §25.4 the session park: no run opens at or past the 5-hour park % (exit 6, the task parked). Below the
    # refusal gates, so a refused prompt reads no usage (§25.1). Best effort: only the park refuses; a failed
    # reading or wait write is a warning
    session_warn = usage.session_step(cfg, q, tid, f"ccp prompt {phase}",
                                      read=lambda: usage.reading_warnings(cfg, q, usage.reading(cfg, q)))
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
    prompt_file = prompt_path(q, run_id)
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    workdir = (worktree if phase in runs.CHANGE_PHASES else own) or ""
    from ccp import wt  # noqa: PLC0415
    kind = "impl" if phase in runs.CHANGE_PHASES else "rev" if phase == "review" else "ver"
    # §13.3: the worker's worktree kind, seat and round, from the record of the worktree the run is bound
    # to (§12.1); with none recorded there, the phase's kind, its default seat and the round its name gives
    bound = wt.recorded_at(q, Path(workdir)) if workdir else None
    env_file, env_list = worker_env(cfg, q, prompt_file, {
        "run_id": run_id, "task_id": tid, "nnnn": nnnn, "phase": phase, "worktree": workdir,
        "kind": str(bound["kind"]) if bound and bound.get("kind") else kind,
        "seat": str(bound["seat"]) if bound and bound.get("seat") else wt.KINDS[kind][0],
        "round": str(bound["round"] if bound else wt.round_of(Path(workdir).name) if workdir else 1),
        "main_checkout": str(main_checkout(cfg)), "queue_root": str(q), "project_id": cfg.project_id})
    verdicts_run, verdicts = reported_verdicts(cfg, q, tid) if phase == "review" else ("", {})
    runner = holder_teammate(q, tid)
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
        "rules_doc": rules_doc_for(cfg),
        "fragment": frag, "fragment_path": frag_path, "note": note or "",
        "prior_reports": prior_reports(q, tid, phase),
        "queue_root": str(q), "ccp": ccp_command(cfg), "report_path": str(report),
        "verification_example": str(PLANE / "contracts" / "verification.example.json"),  # §15.4, from any checkout
        "runner": runner,  # §10.2, §16.4: the runner that holds this task, as bound
        "report_lines": report_lines(cfg, phase, "resolution" if resolution else None, runner=runner),
        "suite_lanes": suite_lanes(cfg, phase),
        # §13.4: the product's declared verdicts, as the latest implementer report states them
        "report_verdicts": "; ".join(f"`{k}: {v}`" for k, v in verdicts.items()), "report_verdicts_run": verdicts_run,
        "full_lane": lane_for(cfg, "full"),  # §14.1: the lane the product's full suite runs as
        "part_lane": lane_for(cfg, "part"),  # §14.1: the lane a subset or a mutation run goes through
        "gate_lane": lane_for(cfg, "gate"),  # §14.2: the verifier asks for a cold gate with `--cold` on it
        "worker_env": env_list, "worker_env_file": env_file,
        # §15.3: the product's content-keyed test cache, when its plane.json accepts the hits
        "accept_cache": bool(verify.cache_rule(cfg)), "cache_max_age_days": (verify.cache_rule(cfg) or {}).get("max_age_days") or "",
        "cold_gate": verify.cold_gate(cfg, meta),
        # §15.2: the reviewer and the verifier check the PR's SPEC lines against the signed text
        "brief_sign_off": "brief" in tasklog.sign_off_stages(meta),
        # §15.3: the reviewer's touched modules through the same cache, when the product says so
        "review_cache": bool((verify.cache_rule(cfg) or {}).get("review")),
        # §15.2: the fail-fast pre-gate names the product's house-rule checks
        "architect_checks": ", ".join(f"`{c['cmd']}`" for c in (cfg.architect or {}).get("checks") or []),
        "budgets": bool((cfg.architect or {}).get("budgets")),  # §20.2: `ccp budgets check` in the gates
        **minor_only(q, skipped),  # §15.2: a fix of a clean review's minor findings, verified with no new review
        "resolution": resolution,  # §13.2: a resolution review of a conflicted integration merge
        **resolution_verify(q, tid, phase, a.head or ""),  # §15.6 rule 3: the verify after a contained one
    }
    body = render((TEMPLATES / f"{phase}.md").read_text(), values).rstrip() + "\n\n" \
        + render((TEMPLATES / "_common.md").read_text(), values).rstrip() + "\n"
    token = prompt_token(run_id, body)  # §13.2: the last line proves the worker got the whole prompt
    body += f"\n{PROMPT_END}{token}\n"
    report.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(body)
    ref = audit(q, cfg, tid, phase, prompt_file, run_id, meta, worktree if phase in runs.CHANGE_PHASES else own, note)
    prune_audits(q, cfg)
    warnings: list[str] = list(session_warn) + tip_warn + body_warn
    model, alias, model_warns = worker_model(cfg, q, phase, meta)  # §2.4
    warnings.extend(model_warns)
    rec = runs.open_run(q, cfg, tid, phase, prompt_ref=ref, note=note, supersede=a.supersede, warnings=warnings, by=caller,
                        extra={"pr": a.pr or None, "head": a.head or None, "prompt_token": token,
                               **({"expected_model": model} if model else {}),
                               # §14.1: a suite run from inside this worktree binds to the run
                               "worktree": (worktree if phase in runs.CHANGE_PHASES else own) or None,
                               **({"allow_unreviewed_fix": override} if override else {}),
                               **({"review_skip": skipped} if skipped else {}),
                               **({"mode": "resolution"} if resolution else {}),
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
            "report_path": str(report), "prompt_ref": ref, "prompt_token": token, "env_file": env_file or None, "expected_model": rec["expected_model"],
            "expected_effort": rec["expected_effort"], **({"allow_unreviewed_fix": override} if override else {}),
            **({"review_skip": skipped} if skipped else {}),
            **({"mode": "resolution"} if resolution else {}),
            **({"repeat_verify": repeat} if repeat else {}),
            **({"report_fields": {"run_id": verdicts_run, "fields": verdicts}} if verdicts else {}),
            **({"warnings": warnings} if warnings else {}),
            "agent_call": {"subagent_type": runs.definition(cfg, runs.AGENT_TYPE[phase])[0], "description": desc,
                           "prompt": pointer(prompt_file), **({"model": alias} if alias else {})}}

