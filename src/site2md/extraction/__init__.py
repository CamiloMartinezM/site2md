"""Caller-facing structured extraction operation."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from html.entities import html5
from importlib.metadata import Distribution, EntryPoint, distributions
from pathlib import Path
from typing import Any, Literal, Protocol, cast

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
EXTRACTOR_ID = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)+$")

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


class ExtractionError(Exception):
    """A structured failure while resolving or running an Extractor."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        providers: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.providers = providers


@dataclass(frozen=True)
class ExtractorInfo:
    """Static information about one installed Extractor declaration."""

    id: str
    status: Literal["available", "conflict", "unavailable"]
    provider_distribution: str
    provider_version: str
    implementation_version: str | None
    record_schema_id: str | None
    record_schema_version: str | None
    record_schema: Mapping[str, Any]
    detail: str


@dataclass(frozen=True)
class _DiscoveredExtractor:
    """Internal static discovery record retaining its lazy entry point."""

    info: ExtractorInfo
    provider: Distribution
    entry_point: EntryPoint | None
    declaration: Mapping[str, Any] | None
    failure_code: str | None = None


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


def list_extractors() -> tuple[ExtractorInfo, ...]:
    """Return deterministic static information about installed Extractors."""
    return tuple(item.info for item in _discover_extractors())


def extract(markdown: str, extractor_id: str) -> ExtractionResult:
    """Extract validated records from Markdown using one exact Extractor ID."""
    selected = _selected_extractor(extractor_id)
    provider = selected.provider
    declaration = selected.declaration
    entry_point = selected.entry_point
    if declaration is None or entry_point is None:
        raise AssertionError("Available Extractor lacks static discovery metadata")
    schema = declaration["record_schema"]["schema"]
    Draft202012Validator.check_schema(schema)

    try:
        factory = entry_point.load()
    except Exception as cause:
        raise ExtractionError(
            "site2md.extractor_import_failed",
            f"Could not import Extractor {extractor_id}: {cause}",
        ) from cause
    if not callable(factory):
        interface_cause = TypeError("Extractor entry point is not a callable factory")
        raise ExtractionError(
            "site2md.extractor_interface_invalid",
            f"Extractor {extractor_id} does not expose a callable factory",
        ) from interface_cause
    try:
        extractor: Extractor = factory()
    except Exception as cause:
        raise ExtractionError(
            "site2md.extractor_factory_failed",
            f"Extractor factory {extractor_id} failed: {cause}",
        ) from cause
    if not callable(getattr(extractor, "extract", None)):
        interface_cause = TypeError(
            "Extractor factory result has no callable extract method"
        )
        raise ExtractionError(
            "site2md.extractor_interface_invalid",
            f"Extractor factory {extractor_id} returned an incompatible object",
        ) from interface_cause
    document = _converted_document(markdown)
    try:
        provider_result = extractor.extract(document)
    except Exception as cause:
        raise ExtractionError(
            "site2md.extractor_execution_failed",
            f"Extractor {extractor_id} failed: {cause}",
        ) from cause
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


def _selected_extractor(extractor_id: str) -> _DiscoveredExtractor:
    """Resolve one exact, statically valid, unambiguous Extractor."""
    if EXTRACTOR_ID.fullmatch(extractor_id) is None:
        raise ExtractionError(
            "site2md.extractor_unknown",
            f"Unknown Extractor ID: {extractor_id}",
        )
    matches = [item for item in _discover_extractors() if item.info.id == extractor_id]
    if not matches:
        raise ExtractionError(
            "site2md.extractor_unknown",
            f"Unknown Extractor ID: {extractor_id}",
        )
    selected = matches[0]
    if selected.info.status == "conflict":
        providers = tuple(
            f"{item.info.provider_distribution} {item.info.provider_version}"
            for item in matches
        )
        provider_list = ", ".join(providers)
        raise ExtractionError(
            "site2md.extractor_conflict",
            f"Extractor ID {extractor_id} is claimed by: {provider_list}",
            providers=providers,
        )
    if selected.info.status == "unavailable":
        raise ExtractionError(
            selected.failure_code or "site2md.extractor_unavailable",
            f"Extractor {extractor_id} is unavailable: {selected.info.detail}",
        )
    return selected


def _discover_extractors() -> tuple[_DiscoveredExtractor, ...]:
    """Inspect installed distribution metadata without importing provider code."""
    discovered: list[_DiscoveredExtractor] = []
    for provider in distributions():
        metadata_errors: list[str] = []
        try:
            entry_points = tuple(
                entry_point
                for entry_point in provider.entry_points
                if entry_point.group == ENTRY_POINT_GROUP
            )
        except Exception as cause:
            entry_points = ()
            metadata_errors.append(f"entry-point metadata could not be read: {cause}")
        try:
            manifest_files = tuple(
                file
                for file in provider.files or ()
                if Path(str(file)).name == MANIFEST_NAME
            )
        except Exception as cause:
            manifest_files = ()
            metadata_errors.append(f"installed file metadata could not be read: {cause}")
        if not entry_points and not manifest_files:
            continue
        discovered.extend(
            _inspect_provider(
                provider,
                entry_points,
                manifest_files,
                metadata_errors,
            )
        )

    by_id: dict[str, list[int]] = {}
    for index, item in enumerate(discovered):
        by_id.setdefault(item.info.id, []).append(index)
    for indexes in by_id.values():
        if len(indexes) < 2:
            continue
        providers = sorted(
            (
                f"{discovered[index].info.provider_distribution} "
                f"{discovered[index].info.provider_version}"
                for index in indexes
            ),
            key=str.casefold,
        )
        detail = f"claimed by multiple providers: {', '.join(providers)}"
        for index in indexes:
            item = discovered[index]
            discovered[index] = replace(
                item,
                info=replace(item.info, status="conflict", detail=detail),
                failure_code="site2md.extractor_conflict",
            )
    return tuple(sorted(discovered, key=_discovery_sort_key))


def _inspect_provider(
    provider: Distribution,
    entry_points: tuple[EntryPoint, ...],
    manifest_files: tuple[object, ...],
    metadata_errors: list[str],
) -> list[_DiscoveredExtractor]:
    """Validate one provider's static manifest against its entry points."""
    errors = list(metadata_errors)
    try:
        provider_name = provider.metadata.get("Name")
    except Exception as cause:
        provider_name = None
        errors.append(f"provider distribution metadata could not be read: {cause}")
    if not provider_name:
        provider_name = "<unknown provider>"
        errors.append("provider distribution name is missing")
    try:
        provider_version = provider.version
    except Exception as cause:
        provider_version = None
        errors.append(f"provider distribution version could not be read: {cause}")
    if not provider_version:
        provider_version = "<unknown version>"
        errors.append("provider distribution version is missing")
    declarations: list[Mapping[str, Any]] = []

    if len(manifest_files) != 1:
        errors.append(f"provider must contain exactly one {MANIFEST_NAME}")
    else:
        try:
            manifest_path = provider.locate_file(manifest_files[0])  # type: ignore[arg-type]
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as cause:
            errors.append(f"provider manifest could not be read: {cause}")
        else:
            if not isinstance(manifest, Mapping):
                errors.append("provider manifest must be a JSON object")
            else:
                if type(manifest.get("manifest_version")) is not int or manifest.get(
                    "manifest_version"
                ) != 1:
                    errors.append("provider manifest does not use manifest version 1")
                raw_declarations = manifest.get("extractors")
                if not isinstance(raw_declarations, list) or not raw_declarations:
                    errors.append("provider manifest must declare at least one Extractor")
                else:
                    for declaration in raw_declarations:
                        if isinstance(declaration, Mapping):
                            declarations.append(declaration)
                        else:
                            errors.append("every Extractor declaration must be an object")

    entry_point_ids = [entry_point.name for entry_point in entry_points]
    declaration_ids: list[str] = []
    for declaration in declarations:
        declaration_id = declaration.get("id")
        if isinstance(declaration_id, str):
            declaration_ids.append(declaration_id)
    if len(entry_point_ids) != len(set(entry_point_ids)):
        errors.append("provider has duplicate Extractor entry-point names")
    if len(declaration_ids) != len(set(declaration_ids)):
        errors.append("provider has duplicate Extractor declarations")
    if set(entry_point_ids) != set(declaration_ids):
        errors.append("manifest Extractor IDs do not agree with entry-point names")

    ids = sorted(set(entry_point_ids) | set(declaration_ids))
    if not ids:
        ids = ["<unknown>"]
    results: list[_DiscoveredExtractor] = []
    for extractor_id in ids:
        item_errors = list(errors)
        if EXTRACTOR_ID.fullmatch(extractor_id) is None:
            item_errors.append(
                "Extractor ID must be lowercase and provider-qualified"
            )
        matching_declarations = [
            declaration
            for declaration in declarations
            if declaration.get("id") == extractor_id
        ]
        matching_entry_points = [
            entry_point
            for entry_point in entry_points
            if entry_point.name == extractor_id
        ]
        declaration = (
            matching_declarations[0] if len(matching_declarations) == 1 else None
        )
        entry_point = (
            matching_entry_points[0] if len(matching_entry_points) == 1 else None
        )
        failure_code = "site2md.extractor_unavailable"
        if declaration is not None:
            declaration_errors, unsupported = _declaration_errors(declaration)
            item_errors.extend(declaration_errors)
            if unsupported and len(declaration_errors) == 1 and not errors:
                failure_code = "site2md.extractor_unsupported"
        if entry_point is None:
            item_errors.append("Extractor must have exactly one matching entry point")

        implementation_version, schema_id, schema_version, schema = (
            _declaration_information(declaration)
        )
        status: Literal["available", "unavailable"] = (
            "unavailable" if item_errors else "available"
        )
        info = ExtractorInfo(
            id=extractor_id,
            status=status,
            provider_distribution=provider_name,
            provider_version=provider_version,
            implementation_version=implementation_version,
            record_schema_id=schema_id,
            record_schema_version=schema_version,
            record_schema=schema,
            detail="; ".join(dict.fromkeys(item_errors)),
        )
        results.append(
            _DiscoveredExtractor(
                info=info,
                provider=provider,
                entry_point=entry_point,
                declaration=declaration,
                failure_code=failure_code if item_errors else None,
            )
        )
    return results


def _declaration_errors(
    declaration: Mapping[str, Any],
) -> tuple[list[str], bool]:
    """Return static shape and interface errors for one declaration."""
    errors: list[str] = []
    interface_version = declaration.get("interface_version")
    unsupported = type(interface_version) is int and interface_version != 1
    if type(interface_version) is not int:
        errors.append("Extractor interface version must be an integer")
    elif interface_version != 1:
        errors.append(f"unsupported Extractor interface version {interface_version}")
    if not isinstance(declaration.get("implementation_version"), str) or not declaration.get(
        "implementation_version"
    ):
        errors.append("Extractor implementation version must be a nonempty string")
    record_schema = declaration.get("record_schema")
    if not isinstance(record_schema, Mapping):
        errors.append("record schema declaration must be an object")
    else:
        if not isinstance(record_schema.get("id"), str) or not record_schema.get("id"):
            errors.append("record schema ID must be a nonempty string")
        if not isinstance(record_schema.get("version"), str) or not record_schema.get(
            "version"
        ):
            errors.append("record schema version must be a nonempty string")
        if not isinstance(record_schema.get("schema"), Mapping):
            errors.append("record schema must be a JSON object")
    return errors, unsupported


def _declaration_information(
    declaration: Mapping[str, Any] | None,
) -> tuple[str | None, str | None, str | None, Mapping[str, Any]]:
    """Extract public listing fields from one declaration when present."""
    if declaration is None:
        return None, None, None, {}
    implementation_version = declaration.get("implementation_version")
    record_schema = declaration.get("record_schema")
    if not isinstance(record_schema, Mapping):
        return (
            implementation_version if isinstance(implementation_version, str) else None,
            None,
            None,
            {},
        )
    schema_id = record_schema.get("id")
    schema_version = record_schema.get("version")
    schema = record_schema.get("schema")
    return (
        implementation_version if isinstance(implementation_version, str) else None,
        schema_id if isinstance(schema_id, str) else None,
        schema_version if isinstance(schema_version, str) else None,
        schema if isinstance(schema, Mapping) else {},
    )


def _discovery_sort_key(item: _DiscoveredExtractor) -> tuple[str, str, str]:
    """Return the stable ordering key for public Extractor information."""
    return (
        item.info.id,
        item.info.provider_distribution.casefold(),
        item.info.provider_version,
    )


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
