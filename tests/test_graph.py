"""ccp/graph.py: the cycles in a dependency map and what a node depends on, on plain mappings."""
from __future__ import annotations

import unittest

from ccp import graph


class CyclesTests(unittest.TestCase):
    def test_no_cycle(self):
        self.assertEqual(graph.cycles({"a": ["b", "c"], "b": ["c"], "c": []}), [])

    def test_a_self_loop(self):
        self.assertEqual(graph.cycles({"a": ["a"], "b": ["a"]}), [["a"]])

    def test_two_cycles_each_once_from_the_lowest_node(self):
        deps = {"a": ["a"], "b": ["d"], "c": ["b"], "d": ["c", "zz"], "e": ["d"]}
        self.assertEqual(graph.cycles(deps), [["a"], ["b", "d", "c"]])

    def test_a_missing_node_is_not_followed(self):
        self.assertEqual(graph.cycles({"a": ["gone"]}), [])


class ClosureTests(unittest.TestCase):
    def test_through_a_diamond(self):
        deps = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": [], "x": ["a"]}
        self.assertEqual(graph.closure(deps, "a"), {"b", "c", "d"})

    def test_a_missing_node_is_in_the_set_and_not_followed(self):
        self.assertEqual(graph.closure({"a": ["gone", "b"], "b": []}, "a"), {"gone", "b"})
        self.assertEqual(graph.closure({"a": []}, "nope"), set())

    def test_a_cycle_ends(self):
        self.assertEqual(graph.closure({"a": ["b"], "b": ["a"]}, "a"), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
