"""Version-one public interface for trusted Extractor providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol, Union

JsonScalar = Union[None, bool, int, float, str]
JsonValue = Union[JsonScalar, Sequence["JsonValue"], Mapping[str, "JsonValue"]]


@dataclass(frozen=True)
class SourceSpan:
    """Locate content within one source section of a converted document."""

    source_section: int
    start: int
    end: int
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Node:
    """A host-owned Markdown node that does not expose the Markdown engine."""

    kind: str
    text: str
    attributes: Mapping[str, JsonValue]
    children: tuple[Node, ...]
    span: SourceSpan

    def __post_init__(self) -> None:
        """Freeze nested provider-visible collections."""
        object.__setattr__(self, "attributes", _immutable_mapping(self.attributes))
        object.__setattr__(self, "children", tuple(self.children))

    def plain_text(self) -> str:
        """Return the visible text beneath this node."""
        if self.kind == "html":
            return ""
        if self.text:
            return self.text
        return "".join(child.plain_text() for child in self.children)


@dataclass(frozen=True)
class SourceSection:
    """An ordered portion of a converted document with source attribution."""

    source: str | None
    nodes: tuple[Node, ...]

    def __post_init__(self) -> None:
        """Freeze the section's ordered nodes."""
        object.__setattr__(self, "nodes", tuple(self.nodes))


@dataclass(frozen=True)
class ConvertedDocument:
    """The complete provider-facing converted document."""

    sections: tuple[SourceSection, ...]
    _markdown: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        """Freeze the document's ordered source sections."""
        object.__setattr__(self, "sections", tuple(self.sections))

    def walk(self, node: Node | None = None) -> tuple[Node, ...]:
        """Return nodes in depth-first document order, optionally below one node."""
        roots = (node,) if node is not None else tuple(
            root for section in self.sections for root in section.nodes
        )
        walked: list[Node] = []
        pending = list(reversed(roots))
        while pending:
            current = pending.pop()
            walked.append(current)
            pending.extend(reversed(current.children))
        return tuple(walked)

    def plain_text(self, node: Node) -> str:
        """Return the visible text beneath one provider-visible node."""
        return node.plain_text()

    def source_text(self, span: SourceSpan) -> str:
        """Return the exact original Markdown covered by a source span."""
        return self._markdown[span.start : span.end]

    def covering_span(self, first: Node, last: Node) -> SourceSpan:
        """Return the span covering two ordered nodes in one source section."""
        if first.span.source_section != last.span.source_section:
            raise ValueError("Cannot cover nodes from different source sections")
        if first.span.start > last.span.end:
            raise ValueError("Cannot cover nodes outside document order")
        return SourceSpan(
            source_section=first.span.source_section,
            start=first.span.start,
            end=last.span.end,
            start_line=first.span.start_line,
            end_line=last.span.end_line,
        )


@dataclass(frozen=True)
class RecordCandidate:
    """A provider-produced value linked to its source evidence."""

    value: Mapping[str, JsonValue]
    provenance: tuple[SourceSpan, ...]

    def __post_init__(self) -> None:
        """Freeze the candidate's ordered provenance spans."""
        object.__setattr__(self, "provenance", tuple(self.provenance))


@dataclass(frozen=True)
class Diagnostic:
    """A provider warning or error with optional ordered provenance."""

    severity: Literal["warning", "error"]
    code: str
    message: str
    provenance: tuple[SourceSpan, ...] = ()

    def __post_init__(self) -> None:
        """Freeze the diagnostic's ordered provenance spans."""
        object.__setattr__(self, "provenance", tuple(self.provenance))


@dataclass(frozen=True)
class Extraction:
    """Ordered record candidates returned by an Extractor."""

    records: tuple[RecordCandidate, ...]
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        """Freeze ordered provider output collections."""
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))


class Extractor(Protocol):
    """Interpret one complete converted document."""

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return record candidates from the complete document."""
        ...


def _immutable_mapping(values: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """Return a deeply immutable provider-visible JSON mapping."""
    return MappingProxyType(
        {key: _immutable_json_value(value) for key, value in values.items()}
    )


def _immutable_json_value(value: JsonValue) -> JsonValue:
    """Freeze nested mappings and sequences without changing scalar values."""
    if isinstance(value, Mapping):
        return _immutable_mapping(value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(_immutable_json_value(item) for item in value)
    return value
