"""Implement the extractors command."""

from __future__ import annotations

from rich.console import Console

from site2md.extraction import list_extractors

console = Console()


def extractors() -> None:
    """List installed Extractors using static provider metadata."""
    headers = (
        "ID",
        "Status",
        "Provider",
        "Extractor version",
        "Record schema",
        "Details",
    )
    rows: list[tuple[str, ...]] = []
    for info in list_extractors():
        provider = f"{info.provider_distribution} {info.provider_version}"
        record_schema = ""
        if info.record_schema_id is not None:
            record_schema = info.record_schema_id
            if info.record_schema_version is not None:
                record_schema += f" {info.record_schema_version}"
        rows.append(
            (
                info.id,
                info.status,
                provider,
                info.implementation_version or "",
                record_schema,
                info.detail,
            )
        )
    widths = tuple(
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    )
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in rows
    )
    console.print("\n".join(lines), markup=False, soft_wrap=True)
