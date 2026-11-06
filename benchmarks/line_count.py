"""Count the lines of a benchmark solution under the counting rules in BENCHMARKS.md."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass

from benchmarks._types import PythonFormatter, SourceKind

# The formatter decides how many lines a statement takes, so its version is pinned and recorded.
RUFF_VERSION = "0.17.4"
LOCAL_SERVER_MARKER = re.compile(r"\s*#\s*127\.0\.0\.1-only\s*$")


@dataclass(frozen=True)
class LineCount:
    """The counted lines of one file or command, and the lines left out of the count."""

    counted: int
    local_only: tuple[str, ...]


def _count_text_lines(text: str) -> LineCount:
    """Count non-blank, non-comment lines, setting aside lines needed only for 127.0.0.1."""
    counted = 0
    local_only: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if LOCAL_SERVER_MARKER.search(stripped):
            local_only.append(LOCAL_SERVER_MARKER.sub("", stripped))
        else:
            counted += 1
    return LineCount(counted, tuple(local_only))


def format_with_ruff(source: str, *, command: Sequence[str]) -> str:
    """Return Python source formatted by `ruff format` at 88 columns, ignoring project settings."""
    completed = subprocess.run(
        [*command, "format", "--isolated", "--stdin-filename", "solution.py", "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"ruff could not format the source: {completed.stderr.decode('utf-8')}")
    return completed.stdout.decode("utf-8")


def count_lines(text: str, kind: SourceKind, *, format_python: PythonFormatter) -> LineCount:
    """Count one file's lines: Python as formatted, JSON with two-space indentation, TOML as written."""
    if kind == "python":
        text = format_python(text)
    elif kind == "json":
        try:
            text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError as error:
            raise ValueError(f"not valid JSON: {error}") from error
    # shortcut: TOML is counted as written, so an inline table can hide keys; one key per line is on the author.
    return _count_text_lines(text)
