"""Write files the way the harness always does: atomically, creating the folder."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomically(destination: Path, contents: bytes) -> None:
    """Write a file by replacing it only once the new contents are complete on disk."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
    ) as temporary:
        temporary.write(contents)
        temporary.flush()
        os.fsync(temporary.fileno())
    Path(temporary.name).replace(destination)
