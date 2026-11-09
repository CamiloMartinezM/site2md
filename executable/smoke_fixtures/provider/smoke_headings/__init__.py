"""A minimal Extractor provider for the executable's smoke test: one record per heading."""

from __future__ import annotations

from site2md.extractors.v1 import (
    ConvertedDocument,
    Extraction,
    Extractor,
    RecordCandidate,
)


class Headings:
    """Return the text of every heading as one record."""

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return one record candidate per non-empty heading, in document order."""
        records = tuple(
            RecordCandidate(value={"name": document.plain_text(node).strip()}, provenance=(node.span,))
            for node in document.walk()
            if node.kind == "heading" and document.plain_text(node).strip()
        )
        return Extraction(records=records)


def create_extractor() -> Extractor:
    """Return a fresh Extractor."""
    return Headings()
