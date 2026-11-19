"""Whether an observed model id is the one a run expects (SPEC §2.4, §24.5).

A run's expected model is a full id (an agent definition's `model`) or, for the implementer under
plane.json `workers.implementer_model`, an alias the Agent call accepts (`WORKER_MODEL_ALIASES`).
Telemetry reports full ids. Equal ids match; an alias matches any full id of its family (`sonnet`
matches an id containing `-sonnet-`); anything else, an unknown alias included, matches only itself.

Each role's default model and effort are written once, in `ROLES`, and each alias's full id once, in
`FULL_IDS` (SPEC §2.4): the headless launchers take their flags from `headless_flags`, and the seat
checks and the tests read `default`. An agent definition keeps its own full id and effort; a test holds
it to its role's row.
"""
from __future__ import annotations

from typing import Any

from ccp.config import WORKER_MODEL_ALIASES

# role -> (model alias, effort): the model and effort the plane gives that role by default.
ROLES: dict[str, tuple[str, str]] = {
    "runner": ("sonnet", "high"),
    "implementer": ("opus", "high"),
    "reviewer": ("sonnet", "high"),
    "verifier": ("sonnet", "high"),
    "architect": ("opus", "high"),
    "estimator": ("sonnet", "medium"),
}
# alias -> the full model id the plane pins: the one place a full id is written in code.
FULL_IDS: dict[str, str] = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}


def default(role: str) -> tuple[str, str]:
    """The (full model id, effort) the plane gives `role` by default."""
    alias, effort = ROLES[role]
    return FULL_IDS[alias], effort


def headless_flags(role: str) -> list[str]:
    """The `claude -p` flags that pin `role`'s default model and effort."""
    model, effort = default(role)
    return ["--model", model, "--effort", effort]


def matches(observed: Any, expected: Any) -> bool:
    """True when `observed` (a model id telemetry reported) is what `expected` pins."""
    o, e = str(observed), str(expected)
    if o == e:
        return True
    return e in WORKER_MODEL_ALIASES and f"-{e}-" in o
