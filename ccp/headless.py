"""A plane-launched `claude -p` (SPEC §24.3, house rule E8): its environment without the API keys, the
JSON it prints, and whether it stopped on a quota. The architect and estimator seats launch through it."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from ccp.queue import lib

STRIP_KEYS = ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN")

QUOTA_RE = re.compile(
    r"(usage limit|session limit|limit reached|rate[ _-]?limit|credit balance|out of credits|"
    r"quota|5-hour limit|weekly limit|resets? at)",
    re.I,
)

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})")

EPOCH_RE = re.compile(r"\b(1[7-9]\d{8})\b")


def headless_env(project_id: str, seat: str) -> dict[str, str]:
    """The environment of a plane-launched `claude -p` (SPEC §24.3): ours without the API keys, plus
    the resource attributes that route its telemetry to the project and to its seat, subagents too."""
    env = {k: v for k, v in os.environ.items() if k not in STRIP_KEYS}
    keep = [x.strip() for x in (env.get("OTEL_RESOURCE_ATTRIBUTES") or "").split(",")
            if x.strip() and not x.strip().startswith("ccp.")]
    env["OTEL_RESOURCE_ATTRIBUTES"] = ",".join(keep + [f"ccp.project_id={project_id}", f"ccp.seat={seat}"])
    return env


def parse_claude_json(stdout: str) -> dict[str, Any]:
    """The result object of `--output-format json`: the last `result` entry of a list, the object itself, or
    the last JSON object line of mixed output; {} when there is none."""
    s = (stdout or "").strip()
    if not s:
        return {}
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            obj = next((x for x in reversed(obj) if isinstance(x, dict) and x.get("type") == "result"), {})
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        for line in reversed(s.splitlines()):
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return {}


def detect_quota(res: dict[str, Any], stdout: str, stderr: str) -> tuple[bool, str | None, str | None]:
    """(stopped on a quota, its class `credit` or `session`, when it resets as a UTC stamp or None)."""
    text = " ".join([str(res.get("result") or ""), str(res.get("api_error_status") or ""), stdout[-4000:], stderr[-4000:]])
    is_err = bool(res.get("is_error")) or not res
    if not (is_err and QUOTA_RE.search(text)) and str(res.get("api_error_status") or "") != "429":
        return False, None, None
    qclass = "credit" if re.search(r"credit|balance", text, re.I) else "session"
    resets = res.get("resets_at")
    if not resets:
        m = ISO_RE.search(text)
        if m:
            resets = m.group(0)
        else:
            m = EPOCH_RE.search(text)
            if m:
                resets = lib.fmt_dt(datetime.fromtimestamp(int(m.group(1)), tz=timezone.utc))
    if resets:
        try:
            resets = lib.fmt_dt(lib.parse_dt(resets))
        except Exception:
            resets = None
    return True, qclass, resets
