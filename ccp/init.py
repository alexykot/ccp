"""`ccp init`: adopt a product with one command (SPEC §4.3, §4.5, §8.3).

Run in a product's repository, it writes the product footprint (the PROJECT, SPEC and delivery
templates, with `--starter-rules` the plane's starter house rules (§20.5), a minimal `plane.json`, `.plane-runtime/` in `.gitignore`, the plugin anchor merged into
`.claude/settings.json`, the one `CLAUDE.md` line) and, outside the repository, the binding in this
plane's bindings directory and the queue directory it names. The binding is the one source of
truth: every reader resolves it through `lib.binding_path`, and no copy goes into the queue (§8.3).

It never overwrites a file without `--force`: an existing file is kept and listed as kept, so a
second run, or a run after the binding was edited, changes nothing. It refuses, writing nothing, when
keeping a file would leave the product inconsistent: a `plane.json` naming another project id or
not loading, a binding for the id that names another product root, or a settings file that is not a
JSON object. It also refuses, writing nothing, a `--gate` it cannot split and a product root or
queue path holding `#`, which every binding reader cuts off as a comment.

Pull requests need a GitHub origin until the PR host is an adapter (ADR-0040 D7): when the product
has no `origin`, or its host is not GitHub, init warns on stderr and in the result's `warnings`,
naming the commands that need one, and adopts the product all the same.

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
from urllib.parse import urlsplit
from pathlib import Path
from typing import Any

from ccp import config, refs, rules, tasklog
from ccp.queue import PLANE, QueueError, _main_worktree, lib

TEMPLATES = PLANE / "templates"
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
# §4.5, §18.5: what `--permissions` allows besides `ccp`, the plane's seat scripts and the gate lane:
# the git verbs the runner and its workers run, and the destructive commands it denies.
SEAT_SCRIPTS = ("scripts/team.sh", "scripts/spec-maintainer-ask.sh")
GIT_VERBS = ("add", "branch", "commit", "diff", "fetch", "log", "ls-files", "merge", "merge-base", "push",
             "rev-parse", "show", "status", "worktree")
DENY = ("git push --force", "git push --force-with-lease", "git push -f", "git reset --hard", "git clean",
        "git branch -D", "git stash", "git checkout --", "git restore", "rm -rf", "gh repo delete")
# ADR-0040 D7: what needs a GitHub origin and a logged-in `gh` until the PR host is an adapter.
GITHUB_ONLY = ("ccp verify merge-ok", "ccp tasks close (its default merge and its merge confirmation)",
               "the workers' `gh pr` steps (the implementer's PR, review and verify)")
# The init flags that write: `--permissions` writes nothing, so it refuses them.
WRITING_FLAGS = (("--project-id", "project_id"), ("--queue-root", "queue_root"),
                 ("--integration-branch", "integration_branch"), ("--gate", "gate"),
                 ("--starter-rules", "starter_rules"), ("--force", "force"))


def _default_id(root: Path) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", root.name.lower())).strip("-")


def _scalar(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*([^#\n]+)", text, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def _paragraph_break(text: str) -> str:
    """What goes between `text` and an appended line so the line is its own paragraph: nothing after
    an empty file or one already ending in a blank line, else the line break(s) up to one blank line."""
    lines = text.splitlines()
    if not text.strip() or not lines[-1].strip():
        return "" if not text or text.endswith("\n") else "\n"
    return "\n" if text.endswith("\n") else "\n\n"


def origin_host(root: Path) -> str | None:
    """The host of the product's `origin` URL (lowercased), "" for a local path or a URL with none,
    None when there is no origin. Only the host is kept: a URL may carry credentials."""
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    url = r.stdout.strip()
    if r.returncode != 0 or not url:
        return None
    if "://" in url:
        return (urlsplit(url).hostname or "").lower()
    scp = re.match(r"^(?:[^@/:]+@)?([^/:]+):", url)  # git's scp-like form: a colon before any slash
    return scp.group(1).lower() if scp and len(scp.group(1)) > 1 else ""


def is_github(host: str | None) -> bool:
    return host is not None and (host == "github.com" or host.endswith(".github.com"))


def github_warning(root: Path) -> str | None:
    """ADR-0040 D7: the warning init gives when the product's origin is missing or not on GitHub."""
    host = origin_host(root)
    if is_github(host):
        return None
    where = "has no origin" if host is None else (f"has its origin on {host}" if host else "has a local origin")
    return (f"pull requests need a GitHub origin and a logged-in `gh`, and this product {where}: "
            f"{'; '.join(GITHUB_ONLY)} will fail until it has one (ADR-0040)")


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
    starter rules' settings with `--starter-rules` (§20.5)."""
    cfg: dict[str, Any] = {"project_id": project_id, "worktrees": {"dir": WORKTREES_DIR}}
    if gate:
        cfg["suite"] = {"lanes": {"gate": shlex.split(gate)}}
    if starter_rules:
        cfg.update(json.loads(json.dumps(STARTER_CONFIG)))
    return json.dumps(cfg, indent=2) + "\n"


def _merged_settings(path: Path) -> tuple[dict[str, Any], bool]:
    """The settings with the anchor merged in; True when that changed them. Other keys, and any value
    the product already set for these, stay as they are."""
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
    return data, json.dumps(data, sort_keys=True) != before


def init(root: Path, project_id: str | None, queue_root: str | None, branch: str | None,
         gate: str | None, force: bool, starter_rules: bool = False) -> dict[str, Any]:
    """Adopt the product at `root`; returns what was written, merged and kept. Raises QueueError
    (nothing written) on a refusal."""
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

    binding = lib.bindings_dir() / f"{pid}.yaml"
    old = binding.read_text() if binding.is_file() else None
    if old is not None and not force:
        bound = _scalar(old, "product_root")
        if not bound or Path(bound).expanduser().resolve() != product_root:
            raise QueueError(f"ccp init: the binding {binding} names another product root ({bound}); "
                             "pick another --project-id, or --force to rewrite it", 2)
    keep_binding = old is not None and not force
    q = Path(queue_root).expanduser() if queue_root else None
    if keep_binding:
        bound_q = _scalar(old, "queue_root")
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
    merged_settings, settings_changed = _merged_settings(settings)  # refuses before anything is written

    out: dict[str, Any] = {"project_id": pid, "product_root": str(product_root), "binding": str(binding),
                           "queue_root": str(q), "written": [], "merged": [], "kept": []}

    def put(path: Path, text: str, label: str) -> None:
        if path.exists() and not force:
            out["kept"].append(label)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        out["written"].append(label)

    copies = {**COPIES, **(dict([STARTER_RULES_DOC]) if starter_rules else {})}
    for rel, tpl in copies.items():
        put(root / rel, (TEMPLATES / tpl).read_text(), rel)
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

    cfg = config.load(root)
    if cfg.task_log.get("index", True) and (force or not (root / cfg.task_log["dir"] / "INDEX.yaml").exists()):
        tasklog.write_index(cfg)
        out["written"].append(f"{cfg.task_log['dir']}/INDEX.yaml")
    return out


def _rule(cmd: str) -> str:
    return f"Bash({cmd}:*)"


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
    return {"permissions": {"allow": allow, "deny": [_rule(cmd) for cmd in DENY]}}


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
    from ccp.cli import binding_queue_root  # noqa: PLC0415  (cli imports this module lazily)
    q = binding_queue_root(cfg)
    if not q:
        print(f"ccp init: no binding with a queue for {cfg.project_id!r} names this product; "
              "adopt it with `ccp init` first", file=sys.stderr)
        return 2
    print(json.dumps(permissions(cfg, q), indent=2))
    return 0


RULE_ITEM_RE = re.compile(r"^(\s*)([-*]\s+)")


def _rule_ends(text: str, ids: refs.Ids) -> dict[str, tuple[int, str]]:
    """{rule id: (the index of its item's last non-blank line, the indent a line inside it takes)}. A rule's
    item runs from its opening line until a line indented no deeper than its marker, or a heading."""
    lines = text.splitlines()
    rx = rules.rule_re(ids)
    out: dict[str, tuple[int, str]] = {}
    for i, line in enumerate(lines):
        m = rx.match(line)
        if not m or m.group(1) in out:
            continue
        marker = RULE_ITEM_RE.match(line)
        assert marker is not None
        indent = len(marker.group(1))
        last = i
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if not nxt.strip():
                continue
            if nxt.lstrip().startswith("#") or len(nxt) - len(nxt.lstrip()) <= indent:
                break
            last = j
        out[m.group(1)] = (last, " " * (indent + len(marker.group(2))))
    return out


def rules_doc(root: Path, path: str, adopt: bool) -> dict[str, Any]:
    """§4.5, §20.1 `ccp init --rules-doc PATH [--adopt]`: each rule of the doc at PATH (relative to the
    product root) with no `check:` line, and with `adopt` that doc rewritten with a `check: pass` line
    closing each such rule. The rule ids and `rules_max_lines` are the product's when its plane.json
    loads. Raises QueueError: exit 2 when the doc is missing, exit 1 (nothing written) when the added
    lines would put it over `rules_max_lines`."""
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
    text = doc.read_text()
    kinds, _ = rules.parse_rules(text, ids)
    unchecked = [rid for rid, kind in kinds.items() if kind is None]
    lines = len(text.splitlines())
    out: dict[str, Any] = {"rules_doc": rel, "rules": len(kinds), "unchecked": unchecked, "lines": lines,
                           "rules_max_lines": cap, "adopted": []}
    if adopt and unchecked:
        if lines + len(unchecked) > cap:
            raise QueueError(f"ccp init: {rel} has {lines} lines; a `check: pass` line for each of its "
                             f"{len(unchecked)} unchecked rules would make {lines + len(unchecked)}, over "
                             f"rules_max_lines {cap}: shorten it first. Nothing written", 1)
        ends = _rule_ends(text, ids)
        after = {ends[rid][0]: ends[rid][1] + "check: pass" for rid in unchecked}
        new: list[str] = []
        for i, line in enumerate(text.splitlines()):
            new.append(line)
            if i in after:
                new.append(after[i])
        doc.write_text("\n".join(new) + ("\n" if text.endswith("\n") or not text else ""))
        out.update(adopted=unchecked, lines=len(new))
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
