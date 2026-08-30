"""Caller-facing structured extraction operation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import Distribution, distribution
from pathlib import Path
from typing import Any, Protocol, cast

import marko
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from site2md.extractors.v1 import (
    ConvertedDocument,
    Extractor,
    Node,
    RecordCandidate,
    SourceSection,
    SourceSpan,
)

ENTRY_POINT_GROUP = "site2md.extractors.v1"
MANIFEST_NAME = "provider-manifest-v1.json"
SOURCE_MARKER = re.compile(r"^<!-- Source: (?P<source>.+) -->\r?\n?$")


class _PositionedMarkoNode(Protocol):
    """Internal typing view of Marko's source-mapped nodes."""

    source_span: tuple[int, int]


@dataclass(frozen=True)
class ExtractionResult:
    """A validated extraction result with deterministic JSON serialization."""

    payload: Mapping[str, Any]

    def to_json(self) -> str:
        """Serialize the result deterministically as JSON."""
        return json.dumps(
            self.payload,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n"


def extract(markdown: str, extractor_id: str) -> ExtractionResult:
    """Extract validated records from Markdown using one exact Extractor ID."""
    provider = distribution("site2md")
    declaration = _extractor_declaration(provider, extractor_id)
    schema = declaration["record_schema"]["schema"]
    Draft202012Validator.check_schema(schema)

    entry_point = next(
        (
            candidate
            for candidate in provider.entry_points
            if candidate.group == ENTRY_POINT_GROUP and candidate.name == extractor_id
        ),
        None,
    )
    if entry_point is None:
        raise ValueError(f"Unknown Extractor ID: {extractor_id}")

    factory = entry_point.load()
    extractor: Extractor = factory()
    document = _converted_document(markdown)
    provider_result = extractor.extract(document)
    values = [candidate.value for candidate in provider_result.records]
    Draft202012Validator(schema).validate(values)

    payload = _result_payload(
        markdown=markdown,
        document=document,
        records=provider_result.records,
        provider=provider,
        declaration=declaration,
    )
    return ExtractionResult(payload=payload)


def _extractor_declaration(
    provider: Distribution, extractor_id: str
) -> Mapping[str, Any]:
    """Read one Extractor declaration from the provider's static manifest."""
    manifest_files = [
        file
        for file in provider.files or ()
        if Path(str(file)).name == MANIFEST_NAME
    ]
    if len(manifest_files) != 1:
        raise ValueError(f"Provider must contain exactly one {MANIFEST_NAME}")
    manifest_path = provider.locate_file(manifest_files[0])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 1:
        raise ValueError("Provider manifest does not use interface version 1")
    declarations = [
        declaration
        for declaration in manifest.get("extractors", [])
        if declaration.get("id") == extractor_id
    ]
    if len(declarations) != 1:
        raise ValueError(f"Unknown Extractor ID: {extractor_id}")
    return declarations[0]


def _converted_document(markdown: str) -> ConvertedDocument:
    """Translate Marko output into provider-facing site2md nodes."""
    marko_document = marko.Markdown(extensions=["gfm"]).parse(markdown)
    section_nodes: list[list[Node]] = [[]]
    section_sources: list[str | None] = [None]

    for marko_node in marko_document.children:
        marker_source = _source_marker(markdown, marko_node)
        if marker_source is not None:
            if not section_nodes[-1] and section_sources[-1] is None:
                section_sources[-1] = marker_source
            else:
                section_nodes.append([])
                section_sources.append(marker_source)
            continue
        if type(marko_node).__name__ == "BlankLine":
            continue
        section_index = len(section_nodes) - 1
        section_nodes[section_index].append(
            _owned_node(markdown, marko_node, section_index)
        )

    sections = tuple(
        SourceSection(source=source, nodes=tuple(nodes))
        for source, nodes in zip(section_sources, section_nodes)
    )
    return ConvertedDocument(sections=sections)


def _source_marker(markdown: str, marko_node: object) -> str | None:
    """Return a standalone source marker's attributed source, if present."""
    if type(marko_node).__name__ != "HTMLBlock":
        return None
    start, end = cast(_PositionedMarkoNode, marko_node).source_span
    match = SOURCE_MARKER.fullmatch(markdown[start:end])
    return match.group("source") if match else None


def _owned_node(markdown: str, marko_node: object, section_index: int) -> Node:
    """Recursively translate one Marko node to a stable owned node."""
    kind = {
        "Heading": "heading",
        "Paragraph": "paragraph",
        "StrongEmphasis": "strong",
        "RawText": "text",
        "LineBreak": "line_break",
        "BlankLine": "blank_line",
    }.get(type(marko_node).__name__, "unknown")
    raw_children = getattr(marko_node, "children", ())
    if isinstance(raw_children, list):
        children = tuple(
            _owned_node(markdown, child, section_index) for child in raw_children
        )
        text = ""
    elif isinstance(raw_children, str):
        children = ()
        text = raw_children
    else:
        children = ()
        text = ""
    attributes: dict[str, int] = {}
    level = getattr(marko_node, "level", None)
    if isinstance(level, int):
        attributes["level"] = level
    start, end = cast(_PositionedMarkoNode, marko_node).source_span
    return Node(
        kind=kind,
        text=text,
        attributes=attributes,
        children=children,
        span=_source_span(markdown, section_index, start, end),
    )


def _source_span(
    markdown: str, section_index: int, start: int, end: int
) -> SourceSpan:
    """Create a source span from Marko's original-content offsets."""
    return SourceSpan(
        source_section=section_index,
        start=start,
        end=end,
        start_line=markdown.count("\n", 0, start) + 1,
        end_line=markdown.count("\n", 0, max(start, end - 1)) + 1,
    )


def _result_payload(
    *,
    markdown: str,
    document: ConvertedDocument,
    records: tuple[RecordCandidate, ...],
    provider: Distribution,
    declaration: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Construct the host-owned extraction-result envelope."""
    schema = declaration["record_schema"]
    return {
        "format_version": 1,
        "extractor": {
            "id": declaration["id"],
            "interface_version": declaration["interface_version"],
            "implementation_version": declaration["implementation_version"],
        },
        "provider": {
            "distribution": provider.metadata["Name"],
            "version": provider.version,
        },
        "record_schema": {"id": schema["id"], "version": schema["version"]},
        "input_digest": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "source_sections": [
            {"index": index, "source": section.source}
            for index, section in enumerate(document.sections)
        ],
        "records": [
            {
                "value": candidate.value,
                "provenance": _provenance(candidate, document),
            }
            for candidate in records
        ],
        "diagnostics": [],
    }


def _provenance(
    candidate: RecordCandidate, document: ConvertedDocument
) -> Mapping[str, Any]:
    """Serialize the primary source span for a record."""
    span = candidate.provenance[0]
    section = document.sections[span.source_section]
    return {
        "source_section": span.source_section,
        "source": section.source,
        "start": span.start,
        "end": span.end,
        "start_line": span.start_line,
        "end_line": span.end_line,
    }
