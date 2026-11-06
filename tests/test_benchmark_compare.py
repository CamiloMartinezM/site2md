"""Tests for comparing a tool's output with the benchmark reference."""

from __future__ import annotations

import unittest

from benchmarks._types import JsonValue
from benchmarks.compare import first_difference, unordered_difference

REFERENCE: JsonValue = [
    {"name": "Andorra", "capital": "Andorra la Vella", "population": 84000, "area_km2": 468.0},
    {"name": "Antarctica", "capital": None, "population": 0, "area_km2": 14000000.0},
]
ANDORRA_TEXT = '{"name": "Andorra", "capital": "Andorra la Vella", "population": 84000, "area_km2": 468.0}'
ANTARCTICA_TEXT = '{"name": "Antarctica", "capital": null, "population": 0, "area_km2": 14000000.0}'
REFERENCE_TEXT = f"[{ANDORRA_TEXT}, {ANTARCTICA_TEXT}]"


class FirstDifferenceTests(unittest.TestCase):
    """Check that only an exact match, number types included, counts as a match."""

    def test_identical_output_matches(self) -> None:
        self.assertIsNone(first_difference(REFERENCE_TEXT, REFERENCE))

    def test_whitespace_key_order_and_number_notation_are_ignored(self) -> None:
        output = """[
            {"area_km2": 468.0, "population": 84000, "capital": "Andorra la Vella", "name": "Andorra"},
            {"name": "Antarctica", "capital": null, "population": 0, "area_km2": 1.4E7}
        ]"""
        self.assertIsNone(first_difference(output, REFERENCE))

    def test_changed_value_is_reported_with_its_location(self) -> None:
        output = REFERENCE_TEXT.replace("84000", "84001")
        difference = first_difference(output, REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("[0].population", str(difference))

    def test_a_missing_record_is_reported_by_count(self) -> None:
        self.assertEqual(first_difference("[]", REFERENCE), "output: expected 2 records, got 0")

    def test_integer_where_the_reference_has_a_float_does_not_match(self) -> None:
        output = REFERENCE_TEXT.replace("468.0", "468")
        difference = first_difference(output, REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("[0].area_km2", str(difference))

    def test_float_where_the_reference_has_an_integer_does_not_match(self) -> None:
        output = REFERENCE_TEXT.replace('"population": 0', '"population": 0.0')
        self.assertIsNotNone(first_difference(output, REFERENCE))

    def test_boolean_does_not_match_the_number_it_equals(self) -> None:
        self.assertIsNotNone(first_difference("[true]", [1]))

    def test_missing_capital_must_be_null_not_a_string(self) -> None:
        output = REFERENCE_TEXT.replace("null", '"None"')
        difference = first_difference(output, REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("[1].capital", str(difference))

    def test_reordered_records_do_not_match(self) -> None:
        output = f"[{ANTARCTICA_TEXT}, {ANDORRA_TEXT}]"
        self.assertIsNotNone(first_difference(output, REFERENCE))

    def test_missing_record_is_reported_as_a_length_difference(self) -> None:
        difference = first_difference(f"[{ANDORRA_TEXT}]", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("2", str(difference))

    def test_extra_key_does_not_match(self) -> None:
        output = REFERENCE_TEXT.replace('"name": "Andorra"', '"name": "Andorra", "code": "AD"')
        self.assertIsNotNone(first_difference(output, REFERENCE))

    def test_text_that_is_not_json_does_not_match(self) -> None:
        difference = first_difference("### Andorra", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("JSON", str(difference))


class UnorderedDifferenceTests(unittest.TestCase):
    """Check that a crawl's output may come in any order but must hold exactly the reference records."""

    def test_the_reference_in_another_order_matches(self) -> None:
        self.assertIsNone(unordered_difference(f"[{ANTARCTICA_TEXT}, {ANDORRA_TEXT}]", REFERENCE))

    def test_whitespace_key_order_and_number_notation_are_ignored(self) -> None:
        output = """[
            {"name": "Antarctica", "capital": null, "population": 0, "area_km2": 1.4E7},
            {"area_km2": 468.0, "population": 84000, "capital": "Andorra la Vella", "name": "Andorra"}
        ]"""
        self.assertIsNone(unordered_difference(output, REFERENCE))

    def test_a_missing_record_is_named(self) -> None:
        difference = unordered_difference(f"[{ANDORRA_TEXT}]", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("missing", str(difference))
        self.assertIn("Antarctica", str(difference))

    def test_a_record_that_is_not_in_the_reference_is_named(self) -> None:
        decoy = '{"name": "Decoyland", "capital": "Decoy City", "population": 1, "area_km2": 2.0}'
        difference = unordered_difference(f"[{ANDORRA_TEXT}, {ANTARCTICA_TEXT}, {decoy}]", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("unexpected", str(difference))
        self.assertIn("Decoyland", str(difference))

    def test_integer_where_the_reference_has_a_float_does_not_match(self) -> None:
        andorra = ANDORRA_TEXT.replace("468.0", "468")
        self.assertIsNotNone(unordered_difference(f"[{andorra}, {ANTARCTICA_TEXT}]", REFERENCE))

    def test_missing_capital_must_be_null_not_a_string(self) -> None:
        antarctica = ANTARCTICA_TEXT.replace("null", '"None"')
        self.assertIsNotNone(unordered_difference(f"[{ANDORRA_TEXT}, {antarctica}]", REFERENCE))

    def test_a_repeated_record_is_named(self) -> None:
        difference = unordered_difference(f"[{ANDORRA_TEXT}, {ANTARCTICA_TEXT}, {ANDORRA_TEXT}]", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("repeated", str(difference))
        self.assertIn("Andorra", str(difference))

    def test_a_repeated_record_does_not_hide_a_missing_one(self) -> None:
        difference = unordered_difference(f"[{ANDORRA_TEXT}, {ANDORRA_TEXT}]", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("missing", str(difference))
        self.assertIn("repeated", str(difference))

    def test_text_that_is_not_json_does_not_match(self) -> None:
        difference = unordered_difference("### Andorra", REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("JSON", str(difference))

    def test_json_that_is_not_an_array_does_not_match(self) -> None:
        difference = unordered_difference(ANDORRA_TEXT, REFERENCE)
        self.assertIsNotNone(difference)
        self.assertIn("array", str(difference))


if __name__ == "__main__":
    unittest.main()
