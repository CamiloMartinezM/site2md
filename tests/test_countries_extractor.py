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

    def test_source_drift_fixtures_fail_the_complete_extraction(self) -> None:
        fixtures = (
            "missing-label.md",
            "duplicate-label.md",
            "empty-name.md",
            "invalid-population.md",
            "invalid-area.md",
            "duplicate-name.md",
            "count-mismatch.md",
            "zero-candidates.md",
            "exact-duplicate-record.md",
        )

        for fixture in fixtures:
            with self.subTest(fixture=fixture), self.assertRaises(ExtractionError):
                extract(self.fixture(fixture), EXTRACTOR_ID)

    def test_country_collection_schema_enforces_the_complete_contract(self) -> None:
        info = next(item for item in list_extractors() if item.id == EXTRACTOR_ID)
        schema = info.record_schema
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
        invalid_collections: tuple[list[object], ...] = (
            [],
            [valid, valid],
            [{**valid, "continent": "Elsewhere"}],
            [{**valid, "name": ""}],
            [{**valid, "capital": ""}],
            [{**valid, "population": -1}],
            [{**valid, "population": 1.5}],
            [{**valid, "area_km2": -0.1}],
        )
        for collection in invalid_collections:
            with self.subTest(collection=collection):
                self.assertTrue(list(validator.iter_errors(collection)))


if __name__ == "__main__":
    unittest.main()
