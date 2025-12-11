from pathlib import Path
from typing import List

def find_html_files(root_dir: Path) -> List[Path]:
    """
    Finds and sorts HTML files in the given directory.

    Strategy:
    1. 'index.html' fits first.
    2. Then all other .html files in the root directory, sorted alphabetically.
    3. Then recursively find .html files in subdirectories, sorted alphabetically by directory name, then filename.
    
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
    root_files = [
        p for p in root_dir.glob("*.html") 
        if p.name != "index.html" and p.is_file()
    ]
    html_files.extend(sorted(root_files, key=sort_key))

    # 3. Subdirectories (recursive)
    # We want to traverse directories in alphabetical order
    # Note: Path.rglob returns a generator that doesn't guarantee order, so we might want to do manual walk or sort.
    # However, creating a custom recursive walker is safer for controlling order.
    
    subdirs = sorted([d for d in root_dir.iterdir() if d.is_dir() and not d.name.startswith('.')], key=sort_key)
    
    for subdir in subdirs:
        # Recursively find files in subdirectories
        # Using rglob locally within the subdir to easily flatten, but we want to maintain folder structure order
        # So let's actually just crawl recursively with our own function to ensure directory-first sorting?
        # A simpler approach: use rglob("*") and then sort by full path string?
        # No, sorting by full path string keeps folders together.
        
        # Let's try to get all html files in this subdir and its children
        subdir_files = sorted(subdir.rglob("*.html"), key=lambda p: str(p.relative_to(root_dir)).lower())
        html_files.extend(subdir_files)

    return html_files
