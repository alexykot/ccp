"""The plane's one schema checker (SPEC §10.1, §15.3): where a value breaks a contract in `contracts/`.

A stdlib subset of JSON Schema, so the plane takes no dependency. `schema_errors` knows only the keywords the
contracts use; a schema with another keyword is an error, so a contract change cannot silently weaken a check.
`ccp verify` holds a verdict to its contract with it, and the tests hold each live contract to the record its
writer writes (`tests/test_contract_writers.py`)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
# Keywords that only describe; every other keyword must be one `schema_errors` enforces.
_ANNOTATIONS = {"$schema", "$id", "title", "description", "default"}
_KEYWORDS = {"type", "enum", "const", "required", "properties", "additionalProperties", "items", "minItems",
             "minLength", "minimum", "maxProperties", "pattern", "format", "allOf", "anyOf", "oneOf", "not", "if", "then"}
_UNCHECKABLE = "which ccp verify cannot check"


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_type(value: Any, typ: str) -> bool:
    if typ == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if typ == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[typ])


def _kind(value: Any) -> str:
    """The JSON type of `value`, with `1` and `1.0` both a number, so `const` compares as JSON Schema does."""
    for typ in ("null", "boolean", "string", "number", "array", "object"):
        if is_type(value, typ):
            return typ
    return type(value).__name__


def schema_errors(value: Any, schema: dict[str, Any], at: str = "record", newer: bool = False) -> list[str]:
    """Where `value` breaks `schema`. Only the keywords the plane's contracts use are known; an
    unknown one is an error, so a contract change cannot silently weaken this check. With `newer`
    (a record written by a newer version) a key the schema does not name is passed over; every key
    it names is still checked."""
    unknown = set(schema) - _ANNOTATIONS - _KEYWORDS
    if unknown:
        return [f"{at}: the schema uses {', '.join(sorted(unknown))}, {_UNCHECKABLE}"]
    types = schema.get("type")
    if types is not None:
        types = [types] if isinstance(types, str) else types
        if not any(is_type(value, t) for t in types):
            return [f"{at}: {json.dumps(value)[:60]} is not {' or '.join(types)}"]
    errs: list[str] = []
    if "const" in schema and (value != schema["const"] or _kind(value) != _kind(schema["const"])):
        errs.append(f"{at}: {json.dumps(value)[:60]} is not {json.dumps(schema['const'])}")
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{at}: {json.dumps(value)[:60]} is not one of {', '.join(map(str, schema['enum']))}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{at}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{at}: {value!r} does not match {schema['pattern']}")
        if schema.get("format") == "date-time" and parse_dt(value) is None:
            errs.append(f"{at}: {value!r} is not an RFC 3339 date-time")
    if "minimum" in schema and is_type(value, "number") and value < schema["minimum"]:
        errs.append(f"{at}: {value} is below {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{at}: fewer than {schema['minItems']} item(s)")
        for i, item in enumerate(value):
            errs += schema_errors(item, schema.get("items", {}), f"{at}[{i}]", newer)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{at}: missing {k}")
        for k, v in value.items():
            if k in props:
                errs += schema_errors(v, props[k], f"{at}.{k}", newer)
            elif isinstance(schema.get("additionalProperties"), dict):
                errs += schema_errors(v, schema["additionalProperties"], f"{at}.{k}", newer)
            elif schema.get("additionalProperties") is False and not newer:
                errs.append(f"{at}: unexpected key {k}")
        if len(value) > schema.get("maxProperties", len(value)):
            errs.append(f"{at}: more than {schema['maxProperties']} key(s)")
    return errs + _combined(value, schema, at, newer)


def _combined(value: Any, schema: dict[str, Any], at: str, newer: bool) -> list[str]:
    """The keywords that combine sub-schemas: `allOf` (each holds), `anyOf` (one does), `oneOf` (exactly one),
    `not` (it does not) and `if`/`then` (when the first holds, so does the second). `not` and `if` are judged
    strictly, whatever `newer` says: a key skipped there would make the sub-schema match more. A sub-schema with a keyword
    this checker does not know is reported as it stands, never read as one that failed to match."""
    def run(sub: dict[str, Any], newer: bool = newer) -> list[str]:
        return schema_errors(value, sub, at, newer)

    def unchecked(results: list[list[str]]) -> list[str]:
        return [e for errs in results for e in errs if _UNCHECKABLE in e]

    errs: list[str] = []
    for sub in schema.get("allOf", []):
        errs += run(sub)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            results = [run(sub) for sub in schema[key]]
            held = sum(1 for r in results if not r)
            if unchecked(results):
                errs += unchecked(results)
            elif key == "anyOf" and held == 0:
                errs.append(f"{at}: {json.dumps(value)[:60]} matches none of the anyOf schemas")
            elif key == "oneOf" and held != 1:
                errs.append(f"{at}: {json.dumps(value)[:60]} matches {held} of the oneOf schemas, not one")
    if "not" in schema:
        inner = run(schema["not"], newer=False)
        if unchecked([inner]):
            errs += unchecked([inner])
        elif not inner:
            errs.append(f"{at}: {json.dumps(value)[:60]} matches a schema it must not match")
    if "if" in schema and "then" in schema:
        cond = run(schema["if"], newer=False)
        if unchecked([cond]):
            errs += unchecked([cond])
        elif not cond:
            errs += run(schema["then"])
    return errs
