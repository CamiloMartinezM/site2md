"""Version-one public interface for trusted Extractor providers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, Union

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

    def plain_text(self) -> str:
        """Return the visible text beneath this node."""
        if self.text:
            return self.text
        return "".join(child.plain_text() for child in self.children)


@dataclass(frozen=True)
class SourceSection:
    """An ordered portion of converted Markdown with source attribution."""

    source: str | None
    nodes: tuple[Node, ...]


@dataclass(frozen=True)
class ConvertedDocument:
    """The complete provider-facing interpretation of converted Markdown."""

    sections: tuple[SourceSection, ...]


@dataclass(frozen=True)
class RecordCandidate:
    """A provider-produced value linked to its source evidence."""

    value: Mapping[str, JsonValue]
    provenance: tuple[SourceSpan, ...]


@dataclass(frozen=True)
class Extraction:
    """Ordered record candidates returned by an Extractor."""

    records: tuple[RecordCandidate, ...]


class Extractor(Protocol):
    """Interpret one complete converted document."""

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return record candidates from the complete document."""
        ...
