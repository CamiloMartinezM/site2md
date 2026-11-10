# Writing an Extractor provider

An Extractor provider is a normal Python distribution that derives source-specific records from a converted document. Install providers with `pip` or another standard package tool, then inspect them with `site2md extractors`.

The standalone executable finds providers differently; see [Using a provider with the executable](#using-a-provider-with-the-executable).

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

A distribution that ships a manifest but declares no entry point is still inspected: `site2md extractors` lists it, and `site2md extract` reports a conflict or an unavailable Extractor if it claims the requested ID. `site2md extract --entry-points-only` (or `site2md.extraction.extract(..., entry_points_only=True)`) skips every distribution that declares no `site2md.extractors.v1` entry point, so it never reads that distribution's installed-file list. With the option, `extract` doesn't notice such a distribution, though `site2md extractors` always keeps the full scan. A provider that declares its entry points as above gives the same result with and without the option.

`site2md build ... --extract ID` runs an Extractor the same way in the same process as the conversion. It saves the converted document first, then passes exactly that saved Markdown to the Extractor, so a provider needs no change to support it. `--entry-points-only` and `--values-only` apply to it as they do to `extract`. `--extract-output PATH` writes the result to that file instead of standard output, replacing it atomically as `extract --output` does, and it can't name the same file as `--output`. `build` doesn't check up front that the ID exists. If the Extractor is missing or fails, the Markdown stays, the command exits with status `1`, and it reports the same errors and diagnostics as `extract`.

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

## Using a provider with the executable

The standalone executable carries its own Python, so it can't see providers that pip installed into another environment, and it ignores `PYTHONPATH`. Install a provider into a folder of its own, then name the folder in `SITE2MD_PROVIDER_PATH`:

```shell
python3.12 -m pip install --target providers example-catalog
SITE2MD_PROVIDER_PATH=providers site2md extractors
```

In PowerShell, set the variable first: `$env:SITE2MD_PROVIDER_PATH = "providers"`.

`pip install --target` puts the provider and its dependencies in the folder. The variable holds one or more folders, separated as in `PATH`: `:` on Linux and `;` on Windows. The executable adds them after its own folders and before it looks for Extractors, and it processes `.pth` files in them. An empty entry is skipped, and a folder that doesn't exist has no effect and isn't reported. Only the executable reads the variable. The package finds providers in its own environment, as before.

If a provider depends on site2md, pip puts a second copy of site2md in the folder, and `site2md extractors` then reports the built-in Extractor as a conflict. Pass `--no-deps` and install the provider's other dependencies by name.

Inside the executable, a provider has three limits:

- **Standard library.** Only the standard-library modules that the bundle includes are available. A provider that imports another one, such as `sqlite3`, `zoneinfo` or `xml.etree`, fails with `ModuleNotFoundError`. From 0.6.0 the bundle no longer has `multiprocessing` either, so `concurrent.futures.ProcessPoolExecutor` fails too.
- **Compiled code.** Extension modules must be built for Python 3.12 on the same platform as the executable. Use a Python 3.12 of that platform to run `pip`. Pure-Python providers work as they are.
- **Bundled libraries.** A provider can't replace a library that the bundle already has, such as `marko` or `jsonschema`. The provider's folders come after the bundle's, so the bundled copy wins even when the folder holds another version.

Anyone who hits one of these limits should use the package instead.

## Testing and publishing

Test through the public `site2md.extraction.extract` operation with independently authored Markdown fixtures. Cover successful normalization, source spans, warnings, recognizable drift, and complete schema failure. Build and install the wheel in an isolated environment to verify that the entry point and exactly one static manifest are present, `site2md extractors` can inspect the provider without importing it, and two extractions receive fresh factory instances. Keep routine tests offline; make any permitted live drift check explicit and opt-in.
