"""Public-interface tests for structured extraction."""

from __future__ import annotations

import hashlib
import json
import unittest

from site2md.extraction import extract


class ExtractionTests(unittest.TestCase):
    """Exercise extraction through its caller-facing operation."""

    def test_country_markdown_produces_valid_deterministic_result(self) -> None:
        markdown = """<!-- Source: https://example.test/countries -->
# One independently authored country

### République d'Exemple

**Capital:** Cité d’Essai
**Population:** 125000
**Area (km2):** 4.68e2
"""

        first = extract(markdown, "site2md.scrapethissite.countries")
        second = extract(markdown, "site2md.scrapethissite.countries")
        document = json.loads(first.to_json())

        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(document["format_version"], 1)
        self.assertEqual(
            document["extractor"],
            {
                "id": "site2md.scrapethissite.countries",
                "interface_version": 1,
                "implementation_version": "1.0.0",
            },
        )
        self.assertEqual(document["provider"]["distribution"], "site2md")
        self.assertEqual(
            document["record_schema"],
            {
                "id": "urn:site2md:extractors:scrapethissite:countries:v1",
                "version": "1.0.0",
            },
        )
        self.assertEqual(
            document["input_digest"], hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        )
        self.assertEqual(
            document["records"][0]["value"],
            {
                "name": "République d'Exemple",
                "capital": "Cité d’Essai",
                "population": 125000,
                "area_km2": 468.0,
            },
        )
        self.assertEqual(document["records"][0]["provenance"]["source_section"], 0)
        self.assertEqual(
            document["records"][0]["provenance"]["source"],
            "https://example.test/countries",
        )
        self.assertTrue(first.to_json().endswith("\n"))


if __name__ == "__main__":
    unittest.main()
