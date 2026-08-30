"""Built-in Extractor for Scrape This Site country Markdown."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from site2md.extractors.v1 import (
    ConvertedDocument,
    Extraction,
    Extractor,
    Node,
    RecordCandidate,
    SourceSpan,
)

LABELS = ("Capital:", "Population:", "Area (km2):")


class CountriesExtractor:
    """Extract country records from converted training-page Markdown."""

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return the country candidates in source order."""
        records = []
        for section in document.sections:
            for index, node in enumerate(section.nodes[:-1]):
                paragraph = section.nodes[index + 1]
                if not _is_country_start(node, paragraph):
                    continue
                values = _labeled_values(paragraph)
                records.append(
                    RecordCandidate(
                        value={
                            "name": node.plain_text().strip(),
                            "capital": _capital(values["Capital:"]),
                            "population": int(values["Population:"]),
                            "area_km2": _area(values["Area (km2):"]),
                        },
                        provenance=(_covering_span(node.span, paragraph.span),),
                    )
                )
        return Extraction(records=tuple(records))


def create_extractor() -> Extractor:
    """Return a fresh version-one country Extractor."""
    return CountriesExtractor()


def _is_country_start(heading: Node, paragraph: Node) -> bool:
    """Return whether two adjacent nodes begin a country record."""
    if heading.kind != "heading" or heading.attributes.get("level") != 3:
        return False
    if paragraph.kind != "paragraph":
        return False
    strong_text = {
        child.plain_text().strip() for child in paragraph.children if child.kind == "strong"
    }
    return bool(strong_text.intersection(LABELS))


def _labeled_values(paragraph: Node) -> dict[str, str]:
    """Read required values following their exact strong labels."""
    values: dict[str, str] = {}
    children = paragraph.children
    for index, child in enumerate(children):
        label = child.plain_text().strip()
        if child.kind != "strong" or label not in LABELS:
            continue
        value_parts = []
        for following in children[index + 1 :]:
            if following.kind in {"strong", "line_break"}:
                break
            value_parts.append(following.plain_text())
        values[label] = "".join(value_parts).strip()

    missing = [label for label in LABELS if label not in values]
    if missing:
        raise ValueError(f"Country record is missing labels: {', '.join(missing)}")
    return values


def _capital(value: str) -> str | None:
    """Normalize the source's missing-capital sentinel."""
    return None if value == "None" else value


def _area(value: str) -> float:
    """Parse decimal or exponent-form square kilometers."""
    try:
        return float(Decimal(value))
    except InvalidOperation as error:
        raise ValueError(f"Invalid country area: {value}") from error


def _covering_span(first: SourceSpan, last: SourceSpan) -> SourceSpan:
    """Cover adjacent nodes from one source section."""
    return SourceSpan(
        source_section=first.source_section,
        start=first.start,
        end=last.end,
        start_line=first.start_line,
        end_line=last.end_line,
    )
