"""Built-in Extractor for Scrape This Site country Markdown."""

from __future__ import annotations

import math
import re
from decimal import Decimal, InvalidOperation

from site2md.extractors.v1 import (
    ConvertedDocument,
    Diagnostic,
    Extraction,
    Extractor,
    Node,
    RecordCandidate,
)

LABELS = ("Capital:", "Population:", "Area (km2):")
DECLARED_COUNT = re.compile(r"\b([0-9]+)\s+countries?\b", re.IGNORECASE)
DIAGNOSTIC_PREFIX = "site2md.scrapethissite.countries"


class CountriesExtractor:
    """Extract country records from converted training-page Markdown."""

    def extract(self, document: ConvertedDocument) -> Extraction:
        """Return the country candidates in source order."""
        records = []
        diagnostics = []
        names: set[str] = set()
        for section in document.sections:
            for index, node in enumerate(section.nodes[:-1]):
                paragraph = section.nodes[index + 1]
                if not _is_country_start(node, paragraph):
                    continue
                name = document.plain_text(node).strip()
                values, encountered_labels, unexpected_labels = _labeled_values(
                    paragraph
                )
                if encountered_labels != LABELS:
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            code=f"{DIAGNOSTIC_PREFIX}.reordered-labels",
                            message=f"Country record labels are reordered: {name}",
                            provenance=(paragraph.span,),
                        )
                    )
                for label in unexpected_labels:
                    diagnostics.append(
                        Diagnostic(
                            severity="warning",
                            code=f"{DIAGNOSTIC_PREFIX}.unexpected-label",
                            message=f"Country record has an unexpected label: {label}",
                            provenance=(paragraph.span,),
                        )
                    )
                if name in names:
                    raise ValueError(f"Duplicate country name: {name}")
                names.add(name)
                records.append(
                    RecordCandidate(
                        value={
                            "name": name,
                            "capital": _capital(values["Capital:"]),
                            "population": _population(values["Population:"]),
                            "area_km2": _area(values["Area (km2):"]),
                        },
                        provenance=(document.covering_span(node, paragraph),),
                    )
                )
        _validate_declared_counts(document, len(records))
        return Extraction(records=tuple(records), diagnostics=tuple(diagnostics))


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
        child.plain_text().strip()
        for child in _inline_nodes(paragraph)
        if child.kind == "strong"
    }
    return bool(strong_text.intersection(LABELS))


def _labeled_values(paragraph: Node) -> tuple[dict[str, str], tuple[str, ...], tuple[str, ...]]:
    """Read required values following their exact strong labels."""
    values: dict[str, str] = {}
    encountered_labels = []
    unexpected_labels = []
    children = _inline_nodes(paragraph)
    for index, child in enumerate(children):
        label = child.plain_text().strip()
        if child.kind != "strong":
            continue
        if label not in LABELS:
            unexpected_labels.append(label)
            continue
        if label in values:
            raise ValueError(f"Country record has duplicate label: {label}")
        encountered_labels.append(label)
        value_parts = []
        for following in children[index + 1 :]:
            if following.kind in {"strong", "line_break"}:
                break
            value_parts.append(following.plain_text())
        values[label] = "".join(value_parts).strip()

    missing = [label for label in LABELS if label not in values]
    if missing:
        raise ValueError(f"Country record is missing labels: {', '.join(missing)}")
    return values, tuple(encountered_labels), tuple(unexpected_labels)


def _inline_nodes(node: Node) -> tuple[Node, ...]:
    """Return inline content in source order with strong labels kept atomic."""
    flattened = []
    for child in node.children:
        if child.kind in {"strong", "line_break"} or not child.children:
            flattened.append(child)
        else:
            flattened.extend(_inline_nodes(child))
    return tuple(flattened)


def _capital(value: str) -> str | None:
    """Normalize the source's missing-capital sentinel."""
    return None if value == "None" else value


def _population(value: str) -> int:
    """Parse a country population as an integer."""
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Invalid country population: {value}") from error


def _area(value: str) -> float:
    """Parse decimal or exponent-form square kilometers."""
    try:
        area = float(Decimal(value))
    except InvalidOperation as error:
        raise ValueError(f"Invalid country area: {value}") from error
    if not math.isfinite(area):
        raise ValueError(f"Invalid country area: {value}")
    return area


def _validate_declared_counts(document: ConvertedDocument, record_count: int) -> None:
    """Reject H1 country counts that disagree with valid candidates."""
    for section in document.sections:
        for node in section.nodes:
            if node.kind != "heading" or node.attributes.get("level") != 1:
                continue
            match = DECLARED_COUNT.search(document.plain_text(node))
            if match is None:
                continue
            declared_count = int(match.group(1))
            if declared_count != record_count:
                raise ValueError(
                    "Declared country count "
                    f"{declared_count} does not match {record_count} candidates"
                )
