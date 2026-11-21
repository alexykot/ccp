"""Walks over a dependency map (SPEC §5, §21.1): the cycles in it and what a node depends on.

A map is `{node: [the nodes it depends on]}` on plain ids, with no task or ADR in it. A dependency
that is not a key of the map is a node the map does not describe: no walk follows it."""
from __future__ import annotations

from typing import Mapping


def cycles(deps: Mapping[str, list[str]]) -> list[list[str]]:
    """The cycles in the map, at least one through every set of nodes that wait on each other, each
    once, as the ids along it from its lowest one (`[a, b]`: a depends on b, b on a; `[a]`: a depends
    on itself), in the order of those ids. A dependency on a node that is not a key is not followed."""
    state: dict[str, int] = {}  # 1: on the walk's path, 2: finished
    found: dict[tuple[str, ...], list[str]] = {}
    for root in sorted(deps):
        if root in state:
            continue
        path, its = [root], [iter(deps[root])]
        state[root] = 1
        while path:
            d = next(its[-1], None)
            if d is None:
                state[path.pop()] = 2
                its.pop()
            elif d not in deps or state.get(d) == 2:
                continue
            elif state.get(d) == 1:
                cyc = path[path.index(d):]
                k = cyc.index(min(cyc))
                cyc = cyc[k:] + cyc[:k]
                found.setdefault(tuple(cyc), cyc)
            else:
                state[d] = 1
                path.append(d)
                its.append(iter(deps[d]))
    return [found[k] for k in sorted(found)]


def closure(deps: Mapping[str, list[str]], start: str) -> set[str]:
    """Every node `start` depends on, directly or through others, not `start` itself unless it
    depends on itself through a cycle. A dependency that is not a key is in the set and not followed."""
    out: set[str] = set()
    stack = list(deps.get(start, []))
    while stack:
        d = stack.pop()
        if d in out:
            continue
        out.add(d)
        stack += deps.get(d, [])
    return out
