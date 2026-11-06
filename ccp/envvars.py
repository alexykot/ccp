"""The plane's environment variables are named `CCP_*` (ADR-0036 D3). Readers go through `envvar`, and
the variables `ccp` sets for a command it runs through `for_child`, so the naming has one place."""
from __future__ import annotations

import os


def envvar(name: str, default=None, environ=None):
    """`name` from the environment, else `default`. Empty counts as unset, as in the shell scripts'
    `${CCP_X:-default}`."""
    e = os.environ if environ is None else environ
    return e.get(name) or default


def for_child(variables: dict) -> dict:
    """The variables `ccp` sets for a child command."""
    return dict(variables)
