#!/usr/bin/env bash
# sync-product-docs.sh — SPEC §9.5: check a product repo for the managed copies the plane no longer installs.
#
# Usage:
#   scripts/sync-product-docs.sh <project_id> --check [--product-root DIR] [--project-yaml FILE]
#
# The one form is --check; a call without it, or with any other option, exits 2 with the usage line.
# Every product is read as one on the plugin (SPEC §9.5): the plugin ships the orientation, the protocols, the
# architect skill, the agents and the hooks, so no product holds a managed copy of them. The script reads the
# product and writes nothing to it.
#
# Paths it looks for in product_root (each once a managed copy, SPEC §9.5):
#   docs/delivery/CONTROL-PLANE.md, docs/delivery/SPEC-MAINTAINER.md, docs/delivery/REVIEW-TRIAGE.md
#   .claude/skills/architect/SKILL.md, and the two skills it replaced (architecture-review, docs-audit)
#   .claude/agents/delivery-{runner,implementer,reviewer,verifier}.md
#   .claude/hooks/runner-idle.sh, .claude/hooks/run-binding.sh
# A path that carries the managed-copy header (a line naming the plane template it was copied from) is reported
# `DRIFT <path>: retired`; one without the header is the product's own, a `left alone` note; a missing one is
# nothing. Also reported as drift: the CLAUDE.md import line @docs/delivery/CONTROL-PLANE.md (SPEC §4.3) and
# the settings hook entries that call .claude/hooks/ copies (SPEC §9.1).
# Notes (printed, never drift): a plane.json `architect.rules_doc` that does not exist yet (copy
#   templates/docs-project/ENGINEERING.md; it is product-owned, never a managed copy); the telemetry keys the
#   project settings carry in vain; the old `cpl.project_id` key.
# Exit 0 clean, 1 drift (the last line says to delete the listed copies and commit the product change),
# 2 usage / config error (unknown project, no product_root, product_root missing).
#
# Defaults: --project-yaml = the one resolver's file for the project id (`lib.binding_for_id`: the file PROJECT_YAML
# names when it binds that id, else <the bindings directory>/<project_id>.yaml, CCP_BINDINGS_DIR else
# <plane>/projects); --product-root = its product_root.
# No secrets are read or written.
set -euo pipefail
PLANE="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 - "$PLANE" "$@" <<'PY'
import contextlib, io, json, re, sys
from pathlib import Path

plane = Path(sys.argv[1]); args = sys.argv[2:]
sys.path.insert(0, str(plane))
from ccp import lib  # the one binding parser and resolver (SPEC §8.3)
IMPORT_LINE = "@docs/delivery/CONTROL-PLANE.md"
HEADER_RE = re.compile(r"^(?:>|#) Managed copy of control-plane `((?:templates|plugin)/[^`]+)` at ([0-9a-f]{7,40})(\+dirty)?\. ", re.M)

def usage(code):
    print("usage: sync-product-docs.sh <project_id> --check [--product-root DIR] [--project-yaml FILE]", file=sys.stderr)
    sys.exit(code)

def fail(msg, code=2):
    print(f"sync-product-docs: {msg}", file=sys.stderr); sys.exit(code)

project = None; check = False; product_root = None; project_yaml = None
i = 0
while i < len(args):
    a = args[i]
    if a in ("-h", "--help"): usage(0)
    elif a == "--check": check = True
    elif a in ("--product-root", "--project-yaml"):
        if i + 1 >= len(args): usage(2)
        v = args[i + 1]; i += 1
        if a == "--product-root": product_root = v
        else: project_yaml = v
    elif a.startswith("-"): usage(2)
    elif project is None: project = a
    else: usage(2)
    i += 1
if not project or not check: usage(2)

yml = Path(project_yaml) if project_yaml else lib.binding_for_id(project)
if yml is None: fail(f"no project binding for {project} in {lib.bindings_dir()}")
if not yml.is_file(): fail(f"no project binding {yml}")
binding = lib.read_binding(yml.read_text())
if lib.binding_str(binding, "project_id") and lib.binding_str(binding, "project_id") != project:
    fail(f"{yml} is project_id {lib.binding_str(binding, 'project_id')}, not {project}")
root = Path(product_root or lib.binding_str(binding, "product_root") or "")
if not str(root) or str(root) == ".": fail(f"{yml} has no product_root (pass --product-root)")
if not root.is_dir(): fail(f"product_root {root} does not exist")

notes = []; drift = []
# The paths the plane once copied into a product (SPEC §9.5), and why each is retired.
by_plugin = "the control-plane plugin ships it (SPEC §4)"
replaced = "replaced by the architect skill (SPEC §19)"
retired = [("docs/delivery/CONTROL-PLANE.md", by_plugin), ("docs/delivery/SPEC-MAINTAINER.md", by_plugin),
           ("docs/delivery/REVIEW-TRIAGE.md", by_plugin), (".claude/skills/architect/SKILL.md", by_plugin),
           (".claude/skills/architecture-review/SKILL.md", replaced), (".claude/skills/docs-audit/SKILL.md", replaced)]
retired += [(f".claude/agents/delivery-{a}.md", by_plugin) for a in ("runner", "implementer", "reviewer", "verifier")]
retired += [(f".claude/hooks/{h}.sh", by_plugin) for h in ("runner-idle", "run-binding")]
# SPEC §9.1: hook entries in the product's settings that call .claude/hooks/ copies would run
# beside the plugin's own hooks (runner-idle twice per idle), then fail once the copies are gone.
for sname in ("settings.json", "settings.local.json"):
    try:
        s = json.loads((root / ".claude" / sname).read_text())
    except (OSError, ValueError):
        continue
    stale = sorted({ev for ev, entries in (s.get("hooks") or {}).items()
                    if ".claude/hooks/" in json.dumps(entries)})
    if stale:
        msg = f".claude/{sname}: hook entries for {', '.join(stale)} call .claude/hooks/ copies; remove them, the plugin's hooks replace them (SPEC §9)"
        drift.append({"file": f".claude/{sname}", "kind": "stale_hooks", "detail": msg})
# SPEC §24: Claude Code ignores the six keys that turn telemetry on in a project's settings (2.1.308;
# a project may only turn it off) and warns; the user settings carry them. OTEL_RESOURCE_ATTRIBUTES with
# ccp.project_id is honoured there and is the supported project key. A leftover key is a note, never drift.
try:
    penv = json.loads((root / ".claude" / "settings.json").read_text()).get("env")
except (OSError, ValueError, AttributeError):
    penv = None
tkeys = sorted(k for k in penv if k != "OTEL_RESOURCE_ATTRIBUTES"
               and re.match(r"^(CLAUDE_CODE_ENABLE_TELEMETRY|CLAUDE_CODE_ENHANCED_TELEMETRY_BETA|OTEL_.+)$", str(k))) \
    if isinstance(penv, dict) else []
if tkeys:
    notes.append(f".claude/settings.json: env {', '.join(tkeys)} is ignored by Claude Code in project settings and "
                 "can be removed; the user settings carry the enabling keys, and OTEL_RESOURCE_ATTRIBUTES with "
                 "ccp.project_id is the supported project key (`ccp otel env --project ID`, SPEC §24)")
# ADR-0036 D3: the project key was `cpl.project_id`; the receiver no longer reads it.
if isinstance(penv, dict) and re.search(r"\bcpl\.project_id=", str(penv.get("OTEL_RESOURCE_ATTRIBUTES") or "")):
    notes.append(".claude/settings.json: OTEL_RESOURCE_ATTRIBUTES uses the old key cpl.project_id; rename it to "
                 "ccp.project_id (`ccp otel env --project ID`): the receiver no longer reads the old key")

try:  # the product's configuration as ccp loads it (defaults included); the load's warnings are not printed
    sys.path.insert(0, str(plane))
    from ccp import config as ccp_config
    with contextlib.redirect_stderr(io.StringIO()):
        rules_doc = (ccp_config.load(root).architect or {}).get("rules_doc")
except Exception:  # no plane.json, invalid JSON, a ConfigError: no rules doc
    rules_doc = None
if rules_doc and not (root / rules_doc).is_file():
    notes.append(f"plane.json architect.rules_doc {rules_doc} does not exist: copy "
                 "templates/docs-project/ENGINEERING.md there and make it the product's own (SPEC §20.1)")

for rel, why in retired:
    dest = root / rel
    if not dest.is_file():
        continue
    if not HEADER_RE.search(dest.read_text()[:2000]):
        notes.append(f"{rel}: {why}, but it has no managed-copy header; left alone")
    else:
        drift.append({"file": rel, "kind": "retired", "detail": why})

cm = root / "CLAUDE.md"
if cm.is_file() and any(l.strip() == IMPORT_LINE for l in cm.read_text().splitlines()):
    # The plugin's SessionStart hook gives the orientation; CLAUDE.md is the product's to edit.
    drift.append({"file": "CLAUDE.md", "kind": "import_line", "detail": f"remove {IMPORT_LINE} and its section (SPEC §4.3)"})

print(f"sync-product-docs: {project} check product_root={root}")
for n in notes: print(f"  note: {n}")
for d in drift:
    print(f"  DRIFT {d['file']}: {d['kind']}" + (f" — {d['detail']}" if d.get("detail") else ""))
print("  result: " + ("drift — delete the listed copies and commit the product change" if drift else "clean"))
sys.exit(1 if drift else 0)
PY
