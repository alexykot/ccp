"""`ccp init`: adopt a product with one command (SPEC §4.3, §4.5, §8.3).

Run in a product's repository, it writes the product footprint (the PROJECT, SPEC and delivery
templates, a minimal `plane.json`, `.plane-runtime/` in `.gitignore`, the plugin anchor merged into
`.claude/settings.json`, the one `CLAUDE.md` line) and, outside the repository, the binding in this
plane's bindings directory and the queue directory it names. The binding is the one source of
truth: every reader resolves it through `lib.binding_path`, and no copy goes into the queue (§8.3).

It never overwrites a file without `--force`: an existing file is kept and listed as kept, so a
second run, or a run after the binding was edited, changes nothing. It refuses, writing nothing, when
keeping a file would leave the product inconsistent: a `plane.json` naming another project id, a
binding for the id that names another product root, or a settings file that is not a JSON object.
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from ccp import config, tasklog
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


def _default_id(root: Path) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", root.name.lower())).strip("-")


def _scalar(text: str, key: str) -> str | None:
    m = re.search(rf"^{key}:\s*([^#\n]+)", text, re.M)
    return m.group(1).strip().strip("'\"") if m else None


def binding_text(project_id: str, product_root: Path, queue_root: Path, branch: str) -> str:
    """The binding init writes (§8.3): the required keys, the product root and the runner block."""
    return (f"project_id: {project_id}\n"
            f"integration_branch: {branch}\n"
            f"product_root: {product_root}\n"
            "durable_docs_path: docs/delivery/\n"
            f"queue_root: {queue_root}\n"
            "runner:\n"
            "  agent_type: ccp:delivery-runner\n"
            "  name: runner\n"
            f"  worktree: {product_root / WORKTREES_DIR / 'runner'}\n")


def plane_json_text(project_id: str, gate: str | None) -> str:
    """A minimal plane.json (§8.1): the id, the worktrees directory, and the gate lane when given."""
    cfg: dict[str, Any] = {"project_id": project_id, "worktrees": {"dir": WORKTREES_DIR}}
    if gate:
        cfg["suite"] = {"lanes": {"gate": shlex.split(gate)}}
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
         gate: str | None, force: bool) -> dict[str, Any]:
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

    for rel, tpl in COPIES.items():
        put(root / rel, (TEMPLATES / tpl).read_text(), rel)
    put(plane_json, plane_json_text(pid, gate), config.CONFIG_REL)
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
        cm.write_text(text + ("" if not text or text.endswith("\n") else "\n") + CLAUDE_LINE + "\n")
        out["merged"].append("CLAUDE.md")

    put(binding, binding_text(pid, product_root, q, branch or "main"), "binding")
    q.mkdir(parents=True, exist_ok=True)

    cfg = config.load(root)
    if cfg.task_log.get("index", True) and (force or not (root / cfg.task_log["dir"] / "INDEX.yaml").exists()):
        tasklog.write_index(cfg)
        out["written"].append(f"{cfg.task_log['dir']}/INDEX.yaml")
    return out


def main(root_arg: str | None, a: Any) -> int:
    try:
        root = config.find_root(root_arg)
    except config.ConfigError as e:
        print(f"ccp init: {e}", file=sys.stderr)
        return 2
    try:
        res = init(root, a.project_id, a.queue_root, a.integration_branch, a.gate, a.force)
    except QueueError as e:
        print(str(e), file=sys.stderr)
        return e.code
    print(json.dumps(res))
    return 0
