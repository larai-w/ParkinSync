#!/usr/bin/env python3

import unittest

from check_schema_drift import normalize


class SchemaDriftGuardTests(unittest.TestCase):
    def test_ignores_object_required_and_enum_order(self):
        left = {
            "required": ["a", "b"],
            "properties": {"kind": {"enum": ["x", "y"]}},
        }
        right = {
            "properties": {"kind": {"enum": ["y", "x"]}},
            "required": ["b", "a"],
        }
        self.assertEqual(normalize(left), normalize(right))

    def test_detects_a_semantic_enum_change(self):
        left = {"properties": {"kind": {"enum": ["x", "y"]}}}
        right = {"properties": {"kind": {"enum": ["x", "z"]}}}
        self.assertNotEqual(normalize(left), normalize(right))

    def test_preserves_order_where_array_order_can_carry_meaning(self):
        left = {"examples": ["first", "second"]}
        right = {"examples": ["second", "first"]}
        self.assertNotEqual(normalize(left), normalize(right))


if __name__ == "__main__":
    unittest.main()
