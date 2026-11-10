"""References and ids, parsed and formatted in one place (SPEC §7).

Every id the plane reads or writes in a product's docs goes through an `Ids`: task ids (`NNNN-slug`),
ADR ids and refs (`ADR-NNNN`, `NNNN D2`), SPEC section refs (`S12`, `S3–S5`), house-rule ids (`E7`)
and review-point ids (`R3`), and the delivery ids the package-doc check keeps out of docs and comments
(tasks, architect findings, spec-question rulings, §21.3). The patterns come from plane.json's optional `ids` block; the defaults
are the conventions the plane has always used, so a product without the block sees no change.

`ids(cfg)` gives the product's `Ids`; `DEFAULT` serves code that has no config (it is the defaults).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from typing import Any

IDS_DEFAULTS: dict[str, Any] = {
    "task": {"width": 4},
    "adr": {"prefix": "ADR-", "width": 4},
    "spec": {"prefix": "S"},
    "rule": {"pattern": "E[0-9]+"},
    "review_point": {"pattern": "R[1-9][0-9]*"},
}

SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"
# A task id in a run id or a queue file, whatever the product's width: the task log enforces the width.
ANY_TASK_ID = rf"[0-9]+-{SLUG}"
# Ids the plane mints for its own records, a UTC stamp and four hex digits: an architect or shaping
# pass (`ar-…`, `sh-…`), with `#F<n>` naming one of its findings, and a spec question (`sm-…`), whose
# answer is a ruling.
STAMP_ID = r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{4}"
REVIEW_ID = rf"(?:ar|sh)-{STAMP_ID}(?:#F[0-9]+)?"
QUESTION_ID = rf"sm-{STAMP_ID}"


@dataclass(frozen=True)
class AdrRef:
    """One ADR reference: `0031 D2` → number 31, decision `2`; `0028 Acceptance tests arms-12` →
    number 28, section `Acceptance tests arms-12`; `ADR-0007` → number 7."""
    number: int
    decision: str | None = None
    section: str | None = None
    raw: str = ""


@dataclass(frozen=True)
class Ids:
    task_width: int = 4
    adr_prefix: str = "ADR-"
    adr_width: int = 4
    spec_prefix: str = "S"
    rule_pattern: str = "E[0-9]+"
    review_point_pattern: str = "R[1-9][0-9]*"

    # ------------------------------------------------------------------ tasks

    @cached_property
    def task_file_re(self) -> re.Pattern[str]:
        """A task file name, `NNNN-slug.md`: group 1 the number, group 2 the slug."""
        return re.compile(rf"^(\d{{{self.task_width}}})-({SLUG})\.md$")

    @cached_property
    def task_id_re(self) -> re.Pattern[str]:
        return re.compile(rf"^\d{{{self.task_width}}}-{SLUG}$")

    @cached_property
    def task_number_re(self) -> re.Pattern[str]:
        """A task number at the start of a string (`0042`, `0042-slug`), not followed by another digit."""
        return re.compile(rf"^(\d{{{self.task_width}}})(?!\d)")

    def task_number(self, tid: Any) -> str:
        """The number part of a task id or file name (`0042-x` → `0042`); a string too short to hold one
        gives its own first characters, as the old `tid[:4]` did."""
        return str(tid or "")[: self.task_width]

    def format_task_number(self, n: int) -> str:
        return f"{n:0{self.task_width}d}"

    def same_task(self, a: Any, b: Any) -> bool:
        """Whether `b` names task `a`: the whole id, or its number."""
        a, b = str(a or ""), str(b or "")
        return a == b or (len(b) == self.task_width and b.isdigit() and self.task_number(a) == b)

    def task_mention_patterns(self, numbers: Iterable[str]) -> tuple[str, ...]:
        """A task named in prose or code, matched only when its number is one of `numbers` (the task
        log's, at the product's width), so a year, a file mode or a migration's name is not a task:
        its id (number, `-`, slug), not followed by a file extension; its zero-padded number standing
        alone (a sentence's full stop may follow it, a decimal's digits may not); or `task <n>`,
        `task #<n>` or `Task: <n>`, padded or not. No numbers, no patterns."""
        w = self.task_width
        nums = sorted({n for n in numbers if re.fullmatch(rf"\d{{{w}}}", n)}, reverse=True)
        if not nums:
            return ()
        padded = [n for n in nums if n.startswith("0")]
        short = sorted({str(int(n)) for n in nums}, key=lambda n: (-len(n), n))
        pats = [rf"(?<![\w-])(?:{'|'.join(nums)})-[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?![\w-]|\.\w)"]
        if padded:
            pats.append(rf"(?<![\w.-])(?:{'|'.join(padded)})(?![\w-]|\.\w)")
        pats.append(rf"(?i:\btask:?\s+#?)(?=\d{{1,{w}}}\b)0*(?:{'|'.join(short)})\b")
        return tuple(pats)

    def delivery_id_patterns(self, numbers: Iterable[str]) -> tuple[str, ...]:
        """The delivery ids the plane knows: a task in the log (`task_mention_patterns`), and always an
        architect finding or pass (`REVIEW_ID`) and a spec question's ruling (`QUESTION_ID`)."""
        return (*self.task_mention_patterns(numbers), rf"(?<![\w-]){REVIEW_ID}(?![\w-])",
                rf"(?<![\w-]){QUESTION_ID}(?![\w-])")

    def family(self, tid: Any) -> str:
        """A task's family, the slug's first token (`0042-sf-store` → `sf`), or empty."""
        parts = str(tid).split("-")
        return parts[1] if len(parts) > 1 else ""

    # ------------------------------------------------------------------ ADRs

    def adr_id(self, n: int) -> str:
        return f"{self.adr_prefix}{n:0{self.adr_width}d}"

    def adr_globs(self, n: int) -> tuple[str, ...]:
        """File-name globs for ADR `n`: `NNNN-*.md`, `<prefix>NNNN*.md`, `NNNN.md`."""
        num = f"{n:0{self.adr_width}d}"
        return (f"{num}-*.md", f"{self.adr_prefix}{num}*.md", f"{num}.md")

    @cached_property
    def adr_file_re(self) -> re.Pattern[str]:
        """An ADR file name, `NNNN-slug.md` or `<prefix>NNNN-slug.md`: group 1 the number."""
        return re.compile(rf"^(?:{re.escape(self.adr_prefix)})?(\d{{{self.adr_width}}})-[^/]+\.md$")

    @cached_property
    def _adr_ref_re(self) -> re.Pattern[str]:
        p = re.escape(self.adr_prefix.rstrip("-"))
        return re.compile(rf"^\s*(?:{p}[- ]?)?0*(\d{{1,{self.adr_width}}})\b(?![-/.]\d)|\badr/(?:{p}-)?0*(\d+)", re.I)

    @cached_property
    def _adr_num_re(self) -> re.Pattern[str]:
        return re.compile(r"(\d+)")

    def adr_number(self, ref: Any) -> int | None:
        """The ADR number a ref cites: it opens with `[ADR-]NNNN`, or names `adr/NNNN-…`. A task id or
        a date (`0031-x`, `2026-10-01`) is not an ADR ref."""
        m = self._adr_ref_re.search(str(ref or ""))
        return int(m.group(1) or m.group(2)) if m else None

    def parse_adr_ref(self, ref: Any) -> AdrRef | None:
        """A structured ADR ref: number, decision (`D2`, `D2a` → `2`, `2a`) and any other trailing text
        as a section anchor."""
        raw = str(ref or "")
        n = self.adr_number(raw)
        if n is None:
            return None
        d = re.search(r"\bD(\d+[a-z]?)\b", raw)
        rest = re.sub(rf"^\s*(?:{re.escape(self.adr_prefix.rstrip('-'))}[- ]?)?0*\d+\s*", "", raw, flags=re.I).strip()
        section = None if d or not rest or rest.startswith("adr/") else rest
        return AdrRef(n, d.group(1) if d else None, section, raw)

    @cached_property
    def adr_mention_re(self) -> re.Pattern[str]:
        """An ADR named in prose, `ADR-0031` / `ADR 31` (group 1 the number); a bare number never counts."""
        return re.compile(rf"\b{re.escape(self.adr_prefix.rstrip('-'))}[- ]?0*(\d+)\b", re.I)

    def adr_canonical(self, arg: Any) -> str:
        """`ADR-0031`, `0031` or `31` → `ADR-0031`; anything without a number is kept as given."""
        m = self._adr_num_re.search(str(arg or ""))
        return self.adr_id(int(m.group(1))) if m else str(arg)

    # ------------------------------------------------------------------ SPEC refs

    @cached_property
    def spec_ref_re(self) -> re.Pattern[str]:
        """A SPEC section ref or range: `S12`, `S3–S5`, `S3 to S5` (groups: first, last)."""
        p = re.escape(self.spec_prefix)
        return re.compile(rf"\b{p}(\d{{1,3}})(?:\s*(?:–|—|-|to)\s*{p}(\d{{1,3}}))?\b")

    def spec_ref(self, n: int) -> str:
        return f"{self.spec_prefix}{n}"

    # ------------------------------------------------------------------ house rules and review points

    @cached_property
    def rule_id_re(self) -> re.Pattern[str]:
        return re.compile(rf"^(?:{self.rule_pattern})$")

    def is_rule_id(self, s: Any) -> bool:
        return bool(self.rule_id_re.match(str(s or "")))

    @property
    def rule_shape(self) -> str:
        """How messages name a house-rule id: `E<n>` by default, else the product's pattern."""
        return "E<n>" if self.rule_pattern == IDS_DEFAULTS["rule"]["pattern"] else self.rule_pattern

    @property
    def review_point_shape(self) -> str:
        """How messages name a review-point id: `R<number> (R1, R2, …` by default, else the pattern."""
        return ("R<number> (R1, R2, …" if self.review_point_pattern == IDS_DEFAULTS["review_point"]["pattern"]
                else f"a review-point id ({self.review_point_pattern}")

    @cached_property
    def review_point_re(self) -> re.Pattern[str]:
        return re.compile(rf"^(?:{self.review_point_pattern})$")

    def is_review_point(self, s: Any) -> bool:
        return bool(self.review_point_re.match(str(s or "")))

    def review_point_number(self, rp: Any) -> int | None:
        """A review point's order number (`R12` → 12): its first run of digits."""
        if not self.is_review_point(rp):
            return None
        m = re.search(r"\d+", str(rp))
        return int(m.group(0)) if m else None


DEFAULT = Ids()


def number_prefix(s: Any) -> str:
    """The leading digits of an id (`0042-x` → `0042`), whatever the width; empty when there are none."""
    m = re.match(r"\d+", str(s or ""))
    return m.group(0) if m else ""


def from_config(given: dict[str, Any] | None) -> Ids:
    """An `Ids` from a validated `ids` block (missing keys take the defaults)."""
    if not given:
        return DEFAULT
    g = given
    t, a, s = g.get("task") or {}, g.get("adr") or {}, g.get("spec") or {}
    r, rp = g.get("rule") or {}, g.get("review_point") or {}
    d = IDS_DEFAULTS
    got = Ids(task_width=int(t.get("width", d["task"]["width"])),
               adr_prefix=str(a.get("prefix", d["adr"]["prefix"])),
               adr_width=int(a.get("width", d["adr"]["width"])),
               spec_prefix=str(s.get("prefix", d["spec"]["prefix"])),
               rule_pattern=str(r.get("pattern", d["rule"]["pattern"])),
               review_point_pattern=str(rp.get("pattern", d["review_point"]["pattern"])))
    return DEFAULT if got == DEFAULT else got


def validate(given: Any) -> list[str]:
    """Problems with an `ids` block, empty when it is usable (or absent)."""
    if given is None:
        return []
    if not isinstance(given, dict):
        return ["ids must be an object"]
    bad = []
    unknown = sorted(set(given) - set(IDS_DEFAULTS))
    if unknown:
        bad.append(f"ids: unknown key(s) {', '.join(unknown)}")
    for key, keys in (("task", {"width"}), ("adr", {"prefix", "width"}), ("spec", {"prefix"}),
                      ("rule", {"pattern"}), ("review_point", {"pattern"})):
        v = given.get(key)
        if v is None:
            continue
        if not isinstance(v, dict) or set(v) - keys:
            bad.append(f"ids.{key} takes only {', '.join(sorted(keys))}")
            continue
        w = v.get("width")
        if w is not None and (isinstance(w, bool) or not isinstance(w, int) or not 1 <= w <= 9):
            bad.append(f"ids.{key}.width must be an integer from 1 to 9")
        pre = v.get("prefix")
        if pre is not None and not (isinstance(pre, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,15}", pre)):
            bad.append(f"ids.{key}.prefix must be letters, digits, '_' or '-', starting with a letter")
        elif key == "adr" and isinstance(pre, str) and re.fullmatch(r"[Dd]-?", pre):
            bad.append("ids.adr.prefix must not be 'D' or 'D-': it would read a decision ref (D2) as an ADR")
        pat = v.get("pattern")
        if pat is not None:
            try:
                if not isinstance(pat, str) or not pat:
                    raise re.error("it must be a non-empty string")
                re.compile(pat)
            except re.error as e:
                bad.append(f"ids.{key}.pattern is not a regular expression ({e})")
    return bad


def ids(cfg: Any) -> Ids:
    """The product's `Ids` (its plane.json `ids` block), or the defaults for a config without one."""
    got = getattr(cfg, "ids", None)
    return got if isinstance(got, Ids) else DEFAULT
