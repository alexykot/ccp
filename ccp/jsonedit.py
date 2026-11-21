"""Edit one member of a JSON object in its text, keeping every other byte (SPEC §29.3).

The commands that record into a product's plane.json (`ccp upgrade take` and `decline`) change one entry
and nothing else: the file's own layout (compact lists, inline objects, its indent) stays as the product
wrote it, so the diff is the entry alone.

  set_member(text, path, key, value)   in the object at `path` (keys from the top), set `key` to `value`
  delete_member(text, path, key)       remove `key` and its separating comma from the object at `path`

A scanner reads the text (strings with their escapes, numbers, literals, nested objects and arrays,
whitespace) and records each object member's key span and value span. An edit splices only those spans:
- an existing member's value span is replaced by `json.dumps(value, ensure_ascii=False)`;
- a new member goes after the object's last member, on a line of its own indented and broken like that
  member's when the member sits on its own line, else inline as `, "key": value`; into an empty object as
  `"key": value`;
- a missing object on `path` is made the same way, holding the rest of the path inline (`{"key": value}`);
- a deleted member takes its separating comma with it (the one after it, or before it when it is the
  last member); deleting the only member leaves `{}`. A key that is not there, or a path that does not
  lead to an object, leaves the text unchanged.
After each edit, `json.loads` of the result must equal the same edit made on the loaded data; otherwise
the function raises ValueError, as it does for text that is not a JSON object, and the caller writes
nothing. Standard library only.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_WS = " \t\n\r"
_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_LITERALS = ("true", "false", "null")


@dataclass
class _Node:
    """A scanned value: its span in the text, and for an object its members in order."""
    start: int
    end: int
    kind: str  # "object", "array" or "scalar"
    members: list = field(default_factory=list)


@dataclass
class _Member:
    key: str
    key_start: int
    key_end: int
    value: _Node


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text

    def _ws(self, i: int) -> int:
        while i < len(self.text) and self.text[i] in _WS:
            i += 1
        return i

    def _fail(self, i: int, what: str) -> ValueError:
        return ValueError(f"not JSON at character {i}: {what}")

    def _string(self, i: int) -> int:
        """The end of the string starting at `i` (its opening quote), past the closing quote."""
        j = i + 1
        while j < len(self.text):
            c = self.text[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                return j + 1
            if c < " ":
                raise self._fail(j, "a control character in a string")
            j += 1
        raise self._fail(i, "an unterminated string")

    def value(self, i: int) -> _Node:
        i = self._ws(i)
        if i >= len(self.text):
            raise self._fail(i, "a value is missing")
        c = self.text[i]
        if c == "{":
            return self._object(i)
        if c == "[":
            return self._array(i)
        if c == '"':
            return _Node(i, self._string(i), "scalar")
        for lit in _LITERALS:
            if self.text.startswith(lit, i):
                return _Node(i, i + len(lit), "scalar")
        m = _NUMBER.match(self.text, i)
        if m:
            return _Node(i, m.end(), "scalar")
        raise self._fail(i, f"unexpected {c!r}")

    def _object(self, i: int) -> _Node:
        node = _Node(i, i, "object")
        j = self._ws(i + 1)
        if j < len(self.text) and self.text[j] == "}":
            node.end = j + 1
            return node
        while True:
            if j >= len(self.text) or self.text[j] != '"':
                raise self._fail(j, "an object key is missing")
            key_end = self._string(j)
            key = json.loads(self.text[j:key_end])
            colon = self._ws(key_end)
            if colon >= len(self.text) or self.text[colon] != ":":
                raise self._fail(colon, "':' is missing")
            val = self.value(colon + 1)
            node.members.append(_Member(key, j, key_end, val))
            j = self._ws(val.end)
            if j < len(self.text) and self.text[j] == ",":
                j = self._ws(j + 1)
                continue
            if j < len(self.text) and self.text[j] == "}":
                node.end = j + 1
                return node
            raise self._fail(j, "',' or '}' is missing")

    def _array(self, i: int) -> _Node:
        j = self._ws(i + 1)
        if j < len(self.text) and self.text[j] == "]":
            return _Node(i, j + 1, "array")
        while True:
            j = self._ws(self.value(j).end)
            if j < len(self.text) and self.text[j] == ",":
                j += 1
                continue
            if j < len(self.text) and self.text[j] == "]":
                return _Node(i, j + 1, "array")
            raise self._fail(j, "',' or ']' is missing")


def _scan(text: str) -> _Node:
    """The text's top-level object, scanned; ValueError when the text is not one JSON object."""
    s = _Scanner(text)
    root = s.value(0)
    tail = s._ws(root.end)  # noqa: SLF001
    if tail != len(text):
        raise s._fail(tail, "text after the top-level value")  # noqa: SLF001
    if root.kind != "object":
        raise ValueError("the top-level value is not an object")
    return root


def _member(obj: _Node, key: str) -> Optional[_Member]:
    """The member `key` of `obj` as json.loads reads it: the last one of that name."""
    hits = [m for m in obj.members if m.key == key]
    return hits[-1] if hits else None


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _insert(text: str, obj: _Node, key: str, value: Any) -> str:
    """`text` with a new member `key: value` after `obj`'s last member (or in it, when it is empty)."""
    pair = f"{_dumps(key)}: {_dumps(value)}"
    if not obj.members:
        return text[:obj.start + 1] + pair + text[obj.start + 1:]
    last = obj.members[-1]
    line_start = text.rfind("\n", obj.start, last.key_start) + 1
    indent = text[line_start:last.key_start]
    if line_start and not indent.strip(_WS):  # the last member sits on its own line, broken as that line is
        sep = (",\r\n" if text[line_start - 2:line_start] == "\r\n" else ",\n") + indent
    else:
        sep = ", "
    return text[:last.value.end] + sep + pair + text[last.value.end:]


def _set_text(text: str, path: list[str], key: str, value: Any) -> str:
    obj = _scan(text)
    for i, part in enumerate(path):
        m = _member(obj, part)
        if m is None:
            return _insert(text, obj, part, _nested(path[i + 1:], key, value))
        if m.value.kind != "object":
            raise ValueError(f"`{'.'.join(path[:i + 1])}` is not an object")
        obj = m.value
    m = _member(obj, key)
    if m is None:
        return _insert(text, obj, key, value)
    return text[:m.value.start] + _dumps(value) + text[m.value.end:]


def _nested(rest: list[str], key: str, value: Any) -> Any:
    """The value a missing object on the path is made with: `{rest[0]: {...: {key: value}}}`."""
    out: Any = {key: value}
    for k in reversed(rest):
        out = {k: out}
    return out


def _delete_text(text: str, path: list[str], key: str) -> str:
    obj = _scan(text)
    for part in path:
        m = _member(obj, part)
        if m is None or m.value.kind != "object":
            return text
        obj = m.value
    for i in reversed(range(len(obj.members))):  # every member of that name: json.loads reads the last
        if obj.members[i].key != key:
            continue
        text = _drop(text, obj, i)
        obj = _scan_at(text, path)
    return text


def _scan_at(text: str, path: list[str]) -> _Node:
    obj = _scan(text)
    for part in path:
        m = _member(obj, part)
        assert m is not None  # the path was there before the member was dropped
        obj = m.value
    return obj


def _drop(text: str, obj: _Node, i: int) -> str:
    """`text` without `obj`'s member `i` and its separating comma."""
    ms = obj.members
    if len(ms) == 1:
        return text[:obj.start + 1] + text[obj.end - 1:]
    if i + 1 < len(ms):  # the member, its comma and the space up to the next member's key
        return text[:ms[i].key_start] + text[ms[i + 1].key_start:]
    return text[:ms[i - 1].value.end] + text[ms[i].value.end:]  # the last: the comma before it and the member


def _walk(data: Any, path: list[str], make: bool) -> Optional[dict]:
    for part in path:
        if not isinstance(data, dict):
            return None
        if part not in data:
            if not make:
                return None
            data[part] = {}
        data = data[part]
    return data if isinstance(data, dict) else None


def _checked(after: str, expected: Any) -> str:
    try:
        got = json.loads(after)
    except ValueError as e:
        raise ValueError(f"the edited text is not JSON ({e})") from None
    if got != expected:
        raise ValueError("the edited text does not read as the edit made on the loaded data")
    return after


def set_member(text: str, path: list[str], key: str, value: Any) -> str:
    """`text` with `key` set to `value` in the object at `path`, every other byte kept; ValueError when the
    text is not a JSON object, an object on `path` is not one, or the result does not read as the edit."""
    after = _set_text(text, path, key, value)
    expected = copy.deepcopy(json.loads(text))
    target = _walk(expected, path, make=True)
    if target is None:
        raise ValueError(f"`{'.'.join(path)}` is not an object")
    target[key] = copy.deepcopy(value)
    return _checked(after, expected)


def delete_member(text: str, path: list[str], key: str) -> str:
    """`text` without `key` and its separating comma in the object at `path`, every other byte kept; the
    text unchanged when the key is not there; ValueError when the text is not a JSON object or the result
    does not read as the edit."""
    after = _delete_text(text, path, key)
    expected = json.loads(text)
    target = _walk(expected, path, make=False)
    if target is not None:
        target.pop(key, None)
    return _checked(after, expected)
