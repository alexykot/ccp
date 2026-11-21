"""The durable task log: validation, ordering and the generated index (SPEC §4, §10, §20).

One task per file, `docs/delivery/tasks/NNNN-kebab-slug.md`, never deleted, never renumbered. The run
order follows `depends_on`, ties broken by number (§10.3): a dependency may have a higher number than its
dependant, and `check()` refuses only a missing id or a cycle. What the plane used to leave to discipline, this module
enforces: metadata is YAML frontmatter (a parser can read it), `INDEX.yaml` is generated from the
files rather than written beside them (it cannot drift), and `check()` is the gate the Verifier
runs before any task's own `dod_checks`.

A task file is never deleted and carries no runtime state: `check()` refuses runtime keys in
frontmatter, a task file that git or the committed INDEX knew and that is gone, and a number
reused by another task (a renamed task says `renamed_from: <old id>`), each naming its fix; a task
file with no frontmatter is one failure that names `ccp tasks migrate` (`ccp/taskmigrate.py`).
`warnings()` is what `check` reports without failing (§21.1); each warning is stated with its rule's §.

A task has a kind (§20): `feature` (the default) or `refactor`. A refactor changes no rule, so it
cites house rules or review findings (`rule_refs`, `review_refs`) instead of the spec, and proves
itself by its own checks, never by re-running the gate or full lane (§21.1). With the
architect seat adopted (§19.11), refactors get reserved capacity in `next_task`; by default a refactor joins a
scope only when a task in it depends on the refactor (`refactor_in_scope: "deps"`), and the rest wait
for the top of the next review point's scope. New tasks citing an ADR need its shaping record (`reviews/sh-*.md`) or a waiver.

A task carries `review_point` (§22.1, §22): the review point whose scope it belongs to, set by the
task-log owner when scoping. With the review-point register (`ccp/reviewpoints.py`, which this check
also validates) it is `R<n>` and one of the register's ids; without it, it matches
`ids.review_point.pattern`, as before the register. `ccp tasks close`
stamps work.json's point into a task that carries none, as a fallback.

The product-specific values live in `plane.json`.
"""
from __future__ import annotations

import fnmatch
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import functools

from ccp import config, graph, refs, reviewpoints
from ccp.config import Config, lane_for, lane_stages

NAME_RE = refs.DEFAULT.task_file_re  # the default; checks use refs.ids(cfg).task_file_re

# ---------------------------------------------------------------- the canonical task file (SPEC §5.1)
# The format is the plane's. These names are what ccp reads and writes; a product does not rename them.
SEC_INTENT = "Intent"
SEC_CONTEXT = "Context (not checked)"
SEC_SCOPE = "Scope"
SEC_CHECKS = "dod_checks"
SEC_IMPL = "Implementation notes"
SEC_VERIFY = "Verification notes"
SECTIONS = (SEC_INTENT, SEC_CONTEXT, SEC_SCOPE, SEC_CHECKS, SEC_IMPL, SEC_VERIFY)
# An older name a section is still found under (the plane's template once said "not verified").
SECTION_ALIASES = {SEC_CONTEXT: ("Context (not verified)",)}
# Written during the work, not by the task's writer: left out of estimates (§26.3).
NOTES_SECTIONS = (SEC_IMPL, SEC_VERIFY)
# A dod_check opens `- id: `kind-NN``: a lowercase kind and a number.
CHECK_RE = re.compile(r"^- id: `([a-z]+-\d+)`[ \t]*(?:#.*)?$", re.M)
# A key line of a check's block: an indent, a lowercase key (`dry run (`sha`)` is the key `dry run`), a colon.
FIELD_RE = re.compile(r"^([ \t]+)([a-z_]+(?: [a-z_]+)*)(?: \([^)\n]*\))?:[ \t]*(.*)$", re.M)
# Where a check runs (§5.5): its `runs_on:` line, right after its `setup:` line, holds the one value; a check
# without the line is the workers' to run.
RUNS_ON_KEY = "runs_on"
RUNS_ON_OPERATOR = "operator-machine"
# The statuses a task file carries: knowledge and outcomes. Who is working on a task, and in which
# phase, is runtime state in the queue (§4).
STATUSES = ("pending", "done", "dropped")
TERMINAL = ("done", "dropped")
# Older files may still carry an in-flight status. It reads as its canonical state, with a warning.
LEGACY_STATUSES = {"in_progress": "pending", "blocked": "pending"}
KINDS = ("feature", "refactor")
# §3.5: the operator sign-offs a task may declare (`sign_off:`): `brief`, on text known when the task is
# written, recorded before the claim; `build`, on text the build finds, recorded after verify for the PR head.
SIGN_OFF_STAGES = ("brief", "build")
REFACTOR_REFS = ("rule_refs", "review_refs")  # the default refactor rule (task_log.kinds)
WAIVER_RE = re.compile(r"^waived\s*[—–:-]+\s*\S")
ADR_LINE_RE = re.compile(r"^\W*adr\W*:(.*)$", re.I | re.M)
# Runtime state (SPEC §4, contracts/task.schema.json) lives in the queue, never in a task file.
RUNTIME_KEYS = ("waiting_on", "waiting_on_since", "lease", "lease_holder", "lease_expires_at",
                "session_id", "claude_session_id", "ports", "planned_resume_at", "quota_class",
                "implementation_started_at")
# §10 task_log.dry_run: a step that runs a backticked command, and the writer's record of running it.
# A numbered step (`1.` or `1)`) with "run `…`" anywhere in it, the command wrapped onto the next line too.
# §5.2, ADR-0041 D1: `adopt:` names what a product must do to use a task's delivery; missing, it is this.
ADOPT_NONE = "none"
# §5.2: a step a product must take for the plane to keep working with it starts with this; any other is optional.
ADOPT_REQUIRED = "required:"
# ADR-0041 D1: a task whose `paths` name one of these adds a knob or a setting a product must take, so
# `ccp tasks check` warns when it carries no `adopt:` (a settings template: a templates/ file named *settings*).
ADOPT_SCHEMA = "contracts/plane_config.schema.json"
# §5.2: the binding's blocks a product sets keys in (§8.3); a `none` step that names a key under one of
# them, or under a plane.json block, or a settings key `ccp init` writes, hides a step (`hidden_step`).
BINDING_BLOCKS = ("runner", "lead")
# A key named in prose: dotted words not inside a path (`ccp/upgrade.py` is no key).
ADOPT_KEY_RE = re.compile(r"(?<![\w$./-])[A-Za-z_$][\w$-]*(?:\.[A-Za-z_$][\w$-]*)*")
RUN_STEP_RE = re.compile(r"^[ \t]*\d+[.)][ \t]+(?:[^\n]*?\b)?run[ \t]*\n?[ \t]*`", re.I | re.M)
# Each record says something: what the run printed, or why it cannot run yet (not the template's `<why>`).
DRY_RUN_RE = re.compile(r"^[ \t]*dry run \(`?[0-9a-f]{7,40}`?\):[ \t]*(?:\n[ \t]*)?\S", re.I | re.M)
DRY_RUN_NA_RE = re.compile(r"^[ \t]*dry run:[ \t]*n/a[ \t]*[—–-]+[ \t]*(?:\n[ \t]*)?(?!<[^>\n]*>[ \t]*$)\S", re.I | re.M)
DRY_RUN_LINE_RE = re.compile(r"^[ \t]*dry run\b.*$", re.I | re.M)
INDEX_ID_RE = re.compile(r"^  - id: (\S+)$", re.M)
# §21.1: a check's `steps:`, up to its `expect:` or a dry-run record, read for the commands it runs.
STEPS_RE = re.compile(r"^[ \t]*steps:(.*?)(?=^[ \t]*(?:expect:|dry run\b)|\Z)", re.I | re.M | re.S)
# §21.1 `ccp tasks dry-run`: a numbered step, and the one shape of step it runs: one backticked command and
# nothing else (`N. Run `…`.`), read on the step's text with each line break and the indent around it made one
# space; a run of spaces within a line is kept, as a code span keeps it.
STEP_RE = re.compile(r"^[ \t]*(\d+)[.)][ \t]+", re.M)
LINE_BREAK_RE = re.compile(r"[ \t]*\n[ \t]*")
SOLE_COMMAND_RE = re.compile(r"run (`+)(?!`)((?:(?!\1).)+?)(?<!`)\1\.?", re.I)
# The lane roles a refactor's own checks never re-run (§20.3): the verifier's gate already runs them.
WHOLE_SUITE_ROLES = ("gate", "full")
SHELL_CONTROL = frozenset({";", "&", "&&", "|", "||", "(", ")"})
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
REDIRECT_RE = re.compile(r"^[<>&]*[<>][<>&]*$")
# Words that run the command after them: `env [-u NAME|NAME=value]…`, `bash`/`sh`, `time`, `timeout N`.
SHELLS = frozenset({"bash", "sh"})
# §5: the plane template's placeholders. One left in a task file not yet done or dropped is a copy
# not filled in. A placeholder inside a code span or a fenced block is quoted, not left, so it is not read.
PLACEHOLDERS = ("NNNN-kebab-slug", "YYYY-MM-DD", "As a <role>", "<preconditions",
                "<concrete, observable result>", "One line, imperative")
# A fence closes on a line of only its own character, at least as many as opened it; a code span
# stays on one line, so one stray backtick cannot quote the lines after it.
FENCE_RE = re.compile(r"^[ \t]*(?P<f>(?P<c>[`~])(?P=c){2,})[^\n]*\n.*?^[ \t]*(?P=f)(?P=c)*[ \t]*$", re.M | re.S)
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)[^\n]+?(?<!`)\1(?!`)")
# §5: a measured premise in Context names the command that measured it. A number here is a figure
# stated in prose: a run of digits that is not part of an id or a ref (`R5`, `§31.1`, `ADR-0033`,
# `PR #89`, a date, a time, a sha), not a zero-padded id (`0000`), not a list marker and not in a
# date written with its month's name (`11 Nov 2026`, `November 11, 2026`). A size or a time joined
# to its unit (`40MB`, `300ms`) and a dash range (`5-10`, `2-3s`) are numbers too; a year and month
# (`2026-11`) is not. A command is a code span of at least two words (`git grep -c foo`); a lone path
# or id in backticks is not one.
_NUM = r"\d+(?:[.,]\d+)*"
_UNIT = r"(?i:[kmgtp]i?b|b|k|m|ns|us|µs|ms|s|secs?|mins?|h|hrs?|d|x)"
CONTEXT_NUMBER_RE = re.compile(rf"(?<![\w§.\-/:#])(?!0\d)(?!(?:19|20)\d\d-(?:0[1-9]|1[0-2])(?!\d))"
                               rf"{_NUM}(?:-{_NUM})?{_UNIT}?(?![\w\-/:]|[.,]\d)")
# A stated limit or a protocol code is not a measurement: the number right after one of these words.
NOT_MEASURED_RE = re.compile(r"(?i:\b(?:at most|at least|up to|no more than|no less than|within|under|status code|status|"
                             rf"HTTP|exit code|exits|exit)[ \t]+)({_NUM}(?:-{_NUM})?{_UNIT}?)")
LIST_MARKER_RE = re.compile(r"^([ \t]*)\d+[.)](?=[ \t])")
_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
          r"Sep(?:t|tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
WORD_DATE_RE = re.compile(rf"\b(?:\d{{1,2}}[ \t]+{_MONTH}(?:[ \t]+\d{{4}})?|{_MONTH}[ \t]+\d{{1,2}}(?:,?[ \t]+\d{{4}})?)\b")
# §10.5, §5.5: a line of a quoted block, where a ruling written verbatim goes; not read for numbers.
QUOTED_RE = re.compile(r"^[ \t]*>(?:[ \t]|$)")
# §21.1: the commit a task's Context was measured at, its first ``Measured at `<sha>` ``; a stale-Context
# warning names this many of the commits since, then counts the rest.
MEASURED_AT_RE = re.compile(r"\bMeasured at `([0-9a-f]{7,40})`", re.I)
STALE_NAMED = 3
# §21.1: a task file with no frontmatter, as `check` and `ccp tasks list` name it.
NO_FRONTMATTER = ("no frontmatter: an earlier plane generation's task file? convert it with "
                  "`ccp tasks migrate`")
# §5.2: what an empty ref list that includes spec_refs is told to do.
SPEC_REFS_HINT = " — list the SPEC sections this task answers to in `spec_refs` and cite them in its text (§5.2)"


@functools.lru_cache(maxsize=8)
def prose_dep_re(width: int) -> re.Pattern[str]:
    """A prerequisite named in prose: "gated on 0197", "blocked by `0197`", "waits for task 0197"."""
    return re.compile(
        r"\b(?:gated on|gated by|blocked on|blocked by|waits? (?:for|on)|waiting (?:for|on)|depends on|"
        rf"dependent on|requires|prerequisite|until|after|once)\s+(?:task\s+)?`?(\d{{{width}}})(?![-/.:]?\d)", re.I)


PROSE_DEP_RE = prose_dep_re(refs.DEFAULT.task_width)


def _strip_comment(v: str) -> str:
    """Drop a trailing ` # comment` outside quotes (the templates annotate their fields)."""
    q = None
    for i, ch in enumerate(v):
        if ch in "\"'" and q in (None, ch):
            q = None if q else ch
        elif ch == "#" and q is None and (i == 0 or v[i - 1] in " \t"):
            return v[:i].rstrip()
    return v


def _split_list(inner: str) -> list[str]:
    """`a, "b, c"` → ["a", "b, c"]: commas inside quotes stay in their item."""
    items, cur, q = [], "", None
    for ch in inner:
        if ch in "\"'" and (q == ch or (q is None and not cur.strip())):  # a quote opens only an item
            q = None if q else ch
        elif ch == "," and q is None:
            items.append(cur)
            cur = ""
            continue
        cur += ch
    return [i.strip().strip('"').strip("'") for i in items + [cur] if i.strip()]


def adr_number(ref: str, cfg: Config | None = None) -> int | None:
    """The ADR an `adr_refs` entry cites, or None when it cites none (refs.Ids.adr_number)."""
    return refs.ids(cfg).adr_number(ref)


def frontmatter(text: str) -> dict[str, Any]:
    """Frontmatter as scalars and flat inline lists. Deliberately tiny: the fields are fixed, and
    the plane takes no YAML dependency."""
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    out: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = _strip_comment(v.strip())
        if v.startswith("[") and v.endswith("]"):
            out[k.strip()] = _split_list(v[1:-1].strip())
        else:
            out[k.strip()] = v.strip('"').strip("'")
    return out


def has_frontmatter(text: str) -> bool:
    """The file opens with a `---` block that closes, as `frontmatter` reads it: the current format's
    frontmatter (§5.2). A task file without one is an earlier plane generation's, which `ccp tasks
    migrate` converts (§5.3)."""
    return text.startswith("---\n") and text.find("\n---\n", 4) != -1


def canonical_status(status: Any) -> Any:
    """A task file's status as the canonical vocabulary reads it: a legacy in-flight value
    (`in_progress`, `blocked`) is `pending`; anything else is returned as given."""
    return LEGACY_STATUSES.get(str(status), status) if isinstance(status, str) else status


def _section_at(text: str, name: str) -> tuple[int, str] | None:
    """The body under `## <name>` (or an older name for that section), up to the next `## `
    heading, with its offset in `text`; None when the heading is absent."""
    names = [name, *SECTION_ALIASES.get(name, ())]
    names += [k for k, olds in SECTION_ALIASES.items() if name in olds]
    m = None
    for n in names:
        m = re.search(rf"^## {re.escape(n)}[ \t]*$", text, re.M)
        if m:
            break
    if not m:
        return None
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return m.end(), (text[m.end(): m.end() + nxt.start()] if nxt else text[m.end():])


def _section(text: str, name: str) -> str | None:
    """The body under `## <name>` (or an older name for that section), up to the next `## `
    heading; None when the heading is absent."""
    at = _section_at(text, name)
    return at[1] if at else None


@dataclass(frozen=True, eq=False)
class Check:
    """One dod_check of a task file (§5.5): its `id`; its `block`, the text after its `- id:` line up to the next
    check or the section's end; `fields`, the block's `key: value` lines by key (the first line of each, at
    the indent of the block's first key, a key a lowercase word or words: `runs_on`, `expect`, `dry run`); and
    where the block starts and ends in the file's text (`start`, `end`)."""
    id: str
    block: str
    fields: dict[str, str]
    start: int
    end: int

    @property
    def runs_on(self) -> str | None:
        """§5.5: the value of the check's `runs_on:` line as written, or None when it has none (the workers'
        check). Only `operator-machine` is valid; `runs_on_errors` names any other, or a misplaced line."""
        return self.fields.get(RUNS_ON_KEY)

    @property
    def on_operator_machine(self) -> bool:
        """§5.5: the check is marked as one the workers cannot take."""
        return self.runs_on == RUNS_ON_OPERATOR


def _fields(block: str) -> dict[str, str]:
    """The `key: value` lines of a check's block, at the indent of its first one; a key repeated keeps its
    first line. A line deeper in (a step, a wrapped value) is no key."""
    out: dict[str, str] = {}
    indent: str | None = None
    for m in FIELD_RE.finditer(block):
        if indent is None:
            indent = m.group(1)
        if m.group(1) == indent:
            out.setdefault(m.group(2), m.group(3).strip())
    return out


def checks(text: str) -> list[Check]:
    """§5.5: each dod_check of a task file's text, in order. The one parser of the section (house rule E22):
    every reader of a check's id, block or fields (`tasks check`, `tasks dry-run`, a check's `runs_on`, and the
    estimates' read of the ids) reads it here. No `dod_checks` section: none."""
    at = _section_at(text, SEC_CHECKS)
    if at is None:
        return []
    start, body = at
    heads = list(CHECK_RE.finditer(body))
    out = []
    for i, m in enumerate(heads):
        lo, hi = start + m.end(), start + (heads[i + 1].start() if i + 1 < len(heads) else len(body))
        out.append(Check(m.group(1), text[lo:hi], _fields(text[lo:hi]), lo, hi))
    return out


def runs_on_errors(c: Check) -> list[str]:
    """§21.1: what is wrong with a check's `runs_on:` lines, each a phrase naming the line: a value other than
    `operator-machine`, or a line that is not the key right after the check's `setup:` (its wrapped lines
    aside). A line deeper in than the check's keys is out of place too."""
    keys = list(FIELD_RE.finditer(c.block))
    indent = keys[0].group(1) if keys else ""
    out: list[str] = []
    prev: str | None = None
    for m in keys:
        key, value = m.group(2), m.group(3).strip()
        if key == RUNS_ON_KEY:
            if value != RUNS_ON_OPERATOR:
                out.append(f"`{RUNS_ON_KEY}: {value}` is not `{RUNS_ON_KEY}: {RUNS_ON_OPERATOR}`, the one value it takes")
            if m.group(1) != indent or prev != "setup":
                out.append(f"its `{RUNS_ON_KEY}:` line is not right after its `setup:` line")
        if m.group(1) == indent:
            prev = key
    return out


def check_steps(block: str) -> list[tuple[str, str | None]]:
    """§21.1 `ccp tasks dry-run`: each numbered step of a check's body, as its number and, when the step is
    one backticked command and nothing else (`N. Run `…`.`), that command; None for any other step."""
    out: list[tuple[str, str | None]] = []
    for s in STEPS_RE.finditer(block):
        steps = s.group(1)
        items = list(STEP_RE.finditer(steps))
        for i, m in enumerate(items):
            raw = steps[m.end(): items[i + 1].start() if i + 1 < len(items) else len(steps)]
            text = LINE_BREAK_RE.sub(" ", raw.strip())
            sole = SOLE_COMMAND_RE.fullmatch(text)
            out.append((m.group(1), sole.group(2).strip() if sole and sole.group(2).strip() else None))
    return out


def _check_lines_end(text: str, start: int, end: int) -> int:
    """Where a check's last line ends: the last non-blank line of its body that belongs to it (indented),
    before any unindented text after the checks."""
    last, pos = start, start
    for line in text[start:end].split("\n")[1:]:
        pos += 1
        if line.strip() and not line[:1].isspace():
            break
        pos += len(line)
        if line.strip():
            last = pos
    return last


def with_dry_runs(text: str, sha: str, records: dict[str, str]) -> str:
    """§21.1 `ccp tasks dry-run --write`: `text` with the dry-run record of each check `records` names set to
    ``dry run (`<sha>`): <record>``, replacing the one already there (its wrapped lines too), else added
    after the check's last line, at its keys' indent. Nothing else in `text` changes."""
    for c in reversed(checks(text)):
        cid, start, end = c.id, c.start, c.end
        if cid not in records:
            continue
        old = DRY_RUN_LINE_RE.search(text, start, end)
        if old:
            indent = old.group(0)[: len(old.group(0)) - len(old.group(0).lstrip())]
            stop = old.end()
            while stop < end:
                nxt = text.find("\n", stop + 1)
                line = text[stop + 1: end if nxt == -1 or nxt > end else nxt]
                if not line.strip() or len(line) - len(line.lstrip()) <= len(indent):
                    break
                stop += 1 + len(line)
            text = f"{text[:old.start()]}{indent}dry run (`{sha}`): {records[cid]}{text[stop:]}"
        else:
            key = re.search(r"^([ \t]+)(?:expect|steps|setup|story):", text[start:end], re.M)
            at = _check_lines_end(text, start, end)
            text = f"{text[:at]}\n{key.group(1) if key else '  '}dry run (`{sha}`): {records[cid]}{text[at:]}"
    return text


def load(cfg: Config, texts: dict[Path, str] | None = None) -> list[dict[str, Any]]:
    """Every task, in filesystem (number) order; the run order is `ranked`'s. `texts` stands in for the
    text of the files it names (`ccp tasks migrate` checks a file before writing it)."""
    out = []
    for f in sorted(cfg.tasks_dir.glob("*.md")):
        text = texts[f] if texts and f in texts else f.read_text()
        meta = frontmatter(text)
        if meta.get("status") in LEGACY_STATUSES:   # §5: read as its canonical state everywhere
            meta["_legacy_status"] = meta["status"]
            meta["status"] = canonical_status(meta["status"])
        meta["_file"] = f
        meta["_text"] = text
        meta["_checks"] = [c.id for c in checks(text)]
        out.append(meta)
    return out


def lags(cfg: Config, ref: str) -> bool:
    """The checkout's HEAD lacks a commit `ref` holds (it is behind it, or has diverged from it). False
    when `ref` does not resolve here, or HEAD already contains it. Nothing is fetched."""
    if _git(cfg, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is None:
        return False
    r = subprocess.run(["git", "-C", str(cfg.root), "merge-base", "--is-ancestor", ref, "HEAD"],
                       capture_output=True, text=True)
    return r.returncode == 1


def text_at(cfg: Config, rev: str, rel: str) -> str | None:
    """The text of the file `rel` (relative to the checkout's root) at `rev`, read from the git objects: a
    commit or ref, or "" for the index. None when `rev` does not resolve or the file is not there; the
    checkout's copy is never read in its place, a caller that wants it says so. The reader of a task or ADR file
    at a commit for lifecycle, adr and verify; bytes are decoded as they are (a CRLF file keeps its `\\r\\n`),
    `statuses_at` stays its own batch read of many files."""
    r = subprocess.run(["git", "-C", str(cfg.root), "show", f"{rev}:./{rel}"], capture_output=True)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else None


def statuses_at(cfg: Config, ref: str, ids: list[str]) -> dict[str, str]:
    """The canonical status each named task's file says at `ref` (one `git cat-file --batch`), by task id
    (its file name). A task with no file there, or a `ref` that does not resolve, is left out."""
    rel = cfg.rel(cfg.tasks_dir)
    req = "".join(f"{ref}:{rel}/{tid}.md\n" for tid in ids).encode()
    r = subprocess.run(["git", "-C", str(cfg.root), "cat-file", "--batch"], input=req, capture_output=True)
    if r.returncode != 0:
        return {}
    out: dict[str, str] = {}
    data, pos = r.stdout, 0
    for tid in ids:
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        head = data[pos:nl].split()
        pos = nl + 1
        if len(head) != 3 or head[1] != b"blob":
            continue
        size = int(head[2])
        text = data[pos:pos + size].decode("utf-8", "replace")
        pos += size + 1
        status = canonical_status(frontmatter(text).get("status"))
        if isinstance(status, str) and status:
            out[tid] = status
    return out


def _as_list(v: Any) -> list[str]:
    return v if isinstance(v, list) else ([] if v in (None, "") else [v])


def _id_list_errors(rel: str, t: dict[str, Any], key: str, ids: set[Any], own: bool = False) -> list[str]:
    """§5: a frontmatter list of task ids (`depends_on`, `clashes_with`): an id that names no task is
    refused, and with `own` so is the task's own id (a task cannot clash with itself)."""
    out = []
    for x in _as_list(t.get(key)):
        if x not in ids:
            out.append(f"{rel}: {key} `{x}`, which does not exist")
        elif own and x == t.get("task_id"):
            out.append(f"{rel}: {key} `{x}`, which is the task itself")
    return out


def sign_off_stages(t: dict[str, Any]) -> list[str]:
    """§3.5: the sign-offs the task declares (`sign_off: brief`, `build` or both), in that order."""
    want = {str(x).strip().lower() for x in _as_list(t.get("sign_off"))}
    return [s for s in SIGN_OFF_STAGES if s in want]


def sign_off_malformed(t: dict[str, Any]) -> str | None:
    """§3.5: why the task's `sign_off:` value is not one the plane reads (no stage, or one that is not
    brief or build), or None when it is absent or well formed."""
    if "sign_off" not in t:
        return None
    so = [str(x).strip().lower() for x in _as_list(t["sign_off"])]
    if so and all(x in SIGN_OFF_STAGES for x in so):
        return None
    return (f"sign_off {t['sign_off']!r} names no stage, or one that is not "
            f"{' or '.join(SIGN_OFF_STAGES)} (SPEC §3.5)")


def adopt_step(t: dict[str, Any]) -> str:
    """§5.2: the task's adoption step, `none` when it carries no `adopt:` key (ADR-0041 D1)."""
    v = t.get("adopt")
    return v.strip() if isinstance(v, str) and v.strip() else ADOPT_NONE


def adopt_required(step: str) -> tuple[bool, str]:
    """§5.2: whether an `adopt` step is required (it starts with `required:`, in any case), and the step
    without that prefix; any other step is optional and comes back as it is."""
    if step[:len(ADOPT_REQUIRED)].lower() == ADOPT_REQUIRED:
        return True, step[len(ADOPT_REQUIRED):].strip()
    return False, step


def asks_nothing(step: str) -> bool:
    """§5.2: whether an `adopt` step is `none`: its first word, after any `required:` prefix, is `none`, an
    explanation after it allowed (`none: it applies by itself`)."""
    words = adopt_required(step.strip())[1].split(None, 1)
    return bool(words) and words[0].rstrip(":;,.").lower() == ADOPT_NONE


def adopt_malformed(t: dict[str, Any]) -> str | None:
    """§5.2: why the task's `adopt:` value is not one line of text, or None when it is absent or one."""
    if "adopt" not in t:
        return None
    v = t["adopt"]
    if isinstance(v, str) and v.strip():
        return None
    return (f"adopt {v!r} is not one step: write `none`, or one line naming the file and key a product "
            "sets to use what the task delivers (SPEC §5.2)")


def _names_knob(path: str) -> bool:
    """ADR-0041 D1: a `paths` entry that names the plane.json schema (itself or a glob over it) or a
    settings template (a file under templates/ whose name holds `settings`)."""
    p = path.strip().removeprefix("./")
    if p == ADOPT_SCHEMA or (any(c in p for c in "*?[") and fnmatch.fnmatch(ADOPT_SCHEMA, p)):
        return True
    return p.startswith("templates/") and "settings" in p.rsplit("/", 1)[-1]


def missing_adopt(t: dict[str, Any], rel: str) -> list[str]:
    """ADR-0041 D1: a task not yet done or dropped whose `paths` name the plane.json schema or a settings
    template and that carries no `adopt:` key. A warning: a product learns its step from that key."""
    if t.get("status") in TERMINAL or "adopt" in t:
        return []
    named = [str(p) for p in _as_list(t.get("paths")) if _names_knob(str(p))]
    if not named:
        return []
    return [f"{rel}: its paths name a knob a product sets ({', '.join(named)}) but it carries no `adopt:` key: "
            "name the step a product takes to use it (the file and key), or `adopt: none` (SPEC §5.2)"]


def hidden_step(t: dict[str, Any], rel: str) -> list[str]:
    """§5.2: a task not dropped whose `adopt` value's first word is `none` and that names a dotted key under a
    plane.json block or a binding block (`runner`, `lead`), or a settings key `ccp init` writes: a step
    behind `none`, which `ccp upgrade status` never shows. A warning."""
    v = t.get("adopt")
    if t.get("status") == "dropped" or not isinstance(v, str) or not asks_nothing(v.strip()):
        return []
    from ccp import init  # noqa: PLC0415  (init reads the task log)
    settings = {*init.ANCHOR, init.CACHE_TTL_SETTING[0], init.COMPACT_SETTING}
    keys: list[str] = []
    for m in ADOPT_KEY_RE.finditer(v):
        parts = m.group(0).split(".")
        named = (len(parts) > 1 and parts[0] in (*config.BLOCKS, *BINDING_BLOCKS)) or parts[0] in settings
        if named and m.group(0) not in keys:
            keys.append(m.group(0))
    if not keys:
        return []
    return [f"{rel}: its `adopt` value starts with `none` but names {', '.join(f'`{k}`' for k in keys)}, a key "
            "a product sets: write the step a product takes (`<file> <key> [value]`), not `none`, so "
            "`ccp upgrade status` shows it (SPEC §5.2)"]


def kind_of(t: dict[str, Any]) -> str:
    return str(t.get("kind") or "feature")


def _number(tid: Any, cfg: Config | None = None) -> int | None:
    m = refs.ids(cfg).task_number_re.match(str(tid or ""))
    return int(m.group(1)) if m else None


def seat_reads(cfg: Config, t: dict[str, Any]) -> bool:
    """Whether the architect seat judges this task (§19.11): the seat is on and the task is numbered from its
    adoption point. With no adoption point it judges none; a task without a number is judged."""
    start = config.adoption_point(cfg)
    if not config.architect_adopted(cfg):
        return False
    n = _number(t.get("task_id"), cfg)
    return n is None or n >= start


def lane_refactor(cfg: Config, t: dict[str, Any]) -> bool:
    """Whether the refactor lane (§20.3, §20.4) counts this task a refactor: its `kind` is read, like the
    kind checks, only from the adoption point (§19.11); one numbered before it is an ordinary task."""
    return kind_of(t) == "refactor" and seat_reads(cfg, t)


def shaped_adrs(cfg: Config) -> set[int]:
    """ADR numbers that have a shaping record: the `ADR-NNNN` tokens on a `reviews/sh-*.md`'s `ADR:`
    lines (`ADR: ADR-0031 (accepted 2026-10-06)` names ADR 31 only), or anywhere in a record that has
    no such line. A bare number never counts."""
    out: set[int] = set()
    for f in sorted(cfg.reviews_dir.glob("sh-*.md")):
        text = f.read_text(errors="ignore")
        lines = ADR_LINE_RE.findall(text)
        out.update(int(n) for n in refs.ids(cfg).adr_mention_re.findall("\n".join(lines) if lines else text))
    return out


REF_LABELS = {"rule_refs": "rule_refs (house-rule ids)", "review_refs": "review_refs (finding ids)"}


def kind_refs(cfg: Config, kind: str) -> list[str]:
    """The ref lists a task of `kind` must cite one of: the kind's own `refs_any`, else the task
    log's (`task_log.kinds`, §20)."""
    rule = (cfg.task_log.get("kinds") or {}).get(kind) or {}
    own = rule.get("refs_any")
    return list(own) if own else list(cfg.task_log["refs_any"])


def kind_forbids(cfg: Config, kind: str) -> list[str]:
    """The ref lists a task of `kind` must leave empty: the kind's `forbid`, plus, for a kind with
    its own `refs_any`, the task log's `refs_any` lists it does not share."""
    rule = (cfg.task_log.get("kinds") or {}).get(kind) or {}
    own = rule.get("refs_any")
    extra = [k for k in cfg.task_log["refs_any"] if own and k not in own]
    return list(dict.fromkeys([*(rule.get("forbid") or []), *extra]))


def _check_kind(cfg: Config, t: dict[str, Any], rel: str) -> list[str]:
    """§20, §5: a task's kind sets which refs it cites (`task_log.kinds`). By default a refactor
    changes no rule: it cites house rules or findings, never the spec or an ADR."""
    kind = kind_of(t)
    kinds = cfg.task_log.get("kinds") or {}
    if kind not in kinds:
        return [f"{rel}: kind {kind!r} is not one of {', '.join(kinds)}"]
    errs = []
    cited = [k for k in kind_forbids(cfg, kind) if _as_list(t.get(k))]
    if cited:
        why = "changes no rule, so it " if kind == "refactor" else ""
        hint = " (a change to behaviour or stored data is a feature task)" if kind == "refactor" else ""
        errs.append(f"{rel}: a {kind} {why}cites no {', '.join(cited)}{hint}")
    if not (kinds.get(kind) or {}).get("refs_any"):
        return errs
    need = kind_refs(cfg, kind)
    if not any(_as_list(t.get(k)) for k in need):
        errs.append(f"{rel}: a {kind} cites " + " or ".join(REF_LABELS.get(k, k) for k in need) + _spec_hint(need))
    for r in _as_list(t.get("rule_refs")) if "rule_refs" in need else []:
        if not refs.ids(cfg).is_rule_id(r):
            errs.append(f"{rel}: rule_refs entry {r!r} is not a house-rule id ({refs.ids(cfg).rule_shape})")
    return errs


def _check_dry_runs(t: dict[str, Any], rel: str) -> list[str]:
    """§10 task_log.dry_run: each check of a task not yet done (or dropped) that has a step running a
    backticked command carries its writer's `dry run (<sha>):` line, or `dry run: n/a — <reason>`. Only
    that the line is there is checked; reading its output against `expect` stays the writer's."""
    if t.get("status") in TERMINAL:
        return []
    errs = []
    for c in checks(t["_text"]):
        block, cid = c.block, c.id
        if RUN_STEP_RE.search(block) and not (DRY_RUN_RE.search(block) or DRY_RUN_NA_RE.search(block)):
            errs.append(f"{rel}: dod_check `{cid}` runs a command but records no `dry run (<commit>):` "
                        "line from its writer's run, nor `dry run: n/a — <reason>` (task_log.dry_run, WRITING-tasks.md)")
    return errs


def _check_runs_on(t: dict[str, Any], rel: str) -> list[str]:
    """§21.1: each check's `runs_on:` line holds `operator-machine` and comes right after its `setup:` line,
    in a task of any status; a failure names the task's file and the check."""
    return [f"{rel}: dod_check `{c.id}`: {why} (SPEC §5.5)" for c in checks(t["_text"]) for why in runs_on_errors(c)]


def _tokens(cmd: str) -> list[str]:
    """A backticked command's shell words, with `;`, `&&`, `|` and the like as words of their own."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return [w[2:] if w.startswith("./") else w for w in lex]
    except ValueError:  # an unclosed quote: read it by whitespace
        return [w[2:] if w.startswith("./") else w for w in cmd.split()]


def _ends_command(words: list[str], k: int) -> bool:
    """A command ends at word `k`: the end, a shell control word, or a redirection (`>`, `2>&1`…)."""
    if k == len(words) or words[k] in SHELL_CONTROL or REDIRECT_RE.match(words[k]):
        return True
    return words[k].isdigit() and k + 1 < len(words) and bool(REDIRECT_RE.match(words[k + 1]))


def _command_starts(words: list[str], k: int) -> Iterator[int]:
    """From a command position `k`, each index a command may start at: `k` itself, then past each
    `NAME=value` word and each wrapper `env [-u NAME|NAME=value]…`, `bash`/`sh`, `time` and `timeout N`.
    Every step is yielded, so a lane declared with its wrapper (`bash scripts/gate.sh`) still matches."""
    while k < len(words):
        yield k
        w = words[k].rsplit("/", 1)[-1]
        if ASSIGNMENT_RE.match(words[k]) or w in SHELLS or w == "time":
            k += 1
        elif w == "env":
            k += 1
            while k < len(words) and (words[k] in ("-i", "-") or ASSIGNMENT_RE.match(words[k])
                                      or (words[k] == "-u" and k + 1 < len(words))):
                k += 2 if words[k] == "-u" else 1
        elif w == "timeout" and k + 1 < len(words) and re.match(r"^\d+(\.\d+)?[smhd]?$", words[k + 1]):
            k += 2
        else:
            return


def _suite_run_dashes(words: list[str], k: int) -> bool:
    """Word `k` is the `--` that ends a `ccp suite run`'s options, so a command starts after it; the
    `--` of any other command (`git diff -- <path>`) is not a command position."""
    start = max((i + 1 for i in range(k) if words[i] in SHELL_CONTROL), default=0)
    for i in range(start, k):
        if words[i].rsplit("/", 1)[-1] == "ccp" and words[i + 1:i + 3] == ["suite", "run"]:
            return words.index("--", i + 3) == k
    return False


def _runs_argv(words: list[str], argv: list[str]) -> bool:
    """`words` run `argv` as a whole command: it starts where a command starts (the start, after a
    shell control word or after a `ccp suite run`'s `--`, past any `NAME=value` and the wrappers
    `_command_starts` names) and ends where one ends (`_ends_command`)."""
    argv = [a[2:] if a.startswith("./") else a for a in argv]
    n = len(argv)
    for k in range(len(words)):
        if k and words[k - 1] not in SHELL_CONTROL and not (words[k - 1] == "--" and _suite_run_dashes(words, k - 1)):
            continue
        if any(words[i:i + n] == argv and _ends_command(words, i + n) for i in _command_starts(words, k)):
            return True
    return False


def _runs_lane(words: list[str], lane: str) -> bool:
    """`words` hold `ccp suite run … --lane <lane>` with no `-- <command>`: the run of the lane's
    declared command (§14.1)."""
    for i, w in enumerate(words):
        if w.rsplit("/", 1)[-1] != "ccp" or words[i + 1:i + 3] != ["suite", "run"]:
            continue
        rest = words[i + 3:]
        end = next((k for k, x in enumerate(rest) if x in SHELL_CONTROL), len(rest))
        opts = rest[:end]
        if "--" in opts:
            continue
        if any(x == f"--lane={lane}" or (x == "--lane" and k + 1 < len(opts) and opts[k + 1] == lane)
               for k, x in enumerate(opts)):
            return True
    return False


def _check_refactor_gate(cfg: Config, t: dict[str, Any], rel: str) -> list[str]:
    """§20.3, §21.1: a refactor proves itself by its own checks; the verifier's gate already runs the
    whole suite. A refactor not yet done (or dropped) whose dod_check step runs the gate or full lane,
    as `suite.lanes` declares it (the lane's argv as a whole command, or `ccp suite run --lane <lane>`
    without a command), is refused, naming the check and the lane."""
    if kind_of(t) != "refactor" or t.get("status") in TERMINAL:
        return []
    lanes = (cfg.suite or {}).get("lanes") or {}
    judged = [(role, lane_for(cfg, role)) for role in WHOLE_SUITE_ROLES]
    judged = [(role, lane, lanes[lane]) for role, lane in judged if lane in lanes]
    if not judged:
        return []
    errs = []
    for c in checks(t["_text"]):
        cid = c.id
        steps = "".join(s.group(1) for s in STEPS_RE.finditer(c.block))
        runs = [_tokens(span.group(0).strip("`")) for span in CODE_SPAN_RE.finditer(steps)]
        hit = [f"{role} lane `{lane}`" for role, lane, decl in judged
               if any(_runs_lane(w, lane) or (lane_stages(decl) is None and _runs_argv(w, decl)) for w in runs)]
        if hit:
            errs.append(f"{rel}: dod_check `{cid}` of a refactor runs the {' and the '.join(hit)} — a refactor "
                        "proves itself by its own checks; the verifier's gate already runs the whole suite (§20.3, §21.1)")
    return errs


def _blank(m: re.Match[str]) -> str:
    """The matched text as spaces, its line breaks kept, so line numbers still count."""
    return re.sub(r"[^\n]", " ", m.group(0))


def _check_placeholders(t: dict[str, Any], rel: str) -> list[str]:
    """§5: a task not yet done or dropped that still holds a template placeholder is a copy not
    filled in. Names each placeholder and its line; quoted ones (code spans, fenced blocks) pass."""
    if t.get("status") in TERMINAL:
        return []
    text = CODE_SPAN_RE.sub(_blank, FENCE_RE.sub(_blank, t["_text"]))
    return [f"{rel}:{n}: template placeholder {ph!r} is still there — write the task's own text in its place "
            "(§5), or put it in backticks if you mean the text itself"
            for n, line in enumerate(text.split("\n"), 1) for ph in PLACEHOLDERS if ph in line]


def unmeasured_numbers(t: dict[str, Any], rel: str) -> list[str]:
    """§5: a task not yet done or dropped whose Context states a number on a line with no backticked
    command, named with its line. Fenced blocks, code spans and the lines of a quoted block (`> `, where a
    ruling written verbatim goes, §10.5) are quoted text, not read for numbers, nor is a stated limit or a
    protocol code: a number right after `at most`, `at least`, `up to`, `no more than`, `no less than`,
    `within` or `under`, or after `status`, `status code`, `HTTP`, `exit`, `exits` or `exit code` (any case)."""
    if t.get("status") in TERMINAL:
        return []
    at = _section_at(t["_text"], SEC_CONTEXT)
    if at is None:
        return []
    start, body = at
    first = t["_text"].count("\n", 0, start) + 1
    unfenced = FENCE_RE.sub(_blank, body)
    out = []
    for n, line in enumerate(unfenced.split("\n")):
        if QUOTED_RE.match(line):
            continue
        if any(len(span.group(0).strip("`").split()) > 1 for span in CODE_SPAN_RE.finditer(line)):
            continue
        prose = WORD_DATE_RE.sub(_blank, LIST_MARKER_RE.sub(r"\1", CODE_SPAN_RE.sub(_blank, line)))
        prose = NOT_MEASURED_RE.sub(lambda m: m.group(0)[:m.start(1) - m.start(0)] + " " * len(m.group(1)), prose)
        nums = [m.group(0) for m in CONTEXT_NUMBER_RE.finditer(prose)]
        if nums:
            out.append(f"{rel}:{first + n}: Context states a number ({', '.join(nums)}) with no backticked command on "
                       "its line: name the command that measured it and the commit it ran at (§5)")
    return out


def stale_warning(rel: str, sha: str, commits: list[str]) -> list[str]:
    """§21.1: the warning for a task whose Context was measured at `sha` when `commits` (newest first) have
    changed its paths since: the first few named, the rest counted. None without commits."""
    if not commits:
        return []
    named = ", ".join(commits[:STALE_NAMED]) + (f" and {len(commits) - STALE_NAMED} more" if len(commits) > STALE_NAMED else "")
    return [f"{rel}: Context says Measured at `{sha}`, and {len(commits)} commit(s) since changed the task's paths "
            f"({named}): re-read the brief against them and re-measure its figures (§21.1)"]


def stale_context(cfg: Config, t: dict[str, Any], rel: str) -> list[str]:
    """§21.1: a task not yet done or dropped whose Context says ``Measured at `<sha>` `` (the first one) and whose
    `paths` a commit since that sha changed (`git log <sha>..HEAD -- <paths>`), warned about. An unknown sha, a
    task with no paths or a checkout without git gives no warning."""
    if t.get("status") in TERMINAL:
        return []
    m = MEASURED_AT_RE.search(_section(t["_text"], SEC_CONTEXT) or "")
    paths = [str(p).strip() for p in _as_list(t.get("paths")) if str(p).strip()]
    if not m or not paths:
        return []
    log = _git(cfg, "log", "--format=%h", f"{m.group(1)}..HEAD", "--", *paths)
    return stale_warning(rel, m.group(1), (log or "").split())


def _names_spec(path: str, spec_paths: list[str]) -> bool:
    """§3.5: whether a path names a SPEC file: it equals an entry of `spec_paths` or, for an entry
    ending in `/`, lies under it; an entry without its `/` is exact (`docs/spec` meets no file under it)."""
    p = path.strip().removeprefix("./")
    return any(p == e or (e.endswith("/") and p.startswith(e))
               for e in (str(x).strip().removeprefix("./") for x in spec_paths) if e)


def unsigned_spec_edit(cfg: Config, t: dict[str, Any], rel: str) -> list[str]:
    """§3.5: a task not yet done or dropped whose `paths` name a SPEC file (`spec_paths`) and that
    neither declares a `brief` sign-off nor says `§31.1` on a Scope line (its SPEC text only describes its
    own feature). A warning: the rule text is signed when the task is written, not after verify."""
    if t.get("status") in TERMINAL or "brief" in sign_off_stages(t):
        return []
    named = [str(p) for p in _as_list(t.get("paths")) if _names_spec(str(p), config.spec_paths(cfg))]
    if not named or "§31.1" in (_section(t["_text"], SEC_SCOPE) or ""):
        return []
    return [f"{rel}: its paths name the SPEC ({', '.join(named)}) but it declares no `sign_off: brief`: a task "
            "that changes a § rule carries the exact CURRENT → PROPOSED text in its Scope and declares "
            "`sign_off: brief`, so the operator signs the words before the claim; one whose SPEC text only "
            "describes its own feature says `§31.1` in its Scope (SPEC §3.5)"]


def _spec_hint(lists: list[str]) -> str:
    """The hint for a task that cites none of `lists`, when spec_refs is one of them."""
    return SPEC_REFS_HINT if "spec_refs" in lists else ""


def _check_shaping(cfg: Config, t: dict[str, Any], rel: str, shaped: set[int]) -> list[str]:
    """§19.6: with shape_adrs on, a pending task from the architect's adoption point on that cites an ADR needs the
    ADR's shaping record, or `shaping: waived — <reason>`."""
    a = cfg.architect
    if not config.architect_on(cfg) or not a["shape_adrs"] or t.get("status") != "pending":
        return []
    n, start = _number(t.get("task_id"), cfg), config.adoption_point(cfg)
    if n is None or start is None or n < start:
        return []
    waiver = str(t.get("shaping") or "")
    if waiver:
        return [] if WAIVER_RE.match(waiver) else \
            [f"{rel}: shaping {waiver!r}: a waiver reads `shaping: waived — <reason>`"]
    errs, named = [], set()
    for ref in _as_list(t.get("adr_refs")):
        n = adr_number(ref, cfg)
        if n is not None and n not in shaped and n not in named:
            named.add(n)
            errs.append(f"{rel}: cites {refs.ids(cfg).adr_id(n)} ({ref!r}), which has no shaping record "
                        f"({cfg.rel(cfg.reviews_dir)}/sh-*.md): run "
                        "`ccp architect run --mode shape --adr <id>` first, or add `shaping: waived — <reason>`")
    return errs


def _git(cfg: Config, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(cfg.root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _renames(cfg: Config) -> dict[str, tuple[str, str]]:
    """Task files git shows renamed within the task directory (`git log -M --diff-filter=R`): each old
    file stem to the new path and the commit, the newest rename of it first."""
    log = _git(cfg, "log", "-M", "--diff-filter=R", "--name-status", "--format=%x01%h",
               "--", cfg.rel(cfg.tasks_dir)) or ""
    out: dict[str, tuple[str, str]] = {}
    sha = ""
    for line in log.splitlines():
        if line.startswith("\x01"):
            sha = line[1:]
        elif line.startswith("R") and line.count("\t") == 2:
            _, old, new = line.split("\t")
            out.setdefault(Path(old).stem, (new, sha))
    return out


def missing_task_files(cfg: Config) -> list[str]:
    """Task files that are gone, and numbers reused. A task file is never deleted and its NNNN is
    never reused (SPEC §4); a task that is no longer wanted is `dropped`.

    A file is gone when an id in the committed INDEX.yaml (or, outside git, the one on disk), or a
    task file git history deleted, has no file now. Its NNNN then either has no file, or another
    file holds it. That file is the same task under an amended id (a new slug, §17.4) only when its
    frontmatter says so: `renamed_from: <old id>`. Any other file holding the number is a reused
    number. A deleted path that is not a task file name (`NNNN-kebab-slug.md`) is not a task.

    The message names the fix (§21.1): the restore command (`git checkout <sha>^ -- <path>` for a file a
    commit deleted, `git checkout HEAD -- <path>` for one deleted since HEAD), then `ccp tasks migrate`
    when the file's last committed text has no frontmatter (an earlier plane generation's). A file git
    shows renamed to the file now holding its number is told only to add `renamed_from`."""
    ids = refs.ids(cfg)
    holders: dict[str, tuple[str, list[str]]] = {}
    for f in cfg.tasks_dir.glob("*.md"):
        if m := ids.task_file_re.match(f.name):
            holders[m.group(1)] = (f.stem, _as_list(frontmatter(f.read_text()).get("renamed_from")))
    present = {tid for tid, _ in holders.values()}
    gone: dict[str, str] = {}
    deleted: dict[str, tuple[str, str]] = {}  # stem → (commit, path), the newest deletion
    committed = _git(cfg, "show", f"HEAD:./{cfg.rel(cfg.index_path)}")
    if committed is None and cfg.index_path.is_file():
        committed = cfg.index_path.read_text()
    for tid in INDEX_ID_RE.findall(committed or ""):
        if ids.task_file_re.match(f"{tid}.md") and tid not in present:
            gone.setdefault(tid, "listed in INDEX.yaml")
    log = _git(cfg, "log", "--no-renames", "--diff-filter=D", "--name-only", "--format=%x01%h",
               "--", cfg.rel(cfg.tasks_dir)) or ""
    sha = ""
    for line in log.splitlines():
        if line.startswith("\x01"):
            sha = line[1:]
        elif ids.task_file_re.match(Path(line).name) and Path(line).stem not in present:
            gone.setdefault(Path(line).stem, f"deleted in {sha}")
            deleted.setdefault(Path(line).stem, (sha, line))
    renames = _renames(cfg) if gone else {}
    out = []
    for tid, why in sorted(gone.items()):
        holder = holders.get(ids.task_number(tid))
        if holder is not None and tid in holder[1]:
            continue
        moved = renames.get(tid)
        if holder is not None and moved and Path(moved[0]).stem == holder[0]:
            out.append(f"{tid}: renamed to {moved[0]} in {moved[1]}: add `renamed_from: {tid}` to its frontmatter")
            continue
        fix = _restore(cfg, tid, deleted.get(tid))
        if holder is None:
            out.append(f"{tid}: its task file is gone ({why}). A task file is never deleted: {fix}")
        else:
            out.append(f"{tid}: its task file is gone ({why}) and its number now belongs to {holder[0]}. "
                       f"A number is never reused: {fix} Then give {holder[0]} the next free number; if "
                       f"{holder[0]} is {tid} under an amended id, its frontmatter says `renamed_from: {tid}`")
    return out


def _restore(cfg: Config, tid: str, deletion: tuple[str, str] | None) -> str:
    """What a gone task file's message tells the reader to do: the restore command, then what the
    restored file needs (§21.1)."""
    path = f"{cfg.rel(cfg.tasks_dir)}/{tid}.md"
    at_head = _git(cfg, "show", f"HEAD:./{path}")
    if at_head is not None:
        cmd, last = f"git checkout HEAD -- {path}", at_head
    elif deletion is not None:
        cmd, last = f"git checkout {deletion[0]}^ -- {deletion[1]}", _git(cfg, "show", f"{deletion[0]}^:{deletion[1]}")
    else:
        cmd, last = None, None
    head = f"restore it with `{cmd}`." if cmd else "restore it."
    if last is not None and not has_frontmatter(last):
        return f"{head} It is an earlier plane generation's task file: convert it with `ccp tasks migrate`."
    return f"{head} A done task stays `done`; only a task no longer wanted is `status: dropped`, with a note naming what replaced it."


def warnings(cfg: Config) -> list[str]:
    """What `check` reports without failing (§21.1); each warning is stated with its rule's §."""
    from ccp import adr  # noqa: PLC0415  (adr reads the task log)

    tasks = load(cfg)
    ids = refs.ids(cfg)
    later = {m.group(1): t.get("task_id") for t in tasks if (m := ids.task_file_re.match(t["_file"].name))}
    from ccp.config import config_warnings  # noqa: PLC0415
    out = config_warnings(cfg) + [f"{cfg.rel(t['_file'])}: status {t['_legacy_status']!r} is an in-flight state, which lives in the queue, "
           f"not the task file (§5): it reads as {t['status']!r}; write that"
           for t in tasks if t.get("_legacy_status")]
    for t in tasks:
        out += unmeasured_numbers(t, cfg.rel(t["_file"]))
        out += stale_context(cfg, t, cfg.rel(t["_file"]))
        out += unsigned_spec_edit(cfg, t, cfg.rel(t["_file"]))
        out += missing_adopt(t, cfg.rel(t["_file"]))
        out += hidden_step(t, cfg.rel(t["_file"]))
        own = _number(t.get("task_id"), cfg)
        if own is None or t.get("status") in TERMINAL:
            continue
        body = t["_text"].split("\n---\n", 1)[-1]
        for m in prose_dep_re(ids.task_width).finditer(body):
            if m.group(1) in later and int(m.group(1)) > own:
                out.append(f"{cfg.rel(t['_file'])}: {m.group(0)!r} names {later[m.group(1)]}, which has a higher number, "
                           "as a prerequisite in prose, where nothing enforces it. List it in depends_on, "
                           "which may name a higher number (SPEC §5)")
    return out + adr.unbuilt_cited(cfg, tasks)


def dependency_cycles(tasks: list[dict[str, Any]]) -> list[list[str]]:
    """§5: the cycles `depends_on` forms among the tasks, at least one through every set of tasks that
    wait on each other, each once, as the task ids along it from its lowest-numbered one (`[a, b]`: a
    depends on b, b on a; `[a]`: a depends on itself). A dependency on a missing id is not followed."""
    return graph.cycles({str(t.get("task_id")): [str(d) for d in _as_list(t.get("depends_on"))] for t in tasks})


def check(cfg: Config, texts: dict[Path, str] | None = None) -> list[str]:
    """Everything the structure promises, enforced. Returns the failures. `texts`: as `load`'s."""
    tl = cfg.task_log
    soft_re = re.compile(r"\b(" + "|".join(re.escape(w) for w in tl["soft_words"]) + r")\b", re.I) \
        if tl["soft_words"] else None
    errs: list[str] = []
    if not cfg.tasks_dir.is_dir():
        return [f"{cfg.rel(cfg.tasks_dir)}: missing — the task log lives here"]
    tasks = load(cfg, texts)
    shaped = shaped_adrs(cfg) if config.architect_on(cfg) and cfg.architect["shape_adrs"] else set()
    register, reg_errs = reviewpoints.load(cfg)  # §22: the review-point register, when the product keeps one
    errs += reg_errs
    seen: dict[str, str] = {}
    ids = {t.get("task_id") for t in tasks}
    for t in tasks:
        f: Path = t["_file"]
        rel = cfg.rel(f)
        m = refs.ids(cfg).task_file_re.match(f.name)
        if not m:
            errs.append(f"{rel}: filename must be NNNN-kebab-slug.md")
            continue
        nnnn = m.group(1)
        if nnnn in seen:
            errs.append(f"{rel}: NNNN {nnnn} already used by {seen[nnnn]} — never reuse")
        seen[nnnn] = f.name
        if not has_frontmatter(t["_text"]):  # §21.1: one failure, not one per key
            errs.append(f"{rel}: {NO_FRONTMATTER}")
            continue
        # Kinds are read with the architect seat on, for tasks from its adoption point; otherwise `kind:` is not (§19.11).
        judged = seat_reads(cfg, t)
        own_refs = judged and bool(((tl.get("kinds") or {}).get(kind_of(t)) or {}).get("refs_any"))
        for k in tl["required"]:
            # A kind with its own refs (a refactor) may leave out the ones it is not allowed to fill (§20).
            own = ((tl.get("kinds") or {}).get(kind_of(t)) or {}).get("refs_any") or []
            if k not in t and not (own_refs and k in tl["refs_any"] and k not in own):
                errs.append(f"{rel}: frontmatter is missing `{k}`")
        if "paths" in t:   # §5: an inline list of repo-relative paths or globs
            ps = t["paths"]
            if not isinstance(ps, list) or not ps:
                errs.append(f"{rel}: paths must be a non-empty inline list, e.g. paths: [src/a.py, docs/*.md]")
            else:
                bad = [p for p in ps if str(p).startswith("/") or ".." in str(p).split("/") or "," in str(p)]
                if bad:
                    errs.append(f"{rel}: paths must be relative to the repo, without '..': {', '.join(map(str, bad))}")
        if t.get("task_id") != f.stem:
            errs.append(f"{rel}: task_id {t.get('task_id')!r} does not match the filename")
        for k in RUNTIME_KEYS:
            if k in t:
                errs.append(f"{rel}: frontmatter carries `{k}`, which is runtime state (SPEC §4): "
                            "it lives in the queue, never in the task file")
        if t.get("status") not in STATUSES and t.get("status") not in LEGACY_STATUSES:
            errs.append(f"{rel}: status {t.get('status')!r} is not one of {', '.join(STATUSES)}")
        if "review_point" in t:  # §22, §22.4: set when scoping; `ccp tasks close` stamps it otherwise
            rp = t["review_point"]
            if register is None:  # no register: the rule before it, unchanged (§22)
                if not isinstance(rp, str) or not refs.ids(cfg).is_review_point(rp):
                    errs.append(f"{rel}: review_point {rp!r} does not match ids.review_point.pattern "
                                f"({refs.ids(cfg).review_point_pattern}, SPEC §22)")
            elif why := reviewpoints.problem(cfg, rp, register):
                errs.append(f"{rel}: {why}")
        errs += _id_list_errors(rel, t, "depends_on", ids)
        errs += _id_list_errors(rel, t, "clashes_with", ids, own=True)
        if not own_refs and tl["refs_any"] and not any(_as_list(t.get(k)) for k in tl["refs_any"]):
            errs.append(f"{rel}: cites none of {', '.join(tl['refs_any'])}" + _spec_hint(tl["refs_any"]))
        if judged:
            errs += _check_kind(cfg, t, rel)
            errs += _check_refactor_gate(cfg, t, rel)
        if why := sign_off_malformed(t):  # §3.5: brief, build or both
            errs.append(f"{rel}: {why}")
        if why := adopt_malformed(t):  # §5.2: one step, or none
            errs.append(f"{rel}: {why}")
        if "gate" in t and str(t.get("gate") or "").strip().lower() != "cold":
            errs.append(f"{rel}: gate {t.get('gate')!r} is not `cold`, the one value it takes (§15.3)")
        errs += _check_shaping(cfg, t, rel, shaped)
        errs += _check_placeholders(t, rel)
        for s in tl["sections"]:  # the canonical six by default; a product may require more
            if _section(t["_text"], s) is None:
                errs.append(f"{rel}: missing section `## {s}`")
        checks = t["_checks"]
        if not checks:
            errs.append(f"{rel}: no dod_checks — a task with nothing to verify is not a task")
        if len(checks) > tl["max_checks"]:
            errs.append(f"{rel}: {len(checks)} dod_checks — more than {tl['max_checks']} means this is "
                        "more than one task (WRITING-tasks.md)")
        if len(set(checks)) != len(checks):
            errs.append(f"{rel}: duplicate dod_check ids")
        errs += _check_runs_on(t, rel)
        if tl["dry_run"]:
            errs += _check_dry_runs(t, rel)
        if soft_re:
            # a dry run line quotes what a command printed, so its words are not the check's own (§21)
            for mm in soft_re.finditer(DRY_RUN_LINE_RE.sub("", _section(t["_text"], SEC_CHECKS) or "")):
                errs.append(f"{rel}: soft language {mm.group(0)!r} in a check — "
                            "if it cannot fail, it is not a check")
        if t.get("status") == "done":
            ver = _section(t["_text"], SEC_VERIFY) or ""
            if not re.search(r"^- ", ver, re.M):
                errs.append(f"{rel}: status is done with no verification notes")
    by_id = {str(t.get("task_id")): t for t in tasks}
    for cyc in dependency_cycles(tasks):
        errs.append(f"{cfg.rel(by_id[cyc[0]]['_file'])}: depends_on forms a cycle: {' → '.join(cyc + [cyc[0]])} "
                    "— no task in it can ever be ready")
    errs += missing_task_files(cfg)
    if not cfg.task_log.get("index", True):
        return errs  # SPEC §5.7: the product keeps no index
    idx = cfg.rel(cfg.index_path)
    if not cfg.index_path.exists():
        errs.append(f"{idx}: missing — run `ccp tasks index`")
    elif cfg.index_path.read_text() != render_index(cfg, tasks):
        errs.append(f"{idx}: stale — run `ccp tasks index`")
    return errs


def render_index(cfg: Config, tasks: list[dict[str, Any]] | None = None) -> str:
    """INDEX.yaml. Its format is frozen (SPEC §5.7): these five fields per task, nothing added.
    New task fields go to the board (`board.json`, §28.3)."""
    tasks = tasks if tasks is not None else load(cfg)
    # No generated-on date: it would make the index "stale" every midnight and force a rewrite
    # that changes nothing. Git records when it was written.
    lines = ["# Generated by `ccp tasks index` — do not hand-edit.",
             "# One task per file under tasks/. Never delete, never renumber.",
             f"project_id: {cfg.project_id}",
             "tasks:"]
    for t in tasks:
        lines += [f"  - id: {t.get('task_id')}",
                  f"    status: {t.get('status')}",
                  f"    title: {t.get('title')}",
                  f"    depends_on: [{', '.join(_as_list(t.get('depends_on')))}]",
                  f"    path: tasks/{t['_file'].name}"]
    return "\n".join(lines) + "\n"


def write_index(cfg: Config) -> str:
    """Write INDEX.yaml, or nothing when the product keeps none (SPEC §5.7)."""
    if not cfg.task_log.get("index", True):
        return "(no index: task_log.index is false)"
    cfg.index_path.write_text(render_index(cfg))
    return cfg.rel(cfg.index_path)


def in_scope(tid: str, scope: list[str] | None) -> bool:
    """A scope entry names a whole task id or its NNNN; no scope means every task."""
    return not scope or any(tid == s or tid.split("-", 1)[0] == s for s in scope)


def done_order(cfg: Config, tasks: list[dict[str, Any]] | None = None) -> list[str]:
    """Every `done` task, in the order its file's status became `done` in git history (one
    `git log -G` over the task directory). Tasks done only in the working tree, or outside git,
    come last in NNNN order."""
    tasks = tasks if tasks is not None else load(cfg)
    done = {t.get("task_id") for t in tasks if t.get("status") == "done"}
    order: list[str] = []
    r = subprocess.run(["git", "-C", str(cfg.root), "log", "--reverse", "--format=%x01%H", "-p", "-U0",
                        "--no-color", "--no-ext-diff", "-G^status:", "--", cfg.rel(cfg.tasks_dir)],
                       capture_output=True, text=True)
    if r.returncode == 0:
        per_file: dict[str, list[bool]] = {}

        def flush() -> None:
            for tid, (minus, plus) in per_file.items():
                if plus and not minus and tid not in order:
                    order.append(tid)
                elif minus and not plus and tid in order:
                    order.remove(tid)  # reopened: it re-enters when it is done again
            per_file.clear()

        cur = None
        for line in r.stdout.splitlines():
            if line.startswith("\x01"):
                flush()
            elif line.startswith("+++ "):
                cur = Path(line[6:]).stem if line.startswith("+++ b/") else None
            elif cur and (line.startswith("+status:") or line.startswith("-status:")):
                if _strip_comment(line[8:].strip()).strip("'\"") == "done":
                    per_file.setdefault(cur, [False, False])[0 if line[0] == "-" else 1] = True
        flush()
    order = [t for t in order if t in done]
    return order + sorted(done - set(order))


def features_since_refactor(cfg: Config, tasks: list[dict[str, Any]]) -> int:
    """Feature tasks merged since the last refactor merged (all of them, if none has)."""
    kinds = {t.get("task_id"): "refactor" if lane_refactor(cfg, t) else "feature" for t in tasks}
    n = 0
    for tid in done_order(cfg, tasks):
        n = 0 if kinds.get(tid) == "refactor" else n + 1
    return n


def scope_deps(tasks: list[dict[str, Any]], scope: list[str] | None) -> dict[str, str]:
    """Every task an open (not done, not dropped) task in the scope depends on, directly or
    transitively, outside the scope, mapped to the scope task that needs it (the lowest NNNN). The
    walk stops at a dropped task: a dropped dependency never makes its own dependencies needed."""
    dropped = {str(t.get("task_id")) for t in tasks if t.get("status") == "dropped"}
    deps = {str(t.get("task_id")): [d for d in map(str, _as_list(t.get("depends_on")))
                                    if d not in dropped and not in_scope(d, scope)]
            for t in tasks}
    need: dict[str, str] = {}
    for t in tasks:
        tid = str(t.get("task_id"))
        if scope and in_scope(tid, scope) and t.get("status") not in ("done", "dropped"):
            for d in graph.closure(deps, tid):
                need.setdefault(d, tid)
    return need


def refactor_reach(cfg: Config, tasks: list[dict[str, Any]], scope: list[str] | None) -> dict[str, str]:
    """§20: the refactors outside the scope that `next` widens it to, each with the reason:
    every refactor under `refactor_in_scope: true`, the ones a scope task depends on under "deps",
    none under false or unless the seat is adopted."""
    a = cfg.architect
    mode = a["refactor_in_scope"] if config.architect_adopted(cfg) else False
    if not scope or mode is False:
        return {}
    need = scope_deps(tasks, scope) if mode == "deps" else {}
    return {str(t.get("task_id")): need.get(str(t.get("task_id")), "")
            for t in tasks if lane_refactor(cfg, t) and not in_scope(str(t.get("task_id")), scope)
            and (mode is True or str(t.get("task_id")) in need)}


def waiting_refactors(cfg: Config, scope: list[str] | None,
                      tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """§20.4: outstanding (pending, ready or not) refactors that the scope neither names nor reaches,
    in task order. Under "deps" these go to the top of the next review point's scope (§10.2)."""
    if not config.architect_adopted(cfg) or not scope:
        return []
    tasks = tasks if tasks is not None else load(cfg)
    reach = refactor_reach(cfg, tasks, scope)
    return [t for t in tasks if lane_refactor(cfg, t) and t.get("status") == "pending"
            and not in_scope(str(t.get("task_id")), scope) and str(t.get("task_id")) not in reach]


def preferred(cfg: Config, tid: str, scope: list[str] | None,
              tasks: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any] | None, str]:
    """§10.4: one entry of the lead's preference list (work.json `next_tasks`, `ccp tasks prefer`), and its state:
    "ready" (pending, every dependency done, in the scope or reached by it), "waiting on <ids>",
    or why it is ignored ("unknown", "done", "dropped", "<status>", "out of scope")."""
    tasks = tasks if tasks is not None else load(cfg)
    t = next((x for x in tasks if str(x.get("task_id")) == tid or x["_file"].stem == tid), None)
    if t is None:
        return None, "unknown"
    if t.get("status") != "pending":
        return t, str(t.get("status") or "no status")
    if not in_scope(tid, scope) and tid not in refactor_reach(cfg, tasks, scope):
        return t, "out of scope"
    done = {x.get("task_id") for x in tasks if x.get("status") == "done"}
    waits = [d for d in _as_list(t.get("depends_on")) if d not in done]
    return t, ("waiting on " + ", ".join(waits)) if waits else "ready"


def ranked(cfg: Config, scope: list[str] | None = None, first: list[str] | None = None,
           prefer: list[tuple[dict[str, Any], str]] | None = None,
           tasks: list[dict[str, Any]] | None = None,
           review_point: str | None = None, since: int | None = None) -> list[tuple[dict[str, Any], str]]:
    """The one selection `ccp tasks next` and the board share (§10.3, §20.3): every ready task, each
    with why it comes where it does, in the order `next` would return them if each merged in turn
    and nothing else became ready. Row 0 is `next`'s pick now.

    Ready: pending, every dependency done (dependencies need not be in scope), in the scope or
    reached by it (`refactor_reach`: all refactors under `refactor_in_scope: true`, the ones a scope
    task depends on under "deps"). The order: `prefer` (the lead's preference list, each with its why:
    the ready ones, in the lead's order); then `first` (work.json's `review_point_refactors`), lowest NNNN first; then a
    ready refactor whenever `refactor_every` features have merged since the last refactor; then
    lowest NNNN.

    A task never comes before one of its dependencies, whatever their numbers (§5, §10.3): a task is
    ranked only once every dependency is done, so no ready task waits on another, and the number only
    breaks ties among tasks the graph leaves free. Replaying it, each pick merged in turn, gives the run
    order (the forecast's)."""
    tasks = tasks if tasks is not None else load(cfg)
    done = {t.get("task_id") for t in tasks if t.get("status") == "done"}
    a = cfg.architect
    reach = refactor_reach(cfg, tasks, scope)
    ready = sorted((t for t in tasks
                    if (in_scope(str(t.get("task_id")), scope) or str(t.get("task_id")) in reach)
                    and t.get("status") == "pending" and all(d in done for d in _as_list(t.get("depends_on")))),
                   key=lambda t: str(t.get("task_id")))  # the number, whatever order the caller's list is in
    out: list[tuple[dict[str, Any], str]] = []
    for p in prefer or []:
        if p[0] in ready:
            ready.remove(p[0])
            out.append(p)
    every = a["refactor_every"] if config.architect_adopted(cfg) else 0
    # git's count is only needed when a ready refactor could jump the queue (it is one `git log`)
    since = (since if since is not None else features_since_refactor(cfg, tasks)) \
        if every and any(lane_refactor(cfg, t) for t in ready) else 0
    for p, _ in out:
        since = 0 if lane_refactor(cfg, p) else since + 1
    while ready:
        firsts = [t for t in ready if str(t.get("task_id")) in (first or [])]
        refactors = [t for t in ready if lane_refactor(cfg, t)]
        if firsts:
            pick = firsts[0]
            why = (f"a refactor waiting from an earlier cycle, taken first at review point {review_point or '?'} "
                   "(work.json review_point_refactors, SPEC §20)")
        elif every and refactors and ready[0] is not refactors[0] and since >= every:
            pick, why = refactors[0], f"a refactor, due after {every} feature merge{'' if every == 1 else 's'} since the last (SPEC §20)"
        else:
            pick = ready[0]
            tid = str(pick.get("task_id"))
            need = reach.get(tid) if scope and not in_scope(tid, scope) else None
            why = (f"outside the given scope: a refactor that in-scope task {need} depends on "
                   '(plane.json architect.refactor_in_scope: "deps", SPEC §20.4)' if need else
                   "outside the given scope: a refactor, and refactors belong to every scope "
                   "(plane.json architect.refactor_in_scope: true, SPEC §20.4)"
                   if scope and not in_scope(tid, scope) else "")
        ready.remove(pick)
        since = 0 if lane_refactor(cfg, pick) else since + 1
        out.append((pick, why))
    return out


def next_task(cfg: Config, scope: list[str] | None = None,
              first: list[str] | None = None) -> dict[str, Any] | None:
    """`ranked`'s first row without a preference: what `ccp tasks next` picks by the plane's own order."""
    r = ranked(cfg, scope, first)
    return r[0][0] if r else None


def task_numbers(cfg: Config) -> frozenset[str]:
    """The numbers of the tasks in the task log (its `NNNN-slug.md` files), as written (`0042`)."""
    ids = refs.ids(cfg)
    if not cfg.tasks_dir.is_dir():
        return frozenset()
    return frozenset(m.group(1) for f in cfg.tasks_dir.glob("*.md") if (m := ids.task_file_re.match(f.name)))


def next_number(cfg: Config) -> str:
    """The next free NNNN, for a seat or tool filing a new task."""
    ids = refs.ids(cfg)
    nums = [int(m.group(1)) for f in cfg.tasks_dir.glob("*.md") if (m := ids.task_file_re.match(f.name))]
    return ids.format_task_number(max(nums, default=0) + 1)
