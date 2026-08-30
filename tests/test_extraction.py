"""Public-interface tests for structured extraction."""

from __future__ import annotations

import hashlib
import json
import math
import unittest
from dataclasses import FrozenInstanceError
from importlib.resources import files
from unittest.mock import patch

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from site2md.extraction import ExtractionError, extract
from site2md.extractors.v1 import (
    ConvertedDocument,
    Diagnostic,
    Extraction,
    RecordCandidate,
    SourceSpan,
)


class ObservingExtractor:
    """Capture the converted document through the public provider interface."""

    def __init__(self) -> None:
        self.documents: list[ConvertedDocument] = []

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return one schema-valid record with ordered multi-span provenance."""
        self.documents.append(document)
        record_section = next(
            section
            for section in document.sections
            if len(section.nodes) >= 2 and section.nodes[0].kind == "heading"
        )
        first_heading = record_section.nodes[0]
        first_paragraph = record_section.nodes[1]
        final_node = document.sections[-1].nodes[-1]
        return Extraction(
            records=(
                RecordCandidate(
                    value={
                        "name": document.plain_text(first_heading),
                        "capital": "Example",
                        "population": 1,
                        "area_km2": 2.0,
                    },
                    provenance=(
                        document.covering_span(first_heading, first_paragraph),
                        final_node.span,
                    ),
                ),
            )
        )


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

    def test_provider_observes_exact_complete_document_once(self) -> None:
        markdown = (
            "Before the first marker.\r\n\r\n"
            "Inline `<!-- Source: not-a-marker -->` and "
            "<!-- Source: still-not-a-marker --> text.\r\n\r\n"
            "---\r\n\r\n"
            "```md\r\n<!-- Source: also-not-a-marker -->\r\n```\r\n\r\n"
            "<!-- Source: first.md -->\r\n\r\n"
            "# First &amp; \\*source\\*\r\n\r\n"
            "Evidence.\r\n\r\n"
            "<!-- Source: https://example.test/second -->\r\n\r\n"
            "## Second\r\n"
        )
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ) as factory:
            result = extract(markdown, "site2md.scrapethissite.countries")

        factory.assert_called_once_with()
        self.assertEqual(len(observer.documents), 1)
        document = observer.documents[0]
        self.assertEqual(
            [section.source for section in document.sections],
            [None, "first.md", "https://example.test/second"],
        )
        self.assertIn("thematic_break", [node.kind for node in document.walk()])
        self.assertIn("code_block", [node.kind for node in document.walk()])

        first_heading = document.sections[1].nodes[0]
        first_paragraph = document.sections[1].nodes[1]
        self.assertEqual(document.plain_text(first_heading), "First & *source*")
        self.assertEqual(document.source_text(first_heading.span), "# First &amp; \\*source\\*\r\n")
        covering = document.covering_span(first_heading, first_paragraph)
        self.assertEqual(
            document.source_text(covering),
            "# First &amp; \\*source\\*\r\n\r\nEvidence.\r\n",
        )
        self.assertEqual(
            (covering.start_line, covering.end_line, covering.source_section),
            (13, 15, 1),
        )

        payload = json.loads(result.to_json())
        self.assertEqual(
            payload["input_digest"], hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        )
        self.assertNotIn("timestamp", payload)
        self.assertNotIn("input_path", payload)
        provenance = payload["records"][0]["provenance"]
        self.assertEqual(provenance["source_section"], 1)
        self.assertEqual(
            [span["source_section"] for span in provenance["spans"]],
            [1, 2],
        )

    def test_provider_nodes_expose_stable_immutable_markdown_semantics(self) -> None:
        markdown = """# Contract &amp; \\*text\\*

Evidence paragraph.

- [x] Outer
  1. Nested [inline](https://example.test/inline?a=1&amp;b=2 "Inline &amp; title")

| Name | Value |
| :--- | ---: |
| [reference][ref] | 3 |

[ref]: https://example.test/reference?a=1&amp;b=2 "Reference &amp; title"

<!-- ordinary comment -->

> [!NOTE]
> Fallback content

```lang&amp;x
code
```
"""
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        document = observer.documents[0]
        self.assertEqual([section.source for section in document.sections], [None])
        nodes = document.walk()
        self.assertEqual(
            {"heading", "list", "list_item", "table", "table_row", "table_cell"}
            - {node.kind for node in nodes},
            set(),
        )
        comment = next(node for node in nodes if node.kind == "html")
        self.assertEqual(comment.text, "<!-- ordinary comment -->\n")
        unknown = next(
            node
            for node in nodes
            if node.kind == "unknown"
            and document.source_text(node.span).startswith("> [!NOTE]")
        )
        self.assertEqual(
            document.source_text(unknown.span),
            "> [!NOTE]\n> Fallback content\n",
        )
        heading = nodes[0]
        self.assertEqual(document.plain_text(heading), "Contract & *text*")
        self.assertEqual(heading.attributes["level"], 1)
        task = next(
            node
            for node in nodes
            if node.kind == "paragraph" and "Outer" in document.plain_text(node)
        )
        self.assertIs(task.attributes["checked"], True)

        links = [node for node in nodes if node.kind == "link"]
        self.assertEqual(
            [link.attributes["destination"] for link in links],
            [
                "https://example.test/inline?a=1&b=2",
                "https://example.test/reference?a=1&b=2",
            ],
        )
        self.assertEqual(
            [link.attributes["title"] for link in links],
            ["Inline & title", "Reference & title"],
        )
        self.assertEqual(
            [document.plain_text(link) for link in links],
            ["inline", "reference"],
        )
        self.assertEqual(
            [node.kind for node in document.walk(links[0])],
            ["link", "text"],
        )
        code_block = next(node for node in nodes if node.kind == "code_block")
        self.assertEqual(code_block.attributes["language"], "lang&x")
        self.assertTrue(
            all(type(node).__module__ == "site2md.extractors.v1" for node in nodes)
        )

        with self.assertRaises(TypeError):
            links[0].attributes["destination"] = "changed"  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            heading.text = "changed"  # type: ignore[misc]

    def test_provider_observes_a_table_nested_in_a_list(self) -> None:
        markdown = """# Nested contract

Evidence.

- Outer item

  | Key | Value |
  | --- | --- |
  | A | B |
"""
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        document = observer.documents[0]
        outer_list = next(node for node in document.walk() if node.kind == "list")
        nested_table = next(
            node for node in document.walk(outer_list) if node.kind == "table"
        )
        self.assertNotIn(nested_table, document.sections[0].nodes)
        self.assertEqual(
            document.source_text(nested_table.span),
            "| Key | Value |\n  | --- | --- |\n  | A | B |\n",
        )

    def test_provider_observes_malformed_markdown_as_literal_content(self) -> None:
        markdown = """# Malformed contract

Evidence.

[unterminated link
"""
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        document = observer.documents[0]
        malformed_paragraph = document.sections[0].nodes[-1]
        self.assertEqual(
            document.plain_text(malformed_paragraph),
            "[unterminated link",
        )

    def test_plain_text_decodes_only_complete_commonmark_entities(self) -> None:
        markdown = "# &copy &copy; &#65 &#65; &notit;\n\nEvidence.\n"
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        heading = observer.documents[0].sections[0].nodes[0]
        self.assertEqual(
            observer.documents[0].plain_text(heading),
            "&copy © &#65 A &notit;",
        )

    def test_plain_text_omits_inline_html_syntax(self) -> None:
        markdown = "# A <em>word</em><!-- comment --> tail.\n\nEvidence.\n"
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        document = observer.documents[0]
        heading = document.sections[0].nodes[0]
        self.assertEqual(document.plain_text(heading), "A word tail.")

    def test_lone_carriage_returns_have_exact_lines_and_offsets(self) -> None:
        markdown = "<!-- Source: one -->\r# Lines\r\rEvidence.\r"
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        document = observer.documents[0]
        paragraph = document.sections[0].nodes[1]
        self.assertEqual([section.source for section in document.sections], ["one"])
        self.assertEqual(document.source_text(paragraph.span), "Evidence.\r")
        self.assertEqual((paragraph.span.start_line, paragraph.span.end_line), (4, 4))

    def test_leading_blank_markdown_keeps_an_unknown_source_section(self) -> None:
        markdown = "\r\n\r\n<!-- Source: one -->\r\n# One\r\n\r\nEvidence.\r\n"
        observer = ObservingExtractor()

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            extract(markdown, "site2md.scrapethissite.countries")

        self.assertEqual(
            [section.source for section in observer.documents[0].sections],
            [None, "one"],
        )

    def test_warning_diagnostic_is_preserved_on_success(self) -> None:
        markdown = "# Country\n\nEvidence.\n"
        observer = ObservingExtractor()
        original_extract = observer.extract

        def extract_with_warning(document: ConvertedDocument) -> Extraction:
            extracted = original_extract(document)
            return Extraction(
                records=extracted.records,
                diagnostics=(
                    Diagnostic(
                        severity="warning",
                        code="site2md.scrapethissite.countries.reordered",
                        message="Fields were reordered",
                        provenance=(document.sections[0].nodes[0].span,),
                    ),
                ),
            )

        observer.extract = extract_with_warning  # type: ignore[method-assign]
        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=observer,
        ):
            result = extract(markdown, "site2md.scrapethissite.countries")

        payload = json.loads(result.to_json())
        self.assertEqual(payload["diagnostics"][0]["severity"], "warning")
        self.assertEqual(
            payload["diagnostics"][0]["provenance"][0]["start"],
            0,
        )

    def test_error_diagnostic_discards_candidates_and_fails(self) -> None:
        class ErrorExtractor:
            def extract(self, document: ConvertedDocument) -> Extraction:
                heading = document.sections[0].nodes[0]
                return Extraction(
                    records=(
                        RecordCandidate(
                            value={
                                "name": "Must be discarded",
                                "capital": None,
                                "population": 0,
                                "area_km2": 0,
                            },
                            provenance=(heading.span,),
                        ),
                    ),
                    diagnostics=(
                        Diagnostic(
                            severity="error",
                            code="site2md.scrapethissite.countries.drift",
                            message="Source structure changed",
                            provenance=(heading.span,),
                        ),
                    ),
                )

        with patch(
            "site2md.extractors.countries.create_extractor",
            return_value=ErrorExtractor(),
        ), self.assertRaises(ExtractionError) as raised:
            extract("# Country\n", "site2md.scrapethissite.countries")

        self.assertEqual(raised.exception.code, "site2md.extractor_reported_error")
        self.assertEqual(
            [diagnostic.code for diagnostic in raised.exception.diagnostics],
            ["site2md.scrapethissite.countries.drift"],
        )

    def test_malformed_diagnostics_are_rejected(self) -> None:
        cases = (
            Diagnostic(
                severity="notice",  # type: ignore[arg-type]
                code="site2md.scrapethissite.countries.notice",
                message="Wrong severity",
            ),
            Diagnostic(
                severity="warning",
                code="another-provider.warning",
                message="Wrong namespace",
            ),
            Diagnostic(
                severity="warning",
                code="site2md.scrapethissite.countries.empty",
                message="",
            ),
            Diagnostic(
                severity="warning",
                code=7,  # type: ignore[arg-type]
                message="Non-string code",
            ),
        )
        for diagnostic in cases:
            with self.subTest(code=diagnostic.code):
                class InvalidDiagnosticExtractor:
                    def __init__(self, invalid: Diagnostic) -> None:
                        self.invalid = invalid

                    def extract(self, document: ConvertedDocument) -> Extraction:
                        return Extraction(records=(), diagnostics=(self.invalid,))

                with patch(
                    "site2md.extractors.countries.create_extractor",
                    return_value=InvalidDiagnosticExtractor(diagnostic),
                ), self.assertRaises(ExtractionError) as raised:
                    extract("# Diagnostic\n", "site2md.scrapethissite.countries")

                self.assertEqual(
                    raised.exception.code,
                    "site2md.extractor_output_invalid",
                )

    def test_invalid_json_values_and_provenance_fail_structurally(self) -> None:
        cyclic: list[object] = []
        cyclic.append(cyclic)
        cases = (
            ({1: "not a string key"}, None, "site2md.extractor_output_invalid"),
            ({"instance": object()}, None, "site2md.extractor_output_invalid"),
            ({"instance": math.inf}, None, "site2md.extractor_output_invalid"),
            ({"instance": cyclic}, None, "site2md.extractor_output_invalid"),
            (
                {"instance": 1},
                SourceSpan(0, 0, 1000, 1, 1),
                "site2md.provenance_invalid",
            ),
        )
        for value, invalid_span, expected_code in cases:
            with self.subTest(value=value):
                class InvalidExtractor:
                    def __init__(
                        self,
                        invalid_value: object,
                        invalid_provenance: SourceSpan | None,
                    ) -> None:
                        self.invalid_value = invalid_value
                        self.invalid_provenance = invalid_provenance

                    def extract(self, document: ConvertedDocument) -> Extraction:
                        span = (
                            self.invalid_provenance
                            or document.sections[0].nodes[0].span
                        )
                        return Extraction(
                            records=(RecordCandidate(value=self.invalid_value, provenance=(span,)),),  # type: ignore[arg-type]
                        )

                with patch(
                    "site2md.extractors.countries.create_extractor",
                    return_value=InvalidExtractor(value, invalid_span),
                ), self.assertRaises(ExtractionError) as raised:
                    extract("# Country\n", "site2md.scrapethissite.countries")

                self.assertEqual(raised.exception.code, expected_code)

    def test_successful_result_is_deeply_immutable(self) -> None:
        result = extract(
            "# One country\n\n### Example\n\n**Capital:** None  \n**Population:** 1  \n**Area (km2):** 2\n",
            "site2md.scrapethissite.countries",
        )

        with self.assertRaises(TypeError):
            result.payload["format_version"] = 2  # type: ignore[index]
        record = result.payload["records"][0]  # type: ignore[index]
        with self.assertRaises(TypeError):
            record["value"]["name"] = "changed"  # type: ignore[index]
        with self.assertRaises(AttributeError):
            result.payload["records"].append(record)  # type: ignore[union-attr]

    def test_shared_result_schema_validates_the_fixed_envelope(self) -> None:
        markdown = "# One country\n\n### Åland\n\n**Capital:** Mariehamn  \n**Population:** 1  \n**Area (km2):** 2\n"
        serialized = extract(
            markdown,
            "site2md.scrapethissite.countries",
        ).to_json()
        schema = json.loads(
            files("site2md.extraction")
            .joinpath("result-schema-v1.json")
            .read_text(encoding="utf-8")
        )

        self.assertEqual(schema["$id"], "urn:site2md:extraction-result:v1")
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(json.loads(serialized))
        self.assertEqual(
            list(json.loads(serialized)),
            [
                "format_version",
                "extractor",
                "provider",
                "record_schema",
                "input_digest",
                "source_sections",
                "records",
                "diagnostics",
            ],
        )
        self.assertIn("Åland", serialized)
        self.assertNotIn("\\u00c5", serialized)
        self.assertTrue(serialized.endswith("\n"))
        self.assertFalse(serialized.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
