"""Tests for comparing a tool's output with the benchmark reference."""

from __future__ import annotations

import unittest

from benchmarks._types import JsonValue
from benchmarks.compare import first_difference

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


if __name__ == "__main__":
    unittest.main()
