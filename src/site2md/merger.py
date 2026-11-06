"""Module for merging multiple Markdown contents into a single file"""

from __future__ import annotations

from pathlib import Path


def merge_markdowns(markdown_contents: list[str], output_path: Path) -> None:
    """Concatenates a list of Markdown strings into a single file.

    Args:
        markdown_contents: List of markdown strings.
        output_path: Path to the output file.

    Raises:
        OSError: If the output file cannot be written.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        for content in markdown_contents:
            f.write(content)
            f.write("\n\n---\n\n")  # Horizontal rule as page break
