"""Read and write the committed results files, one per tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from benchmarks._types import ToolResult
from benchmarks.files import write_atomically
from benchmarks.paths import RESULTS_DIRECTORY


def load_results() -> dict[str, ToolResult]:
    """Return every committed results file, keyed by tool id."""
    # cast: the harness writes these files, and the report tests render every committed one.
    return {
        path.stem: cast(ToolResult, json.loads(path.read_text(encoding="utf-8")))
        for path in sorted(RESULTS_DIRECTORY.glob("*.json"))
    }


def write_result(tool_id: str, result: ToolResult) -> Path:
    """Write one tool's results file, and return its path."""
    destination = RESULTS_DIRECTORY / f"{tool_id}.json"
    # The trailing newline keeps reruns diffable; write_atomically ends lines with "\n" everywhere.
    contents = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    write_atomically(destination, contents.encode("utf-8"))
    return destination
