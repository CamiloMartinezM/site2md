"""Module for merging multiple Markdown contents into a single file"""

from __future__ import annotations

import os
from pathlib import Path


def merge_markdowns(markdown_contents: list[str], output_path: Path) -> bytes:
    """Concatenates a list of Markdown strings into a single file.

    Args:
        markdown_contents: List of markdown strings.
        output_path: Path to the output file.

    Returns:
        The bytes written, so that a caller needn't read the file back.

    Raises:
        OSError: If the output file cannot be written.
    """
    # A horizontal rule after each page is the page break. The line endings are the ones a text-mode write stores.
    merged = "".join(f"{content}\n\n---\n\n" for content in markdown_contents)
    document = merged.replace("\n", os.linesep).encode("utf-8")
    output_path.write_bytes(document)
    return document
