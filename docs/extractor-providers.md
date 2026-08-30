# Writing an Extractor provider

An Extractor provider is a normal Python distribution that derives source-specific records from a converted document. Install providers with `pip` or another standard package tool, then inspect them with `site2md extractors`.

> [!WARNING]
> Providers are trusted, in-process Python code. `site2md` does not sandbox them. Interface version 1 also has no per-run provider configuration; publish materially different behavior under a separate exact Extractor ID.

## Package contract

Register each Extractor as a zero-argument factory in the versioned entry-point group. The entry-point name is the exact, case-sensitive Extractor ID. IDs are lowercase, provider-qualified strings whose alphanumeric segments are separated by dots or hyphens.

```toml
[project.entry-points."site2md.extractors.v1"]
"example.catalog.products" = "example_catalog.extractor:create_extractor"
```

The installed distribution must contain exactly one file named `provider-manifest-v1.json`. It declares every entry point without importing provider code:

```json
{
  "manifest_version": 1,
  "extractors": [
    {
      "id": "example.catalog.products",
      "interface_version": 1,
      "implementation_version": "1.0.0",
      "record_schema": {
        "id": "https://example.com/schemas/catalog-products/v1",
        "version": "1.0.0",
        "schema": {
          "$schema": "https://json-schema.org/draft/2020-12/schema",
          "$id": "https://example.com/schemas/catalog-products/v1",
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["name"],
            "properties": {"name": {"type": "string", "minLength": 1}}
          }
        }
      }
    }
  ]
}
```

Entry-point names and manifest IDs must agree exactly. Include the manifest in wheel metadata as package data. Multiple distributions claiming the same ID create a visible conflict; installation order never selects a winner.

Keep the three versions independent:

- `interface_version` is the integer `1`, matching the entry-point group.
- `implementation_version` follows PEP 440 and describes provider behavior.
- `record_schema.version` follows semantic versioning. Increment the major version for breaking record changes, the minor version for additive optional fields, and the patch version for non-behavioral clarification. Its `id` is a stable absolute URI.

The record schema must use JSON Schema Draft 2020-12 and validate the complete ordered candidate array. It must be self-contained: only local references are accepted, and remote retrieval and format checking are disabled.

## Provider interface

Import provider types from `site2md.extractors.v1`. A factory must return a fresh Extractor object on every call so state cannot leak between runs. The host calls `extract` once with the complete converted document.

```python
from site2md.extractors.v1 import (
    ConvertedDocument,
    Extraction,
    Extractor,
    RecordCandidate,
)


class ProductExtractor:
    def extract(self, document: ConvertedDocument) -> Extraction:
        records = tuple(
            RecordCandidate(
                value={"name": document.plain_text(node).strip()},
                provenance=(node.span,),
            )
            for node in document.walk()
            if node.kind == "heading" and document.plain_text(node).strip()
        )
        return Extraction(records=records)


def create_extractor() -> Extractor:
    return ProductExtractor()
```

`ConvertedDocument.sections` preserves source-section order. Each section has its source marker value, if present, and ordered immutable nodes. A node exposes `kind`, `text`, immutable semantic `attributes`, ordered `children`, and a `SourceSpan`. Stable kinds cover headings, paragraphs, quotes, lists and list items, thematic breaks, HTML, emphasis, text, line breaks, links, images, code, tables, blank lines, and an `unknown` fallback. Semantic attributes carry details such as heading level, list ordering, link destination, code language, and table alignment. Use the document's `walk`, `plain_text`, `source_text`, and `covering_span` helpers instead of depending on Marko or parsing Markdown lines again.

A source span identifies one section and an exact range in the original Markdown. `start` and `end` are zero-based, half-open character offsets; `start_line` and `end_line` are one-based inclusive line numbers; `source_section` is a zero-based section index. Every record candidate needs at least one ordered span. The first is primary evidence, and additional spans can represent corroborating or joined content.

Return an `Extraction` containing ordered `RecordCandidate` and `Diagnostic` values. Candidate values must contain only JSON-native values, finite numbers, and string object keys. A diagnostic has `severity` (`warning` or `error`), a stable provider-qualified `code`, a human-readable `message`, and optional provenance. Warnings are retained in successful results; any error diagnostic fails the whole extraction. The host owns final result identity, schema validation, provenance validation, and deterministic JSON serialization.

## Testing and publishing

Test through the public `site2md.extraction.extract` operation with independently authored Markdown fixtures. Cover successful normalization, source spans, warnings, recognizable drift, and complete schema failure. Build and install the wheel in an isolated environment to verify that the entry point and exactly one static manifest are present, `site2md extractors` can inspect the provider without importing it, and two extractions receive fresh factory instances. Keep routine tests offline; make any permitted live drift check explicit and opt-in.
