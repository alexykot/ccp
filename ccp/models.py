"""Each role's model, and whether an observed model id is the one a run expects (SPEC §2.4, §24.5).

A run's expected model is a full id (an agent definition's `model`) or, where the role's model for the task
differs from the definition's, an alias the Agent call accepts (`ALIASES`). Telemetry reports full ids.
Equal ids match; an alias matches any full id of its family
(`sonnet` matches an id containing `-sonnet-`); anything else, an unknown alias included, matches only itself.

Each role's default model and effort are written once, in `ROLES`, and each alias's full id once, in
`FULL_IDS` (SPEC §2.4): plane.json `models` overrides a role's model, `model_for` reads it, the headless
launchers take their flags from `headless_flags`, and the seat checks and the tests read `default`. An agent
definition keeps its own full id and effort; a test holds it to its role's row.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ccp.config import Config

# The aliases the Agent call's `model` accepts; plane.json `models` takes nothing else, a full id included.
ALIASES = ("sonnet", "opus", "haiku", "fable")
# role -> (model alias, effort): the model and effort the plane gives that role by default; effort None where
# the operator's session sets it (the lead). The implementer's small and refactor arms are roles of their own:
# `implementer_small` for a task whose estimate is small, `implementer_refactor` for a refactor.
ROLES: dict[str, tuple[str, str | None]] = {
    "lead": ("opus", None),
    "runner": ("sonnet", "high"),
    "implementer": ("opus", "high"),
    "implementer_small": ("sonnet", "high"),
    "implementer_refactor": ("sonnet", "high"),
    "reviewer": ("opus", "high"),
    "verifier": ("sonnet", "high"),
    "architect": ("opus", "high"),
    "estimator": ("sonnet", "medium"),
}
# The arms of the deprecated plane.json `workers.implementer_model`, by the role each became (removed after
# the grace release).
LEGACY_ARMS = {"implementer_small": "small", "implementer_refactor": "refactor"}
# alias -> the full model id the plane pins: the one place a full id is written in code.
FULL_IDS: dict[str, str] = {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"}


def default(role: str) -> tuple[str, str | None]:
    """The (full model id, effort) the plane gives `role` by default."""
    alias, effort = ROLES[role]
    return FULL_IDS[alias], effort


def model_for(cfg: Config, role: str, task: dict[str, Any] | None = None, estimate_s: float | None = None) -> str:
    """The alias of `role`'s model in the product: plane.json `models.<role>`, else the plane's default (§2.4).
    For the implementer and a `task` (its front matter), the arm that applies: `implementer_refactor` for a
    task of kind `refactor`, else `implementer_small` when `estimate_s` (the task's estimated seconds) is at
    most `workers.small_estimate_minutes`, else `implementer`. A deprecated `workers.implementer_model` arm
    applies where `models` does not set that arm."""
    w = cfg.workers or {}
    if role == "implementer" and task is not None:
        if str(task.get("kind") or "feature") == "refactor":
            role = "implementer_refactor"
        elif estimate_s is not None and estimate_s <= float(w.get("small_estimate_minutes") or 30) * 60:
            role = "implementer_small"
    legacy = (w.get("implementer_model") or {}).get(LEGACY_ARMS.get(role, ""))
    if legacy and role not in cfg.models_given:
        return str(legacy)
    return str((cfg.models or {}).get(role) or ROLES[role][0])


def pin(alias: str, definition_model: str | None) -> str | None:
    """The model a run pins when the role's model is `alias`: the definition's own id when the alias is its
    family, else the alias (the Agent call's `model` overrides the definition)."""
    if definition_model is None or matches(definition_model, alias):
        return definition_model
    return alias


def headless_flags(role: str, cfg: Config | None = None) -> list[str]:
    """The `claude -p` flags that pin `role`'s model (the product's, with `cfg`; else the default) and its
    default effort."""
    effort = ROLES[role][1]
    if effort is None:
        raise KeyError(f"{role} has no effort row: the operator's session sets it")
    alias = model_for(cfg, role) if cfg is not None else ROLES[role][0]
    model = FULL_IDS.get(alias, alias)  # an alias the plane pins no full id for goes to `claude` as it is
    return ["--model", model, "--effort", effort]


def matches(observed: Any, expected: Any) -> bool:
    """True when `observed` (a model id telemetry reported) is what `expected` pins."""
    o, e = str(observed), str(expected)
    if o == e:
        return True
    return e in ALIASES and f"-{e}-" in o
