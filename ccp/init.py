"""`ccp init`: adopt a product with one command (SPEC §4.3, §4.5, §8.3).

Run in a product's repository, it writes the product footprint (the PROJECT, SPEC and delivery
templates, with `--starter-rules` the plane's starter house rules (§20.5), a minimal `plane.json`,
`.plane-runtime/` in `.gitignore`, the plugin anchor merged into `.claude/settings.json` with the
session settings `subagentPromptCacheTtl` and `autoCompactWindow`, the one `CLAUDE.md` line) and,
outside the repository, the binding in this plane's bindings directory and the queue directory it
names. Inside a sandbox (`ccp sandbox`, §29.3) the binding is `<project_id>.yaml` in the sandbox's
bindings directory and the queue is the sandbox's, `--force` or not; a `--queue-root` naming any other
path is refused, writing nothing. The binding is the one source of truth: every reader resolves it through `lib.binding_path`,
and no copy goes into the queue (§8.3).

It never overwrites a file without `--force`: an existing file is kept and listed as kept, so a
second run, or a run after the binding was edited, changes nothing. A session setting the product
already has is never overwritten, `--force` or not; the result's `settings` names each as added or
kept. It refuses, writing nothing, when keeping a file would leave the product inconsistent: a
`plane.json` naming another project id or not loading, a binding for the id that names another
product root, or a settings file that is not a JSON object. It also refuses, writing nothing, a
`--gate` it cannot split and a product root or queue path holding `#`, which every binding reader
cuts off as a comment.

Pull requests need a GitHub origin until the PR host is an adapter (ADR-0040 D7): when the product
has no `origin`, or its host is not GitHub, init warns on stderr and in the result's `warnings`,
naming the commands that need one, and adopts the product all the same.

When the task directory already holds task files with no frontmatter (an earlier plane generation's),
the result's `warnings` names their count and `ccp tasks migrate` (§5.3).
When the queue it keeps already holds entries `ccp plane check` would list (an earlier plane
generation's), the result's `warnings` names their count and `ccp plane check --archive` (§31.3); init
moves nothing.

It records the adoption in the queue's ledger, a `plane`/`adopted` event (the plane checkout's HEAD, the
binding `written` or `kept`), when it writes the binding, or when the ledger holds no such event yet (a
queue from before the event, re-adopted), then with `since`, the binding file's last change, as the
adoption point; a rerun on an adopted product records nothing (§4.5). `ccp health` reads from the latest
one onwards (§27.1).

A kept binding is checked against the current shape (§8.3): the result's `warnings` names, with the binding
file and the fix, each key it lacks (the contract's required keys, `product_root`, a `runner` block with
`agent_type` and `name`) and each obsolete key it carries (the keys §8.3 says are ignored, a key the
contract marks ignored or retired, a key it does not list). An existing `INDEX.yaml` is kept and listed
as kept. With `--gate`, the gate lane is one stage, `gate`, whose `cmd` is the line as given, and a
`standing-dod.md` init writes names the gate in its placeholder product item (§4.5). A blank `--gate` (empty
or only whitespace) is refused (exit 2) before anything is written.

With `--permissions` it writes nothing: in an adopted product it prints the runner's and workers'
permission allowlist and a deny list for destructive commands, as a JSON `permissions` block for the
operator to apply to `.claude/settings.json` (§4.5, §18.5).

With `--rules-doc PATH` it brings a product's existing house rules in (§4.5, §20.1): it lists each rule
with no `check:` line and, with `--adopt`, gives each a `check: pass` line (the architect judges it),
refusing, writing nothing, when that would put the doc over `rules_max_lines`. It writes nothing
else, and points at the plane's starter rules (§20.5) for the checks the plane already runs.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any

from ccp import config, docrules, refs, rules, tasklog
from ccp.queue import PLANE, QueueError, _main_worktree, emit, lib, queue_leftovers, script_drift

TEMPLATES = PLANE / "templates"
SCHEMA = PLANE / "contracts" / "project.schema.json"
# §8.3: the binding's nested keys the plane ignores, each `<top>.<child>` a first-level child of its top-level
# key (the binding read nested by indentation, `lib.read_binding`); a top-level key whose contract description says
# ignored or retired is obsolete too, and so is one the contract does not list.
IGNORED_NESTED = ("seats.runner", "seats.verifier", "seats.watchdog", "cadence.verify_stale_minutes")
IGNORED_TOP = ("email",)
RETIRED_RE = re.compile(r"\b(ignored|retired)\b", re.I)
RUNNER_KEYS = ("agent_type", "name")
# §4.5, §21.2: the template's placeholder product item, and the gate item init writes in its place.
STANDING_DOD = "docs/delivery/standing-dod.md"
PLACEHOLDER_RE = re.compile(r"^\s*\d+\.\s*…\s*$")
GATE_ITEM = "7. **The gate is `{gate}`**, run by the verifier at the PR head (item 5)."
# What init copies: product path -> template.
COPIES = {
    "docs/PROJECT.md": "docs-project/PROJECT.md",
    "docs/SPEC.md": "docs-project/SPEC.md",
    "docs/delivery/TEMPLATE-task.md": "docs-delivery/TEMPLATE-task.md",
    "docs/delivery/WRITING-tasks.md": "docs-delivery/WRITING-tasks.md",
    "docs/delivery/standing-dod.md": "docs-delivery/standing-dod.md",
}
# §20.5: `--starter-rules` writes the starter house rules here, and these settings into a new plane.json:
# the set adopted, nothing declined, and the `package_docs` rules its `docs` checks name, with neutral
# defaults (no language pack; the docs are the top-level ones init writes, the SPEC its own).
STARTER_RULES_DOC = ("docs/ENGINEERING.md", "docs-project/starter-rules.md")
STARTER_CONFIG: dict[str, Any] = {
    "package_docs": {"language": "none", "rules": {
        "history_attr": "history",
        "no_ids": {"globs": ["docs/*.md"]},
        "citations": {"globs": ["docs/*.md"], "targets": ["docs/SPEC.md"]}}},
    "docs": {"starter_rules": {"declined": {}}},
}
WORKTREES_DIR = ".plane-runtime"
# §4.3: the anchor and the CLAUDE.md line, the one source the SPEC and the README quote. The anchor
# names the plane's marketplace, not a version, so a release needs no product commit; the env entry
# turns on the agent team the plane runs on (§2.2).
ANCHOR: dict[str, dict[str, Any]] = {
    "extraKnownMarketplaces": {"ccp": {"source": {"source": "github", "repo": "alexykot/ccp"}, "autoUpdate": True}},
    "enabledPlugins": {"ccp@ccp": True},
    "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
}
CLAUDE_LINE = "This repo is delivered by CCP (Claude Control Plane): its plugin and `ccp`."
# §2.4, §4.5: the session settings init adds when absent and never overwrites: the runner teammate's
# prompt-cache lifetime, and the lead's compaction window (the binding's `lead.auto_compact_window`).
CACHE_TTL_SETTING = ("subagentPromptCacheTtl", "1h")
COMPACT_SETTING = "autoCompactWindow"
# §4.5, §18.5: what `--permissions` allows besides `ccp`, the plane's seat scripts and the gate lane:
# the git verbs the runner and its workers run, and the destructive commands it denies.
SEAT_SCRIPTS = ("scripts/team.sh", "scripts/spec-maintainer-ask.sh")
GIT_VERBS = ("add", "branch", "commit", "diff", "fetch", "log", "ls-files", "merge", "merge-base", "push",
             "rev-parse", "show", "status", "worktree")
# An entry is a prefix (`Bash(cmd:*)`), or, holding a `*`, a wildcard rule matched whole (`Bash(cmd)`): a
# forced push is denied with its flag right after `push`, after the remote or branch, and at the end.
FORCE_FLAGS = ("--force", "--force-with-lease", "-f")
DENY = (*(f"git push {flag}" for flag in FORCE_FLAGS),
        *(f"git push * {flag}{tail}" for flag in FORCE_FLAGS for tail in (" *", "")),
        "git reset --hard", "git clean", "git branch -D", "git stash", "git checkout --", "git restore", "rm -rf",
        "gh repo delete")
# ADR-0040 D7: what needs a GitHub origin and a logged-in `gh` until the PR host is an adapter.
GITHUB_ONLY = ("ccp verify merge-ok", "ccp tasks close (its default merge and its merge confirmation)",
               "the workers' `gh pr` steps (the implementer's PR, review and verify)")
# The init flags that write: `--permissions` writes nothing, so it refuses them.
WRITING_FLAGS = (("--project-id", "project_id"), ("--queue-root", "queue_root"),
                 ("--integration-branch", "integration_branch"), ("--gate", "gate"),
                 ("--starter-rules", "starter_rules"), ("--force", "force"))


def _default_id(root: Path) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", root.name.lower())).strip("-")


def _paragraph_break(text: str) -> str:
    """What goes between `text` and an appended line so the line is its own paragraph: nothing after
    an empty file or one already ending in a blank line, else the line break(s) up to one blank line."""
    lines = text.splitlines()
    if not text.strip() or not lines[-1].strip():
        return "" if not text or text.endswith("\n") else "\n"
    return "\n" if text.endswith("\n") else "\n\n"


def origin_url(root: Path) -> str | None:
    """The product's `origin` URL, None when it has none."""
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    url = r.stdout.strip()
    return url if r.returncode == 0 and url else None


def url_host(url: str) -> str | None:
    """The host of a remote URL (lowercased), "" for a local path or a URL with none, None when the URL
    does not parse."""
    if "://" in url:
        try:
            return (urlsplit(url).hostname or "").lower()
        except ValueError:  # a malformed URL, such as an unclosed `[` around an IPv6 host
            return None
    scp = re.match(r"^(?:[^@/:]+@)?([^/:]+):", url)  # git's scp-like form: a colon before any slash
    return scp.group(1).lower() if scp and len(scp.group(1)) > 1 else ""


def origin_host(root: Path) -> str | None:
    """The host of the product's `origin` URL (lowercased), "" for a local path or a URL with none,
    None when there is no origin or its URL does not parse. Only the host is kept: a URL may carry
    credentials."""
    url = origin_url(root)
    return url_host(url) if url else None


def is_github(host: str | None) -> bool:
    return host is not None and (host == "github.com" or host.endswith(".github.com"))


def github_warning(root: Path) -> str | None:
    """ADR-0040 D7: the warning init gives when the product's origin is missing, does not parse, or is
    not on GitHub."""
    url = origin_url(root)
    host = url_host(url) if url else None
    if is_github(host):
        return None
    if url and host is None:
        bare = re.sub(r"^([^:/]+://).*@", r"\1", url)  # named without anything that may be credentials
        where = f"has an origin URL that does not parse ({bare})"
    else:
        where = "has no origin" if host is None else (f"has its origin on {host}" if host else "has a local origin")
    return (f"pull requests need a GitHub origin and a logged-in `gh`, and this product {where}: "
            f"{'; '.join(GITHUB_ONLY)} will fail until it has one (ADR-0040)")


def binding_shape_warnings(binding: Path, text: str) -> list[str]:
    """§8.3: what a kept binding lacks and what obsolete keys it carries, each a warning naming the
    binding file and the fix."""
    schema = json.loads(SCHEMA.read_text())
    props: dict[str, Any] = schema.get("properties", {})
    # each top-level key with its first-level keys only (one with a value of its own has none)
    keys = {k: list(v) if isinstance(v, dict) else [] for k, v in lib.read_binding(text).items()}
    fix = f"edit {binding}, or run `ccp init --force` to rewrite it (its other edits are lost)"
    out: list[str] = []
    out += [f"the kept binding {binding} lacks `{k}`: {fix}"
            for k in (*schema.get("required", []), "product_root") if k not in keys]
    if "runner" not in keys or not keys["runner"]:
        out.append(f"the kept binding {binding} lacks the `runner` block (with `agent_type` and `name`): {fix}")
    else:
        out += [f"the kept binding {binding} lacks `runner.{k}`: {fix}" for k in RUNNER_KEYS if k not in keys["runner"]]
    for k in keys:
        if k not in props:
            out.append(f"the kept binding {binding} carries `{k}`, which {SCHEMA.name} does not list: {fix}")
        elif k in IGNORED_TOP or RETIRED_RE.search(str(props[k].get("description", ""))):
            out.append(f"the kept binding {binding} carries `{k}`, which the plane ignores (SPEC §8.3): {fix}")
    out += [f"the kept binding {binding} carries `{k}`, which the plane ignores (SPEC §8.3): {fix}"
            for k in IGNORED_NESTED if k.partition(".")[2] in keys.get(k.partition(".")[0], [])]
    return out


def standing_dod_text(gate: str | None) -> str:
    """The standing DoD init writes: the template, with `gate` named in its placeholder product item."""
    text = (TEMPLATES / COPIES[STANDING_DOD]).read_text()
    if not gate:
        return text
    return "".join(GATE_ITEM.format(gate=gate) + "\n" if PLACEHOLDER_RE.match(line) else line
                   for line in text.splitlines(keepends=True))


def placeholder_warnings(root: Path) -> list[str]:
    """§21.2: each numbered item of the product's standing DoD that is only `…`, the template's placeholder."""
    p = root / STANDING_DOD
    if not p.is_file():
        return []
    return [f"{STANDING_DOD}:{n}: item `{line.strip()}` is the template's placeholder: name the gate (item 5) and "
            "the product's own standing items there"
            for n, line in enumerate(p.read_text().splitlines(), 1) if PLACEHOLDER_RE.match(line)]


def binding_text(project_id: str, product_root: Path, queue_root: Path, branch: str) -> str:
    """The binding init writes (§8.3): the required keys, `production_branch` (the integration branch
    until the operator names another), the product root and the runner block."""
    return (f"project_id: {project_id}\n"
            f"integration_branch: {branch}\n"
            f"production_branch: {branch}\n"
            f"product_root: {product_root}\n"
            "durable_docs_path: docs/delivery/\n"
            f"queue_root: {queue_root}\n"
            "runner:\n"
            "  agent_type: ccp:delivery-runner\n"
            "  name: runner\n"
            f"  worktree: {product_root / WORKTREES_DIR / 'runner'}\n")


def plane_json_text(project_id: str, gate: str | None, starter_rules: bool = False) -> str:
    """A minimal plane.json (§8.1): the id, the worktrees directory, the gate lane when given, and the
    starter rules' settings with `--starter-rules` (§20.5). The gate lane is one stage, `gate`, running
    the line as given (§4.5), so a chained or `cd`-ing line keeps its meaning; a line `shlex` cannot
    split raises ValueError."""
    cfg: dict[str, Any] = {"project_id": project_id, "worktrees": {"dir": WORKTREES_DIR}}
    if gate:
        shlex.split(gate)  # an unclosed quote is refused, though the line is stored whole
        cfg["suite"] = {"lanes": {"gate": [{"name": "gate", "cmd": gate}]}}
    if starter_rules:
        cfg.update(json.loads(json.dumps(STARTER_CONFIG)))
    return json.dumps(cfg, indent=2) + "\n"


def _merged_settings(path: Path, compact_window: int) -> tuple[dict[str, Any], bool, dict[str, str]]:
    """The settings with the anchor merged in and the session settings (§4.5) added when absent; True
    when that changed them; each session setting as `added` or `kept`. Other keys, and any value the
    product already set for these, stay as they are."""
    data: Any = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            raise QueueError(f"ccp init: {path} is not valid JSON ({e}); fix it, then run init again", 2) from e
        if not isinstance(data, dict):
            raise QueueError(f"ccp init: {path} is not a JSON object; fix it, then run init again", 2)
    before = json.dumps(data, sort_keys=True)
    for key, add in ANCHOR.items():
        block = data.setdefault(key, {})
        if not isinstance(block, dict):
            raise QueueError(f"ccp init: {path}: `{key}` is not an object; fix it, then run init again", 2)
        for k, v in add.items():
            block.setdefault(k, v)
    session: dict[str, str] = {}
    for key, value in (CACHE_TTL_SETTING, (COMPACT_SETTING, compact_window)):
        session[key] = "kept" if key in data else "added"
        data.setdefault(key, value)
    return data, json.dumps(data, sort_keys=True) != before, session


def init(root: Path, project_id: str | None, queue_root: str | None, branch: str | None,
         gate: str | None, force: bool, starter_rules: bool = False) -> dict[str, Any]:
    """Adopt the product at `root`; returns what was written, merged and kept. Raises QueueError
    (nothing written) on a refusal."""
    if gate is not None and not gate.strip():  # §4.5: refused before anything is written
        raise QueueError("ccp init: --gate is blank: give the gate lane's command, or leave --gate out", 2)
    product_root = _main_worktree(root.resolve())
    plane_json = root / config.CONFIG_REL
    existing_id = None
    if plane_json.is_file():
        try:
            existing_id = str(json.loads(plane_json.read_text()).get("project_id") or "") or None
        except (json.JSONDecodeError, AttributeError):
            existing_id = None
    pid = project_id or existing_id or _default_id(product_root)
    if not config.PROJECT_ID_RE.match(pid):
        raise QueueError(f"ccp init: project id {pid!r} is not lowercase letters, digits and hyphens; "
                         "give one with --project-id", 2)
    if plane_json.is_file() and existing_id != pid and not force:
        raise QueueError(f"ccp init: {config.CONFIG_REL} names project {existing_id!r}, not {pid!r}; "
                         "pass that id, or --force to rewrite it", 2)
    keep_plane_json = plane_json.is_file() and not force
    if keep_plane_json:
        try:
            config.load(root)
        except config.ConfigError as e:
            raise QueueError(f"ccp init: {e}; fix it, or --force to rewrite it", 2) from e
    try:
        plane_json_new = plane_json_text(pid, gate, starter_rules)
    except ValueError as e:
        raise QueueError(f"ccp init: --gate {gate!r} is not a shell command line ({e})", 2) from e

    from ccp import sandbox as sandboxes  # noqa: PLC0415  (sandbox runs init as a child)
    sandbox = sandboxes.sandbox_of(root)
    if sandbox is not None and queue_root:  # §29.3: the sandbox's queue, never one elsewhere
        given, own = Path(queue_root).expanduser().resolve(), (sandbox / sandboxes.QUEUE).resolve()
        if given != own:
            what = ("is not the queue of the sandbox" if sandbox in given.parents
                    else "names a path outside the sandbox")
            raise QueueError(f"ccp init: --queue-root {given} {what} {sandbox}: its queue is {own}; leave "
                             "--queue-root out (SPEC §29.3)", 2)
    binding = (sandbox / sandboxes.BINDINGS if sandbox is not None else lib.bindings_dir()) / f"{pid}.yaml"
    old = binding.read_text() if binding.is_file() else None
    held = lib.read_binding(old or "")
    if old is not None and not force:
        bound = lib.binding_str(held, "product_root")
        if not bound or Path(bound).expanduser().resolve() != product_root:
            raise QueueError(f"ccp init: the binding {binding} names another product root ({bound}); "
                             "pick another --project-id, or --force to rewrite it", 2)
    keep_binding = old is not None and not force
    q = Path(queue_root).expanduser() if queue_root else None
    if sandbox is not None:
        q = sandbox / sandboxes.QUEUE
    if keep_binding:
        bound_q = lib.binding_str(held, "queue_root")
        if q and (not bound_q or Path(bound_q).expanduser().resolve() != q.resolve()):
            raise QueueError(f"ccp init: the binding {binding} names the queue {bound_q}, not {q}; "
                             "edit the binding, or --force to rewrite it", 2)
        q = Path(bound_q).expanduser() if bound_q else q
    q = (q or Path.home() / ".delivery-queue" / pid).resolve()
    for what, path in (("product root", product_root), ("queue path", q)):
        if "#" in str(path):
            raise QueueError(f"ccp init: the {what} {path} holds `#`, which the binding readers cut off "
                             "as a comment; use a path without it", 2)
    settings = root / ".claude" / "settings.json"
    # §4.5: the window is the binding's as it stands after init: the kept one's, else the default.
    lead = lib._yaml_block_scalars(old, "lead") if keep_binding and old else {}
    window = config.lead_auto_compact_window(lead)
    # refuses before anything is written
    merged_settings, settings_changed, session = _merged_settings(settings, window)

    out: dict[str, Any] = {"project_id": pid, "product_root": str(product_root), "binding": str(binding.resolve()),
                           "queue_root": str(q), "written": [], "merged": [], "kept": [], "settings": session}

    def put(path: Path, text: str, label: str) -> None:
        if path.exists() and not force:
            out["kept"].append(label)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        out["written"].append(label)

    copies = {**COPIES, **(dict([STARTER_RULES_DOC]) if starter_rules else {})}
    for rel, tpl in copies.items():
        put(root / rel, standing_dod_text(gate) if rel == STANDING_DOD else (TEMPLATES / tpl).read_text(), rel)
    unapplied = [flag for flag, given in (("--gate", gate), ("--starter-rules", starter_rules)) if given]
    put(plane_json, plane_json_new,
        config.CONFIG_REL + (f" ({', '.join(unapplied)} not applied)" if unapplied and keep_plane_json else ""))
    (root / "docs" / "delivery" / "tasks").mkdir(parents=True, exist_ok=True)

    gi = root / ".gitignore"
    lines = gi.read_text().splitlines() if gi.is_file() else []
    if not {f"{WORKTREES_DIR}/", WORKTREES_DIR, f"/{WORKTREES_DIR}/", f"/{WORKTREES_DIR}"} & {x.strip() for x in lines}:
        text = gi.read_text() if gi.is_file() else ""
        gi.write_text(text + ("" if not text or text.endswith("\n") else "\n") + f"{WORKTREES_DIR}/\n")
        out["merged"].append(".gitignore")

    if settings_changed:
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(merged_settings, indent=2) + "\n")
        out["merged"].append(".claude/settings.json")

    cm = root / "CLAUDE.md"
    text = cm.read_text() if cm.is_file() else ""
    if CLAUDE_LINE not in (x.strip() for x in text.splitlines()):
        cm.write_text(text + _paragraph_break(text) + CLAUDE_LINE + "\n")
        out["merged"].append("CLAUDE.md")

    put(binding, binding_text(pid, product_root, q, branch or "main"), "binding")
    q.mkdir(parents=True, exist_ok=True)

    warning = github_warning(product_root)
    if warning:
        out["warnings"] = [warning]
    if keep_binding and old is not None:
        out.setdefault("warnings", []).extend(binding_shape_warnings(binding.resolve(), old))
    if not out.get("warnings"):
        out.pop("warnings", None)

    leftovers = len(script_drift(q)) + len(queue_leftovers(q))
    if leftovers:  # §31.3: a queue an earlier plane generation used; init moves nothing
        out.setdefault("warnings", []).append(
            f"{leftovers} entr{'y' if leftovers == 1 else 'ies'} in the queue {q} the plane does not write "
            "(an earlier plane generation's?): see them with `ccp plane check`, move them to its `_legacy/` "
            "with `ccp plane check --archive`")

    cfg = config.load(root)
    record_adoption(q, cfg, "binding" in out["written"], binding)
    old_files = [f for f in sorted(cfg.tasks_dir.glob("*.md")) if not tasklog.has_frontmatter(f.read_text())]
    if old_files:  # §5.3: an earlier plane generation's task log
        out.setdefault("warnings", []).append(
            f"{len(old_files)} task file(s) in {cfg.rel(cfg.tasks_dir)} have no frontmatter (an earlier plane "
            "generation's?): convert them with `ccp tasks migrate`")
    index = f"{cfg.task_log['dir']}/INDEX.yaml"
    if cfg.task_log.get("index", True) and (force or not (root / index).exists()):
        tasklog.write_index(cfg)
        out["written"].append(index)
    elif cfg.task_log.get("index", True):  # kept: a rewrite could drop what an earlier generation's files need
        out["kept"].append(index)
    return out


def record_adoption(q: Path, cfg: config.Config, written: bool, binding: Path | None = None) -> dict[str, Any] | None:
    """§4.5: the `plane`/`adopted` ledger event, recorded when init wrote the binding or when the queue's
    ledger holds none yet (a queue from before the event, re-adopted); else nothing, so a rerun does not
    move the adoption forward. Its payload: `plane`, the plane checkout's HEAD; `binding`, `written` or
    `kept`; for a kept one, `since`, the binding file's last change in UTC, the adoption point `ccp health`
    reads in place of the event's time (the binding is rewritten only by `--force`, which records its own)."""
    from ccp import health  # noqa: PLC0415  (health is heavy; only init's adoption reads it)
    if not written and health.adopted_at(q) is not None:
        return None
    head = subprocess.run(["git", "-C", str(PLANE), "rev-parse", "HEAD"], capture_output=True, text=True)
    payload = {"plane": head.stdout.strip() if head.returncode == 0 else "",
               "binding": "written" if written else "kept"}
    if not written and binding is not None and binding.is_file():
        changed = datetime.fromtimestamp(binding.stat().st_mtime, timezone.utc)
        payload["since"] = changed.strftime("%Y-%m-%dT%H:%M:%SZ")
    return emit(q, cfg, "", "plane", "adopted", payload, who="operator")


def _rule(cmd: str) -> str:
    return f"Bash({cmd}:*)"


def _deny_rule(cmd: str) -> str:
    """A `DENY` entry as a rule: a wildcard one as it stands, a prefix as `_rule` writes it."""
    return f"Bash({cmd})" if "*" in cmd else _rule(cmd)


def permissions(cfg: config.Config, queue_root: str) -> dict[str, Any]:
    """§4.5, §18.5: the runner's and workers' permission block. Allowed: `ccp` by name (§4.3) and
    the plane's seat scripts by absolute path, each also behind the binding's `QUEUE_ROOT=` as the seats run them; git
    by verb; `gh pr`; the gate lane's commands (its argv, or each stage's command). Denied: `DENY`."""
    q = shlex.quote(queue_root)
    allow: list[str] = []
    for cmd in ("ccp", *(shlex.quote(str(PLANE / s)) for s in SEAT_SCRIPTS)):
        allow += [_rule(cmd), _rule(f"QUEUE_ROOT={q} {cmd}")]
    allow += [_rule(f"git {verb}") for verb in GIT_VERBS]
    allow.append(_rule("gh pr"))
    gate = ((cfg.suite or {}).get("lanes") or {}).get("gate")
    stages = config.lane_stages(gate)
    if stages is not None:
        allow += [_rule(st["cmd"]) for st in stages]
    elif gate:
        allow.append(_rule(shlex.join(gate)))
    return {"permissions": {"allow": allow, "deny": [_deny_rule(cmd) for cmd in DENY]}}


def print_permissions(root: Path, a: Any) -> int:
    """`ccp init --permissions`: print the block for an adopted product; refuse (exit 2) a writing flag,
    a product without a loading plane.json, or one without its binding and queue."""
    given = [flag for flag, attr in WRITING_FLAGS if getattr(a, attr, None)]
    if given:
        print(f"ccp init: --permissions writes nothing; drop {', '.join(given)}", file=sys.stderr)
        return 2
    try:
        cfg = config.load(root)
    except config.ConfigError as e:
        print(f"ccp init: {e}; adopt the product with `ccp init` first", file=sys.stderr)
        return 2
    from ccp.cli import product_queue_root  # noqa: PLC0415  (cli imports this module lazily)
    q = product_queue_root(cfg)
    if not q:
        print(f"ccp init: no binding with a queue for {cfg.project_id!r} names this product; "
              "adopt it with `ccp init` first", file=sys.stderr)
        return 2
    print(json.dumps(permissions(cfg, q), indent=2))
    return 0


RULE_ITEM_RE = re.compile(r"^(\s*)([-*]\s+)")


def _rule_ends(text: str, ids: refs.Ids) -> dict[str, tuple[int, str]]:
    """{rule id: (the index of its item's last non-blank line, the indent a line inside it takes)}. A rule's
    item runs from its opening line until a line indented no deeper than its marker, a heading, or the
    next rule's opening line at any indent. A fenced block opened inside the item belongs to it whole, and
    a line in a fenced block opens no rule (as `rules.rule_blocks` reads the doc)."""
    lines = text.splitlines()
    rx = rules.rule_re(ids)
    openers = {n - 1 for n, line in docrules.unfenced(text) if rx.match(line)}
    out: dict[str, tuple[int, str]] = {}
    for i in sorted(openers):
        m = rx.match(lines[i])
        assert m is not None
        if m.group(1) in out:
            continue
        marker = RULE_ITEM_RE.match(lines[i])
        assert marker is not None
        indent = len(marker.group(1))
        last, fence = i, None
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            f = docrules.FENCE_RE.match(nxt)
            if fence is not None:  # inside a fence the item opened: its content, whatever it holds
                last = j
                if f and f.group(1) == fence:
                    fence = None
                continue
            if not nxt.strip():
                continue
            if nxt.lstrip().startswith("#") or len(nxt) - len(nxt.lstrip()) <= indent or rx.match(nxt):
                break
            last = j
            if f:
                fence = f.group(1)
        out[m.group(1)] = (last, " " * (indent + len(marker.group(2))))
    return out


def _with_checks(text: str, after: dict[int, str]) -> str:
    """`text` with each `after[i]` as a line of its own after line i, ending as the line it follows does
    (or as the doc's first line does, after a last line with no ending), so a CRLF doc stays CRLF."""
    lines = text.splitlines(keepends=True)
    nl = (lines[0][len(lines[0].splitlines()[0]):] if lines else "") or "\n"
    out: list[str] = []
    for i, line in enumerate(lines):
        if i not in after:
            out.append(line)
            continue
        end = line[len(line.splitlines()[0]):]
        out.append(line + after[i] + end if end else line + nl + after[i])
    return "".join(out)


def rules_doc(root: Path, path: str, adopt: bool) -> dict[str, Any]:
    """§4.5, §20.1 `ccp init --rules-doc PATH [--adopt]`: each rule of the doc at PATH (relative to the
    product root) with no `check:` line, and with `adopt` that doc rewritten with a `check: pass` line
    closing each such rule's own item, its line endings kept. The rule ids and `rules_max_lines` are the
    product's when its plane.json loads. Raises QueueError: exit 2 when the doc is missing, exit 1
    (nothing written) when the added lines would put it over `rules_max_lines`, or when the doc, read
    again with them, would not have each adopted rule checked and every other rule as it was. A code fence the
    doc never closes hides the rules after it: the result's `warnings` names it, and so does a refusal."""
    doc = Path(path) if Path(path).is_absolute() else root / path
    if not doc.is_file():
        raise QueueError(f"ccp init: --rules-doc {path}: no such file under {root}", 2)
    try:
        cfg: config.Config | None = config.load(root)
    except config.ConfigError:
        cfg = None
    ids = refs.ids(cfg)
    cap = int(((cfg.architect if cfg else None) or config.ARCHITECT_DEFAULTS)["rules_max_lines"])
    try:
        rel = str(doc.resolve().relative_to(root.resolve()))
    except ValueError:
        rel = str(doc)
    with open(doc, newline="") as fh:  # as written: a CRLF doc keeps its line endings
        text = fh.read()
    kinds, _ = rules.parse_rules(text, ids)
    unchecked = [rid for rid, kind in kinds.items() if kind is None]
    lines = len(text.splitlines())
    fence = rules.fence_warning(rel, text)  # §20.1: rules after a fence left open are not read at all
    out: dict[str, Any] = {"rules_doc": rel, "rules": len(kinds), "unchecked": unchecked, "lines": lines,
                           "rules_max_lines": cap, "adopted": [], "warnings": [fence] if fence else []}
    also = f" ({fence})" if fence else ""
    if adopt and unchecked:
        if lines + len(unchecked) > cap:
            raise QueueError(f"ccp init: {rel} has {lines} lines; a `check: pass` line for each of its "
                             f"{len(unchecked)} unchecked rules would make {lines + len(unchecked)}, over "
                             f"rules_max_lines {cap}: shorten it first. Nothing written{also}", 1)
        ends = _rule_ends(text, ids)
        new = _with_checks(text, {ends[rid][0]: ends[rid][1] + "check: pass" for rid in unchecked})
        # Re-read as docs check reads it: each adopted rule now checked and no other changed, so a rerun
        # finds nothing to add.
        now, _ = rules.parse_rules(new, ids)
        wrong = [rid for rid in kinds if now.get(rid) != ("pass" if rid in unchecked else kinds[rid])]
        if wrong:
            raise QueueError(f"ccp init: {rel}: with a `check: pass` line closing each unchecked rule's item, "
                             f"{', '.join(wrong)} would not read as intended (is a fenced block left open?): "
                             f"add the lines by hand. Nothing written{also}", 1)
        with open(doc, "w", newline="") as fh:
            fh.write(new)
        out.update(adopted=unchecked, lines=len(new.splitlines()))
    out["starter_rules"] = (f"the plane's starter rules (SPEC §20.5), {rules.STARTER_DOC}: a rule the plane "
                            "already checks can take its `docs` check there; adopt the set with "
                            "docs.starter_rules in plane.json")
    if not cfg or not cfg.architect or cfg.architect.get("rules_doc") != rel:
        out["note"] = (f"set architect.rules_doc to {rel} in plane.json: until then ccp docs check does not "
                       "check it and no architect judges its `check: pass` rules")
    return out


def print_rules_doc(root: Path, a: Any) -> int:
    """`ccp init --rules-doc PATH [--adopt]`: print the report; refuse (exit 2) another init flag."""
    given = [flag for flag, attr in (*WRITING_FLAGS, ("--permissions", "permissions")) if getattr(a, attr, None)]
    if given:
        print(f"ccp init: --rules-doc writes only the rules doc; drop {', '.join(given)}", file=sys.stderr)
        return 2
    try:
        res = rules_doc(root, a.rules_doc, bool(getattr(a, "adopt", False)))
    except QueueError as e:
        print(str(e), file=sys.stderr)
        return e.code
    for w in res["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    print(json.dumps(res, indent=2))
    return 0


def main(root_arg: str | None, a: Any) -> int:
    try:
        root = config.find_root(root_arg)
    except config.ConfigError as e:
        print(f"ccp init: {e}", file=sys.stderr)
        return 2
    if getattr(a, "adopt", False) and not getattr(a, "rules_doc", None):
        print("ccp init: --adopt goes with --rules-doc PATH", file=sys.stderr)
        return 2
    if getattr(a, "rules_doc", None):
        return print_rules_doc(root, a)
    if getattr(a, "permissions", False):
        return print_permissions(root, a)
    try:
        res = init(root, a.project_id, a.queue_root, a.integration_branch, a.gate, a.force, a.starter_rules)
    except QueueError as e:
        print(str(e), file=sys.stderr)
        return e.code
    for w in res.get("warnings", []):
        print(f"ccp init: warning: {w}", file=sys.stderr)
    print(json.dumps(res))
    return 0
