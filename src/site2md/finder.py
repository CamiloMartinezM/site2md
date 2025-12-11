"""Module for finding and sorting HTML files within directories."""

from pathlib import Path


def find_html_files(root_dir: Path) -> list[Path]:
    """Finds and sorts HTML files in the given directory.

    **Strategy:**
    1. `'index.html'` first.
    2. Other root .html files (alphabetical).
    3. Subdirectories recursively (directory name alphabetical, then filename).

    Args:
        root_dir: The root directory to search.

    Returns:
        A list of Path objects to the HTML files in the desired order.
    """
    html_files = []

    # helper for sorting
    def sort_key(p: Path):
        return p.name.lower()

    # 1. Root index.html
    index_file = root_dir / "index.html"
    if index_file.exists():
        html_files.append(index_file)

    # 2. Other root HTML files
    root_files = [p for p in root_dir.glob("*.html") if p.name != "index.html" and p.is_file()]
    html_files.extend(sorted(root_files, key=sort_key))

    # 3. Subdirectories (recursive)
    # Sort subdirectories alphabetically to ensure consistent order
    subdirs = sorted(
        [d for d in root_dir.iterdir() if d.is_dir() and not d.name.startswith(".")], key=sort_key
    )

    for subdir in subdirs:
        # Recursively find files in subdirectories
        # Using rglob locally within the subdir ensures we capture nested files.
        # Let's try to get all html files in this subdir and its children
        subdir_files = sorted(
            subdir.rglob("*.html"), key=lambda p: str(p.relative_to(root_dir)).lower()
        )
        html_files.extend(subdir_files)

    return html_files
