#!/usr/bin/env bash
# sync-product-docs.sh — SPEC §9.5: install / check the plane's managed copies in a product repo.
#
# Usage:
#   scripts/sync-product-docs.sh <project_id> [--check] [--product-root DIR] [--project-yaml FILE]
#                                [--daily-stamp FILE] [--allow-dirty]
#
# Managed copies (in product_root):
#   docs/delivery/CONTROL-PLANE.md   always (role-neutral orientation, template plugin/orientation.md)
#   docs/delivery/SPEC-MAINTAINER.md  only when the binding declares a spec_maintainer block (SPEC §17)
#   docs/delivery/REVIEW-TRIAGE.md    always (the architect's review triage protocol, SPEC §19.8)
#   .claude/skills/architect/SKILL.md  always (the architect skill, SPEC §19; template
#                                      plugin/skills/architect/SKILL.md). It replaces the
#                                      architecture-review and docs-audit skills (§19): a sync removes
#                                      their managed copies (only files carrying the managed-copy header),
#                                      and --check reports them as stale.
#   .claude/agents/delivery-runner.md   SPEC §2: the runner teammate's agent definition
#   .claude/agents/delivery-{implementer,reviewer,verifier}.md  the runner's subagents; each fixes its
#                                       own model and effort, SPEC §2
#   .claude/hooks/runner-idle.sh        SPEC §18.2 TeammateIdle hook; executable; the settings entry
#                                       that calls it is product-local, see the script header
#   .claude/hooks/run-binding.sh        SPEC §11.1 SubagentStart/SubagentStop hooks that bind runs;
#                                       executable; settings entry product-local, see its header
# plus the CLAUDE.md "Control plane" section holding the import line @docs/delivery/CONTROL-PLANE.md.
#
# Each copy = one managed-copy header line naming the template and the plane commit that last
# changed it, then the template body (a leading <!-- ... --> template note is dropped). A skill keeps
# its YAML frontmatter first (Claude Code reads it); the header line goes right after it.
#
# Without --check: writes the copies (only if different) and appends the CLAUDE.md section if the
#   import line is missing (creates CLAUDE.md if absent; never rewrites existing content). Never
#   commits: the seat or the operator commits the product change. Refuses if a template has uncommitted
#   changes (the stamp would lie) unless --allow-dirty.
# With --check: no writes to the product. Prints what drifted; exit 0 clean, 1 drift.
#   --daily-stamp FILE (Watchdog, runtime file e.g. $QUEUE_ROOT/product-docs-check.json): skip with
#   exit 0 if FILE already records a check today (UTC, or the zone in CCP_TIMEZONE); otherwise check and record the
#   result there. Drift is a low-priority note, not an alarm.
# Notes (printed, never drift): a plane.json `architect.rules_doc` that does not exist yet (copy
#   templates/docs-project/ENGINEERING.md; it is product-owned, never a managed copy).
# Exit 2: usage / config error (unknown project, no product_root, product_root missing).
#
# Defaults: --project-yaml = <plane>/projects/<project_id>.yaml; --product-root = its product_root.
# No secrets are read or written.
set -euo pipefail
PLANE="$(cd "$(dirname "$0")/.." && pwd)"
exec python3 - "$PLANE" "$@" <<'PY'
import difflib, json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

plane = Path(sys.argv[1]); args = sys.argv[2:]
IMPORT_LINE = "@docs/delivery/CONTROL-PLANE.md"
SECTION = ("## Control plane\n\n" + IMPORT_LINE + "\n\n"
           "That file is the control plane's orientation for this repo: how work flows, which seats "
           "exist, and which role, if any, you have.\n")
HEADER_RE = re.compile(r"^(?:>|#) Managed copy of control-plane `((?:templates|plugin)/[^`]+)` at ([0-9a-f]{7,40})(\+dirty)?\. ", re.M)

def usage(code):
    print("usage: sync-product-docs.sh <project_id> [--check] [--product-root DIR] [--project-yaml FILE] "
          "[--daily-stamp FILE] [--allow-dirty]", file=sys.stderr)
    sys.exit(code)

def fail(msg, code=2):
    print(f"sync-product-docs: {msg}", file=sys.stderr); sys.exit(code)

project = None; check = False; product_root = None; project_yaml = None; stamp = None; allow_dirty = False
i = 0
while i < len(args):
    a = args[i]
    if a in ("-h", "--help"): usage(0)
    elif a == "--check": check = True
    elif a == "--allow-dirty": allow_dirty = True
    elif a in ("--product-root", "--project-yaml", "--daily-stamp"):
        if i + 1 >= len(args): usage(2)
        v = args[i + 1]; i += 1
        if a == "--product-root": product_root = v
        elif a == "--project-yaml": project_yaml = v
        else: stamp = v
    elif a.startswith("-"): usage(2)
    elif project is None: project = a
    else: usage(2)
    i += 1
if not project: usage(2)
if stamp and not check: fail("--daily-stamp needs --check")

def today_local():
    """Today's date in UTC, or in the IANA zone named by CCP_TIMEZONE."""
    zone = os.environ.get("CCP_TIMEZONE") or "UTC"
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(zone)).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()

if stamp:
    try:
        prev = json.loads(Path(stamp).read_text())
    except (OSError, ValueError):
        prev = {}
    if prev.get("project_id") == project and prev.get("date_local") == today_local():
        print(f"sync-product-docs: {project} check skipped: already checked today "
              f"({prev.get('checked_at')}, drift={prev.get('drift')}); daily cadence (SPEC §9.5)")
        sys.exit(0)

yml = Path(project_yaml) if project_yaml else plane / "projects" / f"{project}.yaml"
if not yml.is_file(): fail(f"no project binding {yml}")
text = yml.read_text()
def top(key):
    m = re.search(rf"^{key}:\s*(\S+)", text, re.M)
    return m.group(1).strip("'\"") if m else None
if top("project_id") and top("project_id") != project:
    fail(f"{yml} is project_id {top('project_id')}, not {project}")
root = Path(product_root or top("product_root") or "")
if not str(root) or str(root) == ".": fail(f"{yml} has no product_root (pass --product-root)")
if not root.is_dir(): fail(f"product_root {root} does not exist")

sm = re.search(r"^spec_maintainer:\s*\n((?:[ \t]+.*\n?|[ \t]*#.*\n?|\s*\n)*)", text, re.M)
managed = [("plugin/orientation.md", "docs/delivery/CONTROL-PLANE.md")]
if sm:
    managed.append(("plugin/skills/spec-maintainer/SKILL.md", "docs/delivery/SPEC-MAINTAINER.md"))
managed += [("plugin/skills/review-triage/SKILL.md", "docs/delivery/REVIEW-TRIAGE.md"),
            ("plugin/skills/architect/SKILL.md", ".claude/skills/architect/SKILL.md")]
# Managed copies the plane no longer ships (§19): removed by a sync, reported by --check.
retired = [".claude/skills/architecture-review/SKILL.md", ".claude/skills/docs-audit/SKILL.md"]
managed += [(f"plugin/agents/delivery-{a}.md", f".claude/agents/delivery-{a}.md")
            for a in ("runner", "implementer", "reviewer", "verifier")]
managed.append(("plugin/hooks/runner-idle.sh", ".claude/hooks/runner-idle.sh"))
managed.append(("plugin/hooks/run-binding.sh", ".claude/hooks/run-binding.sh"))
notes = []
# SPEC §4: a product whose settings enable the control-plane plugin gets these from the plugin.
# Nothing is installed; a managed copy left in the product is stale (a sync removes it, --check reports it).
def plugin_enabled():
    try:
        s = json.loads((root / ".claude" / "settings.json").read_text())
    except (OSError, ValueError):
        return False
    return any(k.startswith("ccp@") and v for k, v in (s.get("enabledPlugins") or {}).items())
plugin = plugin_enabled()
if plugin:
    retired = retired + [dest for _, dest in managed]
    managed = []
hook_drift = []
if plugin:
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
            (hook_drift.append({"file": f".claude/{sname}", "kind": "stale_hooks", "detail": msg}) if check else notes.append(msg))
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
if sm and not plugin:
    pd = re.search(r"^\s+protocol_doc:\s*(\S+)", sm.group(1), re.M)
    kind = re.search(r"^\s+kind:\s*(\S+)", sm.group(1), re.M)
    if kind and kind.group(1) == "claude-session":
        notes.append(f"binding {yml}: spec_maintainer.kind claude-session was removed (SPEC §17, 2026-11-05); "
                     "the team lead answers spec questions: drop the block or set kind team-lead")

try:
    rules_doc = (json.loads((root / "docs/delivery/plane.json").read_text()).get("architect") or {}).get("rules_doc")
except (OSError, ValueError, AttributeError):
    rules_doc = None
if rules_doc and not (root / rules_doc).is_file():
    notes.append(f"plane.json architect.rules_doc {rules_doc} does not exist: copy "
                 "templates/docs-project/ENGINEERING.md there and make it the product's own (SPEC §20.1)")

def git(*a):
    r = subprocess.run(["git", "-C", str(plane), *a], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""

def expected(rel, dest_rel=""):
    src = plane / rel
    if not src.is_file(): fail(f"missing template {src}")
    sha = git("log", "-1", "--format=%h", "--abbrev=7", "--", rel)
    if not sha: fail(f"template {rel} is not committed in the plane repo")
    dirty = bool(git("status", "--porcelain", "--", rel))
    body = src.read_text()
    if body.startswith("---\n") and dest_rel.startswith("docs/"):
        # A plugin skill copied as a product doc: the skill's frontmatter is not the doc's.
        end = body.find("\n---\n", 4)
        if end != -1:
            body = body[end + 5:].lstrip("\n")
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        after = body[end + 5:].lstrip("\n") if end != -1 else ""
        if after.startswith("<!--") and after.find("-->") != -1:
            body = body[:end + 5] + after[after.find("-->") + 3:]
    if body.startswith("<!--"):
        end = body.find("-->")
        if end != -1:
            body = body[end + 3:]
    body = body.lstrip("\n")
    header = (f"> Managed copy of control-plane `{rel}` at {sha}{'+dirty' if dirty else ''}. "
              "Edit the template, then re-sync; local edits are overwritten.\n\n")
    if rel.endswith(".sh"):
        # A script keeps its shebang first; the header is a shell comment right after it.
        first, _, rest = body.partition("\n")
        return first + "\n# " + header[2:].rstrip("\n") + "\n" + rest, sha, dirty
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end != -1:
            front, rest = body[:end + 5], body[end + 5:].lstrip("\n")
            return front + "\n" + header + rest, sha, dirty
    return header + body, sha, dirty

drift, wrote, ok = list(hook_drift), [], []
for tmpl, dest_rel in managed:
    name = Path(dest_rel).name
    want, sha, dirty = expected(tmpl, dest_rel)
    dest = root / dest_rel
    rel = dest.relative_to(root)
    if check:
        if not dest.is_file():
            drift.append({"file": str(rel), "kind": "missing"}); continue
        have = dest.read_text()
        if have == want:
            ok.append(str(rel)); continue
        hm = HEADER_RE.search(have)
        item = {"file": str(rel), "kind": "content"}
        if not hm: item["kind"] = "no_header"
        elif hm.group(2) != sha or bool(hm.group(3)) != dirty:
            item["header"] = f"copy stamped {hm.group(2)}{hm.group(3) or ''}, template at {sha}{'+dirty' if dirty else ''}"
        diff = list(difflib.unified_diff(have.splitlines(), want.splitlines(), f"product/{rel}", tmpl, lineterm="", n=1))
        item["diff"] = diff[:60] + (["... (diff truncated)"] if len(diff) > 60 else [])
        drift.append(item)
    else:
        if dirty and not allow_dirty:
            fail(f"template {tmpl} has uncommitted changes; commit it first (or --allow-dirty)", 1)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_file() and dest.read_text() == want:
            ok.append(str(rel)); continue
        fd, tmp = tempfile.mkstemp(dir=str(dest.parent), prefix=f".{name}.")
        with os.fdopen(fd, "w") as f: f.write(want)
        os.chmod(tmp, 0o755 if dest_rel.endswith(".sh") else 0o644); os.replace(tmp, dest); wrote.append(str(rel))

for rel in retired:
    dest = root / rel
    if not dest.is_file():
        continue
    why = "the control-plane plugin ships it (SPEC §4)" if plugin and "/architecture-review/" not in rel \
        and "/docs-audit/" not in rel else "replaced by the architect skill (SPEC §19)"
    if not HEADER_RE.search(dest.read_text()[:2000]):
        notes.append(f"{rel}: {why}, but it has no managed-copy header; left alone")
    elif check:
        drift.append({"file": rel, "kind": "retired", "detail": why})
    else:
        dest.unlink()
        try:
            dest.parent.rmdir()
        except OSError:
            pass
        wrote.append(f"{rel} (removed: {why})")

cm = root / "CLAUDE.md"
has_import = cm.is_file() and any(l.strip() == IMPORT_LINE for l in cm.read_text().splitlines())
if plugin:
    # The plugin's SessionStart hook gives the orientation; CLAUDE.md is the product's to edit.
    if has_import:
        (drift if check else notes).append(
            {"file": "CLAUDE.md", "kind": "import_line", "detail": f"remove {IMPORT_LINE} and its section (SPEC §4.3)"}
            if check else f"CLAUDE.md: remove the {IMPORT_LINE} line and its section (SPEC §4.3); the plugin gives the orientation")
elif has_import:
    ok.append("CLAUDE.md (import line)")
elif check:
    drift.append({"file": "CLAUDE.md", "kind": "missing" if not cm.is_file() else "no_import_line",
                  "detail": f"needs a '## Control plane' section with the line {IMPORT_LINE}"})
else:
    cur = cm.read_text() if cm.is_file() else ""
    new = cur + ("" if not cur or cur.endswith("\n") else "\n") + ("\n" if cur else "") + SECTION
    fd, tmp = tempfile.mkstemp(dir=str(root), prefix=".CLAUDE.md.")
    with os.fdopen(fd, "w") as f: f.write(new)
    os.chmod(tmp, 0o644); os.replace(tmp, cm)
    wrote.append("CLAUDE.md (appended Control plane section)" if cur else "CLAUDE.md (created with Control plane section)")

mode = "check" if check else "sync"
print(f"sync-product-docs: {project} {mode} product_root={root}")
for n in notes: print(f"  note: {n}")
for w in wrote: print(f"  wrote: {w}")
for o in ok: print(f"  ok: {o}")
for d in drift:
    print(f"  DRIFT {d['file']}: {d['kind']}" + (f" ({d['header']})" if d.get("header") else "") + (f" — {d['detail']}" if d.get("detail") else ""))
    for line in d.get("diff", []): print(f"    {line}")
if stamp:
    rec = {"schema_version": 1, "project_id": project, "product_root": str(root),
           "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "date_local": today_local(), "drift": bool(drift),
           "items": [{k: v for k, v in d.items() if k != "diff"} for d in drift],
           "priority": "low", "note": "SPEC §9.5: drift is a low-priority note for the Watchdog digest, not an alarm"}
    sp = Path(stamp); sp.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(sp.parent), prefix=f".{sp.name}.")
    with os.fdopen(fd, "w") as f: json.dump(rec, f, indent=2); f.write("\n")
    os.replace(tmp, sp)
if check:
    print("  result: " + ("drift — run scripts/sync-product-docs.sh " + project + " and commit the product change" if drift else "clean"))
sys.exit(1 if (check and drift) else 0)
PY
