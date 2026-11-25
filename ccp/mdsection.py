"""The one fence-aware finder of a Markdown section under a heading (house rule E22): a task file's (SPEC §5),
a worker report's (§13.4), a SPEC section (§7.2, §26.3), an ADR decision (§6.3). A `#` line inside a fenced
block is quoted text: it neither starts nor ends a section."""
from __future__ import annotations

import re

# A fence closes on a line of only its own character, at least as many as opened it; a code span
# stays on one line, so one stray backtick cannot quote the lines after it. A tilde fence's info string
# may hold any text, a backtick fence's no backtick: a line that starts with a three-backtick code span
# is prose, no opener.
FENCE_RE = re.compile(r"^[ \t]*(?P<f>(?P<c>[`~])(?P=c){2,})(?:(?<=~)[^\n]*|[^`\n]*)\n.*?^[ \t]*(?P=f)(?P=c)*[ \t]*$",
                      re.M | re.S)


def blank(m: re.Match[str]) -> str:
    """The matched text as spaces, its line breaks kept, so line numbers still count."""
    return re.sub(r"[^\n]", " ", m.group(0))


def unfence(text: str) -> str:
    """`text` with each fenced block blanked (`blank`): the same length and line breaks, so an offset in it is one
    in `text`. A `#` line inside a fence is quoted text, no heading: headings are found here."""
    return FENCE_RE.sub(blank, text)


def _ends(level: int) -> re.Pattern[str]:
    """A heading line of `level` or higher: one to `level` `#`, then a blank or the line's end."""
    return re.compile(rf"^#{{1,{level}}}(?:[ \t]|\r?$)", re.M)


def section_end(unfenced: str, at: int, level: int) -> int:
    """Where a section of heading `level` whose body starts at offset `at` ends: the next heading of its level or
    higher, else the text's end. `unfenced` is the text as `unfence` gives it."""
    nxt = _ends(level).search(unfenced, at)
    return nxt.start() if nxt else len(unfenced)


def heading_span(text: str, pattern: str, level: int | None = None) -> tuple[int, int, int] | None:
    """Where the section under the first heading outside a fenced block whose text matches `pattern` (at `level`
    `#`, or any level) lies in `text`: the offsets of its heading line's start, of the end of `pattern`'s match and
    of the section's end (`section_end`); None when no heading matches."""
    unfenced = unfence(text)
    hashes = "#+" if level is None else f"#{{{level}}}"
    m = re.search(rf"^(?P<mdsection_hashes>{hashes})[ \t]+(?:{pattern})", unfenced, re.M)
    if not m:
        return None
    return m.start(), m.end(), section_end(unfenced, m.end(), len(m.group("mdsection_hashes")))


def heading_block(text: str, pattern: str, level: int | None = None) -> str | None:
    """The block from the first heading outside a fenced block whose text matches `pattern` (at `level`, or any
    level), up to the next heading outside a fenced block of its level or higher; None when no heading matches."""
    span = heading_span(text, pattern, level)
    return text[span[0]:span[2]] if span else None

