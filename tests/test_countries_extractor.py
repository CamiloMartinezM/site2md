"""Behavior tests for the built-in Scrape This Site countries Extractor."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from site2md.extraction import ExtractionError, extract, list_extractors

EXTRACTOR_ID = "site2md.scrapethissite.countries"
FIXTURES = Path(__file__).with_name("fixtures") / "countries"


class CountriesExtractorTests(unittest.TestCase):
    """Exercise country extraction through caller-facing operations."""

    def fixture(self, name: str) -> str:
        """Return one independently authored country fixture."""
        return (FIXTURES / name).read_text(encoding="utf-8")

    def assert_fixture_fails(self, name: str) -> ExtractionError:
        """Return the structured failure from one drift fixture."""
        with self.assertRaises(ExtractionError) as raised:
            extract(self.fixture(name), EXTRACTOR_ID)
        return raised.exception

    def country_schema(self) -> dict[str, object]:
        """Return the JSON-native built-in country collection schema."""
        info = next(item for item in list_extractors() if item.id == EXTRACTOR_ID)
        return json.loads(json.dumps(info.record_schema))

    def test_valid_fixture_normalizes_complete_records_and_warns_on_order(self) -> None:
        result = extract(self.fixture("valid.md"), EXTRACTOR_ID)
        payload = json.loads(result.to_json())

        self.assertEqual(
            [record["value"] for record in payload["records"]],
            [
                {
                    "name": "Île d’Érable",
                    "capital": "Cité du Nord",
                    "population": 17,
                    "area_km2": 125.5,
                },
                {
                    "name": "Nørhaven",
                    "capital": None,
                    "population": 0,
                    "area_km2": 420.0,
                },
            ],
        )
        self.assertEqual(
            [diagnostic["code"] for diagnostic in payload["diagnostics"]],
            [f"{EXTRACTOR_ID}.reordered-labels"],
        )
        second_provenance = payload["records"][1]["provenance"]
        source = self.fixture("valid.md")
        covered = source[
            second_provenance["spans"][0]["start"] : second_provenance["spans"][0]["end"]
        ]
        self.assertTrue(covered.startswith("### Nørhaven\n"))
        self.assertTrue(covered.endswith("**Population:** 0\n"))
        self.assertNotIn("Routine footer", covered)

    def test_unexpected_label_warns_without_changing_record(self) -> None:
        payload = json.loads(
            extract(self.fixture("unexpected-label.md"), EXTRACTOR_ID).to_json()
        )

        self.assertEqual(
            payload["records"][0]["value"],
            {
                "name": "Labelia",
                "capital": "Known City",
                "population": 4,
                "area_km2": 8.0,
            },
        )
        self.assertEqual(
            [diagnostic["code"] for diagnostic in payload["diagnostics"]],
            [f"{EXTRACTOR_ID}.unexpected-label"],
        )

    def test_nested_strong_labels_are_accepted(self) -> None:
        markdown = """### Nested Emphasis

***Capital:*** Layer City
**Population:** 6
**Area (km2):** 9
"""

        payload = json.loads(extract(markdown, EXTRACTOR_ID).to_json())

        self.assertEqual(payload["records"][0]["value"]["capital"], "Layer City")

    def test_missing_label_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("missing-label.md")

    def test_duplicate_label_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("duplicate-label.md")

    def test_empty_name_fails_record_schema(self) -> None:
        error = self.assert_fixture_fails("empty-name.md")

        self.assertEqual(error.code, "site2md.record_schema_validation_failed")

    def test_invalid_population_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("invalid-population.md")

    def test_invalid_area_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("invalid-area.md")

    def test_duplicate_names_fail_even_when_values_differ(self) -> None:
        self.assert_fixture_fails("duplicate-name.md")

    def test_declared_count_mismatch_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("count-mismatch.md")

    def test_zero_candidates_fail_collection_schema(self) -> None:
        error = self.assert_fixture_fails("zero-candidates.md")

        self.assertEqual(error.code, "site2md.record_schema_validation_failed")

    def test_exact_duplicate_record_fixture_fails_complete_extraction(self) -> None:
        self.assert_fixture_fails("exact-duplicate-record.md")

    def test_country_collection_schema_enforces_the_complete_contract(self) -> None:
        schema = self.country_schema()
        validator = Draft202012Validator(schema)
        valid = {
            "name": "Schema Land",
            "capital": None,
            "population": 0,
            "area_km2": 0,
        }

        self.assertEqual(schema["type"], "array")
        self.assertEqual(schema["minItems"], 1)
        self.assertIs(schema["uniqueItems"], True)
        self.assertFalse(list(validator.iter_errors([valid])))

    def test_country_collection_schema_rejects_exact_duplicates(self) -> None:
        validator = Draft202012Validator(self.country_schema())
        record = {
            "name": "Duplicate Land",
            "capital": None,
            "population": 1,
            "area_km2": 2,
        }

        self.assertTrue(list(validator.iter_errors([record, record])))

    def test_country_record_schema_forbids_additional_fields(self) -> None:
        validator = Draft202012Validator(self.country_schema())
        record = {
            "name": "Extra Land",
            "capital": None,
            "population": 1,
            "area_km2": 2,
            "continent": "Elsewhere",
        }

        self.assertTrue(list(validator.iter_errors([record])))

    def test_country_record_schema_declares_scalar_constraints(self) -> None:
        record_schema = self.country_schema()["items"]

        self.assertEqual(
            record_schema,
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "capital", "population", "area_km2"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "capital": {
                        "anyOf": [
                            {"type": "string", "minLength": 1},
                            {"type": "null"},
                        ]
                    },
                    "population": {"type": "integer", "minimum": 0},
                    "area_km2": {"type": "number", "minimum": 0},
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
