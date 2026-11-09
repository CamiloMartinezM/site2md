"""Implement the extract command."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import cyclopts

from site2md.file_extraction import FileExtractionError, extract_markdown_file


def _extract_failure(message: str) -> NoReturn:
    """Report one concise extraction-command failure."""
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def extract(
    extractor_id: str,
    input_source: Annotated[
        str, cyclopts.Parameter(allow_leading_hyphen=True)
    ],
    *,
    output: Path | None = None,
    entry_points_only: bool = False,
    values_only: bool = False,
) -> None:
    """Extract structured records from a Markdown file or standard input.

    Args:
        values_only: Write only a JSON array of the record values, in record order. This drops
            the format version, the provenance, the Extractor, provider and record schema
            identity, the input digest, the source sections and the diagnostics. Warnings then
            go only to standard error.
        entry_points_only: Look up the Extractor faster by skipping installed distributions
            that declare no Extractor entry point. Extract then doesn't notice a distribution
            that ships a manifest without an entry point, though site2md extractors still
            reports it.
    """
    if output is not None and not output.parent.is_dir():
        _extract_failure(f"output folder does not exist: {output.parent}")
    try:
        warnings = extract_markdown_file(
            extractor_id,
            None if input_source == "-" else Path(input_source),
            output=output,
            entry_points_only=entry_points_only,
            values_only=values_only,
        )
    except FileExtractionError as error:
        for line in error.lines:
            print(line, file=sys.stderr)
        raise SystemExit(1) from None
    for line in warnings:
        print(line, file=sys.stderr)
