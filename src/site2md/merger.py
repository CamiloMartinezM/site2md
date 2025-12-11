from pathlib import Path
from typing import List

def merge_markdowns(markdown_contents: List[str], output_path: Path) -> None:
    """
    Concatenates a list of Markdown strings into a single file.

    Args:
        markdown_contents: List of markdown strings.
        output_path: Path to the output file.
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            for content in markdown_contents:
                f.write(content)
                f.write("\n\n---\n\n") # Horizontal rule as page break
    except Exception as e:
        print(f"Error writing to {output_path}: {e}")
