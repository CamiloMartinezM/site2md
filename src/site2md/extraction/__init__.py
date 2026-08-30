"""Caller-facing structured extraction operation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from html.entities import html5
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
SOURCE_MARKER = re.compile(
    r"^[ \t]{0,3}<!-- Source: (?P<source>.+?) -->[ \t]*(?:\r\n|\r|\n)?$"
)
ENTITY_REFERENCE = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]{1,31});"
)
LINE_ENDING = re.compile(r"\r\n?|\n")

NODE_KINDS = {
    "Heading": "heading",
    "SetextHeading": "heading",
    "Paragraph": "paragraph",
    "Quote": "quote",
    "List": "list",
    "ListItem": "list_item",
    "ThematicBreak": "thematic_break",
    "HTMLBlock": "html",
    "StrongEmphasis": "strong",
    "Emphasis": "emphasis",
    "RawText": "text",
    "Literal": "text",
    "LineBreak": "line_break",
    "InlineHTML": "html",
    "Link": "link",
    "AutoLink": "link",
    "Url": "link",
    "Image": "image",
    "CodeSpan": "code",
    "CodeBlock": "code_block",
    "FencedCode": "code_block",
    "Strikethrough": "strikethrough",
    "Table": "table",
    "TableRow": "table_row",
    "TableCell": "table_cell",
    "BlankLine": "blank_line",
}


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
    normalized, original_offsets = _normalize_markdown(markdown)
    marko_document = marko.Markdown(extensions=["gfm"]).parse(normalized)
    section_nodes: list[list[Node]] = [[]]
    section_sources: list[str | None] = [None]
    section_has_markdown = [False]

    for marko_node in marko_document.children:
        marker_source = _source_marker(markdown, original_offsets, marko_node)
        if marker_source is not None:
            if not section_has_markdown[-1] and section_sources[-1] is None:
                section_sources[-1] = marker_source
            else:
                section_nodes.append([])
                section_sources.append(marker_source)
                section_has_markdown.append(False)
            continue
        section_has_markdown[-1] = True
        if type(marko_node).__name__ == "BlankLine":
            continue
        section_index = len(section_nodes) - 1
        section_nodes[section_index].append(
            _owned_node(markdown, original_offsets, marko_node, section_index)
        )

    sections = tuple(
        SourceSection(source=source, nodes=tuple(nodes))
        for source, nodes in zip(section_sources, section_nodes)
    )
    return ConvertedDocument(sections=sections, _markdown=markdown)


def _normalize_markdown(markdown: str) -> tuple[str, tuple[int, ...]]:
    """Normalize Marko input while retaining normalized-to-original offsets."""
    normalized: list[str] = []
    original_offsets = [0]
    original_index = 0
    while original_index < len(markdown):
        character = markdown[original_index]
        if character == "\r" and markdown[original_index : original_index + 2] == "\r\n":
            normalized.append("\n")
            original_index += 2
        else:
            if character in {"\r", "\f"}:
                character = "\n"
            elif character == "\x00":
                character = "�"
            normalized.append(character)
            original_index += 1
        original_offsets.append(original_index)
    return "".join(normalized), tuple(original_offsets)


def _source_marker(
    markdown: str, original_offsets: tuple[int, ...], marko_node: object
) -> str | None:
    """Return a standalone source marker's attributed source, if present."""
    if type(marko_node).__name__ != "HTMLBlock":
        return None
    start, end = cast(_PositionedMarkoNode, marko_node).source_span
    match = SOURCE_MARKER.fullmatch(
        markdown[original_offsets[start] : original_offsets[end]]
    )
    return match.group("source") if match else None


def _owned_node(
    markdown: str,
    original_offsets: tuple[int, ...],
    marko_node: object,
    section_index: int,
) -> Node:
    """Recursively translate one Marko node to a stable owned node."""
    node_type = type(marko_node).__name__
    kind = NODE_KINDS.get(node_type, "unknown")
    raw_children = getattr(marko_node, "children", ())
    children: tuple[Node, ...]
    if node_type == "HTMLBlock":
        children = ()
        body = getattr(marko_node, "body", "")
        text = body if isinstance(body, str) else ""
    elif node_type in {"CodeBlock", "FencedCode"}:
        children = ()
        text = _code_text(raw_children)
    elif isinstance(raw_children, list):
        children = tuple(
            _owned_node(markdown, original_offsets, child, section_index)
            for child in raw_children
            if getattr(child, "source_span", None) is not None
        )
        text = ""
    elif isinstance(raw_children, str):
        children = ()
        text = _node_text(node_type, raw_children)
    else:
        children = ()
        text = ""
    attributes: dict[str, Any] = {}
    level = getattr(marko_node, "level", None)
    if isinstance(level, int):
        attributes["level"] = level
    if node_type == "List":
        attributes.update(
            ordered=bool(getattr(marko_node, "ordered", False)),
            start=getattr(marko_node, "start", 1),
            tight=bool(getattr(marko_node, "tight", False)),
        )
    if node_type == "LineBreak":
        attributes["soft"] = bool(getattr(marko_node, "soft", False))
    checked = getattr(marko_node, "checked", None)
    if isinstance(checked, bool):
        attributes["checked"] = checked
    if node_type in {"Link", "AutoLink", "Url", "Image"}:
        attributes["destination"] = _decode_entities(
            str(getattr(marko_node, "dest", ""))
        )
        title = getattr(marko_node, "title", None)
        if isinstance(title, str) and title:
            attributes["title"] = _decode_entities(title)
    if node_type in {"CodeBlock", "FencedCode"}:
        language = getattr(marko_node, "lang", "")
        if isinstance(language, str) and language:
            attributes["language"] = _decode_entities(language)
    if node_type == "TableCell":
        attributes["header"] = bool(getattr(marko_node, "header", False))
        alignment = getattr(marko_node, "align", None)
        if isinstance(alignment, str):
            attributes["alignment"] = alignment
    start, end = cast(_PositionedMarkoNode, marko_node).source_span
    return Node(
        kind=kind,
        text=text,
        attributes=attributes,
        children=children,
        span=_source_span(
            markdown,
            original_offsets,
            section_index,
            start,
            end,
        ),
    )


def _code_text(raw_children: object) -> str:
    """Return the semantic text stored by a Marko code block."""
    if isinstance(raw_children, list) and len(raw_children) == 1:
        text = getattr(raw_children[0], "children", "")
        if isinstance(text, str):
            return text
    return ""


def _node_text(node_type: str, text: str) -> str:
    """Return semantic leaf text without Markdown escape or entity syntax."""
    if node_type == "LineBreak":
        return "\n"
    if node_type in {"RawText", "Literal"}:
        return _decode_entities(text)
    return text


def _decode_entities(text: str) -> str:
    """Decode complete, defined CommonMark entity references in text."""
    return ENTITY_REFERENCE.sub(_decode_entity, text)


def _decode_entity(match: re.Match[str]) -> str:
    """Decode one complete CommonMark entity reference when it is defined."""
    reference = match.group()
    if reference.startswith("&#"):
        return html.unescape(reference)
    return html5.get(reference[1:], reference)


def _source_span(
    markdown: str,
    original_offsets: tuple[int, ...],
    section_index: int,
    normalized_start: int,
    normalized_end: int,
) -> SourceSpan:
    """Create a source span from Marko's original-content offsets."""
    start = original_offsets[normalized_start]
    end = original_offsets[normalized_end]
    return SourceSpan(
        source_section=section_index,
        start=start,
        end=end,
        start_line=_line_number(markdown, start),
        end_line=_line_number(markdown, max(start, end - 1)),
    )


def _line_number(markdown: str, offset: int) -> int:
    """Return the one-based line containing one original character offset."""
    line = 1
    for line_ending in LINE_ENDING.finditer(markdown):
        if line_ending.end() > offset:
            break
        line += 1
    return line


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
    """Serialize ordered source spans with the first span as primary."""
    primary = dict(_span_payload(candidate.provenance[0], document))
    primary["spans"] = [
        _span_payload(span, document) for span in candidate.provenance
    ]
    return primary


def _span_payload(
    span: SourceSpan, document: ConvertedDocument
) -> Mapping[str, Any]:
    """Serialize one source span with its source attribution."""
    section = document.sections[span.source_section]
    return {
        "source_section": span.source_section,
        "source": section.source,
        "start": span.start,
        "end": span.end,
        "start_line": span.start_line,
        "end_line": span.end_line,
    }
