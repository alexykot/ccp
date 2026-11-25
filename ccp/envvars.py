"""The plane's environment variables are named `CCP_*` (ADR-0036 D3). `envvar` reads one, an empty value
counting as unset, as the shell scripts' `${CCP_X:-default}` does."""
from __future__ import annotations

import os


def envvar(name: str, default=None, environ=None):
    """`name` from the environment, else `default`. Empty counts as unset, as in the shell scripts'
    `${CCP_X:-default}`."""
    e = os.environ if environ is None else environ
    return e.get(name) or default
