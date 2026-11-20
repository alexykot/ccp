"""config.architect_on and config.adoption_point (SPEC §19, §19.11): the one test for "the architect seat is on"
and the one reader of the task number it starts from, on a product with no architect block, with one, with
`"architect": false`, and with one naming `shape_from_task` as a number and as an id."""
from __future__ import annotations

import unittest

from ccp import config
from tests.helpers import Product


def load(architect=None, **extra) -> config.Config:
    plane = {"architect": architect} if architect is not None else {}  # None: no block at all
    p = Product({**plane, **extra}, bare=True)
    try:
        return config.load(p.root)
    finally:
        p.cleanup()


class ArchitectOn(unittest.TestCase):
    def test_a_product_with_no_architect_block_has_it_on(self):
        self.assertIs(config.architect_on(load()), True)

    def test_false_is_the_one_way_to_turn_it_off(self):
        self.assertIs(config.architect_on(load(False)), False)

    def test_true_is_not_a_block(self):
        with self.assertRaises(config.ConfigError):
            load(True)

    def test_an_empty_block_turns_it_on(self):
        self.assertIs(config.architect_on(load({})), True)

    def test_a_block_with_keys_turns_it_on(self):
        self.assertIs(config.architect_on(load({"grace_tasks": 3})), True)


class AdoptionPoint(unittest.TestCase):
    def test_none_without_a_block(self):
        self.assertIsNone(config.adoption_point(load()))

    def test_none_with_the_seat_off(self):
        self.assertIsNone(config.adoption_point(load(False)))

    def test_none_with_a_block_that_names_no_start(self):
        self.assertIsNone(config.adoption_point(load({})))

    def test_a_task_number(self):
        self.assertEqual(config.adoption_point(load({"shape_from_task": "0042"})), 42)

    def test_a_task_id(self):
        self.assertEqual(config.adoption_point(load({"shape_from_task": "0042-some-task"})), 42)

    def test_a_number_with_the_product_task_width(self):
        cfg = load({"shape_from_task": "00042-x"}, ids={"task": {"width": 5}})
        self.assertEqual(config.adoption_point(cfg), 42)


if __name__ == "__main__":
    unittest.main()
