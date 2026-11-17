"""Whether an observed model id is the one a run expects (SPEC §2.4, §24.5).

A run's expected model is a full id (an agent definition's `model`) or, for the implementer under
plane.json `workers.implementer_model`, an alias the Agent call accepts (`WORKER_MODEL_ALIASES`).
Telemetry reports full ids. Equal ids match; an alias matches any full id of its family (`sonnet`
matches an id containing `-sonnet-`); anything else, an unknown alias included, matches only itself.
"""
from __future__ import annotations

from typing import Any

from ccp.config import WORKER_MODEL_ALIASES


def matches(observed: Any, expected: Any) -> bool:
    """True when `observed` (a model id telemetry reported) is what `expected` pins."""
    o, e = str(observed), str(expected)
    if o == e:
        return True
    return e in WORKER_MODEL_ALIASES and f"-{e}-" in o
